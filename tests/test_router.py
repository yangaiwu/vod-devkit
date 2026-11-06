"""H1-H4：强制评估路由回归锁（vod-feedback-router/router.route 纯函数）。

场景（docs/hermes-router.md §用例）：
- H1 显式前缀「提交反馈：」→ 强指令（确定性短路，100%）
- H2 口语抱怨变体（体验差/太慢/卡/报错/希望支持）→ 采集指令
- H3 普通对话/操作请求 → 零注入（不刷屏）
- H4 边界：空/非字符串消息 → None
"""
import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "vod_router",
    Path(__file__).resolve().parent.parent / "hermes-plugin" / "vod-feedback-router" / "router.py")
assert _SPEC is not None and _SPEC.loader is not None, "router.py 缺失"
router = importlib.util.module_from_spec(_SPEC)
sys.modules["vod_router"] = router
_SPEC.loader.exec_module(router)


def test_h1_explicit_prefix_strong_directive():
    out = router.route("提交反馈：网页卡顿")
    assert out is not None and "提交反馈" in out and "无需再判断意图" in out
    # 前缀出现在句中也命中（口语场景）
    assert router.route("帮我提交反馈 体验很差") is not None


def test_h2_complaint_variants_directive():
    for msg in ("体验不好", "太慢了", "网页卡", "老是报错", "希望支持深色模式",
                "为什么不能导出", "产品体验很差劲"):
        out = router.route(msg)
        assert out is not None, msg
        assert "vod-feedback-collect" in out
        assert "禁止询问产品归属" in out


def test_h3_ordinary_messages_zero_injection():
    for msg in ("帮我部署一下服务", "grape 的 MR 合了吗", "看下日志",
                "把这段代码重构一下", "今天天气怎么样"):
        assert router.route(msg) is None, msg


def test_h4_edge_inputs():
    assert router.route(None) is None
    assert router.route("") is None
    assert router.route("   ") is None
    assert router.route(12345) is None
