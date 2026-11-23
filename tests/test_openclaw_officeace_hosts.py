"""OpenClaw / OfficeAce 两个新宿主的形态与破坏性边界（2026-11-16）。

为什么门禁只锁形态、不锁"真机连通"：
- OpenClaw 侧已真机闭环（探测/会话/提交都验过，见 README 与 host.json notes），
  但 CI 机器不一定装 openclaw，所以用例用**假 CLI** 锁"只经 CLI 写、绝不直改 JSON5"；
- OfficeAce 是桌面端（Windows-only），本机无安装对象，只能锁 sqlite 行域逻辑
  与"非 Windows 拒绝"，不伪造真机断言。
"""
import ast
import json
import re
import sqlite3
import sys
import types
import warnings
from pathlib import Path

import pytest

from vod_mcp.host_adapters import officeace, openclaw

ROOT = Path(__file__).resolve().parent.parent


def _spec(p):
    return types.SimpleNamespace(product="CodeArts", java_api_base="https://e",
                                 dsh_profile="", mcp_config="")


# ── 注册表 / 数据面 ───────────────────────────────────────────────────────
def test_both_hosts_registered_with_host_json():
    from vod_mcp import hosts
    from vod_mcp.host_adapters import REGISTRY
    for h in ("openclaw", "officeace"):
        assert h in REGISTRY, f"{h} 没进适配器注册表"
        assert h in hosts.hosts(), f"{h} 缺 integrations/{h}/host.json"
        spec = hosts.load(h)
        for key in ("configPath", "skillsDir"):
            assert spec.get(key), f"{h} 的 host.json 缺 {key}"
    assert openclaw.SUPPORTS_REMOTE is True
    assert officeace.SUPPORTS_REMOTE is False


def test_openclaw_config_is_never_written_directly():
    """openclaw.json 是 JSON5：正常路径只经 CLI；唯一允许的直写是护栏兜底的外科摘除。

    护栏实锤（2026-11-16 矩阵）：配置很小时 `mcp unset` 会被 openclaw 自己的
    `size-drop-vs-last-good` 拒写。兜底只允许：**严格 JSON 可解析**时原子摘掉
    mcp.servers.vod-devkit 一个键（先落 .bak）；JSON5 带注释则不动字节。
    """
    src = (ROOT / "src" / "vod_mcp" / "host_adapters" / "openclaw.py").read_text(encoding="utf-8")
    import re as _re
    bare = _re.findall(r"(?<!atomic_)write_text\(", src)
    assert not bare, "不许出现裸 write_text（会写坏 JSON5/丢注释）"
    assert "merge_mcp_servers(" not in src
    assert '"mcp", "add"' in src and '"mcp", "unset"' in src
    # 唯一写点必须在 _surgical_remove 里，且先做严格 JSON 解析、先备份
    seg = src[src.index("def _surgical_remove"):src.index("def uninstall")]
    assert "json.loads" in seg and "atomic_write_text" in seg and "copyfile" in seg, seg
    assert seg.index("json.loads") < seg.index("atomic_write_text"), "兜底必须先校验再写"
    assert seg.index("copyfile") < seg.index("atomic_write_text"), "兜底必须先备份再写"


# ── OpenClaw：假 CLI 全链路 ───────────────────────────────────────────────
FAKE_CLI = '''#!/usr/bin/env python3
import json, sys
from pathlib import Path
store = Path(sys.argv[0]).with_name("store.json")
state = json.loads(store.read_text()) if store.exists() else {"calls": [], "server": None}
state["calls"].append(sys.argv[1:])
cmd = sys.argv[1:2]
if cmd == ["mcp"] and len(sys.argv) > 2:
    sub = sys.argv[2]
    if sub == "add":
        # 已存在：add 被拒，触发 set 路径
        state["calls"][-1].append("REFUSED-ADD")
        store.write_text(json.dumps(state))
        print("server already exists", file=sys.stderr)
        sys.exit(1)
    if sub == "set":
        state["server"] = json.loads(sys.argv[4])
        store.write_text(json.dumps(state))
        print("saved")
        sys.exit(0)
    if sub == "show":
        store.write_text(json.dumps(state))
        print(json.dumps(state["server"] or {}))
        sys.exit(0)
    if sub == "unset":
        state["server"] = None
        store.write_text(json.dumps(state))
        print("removed")
        sys.exit(0)
store.write_text(json.dumps(state))
'''


def _fake_openclaw(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".openclaw").mkdir(parents=True)
    conf = home / ".openclaw" / "openclaw.json"
    original = '{\n  // 用户的 JSON5 注释，绝不能被我们吃掉\n  "mcp": {"servers": {}}\n}\n'
    conf.write_text(original, encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    cli = bindir / "openclaw"
    cli.write_text(FAKE_CLI, encoding="utf-8")
    cli.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    return home, conf, original, cli.with_name("store.json")


def test_openclaw_install_goes_through_cli_and_keeps_config_bytes(tmp_path, monkeypatch):
    home, conf, original, store = _fake_openclaw(tmp_path, monkeypatch)
    conf_path = openclaw.install(_spec(None), "core,collect")
    assert str(conf_path).endswith(".openclaw/openclaw.json")
    st = json.loads(store.read_text())
    calls = [" ".join(c) for c in st["calls"]]
    assert any(c.startswith("mcp add vod-devkit") for c in calls), calls
    assert any(c.startswith("mcp set vod-devkit") for c in calls), calls
    assert st["server"] and st["server"]["env"].get("VOD_PACKS") == "core,collect"
    assert conf.read_text(encoding="utf-8") == original, (
        "安装器直改 openclaw.json → JSON5 注释会被吃掉")


def test_openclaw_uninstall_only_unsets_own_entry(tmp_path, monkeypatch):
    home, conf, original, store = _fake_openclaw(tmp_path, monkeypatch)
    openclaw.install(_spec(None), "core")
    assert openclaw.uninstall() is True
    st = json.loads(store.read_text())
    assert any(c[:2] == ["mcp", "unset"] and c[2] == "vod-devkit" for c in st["calls"])
    assert st["server"] is None
    assert conf.read_text(encoding="utf-8") == original


def test_openclaw_without_cli_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))          # 空 PATH：找不到 openclaw
    with pytest.raises(SystemExit) as ei:
        openclaw.install(_spec(None), "core")
    assert ei.value.code == 2


# ── OfficeAce：平台拒绝 + sqlite 行域 ────────────────────────────────────
def _mk_officeace_db(tmp_path):
    db = tmp_path / "data" / "mcp-connectors.sqlite"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(str(db))
    con.execute("""CREATE TABLE mcp_connectors (
        id TEXT PRIMARY KEY, owner_user_id TEXT, type TEXT, name TEXT,
        normalized_name TEXT, transport TEXT, timeout_ms INTEGER, command TEXT,
        args_json TEXT, env_json TEXT, enabled INTEGER, status TEXT,
        created_at TEXT, updated_at TEXT, version INTEGER, seeded INTEGER)""")
    con.execute("""CREATE TABLE mcp_connector_tools (
        connector_id TEXT, tool_name TEXT)""")
    con.execute("INSERT INTO mcp_connectors (id, owner_user_id, name, command) "
                "VALUES ('other', 'u-42', 'someone-else', 'x')")
    con.commit()
    con.close()
    return db


def test_officeace_refuses_off_windows(tmp_path, monkeypatch):
    if sys.platform.startswith("win"):
        pytest.skip("这条锁的是非 Windows 平台")
    with pytest.raises(SystemExit) as ei:
        officeace.install(_spec(None), "core")
    assert ei.value.code == 2


def test_officeace_upsert_is_idempotent_and_keeps_owner(tmp_path):
    db = _mk_officeace_db(tmp_path)
    row = officeace.connector_row("/usr/bin/python3", ["/x/server.py"], {"A": "1"})
    assert officeace.upsert_row(db, row) == "created"
    assert officeace.upsert_row(db, officeace.connector_row(
        "/usr/bin/python3", ["/x/server.py"], {"A": "2"})) == "updated"
    con = sqlite3.connect(str(db))
    rows = con.execute("SELECT name, owner_user_id, env_json FROM mcp_connectors "
                       "WHERE name = 'vod-devkit'").fetchall()
    con.close()
    assert len(rows) == 1, rows
    assert rows[0][1] is None, (
        "owner_user_id 默认必须 NULL（2026-11-16 评审 P4：从库里抄第一个非空值 = 把连接器挂到别人名下）")
    assert json.loads(rows[0][2]) == {"A": "2"}


def test_officeace_upsert_raises_no_deprecation_under_strict_warnings(tmp_path):
    """回归锁（2026-11-19 修复清单 P1）：UPDATE 分支曾用 ?1..?6 编号占位符绑位置元组。

    sqlite3 认为编号占位符是「命名参数」，配位置序列在 3.14 起抛 ProgrammingError；
    3.12/3.13 只发 DeprecationWarning，于是普通跑测试永远绿 —— 这正是「现在绿、将来必崩」。
    本用例把两者都升级为异常，两条分支（插入 / 更新）各走一次。
    """
    db = _mk_officeace_db(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert officeace.upsert_row(db, officeace.connector_row(
            "/usr/bin/python3", ["/x/server.py"], {"A": "1"})) == "created"
        assert officeace.upsert_row(db, officeace.connector_row(
            "/usr/bin/python3", ["/x/server.py"], {"A": "2"})) == "updated"


def test_officeace_sql_uses_positional_placeholders_only():
    """源码锁：本仓 host_adapters 不许用 ?1..?N 编号占位符（Python 3.14 前向兼容）。

    用 AST 只取**字符串字面量**，不用正则扫全文：正则会把注释（本仓刚踩过——注释里
    写「不是编号 ?1..?N」就被自己抓红）和文档字符串误判成违规，噪音掩盖真问题。
    只锁 host_adapters 目录：本目录全部按位置元组传参，编号占位符（本该配 dict）混用必崩。
    """
    root = Path(officeace.__file__).parent
    offenders = []
    for py in sorted(root.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.search(r"\?\d", node.value):
                    offenders.append(f"{py.name}:{node.lineno}: {node.value[:60]!r}")
    assert not offenders, (
        "host_adapters 里出现编号 SQL 占位符，与位置元组绑定混用会在 Python 3.14 抛 "
        "ProgrammingError。改用 ?：\n" + "\n".join(offenders))


def test_officeace_owner_only_from_explicit_env(tmp_path, monkeypatch):
    db = _mk_officeace_db(tmp_path)
    monkeypatch.setenv("OFFICEACE_OWNER_USER_ID", "u-7")
    officeace.upsert_row(db, officeace.connector_row("/py", ["/s.py"], {}))
    con = sqlite3.connect(str(db))
    got = con.execute("SELECT owner_user_id FROM mcp_connectors WHERE name='vod-devkit'").fetchone()
    con.close()
    assert got[0] == "u-7", "显式来源必须生效（且只认这一个来源）"


def test_officeace_uninstall_removes_only_its_rows(tmp_path):
    db = _mk_officeace_db(tmp_path)
    officeace.upsert_row(db, officeace.connector_row("/py", ["/s.py"], {}))
    assert officeace.remove_rows(db) == 1
    con = sqlite3.connect(str(db))
    names = [r[0] for r in con.execute("SELECT name FROM mcp_connectors")]
    con.close()
    assert names == ["someone-else"], names


def test_officeace_never_creates_schema(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(str(db)).close()
    with pytest.raises(RuntimeError):
        officeace.upsert_row(db, officeace.connector_row("/py", ["/s.py"], {}))

# ── openclaw 的 size-drop 护栏兜底（2026-11-16 矩阵实锤：小配置 941→458 被 CLI 拒写）──
BLOCKED_CLI = '''#!/usr/bin/env python3
import sys
print("some unrelated failure text that may change between versions", file=sys.stderr)
sys.exit(1)
'''


def test_openclaw_unset_failure_with_entry_still_present_falls_back(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".openclaw").mkdir(parents=True)
    conf = home / ".openclaw" / "openclaw.json"
    conf.write_text(json.dumps({"mcp": {"servers": {"vod-devkit": {"command": "py", "args": ["/s.py"]},
                                                   "other": {"command": "x"}}},
                                "plugins": {"entries": {}}}, indent=2), encoding="utf-8")
    bindir = tmp_path / "bin"; bindir.mkdir()
    cli = bindir / "openclaw"; cli.write_text(BLOCKED_CLI, encoding="utf-8"); cli.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(conf))
    monkeypatch.setenv("HOME", str(home))
    assert openclaw.uninstall() is True
    data = json.loads(conf.read_text(encoding="utf-8"))
    assert "vod-devkit" not in data["mcp"]["servers"], "护栏兜底没摘掉条目"
    assert "other" in data["mcp"]["servers"], "外科摘除不许碰别人的 server"
    assert data["plugins"] == {"entries": {}}, "其它键必须原样保留"
    assert list(conf.parent.glob("openclaw.json.bak-vod-devkit")), "兜底前必须落备份"


def test_openclaw_surgical_remove_refuses_json5_with_comments(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".openclaw").mkdir(parents=True)
    conf = home / ".openclaw" / "openclaw.json"
    raw = '{\n  // 用户注释\n  "mcp": {"servers": {"vod-devkit": {}}}\n}\n'
    conf.write_text(raw, encoding="utf-8")
    bindir = tmp_path / "bin"; bindir.mkdir()
    cli = bindir / "openclaw"; cli.write_text(BLOCKED_CLI, encoding="utf-8"); cli.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(conf))
    assert openclaw.uninstall() is False
    assert conf.read_text(encoding="utf-8") == raw, "JSON5 带注释时不许动字节（宁可不摘）"


def test_audit_flags_openclaw_entry_without_ledger_row(tmp_path, monkeypatch):
    """P1 门禁：装了 openclaw（注册表有条目）但账本缺行 → 巡检必须红。"""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "scripts"))
    import host_matrix as hm
    cli = tmp_path / "openclaw"
    cli.write_text("#!/usr/bin/env python3\n"
                   "import json,sys\n"
                   "print(json.dumps({'servers': {'vod-devkit': {'launch': '/x/py /y/server.py',"
                   " 'tools': 10}}}))\n", encoding="utf-8")
    cli.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setenv("VOD_DEVKIT_MANIFEST", str(tmp_path / "none.json"))
    monkeypatch.setattr(hm, "_probe", lambda entry, ver: (True, "工具面 OK，版本一致"))
    verdict, msg = hm._audit_openclaw(tmp_path, "0.5.24")
    assert verdict == "DRIFT", msg
    assert "账本" in msg, msg


# ── OfficeAce：备份必须是一致性快照（sqlite backup API），回滚也走 sqlite ──────
def test_officeace_snapshot_is_sqlite_consistency_copy(tmp_path):
    db = _mk_officeace_db(tmp_path)
    officeace.upsert_row(db, officeace.connector_row("/py", ["/s.py"], {}))
    snap = officeace._snapshot(db)
    assert snap.exists() and snap.name.endswith(".bak"), snap
    assert snap.read_bytes()[:15] == b"SQLite format 3", "备份必须是 sqlite 库文件（backup API 产出）"
    # 快照内容与在线库一致（行数相同）
    con = sqlite3.connect(str(snap))
    n = con.execute("SELECT count(*) FROM mcp_connectors").fetchone()[0]
    con.close()
    assert n == 2, n


def test_officeace_restore_rolls_back_through_sqlite(tmp_path):
    db = _mk_officeace_db(tmp_path)
    officeace.upsert_row(db, officeace.connector_row("/py", ["/s.py"], {}))
    snap = officeace._snapshot(db)
    officeace.remove_rows(db)                     # 模拟"写坏了"
    assert officeace._readback(db) is None
    officeace._restore(snap, db)                  # 用快照写回在线库（不是覆盖文件）
    assert officeace._readback(db) is not None, "回滚后条目应恢复"
    con = sqlite3.connect(str(db))
    assert con.execute("SELECT count(*) FROM mcp_connectors").fetchone()[0] == 2
    con.close()


def test_officeace_snapshot_retention_prunes_old_backups(tmp_path):
    import os as _os, time as _time
    db = _mk_officeace_db(tmp_path)
    old = db.with_name(f"{db.name}.vod-devkit-20260101-000000-1.bak")
    old.write_bytes(b"x")
    stale = _time.time() - 30 * 86400
    _os.utime(old, (stale, stale))
    fresh = officeace._snapshot(db)
    assert fresh.exists()
    assert not old.exists(), "超过保留期的旧快照应被清理（不能每装一次堆一份）"
