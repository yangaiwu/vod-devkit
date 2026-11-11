"""远程面 HTTP 外壳（Streamable HTTP）：形态逐项对齐 huaweicloud-devkit。

devkit 的契约（mcp-server-remote.ts + test/remote-mcp-server.test.ts 实测），
本文件照抄行为，不另发明：

    POST  → Streamable HTTP（官方 SDK，stateless + json_response）
    GET   → 405 Allow: POST, OPTIONS（"the shell keeps the method filter"）
    OPTIONS → 204 + Access-Control-Allow-Origin: *
    通知（无 id）→ 202
    坏 JSON → 400 -32700
    默认 127.0.0.1:9528，--port/--host 可改；无内建鉴权

实现手段的差异（唯一）：devkit 用 @modelcontextprotocol/sdk + node:http 直接
拿 WebStandard Request；Python SDK 的入口是 ASGI（StreamableHTTPSessionManager
.handle_request(scope, receive, send)），而本仓不引入 ASGI 服务器，所以这里
用一个小的 ASGI 适配层把 stdlib http.server 的请求转成 scope/receive/send。
协议处理仍然全部在 SDK 里，与 devkit 同源。

身份：请求头 Authorization: Bearer <key> 逐请求注入（见 tools._REQ_KEY），
不落盘、不进 env；插件不代签身份——缺 key 时 submit 结构化拒绝。
"""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9528
MAX_BODY = 4 * 1024 * 1024
LOOPBACK = ("127.0.0.1", "localhost", "::1")


class RemoteRuntime:
    """持有 asyncio 事件循环 + SDK session manager 的生命周期。"""

    def __init__(self, host: str, port: int):
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from vod_mcp.remote_app import build_server

        self.host, self.port = host, port
        self._loop = asyncio.new_event_loop()
        # stateless + json_response：与 devkit 的 WebStandardStreamableHTTPServerTransport
        # ({sessionIdGenerator: undefined, enableJsonResponse: true}) 等价
        self.manager = StreamableHTTPSessionManager(
            app=build_server(remote=True), json_response=True, stateless=True)
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)

    def _serve_loop(self):
        asyncio.set_event_loop(self._loop)

        async def run():
            async with self.manager.run():
                self._ready.set()
                await asyncio.Event().wait()  # 直到进程退出

        self._loop.run_until_complete(run())

    def start(self):
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError("MCP session manager 启动超时")

    def request(self, scope: dict, body: bytes, sink, timeout: float = 60) -> None:
        """把一次 HTTP 请求投递进事件循环，响应**逐块下沉**给 sink。

        sink.start(status, headers) / sink.body(bytes) / sink.end()。
        逐块而不是攒全再写：devkit 的 shell 也是 `for await (chunk of
        response.body) res.write(chunk)`——SSE 这种长响应攒全再写等于把流式
        语义废掉（客户端一个字节都看不到，直到响应结束）。
        """
        state = {"body_sent": False}

        async def receive():
            if state["body_sent"]:
                return {"type": "http.disconnect"}
            state["body_sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                headers = [(k.decode() if isinstance(k, bytes) else k,
                            v.decode() if isinstance(v, bytes) else v)
                           for k, v in message.get("headers", [])]
                sink.start(message["status"], headers)
            elif message["type"] == "http.response.body":
                chunk = message.get("body") or b""
                if chunk:
                    sink.body(chunk)

        async def run():
            try:
                await self.manager.handle_request(scope, receive, send)
            finally:
                sink.end()

        fut = asyncio.run_coroutine_threadsafe(run(), self._loop)
        try:
            fut.result(timeout=timeout)
        except Exception as e:  # 传输层异常：写 stderr 并让外壳答 500/断连
            sys.stderr.write(f"remote transport error: {e}\n")
            raise


def _normalize_headers(handler) -> list:
    """把请求头规范到 SDK 能接的形态——逐条照 devkit 的外壳做法。

    devkit 在构造 `Request` 前做两件事（mcp-server-remote.ts）：
      ① 缺 content-type 或 `text/plain*` → 覆盖成 `application/json`
         （裸 `curl -d` 与 undici 默认体不因此吃 415）；
      ② 缺 accept → 补 `application/json, text/event-stream`
         （否则 SDK 的 accept 协商会 406）。
    这两条不是"宽松"，是让最小客户端也能跑通同一份契约。
    """
    headers = []
    ctype = (handler.headers.get("Content-Type") or "").strip()
    if not ctype or ctype.lower().startswith("text/plain"):
        ctype = "application/json"
    seen_ctype = False
    for k, v in handler.headers.items():
        lk = k.lower()
        if lk == "content-type":
            seen_ctype = True
            headers.append((b"content-type", ctype.encode()))
            continue
        headers.append((lk.encode(), str(v).encode()))
    if not seen_ctype:
        headers.append((b"content-type", ctype.encode()))
    if not handler.headers.get("Accept"):
        headers.append((b"accept", b"application/json, text/event-stream"))
    return headers


def _scope(handler, body: bytes) -> dict:
    from urllib.parse import urlsplit
    parts = urlsplit(handler.path)
    return {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": handler.command, "scheme": "http",
        "path": parts.path or "/", "raw_path": (parts.path or "/").encode(),
        "query_string": (parts.query or "").encode(),
        "headers": _normalize_headers(handler),
        "client": (handler.client_address[0], handler.client_address[1]),
        "server": (handler.server.server_address[0], handler.server.server_address[1]),
        "root_path": "",
    }


class _StreamSink:
    """把 ASGI 的 send 回调落成 HTTP 响应字节流（逐块，不攒全）。

    与 devkit 的 `for await (chunk of response.body) res.write(chunk)` 等价：
    - 响应头里有 content-length → 原样写；
    - 没有（SSE 这类流式响应）→ 用 chunked 分帧，客户端能立刻收到字节。
    """

    def __init__(self, handler):
        self.h = handler
        self.started = False
        self.chunked = False
        self.closed = False

    def start(self, status, headers):
        h = self.h
        h.send_response_only(status)
        hdrs = [(k, v) for k, v in headers if k.lower() != "transfer-encoding"]
        self.chunked = not any(k.lower() == "content-length" for k, _ in hdrs)
        for k, v in hdrs:
            h.send_header(k, v)
        h._cors()
        if self.chunked:
            h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        h.wfile.flush()
        self.started = True

    def body(self, chunk: bytes):
        if not self.started:
            raise RuntimeError("ASGI body 先于 response.start")
        if self.chunked:
            self.h.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
        else:
            self.h.wfile.write(chunk)
        self.h.wfile.flush()

    def end(self):
        if not self.started or self.closed:
            return
        self.closed = True
        if self.chunked:
            self.h.wfile.write(b"0\r\n\r\n")
            self.h.wfile.flush()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "vod-devkit-mcp"

    def log_message(self, fmt, *args):  # 静默：日志走 /tmp/vod_mcp_server.log
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, MCP-Protocol-Version, Mcp-Session-Id, Accept, Authorization")
        self.send_header("Access-Control-Expose-Headers",
                         "MCP-Protocol-Version, Mcp-Session-Id")

    def _empty(self, code, extra=None):
        self.send_response(code)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._empty(204)

    def do_GET(self):
        # 与 devkit 同契约：GET 不进传输层（SDK 会把它变成 SSE 长连）
        self._empty(405, {"Allow": "POST, OPTIONS"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "空或超大请求体"}})
            return
        body = self.rfile.read(length)
        try:
            message = json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            self._json(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}})
            return
        # 通知（含 notifications/initialized）：不构造 transport，直接 202
        #（devkit 同样的短路，保留 devkit 的 202 契约）
        if isinstance(message, dict) and "id" not in message:
            self._empty(202)
            return
        raw_auth = (self.headers.get("Authorization") or "").strip()
        key = raw_auth[7:].strip() if raw_auth.lower().startswith("bearer ") else ""

        from vod_mcp import tools
        sink = _StreamSink(self)
        tok_key = tools._REQ_KEY.set(key or None)
        tok_face = tools._SERVER_FACE.set(True)
        try:
            self.server.runtime.request(_scope(self, body), body, sink)
        except Exception as e:  # 传输层异常：能答就答 500，已经流出去就断连
            if not sink.started:
                self._json(500, {"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32603, "message": str(e)}})
            return
        finally:
            tools._SERVER_FACE.reset(tok_face)
            tools._REQ_KEY.reset(tok_key)


def serve(host: str, port: int) -> int:
    if host not in LOOPBACK:
        print(f"[vod-devkit] 警告：远程 MCP 绑定非回环地址 {host}——本进程无内建鉴权，"
              "不要把它匿名暴露到公网；TLS 与身份校验应由反代承担。", file=sys.stderr)
    runtime = RemoteRuntime(host, port)
    runtime.start()
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.daemon_threads = True
    httpd.runtime = runtime
    real_port = httpd.server_address[1]
    print(f"vod-devkit MCP server (remote) listening on {host}:{real_port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0