"""声明计数对账门禁（借鉴 huaweicloud-devkit：counts derive from the roster,
never from hand lists that silently drift）。

事故（2026-11-11 实测）：同一份代码同时被四处文档描述成不同的规模——
README.md 写「39 用例」、README.en.md 写「39 tests」、ci.yml 步骤名写
「25 用例」、scheme-overview 写「24 用例」，真实是全量 194+24。
数字没人读得出来是错的，但每一条都在替产品背书。

纪律：对外文档不手写用例/测试/工具计数，只写「全量」并给出实测命令；
计数由 CI/本测试现场测量。历史记录（CHANGELOG/decisions.md）不受此限——
它们是台账，不是现状声明。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCANNED = [
    "README.md",
    "README.en.md",
    "INSTALL.md",
    "QUICKSTART.md",
    "CONTRIBUTING.md",
    "docs/scheme-overview.md",
    "docs/safety-model.md",
    ".github/workflows/ci.yml",
]

# 中文/英文的「用例/测试」计数
_CASES = re.compile(r"(\d{1,4})\s*(?:个)?(?:测试用例|用例|条用例)")
_TESTS = re.compile(r"(\d{1,4})\s+tests?\b")
# 工具面计数（改工具数=改契约，文档手写必漂）
_TOOLS = re.compile(r"(\d{1,4})\s*(?:个)?(?:MCP\s*)?工具")


def _scan():
    hits = []
    for rel in SCANNED:
        p = ROOT / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for rx, kind in ((_CASES, "用例"), (_TESTS, "测试"), (_TOOLS, "工具")):
                m = rx.search(line)
                if m:
                    hits.append(f"{rel}:{i} 「{kind} {m.group(1)}」 → {line.strip()[:80]}")
    return hits


def test_no_hand_written_case_or_tool_counts_in_outward_docs():
    hits = _scan()
    assert not hits, (
        "对外文档/CI 里手写了用例或工具计数（必然漂移，且无人能读出是错的）：\n  "
        + "\n  ".join(hits)
        + "\n改写方式：写「全量」并给实测命令（python3 -m pytest tests/ -q），"
          "或删除数字；不要改成另一个数字。")


def test_scanned_docs_exist():
    """扫描清单本身要有承载——文件改名后静默放过整条门禁是更坏的失败。"""
    missing = [rel for rel in SCANNED if not (ROOT / rel).exists()]
    assert not missing, (
        "声明对账扫描清单里的文件不存在（改名了？同步更新 SCANNED）：\n  "
        + "、".join(missing))