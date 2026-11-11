"""发版状态对账（scripts/registry_reconcile.py）的行为锁。

为什么单独锁：tag↔registry 之间原本没有任何自动对账（v0.4.2 漏发实锤），
这份测试保证「仓内领先/registry 领先/两包不同版/契约失步/tag 缺失」五种形态
各判各的，且离线时明确 UNKNOWN 而不是绿。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import registry_reconcile as rr  # noqa: E402


def _local(v="0.5.1", dsh=None, contract=None):
    return {"vod-devkit": v, "dsh-vod-devkit": dsh or v, "contract": contract or v}


def test_published_and_tagged_is_ok():
    rep = rr.reconcile(_local("0.5.0"),
                       {"vod-devkit": "0.5.0", "dsh-vod-devkit": "0.5.0"},
                       {"v0.5.0": True})
    assert rep["status"] == "ok", rep


def test_repo_ahead_of_registry_is_ahead_not_drift():
    rep = rr.reconcile(_local("0.5.1"),
                       {"vod-devkit": "0.5.0", "dsh-vod-devkit": "0.5.0"},
                       {"v0.5.1": False})
    assert rep["status"] == "ahead", rep
    assert any("未发布改动" in f for f in rep["findings"])
    assert any("缺 tag" in f for f in rep["findings"])


def test_registry_ahead_of_repo_is_drift():
    rep = rr.reconcile(_local("0.5.0"),
                       {"vod-devkit": "0.5.2", "dsh-vod-devkit": "0.5.2"},
                       {"v0.5.0": True})
    assert rep["status"] == "drift", rep


def test_two_packages_must_match():
    rep = rr.reconcile(_local("0.5.0", dsh="0.4.4"),
                       {"vod-devkit": "0.5.0", "dsh-vod-devkit": "0.5.0"},
                       {"v0.5.0": True})
    assert rep["status"] == "drift"
    assert any("两包版本不一致" in f for f in rep["findings"])


def test_contract_version_must_match_package():
    rep = rr.reconcile(_local("0.5.0", contract="0.4.4"),
                       {"vod-devkit": "0.5.0", "dsh-vod-devkit": "0.5.0"},
                       {"v0.5.0": True})
    assert rep["status"] == "drift"
    assert any("契约版本失步" in f for f in rep["findings"])


def test_published_but_missing_tag_is_drift():
    rep = rr.reconcile(_local("0.5.0"),
                       {"vod-devkit": "0.5.0", "dsh-vod-devkit": "0.5.0"},
                       {"v0.5.0": False})
    assert rep["status"] == "drift", rep


def test_offline_registry_is_unknown_not_green():
    rep = rr.reconcile(_local("0.5.0"), {"vod-devkit": None, "dsh-vod-devkit": None})
    assert rep["status"] == "unknown", rep
    assert any("不算绿" in f for f in rep["findings"])


def test_npm_view_swallows_failures():
    class R:
        returncode = 1
        stdout = ""
    assert rr.npm_view("x", "version", runner=lambda *a, **k: R()) is None

    def boom(*a, **k):
        raise OSError("npm missing")
    assert rr.npm_view("x", "version", runner=boom) is None


def test_local_versions_reads_repo(tmp_path):
    (tmp_path / "dsh").mkdir()
    (tmp_path / "contract").mkdir()
    (tmp_path / "package.json").write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")
    (tmp_path / "dsh" / "package.json").write_text(json.dumps({"version": "1.2.3"}),
                                                   encoding="utf-8")
    (tmp_path / "contract" / "tools.schema.json").write_text(json.dumps({"version": "1.2.3"}),
                                                              encoding="utf-8")
    got = rr.local_versions(tmp_path)
    assert got == {"vod-devkit": "1.2.3", "dsh-vod-devkit": "1.2.3", "contract": "1.2.3"}


def test_version_compare_is_numeric_not_string():
    assert rr._cmp("0.5.10", "0.5.9") > 0
    assert rr._cmp("0.5.0-rc1", "0.5.0") == 0