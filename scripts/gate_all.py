#!/usr/bin/env python3
"""统一门禁入口（ARCH-BLD-01，2026-11-19 走查 P1）。

**为什么要有这个文件**：CI 有两份定义（GitHub / GitCode），门禁清单长期漂移——
GitHub 侧 10 步、GitCode 侧 5 步，`secret_scan`/`mypy`/花名册对账/规则溯源/发版对账/
dsh 单测/宿主矩阵在 GitCode 侧**全部缺席**。本仓实际托管在 GitCode ⇒ 真跑的门禁只有
那 5 步。两份定义各自内联，改一处忘一处是必然。

修法：**门禁清单只写在这里**，两份 CI 都只调 `python3 scripts/gate_all.py --all`。
再加用例断言"两份 yaml 的 step 名集合相等"，漂移当场红。

用法：
    python3 scripts/gate_all.py --all              # CI 全量
    python3 scripts/gate_all.py lint copies tests  # 本地挑着跑
    python3 scripts/gate_all.py --list             # 列出所有门禁名

退出码：任一门禁失败即非零（CI 据此判红）。**"跳过"必须打印原因且不判绿**——
无引擎检出/无 node 时 SKIP 是事实，但绝不能说成通过（历史实锤：SKIP 被当绿，
dsh 单测红了整周没人发现）。
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list, cwd: Path | None = None, env: dict | None = None) -> int:
    print(f"\n▶ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, cwd=str(cwd or ROOT), env=env)
    return r.returncode


def gate_lint(_):
    return _run([sys.executable, "-m", "pyflakes", "src/vod_mcp", "src/vodkit_cli",
                 "integrations/hermes/hooks", "tests"])


def gate_copies(_):
    rc = _run([sys.executable, "scripts/sync_plugin.py"])
    if rc:
        return rc
    return _run([sys.executable, "scripts/verify_copies.py"])


def gate_secret(_):
    return _run([sys.executable, "scripts/secret_scan.py"])


def gate_roster(_):
    return _run([sys.executable, "scripts/sync_case_roster.py", "--check"])


def gate_rules(_):
    """规则技能 ↔ 引擎真源对账。无引擎检出时脚本自身会 SKIP 并打印原因。"""
    return _run([sys.executable, "scripts/rules_provenance.py"])


def gate_mypy(_):
    return _run([sys.executable, "-m", "mypy"])


def gate_registry(_):
    """发版状态对账（registry ↔ 仓内）。仓内领先=开发中，脚本不判红。"""
    return _run([sys.executable, "scripts/registry_reconcile.py"])


def gate_tests(_):
    return _run([sys.executable, "-m", "pytest", "tests/", "-q"])


def gate_dsh(_):
    """dsh 壳单测（node --test）。没 node 或没装依赖时必须明说 SKIP。"""
    pkg = ROOT / "packages" / "dsh"
    if not shutil.which("node"):
        print("\n▶ dsh 单测：SKIP（runner 无 node，**不判绿**）")
        return 0
    if not (pkg / "node_modules").is_dir():
        print("\n▶ dsh 单测：安装依赖…")
        rc = _run(["npm", "install", "--no-audit", "--no-fund"], cwd=pkg)
        if rc:
            return rc
    return _run(["npm", "test"], cwd=pkg)


def gate_packaging(_):
    """npm 包内容校验：包内文件必须覆盖 src/ 全量（BLD-06 的兜底，不靠人眼看 asserts）。"""
    script = ROOT / "scripts" / "pack_verify.py"
    if not script.is_file():
        print("\n▶ 包内容校验：SKIP（scripts/pack_verify.py 不存在）")
        return 0
    return _run([sys.executable, str(script)])


def gate_hostmatrix(_):
    """宿主安装矩阵（隔离 HOME 装→验→卸）。runner 无宿主 CLI 的项记 SKIP。"""
    return _run([sys.executable, "scripts/host_matrix.py"])


# 名字 → 函数。**顺序即执行顺序**：先便宜的后贵的，便于快速失败。
GATES = {
    "lint": gate_lint,
    "copies": gate_copies,
    "secret": gate_secret,
    "roster": gate_roster,
    "rules": gate_rules,
    "mypy": gate_mypy,
    "registry": gate_registry,
    "tests": gate_tests,
    "dsh": gate_dsh,
    "packaging": gate_packaging,
    "hostmatrix": gate_hostmatrix,
}


def main() -> int:
    ap = argparse.ArgumentParser(prog="gate_all.py")
    ap.add_argument("names", nargs="*", help="要跑的门禁名（缺省配合 --all）")
    ap.add_argument("--all", action="store_true", help="跑全部门禁")
    ap.add_argument("--list", action="store_true", help="列出所有门禁名")
    args = ap.parse_args()

    if args.list:
        for n in GATES:
            print(n)
        return 0

    names = list(GATES) if args.all else args.names
    if not names:
        ap.print_help()
        return 2

    unknown = [n for n in names if n not in GATES]
    if unknown:
        print(f"未知门禁名：{unknown}（可用：{list(GATES)}）", file=sys.stderr)
        return 2

    failed = []
    for n in names:
        rc = GATES[n](None)
        print(f"  {'✅' if rc == 0 else '❌'} {n}")
        if rc != 0:
            failed.append(n)

    print("\n" + "=" * 60)
    if failed:
        print(f"FAIL 门禁未过：{', '.join(failed)}")
        return 1
    print(f"PASS 全部 {len(names)} 项门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())