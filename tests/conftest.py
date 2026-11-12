"""全局测试隔离：所有用例的 runtime 读写重定向到 tmp。

实锤教训：test_followup 等 _submit 路径用例桩了 _http 却没重定向
_runtime_path，账本追加直接写进仓内真实 vod_mcp/runtime.json——
本地 200 条账本被测试数据灌满（cap 挤压真实提交记录）。
autouse 先生效，用例内自身 setattr 可覆盖（后 setattr 者胜）。
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime(tmp_path, monkeypatch):
    from vod_mcp import tools
    monkeypatch.setattr(tools, "_runtime_path", lambda: tmp_path / "runtime.json")
    yield


@pytest.fixture(autouse=True)
def _legacy_product_switch(monkeypatch):
    """D-product-ask-1 前写的老用例默认走兼容开关；专项用例把它 delenv 掉验证强制。"""
    monkeypatch.setenv("VOD_ALLOW_UNKNOWN_PRODUCT", "1")
    # 会话记忆是进程内全局（D-product-ask-1），跨用例会串——每个用例清空
    from vod_mcp import tools as _t
    _t._SESSION_MEM.clear()
