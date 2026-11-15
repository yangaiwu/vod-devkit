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
    yield


@pytest.fixture(autouse=True)
def _legacy_product_switch(monkeypatch):
    """D-product-ask-1 前写的老用例默认走兼容开关；专项用例把它 delenv 掉验证强制。"""
    monkeypatch.setenv("VOD_ALLOW_UNKNOWN_PRODUCT", "1")
    # 会话记忆是进程内全局（D-product-ask-1），跨用例会串——每个用例清空
    from vod_mcp import runtime_state as _rt
    _rt._SESSION_MEM.clear()
