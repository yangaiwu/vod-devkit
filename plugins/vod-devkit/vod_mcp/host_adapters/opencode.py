"""OpenCode 宿主适配：opencode.json 的 mcp 段无损合并 + 随装生成物。"""
import json
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import server_env, server_entry

HOST = "opencode"
SUPPORTS_REMOTE = True
_SPEC = host_specs.load("opencode")


def skills_dir(args):
    d = _SPEC.get("skillsDir")
    return Path(d) if d else None


def install(args, packs: str) -> Path:
    """OpenCode：~/.config/opencode/opencode.json 的 mcp 段无损合并。

    schema 实测要求：command=数组、enabled 必填；既有内容（provider 等）
    原样保留（读改写，只动 mcp.vod-devkit 键）。
    """
    spec = host_specs.load("opencode")
    conf = Path(spec["configPath"])
    conf.parent.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if conf.exists():
        try:
            cfg = json.loads(conf.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.setdefault("mcp", {})["vod-devkit"] = {
        "type": "local",
        "command": [sys.executable, server_entry()],
        "enabled": True,
        "environment": server_env(args, packs),
    }
    conf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 OpenCode 配置：{conf}（重启 OpenCode 会话生效）")
    # 随装生成物走 integrations/opencode/ 的模板（单一来源——此前模板正文
    # 硬编码在本函数里，改文案要同时改代码与文档两处）
    for g in spec["generated"]:
        dest = Path(g["dest"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(Path(g["template"]).read_text(encoding="utf-8"),
                        encoding="utf-8")
        print(f"已写入 OpenCode 自检命令：/vod-doctor（{dest}）")
    return conf


def install_remote(args, url, token):
    """mcp.vod-devkit = {type:remote, url, enabled, headers}（headers 明文，提示权限）。"""
    conf = Path(_SPEC["configPath"])
    conf.parent.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if conf.exists():
        try:
            cfg = json.loads(conf.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.setdefault("mcp", {})["vod-devkit"] = {
        "type": "remote", "url": url, "enabled": True,
        "headers": {"Authorization": f"Bearer {token}"},
    }
    conf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 OpenCode 远程 MCP 配置：{conf}（token 随配置存放，注意文件权限）")
    return conf
