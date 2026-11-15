"""mypy 作用域护栏：从“逐文件白名单”反转为“存量免疫、新增必检”。

为什么反转：白名单的失败模式是静默——新增模块忘加白名单就永远不被检查，
门禁看着是绿的实际没覆盖（这正是 pyflakes 改递归要消灭的同一个坑）。
反转后失败模式是响的：新模块默认被检，报错就修，或显式写进下面的技术债清单。

本清单只许缩不许长：往里加一条必须同时改 EXPECTED_LEGACY 并写明原因
（存量为什么炸），逼着“豁免”成为一次显式决策而不是随手追加。
"""
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 存量技术债（2026-11-15 实测：全量 mypy vod_mcp = 25 errors / 10 files）
EXPECTED_LEGACY = {
    "vod_mcp.transport_remote",
    "vod_mcp.tools",
    "vod_mcp.payload",
    "vod_mcp.skills_registry",
    "vod_mcp.server",
    "vod_mcp.policy",
    "vod_mcp.host_adapters.codex",
    "vod_mcp.diagnose",
    "vod_mcp.detect_framework",
    "vod_mcp.config_forms",
}


def _cfg() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_mypy_checks_the_whole_package_by_default():
    """files 必须是整包：新增模块不写任何配置也会被检查。"""
    pytest.importorskip("tomllib")
    assert _cfg()["tool"]["mypy"]["files"] == ["vod_mcp"], (
        "mypy files 不是整包——新增模块会静默逃检；豁免请走 overrides 技术债清单")


def test_mypy_exemptions_are_explicit_and_resolvable():
    pytest.importorskip("tomllib")
    overrides = _cfg()["tool"]["mypy"].get("overrides", [])
    exempt = set()
    for ov in overrides:
        assert ov.get("ignore_errors") is True, f"override 不是 ignore_errors：{ov}"
        exempt |= set(ov.get("module", []))
    assert exempt == EXPECTED_LEGACY, (
        "mypy 豁免清单与 EXPECTED_LEGACY 不一致——豁免是一次显式决策，"
        f"差异：多 {sorted(exempt - EXPECTED_LEGACY)} / 少 {sorted(EXPECTED_LEGACY - exempt)}")
    for mod in sorted(exempt):
        path = ROOT / (mod.replace(".", "/") + ".py")
        assert path.is_file(), f"豁免清单里的模块不存在：{mod}（删模块要摘名单）"