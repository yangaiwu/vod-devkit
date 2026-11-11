"""用例花名册的共享逻辑（借鉴 huaweicloud-devkit：roster 与 runner 共用同一模块）。

只做扫描与映射，不含断言——生成器（scripts/sync_case_roster.py）与门禁
（tests/test_case_roster.py）都 import 本模块，保证「文档里的用例号」与「花名册
文件」不会各自漂移。

扫描口径（与门禁同源，改这里只改一处）：
- 定义：docs/proposal.md 行首（表格行/列表项也认）的 S/U/DG + 数字
- 承载：docs/design.md、tests/*.py、dsh/test/*.mjs 里出现的同一编号（区间写法展开）
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ID = re.compile(r"(?m)^(?:\|\s*)?(?:[-*]\s*)?(S|U|DG)(\d{1,3})\b")
_ID_ANY = re.compile(r"\b(S|U|DG)(\d{1,3})\b")
_RANGE = re.compile(r"\b(S|U|DG)(\d{1,3})\s*[-–~]\s*(?:S|U|DG)?(\d{1,3})\b")


def ordered(ids) -> list:
    def key(x):
        m = re.match(r"\D*", x)
        n = re.search(r"\d+", x)
        return (m.group() if m else x, int(n.group()) if n else 0)
    return sorted(ids, key=key)


def expand(text: str) -> set:
    out = {f"{a}{b}" for a, b in _ID_ANY.findall(text)}
    for a, x, y in _RANGE.findall(text):
        out |= {f"{a}{n}" for n in range(int(x), int(y) + 1)}
    return out


def carrier_files() -> list:
    files = [ROOT / "docs" / "design.md"]
    files += sorted((ROOT / "tests").glob("*.py"))
    files += sorted((ROOT / "dsh" / "test").glob("*.mjs"))
    return [f for f in files if f.exists()]


def defined_cases() -> list:
    prop = (ROOT / "docs" / "proposal.md").read_text(encoding="utf-8")
    return ordered({f"{a}{b}" for a, b in _ID.findall(prop)})


def carry_map() -> dict:
    """case id → 第一个承载它的文件（相对仓根路径）；无承载为 None。"""
    out = {}
    for f in carrier_files():
        rel = str(f.relative_to(ROOT))
        for cid in expand(f.read_text(encoding="utf-8")):
            out.setdefault(cid, rel)
    return out


def baseline_waivers() -> list:
    p = ROOT / "tests" / "case_roster_baseline.txt"
    if not p.exists():
        return []
    return [x.strip() for x in p.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]