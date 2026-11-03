#!/usr/bin/env bash
# 发版自动化（release-please 的本地等价物）
# 用法：scripts/release.sh patch|minor|major [--dry-run]
# 动作：版本三处同步 bump（package.json/pyproject/__init__）
#      → CHANGELOG 从 git log 生成 → tag → push（npm/GitHub 远端存在时一并推）
set -e
cd "$(dirname "$0")/.."

PART="${1:-patch}"
DRY="${2:---dry-run}"

CUR=$(python3 -c "import json;print(json.load(open('package.json'))['version'])")
case "$PART" in
  patch) BUMP=$(python3 -c "v='$CUR'.split('.');v[2]=str(int(v[2])+1);print('.'.join(v))");;
  minor) BUMP=$(python3 -c "v='$CUR'.split('.');v[1]=str(int(v[1])+1);v[2]='0';print('.'.join(v))");;
  major) BUMP=$(python3 -c "v='$CUR'.split('.');v[0]=str(int(v[0])+1);v[1]='0';v[2]='0';print('.'.join(v))");;
  *) echo "用法: $0 patch|minor|major [--dry-run]"; exit 1;;
esac
echo "版本: $CUR → $BUMP"

# 质量门：发版前必须全绿（同 pre-push）
PY=$(ls /root/.hermes/tools/python-3.14.7*/bin/python3 2>/dev/null || command -v python3)
export PYTHONPATH="/root/.hermes/cache/scratch/pylibs:$PYTHONPATH"
"$PY" -m pyflakes vod_mcp/*.py tests/*.py && "$PY" -m pytest tests/ -q || { echo "FAIL: 质量门未过，拒绝发版"; exit 1; }

if [ "$DRY" = "--dry-run" ]; then echo "[dry-run] 止步于此（质量门已过）"; exit 0; fi

python3 - "$CUR" "$BUMP" <<'EOF'
import json, sys, re
cur, new = sys.argv[1], sys.argv[2]
# package.json
p = json.load(open('package.json')); p['version'] = new
json.dump(p, open('package.json','w'), indent=2, ensure_ascii=False)
# pyproject.toml
t = open('pyproject.toml').read().replace(f'version = "{cur}"', f'version = "{new}"')
open('pyproject.toml','w').write(t)
# vod_mcp/__init__.py
i = open('vod_mcp/__init__.py').read().replace(f'__version__ = "{cur}"', f'__version__ = "{new}"')
open('vod_mcp/__init__.py','w').write(i)
EOF

# CHANGELOG 段生成（自上次 tag 以来的 commit）
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
RANGE="${PREV_TAG}..HEAD" && [ -z "$PREV_TAG" ] && RANGE="HEAD"
{
  echo ""
  echo "## v$BUMP（$(date +%F)）"
  echo ""
  git log --oneline "$RANGE" | sed 's/^/- /'
  echo ""
} >> CHANGELOG.md

git add -A
git commit -qm "release: v$BUMP"
git tag "v$BUMP"
git push origin main --tags 2>/dev/null && echo "已推送 GitCode" || echo "GitCode 推送跳过"
git push github main --tags 2>/dev/null && echo "已推送 GitHub 镜像" || echo "GitHub 镜像推送跳过（token 权限待补）"
echo "发版完成 v$BUMP（npm publish 需 granular token+2FA bypass，就绪后：npm publish --access public）"
