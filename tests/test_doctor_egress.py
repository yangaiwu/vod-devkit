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


# ── ARCH-CALL-06：可达性判定单一真源 ────────────────────────────────────────
#
# 旧实现两套状态机：`net.probe_key`（带 key）五态 vs `doctor._probe_engine`
# （不带 key）三态，且 doctor 手抄 URL、把 5xx 归成 unreachable（引擎故障被说成网络问题）。
# 修法：判定统一到 `net.probe_reachable`，doctor 只做展示层映射；路径单一真源 `net.META_PATH`。


def _stub_status(code: int):
    """独立 stub：固定返回某个 HTTP 状态码（原 `_serve(mode)` 只支持 ok/401 两档）。"""
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(code)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format, *args):  # noqa: D401
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_probe_reachable_maps_status_correctly():
    """net.probe_reachable 对 200/401/403/500/503 的判定。"""
    from vod_mcp import net
    for code, expect in ((200, "verified"), (401, "needs-auth"), (403, "needs-auth"),
                         (500, "server-error"), (503, "server-error")):
        srv, base = _stub_status(code)
        try:
            r = net.probe_reachable(base=base, timeout=3)
        finally:
            srv.shutdown()
        assert r["reason"] == expect, f"HTTP {code}: {r}"
        assert r["status"] == code, f"HTTP {code} 的原始码丢了：{r}"


def test_5xx_is_server_error_not_unreachable():
    """5xx 是引擎自身故障，**不是**网络不可达（旧 doctor 把它说成网络问题）。"""
    from vod_mcp import net
    srv, base = _stub_status(503)
    try:
        r = net.probe_reachable(base=base, timeout=3)
    finally:
        srv.shutdown()
    assert r["reason"] == "server-error"
    assert r["reason"] != "unreachable"
    assert r["ok"] is None, "故障不等于不通，ok 必须是 None"


def test_doctor_probe_uses_net_semantics(monkeypatch):
    """桩住 net.probe_reachable 后 doctor 必须跟着走——不许再自己发请求。"""
    from vod_mcp import net
    seen = {}

    def fake(base=None, timeout=4):
        seen["called"] = True
        return {"ok": None, "reason": "server-error", "status": 503}

    monkeypatch.setattr(net, "probe_reachable", fake)
    state, detail = doctor._probe_engine("https://example.test")
    assert seen.get("called"), "doctor 没走 net.probe_reachable（又自己发请求了）"
    assert state == "server-error" and "503" in detail and "引擎故障" in detail


def test_doctor_maps_all_net_reasons(monkeypatch):
    """net 的每种 reason 在 doctor 都有确定的展示层映射。"""
    from vod_mcp import net
    mapping = {"verified": "ok", "needs-auth": "auth",
               "server-error": "server-error", "unreachable": "unreachable"}
    for reason, expect in mapping.items():
        monkeypatch.setattr(net, "probe_reachable",
                            lambda base=None, timeout=4, _r=reason: {"ok": None, "reason": _r, "status": 500})
        state, detail = doctor._probe_engine("https://example.test")
        assert state == expect, f"{reason} -> {state}，期望 {expect}"
        assert detail, f"{reason} 无 detail"


def test_meta_path_has_one_source():
    """三处曾各自硬编码 meta 路径，现在必须只剩 net 一处定义。"""
    from pathlib import Path
    from vod_mcp import net
    src = Path(__file__).resolve().parent.parent / "src"
    hits = []
    for f in src.rglob("*.py"):
        if f.name == "net.py":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if ("/rest/developer" in line) and ("external/meta" in line):
                hits.append(f"{f.relative_to(src)}:{i}")
    assert not hits, f"还有硬编码的 meta 路径：{hits}"
    assert net.API_PREFIX + "/external/meta" == net.META_PATH
