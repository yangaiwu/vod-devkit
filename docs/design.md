# vod-devkit 插件化技术设计

- 需求：docs/vod-devkit-plugin/proposal.md（VOD-PLUGIN）
- 版本：v0.1（2026-11-03）
- 状态：待评审
- 参考实现：huaweicloud-devkit v2（55f53ad0）

---

## 一、总体架构

一个引擎，两张脸；插件是薄壳，不复制业务。

```
vod-devkit（可分发插件包，目录随本设计落仓）
├── bin/vod-devkit            # 安装器 CLI
├── vod_mcp/                  # MCP server（stdio，薄壳；双后端出口见下）
│   ├── server.py             # 工具注册与调度（握手时记录 clientInfo）
│   ├── tools.py              # 5 个工具 → api.py 调用链
│   ├── packs.py              # VOD_PACKS 裁剪：core/workflow/kb
│   └── provenance.py         # build-info 读取 + 宿主身份（clientInfo）
├── build-info.json           # 构建时烧录（git commitSHA/version/time）
├── skills/
│   ├── vod-core/SKILL.md     # 元技能：路由入口（对齐 huaweicloud-core）
│   ├── vod-category-matching/
│   ├── vod-problem-classification/
│   └── vod-scoring-rules/
├── safety/
│   ├── policy.json           # 声明式护栏（对齐 devkit safety/policy.json）
│   └── rules/vod-risk-rules.json
├── contract/
│   └── tools.schema.json     # 工具契约唯一事实源（JSON Schema，实现侧生成/校验）
└── integrations/
    ├── hermes/               # manifest + hooks（首个目标）
    └── opencode/ codex/      # 有真实消费者再补
```

单上游出口（方案 A 收敛后）：
  java：VOD_JAVA_API_BASE + VOD_JAVA_API_KEY（ExternalApiKeyFilter Bearer）
        → POST …/external/voice/submit（提交）+ …/external/token（令牌）
  统一出口 _http() 一律携带 Authorization（E1 修复；协议级测试以真
  HTTP 服务器锁死头/路径，永久回归门）。
  workflow 后端已随方案 A 删除（E2 的双后端拓扑成为历史，git 可查）

护栏作用域（E4 修复）：文本 deny 规则只扫结构性字段（scene/tags/query/
product…）；voices[].content 与 data 是用户原话，不进文本规则——
拦"凭据读取意图"不误杀"反馈内容引用凭据"（S4/U23 锁定）。

安装预置（方案 A 后）：preset=collect（core+collect+knowledge 可选）；
full 已删。技能拷贝按 packs 过滤；manifest 记录 preset。

依赖边界铁律：
1. vod_mcp 只允许 import workflow/api.py 的 HTTP 客户端，禁止 import 引擎内部模块
2. 外部 agent 无 DB 直连路径（护栏 deny 兜底）
3. 任务 ID（引擎任务表主键）是唯一对账主键，工具返回一律携带

## 二、MCP 工具契约

契约单一事实源：全部工具 schema 以一份 JSON Schema 契约文件
（safety 同级：contract/tools.schema.json）为唯一事实源，Python 实现
（以及将来任何宿主适配壳/TS 实现）均从同一份契约生成或校验，禁止两边
各自手写。跨语言边界的类型漂移由契约文件+CI 对账兜住（业界混合架构
的通行纪律：字段变更只改契约，实现自动跟进；golden fixture 校验入
pytest）。

### 2.1 vod_run_analysis（写，confirm）

入参：`product_profile`（string，须在白名单）、`source`（string，数据来源标识）、
`max_voices`（int，≤上限，默认 500）。
出参：`taskId`、`status`、`createdAt`。
调用链：工具 → POST api.py /analysis/run → 引擎建任务行 → 返回 taskId。
护栏：confirm 规则命中须用户确认；条数超上限 deny；并发>1 排队（引擎串行）。

### 2.2 vod_task_status（读）

入参：`taskId`。出参：`taskId`、`node`（当前节点）、`status`、`updatedAt`。
调用链：GET /analysis/status/{taskId}，直读引擎任务表。

### 2.3 vod_task_result（读）

入参：`taskId`。出参：报告路径/URL、评分汇总、高价值条数。
调用链：GET /analysis/result/{taskId}。与 vod-system 前端同源同结果。

### 2.4 vod_kb_search（读）

入参：`query`（string）、`top_k`（int，默认 5）。
出参：命中卡片列表（title/snippet/source_path）。
调用链：→ workflow/src/kb_precision_retriever 三层匹配（关键词→TF-IDF→LLM）。

### 2.5 vod_devkit_info（读，core pack 常驻）

入参：无。
出参：`version`、`commitSha`（读包内 build-info.json）、`packs`、
`hostClient`（MCP initialize 握手的 clientInfo：name/version）、
`manifestSummary`（安装时 target/installedAt，读 install-manifest.json）。
调用链：纯本地读，零网络零引擎依赖。packs 裁剪后始终保留（对齐
devkit 元技能常驻语义）。

## 二·五、安装溯源与宿主感知

对齐需求文档三·五节。三份凭证、两个校验点：

1. **build-info.json（包内，构建时烧录）**：构建脚本读
   `git rev-parse HEAD`（要求工作区 clean，dirty 即构建失败）写入
   commitSha/version/builtAt。内容与 SHA 绑定：改内容必换 SHA。
2. **install-manifest.json（安装时落目标侧）**：source 段直接复抄
   build-info 的 commitSHA 与 origin remote/ref + target（宿主探测结果）
   + installedAt + packs。
3. **clientInfo（运行时握手）**：MCP 协议 initialize 必带客户端
   name/version，server.py 在握手处理里记录到会话状态，
   vod_devkit_info 据此返回宿主身份。

校验点：

- `vod-devkit verify`：git fetch origin 后 `git cat-file -e <SHA>^{commit}`
  确认 commit 存在 → 比对包内 build-info 与安装侧 install-manifest 的
  SHA 一致 → 一致=可信；commit 不存在（被 force push 改写）或不一致
  =篡改告警，退出码非零。主键口径：commitSHA（40 位），不比对 tag
  （tag 可被移动，commit 不可漂移）。
- MCP 握手自报：每次会话启动即获得宿主身份，无需任何上报通道
  （遥测回传不做，需求已决策）。

防漂移：分发锁定 --ref/--version（默认跟踪 git tag），不用浮动拉取；
已装版本可复现 = `git show <SHA>` 即该份插件全部源码。

### 2.5b vod_auth_status（读，core pack 常驻）

入参：无。出参：javaKey/workflowKey 各自 {configured, fingerprint(8位),
base}（明文禁止）+ packs + 缺 key 时三步引导（令牌/升级/宿主，
对齐 devkit error-table"步骤=可执行动作"纪律）。
调用链：纯本地读+运行时状态，探测上游时轻量 ping。

### 2.5c 产品归因（_resolve_product）

三层：runtime.json product（安装绑定）> 调用方显式 > 报错 -32013
（引导 install --product / 传参 / 问用户）。静默默认禁止。
别名归一对齐引擎（modelarts→MaaS）。

### 2.6 vod_submit_voices（写，confirm，collect pack）

后端=java（契约 backends 标注）。

**零字段令牌链（缺 key/401 时，仅首条触发一次）**：
无 VOD_JAVA_API_KEY 或收到 401(-32012) → POST /external/token
（空 body，引擎侧 IP 限频，VOD-KEY 端点）→ 令牌回填运行时 +
落 runtime.json（token_tier=anonymous）→ 重试提交 → 成功。
令牌端点不可用 → 结构化引导错误（三步），不裸 404。
设计依据见 proposal 三·四节方案比对：进门零摩擦，问责靠档位。E3 修正待落引擎侧文档：查重依赖提交方
外部去重键或内容 hash——服务端生成 voice_id 使 saveCollectRecord 的
voice_id 查重不生效（详见 VOD-VOI 文档修正）。

入参：`voices[]`（content 必填 ≤2000、scene/userType/tags 可选）、
`confirmed`（逐次同意护栏）。
出参：`accepted`、`voiceIds[]`（引擎生成，第二类对账主键）、`rejected[]`。
调用链：工具 → 服务端注入 source=握手 clientInfo.name（忽略调用方参数，
防来源伪造）→ POST Java /external/voices（VOD-VOI 实测修正后落点：
复用 DataCollectService.saveCollectRecord 入库+查重，voiceId 用既有
voice_id 体系；鉴权走 ExternalApiKeyFilter Bearer，多 key 防线 P1）
→ 逐条回执（1=新增/0=跳过均回执，voiceId 对账）。
护栏：confirm 逐次 + 单批 ≤50（maxVoicesPerSubmit）+ 凭据/PII 文本规则。
配套技能 vod-feedback-collect：识别用户反馈意图→征得同意→结构化提交→
voiceId 回执对账。

## 二·八、认证与 key 交付（含方案比对结论）

方案演进：A 宿主代管制（户口=宿主数，但只覆盖被集成宿主）→
B 自助注册制（会把人跑掉，否决为入门方案）→ **C 零字段自动令牌
（定稿入门）**。完整比对表见 proposal 三·四节。

实现件：
1. 令牌签发端点（引擎侧 VOD-KEY）：POST /external/token 空 body，
   IP 限频，返回 {token, dailyLimit}；落 t_vod_api_keys（tier=anonymous）
2. 令牌回填链（插件侧已实现）：_fetch_anon_token → JAVA_KEY 回填 →
   _save_runtime 持久化（token_tier=anonymous）
3. vod_auth_status（插件侧已实现）：指纹化输出+引导
4. 升级/宿主档：同一张 key 表不同 tier，管理台处置（吊销/调配额）
5. fingerprint 纪律：所有 key 输出点（status/doctor/manifest）一律
   sha1(key)[:8]，明文禁止

错误引导（devkit error-table 模式，已实现）：
- 令牌不可用：code -32012 + 三步引导文案（自动令牌/升级/宿主）
- 步骤=可执行动作，禁止"请参考文档"式死链接

## 三、语言选型（vod_mcp 用 Python，依据与推翻条件）

业界分工共识（2026 生产实践）：编排层默认 Python，插件/MCP 层按工具性质
分治——I/O 型偏 TS、数据/ML 封装型偏 Python，MCP 协议使插件层语言
切换成本趋近改配置（窄腰解耦），故语言决策重量低、可逆。

按工具性质如实判定：本插件 5 个工具全部为 HTTP 转发（I/O 型），名义
默认落在 TS 一侧——此判定写明，不回避。仍选 Python 的依据（按权重排序）：

1. 宿主 hook 层：首个消费者 Hermes 的 hook 机制是 .py；壳与 hook 同仓
   同语言，维护面减半（devkit 同款纪律：hook 语言跟宿主走）
2. 团队与仓库现状：VOD 仓 49 个 Python 模块+pytest+venv；TS 壳=第二套
   工具链+第二套 CI，为一个 5 工具的薄壳不成立
3. 决策重量低且可逆（MCP 窄腰）：此处选"顺手的"而非"名义默认的"是
   理性排序；真要换，适配壳层逐个换不影响契约与宿主配置

弱依据（已降级，不再作为主论据）："薄壳与引擎同语言"——引擎在 HTTP
对面，HTTP 本身语言中立，跨语言税仅存在于直接 import（设计已禁止）。

推翻条件（满足任一重评估）：JS 系宿主成为主力且要求 .mjs hook 深度
集成；需要发 npm 包进入 dsh 类生态分发；工具面膨胀到 15+ 且高频迭代。
宿主矩阵分流纪律：MCP 客户端宿主（AIShell/CodeArts/通用 agent）走
stdio 直连零语言成本；宿主原生格式（dsh 的 npm 包等）单独写宿主语言
的薄适配壳，不反推核心换语言。

## 三·五、packs 裁剪

`VOD_PACKS` 环境变量，逗号分隔，默认全装：

| pack | 内容 | 启用工具/技能 |
|---|---|---|
| core | 路由元技能 + 护栏 | vod-core |
| knowledge | 纯技能零工具 | 3 个领域规则技能（采集预分类，零依赖） |
| collect | 反馈采集 | vod_submit_voices + vod-feedback-collect 技能 |

实现：packs.py 一张启用表，未启用的工具不注册、技能不落盘（与 devkit
DEVKIT_PACKS 同语义）。

## 四、安全护栏（声明式）

policy.json 规则集（severity: deny / confirm / warn）：

| id | severity | 匹配 | 动作 |
|---|---|---|---|
| vod-write-run-analysis | confirm | tool==vod_run_analysis | 需用户确认 |
| vod-voices-limit | deny | max_voices>上限 | 拒绝执行 |
| vod-no-db-direct | deny | 文本含 mysql/jdbc/t_vod_ 直连模式 | 拦截 |
| vod-no-credential | deny | AK/SK/token 凭据模式（清单抄 devkit policy.json） | 拦截 |

执行点：MCP server 工具入口前置检查（Python 侧）；Hermes 集成另挂 hook
（对齐 devkit hooks 双实现思路，Hermes 侧用 .py）。

## 五、安装器

`vod-devkit install --target <hermes|opencode|codex> [--ref <git ref>]`：

1. 探测目标（0/1/N 三分支，对齐 devkit 行为：交互式多选，非交互式报错列出目标）；
   探测依据=各产品特征目录/配置文件路径，探测结果即宿主感知的 target 值
2. 写 mcpServers 配置（stdio，command=包内 vod_mcp 启动入口）
3. skills/ 落盘到目标技能目录（只拷启用的 pack）
4. 落 install-manifest.json（见二·五节：source/target/installedAt/packs）
5. doctor / status / verify / update / uninstall 子命令：
   - doctor：配置+skills+build-info 三者齐全且 SHA 一致
   - status：打印 manifest 全量（版本+来源+宿主+packs）
   - verify：见二·五节校验流程
   - uninstall：校验 manifest 后清配置+skills+manifest，引擎与任务数据零接触

安装器自身不触网拉包（包来自仓库构建产物或本地目录），避免 devkit
npx 浮动版本的来源不可控问题。

## 六、质量与验收

- 交付纪律：仓库内只含插件产品代码 + 随 CI 跑的 pytest 用例 + 本对文档；
  验收脚本/环境探测工具不入库，用例清单以 proposal.md 第四节为准
- pytest：工具契约（mock api.py）+ 护栏规则命中 + packs 裁剪 + 安装器
  uninstall 幂等
- 走完整调用链验证后断言才能落文档（入口路由→api.py→任务表）
