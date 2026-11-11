"""征询话术门禁（「给范围，不给结论」，2026-11-11 负责人拍板 A）。

真机观测（CodeArts Agent 会话 ses_e34d750d）：模型输出第 3 句时插了
"（比如哪里慢、哪里报错、哪里操作别扭）"。判断为合理——它给的是反馈维度，
不是现象断言——但当时 skill 只写了"整段一轮说完、禁止改写"，没有为这类
灵活性定边界，模型只能靠善意判断，下次就可能从"允许举例"滑到"允许暗示"。

本文件把边界变成可执行规则：
  ① 第 3 句的允许示例=封闭集合（慢 / 报错 / 操作别扭），多一个字都算漂移
  ② 兜底句"不说我也会按你的原话提交"必须保留（用户拒绝补充的退出通道）
  ③ 明确禁令四条必须在（现象断言 / 暗示已知问题 / 替用户补全 / 兜底句不可删）
  ④ 路由插件与 server instructions 的归因口径不得退回"安装绑定决定"
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = (ROOT / "skills" / "vod-feedback-collect" / "SKILL.md").read_text(encoding="utf-8")

SENT1 = "收到，你对产品体验不满意"
SENT2 = "要把这条反馈提交给产品团队吗？"
SENT3_ALLOWED = "方便的话说下具体现象（比如哪里慢、哪里报错、"
SENT3_TAIL = "哪里操作别扭），不说我也会按你的原话提交"
FALLBACK = "不说我也会按你的原话提交"


def test_fixed_three_sentences_present():
    assert SENT1 in SKILL
    assert SENT2 in SKILL
    assert SENT3_ALLOWED.replace("\n", "") in SKILL.replace("\n", "")
    assert SENT3_TAIL in SKILL


def test_fallback_sentence_is_mandatory():
    assert FALLBACK in SKILL, "兜底句是用户拒绝补充时的退出通道，不能删"
    assert "必须保留" in SKILL, "边界规则必须写明兜底句不可弱化/删除"


def test_scope_not_conclusion_rules_are_explicit():
    for rule in ("禁止现象断言", "禁止暗示已知问题", "禁止替用户补全"):
        assert rule in SKILL, f"缺少边界规则：{rule}"
    assert "示例回答\"你想说哪一类\"" in SKILL or "示例回答" in SKILL


def test_no_second_example_set_sneaks_in():
    """允许的示例是封闭集合：出现别的示例清单（如"比如卡顿/闪退"）即漂移。"""
    import re
    for m in re.finditer(r"（比如[^）]*）", SKILL):
        assert m.group(0).startswith("（比如哪里慢、哪里报错、"), (
            f"第 3 句出现了未批准的示例集合：{m.group(0)}")


def test_router_and_instructions_do_not_regress_to_install_binding():
    router = (ROOT / "hermes-plugin" / "vod-feedback-router" / "router.py").read_text(encoding="utf-8")
    server = (ROOT / "vod_mcp" / "server.py").read_text(encoding="utf-8")
    for name, text in (("router.py", router), ("server.py", server)):
        assert "归因由安装绑定决定" not in text and "安装绑定完成" not in text, (
            f"{name} 的归因口径退回旧语义（D-attrib-B 已改为原话解析，绑定仅先验）")
    assert "从用户原话解析" in router