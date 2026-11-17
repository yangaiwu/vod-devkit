"""插件 MCP 清单形态（D-mcp-manifest-a3-1）与 codex 改写失败分类的用例。

结论先行（2026-11-15 codex 0.167.0 实测，证据见 docs/design.md 同名节）：
- 规范承诺的 `${PLUGIN_ROOT}` 展开与「cwd = 插件根」**未落地到这个二进制**：
  args 里原样收到字面量 `${PLUGIN_ROOT}`，cwd 是 `~/.codex`，PLUGIN_ROOT/PLUGIN_DATA
  也没注入环境。把插件包迁到 Agent Plugins 格式（根 plugin.json + mcp.json）后，
  该 MCP 条目在 0.167 下**根本没注册**（`codex mcp list` 为空）。
- 因此静态清单只能保留 CLI 形态（`vod-devkit serve`）——它是唯一实测能跑通的入口，
  代价是 PATH 上那份 CLI 的版本（旧版静默运行，0.4.2 实锤）不可控。
- 运行时正确性因此**必须由安装器改写承担**：`codex plugin add` 之后把缓存内
  .mcp.json 改写成「绝对解释器 + 载荷副本」，并读回验证。

用例承载：
  S111 静态清单形态（实测锁定 + 规范字段补全，附"为什么不是 ${PLUGIN_ROOT}"）
  S112 运行时形态由改写保证（绝对解释器 + 载荷路径，不含字面量占位符）
  S113 无 env 时工具面 = 历史默认（全 packs），不会静默收缩
  S114 改写失败分类（bad-json / not-writable warn，读回不一致 fail）
"""
import json
from pathlib import Path

import pytest

from vod_mcp import packs
from vod_mcp.host_adapters import codex

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "plugins" / "vod-devkit" / ".mcp.json"

SCHEMA = "agent-plugins.org/schemas/1.0.0/mcp.schema.json"
RESERVED = ("PLUGIN_ROOT", "PLUGIN_DATA")


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _server() -> dict:
    return _manifest()["mcpServers"]["vod-devkit"]


# ── S111 静态清单形态 ─────────────────────────────────────

def test_s111_schema_and_type_present():
    mj = _manifest()
    assert mj["$schema"] == SCHEMA, "Agent Plugins 规范要求 $schema 必填且为约定值"
    assert set(mj) == {"$schema", "mcpServers"}, "规范只允许这两个顶层字段"
    assert _server()["type"] == "stdio"


def test_s111_static_form_is_cli_because_expansion_not_implemented():
    """静态形态锁定 CLI：codex 0.167 实测 ${PLUGIN_ROOT} 不展开、cwd 非插件根。

    这条断言**不是偏好**，是实测结论的可执行记录。哪天 codex 支持了保留变量，
    这里的用例先红 → 再按 S112 的改写产物形态评估切回 ${PLUGIN_ROOT}。
    """
    srv = _server()
    assert srv["command"] == "vod-devkit" and srv["args"] == ["serve"]
    # 清单里出现保留变量而版本不支持展开 = 宿主收到字面量（静默坏），禁止写
    blob = json.dumps(srv, ensure_ascii=False)
    assert "${" not in blob, "0.167 不展开保留变量；写了就是字面量透传"


def test_s111_packs_default_is_explicit():
    """静态清单保留 packs 显式默认值：删成缺省会让工具面按代码默认（全 packs）放开。"""
    assert _server()["env"]["VOD_PACKS"] == "core,collect"


def test_s111_rewrite_entrypoint_exists():
    """运行时正确性靠改写——别以为静态清单能自足就拆掉 codex.py 的改写逻辑。"""
    src = (ROOT / "src" / "vod_mcp" / "host_adapters" / "codex.py").read_text(encoding="utf-8")
    assert "rewrite_plugin_mcp(" in src and "server_entry()" in src


# ── S112 运行时形态由改写保证 ───────────────────────────────

def test_s112_rewrite_produces_absolute_interpreter_and_payload(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text(MANIFEST.read_text(encoding="utf-8"), encoding="utf-8")
    got = codex.rewrite_plugin_mcp(p, python="/usr/bin/python3.12",
                                   entry="/payload/vod_mcp/server.py",
                                   env={"VOD_PACKS": "core", "VOD_JAVA_API_BASE": "http://x"})
    assert got["command"] == "/usr/bin/python3.12", "PATH 名不得留在运行时形态里"
    assert got["args"] == ["/payload/vod_mcp/server.py"]
    assert not any("${" in a for a in got["args"]), "占位符必须已在装机形态中消解"
    assert got["env"]["VOD_PACKS"] == "core"
    on_disk = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["vod-devkit"]
    assert on_disk == got, "写成功必须等于落盘内容（读回验证）"


def test_s112_reserved_vars_are_documented_not_used():
    """保留变量名只在文档里出现（S111 引用的实测结论），清单本体不得使用。"""
    assert RESERVED, "保留变量清单是规范知识，保留在此便于将来切回"
    assert "${" not in MANIFEST.read_text(encoding="utf-8")


# ── S113 无 env 时工具面不收缩 ──────────────────────────────

def _tool_names(env_extra: dict) -> set:
    from probe import Probe
    p = Probe(env_extra=env_extra)
    try:
        return {t["name"] for t in p.list_tools()}
    finally:
        p.close()


def test_s113_default_env_matches_historical_default(tmp_path):
    """VOD_PACKS 缺省 = 全 packs（packs.enabled_packs 的空值语义）；
    静态清单里显式写 core,collect 是**有意收窄**，不是兜底。"""
    expected = {t for pack in packs.ALL_PACKS for t in packs.PACK_TOOLS[pack]}
    # HOME 指向临时目录：熔断标记在 ~/.codex 下，真机存在会摘掉 collect（S109 同款环境无关）
    got = _tool_names({"HOME": str(tmp_path), "VOD_PACKS": ""})
    assert got == expected


def test_s113_explicit_narrowing_is_respected(tmp_path):
    expected = {t for pack in ("core", "collect") for t in packs.PACK_TOOLS[pack]}
    got = _tool_names({"HOME": str(tmp_path), "VOD_PACKS": "core,collect"})
    assert got == expected
    assert "vod_list_skills" not in got


# ── S114 codex 改写失败分类 ─────────────────────────────────

def _static_manifest(tmp_path: Path) -> Path:
    p = tmp_path / ".mcp.json"
    p.write_text(json.dumps({
        "$schema": SCHEMA,
        "mcpServers": {"vod-devkit": {
            "type": "stdio", "command": "vod-devkit", "args": ["serve"],
            "env": {"VOD_PACKS": "core,collect"}}}}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return p


def test_s114_rewrite_ok_reads_back_absolute_form(tmp_path):
    p = _static_manifest(tmp_path)
    got = codex.rewrite_plugin_mcp(p, python="/usr/bin/python3.12",
                                   entry="/payload/vod_mcp/server.py",
                                   env={"VOD_PACKS": "core", "VOD_JAVA_API_BASE": "http://x"})
    assert got["command"] == "/usr/bin/python3.12"
    assert got["args"] == ["/payload/vod_mcp/server.py"]
    assert got["env"]["VOD_PACKS"] == "core"
    on_disk = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["vod-devkit"]
    assert on_disk == got


def test_s114_bad_json_is_classified(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(codex.PluginMcpRewriteError) as e:
        codex.rewrite_plugin_mcp(p, python="/py", entry="/s.py")
    assert e.value.kind == "bad-json"
    assert codex.PluginMcpRewriteError.REMEDY.get("bad-json")


def test_s114_missing_entry_is_classified(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    with pytest.raises(codex.PluginMcpRewriteError) as e:
        codex.rewrite_plugin_mcp(p, python="/py", entry="/s.py")
    assert e.value.kind == "bad-json"


def test_s114_readonly_classified_not_fatal(tmp_path, monkeypatch):
    """只读/权限这类不该判死安装（插件仍装在宿主里），只给分类补救指引。"""
    p = _static_manifest(tmp_path)

    # S179 起写走 paths.atomic_write_text（tmp+replace），不再经 Path.write_text：
    # 权限类故障的注入点随之改到原子写入口
    from vod_mcp import paths as _paths

    def boom(path, text, *a, **kw):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(_paths, "atomic_write_text", boom)
    with pytest.raises(codex.PluginMcpRewriteError) as e:
        codex.rewrite_plugin_mcp(p, python="/py", entry="/s.py")
    assert e.value.kind == "not-writable"
    assert codex.PluginMcpRewriteError.REMEDY.get("not-writable")


def test_s114_verify_mismatch_is_hard_fail(tmp_path, monkeypatch):
    """读回与期望不一致 = 半写状态留给宿主，必须让安装失败。"""
    p = _static_manifest(tmp_path)
    from vod_mcp import paths as _paths
    real_write = _paths.atomic_write_text

    def tampered(path, text, *a, **kw):
        real_write(path, text, *a, **kw)
        real_write(path, json.dumps({"mcpServers": {"vod-devkit": {
            "command": "vod-devkit", "args": ["serve"]}}}), *a, **kw)

    monkeypatch.setattr(_paths, "atomic_write_text", tampered)
    with pytest.raises(RuntimeError) as e:
        codex.rewrite_plugin_mcp(p, python="/py", entry="/s.py")
    assert "验证不通过" in str(e.value)


def test_s114_every_raised_kind_has_remedy():
    """新增分类必须同时给补救指引，否则 install 会打出 '见 INSTALL.md' 的空话。"""
    src = (ROOT / "src" / "vod_mcp" / "host_adapters" / "codex.py").read_text(encoding="utf-8")
    kinds = {chunk.split('"')[0] for chunk in src.split('PluginMcpRewriteError("')[1:]}
    assert kinds, "至少要有一个分类"
    assert kinds <= set(codex.PluginMcpRewriteError.REMEDY)


# ── S115 doctor 能报"实际跑的是哪一种" ──────────────────────

def _form_file(tmp_path: Path, srv: dict) -> Path:
    p = tmp_path / ".mcp.json"
    p.write_text(json.dumps({"mcpServers": {"vod-devkit": srv}}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def test_s115_form_payload_when_absolute(tmp_path):
    p = _form_file(tmp_path, {"command": "/usr/bin/python3.12",
                             "args": ["/payload/vod_mcp/server.py"]})
    kind, srv = codex.plugin_mcp_form(p)
    assert kind == "payload" and srv["command"] == "/usr/bin/python3.12"


def test_s115_form_cli_when_bare_name(tmp_path):
    p = _form_file(tmp_path, {"command": "vod-devkit", "args": ["serve"]})
    assert codex.plugin_mcp_form(p)[0] == "cli", "CLI 形态=版本不确定，doctor 必须报出来"


def test_s115_form_placeholder_when_unexpanded(tmp_path):
    p = _form_file(tmp_path, {"command": "python3",
                              "args": ["${PLUGIN_ROOT}/vod_mcp/server.py"]})
    assert codex.plugin_mcp_form(p)[0] == "placeholder"


def test_s115_form_unreadable_when_broken(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text("{oops", encoding="utf-8")
    assert codex.plugin_mcp_form(p)[0] == "unreadable"


def test_s115_doctor_actually_reports_the_form():
    """文档写了"doctor 可查实际形态"——这句必须有用例兜着，否则是空话。"""
    src = (ROOT / "src" / "vodkit_cli" / "doctor.py").read_text(encoding="utf-8")
    assert "plugin_mcp_form(" in src
    assert "codex 插件 MCP 形态" in src