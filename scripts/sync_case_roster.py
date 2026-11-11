"""重录用例花名册（tests/case_roster.json）。

显式清单取代「门禁靠正则现场扫文档」：花名册成为可审阅的单一真源，门禁只做
对账。新增/删除用例后跑一次本脚本，diff 里看得见每条用例的承载落在哪。

用法：
  python3 scripts/sync_case_roster.py           # 重录（保留基线豁免）
  python3 scripts/sync_case_roster.py --check   # 只校验不写（CI 用，等价门禁）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_roster as roster  # noqa: E402

OUT = roster.ROOT / "tests" / "case_roster.json"


def build() -> dict:
    defined = roster.defined_cases()
    carried = roster.carry_map()
    waivers = roster.baseline_waivers()
    return {
        "_comment": ("生成物：python3 scripts/sync_case_roster.py 重录。"
                     "cases=用例号→承载文件（null=无承载，必须同时在 baseline 豁免）；"
                     "waivers 与 tests/case_roster_baseline.txt 同步（棘轮只缩）。"),
        "cases": {cid: {"carrier": carried.get(cid)} for cid in defined},
        "waivers": roster.ordered(waivers),
    }


def main() -> int:
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != text:
            print("FAIL: tests/case_roster.json 与文档/测试现状不一致，请重录：\n"
                  "  python3 scripts/sync_case_roster.py", file=sys.stderr)
            return 1
        print("roster OK（花名册与文档/测试一致）")
        return 0
    OUT.write_text(text, encoding="utf-8")
    missing = [cid for cid, v in data["cases"].items() if v["carrier"] is None]
    print(f"已重录 {OUT}：用例 {len(data['cases'])} 个，无承载 {len(missing)} 个"
          f"（{', '.join(missing[:12])}{' …' if len(missing) > 12 else ''}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())