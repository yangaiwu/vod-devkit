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
from vod_mcp.remote_app import SIDELESS_MARK_HEADER
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9528
MAX_BODY = 4 * 1024 * 1024
LOOPBACK = ("127.0.0.1", "localhost", "::1")

# ARCH-CFG-02：默认 Origin 白名单——只要回环 + 任意端口。
# 浏览器跨域必带 Origin；不在名单里 → 不发 CORS 头且 do_POST 直接 403。
# 非回环部署要用别的来源，必须显式 `--allow-origin <origin>`（可多次）。
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1",
    "http://localhost",
    "http://[::1]",
    "https://127.0.0.1",
    "https://localhost",
    "https://[::1]",
)


def origin_allowed(origin: str, allowed) -> bool:
    """Origin 是否在白名单里。

    规则：**精确匹配，或 `<白名单项>:<任意端口>`**。
    只比到端口分隔符，所以 `http://127.0.0.1.evil.com` 不会被
    `http://127.0.0.1` 前缀误放行（本仓 S180 同源教训：前缀匹配必须带边界）。
    """
    origin = (origin or "").strip().rstrip("/")
    for a in allowed or ():
        a = a.rstrip("/")
        if origin == a or origin.startswith(a + ":"):
            return True
    return False

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
        # D-scope-1：session TTL 与记忆窗口同源（都取 rt.SCOPE_TTL_SEC），
        # 避免两个独立时钟产生「记忆还在但会话已回收」（悬挂桶泄漏）或
        # 「窗口内会话过期导致同一用户被当新客」。记忆 TTL 由 session TTL 驱动。
        from vod_mcp import runtime_state as _rt_ttl
        self.manager = StreamableHTTPSessionManager(
            app=build_server(remote=True), json_response=True,
            stateless=False, session_idle_timeout=_rt_ttl.SCOPE_TTL_SEC)
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
    补好头的新 scope —— 后续仍由 manager 按标准路径处理，客户端无感。

    🔴 审查 ⑤（2026-11-19）：**必须复用同一个"哨兵会话"，不能每次新建。**
    旧实现每次调用都内部 initialize 一次，SDK 的会话不随请求结束销毁（靠
    session_idle_timeout 1800s 回收）→ 裸客户端 1 req/s 就常驻 1800 个会话，
    持续 5.6 req/s 打满默认上限 10000，之后**所有**客户端（含标准客户端）
    拿 503「Too many open sessions」——一个不守规矩的客户端能打挂守规矩的。
    现在会话池占用从 O(请求数) 降到 O(1)。

    ⚠️ 复用带来一个必须同时处理的副作用：哨兵会话是**共享**的，若让它照常
    进分桶，所有裸客户端会共用一个记忆桶（"一人一桶"退化成"大家一桶"，
    比新建成独立会话更坏）。所以补 sid 时**同时**打 `x-vod-sideless` 标记，
    remote_app._req_scope 见到它就把会话清空 → key=None（读写皆禁），
    业务行为与旧实现完全一致：无 session 请求就是无记忆。

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

    sid = await _sentinel_session(manager, scope)
    if not sid:
        return None                               # 握手没给会话 → 退回标准拒绝路径

    new_scope = dict(scope)
    new_scope["headers"] = [(k, v) for k, v in (scope.get("headers") or [])
                            if (k.decode() if isinstance(k, bytes) else k).lower()
                            not in ("mcp-session-id", SIDELESS_MARK_HEADER)] \
        + [(b"mcp-session-id", sid.encode()),
           (SIDELESS_MARK_HEADER.encode(), b"1")]
    return new_scope


# 哨兵会话登记（进程级）：按 manager 实例绑定 {id(manager): {"sid":..., "at":...}}
# 🔴 必须按 manager 绑定，不能只存一份全局 sid：会话归属 manager 实例
#    （它的 _server_instances），进程内新建一个 manager（重启/重建 runtime、
#    多实例测试）后旧 sid 一律 404。本会话实测：只存全局 → 同进程第二个
#    runtime 起来后第一发就吃「Session not found」。
_SENTINEL: dict = {}
_SENTINEL_LOCK: threading.Lock = threading.Lock()
# 与 SDK 的 session_idle_timeout 同源（SCOPE_TTL_SEC）。留一半余量：
# 哨兵在"半个 TTL 内没被用过"就先自己重建，避免拿着一条已被回收的 sid
# 让客户端吃 404「Session not found」。
_SENTINEL_FRESH_SEC = None       # None = 用运行时算出的默认值（见 _sentinel_ttl）


def _sentinel_ttl() -> float:
    if _SENTINEL_FRESH_SEC:
        return float(_SENTINEL_FRESH_SEC)
    try:
        from vod_mcp import runtime_state as _rts
        return max(30.0, float(_rts.SCOPE_TTL_SEC) / 2)
    except Exception:                             # pragma: no cover
        return 900.0


def _reset_sideless_state(keep_sid: str | None = None, manager=None) -> None:
    """清空哨兵登记。

    - 测试隔离用；生产路径不需要调用（失效由时间戳 + manager 绑定自己处理）。
    - keep_sid：模拟"登记的 sid 已在 manager 侧被 TTL 回收"（时间戳置远古）。
    - manager 省略时对**所有** manager 生效。
    """
    with _SENTINEL_LOCK:
        if manager is None:
            _SENTINEL.clear()
            if keep_sid:
                _SENTINEL["__global__"] = {"sid": keep_sid, "at": -1e12}
        else:
            _SENTINEL.pop(id(manager), None)
            if keep_sid:
                _SENTINEL[id(manager)] = {"sid": keep_sid, "at": -1e12}


def _sentinel_peek(manager=None) -> dict:
    """读当前哨兵登记（诊断/测试用）。"""
    with _SENTINEL_LOCK:
        if manager is None:
            return dict(_SENTINEL.get("__global__") or {})
        return dict(_SENTINEL.get(id(manager)) or {})


async def _sentinel_session(manager, scope: dict) -> str:
    """取（必要时创建一次）哨兵会话 id。失败返回空串。

    并发保护：ThreadingHTTPServer + 单事件循环，协程 await 之间可能交错。
    "先查后建"可能多建一两个，但不会退化成每请求一个——多建一个只是多占
    一个会话位，代价可忽略；而每请求一个就是本审查要消灭的 503 根因。
    """
    import time as _time

    ttl = _sentinel_ttl()
    key = id(manager)
    with _SENTINEL_LOCK:
        rec = _SENTINEL.get(key) or {}
        sid = str(rec.get("sid") or "")
        at = float(rec.get("at") or 0)
        if sid and (_time.monotonic() - at) < ttl:
            _SENTINEL[key] = {"sid": sid, "at": _time.monotonic()}
            return sid

    sid = await _handshake_once(manager, scope)
    if not sid:
        return ""
    with _SENTINEL_LOCK:
        _SENTINEL[key] = {"sid": sid, "at": _time.monotonic()}
    sys.stderr.write("[vod-devkit] 兼容模式：已建立/复用兜底会话（compat-sideless）\n")
    return sid


async def _handshake_once(manager, scope: dict) -> str:
    """内部握手一次，拿会话 id（不建则返回空串）。"""
    import json as _json

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
                             not in ("mcp-session-id", SIDELESS_MARK_HEADER)]
    try:
        await manager.handle_request(init_scope, init_receive, init_send)
    except Exception:
        return ""
    return (captured.get("sid") or "").strip()


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

    # ── Origin/Host 收紧（ARCH-CFG-02，2026-11-19 走查 P1）──────────────────
    # 缺陷：此前无条件发 `Access-Control-Allow-Origin: *`、预检一律 204、`do_POST`
    # 全程不校验 Origin/Host ⇒ **用户机器上已装插件时，任意网页都能跨域驱动本机端点**
    # （DNS rebinding 还能绕过"仅回环"）。
    # 修法：默认只答回环 Origin/Host，其余 403；非回环绑定必须显式给白名单。
    # ⚠️ CORS 头只约束浏览器，挡不住本机进程/DNS rebinding —— 所以**403 必须在
    # do_POST 里显式判**，不能只靠"不发 CORS 头"（台账原方案只写"不发头"，不够）。
    _LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

    def _origin_allowed(self) -> bool:
        """Origin 校验：无 Origin（非浏览器客户端）放行；有则必须命中白名单。

        浏览器跨域请求必带 Origin；curl/SDK 不带。所以这条只管浏览器面，
        不能拿它挡"本机进程"——那由 Host 校验与既有令牌机制负责。

        匹配规则：**精确匹配，或"回环前缀 + 任意端口"**（`http://127.0.0.1:3000`）。
        端口不固定是常态（本地 dev server 各种端口），但主机必须精确——否则
        `http://127.0.0.1.evil.com` 这类会被前缀误放行。
        """
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True                      # 非浏览器（curl/SDK/stdio 转发）
        return origin_allowed(origin, self.server.allowed_origins)  # type: ignore[attr-defined]

    def _host_allowed(self) -> bool:
        """Host 校验：挡住 DNS rebinding（把 evil.example 解析到 127.0.0.1）。

        绑定回环时只认回环 Host；显式绑非回环时，额外接受配置里的 allow_hosts。
        """
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return True                      # HTTP/1.0 无 Host：交后续鉴权兜底
        bare = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        if bare in self._LOOPBACK_HOSTS:
            return True
        return host in self.server.allowed_hosts or bare in self.server.allowed_hosts  # type: ignore[attr-defined]

    def _reject_cross_origin(self, why: str) -> None:
        """拒收：不发任何 CORS 头（浏览器自然拦），并 403 说明原因。"""
        body = json.dumps({"jsonrpc": "2.0", "id": None,
                           "error": {"code": -32600,
                                     "message": f"跨域/跨主机请求被拒：{why}（默认只接受回环）"}},
                          ensure_ascii=False).encode()
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()                   # 注意：不调 _cors()，不给浏览器放行机会
        self.wfile.write(body)

    def _cors(self):
        # 只回显**白名单内**的 Origin；不在白名单就不发（浏览器自然拦）。
        # 不再无条件 `*`——那是 CFG-02 的原缺陷。
        origin = (self.headers.get("Origin") or "").strip()
        if origin and origin_allowed(origin, self.server.allowed_origins):  # type: ignore[attr-defined]
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
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
        # ARCH-CFG-02：Origin/Host 必须在**进业务之前**判（CORS 头只约束浏览器，
        # 挡不住本机进程与 DNS rebinding，所以这里显式 403）。
        if not self._host_allowed():
            self._reject_cross_origin(f"Host={self.headers.get('Host')!r}")
            return
        if not self._origin_allowed():
            self._reject_cross_origin(f"Origin={self.headers.get('Origin')!r}")
            return
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


def serve(host: str, port: int, allow_anon_mint: bool = False,
          allow_origins: tuple | None = None, allow_hosts: tuple | None = None) -> int:
    anon = _apply_anon_mint_policy(host, allow_anon_mint)
    if host not in LOOPBACK:
        print(f"[vod-devkit] 警告：远程 MCP 绑定非回环地址 {host}——本进程无内建鉴权，"
              "不要把它匿名暴露到公网；TLS 与身份校验应由反代承担。", file=sys.stderr)
        if not anon:
            print("[vod-devkit] 匿名令牌代领已关闭（非回环绑定）：调用方须带 "
                  "Authorization: Bearer <key>；...代领时加 --allow-anon-mint",
                  file=sys.stderr)
    runtime = RemoteRuntime(host, port)
    runtime.start()
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.daemon_threads = True
    httpd.runtime = runtime
    # ARCH-CFG-02：Origin/Host 白名单（默认只回环；非回环需显式 --allow-origin/--allow-host）
    httpd.allowed_origins = frozenset(allow_origins or DEFAULT_ALLOWED_ORIGINS)  # type: ignore[attr-defined]
    httpd.allowed_hosts = frozenset(allow_hosts or ())                            # type: ignore[attr-defined]
    real_port = httpd.server_address[1]
    print(f"vod-devkit MCP server (remote) listening on {host}:{real_port}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0