#!/usr/bin/env python3
"""三宿主连通冒烟（安装后自检/发版前回归；不替代 pytest 门禁）。

用法：python3 scripts/smoke_hosts.py [--target hermes|opencode|codex]...
每宿主做识别级检查（MCP 配置可见/工具清单可达），汇总退出码：
0=全部通过，1=任一失败。需要真宿主 CLI 在 PATH——CI 无宿主时跳过不跑。
"""
import argparse
import shutil
import subprocess
import sys

CHECKS = {
    "hermes": ["hermes", "mcp", "list"],
    "opencode": ["opencode", "mcp", "list"],
    "codex": ["codex", "mcp", "list"],
}


def smoke(target: str) -> bool:
    cmd = CHECKS[target]
    if not shutil.which(cmd[0]):
        print(f"[{target}] SKIP: {cmd[0]} 不在 PATH")
        return True  # 无宿主=跳过不 FAIL（CI 语义）
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    hit = "vod-devkit" in out  # 断言：宿主可见 vod-devkit 注册
    print(f"[{target}] {'OK' if (r.returncode == 0 and hit) else 'FAIL'}: {' '.join(cmd)}")
    if not (r.returncode == 0 and hit):
        print(out.strip()[:400])
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="append", choices=list(CHECKS))
    a = ap.parse_args()
    targets = a.target or list(CHECKS)
    results = {t: smoke(t) for t in targets}
    for t, ok in results.items():
        print(f"{t}: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
