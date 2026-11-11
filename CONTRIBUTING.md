# 贡献指南

感谢关注 vod-devkit —— VOD 用户声音采集插件（纯采集形态）。

## 定位边界（先读）

本插件是**服务面插件**：无状态薄壳，永远是 VOD 引擎的客户端。

- 只做用户声音采集：`submit_voices` + 采集技能 + 护栏
- 不做分析发起 / 状态 / 结果查询（workflow 工具已删，运营能力归 vod-system 前端）
- 插件侧禁止 import 引擎内部模块，只走 HTTP API
- 破坏性写工具（删除/覆盖/撤回类）入库前必须先升级为 token 化审批（见
  docs/design.md 审批机制节），不许在布尔 confirmed 审批下放行

## 开发环境

- Python ≥ 3.10，零第三方运行时依赖（stdlib only）
- 测试：`pytest tests/`（含真子进程 stdio 协议回环、真 HTTP 服务器锁协议）
- Lint：`pyflakes`（CI 与 pre-push 门禁同款）
- 安装后自检：`bin/vod-devkit doctor`

## 改动纪律（CI 会拦）

1. **契约单一事实源**：工具 schema 改动改 `contract/tools.schema.json`，
   不许双边手写；U15 测试锁 schema 与实现同步
2. **账本读改写**：runtime.json 一律文件级读-改-写、只动目标键，
   禁止从内存整体回写（历史缺陷，有回归测试）
3. **新增网络函数**必须给存量用例注入桩，防止测试真打网络
4. **可漂移值**（product 白名单等）走 `GET /external/meta` 动态取，
   快照兜底须带 `[stale]` 标记；不许把引擎枚举硬编码进新代码
5. 提交前跑 `.githooks/pre-push`（已 `git config core.hooksPath .githooks`）
6. **提交信息两段式**：写清「改动」+「已验证证据」+「已知残余」三段。
   证据要可复跑（跑了哪些测试、真机验了什么），残余要写"没测到/已知边界"——
   借鉴 huaweicloud-devkit 的 ledger 纪律：没有残余声明的提交，评审无法
   判断边界在哪，只能重走一遍。

## 用例与计数纪律（CI 会拦）

- **新用例必须带承载**：在 `docs/proposal.md` 定义的每个用例号（`S*`/`U*`/`DG*`）
  都要能在 `docs/design.md` 承载表或某个测试文件里找到痕迹；
  `tests/test_case_roster.py` 是棘轮——新增未承载即红，历史欠账在
  `tests/case_roster_baseline.txt` 里只许缩不许增（补上承载后要删掉那一条）。
- **文档不手写用例/工具计数**：`tests/test_claims.py` 会拦。
  写「全量」并给实测命令（`python3 -m pytest tests/ -q`），不写具体数字——
  数字必然漂移，且没人能从文档里读出它是错的。
- **golden 只在有意变更时重录**：`UPDATE_GOLDEN=1` 重录后必须人工过目 diff
  （版本号/文案变更 vs 行为漂移，一眼能分）；门禁拦住是它该干的活。

## 领域规则技能

`skills/` 下的分类/评分规则技能由 `scripts/vendor_rules.py` 从
VodTeam/VOD-Project 按 commitSHA 锁定拉取——**规则只改引擎仓一处**，
本仓不手改 vendored 内容（过期停用标注除外）。

## 提交流程

1. fork / 分支 → 改动 → 本地全量测试 + pyflakes 绿
2. 提 MR（base=main），标题写清动机；破坏行为变更须先在
   `docs/decisions.md` 记决策依据
3. 评审关注：最坏伤害半径自审、护栏（confirm/批量上限/传输守卫）未被绕过
