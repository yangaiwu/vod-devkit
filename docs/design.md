# vod-devkit 插件化技术设计

- 需求：docs/proposal.md（本仓，随实现演进增补 S 号）
- 状态：**现行设计**（结构以 docs/architecture.md 为准；本文保留各轮决策与判据）
- 参考实现：huaweicloud-devkit v2（55f53ad0，2026-11 初版对标；差异见 decisions.md）

---

## 一、总体架构

一个引擎，两张脸；插件是薄壳，不复制业务。

```
vod-devkit（可分发插件包；仓内布局 vs 载荷布局见 architecture.md）
├── bin/vod-devkit            # 薄壳入口：找解释器 + 显式设两个根 + 透传子命令
├── npm/cli.js                # npx 引导器（同一薄壳）
├── src/vod_mcp/              # 运行时（MCP server、适配器、packs 包、provenance…）
├── src/vodkit_cli/           # 安装器 CLI（install/status/doctor/verify/update/…）
├── assets/                   # 项目级资产真源：skills/ contract/ safety/
├── integrations/<host>/      # 宿主规格 host.json + 宿主侧 hook 脚本（hermes/hooks）
├── packages/dsh/             # dsh 壳（独立 npm 包：Node 半 + 浏览器半）
├── plugins/vod-devkit/       # 发布树（生成物，零提交）
├── scripts/                  # 生成器与门禁（sync_plugin ↔ verify_copies、巡检、发布…）
└── tests/                    # pytest（含结构/范围/用例花名册/声明对账门禁）

载荷/发布布局仍是根级平铺（vod_mcp/ skills/ contract/ safety/ hooks/），
由 paths.ASSETS 与 sync_plugin 物化——改仓内布局不要连带改载荷布局。
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
（safety 同级：assets/contract/tools.schema.json）为唯一事实源，Python 实现
（以及将来任何宿主适配壳/TS 实现）均从同一份契约生成或校验，禁止两边
各自手写。跨语言边界的类型漂移由契约文件+CI 对账兜住（业界混合架构
的通行纪律：字段变更只改契约，实现自动跟进；golden fixture 校验入
pytest）。

### 2.1-2.4 已删除（2026-11-03 方案 A 拍板，git 留档 f1103df）

vod_run_analysis / vod_task_status / vod_task_result / vod_kb_search
四工具已删除：运营能力归 vod-system 前端（受众不同+职责耦合+负复杂度，
净删 304 行）；kb 知识改 skills 形态本地分发（零工具零依赖）。历史契约
详见 git 留档；现存工具面=2.5 info / 2.5b auth_status / 2.6 submit_voices
/ 2.5g list_submitted，共 4 个。

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

### 2.5c 动态元数据（_load_meta）

GET /external/meta → {products:[...]}；缓存 runtime.json meta_cache
（TTL 24h）；不可达→_META_SNAPSHOT 快照+stale=True。所有引导文案
与 auth_status 携带 stale 态。设计依据：硬编码枚举必漂移（技能过期
+白名单常量为实证）；/external/products 是报告侧全集不可用作
submit 源——meta 必须以 submit 校验常量为源（引擎侧 VOD-KEY 交付）。

### 2.5d 传输协议守卫（_http 前置）

http 仅限本机回环（127.0.0.1/localhost/::1——recorder 测试与同机引擎）；
非回环 http 拒绝（-32014，引导 https 配置）——Bearer key 不得明文过公网。
https 全场景放行（测试环境 TLS 链路已实测：taskId=419/420）。
双向测试锁死（U38）：http 公网必须拒、http 回环必须放行（报 -32001
而非协议拒绝）。

### 2.5e 身份模型（归属/认证分离）

归属（谁提的）=数据字段：voices[].userType/customer 随声音入库，
引擎侧不建用户体系；授权（谁在调）=接入方 key 三档（匿名令牌/
正式/宿主）。工具 Schema 零身份参数（模型不可伪造归属）；可信层
注入仅作用于 key/product（env>runtime>快照）。失败关闭：无 key 且
令牌不可达→拒写。内容边界：content ≤2000（逐条校验落码），
scene ≤128。签名回执记 P2 前置（用户自助查询/撤回的前置条件，
见 proposal 三·四e）。

### 2.5f 产品归因（_resolve_product）

四层（D-attrib-binding-1 起的口径）：原话字面唯一命中 > 调用方显式 > 会话记忆 > 安装绑定先验；
都没有就**问用户一次**。本地不再有 `-32013` 归因拦截码（旧三层含报错码，已废除）。静默默认禁止。
别名归一对齐引擎（modelarts→MaaS）；白名单经 meta 动态校验
（快照兜底时容忍提交并标 stale——引擎侧最终校验为准）。

### 2.5g 提交账本与查询（层级①）

_ledger_append：submit 成功后落 runtime.json submissions（cap 200
环形截断）；纪律=文件读改写+只动 submissions 键（防陈旧配置整体
回写覆盖其他键——该缺陷曾被测试实锤并修正）。vod_list_submitted
（只读，collect pack）：limit 1-100，最新在前，scope 字段明示
"本机记录（换机不保留）"。层级②引擎级（GET /external/voices，按
key 过滤）随 VOD-VOI；层级③用户自助维持 P2（签名回执）。

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
   IP 限频；落 t_vod_api_keys（tier=anonymous）。**返回契约=
   ApiResponse 信封 {"code":200,"data":{"token":...}}（D-anon-verify
   2026-11-05 真机实锤：插件顶层取 token 曾恒 None → 无 key 首提必
   -32012；解析收敛在 _extract_anon_token 单函数，信封+扁平双兼容）**
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

按工具性质如实判定：本插件的工具面全部为 HTTP 转发（I/O 型），名义
默认落在 TS 一侧——此判定写明，不回避。仍选 Python 的依据（按权重排序）：

1. 宿主 hook 层：首个消费者 Hermes 的 hook 机制是 .py；壳与 hook 同仓
   同语言，维护面减半（devkit 同款纪律：hook 语言跟宿主走）
2. 团队与仓库现状：VOD 仓 49 个 Python 模块+pytest+venv；TS 壳=第二套
   工具链+第二套 CI，为一个薄壳不成立
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
| core | 路由元技能 + 护栏 + 版本提醒 | vod-core 技能；vod_devkit_info / vod_auth_status / vod_check_update |
| knowledge | 领域规则技能 + 披露面 | 2 个规则技能（问题分类/评分）+ vod_list_skills / vod_retrieve_skill（只读、零上游） |
| collect | 反馈采集 | vod_submit_voices / draft / commit / list_submitted + vod-feedback-collect 技能 |

实现：packs.py 一张启用表，未启用的工具不注册、技能不落盘（与 devkit
DEVKIT_PACKS 同语义）。

## 三·九、dsh 薄壳形态（R3 已落地，2026-11-03 真机验证）

dsh 宿主不识 MCP，只认自家 cordis 插件协议——故以独立薄壳包 dsh/
（dsh-vod-devkit@0.1.0）承载同一采集语义。语言跟宿主走（Node ESM），
验证了「宿主原生格式单独写适配壳」的语言选型纪律。

结构：
- dsh/package.json：peerDeps=cordis/dsh-tools/schemastery（均 npm 公网），
  `dsh.bundle.patch` 指向 cordis.patch.yml
- packages/dsh/lib/index.js：cordis 插件入口（name/inject=['tools']/Config/apply）。
  **当前是 B 模式（0.5.10 起）**：壳只留 UI 半（`registerTools: false`），工具面由
  `@deepseek-ai/dsh-mcp-client` 的 MCP stdio 提供；缺该依赖时降级为壳自带的采集面
  （工具名 `mcp__vod-devkit__vod_*` 才是常态，壳自述工具名只出现在降级形态）
- dsh/cordis.patch.yml：bundle 激活声明（insert 条目）
- 审批：ctx.on('tools/pre-execute') 对 submit 返回 kind:'ask'（dsh 原生
  审批通道，web 端弹卡片）——对应 MCP 形态的 confirmed 语义

配置面（schemastery，热改 volatile）：apiBase/apiKey(secret,role 指纹化)/
product（归因安装绑定层）/confirmWrites/timeoutSec。

与 vod_mcp 语义对齐（S16 回归约束）：voiceId 同构（f(source,content,nonce)，
同调用幂等跨调用保声量——与引擎端 VOD-VOI 确定性键是**分层而非分叉**：客户端
键=本地对账主键+重试幂等，引擎 /external/voices 忽略 body.voiceId 自算确定性
键查重 V9）、传输守卫同构（-32014：非 https 且非本机回环拒绝，Bearer 不得明
文过公网，2026-11-03 深审 D-dsh-1 落码）、PRODUCT_MAP 归一
（codearts→CodeArts，引擎大小写敏感实测；注：dsh 形态不拉 /external/meta，
PRODUCT_MAP 硬编码需随引擎 VodExternalProducts 手工同步——D-dsh-3）、归因三
层、批量/长度护栏、
无 key→匿名令牌兜底→-32012 引导、本地账本（data/runtime.json，cap 200
读改写只动目标键）。

实测坑（安装器/宿主适配必读）：
1. dsh plugin 子命令硬依赖 pnpm（先 npm i -g pnpm）
2. 只装包不激活：须 profile 层 cordis.patch.yml insert 条目
3. dsh-tools 强校验 output={schema,render} 双字段，缺 render 即 TypeError
4. 引擎 product 枚举大小写敏感且 400 无错误体（S13，根治在引擎侧）

冒烟验证链（.smoke/ 不入库）：mock ctx 加载→壳工具面注册（降级形态；B 模式走 MCP）→审批门禁
（ask/passthrough）→真实提交（taskId=425/426）→账本回读；另有真机
web 会话端到端（S12，taskId=427）。

## 三·十、dsh UI 部署配置通道（D-anon-ui，2026-11-05）

**机制**（逆向自官方 settings-account 的 __DSH_CONTACT_CONFIG__）：
server 半 `apply(ctx, config)` 里 `ctx.on("webserver/index-inject",
table => table.push({kind:"global", ...}))` 把部署配置注入页面全局；
client 半模块顶层读 `globalThis.__VOD_DSH_UI_*`（原 T7d 契约零改动）。

**键位分工**：
- `__VOD_DSH_UI_PRODUCT__` ← config.product：恒注入（安装必配，T7d）
- `__VOD_DSH_UI_BASE__` ← config.uiBase：仅跨域部署显式配置才注入；
  默认同源相对路径（宿主代理 /rest/）。**apiBase 是 server 半自用的
  绝对地址，禁止注入页面**（同源策略下浏览器 fetch 127.0.0.1 即
  Failed to fetch，公网实锤）。

**实现约束**：注入行由纯函数 `uiGlobals(config)` 计算（可单测，
test/d-anon-ui.test.mjs 契约锁：同源只注 product / uiBase 才注 base /
apiBase 永不注入 / 无 product 注空串供 fail fast）。

**过时口径警示**：VALID_PRODUCTS 拒收 AIShell 为 !152 前旧口径——
normalizeLoose 后不设白名单（未注册落 UNKNOWN 档+productRegistered
软标记）。文档与模型可见文本一律不得再使用"会被拒收"表述。

## 三·十一、反馈页面职责与历史面板（D-anon-ui 收口）

**弹窗=极简三件**：单输入框（voice_title=原文前 64 字）/
历史面板 / 提交。分类 chips 已撤（2026-11-05 用户拍板：n01 引擎
全量重判覆盖分类信号，UI 预分类仅 hint 且用户分不清边界——认知
负担换不来信号质量）。无去向说明、无复核说教、无内部机制词汇。

**历史面板（三主体边界实现）**：
- 数据源=本机账本（localStorage，不出浏览器）+ 本人令牌回执
  （GET /external/voices 按签发 key 过滤——层级②设计，无按 voiceId
  全局查询面，无枚举越权）；
- 顶部固定边界标注"仅保存在当前浏览器"（匿名档"我的"="本机的"）；
- `--no-local-ledger`（数据驻留）：server 半 uiGlobals 注入
  __VOD_DSH_UI_LEDGER_DISABLED__ → UI 停写账本+面板显式不可用
  （部署策略提示，不显示空列表）。

**UI 设备锚点**：getDeviceId 生成即纯 hex（32 位）——引擎
[0-9a-f]{8,64} 校验不过会静默降 legacy 锚点（签发 5 次/天打满）。

**SKILL 话术分层**（模型可见文本三层）：
1. 正向职责一句话（整理为一条声音+用户同意+提交+人话回执；模型
   只做识别意图/忠实转写/征得同意）+ 可判定触发条件清单；
2. 字段处理分级表 + 推断≠编造正反例 + 调用前三项预检 + 不追问原则
   （借鉴 gitcode-issue-creator 方法论）；
3. 禁令（不问产品/不自报归因/不暴露工具名与机制词/失败路径人话）
   作为上述三件事的实施边界，不是职责主体；
4. 追加反馈定性话术（S49-S53，2026-11-06 定稿）：确认环节用户追加
   表达时先定性再问——定性标注为 agent 理解并留纠正口子（「听
   起来更像…我理解得对吗」非事实断言，S50），确认范围仅两个
   真实可执行选项（都提/只提原句），极端选择（只提追加句）走
   括号兜底不进并列选项（S52），用户纠正定性后不辩论、按纠正
   理解走但 content 仍原话逐字（S53）；禁空头承诺：无引擎/插件
   制（如「过程反馈单独记录」）不得出现在话术选项里（S51，泛化
   纪律=D-option-executability-1：写选项前逐项问「用户选这项，
   代码路径在哪」，答不出=删）。承载=
   skills/vod-feedback-collect/SKILL.md 正文（双副本同步，
   test_collect_qualify 锁一致性与话术要素）。

**暂存恢复提示（S54）**：后台自动重试成功=完成用户已确认的
   提交指令（暂存仅产生于点提交后的技术失败分支），非新提交
   行为——补提示含逐条原话回显（方案 A 覆盖恢复场景），voice-id
   不出用户面（F2）、产品名不带（用户不感知归因）、无更正/撤回
   承诺（S51）。items 空值时话术降级为纯状态告知（残句防护）。
   承载=dsh/src/client.jsx（retryStashedSubmissions+FeedbackModal
   恢复旗标），ux-sync 回归锁。

**UI 形态**：弹窗 textarea resize:none（S55，用户拉伸角顶破布局）；
   widget E_AUTH 草稿兜底对齐（S57）。

**回执与安装面（S58/S59）**：回执话术=行为实况（S51 应用——
   匿名直建无审核闸，issue 链接只由 pollForReceipt 真实建成后
   补出）；installer dsh 块模板自带 name 绑定行（重装不吞，
   cordis.patch.yml 必须保持 `- insert:` 嵌套，打平=工具壳+UI
   双静默消失）。承载=bin/vod-devkit（块模板）+
   tests/test_installer.py name 断言 + ux-sync S51 回执锁。

**codex 熔断与恢复门禁（S60-S62）**：检测账本 ≥2 次未确认提交
   → 熔断切只读（packs 去 collect+标记）；恢复门禁双层=install
   拒装 + serve 运行期 enabled_packs 强制降级（堵 VOD_PACKS 绕
   过）；--ack-suspension=删标记+审计日志（真解除语义）。
   承载=bin/vod-devkit（install 门禁+ack 解除）+
   vod_mcp/packs.py（运行期降级）+
   tests/test_installer.py（门禁四态+运行期降级两锁）+
   docs/decisions.md D-codex-circuit-breaker-1（立项表述纠偏：
   token 化=最强摩擦+审计链非硬保证；恢复门禁前置）。

**复现步骤 AI 追问（S63 → S64-S66 已落地，D-followup-impl-2）**：前置规范
   （业界对表 D-followup-design-1：可选增强/话术固定化/数据分层/
   诚实回退四约束）——引擎承载就绪后经负责人批准落地（2026-11-08，
   A1 确认环节合并一问 / A2 MCP+dsh 壳，UI 壳红线不动）。承载映射：

| 用例 | 承载 |
|---|---|
| S64 透传正例 | tools.py `_followup_fields`（单源）+ tests/test_followup.py 透传/两段式两例 + packages/dsh/test/followup.test.mjs 行为级 |
| S65 键集合零漂移 | 拒答词集兜底（_FOLLOWUP_DECLINES）+ test_followup 键集合断言（{title,content}）+ 超 2000 截断例 |
| S66 话术固定化 | 固定问句逐字锁（contract description 恰 1 次）+ SKILL 双副本 + dsh 壳描述；desc 预算门禁（≤1500）复验 |
| S67-S70 触发判定块 | SKILL 三层判定块逐字锁（test_followup_skill_judgment_block_locked）+ 契约跳过句（test_followup_skip_clause_in_contract）；dsh 壳 desc 预算 1495/1500 无余量不塞跳过句——dsh 宿主由原生技能层（判定块全量）承载 |
| S72 反截断红线 | SKILL 补充句整体=content 逐字锁（test_anti_truncation_redline_locked）——宿主会话日志取证（opencode.db part 表） |
| S73 拼接判定例 | 逐字=含语气词/标点，禁删啊补句号式改写（test_concat_verbatim_judgment_example_locked） |
| S71 问卷化 tripwire | 话术载体结构词黑名单锁（test_followup_questionnaire_structure_words_banned）——自由生成追问清单的门禁化拦截 |
| S67-S70 二次微调 | 跳过条件收窄（新字段来源唯一=固定追问原样回答，引导补充的操作/期望留 content 不回溯）+「未回应/泛化抱怨」判定例+一句话口径可测原文（payload 键/issue 补充段/来源注记三处诚实回退）——边界锁 test_followup_boundary_refinement_locked；契约 939/1500 |

   数据分层：追问答案只进 reproSteps/expectedBehavior 独立字段
   （引擎 V20261106110000003 列 → issue 渲染带「（用户追问补充）」来源
   注记），content 原话逐字不变（回归断言）。诚实回退：未答/拒答=字段
   不上送，issue 侧整段不出现不注记（引擎 I21/I22 对应）。ux-sync S63
   tripwire 保留：禁的是"承诺未来会追问"的空头话术，实际问句不触雷。

## 四、安全护栏（声明式）

policy.json 规则集（severity: deny / confirm / warn）：

| id | severity | 匹配 | 动作 |
|---|---|---|---|
| vod-write-submit-voices | confirm | tool==vod_submit_voices 且 confirmed=false | 需用户逐次确认（-32011 引导重传 confirmed=true） |
| vod-voices-batch-limit | deny | voices 条数 > 50 | 拒绝执行 |
| vod-no-db-direct | deny | 文本含 mysql/jdbc/t_vod_ 直连模式 | 拦截 |
| vod-no-credential | deny | AK/SK/token 凭据模式（清单抄 devkit policy.json） | 拦截 |

执行点：MCP server 工具入口前置检查（Python 侧）；Hermes 集成另挂 hook
（对齐 devkit hooks 双实现思路，Hermes 侧用 .py）。

## 五、安装器

`vod-devkit install --target <hermes|opencode|codex|dsh> [--ref <git ref>]`：

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

### dsh target（D-dsh-install-1，2026-11-06 拍板 A）

`install --target dsh --profile <p> --product <产品>`：--profile 必填
（进入任何安装动作前校验）；产品安装期硬校验复用 _validate_product_or_exit
（与三壳统一口径），校验先于 `dsh plugin add`（拒绝=无半成品）；add 后
幂等 upsert `~/.dsh/profiles/<p>/cordis.patch.yml` 的
`- id: vod-devkit: config: {product, apiBase}` 段——该 config override
是 dsh 工具壳读取归因/引擎地址的唯一运行时通道（真机实证 dsh 0.2.1-rc.5，
启动 banner+桩引擎提交链）。块边界扫描单一实现（_find_dsh_block）供
upsert 与 uninstall 共用；dsh 缺失 exit 2、add 失败 exit 1、配置写失败
exit 1 附可照抄的手动修复格式。manifest 增 dshProfile 键（golden 已重录）。
退出码约定不变：用法/校验=2，环境/运行失败=1。

## 六、质量与验收

- 交付纪律（S234 校正措辞，与现状对齐）：仓库内 = 插件产品代码 + 随 CI 跑的 pytest 用例 +
  本对文档；验收/环境探测脚本放 `scripts/`（`host_matrix` / `smoke_hosts` / `probe_tools` /
  `e2e_*`），**不进 `package.json` 的 `files` 白名单**（随包发不出去），也不是交付物清单的一部分；
  用例清单以 proposal.md 第四节为准，禁止把一次性探针塞进交付面
- 面向用户的用语纪律是**禁词表**，不只是「别科普」（S237）：技能里原有「不向用户解释机制」
  只是职责边界，模型仍会说「已按 X 归因」（真机 C3/C5 实测）。现口径：技能写死禁词表
  （归因/白名单/令牌/配额/幂等/引擎/端点/提交链/囤积/草稿/主键/名单/voiceId/插件/MCP）+
  三条替换示例（「产品归属：X」「已受理，请确认是否提交」/整句删掉只说结果）；e2e 的
  `FORBIDDEN_REPLY_WORDS` 同步扩充，门禁锁「技能有表 + 判定函数真能报出来 + 不误伤回执话术」
- 行为级 e2e 的引擎行必须收窄到本轮 voiceId（S236）：`engine_rows_since(t0)` 返回时间窗内
  **所有**行，并发提交/人工验证声音会混进来；旧实现拿它们做原话保真比对，把外来行报成
  「改写」（实测 C1/C4 两条假红）。现口径 `scope_engine_rows()`：以本机账本本轮回执的
  voiceId 为白名单收窄，并在回执 `notes` 里写明排除了几行；账本无回执时保持原样，交三态
  判定报「不可判」。**e2e 不得与其他提交并发跑**——收窄只能排除异 id 行，同 id 同文的
  重复提交仍会干扰，跑前确认窗口干净
- 功能级验证入口单一来源（S234）：`host_matrix.resolve_entry()` 是"宿主 → 它自己配置里的
  launch"的唯一解析点，巡检与 `scripts/probe_tools.py` 共用；环境变量两种键（`env` /
  `environment`）都要读——三个宿主用后者，裸探针只读前者会把 10 工具报成 12（实测）。
  探针只调只读工具，不提交、不落库
- pytest：工具契约（mock api.py）+ 护栏规则命中 + packs 裁剪 + 安装器
  uninstall 幂等
- 走完整调用链验证后断言才能落文档（入口路由→api.py→任务表）
- description 截断预算门禁（tests/test_desc_budget.py，D-desc-budget-1，
  2026-11-06）：①同意先决条件（确认纪律）必须落在前 500 字符内
  （dsh 固定 500 字符窗口=最严截断；Codex 5440 硬预算曾把 119 技能中
  103 个截到均值 232 字符——openai/codex#24299，被截断即对模型不可见）
  ②description 总长 ≤1500（现状 contract 665/dsh 组合 ~1285，防无界
  增长挤占宿主预算）③双载体同测（contract JSON=python 单一事实源 +
  packages/dsh/lib/index.js 组合串提取）④归因口径漂移锁（禁旧宽容口径句回流）。
  随 pre-push 门禁自动生效

## 七、分发形态实现（D-key-guard-3，2026-11-05）

对应 proposal.md 第七节（需求/用例 DG1-DG9）。实现落点：

### 形态位

- 写入：`install --distribution devkit|preset` → install-manifest.json
  `.distribution`；缺省 devkit（存量安装读不到该字段=devkit，行为不变）
- 读取：bin `_distribution()` 与 vod_mcp/tools `_distribution()` 各自实现
  （bin 面向子命令，tools 面向运行时；两处同语义：manifest 缺失/损坏→devkit）

### 逐条分支

1. **key 禁随包**（bin cmd_install）：distribution=preset 时 `os.environ.pop`
   VOD_JAVA_API_KEY 并 stderr 告警——installer 的 env 透传天然拿不到，key
   进不了宿主配置文件；devkit 形态不动
2. **update 禁用**（bin cmd_update）：preset → 打印"随 agent 发版管理"直接返回
3. **verify 降级**（bin cmd_verify）：preset → 只比对 manifest.commitSha 与
   build-info.commitSha（本地完整性），一致即 OK（输出标 unchecked），不一致
   FAIL（产物混装/篡改）；不触 git——客户机离线可用
4. **首启残留清理**（tools._ensure_first_boot，server.main 启动时调）：
   - runtime.json 无 firstBootAt 标记 = 首启（或残留）；
   - preset + 携带状态键（java_key/token_tier/install_nonce/submissions/meta_cache）
     → 构建机残留 → `_save_runtime(replace=True)` 整体重建（保留非状态键
     product/java_base 等）+ firstBootAt + 日志告警；随后重新自领匿名令牌/nonce
   - devkit 或无状态 → 只补 firstBootAt 标记
   - 处置选自动重生成不选拒绝启动：残留全为本机可再生数据，伤害半径为零
   - **时间戳启发式被否**：update 每次重烧 build-info/manifest，"nonce 早于
     manifest"会误伤全部正常自更新的安装——判定只认 firstBootAt 标记缺失
5. **账本出口**（tools._ledger_append）：runtime.json `local_ledger: false`
   （install --no-local-ledger 写入）→ 提交不落账本；vod_list_submitted
   返回空。留痕是可选项不是义务（企业数据驻留）
6. **日志轮转**（tools._log 统一出口）：>1MB 截断，尾部 200KB 迁 .old，
   新写追加；_http 与 _warn 两处共用（原来两处各自裸 append）

### 重构实锤（测试抓出的存量缺陷）

- `_runtime_cfg` 与 `_save_runtime` 路径双写（一个用 `Path(__file__)` 直算、
  一个走 `_runtime_path()`）——注入/重定位场景读写分叉。修：路径单源，
  `_runtime_cfg` 改走 `_runtime_path()`，且定义上移至 `_RT` 初始化之前
- `_save_runtime` 原只有合并语义无法删键——残留清理需要删键，新增
  `replace=True` 整体重建参数（默认 False 行为不变）

### 与既有机制的边界

- preset 不改认证链本身：匿名令牌自领/fail fast/探针/写后验全部继续生效
  （DG9：devkit 形态注入 key 的运营场景零变化）
- preset 不动 CORS/浏览器通道（dsh UI 形态若被产品集成，走 cordis.patch.yml
  config 注入检查，红线同源——配置段含 key 即违规，后续 UI 集成立项时对齐）

## 八、Codex 原生插件接入（D-codex-plugin-1，2026-11-05）

### 机制（codex CLI 0.166 实测）
- `codex plugin marketplace add <root>`：root 必须含 `.agents/plugins/marketplace.json`
  （本仓 root=plugins/ 目录）+ `plugins/<name>/` 插件目录
- 插件清单 `.codex-plugin/plugin.json`（官方兼容布局，便携版=根 plugin.json+
  extensions.com.openai+agents/openai.yaml，暂不迁）：声明 `skills:"./skills/"`
  与 `mcpServers:"./.mcp.json"`；interface 元数据（displayName/defaultPrompt/
  capabilities）为展示层
- Skill 渐进式加载：模型只见 name+description 元数据（description=触发条件），
  匹配才读全文——SKILL.md 的 description 必须写清触发，细节在 body
- **宿主能力判定纪律**：结论前必须翻全 `--help` 子命令树（"codex 无 skill"
  的误判即因只探测了 mcp/exec 单点）

### 约束三层分工（官方 skills 概念直接对应）
| 层 | 载体 | 承载 |
|---|---|---|
| 硬约束 | MCP 工具描述（contract 单一事实源，话术前置防截断） | 归因不问用户/S1 自报不采信/禁内部机制 |
| 工作流 | 插件 SKILL.md（vod-feedback-collect 全量） | 触发三条件/字段分级/推断≠编造/预检/回执话术 |
| 冗余 | AGENTS.md | 已撤（被原生 skill 取代，仅保留 strip 清理旧装机残留） |

### 自包含与缓存治理（devkit 对表采纳）
- 插件包自带 `vod_mcp/`（`scripts/sync_plugin.py` 同步+烧录 build-info.json）
  ——.mcp.json 相对路径 `python3 ./vod_mcp/server.py` + cwd，缓存隔离安装后
  仍可拉起，去 npm -g 全局命令前置
- install 前清 `~/.codex/plugins/{marketplaces,cache}/vod-local`（缓存不自动
  失效，不清=重装旧版残留）
- 版本真源四点同步：package.json/pyproject/__init__/contract（契约 version
  曾滞留 0.1.0 致 vod_devkit_info 假象）——release.sh 硬断言 4 处
- 安装校验探针全程同设备锚点（X-Vod-Device-Id+UA，token/meta 一致；S1 设备
  绑定；每次装机新锚点=一次校验一枚令牌额度）

## 九、Hermes/OpenCode 接入对照与取舍（D-drift-lock，2026-11-05 devkit 对表）

### 与 huaweicloud-devkit v2 的形态差异
| 维度 | devkit | 本仓 | 取舍依据 |
|---|---|---|---|
| hermes skills 分发 | MCP 数据下发（list/retrieve，防拷贝漂移+pack 动态门控） | 文件拷贝+**漂移锁**（manifest.skillHashes→doctor 比对） | 规模是决定变量：几十个动态技能 vs 5 个静态技能；拷贝够用但漂移必须可检（vendor 漂移实锤）；架构迁移挂账到技能增长时 |
| 护栏层 | 宿主 PreToolUse hook（2665 行，拦 shell 里 hcloud 绕行路，防 ANSI-C/引号/bash -c 包装逃逸） | server 内 policy+confirmed | **威胁面决定**：hook 价值=封"MCP 旁的 shell 直达破坏面"绕行路；囤积链无破坏面（绕过 MCP 直发=自愿提交），无路可封不建墙；演进闸=出现破坏性写先 token 化审批。devkit 自己也承认 hook 不可移植（server 内同 policy 双实现） |
| opencode 附加 | command/huaweicloud-doctor.md + 权限缝（external_directory allow+edit deny） | command/vod-doctor.md（自检序列+key 禁令） | 权限缝依赖技能文件树随宿主可写；我们技能装在 hermes 侧，opencode 侧无树可缝——采纳命令、缝随技能上 opencode 时一并配 |
| 冒烟 | smoke-agents E2E | scripts/smoke_hosts.py（list 可见性断言，无宿主 SKIP） | 真机基线三宿主 PASS |

### 安装器校验设备锚点（S37 补设计）
校验链 token+meta 全程携带自生成纯 hex X-Vod-Device-Id+固定 UA：S1 设备绑定
要求 token 与后续请求同锚点（缺设备头=meta 401 设备不匹配，或走 legacy ip|ua
锚点烧日 5 次签发额度）；每次装机生成新锚点=一次校验恰好消耗一枚令牌额度。

### Golden 基线（D-golden-1，devkit doctor-golden 对表）
doctor/verify 的用户可见输出=对外契约的一部分：文案漂移/判定顺序变化/
新增行都影响依赖输出的用户与脚本。测试快照比对（tests/golden/），易变段
（HOME/REPO/SHA）归一化；UPDATE_GOLDEN=1 显式重录——重录动作本身即"口径
变更评审点"。已知取舍：key 探针行含易变指纹不入基线（golden 锁无 key
基线，key 态由 auth_status 专项用例覆盖）；测试基建注意 shutil.ignore_
patterns 只匹配基名（带斜杠的模式永不命中——runtime.json 曾因此漏进 clone）。
（续 golden 节）status/preset-update 拒绝语纳入基线：status 契约=原样
manifest（归一化 HOME/REPO/ORIGIN/SHA/installedAt，skillHashes 值不锁——
漂移由 D-drift-lock 专项覆盖）；探针手法沉淀 tests/probe.py（护栏拒止按
error 字段分流的教训入注释），pack 门控补真实装配层锁（stdio probe 对
VOD_PACKS 两种取值的 tools/list 断言）。

## 九·五、插件边界：不托管宿主生命周期（D-boundary-1，2026-11-17）

- 插件只做三件：写宿主配置（config.yaml / opencode.json / cordis.patch.yml…）、落载荷与
  技能、doctor 读回版本。不声明 unit、不探测进程管理方式、不重启宿主进程。
- 生效口径一句话：**重启宿主会话后生效**（对照样本 huaweicloud-devkit @adfd826：9 个宿主
  同一句）。宿主何时重读配置是宿主的语义，不写成产品约束。
- 已知宿主行为照实登记：常驻 gateway 按会话冻结 `mcp_servers` 快照
  （`docs/host-realverify.md:66-71`），换配置必须重启 gateway 或开新会话——hermes 上表现为
  "新会话才拿到工具面"，dsh 上表现为"重启实例 + 刷新页面"。
- 载荷固化的唯一成立理由：入口稳定（npx 缓存可变、会被清）+ preset/离线分发
  （`install.py:344`、D-payload-1、本文件 preset 禁自更新）。多版本并存与 prune 是这笔设计
  的运维债，挂账收敛为"升级即替换 + 保留最近 1 份"。
- 不采纳：由插件侧用 systemd / socket activation 托管宿主——越界，且本机端口动态分配、
  会话快照断点不因托管方式改变。
- **Falsifier**：宿主若支持 `tools/list_changed` 或会话内重连，可只换工具面而不重启进程，
  第 2 条话术可删；部署面若恒可访问 registry 且无 preset/离线需求，载荷固化与账本可退化为
  包依赖 + lockfile。

### 计数类断言必须由代码真值推导（S233）

文档与注释里写死的"工具数/用例数"会随 packs 与实现漂移，且漂移只在真机上暴露。实测两处：
proposal 写 dsh 降级形态 `Registered 3 tools`（真值 6，壳 `name: '<tool>'` 定义数），
壳注释把 MCP 形态写成"12 工具"（真值随 packs：默认 core,collect=10，含 knowledge=12）。
口径：计数不进文档正文当事实，**一律由代码/测试推导**——`tests/test_s233_counts.py` 从壳源码
数工具、从文档抽 `Registered N tools` 对账；改壳工具面而没改文档会在门禁红。
候选串同理：`core.format_candidates()` 是「名字（主键）」的唯一拼写点（collect 三处曾各拼一次）。

### hook 保护层的宿主差异要机器可查（S232）

只有 hermes 注册了 hook 层（`pre_llm_call` 路由 + `pre_tool_call` 读 key 拦截）；其余宿主
只有技能教法（软约束），codex/opencode 的等价注册未探（docs/hooks.md:90）。这个差异原来只写在
文档里，运维从巡检输出看不出来，容易把 10 个宿主当同一保护等级。现口径：`host_matrix --audit`
每行追加 `hook 层：有/无`（`HOOK_LAYER`/`hook_layer_label()`），使安全面差异在机器上可见。
新增宿主支持 hook 时必须同步该表——表里没有即按"无"报，宁可低估不虚报。

## 承载补充：followupStatus 插件对接（S74-S76，2026-11-08）

- 单源：_followup_fields 扩展（submit 主路径/draft 暂存共用）——三态白名单
  strip+lower 归一，白名单外/缺失省键（引擎侧降 NULL 不拒收，插件同口径双保险）
- 契约：tools.schema.json draft/submit 双工具 voices[].followupStatus
  （enum 白名单，maxLength 32）；工具 description 零增量（预算门禁不回退）
- dsh 壳：透传循环同口径扩展；desc 无预算不宣讲（SKILL 宿主技能层承载）
- SKILL：判定块第 5 条=三态映射话术锁（双副本+宿主副本 md5 对齐）
- 边界：commit 复用 draft 暂存 payload，followupStatus 随 draft 冻结（防调包语义不变）

## 承载补充：两段式断回合续提交（D-resume-commit-1，2026-11-09）

- 单源改动点：`vod_mcp/tools.py` draft_voices（草稿条目新增 `token` 明文落盘）、
  commit_voices（approvalToken/payloadSha256 可省略，draftId 命中本地未过期草稿
  即恢复）；`assets/contract/tools.schema.json` vod_commit_voices required 收窄为
  `draftId`。附带重构 `_drafts_load()`：draft/commit 草稿库读写单源
  （现读+TTL 惰性清除），禁双边漂移。
- 安全语义：token 威胁模型=防 draft→commit 间载荷改写（sha 比对），非同意
  凭证——落盘不放大风险；runtime.json 0600 与 java_key 同级保护。显式传入
  参数仍走原校验（错 sha/错 token 照拒），恢复路径只是"省略即取签发值"。
- 分层治理口径（对齐业界软硬分层共识）：
  - 规则真源：SKILL 五副本由仓源 skills/ 经 sync_plugin.py 确定性生成，
    test_skill_drift_lock 在 pre-push 质量门内做新鲜度检查——副本不手工维护。
  - 软约束：SKILL 收口话术锁（确认后当回合必须 commit、不成必须明告未提交）——
    引导模型走向正确路径。
  - 硬约束：机制层已有 payloadSha256+approvalToken 防调包闸、单次消费闸；
    本次补断回合可恢复。"用户是否同意"是对话语义，插件侧无法确定性判定，
    明示为边界（完全确定性同意=宿主 UI 结构化确认，属宿主协议改动）。
- 验收映射：场景用例 S83-S86（proposal.md），回归 tests/test_two_phase.py。

## 配额数值归属：引擎侧可配置，插件零数值（2026-11-09 D-quota-raise-1）

- 匿名档配额/限频的数值真源在引擎（VOD-KEY 表+t_vod_api_keys，vod.external.* 七项
  可配置，默认 30 天/5000 累计/日 500/锚点签发 1000/天）。插件 vod_mcp 不携带、
  不缓存、不解释任何配额数值——429 回执与引导文案由引擎下发透传。
- 设计收益：引擎侧拍板提额（500→5000 等）或运营调参，插件与已装机宿主零发版
  零改动即随新值生效；插件发版周期与配额运营解耦。
- 边界：签发时 daily_quota 烧进 key 行——存量令牌的日配额不随引擎配置变更
  （换发新令牌才吃新默认）；累计/限频类读实时值即时生效。

## 承载补充：无通道 pending 队列（D-pending-1 及补强，2026-11-09）

- 承载：vod_mcp/pending.py（原子 IO/幂等键/plan_flush 纯函数）+
  tools.py `_flush_pending`（submit_voices 两成功路径接线，同步、失败
  不回滚主提交、corrected/expired 进内部诊断）+ skills 真源无通道 fallback
  段（三副本同步：skills//plugins//hermes profile）。
- 决策：幂等键=条目级 sha1(content+confirmAt+source)，内容级去重归引擎
  uk_voice_id（两层分工）；flush 同步非异步（单进程竞态成本>收益，异步留
  扩展点）；originalLines 权威拼接=S73 家族的技术层下沉（规则锁不死的行为
  改机械锁）；双通道消息分离（用户人话/日志全量，路径属 CWE-209）。
- 定性边界：通道方三问（确认/原话/送达），不问第四个；内容价值判断归
  引擎（幂等/R2/人工归因）与运营侧。

## 承载补充：技能披露第二轨 / 版本提醒 / 宿主适配层（2026-11-11，对表 devkit）

三条改造的共同判据是「把可对账性与单一事实源下沉到代码」，对应 devkit 已
验证过的工程形状（skills-as-server-data、update-check、integrations/<host>）。

- **技能披露第二轨**：`vod_list_skills` + `vod_retrieve_skill`（knowledge pack，
  只读零上游）。技能文本成为 server data，任何 MCP 宿主（含没有原生技能目录的
  dsh）都能取到与包内一致的规则全文；owner pack 被裁剪时返回恢复命令而非空内容。
  元技能（vod-core / vod-feedback-collect）仍原生安装——激活时机不能靠工具调用。
  承载：vod_mcp/skills_registry.py + tests/test_skills_disclosure.py（含 pack 裁剪、
  未知技能、路径穿越、零 HTTP 四类锁）。
- **版本提醒**：`vod_check_update`（core）。24h 缓存 + 拒绝冷却 3 天 + 失败静默；
  preset 形态零外呼；只给 upgradeCommand，从不自升级（D-key-guard-3② 口径不变）。
  承载：vod_mcp/update_check.py + tests/test_update_check.py（semver 数值比较
  0.4.10>0.4.9 单独锁——字符串比较会判反）。
- **宿主适配层**：`integrations/<host>/host.json` 承载配置落点/技能目录/平台分叉/
  随装生成物，`vod_mcp/hosts.py` 解析；安装器不再出现宿主路径字面量（反向锁
  test_no_second_source_of_host_paths_in_installer）。新增宿主=加一个目录 +
  一段安装逻辑，改漏变成结构上不可能。承载：integrations/*/host.json +
  tests/test_hosts_spec.py。
- **顺手修的两处存量漂移**（本次实测发现）：
  ① `assets/skills/vod-core/SKILL.md` 还在教 `vod_run_analysis` / `vod_task_status` /
  `vod_task_result` / `vod_kb_search`（2026-11-03 已删的工具）与不存在的
  `vod-category-matching` 技能——按本技能路由会直接调到不存在的工具，已按当前
  工具面重写（v2）。
  ② opencode 的 `/vod-doctor` 命令正文硬编码在安装器函数里，已移入
  integrations/opencode/command/vod-doctor.md 模板（单一来源）。

## 承载补充：传输解耦（Streamable HTTP 远程面，2026-11-11，对齐 devkit）

形态逐项照 huaweicloud-devkit 的远程面（它的 mcp-server-remote.ts 与
test/remote-mcp-server.test.ts 是参照物），只在我们有身份/写面的地方收紧。

| 维度 | devkit | 本插件 |
|---|---|---|
| 启动 | 同一二进制 `--transport remote --port 9528 --host 127.0.0.1` | `vod-devkit serve --transport remote --port 9528 --host 127.0.0.1`（bin 透传） |
| 传输 | 官方 SDK Streamable HTTP，stateless + jsonResponse | 官方 Python SDK `StreamableHTTPSessionManager(json_response=True, stateless=True)` |
| 方法契约 | POST 进传输；GET 405；OPTIONS 204 + ACAO:*；通知 202；坏 JSON 400 | 同（逐条测试钉死）；`Accept` 必须含 `application/json`——只给 `text/event-stream` 的客户端按 jsonResponse 模式回 406（与 devkit 同） |
| 工具面门控 | remoteSurface 摘掉 secrets 包 + 本地写工具 | `packs.REMOTE_WITHHELD` 只摘 `vod_packs_configure`（2026-11-16 修订，见 D-token-machine-1）；draft/commit/ledger 与本地一致，草稿按宿主隔离 |
| instructions | remote 版不给 skillRoot，教 retrieve_skill | 同；`vod_retrieve_skill` 在远程面不返回 path，`vod_list_skills` 不返回 skillsDir |
| 身份 | 不管（凭据在服务器本机文件） | **请求头 Authorization 逐请求注入优先**；无 Bearer 时与本地同链领/复用机器级匿名令牌（2026-11-16 修订） |
| 鉴权 | 无，README 警告别公开 | 无内建鉴权（同），默认回环 + 反代承担 TLS/身份 |

插件不写库这条在远程面同样成立：HTTP 面唯一的出站动作仍是引擎 HTTP API
（POST /external/voices 等），落库/配额/审计全在服务端；本仓没有任何 DB 连接
代码路径，远程面也没有新增。

承载：`vod_mcp/transport_remote.py`（HTTP 外壳 + ASGI 适配层）、
`vod_mcp/remote_app.py`（SDK Server 与工具面/instructions）、
`vod_mcp/guardrails.py`（护栏唯一实现，两面共用）、`packs.REMOTE_WITHHELD`、
`tools._REQ_KEY/_SERVER_FACE`（逐请求身份）、tests/test_remote_transport.py（13 例）。

与参照物逐条对账（不留"够用就行"的账）：

| 项 | devkit | 本插件 | 状态 |
|---|---|---|---|
| 响应流式写出 | `for await (chunk) res.write(chunk)` | `_StreamSink` 逐块写；无 content-length 时 chunked 分帧并每块 flush | **已对齐**（`test_stream_sink_*` 2 例钉字节与分帧）。可达性如实说明：jsonResponse 模式下 SDK 的响应都带 content-length，走的是原样分支；chunked 分支只在 SDK 给无长度响应（如将来关掉 jsonResponse 开 SSE）时生效 |
| `capabilities.tools.listChanged` | `{tools:{listChanged:true}}` 断言 | `_RemoteServer` 覆盖 `create_initialization_options` 传 `NotificationOptions(tools_changed=True)` | **已对齐**（`test_initialize_*` 断真值） |
| 请求头规范化 | 缺省/`text/plain` content-type → JSON；缺 accept → 补双类型 | `_normalize_headers` 同规则 | **已对齐**（实测不做的后果：`text/plain` 请求被 SDK 判 400 Invalid Content-Type；`test_minimal_client_headers_*` 钉住） |
| `tools/call` 省略 `arguments` | 在 JSON 边界补 `{}`（其 zod 层拒 undefined） | **不补**：Python SDK 的 `CallToolRequestParams.arguments` 本就可空，实测不补即 200 | 不复制——那段代码补的是 JS schema 的洞，属无收益复杂度；wire 契约仍由 `test_tools_call_without_arguments_*` 钉住 |
| initialize 副作用 | 预热 user hash（3s 超时）+ 上报 agent/telemetry | 本仓无 telemetry/hash 子系统 | 不适用（不是"没做"，是没有对应对象） |
| dsh 壳 | 不走 MCP | 同 | 范围外（它有自己的工具面，不经 MCP 传输） |

dsh 壳归因同步（2026-11-11，负责人要求「能力一致」）：`packages/dsh/lib/index.js` 落同一
优先级链（字面证据 > 记忆 30 分钟 > config product 先验 > UNKNOWN），索引/匹配/
歧义/误命中判定例与 Python 侧逐条对齐（含线上 meta 的 catalog≠展示名两颗雷），
账本与回执同带 productSource/productEvidence；硬编码 PRODUCT_MAP 删除（改名录
驱动）；工具面本就无 product 入参。用例见 packages/dsh/test/attribution.test.mjs（7 例，
含行为级 stub fetch：无证据走先验、中文别名压过先验、歧义不带 product）。

## 归因：运行期字面解析（D-attrib-B，2026-11-11 负责人拍板 A/A/A/A）

**2026-11-16 修订（负责人拍板 A，D-attrib-binding-1）**：安装先验不再无条件兜底。
`--product` 写入的 binding 只有**原话出现自指**（"这个产品/你们家/本平台/这插件"等，
词表在 `attribution.SELF_REFERENCE`）时才作为归因证据（`source=install_binding`，
`evidence.reason=self-reference` 带 snippet 可回指）；无自指 → 视为无证据，回到
"先问用户一次"。理由与删 `host_default` 同源：先验是无字面证据的推断，用户在 A 产品
插件里吐槽 B 产品时会错归，而错归会进引擎幂等/判重域，污染静默且难追溯。
单产品部署的免打扰场景仍由自指覆盖（用户说"你们这个产品"即可归）。

产品不再由安装/启动配置决定。install `--product` 由必填降为可选先验；归因在
提交/起草时由插件从**用户原话**解析，证据落账本。推翻面：D-product-id-2 的
「--product 必填 + 硬校验」→ 只保留「给了就必须对」（提供时仍校验，不给不拦装）；
D-attrib-A 的「只认安装绑定」→ 绑定降为第三顺位先验，模型自报仍不采信。

### 归因优先级链（证据强度降序）

| 顺位 | 来源 | 判据 | productSource |
|---|---|---|---|
| 1 | 用户原话字面证据 | 命中产品名录别名且**唯一** | `user_input` |
| 2 | 记忆 | TTL 30 分钟内最近一次**有字面证据**的归因 | `memory` |
| 3 | 安装先验 | install --product（可选，提供即校验） | `install_binding` |
| 4 | 未知 | 以上皆空或多产品歧义 | `unknown` |

硬规则：
- **唯一命中才采信**；≥2 个不同产品命中 → product 留空 + `reason=ambiguous`，
  全部命中片段进 productEvidence（人工归因要有上下文，S94）。
- **模型自报不采信**：契约删除 product 参数；调用方仍塞值时忽略并回执
  `ignoredRuntimeProduct`（D-attrib-A 的可观测性保留，S97）。
- **记忆只复用有证据的归因**，且只在 0 命中时启用；新字面证据无条件覆盖；
  歧义/无证据调用不写记忆（S100）。
- **名录不可用不猜**：meta 不可达或老引擎（无 catalog/nameAliases）时只走短码
  匹配，仍无证据 → unknown 并在回执明示（S98）。
- 记忆是机器级（runtime.json），同机换人/换项目靠 30 分钟 TTL 收敛；回执
  productSource=memory 且 evidence 回指历史命中，便于追污染（负责人风险 #2）。

### 冷启动目录可达性与主键纪律（S231，2026-11-17 真机）

单独部署（standalone，无宿主装机、无 key）实测：冷启动态 `vod_search_products` 恒返回 0 候选；
先 `vod_auth_ensure` 领匿名令牌后同一次查询返回 3 候选 / total=103。即目录要靠令牌才取得到，
「缺产品先给 3-5 候选问一次」在冷态不成立。定稿三条：

- `search_products` 目录为空时**懒领一次匿名令牌**再取（本工具唯一写盘例外，仅目录为空时触发）；
  仍取不到 → 回执 `reason=catalog_unavailable` + 处置提示，不静默给空、不编候选。
- `productId` 不许用名字冒充主键：目录里有该条但无 `id` → `source=unknown` + `evidence.reason=id_unresolved`；
  展示名只在 `products` 里（catalog 用另一套库名，如 OBS vs 对象存储服务 OBS）→ 名字通道保留，证据标 `name_only`；
  老引擎（无 catalog）→ `name_legacy`。
- 用户回答命中目录项但无主键 → 同口径回 `unmatched_answer` 交候选，绝不写 `"None"`。
- 空查询要分因（S232）：`query` 为空（模型把入参写成 `keyword`/`q`）时回
  `reason=empty_query` + `hint`（说明入参名是 query），不再静默返回 0 候选——
  否则看起来像"目录里没有这个产品"。

### 别名索引与误命中判定例

数据源全部来自引擎 meta（单一真源，插件零手写别名表）：
`productCatalog[{id,name}]`（提交主键）＋`products`（显示名）＋
`nameAliases{CODEARTS:[码道, CodeArts, 软件开发生产线 CodeArts, ...]}`＋
`aliases{modelarts: maas}`。

| 规则 | 判定例 |
|---|---|
| 中文别名按子串匹配 | 「码道导出转圈」命中 CodeArts；「对象存储服务 OBS 上传失败」命中 OBS |
| 拉丁别名大小写不敏感 + 词边界（前后不得为 `[A-Za-z0-9_-]`） | `CodeArts`/`codearts` 命中；`codearts.yaml`、`mycodearts` 不命中 |
| 短别名（<5 字符，如 obs/maas）只认强形态，不收小写裸词 | 只认 `OBS`、`对象存储服务 OBS`；`obs://bucket`、小写 `obs` 不命中 |
| 长别名优先，重叠命中合并同产品 | 「软件开发生产线 CodeArts」优先于其子串 `CodeArts`，证据保留最长片段 |

### 证据与留痕（承载）

`productEvidence` 为结构化列表，每条 `{product, alias, snippet, reason?}`：
单命中一条、歧义多条、记忆来源带 `at` 回指。落点=工具回执（模型与账本双可见）
＋本机账本条目字段（`productSource`/`productEvidence`）。引擎侧本期不加列
（负责人拍板 P4-A：等错归率报表需求明确再评估）。

### 用例承载

S91-S100（proposal）→ 承载：`vod_mcp/attribution.py`（索引/匹配/优先级链）、
`tests/test_attribution.py`；记忆列=`runtime.json attribution_memory`；证据列=
账本 `productSource/productEvidence`；契约面无 product 参数（S97 的
ignoredRuntimeProduct 为回执字段，非入参）。

## 宿主 attach：MCP 单独部署（D-attach-1，2026-11-11 负责人拍板 B）

形态：一个远程端点服务多个宿主；宿主只把 MCP 配置指向它 + 本地装技能。与 devkit
的差别是身份模型（他们凭据在服务器本机、remote 只能同机；我们 per-request Bearer），
因此 attach 是产品能力而不是文档片语。

### 三宿主配置形态（各用官方通道，不自创）

| 宿主 | 写入方式 | token 承载 |
|---|---|---|
| hermes | `hermes mcp add vod-devkit --url ... --auth header` | env `MCP_VOD_DEVKIT_API_KEY` → hermes 写 `${...}` 引用（配置无明文） |
| opencode | `mcp.vod-devkit = {type:"remote", url, enabled, headers}` | `Authorization: Bearer <token>`（明文在配置，提示文件权限） |
| codex | `codex mcp add vod-devkit --url ... --bearer-token-env-var VOD_MCP_TOKEN` | 用户环境变量 |
| dsh | 不支持（壳不走 MCP） | `--mcp-url`/`--skills-only` 显式 exit 2 |

### 探活契约（写入之前）

`initialize` → `tools/list`，期望集合 = 契约工具 − `packs.REMOTE_WITHHELD`；缺一个都
exit 2（端点不是 vod-devkit、或版本/角色不匹配）。探活失败零副作用：不写宿主配置、
不写 install-manifest。

### 安装产物

manifest 增 `transport`（stdio|remote|skills-only）与 `mcpUrl`；`skills-only` 不动任何
MCP 配置（MCP 已由别处注册的场景）。`doctor` 远程三查：端点可达（GET 405/401 也算
活）、tools/list 工具面、token 是否可用（无 token 只提示不判红）。

### 卸载的托管条目语义（同批修掉的存量 P0）

共享用户配置（config.toml / opencode.json / opencode.jsonc / config.yaml）**永不整
文件删除**：opencode 只摘 `mcp.vod-devkit`，hermes/codex 走官方 `mcp remove`。旧实现
对 manifest.mcpConfig 直接 unlink，opencode 场景等于删掉用户整份 provider 配置
（旧守卫只挡了 config.toml）。

### 技能双面（传输面自适应）

远程面摘掉 draft/commit/list_submitted → SKILL 必须"先看工具面再定流程"：有草稿工具
走两段式；没有则单发 submit + 回执回显，且不承诺本机账本查询。这是 devkit
"skillRoot 有/无" 双轨的同构做法（他们按面切换技能加载路径，我们按面切换流程）。


## 插件副本生成物边界（D-copies-generated-1，v0.5.9，S103-S110）

### 一句话

`plugins/vod-devkit/{vod_mcp,skills,contract,safety,build-info.json}` 是**构建产物**：
git 里没有它，`scripts/sync_plugin.py` 生成它，`scripts/verify_copies.py` 证明它
与源一致且没有回流进 git。发版链上不再存在「两份真值」，因此也没有「两份不一致」。

### 为什么必须零提交（而不是再加一道 diff 门禁）

旧形态的门禁全部形如 `diff -r 源 副本`。而 sync 是「整目录覆盖」，它把**两边都**
写成新内容——门禁比较的永远是「刚同步过的两份」，恒真。v0.5.8 的真实事故：
提交清单漏 `plugins/vod-devkit/contract/tools.schema.json`，于是提交树里副本停在
0.5.7、工作区两边都是 0.5.8、所有门禁绿，npm tarball 里的契约版本与 tag 不一致，
直到发版之后才被发现。结论：能证明「同步跑过」的判据，证明不了「发布物 == tag 的代码」。
唯一稳的修法是不让副本进入 commit 图。

### 组件与职责

| 组件 | 职责 | 关键约束 |
|---|---|---|
| `scripts/sync_plugin.py` | 唯一生成入口：整目录覆盖四目录 + 烧两处 build-info | `PAIRS` / `IGNORE_PATTERNS` / `BUILD_INFO` 在此定义；`sync(root, quiet)` 幂等；`runtime.json` 永不入副本 |
| `scripts/verify_copies.py` | 唯一门禁：内容一致 + 副本零跟踪 | 从 sync_plugin import `PAIRS`/`IGNORE_PATTERNS`（清单只有一处）；`git ls-files` 为空是第二条断言 |
| `package.json` `scripts.prepack` | 打包/发布前自动重跑生成器 | 输出重定向到 /dev/null（否则污染 `npm pack --json`） |
| `.githooks/pre-push` | 推送前：sync → verify → 测试 | 先 sync 再 verify（干净检出也能过） |
| `.github/workflows/ci.yml` | 同上，跑在完整历史（fetch-depth: 0） | 不再自拼 `diff -r`；浅克隆仍有脚本侧兜底 |
| `scripts/release.sh` | 发版：sync → 门禁 → bump → commit → **复验** → tag → push → pack | 复验位置=commit 之后、tag 之前 |
| `tests/conftest.py` | 全程测试前同步一次（import 生成器，非子进程） | 副本自包含类用例读到的是当前源码 |
| `scripts/host_matrix.py` | 矩阵开始前同步一次 | 矩阵装的是当前源码 |
| `vod_mcp/host_adapters/codex.py` | 仓内直跑安装时缺副本则兜底生成 | npm 包内副本本就随包，缺=包损坏，exit 2 |

### 发版时序（顺序本身就是门禁）

```
sync_plugin → verify_copies（发版起点零漂移）
→ bump 版本落点 → golden 重录 → CHANGELOG
→ git add（显式清单，副本不在其中）→ git commit
→ verify_copies（提交后再验：唯一能抓「同步了但没提交」的位置）
→ git tag v$BUMP → push → npm pack（prepack 再跑一次 sync）
→ 指纹断言：build-info.commitSha ∈ {v$BUMP^, v$BUMP}
→ publish → publish_verify（registry 上真的有这颗版本）
```

指纹断言的区间语义：`prepack` 在发版提交之后重跑 sync，`commitSha` 于是等于发版
提交本身而不是它的父提交。两者指的是同一份代码（release 提交只改版本号），
断言接受这个区间；落在区间外=包内代码不是本 tag 的代码，禁止发布。

### 环境一致性（同一批修掉的两个假红）

| 现象 | 根因 | 修法 | 承载 |
|---|---|---|---|
| CI 报「缺 tag」判 DRIFT | `actions/checkout` 默认 fetch-depth=1，tag 不可见被当成没打 | 脚本 `is_shallow()` 区分「不可见/缺失」；CI 改 fetch-depth: 0 | S108 |
| CI 上 `KeyError: 'keyCheck'` | 断言依赖本机 `runtime.json` 的 java key；CI 无该文件 | 用例显式钉 `JAVA_KEY` 并断言「探针必须命中假 `_http`」 | S109 |

### 对既有结论的影响

- 「双副本一致性」不再是「两份文件相同」的命题，而是「生成物与源一致 + 生成物不
  回流 git」。**报验证结论时按这两条说**，别再说「diff 四目录无差异」。
- `pack_verify` 的 166→172 文件不是内容膨胀，是副本现在由生成器产出（含忽略规则
  统一的 `*.pyc`/`*.log` 之外的完整目录）。
- 装机副本（`~/.hermes/...`、`~/.dsh/profiles/...`）仍是**运行时快照**，与本节的
  仓库生成物是两回事：后者保证发布物与源码同源，前者要靠重装刷新。

### 场景用例承载

S103（零提交）→ `.gitignore` + `verify_copies.tracked_paths`；
S104（单一入口/fresh clone）→ `sync_plugin.sync()`；
S105（单门禁）→ `verify_copies.check()` + 三处调用点文本锁；
S106（时序）→ release.sh 位置锁；
S107（指纹区间）→ release.sh 断言结构；
S108 → `registry_reconcile.reconcile(shallow=True)`；
S109 → `tests/test_p2_structure.py::test_patch_on_net_http_intercepts_real_call_chain`；
S110 → conftest / host_matrix / codex 适配器的兜底 sync。
测试落点：`tests/test_copies_generated.py`、`tests/test_verify_copies.py`、
`tests/test_registry_reconcile.py`。

## 插件 MCP 清单形态与改写失败分类（D-mcp-manifest-a3-1，2026-11-15）

三份东西各管一件事，别再混着说：

| 层 | 文件 | 谁写它 | 它保证什么 |
|---|---|---|---|
| 静态清单（发布物） | `plugins/vod-devkit/.mcp.json` | 我们，随 npm 发 | 规范字段齐全（`$schema`/`type`）；入口是实测可用的 CLI 形态 |
| 装机缓存清单 | `~/.codex/plugins/cache/<mp>/vod-devkit/<ver>/.mcp.json` | codex `plugin add` 复制，随后被安装器改写 | 绝对解释器 + 载荷副本（唯一能保证版本正确的形态） |
| server 入口 | `vod_mcp/server.py` | 我们 | 解释器 < 3.10 时可读诊断，不是 traceback |

实测（codex-cli 0.167.0，2026-11-15；探针插件把收到的 argv/cwd/env 落盘，
用 `codex app-server` 的 `mcpServerStatus/list` 触发真实 spawn）：

| 规范承诺 | 0.167 实测 | 后果 |
|---|---|---|
| `args` 里 `${PLUGIN_ROOT}` 展开 | 原样收到字面量 `${PLUGIN_ROOT}/vod_mcp/server.py` | 启动失败（文件不存在），或更差：误命中别处的同名路径 |
| stdio cwd 默认 = 插件根 | `cwd` = `~/.codex` | 相对路径 args 全部失效（与 0.166 的旧结论一致） |
| 注入 `PLUGIN_ROOT`/`PLUGIN_DATA` 环境变量 | 两者均未注入（`null`） | 无法在 server 内自查插件根 |
| `VOD_PACKS` 等自定义 env 透传 | 正常传入 | 可用 |
| 插件包迁到 Agent Plugins 格式（根 `plugin.json` + `mcp.json`） | 插件 installed/enabled，但 MCP 条目**没注册**（`codex mcp list` 空） | 该格式在当前二进制上还不能承载 MCP |

结论：`${PLUGIN_ROOT}` 静态形态（A3）**搁置**，理由不是偏好而是实测。清单保持 CLI 形态，
并禁止出现任何 `${...}`（未展开=静默坏）。运行时正确性由安装器改写承担。

失败分层（安装器处置，不是"catch 全部 exit 1"）：

| 类别 | 触发 | 处置 | 为什么 |
|---|---|---|---|
| `bad-json` | 缓存清单非法 JSON / 缺 `mcpServers.vod-devkit` | warn + 补救文案，安装继续 | 插件已装进宿主，静态 CLI 形态仍可跑 |
| `not-writable` | 读/写抛 OSError（只读挂载、权限） | warn + 补救文案（含"把 command 指向 3.10+ 解释器"） | 内网/沙箱不该被卡死 |
| 读回不一致 | 写完再解析，字段与期望不符 | 安装失败（exit 2） | 半写状态留给宿主=坏配置，比装不上更糟 |

对既有结论的影响：
- 「入口不依赖 PATH」这条铁律在 codex 上**做不到**（静态形态只能走 CLI），所以它降级为
  「运行时形态必须被安装器改写为绝对路径」——改写从"优化"升格为**必需**，不能拆。
- 「插件副本零提交」不受影响：`.mcp.json` 是手写发布物，不在生成物清单里。
- 熔断标记仍在 `~/.codex/` 下：用例必须把 HOME 指到临时目录，否则真机装了熔断时
  S113 会假红（S109 同款环境无关纪律）。

残余风险（写清楚，不掩）：
- marketplace 直装（不经我们的安装器）仍是 CLI 形态 → PATH 上的版本不确定，
  可能是旧副本。这是当前宿主的限制，不是我们能靠清单解决的；已在 README 标注
  「用 install --target codex 装」，并且 **doctor 直接报实际形态**（payload / cli /
  placeholder / unreadable，后三种判问题，S115 兜着）。
- 解释器 < 3.10 → server 顶部 guard 报版本并退出（响失败），宿主侧只看到启动失败。

实测记录（本机端到端，2026-11-15）：`install --target codex` 到临时 HOME →
cache 内 .mcp.json 被改写成 `python3` 绝对路径 + `payloads/0.5.9/vod_mcp/server.py`
→ `doctor` 打印「codex 插件 MCP 形态：载荷（…）」并 `doctor: OK`；把该文件手改回
`vod-devkit serve` → `doctor` 判 FAIL「插件 MCP 仍是 CLI 形态…重跑 install」。

复验方法（A3 解禁的条件，写死在文档里）：探针插件 + `codex app-server` 的
`mcpServerStatus/list` 落盘 argv/cwd/env；若 `${PLUGIN_ROOT}` 被展开且 cwd = 插件根，
切回 A3，改写逻辑届时降级为"解释器版本兜底"（推荐而非必须），不要同时拆掉。

用例承载：`tests/test_mcp_manifest_a3.py`（S111-S114）；
需求侧见 `docs/proposal.md`「插件 MCP 清单形态」一节。

## 全局命令：读路径与写纪律（D-global-cmds-1，2026-11-15）

一个视图，两个来源：

| 来源 | 用途 | 为什么不是另一个 |
|---|---|---|
| `install-manifest.json` 的 `installs[]` | "我装过哪些宿主、装的是哪个版本、用了哪个载荷" | 这是**我们写过的**记录，回答安装意图 |
| 宿主真实配置文件 | "现在实际生效的 packs/入口是什么" | 宿主可能被手工改过、被别的安装动作覆盖；只读 manifest 会把"以为的"当成"实际的" |

`version` 把两者并排打：已装版本来自 manifest，生效 packs 来自宿主配置。两者不一致
本身就是诊断信息（例如人在配置里改了 VOD_PACKS，manifest 还停在安装值）。

宿主配置定位（不写九张表）：递归找"哪个对象里有 `vod-devkit` 且该值像 server 条目
（有 command/args）"，再取它的 `env` 或 `environment`；hermes 那种"独立 mcp json 顶层
就是条目"单独判一次。写死九个路径的写法在下一个宿主形态上必然再漏一次——递归定位
把"新宿主"退化成"配置里有没有这条目"。

写纪律（`packs enable|disable|all`）：
- 缺省 dry-run，`--apply` 才写：多宿主批量改配置属于"一次影响九台宿主"，必须两步。
- 只改 `env.VOD_PACKS`：其它 env（`VOD_JAVA_API_BASE` 等）、宿主其它 server、用户自有键
  原样保留；首改落 `.bak`。
- 写后读回：与 codex 改写同一条纪律——写成功 ≠ 落盘就是我们要的；不一致抛错。
- `core` 强制包含：禁 core 等于关掉元数据/安全面，跟 devkit 同口径。
- 不可直写配置的宿主（dsh 的 cordis.patch.yml、codex-desktop 的 marketplace、
  openclaw 的 JSON5 `openclaw.json`——只能经 `openclaw mcp add/set/unset`）**明确报
  "需重跑 install"**，不打印成功。

卸载语义（`uninstall --target` / `--clean-global`）：
- `--target` 只摘该行；其它行、与其它行共用的载荷、`skillInstalls` 里属于别的宿主
  的原生副本都不动。
- `--clean-global` 只清两类认得的残留：①无 `payload.json` 的载荷目录（`payload.residue`）；
  ②`~/.npm/_npx/*/node_modules/vod-devkit` 的 npx 缓存目录。在用载荷与不认得的目录绝不碰，
  逐条打印删了什么。

未知包 id 的两个入口（S116）：安装口（`install` 在写任何宿主配置之前）与运行口
（server 启动、`initialize` 之前）共用 `packs.parse_packs`，都 exit 2 并列可用 id。
静默过滤的反例是实测的：`VOD_PACKS=core,bogus` 曾静默变成 `('core',)`——操作者以为
关掉/打开了某个包，实际两头都不是。

已知边界（诚实标注）：
- `version` 报"已装版本"来自 manifest 记录，不启动宿主、不探活；版本漂移的**真实**
  运行时形态由 `doctor` 回答（它会读 codex 插件缓存的实际 command/args）。
- dsh 的 packs 目前改不了（写在 profile patch 里），`packs` 会明说而不是静默跳过。

账本外宿主（S130-S131，D-dsh-global-view-1）：`version` / `packs status` 的行数等于
`installs[]` 条数，而 dsh 由 `dsh-vod-devkit` 的 profile 依赖承载、安装器不写账本行——
全局视图里它原来连一行都没有，连 `[missing]` 都不给（那个提示只服务"账本有行、配置
没条目"）。补法是**只读探测** `~/.dsh/profiles/*/package.json`：只列声明了
`dsh-vod-devkit` 的 profile，版本取 `node_modules/dsh-vod-devkit/package.json` 的实际
版本（取不到报「已装版本未知」，不回落到 `file:…tgz` 之类的 spec——那是意图不是现状），
`packs` 面对它一律 `[n/a]` + "需重装"。**不把 dsh 塞进 installs[]**：那会改写
`uninstall` 语义（按行删壳依赖），是另一件事。

探测与交互（S127）：判据是"宿主 CLI 在 PATH 或配置目录存在"，规则在
`integrations/<host>/host.json` 的 `detect` 段（`hosts.raw()` 归一成 detectCLI/detectPath），
不在代码里写宿主清单。**只有 stdin+stdout 都是终端才问**——CI/重定向下"多选"退化成
"报错列选项"，因为猜错宿主的代价是写坏别人的配置。多选与 `--target all` 共用同一个
安装循环（`_install_many`）：缺落点（dsh 无 `--profile`）跳过并说明，单宿主失败不阻塞其它。

用例承载：`tests/test_global_cmds.py`（S116-S123、S126-S128、S130-S131）、
`tests/test_packs_configure.py`（S132-S133、S136）、`tests/test_doctor_egress.py`（S134）、
`tests/test_key_guard_hook.py`（S135）、`tests/test_runtime_atomic.py`（S137、S139）、
`tests/test_state_read.py`（S140）。

## 状态读取口径：现读还是快照（D-state-read-1，2026-11-16）

状态有两层，**用途不同、不许混**：

| 层 | 是什么 | 谁读 |
|---|---|---|
| `_RT` 镜像 | 进程启动时读一次的文件快照 + 本进程写入后的增量 | 需要"本会话内一致"的判定（会话记忆、首启标记） |
| 文件现读 | `runtime_state._runtime_cfg()` | 身份类值（java_key / java_base / token_tier）与账本对账 |

身份类值必须现读：它们会被**别的进程**改（`auth init --apply`、安装器、CLI 卸载）。
写成模块常量等于把"用户刚换的 key"冻在启动那一刻，表现为 401 或打到旧环境——而且
`auth status` 与出口用的是同一份旧值，自洽地错，最难查。

实现取 PEP 562 模块级 `__getattr__`：`net.JAVA_KEY` / `net.JAVA_BASE` 未被人显式 set 时
每次现读（env > 文件 > 镜像 > 默认），被 set 过则用 set 的值——保住既有的 patch 面
（`monkeypatch.setattr(net, "JAVA_KEY", …)` 仍生效）。模块**内部**必须调 `_java_key()`：
模块内的全局名查找不触发 `__getattr__`，写成裸 `JAVA_KEY` 会 NameError 或读到旧值。

**代价**：每次出口调用读一次 runtime.json（几十 KB、账本上限 200 条），提交/元数据都是低频，
可接受；如果将来有高频只读路径，再加 mtime 缓存——不要在没测量的情况下先加。

## 会话内能力面开关（D-packs-configure-1，2026-11-16）

能力面此前只有 `VOD_PACKS`：安装期写进宿主配置、启动期读一次，改了要重启会话，
也没有工具能回答"现在开的是哪几个"。`vod_packs_configure`（core）补会话内开关。

**三层写面的分工（不许混）**：

| 面 | 入口 | 作用域 | 谁写 |
|---|---|---|---|
| 持久 | CLI `packs enable\|disable\|all --apply` | 宿主配置文件（重启生效） | 运维/用户 |
| 会话 | `vod_packs_configure` | 进程内 `_RUNTIME`（重启即清） | 模型（会话内，不落盘） |
| 环境 | `VOD_PACKS` env | 进程启动快照 | 平台/CI 注入 |

`effective_packs()` 的优先级：会话内开关 > `VOD_PACKS`（含 core 强制与熔断）。
**MCP 工具不写宿主配置文件**——那会让"谁改的"变成猜谜，而持久化面已经有可解释入口。

**熔断不能被绕过**：`normalize_packs()` 里 `collect` 遇到 `BREAKER_MARKERS` 直接抛
`PackRefused`（工具层转 `-32015`），不是静默摘掉——静默摘等于"配了没生效"，而这里是
**显式动作被安全门禁拒绝**，两者必须用不同信号。启动期的 `_resolve` 仍走静默摘除+stderr
告警（那是"配置优先"的既有语义，不动）。

**通知只发在真变化时**：`changed` 为真的 `tools/call` 才追加
`notifications/tools/list_changed`；同一次调用在 stdio 上输出两行（响应在前、通知在后）。
`handle()` 因此允许返回 list，`main()` 逐条写出——这是全仓唯一会主动向客户端发消息的位置。
capabilities 必须声明 `tools.listChanged=true`，否则合规客户端不会重拉 `tools/list`。

**远程面摘除**：`REMOTE_WITHHELD` 加该工具。理由不是"安全"而是语义：HTTP 面每请求现造
server、无会话，开关写完下一个请求就没了（"以为改了其实没改"）。dsh 壳同理不提供。

## doctor 出站面：代理与引擎可达（D-doctor-egress-1，2026-11-16）

doctor 此前对出站面是盲的：key 探针只在配了 key 时跑，没 key 时连"引擎通不通"都答不上；
代理完全没有可观测面（urllib 隐式读 env，但没人能回答"现在走哪个代理"）。

两条都**只报告**：不改退出码、不建配置文件、不改路由。理由是 doctor 的既有契约——
离线装机必须能跑通 doctor；把网络问题变成 FAIL 会把"环境不可达"误报成"插件坏了"。

- 代理：只读 env（`HTTPS_PROXY/HTTP_PROXY/ALL_PROXY/NO_PROXY` 及小写），值先过
  `_mask_proxy()`（`user:pass@` → `***:***@`）。**不建 proxy.json**：devkit 建了，
  但它有"文件 < env"的优先级链要解释；我们没有文件，就不存在"改了文件不生效"。
  代价是没人能给"这台机器的代理"做持久记录——需要时写进宿主/CI 环境，不进插件状态。
- 引擎可达：无条件 `GET <apiBase>/rest/developer/manager/hdvodmngservice/v1/external/meta`
  （4s、不重试、不带 key）。判定三态：200=`ok`；`HTTPError`（含 401/403）=`auth`
  **算可达**——把鉴权失败报成不稳定会把排查方向带偏；其它异常=`unreachable` 只 `warn`。
  缺 `apiBase` 时明说"install 未写入"，不沉默。

**诚实标注**（对齐 devkit 的 honest residual）：宿主对 `runtime.json` 的读取门控
（沙箱规则/allow 列表）插件侧探测不到，所以 README 的「诚实残留」写"未验证"，不声称已拦。
真实降低暴露面的做法已经落地：安装器不把 `java_key` 种进载荷副本（运行期走匿名令牌）、
`auth status` 只输出指纹。

## 凭据单入口与技能读取教法（D-auth-init-1 / D-skill-teaching-1，2026-11-15）

**凭据为什么必须只有一个写入口**：key 是设备绑定 + 引擎签发，不是配置项。多入口
（手改 runtime.json / 写宿主 env / 重装）会产生"到底哪一把在生效"不可回答的状态。
`auth init` 把写收成一条路径，其余全是读：

| 动作 | 入口 | 可解释性 |
|---|---|---|
| 显式配 key | `auth init --key … --apply` | 只显示指纹；写后读回一致才算成功 |
| 查看当前 | `auth status` | 引擎地址 + 指纹 + 档位（显式 key / 匿名令牌） |
| 自动领匿名令牌 | 首提时插件自领（无 key） | 设备绑定；不是 key，档位标 anonymous |

拒绝规则（宁可不写也不留坏状态）：形态可疑（含空白/长度 < 8）拒写；引擎可达且判拒
（401/-32012）拒写；引擎不可达**告警后允许**（网络问题不等于 key 问题，离线装机要能走）。
明文 key 永不出现在输出、日志、文档示例里——示例一律用 `<引擎签发的 key>`。

**技能教法的取舍**：devkit 的做法是"先直读、被拒回落、绝不反复请求"。我们照搬这条，
原因是它把"能不能读"当成运行时探测而不是预判（预设"宿主一定能/一定不能读工作目录外"
两类都错过：openCode 有门控但可预授权，codex 沙箱基本不受限）。代价是第一次可能被拒一次
——可接受，因为回落路径（`vod_retrieve_skill`）不需要文件权限。

远程面不给 `skillRoot`：未鉴权面把服务器安装路径交出去等于免费侦察面。这条在
`remote_app.REMOTE_INSTRUCTIONS` 与 `skills_registry._server_face()` 两处同时实现，
不是只写在文档里。

用例承载：`tests/test_auth_and_skills.py`（S124-S125）。

## 凭据作用域：一台机器一个匿名令牌（D-token-machine-1，2026-11-16 负责人拍板）

**结论**：匿名令牌是**机器级**身份，不是版本级、不是宿主级。同一台机器上，全部已装宿主（含多 profile 的 dsh）、跨版本升级、
MCP 单独部署，都共用 `<state>/runtime.json` 里的同一个 `install_nonce` 与同一枚匿名令牌。

**为什么改**（两处实测隐患）：

1. 令牌绑 `install_nonce`（设备锚点），而 nonce 活在 `runtime.json` 里；旧路径
   `DIST_ROOT/vod_mcp/runtime.json` 是**按载荷版本目录**分的（`payloads/0.5.9`）。一次升级
   就是新目录 → 新 nonce → 重领令牌，匿名档日限额重新计。这比"多宿主各领一份"更常发生。
2. 机器上实际存在三份 runtime（载荷 / 仓内 `src/vod_mcp` / `packages/dsh/data`）→ 三个匿名
   令牌，限额被拆散；`probe_key` 的 `device-mismatch`（"令牌本身有效，但不是本机签发"）
   正是这类 nonce 漂移的现形。

**状态目录契约**：

| 项 | 取值 |
|---|---|
| 显式 | `VOD_DEVKIT_HOME`（装机由 `server_env()` 写进各宿主配置，测试写 tmp） |
| 默认 | `~/.vod-devkit/state` |
| 文件 | `<state>/runtime.json` + `runtime.json.lock`（flock 同目录） |
| 权限 | 文件 0600、目录 0700（迁移与每次写都收紧） |
| 解析优先级 | `VOD_DEVKIT_HOME` > 机器级 state 已存在（存在即用）> 旧 `DIST_ROOT/vod_mcp/runtime.json`（首启兼容） |

**"机器级"的准确含义**：指**该用户（服务账户）下的安装实例级**，不是操作系统级。
多用户共享同一台物理机时，各用户仍各一份 state、各一枚令牌（匿名限额仍会按用户拆开）。
要做真正的系统级共享（如 `/var/lib/vod-devkit`）需要显式配置 `VOD_DEVKIT_HOME` 并处理
多账户写权限（0700 目录 + 同组），本轮不默认开启——默认把状态放到用户目录里，
是"零配置可用"与"多用户不互相踩"的取舍。

**装机注入的口径**：装机是权威——`merge_json_mcp()` 整块重写宿主的 mcp 条目，
用户在宿主配置里手改的 `env`（包括 `VOD_DEVKIT_HOME`）会在下一次重装时被覆盖（与 `VOD_PACKS`
同语义）。要换状态目录，请在外层进程环境（systemd/容器 env）设置，不要手改宿主配置。

**不提供**模块级 `RUNTIME_JSON` 快照常量（收口时删除）：零消费方，且违反"路径类值不
import 期冻结"的纪律（D-state-read-1）。`runtime_state._runtime_path()` 一律走 `runtime_json_path()`。

**迁移（只做一次，保留设备锚点）**：首启时若 `<state>/runtime.json` 不存在、而旧位置有内容 →
**复制**过去（含 `install_nonce` / `java_key` / `token_tier` / `product` / 账本），旧文件保留不删，
并落 `<state>/.migrated` 标记。标记的用途是**防止回灌**：用户手工清掉 state 后，旧文件不得
被下一次启动悄悄还原（令牌/账本复活）。有标记即视为"这台机器已经迁过"。
此后旧位置**只读**：全仓写点只有 `paths.runtime_json_path()` 一处，任何形态（载荷 / 仓内直跑 /
CLI / 测试）都走它——实测仓内形态、不带任何 env 时解析结果就是 `<state>/runtime.json`。
不迁移的代价是改造当天全机变新设备、限额重计且历史账本断档。

**新工具 `vod_auth_ensure`（core pack，判 + 领，幂等）**：

| 当前态 | 动作 | 返回 |
|---|---|---|
| `VOD_JAVA_API_KEY` 显式存在 | 只探针，绝不覆盖 | `source=env` |
| runtime 有显式 key（`auth init` 写入，tier≠anonymous） | 只探针；被拒即 fail fast | `source=runtime-key` |
| runtime 有匿名令牌且 `verified` | 原样返回 | `source=runtime-anonymous`，`changed=false` |
| `no-key` / `expired-anonymous` / `device-mismatch` | 领零字段匿名令牌 → 落 state → 复探 | `source=new-anonymous`，`changed=true` |
| `rejected`（显式 key 被引擎拒） | **不领**，报错（fail fast，不静默降档） | `verified=false` + guidance |
| `unreachable` | **不领**，不判定 | `verified=null` |

返回字段：`tier / source / fingerprint / verified / reason / changed / base`；
`source ∈ {env, runtime-key, runtime-anonymous, new-anonymous, none}` —— 事后审计要能回答
"这身份是哪来的"，所以 runtime 里的显式 key 与自动领的匿名令牌分开报（前者被拒必须
fail fast，后者被拒可重领）。
`auth_status` 保持**只读**语义不变（ensure 是唯一有副作用的认证工具）。

**并发语义（明确写死，不加跨网络全局锁）**：两个宿主同时 ensure 时可能各领一枚匿名令牌
（最后写入者生效）。不为此加覆盖"探针 + 领取"的全局锁：那段持锁最长 25s，会把其他宿主的
账本/草稿写全堵住，代价大于收益。状态写本身是事务的（进程内 RLock + 跨进程 flock +
tmp→`os.replace` + 0600），并发不会丢更新、不会写坏文件。

**远程面 = 同机独立进程，与本地同效果（2026-11-16 负责人澄清）**：远程部署的实际形态是
"同一台机器上把 MCP server 跑成一个常驻进程（127.0.0.1:9528），多个 agent 通过 HTTP 连它"，
不是跨机/多租户。因此：

- 身份：与本地同一套——请求头 Bearer 优先；没有就由服务端领/复用**机器级匿名令牌**。
  旧口径"服务面不代签身份"（-32012 硬拒）已废除。
- 工具面：`REMOTE_WITHHELD` 收窄到只剩 `vod_packs_configure`（进程内开关，HTTP 每请求现造
  server、多 agent 共用会互相影响）。`vod_draft_voices` / `vod_commit_voices` /
  `vod_list_submitted` 远程同样可用。
- 两段式放开的前置是**草稿归属隔离**：草稿落盘时记 `owner = _session_key(client_info)`
  （宿主名 + 身份 hash），commit 校验归属，不同 clientInfo 提交一律 -32011
  （"这份草稿不属于当前客户端"）。旧草稿无 owner 字段 → 兼容放行（升级不断回合）。
- **匿名代领护栏**：回环绑定（同机部署默认 `127.0.0.1`）与本地一致、可代领；
  非回环绑定（`--host 0.0.0.0` 或可能被反代触达）**默认关闭代领**，调用方必须带
  Authorization，确需开启用 `--allow-anon-mint`（`net.ANON_MINT_DISABLED` 进程级开关，
  判定在 `transport_remote._apply_anon_mint_policy`）。理由：服务面无内建鉴权，
  代领等于"任何能连端口的进程都能用本机身份提交、消耗额度"。

**边界（不做什么）**：

- 不做跨机器共享：令牌绑设备锚点，集中发放要改引擎侧；共享卷上的 flock 不可靠，
  并发领取会重复。
- 不做每宿主一令牌：与"机器级一份"相反，且把匿名限额拆散。
- 不让 skill 读 env 判档：env 是 **server 进程**的环境，宿主 agent 侧读到的可能不是同一份；
  server 身份由 `net._live()` 现读 env > runtime，skill 只调 `vod_auth_ensure` 读结果。
- **dsh 壳本轮不并入**（诚实边界）：它是独立的 JS 实现，runtime 里混装身份与账本
  （cap 200 环形），与 Python 侧共享同一 JSON 需要跨语言共用锁与字段契约——那是破坏性合并，
  单独评审再做（记为待办，不占新编号）。当前若手工把 `VOD_DSH_RUNTIME` 指向 `<state>/runtime.json`，
  两侧会互相覆盖账本（无共同锁），**不要这么做**。

**护栏**：`<state>/runtime.json` 0600（写后立即 chmod，已有）；同目录 flock（已有）；
镜像克隆检测（`firstBootAt` vs 本机 uptime，已有）+ 装机 checklist"冻结前清 state"；
`uninstall --clean-global` 把 state 列为外部残留逐条打印后删除；**测试必须把
`VOD_DEVKIT_HOME` 指到 tmp，且测试隔离门禁增加第 4 项快照（机器级 state 目录清单）**——
否则机器级"存在即用"会让测试读到真机令牌。

用例承载：`tests/test_token_machine_scope.py`（S145）。

## dsh 走 MCP client：壳只留 UI（D-dsh-mcp-b-1，2026-11-16）

**参照物做法**（huaweicloud-devkit，本地克隆核对）：dsh 不做专用 JS 工具插件，用 dsh 本体自带的
`@deepseek-ai/dsh-mcp-client` 把 MCP server 挂成宿主工具；profile patch 里一个**托管块**
（`# … start/end` 注释包裹 + 幂等替换 + 卸载只摘自己），缺 client 时用 `dsh plugin add` 自装。
本仓照抄这套**形态**（不抄业务面）。

| 项 | 实现 |
|---|---|
| 版本门槛 | `_dsh_root()` = `realpath(dsh).parent.parent`；client 装在**本体** `node_modules/@deepseek-ai/dsh-mcp-client`（profile 的 node_modules 里没有） |
| 自装 | 缺则 `dsh plugin --profile <p> add @deepseek-ai/dsh-mcp-client`；`VOD_DSH_SKIP_MCP_CLIENT_ADD=1` 跳过（跳过/失败都降级，不阻断安装） |
| 托管块 | `config_forms._DSH_MARK_START/_END`；`find_dsh_block` 优先按标记定位，无标记回落旧 `- id: vod-devkit`（兼容已装机实例） |
| 有 client | 两条 insert 子项：`id: vod-devkit-mcp`（serverName=vod-devkit、stdio、`command`=安装器解释器、`args`=载荷 `server.py`、env 显式 `VOD_DEVKIT_HOME`/`VOD_JAVA_API_BASE`/`VOD_PACKS`、**不传 key** 走机器级匿名令牌）+ `id: vod-devkit`（壳，`registerTools: false` 只留 UI 半） |
| 无 client | 只写壳块（6 工具自注册，`registerTools` 缺省 true），报文写明"降级" |
| 卸载 | 只摘托管块；**`cordis.patch.yml` 是共享文件，永不整文件删**（本轮实锤：旧卸载路径会整份删掉，连带用户的其它 insert 块） |

**为什么壳不能继续注册工具**：MCP 与壳同时注册 = 两个 `vod_submit_voices`、两套账本/令牌，
用户可能重复提交。所以 `registerTools=false` 是 B 模式的强制项，降级形态才保留 true。

**实测**（工具在 `vod-devkit-verification` 技能的 `scripts/dsh-mcp-probe.py`）：dsh 0.2.1-rc.5 +
mcp-client 0.2.1-rc.5，stdio 与 streamable-http 两条传输都通；server 日志 argv 指向载荷
`server.py`，模型回执 0.5.9；工具名 `mcp__vod-devkit__vod_*`。

**边界**：本轮 MCP 模式只做 stdio，`SUPPORTS_REMOTE` 仍 False（client 支持 streamable-http，
远程 attach 单独一轮）；**UI 半不随本方案统一**——`packages/dsh/src/client.jsx` 仍是浏览器直连
引擎（自己领令牌、自己提交），agent 工具面与 UI 提交是两条链。

用例承载：`tests/test_dsh_mcp_mode.py`（S146）。

## 载荷生命周期与显式清理（D-prune-payloads-1，2026-11-16）

载荷是"宿主入口指向的稳定副本"（`~/.vod-devkit/payloads/<ver>/`），与 npx 缓存解耦；每次
install 覆盖当前版本、**从不删旧版本**。清理只有一条路：显式 `prune --payloads`。

| 阶段 | 行为 |
|---|---|
| install | stage 当前版本；不删任何旧版本（删错=某宿主配置指向的 `server.py` 消失） |
| doctor | 报 `载荷：在用 X(宿主…)；未被任何安装行引用 [Y, Z]（不自动删…）` |
| prune (dry-run) | 列 版本/大小/路径 + 总量，不动盘 |
| prune --apply | 删除清单（**只认带 `payload.json` 的 stage 产物**，保留当前版本与在用版本，`--keep N`），交互 y/N / 非 tty 需 `--yes` |
| uninstall --clean-global | 复用同一实现（`payload.prune_candidates` + `remove_payloads`） |

不变量：只删载荷目录；机器级 state（令牌/账本/`.migrated`）一律不碰。

用例承载：`tests/test_prune_payloads.py`（S148）。

## 安装期产品校验的凭据复用（D-token-reuse-1，2026-11-16 真机实锤）

产品硬校验需要一枚匿名令牌，而引擎对"同网络当日 / 同 IP 每小时"的**签发次数**限流
（真机撞到 100/日、60/小时，整批装机被挡）。所以校验链的取令牌顺序是：

1. `VOD_JAVA_API_KEY`（正式 key，不占匿名配额）；
2. `<state>` 里已有的匿名令牌 + 它的 `install_nonce` 作 device（**配对**，S1 设备绑定）；
3. 都没有才新签一枚。

失败分档（文案必须可区分，否则排错方向会错）：`401` 换锚点重领重试一次 → 仍 401 报"鉴权
异常（可能集群令牌不同步）"；`429` **立即停**并报"签发被限流"；网络异常重试一次后报"不可达"；
目录空单独一档（指向 T7i 部署）。

遗留：`host_matrix --audit` 每次隔离装一个宿主 = 一次签发，次数随宿主数与 profile 数增长；下一轮做
productCatalog 的 state 缓存（TTL + 强制刷新开关）。

**已落地（S149）**：校验成功的名录落 `<state>/product-catalog.json`（base 键控 + 7 天 TTL +
`--refresh-product-catalog` 强刷）；巡检走 `VOD_SKIP_PRODUCT_CHECK=1`（`host_matrix._run_install`
自动设）——巡检验装载面，不重验归因名单。

用例承载：`tests/test_install_product_auth.py`（S147 / S149）。

## 巡检探针自证（D-matrix-probe-1，2026-11-16）

巡检/矩阵的 `_probe` 必须让**被装的那份载荷**自证，而不是让巡检进程的根变量决定它读谁的
`build-info.json`：

1. 子进程 env pop `VOD_DEVKIT_{SRC,DIST}_ROOT` / `VOD_DEVKIT_ROOT`（entry 显式声明才保留）；
2. 第二判据 = 载荷文件自证：entry 指向的 `vod_mcp/server.py` 所在载荷目录的
   `build-info.json` 版本必须 == 期望构建版本（文件不受 env 影响）；
3. 报文必带"载荷版本 / 期望版本 / entry argv"，一眼能审。

真机复验：修前 `9 PASS`（假绿）→ 修后 `0 PASS / 9 DRIFT`（载荷与壳 0.5.11 vs 构建 0.5.14）。

用例承载：`tests/test_host_matrix.py`（S150）。

## doctor 自愈的边界（D-doctor-repair-1，2026-11-16；**判据已被 D-doctor-repair-2 取代，本节保留历史**）

D-doctor-repair-1 只解决了"切块"，判据仍是块文本比对——该判据把环境值当正确性，被
D-doctor-repair-2 推翻（结构化不变量 + 安装期真源，见下节）。当时的口径如下（不再执行）：

doctor 的 dsh patch 自愈只做一件事：让文件回到**安装器该写的样子**。判据是块文本比对
（`_patch_block(...)` 生成块整体 `in text` 即完好），重建走 `upsert_patch`（托管标记优先划界）。
**绝不用 `- ` 猜边界**——mcp 块的 args 列表项形如 `- /path/server.py`，会把块从中间切断，
再叠加旧形态块后文件里出现两份 `- id: vod-devkit`，后续自愈全部 refuse，工具面静默降级。
多块/形态未知 → 只报告 + 人工指引，不动字节。

用例承载：`tests/test_dsh_mcp_mode.py`（S151）。

## doctor 自愈：结构化不变量 + 安装期真源（D-doctor-repair-2，2026-11-16）

自愈**只补形态缺口**，不比"整块文本"，因为块内嵌 `command` / `VOD_DEVKIT_HOME` / payload 路径
三处安装期环境值——拿当前进程重新生成再比，会把环境差异当配置损坏（换解释器改 command、
手工 `uiBase` 被回写、PATH 无 `dsh` 时删 MCP 块、缺 payloadDir 时写相对入口）。

| 形态 | 判定 | 动作 |
|---|---|---|
| 缺 MCP 块 / 缺壳块 / 壳未 `registerTools:false` | 形态缺口 | 用 `dshPatch` 记录值重建（`upsert_patch`，标记划界）|
| 已有块、字段与记录不同 | 字段差异 | **只报告**，不动字节（手工定制保留）|
| 无 `payloadDir` / 无 `dshPatch` | 环境不可判定 | 不动字节 + 打印重装指引 |

`dshPatch = {command, stateHome, mcpClient}` 由 install 写入 manifest 行；老账本无此字段时
才回退环境探测（只为补缺口，并提示重装固化）。

## dsh 多 profile：账本行键与"在用"集合（D-installs-profile-1，2026-11-16）

- 账本行键 = `(target, dshProfile)`：web / headless 各一行；doctor 遍历全部 dsh 行逐 profile 自愈，
  uninstall 只摘对应的那份块。
- `prune --payloads` 的"在用"集合 = `installs[].payloadDir` ∪ `~/.dsh/profiles/*/cordis.patch.yml`
  的 args 指向的载荷根——版本错位时另一个 profile 仍在用的载荷不会被当孤儿删掉。
- `--audit` 逐 profile 判，并读 manifest 的 `dshPatch.mcpClient` 区分"MCP 块被清"（DRIFT）
  与"合法降级"（PASS）；降级分支只做配置面判据，不冒充 L3 拉起。

## provenance 判据的取值面（D-doctor-provenance-1，2026-11-16）

诊断链（doctor / verify 的 preset 分支）判定「装的东西是不是同一份构建」时，一律读
**载荷** `payloadDir/build-info.json`：

| 判据 | 取值 | 为什么不是另一个 |
|---|---|---|
| 安装记录 ↔ 安装产物同源 | `<payloadDir>/build-info.json` | 根 `build-info.json` 是 tracked 的发版快照，release 记 `v^`、install 重烧 HEAD，发版后天然不等 |
| 回落 | 老账本无 `payloadDir` / 载荷缺文件 → 仓根 | 不新增误伤面；载荷缺失另有完整性 FAIL |
| 与调用方的约定 | `doctor._provenance_problem(mf) -> str \| None` | 单一入口，doctor 与 verify 共用，禁止第二套读法 |

## hermes 落点重定向的归属判据（D-hermes-reroot-1，2026-11-16）

`host_adapters/hermes._spec()` 在设了 `HERMES_HOME` 时重定向落点，判据是**前缀归属**：

| 情形 | 行为 |
|---|---|
| 落点在 `$HOME/.hermes/` 之下 | 改挂到 `HERMES_HOME/<尾巴>` |
| 落点不在此前缀下 | 原样保留（不改写别人钉的路径） |
| `HOME` 是隔离目录、`HERMES_HOME` 在该 HOME 之内 | 认它（矩阵 / 显式钉根，S168-3） |
| `HOME` 是隔离目录、`HERMES_HOME` 在真实家目录之下 | 忽略（网关泄漏面，落点跟随 HOME，S168-2） |
| `HOME` 是隔离目录、`HERMES_HOME` 在两者之外 | 认它（容器挂载卷等显式运维配置，S168-1） |
| `HOME` 是真实家目录 | 尊重 `HERMES_HOME` |

为什么不用「路径里有没有 `.hermes` 分量」：HOME 自身可能落在含该分量的路径里
（`<tmp>/.hermes/cache/...`），按分量搜索会命中外层并产生自我嵌套（2026-11-16 矩阵实锤）。
与 `_cli_env()` 保持同源——隔离时 CLI 与文件写入的落点都跟随 HOME。

## 共享语义的单一入口（D-single-entry-1，2026-11-16）

三处「同一语义」只允许一个实现，其余消费者调它：

| 语义 | 唯一入口 | 曾经的重复 | 铁律 |
|---|---|---|---|
| 账本里的安装行 | `common.install_rows(mf)` | doctor ×3 / prune / packs / uninstall | 空 manifest 返回 `[]`；老账本（顶层有 `target`）退化为单行 |
| 行视图（顶层 + 行覆盖） | `common.row_view(mf, row)` | doctor ×2 / verify | 行内 None **不覆盖**顶层；不改入参 |
| 最近一次安装行 | `common.latest_row(mf)` | verify | 取 `install_rows()` 末条，空账本 `{}` |
| hermes 落点判定 | `hermes._home_state()` / `_effective_hermes_home()` | `_cli_env` / `_spec` | 隔离 HOME 下三分支（根内认 / 真实家忽略 / 其余认）；CLI 与文件写入同源 |

为什么这是"合理性"问题而不是风格问题：多份实现的判据会**各自演化**。实测已出现两种分叉——
uninstall 的安装行读法少了 `target` 判据（空账本被当有安装），hermes 的落点判据给出相反结论
（CLI 与文件写到两处）。门禁形态取"禁止第二套实现"（`tests/test_common_single_entry.py` 扫源），
而不是逐个调用点补断言——后者只能锁住当时想到的那几处。

## 落点与 provenance 的不变量（D-review-r2-1，2026-11-16）

| 不变量 | 形态 | 门禁 |
|---|---|---|
| 文件落点根 ≡ CLI 落点根 | `hermes._spec()["configPath"].parent.parent == hermes._cli_env()["HERMES_HOME"]`（未设时按 `<HOME>/.hermes` 解释） | S162，参数化 5 组 env，断言等式而非抽样 |
| 测试不写被断言的 tracked 文件 | `sync(write_build_info=False)`；根 build-info 只在发版/显式 build-info 时重烧 | S163-1，比较 sync 前后字节 |
| 溯源口径 | version：根 == 包内 == package.json；commitSha 须为本仓真实提交（不锁单值） | S163-2 |
| 不可核验 ≠ 通过 | 载荷与仓根都无 build-info → 「无法核验 provenance」 | S164-1 |
| preset 完整性覆盖全行 | 逐 `install_rows()` 行判，报文带 target | S164-2 |
| 外部 CLI 调用必须有超时 | `_CLI_TIMEOUT`（默认 60s），超时走降级分支 | S165 |

## 安装期读回与写入纪律（D-install-readback-2 / D-host-home-verify-2 / D-atomic-host-writes-1，2026-11-17 真机）

| 面 | 判据 | 落点/兜底 |
|---|---|---|
| dsh 壳版本 | profile 的 `node_modules/dsh-vod-devkit/package.json` == 安装器版本 | 读到且不等 → install 非零退出、不写 patch；完全读不到 → 告警不阻断 |
| hermes hook | 行存在 → 命令指向当前 hook 脚本 → 两条同一解释器 | 任一条不满足 doctor FAIL；install 侧「同 mark 命令不同即替换」 |
| JSON 宿主注册 | install 收尾 `host_verify.require_ok()`：条目在、enabled≠false、server.py 存在、远程 url 非空 | 落点走适配器 `config_path()`（codeartswork 新旧目录） |
| 宿主体检的遍历面 | `common.install_rows(mf)` 的 target 集合 | **禁用 `mf["target"]`**：它是最近一次安装的宿主，多宿主机器上整段体检会不执行 |
| 写入 | 宿主主配置/共享 JSON/状态一律 `atomic_write_text` | 软链先 resolve；owner 写位缺失抛 PermissionError；bak/dest 例外 |

对应用例见 `docs/proposal.md` 同名章节（用例编号只在 tests/ 与 proposal 里出现，避免本文件抢走承载）。

## 预采集路由的判定口径（D-router-scope-1，2026-11-17）

`vod_router` 是确定性路由：只回 `{"context": …}` 或零输出，不跑模型。旧实现只判「有没有触发词」，
把**讨论反馈这件事**当成**反馈**（实测 7 条元讨论 6 条误判，注入把设计评审拐去提单）。判定分三层，
全部落在同一文件的词表上（单一事实源）：

| 面 | 判据 | 反向约束 |
|---|---|---|
| 强入口 | 消息以「提交反馈」开头 → 强指令 | 元语汇不得压掉它（用户指令优先于我们的排除规则） |
| 命中面 | 「现象词/建议词」任一命中（体验差、太慢、卡死、白屏、没反应、希望支持…） | 现象词变体按真实原话补：「体验太差 / 白屏 / 没反应」曾是实测漏判 |
| 排除面 | 命中 `META_WORDS`（代码/用例/门禁/文档/评审/方案/接口/配置/profile/packs…）且不含 `ANCHOR_WORDS`（页面/按钮/登录/导出/加载/点击/体验…）→ 零注入 | 带锚点的自身遭遇必须照旧注入，排除不得扩大成漏判 |

**原因标签（reason）**：路由的每个结论都带一个可审计标签，集合由
`vod_router.REASONS` 声明，用例断言实际产出与之相等，且每个标签必须在本节登记
（`tests/test_router_reasons.py` 是文档与判据的同步门禁）：

| reason | 含义 | 触发条件 |
|---|---|---|
| `empty` | 不处理 | 非字符串或空文本 |
| `envelope` | 宿主信封 | 内部通知/后台回执/压缩摘要，剥完没有用户在说话的标记 |
| `strong-prefix` | 显式指令 | 文本以「提交反馈」开头（任何排除规则都不许压掉） |
| `no-trigger` | 未命中 | 触发词与失能词都没命中 |
| `engineering-object` | 工程自述 | 只有失能词 + 工程对象词 + 无用户视角锚点 |
| `meta-discussion` | 元讨论 | 工程语汇命中且无用户视角锚点 |
| `trigger` | 现象词命中 | TRIGGER_WORDS |
| `disable` | 失能词命中 | DISABLE_WORDS（无现象词时的兜底路径） |


取舍：漏注入的代价是回到概率路由（模型仍可能自识别，显式前缀兜底）；误注入的代价是**当轮任务
被拐走**。两侧都有用例（正/反/显式前缀三条），机制与真机注册细节见 `docs/hermes-router.md`。

## 行为回归的判定分层与退出码（D-e2e-engine-5xx-1 / D-e2e-model-override-1 / D-e2e-indeterminate-1 / D-e2e-exit-codes-1 / D-e2e-runlog-1）

判定基准只有一个：**引擎侧归档行**（`GET /external/voices`，带被测安装的 key 与
`X-Vod-Device-Id`=install_nonce）。模型自述、本地计数器都只是遥测，不做终裁。

一轮套件的结论分四层，逐层都可能「没有结论」，必须与「产品违规」分开：

| 层 | 事实 | 结论形态 |
|---|---|---|
| 引擎不可达 | 5xx/连接类错误（退避重试 4 次后仍失败） | 不可判（环境） |
| 引擎拒绝 | 4xx（鉴权档 / 设备绑定 / 契约漂移） | 鉴权问题（不是环境、不是产品违规，且**不重试**） |
| 宿主回合无产出 | 回复为空 **且** 零落库 | 不可判（回执线与内容线都没有依据） |
| 宿主回复为空但已有落库 | 内容线有结论、回显线无依据 | 回执不可判：内容判据照判，回显线不计违规 |

退出码表（自动化据此分流，优先级 1 > 2 > 3 > 4）：

| 码 | 含义 |
|---|---|
| 0 | 全绿 |
| 1 | 真违规（有 fails；含「异常发生前已判」的违规） |
| 2 | 熔断（窗口内桶达阈值且 `action=exit`） |
| 3 | 不可判（引擎不可用 / 宿主回合无产出 / 仅是回显线无结论） |
| 4 | 鉴权或引擎 4xx |

编排纪律：`run_suite()` 只负责「逐案跑 + 聚合」，退出码只在 `main` 一处计算——异常分支与正常
分支必须吃同一个聚合结果，否则「第 1 条真违规 + 第 2 条遇 502」会被报成「没结论」。

对账纪律（巡检层）：`--audit` **按 commitSha 对账，不只比版号**——版号相等不代表代码相同
（实测：用仓内入口把载荷就地重打成未发版提交，版号不变，巡检照旧全 PASS，而 registry 上同版号
是另一个提交）。判据=载荷 build-info 的 commitSha ∈ 账本该版本的 sha 集，否则 DRIFT。

留痕纪律：每轮自动 tee 一份 `<repo>/.e2e-runs/<ts>-<host>-<model>.log`，头部打
`host/model/argv`，每案开始打 `[case i/n] id` 心跳，收尾打 `e2e[exit]=N reason=…`；
模型是 `--model` 临时覆盖的（只改本轮 argv，不改宿主配置），所以日志必须带模型名，
否则事后无法判断结论是在哪个模型下得到的。**写即刷**：`Tee.write` 逐行 flush、日志文件按行
缓冲——「kill 掉也留下已产生的行」这句承诺只有在缓冲不攒的前提下才成立（实测踩过：只转发
不 flush，进程被 kill 时日志全程 0 字节，旧用例还因为自己先 flush 而绿着）。

## 预采集路由的三层判定与词表纪律（D-router-scope-1）

`vod_router` 是确定性路由（stdin JSON → stdout `{"context": …}` / 零输出，不跑模型）。判定三层：

| 层 | 判据 | 反向约束 |
|---|---|---|
| 强入口 | 消息以「提交反馈」开头 | 任何排除规则都不得压掉它（用户指令优先） |
| 命中面 | `TRIGGER_WORDS`：现象词（报错/卡死/失败/打不开/超时/崩/白屏/没反应…）+ 建议词（希望支持/建议增加/能不能…）+ 口语词（太慢/太麻烦…）；**第二条路径** `DISABLE_WORDS`：失能/否定描述（用不了/没法用/挂了/闪退/丢了/空的/没动静/不相关/难用/不回/转圈/自动刷新） | 触发词表必须 ⊇ SKILL 里教模型的现象词表；失能词是覆盖率的兜底——词表只能覆盖"我们想得到的说法"，用户常用的是失能描述 |
| 排除面 | 命中 `META_WORDS`（代码/用例/门禁/文档/评审/方案/… + 工程动作词 改成/抽成/重构/写死/解耦/排查… + 工程第二层 CI/构建/编译/流水线/回滚… + **工程搭配**：发布流水线/发布流程/环境变量/测试环境/预发环境/构建产物）且不含 `ANCHOR_WORDS`（页面/按钮/登录/导出/加载/点击/体验…） | 带用户视角锚点的自身遭遇必须照旧注入；用户与工程师共用词（接口/配置/字段/日志/版本）以及裸「发布」「环境」**不进** META——用户也会说「刚发布的版本打不开」「生产环境卡死了」 |

两个实现细节：裸「卡」在装配正则时加边界（`卡(?!片|号|券|通|位|口|车|牌|包|针)`，词表仍只写
一个字，边界只此一处）；词表不变量（无重复/无空串/三表互不相交/只有一处边界规则）由用例锁住。

**判定可解释**：`route_detail()` 把三层结论结构化（decision / reason / 命中的 trigger 与 meta 词），
`route()` 只是它的薄包装——单一判定路径，避免「两层各算一次」。四轮词表问题的共同困难是
「知道结果错、不知道为什么错」，所以排障与语料用例都直接读 `reason`，不再靠人肉跑探针猜。

取舍与残余（不写成零成本）：漏注入的代价是回到概率路由（模型可能自识别，显式前缀兜底）；
误注入的代价是**当轮任务被拐走**。因此「工程对象 + 用户抱怨」的混合句（如「构建太麻烦了」）
会被压掉；用户用了未收录的口语名词会漏。收敛方式是**加语料**而不是加词：每轮新发现的误判/漏判
原文都要登记成语料用例（含反向断言「真实抱怨仍命中」），否则换个词就复发。

## 安装绑定可观测性与归因链（D-attrib-binding-1）

归因次序：用户明确回答 > 原话唯一高置信提及 > 会话记忆（30 分钟）> **安装先验**。
安装先验只在原话出现自指（`attribution.SELF_REFERENCE`：你们家/这个产品/本平台/这插件…）时
生效——这是为了防止「在 A 产品插件里吐槽 B 产品」被错归（错归会污染引擎幂等/判重域）。

可执行性前提：模型必须能**看到**本机绑定。`vod_devkit_info` 的 `manifestSummary.product`
= 安装期绑定产品（runtime state 优先、回落 manifest 唯一绑定、多绑定/未绑定返回 null——
多绑定不许挑一个）。SKILL 据此三分支：有值+自指 → 不问产品、直接建草稿；有值无自指 → 按
候选追问一次；为空 → 追问一次、不许自己挑。**顺序是硬约束**：采集流程第 0 步的首个动作
就是调一次 `vod_devkit_info` 看这个字段——有值+自指时**禁止**先调 `vod_search_products`
或追问（真机实测：不写死顺序时模型会按自己的计划先查名录，拿 score 0 的候选回头追问）。

**判据与被测样本必须解耦**：轮次盐只是标识，不许同时扮演"原话内容"——判据基准先剥盐
（`strip_salt_offset`），否则模型把括号时间戳当插注丢掉这种**正常行为**会被记成 echo 违规并喂熔断。
同理，信封装的不是用户原话：先剥信封再判余文，余文里有用户在说话才继续判。

**门禁必须在独占树上跑**：并发改树时跑全量，结论不可信——实测同一次跑里"测试文件是新版、
实现是旧版"导致用例 100% CPU 空转 600 秒，另有一条因文档正在被改而红、几分钟后单跑就绿。
发版门禁与评审证据一律在独立 worktree + 固定 HEAD 上取。

**门禁漂移先归因**：整套测试前后的机器状态快照（S143）在漂移时不能直接判隔离缺失——
并发跑的真机 install/巡检/e2e 会写账本与 state，那是预期行为。先扫描写入者，有则打印归因、
保持绿；无写入者才是真漏洞，exit 1。

**落库线的三态**：判据不能只有「有行/没行」两态。引擎查询按 `key + X-Vod-Device-Id`
双绑定，重装/复装会**轮换 install_nonce**——用旧设备头查只会拿到旧设备那批行（实测：
旧头查回 11 行、最新 at 停在 11-11；用当前头查，新提交 +0s 即可见）。这类漂移属于
**环境形态**而不是产品违规：引擎有行→可判；无引擎行但本机账本（含引擎分配的 voiceId）
有回执→**不可判**；两者皆空→真违规。（早期把这一现象归因成「引擎查询不覆盖囤积档」，
正交实测后已撤回，见 ADR D-engine-view-gap-1 的修订。）

**盐的位置**：幂等盐 `{t}` 放提示词末尾，不进原话区——模型会把紧挨正文的时间戳当成原话的一部分，
旧实现把盐放在内容起点之前，引擎落库就与比对基准第 1 字起不同（实测判成"改写"）。
**用例基准**：期望落库的用例必须在提示词里带明确提交指令（提交/收录/上报）——「帮我记录反馈」
只表达承接意愿，按纪律还要二次确认，模型会正确停在草稿确认页（实测踩过两次：用例基准误判成
产品缺陷）。这条由语料用例锁住，改提示词不许悄悄去掉提交指令。

**归属判据**：引擎行按双锚点（前缀 anchor + tail）归属用例；多个 anchor 同时命中时按**最长**
归属，不按 SUITE 顺序——实测「请帮我提交反馈：」的行里包含另一用例的锚点「帮我提交反馈」，
顺序匹配会把行记到别人头上（改写/回显桶全错位）。

**回执边界**（S204 的口子必须写死）：工具回执只允许「事实 + 一句处置」，不许塞多步流程——
否则回执会慢慢变成话术容器（每条纪律都往里加一句）。`nextStep` 也不许复制真源词表
（举例会被模型当穷举）。
**契约对账**：回执新增字段必须同批登记进 `assets/contract/tools.schema.json` 并有用例断言
「handler 返回键 ⊆ 契约 properties」——该文件自称单一事实源，账面缺字段等于事实源失真。

**兜底不靠服从性**：把话术写死仍不保证照做（实测模型能背出该条却照样先搜），所以绑定同时
出现在 `vod_search_products` 回执里（`installBinding` + `nextStep`）——模型走到它实际会走的
那一步就能拿到答案。无绑定时不给，缺证据仍按纪律先问一次。缺这个字段时那句纪律在真机上不可执行（实测：
0.5.31 里模型看不到绑定，于是每条正向用例都停在「这条是哪个产品的？」）。
