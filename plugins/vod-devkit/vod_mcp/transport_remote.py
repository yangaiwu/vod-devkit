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

    def request(self, scope: dict, body: bytes, timeout: float = 60) -> tuple:
        """把一次 HTTP 请求投递进事件循环 → (status, headers, body)。"""
        collected = {"status": None, "headers": [], "chunks": []}

        async def receive():
            if collected.get("body_sent"):
                return {"type": "http.disconnect"}
            collected["body_sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                collected["status"] = message["status"]
                collected["headers"] = [(k.decode() if isinstance(k, bytes) else k,
                                         v.decode() if isinstance(v, bytes) else v)
                                        for k, v in message.get("headers", [])]
            elif message["type"] == "http.response.body":
                chunk = message.get("body") or b""
                collected["chunks"].append(chunk)

        async def run():
            await self.manager.handle_request(scope, receive, send)

        fut = asyncio.run_coroutine_threadsafe(run(), self._loop)
        fut.result(timeout=timeout)
        return (collected["status"] or 500, collected["headers"],
                b"".join(collected["chunks"]))


def _scope(handler, body: bytes) -> dict:
    from urllib.parse import urlsplit
    parts = urlsplit(handler.path)
    return {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": handler.command, "scheme": "http",
        "path": parts.path or "/", "raw_path": (parts.path or "/").encode(),
        "query_string": (parts.query or "").encode(),
        "headers": [(k.lower().encode(), str(v).encode())
                    for k, v in handler.headers.items()],
        "client": (handler.client_address[0], handler.client_address[1]),
        "server": (handler.server.server_address[0], handler.server.server_address[1]),
        "root_path": "",
    }


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
        tok_key = tools._REQ_KEY.set(key or None)
        tok_face = tools._SERVER_FACE.set(True)
        try:
            status, headers, payload = self.server.runtime.request(_scope(self, body), body)
        except Exception as e:  # 传输层异常必须答 500，而不是断连
            tools._SERVER_FACE.reset(tok_face)
            tools._REQ_KEY.reset(tok_key)
            self._json(500, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32603, "message": str(e)}})
            return
        finally:
            tools._SERVER_FACE.reset(tok_face)
            tools._REQ_KEY.reset(tok_key)
        self.send_response(status)
        for k, v in headers:
            if k.lower() in ("content-length", "transfer-encoding"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self._cors()
        self.end_headers()
        self.wfile.write(payload)


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