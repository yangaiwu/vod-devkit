"""S230：当前态文档的路径卫生（旧布局不许再出现在现役文档里）。

背景：结构迁移（2026-11-15）把 `contract/ safety/ skills/ hooks/` 收进 `assets/` 与
`integrations/hermes/hooks/`，但现役文档里残留了十处裸路径——读者照着文档去仓根
找不到那个文件。历史台账（decisions.md、CHANGELOG）不改：那里记的是当时的路径。

判据两条：
1. 现役文档内 markdown 相对链接必须可达（零坏链）。
2. 现役文档不得出现未加前缀的旧布局路径；合法的两种前缀是 `assets/…` /
   `integrations/hermes/hooks/…`，以及载荷内平铺语境（`<payload>/…`、载荷物化树）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 现役文档（历史台账与生成物不在内）
CURRENT = [
    "README.md", "README.en.md", "RELEASING.md",
    "docs/architecture.md", "docs/design.md", "docs/proposal.md",
    "docs/hooks.md", "docs/safety-model.md", "docs/dsh-ui-collect.md",
    "docs/dsh-plugin-install.md", "docs/hermes-router.md", "docs/host-realverify.md",
]

# 旧布局裸路径（左侧不得紧跟 / 或字母，避免误伤 assets/… 与 integrations/…）
LEGACY = re.compile(
    r"(?<![\w/<])("
    r"contract/tools\.schema\.json"
    r"|safety/policy\.json"
    r"|skills/vod-core/SKILL\.md"
    r"|hooks/vod_(?:router|guard)\.py"
    r")"
)
# 载荷内平铺语境：这些行允许出现裸路径（发布布局按设计就是根级平铺）
PAYLOAD_CONTEXT = re.compile(r"载荷|payload|<PAYLOAD>|载荷物化|发布布局")

_LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")


def _docs() -> list[Path]:
    return [ROOT / p for p in CURRENT if (ROOT / p).exists()]


def test_s230_current_docs_have_no_broken_relative_links():
    bad = []
    for p in _docs():
        for m in _LINK.finditer(p.read_text(encoding="utf-8")):
            target = m.group(1).split()[0]
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not (p.parent / target).resolve().exists():
                bad.append(f"{p.relative_to(ROOT)} -> {target}")
    assert not bad, "现役文档存在坏链：\n" + "\n".join(bad)


def test_s230_current_docs_have_no_bare_legacy_paths():
    bad = []
    for p in _docs():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if PAYLOAD_CONTEXT.search(line):
                continue
            if LEGACY.search(line):
                bad.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:100]}")
    assert not bad, ("现役文档里出现旧布局裸路径（应写 assets/… 或 "
                     "integrations/hermes/hooks/…）：\n" + "\n".join(bad))


def test_s230_boundary_section_points_at_decision():
    """S230 附带：设计文档的边界节必须回指 D-boundary-1（避免只留一句口号）。"""
    text = (ROOT / "docs/design.md").read_text(encoding="utf-8")
    assert "九·五、插件边界" in text and "D-boundary-1" in text