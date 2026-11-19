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

# --- S204：把绑定兜在模型**实际会走的那一步**（实测服从性天花板）-----------------
# 现场：0.5.32 + 最新 SKILL（含「第一步永远是看本机绑定」）跑 C1，模型连续两轮都跳过
# vod_devkit_info 直接 vod_search_products（score 0.0 / catalog-default）后追问；
# 但同一条 prompt 让它「原样背出技能第 0 步前两行」时，它能一字不差背出来——说明它**读得到**
# 纪律，只是在任务里按自己的计划走。对这种服从性天花板，话术再加一句没有用，
# 兜住它实际会调的那个工具：search_products 回执带上本机绑定 + 一句 nextStep。
def test_s204_search_products_carries_install_binding(monkeypatch):
    from vod_mcp.packs import core
    monkeypatch.setattr(core.provenance, "install_binding", lambda: "CodeArts")
    monkeypatch.setattr(core.net, "_load_meta",
                        lambda: {"catalog": [{"id": "1", "name": "CodeArts"},
                                             {"id": "2", "name": "AgentArts"}]})
    out = core.search_products({"query": "批量导入"})
    assert out["installBinding"] == "CodeArts", out
    assert "不要再追问" in out["nextStep"], out["nextStep"]
    assert out["candidates"], "候选仍要照给（用户真需要选时用）"


def test_s204_no_binding_means_no_hint(monkeypatch):
    from vod_mcp.packs import core
    monkeypatch.setattr(core.provenance, "install_binding", lambda: None)
    monkeypatch.setattr(core.net, "_load_meta", lambda: {"catalog": [{"id": "1", "name": "X"}]})
    out = core.search_products({"query": "批量导入"})
    assert "installBinding" not in out and "nextStep" not in out, \
        "没绑定就不要给药方（缺证据仍按纪律先问一次）"


# --- S208：nextStep 不许复制自指词表（第三处副本会收窄模型行为）-------------------
# 评审实测：core.py 的 nextStep 硬编码「你们家/这个产品/本平台」三个例子，而真源
# attribution.SELF_REFERENCE 有 16 个。模型很可能把这 3 个当穷举 → 行为变窄；
# 而 S190 立过「不许复制自指词表」的纪律，这里没有锁。
def test_s208_next_step_does_not_duplicate_self_reference_table():
    from vod_mcp import attribution
    from vod_mcp.packs import core
    import unittest.mock as m

    with m.patch.object(core.provenance, "install_binding", lambda: "CodeArts"), \
         m.patch.object(core.net, "_load_meta",
                        lambda: {"catalog": [{"id": "1", "name": "CodeArts"}]}):
        out = core.search_products({"query": "批量导入"})
    hint = out["nextStep"]
    leaked = [w for w in attribution.SELF_REFERENCE if w in hint]
    assert not leaked, f"nextStep 复制了自指词表举例（第二真源）：{leaked}"


# --- S209：工具回执字段必须在契约里登记 -------------------------------------------
# 评审实测：契约 vod_search_products.output 只有 candidates/total，S204 新增的
# installBinding/nextStep 没登记——该文件自称「python/MCP 单一事实源」，账面缺字段且无门禁。
def test_s209_contract_registers_every_search_products_field():
    import json
    from pathlib import Path
    from vod_mcp.packs import core
    import unittest.mock as m

    contract = json.loads((Path(__file__).resolve().parent.parent
                           / "assets" / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
    props = contract["tools"]["vod_search_products"]["output"]["properties"]
    with m.patch.object(core.provenance, "install_binding", lambda: "CodeArts"), \
         m.patch.object(core.net, "_load_meta",
                        lambda: {"catalog": [{"id": "1", "name": "CodeArts"}]}):
        returned = set(core.search_products({"query": "x"}))
    assert returned <= set(props), f"回执字段未登记进契约：{sorted(returned - set(props))}"
    for k in ("installBinding", "nextStep"):
        assert k in props, f"契约缺 {k}"

# ---- ARCH-BLD-04：根 build-info 快照落后 HEAD 时，安装账本必须记下真实 HEAD ----

def test_install_manifest_records_worktree_head_when_snapshot_lags(tmp_path, monkeypatch):
    """台账点名的验收断言：快照 ≠ HEAD 时，manifest 要**两个值都记**，
    且 `snapshotLagsHead` 为真 —— 否则运维按 commitSha 对账会对到发版快照，
    而不是"实际装进去的代码"（BLD-04 实锤：0.5.44 快照落后 HEAD 三个提交）。

    不跑真实 git：直接对 `_write_install_manifest` 的字段组装逻辑做单元验证，
    用桩替换 build-info 文件与 git 调用，避免依赖当前检出的分支状态。
    """
    import json as _json
    from types import SimpleNamespace

    from vodkit_cli import common

    snap_sha, head_sha = "a" * 40, "b" * 40
    (tmp_path / "build-info.json").write_text(_json.dumps({
        "version": "0.5.45", "commitSha": snap_sha,
        "builtAt": "2026-11-19T00:00:00", "sourceRemote": "git@example:x/y.git",
        "snapshot": "released",
    }), encoding="utf-8")
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setenv("VOD_DEVKIT_MANIFEST", str(tmp_path / "install-manifest.json"))

    real_run = common.subprocess.run

    class _P:
        def __init__(self, out=""):
            self.stdout, self.returncode = out, 0

    def _fake_run(cmd, *a, **kw):
        # `git rev-parse HEAD` → 工作树真值；`--abbrev-ref HEAD` → 分支名
        if list(cmd[:3]) == ["git", "rev-parse", "HEAD"]:
            return _P(head_sha + "\n")
        if "HEAD" in cmd and "--abbrev-ref" in cmd:
            return _P("dev\n")
        if "tag" in cmd or "branch" in cmd:
            return _P("")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(common.subprocess, "run", _fake_run)

    args = SimpleNamespace(target="hermes", preset=None)
    common._write_install_manifest(args, "hermes", ["core"], None, None, [],
                                   transport="stdio", payload_dir=str(tmp_path / "payload"))

    mf = _json.loads((tmp_path / "install-manifest.json").read_text(encoding="utf-8"))
    src = mf["source"]
    assert src["commitSha"] == snap_sha, "commitSha 仍应是 build-info 快照里的提交"
    assert src["worktreeHead"] == head_sha, "必须记录安装时真实工作树 HEAD"
    assert src["snapshotLagsHead"] is True, "快照 ≠ HEAD 必须标记为落后"
    assert src["snapshot"] == "released", "快照来源标记应透传 build-info 的 snapshot"
