"""S231：独立部署冷启动的目录可达性 + 产品主键不许用名字冒充。

真机实测（2026-11-17，payloads/0.5.35，隔离 HOME）：
- 冷启动（无 token、无目录缓存）`vod_search_products` 恒返回 0 候选；
  先 `vod_auth_ensure` 再查就返回 3 候选 / total=103 → 目录要靠令牌才取得到；
- 冷态 `draft` 回执里 productId 被写成产品名（"CodeArts"），领到目录后才回主键 "1"。
  按"对外对账以平台签发主键为准"的口径，冷态那条证据链不成立。
"""
from __future__ import annotations

import pytest

from vod_mcp import attribution as _attrib
from vod_mcp import net as _net
from vod_mcp import runtime_state as _rt
from vod_mcp.packs import collect as _collect
from vod_mcp.packs import core as _core

COLD = {"products": ["CodeArts"], "catalog": [], "stale": True, "source": "snapshot"}
WARM = {"products": ["CodeArts"],
        "catalog": [{"id": "1", "name": "CodeArts"}, {"id": "5", "name": "Maas"}],
        "stale": False, "source": "meta"}
NO_ID = {"products": ["CodeArts", "智果"], "catalog": [{"name": "智果"}],
         "stale": False, "source": "meta"}


@pytest.fixture
def cold(monkeypatch, tmp_path):
    """冷启动桩：第一次 meta 无目录；ensure 成功后再取才有目录。"""
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_rt, "_SESSION_MEM", {})
    monkeypatch.setattr(_rt, "_runtime_path", lambda: tmp_path / "runtime.json")
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "JAVA_BASE", "http://stub")
    state = {"ensured": False}
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: WARM if state["ensured"] else COLD)

    def _ensure(_params, client_info=None):
        state["ensured"] = True
        return {"tier": "anonymous", "reason": "verified"}

    monkeypatch.setattr(_core, "auth_ensure", _ensure)
    return state


def test_s231_search_lazily_ensures_token_then_returns_candidates(cold):
    """S231：目录为空时 search 自己领一次令牌，随即就能给出候选。"""
    assert not cold["ensured"]
    out = _core.search_products({"query": "网页卡", "limit": 3})
    assert cold["ensured"] is True, "冷态 search 没有触发懒 ensure"
    assert out["candidates"], out
    assert out["total"] == 2
    assert all(c["id"] for c in out["candidates"])


def test_s231_search_reports_reason_when_catalog_stays_unavailable(monkeypatch, tmp_path):
    """S231：领不到令牌/取不到目录时不静默给空，回执带 reason+hint。"""
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "JAVA_KEY", None)
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: COLD)
    monkeypatch.setattr(_core, "auth_ensure",
                        lambda _p, client_info=None: (_ for _ in ()).throw(RuntimeError("boom")))
    out = _core.search_products({"query": "网页卡"})
    assert out["candidates"] == [] and out["reason"] == "catalog_unavailable"
    assert "产品名或 ID" in out["hint"]


def test_s231_user_answer_without_catalog_id_is_not_submitted(monkeypatch, tmp_path):
    """S231：用户回答命中目录项但没有主键 → 不拿名字（更不拿 "None"）当 productId。"""
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_rt, "_SESSION_MEM", {})
    monkeypatch.setattr(_rt, "_runtime_path", lambda: tmp_path / "runtime.json")
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: NO_ID)
    monkeypatch.delenv("VOD_ALLOW_UNKNOWN_PRODUCT", raising=False)
    with pytest.raises(_net.ToolError):
        _collect.submit_voices({"voices": [{"content": "这个不太好用"}], "confirmed": True,
                                "product": "智果"}, client_info={"name": "codearts"})


def test_s231_single_hit_without_primary_key_is_unknown():
    """S231：目录在、产品无主键 → source=unknown + evidence id_unresolved。"""
    meta = {"products": ["CodeArts"], "catalog": [{"name": "CodeArts"}], "aliases": {}}
    out = _attrib.attribute("CodeArts 导出失败了", meta)
    assert out["product"] is None and out["source"] == "unknown"
    assert out["evidence"][0]["reason"] == "id_unresolved"


def test_s231_legacy_name_channel_kept_only_without_catalog():
    """S231：目录完全不可用（老引擎）时保留 name 兼容通道，但证据标 name_legacy。"""
    meta = {"products": ["CodeArts"], "catalog": [], "aliases": {}}
    out = _attrib.attribute("CodeArts 导出失败了", meta)
    assert out["product"] == "CodeArts" and out["source"] == "user_input"
    assert out["evidence"][0]["reason"] == "name_legacy"