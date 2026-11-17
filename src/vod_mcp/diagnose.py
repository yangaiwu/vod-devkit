"""诊断分层与错误解释（doctor 报告 + `explain` 子命令共用一张表）。

动机（对表 huaweicloud-devkit 的 doctor-report / explain-error）：我们原来的
doctor 是一条条 FAIL 平铺打印，"哪里坏了"和"下一步做什么"全靠读文案猜；
运维在现场只会记住一句话——"doctor 报错了"。这里把**分类**和**动作**外置成数据：

- 每条检查/错误按关键词归到一个层（环境/载荷/配置/技能/网络/插件），
  输出时按层分组，一眼看出是"机器环境问题"还是"我们自己的安装问题"；
- 同一张表提供 explain()：给错误码或错误片段，返回 层 / 原因 / 动作。

纪律：
- 表只描述"已知失败形态"，不猜未知错误（未知就如实报"未收录"并给出排查入口）。
- 归层只按关键词匹配（确定性），不做语义推断——误归层会把运维带偏。
"""
import fnmatch
import re

LAYERS = ["环境", "载荷", "配置", "技能", "网络", "插件"]

# (关键词/正则, 层, 原因, 动作)
RULES = [
    (r"无 install-manifest|未 install",
     "环境", "还没装（或 manifest 被删）", "运行 install --target <宿主>"),
    (r"commitSHA 不一致|commitSha",
     "载荷", "安装记录与当前包不是同一份构建（升版后未重装）", "重跑 install"),
    (r"载荷目录缺失|载荷被改动|载荷残留",
     "载荷", "MCP 入口指向的副本不在/被改", "重跑 install 重建副本"),
    (r"MCP 配置文件缺失|mcpConfig",
     "配置", "宿主配置文件被删或挪了位置", "重跑 install --target <宿主>"),
    (r"未列出 vod-devkit|mcp list",
     "配置", "宿主没读到我们的 MCP 条目", "检查宿主配置文件里的 mcp 段后重装"),
    (r"skills 目录缺失|技能文件缺失|技能文件漂移|技能原生副本缺失|技能拷贝件",
     "技能", "技能副本缺失或与安装指纹不符", "重跑 install 恢复"),
    (r"预采集 hook 未注册|vod_router|hook 脚本缺失|读 Key 拦截",
     "配置", "config.yaml 的 hooks 段没登记我们的脚本", "重跑 install --target hermes"),
    (r"解释器|hook.*命令|命令指向旧脚本",
     "配置", "hook 行在但命令/解释器与当前安装不一致（旧行不会被覆盖）",
     "重跑 install --target <宿主> 让它重写 hook 行"),
    (r"旧插件形态仍在|vod-feedback-router",
     "插件", "老插件与 shell hook 同时生效（双份注入）", "重跑 install --target hermes 清理"),
    (r"AGENTS\.md 仍含旧一代注入|vod-submit-one-liner",
     "插件", "旧注入教模型跳过征询（红线失效）", "重跑 install --target codex 自动清理"),
    (r"远程面|远程 MCP|探活|不可达|401",
     "网络", "远程端点不可达或工具面不符", "检查网络/端点版本；设 VOD_MCP_TOKEN 再验"),
    (r"key 无效|401 拒绝|指纹",
     "网络", "引擎拒绝了 key", "核对/续期 key，或移除 key 走匿名档"),
    (r"引擎不可达|ProbeError|timed out|Connection",
     "网络", "引擎/网络不可达（不是 key 问题）", "查网络出口与引擎健康；离线可继续工作"),
    (r"-32010|产品", "配置", "缺产品归属，拒绝提交", "先问用户是哪个产品，再带 product 提交"),
    (r"python|node|版本", "环境", "运行时版本不满足", "按 README 的版本要求升级"),
]

_EXPLAIN_EXTRA = {
    "-32010": ("配置",
               "缺少产品归属（用户没说、也追问不到），服务端拒绝写引擎",
               "先用 vod_search_products 给候选问用户；用户说不清楚就不提交"),
    # S154（2026-11-16）：这三条长期缺表 / 语义错。真值来自 raise 点：
    # collect.py:666-679（草稿/令牌不符）、net.py:181/310（令牌不可用）、net.py:159（传输）、
    # packs/core.py:84（PackRefused 安全门禁）。
    "-32011": ("配置", "草稿/审批令牌不符（draft 过期、approvalToken 不匹配、或不属于当前客户端）",
               "重新 vod_draft_voices 取新草稿与令牌；用户确认后把 draftId/approvalToken 原样透传"),
    "-32012": ("认证", "无凭据 / 令牌不可用（缺 key 且匿名令牌领取失败、设备不匹配或已吊销）",
               "vod_auth_status 看档位；首次提交会自动领匿名令牌；仍 401 用正式 key（auth init）"),
    "-32014": ("传输", "非 https 且非回环的引擎地址被拒",
               "把 VOD_JAVA_API_BASE 改成 https:// 地址或回环（127.0.0.1 / localhost）"),
    "-32015": ("配置", "能力包被安全门禁拒绝（熔断/策略），不是参数错",
               "看 doctor 的分层报告确认熔断原因；恢复要显式 --ack-suspension，别改拼写重试"),
    "-32001": ("网络", "上游不可达（引擎地址不可达 / 网络中断）",
               "查网络出口与 VOD_JAVA_API_BASE；离线可继续工作，恢复后重试"),
    # S167（2026-11-17）：引擎 `POST /external/voices` 的 429——voiceId 取号改序列表原子分配后，
    # 极端异常（序列行写不进去/并发删行）会抛「提交排队繁忙，请稍后再试」而不是造假号（引擎
    # 1d4fba8d）。插件 `_http` 对非 401 一律透传 `上游返回 <code>: <detail>`，这条让宿主/用户
    # 知道是「重试」而不是「插件坏了/配置错了」。key 用完整前缀，避免 "429" 误命中端口/哈希。
    "上游返回 429": ("上游", "引擎侧限流或取号排队（voiceId 序列分配重试耗尽 / 提交限频）",
                  "稍后重试一次；持续出现报引擎运维，与本机配置无关"),
}


def classify(message: str) -> tuple:
    """把一条失败/警告文案归到 (层, 原因, 动作)。未收录 → ("未分类", "", "")。"""
    for pat, layer, cause, action in RULES:
        if re.search(pat, message):
            return layer, cause, action
    return "未分类", "", ""


def explain(text: str) -> dict:
    """给错误码或错误片段，返回 {layer, cause, action, known}。"""
    for code, (layer, cause, action) in _EXPLAIN_EXTRA.items():
        if code in text:
            return {"layer": layer, "cause": cause, "action": action, "known": True}
    layer, cause, action = classify(text)
    return {"layer": layer, "cause": cause, "action": action,
            "known": layer != "未分类"}


def group(problems: list) -> dict:
    """按层分组（保持 LAYERS 顺序，未分类排最后）。"""
    buckets = {l: [] for l in LAYERS}
    buckets["未分类"] = []
    for msg in problems:
        layer, cause, action = classify(msg)
        buckets[layer].append((msg, cause, action))
    return {k: v for k, v in buckets.items() if v}


def render_problems(problems: list) -> str:
    """把失败清单渲染成分层报告（供 doctor 输出）。"""
    if not problems:
        return ""
    out = []
    for layer, items in group(problems).items():
        out.append(f"[{layer}]")
        for msg, cause, action in items:
            out.append(f"FAIL: {msg}")
            if cause:
                out.append(f"       原因：{cause}")
            if action:
                out.append(f"       动作：{action}")
    return "\n".join(out)


def matches(message: str, pattern: str) -> bool:
    """给运维手输片段做粗匹配（大小写不敏感，支持 * 通配）。"""
    return fnmatch.fnmatch(message.lower(), pattern.lower())