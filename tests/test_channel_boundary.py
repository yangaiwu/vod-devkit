"""S226：反馈通道边界（同机多技能时的判据）。

背景（2026-11-17 下游反馈）：devspace 同时装 huawei-cloud-vod-collector（反馈→GitCode 工单）
与我们 vod-feedback-collect（反馈→VOD 平台），触发词「体验差/有 bug/报告问题」字面重复，
同一条抱怨会随机进其中一个通道，用户无感知。我们改不了对方技能，能做的是把判据写进
我们自己的技能与部署须知：**看用户要的产物，不看词**。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_s226_skill_has_channel_boundary_section():
    text = (ROOT / "assets/skills/vod-feedback-collect/SKILL.md").read_text(encoding="utf-8")
    assert "## 渠道边界" in text
    # 三条判据必须都在：建单动词、VOD 动词、含糊时问一次
    for kw in ("提个单", "提交反馈", "只进一个通道", "问的去向只问一次"):
        assert kw in text, f"渠道边界缺判据：{kw}"


def test_s226_readme_warns_against_double_install():
    zh = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "两个反馈采集技能" in zh
    assert "huawei-cloud-vod-collector" in zh
    assert "two feedback-capture skills" in en


def test_s226_boundary_precedence_is_stated():
    """边界优先于触发词——写在技能正文里，不许只放在 README。"""
    text = (ROOT / "assets/skills/vod-feedback-collect/SKILL.md").read_text(encoding="utf-8")
    assert "这一条优先于本技能其它触发规则" in text
