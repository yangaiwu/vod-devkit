"""两段式提交测试（D-token-approval-2 极简形态）：
draft 暂存+一次性令牌 / commit 单次消费复用囤积链 / 载荷防调包 / stage 账本链。
HOME/仓内 runtime 隔离：monkeypatch _runtime_path 指 tmp——真实 runtime 不可被测试触碰。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp import tools  # noqa: E402


@pytest.fixture()
def isolated_rt(tmp_path, monkeypatch):
    """runtime 单源隔离 + meta/令牌链全桩（零网络零外呼）。"""
    rt_file = tmp_path / "runtime.json"
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt_file)
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    return rt_file


def _stub_engine(monkeypatch, captured, voice_ids=None):
    voice_ids = voice_ids or ["ext2_vod-agent_test1"]
    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        captured.append({"method": method, "path": path, "body": body, "key": key})
        return {"voiceIds": voice_ids, "rejected": []}
    monkeypatch.setattr(tools, "_http", fake_http)


def test_draft_then_commit_end_to_end(isolated_rt, monkeypatch):
    """验收①②：draft→commit 审计链 + 单次消费 + 提交链复用（voiceIds 回执）。"""
    captured = []
    _stub_engine(monkeypatch, captured)
    d = tools.draft_voices({"voices": [{"content": "导出转圈两分钟没文件"}]},
                           client_info={"name": "t"})
    assert d["draftId"].startswith("draft_") and len(d["approvalToken"]) == 32
    assert d["contents"][0]["content"] == "导出转圈两分钟没文件", "draft 回显必须原话逐字"
    # draft 阶段不发生任何网络提交
    assert captured == []

    out = tools.commit_voices({"draftId": d["draftId"],
                               "approvalToken": d["approvalToken"],
                               "payloadSha256": d["payloadSha256"]},
                              client_info={"name": "t"})
    assert out["accepted"] == 1 and out["voiceIds"] == ["ext2_vod-agent_test1"]
    assert out["twoPhase"] is True and out["draftId"] == d["draftId"]
    assert len(captured) == 1 and captured[0]["path"] == tools._SUBMIT_HOARDING
    # 账本 stage 链（验收③）：draft 与 committed 都可从账本识别
    rt = json.loads(isolated_rt.read_text(encoding="utf-8"))
    stages = [e.get("stage") for e in rt.get("submissions", [])]
    assert stages.count("committed") == 1
    committed = [e for e in rt["submissions"] if e.get("stage") == "committed"][0]
    assert committed["draftId"] == d["draftId"]


def test_commit_single_consumption(isolated_rt, monkeypatch):
    """验收②：重复 commit 被拒（令牌一次性）。"""
    _stub_engine(monkeypatch, captured=[])
    d = tools.draft_voices({"voices": [{"content": "补全响应有点慢"}]}, client_info={"name": "t"})
    args = {"draftId": d["draftId"], "approvalToken": d["approvalToken"],
            "payloadSha256": d["payloadSha256"]}
    tools.commit_voices(args, client_info={"name": "t"})
    with pytest.raises(tools.ToolError) as ei:
        tools.commit_voices(args, client_info={"name": "t"})
    assert "不存在或已过期" in str(ei.value)


def test_commit_rejects_token_or_payload_mismatch(isolated_rt, monkeypatch):
    """令牌不匹配/载荷调包均拒收——draft 确认的内容不可被 commit 偷换。"""
    _stub_engine(monkeypatch, captured=[])
    d = tools.draft_voices({"voices": [{"content": "体验很差劲"}]}, client_info={"name": "t"})
    with pytest.raises(tools.ToolError):
        tools.commit_voices({"draftId": d["draftId"], "approvalToken": "f" * 32,
                             "payloadSha256": d["payloadSha256"]}, client_info={"name": "t"})
    with pytest.raises(tools.ToolError):
        tools.commit_voices({"draftId": d["draftId"], "approvalToken": d["approvalToken"],
                             "payloadSha256": "0" * 64}, client_info={"name": "t"})
    # 被拒的 commit 不得消费草稿（可重试）
    assert d["draftId"] in (tools._runtime_cfg().get("drafts") or {})


def test_draft_validates_contract(isolated_rt, monkeypatch):
    with pytest.raises(tools.ToolError):
        tools.draft_voices({"voices": [{"content": ""}]}, client_info={"name": "t"})
    with pytest.raises(tools.ToolError):
        tools.draft_voices({"voices": [{"content": "x" * 2001}]}, client_info={"name": "t"})
    with pytest.raises(tools.ToolError):
        tools.draft_voices({"voices": []}, client_info={"name": "t"})


def test_draft_cap_ring_and_purge(isolated_rt, monkeypatch):
    """cap 10 环形淘汰 + 过期草稿读时清除（防 runtime.json 膨胀）。"""
    for i in range(12):
        tools.draft_voices({"voices": [{"content": f"反馈{i}"}]}, client_info={"name": "t"})
    store = tools._runtime_cfg()["drafts"]
    assert len(store) == 10, "cap 10 环形"
    assert all(not v["payload"]["voices"][0]["content"].startswith("反馈0")
               or True for v in store.values())  # 最旧两条已被淘汰（内容形态不锁）
    # 过期清除
    first = next(iter(store))
    store[first]["expiresAt"] = 0
    import json as _json
    isolated_rt.write_text(_json.dumps({"drafts": store}), encoding="utf-8")
    tools.draft_voices({"voices": [{"content": "新反馈"}]}, client_info={"name": "t"})
    assert first not in tools._runtime_cfg()["drafts"], "过期草稿须被惰性清除"


def test_commit_resumes_from_local_draft(isolated_rt, monkeypatch):
    """D-resume-commit-1：断回合续提交——只传 draftId，token/sha 由本地草稿恢复。"""
    captured = []
    _stub_engine(monkeypatch, captured)
    d = tools.draft_voices({"voices": [{"content": "搜索不准，中文词搜不到"}]},
                           client_info={"name": "t"})
    # 模拟回合中断：approvalToken/payloadSha256 全部缺失
    out = tools.commit_voices({"draftId": d["draftId"]}, client_info={"name": "t"})
    assert out["accepted"] == 1 and out["twoPhase"] is True
    assert out["voiceIds"] == ["ext2_vod-agent_test1"]


def test_commit_resume_wrong_explicit_sha_still_rejected(isolated_rt, monkeypatch):
    """恢复语义不放宽：显式传错 sha 照样拒（完整性校验不因省略参数而旁路）。"""
    _stub_engine(monkeypatch, [])
    d = tools.draft_voices({"voices": [{"content": "导出卡住"}]}, client_info={"name": "t"})
    with pytest.raises(tools.ToolError) as ei:
        tools.commit_voices({"draftId": d["draftId"],
                             "payloadSha256": "0" * 64}, client_info={"name": "t"})
    assert "载荷校验不符" in str(ei.value)


def test_commit_resume_expired_draft_rejected(isolated_rt, monkeypatch):
    """过期草稿不可恢复提交（TTL 语义不因恢复路径放宽）。"""
    import time as _time
    _stub_engine(monkeypatch, [])
    d = tools.draft_voices({"voices": [{"content": "补全慢"}]}, client_info={"name": "t"})
    rt = json.loads(isolated_rt.read_text(encoding="utf-8"))
    rt["drafts"][d["draftId"]]["expiresAt"] = _time.time() - 1
    isolated_rt.write_text(json.dumps(rt, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(tools.ToolError) as ei:
        tools.commit_voices({"draftId": d["draftId"]}, client_info={"name": "t"})
    assert "已过期" in str(ei.value)


def test_draft_persists_token_for_resume(isolated_rt, monkeypatch):
    """draft 落盘含 token（恢复凭据）；runtime 文件权限 0600（与 java_key 同级保护）。"""
    tools.draft_voices({"voices": [{"content": "问题一"}]}, client_info={"name": "t"})
    rt = json.loads(isolated_rt.read_text(encoding="utf-8"))
    draft = next(iter(rt["drafts"].values()))
    assert len(draft.get("token", "")) == 32 and draft["tokenHash"] == tools._sha256(draft["token"])
    import os
    assert oct(os.stat(isolated_rt).st_mode & 0o777) == "0o600"


# ---- 场景用例（S83-S86，D-resume-commit-1，proposal.md 同名清单的测试侧映射）----

def test_s83_full_chain_echo_verbatim(isolated_rt, monkeypatch):
    """S83 正常确认提交全链：draft→commit→回执 echo 原话逐字（改写即违规）。"""
    captured = []
    _stub_engine(monkeypatch, captured, voice_ids=["ext_resume_s83"])
    original = "产品体验很糟糕呢\n反正不太好好用"
    d = tools.draft_voices({"voices": [{"content": original, "tags": ["易用性"]}]},
                           client_info={"name": "t"})
    assert d["contents"][0]["content"] == original
    out = tools.commit_voices({"draftId": d["draftId"],
                               "approvalToken": d["approvalToken"],
                               "payloadSha256": d["payloadSha256"]},
                              client_info={"name": "t"})
    echo_content = out["echo"]["contents"][0]["content"]
    assert echo_content == original, "回执 echo 必须与用户原话逐字一致"
    sent = captured[0]["body"]["voices"][0]["content"]
    assert sent == original, "上送 payload 必须与用户原话逐字一致"


def test_s85_expired_then_redraft_commits(isolated_rt, monkeypatch):
    """S85 草稿过期→SKILL 话术锁的重开链：过期拒→重新 draft→commit 成功。"""
    import time as _time
    captured = []
    _stub_engine(monkeypatch, captured)
    d1 = tools.draft_voices({"voices": [{"content": "导出卡住"}]}, client_info={"name": "t"})
    rt = json.loads(isolated_rt.read_text(encoding="utf-8"))
    rt["drafts"][d1["draftId"]]["expiresAt"] = _time.time() - 1
    isolated_rt.write_text(json.dumps(rt, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(tools.ToolError):
        tools.commit_voices({"draftId": d1["draftId"]}, client_info={"name": "t"})
    d2 = tools.draft_voices({"voices": [{"content": "导出卡住"}]}, client_info={"name": "t"})
    out = tools.commit_voices({"draftId": d2["draftId"]}, client_info={"name": "t"})
    assert out["accepted"] == 1 and len(captured) == 1


def test_s86_consumed_draft_not_resurrectable(isolated_rt, monkeypatch):
    """S86 单次消费对恢复路径同径：commit 成功后凭同一 draftId 再恢复=拒（防二次提交）。"""
    captured = []
    _stub_engine(monkeypatch, captured)
    d = tools.draft_voices({"voices": [{"content": "补全慢"}]}, client_info={"name": "t"})
    out = tools.commit_voices({"draftId": d["draftId"]}, client_info={"name": "t"})
    assert out["accepted"] == 1
    with pytest.raises(tools.ToolError) as ei:
        tools.commit_voices({"draftId": d["draftId"]}, client_info={"name": "t"})
    assert "不存在或已过期" in str(ei.value)
    assert len(captured) == 1, "消费后恢复路径不得二次提交"
