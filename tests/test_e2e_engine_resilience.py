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
    except e2e.EngineAuthError as e:      # S192：4xx 改抛专用异常（语义仍是「原样上抛、不吞」）
        assert "401" in str(e)
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


# --- S192：退出码分档 + 回执不可判（评审 2026-11-17 P1）--------------------------
# 实测问题：
# ① S189 只堵了「空回复 + 零落库」；「空回复 + 有落库」（流在最后一帧断，工具调用已落库）
#    仍把报文自己写着「不可判」的那行放进 fails → main 走 exit 1，和「产品回归」同码。
# ② exit 2 有三重语义：EngineUnavailable / 熔断 action=exit / indeterminate，自动化读 2
#    分不清「产品熔断」和「环境没结论」；而 4xx（鉴权档/设备绑定）按 ADR 要原样抛出，
#    main 却没人接 → 裸 traceback → 退出码 1，同样冒充违规。
# 定档：0 全绿 / 1 真违规 / 2 熔断 / 3 不可判（含回执不可判）/ 4 鉴权或引擎 4xx。
def test_s192_exit_code_table():
    assert e2e.exit_code([], "report", indeterminate=False) == 0
    assert e2e.exit_code(["真缺陷"], "report", indeterminate=False) == 1
    assert e2e.exit_code([], "exit", indeterminate=False) == 2
    assert e2e.exit_code([], "report", indeterminate=True) == 3
    assert e2e.exit_code([], "report", indeterminate=False, auth_error=True) == 4
    # 优先级：真违规 > 熔断 > 不可判 > 鉴权
    assert e2e.exit_code(["真缺陷"], "exit", indeterminate=True) == 1


def test_s192_empty_reply_with_rows_is_reply_indeterminate(monkeypatch):
    """空回复 + 有落库：回执线不可判，不许进 fails（否则 exit 1 冒充产品回归）。"""
    rec = []
    prompt, start = e2e.render_with_offset(dict(e2e.SUITE[0]))
    rows = [{"id": "V1", "content": prompt[start:][:e2e.VERBATIM_WINDOW]}]
    monkeypatch.setattr(e2e, "run_host", lambda *a, **kw: "")
    monkeypatch.setattr(e2e, "_await_engine_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(e2e, "record_violation",
                        lambda host, kind, days=7: rec.append(kind) or 1)
    res = e2e.run_case("codex", dict(e2e.SUITE[0]),
                       {"threshold": 2, "window_days": 7, "action": "report"})
    assert res["fails"] == [], res["fails"]
    assert res.get("reply_indeterminate"), "空回复必须单独标回执不可判"
    assert rec == [], f"不可许记违规：{rec}"


def test_s192_engine_4xx_raises_auth_error(monkeypatch):
    def fake_urlopen(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, io.BytesIO(b""))

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    try:
        e2e.engine_rows_since("2000-01-01 00:00:00")
    except e2e.EngineAuthError as e:
        assert "401" in str(e)
    else:
        raise AssertionError("4xx 必须抛 EngineAuthError（main 据此 exit 4，不许裸 traceback）")


def test_s192_banner_prints_model_and_argv(capsys):
    e2e.print_run_banner("codex", "glm-5.3-flash", e2e.host_cmd("codex", "p", "glm-5.3-flash"))
    out = capsys.readouterr().out
    assert "model=glm-5.3-flash" in out and "argv=" in out, out


# --- S194：回执不可判不得吞内容违规；异常路径不得丢已收违规（2026-11-17 评审 P1/P2）---
# 评审实测：C1 引擎内容被改写 + 宿主回复为空 → reply_indeterminate=True、fails=[]、
# 本地记账 ['content_rewritten']、exit 3。也就是「不可判」把**内容线已得出的结论**一起吞了，
# 自动化只读退出码与报文 → 真违规看不见。这正是 S189/S192 自己写的红线：
# 不可判只该管回执线，不得兜住真缺陷。
def test_s194_rewritten_content_survives_reply_indeterminate(monkeypatch):
    rec = []
    prompt, start = e2e.render_with_offset(dict(e2e.SUITE[0]))
    rows = [{"id": "V1", "content": "被我改写过的内容"}]          # 内容≠原话前缀
    monkeypatch.setattr(e2e, "run_host", lambda *a, **kw: "")
    monkeypatch.setattr(e2e, "_await_engine_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(e2e, "record_violation",
                        lambda host, kind, days=7: rec.append(kind) or 1)
    res = e2e.run_case("codex", dict(e2e.SUITE[0]),
                       {"threshold": 2, "window_days": 7, "action": "report"})
    assert res.get("reply_indeterminate"), "空回复仍要标回执不可判"
    assert res["fails"], "内容被改写必须留在 fails 里（不可判只管回显线）"
    assert any("改写" in f for f in res["fails"]), res["fails"]
    assert e2e.exit_code(res["fails"], "report", indeterminate=True) == 1, \
        "有真违规 → exit 1（优先级 1 > 3）"


def test_s194_exception_path_keeps_collected_violations():
    """异常路径（引擎 5xx / 4xx）不得把已经收到的违规冲成「没结论」。

    编排层由 tests/test_e2e_orchestration.py 的 run_suite 用例覆盖；这里锁退出码底表：
    有违规时两种异常都不得降级。
    """
    assert e2e.exit_code(["真缺陷"], "report", indeterminate=True, auth_error=True) == 1
    assert e2e.exit_code([], "report", auth_error=True) == 4
    assert e2e.exit_code([], "report", indeterminate=True) == 3


def test_s194_remaining_count_is_not_total():
    """异常报文里的「未完成 N 条」必须是剩余数，不是计划总数。"""
    assert e2e.remaining_cases(total=5, processed=2) == 3
    assert e2e.remaining_cases(total=5, processed=5) == 0


# --- S197：每轮 e2e 必须自动落一份带 host/model 的日志（评审第 5 条）---------------
# 现状：日志靠调用方手工重定向，kill 掉的那两轮留下 0 字节文件，真机结论只能靠 codex
# 会话文件反推。判据：脚本自己 tee 一份到 <repo>/.e2e-runs/<ts>-<host>-<model>.log。
def test_s197_run_log_path_names_host_and_model(tmp_path):
    p = e2e.run_log_path("codex", "glm-5.3-flash", root=tmp_path)
    assert p.parent == tmp_path
    assert "codex" in p.name and "glm-5.3-flash" in p.name and p.suffix == ".log"


def test_s197_run_log_path_defaults_to_repo_runs_dir():
    p = e2e.run_log_path("codex", None)
    assert p.parent.name == ".e2e-runs"
    assert "default" in p.name, "未指定模型也要在文件名里标出来（事后审计要知道跑的是默认模型）"


def test_s197_tee_writes_both_streams(tmp_path):
    f = (tmp_path / "x.log").open("w", encoding="utf-8")
    tee = e2e.Tee(sys.stdout, f)
    tee.write("hello\n")
    tee.flush()
    f.close()
    assert "hello" in (tmp_path / "x.log").read_text(encoding="utf-8")


# --- S201：日志必须"写即可见"，且被 kill 也要能看出跑到第几案 --------------------
# 评审现场（2026-11-17 16:50 那轮）：`.e2e-runs/*.log` 全程 0 字节，而调用方重定向的同轮日志
# 有 610 字节、没有 e2e[exit] 收尾行。根因=`Tee.write` 只转发不 flush，文件按块缓冲；
# `atexit` 只覆盖正常退出，被 kill 时缓冲全丢。旧用例先手动 `tee.flush()` 再读，测的是
# 生产路径不会发生的调用顺序——所以绿着失效。
def test_s201_tee_is_visible_without_manual_flush(tmp_path):
    f = (tmp_path / "x.log").open("w", encoding="utf-8")
    tee = e2e.Tee(sys.stdout, f)
    tee.write("line-without-flush\n")          # 不调 flush
    assert "line-without-flush" in (tmp_path / "x.log").read_text(encoding="utf-8"), \
        "Tee.write 必须立即落盘（否则被 kill 的轮次留下 0 字节日志）"
    f.close()


def test_s201_run_suite_prints_case_heartbeat(monkeypatch, capsys):
    """每案开始先打一行心跳：进程被 kill 时也能看出跑到第几案。"""
    monkeypatch.setattr("e2e_behavior.run_case",
                        lambda host, case, cfg, model=None: {"case": case["id"], "rule": "r",
                                                             "fails": [], "rows": []})
    cases = [{"id": "c1", "rule": "r", "prompt": "p", "expect": "submit_consent"},
             {"id": "c2", "rule": "r", "prompt": "p", "expect": "submit_consent"}]
    e2e.run_suite("codex", cases, {"threshold": 2, "window_days": 7, "action": "report"})
    out = capsys.readouterr().out
    assert "[case 1/2] c1" in out and "[case 2/2] c2" in out, out


# --- S214：引擎查询覆盖不到囤积档时不许判 FAIL，也不许判 PASS（只能不可判）----------
# 实测（2026-11-17 18:35 轮）：codex 回执 `accepted:1 / voiceIds:[VDPL202611170027]`，
# 但 GET /external/voices（同一 key、同一 X-Vod-Device-Id）返回的 11 行最新 at=2026-11-11，
# `?since=2026-11-17 00:00:00` 回 0 行；加 page/pageSize/offset/path=hoarding 全无效（无分页）。
# 即：V16 起 POST /external/voices 走**囤积档**，而查询接口只读老 voices 表 —— 本轮提交
# 在引擎侧不可观测。旧实现在此判 "确认指令未产生落库" = 把**不可判**记成产品违规。
def test_s214_engine_view_gap_is_indeterminate_not_fail():
    fails, indet = _row_verdict(expect_rows=1, engine_rows=[], ledger_rows=[{"id": "VDPL1"}])
    assert not fails, f"查询覆盖不到不许记违规：{fails}"
    assert indet and "囤积" in indet, indet


def test_s214_no_ledger_no_engine_row_is_still_a_fail():
    fails, indet = _row_verdict(expect_rows=1, engine_rows=[], ledger_rows=[])
    assert fails and "未产生落库" in fails[0], fails
    assert not indet


def test_s214_engine_rows_present_keep_strict_judging():
    fails, indet = _row_verdict(expect_rows=1, engine_rows=[{"id": "VDPL1"}], ledger_rows=[])
    assert not fails and not indet
