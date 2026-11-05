#!/usr/bin/env python3
"""插件自包含同步：vod_mcp/ → plugins/vod-devkit/vod_mcp/（发版前/提交前跑）。
插件被 codex 缓存隔离安装，.mcp.json 相对路径只够到插件包内——server 必须
随包携带（对齐 devkit 的 dist 自包含形态）。幂等整目录覆盖。"""
import json, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "vod_mcp"
dst = ROOT / "plugins" / "vod-devkit" / "vod_mcp"
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "runtime.json", "*.log"))
# 烧录 build-info.json（provenance 的版本/SHA 真源）：插件包没有它，vod_devkit_info 版本号失真
import subprocess, datetime
sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
import re
remote = re.sub(r"(https?://)([^@/]+@)", r"\1", remote) or None
version = (dst / "__init__.py").read_text(encoding="utf-8").split('__version__ = "')[1].split('"')[0]
bi = {"version": version, "commitSha": sha,
      "builtAt": datetime.datetime.now().isoformat(timespec="seconds"), "sourceRemote": remote}
(ROOT / "plugins" / "vod-devkit" / "build-info.json").write_text(
    json.dumps(bi, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"synced {src} -> {dst}; build-info: {bi['version']}@{str(bi['commitSha'])[:8]}")
