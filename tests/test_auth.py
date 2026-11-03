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
