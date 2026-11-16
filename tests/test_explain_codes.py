"""S154：错误码解释表与 raise 点一致（2026-11-16 通读漏面实锤）。

背景：`explain` 面长期与代码分叉——`-32011` 被说成"产品不在名录里"（真实语义是草稿/审批
令牌不符），`-32012` / `-32014` / `-32015` 在代码里 raise 却"未收录"。上一轮把错误码清单
改成 -32010/11/12/14，这张表没跟上，于是文档与命令两套说法。

门禁口径：**代码里出现的 `code=-320XX` ⊆ explain 表**，且 explain 必须 known；
另外锁死 -32011 的语义（不许再被写成产品名录）。
"""
import re
from pathlib import Path

from vod_mcp import diagnose

SRC = Path(__file__).resolve().parent.parent / "src" / "vod_mcp"


def _raised_codes() -> set:
    """代码里真实 raise / 抛出的错误码（`ToolError(..., code=-320XX)`）。"""
    codes = set()
    for f in SRC.rglob("*.py"):
        if f.name == "diagnose.py":
            continue                    # 解释表本身不是 raise 点
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"code\s*=\s*(-320\d\d)", text):
            codes.add(m.group(1))
    return codes


def test_s154_every_raised_code_is_explained():
    codes = _raised_codes()
    assert codes, "扫描面失效（一个 raise 点都没扫到）"
    missing = []
    for c in sorted(codes):
        got = diagnose.explain(c)
        if not got["known"] or not got["cause"]:
            missing.append((c, got["cause"]))
    assert not missing, f"代码里 raise 了但 explain 未收录/无原因：{missing}"


def test_s154_known_codes_are_self_consistent():
    for c in ("-32010", "-32011", "-32012", "-32014", "-32015"):
        got = diagnose.explain(c)
        assert got["known"], f"{c} 未收录"
        assert got["layer"] and got["cause"] and got["action"], f"{c} 三要素不全：{got}"


def test_s154_32011_is_draft_token_mismatch_not_catalog():
    got = diagnose.explain("-32011")
    assert "草稿" in got["cause"] or "令牌" in got["cause"], got
    assert "名录" not in got["cause"], f"-32011 又被写成产品名录：{got}"