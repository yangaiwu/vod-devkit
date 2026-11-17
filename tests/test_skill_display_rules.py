"""SKILL 话术契约：草稿展示的缺失声明（S183）与分型话术（S184）。

为什么锁文案：这些是**模型直接读到并照做**的指令，删一句就等于把纪律撤掉，但代码层
没有任何迹象。用文本断言把关键约束钉住：改话术必须同批改用例。
"""
from pathlib import Path

_RAW = (Path(__file__).resolve().parent.parent
        / "assets" / "skills" / "vod-feedback-collect" / "SKILL.md").read_text(encoding="utf-8")
SKILL = _RAW
# 紧凑视图：SKILL 是长行折行的正文，断言跨行句子必须先去掉全部空白
COMPACT = "".join(_RAW.split())


def test_s183_draft_display_declares_missing_fields():
    assert "（操作步骤/期望表现：用户未提供）" in COMPACT
    assert "只缺一个就只点名那一个" in COMPACT
    assert "禁止写进content" in COMPACT and "禁止上送引擎" in COMPACT
    assert "推测句" in COMPACT, "必须显式禁止补写推测"


def test_s184_feedback_triage_and_suggestion_script():
    """S184：分型规则的优先级与建议型话术必须逐字在文里（模型照读的就是这段）。"""
    assert "现象词优先" in COMPACT or "现象词优先" in SKILL.replace(" ", "")
    assert "报错" in COMPACT and "卡死" in COMPACT and "没反应" in COMPACT
    assert "判不了按缺陷型" in COMPACT, "兜底必须保守"
    assert "这条更像改进建议" in COMPACT
    assert "希望它变成" in COMPACT
    assert "禁止索要操作步骤" in COMPACT
    assert "不写problem_type标签" in COMPACT or "不写 problem_type 标签" in SKILL
