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

### 2.1-2.4 已删除（2026-11-03 方案 A 拍板，git 留档 f1103df）

vod_run_analysis / vod_task_status / vod_task_result / vod_kb_search
四工具已删除：运营能力归 vod-system 前端（受众不同+职责耦合+负复杂度，
净删 304 行）；kb 知识改 skills 形态本地分发（零工具零依赖）。历史契约
详见 git 留档；现存工具面=2.5 info / 2.5b auth_status / 2.6 submit_voices
/ 2.5e list_submitted，共 4 个。

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

### 2.5b 动态元数据（_load_meta）

GET /external/meta → {products:[...]}；缓存 runtime.json meta_cache
（TTL 24h）；不可达→_META_SNAPSHOT 快照+stale=True。所有引导文案
与 auth_status 携带 stale 态。设计依据：硬编码枚举必漂移（技能过期
+白名单常量为实证）；/external/products 是报告侧全集不可用作
submit 源——meta 必须以 submit 校验常量为源（引擎侧 VOD-KEY 交付）。

### 2.5f 传输协议守卫（_http 前置）

http 仅限本机回环（127.0.0.1/localhost/::1——recorder 测试与同机引擎）；
非回环 http 拒绝（-32014，引导 https 配置）——Bearer key 不得明文过公网。
https 全场景放行（测试环境 TLS 链路已实测：taskId=419/420）。
双向测试锁死（U38）：http 公网必须拒、http 回环必须放行（报 -32001
而非协议拒绝）。

### 2.5d 身份模型（归属/认证分离）

归属（谁提的）=数据字段：voices[].userType/customer 随声音入库，
引擎侧不建用户体系；授权（谁在调）=接入方 key 三档（匿名令牌/
正式/宿主）。工具 Schema 零身份参数（模型不可伪造归属）；可信层
注入仅作用于 key/product（env>runtime>快照）。失败关闭：无 key 且
令牌不可达→拒写。内容边界：content ≤2000（逐条校验落码），
scene ≤128。签名回执记 P2 前置（用户自助查询/撤回的前置条件，
见 proposal 三·四e）。

### 2.5c 产品归因（_resolve_product）

三层：runtime.json product（安装绑定）> 调用方显式 > 报错 -32013
（引导 install --product / 传参 / 问用户）。静默默认禁止。
别名归一对齐引擎（modelarts→MaaS）；白名单经 meta 动态校验
（快照兜底时容忍提交并标 stale——引擎侧最终校验为准）。

### 2.5e 提交账本与查询（层级①）

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

## 三·九、dsh 薄壳形态（R3 已落地，2026-11-03 真机验证）

dsh 宿主不识 MCP，只认自家 cordis 插件协议——故以独立薄壳包 dsh/
（dsh-vod-devkit@0.1.0）承载同一采集语义。语言跟宿主走（Node ESM），
验证了「宿主原生格式单独写适配壳」的语言选型纪律。

结构：
- dsh/package.json：peerDeps=cordis/dsh-tools/schemastery（均 npm 公网），
  `dsh.bundle.patch` 指向 cordis.patch.yml
- dsh/lib/index.js：cordis 插件入口（name/inject=['tools']/Config/apply），
  注册 3 工具：vod_submit_voices / vod_list_submitted / vod_devkit_info
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

冒烟验证链（.smoke/ 不入库）：mock ctx 加载→3 工具注册→审批门禁
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
| S64 透传正例 | tools.py `_followup_fields`（单源）+ tests/test_followup.py 透传/两段式两例 + dsh/test/followup.test.mjs 行为级 |
| S65 键集合零漂移 | 拒答词集兜底（_FOLLOWUP_DECLINES）+ test_followup 键集合断言（{title,content}）+ 超 2000 截断例 |
| S66 话术固定化 | 固定问句逐字锁（contract description 恰 1 次）+ SKILL 双副本 + dsh 壳描述；desc 预算门禁（≤1500）复验 |
| S67-S70 触发判定块 | SKILL 三层判定块逐字锁（test_followup_skill_judgment_block_locked）+ 契约跳过句（test_followup_skip_clause_in_contract）；dsh 壳 desc 预算 1495/1500 无余量不塞跳过句——dsh 宿主由原生技能层（判定块全量）承载 |

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

- 交付纪律：仓库内只含插件产品代码 + 随 CI 跑的 pytest 用例 + 本对文档；
  验收脚本/环境探测工具不入库，用例清单以 proposal.md 第四节为准
- pytest：工具契约（mock api.py）+ 护栏规则命中 + packs 裁剪 + 安装器
  uninstall 幂等
- 走完整调用链验证后断言才能落文档（入口路由→api.py→任务表）
- description 截断预算门禁（tests/test_desc_budget.py，D-desc-budget-1，
  2026-11-06）：①同意先决条件（确认纪律）必须落在前 500 字符内
  （dsh 固定 500 字符窗口=最严截断；Codex 5440 硬预算曾把 119 技能中
  103 个截到均值 232 字符——openai/codex#24299，被截断即对模型不可见）
  ②description 总长 ≤1500（现状 contract 665/dsh 组合 ~1285，防无界
  增长挤占宿主预算）③双载体同测（contract JSON=python 单一事实源 +
  dsh/lib/index.js 组合串提取）④归因口径漂移锁（禁旧宽容口径句回流）。
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
