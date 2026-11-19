#!/usr/bin/env python3
"""安装/核验 git hooks（ARCH-BLD-05）。

背景：`CONTRIBUTING.md` 早就写了「已 `git config core.hooksPath .githooks`」，
但实测 `git config --get core.hooksPath` **为空** ⇒ 新克隆里 pre-push 门禁从不生效，
开发者以为 push 前会跑 pytest/pyflakes/双副本/secret_scan，实际一条都不跑。
配合 BLD-01（平台侧门禁只覆盖部分项），等于本地与平台都没跑 secret_scan/mypy。

用法：
    python3 scripts/install_hooks.py          # 安装（幂等）
    python3 scripts/install_hooks.py --check  # 只核验，未接线则 exit 1（供 CI/用例断言）

设计纪律：
- **幂等**：已是 `.githooks` 就不重复写；指向别处则如实报告并覆盖（附原值）。
- **不跨仓生效**：设置的是本仓 `.git/config`，不碰 `--global`（否则污染用户其他仓库）。
- **不是 git 仓库就明说**（载荷副本/裸包里没有 .git，退出码 2 而不是假装成功）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ".githooks"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in argv

    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print(f"[hooks] 不是 git 工作树：{ROOT}（载荷副本/裸包无需安装钩子）", file=sys.stderr)
        return 2

    if not (ROOT / HOOKS_DIR / "pre-push").exists():
        print(f"[hooks] 缺 {HOOKS_DIR}/pre-push —— 仓不完整", file=sys.stderr)
        return 2

    cur = _git("config", "--get", "core.hooksPath").stdout.strip()
    # 双向判据：既要比字符串，也要确认钩子真能被执行（core.hooksPath 指向正确
    # 但文件无 x 位时 git 会静默跳过 —— 那是同一个后果）。
    hook = ROOT / HOOKS_DIR / "pre-push"
    executable = hook.stat().st_mode & 0o111 != 0

    if check_only:
        ok = cur == HOOKS_DIR and executable
        print(f"[hooks] core.hooksPath = {cur or '(未设置)'}；pre-push 可执行 = {executable}")
        if not ok:
            print("[hooks] 未接线：请执行 python3 scripts/install_hooks.py", file=sys.stderr)
        return 0 if ok else 1

    if cur == HOOKS_DIR and executable:
        print(f"[hooks] 已接线（core.hooksPath={cur}），无需改动")
        return 0

    if cur and cur != HOOKS_DIR:
        print(f"[hooks] 覆盖原 core.hooksPath={cur} → {HOOKS_DIR}")
    r = _git("config", "core.hooksPath", HOOKS_DIR)
    if r.returncode != 0:
        print(f"[hooks] 写入失败：{r.stderr.strip()[:200]}", file=sys.stderr)
        return 1

    if not executable:
        hook.chmod(hook.stat().st_mode | 0o111)
        print(f"[hooks] 已补 {HOOKS_DIR}/pre-push 执行位")

    print(f"[hooks] 已接线：core.hooksPath={HOOKS_DIR}（仅本仓，未改 --global）")
    print("[hooks] 生效范围：next `git push` 起；如需跳过用 `git push --no-verify`（不推荐）")
    return 0


if __name__ == "__main__":
    sys.exit(main())