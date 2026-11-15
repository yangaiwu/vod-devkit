#!/usr/bin/env python3
"""双副本一致性唯一入口：内容一致 **且** 改动已提交。

为什么不能只用 `diff -r`（2026-11-15 v0.5.8 实锤）：
    release.sh 先跑 sync_plugin.py 把改过的 contract 版本写进
    plugins/vod-devkit/contract/，再按提交清单 git add——而清单漏了这一项。
    于是每次基于工作区的 diff 检查全绿（两边都被 sync 写成新内容），
    但提交树里插件副本仍是旧版：npm tarball ≠ tag，且没人发现。
    「两边文件相同」只证明同步跑过，不证明**同步结果进了提交**。

本脚本两条断言，缺一不可：
    1. 四个运行时目录（vod_mcp / skills / contract / safety）源与插件副本逐文件相同；
    2. 这四个目录（两侧）没有未提交 / 未跟踪改动（git status 为空）。
用法：
    python3 scripts/verify_copies.py            # 提交前/推送前/发版后
    python3 scripts/verify_copies.py --no-git   # 只查内容（无 git 的打包环境）
"""
import argparse
import fnmatch
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = (
    ("vod_mcp", "plugins/vod-devkit/vod_mcp"),
    ("skills", "plugins/vod-devkit/skills"),
    ("contract", "plugins/vod-devkit/contract"),
    ("safety", "plugins/vod-devkit/safety"),
)
# 运行期状态与构建缓存不是副本内容：runtime.json 只活在根侧（含 key 与账本），
# 插件副本永远不该有它（sync 也按同样的模式排除）。
IGNORE = ("runtime.json", "__pycache__", "*.pyc", "*.log")


def _skip(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in IGNORE)


def _files(base: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not _skip(d)]
        for name in filenames:
            if _skip(name):
                continue
            p = Path(dirpath) / name
            out[str(p.relative_to(base))] = p
    return out


def compare_trees(src: Path, dst: Path) -> list[str]:
    """逐文件比较两棵树（用扩展名无关的逐块比对，避免大文件全读进内存）。"""
    problems: list[str] = []
    if not dst.exists():
        return [f"{dst} 不存在（没跑 scripts/sync_plugin.py？）"]
    a, b = _files(src), _files(dst)
    for rel in sorted(set(a) - set(b)):
        problems.append(f"插件副本缺文件：{rel}")
    for rel in sorted(set(b) - set(a)):
        problems.append(f"插件副本多文件：{rel}（源侧没有=副本里塞了私货）")
    for rel in sorted(set(a) & set(b)):
        pa, pb = a[rel], b[rel]
        if pa.stat().st_size != pb.stat().st_size:
            problems.append(f"内容不同（大小）：{rel}")
            continue
        with open(pa, "rb") as fa, open(pb, "rb") as fb:
            while True:
                ca, cb = fa.read(1 << 20), fb.read(1 << 20)
                if ca != cb:
                    problems.append(f"内容不同：{rel}")
                    break
                if not ca:
                    break
    return problems


def dirty_paths(root: Path, paths, runner=subprocess.run) -> list[str]:
    """这四个目录下是否有未提交/未跟踪改动（=同步结果没进提交）。"""
    r = runner(["git", "status", "--porcelain=v1", "--", *paths],
               cwd=root, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return [f"git status 失败：{(r.stderr or '').strip()[:200]}"]
    return [line for line in (r.stdout or "").splitlines() if line.strip()]


def check(root: Path = ROOT, git_check: bool = True,
          runner=subprocess.run) -> list[str]:
    problems: list[str] = []
    for src_rel, dst_rel in PAIRS:
        problems += compare_trees(root / src_rel, root / dst_rel)
    if git_check:
        both = [p for pair in PAIRS for p in pair]
        for line in dirty_paths(root, both, runner=runner):
            problems.append(f"未提交改动：{line}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-git", action="store_true", help="跳过 git 状态断言（无 git 环境）")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    problems = check(Path(args.root), git_check=not args.no_git)
    if problems:
        print("[copies] FAIL: 双副本不一致或同步结果未提交", file=sys.stderr)
        for p in problems[:20]:
            print(f"  - {p}", file=sys.stderr)
        print("  修法：scripts/sync_plugin.py 后把 plugins/vod-devkit/{vod_mcp,skills,contract,safety} 一起提交",
              file=sys.stderr)
        return 1
    print("[copies] OK: 四个目录内容一致且同步结果已提交")
    return 0


if __name__ == "__main__":
    sys.exit(main())