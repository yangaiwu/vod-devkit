"""OpenCode 宿主适配：opencode.json 的 mcp 段无损合并 + 随装生成物。"""
from pathlib import Path

from vod_mcp import msgs
from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import merge_json_mcp, server_env, server_entry, command_list
from vod_mcp.host_adapters import base

HOST = "opencode"
SUPPORTS_REMOTE = True
_SPEC = host_specs.load("opencode")


def skills_dir(args):
    d = _SPEC.get("skillsDir")
    return Path(d) if d else None


def config_path() -> Path:
    """本宿主生效配置落点（单一来源，S178）：install 写哪里，读回就判哪里。

    codeartswork 有新旧两套目录（~/.codearts/mcp 优先），host_verify 若按 host.json
    的默认值判，会把「装到新目录」误报成 no-entry。
    """
    return Path(host_specs.load("opencode")["configPath"])   # 调用期现读（HOME 可能被隔离）


def install(args, packs: str) -> Path:
    """OpenCode：~/.config/opencode/opencode.json 的 mcp 段无损合并。

    schema 实测要求：command=数组、enabled 必填；既有内容（provider 等）
    原样保留（读改写，只动 mcp.vod-devkit 键）。
    """
    spec = host_specs.load("opencode")
    conf = Path(spec["configPath"])
    entry = {
        "type": "local",
        "command": command_list(args, server_entry()),
        "enabled": True,
        "environment": server_env(args, packs),
    }
    action = merge_json_mcp(conf, entry)   # 公共合并件：保用户键 + 首改 .bak
    print(f"已写入 OpenCode 配置（{action}）：{conf}（{msgs.effective('OpenCode')}）")
    # 随装生成物走 integrations/opencode/ 的模板（单一来源——此前模板正文
    # 硬编码在本函数里，改文案要同时改代码与文档两处）
    for g in spec["generated"]:
        dest = Path(g["dest"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(Path(g["template"]).read_text(encoding="utf-8"),
                        encoding="utf-8")
        print(f"已写入 OpenCode 自检命令：/vod-doctor（{dest}）")
    from vod_mcp.host_adapters import host_verify
    host_verify.require_ok(HOST)      # S178：写完读回，形态不对就非零退出
    return conf


def install_remote(args, url, token):
    """mcp.vod-devkit = {type:remote, url, enabled, headers?}（headers 明文，提示权限）。

    token 可选（D-token-machine-1）：给了就写 Authorization（调用方自带身份）；
    没给就不写 headers——请求无 Bearer，由远程 server 用机器级匿名令牌提交。
    """
    conf = Path(_SPEC["configPath"])
    entry = {"type": "remote", "url": url, "enabled": True}
    entry.update({k: v for k, v in base.remote_entry(url, token).items() if k != "url"})
    action = merge_json_mcp(conf, entry)
    suffix = "（token 随配置存放，注意文件权限）" if token else "（未带 token：走服务端匿名令牌）"
    print(f"已写入 OpenCode 远程 MCP 配置（{action}）：{conf}{suffix}")
    return conf
