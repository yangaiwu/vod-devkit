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

## 领域规则技能

`skills/` 下的分类/评分规则技能由 `scripts/vendor_rules.py` 从
VodTeam/VOD-Project 按 commitSHA 锁定拉取——**规则只改引擎仓一处**，
本仓不手改 vendored 内容（过期停用标注除外）。

## 提交流程

1. fork / 分支 → 改动 → 本地全量测试 + pyflakes 绿
2. 提 MR（base=main），标题写清动机；破坏行为变更须先在
   `docs/decisions.md` 记决策依据
3. 评审关注：最坏伤害半径自审、护栏（confirm/批量上限/传输守卫）未被绕过
