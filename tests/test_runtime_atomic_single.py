"""ARCH-CFG-03：原子写必须单源（2026-11-19 走查 P1）。

现状三套并存：
1. `paths.atomic_write_text` —— 同目录 tmp + fsync + chmod + symlink 解析 + 只读保护；
2. `runtime_state._write_cfg_unlocked` —— `write_text`（**无 fsync**）+ chmod + replace，
   无 symlink / 只读保护。掉电可留 0 字节 runtime.json ⇒ key/账本/设备锚点一起丢；
3. `pending.save_entries` —— tmp + fsync + replace，**无 chmod**（见 test_pending_perms）。

`runtime.json` 是每次提交都写的热路径，也是"同版本号两份代码"审计链的一环。
本文件锁两件事：仓内只有一个 `os.replace(` 写盘点位；runtime.json 走那条路时
fsync / symlink / 只读保护三样都在。
"""
import ast
import os
import pathlib

import pytest

from vod_mcp import runtime_state as rt

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _os_replace_call_sites() -> list:
    """src/ 下所有 `os.replace(...)` 调用点（file:line）。"""
    hits = []
    for p in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "replace"
                    and isinstance(n.func.value, ast.Attribute)
                    and n.func.value.attr == "os"):
                hits.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    return hits


def test_single_atomic_writer():
    """`os.replace(` 只允许出现在 paths.atomic_write_text 里（其余实现必须已改为调用它）。"""
    hits = _os_replace_call_sites()
    allowed = {"src/vod_mcp/paths.py"}
    offenders = [h for h in hits if h.rsplit(":", 1)[0] not in allowed]
    assert not offenders, f"仍有私有原子写实现：{offenders}（改调 paths.atomic_write_text）"


def test_runtime_write_is_fsynced(tmp_path, monkeypatch):
    """runtime.json 写入必须 fsync（掉电不许留 0 字节）。"""
    calls = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    p = tmp_path / "runtime.json"
    rt._write_cfg_unlocked(p, {"java_key": "k"})
    assert calls, "runtime.json 写入没有 fsync —— 掉电可留半截文件"
    assert p.exists()


def test_runtime_write_follows_symlink(tmp_path):
    """软链目标：不许被 os.replace 换成普通文件（S180 语义，paths 那套已有）。"""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    target = real_dir / "runtime.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "runtime.json"
    link.symlink_to(target)
    rt._write_cfg_unlocked(link, {"java_key": "k"})
    assert link.is_symlink(), "软链被 replace 成了普通文件（应解析到真实目标再写）"
    assert "java_key" in target.read_text(encoding="utf-8")


def test_runtime_write_refuses_readonly_target(tmp_path):
    """用户 chmod 444 = 要保护：不许静默覆盖（paths.py:240 的既有语义）。"""
    p = tmp_path / "runtime.json"
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o444)
    with pytest.raises(PermissionError):
        rt._write_cfg_unlocked(p, {"java_key": "k"})


def test_runtime_write_is_private(tmp_path):
    """0600 不许退化（既有行为，改动时必须保住）。"""
    import stat
    p = tmp_path / "runtime.json"
    rt._write_cfg_unlocked(p, {"java_key": "k"})
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600