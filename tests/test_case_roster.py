"""用例花名册门禁（借鉴 huaweicloud-devkit e2e-cases-roster 纪律）。

背景（2026-11-11 实测）：proposal 定义了 131 个用例号，其中 72 个在
design/docs 与任何测试文件里都找不到痕迹——不代表没测，而是无法自动对账，
文档里的验收承诺只能靠人记。devkit 的原话是 「names derive from the roster,
never from hand lists that silently drift」。

本门禁的三条断言：
1. proposal 里定义（行首 `S/U/DG + 数字`）的每个用例号，必须在本仓里被
   「承载」——出现在 docs/design.md、任一 tests/*.py 或 dsh/test/*.mjs 中
   （区间写法 S67-S70 会展开）。新增用例当场没有承载即红。
2. 历史欠账进 tests/case_roster_baseline.txt（棘轮基线）：基线只许缩不许增。
3. 基线里已经补上承载的条目必须从基线删除（否则基线会变成永久豁免清单）。

承载不是"必须有一条同名测试"——它是可对账痕迹的最低要求；有承载 ≠ 有断言，
但无承载 = 没人能自动回答"这条承诺兑现了吗"。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_ID = re.compile(r"(?m)^(?:\|\s*)?(?:[-*]\s*)?(S|U|DG)(\d{1,3})\b")
_ID_ANY = re.compile(r"\b(S|U|DG)(\d{1,3})\b")
_RANGE = re.compile(r"\b(S|U|DG)(\d{1,3})\s*[-–~]\s*(?:S|U|DG)?(\d{1,3})\b")


def _ordered(ids):
    def key(x):
        m = re.match(r"\D*", x)
        n = re.search(r"\d+", x)
        return (m.group() if m else x, int(n.group()) if n else 0)
    return sorted(ids, key=key)


def _expand(text: str) -> set:
    """出现过的用例号（含 S67-S70 这类区间写法展开）。"""
    out = {f"{a}{b}" for a, b in _ID_ANY.findall(text)}
    for a, x, y in _RANGE.findall(text):
        out |= {f"{a}{n}" for n in range(int(x), int(y) + 1)}
    return out


def _carrier_texts() -> list:
    files = [ROOT / "docs" / "design.md"]
    files += sorted((ROOT / "tests").glob("*.py"))
    files += sorted((ROOT / "dsh" / "test").glob("*.mjs"))
    return [f for f in files if f.exists()]


def _defined() -> list:
    prop = (ROOT / "docs" / "proposal.md").read_text(encoding="utf-8")
    return _ordered({f"{a}{b}" for a, b in _ID.findall(prop)})


def _carried() -> set:
    out = set()
    for f in _carrier_texts():
        out |= _expand(f.read_text(encoding="utf-8"))
    return out


def _baseline() -> list:
    p = Path(__file__).parent / "case_roster_baseline.txt"
    if not p.exists():
        return []
    return [x.strip() for x in p.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


def test_every_proposal_case_has_a_carrier_or_a_baseline_waiver():
    defined = _defined()
    assert defined, "proposal 里没有解析到任何用例号——解析规则或文档结构变了"
    missing = set(defined) - _carried()
    waivers = set(_baseline())
    new_gaps = _ordered(missing - waivers)
    assert not new_gaps, (
        "新增用例没有承载痕迹（docs/design.md / tests/*.py / dsh/test/*.mjs 均未出现）：\n  "
        + "、".join(new_gaps)
        + "\n用例号必须能对上承载——写明落在哪个设计节/哪个测试，再提交。")


def test_baseline_is_a_shrinking_ratchet():
    """基线只许缩：已补载的条目必须从基线删掉，否则豁免清单永久化。"""
    waivers = set(_baseline())
    still_missing = set(_defined()) - _carried()
    stale = _ordered(waivers - still_missing)
    assert not stale, (
        "基线条目已获得承载，请从 tests/case_roster_baseline.txt 删除：\n  "
        + "、".join(stale))


def test_baseline_entries_are_real_case_ids():
    """基线里不许有幽灵编号（写错/已删用例），否则棘轮对账失真。"""
    defined = set(_defined())
    ghosts = _ordered(set(_baseline()) - defined)
    assert not ghosts, "基线里有 proposal 不存在的用例号：\n  " + "、".join(ghosts)