#!/usr/bin/env python3
"""按宿主**自己的配置**起 server，调只读工具做功能级验证（S234）。

为什么有它：巡检（`host_matrix --audit`）只拉一次 `vod_devkit_info`，证明"入口能起、
版本对"；"能不能真检索/真取技能面"没法验。此前每次要验就手写一次性探针，三次踩到同一个
坑——三个宿主的环境变量键叫 `environment` 而不是 `env`，裸探针只读 `env` → VOD_PACKS 没传
→ 服务端退回全 pack → 把 10 工具报成 12。这里把口径收成一份：

- 入口解析与巡检同源（`host_matrix.resolve_entry`，两处必须给出同一个 launch）；
- 环境变量两种键都读（`entry_env`）：`env` ∪ `environment`；
- 只调只读工具，不提交、不落库：默认 `vod_devkit_info` + `vod_auth_status`；
- 失败必须带 argv 尾巴，别只报"无响应"。

用法：
  python3 scripts/probe_tools.py                      # 全部已装宿主
  python3 scripts/probe_tools.py --host hermes --host dsh
  python3 scripts/probe_tools.py --expect-version 0.5.39 --call vod_search_products
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import host_matrix as hm  # noqa: E402

HOSTS = ["hermes", "opencode", "codeartsdoer", "codeartswork", "workbuddy",
         "atomcode", "codex-desktop", "codex", "openclaw", "dsh"]
DEFAULT_CALLS = [("vod_devkit_info", {}), ("vod_auth_status", {})]


def entry_env(entry: dict) -> dict:
    """宿主的启动环境：`env` ∪ `environment`（两种键都合法，见 S234 的踩坑记录）。"""
    out = {}
    for key in ("env", "environment"):
        raw = entry.get(key) or {}
        if isinstance(raw, dict):
            out.update({str(k): str(v) for k, v in raw.items()})
    return out


def _spawn_env(entry: dict) -> dict:
    env = os.environ.copy()
    extra = entry_env(entry)
    # 与 host_matrix._probe 同纪律：被装的那份载荷必须自证，不继承本进程为跑 CLI 钉的根
    for k in ("VOD_DEVKIT_SRC_ROOT", "VOD_DEVKIT_DIST_ROOT", "VOD_DEVKIT_ROOT"):
        if k not in extra:
            env.pop(k, None)
    env.update(extra)
    return env


def probe_entry(entry: dict, calls=None, timeout: float = 90.0) -> dict:
    """起一次 server，initialize → tools/list → 逐个只读工具调用。"""
    cmd, args = entry.get("command"), list(entry.get("args") or [])
    if isinstance(cmd, list):
        cmd, args = cmd[0], cmd[1:]
    if not cmd:
        raise RuntimeError("配置里没有启动命令")
    argv = [str(cmd), *[str(a) for a in args]]
    gone = [a for a in argv[1:] if a.endswith(".py") and not os.path.exists(a)]
    if gone:
        raise RuntimeError(f"入口文件不存在：{gone[0]}")
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=_spawn_env(entry), text=True)
    n = [0]

    def rpc(method, params=None):
        n[0] += 1
        msg = {"jsonrpc": "2.0", "id": n[0], "method": method}
        if params is not None:
            msg["params"] = params
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            err = (proc.stderr.read() if proc.stderr else "")[-200:]
            raise RuntimeError(f"server 无响应（argv={' '.join(argv[:2])}…）{err}")
        return json.loads(line)

    def call(name, arguments):
        r = rpc("tools/call", {"name": name, "arguments": arguments})
        res = r.get("result") or {}
        if res.get("content"):
            return json.loads(res["content"][0]["text"])
        return res.get("structuredContent") or {}

    try:
        rpc("initialize", {"protocolVersion": "2025-06-18",
                           "clientInfo": {"name": "probe-tools", "version": "1"},
                           "capabilities": {}})
        assert proc.stdin
        proc.stdin.write(json.dumps({"jsonrpc": "2.0",
                                     "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        tools = [t.get("name") for t in
                 (rpc("tools/list", {}).get("result") or {}).get("tools") or []]
        out = {"tools": len(tools), "names": sorted(tools)}
        for name, args_ in (calls or DEFAULT_CALLS):
            out[name] = call(name, args_)
        return out
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def check(host: str, result: dict, expect_version: str) -> tuple:
    info = result.get("vod_devkit_info") or {}
    ver = str(info.get("version") or "")
    sha = str(info.get("commitSha") or "")[:7]
    toolset = result.get("vod_search_products")
    extra = ""
    if toolset is not None:
        extra = f"｜检索候选 {len(toolset.get('candidates') or [])}"
    if not ver:
        return "FAIL", f"未拿到 vod_devkit_info（工具 {result['tools']} 个）"
    if expect_version and ver != expect_version:
        return "FAIL", f"版本 {ver} ≠ 期望 {expect_version}（工具 {result['tools']}）"
    if result["tools"] < 10:
        return "FAIL", f"工具面只有 {result['tools']} 个：{result['names']}"
    return "PASS", f"{result['tools']} 工具，版本 {ver}（{sha}），packs " \
                   f"{','.join(info.get('packs') or [])}{extra}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", default=[])
    ap.add_argument("--expect-version", default="")
    ap.add_argument("--call", action="append", default=[],
                    help="额外调用的只读工具名（可多次）")
    a = ap.parse_args()
    build = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8"))
    expect = a.expect_version or str(build.get("version"))
    calls = list(DEFAULT_CALLS) + [(t, {"query": "CodeArts", "limit": 3})
                                   for t in a.call if t == "vod_search_products"]
    results = {}
    for host in (a.host or HOSTS):
        if host == "dsh":
            for prof in ("web", "headless"):
                entry, why = hm.resolve_entry("dsh", profile=prof)
                label = f"dsh:{prof}"
                if not entry:
                    results[label] = "SKIP"
                    print(f"[{label}] SKIP: {why}")
                    continue
                try:
                    state, msg = check(host, probe_entry(entry, calls), expect)
                except Exception as e:                      # noqa: BLE001
                    state, msg = "FAIL", f"{e.__class__.__name__}: {e}"
                results[label] = state
                print(f"[{label}] {state}: {msg}")
            continue
        entry, why = hm.resolve_entry(host)
        if entry is None:
            state = "SKIP" if hm.EXPECT.get(host, {}).get("skip") else "FAIL"
            results[host] = state
            print(f"[{host}] {state}: {why}")
            continue
        try:
            state, msg = check(host, probe_entry(entry, calls), expect)
        except Exception as e:                              # noqa: BLE001
            state, msg = "FAIL", f"{e.__class__.__name__}: {e}"
        results[host] = state
        print(f"[{host}] {state}: {msg}")
    bad = sum(1 for s in results.values() if s == "FAIL")
    skip = sum(1 for s in results.values() if s == "SKIP")
    print(f"\n工具面探针：{len(results) - bad - skip} PASS / {bad} FAIL / {skip} SKIP"
          f"（期望版本 {expect}）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())