"""多宿主描述前置回归锁（M1：docs/hermes-feedback-router/design.md §五）。

不变量：采集技能 SKILL.md 的 description 前 57 字符（Hermes 索引可见预算，
实测观察值）内必须包含核心触发词——业界实锤宿主对 description 静默截断，
触发词落在预算外=自动路由无信号（8bdc225 修正的事故形态，防回归）。

同时锁定总长上限（Anthropic 指南 150-400 字符量级；防无界增长挤占预算，
呼应另一防线 D-desc-budget-1 对 contract 侧的 1500 上限）。
"""
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "vod-feedback-collect" / "SKILL.md"

VISIBLE_BUDGET = 57      # Hermes 索引实测可见前缀
DESC_MAX = 400           # Anthropic 指南上限量级
# 预算内核心触发词（须同时：可见预算内 + 属于 router 词表；「抱怨」是类目词不作子集校验）
MUST_IN_BUDGET = ("体验差", "提单", "太慢")


def _description() -> str:
    s = SKILL.read_text(encoding="utf-8")
    for line in s.split("\n"):
        if line.startswith("description: '"):
            return line.split("description: '", 1)[1].rsplit("'", 1)[0]
    raise AssertionError("SKILL.md 缺 description frontmatter")


def test_m1_trigger_words_within_visible_budget():
    desc = _description()
    head = desc[:VISIBLE_BUDGET]
    for kw in MUST_IN_BUDGET:
        assert kw in head, (
            f"触发词「{kw}」落在 {VISIBLE_BUDGET} 字符可见预算外——"
            "自动路由无信号（8bdc225 事故形态回归）")


def test_m1b_description_length_bounded():
    desc = _description()
    assert 0 < len(desc) <= DESC_MAX, (
        f"description {len(desc)} 字符超上限 {DESC_MAX}（挤占宿主预算）")


def test_m1c_description_triggers_aligned_with_router_table():
    """一致性：description 内的触发词必须是 router.TRIGGER_WORDS 子集
    （两处分别服务可见预算/全量变体，语义漂移即报警）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "vod_router_m1c",
        Path(__file__).resolve().parent.parent / "hermes-plugin"
        / "vod-feedback-router" / "router.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    desc = _description()
    for kw in MUST_IN_BUDGET:
        assert kw in mod.TRIGGER_WORDS, f"description 触发词「{kw}」不在 router 词表"
        assert kw in desc[:VISIBLE_BUDGET]
    # router 高频词至少一个反哺 description（触发信号不缩水）
    assert any(w in desc for w in ("太慢", "报错"))
