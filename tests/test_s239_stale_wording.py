"""S239：老链回落的"残留表述"清理（S238 删代码后，文案/契约还在说旧行为）。

真机来源：删掉 404→legacy 回落之后，契约里 `vod_submit_voices` 的 description 仍写着
「引擎未部署 404 自动回落老链」——模型据此会以为回落在，用户被拒时会问错方向。
docstring 里也还留着「囤积/legacy 两路径同口径」。

判据：现役「说给模型听」的文本（契约 description）与实现注释不得再把老链写成可用路径；
但允许在错误文案里提醒"不要改用老链"（那是处置指引，不是能力声明）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _contract_desc() -> str:
    data = json.loads((ROOT / "assets" / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
    return str((data["tools"]["vod_submit_voices"] or {}).get("description") or "")


def test_s239_contract_no_longer_promises_legacy_fallback():
    desc = _contract_desc()
    assert "回落老链" not in desc, "契约仍在承诺老链回落"
    assert "voice/submit" not in desc, "契约里出现了已删除的老链接口"
    assert "囤积端点" in desc and "唯一提交路径" in desc, "契约要写清唯一路径"


def test_s239_collect_comment_single_path():
    src = (ROOT / "src" / "vod_mcp" / "packs" / "collect.py").read_text(encoding="utf-8")
    assert "legacy 两路径" not in src, "注释仍写两路径"
    assert "囤积端点单一路径" in src


def test_s239_error_text_still_warns_against_legacy():
    """允许且要求：404 错误文案要提醒"不要改用老链"（处置指引）。"""
    src = (ROOT / "src" / "vod_mcp" / "packs" / "collect.py").read_text(encoding="utf-8")
    assert "不要改用老链" in src
    assert "-32016" in src
