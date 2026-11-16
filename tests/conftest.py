"""全局测试隔离：所有用例的 runtime 读写重定向到 tmp。

S3 起包在 src/：conftest 是测试入口，负责把两个根与 sys.path 显式设好
（paths.py 只读不猜；测试不再依赖"从哪个目录跑 pytest"）。
"""
import sys
from pathlib import Path

_DIST = Path(__file__).resolve().parent.parent
_SRC = _DIST / "src"
# 只把 src/ 放进 sys.path；两个根由 paths 按物理位置 derive（仓内布局可判定），
# 不在这里全局钉 env——否则"造一个临时仓再跑安装器"的用例会被外层根劫持。
sys.path.insert(0, str(_SRC))
# 注意：不设 PYTHONPATH env——否则"把仓复制到临时目录再跑入口"的用例会 import 到
# 外层仓的包，掩盖副本布局问题（实测踩过：插件副本探针读到了仓内 assets/）。
sys.path.insert(0, str(_DIST))

import pytest


@pytest.fixture(scope="session", autouse=True)
def _sync_plugin_copy():
    """插件副本是生成物（v0.5.9 起零提交）：整场测试前同步一次，保证
    「副本自包含」类用例读到的是当前源码，而不是上次留在磁盘上的残骸。
    直接 import 生成器（同一份 PAIRS/忽略规则），不再另起子进程。"""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    import sync_plugin

    sync_plugin.sync(root, quiet=True)
    yield


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path, monkeypatch):
    from vod_mcp import runtime_state
    monkeypatch.setattr(runtime_state, "_runtime_path", lambda: tmp_path / "runtime.json")
    # 镜像也清空：net 的身份读取是"文件优先、_RT 回落"，而 _RT 是**导入期**从真实
    # runtime.json 读出来的快照——不清它，隔离用例会读到真机安装的 java_key/base。
    monkeypatch.setattr(runtime_state, "_RT", {})
    yield


@pytest.fixture(autouse=True)
def _isolate_machine_writes(monkeypatch, tmp_path):
    """S143 修复：切断所有可能把写操作导到真机的**继承**入口。

    为什么不是"把 manifest 一律指到 tmp"（第一版这么写，19 条用例立刻红）：装机器用例
    （tests/test_installer.py 的 `env` fixture）**在克隆仓里跑 bin/vod-devkit**，账本本来就
    应该落在那个克隆仓根，断言读的也是 `<clone>/install-manifest.json`。真正让它写到
    真机的是两件事，都出在"继承"上：
      · 外层进程带着 VOD_DEVKIT_DIST_ROOT（实测：test_host_matrix 的 import 期 setenv
        泄漏）→ 子进程把 DIST_ROOT 解析成真仓 → 账本写到真仓根；
      · 外层带着 VOD_PAYLOAD_HOME/VOD_JAVA_API_KEY → 载荷根/凭据直接指真机。
    所以这里**只 pop 继承值、不强行改值**：宿主的落点由各自的 HOME/根派生（本仓已按
    env > 文件 > 物理位置分层），pop 之后子进程自然落在自己的克隆/假 HOME 里。
    兜底由 S143 的 session 前后快照负责：真有谁漏隔离，跑完就对不上（exit 1）。
    """
    for k in ("VOD_DEVKIT_MANIFEST", "VOD_PAYLOAD_HOME", "VOD_DEVKIT_SRC_ROOT",
              "VOD_DEVKIT_DIST_ROOT", "VOD_JAVA_API_KEY", "VOD_DEVKIT_HOME"):
        monkeypatch.delenv(k, raising=False)
    # D-token-machine-1：机器级 state 必须**显式**指到 tmp，而不是 pop 了事。
    # 因为 paths.runtime_json_path() 的优先级②是"机器级 state 已存在即用"——
    # pop 之后子进程/同进程会读到真机 ~/.vod-devkit/state 的匿名令牌（凭据泄漏进测试）。
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(tmp_path / "machine-state"))
    yield


@pytest.fixture(autouse=True)
def _legacy_product_switch(monkeypatch):
    """D-product-ask-1 前写的老用例默认走兼容开关；专项用例把它 delenv 掉验证强制。"""
    monkeypatch.setenv("VOD_ALLOW_UNKNOWN_PRODUCT", "1")
    # 会话记忆是进程内全局（D-product-ask-1），跨用例会串——每个用例清空
    from vod_mcp import runtime_state as _rt
    _rt._SESSION_MEM.clear()


# ── S143：整套测试不许写真机（门禁） ────────────────────────────────────
#
# 实锤（2026-11-16）：某个 install 用例没被 env 隔离，把**真实仓根** install-manifest.json
# 的 installs[].payloadDir 写成了 pytest 临时目录；随后 uninstall 用例按这份账本把
# ~/.vod-devkit/payloads/0.5.9 整个删掉 —— 九个宿主的入口全部指向不存在的路径
# （MCP 报 "lost its stdio subprocess"），而 pytest 自己只看到 19 条 FileNotFoundError。
# 隔离 runtime 只覆盖了 runtime.json，没覆盖"落在仓根/用户根"的另外两个写点：
# VOD_DEVKIT_MANIFEST（账本）与 VOD_PAYLOAD_HOME（载荷根）。
#
# 这条门禁在**整套**层面比前后快照：不管哪个用例漏了隔离，跑完就对不上。
def _machine_state() -> dict:
    import hashlib
    import os as _os

    def _md5(pth):
        try:
            return hashlib.md5(pth.read_bytes()).hexdigest()
        except OSError:
            return None

    home = Path(_os.path.expanduser("~"))
    repo = Path(__file__).resolve().parent.parent
    payloads = home / ".vod-devkit" / "payloads"
    state = home / ".vod-devkit" / "state"
    return {
        "manifest": _md5(repo / "install-manifest.json"),
        "payloads": sorted(p.name for p in payloads.iterdir()) if payloads.is_dir() else [],
        "hermes_config": _md5(home / ".hermes" / "config.yaml"),
        # D-token-machine-1：机器级 state（跨版本/跨宿主共享的那一份）。
        # 带上 runtime 的 md5——目录清单不变但内容被改写同样算漂移（令牌/账本被测试污染）。
        "state": (sorted(p.name for p in state.iterdir()) if state.is_dir() else [],
                  _md5(state / "runtime.json")),
        # 仓根不该出现运行期状态（改造后单源在机器级 state；出现即说明有子进程按
        # 旧 derive 写了 legacy 位——测试会连带把"工作树只剩构建产物"这条自检污染）。
        "repo_state_dir": (sorted(p.name for p in (repo / "vod_mcp").iterdir())
                           if (repo / "vod_mcp").is_dir() else []),
    }


def pytest_sessionstart(session):
    session.config._machine_before = _machine_state()


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, "_machine_before", None)
    if before is None:
        return
    after = _machine_state()
    drift = [k for k in before if before[k] != after[k]]
    if not drift:
        return
    print("\n[S143] 机器状态被改动了（测试或**并行 install** 都可能）："
          + "；".join(f"{k}: {before[k]!r} → {after[k]!r}" for k in drift)
          + "\n  先确认不是并行 install 在跑（install/矩阵/巡检同一时间只由一方做）；"
            "确实是测试写的才按隔离缺失处理：tests/conftest.py 的 _isolate_machine_writes"
            "（VOD_DEVKIT_MANIFEST / VOD_PAYLOAD_HOME 必须指向 tmp）", file=sys.stderr)
    session.exitstatus = 1
