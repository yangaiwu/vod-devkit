#!/usr/bin/env python3
"""多宿主冒烟：识别级 → 功能级（安装后自检 / 发版前回归，不替代 pytest 门禁）。

为什么要有功能级这一档：识别级（`<host> mcp list` 里出现 vod-devkit）只证明
配置格式被宿主接受了——配置里的**实际启动命令**可能指向旧副本、环境变量
可能被覆盖、runtime.json 可能过期。历史实锤：codex 经 PATH 落到全局 npm
旧副本、opencode 复用 root venv 解释器直接 Permission denied，两者识别级
都是绿的。

功能级做法：读**宿主真正会用的配置**（不是仓内文件），按同样 command/env
拉起 stdio server，握手 → tools/list → 真调一次只读工具 `vod_devkit_info`，
断言返回的 version/commitSha 非空、且与 --expect-version 一致。零写操作。

用法：
  python3 scripts/smoke_hosts.py [--target hermes|opencode|codex|dsh]...
                                  [--expect-version 0.4.4]
                                  [--expect-tools vod_devkit_info,vod_list_skills,...]
                                  [--recognition-only]

注意：--expect-tools 是「发货后」的可信判据——版本号相同不代表工具面相同
（npx 缓存副本与仓内 head 可以同为 0.4.4 而少一半工具）。
退出码：0=全部通过（无宿主/无配置=SKIP 也计通过），1=任一 FAIL。
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()

RECOGNITION = {
    "hermes": ["hermes", "mcp", "list"],
    "opencode": ["opencode", "mcp", "list"],
    "codex": ["codex", "mcp", "list"],
    "dsh": None,  # dsh 无 mcp list：识别按 profile patch 判定
}


def _all(*paths):
    for p in paths:
        if p.exists():
            return p
    return None


def _resolve(host: str):
    """解析宿主实际会用的启动规格 → {command, args, env, source} 或 None。

    只认各宿主安装器写出的那三份配置；读不到就 SKIP，不猜。
    """
    if host == "hermes":
        p = HOME / ".hermes" / "mcp" / "vod-devkit.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"command": d.get("command"), "args": d.get("args") or [],
                "env": d.get("env") or {}, "source": str(p)}
    if host == "opencode":
        p = HOME / ".config" / "opencode" / "opencode.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        srv = (d.get("mcp") or {}).get("vod-devkit") or {}
        if not srv:
            return None
        cmd = srv.get("command") or []
        return {"command": cmd[0] if cmd else None, "args": list(cmd[1:]),
                "env": srv.get("environment") or {}, "source": str(p)}
    if host == "codex":
        cache = HOME / ".codex" / "plugins" / "cache" / "vod-local" / "vod-devkit"
        p = _all(*sorted(cache.glob("*/.mcp.json")) if cache.exists() else [])
        if p is None:
            return None
        srv = ((json.loads(p.read_text(encoding="utf-8")).get("mcpServers") or {})
               .get("vod-devkit") or {})
        if not srv:
            return None
        return {"command": srv.get("command"), "args": srv.get("args") or [],
                "env": srv.get("env") or {}, "source": str(p)}
    if host == "dsh":
        for patch in sorted((HOME / ".dsh" / "profiles").glob("*/cordis.patch.yml")):
            if "- id: vod-devkit" in patch.read_text(encoding="utf-8", errors="replace"):
                return {"command": None, "args": [], "env": {}, "source": str(patch)}
    return None


def _probe_stdio(spec, timeout=60) -> dict:
    """按宿主配置拉起 server：initialize → tools/list → 真调 vod_devkit_info。"""
    import os
    env = os.environ.copy()
    env.update({k: str(v) for k, v in (spec.get("env") or {}).items()})
    proc = subprocess.Popen([spec["command"], *[str(a) for a in spec["args"]]],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, env=env, text=True)
    assert proc.stdin is not None and proc.stdout is not None

    def rpc(msg):
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server 无响应（进程退出或 stdout 关闭——"
                               "多半是启动命令/解释器不对）")
        return json.loads(line)

    try:
        init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18",
                               "clientInfo": {"name": "smoke_hosts", "version": "1"},
                               "capabilities": {}}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0",
                                     "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = [t.get("name") for t in (tools.get("result") or {}).get("tools") or []]
        info = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "vod_devkit_info", "arguments": {}}})
        node = (info.get("result") or {}).get("structuredContent") or {}
        if not node and (info.get("result") or {}).get("content"):
            node = json.loads(info["result"]["content"][0]["text"])
        return {"version": (init.get("result") or {}).get("serverInfo", {}).get("version"),
                "tools": names, "info": node, "error": info.get("error")}
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def _recognition(host) -> tuple:
    cmd = RECOGNITION.get(host)
    if cmd is None:
        return True, "无 CLI 识别面（按配置判定）"
    if not shutil.which(cmd[0]):
        return True, f"SKIP: {cmd[0]} 不在 PATH"
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    ok = r.returncode == 0 and "vod-devkit" in out
    return ok, " ".join(cmd) + ("" if ok else " 未列出 vod-devkit")


def _functional(host, expect_version, expect_tools=()) -> tuple:
    spec = _resolve(host)
    if spec is None:
        return True, "SKIP: 无 vod-devkit 配置（未装到该宿主？）"
    if not spec.get("command"):
        return True, f"SKIP: 插件形态无独立 stdio 面（{spec['source']}）"
    if not Path(spec["command"]).exists() and not shutil.which(spec["command"]):
        return False, f"配置里的启动命令不存在：{spec['command']}（{spec['source']}）"
    try:
        got = _probe_stdio(spec)
    except Exception as e:
        return False, f"stdio 探针失败：{e.__class__.__name__}: {e}（{spec['source']}）"
    if got.get("error"):
        return False, f"tools/call 返回错误：{got['error']}"
    ver = (got.get("info") or {}).get("version") or got.get("version")
    if not ver:
        return False, f"vod_devkit_info 没返回版本（{spec['source']}）"
    if expect_version and str(ver) != str(expect_version):
        return False, (f"版本漂移：探针 {ver} ≠ 期望 {expect_version}——该宿主"
                       f"指向旧副本（{spec['source']}）")
    if expect_tools:
        missing = sorted(set(expect_tools) - set(got["tools"]))
        if missing:
            return False, (f"工具面缺 {len(missing)} 个：{missing}——该宿主跑的是"
                           f"旧副本（{spec['source']}）")
    src = (got.get("info") or {}).get("commitSha") or "n/a"
    note = ""
    root = str(Path(__file__).resolve().parent.parent)
    if spec["args"] and root not in str(spec["args"][0]):
        note = "（注意：该宿主指向的 server 不在本仓，是另一份副本）"
    return True, f"{len(got['tools'])} 工具；版本 {ver}；来源 {src}{note}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="append", choices=list(RECOGNITION))
    ap.add_argument("--expect-version", default="")
    ap.add_argument("--expect-tools", default="",
                    help="逗号分隔的必需工具名（发货后核验工具面，防同版本少工具）")
    ap.add_argument("--recognition-only", action="store_true", help="只做识别级（旧行为）")
    a = ap.parse_args()
    targets = a.target or list(RECOGNITION)
    results = {}
    for t in targets:
        ok_r, msg_r = _recognition(t)
        print(f"[{t}] 识别级 {'OK' if ok_r else 'FAIL'}: {msg_r}")
        if not ok_r:
            results[t] = False
            continue
        if a.recognition_only:
            results[t] = True
            continue
        want = [x.strip() for x in a.expect_tools.split(",") if x.strip()]
        ok_f, msg_f = _functional(t, a.expect_version, want)
        print(f"[{t}] 功能级 {'OK' if ok_f else 'FAIL'}: {msg_f}")
        results[t] = ok_f
    print("\n".join(f"{t}: {'PASS' if ok else 'FAIL'}" for t, ok in results.items()))
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()