"""通用 MCP 宿主适配（A 层兜底）。

对标 huaweicloud-devkit 的 `configureGenericMCP()`：不认识/没有专属模块的宿主
不该"不支持"，而应"能装 + 给片段"。

两条纪律：
- **外科式合并**：只写 `mcpServers["vod-devkit"]` 一个键，其它 server 与用户
  自有键原样保留；首次改动前落 `.bak`。共享配置文件永不整文件重写语义删除。
- **宁可不装不可装错**：现有文件不是合法 JSON / 不是对象 → 报错退出、字节不动。

探测表只收录「已知 config 形态」的宿主（JSON + mcpServers）。不在表里也能装：
`--mcp-config <path>` 显式给出路径即可。
"""
import json
import shutil
import sys
from pathlib import Path

from vod_mcp.host_adapters.base import server_env, server_entry

HOST = "generic"
SUPPORTS_REMOTE = True

ENTRY_NAME = "vod-devkit"

# id → 探测目录 + 默认 MCP 配置文件（相对 HOME）
KNOWN_HOSTS = [
    {"id": "claude-code", "paths": ["~/.claude", "~/.claude.json"],
     "config": "~/.claude.json", "label": "Claude Code"},
    {"id": "cursor", "paths": ["~/.cursor"],
     "config": "~/.cursor/mcp.json", "label": "Cursor"},
    {"id": "windsurf", "paths": ["~/.codeium/windsurf"],
     "config": "~/.codeium/windsurf/mcp_config.json", "label": "Windsurf"},
    {"id": "cline", "paths": ["~/.cline"],
     "config": "~/.cline/mcp_settings.json", "label": "Cline"},
]


def _expand(p: str) -> Path:
    return Path(p).expanduser()


def detect_known() -> list:
    """探测在场但没有专属适配模块的宿主（只读，不写任何文件）。"""
    found = []
    for h in KNOWN_HOSTS:
        if any(_expand(p).exists() for p in h["paths"]):
            found.append(h)
    return found


def snippet(packs: str = "core,collect", api_base: str = "") -> dict:
    """可粘贴的 stdio 片段（安装器 no-path 时打印）。"""
    args = type("A", (), {"java_api_base": api_base})()
    entry = {"command": sys.executable, "args": [server_entry()],
             "env": server_env(args, packs)}
    return {"mcpServers": {ENTRY_NAME: entry}}


def merge_mcp_servers(path: Path, entry: dict, name: str = ENTRY_NAME) -> str:
    """外科式合并 mcpServers 条目 → created / updated / unchanged。

    现有文件非法 JSON 或不是对象时抛 RuntimeError（调用方拒绝安装，字节未动）。
    """
    cfg = {}
    existed = path.exists()
    if existed:
        raw = path.read_text(encoding="utf-8")
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"{path} 不是合法 JSON（{e.msg}），拒绝改动") from e
            if not isinstance(parsed, dict):
                raise RuntimeError(f"{path} 顶层不是对象，拒绝改动")
            cfg = parsed
    servers = cfg.get("mcpServers")
    if servers is None:
        servers = {}
    elif not isinstance(servers, dict):
        raise RuntimeError(f"{path} 的 mcpServers 不是对象，拒绝改动")
    if servers.get(name) == entry:
        return "unchanged"
    action = "updated" if servers.get(name) else "created"
    if existed and action == "created":
        shutil.copyfile(path, str(path) + ".bak")
    servers[name] = entry
    cfg["mcpServers"] = servers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return action


def install(args, packs):
    """无专属模块的宿主：合并到 --mcp-config 指定文件；未给路径则打印片段。"""
    cfg_path = (getattr(args, "mcp_config", "") or "").strip()
    detected = detect_known()
    if not cfg_path:
        if detected:
            print("探测到通用 MCP 宿主：" + "、".join(h["label"] for h in detected)
                  + "（本插件无专属适配，走通用写入）")
            print("  可用：--target generic --mcp-config " + detected[0]["config"])
        print("未给 --mcp-config，不写任何文件。可粘贴片段（MCP 客户端通用）：")
        print(json.dumps(snippet(packs, args.java_api_base), ensure_ascii=False, indent=2))
        print("  （技能目录未知，未安装技能；如需话术层请用 --target hermes|opencode|codex）")
        return None
    path = _expand(cfg_path)
    entry = {"command": sys.executable, "args": [server_entry()],
             "env": server_env(args, packs)}
    action = merge_mcp_servers(path, entry)
    verb = {"created": "写入", "updated": "更新", "unchanged": "跳过（已一致）"}[action]
    print(f"已{verb} {path.name} 的 mcpServers.vod-devkit：{path}（重启宿主会话生效）")
    return path


def install_remote(args, url, token):
    """通用远程写入：headers 带 Bearer（明文，提示权限），其余键不动。"""
    cfg_path = (getattr(args, "mcp_config", "") or "").strip()
    if not cfg_path:
        print("远程 attach 需要显式 --mcp-config <path>（通用宿主猜不出配置文件）",
              file=sys.stderr)
        sys.exit(2)
    path = _expand(cfg_path)
    entry = {"url": url, "headers": {"Authorization": f"Bearer {token}"}}
    action = merge_mcp_servers(path, entry)
    print(f"已写入通用远程 MCP 条目（{action}）：{path}（token 明文，注意文件权限）")
    return path


def skills_dir(args):
    return None