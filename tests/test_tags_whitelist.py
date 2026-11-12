"""分类标注白名单（tags）行为锁。

对照 developer-skill/vod-skill 的 check_classification（分类必须存在于知识库）：
我们的对等缺口是 tags 以前原样透传——契约只声明 string 数组，脏分类会先进报表。
现在的口径：
  ① `problem_type:<值>` 的值必须在**该产品**的分类集内，否则丢弃并回执
     invalidTags（只丢 tag，不拒收声音）
  ② 其它语义的 tag 不参与分类校验、原样保留
  ③ 拿不到白名单（无产品/老引擎/端点不可达）→ 空集，不过滤（宁可放行也不误杀）

2026-11-12 引擎契约变更：问题分类不再随无参 meta 下发（那是"全部分类"的假全集），
改为 `GET /external/meta?productId=<id>` 按产品下发（真源 t_vod_problem_category
按 product_id 分组）。因此本文件的桩要能区分「无产品」与「某产品」两种请求。
"""
from vod_mcp import tools

# 产品 A（CodeArts）：六类标准分类
TYPES_A = ["产品缺陷", "技术业务咨询", "体验改进", "主观评价", "无效问题", "功能需求"]
# 产品 B（OBS）：分类集不同 —— 用来证明白名单确实按产品走，不是全局一份
TYPES_B = ["产品缺陷", "文档问题"]

META = {"products": ["CodeArts", "OBS"],
        "catalog": [{"id": 31, "name": "CodeArts"}, {"id": 44, "name": "OBS"}],
        "dictVersion": "x", "stale": False, "source": "meta"}

TYPES_BY_PID = {"31": TYPES_A, "44": TYPES_B}


def _stub(monkeypatch, meta=None, captured=None, saved=None, http=None):
    """桩：_load_meta 提供产品目录；_http 对 meta?productId= 返回该产品分类集。"""
    saved = saved if saved is not None else {}
    captured = captured if captured is not None else {}
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: (meta or META))
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_save_runtime",
                        lambda d, replace=False: saved.update(d))

    def fake_http(m, p, body=None, timeout=30, base=None, key=None):
        if "productId=" in str(p):
            pid = str(p).split("productId=")[-1].split("&")[0]
            return {"code": 200, "data": {"problemTypes": TYPES_BY_PID.get(pid, [])}}
        captured.update(body=body)
        return {"code": 201, "voiceIds": ["ext_1"], "statuses": ["new"]}

    monkeypatch.setattr(tools, "_http", http or fake_http)
    return captured


def test_valid_problem_type_kept_and_unknown_dropped(monkeypatch):
    cap = _stub(monkeypatch)
    out = tools.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                          "tags": ["problem_type:产品缺陷",
                                                   "problem_type:瞎写的类",
                                                   "页面:导出"]}],
                               "confirmed": True}, client_info={"name": "t"})
    tags = cap["body"]["voices"][0]["tags"]
    assert tags == ["problem_type:产品缺陷", "页面:导出"], tags
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:瞎写的类"]}]


def test_problem_type_value_is_normalized(monkeypatch):
    cap = _stub(monkeypatch)
    tools.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                     "tags": ["problem_type:  体验改进  "]}],
                         "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:体验改进"]


def test_non_problem_type_tags_are_never_filtered(monkeypatch):
    cap = _stub(monkeypatch)
    tools.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                     "tags": ["随便一个标签", "problem_type:功能需求"]}],
                         "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["随便一个标签", "problem_type:功能需求"]


def test_no_product_means_no_filtering(monkeypatch):
    """无产品归因（原话里没有产品线索）→ 取不到分类集 → 不过滤（宁可放行）。"""
    cap = _stub(monkeypatch)
    out = tools.submit_voices({"voices": [{"content": "导出转圈两分钟",
                                          "tags": ["problem_type:瞎写的类"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:瞎写的类"]
    assert "invalidTags" not in out


def test_whitelist_is_per_product_not_global(monkeypatch):
    """同一脏 tag 在 OBS 下是合法值就保留 —— 证明白名单按产品走。"""
    cap = _stub(monkeypatch)
    out = tools.submit_voices({"voices": [{"content": "对象存储服务 OBS 上传失败",
                                          "tags": ["problem_type:文档问题"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:文档问题"]
    assert "invalidTags" not in out


def test_whitelist_unavailable_means_no_filtering(monkeypatch):
    """分类端点不可达 → 空集 → 不过滤，脏 tag 也放行（不误杀采集）。"""
    cap = {}

    def partial_http(m, p, body=None, timeout=30, base=None, key=None):
        if "productId=" in str(p):
            raise tools.ToolError("unreachable", code=502)
        cap.update(body=body)
        return {"code": 201, "voiceIds": ["ext_1"], "statuses": ["new"]}

    _stub(monkeypatch, http=partial_http)
    out = tools.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                          "tags": ["problem_type:未知类"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert "invalidTags" not in out
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:未知类"]


def test_draft_uses_same_whitelist(monkeypatch):
    saved = {}
    _stub(monkeypatch, saved=saved)
    out = tools.draft_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                          "tags": ["problem_type:瞎写的类",
                                                   "problem_type:产品缺陷"]}]},
                             client_info={"name": "t"})
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:瞎写的类"]}]
    draft = (saved.get("drafts") or {}).get(out["draftId"]) or {}
    assert draft["payload"]["voices"][0]["tags"] == ["problem_type:产品缺陷"]