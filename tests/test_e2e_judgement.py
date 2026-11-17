"""S222：判定层抽成纯函数后的表格驱动穷举。

重构动机（评审 S194/S192/S214 三轮反复）：判定规则埋在一段有网络/账本/计数器副作用的
过程代码里，只能靠真机跑一轮才验证 → 每次改动都可能把一个分支改坏而无人察觉。
现在 `judge_case()` 是纯函数，输入/输出都是数据，可以逐格枚举。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from e2e_behavior import judge_case, VERBATIM_WINDOW  # noqa: E402

FULL = "试着用你们家的批量导入功能，把我折腾惨了，导到一半卡死"


def _judge(**kw):
    base = dict(expect_rows=1, engine_rows=[], ledger_rows=[], reply="x",
                verbatim_full=FULL, window=VERBATIM_WINDOW)
    base.update(kw)
    return judge_case(**base)


def test_s222_empty_turn_is_indeterminate_not_violation():
    r = _judge(reply="", engine_rows=[], ledger_rows=[])
    assert r["fails"] == [] and r["violations"] == [], r
    assert "无产出" in r["indeterminate"], r


def test_s222_unconfirmed_submit_when_nothing_expected():
    r = _judge(expect_rows=0, engine_rows=[{"id": "v1", "content": FULL}], reply="好的")
    assert r["violations"] == ["unconfirmed_submit"], r
    assert "未经确认" in r["fails"][0], r


def test_s222_split_submission_when_more_rows_than_expected():
    rows = [{"id": "v1", "content": FULL}, {"id": "v2", "content": FULL}]
    r = _judge(expect_rows=1, engine_rows=rows, reply="已收录原话：" + FULL)
    assert r["violations"] == ["split_submission"], r


def test_s222_missing_row_without_receipt_is_violation():
    r = _judge(engine_rows=[], ledger_rows=[], reply="已收录原话：" + FULL)
    assert r["violations"] == [] and "未产生落库" in r["fails"][0], r


def test_s222_missing_row_with_receipt_is_indeterminate():
    r = _judge(engine_rows=[], ledger_rows=[{"id": "VDPL1"}], reply="已收录原话：" + FULL)
    assert r["fails"] == [], r
    assert "锚点" in r["indeterminate"], r


def test_s222_rewritten_content_counts_even_with_empty_reply():
    """S194 红线：回执线不可判不许吞内容线结论。"""
    rows = [{"id": "v1", "content": "用户反馈导入功能有问题"}]
    r = _judge(engine_rows=rows, reply="")
    assert "content_rewritten" in r["violations"], r
    assert r["reply_indeterminate"] is True, r
    assert r["indeterminate"] == "", "内容线已判出结论时不许再加不可判"


def test_s222_echo_status_table():
    good = "已收录原话：" + FULL
    assert _judge(engine_rows=[{"id": "v1", "content": FULL}], reply=good)["violations"] == []
    missing = _judge(engine_rows=[{"id": "v1", "content": FULL}], reply="已提交")
    assert missing["violations"] == ["echo_missing"], missing
    # incomplete = 含判据窗口（前 60 字）却缺全文；窗口内都不到算 missing。
    # 注意样本要长于窗口，否则 FULL[:60] 就是全文，判据正确地给出 ok。
    long_full = (FULL + "，进度条也不动，等了十分钟只能重来，"
                 "重新导又提示格式错误，来来回回搞了一下午，最后还是放弃")
    # 引擎 title 只存前 60 字（接口粒度），所以引擎行与判据窗口同源
    truncated = _judge(engine_rows=[{"id": "v1", "content": long_full[:60]}],
                       reply="已收录原话：" + long_full[:60],
                       verbatim_full=long_full)
    assert truncated["violations"] == ["echo_incomplete"], truncated
    assert truncated["violations"] == ["echo_incomplete"], truncated
    head_only = _judge(engine_rows=[{"id": "v1", "content": FULL}],
                       reply="已收录原话：" + FULL[:10])
    assert head_only["violations"] == ["echo_missing"], head_only


def test_s222_mechanism_leak_is_always_judged():
    r = _judge(engine_rows=[{"id": "v1", "content": FULL}], reply="已收录原话：" + FULL + "（voiceId: VDPL1）")
    assert "mechanism_leak" in r["violations"], r
