"""OpenClaw / OfficeAce 两个新宿主的形态与破坏性边界（2026-11-16）。

为什么门禁只锁形态、不锁"真机连通"：
- OpenClaw 侧已真机闭环（探测/会话/提交都验过，见 README 与 host.json notes），
  但 CI 机器不一定装 openclaw，所以用例用**假 CLI** 锁"只经 CLI 写、绝不直改 JSON5"；
- OfficeAce 是桌面端（Windows-only），本机无安装对象，只能锁 sqlite 行域逻辑
  与"非 Windows 拒绝"，不伪造真机断言。
"""
import json
import sqlite3
import sys
import types
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
    """openclaw.json 是 JSON5：adapter 里不许出现对它 write_text/merge 的路径。"""
    src = (ROOT / "src" / "vod_mcp" / "host_adapters" / "openclaw.py").read_text(encoding="utf-8")
    for bad in ("write_text(", "merge_mcp_servers(", "atomic_write_text("):
        assert bad not in src, f"openclaw 适配器出现了直改配置的写法：{bad}"
    assert "mcp\", \"add" in src or '"mcp", "add"' in src
    assert '"mcp", "unset"' in src


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
    assert rows[0][1] == "u-42", "owner_user_id 必须沿用已有行，不许自己编"
    assert json.loads(rows[0][2]) == {"A": "2"}


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