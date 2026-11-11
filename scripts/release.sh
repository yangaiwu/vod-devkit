#!/usr/bin/env bash
# 发版自动化（对齐 devkit release-please 语义的本地实现）：
#   bump 推导：默认从上一 tag 以来的提交历史推导（feat→minor，破坏性→major，
#   否则 patch）；显式 patch|minor|major 可覆盖。
#   版本落点表驱动：EXTRA_FILES 声明全部附加版本落点（加落点只改表——
#   __init__/契约曾静默滞留旧版本的实锤教训）；落点用正则整行替换（非子串
#   replace），替换后逐点硬断言兜底。
#   质量门：pyflakes+pytest 全绿才发。
# 用法：scripts/release.sh [patch|minor|major|auto] [--dry-run]
set -e
cd "$(dirname "$0")/.."

PART="auto"; DRY="--run"; PUBLISH=0
for a in "$@"; do
  case "$a" in
    patch|minor|major|auto) PART="$a" ;;
    --dry-run) DRY="--dry-run" ;;
    --publish) PUBLISH=1 ;;
    *) echo "未知参数: $a（可用：patch|minor|major|auto --dry-run --publish）" >&2; exit 1 ;;
  esac
done

CUR=$(python3 -c "import json;print(json.load(open('package.json'))['version'])")
if [ "$PART" = "auto" ]; then
  LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
  RANGE=${LAST_TAG:+$LAST_TAG..HEAD}
  if [ -n "$LAST_TAG" ] && git log $RANGE --oneline | grep -qiE ' (feat|fix)![(:]|BREAKING CHANGE'; then
    PART=major
  elif [ -n "$LAST_TAG" ] && git log $RANGE --oneline | grep -qE '^\w+ feat(\(|:| )'; then
    PART=minor
  else
    PART=patch
  fi
  echo "bump 由提交历史推导：$PART"
fi
case "$PART" in
  patch) BUMP=$(python3 -c "v='$CUR'.split('.');v[2]=str(int(v[2])+1);print('.'.join(v))");;
  minor) BUMP=$(python3 -c "v='$CUR'.split('.');v[1]=str(int(v[1])+1);v[2]='0';print('.'.join(v))");;
  major) BUMP=$(python3 -c "v='$CUR'.split('.');v[0]=str(int(v[0])+1);v[1]='0';v[2]='0';print('.'.join(v))");;
  *) echo "用法: scripts/release.sh [patch|minor|major|auto] [--dry-run]"; exit 1;;
esac
echo "版本: $CUR → $BUMP"

# 质量门：发版前必须全绿（同 pre-push）
PY=$(ls /root/.hermes/tools/python-3.14.7*/bin/python3 2>/dev/null || command -v python3)
export PYTHONPATH="/root/.hermes/cache/scratch/pylibs:$PYTHONPATH"
"$PY" -m pyflakes vod_mcp/*.py tests/*.py && "$PY" -m pytest tests/ -q || { echo "FAIL: 质量门未过，拒绝发版"; exit 1; }

# 双副本同步门（实锤教训：npm 0.4.1 曾以滞后 10 提交的旧插件副本发出——
# pending 队列缺失、包内 build-info 落后 HEAD）：发版起点必须双副本零漂移。
# sync 重跑一遍，若产生未提交变更=提交前忘了同步，拒绝发版（sync 结果应单独
# 提交）。build-info 每次重写时间戳，不参与本检查（随发版提交再生）。
python3 scripts/sync_plugin.py
if ! git diff --quiet -- plugins/vod-devkit/vod_mcp plugins/vod-devkit/skills; then
  echo "FAIL: 双副本漂移——sync 产生了未提交变更。请先提交 sync 结果（git add plugins/vod-devkit/vod_mcp plugins/vod-devkit/skills）再发版" >&2
  exit 1
fi

if [ "$DRY" = "--dry-run" ]; then echo "[dry-run] 止步于此（质量门已过）"; exit 0; fi

python3 - "$CUR" "$BUMP" <<'EOF'
import json, re, sys
cur, new = sys.argv[1], sys.argv[2]

def sub_line(path, pattern, repl, flags=re.M):
    s = open(path).read()
    s2, n = re.subn(pattern, repl, s, count=1, flags=flags)
    if n != 1:
        print(f"FAIL: {path} 版本落点未命中（{pattern}），中止发版", file=sys.stderr)
        sys.exit(1)
    open(path, "w").write(s2)

# 核心落点：整行正则替换（非子串 replace——静默 no-op 的根因）
sub_line("package.json", r'(?m)^  "version": ".*",$', f'  "version": "{new}",')
sub_line("pyproject.toml", r'(?m)^version = ".*"$', f'version = "{new}"')
sub_line("vod_mcp/__init__.py", r'(?m)^__version__ = ".*"$', f'__version__ = "{new}"')
sub_line("contract/tools.schema.json", r'(?m)^  "version": ".*",$', f'  "version": "{new}",')

# 附加落点表驱动（对齐 devkit release-please extra-files 语义）：
# 加版本落点=在表里加一行，不再改脚本逻辑。
EXTRA_FILES = [
    ("plugins/vod-devkit/.codex-plugin/plugin.json", "json"),
    ("plugins/vod-devkit/build-info.json", "json"),
    ("dsh/package.json", "json"),
]
for f, kind in EXTRA_FILES:
    try:
        d = json.load(open(f))
    except FileNotFoundError:
        continue
    if d.get("version"):
        d["version"] = new
        open(f, "w").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")

# 全落点硬断言兜底（表漏了/替换没生效都在这里拦住）
ALL = ["package.json", "pyproject.toml", "vod_mcp/__init__.py",
       "contract/tools.schema.json"] + [f for f, _ in EXTRA_FILES]
for f in ALL:
    try:
        s = open(f).read()
    except FileNotFoundError:
        continue
    if new not in s:
        print(f"FAIL: {f} 版本未同步到 {new}，中止发版", file=sys.stderr)
        sys.exit(1)
EOF

python3 scripts/sync_plugin.py

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

# 显式文件列表提交（纪律：禁 git add -A——曾误收垃圾文件）
# plugins/vod-devkit/skills 也在提交清单（双副本同步的 skills 半边，此前漏加）
git add package.json pyproject.toml vod_mcp/__init__.py contract/tools.schema.json \
        plugins/vod-devkit/.codex-plugin/plugin.json plugins/vod-devkit/build-info.json \
        plugins/vod-devkit/vod_mcp plugins/vod-devkit/skills dsh/package.json CHANGELOG.md
git commit -qm "release: v$BUMP"
git tag "v$BUMP"
git push origin main --tags || { echo "FAIL: GitCode 推送失败（pre-push 门禁或网络），发版未完成"; exit 1; }
echo "已推送 GitCode"
if git push github main --tags 2>/dev/null; then echo "已推送 GitHub 镜像"; else echo "WARN: GitHub 镜像推送跳过（token 权限待补）"; fi

# npm 包自证（P0 复发根治：npm 0.4.1 实锤——包内缺 pending.py：files 白名单
# 逐文件枚举漏新模块 + 曾以旧插件副本打出）：现场 pack 并断言包内代码指纹
# == tag 父提交（build-info 由 sync 在发版前写入，sha=发版起点提交——自指
# 不可能，等式只能对 tag^ 成立），之后只允许发布这颗已验证的 tarball。
TGZ="vod-devkit-$BUMP.tgz"
npm pack --silent >/dev/null
TAG_PARENT=$(git rev-parse "v$BUMP^")
if ! tar xzOf "$TGZ" package/plugins/vod-devkit/build-info.json | grep -q "\"commitSha\": \"$TAG_PARENT\""; then
  echo "FAIL: pack 出的 tarball 代码指纹（应=$TAG_PARENT，即 v$BUMP 父提交）不符——禁止发布这颗包" >&2
  exit 1
fi
echo "npm tarball 已验证：$TGZ（代码指纹=$TAG_PARENT）"

# dsh 壳同版发布（2026-11-10 实锤教训：dsh 壳游离在发版流程外，npm 停在
# 0.1.1 半个月，期间所有按包名安装的 dsh 装机全拿旧包——安装器内部就是
# `dsh plugin add dsh-vod-devkit` 按包名走 npm）。版本随主包同 bump（落点表），
# pack 后断言包内 lib 指纹 == 工作区（防 stale build 产物随包发出），并与
# 主包一起给出发布命令——两个包都必须发布，缺一即复发。
DSH_TGZ="dsh/dsh-vod-devkit-$BUMP.tgz"
( cd dsh && npm pack --silent >/dev/null )
if ! tar xzOf "$DSH_TGZ" package/lib/index.js | diff -q - dsh/lib/index.js >/dev/null 2>&1; then
  echo "FAIL: dsh tarball lib/index.js 与工作区不一致（src 改后未 build-client？）——禁止发布" >&2
  exit 1
fi
echo "dsh tarball 已验证：$DSH_TGZ（lib 指纹=工作区）"
if [ "$PUBLISH" = "1" ]; then
  # 发布 + 终态断言（v0.4.2 实锤：tag 推了 npm 没上，用户吃旧包且无人发现）。
  # 断言不过即 exit 1——"publish 回执成功"从来不是发版完成的证据。
  echo "发布两颗包…"
  npm publish "$TGZ" --access public || { echo "FAIL: vod-devkit publish 失败"; exit 1; }
  npm publish "$DSH_TGZ" --access public || { echo "FAIL: dsh 壳 publish 失败"; exit 1; }
  python3 scripts/publish_verify.py --version "$BUMP" \
      --pkg vod-devkit --pkg dsh-vod-devkit \
    || { echo "FAIL: 发版终态断言未过（registry 未上线或包内容不符）"; exit 1; }
  echo "发版完成 v$BUMP，两颗包已上线并通过内容核验"
else
  echo "发版完成 v$BUMP，待发布两颗包（加 --publish 可自动发布并核验终态）："
  echo "  1) npm publish $TGZ --access public"
  echo "  2) npm publish $DSH_TGZ --access public"
  echo "  3) python3 scripts/publish_verify.py --version $BUMP --pkg vod-devkit --pkg dsh-vod-devkit"
fi
