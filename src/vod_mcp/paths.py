"""根定位：两个根 + 入口显式设置（D-structure-1 S3-A）。

历史（为什么改成两个根）：此前用"`vod_mcp` 的父目录"一个算式兼容三种形态——仓内直跑、
载荷副本、插件副本。S3 把包迁进 `src/` 后这个算式失效：仓内形态下包根是 `<repo>/src`，
而分发态（install-manifest / build-info / 载荷）在 `<repo>`。一个根无法同时回答两件事。

现在的契约：
- **根由入口显式设置**（`bin/vod-devkit`、`npm/cli.js`、`server.main()`、`tests/conftest`、
  `scripts/host_matrix.py` 各设 `VOD_DEVKIT_SRC_ROOT` / `VOD_DEVKIT_DIST_ROOT`）；
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
import os
import warnings
from pathlib import Path

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
RUNTIME_JSON = DIST_ROOT / "vod_mcp" / "runtime.json"
BUILD_INFO = DIST_ROOT / "build-info.json"


def hook_script() -> Path:
    """预采集 hook 脚本的真实路径。

    仓内：`integrations/hermes/hooks/vod_router.py`（宿主侧资产，随载荷物化到 <payload>/hooks）；
    载荷/插件副本：`<root>/hooks/vod_router.py`。
    """
    repo_local = DIST_ROOT / "integrations" / "hermes" / "hooks" / "vod_router.py"
    if repo_local.is_file():
        return repo_local
    return HOOKS / "vod_router.py"


def describe() -> dict:
    """诊断用：把"当前是哪两个根"打出来（doctor/explain 排障时不再靠猜）。"""
    return {"srcRoot": str(SRC_ROOT), "distRoot": str(DIST_ROOT), "assets": str(ASSETS)}
