"""secret_scan 门禁回归锁：模式命中 + 行内豁免 + 门禁接入。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import secret_scan  # noqa: E402


def _hit(patterns, line):
    import re
    return any(re.search(p, line) for p, _ in patterns)


def test_url_token_detected():
    assert _hit(secret_scan.SECRET_PATTERNS  # secret-scan:allow 正例载体, "https://oauth2:vpTOKEN1234567890abcdef1234@gitcode.com/x.git")


def test_private_key_detected():
    assert _hit(secret_scan.SECRET_PATTERNS  # secret-scan:allow 正例载体, "-----BEGIN RSA PRIVATE KEY-----")


def test_bearer_token_detected():
    assert _hit(secret_scan.SECRET_PATTERNS  # secret-scan:allow 正例载体, "Authorization: Bearer abcdef0123456789abcdef0123456789ab")


def test_benign_line_not_hit():
    assert not _hit(secret_scan.SECRET_PATTERNS, "export VOD_JAVA_API_BASE=http://127.0.0.1:18080")


def test_allow_marker_logic_exists():
    src = Path(secret_scan.__file__).read_text(encoding="utf-8")
    assert "secret-scan:allow" in src


def test_pre_push_hook_wires_scanner():
    hook = Path(__file__).resolve().parent.parent / ".githooks" / "pre-push"
    assert "secret_scan.py" in hook.read_text(encoding="utf-8")
