"""S143 门禁的归因边界（S215）。

失效形态（2026-11-17 实锤）：pytest 全绿（863 passed / 0 failed），但并发在跑的真机 e2e 套件
把机器级 state（账本）改了 → S143 快照判"机器状态被改动"→ `session.exitstatus = 1`。
于是**全绿的测试轮拿到 RC=1**，release.sh 会据此挡住发版，而根因是另一条并发任务。
这与 S213（registry 超时当未发布）同一类：归因没做完。

口径：漂移先归因——有并发写入者（install / host_matrix / e2e_behavior）在跑 → 明确打印归因、
不判隔离缺失；没有并发写入者才是真隔离漏洞，保持 exit 1。
"""
from pathlib import Path

import conftest as cf


def _fake_proc(tmp: Path, entries: dict) -> Path:
    for pid, cmd in entries.items():
        d = tmp / pid
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes(cmd.replace(" ", "\0").encode())
    return tmp


def test_s215_detects_concurrent_writer(tmp_path):
    root = _fake_proc(tmp_path, {"101": "python3 bin/vod-devkit install --target all",
                                 "102": "bash -lc echo hi"})
    cmds = cf._concurrent_mutators(proc_root=root)
    assert len(cmds) == 1 and "install --target" in cmds[0], cmds


def test_s215_no_writer_means_isolation_leak(tmp_path):
    root = _fake_proc(tmp_path, {"101": "bash -lc echo hi"})
    assert cf._concurrent_mutators(proc_root=root) == []


def test_s215_markers_cover_e2e_and_matrix():
    for m in ("host_matrix.py", "e2e_behavior.py"):
        assert m in cf._MUTATOR_MARKERS
