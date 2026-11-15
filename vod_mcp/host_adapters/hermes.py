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
def _spec() -> dict:
    """调用期现读：host.json 的 ~ 必须在调用期按当前 HOME 解析。

    2026-11-12 实锤：模块 import 期求值 _MCP_DIR 后，测试里 monkeypatch HOME
    写不到隔离目录，直接把真实 ~/.hermes/mcp/vod-devkit.json 覆盖成了桩值
    （command=/x/vod_mcp/server.py）——真机 doctor 当场读到坏条目。
    """
    return host_specs.load("hermes")


def skills_dir(args):
    return Path(_spec()["skillsDir"])


PLUGIN_NAME = "vod-feedback-router"


def _enabled_plugins() -> list:
    """读 hermes 配置里的 plugins.enabled（CLI 输出是 "- name" 行）。

    无 CLI 直接返回空：裸 subprocess 会抛 FileNotFoundError 打崩整个 install
    （CI/无宿主机器上实测）——缺 CLI 是"降级"不是"失败"。
    """
    if not shutil.which("hermes"):
        return []
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
    conf = Path(_spec()["configPath"]).parent / "vod-devkit.json"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(json.dumps({
        "name": "vod-devkit", "command": sys.executable,
        "args": [server_entry()], "env": server_env(args, packs),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    env_args = []
    for k, v in server_env(args, packs).items():
        env_args.extend([k + "=" + v])
    # 无 CLI 时不裸 exec（FileNotFoundError 会打崩 install）：JSON 已落盘，
    # 用户可手工并入 config.yaml —— 缺 CLI 是降级，不是失败。
    if shutil.which("hermes"):
        r = subprocess.run(
            ["hermes", "mcp", "add", "vod-devkit", "--command", sys.executable,
             *["--env"] + env_args, "--args", server_entry()],
            input="y\ny\n", capture_output=True, text=True)
    else:
        r = None
        print(f"提示：未找到 hermes CLI（PATH），已写出配置片段：{conf}\n"
              "      将其并入 ~/.hermes/config.yaml 的 mcp_servers 后重启会话生效",
              file=sys.stderr)
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
    if r is None:
        pass  # 无 CLI：上面已经给过指引
    elif r.returncode == 0:
        print("已注册 Hermes MCP（hermes mcp list 可见；重启会话生效）")
    else:
        print(f"提示：hermes mcp add 未成功（{r.stderr.strip()[:150]}）；"
              f"可将 {conf} 内容并入 Hermes 配置")
    return conf


def install_remote(args, url, token):
    """hermes mcp add --url：token 经 env 注入，配置里只留 ${MCP_VOD_DEVKIT_API_KEY} 引用。

    B1（2026-11-13 真机实锤）：hermes mcp add 对已存在条目的交互链是三问
    （Overwrite? → 认证? → Enable all tools?），管道 input 只给两个 y 时第三问
    读不到输入 → hermes 端 Cancelled 且仍 exit 0 → 安装器打印"已注册"但
    config.yaml 纹丝不动（静默假绿）。修法两道：
    ①stdin 喂不封顶的 y 流（迭代器持续供给，hermes 问几问答几个——多问多答、
      少问即 EOF 收尾），不再数提示个数；
    ②rc=0 不算数——读回 hermes 配置真源（config.yaml mcp_servers.vod-devkit
      的 url），断言远程条目真的写进去了；没写进去就非零退出报"未注册"，
      绝不静默。
    """
    import os
    env = os.environ.copy()
    env["MCP_VOD_DEVKIT_API_KEY"] = token

    def _yes_forever():
        # 交互问数随 hermes 版本变化（首次装=2 问，覆盖装=3 问），流式供给不数数
        for _ in range(64):
            yield "y\n"

    r = subprocess.run(
        ["hermes", "mcp", "add", "vod-devkit", "--url", url, "--auth", "header"],
        input="".join(_yes_forever()), capture_output=True, text=True, env=env,
        timeout=180)
    # 防静默：读回 config.yaml 断言远程条目在（Cancelled 会 rc=0 但不落配置）
    registered = _hermes_registration_is_remote(url)
    if r.returncode != 0 or not registered:
        reason = (f"hermes mcp add rc={r.returncode}，"
                  + ("配置读回未见远程条目（交互确认被跳过即静默取消）" if not registered
                     else f"stderr={(r.stderr or '').strip()[-150:]}"))
        print(f"[vod-devkit] Hermes 远程 MCP 注册未落盘：{reason}\n"
              "  可手工执行：hermes mcp add vod-devkit --url <url> --auth header "
              "（逐问回答 y）", file=sys.stderr)
        sys.exit(1)
    conf = Path(_spec()["configPath"]).parent / "vod-devkit.json"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(json.dumps({"name": "vod-devkit", "url": url,
                                "headers": {"Authorization": "Bearer ${MCP_VOD_DEVKIT_API_KEY}"}},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已注册 Hermes 远程 MCP（{url}；token 存 ~/.hermes/.env，配置内只留引用）")
    return conf


def _hermes_registration_is_remote(url: str) -> bool:
    """读回 hermes 内部注册真源（config.yaml mcp_servers），断言 vod-devkit 是远程条目。

    hermes mcp add 写 ~/.hermes/config.yaml 的 mcp_servers.vod-devkit（url 字段
    为远程形态标志）；Cancelled 的假绿在这里现形。无 yaml 依赖红线：远端
    安装器零第三方依赖，这里用受限文本扫描（顶层 mcp_servers: 段下缩进块内
    找 vod-devkit 与 url 行），而非完整 yaml 解析。
    """
    cfg = Path.home() / ".hermes" / "config.yaml"
    if not cfg.is_file():
        return False
    in_section = False
    saw_entry = False
    saw_url = False
    for raw_line in cfg.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indented = raw_line[0] == " "
        stripped = raw_line.strip()
        if not indented:
            in_section = stripped.startswith("mcp_servers:")
            continue
        if not in_section:
            continue
        # mcp_servers 段内的行：条目名（一级缩进）与字段（更深缩进）
        if stripped.startswith("vod-devkit:"):
            saw_entry = True
        elif saw_entry and stripped.startswith("url:"):
            if url in stripped:
                saw_url = True
            break
        elif saw_entry and not raw_line.startswith("  vod-devkit") and stripped.endswith(":"):
            if not raw_line.startswith(" " * 4):  # 下一个一级条目：停止
                break
    return saw_entry and saw_url
