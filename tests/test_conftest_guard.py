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


# ── S244：账本"内容本身合不合法"（前后快照管不到的那一半） ──────────────────
#
# 失效形态（2026-11-19 实锤）：仓根 install-manifest.json 的内容是某轮 pytest 写下的
# /tmp/pytest-of-root/pytest-218/... 落点，时间戳停在那一天。之后每次全量测试前后快照一致
# （没人再写它）→ S143 判绿 exit 0；但 doctor 读它会报一堆假 FAIL，把人引向错误的"重装"。
# 口径：不看本轮有没有写，只看内容指向哪里——指向 pytest/临时目录就是污染。
POLLUTED = {
    "version": "0.5.45",
    "target": "hermes",
    "mcpConfig": "/tmp/pytest-of-root/pytest-218/test_install_copies_all_skills0/.hermes/mcp/vod-devkit.json",
    "skillsDir": "/tmp/pytest-of-root/pytest-218/test_install_copies_all_skills0/.hermes/skills/devops/vod-devkit",
    "payloadDir": "/tmp/pytest-of-root/pytest-218/c0/.vod-devkit/payloads/0.5.45",
    "skillInstalls": [{"host": "hermes", "dir": "/tmp/pytest-of-root/pytest-218/c0/.hermes/skills/x"}],
    "installs": [{"host": "codex", "payloadDir": "/tmp/pytest-of-root/pytest-218/c0/.vod-devkit/payloads/0.5.45"}],
}


def _write_manifest(tmp_path: Path, doc) -> Path:
    import json
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "install-manifest.json").write_text(json.dumps(doc), "utf-8")
    pth = repo / "install-manifest.json"
    # 复用 conftest 的实现需要把 repo 指过来：直接按路径喂给它
    return pth


def test_s244_flags_polluted_manifest(tmp_path, monkeypatch):
    """落点指向 pytest 临时目录 → 必须报污染，且四个字段都被点名。"""
    import json
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "install-manifest.json").write_text(json.dumps(POLLUTED), "utf-8")
    monkeypatch.setattr(cf, "__file__", str(repo / "tests" / "conftest.py"))
    hits = cf._manifest_pollution()
    blob = "\n".join(hits)
    for field in ("mcpConfig", "skillsDir", "payloadDir", "skillInstalls[].dir",
                  "installs[].payloadDir"):
        assert field in blob, f"{field} 没被点名，实际：{hits}"


def test_s244_clean_manifest_is_not_flagged(tmp_path, monkeypatch):
    """真实落点（HOME 下）不该误报。"""
    import json
    import os
    repo = tmp_path / "repo"
    repo.mkdir()
    home = os.path.expanduser("~")
    (repo / "install-manifest.json").write_text(json.dumps({
        "version": "0.5.45",
        "mcpConfig": f"{home}/.hermes/mcp/vod-devkit.json",
        "skillsDir": f"{home}/.hermes/skills/devops/vod-devkit",
        "payloadDir": f"{home}/.vod-devkit/payloads/0.5.45",
        "skillInstalls": [{"host": "hermes", "dir": f"{home}/.hermes/skills/devops/vod-devkit"}],
        "installs": [],
    }), "utf-8")
    monkeypatch.setattr(cf, "__file__", str(repo / "tests" / "conftest.py"))
    assert cf._manifest_pollution() == []


def test_s244_missing_manifest_is_legal(tmp_path, monkeypatch):
    """没有账本 = 未安装，本来就合法，不该报污染。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(cf, "__file__", str(repo / "tests" / "conftest.py"))
    assert cf._manifest_pollution() == []


def test_s244_markers_cover_pytest_tmp():
    for m in ("/tmp/pytest-of-", "/pytest-of-"):
        assert m in cf._TMP_POLLUTION_MARKERS
