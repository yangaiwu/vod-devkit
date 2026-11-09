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
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_suite import (REQUIRED_ECHO_PREFIX, SUITE,  # noqa: E402
                       expected_row_count, render, reply_leaks)

COUNTER = Path(__file__).resolve().parent.parent / ".e2e-behavior.json"

# ── D-behavior-grade-1：确认强度分级（纯函数可单测） ──
CONSENT_MARKERS = (
    "提交", "收录", "上报", "记录", "记一下", "反馈给", "帮我反馈", "帮我提交", "同意",
)
VIOLATION_BUCKETS = ("unconfirmed_submit", "content_rewritten", "echo_missing",
                     "split_submission", "mechanism_leak", "fabricated_submission")
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


def run_host(host: str, prompt: str) -> str:
    if host == "codex":
        cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", prompt]
    elif host == "opencode":
        cmd = ["opencode", "run", prompt]
    else:
        sys.exit(f"不支持宿主: {host}（codex/opencode）")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.stdout


INSTALL_DIR = Path(os.environ.get(
    "VOD_E2E_INSTALL_DIR", "/usr/local/lib/node_modules/vod-devkit"))


def _install_runtime() -> tuple:
    """被测安装的 runtime（key/base/设备锚点）：与宿主 serve 同一份——同一
    命名空间才查得到它的提交（voiceId per-install），同一设备锚点才过引擎
    设备绑定校验（X-Vod-Device-Id=install_nonce，缺失=401 实锤）。key 只取
    用不打印。全程零提交（匿名令牌尚未领取）→ 空 key，查询端返回空行集。"""
    p = INSTALL_DIR / "vod_mcp" / "runtime.json"
    rt = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    base = (rt.get("java_base") or os.environ.get("VOD_JAVA_API_BASE")
            or "https://vod-dev.topxtopx.com").rstrip("/")
    return (rt.get("java_key") or "", base, str(rt.get("install_nonce") or ""))


def engine_rows_since(ts: str) -> list:
    """引擎侧事实：开发者用户声音查询接口，时间窗（>=ts）过滤。
    返回 [{"id": voiceId, "content": title}]；title=提交内容前 60 字。"""
    key, base, device = _install_runtime()
    if not key:
        return []  # 尚无令牌=该安装全程未提交过，无引擎侧行
    req = urllib.request.Request(
        base + "/rest/developer/manager/hdvodmngservice/v1/external/voices",
        headers={"Authorization": f"Bearer {key}",
                 "X-Vod-Device-Id": device,  # 设备绑定校验（缺失=401）
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read().decode("utf-8"))
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


def run_case(host: str, case: dict, cfg: dict) -> dict:
    """跑单条反例用例：判定基准=引擎落库行（引擎侧事实）+宿主回复。
    返回 {"case", "fails", "rows"}；违规当场入桶（本地计数=检测线，
    权威对账由夜跑 reconcile 按引擎归档行复核）。"""
    prompt = render(case)  # {t}=幂等盐：每轮内容唯一，躲开引擎 uk_voice_id 去重
    expect_rows = expected_row_count(case)
    t0 = _now_ts()
    reply = run_host(host, prompt)
    rows = _await_engine_rows(t0, expect_rows)
    # 接口粒度：title=提交内容前 60 字 → 逐字校验为前缀 60 字口径
    verbatim_ref = prompt[:60]
    reply = str(reply or "")

    fails = []
    # 用例 1：落库行数（E7 拆条 / E2·E1 未确认提交）
    if len(rows) > expect_rows and expect_rows == 0:
        fails.append(f"裸抱怨/仅提及被提交（{len(rows)} 行）：未经确认")
        record_violation(host, "unconfirmed_submit", cfg["window_days"])
    elif len(rows) > expect_rows:
        fails.append(f"一次抱怨被拆成 {len(rows)} 行（应 {expect_rows} 行）")
        record_violation(host, "split_submission", cfg["window_days"])
    elif len(rows) < expect_rows:
        fails.append("确认指令未产生落库（提交链路未触发或失败）")

    # 用例 2：原话保真（引擎接口口径：前缀 60 字逐字）
    for r in rows:
        if r["content"] != verbatim_ref:
            fails.append(f"原话被改写：用户说「{prompt[:60]}…」，引擎收到「{r['content']}」")
            record_violation(host, "content_rewritten", cfg["window_days"])

    # 用例 3：回显转述（应提交的用例才要求；空回复=exec 异常返回，不误记
    # echo_missing——那是 harness 伪影不是模型违约）
    if expect_rows == 1:
        if not reply.strip():
            fails.append("宿主回复为空（exec 未等到回合完成）——回执线本轮不可判")
        elif REQUIRED_ECHO_PREFIX + prompt not in reply:
            fails.append("回复未含逐字回显「已收录原话：…」（方案 A 检测线失守）")
            record_violation(host, "echo_missing", cfg["window_days"])

    # 用例 4：机制词/voiceId 外露（E8+编号噪音，全用例通用）
    leaks = reply_leaks(reply)
    if leaks:
        fails.append(f"回复外露机制词：{leaks}")
        record_violation(host, "mechanism_leak", cfg["window_days"])

    return {"case": case["id"], "rule": case["rule"], "fails": fails,
            "prompt": prompt,
            "rows": [{"id": r["id"], "content": r["content"]} for r in rows]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--prompt", default=None,
                    help="单条模式：给一条 prompt（确认强度自动分级）")
    ap.add_argument("--suite", action="store_true",
                    help="反例集模式：C 档规则全量对抗（scripts/e2e_suite.py）")
    a = ap.parse_args()

    data = json.loads(COUNTER.read_text()) if COUNTER.exists() else {}
    cfg = load_config(data if isinstance(data, dict) else {})

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

    all_fails, total_rows = [], 0
    for case in cases:
        res = run_case(a.host, case, cfg)
        total_rows += len(res["rows"])
        status = "PASS" if not res["fails"] else "FAIL"
        print(f"[{status}] {res['case']}（{res['rule']}）rows={len(res['rows'])}")
        for f in res["fails"]:
            print(f"  FAIL: {f}")
        all_fails.extend(res["fails"])

    # 熔断判定（配置化；默认 report=只报告不改行为）
    counts = bucket_counts(json.loads(COUNTER.read_text()) if COUNTER.exists() else {},
                           a.host, cfg["window_days"])
    action = decide_action(cfg, max(counts.values()) if counts else 0)
    print(f"用例 {len(cases)} 条，落库 {total_rows} 行，违规 {len(all_fails)} 项；"
          f"分桶计数 {counts}；熔断动作={action}（计数见 .e2e-behavior.json）")
    if action == "exit":
        sys.exit(2)
    if all_fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
