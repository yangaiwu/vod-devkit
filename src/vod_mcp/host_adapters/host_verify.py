"""宿主 MCP 注册「真的落盘了」的统一判据（D-host-verify-1，2026-11-17 评审）。

为什么必须一处：install 收尾与 doctor 自检曾各用一套判据——install 只看 CLI 的 rc，
doctor 不查 configPath，于是出现「install rc=0 + doctor OK，工具却连不上」
（实测：隔离 HOME + 无 hermes CLI，只写备片 + hooks，config.yaml 无 mcp_servers）。

问题码分档（文案不复用，用户才知道下一步做什么）：
  no-entry  有 CLI 且写入动作发生过，读回没有条目 → **重跑 install**（install 非零退出）
  missing   降级（无 CLI / 超时 / rc!=0）本就没写 → **手工并入备片**（install rc=0，doctor 红）
  disabled  条目在但 enabled: false → 宿主不会加载（改回 true 或重跑 install）

范围：0.5.29 只接 **hermes**（本轮实测有 bug 的那条链：`hermes mcp add` 交互确认被跳过时
rc=0 却不落配置）。codex 的注册态已由 doctor 既有的「.mcp.json 形态三分类」覆盖
（payload / placeholder / cli，走 `plugin_mcp_form()`），此处**不得再报一次**：同一宿主
两套判据必然长成「一侧 OK 一侧 DRIFT」。其余宿主（opencode / atomcode / workbuddy /
codeartswork / codeartsdoer / generic）与 `audit` 侧同样待下一轮迁移到本模块。
"""
SUPPORTED = ("hermes",)


def problems(host: str, *, degraded: bool = False) -> list:
    """返回 [] 表示注册可用；否则 [{"code", "target", "message"}]。

    `degraded=True` 由调用方在「无 CLI / 命令超时 / CLI rc!=0」时传——
    此时没有写入动作发生过，码是 missing（引导手工并入），不是 no-entry（引导重装）。
    """
    if host == "hermes":
        return _hermes_problems(degraded=degraded)
    return []


def _hermes_problems(*, degraded: bool) -> list:
    from vod_mcp.host_adapters import hermes

    st = hermes.mcp_entry_state()
    cfg = hermes._spec().get("profileConfig")
    if not st["present"]:
        code = "missing" if degraded else "no-entry"
        tail = ("手工把 <vod-devkit 备片> 并入该配置的 mcp_servers（无 CLI 时安装器只写备片）"
                if degraded else "重跑 install（逐问回答 y）")
        return [{"code": code, "target": "hermes",
                 "message": f"hermes config.yaml 缺 mcp_servers.vod-devkit（{cfg}）——{tail}"}]
    if st["enabled_false"]:
        return [{"code": "disabled", "target": "hermes",
                 "message": f"hermes 的 mcp_servers.vod-devkit 被 enabled: false 关掉（{cfg}）"
                            "——改回 true 或重跑 install"}]
    return []