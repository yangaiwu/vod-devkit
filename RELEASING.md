# 发版手册（RELEASING）

## 一键发版

```bash
scripts/release.sh patch --publish   # 一次到位：门禁 → bump → tag → push → 打包断言 → npm 两包 → publish_verify
scripts/release.sh patch             # 只到 tag/push，npm 手动发（不传 --publish）
scripts/release.sh minor             # 显式指定 bump（缺省 auto：feat→minor，破坏性→major，否则 patch）
```

实际流程（`scripts/release.sh` 的顺序，照这个排障）：

```
质量门  pyflakes + mypy + pytest + 旧解释器语法门（py_compile，抓 ≤3.11 的语法错）
bump    落点表驱动改版本 + 逐点硬断言（漏一点就 FAIL）
同步    sync_plugin.py → 副本零提交；verify_copies 复验
提交    release: v<ver>（显式清单，不含 src/、tests/）；随后断言工作区无未提交业务文件
tag     git tag v<ver>，push **当前分支** + --tags（不硬编码 main）
镜像    配了 github remote 才推；失败只 WARN
打包    build-info 钉成 tag 内容并标 snapshot=released → npm pack → 断言包内 commitSha ∈ {tag^, tag}
dsh     packages/dsh 同版 pack，断言 lib/index.js 与工作区一致
发布    --publish 时：npm publish 两包 → publish_verify 终态断言（未上线/内容不符即 exit 1）
```

npm 凭据（发布人机器）：三个坑位按错误码判定 ——
`Two-factor authentication or granular access token with bypass 2fa enabled is required`
= 令牌没有 bypass 2FA（可读不可发）；`E_STAGE_REQUIRED … only publish to a staging area`
= 只能发 staging（需 `npm stage publish` + approve）；只有直接回 `+ pkg@version` 的令牌能发 latest。

**push 被 pre-push 拦（`No module named pyflakes`）**：钩子按 `仓内 .venv → ./venv → PATH 上的
python3` 选解释器。不要往解释器里装包、也不要跳钩子，用钩子自带的库路径入口：

```bash
DEVKIT_PREPUSH_LIBS=<含 pyflakes/pytest 的 site-packages> git push origin <分支> --tags
```

**push 失败时脚本已经 bump + 打 tag 了**：不要重跑 `release.sh`（会再 bump 一版）。
补推成功后单独执行后半段（`git checkout v<ver> -- build-info.json` → 标 `snapshot=released`
→ npm pack 指纹断言 → dsh pack → publish 两包 → `publish_verify.py`）。

## 版本落点

版本号存在于：package.json / pyproject.toml / src/vod_mcp/__init__.py /
assets/contract/tools.schema.json / packages/dsh/package.json /
plugins/vod-devkit/.codex-plugin/plugin.json / plugins/vod-devkit/build-info.json。**新增落点=改 release.sh 的 EXTRA_FILES
表**，不要手写替换逻辑（字符串替换静默 no-op 曾致版本滞留旧值多个周期，
两次实锤）。

## 发版纪律

- 提交信息遵循 conventional commits（feat/fix/…，破坏性加 `!`）——bump 自动推导依赖它
- 质量门红了禁止发版；`--dry-run` 可单独验质量门
- **发版前业务代码必须已提交**：`release.sh` 的显式提交清单只覆盖版本号/生成物/CHANGELOG，
  不含 `src/`、`tests/`。工作区还有未提交业务文件时，tag 会缺这些代码而 npm tarball 是从
  工作区打的 → **包与 tag 不一致**（v0.5.12 实锤：tag 里 `grep _dsh_effective` 为 0，
  而 0.5.12 包里是有的）。脚本已在 release commit 之后加硬断言，有未提交改动直接 FAIL；
  看到这条 FAIL 就是"先 commit 再发版"，别去改清单。
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
