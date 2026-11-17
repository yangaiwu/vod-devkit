"""S228/S229：插件边界（不托管宿主生命周期）+ 生效口径单一真源（D-boundary-1）。

S228 锁的是"不做事"：src/ 里不许出现 systemctl/systemd/launchctl/restart 这类
宿主生命周期动作——插件只写配置、落载荷、读回版本。历史上本机会出现过用 transient
unit 前台包 `hermes gateway restart` 的做法，那属于运维动作，绝不能回到代码里。

S229 锁的是"只说一句话"：用户可见的生效提示必须来自 vod_mcp.msgs，不许各适配器
自拼。措辞漂移只在真机文案上暴露（拷贝漏项 / 宿主名不一致都踩过）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from vod_mcp import msgs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# 宿主生命周期动作（大小写不敏感）：出现即越界
_LIFECYCLE = re.compile(r"\b(systemctl|systemd|launchctl|restart)\b", re.I)
# 用户可见的生效口径（只允许 msgs.py 拼）
_HINT = re.compile(r"重启[^\"'\n]{0,20}生效")
# 绝不允许把宿主的进程命令行（systemctl …）写进用户文案
_CMD_IN_TEXT = re.compile(r"(systemctl|launchctl|service\s+\w+\s+restart)")


def _py_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def _string_constants(path: Path) -> list[str]:
    """取非 docstring 的字符串常量（含 f-string 各段）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    out.append(part.value)
    return out


def test_s228_src_has_no_host_lifecycle_action():
    """S228：src/ 不得出现 systemctl/systemd/launchctl/restart（插件不碰宿主进程）。"""
    hits = []
    for p in _py_files():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if _LIFECYCLE.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:90]}")
    assert not hits, "插件侧出现宿主生命周期动作（D-boundary-1 越界）：\n" + "\n".join(hits)


def test_s228_user_facing_text_never_contains_host_command():
    """S228 反向锁：用户文案里不许出现 systemctl/launchctl 这类命令行。"""
    bad = []
    for p in _py_files():
        for s in _string_constants(p):
            if _CMD_IN_TEXT.search(s):
                bad.append(f"{p.relative_to(ROOT)}: {s[:90]!r}")
    assert not bad, "用户文案里出现宿主命令（插件不得教用户跑 systemctl）：\n" + "\n".join(bad)


@pytest.mark.parametrize("path", ["docs/design.md", "docs/decisions.md"])
def test_s228_boundary_is_documented(path):
    """S228：边界必须落在设计/决策正文里，且带 falsifier（可被推翻条件）。"""
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "D-boundary-1" in text, f"{path} 缺 D-boundary-1"
    assert "不托管宿主" in text or "不碰宿主" in text, f"{path} 缺边界陈述"
    assert "Falsifier" in text, f"{path} 缺 Falsifier"


def test_s229_restart_hint_is_single_source():
    """S229：除 msgs.py 外，任何模块不得自拼「重启…生效」文案。"""
    offenders = []
    for p in _py_files():
        if p.name == "msgs.py":
            continue
        for s in _string_constants(p):
            if _HINT.search(s):
                offenders.append(f"{p.relative_to(ROOT)}: {s[:80]!r}")
    assert not offenders, "生效文案出现第二拼写点（应改走 vod_mcp.msgs）：\n" + "\n".join(offenders)


def test_s229_msgs_spelling_is_the_contract():
    """S229：msgs 的输出即契约（真机文案曾因拼写漂移被误判）。"""
    assert msgs.effective() == "重启宿主会话生效"
    assert msgs.effective("Codex") == "重启 Codex 会话生效"
    assert msgs.effective_unit("dsh") == "重启 dsh 生效"
    assert msgs.effective_unit("OpenClaw 会话/网关", tight=True) == "重启 OpenClaw 会话/网关生效"
    assert msgs.after("使用新 key") == "重启宿主会话后使用新 key"
    assert msgs.restart_only("agent 会话") == "重启 agent 会话"


@pytest.mark.parametrize("rel", [
    "vod_mcp/host_adapters/codex.py", "vod_mcp/host_adapters/codearts.py",
    "vod_mcp/host_adapters/codeartswork.py", "vod_mcp/host_adapters/atomcode.py",
    "vod_mcp/host_adapters/workbuddy.py", "vod_mcp/host_adapters/opencode.py",
    "vod_mcp/host_adapters/generic.py", "vod_mcp/host_adapters/hermes.py",
    "vod_mcp/host_adapters/codex_desktop.py", "vod_mcp/host_adapters/officeace.py",
    "vod_mcp/host_adapters/openclaw.py",
])
def test_s229_every_host_adapter_routes_through_msgs(rel):
    """S229：每个宿主适配器都必须走 msgs（新增适配器忘了接口径会在这里红）。"""
    text = (SRC / rel).read_text(encoding="utf-8")
    assert "from vod_mcp import msgs" in text, f"{rel} 未 import msgs"
    assert re.search(r"msgs\.(effective|effective_unit|after|restart_only)\(", text), \
        f"{rel} 未使用 msgs 的生效口径"