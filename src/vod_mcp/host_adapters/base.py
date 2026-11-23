"""宿主适配公共件：MCP server 入口、环境与 JSON 配置合并（各宿主共用）。"""
import json
import os
import shutil
from pathlib import Path

from vod_mcp import paths

ROOT = paths.ROOT

# 载荷目录（bin 在 install 前用 payload.stage() 落好并 set_payload_dir 指过来）
_PAYLOAD_DIR = None


def set_payload_dir(path) -> None:
    global _PAYLOAD_DIR
    _PAYLOAD_DIR = Path(path) if path else None


def payload_dir():
    return _PAYLOAD_DIR


def server_entry() -> str:
    """MCP server 绝对路径：优先载荷副本（npx 缓存被清也不会掉线），否则仓内。"""
    base = _PAYLOAD_DIR or ROOT
    return str(Path(base) / "vod_mcp" / "server.py")


def server_env(args, packs: str) -> dict:
    # 无 key 不写空串（空串会让探针/严格解析器误当字面值；运行时空=未设置，
    # 自动兜底 runtime.json java_key 或首提申请匿名令牌）
    env = {"VOD_PACKS": packs,
           "VOD_JAVA_API_BASE": args.java_api_base,
           # D-token-machine-1：机器级状态目录显式写进宿主配置——
           # 不依赖"默认值恰好一致"，也不随载荷版本目录漂移（升级不换令牌）。
           "VOD_DEVKIT_HOME": str(paths.machine_state_home())}
    key = os.environ.get("VOD_JAVA_API_KEY", "")
    if key:
        env["VOD_JAVA_API_KEY"] = key
    return env


def merge_json_mcp(path: Path, entry: dict, section: str = "mcp",
                   name: str = "vod-devkit", backup: bool = True) -> str:
    """读写共享 JSON 配置里的 <section>.<name> 条目（保留其它键/其它 server）。

    返回 created / updated / unchanged；文件不是合法 JSON 时抛 RuntimeError
    （调用方拒绝安装，字节不动）。共享配置文件首改落 .bak。
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
    block = cfg.get(section)
    if block is None:
        block = {}
    elif not isinstance(block, dict):
        raise RuntimeError(f"{path} 的 {section} 不是对象，拒绝改动")
    if block.get(name) == entry:
        return "unchanged"
    action = "updated" if block.get(name) else "created"
    if existed and backup:
        shutil.copyfile(path, str(path) + ".bak")
    block[name] = entry
    cfg[section] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    paths.atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    return action

def remote_entry(url: str, token: str, *, header_key: str = "headers") -> dict:
    """远程 attach 的 MCP 条目（ARCH：空 token 不许写 `Bearer ` 空头）。

    历史缺陷（2026-11-23 实测）：不带 --mcp-token 时也会写
    `headers.Authorization = "Bearer "`——空 Bearer 会被反代/引擎当作非法凭据，
    本意是"不带头、走服务端匿名令牌"。现在：有 token 才写头，没有就整个省掉。
    `header_key` 供个别宿主用 `environment` 承载头的形态。
    """
    token = (token or "").strip()
    entry: dict = {"url": url}
    if token:
        entry[header_key] = {"Authorization": f"Bearer {token}"}
    return entry

# ── MCP 启动形态（D-interpreter-1） ────────────────────────────────────────────
# python = 绝对解释器 + 载荷脚本（历史形态；宿主机器状态一旦被清就全挂）
# npx    = `npx -y -p vod-devkit@<ver> vod-devkit-mcp`（启动时解析解释器与载荷）
_LAUNCHER_MODES = ("npx", "python")


def launcher_mode(args) -> str:
    # 缺省 python：库级调用（测试/老脚本）不因新增开关改变行为；
    # CLI install 解析器显式默认 npx（见 vodkit_cli/cli.py）。
    mode = str(getattr(args, "mcp_launcher", "python") or "python").strip().lower()
    if mode == "auto":
        mode = "npx" if shutil.which("node") else "python"
    return mode if mode in _LAUNCHER_MODES else "python"


_REGISTRY_CACHE: dict = {}


def _version_published(ver: str) -> bool:
    """该版本在 npm registry 上是否存在（npx 钉版本的前提）。

    注意：不能用 build-info 的 snapshot=worktree 做判据——release.sh 在 worktree 里
    打包，发布出去的 tarball 同样写着 worktree，用它判断会把所有 npm 安装都误降级。
    只信 registry：查不到（404）才降级；网络不可达按"未知"处理并用 npx（离线时
    npx 自己报错，比静默换形态好排查）。
    """
    if os.environ.get("VOD_DEVKIT_SKIP_REGISTRY_CHECK") == "1":
        return True
    if ver in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[ver]
    ok = True
    try:
        import subprocess
        r = subprocess.run(["npm", "view", f"vod-devkit@{ver}", "version"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode != 0 and "E404" in (r.stderr or ""):
            ok = False
    except (OSError, subprocess.SubprocessError):
        ok = True
    _REGISTRY_CACHE[ver] = ok
    return ok


def command_args(args, server_path=None) -> tuple:
    """(command, args) —— MCP server 的启动命令，按 launcher 形态给出。

    为什么不在配置里写死解释器：0.5.45 事故——配置指向被 prune 掉的 venv，
    11 个宿主同时起不来而 doctor 全绿。npx 形态把"解释器在哪"推迟到每次启动解析。
    """
    from vod_mcp import __version__ as _ver
    mode = launcher_mode(args)
    if mode == "npx":
        if not shutil.which("node"):
            mode = "python"
        elif not _version_published(_ver):
            mode = "python"  # 该版本还没发布：npx 钉版本会 404，退回绝对解释器形态
    if mode == "npx":
        return "npx", ["-y", "-p", f"vod-devkit@{_ver}", "vod-devkit-mcp"]
    import sys
    return sys.executable, [server_path or server_entry()]


def command_list(args, server_path=None) -> list:
    """数组形态（"command": [exe, script]）的宿主用。"""
    cmd, rest = command_args(args, server_path)
    return [cmd, *rest]
