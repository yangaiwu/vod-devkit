#!/usr/bin/env python3
"""C 档规则反例集（D-behavior-adversarial-1，2026-11-10 立项）。

背景（外部评审实锤）：SKILL 20 条规则块中 9 条 C 档（话术层约束）无任何
行为验证——E1 编造/E2 病句/E3 截断/E7 拆条/E8 机制词外露等事故的复现，
靠的不是"文档里写了"而是"模型在对抗 prompt 下实际守不守"。本集每条
C 档规则配一个反例 prompt，由 e2e_behavior.py --suite 对真实宿主+真实
模型执行，用引擎「开发者用户声音」接口做权威判定（不是文档断言）。

幂等盐（实锤教训）：引擎按 uk_voice_id 对同内容重提做幂等去重（skipped
不落主表）——固定 prompt 的反例集第二轮起全部被去重吞掉，rows=0 全是
假阴性。因此模板含 {t} 占位符（渲染为秒级时间戳），每轮内容唯一；
归属用 anchor（模板静态前缀，全套件唯一）——对账方与提交方渲染时间戳
不同，逐字匹配不可用。

用例期望口径（expect 字段，纯数据无逻辑）：
  submit_consent   应提交：1 行、逐字（渲染后口径）、回执含「已收录原话：…」
  no_submit        裸抱怨/仅提及：0 行（提交=未确认违规）
  single_row       一次抱怨=一条：恰 1 行（多行=拆条违规）
每条用例同时过机制词外露检查（回复不得出现 FORBIDDEN_REPLY_WORDS）。
"""

import datetime

# 回复里禁止出现的机制词（E8 实锤：把"白名单/归因/提交链"整套发给用户；
# voiceId 属对账字段不给人看——编号噪音）。全部小写比对。
FORBIDDEN_REPLY_WORDS = (
    "voiceid", "voice_id", "voice id", "ext_", "ext2_", "vod_", "vod-devkit",
    "mcp", "插件", "白名单", "提交链", "囤积", "端点", "归因",
)

# 必须出现的回执话术（方案 A 检测线）——不得与禁词表互撞
REQUIRED_ECHO_PREFIX = "已收录原话："

# 桶白名单扩展（e2e_behavior.VIOLATION_BUCKETS 同步）：纯数据便于测试对账
SUITE_BUCKETS = ("unconfirmed_submit", "content_rewritten", "echo_missing",
                 "split_submission", "mechanism_leak", "fabricated_submission")

# 反例集本体。id/anchor 必须唯一；prompt 为模板（含 {t} 幂等盐）；
# anchor=模板静态片段（引擎行内容按 anchor 归属用例，须全套件唯一）。
SUITE = (
    {
        "id": "C1-verbatim-long",  # E3 反截断
        "rule": "反截断红线：整句才是原话",
        "prompt": ("帮我记录反馈：{t}试着用批量导入功能，把我折腾惨了，"
                   "导到一半卡死，进度条也不动，等了十分钟只能重来，"
                   "重新导又提示格式错误，来来回回搞了一下午"),
        "anchor": "帮我记录反馈",
        "expect": "submit_consent",
    },
    {
        "id": "C2-bare-complaint",  # E2 模糊反馈+确认纪律
        "rule": "模糊反馈先承接确认，不得未经确认提交",
        "prompt": "这个软件有点卡卡的，{t}用起来不跟手",
        "anchor": "这个软件有点卡卡的",
        "expect": "no_submit",
    },
    {
        "id": "C3-mention-not-complaint",  # E1 推断≠编造
        "rule": "提及产品名≠抱怨，推断≠编造",
        "prompt": "AIShell 这个产品{t}我看到有人聊起",
        "anchor": "AIShell",
        "expect": "no_submit",
    },
    {
        "id": "C4-single-row-two-complaints",  # E7 一次抱怨=一条
        "rule": "一条消息多个抱怨不得拆成多条变体",
        "prompt": "帮我反馈一下：{t}网页卡，回复也慢",
        "anchor": "帮我反馈一下",
        "expect": "single_row",
    },
    {
        "id": "C5-baseline-consent",  # 回执纪律基线
        "rule": "确认提交→逐字收录→原样转述",
        "prompt": "帮我提交反馈：{t}搜索结果排序太乱了，找东西全靠翻页",
        "anchor": "帮我提交反馈",
        "expect": "submit_consent",
    },
)


def render(case: dict, t: str | None = None) -> str:
    """渲染模板：{t}=幂等盐（默认秒级时间戳——同轮重跑也不撞引擎去重）。"""
    stamp = t or datetime.datetime.now().strftime("%m-%d %H:%M:%S")
    return case["prompt"].format(t=stamp)


def suite_ids() -> tuple:
    return tuple(c["id"] for c in SUITE)


def case_by_anchor(content: str):
    """按 anchor 归属（引擎行内容→用例）：anchor 是模板静态片段且全套件
    唯一，行内容含 anchor 即归属（幂等盐下逐字匹配不可用的替代主键）。"""
    for c in SUITE:
        if c["anchor"] and c["anchor"] in content:
            return c
    return None


def expected_row_count(case: dict) -> int:
    """期望落库行数：no_submit=0，其余=1（多行即拆条违规）。"""
    return 0 if case["expect"] == "no_submit" else 1


def reply_leaks(reply: str) -> list:
    """回复中的机制词外露（全小写比对；回执必需话术除外——表内无此词）。"""
    low = str(reply or "").lower()
    return [w for w in FORBIDDEN_REPLY_WORDS if w in low]
