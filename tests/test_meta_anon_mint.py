"""D-meta-anon-1：匿名档 meta 401 死循环回归锁（Python 侧）。

真机实锤（2026-11-18，stdio 端到端首次跑就挂）：
  未配 key 的默认形态下，`_load_meta` 先于「提交遇 401 才领令牌」发生
  → meta 请求无 Authorization → 引擎 401 → `except ToolError: pass`
  → 回退空快照 → 产品名录恒空 → 产品归因必失败（needsProductAsk）
  → 而领令牌要提交成功、提交成功要归因成功 → **一条声音都提交不了**。

dsh 侧先修（loadMeta 401 → 领令牌 → 重试），Python 侧同构补上。

本文件锁：
  ① 无 key 时 meta 401 → 领匿名令牌 → 带 key 重试拿到名录（source=meta-anon）
  ② 已配 key 时不额外领令牌
  ③ 完全拉不到时仍回退快照，不阻断采集
"""
import pytest

from vod_mcp import net as _net
from vod_mcp import runtime_state as _rt


class _FakeHTTP:
    """记录调用；无 auth 一律 401，有 auth 返回名录。"""

    def __init__(self, *, token_value="anon-t1", products=None):
        self.calls = []
        self.token_value = token_value
        self.products = products if products is not None else ["CodeArts", "OfficeAce"]

    def __call__(self, method, path, body=None, **kw):
        auth = kw.get("key") or ""
        self.calls.append({"method": method, "path": path, "auth": bool(auth)})
        # _http 返回的是响应 JSON 本身（含 data 信封），不是 {status, data} 包装
        if "external/token" in path:
            return {"code": 200, "data": {"token": self.token_value}}
        if "external/meta" in path:
            if not auth:
                raise _net.ToolError("鉴权失败：未提供 API Key", code=-32012)
            return {"code": 200, "data": {
                "products": self.products,
                "productCatalog": [{"id": i + 1, "name": n}
                                   for i, n in enumerate(self.products)],
                "dictVersion": "test",
            }}
        return {"code": 200, "data": {}}


@pytest.fixture
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(tmp_path))
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_eff_key", lambda *a, **k: "")
    monkeypatch.setattr(_net, "_java_base", lambda: "https://vod.example.test")
    yield
    monkeypatch.setattr(_rt, "_RT", {})


def test_meta_401_mints_anon_token_and_retries(monkeypatch, clean_state):
    """① 无 key：meta 401 → 领令牌 → 带 key 重试 → 名录可用。"""
    fake = _FakeHTTP()
    monkeypatch.setattr(_net, "_http", fake)

    meta = _net._load_meta(force=True)

    metas = [c for c in fake.calls if "external/meta" in c["path"]]
    assert len(metas) >= 2, f"meta 应请求 ≥2 次（401 + 重试），实得 {fake.calls}"
    assert metas[0]["auth"] is False, "首次 meta 无 auth（复现真机 401）"
    assert any(c["auth"] for c in metas), "重试那次必须带 key"
    assert any("external/token" in c["path"] for c in fake.calls), "应领取匿名令牌"

    assert meta["source"] == "meta-anon"
    assert meta["stale"] is False
    assert len(meta["products"]) == 2, "名录必须真的拿到，否则归因必失败"


def test_meta_no_extra_token_when_key_configured(monkeypatch, clean_state):
    """② 已配 key：不额外领令牌，首次 meta 就带 auth。"""
    fake = _FakeHTTP()
    monkeypatch.setattr(_net, "_http", fake)
    monkeypatch.setattr(_net, "_eff_key", lambda *a, **k: "preset-key")

    meta = _net._load_meta(force=True)

    assert meta["source"] == "meta", "已配 key 走标准路径"
    assert not any("external/token" in c["path"] for c in fake.calls), "不该领匿名令牌"
    assert all(c["auth"] for c in fake.calls if "external/meta" in c["path"])


def test_meta_falls_back_to_snapshot_when_unreachable(monkeypatch, clean_state):
    """③ 拉不到（令牌也领不到）→ 回退快照，不阻断采集。"""
    def _fail(method, path, body=None, **kw):
        raise _net.ToolError("网络不可达", code=-32000)

    monkeypatch.setattr(_net, "_http", _fail)
    monkeypatch.setattr(_net, "_fetch_anon_token", lambda: None)

    meta = _net._load_meta(force=True)
    assert meta["stale"] is True
    assert meta["source"] == "snapshot"
