"""认证与令牌链路测试：auth_status 指纹化（明文永不输出）+ 零字段令牌自动获取。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vod_mcp import tools  # noqa: E402


def test_auth_status_fingerprint_not_plaintext(monkeypatch):
    monkeypatch.setattr(tools, "probe_key", lambda: {"ok": None, "reason": "unreachable"})  # 隔网
    out = tools.auth_status({}, client_info={"name": "t"})
    fp = out["javaKey"]["fingerprint"]
    assert fp is None or (len(fp) == 8 and fp != tools.JAVA_KEY), \
        "key 只能以 8 位指纹出现，明文禁止（fingerprint 纪律）"
    assert "packs" in out
    assert "workflowKey" not in out, "方案 A：单上游，无 workflowKey"


def test_auth_status_no_key_gives_guidance(monkeypatch):
    monkeypatch.setattr(tools, "JAVA_KEY", "")
    out = tools.auth_status({}, client_info={})
    assert out["javaKey"]["configured"] is False
    assert [g["order"] for g in out["guidance"]] == [1, 2, 3], \
        "缺 key 时必须给三步引导（令牌/升级/宿主）"
    assert "自动" in out["guidance"][0]["label"]


def test_submit_voices_auto_token_then_retry(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta",
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
            raise tools.ToolError("鉴权失败：检查 key", code=-32012)
        return {}

    saved = {}

    def fake_save(update):
        saved.update(update)

    monkeypatch.setattr(tools, "JAVA_KEY", "")
    monkeypatch.setattr(tools, "_http", fake_http)
    monkeypatch.setattr(tools, "_save_runtime", fake_save)
    out = tools.submit_voices(
        {"voices": [{"content": "补全响应有点慢，希望优化一下"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1 and out["path"] == "hoarding"
    assert out["voiceIds"] == ["ext_vod-agent_t1"]  # 囤积语义：无即时任务，id=引擎算
    assert state["token_issued"], "必须先取令牌"
    assert saved.get("java_key") == "anon-token-xyz"
    assert saved.get("token_tier") == "anonymous"
    assert tools.JAVA_KEY == "anon-token-xyz", "令牌应回填运行时供后续复用"


def test_submit_voices_token_unreachable_gives_guidance(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": True, "source": "snapshot"})
    """令牌端点不可用（引擎未上线）→ 结构化引导错误，不是死胡同。"""
    monkeypatch.setattr(tools, "JAVA_KEY", "")

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise tools.ToolError("上游返回 404: Not Found", code=404)  # 对齐真实 _http：HTTP 状态进 code

    monkeypatch.setattr(tools, "_http", fake_http)
    with pytest.raises(tools.ToolError) as ei:
        tools.submit_voices(
            {"voices": [{"content": "反馈内容足够长的一条意见"}],
             "product": "codearts", "confirmed": True},
            client_info={"name": "t"})
    assert "引导" in str(ei.value) and "自动" in str(ei.value), \
        "令牌不可用时错误必须带引导步骤"


def test_voice_volume_preserved_across_calls(monkeypatch):
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    """R1 声量保真：不同调用提交同款反馈 → 不同 voiceId，各占一行。

    （曾为缺陷：确定性 voiceId 使第二个用户同款反馈被去重吞掉，
    声量统计失真——此测试为永久回归锁。）
    """
    seen = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        if path.endswith("/external/voices"):
            # 囤积主路径：voiceId 由引擎按 per-token 命名空间算（server 侧职责），
            # 客户端锁的是“把完整 content 原样交给引擎”+ 404 回落
            raise tools.ToolError("上游返回 404: not found", code=404)
        if path.endswith("/external/voice/submit"):
            seen.append(body["voiceId"])
            return {"code": 200, "data": {"taskId": len(seen)}}
        return {}

    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http", fake_http)
    voice = {"content": "补全响应有点慢，希望优化一下"}
    for _ in range(2):
        out = tools.submit_voices({"voices": [voice], "product": "codearts",
                                   "confirmed": True},
                                  client_info={"name": "mcp"})
        assert out["accepted"] == 1 and out["path"] == "legacy-fallback"
    assert len(set(seen)) == 2, "404 回落老链：同款反馈跨调用必须不去重（R1 声量保真锁）"

    # title 必须是用户原文（R3：分析消费原话；囤积链 voices[].title=content 截断）
    def fake2(method, path, body=None, timeout=30, base=None, key=None):
        assert body["voices"][0]["title"] == voice["content"], "title=用户原文，禁止模板污染"
        return {"code": 200, "voiceIds": ["ext_vod-agent_x"]}
    monkeypatch.setattr(tools, "_http", fake2)
    tools.submit_voices({"voices": [voice], "product": "codearts", "confirmed": True},
                        client_info={"name": "mcp"})


def test_product_id_resolution_t7i(monkeypatch):
    """T7i（方案 A，2026-11-05 拍板）：产品归因主键化——
    ①名字+meta productCatalog → 解析出平台 id 提交（对账主键化）
    ②纯数字=平台 id 原样透传（引擎 selectById 精确命中）
    ③目录无此名/目录不可用 → 规范名上送（引擎 name 兼容通道，不静默丢）"""
    cat = [{"id": 31, "name": "CodeArts"}, {"id": 42, "name": "AIShell"}]

    def fake_meta(force=False):
        return {"products": ["codearts"], "catalog": cat,
                "stale": False, "source": "cache"}

    monkeypatch.setattr(tools, "_load_meta", fake_meta)
    # ① 短码先归一再查目录 → id
    assert tools._resolve_product({"product": "codearts"}) == "31"
    assert tools._resolve_product({"product": "CodeArts"}) == "31"
    assert tools._resolve_product({"product": "aishell"}) == "42"
    # ② 纯数字=平台 id 透传（不查目录）
    assert tools._resolve_product({"product": "31"}) == "31"
    # ③ 目录无此名 → 规范名原样（兼容回落）
    assert tools._resolve_product({"product": "hermes"}) == "hermes"
    # ③' 目录不可用（快照/老引擎 catalog 空）→ 名字通道
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": [], "catalog": [],
                                             "stale": True, "source": "snapshot"})
    assert tools._resolve_product({"product": "codearts"}) == "CodeArts"


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

    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_http", fake_http)
    monkeypatch.setattr(tools, "_save_runtime", lambda u: saved.update(u))
    m1 = tools._load_meta(force=True)
    assert m1["catalog"] == [{"id": 31, "name": "CodeArts"}]
    monkeypatch.setattr(tools, "_RT", saved)
    m2 = tools._load_meta()
    assert fetched["n"] == 1  # 缓存命中零二次请求
    assert m2["catalog"] == [{"id": 31, "name": "CodeArts"}]
    # 老引擎无 productCatalog 键 → catalog 空不崩
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "data": {"products": ["codearts"]}})
    assert tools._load_meta(force=True)["catalog"] == []


def test_product_attribution_layers(monkeypatch):
    """归因（宿主即产品·不设白名单，2026-11-03 拍板）：显式传参 > 安装绑定 >
    无归因（不再 -32013 本地拦截，body 不带 product → 引擎 UNKNOWN 档）。"""
    # ③ 无绑定无传参 → 不拦截：body 不带 product（引擎落 UNKNOWN 档人工归因）
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    captured = {}
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        captured.update(body=body) or {"code": 201, "voiceIds": ["ext_vod-agent_t1"], "statuses": ["new"]})
    out = tools.submit_voices({"voices": [{"content": "够长的一条反馈意见"}],
                                "confirmed": True}, client_info={"name": "t"})
    assert out["accepted"] == 1 and "product" not in captured["body"]

    # ③' 宿主自报产品（不在任何白名单）原样上送，不拒收
    out = tools.submit_voices({"voices": [{"content": "够长的一条反馈意见"}],
                                "product": "hermes", "confirmed": True},
                              client_info={"name": "t"})
    assert out["accepted"] == 1 and captured["body"]["product"] == "hermes"

    # ① 绑定生效（无传参取 runtime 绑定）
    monkeypatch.setattr(tools, "_RT", {"product": "aishell"})
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 201, "voiceIds": ["ext_vod-agent_t1"], "statuses": ["new"]})
    out = tools.submit_voices({"voices": [{"content": "够长的一条反馈意见"}],
                               "confirmed": True}, client_info={"name": "t"})
    assert out["accepted"] == 1


def test_meta_fetch_and_cache(monkeypatch):
    """meta 端点可用：拉取→落 runtime 缓存→命中缓存不再请求。"""
    fetched = {"n": 0}
    saved = {}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        if path.endswith("/external/meta"):
            fetched["n"] += 1
            return {"code": 200, "data": {"products": ["codearts", "aishell"]}}
        raise AssertionError("不应有其他调用")

    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_http", fake_http)
    monkeypatch.setattr(tools, "_save_runtime", lambda u: saved.update(u))
    m1 = tools._load_meta(force=True)
    assert m1["source"] == "meta" and m1["products"] == ["codearts", "aishell"]
    assert saved["meta_cache"]["data"]["products"] == ["codearts", "aishell"]
    # 缓存命中（_RT 被写回语义由 fake 保存体现；此处直接验证不再打端点）
    monkeypatch.setattr(tools, "_RT", saved)
    m2 = tools._load_meta()
    assert m2["source"] == "cache" and fetched["n"] == 1


def test_meta_unreachable_falls_back_snapshot(monkeypatch):
    """meta 不可达：快照兜底+stale 标记（引导文案会带 [stale]）。"""
    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise tools.ToolError("上游不可达", code=-32001)
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_http", fake_http)
    m = tools._load_meta(force=True)
    assert m["source"] == "snapshot" and m["stale"] is True
    assert "codearts" in m["products"]


def test_hoarding_missing_voiceids_not_counted_success(monkeypatch):
    """回归锁（2026-11-06 codex 实锤）：引擎回执无 voiceIds 时不得兜底计成功
    ——旧行为 accepted=len(voices)、voiceId 填空串、账本记成功，宿主据此谎报已提交。"""
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "message": "已入库"})  # 回执缺 voiceIds
    out = tools.submit_voices(
        {"voices": [{"content": "体验不好的一条反馈"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 0, "回执缺 voiceIds 必须计 0 成功"
    assert out["voiceIds"] == [""]
    assert out["rejected"], "必须透出 rejected 说明结果未知"
    assert out["path"] == "hoarding"


def test_hoarding_engine_rejected_passthrough(monkeypatch):
    """引擎侧 rejected（产品校验拒绝等）必须透出到工具回执，不得吞掉。"""
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "voiceIds": [],
                         "rejected": [{"reason": "产品未注册：NoSuchProduct"}]})
    out = tools.submit_voices(
        {"voices": [{"content": "一条会被拒的反馈"}],
         "product": "NoSuchProduct", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 0
    assert any("NoSuchProduct" in str(r.get("reason", "")) for r in out["rejected"])


def test_submit_echo_requires_verbatim_relay(monkeypatch):
    """方案 A 回归锁：回执必须携带 echo（原话回显），content 与提交原话逐字一致。"""
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 201, "voiceIds": ["ext_vod-agent_e1"],
                         "statuses": ["new"]})
    out = tools.submit_voices(
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
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "voiceIds": [],
                         "rejected": [{"reason": "产品未注册"}]})
    out = tools.submit_voices(
        {"voices": [{"content": "x"}], "product": "NoSuchProduct",
         "confirmed": True},
        client_info={"name": "t"})
    assert out["echo"]["requiresUserEcho"] is False
    assert out["echo"]["contents"] == []


def test_content_boundary_rejects_oversize(monkeypatch):
    """内容边界：超 2000 字的反馈逐条拒绝（契约 maxLength 落到代码）。"""
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 201, "voiceIds": ["ext_vod-agent_t1"], "statuses": ["new"]})
    out = tools.submit_voices(
        {"voices": [{"content": "x" * 2001}, {"content": "正常长度的一条反馈"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1
    assert out["rejected"][0]["reason"].startswith("content 超 2000")


def test_ledger_and_list_submitted(monkeypatch, tmp_path):
    """层级①查询闭环：提交落账→list_submitted 读回（最新在前）；只动 submissions 键。"""
    rt_file = tmp_path / "runtime.json"
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": ["codearts"],
                                             "stale": False, "source": "meta"})
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "_http",
                        lambda m, p, body=None, timeout=30, base=None, key=None:
                        {"code": 200, "data": {"taskId": 5}})
    # 重定向 runtime 文件到 tmp（_save_runtime/_runtime_cfg 按模块常量路径）
    import vod_mcp.tools as T
    monkeypatch.setattr(T, "_runtime_cfg", lambda: (
        json.loads(rt_file.read_text()) if rt_file.exists() else {}))
    def _fake_save(upd):
        cfg = json.loads(rt_file.read_text()) if rt_file.exists() else {}
        cfg.update(upd)
        rt_file.write_text(json.dumps(cfg))
        return None

    monkeypatch.setattr(T, "_save_runtime", _fake_save)
    T.submit_voices({"voices": [{"content": "第一条反馈内容足够长"},
                                 {"content": "第二条反馈内容足够长"}],
                     "product": "codearts", "confirmed": True},
                    client_info={"name": "t"})
    T.submit_voices({"voices": [{"content": "第三条反馈内容足够长"}],
                     "product": "codearts", "confirmed": True},
                    client_info={"name": "t"})
    out = T.list_submitted({"limit": 2})
    assert out["total"] == 3
    assert [s["title"][:3] for s in out["submissions"]] == ["第三条", "第二条"], "最新在前"
    cfg = json.loads(rt_file.read_text())
    assert set(cfg) == {"submissions"}, "账本只动 submissions 键，不得触碰其他配置"


def test_transport_guard_rejects_http_public(monkeypatch):
    """传输守卫：http 只许本机回环，公网 http 拒绝（-32014）。"""
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    monkeypatch.setattr(tools, "JAVA_BASE", "http://vod-dev.topxtopx.com")
    with pytest.raises(tools.ToolError) as ei:
        tools._http("POST", "/x", {})
    assert ei.value.code == -32014 and "https" in str(ei.value)
    # 本机回环 http 允许（recorder/同机引擎场景）
    monkeypatch.setattr(tools, "JAVA_BASE", "http://127.0.0.1:9")
    try:
        tools._http("GET", "/health")
        assert False, "不可达但应报 -32001 而非协议拒绝"
    except tools.ToolError as e:
        assert e.code == -32001


# ---- key 安全三件（D-key-guard-1）：401 fail fast / 写后验 / 探针 ----

def test_explicit_key_rejected_401_fails_fast(monkeypatch):
    """显式 key（安装注入）被引擎 401 拒 → fail fast：不取匿名令牌、不覆盖 runtime.json。
    静默降级匿名=配置错误被吞=归因错位（D-key-guard-1 回归锁）。"""
    monkeypatch.setenv("VOD_JAVA_API_KEY", "formal-key-abc")
    monkeypatch.setattr(tools, "JAVA_KEY", "formal-key-abc")
    monkeypatch.setattr(tools, "_RT", {})
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": [], "stale": True, "source": "snapshot"})
    fetched = []
    monkeypatch.setattr(tools, "_fetch_anon_token", lambda: fetched.append(1) or "tok")

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        raise tools.ToolError("鉴权失败", code=-32012)

    monkeypatch.setattr(tools, "_http", fake_http)
    saved = []
    monkeypatch.setattr(tools, "_save_runtime", lambda u: saved.append(u))
    with pytest.raises(tools.ToolError) as ei:
        tools.submit_voices(
            {"voices": [{"content": "希望优化导出速度"}], "product": "codearts",
             "confirmed": True}, client_info={"name": "t"})
    assert "指纹" in str(ei.value) and "被引擎拒绝" in str(ei.value), "报错须带指纹与处置指引"
    assert not fetched, "显式 key 被拒不得触发匿名令牌链"
    assert not saved, "显式 key 被拒不得覆盖 runtime.json（防止假锚定）"


def test_anon_token_expired_401_refetches(monkeypatch):
    """匿名令牌过期 401 → 重领链保持（与显式 key fail fast 分流互斥）。"""
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setattr(tools, "JAVA_KEY", "stale-anon-token")
    monkeypatch.setattr(tools, "_RT", {"token_tier": "anonymous"})
    monkeypatch.setattr(tools, "_load_meta",
                        lambda force=False: {"products": [], "stale": True, "source": "snapshot"})
    calls = []

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        calls.append((path, key))
        if path.endswith("/external/token"):
            return {"token": "fresh-anon"}
        if key == "fresh-anon":
            return {"code": 200, "voiceIds": ["ext_vod-agent_t2"]}
        raise tools.ToolError("鉴权失败", code=-32012)

    monkeypatch.setattr(tools, "_http", fake_http)
    monkeypatch.setattr(tools, "_save_runtime", lambda u: None)
    out = tools.submit_voices(
        {"voices": [{"content": "希望优化导出速度"}], "product": "codearts",
         "confirmed": True}, client_info={"name": "t"})
    assert out["accepted"] == 1, "匿名令牌失效应自动重领并提交成功"
    assert any(p.endswith("/external/token") for p, _ in calls)


def test_save_runtime_write_after_verify_0600(tmp_path, monkeypatch):
    """S1 式写后验：写后文件必须 0600（chmod 效果验证，不是动作验证）。"""
    import os as _os
    target = tmp_path / "runtime.json"
    monkeypatch.setattr(tools, "_runtime_path", lambda: target)
    tools._save_runtime({"java_key": "k1"})
    mode = _os.stat(target).st_mode & 0o777
    assert mode == 0o600, f"写后验必须把 runtime.json 收到 0600，实际 {oct(mode)}"
    cfg = json.loads(target.read_text())
    assert cfg["java_key"] == "k1"


def test_probe_key_three_verdicts(monkeypatch):
    """探针三态：200=有效 / 401=无效 / 网络错误=不判定（网络问题不是 key 问题）。"""
    monkeypatch.setattr(tools, "JAVA_KEY", "k-test")

    def ok_http(method, path, body=None, timeout=30, base=None, key=None):
        assert path.endswith("/external/meta") and key == "k-test"
        return {"products": []}

    monkeypatch.setattr(tools, "_http", ok_http)
    assert tools.probe_key() == {"ok": True, "reason": "verified", "fingerprint": tools._fingerprint("k-test")}

    def denied(method, path, body=None, timeout=30, base=None, key=None):
        raise tools.ToolError("401", code=401)

    monkeypatch.setattr(tools, "_http", denied)
    out = tools.probe_key()
    assert out["ok"] is False and out["reason"] == "rejected"

    def dead(method, path, body=None, timeout=30, base=None, key=None):
        raise tools.ToolError("timeout", code=-32015)

    monkeypatch.setattr(tools, "_http", dead)
    out = tools.probe_key()
    assert out["ok"] is None and out["reason"] == "unreachable", "不可达≠无效"

    monkeypatch.setattr(tools, "JAVA_KEY", "")
    out = tools.probe_key()
    assert out == {"ok": None, "reason": "no-key", "fingerprint": None}


def test_auth_status_no_key_material_anywhere(monkeypatch):
    """脱敏复查（D-key-guard-1③）：auth_status/账本全输出面 grep 不到 key 明文。"""
    secret = "super-secret-key-value-9f2e"
    monkeypatch.setattr(tools, "JAVA_KEY", secret)
    monkeypatch.setattr(tools, "probe_key", lambda: {"ok": None, "reason": "unreachable"})
    out = json.dumps(tools.auth_status({}, client_info={"name": "t"}))
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

    monkeypatch.setattr(tools, "_install_nonce", lambda: "deadbeef")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tools, "JAVA_KEY", "k")
    tools._http("GET", "/rest/developer/manager/hdvodmngservice/v1/external/meta", None)
    assert seen["device"] == "deadbeef", "设备锚点 header 必须随所有 external 请求上送"
    assert seen["auth"] == "Bearer k"


# ==================== D-anon-verify（2026-11-05 真机实锤）：信封契约与匿名链真源对齐 ====================

def test_anon_token_envelope_contract(monkeypatch):
    """S20 令牌端点信封契约（真源=ExternalTokenController ApiResponse）：
    data.token 必须被解析；此前顶层取值恒 None → 无 key 首提必 -32012。"""
    assert tools._extract_anon_token(
        {"code": 200, "message": "令牌已签发",
         "data": {"token": "env-tok", "dailyLimit": 50, "tier": "anonymous"}}
    ) == "env-tok", "引擎真实信封形态必须解析出 token"


def test_anon_token_flat_payload_compat():
    """S21 顶层扁平形态兼容（历史/降级引擎返回 {"token":...} 不破坏）。"""
    assert tools._extract_anon_token({"token": "flat-tok", "dailyLimit": 50}) == "flat-tok"


def test_anon_token_missing_or_garbage_returns_none():
    """信封无 token / 非字典 / 空 data → None（走 -32012 结构化引导，不误用垃圾值）。"""
    assert tools._extract_anon_token({"code": 200, "data": {"dailyLimit": 50}}) is None
    assert tools._extract_anon_token({"code": 200, "data": "not-a-dict"}) is None
    assert tools._extract_anon_token("garbage") is None
    assert tools._extract_anon_token({"token": 123}) is None, "非字符串 token 不得通过"


def test_legacy_key_removed_falls_to_anon_chain_e2e(monkeypatch):
    """S22 key 移除语义（D-key-guard 配套）：runtime.json 无 java_key →
    首提走匿名链自动签发 → 令牌以 java_key 槽落盘 + token_tier=anonymous 标记。"""
    monkeypatch.setattr(tools, "_load_meta",
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
                raise tools.ToolError("鉴权失败（401）", code=-32012)
            assert key == "fresh-anon-tok", "取到令牌后重试必须携带新令牌"
            return {"code": 200, "data": {"accepted": 1,
                                          "voiceIds": ["ext_anonymous_t1"]}}
        return {}

    saved = {}
    monkeypatch.setattr(tools, "JAVA_KEY", "")  # 模拟移除老平台 key 后的 runtime
    monkeypatch.setattr(tools, "_http", fake_http)
    monkeypatch.setattr(tools, "_save_runtime", lambda u: saved.update(u))
    out = tools.submit_voices(
        {"voices": [{"content": "匿名链端到端验证反馈"}],
         "product": "codearts", "confirmed": True},
        client_info={"name": "t"})
    assert out["accepted"] == 1 and out["path"] == "hoarding"
    assert saved.get("token_tier") == "anonymous"
    assert any(p.endswith("/external/token") for m, p, _ in calls), "必须先取令牌"
