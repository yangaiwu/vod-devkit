#!/usr/bin/env python3
"""插件副本生成器（唯一入口）：把源目录同步成 plugins/vod-devkit 的自包含副本。

为什么是生成物而不是入库副本（D-copies-generated-1，v0.5.9）：
副本入库时，本脚本会先把**源侧与副本侧都**写成新内容，于是任何基于工作区的
`diff -r` 门禁恒绿；提交清单只要漏一项（v0.5.8 漏 contract），tarball 就与 tag
不一致，而所有门禁都不会说话。零提交后「两份真值」这个矛盾不存在。

调用方（都在同一条语义上）：
- `package.json` 的 `prepack`：npm 打包/发布前自动重跑
- `scripts/verify_copies.py`：门禁从这里 import PAIRS/IGNORE（单一真源，不再各写一份）
- `tests/conftest.py`、`scripts/host_matrix.py`：测试/矩阵前跑一次
- `vod_mcp/host_adapters/codex.py`：仓内直跑安装时缺副本则兜底生成（子进程调用）

用法：
  python3 scripts/sync_plugin.py            # 生成（幂等整目录覆盖）
  python3 scripts/sync_plugin.py --quiet    # 静默（prepack 用）
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 源目录 → 副本目录（相对仓根）。两侧同名是 paths.root() 的前提：
# “ROOT = vod_mcp 的父目录”对仓根/载荷/插件副本三种形态都成立。
PAIRS: tuple[tuple[str, str], ...] = (
    ("vod_mcp", "plugins/vod-devkit/vod_mcp"),
    ("src/skills", "plugins/vod-devkit/skills"),
    ("src/contract", "plugins/vod-devkit/contract"),
    ("src/safety", "plugins/vod-devkit/safety"),
)
# 运行期状态与构建缓存不属于副本内容：runtime.json 只活在根侧（含 key 与账本），
# 插件副本永远不该有它。verify_copies.py 直接复用这份清单（含忽略规则也只有一处）。
IGNORE_PATTERNS = ("__pycache__", "runtime.json", "*.pyc", "*.log")
# 两处 build-info 一起烧：插件包那份给 provenance 用，根那份给 status/verify/doctor 读
BUILD_INFO = ("plugins/vod-devkit/build-info.json", "build-info.json")


def _version_from_init(path: Path) -> str:
    return path.read_text(encoding="utf-8").split('__version__ = "')[1].split('"')[0]


def _git(args: list[str], root: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def sync(root: Path = ROOT, quiet: bool = False) -> dict:
    """整目录覆盖生成副本 + 烧录两处 build-info（幂等）。返回 build-info 内容。"""
    for src_rel, dst_rel in PAIRS:
        dst = root / dst_rel
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(root / src_rel, dst,
                        ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))

    sha = _git(["rev-parse", "HEAD"], root) or None
    # 远端 URL 脱敏后再烧进包里（push URL 里可能内嵌凭据）
    remote = re.sub(r"(https?://)([^@/]+@)", r"\1", _git(["remote", "get-url", "origin"], root))
    version = _version_from_init(root / "vod_mcp" / "__init__.py")
    bi = {"version": version, "commitSha": sha,
          "builtAt": datetime.datetime.now().isoformat(timespec="seconds"),
          "sourceRemote": remote or None}
    for rel in BUILD_INFO:
        (root / rel).write_text(json.dumps(bi, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    if not quiet:
        print(f"synced {root / 'vod_mcp'} -> {root / PAIRS[0][1]}; "
              f"build-info: {bi['version']}@{str(bi['commitSha'])[:8]}")
    return bi


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="不打印（npm prepack 用）")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    sync(Path(args.root), quiet=args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())