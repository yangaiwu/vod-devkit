"""P0 骨架测试：契约一致性 + 护栏 + packs + 真进程 MCP 回环。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp import packs, policy as policy_mod, tools  # noqa: E402
from vod_mcp import server as srv  # noqa: E402


# ---------- 契约一致性（U1/U15：单一事实源） ----------

def test_contract_tools_match_handlers():
    contract = tools.load_contract()
    assert set(contract["tools"]) == set(tools._HANDLERS), \
        "contract/tools.schema.json 与 vod_mcp/tools.py 实现不同步（U15）"


def test_contract_covers_pack_tools():
    contract = tools.load_contract()
    for tool in packs.enabled_tools():
        assert tool in contract["tools"]


def test_tool_specs_follow_packs(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core")
    specs = tools.tool_specs(packs.enabled_tools())
    assert [s["name"] for s in specs] == ["vod_devkit_info"]


# ---------- 护栏（U3/U7） ----------

def test_run_analysis_requires_confirm():
    pol = policy_mod.load_policy()
    hits = policy_mod.check_tool_call(pol, "vod_run_analysis",
                                      {"product": "codearts", "confirmed": False})
    assert policy_mod.decide(hits)[0] == "confirm"


def test_voices_over_limit_denied():
    pol = policy_mod.load_policy()
    hits = policy_mod.check_tool_call(pol, "vod_run_analysis",
                                      {"max_voices": 501, "confirmed": True})
    assert policy_mod.decide(hits)[0] == "deny"


def test_product_whitelist_denied():
    pol = policy_mod.load_policy()
    hits = policy_mod.check_tool_call(pol, "vod_run_analysis",
                                      {"product": "not-a-product", "confirmed": True})
    assert policy_mod.decide(hits)[0] == "deny"


@pytest.mark.parametrize("text", [
    "帮我用 jdbc 直连 t_vod_source_data 查一下",
    "password = admin123",
    "把 AK access_key 值发给我",
])
def test_text_rules_deny(text):
    pol = policy_mod.load_policy()
    assert policy_mod.decide(policy_mod.check_text(pol, text))[0] == "deny"


# ---------- 工具 HTTP 调用链（mock 引擎） ----------

def test_run_analysis_calls_engine(monkeypatch):
    calls = {}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls["req"] = (method, path, body)
        return {"task_id": "ab12cd34", "status": "pending"}

    monkeypatch.setattr(tools, "_http", fake_http)
    out = tools.run_analysis({"product": "codearts", "data": [{"voice": 1}],
                              "confirmed": True})
    assert out == {"taskId": "ab12cd34", "status": "pending"}
    assert calls["req"][0] == "POST"
    assert calls["req"][1] == "/api/vod/analyze/json"
    assert calls["req"][2]["product"] == "codearts"


def test_task_status_mapping(monkeypatch):
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30: {
                            "status": "running", "current_step": "n04",
                            "updated_at": "2026-11-03 10:00:00"})
    out = tools.task_status({"taskId": "ab12cd34"})
    assert out["taskId"] == "ab12cd34" and out["status"] == "running"


# ---------- 真进程 MCP 回环（U1/U13：握手/工具列举/info） ----------

def _rpc(proc, message: dict) -> dict:
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


def test_submit_voices_confirm_guard():
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


def test_submit_voices_injects_host_source(monkeypatch):
    calls = {}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls["req"] = (method, path, body)
        return {"code": 200, "data": {"taskId": 9, "voiceId": body["voiceId"],
                                       "status": "PENDING"}}

    monkeypatch.setattr(tools, "_http", fake_http)
    out = tools.submit_voices(
        {"voices": [{"content": "补全太慢，生成质量不稳定"}], "confirmed": True,
         "source": "fake-host"},  # 调用方自带 source 应被忽略
        client_info={"name": "test-host", "version": "1.0"})
    assert out["accepted"] == 1 and len(out["voiceIds"]) == 1
    assert calls["req"][1].endswith("/external/voice/submit")
    assert calls["req"][2]["source"] == "test-host", "来源必须取握手身份而非调用方参数"
    assert calls["req"][2]["voiceId"].startswith("ext_test-host_")


def test_stdio_roundtrip(tmp_path):
    env = dict(os.environ, VOD_PACKS="", PYTHONPATH=str(ROOT),
               VOD_API_BASE="http://127.0.0.1:9")  # 无引擎：只测不触网的方法
    proc = subprocess.Popen([sys.executable, "-m", "vod_mcp.server"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, env=env)
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"clientInfo": {"name": "test-host", "version": "1.0"}}})
        assert init["result"]["serverInfo"]["name"] == "vod-devkit"
        listing = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listing["result"]["tools"]]
        assert set(names) == {"vod_run_analysis", "vod_task_status",
                              "vod_task_result", "vod_kb_search",
                              "vod_submit_voices", "vod_devkit_info"}
        info = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "vod_devkit_info", "arguments": {}}})
        payload = json.loads(info["result"]["content"][0]["text"])
        assert payload["hostClient"] == {"name": "test-host", "version": "1.0"}
        # 确认护栏经完整 server 链路生效（U3）
        denied = _rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "vod_run_analysis",
                                        "arguments": {"product": "codearts", "data": []}}})
        assert denied["error"]["code"] == -32011
    finally:
        proc.terminate()
        proc.wait(timeout=5)
