"""会话内能力包开关（S132-S133，D-packs-configure-1）。

对齐 huaweicloud-devkit 的 `packs_configure`：stdio 会话内改工具面，并推
`notifications/tools/list_changed` 让合规客户端重拉 tools/list。

三条边界（都是"不制造第二种真相"）：
- 只改进程内状态：**不写 env、不写宿主配置**（持久化面是 CLI `packs … --apply`）；
- 远程面不给：HTTP 面每请求现造 server、无会话，开关会在下一个请求消失；
- 安全门禁不被绕过：采集熔断期间 enable collect 直接拒绝（不是静默摘掉）。
"""
import json

import pytest

from vod_mcp import packs, server, tools


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch):
    """每个用例从 VOD_PACKS 的启动态开始，用例之间不串会话内开关。"""
    monkeypatch.setenv("VOD_PACKS", "core,collect")
    packs.set_runtime_packs(None)
    yield
    packs.set_runtime_packs(None)


def _call(name, args):
    return server.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})


def _body(out):
    """tool 响应可能被通知包成 list（changed=True 时），统一取出响应体。"""
    resp = out[0] if isinstance(out, list) else out
    return resp["result"]["structuredContent"]


def _tool_names():
    return [t["name"] for t in tools.tool_specs(packs.enabled_tools())]


# ── S132 会话内开关 ──────────────────────────────────────

def test_s132_disable_shrinks_tool_surface():
    before = _tool_names()
    out = _call("vod_packs_configure", {"disable": ["collect"]})
    body = _body(out)
    assert body["removed"] == ["collect"] and body["changed"] is True
    assert body["persisted"] is False, "会话内开关不得声称已持久化"
    after = _tool_names()
    assert "vod_submit_voices" not in after
    assert set(after) < set(before)


def test_s132_enable_brings_it_back_and_core_is_forced():
    _call("vod_packs_configure", {"disable": ["knowledge"]})
    out = _call("vod_packs_configure", {"enable": ["knowledge", "core"]})
    body = _body(out)
    assert "knowledge" in body["packs"] and body["packs"][0] == "core"
    assert "vod_list_skills" in _tool_names()


def test_s132_reset_returns_to_vod_packs(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core")
    packs.set_runtime_packs(None)
    _call("vod_packs_configure", {"enable": ["collect"]})
    assert "vod_submit_voices" in _tool_names()
    out = _call("vod_packs_configure", {"reset": True})
    assert _body(out)["packs"] == ["core"]
    assert "vod_submit_voices" not in _tool_names()


def test_s132_unknown_pack_is_an_error_not_a_silent_filter():
    out = _call("vod_packs_configure", {"enable": ["bogus"]})
    resp = out[0] if isinstance(out, list) else out
    assert resp["error"]["code"] == -32602
    assert "bogus" in resp["error"]["message"]


def test_s132_empty_request_is_rejected():
    out = _call("vod_packs_configure", {})
    resp = out[0] if isinstance(out, list) else out
    assert resp["error"]["code"] == -32602


def test_s132_circuit_breaker_cannot_be_bypassed(tmp_path, monkeypatch):
    """熔断是安全门禁：会话内 enable collect 必须拒绝（-32015），且状态不变。"""
    marker = tmp_path / "vod-collect-suspended.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(packs, "BREAKER_MARKERS", (str(marker),))
    packs.set_runtime_packs(None)
    assert "collect" not in packs.effective_packs(), "VOD_PACKS=core,collect 会被熔断摘掉"
    out = _call("vod_packs_configure", {"enable": ["collect"]})
    resp = out[0] if isinstance(out, list) else out
    assert resp["error"]["code"] == -32015
    assert "熔断" in resp["error"]["message"]
    assert "collect" not in packs.effective_packs()


def test_s132_no_env_or_config_write(monkeypatch, capsys):
    import os
    before = dict(os.environ)
    _call("vod_packs_configure", {"disable": ["knowledge"]})
    assert os.environ.get("VOD_PACKS") == before.get("VOD_PACKS"), "不许改 env"
    assert os.environ == before


# ── S133 协议面：通知 + 远程面摘除 ────────────────────────

def test_s133_capabilities_declare_list_changed():
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"clientInfo": {"name": "t"}}})
    assert init["result"]["capabilities"]["tools"]["listChanged"] is True


def test_s133_changed_surface_emits_a_notification():
    out = _call("vod_packs_configure", {"disable": ["collect"]})
    assert isinstance(out, list) and len(out) == 2, "响应后必须跟一条通知"
    assert out[0]["id"] == 7 and "result" in out[0]
    assert out[1] == {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


def test_s133_no_change_emits_no_notification():
    _call("vod_packs_configure", {"disable": ["knowledge"]})
    again = _call("vod_packs_configure", {"disable": ["knowledge"]})
    assert isinstance(again, dict), "无变化不许发通知（避免客户端重拉风暴）"
    assert again["result"]["structuredContent"]["changed"] is False


def test_s133_stdio_writes_notification_as_its_own_line(tmp_path):
    """真 stdio：同一次调用要在 stdout 上出现两行（响应 + 通知）。"""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"clientInfo": {"name": "t"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "vod_packs_configure",
                    "arguments": {"disable": ["collect"]}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    ]
    r = subprocess.run([sys.executable, str(root / "src" / "vod_mcp" / "server.py")],
                       input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, timeout=90,
                       env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
                            "VOD_PACKS": "core,collect"})
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    methods = [m.get("method") for m in lines]
    assert "notifications/tools/list_changed" in methods
    listed = next(m for m in lines if m.get("id") == 3)["result"]["tools"]
    names = [t["name"] for t in listed]
    assert "vod_submit_voices" not in names, "通知之后的 tools/list 必须反映新区面"


def test_s133_remote_surface_withholds_the_switch():
    assert "vod_packs_configure" in packs.REMOTE_WITHHELD
    spec_names = [t["name"] for t in
                  tools.tool_specs(packs.enabled_tools(remote=True))]
    assert "vod_packs_configure" not in spec_names, "远程面每请求现造 server，开关无意义"


def test_s133_contract_has_the_tool():
    from vod_mcp import tools as t
    spec = t.load_contract()["tools"]["vod_packs_configure"]
    assert set(spec["input"]["properties"]) == {"enable", "disable", "reset"}
    assert "stdio" in spec["description"]