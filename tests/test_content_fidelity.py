"""反例集：原话逐字与分类值域（S101/S102，2026-11-11 CodeArts Agent 真机实锤）。

首夜实测（会话 ses_e34d750d，单轮）：
- 用户说："产品体验很糟糕"
- 落库 content："产品体验很糟糕\\n操作不流畅，使用不方便"  ← 后半句是模型编的
- tags=["易用性"]                                             ← 六类之外的自造值

两个问题都不是"提交失败"，而是"提交内容不是你"。引擎按内容逐字做幂等，
扩写=造出另一条声音；自造 tag 白名单会丢，等于白填。这里把它们锁成反例集，
配合 skills/vod-feedback-collect 的正反例段。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "vod-feedback-collect" / "SKILL.md").read_text(encoding="utf-8")
PROPOSAL = (ROOT / "docs" / "proposal.md").read_text(encoding="utf-8")

PROBLEM_TYPES = ("产品缺陷", "技术业务咨询", "体验改进", "主观评价", "无效问题", "功能需求")


def test_s101_content_verbatim_rule_and_counterexample():
    """S101 反例：content 只允许用户原话，扩写=违规（技能里必须有正反例）。"""
    assert "content 逐字铁律" in SKILL
    assert '正例：用户说"产品体验很糟糕" → content = "产品体验很糟糕"' in SKILL
    assert "操作不流畅，使用不方便" in SKILL, "真机反例必须留在技能里（不写就会重犯）"
    assert "多一个字都算违规" in SKILL


def test_s102_tags_domain_listed_and_no_freeform():
    """S102：tags 值域=六类，技能必须写全并禁止自造。"""
    for t in PROBLEM_TYPES:
        assert t in SKILL, f"技能缺值域项：{t}"
    assert "禁止自造分类" in SKILL
    assert "易用性" in SKILL, "真机自造值要作为反例保留"


def test_cases_are_registered_in_proposal():
    for cid in ("S101", "S102"):
        assert f"| {cid} |" in PROPOSAL, f"{cid} 未进用例表"
