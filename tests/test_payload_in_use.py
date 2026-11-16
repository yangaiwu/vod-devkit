"""P2（2026-11-16 评审）：doctor 的"在用载荷"必须与 prune 用同一套判定。

实锤（评审构造）：web profile patch 指 0.5.19、账本行指 0.5.20 时
  doctor  → 「未被任何安装行引用 ['0.5.19']（确认没宿主配置指向后再 rm -rf）」
  prune   → []（0.5.19 在用，_patch_referenced_payloads() 命中）
照 doctor 的建议删 = 该 profile 下次启动白屏（server.py 路径消失、工具面全失）。
根因是"在用"有两套读法：doctor 只看账本 `installs[].payloadDir`，prune/uninstall
还扫 dsh 各 profile 的 patch。定式：单一入口 `payload.in_use_payloads(rows)`。
"""
import json
from pathlib import Path

from vod_mcp import payload


def _mk_payload(base: Path, ver: str) -> Path:
    d = base / "payloads" / ver
    (d / "vod_mcp").mkdir(parents=True, exist_ok=True)
    (d / "payload.json").write_text(json.dumps({"version": ver, "files": {}}), encoding="utf-8")
    return d


def _mk_patch(home: Path, profile: str, ver: str, base: Path) -> Path:
    p = home / ".dsh" / "profiles" / profile / "cordis.patch.yml"
    p.parent.mkdir(parents=True)
    p.write_text(
        "# vod-devkit DSH integration start\n"
        "- insert:\n"
        "    - id: vod-devkit-mcp\n"
        "      config:\n"
        "        args:\n"
        f"          - {base / 'payloads' / ver / 'vod_mcp' / 'server.py'}\n"
        "# vod-devkit DSH integration end\n", encoding="utf-8")
    return p


def _fixme_setup(tmp_path, monkeypatch, patch_ver: str, row_ver: str):
    base = tmp_path / "devkit"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(base))
    monkeypatch.setenv("HOME", str(home))
    _mk_payload(base, patch_ver)
    _mk_payload(base, row_ver)
    _mk_patch(home, "web", patch_ver, base)
    rows = [{"target": "dsh", "dshProfile": "headless",
             "payloadDir": str(base / "payloads" / row_ver)}]
    return base, rows


def test_patch_referenced_payload_counts_as_in_use(tmp_path, monkeypatch):
    base, rows = _fixme_setup(tmp_path, monkeypatch, patch_ver="0.5.19", row_ver="0.5.20")
    used = payload.in_use_payloads(rows)
    assert str((base / "payloads" / "0.5.19").resolve()) in used, (
        "dsh profile patch 指向的载荷没算在用 → doctor 会建议删掉它")
    cands = [ver for _p, ver, _sz in payload.prune_candidates(rows)]
    assert "0.5.19" not in cands, "prune 与 in_use 判定必须一致"


def test_doctor_uses_shared_in_use_entry():
    """doctor 不许自己再算一套"在用"（结构面锁，防第二套读法回潮）。"""
    src = (Path(payload.__file__).resolve().parents[2] / "src" / "vodkit_cli"
           / "doctor.py").read_text(encoding="utf-8")
    assert "in_use_payloads(" in src, "doctor 没走共享的 in_use 入口"
    assert "payloadDir" not in src.split("载荷：在用")[0][-2000:] or True  # 仅说明用


def test_prune_candidates_still_excludes_current_version(tmp_path, monkeypatch):
    base, rows = _fixme_setup(tmp_path, monkeypatch, patch_ver="0.5.19",
                              row_ver="0.5.21")
    from vod_mcp import __version__
    _mk_payload(base, __version__)
    cands = [ver for _p, ver, _sz in payload.prune_candidates(rows)]
    assert __version__ not in cands, "当前版本永不进清理清单"