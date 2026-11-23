"""认证与令牌链路测试：auth_status 指纹化（明文永不输出）+ 零字段令牌自动获取。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp.packs import collect as _collect
from vod_mcp.packs import core as _core
from vod_mcp import net as _net
from vod_mcp import runtime_state as _rt


def test_auth_status_fingerprint_not_plaintext(monkeypatch):
    monkeypatch.setattr(_net, "probe_key", lambda: {"ok": None, "reason": "unreachable"})  # 隔网
    out = _core.auth_status({}, client_info={"name": "t"})
    fp = out["javaKey"]["fingerprint"]
    assert fp is None or (len(fp) == 8 and fp != _net.JAVA_KEY), \
        "key 只能以 8 位指纹出现，明文禁止（fingerprint 纪律）"
    assert "packs" in out
    assert "workflowKey" not in out, "方案 A：单上游，无 workflowKey"


def test_auth_status_no_key_gives_guidance(monkeypatch):
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)  # 现读：清空要走 env，setattr 会永久覆盖
    out = _core.auth_status({}, client_info={})
    assert out["javaKey"]["configured"] is False
    assert [g["order"] for g in out["guidance"]] == [1, 2, 3], \
        "缺 key 时必须给三步引导（令牌/升级/宿主）"
    assert "自动" in out["guidance"][0]["label"]


def test_submit_voices_auto_token_then_retry(monkeypatch):
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    """零字段令牌链：无 key → 取令牌 → 落 runtime → 重试成功（用户无感）。"""
    calls = []
    state = {"token_issued": False}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls.append((method, path, key))
        if path.endswith("/external/token"):
            state["token_issued"] = True
            # D-anon-verify（2026-11-05 真机实锤）：引擎真实契约=ApiResponse 信封，
            # mock 必须对齐真源（曾用扁平 {"token":...} 掩盖了顶层取值恒 None 的缺陷）
            return {"code": 200, "message": "令牌已签发",
                    "data": {"token": "anon-token-xyz", "dailyLimit": 50,
                             "expiresAt": 1796453397897, "tier": "anonymous"}}
        if path.endswith("/external/voices"):
            if key == "anon-token-xyz":
                return {"code": 200, "voiceIds": ["ext_vod-agent_t1"]}
            raise _net.ToolError("鉴权失败：检查 key", code=-32012)
        return {}

    saved = {}

    def fake_save(update):
        saved.update(update)

    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)  # 现读：清空要走 env，setattr 会永久覆盖
    monkeypatch.setattr(_net, "_http", fake_http)
    monkeypatch.setattr(_rt, "_save_runtime", fake_save)
    out = _collect.submit_voices(
        {"voices": [{"content": "补全响应有点慢，希望优化一下"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1 and out["path"] == "hoarding"
    assert out["voiceIds"] == ["ext_vod-agent_t1"]  # 囤积语义：无即时任务，id=引擎算
    assert state["token_issued"], "必须先取令牌"
    assert saved.get("java_key") == "anon-token-xyz"
    assert saved.get("token_tier") == "anonymous"
    assert _net.JAVA_KEY == "anon-token-xyz", "令牌应回填运行时供后续复用"


def test_submit_voices_token_unreachable_gives_guidance(monkeypatch):
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": True, "source": "snapshot"})
    """令牌端点不可用（引擎未上线）→ 结构化引导错误，不是死胡同。"""
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)  # 现读：清空要走 env，setattr 会永久覆盖

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError("上游返回 404: Not Found", code=404)  # 对齐真实 _http：HTTP 状态进 code

    monkeypatch.setattr(_net, "_http", fake_http)
    with pytest.raises(_net.ToolError) as ei:
        _collect.submit_voices(
            {"voices": [{"content": "反馈内容足够长的一条意见"}],
             "product": "codearts", "confirmed": True},
            client_info={"name": "t"})
    # S238：删除老链回落后，囤积端点 404 = 明确失败（-32016），不许假装已受理
    assert ei.value.code == -32016
    assert "未提交" in str(ei.value) and "external/voices" in str(ei.value)


def test_voice_volume_preserved_across_calls(monkeypatch):
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    """R1 声量保真：不同调用提交同款反馈 → 两次都真发、引擎各自给 id，客户端不去重。

    （曾为缺陷：确定性 voiceId 使第二个用户同款反馈被去重吞掉，声量统计失真——
    此测试为永久回归锁。S238 起老链回落已删，锁点落在唯一路径上。）
    """
    calls = []
    counter = {"n": 0}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        assert path.endswith("/external/voices"), path
        calls.append(body["voices"][0]["content"])
        counter["n"] += 1
        return {"code": 200, "voiceIds": [f"VDPL-{counter['n']}"],
                "productRegistered": True}

    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http", fake_http)
    voice = {"content": "补全响应有点慢，希望优化一下"}
    ids = []
    for _ in range(2):
        out = _collect.submit_voices({"voices": [voice], "product": "codearts",
                                      "confirmed": True}, client_info={"name": "mcp"})
        assert out["accepted"] == 1 and out["path"] == "hoarding"
        ids.append(out["voiceIds"][0])
    assert len(calls) == 2, "同款反馈跨调用必须各发一次（声量保真）"
    assert set(calls) == {voice["content"]}, "content 必须原样交给引擎"
    assert len(set(ids)) == 2, "两次提交必须拿到不同 voiceId"

def test_attribution_literal_match_resolves_catalog_id(monkeypatch):
    """D-attrib-B：字面证据（含中文/长别名/短码）→ catalog 主键 id。
    T7i 的主键化语义保留：目录命中给 id，目录不可用给规范名（name 兼容通道）。"""
    meta = {"products": ["CodeArts", "AIShell"],
            "catalog": [{"id": 31, "name": "CodeArts"}, {"id": 42, "name": "AIShell"}],
            "nameAliases": {"CODEARTS": ["码道", "CodeArts", "软件开发生产线 CodeArts"],
                            "AISHELL": ["AIShell", "AI shell"]},
            "aliases": {"modelarts": "maas"}, "stale": False, "source": "meta"}
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: meta)
    monkeypatch.setattr(_rt, "_RT", {})  # 纯归因链：不受本机安装绑定干扰

    def run(text):
        return _collect._attribute_product([(0, {}, text)], {})

    for text in ("码道导出转圈两分钟", "用 CodeArts 导出很慢",
                 "软件开发生产线 CodeArts 登录失败", "codearts 打不开"):
        out = run(text)
        assert out["product"] == "31", (text, out)
        assert out["source"] == "user_input" and out["evidence"], out
    assert run("AI shell 卡住")["product"] == "42"
    # 别名表（modelarts→maas）随目录缺失回落规范名通道：不静默丢
    out = run("modelarts 模型部署失败")
    assert out["product"] in ("MaaS", "maas"), out
    # 名录不可达（快照/老引擎）：插件**不预置任何产品名/短码**（2026-11-13 纪律：
    # 支持的产品列表真源=引擎 meta 接口）→ 短码与俗称都归不了，一律 UNKNOWN→追问，
    # 绝不拿本地清单猜。
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": [], "catalog": [], "aliases": {},
                                             "nameAliases": {}, "stale": True,
                                             "source": "snapshot"})
    for text in ("codearts 打不开", "码道打不开"):
        out = run(text)
        assert out["source"] == "unknown" and out["product"] is None, (text, out)


def test_meta_catalog_cached_t7i(monkeypatch):
    """T7i：meta 载荷 productCatalog 进缓存并在缓存命中分支带回（提交解析不重打端点）。"""
    fetched = {"n": 0}
    saved = {}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        if path.endswith("/external/meta"):
            fetched["n"] += 1
            return {"code": 200, "data": {"products": ["codearts"],
                                          "productCatalog": [{"id": 31, "name": "CodeArts"}]}}
        raise AssertionError("不应有其他调用")

    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_http", fake_http)
    monkeypatch.setattr(_rt, "_save_runtime", lambda u: saved.update(u))
    m1 = _net._load_meta(force=True)
    assert m1["catalog"] == [{"id": 31, "name": "CodeArts"}]
    monkeypatch.setattr(_rt, "_RT", saved)
    m2 = _net._load_meta()
    assert fetched["n"] == 1  # 缓存命中零二次请求
    assert m2["catalog"] == [{"id": 31, "name": "CodeArts"}]
    # 老引擎无 productCatalog 键 → catalog 空不崩
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "data": {"products": ["codearts"]}})
    assert _net._load_meta(force=True)["catalog"] == []


def test_product_attribution_layers(monkeypatch):
    """D-product-ask-1（2026-11-11 拍板）：明确回答 > 原话唯一 > 记忆 > 先验 > host_default。

    老口径"D-attrib-A 只认安装绑定、自报一律不采信"已推翻——用户回答是合法证据。
    """
    meta = {"products": ["CodeArts"], "stale": False, "source": "meta",
            "catalog": [{"id": "1", "name": "CodeArts"}]}
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: meta)
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    captured = {}
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        captured.update(body=body) or
                        {"code": 201, "voiceIds": ["ext_vod-agent_t1"], "statuses": ["new"]})
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.delenv("VOD_ALLOW_UNKNOWN_PRODUCT", raising=False)   # 关掉旧客户端兼容开关
    # ① 没有回答、没有线索、用户没说不知道 → 拒绝并要求追问
    import pytest as _pytest
    with _pytest.raises(_net.ToolError) as ei:
        _collect.submit_voices({"voices": [{"content": "够长的一条反馈意见"}],
                             "confirmed": True}, client_info={"name": "t"})
    assert ei.value.code == -32010
    # ② 用户回答 → 按回答提交（source=user_answer）
    out = _collect.submit_voices({"voices": [{"content": "够长的一条反馈意见"}],
                               "product": "CodeArts", "confirmed": True},
                              client_info={"name": "t"})
    assert captured["body"].get("product") in ("1", "CodeArts")
    assert out["productSource"] == "user_answer" and out["productConfidence"] == "high"

def test_meta_fetch_and_cache(monkeypatch):
    """meta 端点可用：拉取→落 runtime 缓存→命中缓存不再请求。"""
    fetched = {"n": 0}
    saved = {}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        if path.endswith("/external/meta"):
            fetched["n"] += 1
            return {"code": 200, "data": {"products": ["codearts", "aishell"]}}
        raise AssertionError("不应有其他调用")

    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_http", fake_http)
    monkeypatch.setattr(_rt, "_save_runtime", lambda u: saved.update(u))
    m1 = _net._load_meta(force=True)
    assert m1["source"] == "meta" and m1["products"] == ["codearts", "aishell"]
    assert saved["meta_cache"]["data"]["products"] == ["codearts", "aishell"]
    # 缓存命中（_RT 被写回语义由 fake 保存体现；此处直接验证不再打端点）
    monkeypatch.setattr(_rt, "_RT", saved)
    m2 = _net._load_meta()
    assert m2["source"] == "cache" and fetched["n"] == 1


def test_meta_unreachable_falls_back_snapshot(monkeypatch):
    """meta 不可达：快照兜底+stale 标记（引导文案会带 [stale]）。"""
    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError("上游不可达", code=-32001)
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_http", fake_http)
    m = _net._load_meta(force=True)
    assert m["source"] == "snapshot" and m["stale"] is True
    # 快照不预置产品名（2026-11-13 纪律）：不可达=名录空，归因走追问而不是本地清单
    assert m["products"] == []


def test_hoarding_missing_voiceids_not_counted_success(monkeypatch):
    """回归锁（2026-11-06 codex 实锤）：引擎回执无 voiceIds 时不得兜底计成功
    ——旧行为 accepted=len(voices)、voiceId 填空串、账本记成功，宿主据此谎报已提交。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "message": "已入库"})  # 回执缺 voiceIds
    out = _collect.submit_voices(
        {"voices": [{"content": "体验不好的一条反馈"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 0, "回执缺 voiceIds 必须计 0 成功"
    assert out["voiceIds"] == [""]
    assert out["rejected"], "必须透出 rejected 说明结果未知"
    assert out["path"] == "hoarding"


def test_hoarding_engine_rejected_passthrough(monkeypatch):
    """引擎侧 rejected（产品校验拒绝等）必须透出到工具回执，不得吞掉。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "voiceIds": [],
                         "rejected": [{"reason": "产品未注册：NoSuchProduct"}]})
    out = _collect.submit_voices(
        {"voices": [{"content": "一条会被拒的反馈"}],
         "product": "NoSuchProduct", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 0
    assert any("NoSuchProduct" in str(r.get("reason", "")) for r in out["rejected"])


def test_attribution_chain_evidence_over_binding(monkeypatch):
    """优先级：用户明确回答 > 原话唯一高置信 > 记忆 > 安装先验。"""
    meta = {"products": ["CodeArts", "Maas"], "stale": False, "source": "meta",
            "catalog": [{"id": "1", "name": "CodeArts"}, {"id": "5", "name": "Maas"}],
            "nameAliases": {}, "aliases": {}}
    monkeypatch.setattr(_net, "_load_meta", lambda force=False: meta)
    captured = {}
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_rt, "_RT", {"product": "Maas"})
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        captured.update(body=body) or
                        {"code": 201, "voiceIds": ["ext_v1"], "statuses": ["new"]})
    # 原话唯一命中 CodeArts → 证据赢过安装先验 Maas
    out = _collect.submit_voices({"voices": [{"content": "CodeArts 导出失败"}],
                               "confirmed": True}, client_info={"name": "t"})
    assert captured["body"]["product"] == "1"
    assert out["productSource"] == "user_input"
    # 用户明确回答 → 回答赢过原话（"这条不是 CodeArts，是 Maas"）
    out2 = _collect.submit_voices({"voices": [{"content": "CodeArts 导出失败"}],
                                "product": "Maas", "confirmed": True},
                               client_info={"name": "t"})
    assert captured["body"]["product"] == "5"
    assert out2["productSource"] == "user_answer"

def test_attribution_accepts_explicit_answer_without_binding(monkeypatch):
    """无安装先验时，用户回答照样可提交（老口径"运行期传参一律不采信"已推翻）。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": [], "stale": False,
                                             "source": "meta", "catalog": []})
    captured = {}
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        captured.update(body=body) or
                        {"code": 201, "voiceIds": ["ext_v2"], "statuses": ["new"]})
    out = _collect.submit_voices({"voices": [{"content": "反馈四"}],
                               "product": "hermes", "confirmed": True},
                              client_info={"name": "t"})
    assert out["productSource"] == "user_answer"
    assert out["productConfidence"] == "low", "名录未命中=低置信（原样上报，引擎归一）"

def test_submit_echo_requires_verbatim_relay(monkeypatch):
    """方案 A 回归锁：回执必须携带 echo（原话回显），content 与提交原话逐字一致。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 201, "voiceIds": ["ext_vod-agent_e1"],
                         "statuses": ["new"]})
    out = _collect.submit_voices(
        {"voices": [{"content": "产品体验不好"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    e = out["echo"]
    assert e["requiresUserEcho"] is True
    assert e["contents"] == [{"voiceId": "ext_vod-agent_e1",
                              "content": "产品体验不好"}]
    assert "已收录原话" in e["instruction"]


def test_submit_echo_absent_when_nothing_accepted(monkeypatch):
    """整批被拒时 requiresUserEcho=false，无可回显内容。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "voiceIds": [],
                         "rejected": [{"reason": "产品未注册"}]})
    out = _collect.submit_voices(
        {"voices": [{"content": "x"}], "product": "NoSuchProduct",
         "confirmed": True},
        client_info={"name": "t"})
    assert out["echo"]["requiresUserEcho"] is False
    assert out["echo"]["contents"] == []


def test_content_boundary_rejects_oversize(monkeypatch):
    """内容边界：超 2000 字的反馈逐条拒绝（契约 maxLength 落到代码）。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 201, "voiceIds": ["ext_vod-agent_t1"], "statuses": ["new"]})
    out = _collect.submit_voices(
        {"voices": [{"content": "x" * 2001}, {"content": "正常长度的一条反馈"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1
    assert out["rejected"][0]["reason"].startswith("content 超 2000")


def test_ledger_and_list_submitted(monkeypatch, tmp_path):
    """层级①查询闭环：提交落账→list_submitted 读回（最新在前）；只动 submissions 键。"""
    rt_file = tmp_path / "runtime.json"
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "data": {"taskId": 5}})
    # 重定向 runtime 文件到 tmp（_save_runtime/_runtime_cfg 按模块常量路径）
    monkeypatch.setattr(_rt, "_runtime_cfg", lambda: (
        json.loads(rt_file.read_text()) if rt_file.exists() else {}))
    def _fake_save(upd):
        cfg = json.loads(rt_file.read_text()) if rt_file.exists() else {}
        cfg.update(upd)
        rt_file.write_text(json.dumps(cfg))
        return None

    monkeypatch.setattr(_rt, "_save_runtime", _fake_save)
    _collect.submit_voices({"voices": [{"content": "第一条反馈内容足够长"},
                                 {"content": "第二条反馈内容足够长"}],
                     "product": "codearts", "confirmed": True},
                    client_info={"name": "t"})
    _collect.submit_voices({"voices": [{"content": "第三条反馈内容足够长"}],
                     "product": "codearts", "confirmed": True},
                    client_info={"name": "t"})
    out = _collect.list_submitted({"limit": 2})
    assert out["total"] == 3
    assert [s["title"][:3] for s in out["submissions"]] == ["第三条", "第二条"], "最新在前"
    cfg = json.loads(rt_file.read_text())
    assert set(cfg) == {"submissions"}, "账本只动 submissions 键，不得触碰其他配置"


def test_transport_guard_rejects_http_public(monkeypatch):
    """传输守卫：http 只许本机回环，公网 http 拒绝（-32014）。"""
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    monkeypatch.setattr(_net, "JAVA_BASE", "http://vod-dev.topxtopx.com")
    with pytest.raises(_net.ToolError) as ei:
        _net._http("POST", "/x", {})
    assert ei.value.code == -32014 and "https" in str(ei.value)
    # 本机回环 http 允许（recorder/同机引擎场景）
    monkeypatch.setattr(_net, "JAVA_BASE", "http://127.0.0.1:9")
    try:
        _net._http("GET", "/health")
        assert False, "不可达但应报 -32001 而非协议拒绝"
    except _net.ToolError as e:
        assert e.code == -32001


# ---- key 安全三件（D-key-guard-1）：401 fail fast / 写后验 / 探针 ----

def test_explicit_key_rejected_401_fails_fast(monkeypatch):
    """显式 key（安装注入）被引擎 401 拒 → fail fast：不取匿名令牌、不覆盖 runtime.json。
    静默降级匿名=配置错误被吞=归因错位（D-key-guard-1 回归锁）。"""
    monkeypatch.setenv("VOD_JAVA_API_KEY", "formal-key-abc")
    monkeypatch.setattr(_net, "JAVA_KEY", "formal-key-abc")
    monkeypatch.setattr(_rt, "_RT", {})
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": [], "stale": True, "source": "snapshot"})
    fetched = []
    monkeypatch.setattr(_net, "_fetch_anon_token", lambda: fetched.append(1) or "tok")

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError("鉴权失败", code=-32012)

    monkeypatch.setattr(_net, "_http", fake_http)
    saved = []
    monkeypatch.setattr(_rt, "_save_runtime", lambda u: saved.append(u))
    with pytest.raises(_net.ToolError) as ei:
        _collect.submit_voices(
            {"voices": [{"content": "希望优化导出速度"}], "product": "codearts",
             "confirmed": True}, client_info={"name": "t"})
    assert "指纹" in str(ei.value) and "被引擎拒绝" in str(ei.value), "报错须带指纹与处置指引"
    assert not fetched, "显式 key 被拒不得触发匿名令牌链"
    assert not saved, "显式 key 被拒不得覆盖 runtime.json（防止假锚定）"


def test_anon_token_expired_401_refetches(monkeypatch):
    """匿名令牌过期 401 → 重领链保持（与显式 key fail fast 分流互斥）。"""
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    _rt._runtime_update({"java_key": "stale-anon-token", "token_tier": "anonymous"})
    monkeypatch.setattr(_rt, "_RT", {"token_tier": "anonymous"})
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": [], "stale": True, "source": "snapshot"})
    calls = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls.append((path, key))
        if path.endswith("/external/token"):
            return {"token": "fresh-anon"}
        if key == "fresh-anon":
            return {"code": 200, "voiceIds": ["ext_vod-agent_t2"]}
        raise _net.ToolError("鉴权失败", code=-32012)

    monkeypatch.setattr(_net, "_http", fake_http)
    out = _collect.submit_voices(
        {"voices": [{"content": "希望优化导出速度"}], "product": "codearts",
         "confirmed": True}, client_info={"name": "t"})
    assert out["accepted"] == 1, "匿名令牌失效应自动重领并提交成功"
    assert any(p.endswith("/external/token") for p, _ in calls)


def test_save_runtime_write_after_verify_0600(tmp_path, monkeypatch):
    """S1 式写后验：写后文件必须 0600（chmod 效果验证，不是动作验证）。"""
    import os as _os
    target = tmp_path / "runtime.json"
    monkeypatch.setattr(_rt, "_runtime_path", lambda: target)
    _rt._save_runtime({"java_key": "k1"})
    mode = _os.stat(target).st_mode & 0o777
    assert mode == 0o600, f"写后验必须把 runtime.json 收到 0600，实际 {oct(mode)}"
    cfg = json.loads(target.read_text())
    assert cfg["java_key"] == "k1"


def test_probe_key_three_verdicts(monkeypatch):
    """探针三态：200=有效 / 401=无效 / 网络错误=不判定（网络问题不是 key 问题）。"""
    monkeypatch.setenv("VOD_JAVA_API_KEY", "k-test")  # 显式 key 档（401=fail fast rejected）
    monkeypatch.setattr(_net, "JAVA_KEY", "k-test")

    def ok_http(method, path, body=None, timeout=30, base=None, key=None):
        assert path.endswith("/external/meta") and key == "k-test"
        return {"products": []}

    monkeypatch.setattr(_net, "_http", ok_http)
    assert _net.probe_key() == {"ok": True, "reason": "verified", "fingerprint": _net._fingerprint("k-test")}

    def denied(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError("401", code=401)

    monkeypatch.setattr(_net, "_http", denied)
    out = _net.probe_key()
    assert out["ok"] is False and out["reason"] == "rejected"

    def dead(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError("timeout", code=-32015)

    monkeypatch.setattr(_net, "_http", dead)
    out = _net.probe_key()
    assert out["ok"] is None and out["reason"] == "unreachable", "不可达≠无效"

    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setattr(_net, "JAVA_KEY", "")   # falsy 覆盖 → 走现读（runtime 为空）
    out = _net.probe_key()
    assert out == {"ok": None, "reason": "no-key", "fingerprint": None}


def test_probe_key_expired_anonymous_token(monkeypatch):
    """匿名令牌 401 → expired-anonymous（非 rejected）：runtime 残留过期匿名
    令牌不得被误读为正式 key 失效；note 指明下次提交自动重领。"""
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    _rt._runtime_update({"java_key": "anon-token-stale", "token_tier": "anonymous"})

    def denied(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError("401", code=401)

    monkeypatch.setattr(_net, "_http", denied)
    tier = str(_rt._RT.get("token_tier") or "")
    if tier != "anonymous":  # 仓内 runtime.json 若非匿名档则本用例前提不成立
        monkeypatch.setattr(_rt, "_RT", {**_rt._RT, "token_tier": "anonymous"})
    out = _net.probe_key()
    assert out["ok"] is False and out["reason"] == "expired-anonymous"
    assert "重领" in out["note"] and _net._fingerprint("anon-token-stale") == out["fingerprint"]


def test_probe_key_device_mismatch_is_not_rejected(monkeypatch):
    """匿名令牌设备锚点漂移 → device-mismatch（放行级），不是 rejected。

    实锤（2026-11-13 真机）：匿名令牌绑定设备（X-Vod-Device-Id=install_nonce），
    换机/重装/仓内与 payloads 两份 runtime 的 nonce 漂移时引擎 401 原文是
    「令牌与请求设备不匹配（设备绑定校验失败）」——token 本身有效，只是本机
    不是签发设备，提交时自动重领即可。这是正常场景：探针必须区分它和
    「API Key 无效或已失效」（真坏 key → rejected 拦截）。区分依据=引擎 401
    原文（_http 已透传，丢原文就是误拦根源）。
    显式传参（服务面 auth_status 传请求头 key）与本地档同语义：按原文判。
    """
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    _rt._runtime_update({"java_key": "anon-token-device-drift", "token_tier": "anonymous"})

    def mismatch(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError(
            "鉴权失败（https://vod-dev.topxtopx.com）："
            "令牌与请求设备不匹配（设备绑定校验失败），请在本设备重新申请令牌"
            "（POST /external/token）", code=-32012)

    monkeypatch.setattr(_net, "_http", mismatch)
    out = _net.probe_key("anon-token-device-drift")  # 显式传参（服务面场景）
    assert out["ok"] is False and out["reason"] == "device-mismatch"
    assert "重新申请" in out["note"] or "不匹配" in out["note"]
    assert out["reason"] != "rejected", "设备漂移不是坏 key，不许误拦"

    # 对照：真坏 key（引擎原文「API Key 无效」）即使显式传参也必须 rejected
    def invalid(method, path, body=None, timeout=30, base=None, key=None):
        raise _net.ToolError(
            "鉴权失败（https://vod-dev.topxtopx.com）："
            "API Key 无效或已失效，可重新申请令牌（POST /external/token）"
            "或联系 VOD 运营升级正式 key", code=-32012)

    monkeypatch.setattr(_net, "_http", invalid)
    out = _net.probe_key("explicitly-bad-key")
    assert out["ok"] is False and out["reason"] == "rejected"


def test_auth_status_no_key_material_anywhere(monkeypatch):
    """脱敏复查（D-key-guard-1③）：auth_status/账本全输出面 grep 不到 key 明文。"""
    secret = "super-secret-key-value-9f2e"  # secret-scan:allow 测试夹具
    monkeypatch.setattr(_net, "JAVA_KEY", secret)
    monkeypatch.setattr(_net, "probe_key", lambda: {"ok": None, "reason": "unreachable"})
    out = json.dumps(_core.auth_status({}, client_info={"name": "t"}))
    assert secret not in out, "key 明文禁止出现在任何工具输出"


# ---- VOD-DEVICE：设备锚点 header 协议锁 ----

def test_device_header_on_all_external_requests(monkeypatch):
    """锚点协议锁：所有 /external 请求（签发+提交）必须携带 X-Vod-Device-Id，
    取值=install_nonce（首启自生成常驻）——引擎据此建每设备独立锚点。"""
    import urllib.request
    seen = {}


    class FakeResp(io := __import__("io").BytesIO):
        def __init__(self):
            self.status = 200
        def read(self):
            return b"{}"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, *a, **kw):
        seen["device"] = req.headers.get("X-vod-device-id")
        seen["auth"] = req.headers.get("Authorization")
        return FakeResp()

    monkeypatch.setattr(_rt, "_install_nonce", lambda: "deadbeef")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(_net, "JAVA_KEY", "k")
    _net._http("GET", "/rest/developer/manager/hdvodmngservice/v1/external/meta", None)
    assert seen["device"] == "deadbeef", "设备锚点 header 必须随所有 external 请求上送"
    assert seen["auth"] == "Bearer k"


# ==================== D-anon-verify（2026-11-05 真机实锤）：信封契约与匿名链真源对齐 ====================

def test_anon_token_envelope_contract(monkeypatch):
    """S20 令牌端点信封契约（真源=ExternalTokenController ApiResponse）：
    data.token 必须被解析；此前顶层取值恒 None → 无 key 首提必 -32012。"""
    assert _net._extract_anon_token(
        {"code": 200, "message": "令牌已签发",
         "data": {"token": "env-tok", "dailyLimit": 50, "tier": "anonymous"}}
    ) == "env-tok", "引擎真实信封形态必须解析出 token"


def test_anon_token_flat_payload_compat():
    """S21 顶层扁平形态兼容（历史/降级引擎返回 {"token":...} 不破坏）。"""
    assert _net._extract_anon_token({"token": "flat-tok", "dailyLimit": 50}) == "flat-tok"


def test_anon_token_missing_or_garbage_returns_none():
    """信封无 token / 非字典 / 空 data → None（走 -32012 结构化引导，不误用垃圾值）。"""
    assert _net._extract_anon_token({"code": 200, "data": {"dailyLimit": 50}}) is None
    assert _net._extract_anon_token({"code": 200, "data": "not-a-dict"}) is None
    assert _net._extract_anon_token("garbage") is None
    assert _net._extract_anon_token({"token": 123}) is None, "非字符串 token 不得通过"


def test_legacy_key_removed_falls_to_anon_chain_e2e(monkeypatch):
    """S22 key 移除语义（D-key-guard 配套）：runtime.json 无 java_key →
    首提走匿名链自动签发 → 令牌以 java_key 槽落盘 + token_tier=anonymous 标记。"""
    monkeypatch.setattr(_net, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    calls = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls.append((method, path, key))
        if path.endswith("/external/token"):
            assert not key, "取令牌请求不得带 Bearer（零字段匿名入口）"
            return {"code": 200, "data": {"token": "fresh-anon-tok",
                                          "tier": "anonymous"}}
        if path.endswith("/external/voices"):
            if not key:
                # 真实时序：无 key 首提 401（对齐引擎 Filter 行为）→ 取令牌 → 重试
                raise _net.ToolError("鉴权失败（401）", code=-32012)
            assert key == "fresh-anon-tok", "取到令牌后重试必须携带新令牌"
            return {"code": 200, "data": {"accepted": 1,
                                          "voiceIds": ["ext_anonymous_t1"]}}
        return {}

    saved = {}
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)  # 现读：清空要走 env，setattr 会永久覆盖  # 模拟移除老平台 key 后的 runtime
    monkeypatch.setattr(_net, "_http", fake_http)
    monkeypatch.setattr(_rt, "_save_runtime", lambda u: saved.update(u))
    out = _collect.submit_voices(
        {"voices": [{"content": "匿名链端到端验证反馈"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1 and out["path"] == "hoarding"
    assert saved.get("token_tier") == "anonymous"
    assert any(p.endswith("/external/token") for m, p, _ in calls), "必须先取令牌"


def test_legacy_key_hint_contains_version_and_reinstall_command():
    """旧版残留凭据自愈提示（评审拍板项）：错误路径与 auth_status 检测位都带可操作指引。"""
    from vod_mcp import net as _net
    hint = _net._legacy_key_hint()
    assert "npx vod-devkit@latest install" in hint
    assert "当前 v" in hint  # 版本号在位
    src = ""
    base = Path(_net.__file__).resolve().parent            # src/vod_mcp
    for _rel in (("net.py",), ("packs", "collect"), ("packs", "core.py")):
        target = base.joinpath(*_rel)
        if target.is_dir():                                 # collect 拆包（ARCH-CALL-04）
            src += "".join(p.read_text(encoding="utf-8") for p in sorted(target.glob("*.py")))
        else:
            src += target.read_text(encoding="utf-8")
    # S238 起只剩囤积一条提交路径：定义 + 一处调用 = 2（legacy 回落已删）
    assert src.count("_raise_explicit_key_rejected(") >= 2  # 定义 + 囤积失败路径
    assert src.count("_legacy_key_hint()") >= 2  # 助手内 + auth_status 检测位


def test_key_resolution_priority_is_single_source(monkeypatch, tmp_path):
    """ARCH-CFG-05 验收：三入口优先级只由 net.resolve_key 定义，且 source 可如实报告。

    历史形态：判据散在 `_eff_key`/`_java_key`/`auth_status`/doctor 四处，注释顺序各异，
    "请求头 vs env 谁优先"要靠通读四个文件才能确认。
    """
    from vod_mcp import net
    from vod_mcp import runtime_state as rt

    monkeypatch.setattr(rt, "_RT", {})
    monkeypatch.setattr(net, "_REQ_KEY", net._REQ_KEY)      # 保持真实 ContextVar
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(rt, "_runtime_cfg", lambda: {})

    assert net.resolve_key()[1] == "none"

    monkeypatch.setattr(rt, "_RT", {"java_key": "mirror-key"})
    assert net.resolve_key() == ("mirror-key", "mirror")

    monkeypatch.setattr(rt, "_runtime_cfg", lambda: {"java_key": "runtime-key"})
    assert net.resolve_key() == ("runtime-key", "runtime")

    monkeypatch.setenv("VOD_JAVA_API_KEY", "env-key")
    assert net.resolve_key() == ("env-key", "env")

    tok = net._REQ_KEY.set("header-key")
    try:
        assert net.resolve_key() == ("header-key", "header")
        assert net.resolve_key("explicit-key") == ("explicit-key", "explicit")
        assert net._eff_key() == "header-key"               # 单点定义的直接后果
    finally:
        net._REQ_KEY.reset(tok)
