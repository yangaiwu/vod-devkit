# 发版手册（RELEASING）

## 一键发版

```bash
scripts/release.sh              # bump 从提交历史推导（feat→minor，破坏性→major）
scripts/release.sh minor        # 显式指定
scripts/release.sh auto --dry-run
```

流程：质量门（pyflakes+pytest）→ 版本落点表驱动 bump + 硬断言 → 插件包同步
（sync_plugin.py）→ CHANGELOG → 提交+tag+推 GitCode/GitHub。

发版后手动执行（npm 凭据在发布人机器上）：

```bash
python3 scripts/pack_verify.py   # 包内容校验（必含/危险项）
npm publish --access public      # registry 分发约 1-3 分钟
```

## 版本落点

版本号存在于：package.json / pyproject.toml / vod_mcp/__init__.py /
contract/tools.schema.json / plugins/vod-devkit/.codex-plugin/plugin.json /
plugins/vod-devkit/build-info.json。**新增落点=改 release.sh 的 EXTRA_FILES
表**，不要手写替换逻辑（字符串替换静默 no-op 曾致版本滞留旧值多个周期，
两次实锤）。

## 发版纪律

- 提交信息遵循 conventional commits（feat/fix/…，破坏性加 `!`）——bump 自动推导依赖它
- 质量门红了禁止发版；`--dry-run` 可单独验质量门
- npm 首发或换 token：见 docs/decisions.md 分发三件套节（staging 两段式）
