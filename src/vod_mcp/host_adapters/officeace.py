"""果办 OfficeAce 宿主适配（桌面端，Windows-only；本机未装、未真机验证）。

形态来源：huaweicloud-devkit 的 officeace-paths.ts / officeace-registry.ts（对表结论）：
- 配置根 `<InstallDir>/.office-claw`，InstallDir 依次来自
  ① `OFFICE_CLAW_CONFIG_ROOT`（显式，优先级最高）
  ② HKCU\\SOFTWARE\\OfficeAce\\OfficeAce 的 InstallDir（注册表）
  ③ `%LOCALAPPDATA%/Programs/OfficeAce`
- MCP 条目不是 JSON，而是 sqlite：`<InstallDir>/data/mcp-connectors.sqlite` 的
  `mcp_connectors` 表（type=custom / transport=stdio / name=vod-devkit /
  args_json / env_json / status=disconnected / seeded=0），工具表
  `mcp_connector_tools` 按 connector_id 关联。
- 技能落点 `<capabilities-dir>/skills`（`officeaceSkillsDir()`）。

风险与处置（用户口径：先自审伤害半径）：
- 写的是宿主自己的数据库 → **先整份备份**，再用事务写；写后读回校验，失败即回滚。
- 只认已经存在的 `mcp_connectors` 表，不建表、不改 schema（schema 不是我们的）。
- 非 Windows 平台直接拒绝（本机 Linux 无安装对象，不做"看着装了"的假动作）。
"""
import json
import os
import platform
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from vod_mcp import msgs
from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import server_env, server_entry

HOST = "officeace"
SUPPORTS_REMOTE = False
NAME = "vod-devkit"

_COLS = ("id", "owner_user_id", "type", "name", "normalized_name", "transport",
         "timeout_ms", "command", "args_json", "env_json", "enabled", "status",
         "created_at", "updated_at", "version", "seeded")


def _spec() -> dict:
    return host_specs.load(HOST)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _usable(root: Path) -> bool:
    """OfficeAce 配置根判据（对齐 isUsableOfficeaceRoot）：目录在 + 有证据。"""
    try:
        if not root.is_dir():
            return False
    except OSError:
        return False
    return any((root / x).exists() for x in ("capabilities.json", "skills")) or \
        (root.parent / "data" / "mcp-connectors.sqlite").exists()


def _registry_install_dir() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        r = subprocess.run(["reg", "query", r"HKCU\SOFTWARE\OfficeAce\OfficeAce",
                            "/v", "InstallDir"],
                           capture_output=True, text=True, timeout=5)
    except Exception:      # noqa: BLE001  探测失败按"没有"处理
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").splitlines():
        if "InstallDir" in line and "REG_SZ" in line:
            return line.split("REG_SZ", 1)[1].strip() or None
    return None


def capabilities_dir() -> Path | None:
    """配置根解析（env → 注册表 → LOCALAPPDATA），返回可用的 `<InstallDir>/.office-claw`。"""
    env = (os.environ.get("OFFICE_CLAW_CONFIG_ROOT") or "").strip()
    if env:
        root = Path(env).expanduser()
        return root if _usable(root) else None
    bases: list[Path] = []
    reg = _registry_install_dir()
    if reg:
        bases.append(Path(reg))
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        bases.append(Path(local) / "Programs" / "OfficeAce")
    for base in bases:
        root = base / ".office-claw"
        if _usable(root):
            return root
    return None


def sqlite_path(cap: Path) -> Path:
    return Path(cap).resolve().parent / "data" / "mcp-connectors.sqlite"


def skills_dir(args):
    cap = capabilities_dir()
    return (cap / "skills") if cap else Path(_spec()["skillsDir"])


# ── sqlite 行读写（纯函数，可在任意平台用临时库测） ──────────────────────────
def connector_row(command: str, args: list, env: dict) -> dict:
    now = _now()
    return {"id": str(uuid.uuid4()), "owner_user_id": None, "type": "custom",
            "name": NAME, "normalized_name": NAME, "transport": "stdio",
            "timeout_ms": 60000, "command": command,
            "args_json": json.dumps(args, ensure_ascii=False),
            "env_json": json.dumps(env, ensure_ascii=False),
            "enabled": 1, "status": "disconnected",
            "created_at": now, "updated_at": now, "version": 1, "seeded": 0}


def _tables(db: sqlite3.Connection) -> set:
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def upsert_row(db_path: Path, row: dict) -> str:
    """按 name 幂等写一行（已有则更新 command/args/env，保留 owner_user_id 等用户字段）。

    owner_user_id 没有可查询来源：默认写 NULL（不猜身份），只有显式
    `OFFICEACE_OWNER_USER_ID` 才写；不在库里找"第一个非空值"抄——多用户桌面机上那是把
    连接器挂到别人名下（2026-11-16 评审 P4）。已有行更新时保留原 owner_user_id（不动别人数据）。
    """
    db = sqlite3.connect(str(db_path))
    try:
        if "mcp_connectors" not in _tables(db):
            raise RuntimeError(f"{db_path} 没有 mcp_connectors 表（schema 不是我们的，拒绝建表）")
        cur = db.execute("SELECT id, owner_user_id FROM mcp_connectors WHERE name = ?",
                         (NAME,)).fetchone()
        if cur:
            db.execute(
                "UPDATE mcp_connectors SET command=?1, args_json=?2, env_json=?3, "
                "updated_at=?4, status=?5, enabled=1 WHERE id=?6",
                (row["command"], row["args_json"], row["env_json"], row["updated_at"],
                 "disconnected", cur[0]))
            action = "updated"
        else:
            # 身份只能来自显式来源：OFFICEACE_OWNER_USER_ID。**绝不从库里抄别人的**
            # （2026-11-16 评审 P4：多用户桌面机上照抄 = 把连接器挂到别人名下）。
            owner = (os.environ.get("OFFICEACE_OWNER_USER_ID") or "").strip() or None
            row = dict(row, owner_user_id=owner)
            cols = ", ".join(_COLS)
            marks = ", ".join("?" for _ in _COLS)
            db.execute(f"INSERT INTO mcp_connectors ({cols}) VALUES ({marks})",
                       tuple(row[c] for c in _COLS))
            action = "created"
        db.commit()
        return action
    finally:
        db.close()


def remove_rows(db_path: Path) -> int:
    """只摘 name=vod-devkit 的连接器（工具表按 connector_id 级联清）。"""
    db = sqlite3.connect(str(db_path))
    try:
        tabs = _tables(db)
        if "mcp_connectors" not in tabs:
            return 0
        if "mcp_connector_tools" in tabs:
            try:
                db.execute("DELETE FROM mcp_connector_tools WHERE connector_id IN "
                           "(SELECT id FROM mcp_connectors WHERE name = ?)", (NAME,))
            except sqlite3.Error:
                pass          # 最小安装可能缺该表；连接器行仍要删
        n = db.execute("DELETE FROM mcp_connectors WHERE name = ?", (NAME,)).rowcount
        db.commit()
        return max(n, 0)
    finally:
        db.close()


def _snapshot(db_path: Path) -> Path:
    """用 sqlite 自己的 backup API 做一致性快照（不许 copyfile）。

    2026-11-16 评审：宿主（桌面端）可能正开着这个库，WAL 里还有未落盘事务——
    文件复制拿到的是残缺/过期副本，回滚时等于拿坏副本盖掉宿主数据库。
    backup() 走 sqlite 的在线备份协议，拿到的是事务一致快照；备份名带时分秒+pid，
    并清理同前缀的老备份（默认保留 7 天，避免每装一次堆一份）。
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.name}.vod-devkit-{stamp}-{os.getpid()}.bak")
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    _prune_snapshots(db_path)
    return dest


def _prune_snapshots(db_path: Path, days: int = 7) -> None:
    cutoff = datetime.now().timestamp() - days * 86400
    for old in db_path.parent.glob(f"{db_path.name}.vod-devkit-*.bak"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def _restore(snapshot: Path, db_path: Path) -> None:
    """回滚也走 sqlite：把快照**写回**在线库（而不是覆盖文件），WAL/-shm 由 sqlite 处理。"""
    snap = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
    try:
        live = sqlite3.connect(str(db_path))
        try:
            snap.backup(live)
        finally:
            live.close()
    finally:
        snap.close()


def _readback(db_path: Path) -> tuple | None:
    db = sqlite3.connect(str(db_path))
    try:
        return db.execute("SELECT command, args_json FROM mcp_connectors WHERE name = ?",
                          (NAME,)).fetchone()
    finally:
        db.close()


# ── 适配器契约 ────────────────────────────────────────────────────────────
def _require_windows():
    if platform.system() != "Windows":
        print("[vod-devkit] 拒绝安装 officeace：它是桌面端（Windows 10/11、macOS 13+、"
              "HarmonyOS），本平台没有安装对象；也不做“看着装了”的假动作。"
              "要接入请在目标 Windows 机上执行。", file=sys.stderr)
        sys.exit(2)


def install(args, packs):
    _require_windows()
    cap = capabilities_dir()
    if not cap:
        print("[vod-devkit] 未找到可用的 OfficeAce 配置根（.office-claw）；"
              "请先安装并启动一次 OfficeAce，或设 OFFICE_CLAW_CONFIG_ROOT", file=sys.stderr)
        sys.exit(2)
    db_path = sqlite_path(cap)
    if not db_path.exists():
        print(f"[vod-devkit] OfficeAce 连接器库不存在：{db_path}（先启动一次 OfficeAce）",
              file=sys.stderr)
        sys.exit(2)
    backup = _snapshot(db_path)
    command: str = sys.executable
    entry_args: list = [server_entry()]
    entry_env: dict = dict(server_env(args, packs))
    row = connector_row(command, entry_args, entry_env)
    try:
        action = upsert_row(db_path, row)
        got = _readback(db_path)
        if not got or got[0] != command or json.loads(got[1]) != entry_args:
            raise RuntimeError(f"写后读回不一致：{got}")
    except Exception as e:      # noqa: BLE001  任何失败都回滚到快照，绝不半写
        _restore(backup, db_path)
        print(f"[vod-devkit] OfficeAce 写入失败，已用 sqlite 快照回滚（{backup.name}）：{e}",
              file=sys.stderr)
        sys.exit(2)
    print(f"已{'更新' if action == 'updated' else '写入'} OfficeAce 连接器："
          f"{db_path}（name={NAME}，备份 {backup.name}；{msgs.effective_unit('OfficeAce')}）")
    return Path(db_path)


def install_remote(args, url, token):
    print("[vod-devkit] OfficeAce 本轮只支持本地 stdio 形态（未真机验证远程面）",
          file=sys.stderr)
    sys.exit(2)


def uninstall() -> bool:
    cap = capabilities_dir()
    if not cap:
        print("skip（未找到 OfficeAce 配置根）：不做任何改动", file=sys.stderr)
        return False
    db_path = sqlite_path(cap)
    if not db_path.exists():
        print(f"skip（连接器库不存在）：{db_path}", file=sys.stderr)
        return False
    backup = _snapshot(db_path)
    n = remove_rows(db_path)
    print(f"removed OfficeAce connector rows: {n}（快照 {backup.name}）")
    return n > 0