"""吞点留痕出口（ARCH-ERR-04）。

纪律：`except` 体不允许裸 `pass`——异常被吞时不写日志，排障就失去真源（历史实锤：
runtime.json 被写坏 → 读成空 → 重领令牌 → 设备锚点漂移，而插件侧零痕迹）。

为什么单独成模块：本模块**零依赖**——连 runtime_state 都不 import（函数内 import 也算
import 图上的边，`paths → trace → runtime_state → paths` 会成环）。落盘能力由
runtime_state 在 import 期通过 `set_logger()` 注入；未注入时退回 stderr（宁可多一行
噪声，也不许静默）。
"""

import sys
_LOGGER = None


def set_logger(fn) -> None:
    """由 runtime_state 注入日志实现（模块级、一次性）。"""
    global _LOGGER
    _LOGGER = fn


def suppress(where: str, exc: BaseException | None = None) -> None:
    """记一行「哪个函数的哪类异常被吞了」，绝不向上抛。

    `where` 约定为 `模块.函数`（如 `net._fetch_anon_token`），便于按字段过滤。
    """
    msg = f"suppress {where}"
    if exc is not None:
        msg = f"{msg}: {type(exc).__name__}: {exc}"
    logger = _LOGGER
    if logger is None:
        print(f"[vod-devkit] suppress: {msg}", file=sys.stderr)
        return
    try:
        logger(msg, level="debug", where=where)
    except Exception as e2:                            # noqa: BLE001  日志出口自己失败时只 stderr 兜底
        print(f"[vod-devkit] suppress-log-failed: {msg} ({type(e2).__name__}: {e2})",
              file=sys.stderr)


class tolerant:
    """`with tolerant("where", swallow=(OSError,)):` —— 只吞白名单异常并留痕，其余照常上抛。"""

    def __init__(self, where: str, swallow: tuple = (Exception,)):
        self.where = where
        self.swallow = swallow

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            return False
        if issubclass(exc_type, self.swallow):
            suppress(self.where, exc)
            return True
        return False