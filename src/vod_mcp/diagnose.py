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
    # ARCH-ERR-01（2026-11-19 走查 P0）：policy 不可载入时的 fail-closed 码。
    # 与 -32010 分开是因为处置动作不同（那条是"问产品"，这条是"修规则后重启"）。
    # 新开 -32017 而非复用 -32013：后者是已废除的归因拦截码（四处文档在记），
    # 复用会让同一码位有两种互不相关的说法。
    "-32017": ("配置", "护栏规则不可载入（policy.json 缺失/损坏/规则字段非法）——已拒绝执行",
               "修 policy.json 或重跑 install 恢复随包规则；规则详情看回执里的 rule id；改完重启宿主"),
    "-32014": ("传输", "非 https 且非回环的引擎地址被拒",
               "把 VOD_JAVA_API_BASE 改成 https:// 地址或回环（127.0.0.1 / localhost）"),
    # ARCH-CALL-05 同源面（2026-11-19，fix-list 问题 3）：护栏四类 deny 曾共用 -32010
    # （"缺产品"），用户照着提示补产品永远修不好。按「处置动作不同 ⇒ 码不同」拆开。
    # ⚠️ -32021/-32022 已被闭环方案预留给上游 429/5xx（architecture-remediation.md:294、
    # decisions.md:2809 写明不可复用），故新码从 -32023 起。码位永不复用。
    "-32023": ("配置", "请求内容命中「凭据/敏感信息读取意图」被护栏拦截（不是缺产品、不是参数错）",
               "删掉凭据/AK-SK/密码等内容后重新提交；护栏只管意图，不会代你脱敏"),
    "-32024": ("配置", "越权或超出允许范围被护栏拒绝（如单批条数超上限、写操作越界）",
               "收敛到允许范围（如减少单批条数）后重提；这通常不是参数拼写问题"),
    "-32015": ("配置", "能力包被安全门禁拒绝（熔断/策略），不是参数错",
               "看 doctor 的分层报告确认熔断原因；恢复要显式 --ack-suspension，别改拼写重试"),
    "-32016": ("引擎", "囤积端点未上线（POST /external/voices 返回 404）：本条未提交，"
               "S238 起不再回落老链 /external/voice/submit",
               "等引擎部署囤积端点后重试；不要改用老链，也不要当成参数错反复重试"),
    "-32001": ("网络", "上游不可达（引擎地址不可达 / 网络中断）",
               "查网络出口与 VOD_JAVA_API_BASE；离线可继续工作，恢复后重试"),
    # ── JSON-RPC 保留段（ARCH-ERR-06，2026-11-19 fix-list 附 3）────────────────
    # 此前这五条全部 known=False，而它们**全都会真实抛出**。最糟的是 -32603：
    # 它是主循环兜底码（server.py:193 / transport_remote.py:589,619），用户最可能
    # 拿它来问「什么意思」，偏偏答不出。归层用「协议」以外的既有层名，避免新增层级。
    "-32600": ("配置", "请求体结构不合法（不是合法 JSON-RPC 2.0 请求：缺 jsonrpc/method 等）",
               "这通常是客户端拼包问题；用官方 SDK 或检查请求体字段，不是插件配置错"),
    "-32601": ("配置", "方法/工具名不存在（未知 method 或未知工具名）",
               "调 vod_list_skills 或 tools/list 核对工具名；工具可能在当前包预设下被裁掉"),
    "-32602": ("配置", "参数非法（必填缺失、类型不对、单条超长、批量为空）",
               "按回执文本逐条修参数；不是网络或引擎问题，重试同样会失败"),
    "-32603": ("内部", "内部错误（插件自身异常，已记录日志）——主循环兜底码，不是引擎或网络问题",
               "查 /tmp 下的 vod-devkit JSONL 日志定位 traceback；带 req_id 便于对账；持续出现请报缺陷"),
    "-32700": ("配置", "JSON 解析失败（请求体不是合法 JSON 或为空/超大）",
               "检查请求体编码与大小；客户端拼包问题，不是插件配置错"),
    # S167（2026-11-17）：引擎 `POST /external/voices` 的 429——voiceId 取号改序列表原子分配后，
    # 极端异常（序列行写不进去/并发删行）会抛「提交排队繁忙，请稍后再试」而不是造假号（引擎
    # 1d4fba8d）。插件 `_http` 对非 401 一律透传 `上游返回 <code>: <detail>`，这条让宿主/用户
    # 知道是「重试」而不是「插件坏了/配置错了」。key 用完整前缀，避免 "429" 误命中端口/哈希。
    "上游返回 429": ("上游", "引擎侧限流或取号排队（voiceId 序列分配重试耗尽 / 提交限频）",
                  "稍后重试一次；持续出现报引擎运维，与本机配置无关"),
    # ARCH-ERR-03（2026-11-19 走查 P1）：上游状态码**不再**进 JSON-RPC code 域，
    # 统一映射到 -32018/-32019/-32020（见 net._http_error_code）。三条分开是因为
    # 处置动作不同：429 是"等一会重试"，5xx 是"引擎故障找运维"，其余 4xx 是"请求被拒查参数"。
    "-32018": ("上游", "引擎限流/取号排队（HTTP 429）——本条未提交",
               "稍后重试一次；持续出现报引擎运维，与本机配置无关"),
    "-32019": ("上游", "引擎服务端故障（HTTP 5xx）——本条未提交",
               "等引擎恢复后重试；持续出现报引擎运维（本机配置正确也救不了）"),
    "-32020": ("上游", "请求被引擎拒绝（除 401/404 外的 4xx）——本条未提交",
               "看回执里的引擎原文排查参数/权限；不要盲目重试同一请求"),
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