"""根定位单一真源（P1）。

此前有 11 处各自用 `Path(__file__).resolve().parent.parent` 反推仓库根：
tools / server / skills_registry / policy / provenance / hosts /
transport_remote / payload / host_adapters.base / bin。分散的代价不是不好看，
而是“想挪文件”本身有成本——每挪一个模块都要重算相对深度，于是没人敢动目录。

三种根形态必须同时成立（都已实测）：
  ① 仓内直跑：ROOT = 仓库根（vod_mcp 的父目录）
  ② 载荷：~/.vod-devkit/payloads/<ver>/（payload.stage 固化，含 vod_mcp 与资源）
  ③ 插件副本：plugins/vod-devkit/（宿主隔离安装的独立根，资源随包携带）
三者的共同点：`<ROOT>/vod_mcp/`、`<ROOT>/contract/`、`<ROOT>/safety/`、`<ROOT>/skills/`
都在同一层。所以“ROOT = vod_mcp 的父目录”这个算式对三者都成立——前提是这三份
形态都真的把资源带齐（插件副本此前缺 contract/safety，靠本提交补齐）。

环境变量优先是为了把隐式相对路径变成显式契约：宿主在隔离安装里把插件目录整块
拷走时，可以在启动配置里声明 VOD_DEVKIT_ROOT，而不是赌 __file__ 的深度。
"""
import os
from pathlib import Path

# 物理默认根：本包目录的父目录。不读环境变量，供 sys.path 自举等“必须物理正确”
# 的场合使用（见 server.py 的 bootstrap）。
DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def root() -> Path:
    """运行期根：环境变量优先，物理位置兜底。"""
    env = os.environ.get("VOD_DEVKIT_ROOT")
    return Path(env).expanduser().resolve() if env else DEFAULT_ROOT


ROOT = root()


def assets() -> Path:
    """共享资产根（skills/contract/safety/hooks）。

    仓内布局是 `src/<asset>`（D-structure-1 阶段 S2 起），而**发布布局不变**：
    载荷与插件副本里四个资产直接挂在根下（`<payload>/skills` …）。这条差异只
    在这里判一次，其它模块一律走下面的常量——否则"资产在哪"会在十几个文件里
    各写一份判断，正是 S2 要收掉的东西。
    """
    cand = ROOT / "src"
    if (cand / "skills").is_dir() or (cand / "contract").is_dir():
        return cand
    return ROOT


ASSETS = assets()
SKILLS = ASSETS / "skills"
CONTRACT = ASSETS / "contract" / "tools.schema.json"
POLICY = ASSETS / "safety" / "policy.json"
HOOKS = ASSETS / "hooks"
INSTALL_MANIFEST = ROOT / "install-manifest.json"
RUNTIME_JSON = ROOT / "vod_mcp" / "runtime.json"
