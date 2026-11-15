"""双副本一致性门禁（scripts/verify_copies.py）的行为锁。

历史事故（v0.5.8）：sync 把 contract 版本写进插件副本，提交清单漏了它，
所有基于工作区的 diff 检查全绿，而提交树里副本是旧版 → tarball ≠ tag。
根治=v0.5.9 起副本零提交（生成物），门禁两条：内容一致 + 副本不在 git 里（S105）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verify_copies as vc  # noqa: E402


def _mk(base: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return base


def test_identical_trees_have_no_problems(tmp_path):
    a = _mk(tmp_path / "src", {"m.py": "x = 1\n", "sub/n.py": "y = 2\n"})
    b = _mk(tmp_path / "dst", {"m.py": "x = 1\n", "sub/n.py": "y = 2\n"})
    assert vc.compare_trees(a, b) == []


def test_content_diff_is_reported(tmp_path):
    a = _mk(tmp_path / "src", {"m.py": "x = 1\n"})
    b = _mk(tmp_path / "dst", {"m.py": "x = 2\n"})
    problems = vc.compare_trees(a, b)
    assert problems and "内容不同" in problems[0]


def test_missing_or_extra_files_are_reported(tmp_path):
    a = _mk(tmp_path / "src", {"m.py": "x\n", "only_src.py": "s\n"})
    b = _mk(tmp_path / "dst", {"m.py": "x\n", "only_dst.py": "d\n"})
    problems = vc.compare_trees(a, b)
    assert any("插件副本缺文件：only_src.py" in p for p in problems)
    assert any("插件副本多文件：only_dst.py" in p for p in problems)


def test_missing_destination_is_reported(tmp_path):
    a = _mk(tmp_path / "src", {"m.py": "x\n"})
    assert any("不存在" in p for p in vc.compare_trees(a, tmp_path / "nope"))


def test_runtime_state_and_caches_are_ignored(tmp_path):
    a = _mk(tmp_path / "src", {"m.py": "x\n", "runtime.json": "{}\n"})
    b = _mk(tmp_path / "dst", {"m.py": "x\n", "__pycache__/m.pyc": "junk", "old.log": "l"})
    assert vc.compare_trees(a, b) == [], "runtime.json/__pycache__/*.log 不是副本内容"


def test_tracked_copy_is_reported(tmp_path):
    """生成物零提交：副本一旦进 git 就又有两份真值 → 必须判红。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel in ("vod_mcp", "contract"):
        _mk(repo / rel, {"f.txt": "same\n"})
        _mk(repo / "plugins/vod-devkit" / rel, {"f.txt": "same\n"})
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)  # 故意把副本也加进去
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=repo, check=True)
    assert vc.compare_trees(repo / "vod_mcp", repo / "plugins/vod-devkit/vod_mcp") == []
    problems = vc.check(repo, git_check=True)
    assert any("副本被 git 跟踪" in p for p in problems), problems


def test_generated_untracked_copies_pass(tmp_path):
    """正常态：源在 git 里，副本在磁盘上但没被跟踪（.gitignore）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel in ("vod_mcp", "skills", "contract", "safety"):
        _mk(repo / rel, {"f.txt": "same\n"})
        _mk(repo / "plugins/vod-devkit" / rel, {"f.txt": "same\n"})
    (repo / ".gitignore").write_text("plugins/vod-devkit/vod_mcp/\n"
                                     "plugins/vod-devkit/skills/\n"
                                     "plugins/vod-devkit/contract/\n"
                                     "plugins/vod-devkit/safety/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", ".gitignore", "vod_mcp", "skills", "contract", "safety"],
                   cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=repo, check=True)
    assert vc.check(repo, git_check=True) == []