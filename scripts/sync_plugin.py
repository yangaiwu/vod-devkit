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
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 源目录 → 副本目录（相对仓根）。两侧同名是 paths.root() 的前提：
# “ROOT = vod_mcp 的父目录”对仓根/载荷/插件副本三种形态都成立。
PAIRS: tuple[tuple[str, str], ...] = (
    # 源相对**仓根**；S3 后运行期包在 src/、资产在 assets/
    ("src/vod_mcp", "plugins/vod-devkit/vod_mcp"),
    ("assets/skills", "plugins/vod-devkit/skills"),
    ("assets/contract", "plugins/vod-devkit/contract"),
    ("assets/safety", "plugins/vod-devkit/safety"),
)
# 插件副本还带上 hook 脚本（发布物要自包含）
EXTRA_PAIRS: tuple[tuple[str, str], ...] = (
    ("integrations/hermes/hooks", "plugins/vod-devkit/hooks"),
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


def sync(root: Path = ROOT, quiet: bool = False, write_build_info: bool = True) -> dict:
    """整目录覆盖生成副本 + 烧录两处 build-info（幂等）。返回 build-info 内容。

    `write_build_info=False`（S163-1）：只同步目录，不动两份 build-info。
    测试期的 conftest 夹具必须用这个形态——旧写法把 tracked 的根 build-info 重烧成当前 HEAD，
    于是 `test_build_info_root_and_plugin_copy_agree` 在给自己刚改过的文件打分：
    常规跑绿、`VOD_DEVKIT_NO_BUILD_INFO=1`（host_matrix / CI 顺序）必红。
    """
    for src_rel, dst_rel in PAIRS + EXTRA_PAIRS:
        src, dst = root / src_rel, root / dst_rel
        if not src.is_dir():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))

    sha = _git(["rev-parse", "HEAD"], root) or None
    # 远端 URL 脱敏后再烧进包里（push URL 里可能内嵌凭据）
    remote = re.sub(r"(https?://)([^@/]+@)", r"\1", _git(["remote", "get-url", "origin"], root))
    version = _version_from_init(root / "src" / "vod_mcp" / "__init__.py")
    bi = {"version": version, "commitSha": sha,
          "builtAt": datetime.datetime.now().isoformat(timespec="seconds"),
          "sourceRemote": remote or None}
    if os.environ.get("VOD_DEVKIT_NO_BUILD_INFO") or not write_build_info:
        # 打包/隔离跑法/测试期：保留现有 build-info（npm prepack 会跑本函数，若按当前 HEAD
        # 重烧，tarball 的代码指纹就不再等于 tag，与 release.sh 的终态断言冲突——
        # 2026-11-16 实锤：v0.5.27 因此被拒发）。S163-1：测试期也走这条，不许改 tracked 根。
        if not quiet:
            print("build-info：跳过重烧（VOD_DEVKIT_NO_BUILD_INFO / write_build_info=False）")
        bi = json.loads((root / "build-info.json").read_text(encoding="utf-8")) \
            if (root / "build-info.json").is_file() else bi
        # 插件副本是生成物（不入 git）：只在**缺失**时按现有根内容补一份，
        # 否则副本自包含类用例会直接 FileNotFoundError（S163-1 的边界）。
        pkg_rel = "plugins/vod-devkit/build-info.json"
        if not (root / pkg_rel).is_file():
            (root / pkg_rel).write_text(
                json.dumps(bi, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return bi
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
    ap.add_argument("--no-build-info", action="store_true",
                    help="只同步副本，不重烧 build-info（门禁/pre-push 用：不许动 tracked 根）")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    sync(Path(args.root), quiet=args.quiet, write_build_info=not args.no_build_info)
    return 0


if __name__ == "__main__":
    sys.exit(main())