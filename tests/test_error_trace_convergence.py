"""ARCH-ERR-04（完整收敛）行为与结构锁。

背景：台账原记 26 处 `except: pass`，首批只补了主链 3 点。本批把剩余全部收敛到
`vod_mcp.trace.suppress()`（零依赖模块，懒导入 runtime_state 落日志），并用结构用例
把"裸 pass"钉死——结构用例是唯一能防住"以后又有人写 pass"的门禁。
"""
from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"


def _bare_pass_handlers() -> list[tuple[str, int]]:
    """列出 `except` 体只有一个 `pass`（或 `...`）的处理器。"""
    out = []
    for p in SRC.rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = [b for b in node.body
                    if not (isinstance(b, ast.Expr)
                            and isinstance(b.value, ast.Constant)
                            and b.value.value is Ellipsis)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                out.append((str(p.relative_to(SRC.parent)), node.lineno))
    return sorted(out)


def test_no_bare_except_pass():
    """吞点必须留痕：src/ 内不允许出现只有 `pass` 的 except 体。

    修法唯一：`except X as e: trace.suppress("<模块.函数>", e)`（或 `with trace.tolerant(...)`）。
    这条用例故意扫全 src/ 而不是白名单文件——历史上正是"白名单里加了新文件"让新吞点逃过门禁。
    """
    bad = _bare_pass_handlers()
    assert not bad, "存在只写 pass 的 except 体（异常被静默吞掉，排障无真源）：\n" + \
        "\n".join(f"  {f}:{ln}" for f, ln in bad)


def test_suppress_writes_where_field(monkeypatch):
    """suppress() 必须落一行带 where 的日志，且自身不抛。"""
    from vod_mcp import runtime_state as rt
    from vod_mcp import trace
    logs = []
    monkeypatch.setattr(rt, "_log", lambda line, **kw: logs.append((line, kw)), raising=False)
    trace.suppress("net.demo_point", ValueError("boom"))
    assert logs, "suppress 没有落日志"
    line, kw = logs[0]
    assert "net.demo_point" in line and "ValueError" in line, line
    assert kw.get("where") == "net.demo_point", kw


def test_suppress_survives_broken_logger():
    """日志出口自己坏掉时，suppress 不许把异常抛回吞点（否则等于把 pass 换成炸）。"""
    from vod_mcp import runtime_state as rt
    from vod_mcp import trace

    def _boom(*a, **kw):
        raise OSError("disk full")
    rt._log, orig = _boom, rt._log
    try:
        trace.suppress("paths.demo", RuntimeError("x"))       # 不抛即通过
    finally:
        rt._log = orig


def test_tolerant_swallows_only_whitelisted():
    """tolerant 只吞白名单内的异常；白名单外必须上抛（否则等于扩大吞点）。"""
    from vod_mcp import trace
    with pytest.raises(KeyError):
        with trace.tolerant("demo", swallow=(OSError,)):
            raise KeyError("not in whitelist")
    with trace.tolerant("demo", swallow=(OSError,)):
        raise OSError("swallowed")