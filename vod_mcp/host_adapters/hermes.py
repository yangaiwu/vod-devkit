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


LEGACY_PLUGIN = "vod-feedback-router"   # 旧形态（插件包），只用于清理
HOOK_MARK = "vod_router.py"             # 我们这条 shell hook 的识别标志（幂等/摘除共用）
EVENT = "pre_llm_call"
HOOK_TIMEOUT = 10


def _profile_config() -> Path:
    return Path(_spec()["profileConfig"])


def _hook_script() -> Path:
    return ROOT / "hooks" / "vod_router.py"


def _hook_command() -> str:
    import shlex
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(_hook_script()))}"


def upsert_llm_hook(text: str, command: str, timeout: int = HOOK_TIMEOUT) -> tuple:
    """把 pre_llm_call shell hook 写进 config.yaml **文本**，返回 (new_text, state)。

    为什么手改 YAML 文本而不 load/dump：运行时零第三方依赖（无 pyyaml），而
    round-trip dump 会把用户的注释、锚点、顺序全洗掉——那是拿用户的整份配置
    换我们的方便。所以只做"最小结构插入"，并且**形态不认识就抛错**（调用方
    打印可粘贴片段，绝不猜着改）。

    state: unchanged（已有本条）/ added（插进已有 pre_llm_call）/ created（新建 hooks 段）
    """
    if command in text and HOOK_MARK in text:
        return (text, "unchanged")
    lines = text.splitlines()
    entries = [f'- command: "{command}"', f'  timeout: {timeout}']

    def _is_ours(line: str) -> bool:
        return HOOK_MARK in line and "command" in line

    idx_hooks = next((i for i, ln in enumerate(lines) if ln.rstrip() == "hooks:"), None)
    if idx_hooks is None:
        if any(ln.startswith("hooks:") for ln in lines):
            raise RuntimeError("config.yaml 的 hooks 段不是块形态（hooks: 后有值），"
                              "拒绝自动插入")
        out = list(lines)
        if out and out[-1].strip():
            out.append("")
        out += ["hooks:", f"  {EVENT}:", "    " + entries[0], "    " + entries[1]]
        return ("\n".join(out) + "\n", "created")

    if any(_is_ours(ln) for ln in lines):
        return (text, "unchanged")

    # hooks 段结束位置：下一个缩进为 0 的非空行
    end_hooks = len(lines)
    for j in range(idx_hooks + 1, len(lines)):
        if lines[j].strip() and not lines[j][0].isspace():
            end_hooks = j
            break
    idx_event = next((i for i in range(idx_hooks + 1, end_hooks)
                      if lines[i].strip() == f"{EVENT}:"), None)
    if idx_event is None:
        insert_at = idx_hooks + 1
        new_lines = [f"  {EVENT}:", "    " + entries[0], "    " + entries[1]]
        state = "added"
    else:
        # 插到该事件列表末尾：下一个缩进 <= 2 的非空行，或 hooks 段结束
        insert_at = idx_event + 1
        for j in range(idx_event + 1, end_hooks):
            ln = lines[j]
            if not ln.strip():
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= 2:
                insert_at = j
                break
            insert_at = j + 1
        new_lines = ["    " + entries[0], "    " + entries[1]]
        state = "added"
    out = lines[:insert_at] + new_lines + lines[insert_at:]
    return ("\n".join(out) + "\n", state)


def remove_llm_hook(text: str) -> tuple:
    """从 config.yaml 文本里摘掉我们这条 hook 项（幂等）。返回 (new_text, removed?)。

    只删含 HOOK_MARK 的 `- command:` 行及其紧随的 `timeout:` 行；其余条目（别人的
    hook、用户的注释、事件段本身若是空的也留着）一律不动——空事件段无害，删别人的
    配置才是有害的。
    """
    lines = text.splitlines()
    out, removed, i = [], False, 0
    while i < len(lines):
        ln = lines[i]
        if "- command:" in ln and HOOK_MARK in ln:
            removed = True
            i += 1
            if i < len(lines) and lines[i].strip().startswith("timeout:"):
                i += 1
            continue
        out.append(ln)
        i += 1
    return ("\n".join(out) + ("\n" if text.endswith("\n") else ""), removed)


def remove_legacy_plugin() -> str:
    """摘旧插件形态（幂等）：删目录 + 从 plugins.enabled 去名。

    为什么必须做：老装机里插件与新的 shell hook 会**同时生效**，每轮注入两段
    指令（模型看到重复要求，行为不可预测）。迁移必须单向收敛到 hook。
    """
    removed = []
    d = Path.home() / ".hermes" / "plugins" / LEGACY_PLUGIN
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        removed.append(f"目录 {d}")
    if shutil.which("hermes"):
        r = subprocess.run(["hermes", "config", "get", "plugins.enabled"],
                           capture_output=True, text=True, timeout=60)
        names = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("- "):
                names.append(line[2:].strip())
            elif line.startswith("-"):
                names.append(line[1:].strip())
        if LEGACY_PLUGIN in names:
            keep = [n for n in names if n and n != LEGACY_PLUGIN]
            rr = subprocess.run(["hermes", "config", "set", "plugins.enabled",
                                 json.dumps(keep)], capture_output=True, text=True, timeout=60)
            if rr.returncode == 0:
                removed.append("plugins.enabled 条目")
    return "；".join(removed)


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
    # D-hook-unify-1：预采集路由走 config.yaml 的 hooks.pre_llm_call（shell hook）。
    # 不再装 Python 插件：同一个"stdin JSON → stdout context"脚本可被任何宿主
    # 用各自的机制注册，宿主进程内不需要 import 我们的代码。
    cfg_path = _profile_config()
    try:
        text = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
        new_text, state = upsert_llm_hook(text, _hook_command())
    except RuntimeError as e:
        print(f"[vod-devkit] warn: 预采集 hook 未注册（{e}）。请手动把下面两行加进 "
              f"{cfg_path} 的 hooks.{EVENT}：\n"
              f"    - command: \"{_hook_command()}\"\n    timeout: {HOOK_TIMEOUT}",
              file=sys.stderr)
    else:
        if state != "unchanged":
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(new_text, encoding="utf-8")
        verb = {"created": "已新建 hooks 段",
                "added": "已加入 hooks.pre_llm_call",
                "unchanged": "已存在"}[state]
        print(f"已注册预采集 hook（{cfg_path}，{verb}；首次使用 hermes 会弹一次同意）")
    legacy = remove_legacy_plugin()
    if legacy:
        print(f"已清理旧插件形态（避免与新 hook 双份注入）：{legacy}")
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
