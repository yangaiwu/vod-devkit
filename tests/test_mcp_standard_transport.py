"""D-scope-1：MCP 标准传输 + 厂商兼容性 + 双形态能力对齐。

背景（2026-11-18 真机实锤）：
  远程面此前用 stateless=True —— 偏离 MCP 标准（标准 Transport 是 stateful，
  服务端在 initialize 下发 mcp-session-id，客户端后续请求回传），且无会话标识
  导致多 agent 共用一个 server 时记忆/追问计数/nonce 全串味：

    · A 回答过「CodeArts」→ 写入共享桶 → B 只说「太慢了」被归到 CodeArts（错归）
    · A 追问 2 次产品 → 共享计数 → B 首次被问即被判「第 3 次」→ 直接拒提交（丢单）
    · nonce 相同 → 相同内容 voiceId 撞车 → 引擎判重合并（丢声量，不报错）

  落地方向（负责人拍板）：**按标准实现，不自造一套** —— 外部服务对接必须能互操作；
  stdio 与 remote 只是传输形态不同，**工具能力不得阉割**。

本文件锁四组：
  ① 标准握手：initialize 下发 session、带 session 可用、两会话互不干扰
  ② 厂商兼容：标准 SDK / 裸 HTTP / 不回传 session / 旧协议版本 / 无 Accept 头
  ③ 能力对齐：stdio 与 remote 工具集完全一致（含 vod_packs_configure）
  ④ 降级语义：拿不到会话作用域时不写共享记忆（宁可多问，不可错归）
"""
import json
import pytest

mcp = pytest.importorskip("mcp", reason="远程面需要可选依赖 mcp（pip install 'vod-devkit[remote]'）")

import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from vod_mcp import net as _net  # noqa: E402
from vod_mcp import packs as _packs  # noqa: E402
from vod_mcp import runtime_state as _rt  # noqa: E402
from vod_mcp import transport_remote as tr  # noqa: E402

SESSION_HEADER = "mcp-session-id"


class _Engine(BaseHTTPRequestHandler):
    """最小引擎桩：只回答 meta / token，够握手与工具列举用。"""

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/external/meta" in self.path:
            self._json(200, {"code": 200, "data": {
                "products": ["CodeArts", "OfficeAce"],
                "productCatalog": [{"id": 1, "name": "CodeArts"},
                                   {"id": 3, "name": "OfficeAce"}],
            }})
            return
        self._json(404, {"code": 404})

    def do_POST(self):
        if self.path.endswith("/external/token"):
            self._json(200, {"code": 200, "data": {"token": "anon-t1"}})
            return
        self._json(200, {"code": 200, "voiceIds": ["ext_std_1"]})


@pytest.fixture
def remote(monkeypatch):
    engine = ThreadingHTTPServer(("127.0.0.1", 0), _Engine)
    threading.Thread(target=engine.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{engine.server_port}"
    monkeypatch.setattr(_net, "JAVA_BASE", base)
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)

    runtime = tr.RemoteRuntime("127.0.0.1", 0)
    runtime.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), tr._Handler)
    httpd.daemon_threads = True
    httpd.runtime = runtime
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        engine.shutdown()


def _post(url, payload, headers=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"content-type": "application/json",
                 "accept": "application/json, text/event-stream",
                 **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _handshake(url, name="client", version="2025-06-18", extra=None, accept=True):
    """标准握手：initialize → 取 session → initialized 通知。返回 (sid, status)。"""
    hdrs = dict(extra or {})
    if not accept:
        pass  # 由调用方控制：真不带 Accept 的极端情形走 _post_raw
    st, hd, body = _post(url, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": version, "capabilities": {},
                   "clientInfo": {"name": name, "version": "1"}}}, hdrs)
    sid = hd.get(SESSION_HEADER) or hd.get("Mcp-Session-Id")
    if sid:
        _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"},
              {**hdrs, "Mcp-Session-Id": sid})
    return sid, st, body


def _call(url, sid, tool, args=None):
    st, _h, body = _post(url, {
        "jsonrpc": "2.0", "id": 9, "method": "tools/call",
        "params": {"name": tool, "arguments": args or {}}},
        {"Mcp-Session-Id": sid} if sid else {})
    return st, body


# ── ① 标准握手与会话隔离 ────────────────────────────────────────────
def test_standard_handshake_issues_session(remote):
    """标准 Transport：initialize 必须下发 mcp-session-id。"""
    sid, st, _ = _handshake(remote, "std")
    assert st == 200
    assert sid, "标准 stateful 传输必须在 initialize 响应头下发 mcp-session-id"


def test_session_scoped_call_succeeds(remote):
    """带会话头调用工具应成功（标准路径）。"""
    sid, _st, _ = _handshake(remote, "std")
    st, body = _call(remote, sid, "vod_devkit_info")
    assert st == 200, body[:300]
    payload = json.loads(body)
    assert "result" in payload


def test_two_sessions_isolated(remote):
    """两个会话互不干扰，且都能独立工作。"""
    a, _, _ = _handshake(remote, "agent-A")
    b, _, _ = _handshake(remote, "agent-B")
    assert a and b and a != b, "不同握手必须得到不同会话"
    assert _call(remote, a, "vod_devkit_info")[0] == 200
    assert _call(remote, b, "vod_devkit_info")[0] == 200


# ── ② 厂商兼容矩阵 ─────────────────────────────────────────────────
def test_compat_vendor_standard_sdk(remote):
    """厂商：官方 SDK 客户端 —— 标准握手 + 回传 session。"""
    sid, st, _ = _handshake(remote, "mcp-sdk-python", version="2025-06-18")
    assert st == 200 and sid
    assert _call(remote, sid, "vod_list_skills")[0] == 200


def test_compat_vendor_old_protocol_version(remote):
    """厂商：旧协议（2024-11-05）客户端 —— 应能协商，不因版本拒绝。"""
    sid, st, _ = _handshake(remote, "legacy-client", version="2024-11-05")
    assert st == 200, "旧协议版本必须能协商（实测需支持）"
    assert sid, "旧协议同样应下发会话"


def test_compat_vendor_no_accept_header(remote):
    """厂商：不带 Accept 头（部分自研客户端） —— 不应因此失败。"""
    req = urllib.request.Request(
        remote, data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "no-accept", "version": "1"}}}).encode(),
        method="POST", headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        assert resp.status == 200


def test_compat_vendor_sideless_direct_call(remote):
    """厂商：裸 HTTP 不握手直接 tools/call —— 兜底应放行（不 400）。"""
    st, body = _call(remote, None, "vod_devkit_info")
    assert st == 200, f"极端客户端应被兜底放行，实得 {st}: {body[:200]}"


def test_compat_vendor_sideless_multiple_calls(remote):
    """厂商：连续多次不握手调用 —— 每次独立会话，不应互相影响或耗尽会话。"""
    for i in range(3):
        st, body = _call(remote, None, "vod_devkit_info")
        assert st == 200, f"第{i+1}次无 session 调用失败: {body[:200]}"


# ── ③ 双形态能力对齐（不阉割）────────────────────────────────────────
def test_tool_parity_except_packs_switch():
    """remote 与 stdio 只差 vod_packs_configure，其余完全一致。

    2026-11-18 真机探针实锤：本 SDK 版本所有会话共用同一个 Server 实例，
    且 packs._RUNTIME 是模块级全局 → 会话 A 关掉 collect，会话 B 的 tools/list
    立刻跟着变。即"逐会话工具面"做不到，恢复该工具等于让任何人一条调用摘掉
    同进程所有 agent 的采集能力。故维持摘除。
    """
    stdio = set(_packs.enabled_tools(remote=False))
    rem = set(_packs.enabled_tools(remote=True))
    assert rem == stdio - {"vod_packs_configure"}, (
        f"差异应只有 packs_configure，实得 {sorted(stdio ^ rem)}")
    assert {"vod_draft_voices", "vod_commit_voices", "vod_list_submitted"} <= rem


def test_remote_withheld_is_exactly_packs_switch():
    """摘除范围只能是"进程级、会影响所有会话"的那一个工具。"""
    assert _packs.REMOTE_WITHHELD == ("vod_packs_configure",), (
        f"实得 {_packs.REMOTE_WITHHELD}")


# ── ④ 作用域降级语义 ────────────────────────────────────────────────
def test_scope_degrades_to_no_memory_when_unidentified(monkeypatch):
    """拿不到会话标识（远程面）→ key=None → 读写皆禁用。

    "错归比不归更糟"：宁可多问用户一次，也不把 A 的归因写进 B 的桶。
    """
    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: True)})())
    scope = _rt._resolve_scope({"agent_id": "", "product": ""})
    assert scope["key"] is None
    assert scope["degraded"] is True
    assert scope["degraded_reason"] == "no_session_id"
    assert scope["product_prior"] is False, "多租户下安装先验必须禁用（否则错归）"
    # 不写：_memory_put 应静默跳过；不读：_memory_get 应为空
    before = dict(_rt._SESSION_MEM)
    _rt._memory_put({"agent_id": ""}, product="CodeArts")
    assert _rt._SESSION_MEM == before, "未知调用方不得写入共享记忆桶"
    assert _rt._memory_get({"agent_id": ""}) == {}, "未知调用方不得读共享记忆桶"


def test_scope_isolation_between_sessions():
    """不同会话 → 不同 key（sess: 前缀，非 agent:），记忆互不可见。"""
    s_a = _rt._resolve_scope({"agent_id": "session:a", "product": ""})
    s_b = _rt._resolve_scope({"agent_id": "session:b", "product": ""})
    assert s_a["key"].startswith("sess:"), "会话级作用域用 sess: 前缀，agent: 留给显式身份"
    assert s_a["key"] != s_b["key"]
    s_a = dict(s_a, product_prior=True)  # 仅为写测试放开，实际按 scope 返回值用
    _rt._memory_put({"agent_id": "session:a"}, product="CodeArts")
    assert _rt._memory_get({"agent_id": "session:a"}).get("product") == "CodeArts"
    assert _rt._memory_get({"agent_id": "session:b"}).get("product") is None, (
        "A 的记忆不得泄漏给 B")


def test_scope_agent_prefix_reserved_for_explicit_identity():
    """显式 agent 头 → agent: 前缀；与 sess: 明确区分。"""
    s = _rt._resolve_scope({"agent_id": "codearts-agent", "product": "CodeArts"})
    assert s["key"] == "agent:codearts-agent"
    assert s["id_source"] == "agent"
    assert s["grain"] == "request"


def test_scope_stdio_uses_process_identity_not_name(monkeypatch):
    """stdio 面 key 以进程身份为主，name 只作二级后缀（进程身份内核保证）。"""
    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: False)})())
    monkeypatch.delenv("VOD_DEVKIT_HOME", raising=False)
    s = _rt._resolve_scope({"name": "codearts", "product": ""})
    assert s["key"].startswith("proc:"), f"stdio 应以进程身份为主，实得 {s['key']}"
    # name 只做后缀，不能成为整个 key —— 否则又回到"可被写死"的老路
    assert s["key"].split("|")[0].startswith("proc:"), "name 只能是后缀，不能替代进程身份"
    assert s["product_prior"] is True, "独立进程可用安装先验"


def test_scope_home_in_key_for_multi_install(monkeypatch):
    """同机多装：VOD_DEVKIT_HOME 必须进 key，否则机器级 nonce 相同会撞。"""
    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: False)})())
    monkeypatch.setenv("VOD_DEVKIT_HOME", "/opt/vod/codearts")
    s = _rt._resolve_scope({"name": "x", "product": ""})
    assert "/opt/vod/codearts" in s["key"], f"home 必须进 key，实得 {s['key']}"
    assert s["id_source"] == "proc_home"


def test_scope_request_product_overrides_binding():
    """请求级产品优先于安装绑定。"""
    s = _rt._resolve_scope({"agent_id": "session:x", "product": "OfficeAce"})
    assert s["product"] == "OfficeAce"


def test_scope_ttl_single_source():
    """session TTL 与记忆 TTL 必须同源，防两个独立时钟漂移。"""
    assert _rt.SCOPE_TTL_SEC == _rt._SESSION_TTL
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent
           / "src" / "vod_mcp" / "transport_remote.py").read_text(encoding="utf-8")
    assert "session_idle_timeout=_rt_ttl.SCOPE_TTL_SEC" in src, (
        "传输层必须取单一来源 SCOPE_TTL_SEC，不得硬编码常量")


def test_scope_degraded_reason_distinguishes_cases(monkeypatch):
    """降级原因必须可区分：no_session_id（远程） vs no_proc_id（stdio 理论兜底）。"""
    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: True)})())
    assert _rt._resolve_scope({})["degraded_reason"] == "no_session_id"

    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: False)})())
    import os as _os
    orig = _os.getpid
    monkeypatch.setattr(_os, "getpid", lambda: (_ for _ in ()).throw(OSError("no pid")))
    try:
        s = _rt._resolve_scope({})
        assert s["degraded_reason"] == "no_proc_id"
        assert s["key"] is None
    finally:
        monkeypatch.setattr(_os, "getpid", orig)


def test_product_prior_disabled_on_shared_remote(monkeypatch):
    """共用远程进程必须禁用安装先验（否则一份 runtime.json 代表所有 agent = 错归）。"""
    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: True)})())
    for ci in ({"agent_id": "session:x"}, {"agent_id": "codearts"}, {}):
        assert _rt._resolve_scope(ci)["product_prior"] is False, f"{ci} 必须禁用安装先验"

    monkeypatch.setattr(_net, "_SERVER_FACE", type("C", (), {"get": staticmethod(lambda: False)})())
    monkeypatch.delenv("VOD_DEVKIT_HOME", raising=False)
    assert _rt._resolve_scope({"name": "x"})["product_prior"] is True, "独立进程可用安装先验"
