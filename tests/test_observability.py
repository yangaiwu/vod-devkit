"""ARCH-ERR-05 可观测性回归锁：结构化日志 + 可配置落点 + 请求级关联。

旧实现四个洞（2026-11-19 走查）：
  ① `_log(line, path="/tmp/vod_mcp_server.log")` 默认参数固定路径，容器/沙箱不可写即静默丢失；
  ② 超 1MB 时 read→write 全量重写**无锁**，多进程并发互相覆盖；
  ③ `transport_remote._Handler.log_message` 整体 `pass`，远程面访问面全静默；
  ④ 日志是自由文本，无级别、无 tool/耗时/请求 id ⇒ 一次调用在日志里串不起来。

下面每条都对应当前实现的真实行为，不是复述代码。
"""
from __future__ import annotations

import json
from pathlib import Path

from vod_mcp import runtime_state as rt


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ── 结构化 ─────────────────────────────────────────────────────────────────
def test_log_lines_are_structured_and_carry_tool_context(tmp_path):
    """每行是 JSON 对象，带 ts/level/msg，调用方可附 tool/duration_ms/code。"""
    log = tmp_path / "s.log"
    rt._log("工具调用", tool="vod_submit_voices", duration_ms=42.5, code=-32005,
            event="tool_call", path=str(log))
    rec = _lines(log)[0]
    assert set(rec) >= {"ts", "level", "msg"}, rec
    assert rec["level"] == "info"
    assert rec["tool"] == "vod_submit_voices"
    assert rec["duration_ms"] == 42.5
    assert rec["code"] == -32005


def test_level_is_split_out_of_legacy_warn_prefix(tmp_path):
    """既有 `"warn xxx"` 文案习惯 → level=warn 且 msg 去前缀（按级别过滤才有效）。"""
    log = tmp_path / "s.log"
    rt._log("warn pending: 队列写入失败", path=str(log))
    rec = _lines(log)[0]
    assert rec["level"] == "warn"
    assert rec["msg"] == "pending: 队列写入失败"


def test_warn_helper_tags_level(tmp_path):
    """`_warn()` 走同一出口但自带 level=warn。"""
    log = tmp_path / "s.log"
    rt._warn("补交失败", tool="vod_draft_feedback", path=str(log))
    rec = _lines(log)[0]
    assert rec["level"] == "warn" and rec["tool"] == "vod_draft_feedback"


# ── 落点可配置 ─────────────────────────────────────────────────────────────
def test_log_path_is_configurable_and_creates_private_dir(tmp_path, monkeypatch):
    """VOD_DEVKIT_LOG 优先；父目录不存在会自动建出来（旧实现不建，直接抛 OSError）。"""
    target = tmp_path / "deep" / "nested" / "server.log"
    monkeypatch.setenv("VOD_DEVKIT_LOG", str(target))
    assert rt._log_path() == str(target)
    rt._log("写入深层目录")
    assert target.is_file(), "落点父目录没被创建"
    assert _lines(target)[0]["msg"] == "写入深层目录"


def test_default_log_path_has_no_machine_state_side_effect(monkeypatch):
    """默认落点**不许**在机器级 state 下建目录。

    first-cut 曾默认 machine_state_home()/logs/，任何一次 _log() 都建目录 ⇒ 未隔离的
    子进程污染真机 state，S143 判漂移（实测红过一次）。日志是旁路，不该有这种副作用。
    """
    monkeypatch.delenv("VOD_DEVKIT_LOG", raising=False)
    p = rt._log_path()
    assert "machine_state" not in p and ".vod-devkit" not in p, p
    import tempfile
    assert p.startswith(tempfile.gettempdir()), p


# ── 轮转与并发 ─────────────────────────────────────────────────────────────
def test_rotation_keeps_tail_and_is_lockable(tmp_path):
    """超 1MB 轮转保留尾部，且轮转在锁内做（多进程不会互相覆盖）。

    预填内容是**合法 JSONL**（真实形态），且验证轮转后文件仍是可解析的 JSONL——
    按字节硬截会切碎一行留下半截，tail 从换行边界起算才不会破坏格式。
    """
    log = tmp_path / "s.log"
    line = json.dumps({"ts": "2026-01-01T00:00:00", "level": "info", "msg": "filler"})
    log.write_text((line + "\n") * 20000, encoding="utf-8")   # ~1.3MB
    assert log.stat().st_size > 1024 * 1024
    rt._log("after-rotation", path=str(log))
    assert (tmp_path / "s.log.old").exists(), "轮转没留 .old"
    recs = _lines(log)                                        # 半截行会让这里抛错
    assert recs[-1]["msg"] == "after-rotation"
    assert all(len(r) >= 3 for r in recs), "轮转后留了半截 JSON"


def test_concurrent_writers_do_not_lose_lines(tmp_path):
    """多进程并发写，行数不丢（旧实现轮转无锁会覆盖）。"""
    import subprocess
    import sys
    log = tmp_path / "s.log"
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from vod_mcp import runtime_state as rt\n"
        "for i in range(25): rt._log(f'line-{i}', path=%r)\n"
        % (str(Path(__file__).resolve().parent.parent / "src"), str(log))
    )
    procs = [subprocess.Popen([sys.executable, "-c", script]) for _ in range(4)]
    for p in procs:
        p.wait(timeout=60)
    assert len(_lines(log)) == 100, f"丢了行：{len(_lines(log))}/100"


def test_log_failure_falls_back_to_stderr(tmp_path, capfd):
    """落点不可写 ⇒ stderr 兜底一行，不许静默消失。"""
    bad = "/dev/null/not-a-dir/s.log"
    rt._log("hello", path=bad)
    assert "hello" in capfd.readouterr().err


# ── 远程面接入 ─────────────────────────────────────────────────────────────
def test_remote_access_log_is_no_longer_silent():
    """`_Handler.log_message` 不许是 `pass`（旧实现访问面全静默）。"""
    src = (Path(__file__).resolve().parent.parent
           / "src" / "vod_mcp" / "transport_remote.py").read_text(encoding="utf-8")
    body = src.split("def log_message", 1)[1].split("\n    def ", 1)[0]
    assert "http_access" in body, "log_message 没接进结构化出口"


def test_remote_and_stdio_share_one_outlet():
    """两面请求级日志走同一出口、同一字段集（tool / duration_ms / req_id）。"""
    root = Path(__file__).resolve().parent.parent / "src" / "vod_mcp"
    remote = (root / "transport_remote.py").read_text(encoding="utf-8")
    server = (root / "server.py").read_text(encoding="utf-8")
    for name, src in (("remote", remote), ("stdio", server)):
        for field in ("duration_ms", "req_id", "tool="):
            assert field in src, f"{name} 面缺请求级字段 {field}"