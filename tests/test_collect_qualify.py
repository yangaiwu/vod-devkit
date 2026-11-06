"""追加反馈定性话术回归锁（proposal S49-S51 / design §三 话术分层第 4 条）。

背景（2026-11-06 实锤）：确认环节用户追加表达（如「我看怎么说，你才明白」）
曾被两种形态处理——①把「算不算反馈」丢回给用户（定性职责转嫁）；②agent 当
事实断言替用户下结论。定稿=先定性再问，但定性标注为理解+留纠正口子。

同时锁死两条边界：
- S51 禁空头承诺：无引擎/插件承载的机制（「过程反馈单独记录」）不得成为
  话术选项——客户端无过程反馈通道，承诺即空头支票；
- 双副本一致性：skills/ 与 plugins/vod-devkit/skills/ 两份 SKILL.md 必须
  完全一致（实锤事故：①plugins 副本 description 缺「太慢」的静默漂移；
  ②frontmatter 被部分同步脚本吞掉）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "vod-feedback-collect" / "SKILL.md"
PLUGIN_SKILL = ROOT / "plugins" / "vod-devkit" / "skills" / "vod-feedback-collect" / "SKILL.md"

# 定性话术块的定位锚（块标题）
SECTION_ANCHOR = "追加反馈定性话术"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _qualify_block() -> str:
    """截取定性话术块：从块标题到下一个块标题（职责边界）。"""
    text = _skill_text()
    start = text.find(SECTION_ANCHOR)
    assert start != -1, f"SKILL.md 缺「{SECTION_ANCHOR}」话术块（S49 承载缺失）"
    end = text.find("职责边界", start)
    assert end != -1, "定性话术块后缺「职责边界」块（结构断裂）"
    return text[start:end]


def test_s49_qualify_before_asking():
    """S49：先定性再问——块内必须同时含定性动作与确认范围。"""
    block = _qualify_block()
    assert "先给一句定性再问" in block, "S49 承载缺失：先定性再问纪律未落正文"
    assert "丢给用户" in block and "决策成本" in block, "S49 依据（定性职责归 agent）未落正文"


def test_s50_qualify_marked_as_understanding_with_correction_opening():
    """S50：定性必须标注为理解并留纠正口子，禁止事实断言。"""
    block = _qualify_block()
    assert "听起来更像" in block, "S50 承载缺失：定性未用「听起来更像」理解标注"
    assert "我理解得对吗" in block, "S50 承载缺失：缺显式纠正口子问句"
    assert "不替用户下结论" in block, "S50 承载缺失：禁越权定性条款未落正文"
    # 选项收窄为两个真实可执行项
    assert "只提交最初那句" in block, "S50 承载缺失：两选项之一（只提原句）未落正文"
    assert "不加第三选项" in block, "S50 承载缺失：禁第三选项条款未落正文"


def test_s50_correction_loop_closes():
    """S50 纠正闭环（2026-11-06 用户补口子 2）：用户纠正定性后
    不辩论、按纠正理解走，但 content 仍原话逐字——禁止拿「新定性」
    改写原话（一次抱怨一条+原话红线不因纠正豁免）。"""
    block = _qualify_block()
    assert "不辩论" in block, "纠正后行为缺失：不辩论纪律未落正文"
    assert "原话逐字" in block, "纠正后行为缺失：content 原话约束未落正文"
    assert "不因纠正豁免" in block, "纠正后行为缺失：红线豁免禁令未落正文"
    assert "我按你说的" in block and "不改写" in block, (
        "话术模板尾句（纠正→按原话提交不改写）未落正文")


def test_s50_extreme_option_has_fallback_not_a_sibling_choice():
    """S50 兜底口子（2026-11-06 用户补口子 1）：只提交追加句的
    极端选择有出口（括号兜底），但不作为并列选项抬高常规决策成本。"""
    block = _qualify_block()
    assert "只提交第二句" in block, "兜底出口缺失：极端选择（只提追加句）未落正文"
    assert "不进并列选项" in block, "兜底形态缺失：兜底句未标注不进并列选项"


def test_s51_no_empty_promise_options():
    """S51：无承载机制不得成为话术选项。

    「单独记录」只允许出现在禁令句中（作为反例），不允许出现在
    选项/承诺语境里（「作为过程反馈单独记录」被列为用户可选项=空头支票）。
    """
    block = _qualify_block()
    assert "禁空头承诺" in block, "S51 承载缺失：禁空头承诺条款未落正文"
    assert "空头支票" in block, "S51 承载缺失：空头支票定性未落正文"
    assert "先有承载再进话术" in block, "S51 承载缺失：承载前置纪律未落正文"


def test_skill_copies_in_sync():
    """双副本同步锁：skills/ 与 plugins/ 副本逐字节一致。

    实锤事故：①plugins 副本 description 缺「太慢」（M1 四副本修复漏此份）；
    ②部分同步脚本吞 frontmatter。任何一份单独改动未同步=装机内容分叉。
    """
    assert SKILL.is_file() and PLUGIN_SKILL.is_file(), "双副本路径缺失"
    a, b = SKILL.read_bytes(), PLUGIN_SKILL.read_bytes()
    assert a == b, (
        "skills/ 与 plugins/ 两份 vod-feedback-collect/SKILL.md 不一致"
        "（装机内容分叉，以 skills/ 为源同步 plugins/）")


def test_plugin_copy_has_frontmatter_and_frontloaded_trigger():
    """plugins 副本 frontmatter 完整性 + 触发词前置（吞 frontmatter 事故回归）。"""
    head = PLUGIN_SKILL.read_text(encoding="utf-8").split("\n", 6)
    assert head[0] == "---", "plugins 副本 frontmatter 起始分隔符缺失"
    desc = next((l for l in head if l.startswith("description:")), "")
    assert desc, "plugins 副本缺 description frontmatter"
    assert "太慢" in desc[:57], (
        "plugins 副本 description 前 57 字符缺「太慢」——M1 触发词前置"
        "在这份副本上曾静默漂移缺失")
