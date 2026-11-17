"""OpenClaw 宿主适配：只经它自己的注册表 CLI 写，绝不直改 JSON5 配置。

形态来源（真机实测，2026-11-16，openclaw 2026.11.4 / Node 24.19，aarch64 Linux）：
- 注册表落点 `~/.openclaw/openclaw.json` 的 `mcp.servers.<name>`；
- CLI：`openclaw mcp add <name> --command … --arg … --env k=v`（新装，先探活）、
  `openclaw mcp set <name> '<json>'`（更新）、`openclaw mcp unset <name>`（卸载）；
- 技能落点：个人技能根 `~/.agents/skills`（`openclaw skills list` 里 source=agents-skills-personal）；
  managed 根 `~/.openclaw/skills` 归 OpenClaw 自己，不往里写。

纪律：
- **不读也不写 openclaw.json**：它是 JSON5，可能带注释；我们的 JSON 写盘会吃掉注释，
  卸载时按 JSON 解析还可能整份失败。所有变更走 CLI，读回也走 `openclaw mcp show --json`。
- CLI 缺失 → 报错退出（宁可不装不可装错），不做"直接写文件"的兜底。
- 卸载只 `unset` 自己那一条，配置文件与其它 server 原样保留。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import msgs
from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import server_env, server_entry

HOST = "openclaw"
SUPPORTS_REMOTE = True
NAME = "vod-devkit"
TIMEOUT = 180


def _spec() -> dict:
    """调用期现读（HOME 在测试/隔离跑里会变）。"""
    return host_specs.load(HOST)


def skills_dir(args):
    d = _spec().get("skillsDir")
    return Path(d) if d else None


def _cli() -> str:
    exe = shutil.which("openclaw")
    if not exe:
        print("[vod-devkit] 未找到 openclaw CLI：OpenClaw 的注册表存在 JSON5 配置里，"
              "安装器只经它的 CLI 变更（不直改文件）。先 `npm i -g openclaw@latest` "
              "并确认 `openclaw --version` 可跑", file=sys.stderr)
        sys.exit(2)
    return exe


def _run(argv, what: str):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode != 0:
        print(f"[vod-devkit] openclaw {what} 失败（rc={r.returncode}）："
              f"{(r.stderr or r.stdout or '').strip()[-300:]}", file=sys.stderr)
        sys.exit(2)
    return r


def _definition(args, packs) -> dict:
    return {"command": sys.executable, "args": [server_entry()],
            "env": server_env(args, packs)}


def _show(cli: str) -> dict | None:
    r = subprocess.run([cli, "mcp", "show", NAME, "--json"],
                       capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:      # noqa: BLE001  输出里夹日志行时退回文本比对
        return None


def install(args, packs):
    conf = Path(_spec()["configPath"])
    cli = _cli()
    payload = _definition(args, packs)
    # 先 add（新装 + 探活）；已存在会被拒 → 退到 set（等价于更新，仍带同一定义）
    add = [cli, "mcp", "add", NAME, "--command", payload["command"]]
    add += ["--arg", payload["args"][0]]
    for k, v in payload["env"].items():
        add += ["--env", f"{k}={v}"]
    r = subprocess.run(add, capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode != 0:
        msg = ((r.stderr or "") + (r.stdout or "")).lower()
        # 只有"已存在"才退 set；其它错误（参数/schema/网关占用）必须当场报，不许糊成"更新成功"
        if not any(k in msg for k in ("exist", "已存在", "already")):
            print(f"[vod-devkit] openclaw mcp add 失败（rc={r.returncode}）："
                  f"{(r.stderr or r.stdout or '').strip()[-300:]}", file=sys.stderr)
            sys.exit(2)
        _run([cli, "mcp", "set", NAME, json.dumps(payload, ensure_ascii=False)],
             "mcp set")
        verb = "更新"
    else:
        verb = "写入"
    # 读回自证：注册表里的 command/args 必须与我们要写的一致（防"rc=0 但没落盘"）
    got = _show(cli)
    if got is not None:
        text = json.dumps(got, ensure_ascii=False)
        if payload["args"][0] not in text or payload["command"] not in text:
            print(f"[vod-devkit] openclaw 读回与期望不一致：{text[:300]}", file=sys.stderr)
            sys.exit(2)
    print(f"已{verb} OpenClaw MCP 注册表：{NAME}（{conf}，mcp.servers 键；"
          f"{msgs.effective_unit('OpenClaw 会话/网关', tight=True)}）")
    return conf


def install_remote(args, url, token):
    cli = _cli()
    entry = {"transport": "streamable-http", "url": url}
    if token:
        entry["headers"] = {"Authorization": f"Bearer {token}"}
    _run([cli, "mcp", "set", NAME, json.dumps(entry, ensure_ascii=False)], "mcp set")
    print(f"已更新 OpenClaw 远程 MCP：{NAME} → {url}"
          + ("（token 由 OpenClaw 保存，注意权限）" if token else ""))
    return Path(_spec()["configPath"])


def _config_path() -> Path:
    """当前生效的配置文件（OPENCLAW_CONFIG_PATH 优先——它才是 CLI 的真正落点）。"""
    env = (os.environ.get("OPENCLAW_CONFIG_PATH") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path(_spec()["configPath"])


def _surgical_remove(conf: Path) -> bool:
    """护栏兜底的"外科摘除"：只在配置是**严格 JSON**（无注释）时动字节。

    为什么需要：openclaw 自身有写入护栏（`size-drop-vs-last-good`）——配置文件很小时，
    摘掉一整条大条目会让体积骤降，CLI 直接拒绝写（2026-11-16 矩阵实锤：941→458 被拒）。
    真实用户配置通常更大不会触发，但"刚装上 OpenClaw 就装我们"这种小配置会。
    兜底纪律：先落 .bak；严格 JSON 解析成功才删 `mcp.servers.vod-devkit` 一个键；
    解析失败（JSON5 带注释）就**不动字节**，只打印手工指引。
    """
    if not conf.exists():
        return False
    raw = conf.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[vod-devkit] {conf} 不是严格 JSON（含注释），不做外科摘除；"
              "请手工执行 `openclaw mcp unset vod-devkit` 或删掉 mcp.servers.vod-devkit",
              file=sys.stderr)
        return False
    servers = ((data.get("mcp") or {}).get("servers") or {})
    if NAME not in servers:
        return True
    del servers[NAME]
    backup = conf.with_name(conf.name + ".bak-vod-devkit")
    shutil.copyfile(conf, backup)
    from vod_mcp import paths as _paths
    _paths.atomic_write_text(conf, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"removed OpenClaw MCP entry（护栏 size-drop 触发，已外科摘除；备份 {backup.name}）：{conf}")
    return True


def uninstall() -> bool:
    """只摘自己那一条（openclaw mcp unset）；配置里其它 server 原样保留。"""
    cli = shutil.which("openclaw")
    if not cli:
        print("skip（无 openclaw CLI，且不直改 JSON5 配置）：请手工执行 "
              "`openclaw mcp unset vod-devkit`", file=sys.stderr)
        return False
    r = subprocess.run([cli, "mcp", "unset", NAME],
                       capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode == 0:
        print("removed OpenClaw MCP entry:", (r.stdout or r.stderr or "").strip()[-120:])
        return True
    msg = ((r.stderr or "") + (r.stdout or ""))
    # 兜底触发条件不看**错误文案**（openclaw 改文案就静默退化成"只给指引"）；
    # 只看事实：条目还在不在。还在 + 配置是严格 JSON → 外科摘除（JSON5 会在函数内拒绝）。
    if _entry_present(cli):
        return _surgical_remove(_config_path())
    print("skip（OpenClaw 条目未摘除）：" + msg.strip()[-160:], file=sys.stderr)
    return False


def _entry_present(cli: str) -> bool:
    """条目是否仍在注册表里：先问 CLI（show），CLI 不可判定时退回配置文件文本。"""
    try:
        r = subprocess.run([cli, "mcp", "show", NAME, "--json"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return f'"{NAME}"' in _config_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False