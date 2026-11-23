#!/usr/bin/env bash
# 从指定 tag 干净重装（D-provenance-1，2026-11-24）
#
# 为什么要有它：install 用**工作树内容**物化载荷、build-info 却记 HEAD；手工
# `checkout --detach <tag>` 不清未提交改动，于是"补丁内容 + tag 标签"就装进去了
# （当晚实锤两次）。这个脚本把踩过的顺序固定下来：
#   断言源无未提交改动 → detach 到 tag → install all + 各 dsh profile → 回原分支 → 还原 build-info → doctor
#
# 用法：scripts/reinstall_from_tag.sh v0.5.60 [产品名]
set -euo pipefail

TAG=${1:?用法: scripts/reinstall_from_tag.sh <tag> [产品名]}
PRODUCT=${2:-CodeArts}

cd "$(git rev-parse --show-toplevel)"
BR=$(git rev-parse --abbrev-ref HEAD)
if [ "$BR" = "HEAD" ]; then
  echo "当前是 detached HEAD；先 git checkout <分支> 再跑（否则回不到原处）" >&2
  exit 2
fi
if ! git rev-parse -q --verify "$TAG^{commit}" >/dev/null; then
  echo "没有这个 tag/提交：$TAG" >&2
  exit 2
fi

dirty=$(git status --porcelain -- src assets npm integrations package.json pyproject.toml packages)
if [ -n "$dirty" ]; then
  echo "拒绝重装：源里有未提交改动（会被装成该 tag 的正式内容）：" >&2
  echo "$dirty" >&2
  exit 2
fi

echo "== detach 到 $TAG（$(git rev-parse --short "$TAG^{commit}")）"
git checkout --detach "$TAG" >/dev/null
trap 'git checkout "$BR" >/dev/null 2>&1 || true' EXIT

echo "== install --target all --product $PRODUCT"
./bin/vod-devkit install --target all --product "$PRODUCT"

profiles=$(ls "${DSH_HOME:-$HOME/.dsh}/profiles" 2>/dev/null || true)
for p in $profiles; do
  echo "== install --target dsh --profile $p"
  ./bin/vod-devkit install --target dsh --profile "$p" --product "$PRODUCT"
done

echo "== 回分支 $BR"
git checkout "$BR" >/dev/null
trap - EXIT
git checkout -- build-info.json 2>/dev/null || true

echo "== doctor"
./bin/vod-devkit doctor