"""归因链（D-attrib-B，S91-S100）：运行期字面解析 + 记忆 + 先验 + 弃权。

纯函数层（vod_mcp/attribution.py）+ tools 接线层（留痕/记忆写盘）同测。
"""
import pytest

from vod_mcp import attribution as attr
from vod_mcp import tools

META = {
    "products": ["CodeArts", "MaaS", "OBS", "AIShell"],
    "catalog": [{"id": 31, "name": "CodeArts"}, {"id": 43, "name": "MaaS"},
                {"id": 44, "name": "OBS"}, {"id": 42, "name": "AIShell"}],
    "nameAliases": {
        "CODEARTS": ["码道", "CodeArts", "软件开发生产线 CodeArts", "CODEARTS"],
        "MAAS": ["MaaS", "MAAS"],
        "OBS": ["OBS", "对象存储服务 OBS"],
        "AISHELL": ["AIShell", "AI shell"],
    },
    "aliases": {"modelarts": "maas"},
    "stale": False,
    "source": "meta",
}


def _hit(text, meta=META):
    return attr.match_products(text, attr.build_alias_index(meta))


def _attribute(text, **kw):
    return attr.attribute(text, META, **kw)


# ---- S91/S92：字面证据命中与主键化 ----

def test_s91_chinese_alias_maps_to_catalog_id():
    out = _attribute("码道导出转圈两分钟没文件")
    assert out["source"] == "user_input" and out["product"] == "31"
    assert out["evidence"][0]["alias"] == "码道"
    assert "码道" in out["evidence"][0]["snippet"]


def test_s92_long_alias_wins_and_normalizes():
    hits = _hit("软件开发生产线 CodeArts 登录失败")
    assert {h["product"] for h in hits} == {"CodeArts"}
    assert hits[0]["alias"] == "软件开发生产线 CodeArts", "长别名优先，不被子串重复计数"
    assert _attribute("对象存储服务 OBS 上传失败")["product"] == "44"
    out = _attribute("modelarts 模型部署失败")
    assert out["product"] in ("43", "MaaS"), "别名表随目录命中给 id，否则 name 通道"


# ---- S93：误命中反例（本次评审点名要写成判定例） ----

@pytest.mark.parametrize("text", [
    "codearts.yaml 里配置错了",   # 文件扩展名不算边界
    "mycodearts 报错",            # 词内包含
    "依赖 obs://bucket 路径",     # 短别名小写 + URL 形态
    "obs 一直转圈",               # 小写裸短名不收
    "codearts_config 写坏了",     # 下划线/连字符不算边界
])
def test_s93_negative_cases_do_not_attribution(text):
    assert _hit(text) == [], text


@pytest.mark.parametrize("text,pid", [
    ("OBS 上传失败", "44"),
    ("对象存储服务 OBS 上传失败", "44"),
    ("CodeArts. 打不开", "31"),   # 句点后是空格=句子结束，仍是边界
])
def test_s93_strong_forms_still_match(text, pid):
    assert _attribute(text)["product"] == pid


# ---- S94：多产品歧义 → UNKNOWN + 全部证据 ----

def test_s94_ambiguous_is_unknown_with_all_evidence():
    text = "从 CodeArts 导出到 MaaS 之后打不开"
    out = _attribute(text)
    assert out["product"] is None and out["source"] == "unknown"
    assert {e["product"] for e in out["evidence"]} == {"CodeArts", "MaaS"}
    assert all(e.get("reason") == "ambiguous" for e in out["evidence"])


# ---- S95/S96：记忆与先验回退 ----

def test_s95_memory_reused_within_ttl():
    mem = {"product": "31", "productName": "CodeArts", "alias": "码道",
           "snippet": "码道导出慢", "at": 1_000}
    out = _attribute("导出还是慢", memory=mem, now=1_000 + 60)
    assert out["source"] == "memory" and out["product"] == "31"
    assert out["evidence"][0]["at"] == 1_000, "证据要能回指被复用的历史命中"


def test_s96_expired_memory_falls_back_to_binding_then_unknown():
    mem = {"product": "31", "productName": "CodeArts", "at": 1_000}
    out = _attribute("导出还是慢", memory=mem, binding="CodeArts",
                     ttl=attr.MEM_TTL, now=1_000 + attr.MEM_TTL + 1)
    assert out["source"] == "install_binding" and out["product"] == "31"
    out = _attribute("导出还是慢", memory=mem, binding=None,
                     ttl=attr.MEM_TTL, now=1_000 + attr.MEM_TTL + 1)
    assert out["source"] == "unknown" and out["product"] is None
    assert out["evidence"][0]["reason"] == "no-evidence"


# ---- S97：模型自报不采信（D-attrib-A 事故语义保留） ----

def test_s97_runtime_self_report_is_ignored_but_recorded(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(tools, "_RT", {})
    out = tools._attribute_product([(0, {}, "导出很慢")], {"product": "hermes"})
    assert out["product"] is None, "自报不是归因来源"
    assert out["ignored"] == "hermes"


# ---- S98：名录不可用不猜 ----

def test_s98_snapshot_only_matches_short_codes_and_never_guesses():
    snap = {"products": [], "catalog": [], "aliases": {}, "nameAliases": {},
            "stale": True, "source": "snapshot"}
    assert attr.attribute("码道导出慢", snap)["source"] == "unknown", \
        "无名录=无别名原料，中文点名不可解析 → UNKNOWN 不猜"
    assert attr.attribute("导出慢", snap)["source"] == "unknown"


# ---- S99：留痕（回执 + 账本同一份来源/证据） ----

def test_s99_receipt_and_ledger_carry_source_and_evidence():
    res = _attribute("码道导出很慢")
    receipt = {}
    tools._attach_attribution(receipt, {**res, "ignored": None})
    assert receipt["productSource"] == "user_input"
    assert receipt["productEvidence"][0]["alias"] == "码道"
    ledger = tools._merge_ledger({"stage": "committed"}, res)
    assert ledger["stage"] == "committed"
    assert ledger["productSource"] == "user_input"
    assert ledger["productEvidence"] == receipt["productEvidence"]


# ---- S100：歧义/无证据不写记忆；覆盖要留快照 ----

def test_s100_ambiguous_and_empty_never_write_memory():
    assert attr.remember_if_evidenced(_attribute("CodeArts 和 MaaS 都打不开")) is None
    assert attr.remember_if_evidenced(_attribute("导出很慢")) is None
    mem = attr.remember_if_evidenced(_attribute("码道导出很慢"))
    assert mem and mem["product"] == "31" and mem["alias"] == "码道"


def test_s100_memory_overwrite_keeps_snapshot(monkeypatch):
    saved = {}
    monkeypatch.setattr(tools, "_save_runtime", lambda d, replace=False: saved.update(d))
    monkeypatch.setattr(tools, "_RT", {"attribution_memory": {
        "product": "31", "productName": "CodeArts", "alias": "码道", "at": 100}})
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    tools._remember_attribution({"product": "43", "productName": "MaaS",
                                 "source": "user_input",
                                 "evidence": [{"product": "MaaS", "alias": "MaaS",
                                               "snippet": "MaaS 部署失败"}]})
    hist = saved.get("attribution_history") or []
    assert hist and hist[-1]["product"] == "31" and "replacedAt" in hist[-1]
    assert saved["attribution_memory"]["product"] == "43"

def test_s95_end_to_end_memory_flows_into_next_submission(monkeypatch):
    """真链路：第一次带「码道」→ 写记忆；同一进程第二次只说「还是慢」
    → 归因来源 memory（进程内同步，不靠重启读盘）。"""
    saved = {}
    rt = {}
    monkeypatch.setattr(tools, "_load_meta", lambda force=False: META)
    monkeypatch.setattr(tools, "_RT", rt)
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_save_runtime", lambda d, replace=False: (saved.update(d), rt.update(d)))
    bodies = []
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        bodies.append(body) or
                        {"code": 201, "voiceIds": ["ext_1"], "statuses": ["new"]})
    first = tools.submit_voices({"voices": [{"content": "码道导出转圈两分钟"}],
                                 "confirmed": True}, client_info={"name": "t"})
    assert first["productSource"] == "user_input"
    assert rt["attribution_memory"]["product"] == "31"
    second = tools.submit_voices({"voices": [{"content": "导出还是慢"}],
                                  "confirmed": True}, client_info={"name": "t"})
    assert second["productSource"] == "memory"
    assert bodies[-1]["product"] == "31"
    assert second["productEvidence"][0]["reason"] == "memory"


# ---- 真机数据形态回归（2026-11-11 线上 meta 实锤的两个坑） ----

REAL_META = {
    # catalog 名与展示名不一致：MaaS 存成 Maas、OBS 存成 对象存储服务 OBS
    "products": ["AgentArts", "DataArts", "MaaS", "OfficeClaw", "CodeArts", "AIShell", "OBS"],
    "catalog": [{"id": 5, "name": "Maas"}, {"id": 1, "name": "CodeArts"},
                {"id": 261, "name": "对象存储服务 OBS"}],
    "nameAliases": {"MAAS": ["MaaS", "Maas", "MAAS"],
                    "CODEARTS": ["码道", "CodeArts", "软件开发生产线 CodeArts"],
                    "OBS": ["OBS", "对象存储服务 OBS"]},
    "aliases": {"modelarts": "maas"},
    "stale": False, "source": "meta",
}


def test_real_meta_catalog_display_mismatch_still_resolves_id():
    """坑①：catalog 名（Maas）≠ 展示名（MaaS）时不许拆成两条、不许丢 id。"""
    idx = attr.build_alias_index(REAL_META)
    maas = {(e["alias"], e["id"]) for e in idx if e["product"] == "MaaS"}
    assert ("MaaS", "5") in maas and ("Maas", "5") in maas, maas
    assert attr.attribute("MaaS 部署失败", REAL_META)["product"] == "5"
    # OBS：展示名 OBS + catalog 名「对象存储服务 OBS」合并成同一条（id 261）
    obs = {(e["alias"], e["id"]) for e in idx if e["product"] == "OBS"}
    assert ("OBS", "261") in obs and ("对象存储服务 OBS", "261") in obs, obs


def test_real_meta_alias_dedupe_keeps_case_variants():
    """坑②：别名去重按大小写敏感——短别名精确匹配时 MaaS 不能被 Maas 顶掉。"""
    idx = attr.build_alias_index(REAL_META)
    assert {"MaaS", "Maas", "MAAS"} <= {e["alias"] for e in idx if e["product"] == "MaaS"}


def test_alias_table_target_missing_from_names_still_matches():
    """aliases 表的目标（maas）若不在 products/catalog 里，别名本身仍要能命中
    （建槽兜底；否则别名表被静默丢弃）。"""
    meta = {"products": [], "catalog": [], "nameAliases": {},
            "aliases": {"modelarts": "maas"}, "stale": True, "source": "snapshot"}
    out = attr.attribute("modelarts 部署失败", meta)
    assert out["source"] == "user_input" and out["product"] == "maas"
