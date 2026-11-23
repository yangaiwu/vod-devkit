"""secret_scan 门禁回归锁：模式命中 + 行内豁免 + 门禁接入。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import secret_scan  # noqa: E402


def _hit(patterns, line):
    import re
    return any(re.search(p, line) for p, _ in patterns)


_SAMPLE_URL = "https://oauth2:vpTOKEN1234567890abcdef1234@gitcode.com/x.git"  # secret-scan:allow 正例载体
_SAMPLE_KEY = "-----BEGIN RSA PRIVATE KEY-----"  # secret-scan:allow 正例载体
_SAMPLE_BEARER = "Authorization: Bearer abcdef0123456789abcdef0123456789ab"  # secret-scan:allow 正例载体


def test_url_token_detected():
    assert _hit(secret_scan.SECRET_PATTERNS, _SAMPLE_URL)


def test_query_token_detected():
    sample = "https://gitcode.com/x/y?access_token=abcdefgh1234567890abc"  # secret-scan:allow 正例载体
    assert _hit(secret_scan.SECRET_PATTERNS, sample)


def test_private_key_detected():
    assert _hit(secret_scan.SECRET_PATTERNS, _SAMPLE_KEY)


def test_bearer_token_detected():
    assert _hit(secret_scan.SECRET_PATTERNS, _SAMPLE_BEARER)


def test_benign_line_not_hit():
    assert not _hit(secret_scan.SECRET_PATTERNS, "export VOD_JAVA_API_BASE=http://127.0.0.1:18080")


def test_allow_marker_logic_exists():
    src = Path(secret_scan.__file__).read_text(encoding="utf-8")
    assert "secret-scan:allow" in src


def test_pre_push_hook_wires_scanner():
    hook = Path(__file__).resolve().parent.parent / ".githooks" / "pre-push"
    assert "secret_scan.py" in hook.read_text(encoding="utf-8")


# ── ARCH-CFG-04：覆盖边界（扫描面 / 降级 / 模式缺口） ──────────────────────
#
# 旧实现三个洞：①只扫 git ls-files，而 plugins/ 副本零提交、天然在 tracked 之外，
# 里面藏明文 key 不会被发现；②git 不存在时 FileNotFoundError 直接崩；③非 git 目录
# 拿到空输出 → 循环零次 → 打印 OK exit 0（静默通过，比崩更危险）。
# 下面每条都对应当前实现的真实行为，不是复述代码。


def test_scans_generated_copies_too():
    """生成副本（plugins/、assets/）必须在扫描面内，且相当一部分原先扫不到。"""
    root = Path(secret_scan.__file__).resolve().parent.parent  # type: ignore[arg-type]
    extra = secret_scan.walk_extra(root)
    assert extra, "生成副本扫描面为空——ARCH-CFG-04 回退了"
    assert any(p.startswith("plugins") for p in extra), "plugins/ 副本没进扫描面"
    # 反面证据：这些文件确实不在 git ls-files 里（正是它们原先的盲区）
    tracked = set(secret_scan.subprocess.run(["git", "ls-files"], cwd=root,
                                             capture_output=True, text=True).stdout.split())
    blind = [p for p in extra if p not in tracked]
    assert blind, "生成副本全部是 tracked——那这条扫描面扩展就没意义了"


def test_generated_copy_secret_is_caught(tmp_path):
    """在副本形态的路径上放假 key，必须命中（证明扩展的不只是目录名）。

    假 key 在**运行时拼**出来：写死字面量会让 secret_scan 把本文件自己判红
    （那正是它该做的事），但用 `secret-scan:allow` 豁免又会让这条用例失去意义。
    """
    fake = "JAVA_KEY=" + "abcdefghij" + "1234567890" + "abcdefghij"
    f = tmp_path / "SKILL.md"
    f.write_text(fake + "\n", encoding="utf-8")
    hits, _ = secret_scan.scan_paths(tmp_path, ["SKILL.md"])
    assert hits, "生成副本里的明文 java_key 没被扫到"
    assert "java_key" in hits[0]


def test_git_unavailable_degrades_without_crash(monkeypatch):
    """git 不存在 → 降级返回原因，不许抛异常（旧实现 FileNotFoundError）。"""

    def boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(secret_scan.subprocess, "run", boom)
    files, why = secret_scan.tracked_files(Path("/tmp"))
    assert files == [] and why == "git 不可用"


def test_non_git_dir_is_not_silent_pass(monkeypatch):
    """非 git 目录 → 必须给出降级原因，不许「zero files 但 OK」。"""
    files, why = secret_scan.tracked_files(Path("/tmp"))
    assert files == []
    assert why, "非 git 目录没报降级原因——旧实现会静默打印 OK exit 0"


def test_empty_scan_surface_fails_closed(tmp_path, monkeypatch):
    """扫描面为空时 main 必须 exit 1（fail-closed），不能绿着通过。"""
    monkeypatch.setattr(secret_scan, "tracked_files", lambda root: ([], "git 不可用"))
    monkeypatch.setattr(secret_scan, "walk_extra", lambda root: [])
    monkeypatch.setattr(secret_scan, "__file__", str(tmp_path / "scripts" / "secret_scan.py"))
    assert secret_scan.main() == 1, "扫描面为空却返回成功——旧实现正是这样静默通过的"
