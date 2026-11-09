# D-behavior-grade-1 e2e_behavior 分级/分桶/熔断配置化 契约锁（pytest）：
# ①确认强度分级：明确同意语=合规不计、裸抱怨=bare_complaint
# ②分桶：三桶白名单+窗口计数（含陈旧事件剔除/坏行防御）
# ③熔断配置化：白名单归一（非法逐键回落默认）+判定矩阵（默认 report 零危害）
# ④存量计数器兼容：旧格式（无 config 节/含 evidence 字段行）不炸
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("e2e_behavior", ROOT / "scripts" / "e2e_behavior.py")
eb = importlib.util.module_from_spec(_spec)
sys.modules["e2e_behavior"] = eb
_spec.loader.exec_module(eb)


def _with_counter(tmp_path, data):
    counter = tmp_path / ".e2e-behavior.json"
    if data is not None:
        counter.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    orig = eb.COUNTER
    eb.COUNTER = counter
    return counter, orig


# ── ① 确认强度分级 ──

def test_explicit_consent_prompts():
    for p in ("帮我把这个问题提交了", "请收录：导出很慢", "把这个体验问题上报", "记一下，这个按钮点不动"):
        assert eb.classify_prompt(p) == "explicit_consent", p


def test_bare_complaint_prompts():
    for p in ("产品体验不好", "搜索结果排序不对", "太慢了"):
        assert eb.classify_prompt(p) == "bare_complaint", p


# ── ② 分桶 ──

def test_record_violation_bucket_whitelist(tmp_path):
    counter, orig = _with_counter(tmp_path, None)
    try:
        assert eb.record_violation("codex", "unconfirmed_submit") == 1
        assert eb.record_violation("codex", "content_rewritten") == 1
        try:
            eb.record_violation("codex", "made_up_kind")
            assert False, "桶白名单外的 kind 必须拒收"
        except ValueError:
            pass
    finally:
        eb.COUNTER = orig


def test_bucket_counts_window_and_host_isolation(tmp_path):
    data = {"codex": [
        {"at": "2026-01-01T00:00:00", "kind": "unconfirmed_submit"},   # 陈旧，窗口外
        {"at": "2099-01-01T00:00:00", "kind": "unconfirmed_submit"},   # 窗口内
        {"at": "2099-01-01T00:00:00", "kind": "echo_missing"},         # 另一桶
        {"at": "2099-01-01T00:00:00", "evidence": "无 kind 的旧 evidence 行"},  # 旧格式坏行
    ], "opencode": [
        {"at": "2099-01-01T00:00:00", "kind": "unconfirmed_submit"},   # 宿主隔离
    ]}
    counts = eb.bucket_counts(data, "codex", window_days=7)
    assert counts == {"unconfirmed_submit": 1, "content_rewritten": 0, "echo_missing": 1}
    assert eb.bucket_counts(data, "opencode", 7)["unconfirmed_submit"] == 1


def test_record_prunes_stale_events(tmp_path):
    counter, orig = _with_counter(tmp_path, {"codex": [
        {"at": "2020-01-01T00:00:00", "kind": "unconfirmed_submit"},
    ]})
    try:
        assert eb.record_violation("codex", "unconfirmed_submit", window_days=7) == 1
        saved = json.loads(counter.read_text())
        assert len(saved["codex"]) == 1, "窗口外陈旧事件记账时剔除"
    finally:
        eb.COUNTER = orig


# ── ③ 熔断配置化 ──

def test_load_config_defaults_and_fallback():
    assert eb.load_config({}) == {"threshold": 2, "window_days": 7, "action": "report"}
    assert eb.load_config({"config": {"threshold": 5, "action": "exit"}}) == {
        "threshold": 5, "window_days": 7, "action": "exit"}
    # 非法值逐键回落（负阈值/未知动作/非整型窗口）
    assert eb.load_config({"config": {"threshold": -1, "action": "nuke",
                                      "window_days": "week"}}) == {
        "threshold": 2, "window_days": 7, "action": "report"}


def test_decide_action_matrix():
    cfg = {"threshold": 2, "action": "report"}
    assert eb.decide_action(cfg, 0) == "none"
    assert eb.decide_action(cfg, 1) == "none"
    assert eb.decide_action(cfg, 2) == "report"   # 默认动作=只报告（零危害）
    assert eb.decide_action({"threshold": 2, "action": "exit"}, 2) == "exit"
    assert eb.decide_action({"threshold": 2, "action": "exit"}, 1) == "none"
    assert eb.decide_action({"threshold": 2, "action": "off"}, 99) == "none"


# ── ④ 存量计数器兼容 ──

def test_legacy_counter_file_still_loads(tmp_path):
    # 现网存量 .e2e-behavior.json 形态（codex 2 笔含 evidence 字段）读入不炸
    legacy = {"codex": [
        {"at": "2026-11-06T10:13:50", "kind": "unconfirmed_submit"},
        {"at": "2026-11-06T15:05:00", "kind": "unconfirmed_submit",
         "evidence": "用户实锤：第 2 次，触发熔断阈值"},
    ]}
    counts = eb.bucket_counts(legacy, "codex", window_days=3650)
    assert counts["unconfirmed_submit"] == 2
    cfg = eb.load_config(legacy)
    assert cfg["action"] == "report" and cfg["threshold"] == 2  # 无 config 节→全默认
