"""协议级测试：真 HTTP 服务器（非 mock 函数），锁死 E1（认证头）/E2（双后端）/E4（护栏作用域）。

这类测试的存在理由：mock 只验证"我调了哪个函数"，不验证"线上认识我"——
头、路径、端口、key 配置只有真协议回环才测得出来。
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp import tools  # noqa: E402
from vod_mcp import policy as policy_mod  # noqa: E402


class _Recorder(BaseHTTPRequestHandler):
    """记录每次请求的 method/path/headers/body，按路径回固定 JSON。"""
    requests = []

    def _handle(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _Recorder.requests.append({
            "method": self.command,
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": body.decode(),
        })
        responses = {
            "/api/vod/analyze/json": {"task_id": "wf001", "status": "pending"},
            "/api/vod/status/wf001": {"status": "running"},
            "/external/voice/submit":
                {"code": 200, "data": {"taskId": 9, "voiceId": "x", "status": "PENDING"}},
        }
        out = responses.get(self.path, {})
        payload = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_POST = do_GET = _handle

    def log_message(self, *a):  # 静音
        pass


@pytest.fixture()
def rec_server(monkeypatch):
    _Recorder.requests = []
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_port}"
    monkeypatch.setattr(tools, "WF_BASE", base)
    monkeypatch.setattr(tools, "WF_KEY", "wf-key-123")
    monkeypatch.setattr(tools, "JAVA_BASE", base)
    monkeypatch.setattr(tools, "JAVA_KEY", "java-key-456")
    yield base
    srv.shutdown()


def test_protocol_auth_header_and_paths(rec_server):
    """E1+E2：所有调用带正确 Bearer；workflow 工具走 WF 配置，提交走 Java 前缀路径。"""
    tools.run_analysis({"product": "codearts", "data": [{"voice": 1}], "confirmed": True})
    out = tools.submit_voices({"voices": [{"content": "太慢了，希望优化补全速度"}],
                               "product": "codearts", "confirmed": True},
                              client_info={"name": "aishell"})
    assert out["accepted"] == 1 and out["taskIds"] == [9]
    assert len(_Recorder.requests) == 2
    wf_req, java_req = _Recorder.requests
    assert wf_req["path"] == "/api/vod/analyze/json"
    assert wf_req["auth"] == "Bearer wf-key-123", "workflow 调用必须带 VOD_API_KEY（E1）"
    assert java_req["path"].endswith("/external/voice/submit"), java_req["path"]
    assert java_req["auth"] == "Bearer java-key-456", "Java 调用必须带 VOD_JAVA_API_KEY（E1/E2）"
    jb = json.loads(java_req["body"])
    assert jb["source"] == "aishell" and jb["product"] == "CodeArts"
    assert jb["voiceId"].startswith("ext_aishell_"), "voiceId 必须确定性生成"


def test_protocol_401_surfaces_key_hint(rec_server, monkeypatch):
    """E1：上游 401 时返回可诊断错误码 -32012。"""

    class _401(_Recorder):
        def _handle(self):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_GET = _handle

    _Recorder.requests = []
    srv = HTTPServer(("127.0.0.1", 0), _401)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(tools, "WF_BASE", f"http://127.0.0.1:{srv.server_port}")
    with pytest.raises(tools.ToolError) as ei:
        tools.run_analysis({"product": "codearts", "data": [], "confirmed": True})
    assert ei.value.code == -32012
    srv.shutdown()


# ---------- E4：护栏作用域（用户内容字段不进文本规则） ----------

def test_feedback_content_with_credential_words_not_killed():
    """用户反馈原文含 password = xxx（引用凭据现象）不得整批 deny。"""
    scoped = policy_mod.guard_scope({
        "voices": [{"content": "系统把我的 password = abc123 明文显示在日志里",
                    "scene": "登录"}], "confirmed": True})
    pol = policy_mod.load_policy()
    assert policy_mod.decide(
        policy_mod.check_text(pol, json.dumps(scoped, ensure_ascii=False)))[0] == "allow"


def test_structural_field_still_scanned():
    """结构性字段（scene）含 DB 直连意图仍然 deny——作用域收窄不是关掉护栏。"""
    scoped = policy_mod.guard_scope({
        "voices": [{"content": "正常反馈", "scene": "jdbc t_vod_ 直连"}], "confirmed": True})
    pol = policy_mod.load_policy()
    assert policy_mod.decide(
        policy_mod.check_text(pol, json.dumps(scoped, ensure_ascii=False)))[0] == "deny"


# ---------- G2：preset 分层 ----------

def test_presets_split_internal_external():
    """从 bin/vod-devkit 源码解析 PRESETS 字面量（无扩展名不可 import）。"""
    import ast
    src = (ROOT / "bin" / "vod-devkit").read_text(encoding="utf-8")
    presets = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
                getattr(t_, "id", "") == "PRESETS" for t_ in node.targets):
            presets = ast.literal_eval(node.value)
    assert presets, "bin/vod-devkit 缺 PRESETS 定义"
    assert "workflow" not in presets["collect"], "对外默认不得含分析发起（分层拍板）"
    assert "workflow" in presets["full"]
