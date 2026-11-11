"""技能披露第二轨（vod_list_skills / vod_retrieve_skill）的回归锁。

设计动机：领域规则技能此前只有"拷进宿主技能目录"一条分发路径，四份副本
各自漂移（D-drift-lock 事后才抓得到）。披露工具让技能文本成为 server data，
同时必须守住两条边界：不新增上游调用、与 pack 裁剪一致（知识包被裁时拒绝
并给恢复命令，绝不静默返回空内容）。
"""
import pytest

from vod_mcp import packs, tools

RULE_SKILLS = ("vod-problem-classification-rules", "vod-scoring-rules")


def test_list_skills_reports_pack_and_native_flags(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core,collect,knowledge")
    out = tools.dispatch("vod_list_skills", {})
    names = {s["name"] for s in out["skills"]}
    assert set(RULE_SKILLS) | {"vod-core", "vod-feedback-collect"} == names
    by = {s["name"]: s for s in out["skills"]}
    assert by["vod-core"]["native"] is True
    assert by["vod-problem-classification-rules"]["native"] is False
    assert by["vod-problem-classification-rules"]["pack"] == "knowledge"
    assert by["vod-problem-classification-rules"]["enabled"] is True
    assert by["vod-scoring-rules"]["description"], "描述抽不出来=路由信息丢失"


def test_retrieve_skill_returns_full_text(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core,knowledge")
    out = tools.dispatch("vod_retrieve_skill", {"name": "vod-scoring-rules"})
    assert out["pack"] == "knowledge" and out["truncated"] is False
    assert out["content"].startswith("---"), "必须返回 SKILL.md 原文（含 frontmatter）"
    assert "name: vod-scoring-rules" in out["content"]


def test_retrieve_refuses_when_pack_trimmed(monkeypatch):
    """pack 裁剪时拒绝并给恢复命令——静默返回空内容会让模型以为规则不存在。"""
    monkeypatch.setenv("VOD_PACKS", "core,collect")
    with pytest.raises(tools.ToolError) as ei:
        tools.dispatch("vod_retrieve_skill", {"name": "vod-scoring-rules"})
    assert ei.value.code == -32010
    assert "--packs" in str(ei.value), "拒绝必须带可执行的恢复指引"


def test_retrieve_unknown_name_lists_available(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core,knowledge")
    with pytest.raises(tools.ToolError) as ei:
        tools.dispatch("vod_retrieve_skill", {"name": "vod-category-matching"})
    assert ei.value.code == -32602
    assert "vod-scoring-rules" in str(ei.value), "未知技能要把可用清单带回去"


@pytest.mark.parametrize("bad", ["", "  ", "../etc/passwd", "/etc/passwd",
                                 "vod-scoring-rules/../x", "VOD-SCORING"])
def test_retrieve_rejects_bad_names(monkeypatch, bad):
    """路径穿越/大小写/空名一律拒——技能名是白名单式的标识，不是自由路径。"""
    monkeypatch.setenv("VOD_PACKS", "core,knowledge")
    with pytest.raises(tools.ToolError):
        tools.dispatch("vod_retrieve_skill", {"name": bad})


def test_disclosure_tools_are_gated_by_knowledge_pack(monkeypatch):
    monkeypatch.setenv("VOD_PACKS", "core")
    names = [s["name"] for s in tools.tool_specs(packs.enabled_tools())]
    assert "vod_list_skills" not in names and "vod_retrieve_skill" not in names
    monkeypatch.setenv("VOD_PACKS", "core,knowledge")
    names = [s["name"] for s in tools.tool_specs(packs.enabled_tools())]
    assert "vod_list_skills" in names and "vod_retrieve_skill" in names


def test_disclosure_is_network_free(monkeypatch):
    """披露工具必须零上游调用——任何 _http 打点都算设计错误。"""
    def boom(*a, **k):
        raise AssertionError("披露工具不应发起 HTTP 调用")
    monkeypatch.setattr(tools, "_http", boom)
    monkeypatch.setenv("VOD_PACKS", "core,knowledge")
    tools.dispatch("vod_list_skills", {})
    tools.dispatch("vod_retrieve_skill", {"name": "vod-problem-classification-rules"})