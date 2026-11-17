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


def test_s191_self_reference_skips_product_ask():
    """S191：自指 + 安装先验 → 不许再追问产品（模型照读的就是这句）。

    真机实测（2026-11-17，glm-5.3-flash / codex）：原话「……试着用你们家的批量导入功能……」
    明明满足 D-attrib-binding-1 的自指条件（`attribution.attribute` 直判
    `source=install_binding / product=CodeArts`），宿主却仍问「这条反馈可能是哪个产品的？」。
    根因是 SKILL 只写了「没有任何产品线索 → 取候选后问一次」，没写「自指命中先验时不要再问」，
    模型于是把「没点名产品」等同于「没线索」。
    """
    assert "自指" in COMPACT, "归因段必须出现「自指」这一判据"
    assert "别再问产品" in COMPACT or "不再问产品" in COMPACT, \
        "必须明确写：自指命中安装先验时不再追问产品"
    assert "install_binding" in COMPACT, "要给出可佐证的来源标记（草稿回执里能看到）"
