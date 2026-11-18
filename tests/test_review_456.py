"""审查 ④⑤⑥：草稿归属、sideless 兜底会话池、agent 头格式（2026-11-19）。

背景（docs/review-456-analysis.md）：
  ④ 草稿 owner 用 `_session_key`（即 `_resolve_scope.key`），而 `X-Vod-Agent-Id`
     在该函数里**优先于** session → 带同一个 agent 头的另一个连接能提交别人的草稿。
  ⑤ 无 session 的裸请求每来一次就内部 initialize 一次 → 会话池 O(请求数) 增长，
     30 分钟内 5.6 req/s 即打满 SDK 的 10000 上限，之后**所有**客户端（含标准
     客户端）拿 503。
  ⑥ `X-Vod-Agent-Id` 自由头直接当分桶身份，无格式约束、可跨会话共享桶。
"""
import json

import pytest

mcp = pytest.importorskip("mcp", reason="远程面需要可选依赖 mcp")

from vod_mcp import net as _net          # noqa: E402
from vod_mcp import runtime_state as _rt  # noqa: E402
from vod_mcp.packs import collect as _collect  # noqa: E402


# ── ④ 草稿归属 ───────────────────────────────────────────────────────
def _stub_engine(monkeypatch, captured, voice_ids=None):
    voice_ids = voice_ids or ["v-draft-1"]

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        captured.append({"method": method, "path": path})
        return {"voiceIds": voice_ids, "rejected": []}

    monkeypatch.setattr(_net, "_http", fake_http)


@pytest.fixture()
def draft_env(tmp_path, monkeypatch):
    monkeypatch.setattr(_rt, "_runtime_path", lambda: tmp_path / "runtime.json")
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["CodeArts"], "stale": False,
                                             "source": "meta", "catalog": []})
    monkeypatch.setattr(_collect, "_allowed_tags", lambda product: set())
    captured = []
    _stub_engine(monkeypatch, captured)
    return captured


def test_draft_owner_ignores_agent_header(draft_env):
    """④ 冒用 `X-Vod-Agent-Id` 不得提交他人草稿（同 agent 头、不同会话）。

    真实链路：A（会话 sess-a + 头 X-Vod-Agent-Id: alice）暂存；
              C（会话 sess-c + 同一个头 alice）提交 → 必须 -32011。
    修复前：两者 _session_key 都是 agent:alice → 放行（静默越权）。
    """
    a = {"agent_id": "alice", "session_id": "sess-a"}
    c = {"agent_id": "alice", "session_id": "sess-c"}
    d = _collect.draft_voices({"voices": [{"content": "导出太慢了"}],
                               "product": "CodeArts"}, a)
    assert d["draftId"]

    with pytest.raises(_net.ToolError) as ei:
        _collect.commit_voices({"draftId": d["draftId"],
                                "approvalToken": d["approvalToken"]}, c)
    assert ei.value.code == -32011
    assert "不属于当前客户端" in str(ei.value)


def test_draft_owner_sees_session_change_as_own(draft_env):
    """④ 同一客户端**会话变了**（重连/重启）→ 话术要指向"重新暂存"，不是"别人"。

    两类原因必须分档：会话漂移 = 自己；跨 agent 无关会话 = 可疑。都回 -32011。
    """
    a = {"agent_id": "session:sess-old"}
    b = {"agent_id": "session:sess-new"}
    d = _collect.draft_voices({"voices": [{"content": "导出太慢了"}],
                               "product": "CodeArts"}, a)
    with pytest.raises(_net.ToolError) as ei:
        _collect.commit_voices({"draftId": d["draftId"],
                                "approvalToken": d["approvalToken"]}, b)
    msg = str(ei.value)
    assert ei.value.code == -32011
    assert "vod_draft_voices" in msg, f"会话漂移应提示重新暂存，实得：{msg}"


def test_draft_owner_same_session_still_commits(draft_env):
    """④ 同一会话提交照常成功（修复不能把正常路径也锁死）。"""
    a = {"agent_id": "session:sess-a"}
    d = _collect.draft_voices({"voices": [{"content": "导出太慢了"}],
                               "product": "CodeArts"}, a)
    out = _collect.commit_voices({"draftId": d["draftId"],
                                  "approvalToken": d["approvalToken"]}, a)
    assert out["accepted"] == 1


# ── ⑥ agent 头格式约束 ───────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["a" * 65, "alice\nx", "ali ce", "名字", "a;b"])
def test_agent_header_format_rejected_to_session(monkeypatch, bad):
    """⑥ 非法 agent 头必须忽略并降级到会话（不能直接当 key）。

    真实入参形态由 remote_app._req_scope 产出：agent_id 是 "session:<sid>"。
    """
    from vod_mcp import net as _n
    tok = _n._SERVER_FACE.set(True)          # 远程面才有 session 维度
    try:
        ci = _rt._resolve_scope({"agent_id": "session:s1", "session_id": "s1"})
        assert ci["key"] == "sess:s1", f"基线（无 agent 头）应为会话键，实得 {ci}"
        # remote_app 已把非法头清空 → agent_id 只剩会话形态
        ci = _rt._resolve_scope({"agent_id": "session:s1", "session_id": "s1",
                                 "raw_agent_id": bad})
        assert ci["key"] == "sess:s1", f"非法 agent 头应降级到会话，实得 {ci}"
        # 直连 _resolve_scope 时也必须自己拦（不依赖上游清洗）
        ci = _rt._resolve_scope({"agent_id": bad, "session_id": "s1"})
        assert ci["key"] != f"agent:{bad}", f"非法 agent 头不得进 key，实得 {ci}"
    finally:
        _n._SERVER_FACE.reset(tok)


def test_agent_header_format_accepted():
    """⑥ 合法 agent 头（字母数字 . _ : - ，≤64）仍作请求级身份。"""
    ci = _rt._resolve_scope({"agent_id": "codearts-01:bot", "session_id": "s1"})
    assert ci["key"] == "agent:codearts-01:bot"


# ── ⑤ sideless 兜底会话池 ────────────────────────────────────────────
class _StubManager:
    """只记账不建真会话：数内部握手次数（真 SDK 每次 initialize = 一个常驻会话）。"""

    def __init__(self):
        self.inits = 0
        self.calls = 0

    async def handle_request(self, scope, receive, send):
        body = await receive()
        payload = json.loads(body["body"])
        if payload.get("method") == "initialize":
            self.inits += 1
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"mcp-session-id", f"sid-{self.inits}".encode())]})
            await send({"type": "http.response.body", "body": b"{}"})
            return
        self.calls += 1
        hdrs = {k.decode(): v.decode() for k, v in scope.get("headers") or []}
        self.last_sid = hdrs.get("mcp-session-id")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _sideless_scope(method="tools/call"):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": {"name": "vod_devkit_info", "arguments": {}}}).encode()
    return {"headers": [(b"content-type", b"application/json")], "_vod_body": body,
            "path": "/mcp"}


def test_sideless_reuses_single_sentinel_session():
    """⑤ 连续 N 次无 session 调用只应建 1 个会话（哨兵复用），而不是 N 个。"""
    import asyncio
    from vod_mcp import transport_remote as _tr

    _tr._reset_sideless_state()
    mgr = _StubManager()

    async def run():
        for _ in range(5):
            await _tr._ensure_session_for_sideless(mgr, _sideless_scope())

    asyncio.run(run())
    assert mgr.inits == 1, f"哨兵复用后应只握手 1 次，实得 {mgr.inits}（每次新建=会话池被打满）"


def test_sideless_sentinel_carries_scope_key_none():
    """⑤ 复用哨兵会话后，业务侧作用域仍必须是 key=None（不得变成全员一桶）。"""
    import asyncio
    from vod_mcp import transport_remote as _tr

    _tr._reset_sideless_state()
    mgr = _StubManager()

    async def run():
        scope = await _tr._ensure_session_for_sideless(mgr, _sideless_scope())
        return scope

    scope = asyncio.run(run())
    assert scope is not None
    hdrs = {k.decode(): v.decode() for k, v in scope.get("headers") or []}
    # 兜底路径必须显式打标：remote_app._req_scope 据此强制降级
    assert hdrs.get("x-vod-sideless") == "1", "哨兵会话必须打 sideless 标，否则会被当普通会话分桶"
    ci = {"agent_id": "session:sid-1", "session_id": "sid-1", "sideless": True}
    resolved = _rt._resolve_scope(ci)
    assert resolved["key"] is None, f"sideless 会话不得产出隔离键，实得 {resolved}"
    assert resolved["degraded_reason"] == "no_session_id"


def test_sideless_sentinel_invalidated_rebuilds_once():
    """⑤ 哨兵失效（被回收）后应重建一次并继续复用，不退回每请求新建。"""
    import asyncio
    from vod_mcp import transport_remote as _tr

    _tr._reset_sideless_state()
    mgr = _StubManager()

    async def run_first():
        await _tr._ensure_session_for_sideless(mgr, _sideless_scope())

    asyncio.run(run_first())
    _tr._reset_sideless_state(keep_sid="sid-stale")   # 模拟：登记的 sid 已被 TTL 回收

    async def run_rest():
        for _ in range(4):
            await _tr._ensure_session_for_sideless(mgr, _sideless_scope())

    asyncio.run(run_rest())
    assert mgr.inits == 2, f"失效后应只重建 1 次，实得 {mgr.inits}"


def test_standard_client_path_untouched():
    """⑤ 带 session 的请求走标准路径，不得被兜底逻辑改写。"""
    import asyncio
    from vod_mcp import transport_remote as _tr

    _tr._reset_sideless_state()
    mgr = _StubManager()
    scope = _sideless_scope()
    scope["headers"] = scope["headers"] + [(b"mcp-session-id", b"std-1")]

    async def run():
        return await _tr._ensure_session_for_sideless(mgr, scope)

    assert asyncio.run(run()) is None, "标准客户端必须返回 None（原样交给 manager）"
    assert mgr.inits == 0
