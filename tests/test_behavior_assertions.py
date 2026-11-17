"""行为回归的判定口径单测（S182）：改写 vs 截断 vs 回显缺失/残断。

为什么要有：这些判据此前只活在 `e2e_behavior.py` 的 run_case 里，靠真机 + 引擎 502 好着
才能验；而「原话被改写」这句报文把三种不同故障混成一句（引擎截断、窗口内改写、回显只给开头），
复盘时无法归因。这里把判定抽成纯函数，逐个口径对死。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"加载失败：{path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # e2e_behavior 里 `from e2e_suite import ...` 需要它可见
    spec.loader.exec_module(mod)
    return mod


_suite = _load("e2e_suite_mod", ROOT / "scripts" / "e2e_suite.py")
_beh = _load("e2e_behavior_mod", ROOT / "scripts" / "e2e_behavior.py")

W = _beh.VERBATIM_WINDOW
FULL = ("试着用你们家的批量导入功能，把我折腾惨了，导到一半卡死，进度条也不动，"
        "等了十分钟只能重来，重新导又提示格式错误，来来回回搞了一下午")


def test_s182_render_offset_marks_content_start():
    """模板标记法：offset 落在原话起点，不靠静态片段搜索（模板改动不会漂移）。"""
    case = next(c for c in _suite.SUITE if c["id"] == "C1-verbatim-long")
    text, off = _suite.render_with_offset(case, "11-17 12:00:00")
    assert "{content_start}" not in text, "标记必须被移除"
    assert off > 0 and text[off:].startswith("试着用你们家的批量导入功能"), text
    assert text[:off].endswith("11-17 12:00:00"), "offset 之前的只有命令前缀+盐"


def test_s182_truncation_is_not_rewrite():
    """case1 纯截断：引擎只回窗口内前 40 字 → 改写判据 PASS；回显只给 40 字 → incomplete。"""
    ref = FULL[:W]
    engine = ref[:40]
    assert _beh.content_not_paraphrased(ref, engine) is True
    assert _beh.echo_status("已收录原话：" + engine, FULL, ref) == "incomplete"


def test_s182_one_char_rewrite_in_window_fails():
    """case2 窗口内一字改写（实测形态：「重新导又」→「重新导入又」）→ 改写判据红。"""
    ref = FULL[:W]
    engine = ref[:57] + "入" + ref[58:]
    assert _beh.content_not_paraphrased(ref, engine) is False


def test_s182_exact_content_and_full_echo_pass():
    """case3 完全一致：内容判据双绿（引擎=窗口、回复含全文）。"""
    ref = FULL[:W]
    assert _beh.content_not_paraphrased(ref, ref) is True
    assert _beh.echo_status("已收录原话：" + FULL, FULL, ref) == "ok"


def test_s182_rewrite_beyond_window_is_allowed():
    """case4 窗口之外的差异不判：引擎只回窗口长度，回显给全文 → 双绿。"""
    full = "甲" * (W + 20)
    ref = full[:W]
    engine = ref
    assert _beh.content_not_paraphrased(ref, engine) is True
    assert _beh.echo_status("已收录原话：" + full, full, ref) == "ok"


def test_s182_empty_and_whitespace_are_guarded():
    """case5 空/空白输入不崩：空引擎内容判改写；空原话的回显要求放行。"""
    ref = FULL[:W]
    assert _beh.content_not_paraphrased(ref, "") is False
    assert _beh.content_not_paraphrased(ref, "   ") is False
    assert _beh.echo_status("任意回复", "", "") == "ok"
    assert _beh.echo_status("   ", FULL, ref) == "missing"


def test_s182_normalization_is_strip_and_newline_only():
    """归一化边界：首尾空白/CRLF 容忍，内部空白不被折叠（否则会掩盖吃空格的真问题）。"""
    assert _beh.norm_text("  a b\r\nc  ") == "a b\nc"
    assert _beh.norm_text("a  b") == "a  b"