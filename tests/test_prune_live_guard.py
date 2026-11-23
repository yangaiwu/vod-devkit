"""prune 不得删除活进程仍持有的载荷（0.5.45 事故回归）。

事故：配置/账本都指向新版本后，`prune --apply` 删掉了 0.5.45；三天前起的 MCP 子进程
仍按旧路径读 safety/policy.json，护栏 fail-closed → 每次工具调用都被 deny。
"""
import pytest

from vod_mcp import payload as P


@pytest.fixture()
def fake_proc(tmp_path, monkeypatch):
    root = tmp_path / "proc"
    root.mkdir()
    monkeypatch.setattr(P, "_PROC_ROOT", root)
    return root


def _pid(root, pid, args):
    d = root / str(pid)
    d.mkdir()
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")


def test_live_payload_processes_reads_cmdline(fake_proc, tmp_path):
    pay = tmp_path / "payloads" / "0.5.45"
    (pay / "vod_mcp").mkdir(parents=True)
    _pid(fake_proc, 123, ["/usr/bin/python3", str(pay / "vod_mcp" / "server.py")])
    _pid(fake_proc, 124, ["/usr/bin/python3", "-c", "print(1)"])  # 干扰项
    got = P.live_payload_processes()
    assert list(got) == [str(pay.resolve())]
    assert got[str(pay.resolve())] == [123]


def test_in_use_payloads_includes_live_process(fake_proc, tmp_path):
    pay = tmp_path / "payloads" / "0.5.45"
    (pay / "vod_mcp").mkdir(parents=True)
    _pid(fake_proc, 999, ["python", str(pay / "vod_mcp" / "server.py")])
    assert str(pay.resolve()) in P.in_use_payloads([])


def test_prune_skips_live_payload(fake_proc, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "payloads" / "0.5.45").mkdir(parents=True)
    (home / "payloads" / "0.5.45" / "payload.json").write_text("{}")
    (home / "payloads" / "0.5.44").mkdir(parents=True)
    (home / "payloads" / "0.5.44" / "payload.json").write_text("{}")
    monkeypatch.setattr(P, "payload_home", lambda: home)
    _pid(fake_proc, 555, ["python", str(home / "payloads" / "0.5.45" / "vod_mcp" / "server.py")])
    cands = [v for _, v, _ in P.prune_candidates([], keep=0)]
    assert "0.5.45" not in cands, f"活进程持有的载荷被列为可删：{cands}"
    assert "0.5.44" in cands


def test_doctor_warns_about_stale_live_payload(fake_proc, tmp_path, monkeypatch, capsys):
    from vodkit_cli import doctor as D
    from vod_mcp import payload as P2

    old = tmp_path / "payloads" / "0.5.45"
    (old / "vod_mcp").mkdir(parents=True)
    _pid(fake_proc, 777, ["python", str(old / "vod_mcp" / "server.py")])
    monkeypatch.setattr(P2, "payload_home", lambda: tmp_path)
    problems: list = []
    D._check_live_payloads(problems)
    out = capsys.readouterr().out
    assert "0.5.45" in out and "777" in out
    assert problems == [], "旧进程只报告，不得让 doctor 退出非零（避免门禁误红）"


def test_volatile_interpreter_markers():
    from vodkit_cli.common import volatile_interpreter as v

    assert v("/root/.hermes/cache/scratch/x/bin/python")
    assert v("/tmp/v/bin/python3")
    assert not v("/root/.vod-devkit/venv/bin/python")
    assert not v("/opt/vod-python/bin/python3.14")
    assert not v("/usr/bin/python3")


def test_doctor_reports_volatile_interpreter(tmp_path, monkeypatch, capsys):
    import json as _json

    from vodkit_cli import common as C
    from vodkit_cli import doctor as D

    cfg = tmp_path / "mcp.json"
    cfg.write_text(_json.dumps({"mcpServers": {"vod-devkit": {
        "command": "/root/.hermes/cache/scratch/vdk-venv/bin/python",
        "args": ["/root/.vod-devkit/payloads/0.5.56/vod_mcp/server.py"]}}}))

    class P:
        def exists(self):
            return True

        def read_text(self, encoding="utf-8"):
            return _json.dumps({"installs": [{"target": "hermes", "mcpConfig": str(cfg)}]})

    monkeypatch.setattr(C, "manifest_path", lambda: P())
    D._check_volatile_interpreter()
    out = capsys.readouterr().out
    assert "会被清理的目录" in out and "scratch" in out
