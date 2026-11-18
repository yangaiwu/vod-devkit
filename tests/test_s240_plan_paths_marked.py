"""S240：文档里的"不存在的路径"必须显式标注（计划/反例/不在本仓）。

来源：按 S230 的路径卫生规则扫现役文档，仍有一批**故意**提到的不存在路径——
计划中的目录（docs/reports/、integrations/hooks/）、反例（plugins/vod-devkit/src/vod_mcp/）、
以及不在本仓的技能侧探针（scripts/dsh-mcp-probe.py）。这些不能删（删了丢信息），
但必须让读者一眼看出"别去找"。规则：同一行必须有标注词。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = ("计划", "未建", "反例", "尚未存在", "不在本仓", "不在仓")

# token → 允许出现的文件
CASES = {
    "docs/reports/": ("docs/architecture.md",),
    "integrations/hooks/": ("docs/architecture.md",),
    "plugins/vod-devkit/src/vod_mcp/": ("docs/architecture.md",),
    "dsh-mcp-probe.py": ("docs/design.md",),
}


def test_s240_placeholder_paths_are_annotated():
    bad = []
    for token, files in CASES.items():
        for rel in files:
            for i, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
                if token not in line:
                    continue
                if not any(m in line for m in MARKERS):
                    bad.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not bad, ("以下行提到不存在的路径但没标注（计划/反例/不在本仓）：\n" + "\n".join(bad))


def test_s240_markers_are_present_where_expected():
    """反向锁：确认这些标注真的存在，别被顺手删掉。"""
    arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    assert "计划内，当前未建目录" in arch
    assert "反例，勿照做" in arch
    assert "尚未存在的共享位" in arch
    design = (ROOT / "docs/design.md").read_text(encoding="utf-8")
    assert "不在本仓" in design
