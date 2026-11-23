"""ARCH-CFG-01：pending-feedback.jsonl 存用户原话，权限必须 0600（2026-11-19 走查 P0）。

背景（台账 ARCH-CFG-01，实测复现）：`append_entry` 只 `open("a")`、`save_entries` 只
`tmp+os.replace`（见 `pending.py`），**全仓 chmod 清单里没有 pending** ⇒ 默认 umask 下
文件是 0644 ⇒ 同机其他用户可读真实用户抱怨原文。对照：同目录 `runtime.json`（含 key）
是 0600 —— 更敏感的内容反而放开。

口径（与 `runtime_state._verify_perms` 同源）：**验效果不验动作**——chmod 之后 stat 回验；
WSL/drvfs 会静默忽略 chmod，那条路只告警不阻断（不许因为收紧不了就让采集失败）。
"""
import os
import stat

import pytest

from vod_mcp import pending


@pytest.fixture()
def wide_umask():
    """把 umask 调成 022（多数 Linux 默认），确保新建文件按默认 0644 ——否则用例是假绿。"""
    old = os.umask(0o022)
    yield 0o022
    os.umask(old)


def _mode(p) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


def test_append_entry_creates_private_file(tmp_path, wide_umask):
    """新建（umask 022）必须是 0600，不是 0644。"""
    p = tmp_path / "pending-feedback.jsonl"
    pending.append_entry(p, pending.make_entry("用户原话", ["x"], "2026-11-19T00:00:00", "t"))
    assert _mode(p) == 0o600, f"append_entry 后权限 {oct(_mode(p))}，命期待 0o600"


def test_append_entry_keeps_private_on_second_write(tmp_path, wide_umask):
    """第二条追加不许把权限放宽。"""
    p = tmp_path / "pending-feedback.jsonl"
    pending.append_entry(p, pending.make_entry("a", None, "2026-11-19T00:00:00", "t"))
    pending.append_entry(p, pending.make_entry("b", None, "2026-11-19T00:00:01", "t"))
    assert _mode(p) == 0o600, oct(_mode(p))


def test_save_entries_is_private(tmp_path, wide_umask):
    """flush 重写（tmp + os.replace）后仍 0600 —— os.replace 用的是新 inode 的权限。"""
    p = tmp_path / "pending-feedback.jsonl"
    pending.save_entries(p, [pending.make_entry("a", None, "2026-11-19T00:00:00", "t")])
    assert _mode(p) == 0o600, oct(_mode(p))


def test_existing_wide_file_is_tightened_on_next_write(tmp_path, wide_umask):
    """历史 0644 文件：下一次写入时收紧（只收紧、不放宽）。"""
    p = tmp_path / "pending-feedback.jsonl"
    p.write_text('{"content": "旧的原话", "status": "pending"}\n', encoding="utf-8")
    os.chmod(p, 0o644)
    assert _mode(p) == 0o644
    pending.append_entry(p, pending.make_entry("新的一条", None, "2026-11-19T00:00:00", "t"))
    assert _mode(p) == 0o600, f"旧宽权限未被收紧：{oct(_mode(p))}"


def test_already_private_file_is_not_loosened(tmp_path):
    """本来就是 0600 的文件不许被改成更宽（只收紧方向）。"""
    p = tmp_path / "pending-feedback.jsonl"
    p.write_text("", encoding="utf-8")
    os.chmod(p, 0o600)
    pending.append_entry(p, pending.make_entry("a", None, "2026-11-19T00:00:00", "t"))
    assert _mode(p) == 0o600, oct(_mode(p))


def test_chmod_ignored_warns_but_does_not_raise(tmp_path, wide_umask, monkeypatch):
    """WSL/drvfs 忽略 chmod：只告警，不许抛（否则采集在那种环境上整条挂掉）。"""
    warned = []
    monkeypatch.setattr(pending, "_warn", lambda m: warned.append(m))
    real_chmod = os.chmod
    real_open = os.open

    def _ignore_chmod(path, mode, *a, **kw):
        if str(path).endswith("pending-feedback.jsonl"):
            return None                      # 模拟"chmod 静默无效"
        return real_chmod(path, mode, *a, **kw)

    def _wide_open(path, flags, mode=0o777, *a, **kw):
        # 模拟"文件系统不认 mode 参数"：新文件照样落到 0644（WSL / vfat 的典型行为）
        if str(path).endswith("pending-feedback.jsonl") and (flags & os.O_CREAT):
            return real_open(path, flags, 0o644)
        return real_open(path, flags, mode, *a, **kw)

    monkeypatch.setattr(os, "chmod", _ignore_chmod)
    monkeypatch.setattr(os, "open", _wide_open)
    p = tmp_path / "pending-feedback.jsonl"
    pending.append_entry(p, pending.make_entry("a", None, "2026-11-19T00:00:00", "t"))  # 不许抛
    assert warned, "chmod 未生效时必须留一条告警（否则权限窗口无声打开）"
    assert any("pending" in w or "权限" in w for w in warned), warned