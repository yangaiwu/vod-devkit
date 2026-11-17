"""S233：候选串单一拼写点 + 文档里的"计数"必须由代码真值推导。

真机/清点发现两处漂移（2026-11-17）：
1. `collect` 里三处各自拼「名字（主键）」候选串，其中一处为绕 f-string 限制用 `+` 拼接，
   主键缺失时的写法还不一致 → 收进 `core.format_candidates()`。
2. 文档写死 dsh 降级形态的工具数：proposal 写「Registered 3 tools」，而壳实际自注册 6 个
   （packages/dsh/lib/index.js 里 `name: '<tool>'` 定义数 = 6）；dsh 壳里注释把 MCP client
   形态写成「12 工具」，实际随 packs（默认 core,collect=10，含 knowledge=12）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from vod_mcp.packs import core as _core

ROOT = Path(__file__).resolve().parents[1]
DSH_LIB = ROOT / "packages" / "dsh" / "lib" / "index.js"


def _shell_tool_count() -> int:
    """壳自注册的工具数（真值，不靠文档）。"""
    text = DSH_LIB.read_text(encoding="utf-8")
    return len(re.findall(r"^\s+name: '[a-z_]+',\s*$", text, flags=re.M))


def test_s233_format_candidates_contract():
    """S233：候选串唯一拼写点——名字（主键）、顿号分隔、空集给兜底串。"""
    cands = [{"id": "1", "name": "CodeArts"}, {"id": "5", "name": "Maas"}]
    assert _core.format_candidates(cands) == "CodeArts（1）、Maas（5）"
    assert _core.format_candidates([]) == "（名录为空）"
    assert _core.format_candidates(None, "（名录不可用）") == "（名录不可用）"
    # 缺主键时也保持同一形态（不写 None、不写空括号）
    assert _core.format_candidates([{"name": "智果"}]) == "智果（None）"


def test_s233_dsh_shell_registers_six_tools():
    """S233：dsh 壳自注册工具数 = 6（降级形态的判据，文档与注释都要对得上）。"""
    assert _shell_tool_count() == 6


@pytest.mark.parametrize("rel", ["docs/proposal.md", "docs/dsh-plugin-install.md"])
def test_s233_docs_registered_tools_match_shell(rel):
    """S233：文档里出现的 `Registered N tools` 必须等于壳的真值。"""
    text = (ROOT / rel).read_text(encoding="utf-8")
    nums = {int(n) for n in re.findall(r"Registered\s+(\d+)\s+tools", text)}
    assert nums, f"{rel} 没有 Registered N tools 的例子（删了这条判据就要一起改）"
    assert nums == {_shell_tool_count()}, (rel, nums)


def test_s233_shell_comment_does_not_hardcode_mcp_tool_count():
    """S233：壳注释不许把 MCP client 形态写成固定 12 工具（工具面随 packs）。"""
    text = DSH_LIB.read_text(encoding="utf-8")
    assert "（12 工具" not in text, "壳注释又把 MCP 形态写成固定 12 工具了"
    assert "工具面随 packs" in text