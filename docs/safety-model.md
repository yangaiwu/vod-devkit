# 安全模型（声明式护栏 v0.1.0）

本插件假设 agent 会误做三件事：在用户明确同意之前把反馈写进共享库、把内部机制
（表名/库直连/凭据）带进对外内容、把凭据读出来打印。v0.1 因此在工具面与文本面
默认只读，写操作需要显式确认，跨进程能力一律不出插件。

## 默认拦截什么

- 未经用户同意就写库：`vod_submit_voices` 缺 `confirmed=true` → `[guard:confirm] -32011`。
- 单批超量：`voices` 条数 > `maxVoicesPerSubmit`（50）→ `[guard:deny] -32010`。
- 数据库直连意图（`mysql` / `jdbc` / `t_vod_` / `select ... from`）→ deny。
- 凭据读取意图（access_key / secret_key / x-auth-token / password / private_key
  后接 `:` `=` `值` `发` `读` `取`）→ deny。

## 谁在执行（文件级执行矩阵）

| 规则载体 | 执行点 | 作用面 |
|---|---|---|
| `safety/policy.json`（4 条规则） | — | 硬词汇表，唯一事实源 |
| `vod_mcp/policy.py:check_tool_call` | `vod_mcp/server.py` 的 `tools/call` 前置 | 工具参数（confirm / 批上限） |
| `vod_mcp/policy.py:check_text` | 同上，扫 `guard_scope(args)` 序列化串 | 文本类 deny（DB 直连 / 凭据意图） |
| `vod_mcp/policy.py:guard_scope` | 文本规则扫描面裁剪 | 剔除 `voices[].content` 与 `data`——用户原话不进文本规则，防误杀"反馈里引用凭据串" |
| 两段式 `vod_draft_voices` → `vod_commit_voices` | `vod_mcp/tools.py` | 审计链：一次性令牌 + payloadSha256 防调包；绕过可被账本 `stage` 检测 |
| codex 采集熔断 | `vod_mcp/packs.py:BREAKER_MARKERS` + `bin/vod-devkit` 安装门禁 | 未确认提交 ≥2 次后强制摘除 collect pack |
| 分发红线（key 不随包） | `bin/vod-devkit:cmd_install` `--distribution preset` | `VOD_JAVA_API_KEY` 从 env 摘除且不写宿主配置 |
| 技能拷贝漂移 | `bin/vod-devkit:_skill_hashes/_drifted_skills`（D-drift-lock） | 安装期记录 sha256，doctor/verify 逐落点比对 |

错误码约定（宿主/模型可据此分流）：`-32010` deny、`-32011` confirm、`-32012`
认证（缺 key 且令牌不可得）、`-32013` 归因缺失、`-32014` 传输（非回环 http）。

## 写操作路径

默认路径是「草稿 + 提交」：`vod_draft_voices` 把载荷暂存在本机（cap 10 / TTL
600s），回执逐字回显 `contents`；`vod_commit_voices` 校验一次性令牌与
`payloadSha256` 后复用既有提交链。采集语义下 `vod_submit_voices` 仍然保留
（幂等 + 审核闸 + 不可破坏），断回合续提交走 pending 队列
（`vod_mcp/pending.py`，幂等键条级 + 原话多行必填）。

## 已接受风险（都是有意留下的，不是漏配）

- **布尔审批挡不住自愿违规的 agent**：`confirmed=true` 由模型调用方决定，
  MCP 层无法强制人类确认。实锤：codex/hermes 会跳过确认直发。对应的处置是
  检测层（回执逐字回显 + `scripts/e2e_behavior.py` 违规计数 + 熔断），不是
  假装存在一个确认门（D-codex-circuit-breaker-1 / D-token-approval-2）。
- **两段式 = 审计链不是确认门**：token 锁的是"同一份载荷"，agent 可以自己
  draft→commit 连发；它的价值是事后可判定（账本 stage）、防调包、可熔断。
- **熔断标记是本机文件**：用户/agent 能删（`--ack-suspension` 是显式逃生口，
  动作后置到安装成功，并写审计日志）；运行期 `packs.py` 同查标记，防
  `VOD_PACKS=core,collect serve` 绕过。
- **文本规则只扫结构性字段**：`voices[].content` 刻意不进扫描面——拦意图不
  拦转述，代价是"用户在反馈正文里要求 agent 读凭据"不会被这层拦住。
- **headless 回执 echo 无闸**：dsh headless 单轮模式实测出现过回执改字一笔
  （「点了定义」→「点"转到定义"」），数据层原话无损，展示层无自动拦截。

## Non-goals

不是安全边界。IAM 最小权限、审计日志、本机凭据存储、生成内容的复核仍然是
使用方责任；插件不提供加密存储（静态加密对"本机能读到 key"这一前提零收益），
也不对外宣告自己拦得住蓄意攻击者。