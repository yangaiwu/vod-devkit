#!/usr/bin/env python3
"""vod_router：Hermes shell hook（pre_llm_call）——确定性意图路由。

统一架构（D-hook-unify-1）：路由不再做成 hermes 插件包（要 plugins.enabled、要
宿主进程内 import），而是一个**与宿主无关的钩子脚本**：stdin 读 JSON 事件载荷，
stdout 输出 {"context": "..."}；由各宿主自己的机制注册（hermes=`config.yaml` 的
hooks.pre_llm_call，子进程隔离、按 (event, command) 首次同意）。线协议见
hermes docs「Shell Hooks → JSON wire protocol」。

行为：
- 命中 TRIGGER_WORDS（确定性关键词，非模型判断）→ 注入 directives（含显式
  「提交反馈」前缀的分支）；
- 未命中 → 什么都不输出（零注入零噪音）。

规则表纪律：新增触发词改 TRIGGER_WORDS（单一事实源），改文案改 DIRECTIVE /
STRONG_DIRECTIVE；两处都有回归锁（tests/test_router.py）。
"""
import json
import re
import sys

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

DIRECTIVE = (
    "[vod-router] 确定性意图路由命中：本消息匹配产品反馈采集意图（规则命中，非模型判断）。"
    "必须按 vod-feedback-collect 技能流程处理：先承接用户，再征得提交同意"
    "（产品未定时必须问一次『这条是哪个产品的反馈』，不许裸提交；"
    "用户说不知道就不提交（缺产品不提交）；禁止进入复现排查模式）。"
    "提交时 content=用户原话逐字，一次抱怨一条，回执按 echo 原样转述。"
)

STRONG_DIRECTIVE = (
    "[vod-router] 显式反馈指令（「提交反馈」前缀，确定性短路）：必须立即按 "
    "vod-feedback-collect 技能流程执行采集，无需再判断意图。"
)


def _text_of(payload: dict) -> str:
    """取这一轮的用户原话：real payload 把 user_message 放在 extra 里；
    user_message 可能是多模态列表（取其中的 text 段）。"""
    extra = payload.get("extra") or {}
    msg = extra.get("user_message", payload.get("user_message"))
    if isinstance(msg, list):
        parts = []
        for part in msg:
            if isinstance(part, dict):
                if part.get("type") in (None, "text") and part.get("text"):
                    parts.append(str(part["text"]))
            elif isinstance(part, str):
                parts.append(part)
        msg = "\n".join(parts)
    return msg if isinstance(msg, str) else ""


def route(text) -> str | None:
    """返回要注入的指令；未命中/非字符串返回 None（钩子绝不对载荷形状抛错）。"""
    if not isinstance(text, str) or not text.strip():
        return None
    if text.lstrip().startswith(_STRONG_PREFIX):
        return STRONG_DIRECTIVE
    return DIRECTIVE if _COMPLAINT_RE.search(text) else None


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return 0          # 载荷不可解析=不注入，绝不打断宿主这一轮
    directive = route(_text_of(payload))
    if directive:
        # 协议：dict 里 "context" 键的文本被追加到本轮用户消息
        sys.stdout.write(json.dumps({"context": directive}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())