"""CodeArts Agent 宿主适配（实测 2026-11-11）。

CodeArts Agent 是 OpenCode 的分支（安装壳导出 SCENARIO=codeartsdoer、
OPENCODE_CONFIG=~/.codeartsdoer/codearts_cli.json、KERNEL_CONFIG_DIR=~/.codeartsdoer），
所以配置形态与 opencode 同 schema：`mcp.<name> = {type:"local", command:[...], enabled}`。

现场实测（本机 codearts 已装，286MB 二进制）：
- 往 ~/.codeartsdoer/codearts_cli.json 写 mcp.vod-probe → `codearts mcp list`
  输出 "●  ○ vod-probe disabled / python3 -c pass" → 通道有效，已还原。
- `codearts mcp add` 没有任何参数（交互式向导）→ 程序化只能写 JSON，再用
  `codearts mcp list` 冒烟。
- mcp_settings.json 只对**项目级** `<project>/.codeartsdoer/mcp/mcp_settings.json`
  生效（二进制：`.${SCENARIO}/mcp/mcp_settings.json`）；用户级读
  `~/.config/opencode/mcp/mcp_settings.json` —— 写 ~/.codeartsdoer/mcp/ 无效。
- 技能目录 ~/.codeartsdoer/skills（二进制字符串 "codeartsdoer/skills/"）。
"""
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import merge_json_mcp, server_env, server_entry

HOST = "codeartsdoer"
SUPPORTS_REMOTE = True


def _spec() -> dict:
    """每次现读：host.json 的 ~ 相对 HOME 解析必须在调用期做（测试可重定向 HOME）。"""
    return host_specs.load("codeartsdoer")


def skills_dir(args):
    d = _spec().get("skillsDir")
    return Path(d) if d else None


def install(args, packs):
    """写 codearts_cli.json 的 mcp.vod-devkit（无损合并，保留 provider/model 等键）。"""
    conf = Path(_spec()["configPath"])
    entry = {
        "type": "local",
        "command": [sys.executable, server_entry()],
        "enabled": True,
        "environment": server_env(args, packs),
    }
    action = merge_json_mcp(conf, entry)
    print(f"已写入 CodeArts Agent 配置（{action}）：{conf}（重启 codearts 会话生效）")
    return conf


def install_remote(args, url, token):
    conf = Path(_spec()["configPath"])
    entry = {"type": "remote", "url": url, "enabled": True,
             "headers": {"Authorization": f"Bearer {token}"}}
    action = merge_json_mcp(conf, entry)
    print(f"已写入 CodeArts Agent 远程 MCP（{action}）：{conf}（token 明文，注意文件权限）")
    return conf