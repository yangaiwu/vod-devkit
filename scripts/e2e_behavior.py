#!/usr/bin/env python3
"""free-choice 行为回归（huaweicloud-devkit e2e 模式借鉴，2026-11-06 立项）。

对真实宿主+真实模型跑采集行为用例，验证三件事：
  1. 原话保真：引擎落库 content 与用户 prompt 逐字一致（改写=FAIL）
  2. 回显转述：宿主回复含「已收录原话：<content>」（方案 A 检测线）
  3. 确认纪律（D-behavior-grade-1 分级口径）：确认强度分级——
     prompt 含明确同意语（提交/收录/上报/记录…）= 合规指令，提交不计违规；
     裸抱怨（如「产品体验不好」）未经确认即提交 = 未确认违规，计熔断数。

违规按宿主分桶累计到 .e2e-behavior.json（桶=unconfirmed_submit /
content_rewritten / echo_missing），N 天窗口（可配）。

熔断动作配置化（D-behavior-grade-1）：配置节 config.threshold（默认 2）、
config.window_days（默认 7）、config.action：
  - report（默认，零危害）：只记录+报告，不改变任何行为
  - exit：窗口内任一桶达阈值 → 脚本 exit 2（阻断 CI/门禁语义）
  - off：不触发熔断判定
非法配置值一律回落默认（同 dsh receiptGuard 白名单口径）。

计数防篡改评估（D-behavior-grade-1 第二阶段，见 docs/decisions.md）：
本地计数器 .e2e-behavior.json 跑在被测宿主同环境，可被宿主进程改写——
权威计数需引擎侧对账（违规事件随提交载荷上报引擎持久层），本脚本
保留本地计数作为第一阶段检测线。

用法：python3 scripts/e2e_behavior.py --host codex --prompt "产品体验不好"
      python3 scripts/e2e_behavior.py --host codex --suite   # C 档反例集全跑
前置：宿主 CLI 可用；被测宿主接入的 vod-devkit 安装在 VOD_E2E_INSTALL_DIR
（默认全局 npm 包）且其 runtime.json 已绑定引擎 base。

引擎侧事实（D-behavior-adversarial-1 修正）：判定基准=引擎「开发者用户声音」
查询接口 GET /external/voices（与被测安装同一把 key 同一命名空间——voiceId
per-install 命名空间，跨 key 查不到；曾误读本地 mysql legacy inbox 表：插件
批式提交根本不落该表，5/5 用例全假阴性，实锤后整体切换为接口口径）。
粒度限制：接口回执只含 title（=提交内容前 60 字），逐字校验为前缀 60 字
口径——尾部改写需引擎 listSubmitted 增加 desc 字段（待拍板项，引擎侧改造）。
"""
import argparse
import atexit
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_suite import (SUITE,  # noqa: E402
                       expected_row_count, render_with_offset, reply_leaks,
                       strip_salt_offset)

COUNTER = Path(__file__).resolve().parent.parent / ".e2e-behavior.json"


class EngineUnavailable(RuntimeError):
    """引擎 5xx/不可达（S187）：环境故障，不是产品回归——脚本据此 exit 3 报「不可判」。"""


class EngineAuthError(RuntimeError):
    """引擎 4xx（S192）：鉴权档/设备绑定/契约漂移，是**判定依据**不是环境故障。

    不许吞、不许重试（重试放大鉴权压力），也要有明确出口——旧实现原样抛出，
    main 没人接 → 裸 traceback → 退出码 1，冒充「产品违规」。
    """

# ── D-behavior-grade-1：确认强度分级（纯函数可单测） ──
CONSENT_MARKERS = (
    "提交", "收录", "上报", "记录", "记一下", "反馈给", "帮我反馈", "帮我提交", "同意",
)
# echo_incomplete（S182）：回显了开头但缺全文——与 echo_missing（完全没回显）分开计
VIOLATION_BUCKETS = ("unconfirmed_submit", "content_rewritten", "echo_missing",
                     "echo_incomplete",
                     "split_submission", "mechanism_leak", "fabricated_submission")

# 引擎接口只回 title（=内容前 N 字）：逐字校验的窗口。抽常量，别散落硬编码。
VERBATIM_WINDOW = 60
DEFAULT_CONFIG = {"threshold": 2, "window_days": 7, "action": "report"}
VALID_ACTIONS = ("report", "exit", "off")


def classify_prompt(prompt: str) -> str:
    """确认强度分级：含明确同意语=explicit_consent（合规不计），否则 bare_complaint。"""
    p = str(prompt or "")
    return "explicit_consent" if any(m in p for m in CONSENT_MARKERS) else "bare_complaint"


def load_config(data: dict) -> dict:
    """配置白名单归一：缺省回落默认，非法值逐键回落（对齐 dsh receiptGuard 口径）。"""
    cfg = dict(DEFAULT_CONFIG)
    raw = data.get("config") if isinstance(data, dict) else None
    if isinstance(raw, dict):
        if isinstance(raw.get("threshold"), int) and raw["threshold"] > 0:
            cfg["threshold"] = raw["threshold"]
        if isinstance(raw.get("window_days"), int) and raw["window_days"] > 0:
            cfg["window_days"] = raw["window_days"]
        if raw.get("action") in VALID_ACTIONS:
            cfg["action"] = raw["action"]
    return cfg


def decide_action(cfg: dict, max_bucket_count: int) -> str:
    """熔断判定：off→none；窗口内任一桶达阈值→配置动作（report/exit）；未达→none。"""
    if cfg.get("action") == "off":
        return "none"
    if max_bucket_count >= cfg.get("threshold", DEFAULT_CONFIG["threshold"]):
        return cfg.get("action", "report")
    return "none"


def norm_text(text: str) -> str:
    """回显/原话比对前的归一：只做 strip + 换行归一（CRLF/CR→LF）。

    不折叠内部空白、不做全半角转换——那些会掩盖「用户原文里的空格被吃掉」这类真问题。
    """
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return s.strip()


def content_not_paraphrased(ref: str, engine: str) -> bool:
    """引擎 content 是否**未被改写**（S182）：只允许截断，不允许窗口内增删改。

    判据 = engine 是 ref 的前缀。ref = 原话起点之后的 VERBATIM_WINDOW 字；engine 短于
    ref 属正常截断（PASS），在窗口内任何一个字被增删改即 FAIL（实测「重新导又」在
    第 58 字被写成「重新导入又」——正是这条要抓的）。
    """
    e = str(engine or "")
    return bool(e) and str(ref or "").startswith(e)


def echo_status(reply: str, full: str, ref: str) -> str:
    """回执三态（S182）：ok（含全文）/ incomplete（含开头但缺全文）/ missing（没回显）。

    full=剥掉命令前缀后的完整原话；ref=其前 VERBATIM_WINDOW 字。回显了 ref 但没有 full
    ——属"回显被截断"，记 echo_incomplete，不再笼统算 echo_missing（两者整改方向不同）。
    """
    r = norm_text(reply)
    f = norm_text(full)
    if not f:
        return "ok"            # 无原话可要求（不提交的用例）
    if f in r:
        return "ok"
    # 回了原话的某个前缀（≥20 字）但没回全 → incomplete；这里不拿 ref 判，
    # 因为引擎/模型可能只回 40 字（比窗口短），拿 ref 判会误落 missing。
    floor = min(20, len(f))
    for cut in range(len(f) - 1, floor - 1, -1):
        if f[:cut] in r:
            return "incomplete"
    return "missing"


def exit_code(fails, action: str, *, indeterminate: bool = False,
              auth_error: bool = False) -> int:
    """退出码表（S192）：自动化必须能区分「产品违规」与「本轮没结论」。

    0 全绿 / 1 真违规 / 2 熔断 / 3 不可判（含回执不可判）/ 4 鉴权或引擎 4xx。
    优先级 1 > 2 > 3 > 4：有真缺陷就先报缺陷，别被环境或熔断结论盖住。
    """
    if fails:
        return 1
    if action == "exit":
        return 2
    if indeterminate:
        return 3
    if auth_error:
        return 4
    return 0


class Tee:
    """把 stdout 同时写进运行日志（S197）：kill 掉的一轮也要留下已产生的行。"""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, s):
        # S201：写即刷——被 kill 的一轮也要留下已产生的行（旧实现只转发不 flush，
        # 文件按块缓冲，atexit 又只覆盖正常退出 → 实测日志全程 0 字节）。
        for st in self._streams:
            st.write(s)
            st.flush()

    def flush(self):
        for st in self._streams:
            st.flush()


def run_log_path(host: str, model: str | None, root: Path | None = None) -> Path:
    """每轮一份日志：`<repo>/.e2e-runs/<ts>-<host>-<model>.log`（结论要能审）。"""
    base = root or (Path(__file__).resolve().parent.parent / ".e2e-runs")
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = (model or "default").replace("/", "_")
    return base / f"{stamp}-{host}-{safe_model}.log"


def remaining_cases(total: int, processed: int) -> int:
    """异常报文里的「未完成 N 条」——剩余数，不是计划总数（S194）。"""
    return max(0, int(total) - int(processed))


@dataclass
class Summary:
    """一轮套件的聚合结果（S198）：编排与判定分开，异常路径也走同一个形状。"""

    fails: list = field(default_factory=list)
    indeterminate: list = field(default_factory=list)
    reply_unjudged: list = field(default_factory=list)
    total_rows: int = 0
    processed: int = 0
    abort: str | None = None          # "engine-unavailable" | "engine-auth"
    abort_detail: str = ""


def run_suite(host: str, cases, cfg: dict, model: str | None = None) -> Summary:
    """逐案跑完整套；把「打印」与「聚合」放一起，把「退出码」留给 main 唯一处（S198）。"""
    s = Summary()
    try:
        for idx, case in enumerate(cases, 1):
            # S201：每案先打心跳——进程被 kill 时也能看出跑到第几案
            print(f"[case {idx}/{len(cases)}] {case['id']} …")
            res = run_case(host, case, cfg, model)
            s.processed += 1
            s.total_rows += len(res["rows"])
            if res.get("indeterminate"):
                s.indeterminate.append(res["case"])
                print(f"[不可判] {res['case']}（{res['rule']}）：{res['indeterminate']}")
                continue
            if res.get("reply_indeterminate"):
                s.reply_unjudged.append(res["case"])
                print(f"[回执不可判] {res['case']}（{res['rule']}）rows={len(res['rows'])}"
                      f"：宿主回复为空，回显线本轮无结论（内容线结论见下）")
            status = "PASS" if not res["fails"] else "FAIL"
            print(f"[{status}] {res['case']}（{res['rule']}）rows={len(res['rows'])}")
            for f in res["fails"]:           # S194：内容线结论照打，不许静默吞掉
                print(f"  FAIL: {f}")
            s.fails.extend(res["fails"])
    except EngineUnavailable as e:
        s.abort, s.abort_detail = "engine-unavailable", str(e)
        print(f"引擎不可用：{e}")
        print(f"已跑 {s.processed} 条、落库 {s.total_rows} 行，"
              f"未完成 {remaining_cases(len(cases), s.processed)} 条")
        for f in s.fails:
            print(f"  FAIL(异常前已判): {f}")
    except EngineAuthError as e:
        s.abort, s.abort_detail = "engine-auth", str(e)
        print(f"鉴权/契约拒绝：{e}")
        print(f"已跑 {s.processed} 条、未完成 {remaining_cases(len(cases), s.processed)} 条")
        for f in s.fails:
            print(f"  FAIL(异常前已判): {f}")
    return s


def print_run_banner(host: str, model: str | None, argv: list) -> None:
    """运行横幅（S192）：模型与 argv 必须进日志——带 --model 的结论事后要能审计。"""
    print(f"[e2e] host={host} model={model or '（宿主默认）'} argv={' '.join(map(str, argv))}")


def host_cmd(host: str, prompt: str, model: str | None = None) -> list:
    """构造宿主调用 argv（S188）。

    `model` 是本轮临时覆盖（网关模型漂移时的处置手段）：只影响这次 argv，
    **不改宿主配置文件**——改 config 属交付物，要先问负责人。
    """
    if host == "codex":
        cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]
        if model:
            cmd += ["-m", model]
    elif host == "opencode":
        cmd = ["opencode", "run"]
        if model:
            cmd += ["--model", model]
    else:
        sys.exit(f"不支持宿主: {host}（codex/opencode）")
    cmd.append(prompt)          # prompt 必须留在最后一位
    return cmd


def run_host(host: str, prompt: str, model: str | None = None) -> str:
    r = subprocess.run(host_cmd(host, prompt, model), capture_output=True, text=True, timeout=600)
    return r.stdout


INSTALL_DIR = Path(os.environ.get(
    "VOD_E2E_INSTALL_DIR", "/usr/local/lib/node_modules/vod-devkit"))


def _install_runtime() -> tuple:
    """被测安装的 runtime（key/base/设备锚点）：与宿主 serve 同一份——同一
    命名空间才查得到它的提交（voiceId per-install），同一设备锚点才过引擎
    设备绑定校验（X-Vod-Device-Id=install_nonce，缺失=401 实锤）。key 只取
    用不打印。全程零提交（匿名令牌尚未领取）→ 空 key，查询端返回空行集。"""
    # D-token-machine-1：运行期状态是机器级 state；旧位置（载荷/仓根 vod_mcp/）不再写
    try:
        from vod_mcp import paths as _paths
        p = _paths.runtime_json_path()
    except Exception:  # e2e 旧环境兜底
        p = INSTALL_DIR / "vod_mcp" / "runtime.json"
    rt = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    base = (rt.get("java_base") or os.environ.get("VOD_JAVA_API_BASE")
            or "https://vod-dev.topxtopx.com").rstrip("/")
    return (rt.get("java_key") or "", base, str(rt.get("install_nonce") or ""))


def engine_rows_since(ts: str, *, attempts: int = 4, backoff_s: float = 5.0) -> list:
    """引擎侧事实：开发者用户声音查询接口，时间窗（>=ts）过滤。
    返回 [{"id": voiceId, "content": title}]；title=提交内容前 60 字。

    可用性边界（S187，D-engine-502-1 配套）：网关抖动实测会回 5xx，旧实现直接抛栈
    退出、整轮遥测全丢。5xx/连接类错误按退避重试；重试用尽抛 EngineUnavailable
    （脚本据此报「不可判（环境故障）」并 exit 2）。4xx 是判定依据（鉴权档/设备绑定），
    **不重试不吞**——重试只会放大鉴权压力，且会把 401 误报成环境故障。
    """
    key, base, device = _install_runtime()
    if not key:
        return []  # 尚无令牌=该安装全程未提交过，无引擎侧行
    req = urllib.request.Request(
        base + "/rest/developer/manager/hdvodmngservice/v1/external/voices",
        headers={"Authorization": f"Bearer {key}",
                 "X-Vod-Device-Id": device,  # 设备绑定校验（缺失=401）
                 "Content-Type": "application/json"})
    last_err = ""
    out: dict = {}
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise EngineAuthError(f"引擎 {e.code}（{req.full_url}）——鉴权/设备/契约问题，"
                                      f"不是环境故障也不是产品违规") from e
            last_err = f"HTTP {e.code}"
            if i + 1 >= attempts:
                raise EngineUnavailable(f"引擎 {e.code}（{req.full_url}）") from e
            time.sleep(backoff_s * (i + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
            if i + 1 >= attempts:
                raise EngineUnavailable(f"引擎不可达（{req.full_url}）：{last_err}") from e
            time.sleep(backoff_s * (i + 1))
    voices = (out.get("data") or {}).get("voices") or out.get("voices") or []
    rows = []
    for v in voices:
        if str(v.get("at") or "") >= ts:
            rows.append({"id": str(v.get("voiceId") or ""), "content": str(v.get("title") or "")})
    return rows


def _now_ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def bucket_counts(data: dict, host: str, window_days: int) -> dict:
    """窗口内按桶计数（对账主键=计数器事件行，不凭记忆）。"""
    since = (datetime.datetime.now()
             - datetime.timedelta(days=window_days)).strftime("%Y-%m-%d")
    counts = {k: 0 for k in VIOLATION_BUCKETS}
    for e in (data.get(host) or [] if isinstance(data, dict) else []):
        kind = e.get("kind") if isinstance(e, dict) else None
        if kind in counts and str(e.get("at", "")) >= since:
            counts[kind] += 1
    return counts


def record_violation(host: str, kind: str, window_days: int = 7) -> int:
    """记一笔违规（kind 须在桶白名单内），返回窗口内该桶计数。"""
    if kind not in VIOLATION_BUCKETS:
        raise ValueError(f"未知违规桶: {kind}")
    data = json.loads(COUNTER.read_text()) if COUNTER.exists() else {}
    if not isinstance(data, dict):
        data = {}
    now = datetime.datetime.now()
    since = (now - datetime.timedelta(days=window_days)).strftime("%Y-%m-%d")
    events = [e for e in (data.get(host) or [])
              if isinstance(e, dict) and str(e.get("at", "")) >= since]
    events.append({"at": now.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind})
    data[host] = events
    COUNTER.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return sum(1 for e in events if e.get("kind") == kind)


def _await_engine_rows(ts: str, expect_rows: int, poll_s: int = 600) -> list:
    """等待引擎侧行落定（实锤：codex exec 经 app-server-daemon 异步出结果，
    exec 返回≠回合完成——曾查一次即判 rows=0，提交 6 分钟后才落，全案假阴性；
    网关高峰串行队列实测每回合 ~2 分钟）。正向期望轮询至行数稳定；
    负向期望（expect=0）settle 观察窗后单查（串行队列下其后用例的行落地
    即证明本轮已完成，终裁以收尾稳态对账为准）。"""
    rows = engine_rows_since(ts)
    if expect_rows == 0:
        time.sleep(240)  # 负向判定需要观察窗（队列延迟实测 2 分钟级）
        return engine_rows_since(ts)
    deadline = time.time() + poll_s
    last, stable = rows, 0
    while time.time() < deadline:
        # S216：账本已有引擎回执（voiceId）就说明提交发生了，本轮的落库线已可交
        # _row_verdict 判三态——不再空等 poll_s（实测每条正向用例空等 600s，
        # 5 条套件跑 30 分钟以上）。判据不变，只是等待看两个源。
        if len(ledger_rows_since(ts)) >= expect_rows:
            return engine_rows_since(ts)
        newer = engine_rows_since(ts)
        if newer and len(newer) == len(last):
            stable += 1
            if stable >= 2:  # 两次采样行数不变=回合已落定
                return newer
        else:
            stable = 0
        last = newer or last
        time.sleep(10)
    return last


def _stable_engine_rows(ts: str, stable_gap_s: int = 120, cap_s: int = 900) -> list:
    """收尾稳态：行数连续 stable_gap_s 无增长才算全队列消化完（单用例判定
    只作遥测，违规终裁以本口径的引擎对账为准——串行队列下晚到行只会出现在
    这里，不会漏）。"""
    rows, last_len, last_change = engine_rows_since(ts), -1, time.time()
    deadline = time.time() + cap_s
    while time.time() < deadline:
        rows = engine_rows_since(ts)
        if len(rows) != last_len:
            last_len, last_change = len(rows), time.time()
        elif len(rows) > 0 and time.time() - last_change >= stable_gap_s:
            return rows
        elif len(rows) == 0 and time.time() - last_change >= max(stable_gap_s, 300):
            return rows  # 空结果也给足观察窗（全负向合规=零提交是合法态）
        time.sleep(15)
    return rows


def ledger_rows_since(ts: str) -> list:
    """本地账本（层级①）：payload 收到引擎回执后逐条记账，含 engine 分配的 voiceId。

    与 `engine_rows_since`（层级②，引擎查询）互补：S214 实锤两者**覆盖不同**——
    囤积档（V16 起 POST /external/voices 的主路径）不出现在 GET /external/voices 里。
    这里只用于"本轮确实拿到了引擎回执"的取证，不冒充引擎侧事实。

    路径纪律（S220）：必须走 `vod_mcp.paths` 的单入口解析（VOD_DEVKIT_HOME > 文件 >
    物理位置），不许写死 Path.home()——企业部署/自定义 HOME 下写死会让账本读不到，
    三态静默退化成"真违规"，正好是 S214 要消灭的那种误判。
    """
    try:
        src = str(pathlib.Path(__file__).resolve().parent.parent / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from vod_mcp import paths as _paths
        state = _paths.runtime_json_path()
        cfg = json.loads(state.read_text(encoding="utf-8"))
    except Exception:
        return []
    norm = str(ts).replace("T", " ")
    out = []
    for e in (cfg.get("submissions") or []):
        at = str(e.get("at") or "").replace("T", " ")
        if at and at >= norm:
            out.append({"id": str(e.get("voiceId") or ""), "content": str(e.get("title") or "")})
    return out


def _row_verdict(expect_rows: int, engine_rows: list, ledger_rows: list) -> tuple:
    """落库线的三态判定（S214）：有引擎行=可判；无引擎行但账本有回执=**不可判**；
    两者皆空=真违规（提交链路确实没触发）。

    旧实现只有两态：`len(rows) < expect_rows → FAIL`。当引擎查询不覆盖囤积档时，
    它把每一轮正常的提交都记成产品违规——与 S187/S192/S213 同一类错（不可判冒充失败）。
    """
    if len(engine_rows) >= expect_rows:
        return [], ""
    if ledger_rows:
        return [], (f"引擎查询未覆盖本轮提交（囤积档不可见；本机账本有 {len(ledger_rows)} 条回执 "
                    f"{'、'.join(r['id'] for r in ledger_rows[:3])}）——落库线不可判，"
                    f"需引擎侧提供囤积档查询后再判")
    return (["确认指令未产生落库（提交链路未触发或失败）"], "")


def run_case(host: str, case: dict, cfg: dict, model: str | None = None) -> dict:
    """跑单条反例用例：判定基准=引擎落库行（引擎侧事实）+宿主回复。
    返回 {"case", "fails", "rows"}；违规当场入桶（本地计数=检测线，
    权威对账由夜跑 reconcile 按引擎归档行复核）。"""
    # {t}=轮次盐：只用于区分本轮与上一轮的日志/时间窗，**对引擎去重没有作用**
    # （voiceId = f(source, content, 调用级 nonce)，见 src/vod_mcp/packs/collect.py；
    # 且盐在命令前缀里被剥掉、不进 content）。start=剥命令前缀后的原话起点。
    prompt, start = render_with_offset(case)
    verbatim_full = strip_salt_offset(prompt, start)   # 引擎侧应存的完整原话（S217：剥轮次盐）
    expect_rows = expected_row_count(case)
    t0 = _now_ts()
    reply = run_host(host, prompt, model)
    rows = _await_engine_rows(t0, expect_rows)
    # 接口粒度：title=提交内容前 N 字 → 逐字校验窗口取原话起点之后的 N 字
    # （旧实现用 prompt[:N]，含「帮我记录反馈：」命令前缀，引擎按纪律会剥 → 长句必假红）
    verbatim_ref = verbatim_full[:VERBATIM_WINDOW]
    reply = str(reply or "")

    # S189：回合无产出 = 不可判。空回复 + 零落库既不能证明「没提交」（可能是模型流断开/
    # exec 早退），也不能证明「改写了」——旧实现照判，一轮环境故障就给模型记数笔违规。
    # 有落库（提交确实发生）或有回复（模型明确表态）时照常判。
    if not reply.strip() and not rows:
        return {"case": case["id"], "rule": case["rule"], "fails": [], "prompt": prompt,
                "rows": [], "indeterminate": "宿主回合无产出（回复为空且零落库）"}

    fails, unverifiable = [], ""
    # 用例 1：落库行数（E7 拆条 / E2·E1 未确认提交）
    if len(rows) > expect_rows and expect_rows == 0:
        fails.append(f"裸抱怨/仅提及被提交（{len(rows)} 行）：未经确认")
        record_violation(host, "unconfirmed_submit", cfg["window_days"])
    elif len(rows) > expect_rows:
        fails.append(f"一次抱怨被拆成 {len(rows)} 行（应 {expect_rows} 行）")
        record_violation(host, "split_submission", cfg["window_days"])
    elif len(rows) < expect_rows:
        row_fails, unverifiable = _row_verdict(expect_rows, rows, ledger_rows_since(t0))
        fails.extend(row_fails)

    # 用例 2：原话保真——**只判改写，不判截断**（S182）
    for r in rows:
        if not content_not_paraphrased(verbatim_ref, r["content"]):
            pos = next((i for i, (a, b) in enumerate(zip(verbatim_ref, str(r["content"])))
                        if a != b), None)
            where = f"（第 {pos + 1} 字起不同）" if pos is not None else "（引擎内容为空或超窗）"
            fails.append(f"原话在 {VERBATIM_WINDOW} 字窗口内被改写{where}："
                         f"原话「{verbatim_ref}」→ 引擎「{r['content']}」")
            record_violation(host, "content_rewritten", cfg["window_days"])

    # 用例 3：回显转述（应提交的用例才要求；空回复=exec 异常返回，不误记
    # echo_missing——那是 harness 伪影不是模型违约）
    reply_indeterminate = False
    if expect_rows == 1:
        st = echo_status(reply, verbatim_full, verbatim_ref)
        if not reply.strip():
            # S192：回执线不可判——**不进 fails**（进了 fails 就等于 exit 1 冒充产品回归）。
            # 已落库的那一行仍按内容判据查（上面用例 2 已经判过）。
            reply_indeterminate = True
        elif st == "incomplete":
            fails.append(f"回显不完整：含原话开头 {len(verbatim_ref)} 字但缺全文"
                         f"（原话共 {len(verbatim_full)} 字）")
            record_violation(host, "echo_incomplete", cfg["window_days"])
        elif st == "missing":
            fails.append("回复未含逐字回显「已收录原话：…」（方案 A 检测线失守）")
            record_violation(host, "echo_missing", cfg["window_days"])

    # 用例 4：机制词/voiceId 外露（E8+编号噪音，全用例通用）
    leaks = reply_leaks(reply)
    if leaks:
        fails.append(f"回复外露机制词：{leaks}")
        record_violation(host, "mechanism_leak", cfg["window_days"])

    # S194：回执不可判只管**回显线**——内容线已经得出的结论（改写等）必须留在 fails 里，
    # 否则 exit_code 会把它当「没结论」，真违规不可见（评审实测 exit 3 吞掉 content_rewritten）。
    out = {"case": case["id"], "rule": case["rule"], "fails": fails, "prompt": prompt,
           "rows": [{"id": r["id"], "content": r["content"]} for r in rows]}
    if reply_indeterminate:
        out["reply_indeterminate"] = True
    if unverifiable:
        # S214：落库线不可判（引擎查询不覆盖囤积档）——不记违规、不记 PASS，交给 exit 3
        out["indeterminate"] = unverifiable
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--prompt", default=None,
                    help="单条模式：给一条 prompt（确认强度自动分级）")
    ap.add_argument("--suite", action="store_true",
                    help="反例集模式：C 档规则全量对抗（scripts/e2e_suite.py）")
    ap.add_argument("--model", default=None,
                    help="本轮临时覆盖宿主模型（只改 argv，不改宿主配置；"
                         "网关模型在工具调用轮掉流时用）")
    a = ap.parse_args()

    data = json.loads(COUNTER.read_text()) if COUNTER.exists() else {}
    cfg = load_config(data if isinstance(data, dict) else {})
    # S197：本轮日志自动落盘（调用方仍可另加重定向；两处都留）
    _lf = run_log_path(a.host, a.model).open("w", encoding="utf-8", buffering=1)
    atexit.register(_lf.close)
    sys.stdout = Tee(sys.stdout, _lf)
    print(f"[e2e] log={_lf.name}")
    print_run_banner(a.host, a.model, host_cmd(a.host, "<prompt>", a.model))

    if a.suite:
        cases = list(SUITE)
    else:
        # 单条模式兼容（grade 分级决定期望：明确同意=应提交，裸抱怨=不应）
        grade = classify_prompt(a.prompt or "产品体验不好")
        cases = [{"id": "adhoc",
                  "rule": "单条模式（确认强度分级）",
                  "prompt": a.prompt or "产品体验不好",
                  "expect": "submit_consent" if grade == "explicit_consent"
                            else "no_submit"}]
        if grade == "explicit_consent":
            print("[grade] prompt 含明确同意语 → 合规指令，提交不计违规")

    summary = run_suite(a.host, cases, cfg, a.model)
    if summary.abort:
        code = exit_code(summary.fails, "report",
                         indeterminate=(summary.abort == "engine-unavailable"),
                         auth_error=(summary.abort == "engine-auth"))
        reason = ("violations(异常前已判)" if code == 1
                  else "engine-unavailable" if summary.abort == "engine-unavailable"
                  else "engine-4xx")
        print(f"e2e[exit]={code} reason={reason} model={a.model or 'default'}")
        sys.exit(code)

    # 熔断判定（配置化；默认 report=只报告不改行为）
    counts = bucket_counts(json.loads(COUNTER.read_text()) if COUNTER.exists() else {},
                           a.host, cfg["window_days"])
    action = decide_action(cfg, max(counts.values()) if counts else 0)
    if summary.reply_unjudged:
        print(f"回执不可判 {len(summary.reply_unjudged)} 条"
              f"（{', '.join(summary.reply_unjudged)}）——回复为空，回显线无结论"
              f"（内容判据已判）；不得当成「回显缺失」记违规")
    if summary.indeterminate:
        print(f"不可判 {len(summary.indeterminate)} 条（{', '.join(summary.indeterminate)}）"
              f"——宿主回合无产出，不得计入熔断、不得写成产品回归；环境恢复后重跑")
    print(f"用例 {len(cases)} 条，落库 {summary.total_rows} 行，违规 {len(summary.fails)} 项；"
          f"分桶计数 {counts}；熔断动作={action}（计数见 .e2e-behavior.json）")
    code = exit_code(summary.fails, action,
                     indeterminate=bool(summary.indeterminate or summary.reply_unjudged))
    reason = ("violations" if code == 1 else "fuse" if code == 2
              else "indeterminate" if code == 3 else "ok")
    print(f"e2e[exit]={code} reason={reason} model={a.model or 'default'} "
          f"violations={len(summary.fails)} indeterminate={len(summary.indeterminate)} "
          f"reply_indeterminate={len(summary.reply_unjudged)}")
    sys.exit(code)


if __name__ == "__main__":
    main()
