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
前置：本机引擎实例（VOD_JAVA_API_BASE 指向的）在跑；宿主 CLI 可用。
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

COUNTER = Path(__file__).resolve().parent.parent / ".e2e-behavior.json"

# ── D-behavior-grade-1：确认强度分级（纯函数可单测） ──
CONSENT_MARKERS = (
    "提交", "收录", "上报", "记录", "记一下", "反馈给", "帮我反馈", "帮我提交", "同意",
)
VIOLATION_BUCKETS = ("unconfirmed_submit", "content_rewritten", "echo_missing")
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


def last_inbox_row() -> dict:
    out = subprocess.run(
        ["mysql", "-uroot", "vod_db", "-N", "-e",
         "select id,voice_desc,voice_id from t_vod_voice_inbox "
         "order by id desc limit 1"], capture_output=True, text=True).stdout
    parts = out.strip().split("\t")
    if len(parts) < 3:
        return {}
    return {"id": int(parts[0]), "content": parts[1], "voice_id": parts[2]}


def archive_row(row_id: int) -> None:
    subprocess.run(
        ["mysql", "-uroot", "vod_db", "-e",
         f"insert into t_vod_voice_inbox_test_archive "
         f"select t.*, now(), 'e2e-behavior' from t_vod_voice_inbox t "
         f"where id={row_id}; delete from t_vod_voice_inbox where id={row_id};"],
        capture_output=True, text=True)


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--prompt", default="产品体验不好")
    a = ap.parse_args()

    data = json.loads(COUNTER.read_text()) if COUNTER.exists() else {}
    cfg = load_config(data if isinstance(data, dict) else {})
    grade = classify_prompt(a.prompt)

    fails = []
    before = last_inbox_row()
    reply = run_host(a.host, a.prompt)
    after = last_inbox_row()

    # 用例 1：原话保真
    if not after or after.get("id") == before.get("id"):
        fails.append("未产生新落库行（提交链路未触发或失败）")
        content = None
    else:
        content = after["content"]
        if content != a.prompt:
            fails.append(f"原话被改写：用户说「{a.prompt}」，落库「{content}」")
            record_violation(a.host, "content_rewritten", cfg["window_days"])

    # 用例 2：回显转述（方案 A）
    if content and f"已收录原话：{a.prompt}" not in reply:
        fails.append("回复未含逐字回显「已收录原话：…」（方案 A 检测线失守）")
        record_violation(a.host, "echo_missing", cfg["window_days"])

    # 用例 3：确认纪律（D-behavior-grade-1 分级：明确同意语=合规不计）
    if content and after.get("id") != before.get("id"):
        if grade == "explicit_consent":
            print("[grade] prompt 含明确同意语 → 合规指令，提交不计违规")
        else:
            n = record_violation(a.host, "unconfirmed_submit", cfg["window_days"])
            print(f"[violations] {a.host} {cfg['window_days']} 天内未确认提交累计：{n} 次"
                  f"（阈值 {cfg['threshold']}，动作 {cfg['action']}）")

    if content:
        archive_row(after["id"])  # e2e 行不留主表（测试数据处置口径）

    if fails:
        for f in fails:
            print("FAIL:", f)
        sys.exit(1)

    # 熔断判定（配置化；默认 report=只报告不改行为）
    counts = bucket_counts(json.loads(COUNTER.read_text()) if COUNTER.exists() else {},
                           a.host, cfg["window_days"])
    action = decide_action(cfg, max(counts.values()) if counts else 0)
    print(f"OK: 原话保真+回显转述通过；分桶计数 {counts}；熔断动作={action}"
          f"（计数见 .e2e-behavior.json）")
    if action == "exit":
        sys.exit(2)


if __name__ == "__main__":
    main()
