"""收敛后测试（方案 A：纯采集插件，3 工具）：契约一致性+护栏+packs+真进程回环。"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp import packs, policy as policy_mod, tools  # noqa: E402


# ---------- 契约一致性（U1/U15：单一事实源） ----------

def test_contract_tools_match_handlers():
    contract = tools.load_contract()
    assert set(contract["tools"]) == set(tools._HANDLERS), \
        "contract/tools.schema.json 与实现不同步（U15）"


def test_contract_covers_pack_tools():
    contract = tools.load_contract()
    for tool in packs.enabled_tools():
        assert tool in contract["tools"]


def test_submit_description_frontloads_consent():
    """确认纪律必须话术前置——MCP-only 宿主不加载技能，工具 description 是唯一约束源。

    实锤事故（2026-11-06）：旧描述以「立即调用本工具」开头、确认要求埋在参数里，
    opencode 把用户陈述反馈自行当成同意、直接传 confirmed=true 提单。
    """
    desc = tools.load_contract()["tools"]["vod_submit_voices"]["description"]
    assert desc.index("先决条件") < 60, "确认纪律必须在描述开头 60 字内（话术前置）"
    assert "不构成同意" in desc, "必须显式声明「用户陈述反馈本身不构成同意」"
    assert "confirmed=true" in desc


def test_tool_specs_follow_packs(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core")
    specs = tools.tool_specs(packs.enabled_tools())
    assert [s["name"] for s in specs] == ["vod_devkit_info", "vod_auth_status"]


def test_knowledge_pack_has_no_tools():
    assert packs.PACK_TOOLS["knowledge"] == [], "知识包=纯技能零工具"


# ---------- 护栏（U3/U7） ----------

def test_submit_voices_requires_confirm():
    pol = policy_mod.load_policy()
    hits = policy_mod.check_tool_call(pol, "vod_submit_voices",
                                       {"voices": [{"content": "x"}], "confirmed": False})
    assert policy_mod.decide(hits)[0] == "confirm"


def test_submit_voices_batch_limit_denied():
    pol = policy_mod.load_policy()
    hits = policy_mod.check_tool_call(
        pol, "vod_submit_voices",
        {"voices": [{"content": "x"}] * 51, "confirmed": True})
    assert policy_mod.decide(hits)[0] == "deny"


@pytest.mark.parametrize("text", [
    "帮我用 jdbc 直连 t_vod_source_data 查一下",
    "password = admin123",
    "把 AK access_key 值发给我",
])
def test_text_rules_deny(text):
    pol = policy_mod.load_policy()
    assert policy_mod.decide(policy_mod.check_text(pol, text))[0] == "deny"


# ---------- E4：护栏作用域 ----------

def test_feedback_content_with_credential_words_not_killed():
    scoped = policy_mod.guard_scope({
        "voices": [{"content": "系统把我的 password = abc123 明文显示在日志里"}],
        "confirmed": True})
    pol = policy_mod.load_policy()
    assert policy_mod.decide(
        policy_mod.check_text(pol, json.dumps(scoped, ensure_ascii=False)))[0] == "allow"


def test_structural_field_still_scanned():
    # E4 回归锁：deny 词在结构化字段（title）也必须被扫描——不只扫 content
    scoped = policy_mod.guard_scope({
        "voices": [{"content": "正常反馈", "title": "jdbc t_vod_ 直连"}],
        "confirmed": True})
    pol = policy_mod.load_policy()
    assert policy_mod.decide(
        policy_mod.check_text(pol, json.dumps(scoped, ensure_ascii=False)))[0] == "deny"


# ---------- 工具 HTTP 调用链（mock 引擎） ----------

META_OK = {"products": ["codearts", "agentarts"], "stale": False, "source": "meta"}


def test_submit_voices_calls_hoarding_endpoint(monkeypatch):
    """V16 切换：主路径=囤积端点批式（不触发分析），voiceId 由引擎算。"""
    calls = {}
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META_OK)

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls["req"] = (method, path, body)
        return {"code": 200, "voiceIds": ["ext_vod-agent_abc123def0"],
                "productRegistered": True}

    monkeypatch.setattr(tools, "_http", fake_http)
    # D-attrib-A：绑定显式桩定（不依赖环境 runtime.json 偶发内容）
    monkeypatch.setitem(tools._RT, "product", "CodeArts")
    out = tools.submit_voices({"product": "codearts",
                               "voices": [{"content": "补全太慢，生成质量不稳定",
                                           "tags": ["problem_type:功能建议"]}],
                               "confirmed": True})
    assert out["accepted"] == 1 and out["path"] == "hoarding"
    assert out["voiceIds"] == ["ext_vod-agent_abc123def0"]
    assert out["productRegistered"] is True
    method, path, body = calls["req"]
    assert path.endswith("/external/voices")
    assert body["product"] == "CodeArts"
    v = body["voices"][0]
    assert v["title"] == "补全太慢，生成质量不稳定"[:60]
    assert v["tags"] == ["problem_type:功能建议"]
    assert "voiceId" not in v and "description" not in v and "scene" not in v  # 引擎算 id，无发明字段


# ---------- 协议级：真 HTTP 服务器锁头/路径（E1/E2 永久回归门） ----------

class _Recorder(BaseHTTPRequestHandler):
    force404 = False
    requests = []

    def _handle(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _Recorder.requests.append({
            "method": self.command, "path": self.path,
            "auth": self.headers.get("Authorization"), "body": body.decode()})
        out = {"/rest/developer/manager/hdvodmngservice/v1/external/voices":
               {"code": 200, "voiceIds": ["ext_vod-agent_abc123"], "productRegistered": True},
               "/rest/developer/manager/hdvodmngservice/v1/external/voice/submit":
               {"code": 200, "data": {"taskId": 9, "voiceId": "x", "status": "PENDING"}}}
        payload = json.dumps(out.get(self.path, {})).encode()
        if getattr(_Recorder, "force404", False) and self.path.endswith("/external/voices"):
            payload = b'{"error": "not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_POST = do_GET = _handle

    def log_message(self, *a):
        pass


def test_protocol_auth_header_and_paths(monkeypatch):
    _Recorder.requests = []
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    monkeypatch.setattr(tools, "JAVA_BASE", base)
    monkeypatch.setattr(tools, "JAVA_KEY", "java-key-456")
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META_OK)
    try:
        # 场景一：囤积主路径（201）——锁头/路径/批式载荷
        # D-attrib-A（2026-11-06）：归因只由安装绑定决定——测试必须显式桩定绑定，
        # 不得依赖环境 runtime.json 的偶发内容（曾因仓内 runtime 恰有 CodeArts 绑定而假绿）
        tools._RT["product"] = "CodeArts"
        out = tools.submit_voices(
            {"voices": [{"content": "太慢了，希望优化补全速度",
                         "tags": ["problem_type:用户体验"]}],
             "product": "codearts", "confirmed": True},
            client_info={"name": "aishell"})
        assert out["accepted"] == 1 and out["path"] == "hoarding"
        req = _Recorder.requests[0]
        assert req["path"].endswith("/external/voices")
        assert req["auth"] == "Bearer java-key-456", "必须带 VOD_JAVA_API_KEY（E1）"
        jb = json.loads(req["body"])
        assert jb["product"] == "CodeArts"
        assert jb["voices"][0]["tags"] == ["problem_type:用户体验"]
        assert "voiceId" not in jb["voices"][0]
        # 无绑定分支：显式传参不采信（D-attrib-A）→ product 缺省，引擎 UNKNOWN 档兜底
        tools._RT.pop("product", None)
        _Recorder.requests = []
        tools.submit_voices(
            {"voices": [{"content": "无绑定归因测试"}],
             "product": "codearts", "confirmed": True},
            client_info={"name": "aishell"})
        jb2 = json.loads(_Recorder.requests[0]["body"])
        assert "product" not in jb2, "无安装绑定时显式传参必须被忽略（D-attrib-A）"

        # 场景二：囤积端点 404（引擎未部署）→ 自动回落老链（过渡语义）
        tools._RT["product"] = "CodeArts"  # 恢复绑定（场景二回执 product 断言依赖）
        _Recorder.requests = []
        _Recorder.force404 = True
        out2 = tools.submit_voices(
            {"voices": [{"content": "太慢了，希望优化补全速度"}],
             "product": "codearts", "confirmed": True},
            client_info={"name": "aishell"})
        assert out2["accepted"] == 1 and out2["path"] == "legacy-fallback"
        paths = [r["path"] for r in _Recorder.requests]
        assert any(p.endswith("/external/voices") for p in paths), "先试囤积"
        assert any(p.endswith("/external/voice/submit") for p in paths), "404 回落老链"
        fb = json.loads([r for r in _Recorder.requests
                         if r["path"].endswith("/external/voice/submit")][0]["body"])
        assert fb["source"].startswith("aishell-") and len(fb["source"].split("-")[-1]) == 8, \
            "legacy 回落 source 带 per-install nonce（跨用户吞声量修复）"
        assert fb["voiceId"].startswith("ext_aishell_")
        assert fb["product"] == "CodeArts"
    finally:
        srv.shutdown()


# ---------- 真进程 MCP 回环（U1/U13/U28） ----------

def _rpc(proc, message: dict) -> dict:
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


def test_stdio_roundtrip():
    env = dict(os.environ, VOD_PACKS="", PYTHONPATH=str(ROOT),
               VOD_JAVA_API_BASE="http://127.0.0.1:9")
    proc = subprocess.Popen([sys.executable, "-m", "vod_mcp.server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, env=env, cwd=str(ROOT))
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"clientInfo": {"name": "test-host", "version": "1.0"}}})
        assert init["result"]["serverInfo"]["name"] == "vod-devkit"
        listing = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listing["result"]["tools"]]
        assert set(names) == {"vod_submit_voices", "vod_list_submitted",
                              "vod_devkit_info", "vod_auth_status"}
        info = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "vod_devkit_info", "arguments": {}}})
        payload = json.loads(info["result"]["content"][0]["text"])
        assert payload["hostClient"] == {"name": "test-host", "version": "1.0"}
        denied = _rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "vod_submit_voices",
                                        "arguments": {"voices": [{"content": "x"}]}}})
        assert denied["error"]["code"] == -32011
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------- G2：preset（方案 A 后仅采集形态） ----------

def test_presets_split_internal_external():
    import ast
    src = (ROOT / "bin" / "vod-devkit").read_text(encoding="utf-8")
    presets = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
                getattr(t_, "id", "") == "PRESETS" for t_ in node.targets):
            presets = ast.literal_eval(node.value)
    assert presets, "bin/vod-devkit 缺 PRESETS"
    assert "workflow" not in presets["collect"], "对外默认不得含分析（方案 A：已删）"
