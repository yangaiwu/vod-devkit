"""安装行/视图的单一入口（S160，D-single-entry-1）。

为什么要这道门禁：同一条读法
`manifest.get("installs") or ([manifest] if manifest.get("target") else [])`
曾在 doctor / prune / packs / uninstall 各写一份，而且各自的判据还不一样——
uninstall 那份无条件回落 `[mf]`，空 manifest 会被当成"有安装"；doctor 的 --target
视图与 verify 的 preset 分支又各拼一遍行视图（非 None 覆盖）。收敛到 common 一处，
并用一条反向锁禁止第二套实现长回来。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# 只禁「用整份 manifest 顶替安装行」的写法；`or []`（packs 只更新 installs[]）是合法语义
_ROWS_PAT = re.compile(r'get\(\s*"installs"\s*\)\s*or\s*\(?\[?\s*(?:mf|manifest|raw)\b')


def test_s160_install_rows_handles_both_manifest_shapes():
    from vodkit_cli import common

    new = {"installs": [{"target": "a"}, {"target": "dsh", "dshProfile": "web"}]}
    assert common.install_rows(new) == new["installs"]
    old = {"target": "hermes", "version": "1"}
    assert common.install_rows(old) == [old]
    assert common.install_rows({}) == []
    assert common.install_rows({"installs": []}) == []   # 空 installs 不回落到顶层


def test_s160_row_view_ignores_none_fields():
    from vodkit_cli import common

    mf = {"target": "a", "version": "old", "mcpConfig": "/x"}
    row = {"target": "a", "version": "new", "mcpConfig": None}
    view = common.row_view(mf, row)
    assert view["version"] == "new"
    assert view["mcpConfig"] == "/x"       # None 不覆盖，等价于旧写法
    assert mf["version"] == "old"          # 不改入参


def test_s160_latest_row_takes_last():
    from vodkit_cli import common

    mf = {"installs": [{"target": "a"}, {"target": "b"}]}
    assert common.latest_row(mf)["target"] == "b"
    assert common.latest_row({}) == {}


def test_s160_manifest_rows_read_only_in_common():
    """反向锁：src 里除 common.py 外不许再手写「整份 manifest 顶替安装行」。"""
    offenders = []
    for p in SRC.rglob("*.py"):
        if p.name == "common.py":
            continue
        if _ROWS_PAT.search(p.read_text(encoding="utf-8")):
            offenders.append(str(p.relative_to(ROOT)))
    assert offenders == [], f"安装行读法散落在：{offenders}（改用 common.install_rows）"