"""用例花名册门禁（借鉴 huaweicloud-devkit e2e-cases-roster 纪律）。

2026-11-11 升级：从「门禁现场正则扫文档」改为「显式清单 + 对账」——
tests/case_roster.json 是可审阅的单一真源（devkit 的做法是 roster 与 runner
共用同一模块，手写清单/现场解析都会静默漂移）。重录：
  python3 scripts/sync_case_roster.py

四条断言：
1. 花名册 == proposal 定义的用例号（文档改了没重录 → 红，给重录命令）
2. 有承载的条目，承载文件必须真实存在且正文里出现该编号（防"写了承载其实没有"）
3. 豁免（carrier=null）必须与 tests/case_roster_baseline.txt 完全一致（棘轮基线只缩）
4. 已补承载的条目不许继续留在豁免里（否则基线变永久豁免清单）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import case_roster as roster  # noqa: E402

ROSTER = ROOT / "tests" / "case_roster.json"


def _load() -> dict:
    assert ROSTER.exists(), "花名册缺失：python3 scripts/sync_case_roster.py"
    return json.loads(ROSTER.read_text(encoding="utf-8"))


def test_roster_matches_proposal_definition():
    data = _load()
    defined = set(roster.defined_cases())
    listed = set(data["cases"])
    assert defined == listed, (
        "花名册与 proposal 不一致（新增/删除用例后必须重录）：\n"
        f"  文档有、花名册无：{roster.ordered(defined - listed)}\n"
        f"  花名册有、文档无：{roster.ordered(listed - defined)}\n"
        "  重录：python3 scripts/sync_case_roster.py")


def test_each_carried_case_really_appears_in_its_carrier():
    data = _load()
    missing_files, missing_marks = [], []
    cache = {}
    for cid, meta in data["cases"].items():
        carrier = meta.get("carrier")
        if not carrier:
            continue
        p = ROOT / carrier
        if not p.exists():
            missing_files.append(f"{cid} → {carrier}（文件不存在）")
            continue
        if carrier not in cache:
            cache[carrier] = roster.expand(p.read_text(encoding="utf-8"))
        if cid not in cache[carrier]:
            missing_marks.append(f"{cid} → {carrier}（正文里没有该编号）")
    assert not missing_files and not missing_marks, (
        "花名册承载不实（写了承载但文件/正文对不上）：\n  "
        + "\n  ".join(missing_files + missing_marks))


def test_waivers_equal_baseline_ratchet():
    data = _load()
    listed = set(data.get("waivers") or [])
    baseline = set(roster.baseline_waivers())
    assert listed == baseline, (
        "花名册 waivers 与 tests/case_roster_baseline.txt 不一致：\n"
        f"  只在花名册：{roster.ordered(listed - baseline)}\n"
        f"  只在基线：{roster.ordered(baseline - listed)}\n"
        "  重录：python3 scripts/sync_case_roster.py")


def test_no_waiver_that_already_has_a_carrier():
    """棘轮只缩：已经补上承载的用例必须从基线/豁免里删掉。"""
    data = _load()
    stale = [cid for cid, meta in data["cases"].items()
             if meta.get("carrier") and cid in set(data.get("waivers") or [])]
    assert not stale, (
        "以下用例已有承载却仍在豁免清单（基线必须只缩）：\n  "
        + "、".join(roster.ordered(stale))
        + "\n  从 tests/case_roster_baseline.txt 删除后重录花名册。")


def test_waivers_are_real_case_ids():
    data = _load()
    ghosts = set(data.get("waivers") or []) - set(data["cases"])
    assert not ghosts, "豁免里有 proposal 不存在的幽灵编号：\n  " + "、".join(roster.ordered(ghosts))