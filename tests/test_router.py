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
    Path(__file__).resolve().parent.parent / "src" / "hooks" / "vod_router.py")
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
        assert "必须问一次" in out


def test_h3_ordinary_messages_zero_injection():
    for msg in ("帮我部署一下服务", "grape 的 MR 合了吗", "看下日志",
                "把这段代码重构一下", "今天天气怎么样"):
        assert router.route(msg) is None, msg


def test_h4_edge_inputs():
    assert router.route(None) is None
    assert router.route("") is None
    assert router.route("   ") is None
    assert router.route(12345) is None


def test_r5_long_sentence_embedded_complaint():
    """R5：长句内嵌抱怨词（非开头）→ 正则全文搜索命中。"""
    msg = ("我昨天在客户现场演示的时候打开页面等了很久才加载出来，"
           "整体响应速度也不行，同事们都觉得这个产品体验很糟糕")
    out = router.route(msg)
    assert out is not None and "vod-feedback-collect" in out


def test_r6_multiline_combined_message():
    """R6：多行组合消息（换行分隔）→ 归一后正常判定。"""
    msg = "第一行是普通描述\n体验不好\n第三行还是普通描述"
    out = router.route(msg)
    assert out is not None and "vod-feedback-collect" in out


def test_r7_regex_assembled_from_trigger_table():
    """R7：单一事实源——正则由 TRIGGER_WORDS 自动组装，无第二处硬编码。"""
    import re as _re
    expected = _re.compile("|".join(_re.escape(w) for w in router.TRIGGER_WORDS))
    assert expected.pattern == router._COMPLAINT_RE.pattern
    # 表内每个词都能命中
    for w in router.TRIGGER_WORDS:
        if w == "提交反馈":
            continue  # 前缀词走强指令分支
        assert router._COMPLAINT_RE.search(f"测试{w}场景"), w


def test_r8_shell_hook_wire_protocol(monkeypatch, capsys):
    """R8：shell hook 线协议（D-hook-unify-1）——stdin JSON → stdout {"context"}。

    旧形态是 hermes 插件（ctx.register_hook）；统一架构后脚本由宿主当子进程拉起，
    契约只剩 stdin/stdout 这一层，所以这里测的是**进程边界**而不是 import 边界。
    """
    import io
    import json as _json
    payload = {"hook_event_name": "pre_llm_call",
               "extra": {"user_message": "这个产品体验很差"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(_json.dumps(payload)))
    assert router.main() == 0
    out = capsys.readouterr().out
    assert out and _json.loads(out)["context"] == router.DIRECTIVE

    monkeypatch.setattr(sys, "stdin", io.StringIO(_json.dumps(
        {"hook_event_name": "pre_llm_call", "extra": {"user_message": "帮我看下日志"}})))
    assert router.main() == 0
    assert capsys.readouterr().out == "", "未命中必须零输出（零注入零噪音）"

    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))
    assert router.main() == 0, "坏载荷不许打断宿主这一轮"
