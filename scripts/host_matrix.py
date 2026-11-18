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
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path as _Path

# 入口显式设根（D-structure-1 S3）：脚本不再依赖"从哪跑"，包在 src/
# 注意：**不在 import 期写 os.environ**——本文件会被 tests/test_host_matrix.py 当模块加载，
# import 期 setenv 会把外层仓的根泄漏进整场 pytest，让"造临时仓再跑安装器"的用例
# 打到真实仓（实测 2026-11-16：test_host_matrix + test_installer 同跑 16 条 FileNotFound）。
_DIST = _Path(__file__).resolve().parent.parent
_SRC = _DIST / "src" if (_DIST / "src" / "vod_mcp").is_dir() else _DIST
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _pin_roots() -> None:
    """进程入口处显式钉两个根（main() 调；import 不调）。

    🔴 必须**强制覆盖**而不是 setdefault（2026-11-18 实测假 PASS）：
    外部 shell/CI 若已导出 `VOD_DEVKIT_*_ROOT`（如上次会话遗留、或用户在别的仓里
    export 过），setdefault 会保留那个外部值 → 巡检探的是**别的树**，报 10 PASS
    而实际本仓根本没被检查。现在覆盖并显式告警，让「被谁改了」可见。
    """
    for key, val in (("VOD_DEVKIT_SRC_ROOT", _SRC), ("VOD_DEVKIT_DIST_ROOT", _DIST)):
        prev = os.environ.get(key)
        if prev and prev != str(val):
            print(f"[warn] env {key}={prev} 被覆盖为本仓 {val}（否则巡检会探错树）",
                  file=sys.stderr)
        os.environ[key] = str(val)


from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "vod-devkit"

# host → 期望的配置落点（相对 HOME）与条目路径
EXPECT = {
    # cli 缺省会跳过 CLI 探测 → CI（无 hermes）上会真跑 install 并在裸 exec 处炸；
    # 实测 2026-11-15：这就是 GitHub CI host-matrix 的失败根因。
    "hermes": {"cli": "hermes", "config": ".hermes/mcp/vod-devkit.json", "entry": None},
    "opencode": {"config": ".config/opencode/opencode.json", "entry": ("mcp", "vod-devkit")},
    "codeartsdoer": {"config": ".codeartsdoer/codearts_cli.json", "entry": ("mcp", "vod-devkit")},
    "codeartswork": {"config": ".codeartswork/mcp/mcp_settings.json",
                     "entry": ("mcp", "vod-devkit")},
    "workbuddy": {"config": ".workbuddy/mcp.json", "entry": ("mcpServers", "vod-devkit")},
    "atomcode": {"config": ".atomcode/mcp.json", "entry": ("mcpServers", "vod-devkit")},
    "codex-desktop": {"config": ".agents/plugins/marketplace.json", "entry": ("plugins", None)},
    "codex": {"cli": "codex", "config": None, "entry": None},
    "dsh": {"cli": "dsh", "profile": "web", "config": None, "entry": None},
    # openclaw：注册表在 JSON5 配置里，读侧只信它的 CLI（probe --json）；矩阵里验的是
    # CLI 写出来的那份（CLI 输出合法 JSON），注意真实文件可能带注释。
    "openclaw": {"cli": "openclaw", "config": ".openclaw/openclaw.json",
                 "entry": ("mcp", "servers", "vod-devkit")},
    # officeace：桌面端（Windows-only），本机/no对象 → 显式 SKIP（不做假覆盖）
    "officeace": {"cli": "", "config": None, "entry": None,
                  "skip": "桌面端（Windows 10/11、macOS 13+、HarmonyOS），本机 Linux 无安装对象"},
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


def _isolated_env(host: str, home: Path) -> dict:
    """隔离 HOME 的运行 env：**每个宿主自己的"家"都要一起搬**。

    只用 $HOME 不够——各宿主 CLI 有自己的家目录变量，认它们不认 $HOME：
    · hermes → HERMES_HOME（实测 2026-11-16：`HOME=/tmp/x hermes profile list` 照样列出
      真实 profile；矩阵因此把真实 ~/.hermes/config.yaml 改成了
      `<scratch>/home/.vod-devkit/payloads/…` + 桩地址 127.0.0.1:9/stub，scratch 一清就永久掉线）；
    · codex → CODEX_HOME（libc 的 home，不是 $HOME，实测 0.4.2 旧缓存）；
    · dsh → DSH_HOME。
    新增宿主时先确认它用哪个变量，别假设 $HOME 生效。
    """
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        # codex CLI 用 CODEX_HOME 解析自己的家目录（libc 的 home 而不是 $HOME）——
        # 不设它，隔离矩阵里的 codex 会写到真实 ~/.codex（本轮实锤：0.4.2 旧缓存）。
        **({"CODEX_HOME": str(home / ".codex")} if host in ("codex", "codex-desktop") else {}),
        **({"DSH_HOME": str(home / ".dsh")} if host == "dsh" else {}),
        # hermes CLI 认 HERMES_HOME（不认 HOME）：不搬它，隔离 HOME 里装 hermes 等于
        # 直接改真机配置（2026-11-16 实锤，见 docstring）
        **({"HERMES_HOME": str(home / ".hermes")} if host == "hermes" else {}),
        # openclaw 认 OPENCLAW_CONFIG_PATH / OPENCLAW_STATE_DIR（官方 gateway/index.md）
        **({"OPENCLAW_CONFIG_PATH": str(home / ".openclaw" / "openclaw.json"),
           "OPENCLAW_STATE_DIR": str(home / ".openclaw")} if host == "openclaw" else {}),
        "VOD_DEVKIT_MANIFEST": str(home / "install-manifest.json"),
        "VOD_JAVA_API_BASE": "http://127.0.0.1:9/stub",
        "VOD_PACKS": "core",
        # 矩阵在真实仓里跑：不许把仓内 build-info 重烧成当前 HEAD（否则结构门禁
        # "根/包内 build-info 一致"会在下一次提交时假红）
        "VOD_DEVKIT_NO_BUILD_INFO": "1",
    })
    # 真实 profile / 宿主身份不能带进隔离矩阵（否则 CLI 仍按真实 profile 解析）
    for k in ("HERMES_PROFILE", "HERMES_CONFIG"):
        env.pop(k, None)
    env.pop("VOD_JAVA_API_KEY", None)
    if host == "hermes":
        # 光搬 HERMES_HOME 还不够：hermes CLI 在一个**空的** HERMES_HOME 下会尝试
        # 自举依赖（实测一次 install 卡到 300s 超时，全量矩阵因此整轮 FAIL）。
        # 这里放一个"立刻失败"的 shim 挡住 CLI 段：适配器本来就是 best-effort
        # （rc!=0 → 打印提示并继续），矩阵要验的是安装器写出的条目 + 载荷自证。
        env["PATH"] = _sandbox_host_cli(home, "hermes") + os.pathsep + env.get("PATH", "")
    return env


def _sandbox_host_cli(home: Path, name: str) -> str:
    """在隔离 HOME 里造一个同名 shim 目录（CLI 立刻失败，不碰真机、也不挂住）。"""
    d = home / "bin"
    d.mkdir(parents=True, exist_ok=True)
    shim = d / name
    if not shim.exists():
        shim.write_text("#!/bin/sh\necho 'matrix: host CLI disabled in sandbox' >&2\nexit 1\n",
                        encoding="utf-8")
        shim.chmod(0o755)
    return str(d)


def _run_install(env, host, extra=()):
    # 巡检是"装载面"验收，不是归因验收：产品名在装机时已验过，这里跳过产品校验。
    # 不跳的话每次巡检 = 9 次隔离装 = 9 枚匿名令牌签发，直接把引擎限流打满
    #（真机实锤 100/日、60/小时两档，整批装机被挡）。
    e = {**env, "VOD_SKIP_PRODUCT_CHECK": "1", "VOD_MATRIX": "1"}
    r = subprocess.run([sys.executable, str(BIN), "install", "--target", host, *extra],
                       capture_output=True, text=True, env=e, timeout=300)
    return r


# 账本里"该版本允许的 commitSha"（S210）：由 audit 入口从 manifest 填一次，_probe 只读。
_EXPECT_SHAS: dict = {}


def _payload_version(argv: list):
    """entry 指向的载荷目录里的 build-info 版本（载荷自证，不看 server 自述）。

    适用面：入口形态是 `…/<载荷>/vod_mcp/server.py` 的**文件型**（本仓九宿主目前全是这种）。
    将来若出现 `-m vod_mcp.server` 或纯远程 URL 形态，本函数返回 None —— 此时调用方必须把
    "无载荷文件判据，仅 server 自述"显式写进报文，不许静默退回自述（否定式证据也要可审计）。
    """
    for a in argv:
        if str(a).endswith("vod_mcp/server.py"):
            bi = Path(str(a)).parent.parent / "build-info.json"
            if bi.is_file():
                try:
                    return json.loads(bi.read_text(encoding="utf-8")).get("version")
                except (OSError, ValueError):
                    return None
    return None


def _payload_provenance(argv: list) -> dict:
    """entry 指向的载荷目录的 build-info（版本 + commitSha）。判据同 _payload_version 的适用面。"""
    for a in argv:
        if str(a).endswith("vod_mcp/server.py"):
            bi = Path(str(a)).parent.parent / "build-info.json"
            if bi.is_file():
                try:
                    d = json.loads(bi.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return {}
                return {"version": d.get("version"), "commitSha": d.get("commitSha")}
    return {}


def _payload_drift(argv: list, expect_version: str,
                   expect_shas=None) -> tuple:
    """载荷自证是否漂移（S210）：**版号相等不算对账**——同版本号换内容必须 DRIFT。

    事故：用仓内入口 install 把 payloads/0.5.32 就地重打成含未发版提交的内容，版号仍是 0.5.32，
    而 npm 上的 0.5.32 是另一个提交；巡检只比 version 字符串 → 照旧 10 PASS，对账面全错。
    `expect_shas` = 账本里该版本允许的 commitSha 集合（None=不判；空集=不判）。
    """
    prov = _payload_provenance(argv)
    if not prov:
        return True, ""                       # 无文件判据：调用方另行标注，不在这里假装通过
    ver, sha = prov.get("version"), prov.get("commitSha")
    if expect_version and ver and ver != expect_version:
        return False, f"载荷版本 {ver} ≠ 期望 {expect_version}"
    shas = expect_shas or set()
    if sha and shas and sha not in shas:
        return False, (f"载荷内容与账本不一致（同版号 {ver}，载荷 commitSha {str(sha)[:12]} ≠ 账本 "
                       f"{'/'.join(sorted({str(x)[:12] for x in shas}))}）——版本号相同不代表代码相同")
    return True, ""


def _probe(entry: dict, expect_version: str) -> tuple:
    """按宿主配置真拉起 server：initialize → tools/list → vod_devkit_info。

    失败必须**带上命令/入口路径**：巡检对 8 个宿主同时报"server 无响应"时，
    看不出是载荷目录没了还是 command 写错（2026-11-16 实锤：8 条 DRIFT 全同一句话，
    真正的原因是 payloads/0.5.9 被测试删了）。也包一层兜底 try：巡检崩掉不如报挂。
    """
    cmd = entry.get("command")
    args = entry.get("args") or []
    if isinstance(cmd, list):  # codearts 形态：command 是数组
        cmd, args = cmd[0], cmd[1:]
    if not cmd:
        return False, "配置里没有启动命令"
    argv = [str(cmd), *[str(a) for a in args]]
    tail = "（argv=" + " ".join(argv[:2]) + (" …" if len(argv) > 2 else "") + "）"
    gone = [a for a in argv[1:] if a.endswith(".py") and not os.path.exists(a)]
    if gone:
        return False, f"入口文件不存在：{gone[0]}{tail}"
    # 载荷自证（第二判据，比 server 自述更硬）：entry 指向的载荷目录里 build-info.json
    # 的版本必须就是期望版本。server 自述会被 env（VOD_DEVKIT_DIST_ROOT）影响而读成
    # 仓根版本，文件版本不会——这是"巡检假绿"暴露后补的独立证据。
    pv = _payload_version(argv)
    no_file_evidence = "" if pv else "（无载荷文件判据：入口非 …/vod_mcp/server.py 形态，仅 server 自述）"
    ok_drift, drift_msg = _payload_drift(argv, expect_version, _EXPECT_SHAS.get(str(expect_version)))
    if not ok_drift:
        return False, f"{drift_msg}{tail}"
    env = os.environ.copy()
    entry_env = {k: str(v) for k, v in (entry.get("env") or entry.get("environment") or {}).items()}
    # 巡检子进程必须让"被装的那份载荷"自证，不能继承本进程为跑 CLI 钉的根：
    # VOD_DEVKIT_DIST_ROOT 会让载荷 server 的 provenance 去读**仓根** build-info.json，
    # 于是 0.5.11 的载荷被报成 0.5.14（真机实锤：干净 env 自述 0.5.11，带仓根 0.5.14）。
    # 这正是"巡检假绿"的地基：不 pop 掉，矩阵永远发现不了载荷落后。
    for _k in ("VOD_DEVKIT_SRC_ROOT", "VOD_DEVKIT_DIST_ROOT", "VOD_DEVKIT_ROOT"):
        if _k not in entry_env:
            env.pop(_k, None)
    env.update(entry_env)
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=env, text=True)
    except OSError as e:
        return False, f"起不来（{e.__class__.__name__}: {e}）{tail}"
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
        return True, f"{len(names)} 工具，版本 {ver}{no_file_evidence}"
    except Exception as e:  # noqa: BLE001
        return False, f"{e.__class__.__name__}: {e}{tail}"
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def run_host(host: str, home: Path, expect_version: str, verbose=False) -> tuple:
    spec = EXPECT[host]
    if spec.get("skip"):
        return "SKIP", str(spec["skip"])
    if spec.get("cli") and not shutil.which(spec["cli"]):
        return "SKIP", f"宿主 CLI {spec['cli']} 不在 PATH（自托管 runner 上才有）"
    _seed(home, host)
    if host in ("codex", "codex-desktop"):
        (home / ".codex").mkdir(parents=True, exist_ok=True)  # CODEX_HOME 必须已存在
    env = _isolated_env(host, home)
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


def _parse_hermes_entry(text: str) -> dict | None:
    """从 hermes 的 config.yaml 里取 mcp_servers.vod-devkit（零依赖窄解析）。

    为什么不 import yaml：这个脚本是 CI 门禁，PyYAML 不在依赖里——缺包时假红/假绿
    都比报错难查。只认 `hermes config set` 写出来的块形态；解析不出返回 None，
    由调用方报 DRIFT（宁可报挂，不许静默跳过）。
    """
    lines = text.splitlines()
    sec = next((i for i, ln in enumerate(lines) if ln.rstrip() == "mcp_servers:"), None)
    if sec is None:
        return None
    entry: dict = {}
    base = None          # vod-devkit 键的缩进
    kind = None          # 当前子块：command / args / env
    for ln in lines[sec + 1:]:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent == 0:
            break                                   # 回到顶层键，段结束
        stripped = ln.strip()
        if base is None:
            if stripped == "vod-devkit:":
                base = indent
            continue
        if indent <= base and stripped != "vod-devkit:":
            break                                   # 下一个 server
        child = base + 2
        if indent == child:
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            kind = key
            if val:
                entry[key] = val.strip("'\"")
            elif key == "args":
                entry["args"] = []
            elif key == "env":
                entry["env"] = {}
        elif indent > child:
            if kind == "args" and stripped.startswith("- "):
                entry.setdefault("args", []).append(stripped[2:].strip().strip("'\""))
            elif kind == "env" and ":" in stripped:
                k, _, v = stripped.partition(":")
                entry.setdefault("env", {})[k.strip()] = v.strip().strip("'\"")
    return entry or None


def _hermes_effective_entry(home: Path) -> tuple[dict | None, str]:
    """hermes 实际生效的 MCP 条目 + 一句判据说明（找不出就返回原因）。"""
    p = home / ".hermes" / "config.yaml"
    if not p.exists():
        return None, f"缺 {p}（hermes 的生效入口）"
    try:
        entry = _parse_hermes_entry(p.read_text(encoding="utf-8", errors="replace"))
    except OSError as e:
        return None, f"读不出 {p}: {e}"
    if not entry:
        return None, f"{p} 的 mcp_servers 里没有 vod-devkit（生效入口无条目）"
    if entry.get("enabled") in ("false", False):
        return None, f"{p} 的 mcp_servers.vod-devkit 是 enabled: false"
    return entry, f"生效入口 {p}"


def _codex_enabled_marketplaces(home: Path) -> list:
    """codex config.toml 里 vod-devkit 的启用市场（[plugins."vod-devkit@<mkt>"]）。"""
    cfg = home / ".codex" / "config.toml"
    if not cfg.exists():
        return []
    try:
        import tomllib
        data = tomllib.loads(cfg.read_text(encoding="utf-8", errors="replace"))
        plugins = data.get("plugins") or {}
        out = [k.split("@", 1)[1] for k, v in plugins.items()
               if "@" in k and k.split("@", 1)[0] == "vod-devkit"
               and not (isinstance(v, dict) and v.get("enabled") is False)]
        return out
    except Exception:                                  # noqa: BLE001 3.10 无 tomllib
        import re as _re
        return _re.findall(r'\[plugins\."vod-devkit@([^"]+)"\]', cfg.read_text(
            encoding="utf-8", errors="replace"))


def _codex_effective_mcp(home: Path) -> tuple:
    """codex 实际会用的那份 .mcp.json → (市场名, 路径 | None, 是否靠猜)。

    "猜"=config.toml 没有声明启用市场、marketplace.json 也没 name，只能按"存在的那份"判；
    报文里必须标出来，否则事后审计会以为那个市场名是宿主说的。
    """
    markets = _codex_enabled_marketplaces(home)
    if not markets:
        mp = home / ".agents" / "plugins" / "marketplace.json"
        if mp.exists():
            try:
                markets = [json.loads(mp.read_text(encoding="utf-8")).get("name") or "personal"]
            except json.JSONDecodeError:
                markets = []
    cache = home / ".codex" / "plugins" / "cache"
    for mkt in markets or ["personal"]:
        hits = sorted(cache.glob(f"{mkt}/vod-devkit/*/.mcp.json"))
        if hits:
            return mkt, hits[-1], False
    # 配置里没启用任何市场：退回"存在的那份"（能让巡检报 DRIFT 而不是 NOT_INSTALLED）
    found = sorted(cache.glob("*/*/*/.mcp.json")) if cache.exists() else []
    if found:
        return found[-1].parts[-4], found[-1], True
    return (markets[0] if markets else None), None, False


def _raw_manifest(home: Path) -> dict:
    """安装期账本原文（候选顺序：VOD_DEVKIT_MANIFEST → 安装根(ROOT) → home）。读不到返回 {}。

    真机实测（2026-11-16）：manifest 落在仓根（common.manifest_path()），只读 home/…
    会返回 {}，判据静默失效（真机假绿，隔离用例却因设了 env 而绿）。
    显式指定 env 时**只认它**：文件不在 = 没有账本；回退 ROOT 会让隔离测试读到真机账本。
    """
    env_p = os.environ.get("VOD_DEVKIT_MANIFEST")
    if env_p:
        cands = [Path(env_p)]
    else:
        cands = [ROOT / "install-manifest.json", home / "install-manifest.json"]
    for p in cands:
        if p.is_file():
            break
    else:
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def _dsh_manifest_mcp(home: Path) -> dict:
    """manifest 里每个 dsh profile 的安装期 mcpClient（S153-4）。

    为什么必须读：宿主"本来就没 mcp-client"（合法降级 6 工具）与"MCP 块被清掉"
    （12→6 退化）在 patch 文本上长得一模一样；只有安装期记录能区分。
    """
    out = {}
    for r in (_raw_manifest(home).get("installs") or []):
        if r.get("target") != "dsh":
            continue
        out[r.get("dshProfile") or ""] = (r.get("dshPatch") or {}).get("mcpClient")
    return out


def _audit_dsh_profile(patch: Path, entry: dict, expect_version: str,
                       want_mcp: bool | None = None) -> tuple:
    """单个 dsh profile 的巡检（S153-3）。判据与原实现一致，只是按 profile 隔离。"""
    text = patch.read_text(encoding="utf-8", errors="replace")
    mcp_mode = "- id: vod-devkit-mcp" in text
    shell_off = "registerTools: false" in text
    shell_ver = ""
    pkg = patch.parent / "node_modules" / "dsh-vod-devkit" / "package.json"
    if pkg.exists():
        try:
            shell_ver = json.loads(pkg.read_text(encoding="utf-8")).get("version") or ""
        except Exception:      # noqa: BLE001  坏包按未知处理，不掩盖 patch 事实
            shell_ver = ""
    if mcp_mode:
        if not shell_off:
            return "DRIFT", "有 mcp-client 块但壳仍注册工具（registerTools 未写 false）→ 双 submit"
        if not pkg.exists():
            return "DRIFT", "MCP 模式但 profile 里没装 dsh-vod-devkit（dsh plugin add 未生效）"
        if expect_version and shell_ver and shell_ver != expect_version:
            return "DRIFT", (f"MCP 模式，但 profile 里壳 {shell_ver} ≠ 期望 {expect_version}"
                             "（dsh plugin add 未钉版本，升级装的是旧壳）")
        return "PASS", f"MCP 模式（工具面 mcp__vod-devkit__*，壳只留 UI，壳 {shell_ver or '未知'}）"
    if want_mcp:
        # S153-4：安装期记录说这台机器有 mcp-client，patch 里却没有 mcp 块——这正是
        # decisions 里记的事故形态（MCP 模式 PASS 静默退化成"降级 PASS"，12→6 工具）。
        return "DRIFT", ("MCP 块被清（安装期记录有 mcp-client，patch 里没有 "
                         "- id: vod-devkit-mcp）→ 工具面 12→6，重跑 install 恢复")
    ok, msg = _probe(entry, expect_version) if entry else (True, "降级：壳自注册（patch 存在）")
    return (("PASS" if ok else "DRIFT"),
            msg + "；降级形态：壳自注册 6 工具（无 mcp-client，按配置面判）")


def _audit_openclaw(home: Path, expect_version: str) -> tuple:
    """OpenClaw：只读巡检走它自己的注册表（mcp probe --json），不解析 JSON5 配置。

    为什么不用"读 openclaw.json 找 mcp.servers"：该文件是 JSON5（可能带注释），
    json.loads 会整份失败；而且用户可能用 `openclaw --profile` 另存一份状态。
    probe 的输出里带 launch（真实 command+args），直接拿它拉一次 server 自证版本。
    """
    entry, why = _openclaw_entry(home)
    if entry is None:
        return ("NOT_INSTALLED" if why.startswith("无 openclaw") or "没有 vod-devkit" in why
                else "DRIFT"), why
    row = next((r for r in (_raw_manifest(home).get("installs") or [])
                if r.get("target") == "openclaw"), {})
    ok, msg = _probe(entry, expect_version)
    if ok and not row:
        return "DRIFT", ("注册表里有条目但**账本缺 openclaw 行**（装了没入账：uninstall 摘不到、"
                         "prune 的在用集合靠配置面兜底）——重跑 install --target openclaw")
    label = "openclaw 注册表" + ("" if row else "，账本未记")
    return ("PASS" if ok else "DRIFT"), f"{msg}（{label}）"


def _openclaw_entry(home: Path | None = None) -> tuple:
    """OpenClaw 的 launch 只信它自己的注册表（JSON5 配置不可直接解析）。"""
    home = Path.home() if home is None else home
    cli = shutil.which("openclaw")
    if not cli:
        return None, "无 openclaw CLI"
    try:
        r = subprocess.run([cli, "mcp", "probe", "vod-devkit", "--json"],
                           capture_output=True, text=True, timeout=90)
    except Exception as e:                      # noqa: BLE001
        return None, f"probe 失败：{e}"
    if r.returncode != 0:
        return None, "注册表里没有 vod-devkit"
    raw = r.stdout or ""
    try:
        data = json.loads(raw[raw.find("{"):])
    except Exception:                           # noqa: BLE001
        return None, "probe 输出不是 JSON"
    launch = str(((data.get("servers") or {}).get("vod-devkit") or {}).get("launch") or "")
    if not launch:
        return None, "probe 未给出 launch"
    parts = shlex.split(launch)
    entry = {"command": parts[0], "args": parts[1:]}
    row = next((x for x in (_raw_manifest(home).get("installs") or [])
                if x.get("target") == "openclaw"), {})
    env = {}
    if row.get("packs"):
        env["VOD_PACKS"] = str(row["packs"])
    if row.get("apiBase"):
        env["VOD_JAVA_API_BASE"] = str(row["apiBase"])
    if env:
        entry["env"] = env
    return entry, "openclaw 注册表"


def _dsh_entry(profile: str, home: Path | None = None) -> tuple:
    """从 profile 的 cordis.patch.yml 里取 vod-devkit-mcp 块的 launch（S234）。

    dsh 没有"一份 JSON 配置"可读：MCP 入口写在托管块里（command/args/env）。
    """
    home = Path.home() if home is None else home
    patch = home / ".dsh" / "profiles" / profile / "cordis.patch.yml"
    if not patch.exists():
        return None, f"缺 patch {patch}"
    text = patch.read_text(encoding="utf-8")
    if "vod-devkit-mcp" not in text:
        return None, "patch 里没有 vod-devkit-mcp 块"
    blk = text.split("- id: vod-devkit-mcp", 1)[1]
    for cut in ("\n    - id: vod-devkit\n", "\n    - id: vod-devkit "):
        if cut in blk:
            blk = blk.split(cut, 1)[0]
    cmd = re.search(r"^\s+command:\s*(.+)$", blk, re.M)
    args = re.findall(r"^\s+-\s+(/\S+\.py)\s*$", blk, re.M)
    env = {}
    for k, v in re.findall(r"^\s+(VOD_[A-Z_]+):\s*\"?([^\"\n]+)\"?", blk, re.M):
        env[k] = v.strip()
    if not cmd:
        return None, "patch 块缺 command"
    entry = {"command": cmd.group(1).strip(), "args": args}
    if env:
        entry["env"] = env
    return entry, f"patch:{profile}"


def resolve_entry(host: str, home: Path | None = None, profile: str = "web") -> tuple:
    """宿主 → 它自己配置里的 MCP launch（`--audit` 与 `probe_tools` 共用，S234）。

    巡检与工具面探针必须用**同一个 launch**：两个入口各自解析一份配置，会一边报 PASS
    一边报 12 工具（实测：`env`/`environment` 键不同 + 解析分叉）。
    """
    home = Path.home() if home is None else home
    if host == "hermes":
        return _hermes_effective_entry(home)
    if host == "dsh":
        return _dsh_entry(profile, home)
    if host == "codex":
        mkt, mcp, _guessed = _codex_effective_mcp(home)
        if not mcp:
            return None, f"codex 插件缓存里没有 .mcp.json（市场 {mkt or '未声明'}）"
        entry = (json.loads(Path(mcp).read_text(encoding="utf-8")).get("mcpServers") or {}).get("vod-devkit")
        return entry, f"市场 {mkt}"
    if host == "codex-desktop":
        mcp = home / "plugins" / "vod-devkit" / ".mcp.json"
        if not mcp.exists():
            return None, "插件目录缺 .mcp.json"
        entry = (json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}).get("vod-devkit")
        return entry, "插件目录"
    if host == "openclaw":
        return _openclaw_entry(home)
    spec = EXPECT.get(host) or {}
    if spec.get("skip"):
        return None, spec["skip"]
    conf = home / spec["config"] if spec.get("config") else None
    if conf is None or not conf.exists():
        return None, f"缺配置 {conf}"
    try:
        data = json.loads(conf.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, f"配置不是合法 JSON：{e}"
    entry = _dig(data, spec.get("entry"))
    if not entry:
        return None, "配置里没有 vod-devkit 条目"
    return entry, str(conf)


# S232：安全面差异要机器可查——"哪个宿主有 hook 层"原来只写在文档里，
# 巡检时看不出来（运维会以为 10 个宿主保护等级一样）。口径与 docs/hooks.md 一致：
# 只有 hermes 注册了 pre_llm_call（路由）+ pre_tool_call（读 key 拦截）；其余宿主
# 只有技能教法（软约束），codex/opencode 的等价注册未探。
HOOK_LAYER = {
    "hermes": "有（pre_llm_call 路由 + pre_tool_call 读 key 拦截）",
}


def hook_layer_label(host: str) -> str:
    """巡检用：该宿主的 hook 保护层形态（S232）。未知宿主按文档口径=无。"""
    return HOOK_LAYER.get(host, "无（仅技能教法，软约束）")


def audit_host(host: str, expect_version: str, home: Path | None = None) -> tuple:
    """只读巡检**真实机器**上的安装（不写任何文件）：条目在不在、入口存不存在、
    自证版本是否等于构建版本。返回 PASS / DRIFT / NOT_INSTALLED。

    动机（2026-11-12 实锤）：矩阵全绿不代表这台机器的安装是新的——巡检当场发现
    opencode 指向仓内路径而非载荷、codex 停在 0.5.3、dsh 壳还钉着 0.4.4。
    """
    home = Path.home() if home is None else home
    spec = EXPECT[host]
    if host == "openclaw":
        return _audit_openclaw(home, expect_version)
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
        elif host == "hermes":
            # 生效入口是 config.yaml 的 mcp_servers.vod-devkit；mcp/vod-devkit.json
            # 只是备片（写它不代表宿主会读它——2026-11-16 实锤：备片能跑通，
            # 而 config.yaml 指向已清理的 scratch 路径，巡检却报 PASS）
            entry, why = _hermes_effective_entry(home)
            if entry is None:
                return "DRIFT", why
            ok, msg = _probe(entry, expect_version)
            return ("PASS" if ok else "DRIFT"), f"{msg}（{why}）"
        else:
            entry = _dig(data, spec["entry"])
            if spec["entry"] and not entry:
                return "DRIFT", f"缺条目 {'.'.join(str(x) for x in spec['entry'] if x)}"
    if host == "codex":
        # 不能"排序取最后一份"：personal(0.5.4) 与 vod-local(0.5.9) 并存时排序会选中
        # 后者并报 PASS，而 codex 实际按 config.toml 里 enabled 的那个市场跑（实锤 0.5.4）
        mkt, mcp, guessed = _codex_effective_mcp(home)
        if mcp is None:
            return "NOT_INSTALLED", f"codex 插件缓存里没有 .mcp.json（市场 {mkt or '未声明'}）"
        entry = (json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}
                 ).get("vod-devkit")
        ok, msg = _probe(entry or {}, expect_version)
        note = f"codex 生效市场 {mkt}" + ("，未在 config.toml 声明、按存在的那份判" if guessed else "")
        return ("PASS" if ok else "DRIFT"), f"{msg}（{note}）"
    if host == "dsh":
        patches = sorted((home / ".dsh" / "profiles").glob("*/cordis.patch.yml"))
        hit = [p for p in patches
               if "- id: vod-devkit" in p.read_text(encoding="utf-8", errors="replace")]
        if not hit:
            return "NOT_INSTALLED", "dsh profile patch 里没有 vod-devkit 块"
        # S153-3：dsh 的多 profile 是独立安装对象，巡检必须逐个判——只判 hit[0] 会把
        # "web 的 MCP 块被清掉、headless 完好" 报成 PASS（1 PASS，看不出判的哪个 profile）。
        # 报文一律带 profile 名；任一 profile 非 PASS 即整体 DRIFT。
        rec = _dsh_manifest_mcp(home)      # 安装期记录：区分"合法降级"与"MCP 块被清"（S153-4）
        results = [(p.parent.name,) + _audit_dsh_profile(p, entry or {}, expect_version,
                                                         rec.get(p.parent.name))
                   for p in hit]
        bad = [(n, m) for n, v, m in results if v != "PASS"]
        if bad:
            return "DRIFT", "；".join(f"[{n}] {m}" for n, m in bad)
        return "PASS", "；".join(f"[{n}] {m}" for n, _v, m in results)
    if not entry:
        return "NOT_INSTALLED", "无条目"
    ok, msg = _probe(entry, expect_version)
    return ("PASS" if ok else "DRIFT"), msg


def main():
    _pin_roots()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", default=[])
    ap.add_argument("--keep", action="store_true", help="保留隔离 HOME（排查用）")
    ap.add_argument("--audit", action="store_true",
                    help="只读巡检真实机器上的安装（不装/不卸/不写）")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    # 插件副本是生成物（v0.5.9 零提交）：矩阵要装的是当前源码，先同步一次
    # （import 生成器本身，PAIRS/忽略规则与门禁同源）。
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_plugin
    sync_plugin.sync(ROOT, quiet=True, write_build_info=False)
    build = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8"))
    version = str(build.get("version"))
    hosts = a.host or list(EXPECT)
    tmp = Path(tempfile.mkdtemp(prefix="vod-matrix-"))
    home = tmp / "home"
    home.mkdir()
    results = {}
    if a.audit:
        # S210：按账本填"该版本允许的 commitSha"——版号相等不算对账，同版号换内容必须 DRIFT
        _EXPECT_SHAS.clear()
        for _r in (_raw_manifest(Path.home()).get("installs") or []):
            if _r.get("version") and _r.get("commitSha"):
                _EXPECT_SHAS.setdefault(str(_r["version"]), set()).add(str(_r["commitSha"]))
        for h in hosts:
            if EXPECT.get(h, {}).get("skip"):
                results[h] = "SKIP"
                print(f"[{h}] SKIP: {EXPECT[h]['skip']}")
                continue
            state, msg = audit_host(h, version)
            results[h] = state
            print(f"[{h}] {state}: {msg}｜hook 层：{hook_layer_label(h)}")
        drift = [h for h, s in results.items() if s == "DRIFT"]
        missing = [h for h, s in results.items() if s == "NOT_INSTALLED"]
        skipped = [h for h, s in results.items() if s == "SKIP"]
        print(f"\n巡检：{len(results) - len(drift) - len(missing) - len(skipped)} PASS / "
              f"{len(drift)} DRIFT / {len(missing)} NOT_INSTALLED / {len(skipped)} SKIP"
              f"（构建 {version}）")
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