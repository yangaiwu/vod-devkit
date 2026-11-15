"""doctor 出站面报告（S134，D-doctor-egress-1）。

两条都只**报告**、不 FAIL：
- 出站代理：尊重既有 HTTP env 约定（不建 proxy.json），代理 URL 里的口令必须掩码
  —— doctor 输出会被贴进工单/聊天，带口令的代理值等于泄密；
- 引擎可达：无 key 时此前没有任何网络结论（key 探针只在配了 key 时才跑）。
  401/403 也算可达（鉴权问题≠网络问题）；不可达只 warn，离线装机 doctor 仍可用。
"""
import http.server
import threading

from vodkit_cli import doctor


# ── S134 代理报告与掩码 ──────────────────────────────────

def test_s134_proxy_credentials_are_masked():
    out = doctor._mask_proxy("http://user:secret@proxy.corp:8080")
    assert "secret" not in out and "user" not in out
    assert out == "http://***:***@proxy.corp:8080"


def test_s134_proxy_summary_reflects_env(monkeypatch):
    for k in doctor._PROXY_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://u:p@10.0.0.1:3128")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    s = doctor._proxy_summary()
    assert "HTTPS_PROXY=http://***:***@10.0.0.1:3128" in s
    assert "NO_PROXY=127.0.0.1,localhost" in s


def test_s134_no_proxy_env_says_direct(monkeypatch):
    for k in doctor._PROXY_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert "出站直连" in doctor._proxy_summary()


# ── S134 引擎可达三态 ────────────────────────────────────

_STATE = {"mode": "ok"}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.endswith("/external/meta") and _STATE["mode"] == "ok":
            body = b'{"products": [], "dictVersion": "t"}'
            self.send_response(200)
        else:
            body = b'{"error": "unauthorized"}'
            self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: D401  静音测试日志
        pass


def _serve(mode="ok"):
    _STATE["mode"] = mode
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_s134_reachable_engine():
    srv, base = _serve("ok")
    try:
        state, detail = doctor._probe_engine(base, timeout=3)
    finally:
        srv.shutdown()
    assert state == "ok" and "HTTP 200" in detail


def test_s134_auth_response_still_counts_as_reachable():
    """401 = 网络通、鉴权不通。把 401 报成"不可达"会把排查方向带错。"""
    srv, base = _serve("auth")
    try:
        state, detail = doctor._probe_engine(base, timeout=3)
    finally:
        srv.shutdown()
    assert state == "auth" and "HTTP 401" in detail and "可达" in detail


def test_s134_dead_port_is_unreachable():
    state, detail = doctor._probe_engine("http://127.0.0.1:9", timeout=2)
    assert state == "unreachable" and detail


def test_s134_report_prints_proxy_and_engine_lines(monkeypatch, capsys):
    """报告面只增信息：两行都在，且不带 key 也不会缺网络结论。"""
    for k in doctor._PROXY_KEYS:
        monkeypatch.delenv(k, raising=False)
    srv, base = _serve("ok")
    try:
        doctor._report_egress(base)
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert "[doctor] 出站代理：未设" in out
    assert "[doctor] 引擎可达：HTTP 200" in out


def test_s134_unreachable_only_warns(monkeypatch, capsys):
    for k in doctor._PROXY_KEYS:
        monkeypatch.delenv(k, raising=False)
    doctor._report_egress("http://127.0.0.1:9")
    out = capsys.readouterr().out
    assert "warn: 引擎不可达" in out and "提交会失败" in out


def test_s134_missing_api_base_is_explicit(capsys):
    doctor._report_egress("")
    assert "未配置 apiBase" in capsys.readouterr().out