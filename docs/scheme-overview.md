# vod-devkit 方案一页纸（现状版；历史台账见 CHANGELOG/decisions）

## 一句话

把 AI agent 产品的用户反馈，安全、可对账地送进 VOD 声音分析平台——
插件是纯采集薄壳，一个写口、一个上游、两档信任。

## 架构

```
终端用户（对 agent 说反馈，零 VOD 感知）
   ↓ 采集技能：识别→征得同意→结构化（title=用户原文）
宿主 agent（11 个专属适配：hermes / opencode / codeartsdoer / codeartswork / codex /
codex-desktop / dsh / workbuddy / atomcode / openclaw / officeace；其它 MCP 客户端走 --target generic）
   ↓ MCP stdio（JSON-RPC，工具名 `vod_*`；dsh 的 MCP 模式前缀为 `mcp__vod-devkit__vod_*`）
vod-devkit 插件（Python 单进程薄壳，零第三方依赖；另有远程面 Streamable HTTP 供多 agent 共用）
   ├ 护栏：confirm 逐次 / 单批≤50 / 内容≤2000 / DB·凭据意图 deny
   ├ 归因链：用户明确回答 → 原话唯一命中 → 会话记忆 → 安装先验（**需原话自指**）；
   │  都没有 → 不猜、不提交，先问一次产品（与提交确认合并成一轮）
   ├ 身份：零字段匿名令牌（机器级一份，`vod_auth_ensure` 判+领）→ 正式 key（升级制）→ 宿主 key
   └ 动态元数据：meta 拉取 + 名录缓存（7 天 TTL）+ 快照兜底 + stale 标记
   ↓ Authorization: Bearer（远程面缺省走机器级匿名令牌，Bearer 优先）
*** Java backend（唯一上游：/external/voices 囤积批量 + /external/token + /external/meta）
   → 复用 saveCollectRecord 入库 → 增量分析 → 报告/看板
```

## 身份模型（归属/认证分离）

- **归属**（谁提的）= 数据字段：userType/customer 随声音入库，VOD 不建
  用户体系；工具 Schema 零身份参数——模型不能伪造归属
- **认证**（谁在调）= key 三档：匿名令牌（零字段自动签发，日限低，
  数据打标可过滤）→ 正式 key（升级制）→ 宿主 key（平台对接持有）
- 失败关闭：拿不到任何可追溯凭证就拒写，不存无归属记录

## 关键设计决策（拍板链）

| 决策 | 结论 |
|---|---|
| 插件定位 | 方案 A 纯采集——运营能力归 vod-system 前端，不耦合（负复杂度：净删 304 行） |
| 对齐对象 | devkit 工程骨架（installer/MCP/技能/packs/护栏），不抄其形态（知识面 vs 服务面） |
| 引擎改动 | 零改动起步（复用现有接口实测打通）；囤积端点/meta 端点/多 key 为引擎侧后续 |
| 语言 | Python（宿主 hook+团队栈+MCP 窄腰低风险可逆；I/O 型如实判定偏 TS 已记档） |
| key 交付 | 零字段令牌入门（注册制否决：门槛在价值之前会跑人） |
| voiceId | 调用级唯一（跨调用不去重——声量是分析核心信号） |
| 溯源 | commitSHA 主键+verify 篡改检测（devkit 无此能力） |

## 质量

- 用例：单元+护栏+packs+协议级真 HTTP（锁认证头/路径）+stdio 回环+meta（数量以实测为准，文档不手写计数）
- 门禁：pre-push 钩子（同步副本→校验→lint/pytest/mypy 红了禁推）+ GitHub Actions（ci.yml / release.yml）
- 端到端已实测：多宿主真机会话→引擎落库行对账（行为回归套件 `scripts/e2e_behavior.py`，见 design.md）

## 对外交付形态

开发者拿到三样：git 仓地址 + 一条 install 命令 + 匿名令牌自动获取
（零交互，量大升级）。装完即用：知识层匿名可用，提交声音那一步自动领令牌
——引导（devkit error-table 模式）内建。归因（D-attrib-binding-1，2026-11-16 拍板 A）：
产品由插件从用户原话解析（引擎名录别名，唯一命中才采信；歧义落 UNKNOWN 不猜）；
install 的 `--product` 是**可选先验**，且只在**原话出现自指**（"你们家/这个产品/本平台…"）
时生效——本机绑定产品可由 `vod_devkit_info` 回执的 `manifestSummary.product` 查到，
没有自指就回到"先问一次"。

**分发红线（D-key-guard-2，2026-11-05 拍板）**：key 落在哪台机器，哪台
机器就是信任边界——对外分发的插件产物禁止预置任何 key（env/配置/install
注入均不允许），发版检查产物不含 VOD_JAVA_API_KEY 字面值。三档信任模型：
①终端用户=匿名令牌（唯一对外分发形态）②宿主平台=host key 只配宿主
服务端，插件经代理访问 VOD ③VOD 运营=formal key 自用。key 注入只允许
发生在运营/宿主运维自己的机器，任何"装完即有 key"的分发形态=违规。

## 里程碑

- ✅ 采集闭环端到端（测试环境，v0.1.0 起）
- ✅ 已发布多版（当前 0.5.x 线）：npm 双包（主包 + dsh 壳）、多宿主安装器/巡检/doctor、
  dsh MCP 模式、机器级匿名令牌、两段式草稿、行为回归套件与退出码分档
- ✅ 引擎侧已合 dev（MR !152 线）：VOD-KEY（多 key+meta 端点+匿名令牌）、
  VOD-VOI（囤积端点+收发分离）；产品归因 normalizeLoose 不设白名单
  （AIShell 等未注册产品落 UNKNOWN 档不拒收）
- ✅ 线上引擎：vod-dev.topxtopx.com（本机 doctor 常显可达）
- ✅ GitHub 公开镜像 + npm 壳已落地
- ○ 待做：签名回执（用户自助前置）
