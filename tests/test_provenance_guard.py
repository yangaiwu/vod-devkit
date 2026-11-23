"""D-provenance-1 的三道闸（2026-11-24 实锤两次）：载荷↔commitSha 比对、源脏拒装、读回未自证 fail-closed。

背景：install 用**工作树内容**物化载荷，build-info 记的却是 HEAD；`verify()` 只比
payload.json 指纹（install 当场自洽重建）→「带着未提交补丁从 tag 重装」得到的内容带补丁、
标签写 tag 的载荷，doctor 全绿。这里锁住能抓住它的判据。
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vod_mcp import payload as payload_mod            # noqa: E402
from vodkit_cli import common                         # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    """一个只有 src/vod_mcp/tool.py 的真 git 仓。"""
    r = tmp_path / "repo"
    (r / "src" / "vod_mcp").mkdir(parents=True)
    (r / "src" / "vod_mcp" / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c1")
    return r


def _payload(tmp_path, sha: str, body: str) -> Path:
    p = tmp_path / "payloads" / "0.5.59"
    (p / "vod_mcp").mkdir(parents=True)
    (p / "vod_mcp" / "tool.py").write_text(body, encoding="utf-8")
    (p / "build-info.json").write_text(
        json.dumps({"version": "0.5.59", "commitSha": sha}), encoding="utf-8")
    return p


def test_provenance_ok_when_payload_matches_commit(repo, tmp_path):
    sha = _git(repo, "rev-parse", "HEAD")
    p = _payload(tmp_path, sha, "VALUE = 1\n")
    gap = payload_mod.provenance_gap(p, repo)
    assert gap["status"] == "ok", gap


def test_provenance_mismatch_when_payload_carries_uncommitted_patch(repo, tmp_path):
    """核心场景：载荷内容 = tag + 未提交补丁，build-info 却写 tag sha。"""
    sha = _git(repo, "rev-parse", "HEAD")
    p = _payload(tmp_path, sha, "VALUE = 1  # 未提交补丁\n")
    gap = payload_mod.provenance_gap(p, repo)
    assert gap["status"] == "mismatch", gap
    assert "vod_mcp/tool.py" in gap["files"], gap


def test_provenance_skips_without_git_or_commit(repo, tmp_path):
    p = _payload(tmp_path, "0" * 40, "VALUE = 1\n")
    assert payload_mod.provenance_gap(p, repo)["status"] == "skip"
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    assert payload_mod.provenance_gap(p, nogit)["status"] == "skip"


def test_provenance_reports_dirty_instead_of_mismatch_when_labelled(repo, tmp_path):
    """诚实标注的脏装（build-info 带 dirtySources）→ dirty，不判红；没标注才是谎报。"""
    sha = _git(repo, "rev-parse", "HEAD")
    p = _payload(tmp_path, sha, "VALUE = 1  # 补丁\n")
    bi = json.loads((p / "build-info.json").read_text())
    bi["dirtySources"] = ["M src/vod_mcp/tool.py"]
    (p / "build-info.json").write_text(json.dumps(bi), encoding="utf-8")
    gap = payload_mod.provenance_gap(p, repo)
    assert gap["status"] == "dirty", gap
    assert gap["files"] == ["M src/vod_mcp/tool.py"]


def test_source_dirty_paths_sees_src_change_and_ignores_build_artifacts(repo):
    assert common.source_dirty_paths(repo) == []
    (repo / "build-info.json").write_text("{}\n", encoding="utf-8")   # 构建产物，不算
    assert common.source_dirty_paths(repo) == []
    (repo / "src" / "vod_mcp" / "tool.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert any("src/vod_mcp/tool.py" in x for x in common.source_dirty_paths(repo))


def test_openclaw_readback_unverified_fails_closed(monkeypatch):
    """读回拿不到时必须非零退出——否则装机脚本里 stderr 警告被吞，自证形同虚设。"""
    from vod_mcp.host_adapters import openclaw

    monkeypatch.delenv("VOD_DEVKIT_ALLOW_UNVERIFIED", raising=False)
    monkeypatch.setattr(openclaw, "_cli", lambda: "/bin/true")
    monkeypatch.setattr(openclaw, "_definition",
                        lambda a, p: {"command": "npx", "args": ["-y"], "env": {}})
    monkeypatch.setattr(openclaw, "_show", lambda cli: None)          # 读回拿不到
    monkeypatch.setattr(openclaw.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    args = SimpleNamespace(java_api_base="http://x", mcp_url=None, mcp_token=None)
    with pytest.raises(SystemExit) as exc:
        openclaw.install(args, "core")
    assert exc.value.code == 2

    monkeypatch.setenv("VOD_DEVKIT_ALLOW_UNVERIFIED", "1")           # 逃生开关放行
    openclaw.install(args, "core")