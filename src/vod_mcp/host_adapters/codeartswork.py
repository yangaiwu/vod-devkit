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

from vod_mcp import msgs
from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import merge_json_mcp, server_env, server_entry
from vod_mcp.host_adapters import base

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


def config_path() -> Path:
    """本宿主生效配置落点（单一来源，S178）：install 写哪里，读回就判哪里。

    codeartswork 有新旧两套目录（~/.codearts/mcp 优先），host_verify 若按 host.json
    的默认值判，会把「装到新目录」误报成 no-entry。
    """
    return _config_path()


def install(args, packs):
    conf = _config_path()
    entry = {"command": [sys.executable, server_entry()],
             "environment": server_env(args, packs)}
    action = merge_json_mcp(conf, entry, section="mcp")
    print(f"已{_VERB[action]} CodeArts Work 配置：{conf}（{msgs.effective('CodeArts Work')}）")
    from vod_mcp.host_adapters import host_verify
    host_verify.require_ok(HOST)      # S178：写完读回，形态不对就非零退出
    return conf


def install_remote(args, url, token):
    conf = _config_path()
    entry = base.remote_entry(url, token, header_key="environment")
    action = merge_json_mcp(conf, entry, section="mcp")
    print(f"已{_VERB[action]} CodeArts Work 远程 MCP：{conf}（token 明文，注意文件权限）")
    return conf
