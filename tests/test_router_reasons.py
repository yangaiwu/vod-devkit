"""S223：判据的原因标签必须与文档同步（词表路线的可审计性）。"""
from pathlib import Path

import importlib.util

_HOOK = Path(__file__).resolve().parent.parent / "integrations" / "hermes" / "hooks" / "vod_router.py"
_spec = importlib.util.spec_from_file_location("vod_router_under_test", _HOOK)
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)


def test_s223_every_reason_is_declared():
    assert router.route_detail("")["reason"] == "empty"
    assert router.route_detail("[PRIOR CONTEXT — x] nothing")["reason"] == "envelope"
    assert router.route_detail("提交反馈：网页白屏")["reason"] == "strong-prefix"
    assert router.route_detail("今天天气不错")["reason"] == "no-trigger"
    assert router.route_detail("建议增加一条门禁用例")["reason"] == "meta-discussion"
    assert router.route_detail("缓存丢了")["reason"] == "engineering-object"
    assert router.route_detail("这个功能今天直接挂了")["reason"] == "disable"
    assert router.route_detail("页面老是报错")["reason"] == "trigger"


def test_s223_reason_set_matches_declared_tuple():
    seen = set()

    class _Capture(dict):
        pass

    probes = ["", "[PRIOR CONTEXT — x] y", "提交反馈：白屏", "今天天气不错",
              "建议增加一条门禁用例", "缓存丢了", "这个功能今天直接挂了", "页面老是报错"]
    for p in probes:
        seen.add(router.route_detail(p)["reason"])
    assert seen == set(router.REASONS), (sorted(seen), sorted(router.REASONS))


def test_s223_reasons_documented_in_design():
    doc = (Path(__file__).resolve().parent.parent / "docs" / "design.md").read_text(encoding="utf-8")
    missing = [r for r in router.REASONS if f"`{r}`" not in doc]
    assert not missing, f"design.md 未登记的原因标签：{missing}"
