"""S236：e2e 引擎行必须收窄到本轮 voiceId，外来行不许冒充"改写"。

真机实测（2026-11-17/18）：C1/C4 两条报「原话在 60 字窗口内被改写」，追下去发现命中
的是**同时间窗里别人/人工发的验证声音**——判据把 `engine_rows_since(t0)` 的所有行都当
候选，而囤积档并发提交非常常见。收窄口径：本机账本本轮回执里的 voiceId 为白名单。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e2e_behavior as e2e  # noqa: E402


def _row(rid, content):
    return {"id": rid, "content": content}


def test_s236_foreign_row_is_dropped_and_never_reported_as_rewrite():
    """同窗口外来行必须被排除：不参与行数判定，也不参与原话保真判定。"""
    ledger = [{"id": "VDPL-A", "voiceId": "VDPL-A"}]
    engine = [_row("VDPL-A", "我们家网页卡，回复也慢。"),      # 本轮（内容不同）
              _row("VDPL-X", "别人发的一条完全无关的声音")]      # 外来
    scoped, note = e2e.scope_engine_rows(engine, ledger)
    assert [r["id"] for r in scoped] == ["VDPL-A"]
    assert "排除 1 行" in note

    verdict = e2e.judge_case(expect_rows=1, engine_rows=scoped, ledger_rows=ledger,
                             reply="已收录原话：我们家网页卡，回复也慢。",
                             verbatim_full="我们家网页卡，回复也慢。")
    assert not verdict["fails"], verdict
    assert not verdict["indeterminate"], verdict


def test_s236_without_ledger_rows_keeps_engine_rows_untouched():
    """账本没有回执（囤积档不可见/老路径）时保持原样，三态判定负责报不可判。"""
    engine = [_row("VDPL-X", "x")]
    scoped, note = e2e.scope_engine_rows(engine, [])
    assert scoped == engine and note == ""


def test_s236_ledger_without_engine_row_is_indeterminate_not_violation():
    """本轮有回执但引擎行被收窄掉 → 落库线不可判（不是"改写"，也不是"未提交"）。"""
    ledger = [{"id": "VDPL-B", "voiceId": "VDPL-B"}]
    engine = [_row("VDPL-X", "外来")]
    scoped, note = e2e.scope_engine_rows(engine, ledger)
    assert scoped == [] and "排除 1 行" in note
    verdict = e2e.judge_case(expect_rows=1, engine_rows=scoped, ledger_rows=ledger,
                             reply="已收录原话：本月真原话", verbatim_full="本月真原话")
    assert not verdict["fails"], verdict
    assert "不可判" in verdict["indeterminate"], verdict


def test_s236_foreign_text_identical_prefix_is_not_matched():
    """外来行即使前缀撞车，也不会再被当成本轮落库行（这正是 C1/C4 假红的形态）。"""
    ledger = [{"id": "VDPL-C", "voiceId": "VDPL-C"}]
    engine = [_row("VDPL-C", "试着用你们家的批量导入功能，把我折腾惨了"),
              _row("VDPL-Y", "我们家网页卡，回复也慢。")]
    scoped, _ = e2e.scope_engine_rows(engine, ledger)
    verdict = e2e.judge_case(expect_rows=1, engine_rows=scoped, ledger_rows=ledger,
                             reply="已收录原话：试着用你们家的批量导入功能，把我折腾惨了",
                             verbatim_full="试着用你们家的批量导入功能，把我折腾惨了")
    assert not verdict["fails"], verdict