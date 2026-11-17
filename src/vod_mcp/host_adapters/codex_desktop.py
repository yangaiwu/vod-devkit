"""Codex Desktop 宿主适配：个人市场（marketplace.json）+ 插件目录。

形态来源：huaweicloud-devkit src/targets.ts（codexDesktopPluginsDir/codexMarketplacePath）
与 agents/codex-desktop.ts：
- 插件目录 `~/plugins/<name>`，内含 `.mcp.json`（mcpServers）与
  `.codex-plugin/plugin.json`（插件清单）；技能在插件目录的 skills/ 下。
- Codex Desktop 通过 `~/.agents/plugins/marketplace.json` 发现插件：
  `plugins[]` 里登记 `{name, source: {source: "local", path: "./plugins/<name>"}}`。

纪律：
- marketplace.json 是共享文件：只摘/加自己的那一条，其它插件原样保留；首改落 .bak。
- 卸载 = 摘条目 + 删插件目录；不碰 `~/.agents/skills`、`~/.agents/commands` 等原生目录。
- 本机未装该宿主：形态按对表实现，doctor 标「未真机验证」。
"""
import json
import shutil
import sys
from pathlib import Path

from vod_mcp import msgs
from vod_mcp import paths as _paths
from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import server_env, server_entry

HOST = "codex-desktop"
SUPPORTS_REMOTE = True
NAME = "vod-devkit"


def _version() -> str:
    try:
        from vod_mcp import __version__
        return str(__version__)
    except Exception:
        return "0.0.0"


def _spec() -> dict:
    return host_specs.load(HOST)


def plugin_dir() -> Path:
    return Path(_spec()["skillsDir"]).parent


def marketplace_path() -> Path:
    return Path(_spec()["configPath"])


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{path} 不是合法 JSON（{e.msg}），拒绝改动") from e
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{path} 顶层不是对象，拒绝改动")
    return parsed


def _write_json(path: Path, data: dict) -> None:
    if path.exists():
        shutil.copyfile(path, str(path) + ".bak")
    _paths.atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def skills_dir(args):
    return Path(_spec()["skillsDir"])


def _write_mcp_entry(entry: dict) -> Path:
    pdir = plugin_dir()
    pdir.mkdir(parents=True, exist_ok=True)
    mcp_file = pdir / ".mcp.json"
    mcp = _read_json(mcp_file)
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[NAME] = entry
    mcp["mcpServers"] = servers
    _write_json(mcp_file, mcp)
    return mcp_file


def _register_plugin(pdir: Path) -> None:
    manifest = pdir / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    _paths.atomic_write_text(manifest, json.dumps({
        "name": NAME, "version": _version(),
        "description": "VOD 用户声音采集插件（MCP + 技能）",
        "skills": ["skills"],
    }, ensure_ascii=False, indent=2) + "\n")

    mp_path = marketplace_path()
    mp = _read_json(mp_path)
    if not mp.get("name"):
        mp["name"] = "personal"
    plugins = mp.get("plugins")
    if not isinstance(plugins, list):
        plugins = []
    record = {"name": NAME, "source": {"source": "local", "path": f"./plugins/{NAME}"}}
    replaced = False
    for i, p in enumerate(plugins):
        if isinstance(p, dict) and p.get("name") == NAME:
            plugins[i] = record
            replaced = True
            break
    if not replaced:
        plugins.append(record)
    mp["plugins"] = plugins
    _write_json(mp_path, mp)
    print(f"已写入 Codex Desktop 插件目录：{pdir}")
    print(f"已在个人市场登记（{('更新' if replaced else '新增')}）：{mp_path}（{msgs.effective_unit('Codex Desktop')}）")


def install(args, packs):
    pdir = plugin_dir()
    _write_mcp_entry({"command": sys.executable, "args": [server_entry()],
                      "env": server_env(args, packs)})
    _register_plugin(pdir)
    return marketplace_path()


def install_remote(args, url, token):
    pdir = plugin_dir()
    mcp_file = _write_mcp_entry({"url": url,
                                 "headers": {"Authorization": f"Bearer {token}"}})
    _register_plugin(pdir)
    print(f"已写入 Codex Desktop 远程 MCP：{mcp_file}（token 明文，注意文件权限）")
    return mcp_file


def uninstall() -> None:
    """摘市场条目 + 删插件目录（只动自己的，不删宿主原生目录）。"""
    mp_path = marketplace_path()
    if mp_path.exists():
        try:
            mp = _read_json(mp_path)
        except RuntimeError as e:
            print(f"skip（{e}）")
            return
        plugins = [p for p in (mp.get("plugins") or [])
                   if not (isinstance(p, dict) and p.get("name") == NAME)]
        mp["plugins"] = plugins
        _write_json(mp_path, mp)
        print(f"removed marketplace entry: {mp_path}")
    pdir = plugin_dir()
    if pdir.exists():
        shutil.rmtree(pdir)
        print("removed:", pdir)