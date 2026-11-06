"""vod-feedback-router：Hermes 强制评估钩子（业界 forced-eval 模式，~84% 激活率）。

每轮 pre_llm_call 对用户消息做确定性意图判定（关键词规则，非模型判断）：
命中产品反馈采集意图 → 注入短指令（承诺机制），把「采集 vs 排障」的分流
从模型自由推理变成每轮结构化提醒。未命中返回 None（零注入零噪音）。

设计依据：业界数据简单指令钩子激活率~20%（与无钩子无差异），结构化
评估承诺注入 ~84%（见 vod-devkit docs/hermes-feedback-router/design.md 业界对表）。

规则表维护纪律：新增触发词改 TRIGGER_WORDS（单一事实源），正则自动组装；
指令文案改 DIRECTIVE 常量——两处都有回归锁（tests/test_router.py）。
"""
import re

# ── 确定性触发词表（单一事实源；短短语+口语变体，与采集技能 description 前置触发词同源） ──
TRIGGER_WORDS = (
    "提交反馈", "提单",
    "体验不好", "体验差", "体验很差", "体验糟", "很糟糕", "太糟糕",
    "太慢", "很慢", "回复慢", "响应慢",
    "卡顿", "卡死", "卡",
    "不好用", "很难用",
    "报错", "有bug", "有 bug", "出bug",
    "希望支持", "建议增加", "要是能", "为什么不能",
)
_STRONG_PREFIX = "提交反馈"

_COMPLAINT_RE = re.compile("|".join(re.escape(w) for w in TRIGGER_WORDS))

_DIRECTIVE = (
    "[vod-router] 确定性意图路由命中：本消息匹配产品反馈采集意图（规则命中，非模型判断）。"
    "必须按 vod-feedback-collect 技能流程处理：先承接用户，再征得提交同意"
    "（禁止询问产品归属——归因由安装绑定决定；禁止进入复现排查模式）。"
    "提交时 content=用户原话逐字，一次抱怨一条，回执按 echo 原样转述。"
)

_STRONG_DIRECTIVE = (
    "[vod-router] 显式反馈指令（「提交反馈」前缀，确定性短路）：必须立即按 "
    "vod-feedback-collect 技能流程执行采集，无需再判断意图。"
)


def route(user_message) -> str | None:
    """确定性意图路由。返回注入指令或 None。

    纯函数（便于回归锁）；规则命中才注入，未命中零噪音。
    已知边界（拍板接受的取舍）：「报错/卡」等词在纯排障对话中也会命中——
    采集侧宁可多注入（模型仍需按技能流程先确认），错注入无害（不自动提交）。
    """
    if not user_message or not isinstance(user_message, str):
        return None
    text = user_message.strip()
    if not text:
        return None
    if text.startswith(_STRONG_PREFIX) or _STRONG_PREFIX in text[:20]:
        return _STRONG_DIRECTIVE
    if _COMPLAINT_RE.search(text):
        return _DIRECTIVE
    return None


def register(ctx):
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)


def _on_pre_llm_call(user_message=None, **kwargs):
    return route(user_message)
