#!/usr/bin/env python3
"""宿主安装矩阵（E2E）：隔离 HOME 里装 → 断言配置形态 → 拉起 server 自证 → 卸载 → 断言干净。

为什么要这个（对表 huaweicloud-devkit 的 agent-install-harness）：我们此前对宿主
的验证是"分散的单测 + 一台机器手工冒烟"——新加一个宿主时，最常漏的不是解析逻辑，
而是**端到端的那一段**（配置写到哪、宿主读不读得到、卸载会不会带走用户的东西）。
本脚本把 9 个宿主压成一张矩阵，在一次性 HOME 里全流程跑一遍：

1. seed：往每个宿主配置里放"用户自有内容"（别的 server / provider / 其它插件）
2. install：`bin/vod-devkit install --target <host>`（真实安装器，不是直接调适配器）
3. 断言：配置文件的 section/键名正确、启动命令指向载荷 server.py、字节可解析
4. 功能级：按宿主配置里的 command/args 真拉起 stdio，握手 + tools/list +
   调 vod_devkit_info，版本必须等于构建版本（识别级看不懂这类漂移）
5. uninstall：条目消失、插件目录消失、**用户自有内容原样保留**、文件本身没被删

退出码：0=全通过（CLI 缺失的宿主记 SKIP，不算失败）；1=任一 FAIL。

用法：
  python3 scripts/host_matrix.py [--host hermes ...] [--keep] [--verbose]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "vod-devkit"

# host → 期望的配置落点（相对 HOME）与条目路径
EXPECT = {
    "hermes": {"config": ".hermes/mcp/vod-devkit.json", "entry": None},
    "opencode": {"config": ".config/opencode/opencode.json", "entry": ("mcp", "vod-devkit")},
    "codeartsdoer": {"config": ".codeartsdoer/codearts_cli.json", "entry": ("mcp", "vod-devkit")},
    "codeartswork": {"config": ".codeartswork/mcp/mcp_settings.json",
                     "entry": ("mcp", "vod-devkit")},
    "workbuddy": {"config": ".workbuddy/mcp.json", "entry": ("mcpServers", "vod-devkit")},
    "atomcode": {"config": ".atomcode/mcp.json", "entry": ("mcpServers", "vod-devkit")},
    "codex-desktop": {"config": ".agents/plugins/marketplace.json", "entry": ("plugins", None)},
    "codex": {"cli": "codex", "config": None, "entry": None},
    "dsh": {"cli": "dsh", "profile": "web", "config": None, "entry": None},
}

# 卸载后必须仍然存在的用户内容：host → (文件, 断言函数)
SEED = {
    "opencode": {".config/opencode/opencode.json": {"mcp": {"user-own": {"command": ["x"]}},
                                                   "provider": {"model": "m1"}}},
    "codeartsdoer": {".codeartsdoer/codearts_cli.json": {"mcp": {"user-own": {"type": "local"}},
                                                          "provider": {"model": "m2"}}},
    "codeartswork": {".codeartswork/mcp/mcp_settings.json": {"mcp": {"user-own": {"command": ["z"]}},
                                                             "provider": {"model": "m1"}}},
    "workbuddy": {".workbuddy/mcp.json": {"mcpServers": {"user-own": {"command": "x"}},
                                          "theme": "dark"}},
    "atomcode": {".atomcode/mcp.json": {"mcpServers": {"user-own": {"command": "y"}}}},
    "codex-desktop": {".agents/plugins/marketplace.json": {"name": "personal", "plugins": [
        {"name": "other-tool", "source": {"source": "local", "path": "./plugins/other"}}]}},
}


def _dig(data, entry):
    if entry is None:
        return data
    cur = data
    for key in entry:
        if key is None:
            return cur
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _seed(home: Path, host: str) -> None:
    for rel, payload in SEED.get(host, {}).items():
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_install(env, host, extra=()):
    r = subprocess.run([sys.executable, str(BIN), "install", "--target", host, *extra],
                       capture_output=True, text=True, env=env, timeout=300)
    return r


def _probe(entry: dict, expect_version: str) -> tuple:
    """按宿主配置真拉起 server：initialize → tools/list → vod_devkit_info。"""
    cmd = entry.get("command")
    args = entry.get("args") or []
    if isinstance(cmd, list):  # codearts 形态：command 是数组
        cmd, args = cmd[0], cmd[1:]
    if not cmd:
        return False, "配置里没有启动命令"
    env = os.environ.copy()
    env.update({k: str(v) for k, v in (entry.get("env") or entry.get("environment") or {}).items()})
    proc = subprocess.Popen([cmd, *[str(a) for a in args]], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=env, text=True)
    assert proc.stdin is not None and proc.stdout is not None

    def rpc(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server 无响应（启动命令/解释器不对？）")
        return json.loads(line)

    try:
        rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18",
                        "clientInfo": {"name": "host_matrix", "version": "1"},
                        "capabilities": {}}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0",
                                     "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [t.get("name") for t in (tools.get("result") or {}).get("tools") or []]
        info = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "vod_devkit_info", "arguments": {}}})
        node = (info.get("result") or {}).get("structuredContent") or {}
        if not node and (info.get("result") or {}).get("content"):
            node = json.loads(info["result"]["content"][0]["text"])
        ver = str(node.get("version") or "")
        if expect_version and ver != expect_version:
            return False, f"探针版本 {ver} ≠ 构建 {expect_version}（指向旧副本）"
        if "vod_submit_voices" not in names:
            return False, f"工具面缺 vod_submit_voices（{len(names)} 个工具）"
        return True, f"{len(names)} 工具，版本 {ver}"
    except Exception as e:  # noqa: BLE001
        return False, f"{e.__class__.__name__}: {e}"
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def run_host(host: str, home: Path, expect_version: str, verbose=False) -> tuple:
    spec = EXPECT[host]
    if spec.get("cli") and not shutil.which(spec["cli"]):
        return "SKIP", f"宿主 CLI {spec['cli']} 不在 PATH（自托管 runner 上才有）"
    _seed(home, host)
    if host in ("codex", "codex-desktop"):
        (home / ".codex").mkdir(parents=True, exist_ok=True)  # CODEX_HOME 必须已存在
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        # codex CLI 用 CODEX_HOME 解析自己的家目录（libc 的 home 而不是 $HOME）——
        # 不设它，隔离矩阵里的 codex 会写到真实 ~/.codex（本轮实锤：0.4.2 旧缓存）。
        **({"CODEX_HOME": str(home / ".codex")} if host in ("codex", "codex-desktop") else {}),
        **({"DSH_HOME": str(home / ".dsh")} if host == "dsh" else {}),
        "VOD_DEVKIT_MANIFEST": str(home / "install-manifest.json"),
        "VOD_JAVA_API_BASE": "http://127.0.0.1:9/stub",
        "VOD_PACKS": "core",
        # 矩阵在真实仓里跑：不许把仓内 build-info 重烧成当前 HEAD（否则结构门禁
        # "根/包内 build-info 一致"会在下一次提交时假红）
        "VOD_DEVKIT_NO_BUILD_INFO": "1",
    })
    env.pop("VOD_JAVA_API_KEY", None)
    extra = ["--profile", spec["profile"]] if spec.get("profile") else []
    r = _run_install(env, host, extra)
    if r.returncode != 0:
        return "FAIL", f"install 退出 {r.returncode}: {(r.stderr or r.stdout).strip()[-200:]}"

    conf = home / spec["config"] if spec.get("config") else None
    entry = None
    if conf is not None:
        if not conf.exists():
            return "FAIL", f"配置未落盘：{conf.relative_to(home)}"
        try:
            data = json.loads(conf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return "FAIL", f"配置不是合法 JSON：{e}"
        entry = _dig(data, spec["entry"])
        if spec["entry"] and not entry:
            return "FAIL", f"缺条目 {'.'.join(str(x) for x in spec['entry'] if x)}"
        if host == "codex-desktop":
            names = [p.get("name") for p in (data.get("plugins") or [])]
            if "vod-devkit" not in names:
                return "FAIL", "marketplace 未登记 vod-devkit"
            mcp = home / "plugins" / "vod-devkit" / ".mcp.json"
            if not mcp.exists():
                return "FAIL", "插件目录缺 .mcp.json"
            entry = (json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}
                     ).get("vod-devkit")
        if host == "hermes":
            entry = data
    if host == "codex":
        cache = home / ".codex" / "plugins" / "cache"
        found = sorted(cache.glob("*/*/*/.mcp.json")) if cache.exists() else []
        if not found:
            return "FAIL", "codex 插件缓存里没有 .mcp.json（原生插件未落盘）"
        entry = (json.loads(found[-1].read_text(encoding="utf-8")).get("mcpServers") or {}
                 ).get("vod-devkit")
    if host == "dsh":
        patch_file = home / ".dsh" / "profiles" / spec["profile"] / "cordis.patch.yml"
        if not patch_file.exists() or "- id: vod-devkit" not in patch_file.read_text(
                encoding="utf-8", errors="replace"):
            return "FAIL", "dsh profile patch 里没有 vod-devkit 块"
        mf = json.loads((home / "install-manifest.json").read_text(encoding="utf-8"))
        row = [r for r in (mf.get("installs") or [mf]) if r.get("target") == "dsh"][0]
        entry = {"command": sys.executable,
                 "args": [str(Path(row["payloadDir"]) / "vod_mcp" / "server.py")]}
    ok, msg = _probe(entry or {}, expect_version)

    u = subprocess.run([sys.executable, str(BIN), "uninstall"], capture_output=True,
                       text=True, env=env, timeout=300)
    if u.returncode != 0:
        return "FAIL", f"uninstall 退出 {u.returncode}（功能级：{msg}）"
    if conf is not None and conf.exists():
        data = json.loads(conf.read_text(encoding="utf-8"))
        if host == "codex-desktop":
            if "vod-devkit" in [p.get("name") for p in (data.get("plugins") or [])]:
                return "FAIL", "卸载后 marketplace 仍登记 vod-devkit"
        elif spec["entry"] and _dig(data, spec["entry"]):
            return "FAIL", "卸载后条目仍在"
        for rel, payload in SEED.get(host, {}).items():
            if (home / rel).exists():
                left = json.loads((home / rel).read_text(encoding="utf-8"))
                for key, val in payload.items():
                    if key in ("mcp", "mcpServers"):
                        for name, entry_val in val.items():
                            if left.get(key, {}).get(name) != entry_val:
                                return "FAIL", f"卸载破坏了用户条目 {key}.{name}"
                    elif left.get(key) != val:
                        return "FAIL", f"卸载破坏了用户键 {key}"
            else:
                return "FAIL", f"卸载删掉了用户配置文件 {rel}"
    if host == "codex-desktop" and (home / "plugins" / "vod-devkit").exists():
        return "FAIL", "卸载后插件目录仍在"
    if host == "codex":
        cache = home / ".codex" / "plugins" / "cache"
        if cache.exists() and list(cache.glob("*/*/*/.mcp.json")):
            return "FAIL", "卸载后 codex 插件缓存仍在"
    if host == "dsh":
        patch_file = home / ".dsh" / "profiles" / spec["profile"] / "cordis.patch.yml"
        if patch_file.exists() and "- id: vod-devkit" in patch_file.read_text(
                encoding="utf-8", errors="replace"):
            return "FAIL", "卸载后 dsh patch 块仍在"
    return ("PASS", msg) if ok else ("FAIL", msg)


def audit_host(host: str, expect_version: str) -> tuple:
    """只读巡检**真实机器**上的安装（不写任何文件）：条目在不在、入口存不存在、
    自证版本是否等于构建版本。返回 PASS / DRIFT / NOT_INSTALLED。

    动机（2026-11-12 实锤）：矩阵全绿不代表这台机器的安装是新的——巡检当场发现
    opencode 指向仓内路径而非载荷、codex 停在 0.5.3、dsh 壳还钉着 0.4.4。
    """
    home = Path.home()
    spec = EXPECT[host]
    conf = home / spec["config"] if spec.get("config") else None
    entry = None
    if conf is not None:
        if not conf.exists():
            return "NOT_INSTALLED", f"缺配置 {conf}"
        try:
            data = json.loads(conf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return "DRIFT", f"配置不是合法 JSON：{e}"
        if host == "codex-desktop":
            if "vod-devkit" not in [p.get("name") for p in (data.get("plugins") or [])]:
                return "DRIFT", "marketplace 未登记 vod-devkit"
            mcp = home / "plugins" / "vod-devkit" / ".mcp.json"
            if not mcp.exists():
                return "DRIFT", "插件目录缺 .mcp.json"
            entry = (json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}
                     ).get("vod-devkit")
        else:
            entry = data if host == "hermes" else _dig(data, spec["entry"])
            if spec["entry"] and not entry:
                return "DRIFT", f"缺条目 {'.'.join(str(x) for x in spec['entry'] if x)}"
    if host == "codex":
        cache = home / ".codex" / "plugins" / "cache"
        found = sorted(cache.glob("*/*/*/.mcp.json")) if cache.exists() else []
        if not found:
            return "NOT_INSTALLED", "codex 插件缓存里没有 .mcp.json"
        entry = (json.loads(found[-1].read_text(encoding="utf-8")).get("mcpServers") or {}
                 ).get("vod-devkit")
    if host == "dsh":
        patches = sorted((home / ".dsh" / "profiles").glob("*/cordis.patch.yml"))
        hit = [p for p in patches
               if "- id: vod-devkit" in p.read_text(encoding="utf-8", errors="replace")]
        if not hit:
            return "NOT_INSTALLED", "dsh profile patch 里没有 vod-devkit 块"
        cmd = entry or {}
        ok, msg = _probe(cmd, expect_version) if cmd else (True, "patch 存在（壳自证跳过）")
        return ("PASS" if ok else "DRIFT"), msg
    if not entry:
        return "NOT_INSTALLED", "无条目"
    ok, msg = _probe(entry, expect_version)
    return ("PASS" if ok else "DRIFT"), msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", default=[])
    ap.add_argument("--keep", action="store_true", help="保留隔离 HOME（排查用）")
    ap.add_argument("--audit", action="store_true",
                    help="只读巡检真实机器上的安装（不装/不卸/不写）")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    build = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8"))
    version = str(build.get("version"))
    hosts = a.host or list(EXPECT)
    tmp = Path(tempfile.mkdtemp(prefix="vod-matrix-"))
    home = tmp / "home"
    home.mkdir()
    results = {}
    if a.audit:
        for h in hosts:
            state, msg = audit_host(h, version)
            results[h] = state
            print(f"[{h}] {state}: {msg}")
        drift = [h for h, s in results.items() if s == "DRIFT"]
        missing = [h for h, s in results.items() if s == "NOT_INSTALLED"]
        print(f"\n巡检：{len(results) - len(drift) - len(missing)} PASS / {len(drift)} DRIFT / "
              f"{len(missing)} NOT_INSTALLED（构建 {version}）")
        if drift:
            print("DRIFT：" + "、".join(drift) + " → 重跑 install --target <host>")
        sys.exit(1 if drift else 0)
    try:
        for h in hosts:
            state, msg = run_host(h, home, version, a.verbose)
            results[h] = state
            print(f"[{h}] {state}: {msg}")
            if state == "FAIL" and a.verbose:
                print("  （隔离 HOME 保留：", tmp, "）")
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    bad = [h for h, s in results.items() if s == "FAIL"]
    skipped = [h for h, s in results.items() if s == "SKIP"]
    print(f"\n矩阵：{len(results) - len(bad) - len(skipped)} PASS / {len(bad)} FAIL / "
          f"{len(skipped)} SKIP（构建 {version}）")
    if skipped:
        print("SKIP：" + "、".join(skipped))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()