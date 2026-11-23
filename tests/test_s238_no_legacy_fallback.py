"""S238：删除过渡期老链回落（/external/voice/submit），囤积端点即唯一提交路径。

为什么要删（2026-11-18 负责人拍板）：
- 引擎已上线囤积端点（实测 201 + productRegistered），404 回落是死代码；
- 两套语义并存会让同一插件在不同引擎上行为不同：囤积=延迟分析（deferred），
  老链=提交即分析。用户看到的回执、账本字段、分析时机都会分叉；
- 老链还带一套独立的 voiceId 生成/source 命名空间逻辑，是第二份真源。

现口径：404 → ToolError(-32016)，明确「本条未提交」，不假装成功、不偷偷换链。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vod_mcp import net as _net          # noqa: E402
from vod_mcp.packs import collect as _collect  # noqa: E402



def _collect_src() -> str:
    """collect 已拆包（ARCH-CALL-04）：把包内全部模块拼成一份源码供文本断言用。"""
    root = ROOT / "src" / "vod_mcp" / "packs" / "collect"
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.glob("*.py")))

def test_s238_source_has_no_legacy_endpoint():
    """源码里不许再出现老链常量与回落分支（防止回流）。"""
    src = _collect_src()
    assert "_EXISTING_SUBMIT" not in src, "老链常量回流"
    assert "legacy-fallback" not in src, "老链回落分支回流"
    # 允许注释/文案里提"老链"，但**不许有实际调用**（HTTP POST 到老链）
    assert not any("_http(" in ln and "voice/submit" in ln for ln in src.splitlines()), \
        "仍有对老链的 HTTP 调用"


def test_s238_hoarding_404_is_explicit_failure(monkeypatch):
    """囤积端点 404 → -32016 且明说未提交；不得改调老链。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    seen = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        seen.append(path)
        raise _net.ToolError("上游返回 404: not found", code=404)

    monkeypatch.setattr(_net, "_http", fake_http)
    with pytest.raises(_net.ToolError) as ei:
        _collect.submit_voices({"voices": [{"content": "反馈内容足够长的一条意见"}],
                                "product": "codearts", "confirmed": True},
                               client_info={"name": "t"})
    assert ei.value.code == -32016
    assert "未提交" in str(ei.value)
    assert not any("voice/submit" in p for p in seen), f"仍调了老链：{seen}"


def test_s238_happy_path_still_hoarding_only(monkeypatch):
    """正常路径只打 /external/voices 一次，回执 path=hoarding、analysis=deferred。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    seen = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        seen.append(path)
        return {"code": 200, "voiceIds": ["VDPL-1"], "productRegistered": True}

    monkeypatch.setattr(_net, "_http", fake_http)
    out = _collect.submit_voices({"voices": [{"content": "导出总是失败，重试也不行"}],
                                  "product": "codearts", "confirmed": True},
                                 client_info={"name": "t"})
    assert out["path"] == "hoarding" and out["analysis"] == "deferred"
    assert out["voiceIds"] == ["VDPL-1"]
    assert [p for p in seen if "/external/" in p] and all(
        p.endswith("/external/voices") for p in seen if "/external/" in p)