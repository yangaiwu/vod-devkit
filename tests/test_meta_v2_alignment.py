"""引擎 dev(2026-11-12) 口径对齐的回归锁（叠加在 1bb9f67 的规则派生之上）。

上游：meta 不再下发 nameAliases/aliases/problemTypes；分类按 productId 下发。
本文件锁三件在真机实测中出过问题的事：
  ① 大小写变体（MaaS/Maas）不得退化成单命中 → 双产品句必须 UNKNOWN
  ② 全大写缩写永不 caseless：`obs://bucket`、`/obs/bin`、`a@obs` 都不是产品提及
  ③ 按产品取值域：无产品/接口不可达=不过滤；有产品=白名单过滤并回执 invalidTags
"""
from vod_mcp import attribution as A
from vod_mcp import tools

META = {
    "products": ["CodeArts", "Maas", "对象存储服务 OBS", "ModelArts"],
    "catalog": [{"id": 1, "name": "CodeArts"}, {"id": 5, "name": "Maas"},
                {"id": 261, "name": "对象存储服务 OBS"}, {"id": 4, "name": "ModelArts"}],
    "problemTypes": [],
    "dictVersion": "v", "stale": False, "source": "meta",
}


def _attr(text):
    return A.attribute(text, META, memory={}, binding=None)


def test_case_variant_does_not_collapse_to_single_hit():
    r = _attr("从 CodeArts 导出到 MaaS 打不开")
    assert r["source"] == "unknown"
    assert {e["product"] for e in r["evidence"]} == {"CodeArts", "Maas"}


def test_uppercase_acronym_is_not_caseless():
    """OBS 由"对象存储服务 OBS"派生，但全大写缩写不得做小写匹配（S93）。"""
    assert _attr("OBS 上传失败")["product"] == "261"
    for text in ("obs://bucket 上传失败", "把包放到 /obs/bin 下面", "a@obs 别删"):
        assert _attr(text)["source"] == "unknown", text


def test_modelarts_and_maas_stay_separate_products():
    assert _attr("ModelArts 部署失败")["product"] == "4"
    assert _attr("Maas 上传失败")["product"] == "5"


def test_brand_alias_is_a_local_list_not_derived():
    """「码道」来自本地 BRAND_ALIASES（人工清单），不是引擎下发。"""
    assert A.BRAND_ALIASES.get("CodeArts")
    assert _attr("码道导出转圈两分钟")["product"] == "1"


def test_allowed_tags_none_without_product(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    assert tools._allowed_tags(None) == set()


def test_allowed_tags_fetched_per_product_and_cached(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_save_runtime", lambda d, replace=False: None)
    calls = []

    def fake_http(method, path, body=None, **kw):
        calls.append(path)
        return {"code": 200, "data": {"problemTypes": ["功能需求", "技术/业务咨询"]}}
    monkeypatch.setattr(tools, "_http", fake_http)
    assert tools._allowed_tags("5") == {"功能需求", "技术/业务咨询"}
    assert "productId=5" in calls[0]
    tools._allowed_tags("5")
    assert len(calls) == 1, "同产品第二次必须走缓存"


def test_allowed_tags_failure_means_no_filter(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_save_runtime", lambda d, replace=False: None)

    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(tools, "_http", boom)
    assert tools._allowed_tags("5") == set()


def test_submit_filters_tags_by_product_types(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_save_runtime", lambda d, replace=False: None)
    monkeypatch.setattr(tools, "JAVA_BASE", "http://stub")
    monkeypatch.setattr(tools, "JAVA_KEY", "k")

    def fake_http(method, path, body=None, **kw):
        if "meta" in path:
            return {"code": 200, "data": {"problemTypes": ["功能需求", "产品缺陷"]}}
        return {"code": 201, "voiceIds": ["VDPL202611120001"], "statuses": ["new"]}
    monkeypatch.setattr(tools, "_http", fake_http)
    out = tools.submit_voices({"voices": [{
        "content": "CodeArts 导出失败",
        "tags": ["problem_type:产品缺陷", "problem_type:易用性"]}],
        "confirmed": True}, client_info={"name": "t"})
    assert out["invalidTags"] == [{"index": 0, "tags": ["problem_type:易用性"]}]