"""S198：套件编排抽成可测单元（run_suite），出口只留一处判定。

为什么重构：`main()` 里现在把「逐案循环 + 三类不结论的打印 + 两条异常分支 + 退出码计算」
混在一起，退出码在**三个地方**各算一次（正常收尾、EngineUnavailable、EngineAuthError），
上一轮评审的 P2a（异常路径丢掉已收违规）正是这种重复的直接后果。抽 `run_suite()` 后：
- 编排与判定分开，聚合结果可单测（不用起宿主、不用真引擎）；
- 退出码只在 main 里算一次，异常路径与正常路径共用同一个输入（Summary）；
- 打印文案仍留在原处，行为不变。

`Summary` 是聚合值的唯一形状：fails / indeterminate / reply_unjudged / total_rows /
processed / abort。`abort` 只有 "engine-unavailable" 与 "engine-auth" 两态。
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))


def _cfg():
    return {"threshold": 2, "window_days": 7, "action": "report"}


def _case(cid, expect="submit_consent"):
    return {"id": cid, "rule": "r", "prompt": "帮我记录反馈：{t}{content_start}你们家卡死了",
            "anchor": "帮我记录反馈", "tail": "卡死", "expect": expect}


def test_s198_run_suite_aggregates_all_three_shapes(monkeypatch, capsys):
    from e2e_behavior import run_suite

    results = {
        "c-pass": {"case": "c-pass", "rule": "r", "fails": [], "rows": [{"id": "1", "content": "x"}]},
        "c-fail": {"case": "c-fail", "rule": "r", "fails": ["真缺陷"],
                   "rows": [{"id": "2", "content": "y"}]},
        "c-ind": {"case": "c-ind", "rule": "r", "fails": [], "rows": [],
                  "indeterminate": "宿主回合无产出（回复为空且零落库）"},
        "c-ri": {"case": "c-ri", "rule": "r", "fails": [], "rows": [{"id": "3", "content": "z"}],
                 "reply_indeterminate": True},
    }

    def fake_run_case(host, case, cfg, model=None):
        return results[case["id"]]

    monkeypatch.setattr("e2e_behavior.run_case", fake_run_case)
    cases = [_case("c-pass"), _case("c-fail"), _case("c-ind"), _case("c-ri")]
    s = run_suite("codex", cases, _cfg(), "glm-5.3-flash")

    assert s.fails == ["真缺陷"]
    assert s.indeterminate == ["c-ind"]
    assert s.reply_unjudged == ["c-ri"]
    assert s.total_rows == 3 and s.processed == 4
    assert s.abort is None

    out = capsys.readouterr().out
    assert "[PASS] c-pass" in out and "[FAIL] c-fail" in out
    assert "[不可判] c-ind" in out and "[回执不可判] c-ri" in out


def test_s198_run_suite_abort_keeps_collected_fails(monkeypatch, capsys):
    from e2e_behavior import EngineUnavailable, run_suite, exit_code

    def fake_run_case(host, case, cfg, model=None):
        if case["id"] == "c-boom":
            raise EngineUnavailable("引擎 502")
        return {"case": case["id"], "rule": "r", "fails": ["真缺陷"], "rows": []}

    monkeypatch.setattr("e2e_behavior.run_case", fake_run_case)
    s = run_suite("codex", [_case("c-fail"), _case("c-boom"), _case("c-tail")], _cfg())

    assert s.abort == "engine-unavailable"
    assert s.fails == ["真缺陷"], "异常前已判的违规必须留在聚合里"
    assert s.processed == 1, "processed=已完成条数（抛异常那条没跑完，不算）"
    assert exit_code(s.fails, "report", indeterminate=True) == 1
    out = capsys.readouterr().out
    assert "FAIL(异常前已判)" in out, "异常报文要把已判违规打出来"


def test_s198_run_suite_auth_error_is_distinct_abort(monkeypatch, capsys):
    from e2e_behavior import EngineAuthError, run_suite, exit_code

    monkeypatch.setattr("e2e_behavior.run_case",
                        lambda *a, **kw: (_ for _ in ()).throw(EngineAuthError("引擎 401")))
    s = run_suite("codex", [_case("c1")], _cfg())
    assert s.abort == "engine-auth"
    assert exit_code(s.fails, "report", auth_error=True) == 4


def test_s198_single_exit_definition():
    """退出码只许有一处定义（decide_exit 这个薄包装已合并进 exit_code）。"""
    import e2e_behavior as e2e
    assert not hasattr(e2e, "decide_exit"), "重复的出口判定函数必须删掉（P2a 的根因）"