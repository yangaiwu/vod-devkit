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
import shutil
import subprocess
import sys
from pathlib import Path

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
          "重启 OpenClaw 会话/网关生效）")
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


def uninstall() -> bool:
    """只摘自己那一条（openclaw mcp unset）；配置里其它 server 原样保留。"""
    cli = shutil.which("openclaw")
    if not cli:
        print("skip（无 openclaw CLI，且不直改 JSON5 配置）：请手工执行 "
              "`openclaw mcp unset vod-devkit`", file=sys.stderr)
        return False
    r = subprocess.run([cli, "mcp", "unset", NAME],
                       capture_output=True, text=True, timeout=TIMEOUT)
    ok = r.returncode == 0
    print(("removed OpenClaw MCP entry: " if ok else "skip（OpenClaw 条目未摘除）：")
          + (r.stdout or r.stderr or "").strip()[-160:])
    return ok