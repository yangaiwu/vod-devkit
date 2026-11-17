"""S196：安装期绑定必须**可观测**，否则「自指命中就别问产品」这条话术不可执行。

真机实证（2026-11-17，0.5.31 含 S191 话术）：C1 原话「……试着用你们家的批量导入功能……」，
装机副本确认含「自指命中 → 先验生效，别再问产品」那句（grep 命中 1），模型却仍问
「这条是哪个产品的反馈？」。代码侧一切正常——state 里 `product=CodeArts`，
`attribution.attribute()` 直判 `source=install_binding`。缺的是**模型拿不到这个事实**：
`vod_devkit_info` 的 `manifestSummary` 只有 target/installedAt/source，没有绑定产品，
模型于是保守追问（追问是纪律的合法动作，但它把正向用例永远卡在提交前）。

判据：`vod_devkit_info` 必须回出本机安装绑定产品；来源优先 runtime state（安装器写的
`cfg["product"]`），回落 manifest 里唯一的产品绑定（多产品并存 → 不回单值，避免瞎猜）。
SKILL 必须点明这个字段名，模型才知道去哪儿看。
"""
from pathlib import Path

from vod_mcp import provenance, runtime_state

_SKILL = (Path(__file__).resolve().parent.parent
          / "assets" / "skills" / "vod-feedback-collect" / "SKILL.md").read_text(encoding="utf-8")
_COMPACT = "".join(_SKILL.split())


def _manifest(products):
    return {"target": "codex", "installedAt": "2026-11-17T00:00:00",
            "source": {}, "installs": [{"target": "codex", "product": p} for p in products]}


def test_s196_binding_from_runtime_state(monkeypatch):
    monkeypatch.setattr(provenance, "read_build_info",
                        lambda: {"version": "9.9.9", "commitSha": "deadbeef"})
    monkeypatch.setattr(provenance, "read_manifest", lambda: _manifest(["CodeArts"]))
    monkeypatch.setattr(runtime_state, "_RT", {"product": "AgentArts"})
    out = provenance.info_payload()
    assert out["manifestSummary"]["product"] == "AgentArts", "state 优先（安装器写的绑定）"


def test_s196_binding_falls_back_to_unique_manifest_product(monkeypatch):
    monkeypatch.setattr(provenance, "read_build_info", lambda: {"version": "9.9.9"})
    monkeypatch.setattr(provenance, "read_manifest", lambda: _manifest(["CodeArts"]))
    monkeypatch.setattr(runtime_state, "_RT", {})
    assert provenance.info_payload()["manifestSummary"]["product"] == "CodeArts"


def test_s196_multiple_bindings_do_not_guess(monkeypatch):
    monkeypatch.setattr(provenance, "read_build_info", lambda: {"version": "9.9.9"})
    monkeypatch.setattr(provenance, "read_manifest",
                        lambda: _manifest(["CodeArts", "AgentArts"]))
    monkeypatch.setattr(runtime_state, "_RT", {})
    assert provenance.info_payload()["manifestSummary"]["product"] is None, \
        "多产品并存不许挑一个（错归污染引擎幂等域）"


def test_s196_skill_points_at_the_field():
    assert "manifestSummary.product" in _COMPACT, \
        "话术必须点名字段，否则模型不知道去哪儿看绑定"