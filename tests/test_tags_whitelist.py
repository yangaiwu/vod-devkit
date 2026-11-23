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
from vod_mcp import runtime_state as _rt
from vod_mcp.packs import collect as _collect
from vod_mcp import net as _net

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
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: (meta or META))
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_rt, "_save_runtime",
                        lambda d, replace=False: saved.update(d))

    def _fake_atomic(mutate):
        """事务桩：草稿/账本现在走 _runtime_atomic（读整键→改→写整键必须同锁内）。"""
        cfg = {}
        if mutate(cfg) is not False:
            saved.update(cfg)
        return cfg

    monkeypatch.setattr(_rt, "_runtime_atomic", _fake_atomic)

    def fake_http(m, p, body=None, timeout=30, base=None, key=None):
        if "productId=" in str(p):
            pid = str(p).split("productId=")[-1].split("&")[0]
            return {"code": 200, "data": {"problemTypes": TYPES_BY_PID.get(pid, [])}}
        captured.update(body=body)
        return {"code": 201, "voiceIds": ["ext_1"], "statuses": ["new"]}

    monkeypatch.setattr(_net, "_http", http or fake_http)
    return captured


def test_valid_problem_type_kept_and_unknown_dropped(monkeypatch):
    cap = _stub(monkeypatch)
    out = _collect.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                          "tags": ["problem_type:产品缺陷",
                                                   "problem_type:瞎写的类",
                                                   "页面:导出"]}],
                               "confirmed": True}, client_info={"name": "t"})
    tags = cap["body"]["voices"][0]["tags"]
    assert tags == ["problem_type:产品缺陷", "页面:导出"], tags
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:瞎写的类"]}]


def test_problem_type_value_is_normalized(monkeypatch):
    cap = _stub(monkeypatch)
    _collect.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                     "tags": ["problem_type:  体验改进  "]}],
                         "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:体验改进"]


def test_non_problem_type_tags_are_never_filtered(monkeypatch):
    cap = _stub(monkeypatch)
    _collect.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                     "tags": ["随便一个标签", "problem_type:功能需求"]}],
                         "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["随便一个标签", "problem_type:功能需求"]


def test_no_product_means_no_filtering(monkeypatch):
    """无产品归因（原话里没有产品线索）→ 取不到分类集 → 不过滤（宁可放行）。"""
    cap = _stub(monkeypatch)
    out = _collect.submit_voices({"voices": [{"content": "导出转圈两分钟",
                                          "tags": ["problem_type:瞎写的类"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:瞎写的类"]
    assert "invalidTags" not in out


def test_whitelist_is_per_product_not_global(monkeypatch):
    """同一脏 tag 在 OBS 下是合法值就保留 —— 证明白名单按产品走。"""
    cap = _stub(monkeypatch)
    out = _collect.submit_voices({"voices": [{"content": "对象存储服务 OBS 上传失败",
                                          "tags": ["problem_type:文档问题"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:文档问题"]
    assert "invalidTags" not in out


def test_whitelist_unavailable_means_no_filtering(monkeypatch):
    """分类端点不可达 → 空集 → 不过滤，脏 tag 也放行（不误杀采集）。"""
    cap = {}

    def partial_http(m, p, body=None, timeout=30, base=None, key=None):
        if "productId=" in str(p):
            raise _net.ToolError("unreachable", code=502)
        cap.update(body=body)
        return {"code": 201, "voiceIds": ["ext_1"], "statuses": ["new"]}

    _stub(monkeypatch, http=partial_http)
    out = _collect.submit_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                          "tags": ["problem_type:未知类"]}],
                               "confirmed": True}, client_info={"name": "t"})
    assert "invalidTags" not in out
    assert cap["body"]["voices"][0]["tags"] == ["problem_type:未知类"]


def test_draft_uses_same_whitelist(monkeypatch):
    saved = {}
    _stub(monkeypatch, saved=saved)
    out = _collect.draft_voices({"voices": [{"content": "CodeArts 导出转圈两分钟",
                                          "tags": ["problem_type:瞎写的类",
                                                   "problem_type:产品缺陷"]}]},
                             client_info={"name": "t"})
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:瞎写的类"]}]
    draft = (saved.get("drafts") or {}).get(out["draftId"]) or {}
    assert draft["payload"]["voices"][0]["tags"] == ["problem_type:产品缺陷"]

def test_free_text_fields_are_explicit():
    """ARCH-CFG-07 验收：用户自由文本字段靠**显式白名单**剔除，不靠"新字段记得加"。

    历史缺陷：`guard_scope` 只硬编码 `data` 与 `voices[].content` 两处，
    新增一个装用户原话的字段（reproSteps/expectedBehavior/echo…）就默认进扫描面，
    "反馈内容里引用了凭据"会被判成凭据读取意图。白名单还在，但要**被用例钉住**。
    """
    import json
    import pathlib

    from vod_mcp import policy

    params = {
        "product": "CodeArts",
        "voices": [{"content": "我的 AK/SK 是 AKIA…，帮我看看", "reproSteps": "复现步骤",
                    "expectedBehavior": "期望表现", "tags": ["problem_type:产品缺陷"]}],
        "data": [{"raw": "x"}],
        "originalLines": ["原话"],
        "echo": {"contents": [{"content": "原话"}]},
        "summary": "总结",
        "query": "CodeArts",
    }
    scope = policy.guard_scope(params)
    dumped = json.dumps(scope, ensure_ascii=False)
    for key in policy.USER_TEXT_KEYS:
        assert f'"{key}"' not in dumped, f"用户原话字段 {key} 仍进扫描面：{dumped}"
    assert scope["product"] == "CodeArts" and scope["query"] == "CodeArts", "结构性字段必须保留"
    assert scope["voices"][0]["tags"] == ["problem_type:产品缺陷"], "非原话字段必须保留"
    assert scope["data"] == ["<%d records>" % 1] or scope["data"] == "<1 records>"

    # 契约里声明的用户原话字段必须都在白名单表里（新增字段漏登记 → 这条红）
    schema = json.loads((pathlib.Path(__file__).resolve().parent.parent
                         / "assets" / "contract" / "tools.schema.json").read_text(encoding="utf-8"))

    def props(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "properties" and isinstance(v, dict):
                    yield from v.keys()
                yield from props(v)
        elif isinstance(node, list):
            for item in node:
                yield from props(item)

    userish = {"content", "reproSteps", "expectedBehavior", "originalLines", "echo", "summary"}
    leak = sorted(n for n in set(props(schema)) if n in userish and n not in policy.USER_TEXT_KEYS)
    assert not leak, f"契约里有用户原话字段没登记进白名单：{leak}"
