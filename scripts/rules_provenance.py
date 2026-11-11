"""规则技能 ↔ 引擎真源对账（替代已停用的 scripts/vendor_rules.py）。

背景：技能里的分类/评分口径是从引擎代码人工核对后写死的，而 README 曾长期
写着"由 vendor_rules.py 从 VOD-Project 拉取"——那是一条停用的链，文档在描述
不存在的机制（2026-11-11 评审确认）。本脚本把这条承诺变成可执行对账：

  1. 符号对账：manifest 里每条「技能↔引擎文件↔符号」三元组，符号必须同时出现在
     引擎文件与技能正文里（引擎删了/改名了 → 技能口径已过期，当场红）
  2. 指纹对账：manifest 记录引擎文件与技能文件的 sha256；任一漂移即提示复核，
     复核后 --update 重录（只允许在人工过目后更新，防止静默跟随）

引擎检出位置：--engine，或环境变量 VOD_PROJECT_DIR，默认 /root/VOD-Project。
无引擎检出（外部贡献者/CI 无该仓）→ 跳过并明说 SKIP，不伪绿也不误红。

用法：
  python3 scripts/rules_provenance.py            # 对账（CI/pre-push）
  python3 scripts/rules_provenance.py --update   # 人工复核后重录指纹
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "rules-provenance.json"
DEFAULT_ENGINE = "/root/VOD-Project"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_manifest(data: dict, path: Path = MANIFEST) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def check(engine_dir: str | Path | None, manifest_path: Path = MANIFEST,
          root: Path = ROOT) -> dict:
    """返回 {"status": ok|fail|skip, "reason":..., "entries":[{"skill","problems"}]}。

    root 可注入（单测用临时仓结构），默认本仓。
    """
    data = load_manifest(manifest_path)
    if not engine_dir or not Path(engine_dir).is_dir():
        return {"status": "skip",
                "reason": f"无引擎检出（{engine_dir or '未指定'}）——只跳过，不判绿",
                "entries": []}
    engine = Path(engine_dir)
    report = {"status": "ok", "reason": "", "entries": []}
    for entry in data.get("skills") or []:
        skill_path = Path(root) / entry["skill"]
        problems = []
        skill_text = ""
        if not skill_path.exists():
            problems.append(f"技能文件缺失：{entry['skill']}")
        else:
            skill_text = skill_path.read_text(encoding="utf-8")
        for spec in entry.get("engine") or []:
            f = engine / spec["file"]
            if not f.exists():
                problems.append(f"引擎真源缺失：{spec['file']}（路径变了？先修 manifest）")
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            for sym in spec.get("symbols") or []:
                if sym not in text:
                    problems.append(f"引擎 {spec['file']} 已无符号「{sym}」——规则口径变了，技能必须复核")
                elif skill_text and sym not in skill_text:
                    problems.append(f"技能 {entry['skill']} 未包含引擎符号「{sym}」——技能漏写")
        rec = entry.get("recorded") or {}
        for fname, want in (rec.get("engine") or {}).items():
            p = engine / fname
            if p.exists() and sha256(p) != want:
                problems.append(f"引擎文件漂移：{fname}（指纹不符；复核技能后 --update 重录）")
        if rec.get("skill") and skill_text and sha256(skill_path) != rec["skill"]:
            problems.append(f"技能文件指纹漂移：{entry['skill']}（确认口径无误后 --update）")
        report["entries"].append({"skill": entry["skill"], "problems": problems})
        if problems:
            report["status"] = "fail"
    return report


def record(engine_dir: str | Path, manifest_path: Path = MANIFEST,
           root: Path = ROOT) -> dict:
    """人工复核通过后重录指纹（引擎侧+技能侧）。"""
    data = load_manifest(manifest_path)
    engine = Path(engine_dir)
    for entry in data.get("skills") or []:
        recorded = {"engine": {}, "skill": None}
        for spec in entry.get("engine") or []:
            p = engine / spec["file"]
            if p.exists():
                recorded["engine"][spec["file"]] = sha256(p)
        skill_path = Path(root) / entry["skill"]
        if skill_path.exists():
            recorded["skill"] = sha256(skill_path)
        entry["recorded"] = recorded
    save_manifest(data, manifest_path)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=os.environ.get("VOD_PROJECT_DIR") or DEFAULT_ENGINE)
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--update", action="store_true", help="人工复核后重录指纹")
    args = ap.parse_args(argv)
    if args.update:
        if not Path(args.engine).is_dir():
            print(f"FAIL: --update 需要引擎检出（{args.engine}）", file=sys.stderr)
            return 1
        record(args.engine, Path(args.manifest))
        print(f"已重录指纹：{args.manifest}")
        return 0
    rep = check(args.engine, Path(args.manifest))
    if rep["status"] == "skip":
        print(f"SKIP: {rep['reason']}")
        return 0
    bad = [e for e in rep["entries"] if e["problems"]]
    if bad:
        print("FAIL: 规则技能与引擎真源不一致：", file=sys.stderr)
        for e in bad:
            for p in e["problems"]:
                print(f"  - {e['skill']}: {p}", file=sys.stderr)
        return 1
    print(f"rules provenance OK（{len(rep['entries'])} 条技能，引擎={args.engine}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())