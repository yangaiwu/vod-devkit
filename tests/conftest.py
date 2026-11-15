"""全局测试隔离：所有用例的 runtime 读写重定向到 tmp。

实锤教训：test_followup 等 _submit 路径用例桩了 _http 却没重定向
_runtime_path，账本追加直接写进仓内真实 vod_mcp/runtime.json——
本地 200 条账本被测试数据灌满（cap 挤压真实提交记录）。
autouse 先生效，用例内自身 setattr 可覆盖（后 setattr 者胜）。
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def _sync_plugin_copy():
    """插件副本是生成物（v0.5.9 起零提交）：整场测试前同步一次，保证
    「副本自包含」类用例读到的是当前源码，而不是上次留在磁盘上的残骸。"""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "scripts" / "sync_plugin.py")],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, f"sync_plugin 失败：{r.stderr[-500:]}"
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
