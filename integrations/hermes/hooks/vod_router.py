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
- 命中词出现在元讨论里（工程对象语汇命中且无用户视角锚点）→ 零注入（S185，
  D-router-scope-1）；
- 未命中 → 什么都不输出（零注入零噪音）。

规则表纪律：新增触发词改 TRIGGER_WORDS（单一事实源），改文案改 DIRECTIVE /
STRONG_DIRECTIVE，改元讨论排除改 META_WORDS / ANCHOR_WORDS；三处都有回归锁
（tests/test_router.py 的 S185/S186 与 R7）。
"""
import json
import re
import sys

TRIGGER_WORDS = (
    "提交反馈", "提单",
    "体验不好", "体验差", "体验很差", "体验糟", "很糟糕", "太糟糕",
    "体验太差", "太差", "很差",
    "太慢", "很慢", "回复慢", "响应慢",
    "卡顿", "卡死", "卡",
    "白屏", "没反应",
    "不好用", "很难用", "太麻烦", "很麻烦", "麻烦死了", "不方便",
    "报错", "有bug", "有 bug", "出bug",
    # S184 现象词同表（S193）：教模型的分型词与路由判据必须是同一份，别造两份真源
    "失败", "打不开", "超时", "崩",
    "希望支持", "建议增加", "要是能", "为什么不能",
)

# 裸「卡」必须带边界（S193）：卡片/卡号/卡券/卡通/卡位/卡口/卡车/车牌 不是抱怨。
# 词表仍只写「卡」一个字（单一事实源），边界在装配正则时加——这样新增触发词不必
# 记着两条规则。
_KA_GUARD = r"卡(?!片|号|券|通|位|口|车|牌|包|针)"

# S185 元讨论排除（D-router-scope-1）：命中词出现在「谈工程对象」的句子里时，
# 用户谈的是产品反馈这件事（评审/方案/代码/文档），不是他自己的遭遇。实测 7 条
# 元讨论 6 条被误判成采集意图，注入指令会把设计评审拐去提单。
# 判据 = 命中 META_WORDS 且不含任何「用户视角对象/体验面」锚点 → 零注入。
# 为什么不用模型判断：本 hook 是确定性路由（线协议只回 context，不跑 LLM），
# 且误注入比漏注入贵——漏了模型仍可能自识别反馈，误注入会打断当前任务。
META_WORDS = (
    # 纯工程产物/工位语汇：用户不会用这些词说自己的体验
    "代码", "用例", "测试", "门禁", "文档", "ADR", "断言", "夹具",
    "PR", "MR", "评审", "方案", "仓库", "分支", "发版", "部署",
    "脚本", "函数", "模块", "依赖", "tag", "commit", "pytest", "mypy",
    "profile", "packs", "载荷", "适配器", "巡检", "账本", "契约", "需求",
    # 工程动作词才是「元讨论」的真信号（S193）：接口/配置/字段/日志/版本 是共用词，不在此列
    "改成", "抽成", "重构", "实现", "写死", "解耦", "排查", "调一下", "补一",
    # 工程第二层（S195）：CI/构建/编译/流水线/发布/回滚/单测/环境/栈 是工程语境，
    # 用户说自己的体验不会用这些词（「构建失败」是开发者在说自己的流水线）
    "CI", "构建", "编译", "流水线", "发布", "回滚", "单测", "环境", "栈",
)
ANCHOR_WORDS = (
    "产品", "平台", "网站", "网页", "页面", "界面", "客户端", "插件", "工具", "系统",
    "功能", "按钮", "菜单", "搜索框", "输入框", "登录", "上传", "下载", "导出",
    "加载", "速度", "打开", "点击", "点了", "体验",
)
_STRONG_PREFIX = "提交反馈"

def _trigger_pattern(words=TRIGGER_WORDS) -> str:
    """装配触发词正则（单一事实源）：除裸「卡」外逐词 re.escape。"""
    return "|".join(_KA_GUARD if w == "卡" else re.escape(w) for w in words)


_COMPLAINT_RE = re.compile(_trigger_pattern())
_META_RE = re.compile("|".join(re.escape(w) for w in META_WORDS))
_ANCHOR_RE = re.compile("|".join(re.escape(w) for w in ANCHOR_WORDS))

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


def _is_meta_discussion(text: str) -> bool:
    """元讨论判定（S185）：谈工程对象、又不带任何用户视角锚点 = 在讨论「反馈这件事」。

    两侧都是确定性词表：META_WORDS 是工作产物语汇（代码/用例/门禁/文档/评审…），
    ANCHOR_WORDS 是用户能直接感知的对象与动作（页面/按钮/登录/导出/加载…）。
    只看「有没有命中词」会把评审、方案讨论判成采集意图——那是本 hook 修前的现状。
    """
    return bool(_META_RE.search(text)) and not _ANCHOR_RE.search(text)


def route(text) -> str | None:
    """返回要注入的指令；未命中/非字符串返回 None（钩子绝不对载荷形状抛错）。"""
    if not isinstance(text, str) or not text.strip():
        return None
    if text.lstrip().startswith(_STRONG_PREFIX):
        return STRONG_DIRECTIVE
    if not _COMPLAINT_RE.search(text) or _is_meta_discussion(text):
        return None
    return DIRECTIVE


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