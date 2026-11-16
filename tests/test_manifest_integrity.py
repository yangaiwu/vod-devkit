"""P4（2026-11-16 评审）：账本写入必须原子，且坏账本不许被空账本覆盖。

两个缺陷串起来的成因链（评审复现）：`_read_manifest()` 解析失败静默返回 `{}`，
下一次 `install` 只写自己那一行 → 其它 9 行账本消失 → doctor 只看到一台、
uninstall 摘不到、prune 的"在用"集合也空。

定式（与 runtime.json 同一口径）：
  · 写：tmp（同目录）→ fsync → chmod → os.replace，中断/磁盘满不留半截 JSON；
  · 读：exists 且解析失败 → `ManifestCorrupt`（写路径必须 strict），只读诊断面
    退回空账本但要让用户看见"这份文件坏了"，不许静默；
  · 绝不"读失败 → 当空账本 → 覆盖"。损坏时人工处置（还原备份/修 JSON）。
"""
import json

import pytest

from vodkit_cli import common


def _corrupt(tmp_path, monkeypatch, text: str = "{ broken json"):
    p = tmp_path / "install-manifest.json"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setenv("VOD_DEVKIT_MANIFEST", str(p))
    return p


def test_corrupt_manifest_raises_in_strict_mode(tmp_path, monkeypatch):
    p = _corrupt(tmp_path, monkeypatch)
    with pytest.raises(common.ManifestCorrupt):
        common._read_manifest(strict=True)
    assert p.read_text(encoding="utf-8") == "{ broken json", "读操作不许动字节"


def test_corrupt_manifest_non_strict_is_visible_not_silent(tmp_path, monkeypatch, capsys):
    _corrupt(tmp_path, monkeypatch)
    assert common._read_manifest() == {}
    err = capsys.readouterr().err
    assert "无法解析" in err, "只读面允许退回空账本，但必须把损坏报出来（不许静默）"


def test_manifest_write_is_atomic_on_failure(tmp_path, monkeypatch):
    p = tmp_path / "install-manifest.json"
    good = {"installs": [{"target": "hermes", "version": "0.5.21"}]}
    p.write_text(json.dumps(good), encoding="utf-8")

    def boom(*a, **k):
        raise OSError("No space left on device")

    monkeypatch.setattr(common.os, "replace", boom)
    with pytest.raises(OSError):
        common.atomic_write_text(p, json.dumps({"installs": []}))
    assert json.loads(p.read_text(encoding="utf-8")) == good, (
        "写失败必须保留旧账本（半截 JSON = 下次 install 丢 9 行）")
    assert not list(tmp_path.glob("*.tmp")), "失败后不留临时文件"


def test_manifest_write_atomic_sets_0600(tmp_path):
    p = tmp_path / "install-manifest.json"
    common.atomic_write_text(p, "{}")
    assert (p.stat().st_mode & 0o777) == 0o600, (
        "账本含宿主路径/产品绑定，落盘权限与 runtime.json 同档（0600）")


def test_install_write_path_reads_strict():
    """写路径必须 strict 读：坏账本时宁可报错也不覆盖（结构面锁）。"""
    src = (common.ROOT / "src" / "vodkit_cli" / "common.py").read_text(encoding="utf-8")
    seg = src[src.index("def _write_install_manifest"):]
    seg = seg[:seg.index("\ndef ", 1)]
    assert "_read_manifest(strict=True)" in seg, (
        "_write_install_manifest 还在用宽松读 → 坏账本会被空账本覆盖")
    assert "atomic_write_text" in seg, "账本写入必须走原子写"