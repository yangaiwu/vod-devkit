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
    # issue #1：架构缺陷台账与整改方案（五维走查产物，长期现役）
    "docs/architecture-defects.md", "docs/architecture-remediation.md",
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

# ── 文档 ↔ 代码一致性（本轮新增）：现役使用文档里引用的仓内路径必须真实存在 ──────────
# 历史台账（defects/remediation/decisions）是审计轨迹，允许记录"当时的路径"；这里只锁
# 读者会照着操作的那批文档，避免"文档写 collect.py / dispatch.py，读者找不到"。
_USAGE_DOCS = [
    "README.md", "README.en.md", "INSTALL.md", "QUICKSTART.md", "RELEASING.md",
    "docs/architecture.md", "docs/design.md", "docs/hooks.md", "docs/safety-model.md",
    "docs/scheme-overview.md", "docs/host-realverify.md", "docs/dsh-plugin-install.md",
    "docs/dsh-ui-collect.md", "docs/hermes-router.md",
]
_REF = re.compile(r"`((?:src|scripts|tests|assets|integrations|packages|npm)/[A-Za-z0-9_./\-]+)`")
# 明确标注"不在本仓 / 反例 / 当时 / 历史"的行豁免（对比引用与迁移记录）
_EXEMPT = re.compile(r"不在本仓|反例|勿照做|当时|历史|当年|方案稿|示例|对方|对标|huaweicloud|<|\*")
# 整节豁免：小节标题命中这些词时，整节路径都属于"外部仓/历史迁移"，不是现役路径
_SECTION_EXEMPT = re.compile(r"对方|对标|huaweicloud|迁移前|历史")


def test_usage_docs_reference_existing_paths():
    """现役使用文档里的 `src/…`/`scripts/…`/`tests/…` 路径必须存在（否则读者照抄即踩空）。"""
    missing = []
    for rel_doc in _USAGE_DOCS:
        p = ROOT / rel_doc
        if not p.exists():
            missing.append((rel_doc, 0, "<文档本身不存在>"))
            continue
        skip_section = False
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("#"):
                # 整节豁免：对标仓/历史/迁移记录整节都是外部路径或当时路径
                skip_section = bool(_SECTION_EXEMPT.search(line))
                continue
            if skip_section or _EXEMPT.search(line):
                continue
            for m in _REF.finditer(line):
                ref = m.group(1).rstrip(".,;:)")
                if not (ROOT / ref).exists():
                    missing.append((rel_doc, lineno, ref))
    assert not missing, "现役文档引用了不存在的路径：\n" + "\n".join(
        f"  {d}:{ln} → {ref}" for d, ln, ref in missing)
