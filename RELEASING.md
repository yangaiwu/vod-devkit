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

版本号存在于：package.json / pyproject.toml / src/vod_mcp/__init__.py /
assets/contract/tools.schema.json / packages/dsh/package.json /
plugins/vod-devkit/.codex-plugin/plugin.json / plugins/vod-devkit/build-info.json。**新增落点=改 release.sh 的 EXTRA_FILES
表**，不要手写替换逻辑（字符串替换静默 no-op 曾致版本滞留旧值多个周期，
两次实锤）。

## 发版纪律

- 提交信息遵循 conventional commits（feat/fix/…，破坏性加 `!`）——bump 自动推导依赖它
- 质量门红了禁止发版；`--dry-run` 可单独验质量门
- npm 首发或换 token：见 docs/decisions.md 分发三件套节（staging 两段式）

## 双仓：GitCode 主仓，GitHub 只读镜像

- **主仓 = GitCode**（`xiaowu2119/vod-devkit`）：MR、评审、CI 以它为准。
- **GitHub**（`yangaiwu/vod-devkit`）是**只读镜像**：不接受直接在 GitHub 上
  提 PR 合并（会出现两套历史）。GitHub 的 Actions 会跟着每次同步跑，
  **镜像 CI 红了算真红**——它是第二道网（实测抓到过 GitCode CI 没覆盖的问题）。
- 合并后同步（只在 main 前进时做，快进，不 force）：

  ```bash
  git fetch origin && git checkout main && git merge --ff-only origin/main
  git push github main:main          # 失败重试：github.com:443 会间歇性阻断
  git push github --tags             # 发版后
  git ls-remote --heads github main  # 校验：必须等于 origin/main 的 sha
  ```

- 网络排障：`api.github.com` 通而 `github.com:443` 超时是常见现象（国内出口），
  重试即可（实测第 2 次成功）；`ssh.github.com:443` 是可用的备用通道。
- 分支纪律：GitHub 只保留 `main`。历史分支删除前先打 tag 归档
  （`archive/<name>`），保证提交不丢。
