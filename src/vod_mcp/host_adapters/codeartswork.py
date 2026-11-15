"""CodeArts Work（CodeArts Space）宿主适配。

形态来源：huaweicloud-devkit targets.ts codeartsWorkMcpSettingsFile + agents/codearts-work.ts：
- 只有用户级配置；平台迁移后新址 `~/.codearts/mcp/mcp_settings.json`，旧址
  `~/.codeartswork/mcp/mcp_settings.json` 作为回退（新址目录存在就用新址）。
- 条目是 `mcp.<name> = {command: [exe, ...], environment: {...}}`——注意环境键名
  是 `environment`（与 opencode 的 `environment` 同名、与 mcpServers 的 `env` 不同）。
- 技能落 `~/.codeartswork/skills`。
"""
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import merge_json_mcp, server_env, server_entry

HOST = "codeartswork"
SUPPORTS_REMOTE = True

_VERB = {"created": "写入", "updated": "更新", "unchanged": "跳过（已一致）"}


def _spec() -> dict:
    return host_specs.load(HOST)


def _config_path() -> Path:
    new_dir = Path.home() / ".codearts" / "mcp"
    if new_dir.is_dir():
        return new_dir / "mcp_settings.json"
    return Path(_spec()["configPath"])


def skills_dir(args):
    d = _spec().get("skillsDir")
    return Path(d) if d else None


def install(args, packs):
    conf = _config_path()
    entry = {"command": [sys.executable, server_entry()],
             "environment": server_env(args, packs)}
    action = merge_json_mcp(conf, entry, section="mcp")
    print(f"已{_VERB[action]} CodeArts Work 配置：{conf}（重启 CodeArts Work 会话生效）")
    return conf


def install_remote(args, url, token):
    conf = _config_path()
    entry = {"url": url,
             "environment": {"Authorization": f"Bearer {token}"}}
    action = merge_json_mcp(conf, entry, section="mcp")
    print(f"已{_VERB[action]} CodeArts Work 远程 MCP：{conf}（token 明文，注意文件权限）")
    return conf