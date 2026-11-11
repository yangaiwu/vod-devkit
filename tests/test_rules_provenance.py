"""规则真源对账门禁（scripts/rules_provenance.py 的行为锁）。

守的是「文档承诺的机制真的存在」：vendor_rules.py 已停用而 README 仍写着
"从 VOD-Project 拉取"——这类死链靠人记不住，用测试把新对账链钉住。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rules_provenance as rp  # noqa: E402


def _fixture(tmp_path, engine_symbols=("甲类", "乙类"), skill_text="规则：甲类/乙类\n"):
    engine = tmp_path / "engine"
    (engine / "workflow" / "src").mkdir(parents=True)
    (engine / "workflow" / "src" / "n01.py").write_text(
        "TYPE_DEFS = {" + "".join(f'"{s}": 1,' for s in engine_symbols) + "}\n",
        encoding="utf-8")
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(skill_text, encoding="utf-8")
    manifest = {
        "skills": [{
            "skill": "skills/demo/SKILL.md",
            "engine": [{"file": "workflow/src/n01.py",
                        "symbols": list(engine_symbols)}],
            "recorded": {},
        }]
    }
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return engine, mp, manifest


def test_ok_when_symbols_present_on_both_sides(tmp_path):
    engine, mp, _ = _fixture(tmp_path)
    rep = rp.check(engine, mp, root=tmp_path)
    assert rep["status"] == "ok", rep


def test_skip_when_no_engine_checkout(tmp_path):
    _, mp, _ = _fixture(tmp_path)
    rep = rp.check(tmp_path / "nope", mp, root=tmp_path)
    assert rep["status"] == "skip", rep
    assert "只跳过" in rep["reason"]


def test_fail_when_engine_drops_a_symbol(tmp_path):
    engine, mp, _ = _fixture(tmp_path)
    (engine / "workflow" / "src" / "n01.py").write_text('TYPE_DEFS = {"甲类": 1}\n',
                                                       encoding="utf-8")
    rep = rp.check(engine, mp, root=tmp_path)
    assert rep["status"] == "fail"
    assert any("已无符号「乙类」" in p for p in rep["entries"][0]["problems"])


def test_fail_when_skill_misses_a_symbol(tmp_path):
    engine, mp, _ = _fixture(tmp_path, skill_text="规则：甲类\n")
    rep = rp.check(engine, mp, root=tmp_path)
    assert rep["status"] == "fail"
    assert any("技能" in p and "乙类" in p for p in rep["entries"][0]["problems"])


def test_hash_drift_detected_then_record_clears_it(tmp_path):
    engine, mp, _ = _fixture(tmp_path)
    rp.record(engine, mp, root=tmp_path)          # 初次记录指纹
    assert rp.check(engine, mp, root=tmp_path)["status"] == "ok"
    # 引擎侧改了文件（口径变更）→ 漂移红
    (engine / "workflow" / "src" / "n01.py").write_text(
        'TYPE_DEFS = {"甲类": 1, "乙类": 2}\n# 注释改变指纹\n', encoding="utf-8")
    rep = rp.check(engine, mp, root=tmp_path)
    assert rep["status"] == "fail"
    assert any("引擎文件漂移" in p for p in rep["entries"][0]["problems"])
    # 复核后重录 → 绿（只允许显式 --update，不会静默跟随）
    rp.record(engine, mp, root=tmp_path)
    assert rp.check(engine, mp, root=tmp_path)["status"] == "ok"


def test_real_manifest_matches_engine_when_available():
    """本机有引擎检出时对真实 manifest 对账；没有则 SKIP（CI 语义）。"""
    rep = rp.check("/root/VOD-Project")
    assert rep["status"] in ("ok", "skip"), rep
    if rep["status"] == "ok":
        assert all(not e["problems"] for e in rep["entries"]), rep


def test_real_manifest_has_fingerprints_recorded():
    data = json.loads((ROOT / "docs" / "rules-provenance.json").read_text(encoding="utf-8"))
    for entry in data["skills"]:
        rec = entry.get("recorded") or {}
        assert rec.get("skill", "").startswith("sha256:"), f"{entry['skill']} 缺技能指纹"
        assert rec.get("engine"), f"{entry['skill']} 缺引擎指纹"