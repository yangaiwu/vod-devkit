"""进程级"传输面"标志（ARCH-DEP-01 的破环落点，2026-11-19 走查）。

为什么要独立成一个文件：这个 ContextVar 原先定义在 `net`，而 `runtime_state._is_remote_face()`
要靠它判断"当前是不是远程 HTTP 面"。`net` 顶层 import `runtime_state`（13 处状态读写），
`runtime_state` 又反向 import `net` ⇒ 成环，而环只被"函数内 import"那一行撑着：
任何一次 import 重排（重构 / 格式化工具 / IDE 自动整理）把它提到顶层就 `ImportError`
→ MCP server 起不来，宿主表现为"掉线"。

放在这里之后：`net` 与 `runtime_state` 都**顶层**引用本模块（本模块零依赖、只用 stdlib），
环消失。同时本模块提供 `is_remote()` 作为唯一读取入口，它**只在被调用时**才去问
`net._SERVER_FACE` 的实时绑定——这样 `net._SERVER_FACE.set()/reset()` 与测试的
`monkeypatch.setattr(net, "_SERVER_FACE", 桩)` 都照常生效（本轮实测踩过：直接读本模块
的快照会与 net 的桩不一致，导致三条远程面作用域用例变红）。

纪律：本模块**只许**放这件事与协议版本常量，且**不许**有顶层 `vod_mcp.*` import
（否则环会长回来）。`importlib` 是延迟导入，不是顶层依赖。
"""
import contextvars
import importlib

# MCP 协议版本单一真源（ARCH-CALL-05）。
# 为什么放这里：`server.py`（stdio 面 initialize 自报）、`transport_remote.py`（内部
# 兼容握手）与 `vodkit_cli/remote.py`（安装器探活/探测）三处都要用到它，而本模块零依赖，
# 谁引它都不造环。此前 `server.py` 定义了一个常量却无人引用、三处各写裸字面量 ⇒ 升级
# 协议时只改一处就会「服务端自报与客户端握手不一致」，报错却看不出是版本没同步。
# 门禁：tests/test_structure_guards.py::test_protocol_version_has_single_definition。
PROTOCOL_VERSION = "2025-06-18"

# 真源。`net._SERVER_FACE` 是它的别名（同一个对象）。
SERVER_FACE = contextvars.ContextVar("vod_server_face", default=False)


def _face() -> contextvars.ContextVar:
    """"当前有效的面标志"：优先 net 上的实时绑定，退化到本模块真源。

    net 上的绑定可能被替换（set/reset 不换对象，但测试 monkeypatch 会换对象），
    所以每次现取；本模块已经处于 `vod_mcp` 包内，这一步不会额外触发循环导入。
    """
    mod = importlib.import_module("vod_mcp.net") if _net_loaded() else None
    if mod is not None:
        face = getattr(mod, "_SERVER_FACE", None)
        if face is not None:
            return face
    return SERVER_FACE


def _net_loaded() -> bool:
    import sys
    return "vod_mcp.net" in sys.modules


def is_remote() -> bool:
    return bool(_face().get())


def set_remote(value: bool):
    """设置当前面（返回 token，供 reset）；与 `net._SERVER_FACE.set` 等价。"""
    return _face().set(value)


def reset_remote(token) -> None:
    _face().reset(token)