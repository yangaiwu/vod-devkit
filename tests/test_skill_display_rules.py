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
