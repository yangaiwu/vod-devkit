"""S187：行为回归套件对引擎 5xx 的容错（D-engine-502-1 配套）。

实测事故（2026-11-17）：真机 `e2e_behavior.py --host codex --suite` 跑到第一条用例的
引擎对账环节就 `urllib.error.HTTPError: HTTP Error 502` 抛栈退出——整轮 10 分钟遥测
全丢，日志里只剩 traceback，看起来像产品回归。同一调用手工连打 5 次全 200：网关抖动，
不是代码问题。

三条边界：
- 5xx 先重试（退避），抖动恢复即继续，不丢轮次；
- 持续 5xx → EngineUnavailable（脚本给「不可判（环境故障）」并 exit 2），不是裸 traceback；
- 4xx 不重试不吞：401/403 是判定依据（鉴权档/设备绑定），要原样抛给上层当数据用。
"""
import importlib.util
import io
import sys
import urllib.error
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_SPEC = importlib.util.spec_from_file_location("e2e_behavior", _SCRIPTS / "e2e_behavior.py")
assert _SPEC is not None and _SPEC.loader is not None, "scripts/e2e_behavior.py 缺失"
e2e = importlib.util.module_from_spec(_SPEC)
sys.modules["e2e_behavior"] = e2e
_SPEC.loader.exec_module(e2e)


class _Resp:
    """最小 urlopen 回执替身：read() 出 JSON 体，支持 with（不继承 BytesIO，免覆写语义）。"""

    def __init__(self, payload: bytes, status: int = 200):
        self._buf = io.BytesIO(payload)
        self.status = status

    def read(self, *a):
        return self._buf.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def _row(**kw) -> bytes:
    import json as _json
    return _json.dumps({"code": 200, "data": {"voices": [kw]}}).encode()


def test_s187_retries_transient_5xx_then_returns_rows(monkeypatch):
    calls = []
    payload = _row(voiceId="VDPL1", title="原话", at="2999-01-01 00:00:00")

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", None, io.BytesIO(b""))
        return _Resp(payload)

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(e2e.time, "sleep", lambda *_: None)
    rows = e2e.engine_rows_since("2000-01-01 00:00:00")
    assert len(rows) == 1 and rows[0]["id"] == "VDPL1"
    assert len(calls) == 3, "5xx 应重试而不是立刻放弃"


def test_s187_persistent_5xx_raises_engine_unavailable(monkeypatch):
    def fake_urlopen(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", None, io.BytesIO(b""))

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(e2e.time, "sleep", lambda *_: None)
    try:
        e2e.engine_rows_since("2000-01-01 00:00:00")
    except e2e.EngineUnavailable as e:
        assert "502" in str(e), e
    else:
        raise AssertionError("持续 5xx 必须抛 EngineUnavailable（不能裸 traceback 丢整轮）")


def test_s187_4xx_is_judgement_data_not_retried(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, io.BytesIO(b""))

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(e2e.time, "sleep", lambda *_: None)
    try:
        e2e.engine_rows_since("2000-01-01 00:00:00")
    except urllib.error.HTTPError as e:
        assert e.code == 401
    else:
        raise AssertionError("401 必须原样抛出（鉴权/设备判定依据）")
    assert len(calls) == 1, "4xx 不得重试（重试只会放大鉴权压力）"


def test_s187_no_key_returns_empty_without_calling_engine(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("无 key 不应发请求")

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("", "https://e", ""))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", boom)
    assert e2e.engine_rows_since("2000-01-01 00:00:00") == []

# --- S188：宿主模型临时覆盖（网关模型漂移时继续验，不改宿主配置）------------------
# 实测（2026-11-17）：codex 默认模型 glm-5.3 在「需要工具调用」的回合上 5 次重连后
# `stream disconnected before completion`，正向用例（C1/C4/C5）全挂而负向（C2/C3）全绿；
# 同提示换 glm-5.3-flash 一次过（回执 version 0.5.30）。定责=网关侧模型，不是插件。
# 处置=套件支持 `--model` 临时覆盖（只改这一轮的 argv），**不改宿主配置文件**。
def test_s188_codex_model_override_goes_before_prompt():
    cmd = e2e.host_cmd("codex", "帮我记录反馈：x", model="glm-5.3-flash")
    assert cmd[:3] == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]
    assert cmd[-3:] == ["-m", "glm-5.3-flash", "帮我记录反馈：x"], "prompt 必须留在最后一位"


def test_s188_no_model_keeps_previous_argv():
    assert e2e.host_cmd("codex", "p") == ["codex", "exec",
                                          "--dangerously-bypass-approvals-and-sandbox", "p"]


def test_s188_opencode_uses_long_flag():
    cmd = e2e.host_cmd("opencode", "p", model="glm-5.3-flash")
    assert cmd[:2] == ["opencode", "run"]
    assert cmd[-3:] == ["--model", "glm-5.3-flash", "p"]


def test_s188_unknown_host_fails_loudly():
    try:
        e2e.host_cmd("nohost", "p")
    except SystemExit:
        pass
    else:
        raise AssertionError("未知宿主必须显式失败，不能静默跑错宿主")


# --- S189：回合无产出不得记违规（harness 伪影与模型违约分开）--------------------
# 实测（2026-11-17 真机，glm-5.3 掉流那轮）：C1/C4/C5 的 codex 回合以
# `stream disconnected before completion` 结束、`last_agent_message=null`，run_host 拿到空
# stdout、引擎 0 行——旧实现把这判成「原话被改写 5 项 + 回显缺失 15 项」记进熔断计数器，
# 一轮环境故障等于给模型记了 6 笔违规。判据：**空回复 + 零落库 = 不可判**，既不记违规
# 也不记 PASS；有落库时照常判（提交确实发生了，内容仍要查）。
def _cfg():
    return {"threshold": 2, "window_days": 7, "action": "report"}


def test_s189_empty_reply_and_no_rows_is_indeterminate(monkeypatch):
    rec = []
    monkeypatch.setattr(e2e, "run_host", lambda *a, **kw: "")
    monkeypatch.setattr(e2e, "_await_engine_rows", lambda *a, **kw: [])
    monkeypatch.setattr(e2e, "record_violation",
                        lambda host, kind, days=7: rec.append(kind) or 1)
    case = dict(e2e.SUITE[0])            # C1：expect_rows=1
    res = e2e.run_case("codex", case, _cfg())
    assert res.get("indeterminate"), "空回复 + 零落库必须标不可判"
    assert rec == [], f"不可判不许记违规：{rec}"
    assert res["fails"] == [], res["fails"]


def test_s189_rows_present_still_judged(monkeypatch):
    rec = []
    monkeypatch.setattr(e2e, "run_host", lambda *a, **kw: "")
    monkeypatch.setattr(e2e, "_await_engine_rows",
                        lambda *a, **kw: [{"id": "V1", "content": "被我改写的内容"}])
    monkeypatch.setattr(e2e, "record_violation",
                        lambda host, kind, days=7: rec.append(kind) or 1)
    case = dict(e2e.SUITE[0])
    res = e2e.run_case("codex", case, _cfg())
    assert not res.get("indeterminate"), "有落库就不能标不可判"
    assert "content_rewritten" in rec, "落库内容要照常判改写"


def test_s189_normal_reply_no_rows_still_fails(monkeypatch):
    rec = []
    monkeypatch.setattr(e2e, "run_host", lambda *a, **kw: "我已经记录好了")
    monkeypatch.setattr(e2e, "_await_engine_rows", lambda *a, **kw: [])
    monkeypatch.setattr(e2e, "record_violation",
                        lambda host, kind, days=7: rec.append(kind) or 1)
    case = dict(e2e.SUITE[0])
    res = e2e.run_case("codex", case, _cfg())
    assert not res.get("indeterminate"), "有回复就该判（模型说了提交却没落库=真缺陷）"
    assert any("未产生落库" in f for f in res["fails"]), res["fails"]
