#!/usr/bin/env python3
"""npm 包内容校验（对齐 devkit pack-verify 思想）：
npm pack --dry-run 干跑 → 断言包内文件集：必含项在、危险项（runtime.json/
日志/账本/key 类文件）绝不在。发版流程 npm publish 前必跑。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUST_HAVE = ["package.json", "bin/vod-devkit", "vod_mcp/server.py",
             "contract/tools.schema.json", "README.md",
             # codex 原生插件路径的 npm 分发必需（marketplace+插件随包）
             "plugins/.agents/plugins/marketplace.json",
             "plugins/vod-devkit/.codex-plugin/plugin.json",
             "plugins/vod-devkit/.mcp.json",
             "plugins/vod-devkit/vod_mcp/server.py",
             "plugins/vod-devkit/skills/vod-feedback-collect/SKILL.md"]
MUST_NOT = ["runtime.json", ".log", "install-manifest.json",
            "node_modules/", ".git"]

def main():
    r = subprocess.run(["npm", "pack", "--dry-run", "--json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print("FAIL: npm pack 干跑失败：", r.stderr[:300]); sys.exit(1)
    data = json.loads(r.stdout)
    files = [f["path"] for f in data[0]["files"]]
    fail = []
    for m in MUST_HAVE:
        if not any(f == m or f.endswith("/" + m) for f in files):
            fail.append(f"缺必含文件: {m}")
    for f in files:
        for bad in MUST_NOT:
            if bad in f:
                fail.append(f"危险文件入包: {f}（命中 {bad}）")
    print(f"npm 包内容：{len(files)} 文件")
    if fail:
        for x in fail:
            print("FAIL:", x)
        sys.exit(1)
    print("pack-verify: OK（必含齐、危险项零）")

if __name__ == "__main__":
    main()
