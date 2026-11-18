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

身份：请求头 Authorization: Bearer *** 逐请求注入（见 tools._REQ_KEY），优先生效；
没有 Bearer 时与本地同链——由服务端领/复用**机器级匿名令牌**提交（同机独立部署的
默认形态，D-token-machine-1）。
"""
import asyncio
import json
import os
import sys
import threading

from vod_mcp import net, paths
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9528
MAX_BODY = 4 * 1024 * 1024
LOOPBACK = ("127.0.0.1", "localhost", "::1")

# 载荷自校验缓存：远程面是长驻无鉴权服务，被改过的服务端载荷要当场拒绝服务，
# 不能等运维跑 doctor 才发现（devkit 的每请求 verifySkillTree 同思路）。
# TTL 缓存避免每个请求都做一遍 sha256 全集（40+ 文件）。
_PAYLOAD_GUARD = {"at": 0.0, "sig": None, "problems": []}
_PAYLOAD_GUARD_TTL = 30.0


def payload_problems(force: bool = False) -> list:
    """远程面载荷完整性检查（载荷目录不存在/被改 → 非空列表）。

    只校验"载荷副本"形态：stdio/仓内直跑没有 payload.json，返回空（不误伤）。
    """
    import time as _t
    from pathlib import Path
    from vod_mcp import payload as _pl
    _P = Path
    # 显式 env 优先（安装期注入），否则按自身所在树推断——*不许* import
    # host_adapters：它的 __init__ 会连带 import 各宿主适配模块，而载荷副本不含
    # integrations/（2026-11-12 实锤：请求线程 KeyError → 每个请求 500）。
    env_dir = (os.environ.get("VOD_PAYLOAD_DIR") or "").strip()
    d = _P(env_dir) if env_dir else None
    if d is None:
        # 从载荷副本直接起来的服务（entry = <payload>/vod_mcp/server.py）没有
        # install 期注入的 payload_dir —— 用自身所在树推断：载荷根里有 payload.json
        # 就说明"我就是那份副本"，必须自校验（否则被改的副本会一直对外服务）。
        root = _P(paths.ROOT)
        d = root if (root / "payload.json").exists() else None
    if d is None:
        return []
    meta = _P(d) / "payload.json"
    sig = (str(meta), meta.stat().st_mtime if meta.exists() else 0.0)
    now = _t.time()
    if not force and _PAYLOAD_GUARD["sig"] == sig and now - _PAYLOAD_GUARD["at"] < _PAYLOAD_GUARD_TTL:
        return list(_PAYLOAD_GUARD["problems"])
    problems = _pl.verify(_P(d))
    _PAYLOAD_GUARD.update({"at": now, "sig": sig, "problems": list(problems)})
    return problems


class RemoteRuntime:
    """持有 asyncio 事件循环 + SDK session manager 的生命周期。"""

    def __init__(self, host: str, port: int):
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from vod_mcp.remote_app import build_server

        self.host, self.port = host, port
        self._loop = asyncio.new_event_loop()
        # D-scope-1（2026-11-18）：回归 MCP 标准 stateful 传输。
        # 此前 stateless=True 是简化形态，代价有二：
        #   ① 偏离标准 —— 外部服务对接时按标准实现方能互操作（自造一套无法对接）；
        #   ② 无会话标识 —— 多 agent 共用一个 server 时记忆/计数/nonce 全串味。
        # 标准流程：initialize 下发 mcp-session-id → 客户端后续请求回传 → 按会话隔离。
        # session_idle_timeout 与记忆窗口一致（30 分钟），过期自动回收。
        self.manager = StreamableHTTPSessionManager(
            app=build_server(remote=True), json_response=True,
            stateless=False, session_idle_timeout=30 * 60)
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

        身份传播（2026-11-13 真机实锤修复）：contextvars 不跨线程——do_POST
        在 HTTP 线程 set 的 _REQ_KEY/_SERVER_FACE 到不了事件循环线程的
        on_call_tool（submit 的 -32012 之所以还能触发，是走运的本地态分支）。
        修法：把 key/face 作为参数传入，投递协程体内 set——run_coroutine_threadsafe
        在 loop 线程为 run() 建任务，任务继承创建时刻的 context，体内 set 即对
        handle_request 派生的整个协程链（含 asyncio.to_thread 复制）可见。
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
            # 协程体内 set：见 request() docstring 的身份传播修复说明
            tok_key = net._REQ_KEY.set(scope.get("x_vod_key") or None)
            tok_face = net._SERVER_FACE.set(True)
            try:
                # D-scope-compat-1（2026-11-18）：极端客户端兜底。
                # 标准 stateful 传输要求先 initialize 拿 mcp-session-id 再调用，
                # 缺 session 直接 400（SDK 行为，实测「Missing session ID」）。
                # 自研裸 HTTP 客户端不握手直接 POST tools/call，在此内部握手补上
                # 会话头，让它落到独立会话（不与他人共桶）。
                new_scope = await _ensure_session_for_sideless(self.manager, scope)
                await self.manager.handle_request(
                    new_scope if new_scope is not None else scope, receive, send)
            finally:
                net._SERVER_FACE.reset(tok_face)
                net._REQ_KEY.reset(tok_key)
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
        # 私有键：原始请求体。只给兜底逻辑判断"是不是 initialize"用，
        # 不参与 ASGI 语义（SDK 读 body 走 receive，不读 scope）。
        "_vod_body": body,
    }


async def _ensure_session_for_sideless(manager, scope: dict):
    """极端客户端兜底：无 session 且非 initialize 的请求，内部握手补上会话头。

    标准行为（SDK）是直接 400「Missing session ID」。但存在自研裸 HTTP 客户端
    不握手直接 POST tools/call。兜底在内部走一次 initialize 取得会话 id，返回
    补好头的新 scope —— 后续仍由 manager 按标准路径处理，客户端无感，且这次
    调用落到独立会话（不与其它会话共桶，故不串味）。

    返回 None = 不需兜底或兜底失败（调用方用原 scope，标准错误照常返回，
    不掩盖真实问题）。initialize 本身不拦：那是建会话的入口。
    """
    import json as _json

    headers = {k.decode() if isinstance(k, bytes) else k:
               (v.decode() if isinstance(v, bytes) else v)
               for k, v in (scope.get("headers") or [])}
    if (headers.get("mcp-session-id") or "").strip():
        return None                               # 已有会话：标准路径

    body = scope.get("_vod_body")
    if not body:
        return None
    try:
        payload = _json.loads(body.decode() if isinstance(body, bytes) else body)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("method") == "initialize":
        return None                               # initialize 原样交给 manager

    init_payload = {"jsonrpc": "2.0", "id": "__compat_init__", "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "compat-sideless", "version": "1"}}}
    captured = {}

    async def init_receive():
        return {"type": "http.request",
                "body": _json.dumps(init_payload).encode(), "more_body": False}

    async def init_send(message):
        if message.get("type") == "http.response.start":
            for k, v in message.get("headers") or []:
                kk = k.decode() if isinstance(k, bytes) else k
                vv = v.decode() if isinstance(v, bytes) else v
                if kk.lower() == "mcp-session-id":
                    captured["sid"] = vv

    init_scope = dict(scope)
    init_scope["headers"] = [(k, v) for k, v in (scope.get("headers") or [])
                             if (k.decode() if isinstance(k, bytes) else k).lower()
                             != "mcp-session-id"]
    try:
        await manager.handle_request(init_scope, init_receive, init_send)
    except Exception:
        return None
    sid = (captured.get("sid") or "").strip()
    if not sid:
        return None                               # 握手没给会话 → 退回标准拒绝路径

    new_scope = dict(scope)
    new_scope["headers"] = [(k, v) for k, v in (scope.get("headers") or [])
                            if (k.decode() if isinstance(k, bytes) else k).lower()
                            != "mcp-session-id"] + [(b"mcp-session-id", sid.encode())]
    sys.stderr.write("[vod-devkit] 兼容模式：无 session 请求已内部握手（compat-sideless）\n")
    return new_scope


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
        # 服务端载荷自校验：被改/缺文件的载荷不许继续对外服务
        problems = payload_problems()
        if problems:
            self._json(503, {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                             "error": {"code": -32603,
                                       "message": "服务端载荷校验未通过（拒绝服务）："
                                                  + "；".join(problems[:5])}})
            return

        raw_auth = (self.headers.get("Authorization") or "").strip()
        key = raw_auth[7:].strip() if raw_auth.lower().startswith("bearer ") else ""

        # 身份经 scope 传递（x_vod_key），由 RemoteRuntime.request 在事件循环线程
        # 的协程体内 set _REQ_KEY/_SERVER_FACE——HTTP 线程直接 set 的 contextvar
        # 过不了 run_coroutine_threadsafe 的线程边界（2026-11-13 真机实锤）。
        scope = _scope(self, body)
        scope["x_vod_key"] = key
        sink = _StreamSink(self)
        try:
            self.server.runtime.request(scope, body, sink)
        except Exception as e:  # 传输层异常：能答就答 500，已经流出去就断连
            if not sink.started:
                self._json(500, {"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32603, "message": str(e)}})


def _apply_anon_mint_policy(host: str, allow: bool) -> bool:
    """按绑定地址决定是否允许服务端代领匿名令牌（返回是否开启）。

    回环（同机独立部署的默认形态）→ 开启，与本地 stdio 一致；
    非回环（可能经反代/公网触达）→ 默认关闭，需 `--allow-anon-mint` 显式开启。
    理由：服务面无内建鉴权，代领 = 任何能连端口的进程都能用本机身份提交、消耗额度。
    """
    from vod_mcp import net
    enabled = (host in LOOPBACK) or bool(allow)
    net.ANON_MINT_DISABLED = not enabled
    return enabled


def serve(host: str, port: int, allow_anon_mint: bool = False) -> int:
    anon = _apply_anon_mint_policy(host, allow_anon_mint)
    if host not in LOOPBACK:
        print(f"[vod-devkit] 警告：远程 MCP 绑定非回环地址 {host}——本进程无内建鉴权，"
              "不要把它匿名暴露到公网；TLS 与身份校验应由反代承担。", file=sys.stderr)
        if not anon:
            print("[vod-devkit] 匿名令牌代领已关闭（非回环绑定）：调用方须带 "
                  "Authorization: Bearer <key>；单机可信网络确需代领时加 --allow-anon-mint",
                  file=sys.stderr)
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