"""Python ↔ dsh(JS) 归因对账（F1）：同一份 fixture，两侧各自断言。

为什么需要它：dsh 壳用 JS 重写了归因（buildAliasIndex / matchProducts /
attributeProduct），与 vod_mcp/attribution.py 只靠注释声明"语义对齐"，没有任何
对账。2026-11-15 实测就抓到两处真实漂移：
  · 「maas」（小写）—— Python 从登记名派生大小写变体命中，JS 未派生 → UNKNOWN
  · 「码道」—— Python 有 BRAND_ALIASES 品牌俗称表，JS 缺 → UNKNOWN
两处都会让 dsh 用户的口语反馈掉进"无产品归属"，而 Python 侧行为正确。

做法（不引入跨运行时依赖）：fixture 是唯一真源，
  · 本用例断言 Python 侧的 attribute() == fixture.expect
  · dsh/test/attribution-parity.test.mjs 断言 JS 侧 == fixture.expect
任一侧漂移，它自己的测试套件就红——这就是"对账测试"而不是"比对快照"。
"""
import json
from pathlib import Path

import pytest

from vod_mcp import attribution

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "attribution_parity.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_covers_known_drift_cases():
    """fixture 必须长久覆盖实测漂移过的两种写法（大小写变体 / 品牌俗称）。"""
    texts = [c["text"] for c in _fixture()["cases"]]
    assert any("maas" in t.lower() and t.strip() != "MaaS" for t in texts), \
        "缺「小写 maas」用例——这是 JS 侧曾漏派生大小写变体的实锤漂移点"
    assert any("码道" in t for t in texts), \
        "缺「码道」用例——这是 JS 侧曾缺品牌俗称表的实锤漂移点"


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda c: c["text"][:24])
def test_python_attribution_matches_fixture(case):
    meta = _fixture()["meta"]
    got = attribution.attribute(case["text"], meta)
    expect = case["expect"]
    assert got.get("product") == expect["product"], (
        f"Python 侧归因漂移：{case['text']!r} → {got} / 期望 {expect}")
    assert got.get("productName") == expect["productName"]
    assert got.get("source") == expect["source"]