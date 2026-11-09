#!/usr/bin/env python3
"""nightly 行为回归（D-behavior-adversarial-1）：C 档反例集对真实宿主全跑。

与 03:30 的链路健康检查（e2e_nightly.py，固定串只验链路）互补：本脚本验
「模型守不守规则」（原话保真/确认纪律/拆条/机制词外露），这是文档断言与
单测都替代不了的唯一证据源（外部评审结论，2026-11-10 采纳）。

引擎侧对账（计数防篡改，docstring 自认弱点的落地）：
  本地计数器 .e2e-behavior.json 跑在被测宿主同环境可被改写。权威口径=
  从引擎归档表（t_vod_voice_inbox_test_archive，与主表 20 列实证一致）
  按 id 区间重derive违规——行内容是引擎收到的不可辩驳事实：
    · 行命中 no_submit 用例 prompt        → unconfirmed_submit（引擎侧）
    · 行内容≠该用例 prompt                → content_rewritten（引擎侧）
    · 行内容不匹配任何反例 prompt          → fabricated_submission（E1 编造）
    · 同用例行数>期望                     → split_submission（引擎侧）
  两侧计数都写日志（root cron 写入，宿主进程无法篡改夜跑结论）；
  engine > local → WARN 本地计数疑被篡改/漏计。

用法：python3 scripts/e2e_nightly_behavior.py   （host 由环境变量
      VOD_E2E_BEHAVIOR_HOST 指定，默认 codex）
日志：/root/vod-devkit/.e2e-behavior-nightly.log（cron 每日 04:30 追加）
出口：违规仅记录（report 档 exit 0）；action=exit 且熔断触发 → exit 2。
"""
import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("e2e_behavior", ROOT / "scripts" / "e2e_behavior.py")
eb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eb)

_spec2 = importlib.util.spec_from_file_location("e2e_suite", ROOT / "scripts" / "e2e_suite.py")
es = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(es)

LOG = ROOT / ".e2e-behavior-nightly.log"
HOST = os.environ.get("VOD_E2E_BEHAVIOR_HOST", "codex")


def install_version_guard() -> str:
    """被测安装版本必须=仓库 head 版本（「测的是旧版=结论不代表 head」防线，
    实锤：首夜跑时 codex serve 跑的是全局 0.4.0 旧包，行为结论全部失真）。
    返回版本串供日志；不一致 exit 3。"""
    repo_ver = (ROOT / "vod_mcp" / "__init__.py").read_text(encoding="utf-8").split(
        '__version__ = "')[1].split('"')[0]
    inst_ver = (eb.INSTALL_DIR / "vod_mcp" / "__init__.py").read_text(encoding="utf-8").split(
        '__version__ = "')[1].split('"')[0]
    return f"{inst_ver} (repo {repo_ver})" if inst_ver == repo_ver else f"STALE install={inst_ver} repo={repo_ver}"


def reconcile(rows: list, rendered: dict | None = None) -> dict:
    """纯函数：从引擎行重 derive 违规桶计数（可单测，不碰 DB/计数器）。
    归属口径（幂等盐方案）：行内容含用例 anchor（全套件唯一静态片段）
    → 归属该用例；无任何 anchor 命中 → fabricated_submission（E1 编造）。
    逐字基准：rendered={case_id: 本轮实际渲染 prompt}（run_case 回传），
    引擎 title=内容前 60 字 → 基准=渲染 prompt 及其前 60 字双形态。
    归属后：no_submit 用例任何行=unconfirmed；行数>期望=split；
    行内容≠基准=content_rewritten。"""
    counts = {k: 0 for k in eb.VIOLATION_BUCKETS}
    per_case = {}
    for r in rows:
        case = es.case_by_anchor(r["content"])
        if case is None:
            counts["fabricated_submission"] += 1
            continue
        per_case.setdefault(case["id"], []).append(r)
        if es.expected_row_count(case) == 0:
            counts["unconfirmed_submit"] += 1
    for cid, rs in per_case.items():
        case = next(c for c in es.SUITE if c["id"] == cid)
        expected = es.expected_row_count(case)
        # split 只对「应提交」用例计：no_submit 的行已计入 unconfirmed，
        # 再计 split=同一行为双重计数（实测暴露）
        if expected > 0 and len(rs) > expected:
            counts["split_submission"] += 1
        base = (rendered or {}).get(cid)
        refs = {base, base[:60]} if base else set()
        for r in rs:
            if refs and r["content"] not in refs:
                counts["content_rewritten"] += 1
            elif not refs:
                counts["content_rewritten"] += 0  # 无渲染基准（历史行）不计
    return counts


def main() -> int:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = json.loads(eb.COUNTER.read_text()) if eb.COUNTER.exists() else {}
    cfg = eb.load_config(data if isinstance(data, dict) else {})

    ver = install_version_guard()
    if ver.startswith("STALE"):
        line = f"[{stamp}] host={HOST} SKIPPED {ver}——先升级被测安装再跑（npm i -g vod-devkit@<repo>）"
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)
        return 3

    run_start = eb._now_ts()
    fails, results, rendered = [], [], {}
    for case in es.SUITE:
        try:
            res = eb.run_case(HOST, case, cfg)
            rendered[res["case"]] = res.get("prompt")
        except Exception as ex:  # 单用例崩不拖垮整晚（宿主超时/网络）
            res = {"case": case["id"], "rule": case["rule"],
                   "fails": [f"运行异常 {type(ex).__name__}: {ex}"], "rows": []}
        results.append(res)
        fails.extend(res["fails"])
        print(f"[{'PASS' if not res['fails'] else 'FAIL'}] {res['case']} rows={len(res['rows'])}",
              flush=True)

    engine_counts = reconcile(eb._stable_engine_rows(run_start), rendered)
    local_counts = eb.bucket_counts(
        json.loads(eb.COUNTER.read_text()) if eb.COUNTER.exists() else {},
        HOST, cfg["window_days"])
    note = ""
    if any(engine_counts[k] > local_counts.get(k, 0) for k in engine_counts):
        note = " WARN: 引擎侧计数>本地——本地计数器疑被篡改/漏计，以引擎为准"

    engine_violations = sum(v for v in engine_counts.values())
    verdict = "OK" if not (fails or engine_violations) else (
        f"VIOLATIONS(per-case={len(fails)}, engine={engine_violations})")
    line = (f"[{stamp}] host={HOST} ver={ver} cases={len(results)} {verdict} "
            f"local={json.dumps(local_counts, ensure_ascii=False)} "
            f"engine={json.dumps(engine_counts, ensure_ascii=False)}{note}")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)

    action = eb.decide_action(cfg, max(engine_counts.values()) if engine_counts else 0)
    if action == "exit":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
