"""用户可见的「生效口径」单一拼写点（D-boundary-1，S229）。

为什么集中：9 个宿主适配器 + doctor/update/packs/auth 各自拼「重启…生效」，口径改一次
要改十来处，漂移只在真机文案上暴露（拷贝漏项、宿主名不一致都踩过）。插件对宿主的
生命周期只陈述、不执行——这里只提供措辞，任何调用点不得再自拼。

口径（D-boundary-1）：
- 默认口径 = 「重启宿主会话生效」（插件不知道宿主怎么托管，也不该知道）；
- 宿主名可给（Codex / OpenCode / dsh…），句子结构仍由本模块决定；
- 只影响"什么时候生效"的提示，不产生任何重启动作——插件不碰宿主进程。
"""


def effective(host: str | None = None) -> str:
    """`重启宿主会话生效` / `重启 <host> 会话生效`。"""
    return "重启宿主会话生效" if host is None else f"重启 {host} 会话生效"


def effective_unit(obj: str, tight: bool = False) -> str:
    """宿主以"实例/单元"为生效单位时（dsh、Codex Desktop 市场、OfficeAce 数据库）。

    tight=True 用于对象本身带从句的措辞（如 "OpenClaw 会话/网关生效" 不留空格）。
    """
    return f"重启 {obj}{'' if tight else ' '}生效"


def after(what: str, host: str | None = None) -> str:
    """`重启宿主会话后<what>`（如"使用新 key"）。"""
    base = "宿主会话" if host is None else f"{host} 会话"
    return f"重启{base}后{what}"


def restart_only(obj: str) -> str:
    """只需要"重启<obj>"这个动作短语（如 update 提示里的 agent 会话）。"""
    return f"重启 {obj}"