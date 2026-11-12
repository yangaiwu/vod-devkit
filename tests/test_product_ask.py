"""D-product-ask-1（2026-11-11 拍板）：缺产品必须问一次，不许裸提交 UNKNOWN。

口径（覆盖十种场景）：
  ① 原话唯一高置信 → 直接用（source=user_input）
  ② 无产品线索 → submit 以 -32010 拒绝，错误里带候选（模型据此问一句）
  ③ 用户说"不知道/随便" → productNotSpecified=true → host_default/low（可修正）
  ④ 宿主没有产品映射 → 仍允许提交，但 source=unknown/low + 证据写明用户未指定
  ⑤ 会话记忆 30 分钟滑动，一次抱怨只问一次；用户改口覆盖
  ⑥ 原话多产品/对比 → 低置信，先问
  ⑦ 旧客户端缺 product → 兼容开关给 legacy_default/low，不裸 UNKNOWN
"""
import pytest

from vod_mcp import tools

META = {
    "products": ["CodeArts", "Maas"],
    "catalog": [{"id": "1", "name": "CodeArts"}, {"id": "5", "name": "Maas"}],
    "problemTypes": [], "stale": False, "source": "meta",
}


@pytest.fixture
def eng(monkeypatch, tmp_path):
    """桩引擎：记录 body；关掉旧客户端开关（本文件测强制语义）。"""
    monkeypatch.delenv("VOD_ALLOW_UNKNOWN_PRODUCT", raising=False)
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "JAVA_BASE", "http://stub")
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_SESSION_MEM", {})
    monkeypatch.setattr(tools, "_runtime_path", lambda: tmp_path / "runtime.json")
    sent = []
    def _fake(m, p, body=None, **k):
        if isinstance(body, dict) and "voices" in body:
            sent.append(body)          # 只记录真正的提交（meta 查询 body=None）
        return {"code": 201, "voiceIds": ["VDPL202611120001"], "statuses": ["new"]}
    monkeypatch.setattr(tools, "_http", _fake)
    return sent


def _submit(**params):
    params.setdefault("confirmed", True)
    return tools.submit_voices(params, client_info={"name": "codearts"})


def test_single_literal_product_submits_without_asking(eng):
    out = _submit(voices=[{"content": "CodeArts 导出失败"}])
    assert out["productSource"] == "user_input"
    assert out["productId"] == "1"
    assert eng and eng[0]["product"] == "1"


def test_no_product_is_refused_with_actionable_candidates(eng):
    with pytest.raises(tools.ToolError) as ei:
        _submit(voices=[{"content": "体验很差"}])
    assert ei.value.code == -32010
    assert "先问用户" in str(ei.value)
    assert not eng, "被拒时不得调用引擎（不许裸提交）"


def test_user_says_unknown_falls_back_to_host_product(eng, monkeypatch):
    monkeypatch.setitem(tools._RT, "host_product", "CodeArts")
    out = _submit(voices=[{"content": "体验很差"}], productNotSpecified=True)
    assert out["productSource"] == "host_default"
    assert out["productConfidence"] == "low"
    assert eng[0]["product"] in ("1", "CodeArts")


def test_unknown_without_host_mapping_is_allowed_but_flagged(eng):
    out = _submit(voices=[{"content": "体验很差"}], productNotSpecified=True)
    assert out["productSource"] == "unknown"
    assert out["productConfidence"] == "low"
    assert any(e.get("reason") == "user-not-specified" for e in out["productEvidence"])


def test_multi_product_mention_asks_instead_of_guessing(eng):
    with pytest.raises(tools.ToolError) as ei:
        _submit(voices=[{"content": "从 CodeArts 导出到 Maas 打不开"}])
    assert ei.value.code == -32010
    assert not eng


def test_session_memory_skips_second_question_and_answers_override(eng):
    _submit(voices=[{"content": "CodeArts 导出失败"}], product="CodeArts")
    # 30 分钟内第二条没有产品名 → 用记忆，不再问
    out = _submit(voices=[{"content": "还是有点慢"}])
    assert out["productSource"] == "memory" and out["productId"] == "1"
    # 用户改口说 Maas → 覆盖记忆
    out2 = _submit(voices=[{"content": "这条是 Maas"}], product="Maas")
    assert out2["productSource"] == "user_answer" and out2["productId"] == "5"
    out3 = _submit(voices=[{"content": "继续很慢"}])
    assert out3["productId"] == "5"


def test_memory_expires_after_ttl(eng, monkeypatch):
    _submit(voices=[{"content": "CodeArts 导出失败"}], product="CodeArts")
    mem = dict(tools._SESSION_MEM)
    for k, v in mem.items():
        v["at"] = 0                      # 手动过期
    with pytest.raises(tools.ToolError):
        _submit(voices=[{"content": "又一条没产品名的"}])
        # 注意：这里必须重新抛，不能靠记忆


def test_legacy_client_switch_marks_legacy_default(eng, monkeypatch):
    monkeypatch.setenv("VOD_ALLOW_UNKNOWN_PRODUCT", "1")
    out = _submit(voices=[{"content": "体验很差"}])
    assert out["productSource"] == "legacy_default"
    assert out["productConfidence"] == "low"
    assert eng, "旧客户端兼容：不阻断提交"


def test_search_products_returns_candidates_for_asking(eng):
    r = tools.search_products({"query": "导出慢", "limit": 3})
    assert r["candidates"], "问用户前必须能给候选"
    r2 = tools.search_products({"query": "CodeArts", "limit": 3})
    assert r2["candidates"][0]["id"] == "1"


def test_draft_stores_product_and_does_not_block(eng):
    out = tools.draft_voices({"voices": [{"content": "体验很差"}]},
                             client_info={"name": "codearts"})
    assert out["productSource"] == "unknown"      # 草稿不阻断，等 commit 前补齐
    assert out["productConfidence"] == "low"
    assert not eng, "draft 不触上游"


def test_commit_requires_product(eng):
    d = tools.draft_voices({"voices": [{"content": "体验很差"}]},
                           client_info={"name": "codearts"})
    with pytest.raises(tools.ToolError) as ei:
        tools.commit_voices({"draftId": d["draftId"]}, client_info={"name": "codearts"})
    assert ei.value.code == -32010