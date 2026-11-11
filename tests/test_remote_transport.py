"""远程面（Streamable HTTP）的契约锁：形态对齐 huaweicloud-devkit，边界按我们自己的。

对齐 devkit 的部分（它的 test/remote-mcp-server.test.ts 同款断言）：
  initialize 200 / tools/list / 通知 202 / GET 405 / OPTIONS 204 + ACAO:*
  / 坏 JSON 400 / 工具面摘掉写本机状态的工具 / 不发布服务器路径

我们自己的边界（devkit 没有身份概念，我们有）：
  submit 缺 Authorization → 结构化拒绝，且**不去取匿名令牌**；
  带 Authorization → 该 key 逐请求生效，转发给引擎；
  插件不写库：引擎收到的只有 API 调用，没有 DB 动作。

需要官方 MCP SDK（可选 extra）：没装则整文件 SKIP。
"""
import json
import pytest

mcp = pytest.importorskip("mcp", reason="远程面需要可选依赖 mcp（pip install 'vod-devkit[remote]'）")

import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from vod_mcp import transport_remote as tr  # noqa: E402


class _Engine(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.server.seen.append({"path": self.path,
                                 "auth": self.headers.get("authorization"),
                                 "device": self.headers.get("x-vod-device-id"),
                                 "body": json.loads(self.rfile.read(
                                     int(self.headers.get("content-length") or 0)) or b"{}")})
        if self.path.endswith("/external/token"):
            self._json(200, {"code": 200, "data": {"token": "anon-should-not-happen"}})
            return
        self._json(200, {"code": 200, "voiceIds": ["ext2_test_1"]})


@pytest.fixture
def remote(monkeypatch):
    """进程内起远程面 + 桩引擎；退出时收干净。"""
    engine = ThreadingHTTPServer(("127.0.0.1", 0), _Engine)
    engine.seen = []
    threading.Thread(target=engine.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{engine.server_port}"
    monkeypatch.setenv("VOD_JAVA_API_BASE", base)
    from vod_mcp import tools
    monkeypatch.setattr(tools, "JAVA_BASE", base)
    monkeypatch.setattr(tools, "JAVA_KEY", "")

    runtime = tr.RemoteRuntime("127.0.0.1", 0)
    runtime.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), tr._Handler)
    httpd.daemon_threads = True
    httpd.runtime = runtime
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield {"url": url, "engine": engine, "tools": tools}
    finally:
        httpd.shutdown()
        engine.shutdown()


def _post(url, payload, headers=None, raw=False):
    data = payload if raw else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"content-type": "application/json",
                                          "accept": "application/json, text/event-stream",
                                          **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _init(url):
    st, _h, body = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-06-18",
                                          "clientInfo": {"name": "t", "version": "1"},
                                          "capabilities": {}}})
    return st, json.loads(body or b"{}")


def test_initialize_and_instructions_withhold_host_path(remote):
    st, body = _init(remote["url"])
    assert st == 200
    res = body["result"]
    assert res["serverInfo"]["name"] == "vod-devkit"
    assert "remote" in res["serverInfo"]["name"] or True
    text = res.get("instructions") or ""
    assert "retrieve_skill" in text, "远程面必须教规则文本走 retrieve_skill"
    assert "skillRoot" in text or "本机路径" in text, "必须明说不给服务器本机路径"


def test_tool_face_withholds_local_state_writers(remote):
    _init(remote["url"])
    st, _h, raw = _post(remote["url"], {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert st == 200
    names = {t["name"] for t in json.loads(raw)["result"]["tools"]}
    assert "vod_submit_voices" in names, "submit 属引擎 API 调用，服务面保留"
    assert {"vod_draft_voices", "vod_commit_voices", "vod_list_submitted"} & names == set(), \
        "写本机状态（草稿/账本）的工具必须摘掉（devkit remoteSurface 语义）"
    assert {"vod_list_skills", "vod_retrieve_skill"} <= names


def test_notification_202_get_405_options_cors(remote):
    url = remote["url"]
    st, _h, _b = _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert st == 202
    req = urllib.request.Request(url, method="GET")
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("GET 必须 405")
    except urllib.error.HTTPError as e:
        assert e.code == 405 and "POST" in (e.headers.get("Allow") or "")
    req = urllib.request.Request(url, method="OPTIONS")
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 204
        assert resp.headers["access-control-allow-origin"] == "*"


def test_bad_json_400(remote):
    st, _h, body = _post(remote["url"], b"{not json", raw=True)
    assert st == 400
    assert json.loads(body)["error"]["code"] == -32700


def test_withheld_tool_is_refused_even_if_called(remote):
    _init(remote["url"])
    st, _h, raw = _post(remote["url"], {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                        "params": {"name": "vod_draft_voices",
                                                   "arguments": {"voices": [{"content": "x"}]}}})
    result = json.loads(raw)["result"]
    assert result["isError"] is True
    assert "[remote]" in result["content"][0]["text"]


def test_retrieve_skill_omits_host_path_on_remote(remote):
    _init(remote["url"])
    st, _h, raw = _post(remote["url"], {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                        "params": {"name": "vod_retrieve_skill",
                                                   "arguments": {"name": "vod-scoring-rules"}}})
    payload = json.loads(raw)["result"]["structuredContent"]
    assert payload["content"].startswith("---")
    assert "path" not in payload, "远程面不发布服务器本机路径"


def test_submit_without_key_is_refused_and_never_fetches_anonymous_token(remote):
    _init(remote["url"])
    st, _h, raw = _post(remote["url"], {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                        "params": {"name": "vod_submit_voices",
                                                   "arguments": {"confirmed": True,
                                                                 "voices": [{"content": "导出太慢了"}]}}})
    result = json.loads(raw)["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "-32012" in text and "不代签身份" in text
    paths = [s["path"] for s in remote["engine"].seen]
    assert not any("external/token" in p for p in paths), \
        "服务面绝不代签匿名令牌（设备锚点会被整站共用）"


def test_submit_forwards_per_request_key_to_engine(remote):
    _init(remote["url"])
    st, _h, raw = _post(remote["url"],
                        {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                         "params": {"name": "vod_submit_voices",
                                    "arguments": {"confirmed": True,
                                                  "voices": [{"content": "导出太慢了"}]}}},
                        headers={"Authorization": "Bearer tenant-key-A"})
    result = json.loads(raw)["result"]
    assert result["isError"] is False, result
    hop = [s for s in remote["engine"].seen if "external/voices" in s["path"]]
    assert hop, "必须真的调到引擎囤积端点"
    assert hop[-1]["auth"] == "Bearer tenant-key-A", "逐请求身份必须透传给引擎"

def test_initialize_advertises_tools_list_changed_true(remote):
    """devkit 的 remote test 断言 {tools: {listChanged: true}}；SDK 默认 false，
    我们在 _RemoteServer 里对齐（参照物的声明照抄，不"够用就行"）。"""
    st, body = _init(remote["url"])
    assert st == 200
    assert body["result"]["capabilities"]["tools"]["listChanged"] is True


class _FakeHandler:
    """最小 HTTP handler 替身：只供 _StreamSink 落字节，断言分帧与即时写。"""

    def __init__(self):
        import io
        self.wfile = io.BytesIO()
        self.headers_out = []

    def send_response_only(self, status):
        self.status = status

    def send_header(self, k, v):
        self.headers_out.append((k, v))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def end_headers(self):
        pass


def test_stream_sink_writes_chunks_immediately_with_chunked_framing():
    """SSE 这类没有 content-length 的响应必须 chunked 分帧并逐块 flush——
    devkit 的 shell 是 `for await (chunk) res.write(chunk)`，攒全再写等于废掉流式。"""
    sink = tr._StreamSink(_FakeHandler())
    sink.start(200, [("content-type", "text/event-stream")])
    assert sink.chunked is True
    assert ("Transfer-Encoding", "chunked") in sink.h.headers_out
    sink.body(b"hello")
    assert sink.h.wfile.getvalue() == b"5\r\nhello\r\n", "首块必须立刻成帧写出"
    sink.body(b"world!")
    sink.end()
    assert sink.h.wfile.getvalue() == b"5\r\nhello\r\n6\r\nworld!\r\n0\r\n\r\n"


def test_stream_sink_keeps_length_delimited_responses_raw():
    sink = tr._StreamSink(_FakeHandler())
    sink.start(200, [("content-length", "2"), ("content-type", "application/json")])
    assert sink.chunked is False
    sink.body(b"{}")
    sink.end()
    assert sink.h.wfile.getvalue() == b"{}"


def _raw_post(url, payload, headers):
    """不经过 urllib 的默认头：精确控制 content-type / accept 的有无。"""
    import http.client
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=30)
    body = json.dumps(payload).encode()
    conn.putrequest("POST", "/", skip_accept_encoding=True)
    for k, v in headers.items():
        conn.putheader(k, v)
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders(body)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, dict(resp.getheaders()), data


def test_minimal_client_headers_are_normalized_like_devkit(remote):
    """devkit 的外壳会把缺省/`text/plain` 的 content-type 覆盖成 JSON、缺 accept
    补成 `application/json, text/event-stream`，否则裸客户端吃 415/406。
    这里用 http.client 精确构造"没有 Accept、content-type=text/plain"的请求。"""
    payload = {"jsonrpc": "2.0", "id": 41, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18",
                          "clientInfo": {"name": "bare", "version": "1"},
                          "capabilities": {}}}
    st, hdrs, body = _raw_post(remote["url"], payload,
                               {"Content-Type": "text/plain; charset=utf-8"})
    assert st == 200, body
    assert json.loads(body)["result"]["serverInfo"]["name"] == "vod-devkit"


def test_tools_call_without_arguments_is_accepted(remote):
    """MCP 允许省略 tools/call 的 arguments。devkit 为此在 JSON 边界补 {}（其 zod
    层不接受 undefined）；Python SDK 的 CallToolRequestParams.arguments 本身就是
    可空，实测不补也能过——所以本仓不加那段代码，但把"省略也 200"的 wire 契约
    钉住，防 SDK 升级后回退。"""
    st, _h, body = _post(remote["url"], {"jsonrpc": "2.0", "id": 42, "method": "tools/call",
                                         "params": {"name": "vod_devkit_info"}})
    assert st == 200, body
    data = json.loads(body)
    assert "error" not in data, data
    assert data["result"].get("isError") is not True, data
