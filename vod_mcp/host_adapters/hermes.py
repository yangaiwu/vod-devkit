"""Hermes 宿主适配：官方 hermes mcp add + 路由插件部署。

落点与探测来自 integrations/hermes/host.json（数据驱动，代码里不许出现第二份
路径字面量）；新增 Hermes 特定逻辑只改本模块。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import ROOT, server_env, server_entry

HOST = "hermes"
SUPPORTS_REMOTE = True
_SPEC = host_specs.load("hermes")
_MCP_DIR = Path(_SPEC["configPath"]).parent


def skills_dir(args):
    return Path(_SPEC["skillsDir"])


PLUGIN_NAME = "vod-feedback-router"


def _enabled_plugins() -> list:
    """读 hermes 配置里的 plugins.enabled（CLI 输出是 "- name" 行）。"""
    r = subprocess.run(["hermes", "config", "get", "plugins.enabled"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif line.startswith("-"):
            out.append(line[1:].strip())
    return [x for x in out if x]


def enable_plugin(name: str = PLUGIN_NAME) -> str:
    """把路由插件加进 plugins.enabled（幂等）。返回 created / unchanged / skipped。

    只追加一个名字：读现有名单 → 追加 → `hermes config set plugins.enabled '[...]'`。
    不整文件改 config.yaml（用户可能手改过格式/注释），失败只提示不动。
    """
    import json as _json
    if not shutil.which("hermes"):
        print("提示：未找到 hermes CLI，路由插件需手动在 plugins.enabled 中加入 "
              f"{name} 后生效")
        return "skipped"
    cur = _enabled_plugins()
    if name in cur:
        return "unchanged"
    merged = cur + [name]
    r = subprocess.run(["hermes", "config", "set", "plugins.enabled",
                        _json.dumps(merged)], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print("提示：自动启用路由插件失败（" + (r.stderr or r.stdout).strip()[:120]
              + "）；请手动把 " + name + " 加入 plugins.enabled")
        return "skipped"
    return "created"


def install(args, packs: str) -> Path:
    """Hermes：官方途径 hermes mcp add（config.yaml mcp_servers）。"""
    conf = _MCP_DIR / "vod-devkit.json"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(json.dumps({
        "name": "vod-devkit", "command": sys.executable,
        "args": [server_entry()], "env": server_env(args, packs),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    env_args = []
    for k, v in server_env(args, packs).items():
        env_args.extend([k + "=" + v])
    r = subprocess.run(
        ["hermes", "mcp", "add", "vod-devkit", "--command", sys.executable,
         *["--env"] + env_args, "--args", server_entry()],
        input="y\ny\n", capture_output=True, text=True)
    # D-hook-1：强制评估路由插件（pre_llm_call 确定性意图路由，业界 forced-eval 模式）
    plug_src = ROOT / "hermes-plugin" / "vod-feedback-router"
    plug_dst = Path.home() / ".hermes" / "plugins" / PLUGIN_NAME
    if plug_src.is_dir():
        if plug_dst.exists():
            shutil.rmtree(plug_dst)
        shutil.copytree(plug_src, plug_dst)
        state = enable_plugin()
        verb = {"created": "已自动加入 plugins.enabled",
                "unchanged": "已在 plugins.enabled 中",
                "skipped": "未自动启用（见上方提示）"}[state]
        print(f"已安装 {PLUGIN_NAME} 路由插件（~/.hermes/plugins/，{verb}；重启会话生效）")
    if r.returncode == 0:
        print("已注册 Hermes MCP（hermes mcp list 可见；重启会话生效）")
    else:
        print(f"提示：hermes mcp add 未成功（{r.stderr.strip()[:150]}）；"
              f"可将 {conf} 内容并入 Hermes 配置")
    return conf


def install_remote(args, url, token):
    """hermes mcp add --url：token 经 env 注入，配置里只留 ${MCP_VOD_DEVKIT_API_KEY} 引用。"""
    import os
    env = os.environ.copy()
    env["MCP_VOD_DEVKIT_API_KEY"] = token
    r = subprocess.run(
        ["hermes", "mcp", "add", "vod-devkit", "--url", url, "--auth", "header"],
        input="y\ny\n", capture_output=True, text=True, env=env, timeout=180)
    if r.returncode != 0:
        print(f"[vod-devkit] hermes mcp add（remote）失败：{(r.stderr or r.stdout).strip()[-200:]}",
              file=sys.stderr)
        sys.exit(1)
    conf = _MCP_DIR / "vod-devkit.json"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(json.dumps({"name": "vod-devkit", "url": url,
                                "headers": {"Authorization": "Bearer ${MCP_VOD_DEVKIT_API_KEY}"}},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已注册 Hermes 远程 MCP（{url}；token 存 ~/.hermes/.env，配置内只留引用）")
    return conf
