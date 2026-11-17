"""AtomCode 宿主适配（mcpServers.<name> 形态，配置根可由 ATOMCODE_HOME 覆盖）。

形态来源：huaweicloud-devkit targets.ts atomcodeHome/atomcodeMcpConfigFile ——
`${ATOMCODE_HOME:-~/.atomcode}/mcp.json` 的 mcpServers，技能落 <home>/skills。

刻意不装宿主 hooks.json 的 pre_tool_use 遥测 hook（上游那样做是为了自己的埋点）；
本插件不引入遥测。
"""
import os
import sys
from pathlib import Path

from vod_mcp import msgs
from vod_mcp.host_adapters.base import server_env, server_entry
from vod_mcp.host_adapters.generic import merge_mcp_servers

HOST = "atomcode"
SUPPORTS_REMOTE = True

_VERB = {"created": "写入", "updated": "更新", "unchanged": "跳过（已一致）"}


def _home() -> Path:
    """调用期读 env（测试/多宿主环境可重定向，禁止 import 期求值）。"""
    raw = (os.environ.get("ATOMCODE_HOME") or "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".atomcode"


def _spec() -> dict:
    return {
        "configPath": _home() / "mcp.json",
        "skillsDir": _home() / "skills",
    }


def skills_dir(args):
    return _spec()["skillsDir"]


def config_path() -> Path:
    """本宿主生效配置落点（单一来源，S178）：install 写哪里，读回就判哪里。

    codeartswork 有新旧两套目录（~/.codearts/mcp 优先），host_verify 若按 host.json
    的默认值判，会把「装到新目录」误报成 no-entry。
    """
    return Path(_spec()["configPath"])


def install(args, packs):
    spec = _spec()
    entry = {"command": sys.executable, "args": [server_entry()],
             "env": server_env(args, packs)}
    action = merge_mcp_servers(spec["configPath"], entry)
    print(f"已{_VERB[action]} AtomCode 配置：{spec['configPath']}（{msgs.effective('AtomCode')}）")
    return spec["configPath"]


def install_remote(args, url, token):
    conf = _spec()["configPath"]
    entry = {"url": url, "headers": {"Authorization": f"Bearer {token}"}}
    action = merge_mcp_servers(conf, entry)
    print(f"已{_VERB[action]} AtomCode 远程 MCP：{conf}（token 明文，注意文件权限）")
    from vod_mcp.host_adapters import host_verify
    host_verify.require_ok(HOST)      # S178：写完读回，形态不对就非零退出
    return conf
