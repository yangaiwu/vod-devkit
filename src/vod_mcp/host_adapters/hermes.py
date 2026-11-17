"""Hermes 宿主适配：官方 hermes mcp add + 路由插件部署。

落点与探测来自 integrations/hermes/host.json（数据驱动，代码里不许出现第二份
路径字面量）；新增 Hermes 特定逻辑只改本模块。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp import paths
from vod_mcp.host_adapters.base import server_env, server_entry

HOST = "hermes"
SUPPORTS_REMOTE = True
def _hermes_home() -> Path | None:
    """HERMES_HOME 显式给定时就是宿主根（hermes CLI 只认它，不认 HOME）。"""
    env = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(env).expanduser() if env else None


def _real_home() -> Path | None:
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except Exception:      # noqa: BLE001  平台没有 pwd 就不猜
        return None


def _home_state() -> tuple[Path | None, Path | None, bool]:
    """(HOME, 真实家目录, 是否隔离)——落点判定的**唯一来源**（S161 / D-single-entry-1）。

    2026-11-16 评审实锤：`_cli_env()` 用「root 不在真实家目录之下」判隔离 root，
    `_spec()` 用「root 在 HOME 之下」，两条判据对 `HERMES_HOME=/tmp/shared` 结论相反
    （CLI 写 /tmp/shared、文件写 `<HOME>/.hermes`）——就是 0.5.25 修过的分裂形态又长回来。
    """
    home_s = (os.environ.get("HOME") or "").strip()
    real = _real_home()
    if not home_s:
        return None, real, False
    try:
        home = Path(home_s).expanduser().resolve()
    except OSError:
        return Path(home_s).expanduser(), real, False
    return home, real, home != real


def _effective_hermes_home() -> Path | None:
    """生效的 HERMES_HOME：真实 HOME 直接认；隔离 HOME 下按三支判（S161/S168）。

    1) 位于**当前隔离 HOME 之内** → 认：矩阵/显式钉根（`<HOME>/.hermes` 或自定义子目录）；
    2) 位于**真实家目录**之下（且不在隔离 HOME 内）→ 忽略：网关派生的
       `HERMES_HOME=/root/.hermes` 就是这一支，照它写会把隔离安装带回真机；
    3) 其余 → 认：容器形态 `HOME=/app` + `HERMES_HOME=/data/hermes`（挂载卷）属显式运维
       配置，忽略它会把配置与技能写进镜像层、重建即丢（S168 评审实锤）。
    CLI 与文件两个落点都只读这一个判据，所以任一支下两边都同源。
    """
    root = _hermes_home()
    if root is None:
        return None
    home, real, isolated = _home_state()
    if not isolated or home is None:
        return root
    try:
        root.resolve().relative_to(home)
        return root                                  # 1) 隔离根内
    except (OSError, ValueError):
        pass
    if real is not None:
        try:
            root.resolve().relative_to(real)
            return None                              # 2) 真实家目录派生（泄漏面）
        except (OSError, ValueError):
            pass
    return root                                      # 3) 显式运维配置（容器挂载卷等）


def _cli_env() -> dict:
    """给 hermes CLI 子进程的环境：让 CLI 的落点与我们写文件的落点**同一处**。

    判据全部来自 `_effective_hermes_home()`（与 `_spec()` 同源）：
    - 认到 HERMES_HOME → 两个落点都用它；
    - 隔离 HOME 且 HERMES_HOME 不可信 → 两边都跟随 `<HOME>/.hermes`（stderr 说明）；
    - 真实 HOME 且未设 HERMES_HOME → 原样继承。
    """
    env = dict(os.environ)
    eff = _effective_hermes_home()
    if eff is not None:
        env["HERMES_HOME"] = str(eff)
        return env
    home, real, isolated = _home_state()
    if not isolated or home is None:
        return env
    env["HERMES_HOME"] = str(home / ".hermes")
    print(f"[vod-devkit] 隔离 HOME：hermes CLI 落点跟随 HOME（{env['HERMES_HOME']}），"
          f"不写 {real}（继承的 HERMES_HOME={os.environ.get('HERMES_HOME') or '<unset>'} 被忽略）",
          file=sys.stderr)
    return env


def _spec() -> dict:
    """调用期现读：host.json 的 ~ 必须在调用期按当前 HOME 解析。

    2026-11-12 实锤：模块 import 期求值 _MCP_DIR 后，测试里 monkeypatch HOME
    写不到隔离目录，直接把真实 ~/.hermes/mcp/vod-devkit.json 覆盖成了桩值
    （command=/x/vod_mcp/server.py）——真机 doctor 当场读到坏条目。

    2026-11-16 补：设了 HERMES_HOME 时，spec 里所有 ~/.hermes 前缀重定向到它
    （安装面与 hermes CLI 的落点必须同一处，否则 JSON 与 config.yaml 分裂）。
    """
    spec = host_specs.load("hermes")
    root = _effective_hermes_home()
    if root:
        def reroot(val: str) -> str:
            """`HOME/.hermes` 之下的落点改成挂到 HERMES_HOME 下；其它路径原样返回。

            按**前缀**归属，不按分量名搜索：HOME 本身可能落在含 `.hermes` 分量的路径里
            （隔离/容器形态 `<tmp>/.hermes/cache/...`），`parts.index(".hermes")` 会命中
            外层那一层，把落点拼成 `<HERMES_HOME>/cache/.../home/.hermes/...` 的自我嵌套
            （S159，host_matrix 实锤「配置未落盘」）。
            """
            home = (os.environ.get("HOME") or "").strip()
            if not home or not val:
                return val
            try:
                hh = (Path(home).expanduser() / ".hermes").resolve()
                rel = Path(val).resolve().relative_to(hh)
            except (OSError, ValueError):
                return val
            return str(root / rel) if rel.parts else str(root)

        for key in ("config", "mcpConfigFile", "profileConfig", "skillsDir",
                    "configPath"):
            spec[key] = reroot(str(spec.get(key) or "")) or spec.get(key)
        if spec.get("managedPaths"):
            spec["managedPaths"] = [reroot(str(pth)) for pth in spec["managedPaths"]]
    return spec


def skills_dir(args):
    return Path(_spec()["skillsDir"])


LEGACY_PLUGIN = "vod-feedback-router"   # 旧形态（插件包），只用于清理
HOOK_MARK = "vod_router.py"             # 我们这条 shell hook 的识别标志（幂等/摘除共用）
EVENT = "pre_llm_call"
HOOK_TIMEOUT = 10
# 安全面第二条：pre_tool_call（Hermes 把它当**阻塞事件**，stdout 回
# {"decision":"block"} 或 exit 2 即拦截）。只拦"把 key 读进对话"的动作，
# 其余一律放行——详见 integrations/hermes/hooks/vod_guard.py。
GUARD_EVENT = "pre_tool_call"
GUARD_MARK = "vod_guard.py"
GUARD_TIMEOUT = 5


def _profile_config() -> Path:
    return Path(_spec()["profileConfig"])


# 外部 CLI 子进程的上限（S165）。远程面本来就是 180s；本地面此前没有，空/异常
# HERMES_HOME 下 hermes CLI 会自举依赖挂住，install --target all 卡在最后一台。
_CLI_TIMEOUT = 60


def _hook_script() -> Path:
    return paths.hook_script()


def _hook_command() -> str:
    import shlex
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(_hook_script()))}"


def upsert_hook(text: str, event: str, command: str, timeout: int, mark: str) -> tuple:
    """把一个 shell hook 写进 config.yaml **文本**的指定事件，返回 (new_text, state)。

    为什么手改 YAML 文本而不 load/dump：运行时零第三方依赖（无 pyyaml），而
    round-trip dump 会把用户的注释、锚点、顺序全洗掉——那是拿用户的整份配置
    换我们的方便。所以只做"最小结构插入"，并且**形态不认识就抛错**（调用方
    打印可粘贴片段，绝不猜着改）。

    mark 是"这条 hook 属于我们"的识别标志（脚本名），幂等与摘除共用同一条判据。

    state: unchanged（已有本条）/ added（插进已有事件段）/ created（新建 hooks 段）
    """
    if command in text and mark in text:
        return (text, "unchanged")
    lines = text.splitlines()
    entries = [f'- command: "{command}"', f'  timeout: {timeout}']

    def _is_ours(line: str) -> bool:
        return mark in line and "command" in line

    idx_hooks = next((i for i, ln in enumerate(lines) if ln.rstrip() == "hooks:"), None)
    if idx_hooks is None:
        if any(ln.startswith("hooks:") for ln in lines):
            raise RuntimeError("config.yaml 的 hooks 段不是块形态（hooks: 后有值），"
                              "拒绝自动插入")
        out = list(lines)
        if out and out[-1].strip():
            out.append("")
        out += ["hooks:", f"  {event}:", "    " + entries[0], "    " + entries[1]]
        return ("\n".join(out) + "\n", "created")

    ours = next((ln for ln in lines if _is_ours(ln)), None)
    if ours is not None:
        # S175：同 mark 但命令不同 → 替换。旧实现直接 unchanged，于是换解释器/换脚本路径后
        # 永不更新（真机实测：pre_tool_call 停在 python3.12、pre_llm_call 停在 Hermes 3.14 venv）。
        lead = ours[:len(ours) - len(ours.lstrip())]
        out = [f"{lead}- command: \"{command}\"" if ln is ours else ln for ln in lines]
        return ("\n".join(out), "updated")

    # hooks 段结束位置：下一个缩进为 0 的非空行
    end_hooks = len(lines)
    for j in range(idx_hooks + 1, len(lines)):
        if lines[j].strip() and not lines[j][0].isspace():
            end_hooks = j
            break
    idx_event = next((i for i in range(idx_hooks + 1, end_hooks)
                      if lines[i].strip() == f"{event}:"), None)
    if idx_event is None:
        insert_at = idx_hooks + 1
        new_lines = [f"  {event}:", "    " + entries[0], "    " + entries[1]]
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


def upsert_llm_hook(text: str, command: str, timeout: int = HOOK_TIMEOUT) -> tuple:
    """预采集路由（pre_llm_call）——薄壳，保留历史签名给已有用例。"""
    return upsert_hook(text, EVENT, command, timeout, HOOK_MARK)


def upsert_guard_hook(text: str, command: str, timeout: int = GUARD_TIMEOUT) -> tuple:
    """读 Key 拦截（pre_tool_call，阻塞事件）——薄壳。"""
    return upsert_hook(text, GUARD_EVENT, command, timeout, GUARD_MARK)


def remove_hook(text: str, mark: str) -> tuple:
    """从 config.yaml 文本里摘掉含 mark 的 hook 项（幂等）。返回 (new_text, removed?)。

    只删含 mark 的 `- command:` 行及其紧随的 `timeout:` 行；其余条目（别人的
    hook、用户的注释、事件段本身若是空的也留着）一律不动——空事件段无害，删别人的
    配置才是有害的。
    """
    lines = text.splitlines()
    out, removed, i = [], False, 0
    while i < len(lines):
        ln = lines[i]
        if "- command:" in ln and mark in ln:
            removed = True
            i += 1
            if i < len(lines) and lines[i].strip().startswith("timeout:"):
                i += 1
            continue
        out.append(ln)
        i += 1
    return ("\n".join(out) + ("\n" if text.endswith("\n") else ""), removed)


def remove_llm_hook(text: str) -> tuple:
    return remove_hook(text, HOOK_MARK)


def remove_guard_hook(text: str) -> tuple:
    return remove_hook(text, GUARD_MARK)


def _guard_command() -> str:
    import shlex
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(paths.guard_script()))}"


def _register_hooks(cfg_path: Path) -> None:
    """装两条 shell hook（同一套脚本机制，各自事件注册）。

    - `pre_llm_call`：预采集意图路由（注入采集纪律），非阻塞；
    - `pre_tool_call`：只拦"读 runtime.json / 导出 VOD_*KEY"的动作，Hermes 的**阻塞**事件。

    两条都幂等；config.yaml 形态不认识时只打可粘贴片段，绝不猜着重写用户配置。
    单条失败不阻塞另一条（hook 与 MCP 配置是两条独立链）。
    """
    try:
        text = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
    except OSError as e:
        print(f"[vod-devkit] warn: 读不到 {cfg_path}（{e}），两条 hook 均未注册",
              file=sys.stderr)
        return
    plans = (
        ("预采集 hook", EVENT, _hook_command(), HOOK_TIMEOUT, upsert_llm_hook),
        ("读 Key 拦截 hook", GUARD_EVENT, _guard_command(), GUARD_TIMEOUT, upsert_guard_hook),
    )
    for label, event, cmd, timeout, upsert in plans:
        try:
            new_text, state = upsert(text, cmd)
        except RuntimeError as e:
            print(f"[vod-devkit] warn: {label}未注册（{e}）。请手动把下面两行加进 "
                  f"{cfg_path} 的 hooks.{event}：\n"
                  f"    - command: \"{cmd}\"\n    timeout: {timeout}", file=sys.stderr)
            continue
        if state != "unchanged":
            try:
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(new_text, encoding="utf-8")
            except OSError as e:
                print(f"[vod-devkit] warn: {label}写入失败（{e}）", file=sys.stderr)
                continue
        text = new_text
        verb = {"created": "已新建 hooks 段", "added": f"已加入 hooks.{event}",
                "updated": "已替换旧命令（解释器/脚本路径变了）",
                "unchanged": "已存在"}.get(state, state)
        print(f"已注册{label}（{cfg_path}，{verb}；首次使用 hermes 会弹一次同意）")


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
                           capture_output=True, text=True, timeout=60, env=_cli_env())
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
                                 json.dumps(keep)], capture_output=True, text=True, timeout=60,
                                env=_cli_env())
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
        try:
            r = subprocess.run(
                ["hermes", "mcp", "add", "vod-devkit", "--command", sys.executable,
                 *["--env"] + env_args, "--args", server_entry()],
                input="y\ny\n", capture_output=True, text=True, env=_cli_env(),
                timeout=_CLI_TIMEOUT)
        except subprocess.TimeoutExpired:
            r = None
            print(f"[vod-devkit] hermes mcp add 超时（{_CLI_TIMEOUT}s）：已写出配置片段 {conf}\n"
                  "      可手工执行 `hermes mcp add vod-devkit --command …`（逐问回答 y），"
                  "或把该 JSON 并入 config.yaml 的 mcp_servers", file=sys.stderr)
    else:
        r = None
        print(f"提示：未找到 hermes CLI（PATH），已写出配置片段：{conf}\n"
              "      将其并入 ~/.hermes/config.yaml 的 mcp_servers 后重启会话生效",
              file=sys.stderr)
    # D-hook-unify-1：预采集路由走 config.yaml 的 hooks.pre_llm_call（shell hook）。
    # 不再装 Python 插件：同一个"stdin JSON → stdout context"脚本可被任何宿主
    # 用各自的机制注册，宿主进程内不需要 import 我们的代码。
    # D-key-guard-4：同一套脚本机制再注册一条 hooks.pre_tool_call（阻塞事件），
    # 只拦"读 runtime.json / 导出 VOD_*KEY"的动作——机制化技能里的"只引指纹"。
    _register_hooks(_profile_config())
    legacy = remove_legacy_plugin()
    if legacy:
        print(f"已清理旧插件形态（避免与新 hook 双份注入）：{legacy}")
    registered = mcp_entry_present()
    if registered:
        print("已注册 Hermes MCP（hermes mcp list 可见；重启会话生效）")
    elif r is None:
        # 无 CLI / 超时：降级（片段已写），但缺口必须可见——文案与 doctor 同源（S172）
        from vod_mcp.host_adapters import host_verify

        for p in host_verify.problems("hermes", degraded=True):
            print(f"[vod-devkit] {p['message']}", file=sys.stderr)
    elif r.returncode == 0:
        # S170：rc=0 但配置无条目 = 交互确认被跳过（Cancelled 仍 exit 0）→ 必须非零退出
        print(f"[vod-devkit] Hermes MCP 注册未落盘：hermes mcp add rc=0 但 "
              f"{Path(_spec()['profileConfig'])} 里没有 mcp_servers.vod-devkit"
              "（交互确认被跳过即静默取消）\n"
              f"  可手工把 {conf} 并入该配置的 mcp_servers，或重跑 install（逐问回答 y）",
              file=sys.stderr)
        sys.exit(1)
    else:
        print(f"提示：hermes mcp add 未成功（{r.stderr.strip()[:150]}）；"
              f"可将 {conf} 内容并入 Hermes 配置", file=sys.stderr)
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
    # token 可选（D-token-machine-1）：没有就不注入——请求不带 Bearer，
    # 由远程 server 用机器级匿名令牌提交（同机部署默认形态）。
    if token:
        env["MCP_VOD_DEVKIT_API_KEY"] = token

    def _yes_forever():
        # 交互问数随 hermes 版本变化（首次装=2 问，覆盖装=3 问），流式供给不数数
        for _ in range(64):
            yield "y\n"

    r = subprocess.run(
        ["hermes", "mcp", "add", "vod-devkit", "--url", url, "--auth", "header"],
        input="".join(_yes_forever()), capture_output=True, text=True,
        env={**env, **_cli_env()}, timeout=180)
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
    payload = {"name": "vod-devkit", "url": url}
    if token:   # 无 token 时不写 headers：请求不带 Bearer，走服务端匿名令牌
        payload["headers"] = {"Authorization": "Bearer ${MCP_VOD_DEVKIT_API_KEY}"}
    conf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已注册 Hermes 远程 MCP（{url}；token 存 ~/.hermes/.env，配置内只留引用）")
    return conf


def _scan_mcp_entry_detail(cfg: Path) -> dict:
    """扫描 config.yaml 的 mcp_servers.vod-devkit：{present, enabled_false, url}（D-host-verify-1）。"""
    out: dict = {"present": False, "enabled_false": False, "url": None}
    if not cfg.is_file():
        return out
    in_section = False
    in_entry = False
    for raw_line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indented = raw_line[0] == " "
        stripped = raw_line.strip()
        if not indented:
            in_section = stripped.startswith("mcp_servers:")
            in_entry = False
            continue
        if not in_section:
            continue
        if stripped.startswith("vod-devkit:"):
            out["present"] = True
            in_entry = True
            continue
        if in_entry and stripped.endswith(":") and not raw_line.startswith(" " * 4):
            in_entry = False        # 下一个一级条目
            continue
        if in_entry and stripped.startswith("enabled:"):
            out["enabled_false"] = stripped.split(":", 1)[1].strip().lower() in ("false", "no", "0")
        elif in_entry and stripped.startswith("url:"):
            out["url"] = stripped.split(":", 1)[1].strip().strip("\"'")
    return out


def mcp_entry_state(path: Path | None = None) -> dict:
    """configPath 里 vod-devkit 条目的形态（present / enabled_false / url）。"""
    return _scan_mcp_entry_detail(path or Path(_spec()["profileConfig"]))


def _scan_mcp_entry(cfg: Path, url: str | None = None) -> bool:
    """在 config.yaml 的 mcp_servers 段里找 vod-devkit 条目（给了 url 就要求该行含它）。

    单一扫描实现：本地注册读回（`mcp_entry_present`）与远程读回
    （`_hermes_registration_is_remote`）共用，避免两份文本解析各自演化。
    无 yaml 依赖红线：受限文本扫描（顶层 `mcp_servers:` 段下缩进块），不引 PyYAML。
    """
    if not cfg.is_file():
        return False
    in_section = False
    saw_entry = False
    saw_url = False
    for raw_line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indented = raw_line[0] == " "
        stripped = raw_line.strip()
        if not indented:
            in_section = stripped.startswith("mcp_servers:")
            continue
        if not in_section:
            continue
        if stripped.startswith("vod-devkit:"):
            saw_entry = True
        elif saw_entry and stripped.startswith("url:"):
            if url is None or url in stripped:
                saw_url = True
            break
        elif saw_entry and not raw_line.startswith("  vod-devkit") and stripped.endswith(":"):
            if not raw_line.startswith(" " * 4):      # 下一个一级条目：停止
                break
    return saw_entry if url is None else (saw_entry and saw_url)


def mcp_entry_present(path: Path | None = None) -> bool:
    """configPath（= `_spec()["profileConfig"]`）里有没有 mcp_servers.vod-devkit（S170）。

    为什么必须有：`hermes mcp add` 在交互确认被跳过（Cancelled）时仍 exit 0 且不写配置；
    只看 rc 就会打印「已注册」，而用户侧是「工具连不上、自检全绿」（2026-11-17 实测）。
    """
    return _scan_mcp_entry(path or Path(_spec()["profileConfig"]))


def _hermes_registration_is_remote(url: str) -> bool:
    """读回 hermes 内部注册真源，断言 vod-devkit 是**远程**条目（url 匹配）。

    S171：落点必须与 `_spec()` 同源（configPath/profileConfig），不再用
    `Path.home()/.hermes` —— 自定义 HERMES_HOME（隔离/容器/数据盘）时旧写法会把
    正常注册判成失败并 exit 1（实测）。
    """
    return _scan_mcp_entry(Path(_spec()["profileConfig"]), url)
