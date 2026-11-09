"""打包白名单护栏（P0 根因实锤：npm 0.4.1 包缺 vod_mcp/pending.py——
package.json files 逐文件枚举，新增 .py 忘加白名单=功能静默丢失，
包内代码与仓库 head 脱节且无任何报错）。

纪律：files 是逐文件枚举而非整目录（顶层 vod_mcp/ 含 runtime.json 真实
key+账本，整目录模式会泄漏），因此每新增 vod_mcp 模块必须同步白名单，
本护栏让"忘了"当场红。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# runtime.json（真实 key/账本）与日志/pyc 永不进包
NEVER_PACKED = {"runtime.json"}


def test_files_whitelist_covers_all_vod_mcp_modules():
    """package.json files 必须覆盖 vod_mcp/ 下全部 .py 与 runtime.example.json。"""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    files = set(pkg.get("files", []))
    for entry in sorted((ROOT / "vod_mcp").iterdir()):
        if entry.name in NEVER_PACKED or entry.suffix in (".log", ".pyc"):
            continue
        if entry.is_file() and entry.name != "__pycache__":
            assert f"vod_mcp/{entry.name}" in files, (
                f"vod_mcp/{entry.name} 不在 package.json files 白名单——"
                "npm 包将缺此文件（功能静默丢失）。请补白名单后再发版。")


def test_files_whitelist_covers_all_skills():
    """skills/ 下每个非空技能目录必须能被整目录模式 skills/ 覆盖
    （本用例锁的是：files 必须声明 skills/ 整目录，防止逐目录枚举再漏）。"""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    files = set(pkg.get("files", []))
    assert any(f == "skills/" or f == "skills" for f in files), (
        "files 缺 skills/ 整目录声明——新技能目录将不进包")


def test_runtime_json_never_packable():
    """真实 runtime.json（java_key 明文+200 条账本）绝不允许进包：
    白名单不得出现任何含 runtime.json 的条目，也不得出现 vod_mcp 整目录模式
    （files 白名单生效时整目录会把 runtime.json 一起打进去）。"""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    for f in pkg.get("files", []):
        assert "runtime.json" not in f, f"files 白名单含 {f}——key/账本泄漏风险"
        assert f not in ("vod_mcp", "vod_mcp/"), (
            "files 含 vod_mcp 整目录——会把真实 runtime.json 打进包，"
            "必须逐文件枚举")
