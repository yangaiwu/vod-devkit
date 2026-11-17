"""S232：空查询分因（search 不再静默 0 候选）+ 安全面机器可查（hook 层标签）。

真机现象（2026-11-17 评审反馈）：模型把入参写成 `keyword` 时 `vod_search_products`
返回 0 候选而 total 仍是 103，看起来像"目录里没有这个产品"，实际是参数名不对。
另一条：只有 hermes 注册了 hook 层，其余宿主只有技能教法，这个差异原来只写在文档里，
巡检输出看不出来，容易被当成"10 个宿主同一保护等级"。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vod_mcp.packs import core as _core
from vod_mcp import net as _net
from vod_mcp import runtime_state as _rt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import host_matrix as _hm  # noqa: E402

META = {"products": ["CodeArts"], "catalog": [{"id": "1", "name": "CodeArts"}],
        "stale": False, "source": "meta"}


@pytest.fixture
def warm(monkeypatch):
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(_net, "JAVA_KEY", "k")


def test_s232_empty_query_is_reported_with_reason(warm):
    """S232：query 为空（含模型传错参数名）时必须回 reason+提示，而不是静默空列表。"""
    out = _core.search_products({"keyword": "CodeArts", "limit": 3})
    assert out["candidates"] == []
    assert out["total"] == 1, "目录是有的（total 反映真实条目数）"
    assert out["reason"] == "empty_query"
    assert "query" in out["hint"]


def test_s232_correct_param_name_still_returns_candidates(warm):
    """S232 反向锁：同一目录下用正确的 query 必须出候选。"""
    out = _core.search_products({"query": "CodeArts", "limit": 3})
    assert out["candidates"] and out["candidates"][0]["id"] == "1"
    assert "reason" not in out


@pytest.mark.parametrize("host,expect_has", [
    ("hermes", True), ("codex", False), ("opencode", False),
    ("dsh", False), ("workbuddy", False), ("atomcode", False),
    ("openclaw", False), ("codeartsdoer", False), ("codeartswork", False),
    ("codex-desktop", False),
])
def test_s232_hook_layer_label_per_host(host, expect_has):
    """S232：hook 层按宿主如实报，未知/未注册一律按"无"（宁可低估不虚报）。"""
    label = _hm.hook_layer_label(host)
    assert (label.startswith("有") is True) == expect_has, (host, label)
    assert "软约束" in label or label.startswith("有")


def test_s232_hook_layer_unknown_host_defaults_to_none():
    assert _hm.hook_layer_label("some-new-host").startswith("无")