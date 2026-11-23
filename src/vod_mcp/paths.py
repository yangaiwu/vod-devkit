"""根定位：两个根 + 入口显式设置（D-structure-1 S3-A）。

历史（为什么改成两个根）：此前用"`vod_mcp` 的父目录"一个算式兼容三种形态——仓内直跑、
载荷副本、插件副本。S3 把包迁进 `src/` 后这个算式失效：仓内形态下包根是 `<repo>/src`，
而分发态（install-manifest / build-info / 载荷）在 `<repo>`。一个根无法同时回答两件事。

现在的契约：
- **根由入口显式设置**（`bin/vod-devkit`、`npm/cli.js`、`server.main()`、`tests/conftest`、
  `scripts/host_matrix.py` 各设 `VOD_DEVKIT_SRC_ROOT` / `VOD_DEVKIT_DIST_ROOT`）；
  入口不覆盖已存在的环境变量（测试注入/重定位要用它），但**继承值与入口所在仓不一致时
  必然在 stderr 告警**——静默用错根的表现是"未知宿主 xxx（可选：）"这类无从解释的错；
- 本模块**只读不猜**；读不到时 derive-once 兜底（仅仓内开发/旧脚本），并告警；
- 两处都不可知 → 硬失败并提示应设哪个变量。

三种形态（实测口径，见 docs/architecture.md 7.1）：

| 形态 | SRC_ROOT | DIST_ROOT | ASSETS |
|---|---|---|---|
| 仓内直跑 | `<repo>/src` | `<repo>` | `<repo>/assets` |
| 载荷副本 | 载荷根 | 载荷根 | 载荷根（平铺） |
| 插件副本 | 插件包根 | 插件包根 | 插件包根（平铺） |

旧布局（包直接挂在仓根，即 S3 之前的检出）在 0.6.x 保留一条回落：
`LEGACY_ALLOWED_UNTIL = "0.7.0"`，命中即 `DeprecationWarning`；到达该版本后直接硬失败
（`tests/test_p2_structure.py` 锁住"分支只存在于允许区间"）。
"""
import json
import os
import stat
import tempfile
import warnings
from pathlib import Path
from vod_mcp import trace as _trace

# 物理包位置：本文件在 <root>/vod_mcp/ 下（仓内=src/、载荷/插件副本=各自根）
_PKG_PARENT = Path(__file__).resolve().parent.parent

LEGACY_ALLOWED_UNTIL = "0.7.0"
_warned = False


def _warn(msg: str) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    warnings.warn(msg, DeprecationWarning, stacklevel=3)


def _version() -> str:
    from vod_mcp import __version__
    return __version__


def _v_tuple(v: str) -> tuple:
    parts = []
    for chunk in v.split(".")[:3]:
        num = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(num or 0))
    return tuple(parts + [0] * (3 - len(parts)))


def _looks_like_repo_dir(p: Path) -> bool:
    return (p / "pyproject.toml").exists() or (p / "package.json").exists()


def _derive() -> tuple:
    """derive-once：无 env 时按物理位置推断，并在"非标准形态"上告警。

    返回值 (src_root, dist_root, assets_root)。
    """
    env_src = (os.environ.get("VOD_DEVKIT_SRC_ROOT") or "").strip()
    env_dist = (os.environ.get("VOD_DEVKIT_DIST_ROOT") or "").strip()

    if env_src or env_dist:
        src = Path(env_src).expanduser().resolve() if env_src else _PKG_PARENT
        dist = Path(env_dist).expanduser().resolve() if env_dist else _PKG_PARENT.parent
        assets = dist / "assets" if (dist / "assets" / "skills").is_dir() else src
        return (src, dist, assets)

    repo = _PKG_PARENT.parent
    if _PKG_PARENT.name == "src" and _looks_like_repo_dir(repo):
        # ① 仓内直跑（S3 之后的检出）：包在 src/，资产在 assets/
        return (_PKG_PARENT, repo, repo / "assets")

    if _PKG_PARENT.name != "src" and _looks_like_repo_dir(_PKG_PARENT):
        # ② 旧布局（S3 之前的检出）：包在仓根、资产也在仓根
        if _v_tuple(_version()) >= _v_tuple(LEGACY_ALLOWED_UNTIL):
            raise RuntimeError(
                "检测到 S3 之前的旧仓内布局（vod_mcp/ 在仓根），该回落已在 "
                f"{LEGACY_ALLOWED_UNTIL} 移除。请更新检出，或显式设置 "
                "VOD_DEVKIT_SRC_ROOT / VOD_DEVKIT_DIST_ROOT。")
        _warn("仓内旧布局已弃用（vod_mcp/ 在仓根）：请使用 src/ 布局；"
              f"{LEGACY_ALLOWED_UNTIL} 起将硬失败")
        return (_PKG_PARENT, _PKG_PARENT, _PKG_PARENT)

    # ③ 载荷 / 插件副本：包父目录就是分发根，代码与资产都平铺在它下面
    root = _PKG_PARENT
    return (root, root, root)


SRC_ROOT, DIST_ROOT, ASSETS = _derive()

# 兼容旧名：ROOT 是"分发态根"（manifest/build-info/载荷入口都相对它）
ROOT = DIST_ROOT

SKILLS = ASSETS / "skills"
CONTRACT = ASSETS / "contract" / "tools.schema.json"
POLICY = ASSETS / "safety" / "policy.json"
HOOKS = ASSETS / "hooks"                  # 载荷/插件副本里 hooks 平铺；仓内走 integrations
INSTALL_MANIFEST = DIST_ROOT / "install-manifest.json"
BUILD_INFO = DIST_ROOT / "build-info.json"

# ── 机器级运行期状态（D-token-machine-1，2026-11-16） ─────────────────────
#
# 为什么不在 DIST_ROOT 下：DIST_ROOT 装机形态是 ~/.vod-devkit/payloads/<版本>/，
# 一次升级就换目录 → 换 install_nonce → 重领匿名令牌（额度重计、账本断档）。
# 匿名令牌是**机器级身份**（设备锚点绑定），必须跨版本、跨宿主共享一份。
#
# 解析优先级（每次现读；D-state-read-1 的同一纪律）：
#   ① VOD_DEVKIT_HOME 显式（装机写进各宿主 env；测试写 tmp）
#   ② 机器级 state 已存在 → 用它（存在即用，不依赖 env 透传）
#   ③ 旧 DIST_ROOT/vod_mcp/runtime.json（首启兼容位，不是并行真源）
_STATE_DIRNAME = "state"


def machine_state_home() -> Path:
    """机器级状态目录（现读）：VOD_DEVKIT_HOME > ~/.vod-devkit/state。"""
    env = (os.environ.get("VOD_DEVKIT_HOME") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path(os.path.expanduser("~")) / ".vod-devkit" / _STATE_DIRNAME


def ensure_state_home() -> Path:
    """确保机器级 state 目录存在且为 0700（ARCH-CFG-06）。

    历史形态：只有"从旧位迁移"那条路会 chmod 0700，全新安装（或用户手工 mkdir 的）
    目录可能停在 0755 —— 里面有 runtime.json（引擎 key），组/其他用户可枚举。
    这里统一收紧：建目录时按 0700，已存在的宽权限只收紧不放宽（与 CFG-01 同口径）。
    """
    state = machine_state_home()
    state.mkdir(parents=True, exist_ok=True)
    try:
        if stat.S_IMODE(os.stat(state).st_mode) & 0o077:
            os.chmod(state, 0o700)
    except OSError as e:
        _trace.suppress("paths.ensure_state_home", e)
    return state


def legacy_runtime_json() -> Path:
    """旧位置（版本目录内）：只作兼容/迁移来源，不再作为日常真源。"""
    return DIST_ROOT / "vod_mcp" / "runtime.json"


def runtime_json_path() -> Path:
    """当前生效的 runtime.json 路径（现读，长驻进程不冻结）。"""
    env = (os.environ.get("VOD_DEVKIT_HOME") or "").strip()
    if env:
        return Path(env).expanduser() / "runtime.json"
    machine = machine_state_home() / "runtime.json"
    if machine.exists():
        return machine
    legacy = legacy_runtime_json()
    return legacy if legacy.exists() else machine


def migrate_state_once() -> dict:
    """首启迁移：state 无 runtime 而旧位置有 → 复制一次（保留设备锚点与账本）。

    为什么保留旧文件：迁移本身不该是破坏性操作；旧文件的删除留给
    `uninstall --clean-global`（逐条打印）。
    为什么要 `.migrated` 标记（2026-11-16 评审补强）：只看"state 无 runtime"的话，
    用户手工清掉 state 后旧文件会**复活**（下次启动又迁回来，令牌/账本被悄悄还原）。
    有标记即视为"这台机器已经迁过"，此后旧位置只读、不再回灌。
    返回 {"migrated": bool, "from": str, "reason": str|None}。
    """
    state = machine_state_home()
    target = state / "runtime.json"
    marker = state / ".migrated"
    legacy = legacy_runtime_json()
    if marker.exists():
        return {"migrated": False, "from": None, "reason": "already-migrated"}
    if target.exists() or not legacy.exists():
        return {"migrated": False, "from": None, "reason": None}
    try:
        state.mkdir(parents=True, exist_ok=True)
        target.write_bytes(legacy.read_bytes())
        os.chmod(target, 0o600)
        try:
            os.chmod(state, 0o700)
        except OSError as e:
            _trace.suppress("paths.migrate_state_once", e)
        atomic_write_text(marker, json.dumps({"from": str(legacy), "migrated": True}) + "\n")
        return {"migrated": True, "from": str(legacy), "reason": None}
    except OSError:
        return {"migrated": False, "from": None, "reason": "io-error"}


# 不提供模块级 RUNTIME_JSON 快照常量（D-token-machine-1 收口）：它零消费方，
# 且违反本模块"路径类值不 import 期冻结"的纪律（D-state-read-1）——留着会被后人
# 当合法读法用。调用方一律 runtime_json_path() / runtime_state._runtime_path()。


def hook_script(name: str = "vod_router.py") -> Path:
    """宿主侧 hook 脚本的真实路径（默认预采集路由 vod_router.py；安全面 vod_guard.py）。

    仓内：`integrations/hermes/hooks/<name>`（宿主侧资产，随载荷物化到 <payload>/hooks）；
    载荷/插件副本：`<root>/hooks/<name>`。
    """
    repo_local = DIST_ROOT / "integrations" / "hermes" / "hooks" / name
    if repo_local.is_file():
        return repo_local
    return HOOKS / name


def guard_script() -> Path:
    """读 Key 拦截 hook（pre_tool_call）的路径。"""
    return hook_script("vod_guard.py")


def host_home(var: str, subdir: str) -> Path:
    """宿主家目录：环境变量（CODEX_HOME / DSH_HOME）优先，否则 `~/<subdir>`。

    S177：宿主自己认的是这两个变量（codex 的 CODEX_HOME、dsh 的 DSH_HOME）；适配层
    写死 `Path.home()/.codex` 时，设了变量的机器上会出现「写 A 读 B」——配置写对了、
    宿主看不见，且 doctor/巡检读同一份错落点，自洽地错。宿主的 configPath 统一定义在
    host.json，解析走 hosts._resolve() 同一规则；此函数给代码里必须自己拼路径的地方用。
    """
    v = (os.environ.get(var) or "").strip()
    return Path(v).expanduser() if v else Path.home() / subdir


def describe() -> dict:
    """诊断用：把"当前是哪两个根"打出来（doctor/explain 排障时不再靠猜）。"""
    return {"srcRoot": str(SRC_ROOT), "distRoot": str(DIST_ROOT), "assets": str(ASSETS),
            "stateHome": str(machine_state_home()),
            "runtime": str(runtime_json_path())}


def atomic_write_text(path: Path | str, text: str, mode: int | None = None) -> None:
    """原子写文本（P4，2026-11-16 评审）：同目录 tmp → fsync → chmod → os.replace。

    为什么：账本与宿主 MCP 配置此前是裸 `Path.write_text`——中断/磁盘满会留下半截 JSON，
    而读侧解析失败静默当空账本，下一次 install 就只写自己那一行（其它安装行全丢，
    doctor 只看到一台、uninstall 摘不到）。runtime.json 早已是这套写法，这里统一。

    `mode` 缺省沿用目标文件现有权限（新文件 0600）——账本含宿主路径/产品绑定，
    配置里有用户自己的其它 server 条目，权限不许因改写而放宽。
    """
    p = Path(path)
    # 符号链接：os.replace 换的是链接本身（会把用户的 dotfiles 软链变成普通文件），
    # 而 write_text 是跟随链接写的。落点先解析到真实目标，行为与旧写法一致（S180）。
    if p.is_symlink():
        p = p.resolve()
    # 只读目标（无 owner 写位）在 tmp+replace 下会被静默覆盖（目录可写即可 replace），
    # 与旧 write_text 的 PermissionError 语义不同——用户 chmod 444 就是要保护，先拒（S180）。
    if p.exists() and not (p.stat().st_mode & 0o200):
        raise PermissionError(30, "目标文件没有写权限（chmod 444 保护）", str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = p.stat().st_mode & 0o777
        except OSError:
            mode = 0o600
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError as e:
            _trace.suppress("paths.atomic_write_text", e)
        raise
