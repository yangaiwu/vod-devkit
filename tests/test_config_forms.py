"""宿主配置文件形态守卫的单元锁（vod_mcp/config_forms.py）。

针对三类实锤事故的形态层回归：
1. TOML 只删父表 → 残留 `[mcp_servers.vod-devkit.env]` 在 TOML 语义里重建
   父表 = 装出一个没有 command 的假 server（本次修复的残留 bug）。
2. `args = [ ... ]` 多行数组 → 旧正则断块，块边界必须按表头走而非按行内括号。
3. YAML 打平/tab 缩进/flow 根/重复块 → 全是"改完更糟"的形态，一律拒绝。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vod_mcp import config_forms as cf  # noqa: E402


TOML_FIXTURE = """model = "gpt-5"

[mcp_servers.vod-devkit]
command = "python3"
args = [
  "/opt/server.py",
]

[mcp_servers.vod-devkit.env]
VOD_PACKS = "core,collect"

[mcp_servers.other]
command = "z"
"""


def test_toml_strip_removes_parent_and_child_tables():
    cleaned, removed = cf.strip_managed_toml(TOML_FIXTURE)
    assert "vod-devkit" not in cleaned, "子表残留会在 TOML 语义里重建父表"
    assert sorted(removed) == ["mcp_servers.vod-devkit", "mcp_servers.vod-devkit.env"]
    assert 'model = "gpt-5"' in cleaned
    assert "[mcp_servers.other]" in cleaned and 'command = "z"' in cleaned


def test_toml_multiline_array_does_not_break_block_boundary():
    """多行数组的 `]` 行不能被当表头；块尾必须落在下一个真表头。"""
    text = ('[mcp_servers.vod-devkit]\ncommand = "p"\nargs = [\n  "a",\n  "b",\n]\n\n'
            '[mcp_servers.keep]\ncommand = "k"\n')
    cleaned, removed = cf.strip_managed_toml(text)
    assert removed == ["mcp_servers.vod-devkit"]
    assert cleaned.strip() == '[mcp_servers.keep]\ncommand = "k"'
    assert '"a"' not in cleaned and '"b"' not in cleaned


def test_toml_duplicate_header_is_refused():
    text = '[mcp_servers.vod-devkit]\ncommand = "a"\n[mcp_servers.vod-devkit]\ncommand = "b"\n'
    verdict, reason = cf.classify_codex_toml(text)
    assert verdict == "refuse" and "重复" in reason


def test_toml_malformed_header_raises_refused():
    with pytest.raises(cf.Refused):
        cf.classify_codex_toml('[mcp_servers.vod-devkit\ncommand = "a"\n')


def test_toml_unrelated_prefix_not_touched():
    """`vod-devkit2` 这类相邻表名不能被前缀匹配误删。"""
    text = '[mcp_servers.vod-devkit2]\ncommand = "x"\n'
    cleaned, removed = cf.strip_managed_toml(text)
    assert removed == []
    assert cleaned == text.rstrip()


def test_yaml_accepts_nested_and_flat_blocks():
    nested = ["- insert:", "    - id: vod-devkit", "      name: dsh-vod-devkit", ""]
    flat = ["- id: vod-devkit", "  name: dsh-vod-devkit", ""]
    for lines in (nested, flat):
        assert cf.classify_dsh_patch(lines) == ("ok", "")
        start, end = cf.find_dsh_block(lines)
        assert start is not None and end > start


def test_yaml_refuses_tab_indent():
    verdict, reason = cf.classify_dsh_patch(["- insert:", "\t- id: vod-devkit"])
    assert verdict == "refuse" and "tab" in reason


def test_yaml_refuses_mapping_root():
    verdict, reason = cf.classify_dsh_patch(["plugins:", "  - x"])
    assert verdict == "refuse" and "映射" in reason


def test_yaml_refuses_flow_root():
    verdict, reason = cf.classify_dsh_patch(['{"a": 1}'])
    assert verdict == "refuse" and "flow" in reason
    # 字面量 [] 占位是历史模板形态，允许（upsert 会清理）
    assert cf.classify_dsh_patch(["[]", "- insert:", "    - id: vod-devkit"])[0] == "ok"


def test_yaml_refuses_duplicate_managed_blocks():
    verdict, reason = cf.classify_dsh_patch(
        ["- id: vod-devkit", "  name: a", "- id: vod-devkit", "  name: b"])
    assert verdict == "refuse" and "多个" in reason


def test_yaml_empty_file_is_ok():
    assert cf.classify_dsh_patch([]) == ("ok", "")
    assert cf.find_dsh_block([]) == (None, None)