"""认证与令牌链路测试：auth_status 指纹化（明文永不输出）+ 零字段令牌自动获取。"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp import tools  # noqa: E402


def test_auth_status_fingerprint_not_plaintext():
    out = tools.auth_status({}, client_info={"name": "t"})
    fp = out["javaKey"]["fingerprint"]
    assert fp is None or (len(fp) == 8 and fp != tools.JAVA_KEY), \
        "key 只能以 8 位指纹出现，明文禁止（fingerprint 纪律）"
    assert "packs" in out
    assert "workflowKey" not in out, "方案 A：单上游，无 workflowKey"


def test_auth_status_no_key_gives_guidance(monkeypatch):
    monkeypatch.setattr(tools, "JAVA_KEY", "")
    out = tools.auth_status({}, client_info={})
    assert out["javaKey"]["configured"] is False
    assert [g["order"] for g in out["guidance"]] == [1, 2, 3], \
        "缺 key 时必须给三步引导（令牌/升级/宿主）"
    assert "自动" in out["guidance"][0]["label"]


def test_submit_voices_auto_token_then_retry(monkeypatch):
    """零字段令牌链：无 key → 取令牌 → 落 runtime → 重试成功（用户无感）。"""
    calls = []
    state = {"token_issued": False}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls.append((method, path, key))
        if path.endswith("/external/token"):
            state["token_issued"] = True
            return {"token": "anon-token-xyz", "dailyLimit": 50}
        if path.endswith("/external/voice/submit"):
            if key == "anon-token-xyz":
                return {"code": 200, "data": {"taskId": 77, "status": "PENDING"}}
            raise tools.ToolError("鉴权失败：检查 key", code=-32012)
        return {}

    saved = {}

    def fake_save(update):
        saved.update(update)

    monkeypatch.setattr(tools, "JAVA_KEY", "")
    monkeypatch.setattr(tools, "_http", fake_http)
    monkeypatch.setattr(tools, "_save_runtime", fake_save)
    out = tools.submit_voices(
        {"voices": [{"content": "补全响应有点慢，希望优化一下"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1 and out["taskIds"] == [77]
    assert state["token_issued"], "必须先取令牌"
    assert saved.get("java_key") == "anon-token-xyz"
    assert saved.get("token_tier") == "anonymous"
    assert tools.JAVA_KEY == "anon-token-xyz", "令牌应回填运行时供后续复用"


def test_submit_voices_token_unreachable_gives_guidance(monkeypatch):
    """令牌端点不可用（引擎未上线）→ 结构化引导错误，不是死胡同。"""
    monkeypatch.setattr(tools, "JAVA_KEY", "")

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise tools.ToolError("上游返回 404: Not Found")

    monkeypatch.setattr(tools, "_http", fake_http)
    with pytest.raises(tools.ToolError) as ei:
        tools.submit_voices(
            {"voices": [{"content": "反馈内容足够长的一条意见"}], "confirmed": True},
            client_info={"name": "t"})
    assert "引导" in str(ei.value) and "自动" in str(ei.value), \
        "令牌不可用时错误必须带引导步骤"


def test_voice_volume_preserved_across_calls(monkeypatch):
    """R1 声量保真：不同调用提交同款反馈 → 不同 voiceId，各占一行。

    （曾为缺陷：确定性 voiceId 使第二个用户同款反馈被去重吞掉，
    声量统计失真——此测试为永久回归锁。）
    """
    seen = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        if path.endswith("/external/voice/submit"):
            seen.append(body["voiceId"])
            return {"code": 200, "data": {"taskId": len(seen)}}
        return {}

    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http", fake_http)
    voice = {"content": "补全响应有点慢，希望优化一下"}
    for _ in range(2):
        out = tools.submit_voices({"voices": [voice], "confirmed": True},
                                  client_info={"name": "mcp"})
        assert out["accepted"] == 1
    assert len(set(seen)) == 2, "同款反馈跨调用必须不去重（声量保真）"

    # title 必须是用户原文（R3：分析消费原话，后缀只允许出现在 description）
    def fake2(method, path, body=None, timeout=30, base=None, key=None):
        assert body["title"] == voice["content"], "title=用户原文，禁止模板污染"
        return {"code": 200, "data": {"taskId": 1}}
    monkeypatch.setattr(tools, "_http", fake2)
    tools.submit_voices({"voices": [voice], "confirmed": True},
                        client_info={"name": "mcp"})
