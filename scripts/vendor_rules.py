"""规则 vendor：从 VOD-Project 真源拉领域规则技能进本仓 skills/。

模式：
  --source <本地 VOD-Project 路径>   dev 模式（CI 门禁不认，仅开发快回路）
  --sha <commitSHA>                 锁定模式（发版/CI 必须）：git cat-file 校验后按该版本文件拉取
规则真源永远是 VodTeam/VOD-Project 的 skills/ 下的领域规则文档。
"""
import argparse
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DST = ROOT / "skills"
RULE_SKILLS = (
    "vod-category-matching-rules.md",
    "vod-problem-classification-rules.md",
    "vod-scoring-rules.md",
)


def _repo(source: str) -> str:
    return source


def vendor(source: str, sha: str | None) -> list:
    repo = _repo(source)
    pulled = []
    for name in RULE_SKILLS:
        if sha:
            r = subprocess.run(["git", "show", f"{sha}:skills/{name}"],
                               cwd=repo, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"FAIL: {name} 不存在于 {sha}", file=sys.stderr)
                sys.exit(1)
            content = r.stdout
        else:
            p = Path(repo) / "skills" / name
            if not p.exists():
                print(f"FAIL: {p} 不存在", file=sys.stderr)
                sys.exit(1)
            content = p.read_text(encoding="utf-8")
        dst = SKILLS_DST / name
        dst.write_text(content, encoding="utf-8")
        pulled.append(str(dst))
    return pulled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="VOD-Project 本地路径")
    ap.add_argument("--sha", default=None, help="锁定 commitSHA（CI/发版必须）")
    args = ap.parse_args()
    files = vendor(args.source, args.sha)
    for f in files:
        print("vendored:", f)
    if not args.sha:
        print("WARN: dev 模式（无 SHA 锁定），CI 门禁不认此产物", file=sys.stderr)


if __name__ == "__main__":
    main()
