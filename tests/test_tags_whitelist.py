"""分类标注白名单（tags）行为锁。

对照 developer-skill/vod-skill 的 check_classification（分类必须存在于知识库）：
我们的对等缺口是 tags 以前原样透传——契约只声明 string 数组，脏分类会先进报表。
现在的口径：
  ① `problem_type:<值>` 的值必须在引擎 meta.problemTypes 内，否则丢弃并回执
     invalidTags（只丢 tag，不拒收声音）
  ② 其它语义的 tag 不参与分类校验、原样保留
  ③ meta 拿不到白名单（老引擎/快照）→ 空集，不过滤（宁可放行也不误杀）
"""
from vod_mcp import tools

META = {"products": ["CodeArts"], "catalog": [], "aliases": {}, "nameAliases": {},
        "problemTypes": ["产品缺陷", "技术业务咨询", "体验改进", "主观评价",
                         "无效问题", "功能需求"],
        "dictVersion": "x", "stale": False, "source": "meta"}


def _stub(monkeypatch, meta=META, captured=None, saved=None):
    saved = saved if saved is not None else {}
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: meta)
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_save_runtime",
                        lambda d, replace=False: saved.update(d))
    captured = captured if captured is not None else {}
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        captured.update(body=body) or
                        {"code": 201, "voiceIds": ["ext_1"], "statuses": ["new"]})
    return captured


def test_valid_problem_type_kept_and_unknown_dropped(monkeypatch):
    cap = _stub(monkeypatch)
    out = tools.submit_voices({"voices": [{"content": "导出转圈两分钟",
                                          "tags": ["problem_type:产品缺陷",
                                                   "problem_type:瞎写的类",
                                                   "页面:导出"]}],
                               "confirmed": True}, client_info={"name": "t"})
    tags = cap["body"]["voices"][0]["tags"]
    assert tags == ["problem_type:产品缺陷", "页面:导出"], tags
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:瞎写的类"]}]


def test_problem_type_value_is_normalized(monkeypatch):
    cap = _stub(monkeypatch)
    tools.submit_voices({"voices": [{"content": "导出转圈两分钟",
                                     "tags": ["problem_type:  体验改进  "]}],
                         "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:体验改进"]


def test_non_problem_type_tags_are_never_filtered(monkeypatch):
    cap = _stub(monkeypatch)
    tools.submit_voices({"voices": [{"content": "导出转圈两分钟",
                                     "tags": ["随便一个标签", "problem_type:功能需求"]}],
                         "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["随便一个标签", "problem_type:功能需求"]


def test_no_whitelist_means_no_filtering(monkeypatch):
    """老引擎/快照不提供 problemTypes → 不做校验，脏 tag 也放行（不误杀采集）。"""
    meta = dict(META, problemTypes=[], stale=True, source="snapshot")
    cap = _stub(monkeypatch, meta=meta)
    out = tools.submit_voices({"voices": [{"content": "导出转圈两分钟",
                                          "tags": ["problem_type:未知类"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:未知类"]
    assert "invalidTags" not in out


def test_draft_uses_same_whitelist(monkeypatch):
    saved = {}
    _stub(monkeypatch, saved=saved)
    out = tools.draft_voices({"voices": [{"content": "导出转圈两分钟",
                                          "tags": ["problem_type:瞎写的类",
                                                   "problem_type:产品缺陷"]}]},
                             client_info={"name": "t"})
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:瞎写的类"]}]
    draft = (saved.get("drafts") or {}).get(out["draftId"]) or {}
    assert draft["payload"]["voices"][0]["tags"] == ["problem_type:产品缺陷"]