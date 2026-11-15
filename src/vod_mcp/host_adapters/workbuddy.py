"""WorkBuddy 宿主适配（mcpServers.<name> 形态）。

形态来源：huaweicloud-devkit targets.ts / agents/workbuddy.ts —— 用户级
`~/.workbuddy/mcp.json` 的 mcpServers 里一条，技能落 `~/.workbuddy/skills`。

纪律：
- 只写 mcpServers.vod-devkit 一个键，宿主其它 server/用户键原样保留，首改落 .bak。
- 配置文件不是合法 JSON → 报错退出、字节不动（宁可不装不可装错）。
- 本机未装该宿主：配置形态按对表实现，doctor 会标「未真机验证」。
"""
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import server_env, server_entry
from vod_mcp.host_adapters.generic import merge_mcp_servers

HOST = "workbuddy"
SUPPORTS_REMOTE = True

_VERB = {"created": "写入", "updated": "更新", "unchanged": "跳过（已一致）"}


def _spec() -> dict:
    return host_specs.load(HOST)


def skills_dir(args):
    d = _spec().get("skillsDir")
    return Path(d) if d else None


def install(args, packs):
    conf = Path(_spec()["configPath"])
    entry = {"command": sys.executable, "args": [server_entry()],
             "env": server_env(args, packs)}
    action = merge_mcp_servers(conf, entry)
    print(f"已{_VERB[action]} WorkBuddy 配置：{conf}（重启 WorkBuddy 会话生效）")
    return conf


def install_remote(args, url, token):
    conf = Path(_spec()["configPath"])
    entry = {"url": url, "headers": {"Authorization": f"Bearer {token}"}}
    action = merge_mcp_servers(conf, entry)
    print(f"已{_VERB[action]} WorkBuddy 远程 MCP：{conf}（token 明文，注意文件权限）")
    return conf