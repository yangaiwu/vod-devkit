# VOD 插件化（vod-devkit）需求文档

- 需求编号：VOD-PLUGIN（特性分支 feat/vod-devkit-plugin，基于 yangaiwu 分支）
- 版本：v0.1（2026-11-03）
- 状态：待评审
- 仓址修订（2026-11-03，已决策）：直接于独立新仓开发（本仓）；原「P0 先在 VOD-Project 验证、触发条件后剥离」作废。当前暂住 xiaowu2119/vod-devkit，VodTeam org 建仓/转移需组织管理员权限（API 已试：403/transfer 需 admin），有权限后一步转移，仓内容零改动。
- 引擎前置缺口（2026-11-03 复核）：~~vod_kb_search 依赖 KB 查询端点~~ 已随方案 A 删除该工具；现存前置=POST /external/token 匿名令牌端点未实现（VOD-KEY），灰度期以共用 key 过渡。

---

## 一、业务背景与目标

### 1.1 背景

VOD 的分析能力目前只有两条消费路径：运营人员走 vod-system 前端，Java 后端走
workflow/api.py HTTP 契约。AI agent（Hermes、OpenCode、Codex 等）无法直接使用
VOD 的分析引擎、领域规则和知识库检索——每次都需要人转述需求再手工触发。

参考对象：huaweicloud-devkit（v2, 55f53ad0）已验证"插件包被多 agent 集成"的
工程形态：安装器 + MCP server + 技能集 + packs 裁剪 + 声明式安全护栏。

### 1.2 目标

把 VOD 做成与 huaweicloud-devkit 同构的可分发插件包 vod-devkit，使外部
应用（AI agent 类走 MCP，业务系统类走既有 HTTP API）能够：

1. 发起/查询/取回分析任务（以任务 ID 为唯一对账主键）
2. 使用 VOD 领域知识（分类匹配规则、问题分类规则、评分规则）
3. 使用 KB 精准检索三件套
4. 全程受安全护栏约束（写操作需确认、无 DB 直连、无凭据读取）

### 1.3 非目标

- 不改动 28 节点/新链分析引擎本身（引擎只消费不修改）
- 不新建第二套分析实现（vod-mcp 是 api.py 的薄壳）
- 不做 9 个 agent 目标全适配（适配层逐个按真实消费者补）
- 不做对外网开放的鉴权体系（内网先行，任务级 token 鉴权留 P1）

---

## 二、目标用户（2026-11-03 方案 A 定稿：纯采集插件）

**插件只服务一种受众：反馈采集者。**

1. 外部开发者（主目标）：把插件装进自己的 agent/应用，采集用户反馈进 VOD
2. 终端用户：在 agent 里被采集反馈的人（无 VOD 感知，回执说人话）
3. 平台运维：插件安装/诊断/升级

**运营不在受众内**（2026-11-03 拍板方案 A）：运营的分析/看板/任务管理
归 vod-system 前端（既有唯一工作台）；插件中 workflow 三工具与
kb_search 已删除（git 历史可查）。依据：受众耦合（外部安装携带运营
代码路径=攻击面放大）、双信任模型挤一份护栏、且 workflow pack 真实
使用为零。将来"运营 agent 化"若立项=独立内部工具，永不外发。

删除的连锁简化（负复杂度）：preset 双形态→单一采集形态；P1 任务级
token 整块删除；双后端→单 Java 上游；护栏剩采集语义一套。

---

## 三、能力清单（插件对外暴露面）

| 能力 | 类型 | 工具/载体 | 权限级别 |
|---|---|---|---|
| ~~发起分析任务~~ | ~~写~~ | ~~vod_run_analysis~~ | 已随方案 A 删除（f1103df，2026-11-03 拍板：运营归 vod-system 前端） |
| ~~任务状态查询~~ | ~~读~~ | ~~vod_task_status~~ | 同上 |
| ~~任务结果获取~~ | ~~读~~ | ~~vod_task_result~~ | 同上 |
| ~~KB 精准检索~~ | ~~读~~ | ~~vod_kb_search~~ | 同上（零真实使用+受众耦合） |
| 用户反馈声音采集 | 写 | vod_submit_voices + vod-feedback-collect 技能 | confirm 逐次+单批≤50+source 取握手身份 |
| 本机提交记录查询 | 读 | vod_list_submitted（本地账本，cap 200） | 放行（scope=local-machine 明示） |
| 认证自检 | 读 | vod_auth_status（key 指纹化，无 key 给三步引导） | 放行 |
| 分类匹配规则 | 知识 | 技能 vod-category-matching | 只读 |
| 问题分类规则 | 知识 | 技能 vod-problem-classification | 只读 |
| 评分规则 | 知识 | 技能 vod-scoring-rules | 只读 |
| 插件路由入口 | 知识 | 元技能 vod-core | 只读 |
| 安装溯源与宿主感知 | 元信息 | install-manifest + vod_devkit_info 工具 | 只读 |
| dsh 宿主采集 | 写/读 | dsh/ 薄壳（cordis 插件，同语义 3 工具） | 同 MCP 形态（审批走 dsh tools/pre-execute） |

明确不暴露：Excel 批量导入、数据库直连、任何 DB 写操作。
（表内删除行保留是为对账——历史文档曾宣传 5 工具面，实际收敛纯采集后
为 4 工具；删除决策见决策台账「方案 A 纯采集」，git 留档 f1103df。）

---

## 三·四、key 交付方案演进与比对（已定稿：零字段令牌）

插件可被任何人直接 clone/install（公开分发是主路径），key 交付方案
历经三版，比对如下（结论=方案 C 入门 + 方案 B 升级 + 方案 A 通道）：

| 维度 | A 宿主代管制 | B 自助注册制 | C 零字段自动令牌（定稿入门） |
|---|---|---|---|
| 形态 | key 由宿主运维层持有，宿主用户零感知 | 用户填表（产品/联系方式）换 key | 首次提交时插件自动取随机令牌，零交互零字段 |
| 用户摩擦 | 宿主用户零；但只覆盖被集成的宿主 | **高——门槛放在价值之前，会把人跑掉（评审否决）** | **零——装了就能提交，摩擦只剩 confirm 一次确认** |
| 管理台压力 | 户口数=宿主数（个位数），几乎恒定 | 户口数=用户数，人工签发线性涨 | 签发自动化，人工只管滥用事件 |
| 防投毒 | 宿主信誉背书 | 联系方式可追责 | 令牌进低信任档：入库打标+限流+可吊销；污染只影响低信任档 |
| 定位 | 高信任通道（企业级） | 正式档获取方式（升级用） | **默认入门档（主路径）** |

关键认知：key 的目的不是"知道你是谁"（身份），是"有可限流/可吊销/
可计数的把手"——把手不需要用户填任何东西。问责靠档位升级（用出价值
后再补联系方式）与异常处置，不靠进门门槛。**付费（填表）发生在获得
价值之后，不是之前。**

信任三档（越用越信，没有先信再用）：
1. 匿名令牌（零字段自动签发，日限低，source 打标 anonymous）
2. 正式 key（提交量到限后联系运营升级，来源可信）
3. 宿主 key（平台整体对接，宿主持有，最高信任）

感知矩阵（用户不想感知平台是分层成立的）：
| 谁 | 感知 VOD | 感知 key |
|---|---|---|
| 终端用户 | 完全不（回执只说"已收录"） | 完全不 |
| 宿主开发者 | 知道有反馈通道即可 | 可以不（宿主注入） |
| 独立自助用户 | 有意直连，知道 | 令牌自动（无感）/正式 key 有感 |

## 三·四b、深度审计修正（2026-11-03，R1/R3/F2 已修，R2/F1/F3 排期）

R1 声量失真（已修，回归锁死）：确定性 voiceId=f(source,content) 会把
不同用户的同款反馈去重吞掉——声量是分析核心信号，跨调用必须不去重。
修正：voiceId=f(source, content, 调用级nonce)，同调用内重试幂等。
R3 数据污染（已修）：短反馈补齐模板文字曾会进 LLM 分析原文——
修正：title=用户原文（分析消费），description 才允许 "[vod-devkit]"
标记后缀（仅满足引擎 ≥10 字校验）。
F2 回执噪音（已修）：终端用户不见 voiceId，回执说人话。
R2 分析按档过滤（排期，引擎侧）：VOD-KEY 交付范围补"分析链路按
collect_source 过滤匿名档"——过滤落地前匿名/正式混在同一分析漏斗，
该风险明示不过度承诺。
F1 外发 QUICKSTART（排期，一页纸）：含任意 MCP 客户端手动配置片段。
F3 采集技能观测（排期）：识别准确率/确认时机需一次真实用户观测后定稿。

## 三·四c、产品归因与可漂移值（2026-11-03 实测修正）

**归因三层（已实现）**：反馈关于哪个产品不能猜——
①安装绑定（install --product，装插件的人声明，落 runtime.json+manifest）
②反馈内容/调用显式指定 ③询问用户。静默默认已删除（曾为 codearts，
会把 AIShell 反馈错误归因到 CodeArts——归因错误污染目标产品数据，
比报错更糟；护栏 -32013 引导三种解法）。
**引擎缺口（已解决，2026-11-05 口径更新）**：submit 白名单=代码常量
VALID_PRODUCTS（六值，无 AIShell）曾致 AIShell 类反馈被拒收——
T7f/normalizeLoose（MR !152 线）已改为**不设白名单**：任意产品名
归一后未注册落 UNKNOWN 档 + productRegistered 软标记，不拒收
（实测 product=VOD/AIShell 均正常落库）。meta 端点仍以引擎常量为源。
**可漂移值经接口取最新（设计定稿）**：product 白名单/分类六类定义/
功能子类词典都是引擎侧会漂移的枚举字典（本次技能过期即实证），
静态嵌入必漂移。方案=引擎新增只读 meta 端点（GET /external/meta/*：
products 白名单+归一规则、problem-types 六类、dictionaries），
插件安装/首次调用拉取+缓存（runtime.json，TTL 24h）+快照兜底+
stale 标记。/external/products 实测存在但属报告侧全集，与 submit
白名单不是一个集合——meta 端点须以 submit 校验常量为源。
三个技能已按引擎代码重写（真源=n01_classify/workflow_v2/
category_matcher @2bb3fc82；vendor 源 skills md 已过期停用）。

## 三·四d、动态元数据（可漂移值经接口取最新，已实现客户端）

meta 客户端（_load_meta）：GET /external/meta → product 白名单等
可漂移值；缓存 TTL 24h（runtime.json meta_cache）；端点不可达→
快照兜底+stale 标记（引导文案/auth_status 均带 [stale] 提示）。
_resolve_product 白名单校验改用 meta 值（快照兜底时容忍通过并标
stale，宁可收下后引擎侧拒绝也不静默丢弃采集）。引擎端点上线前
快照=当前 VALID_PRODUCTS 六值+别名；上线后插件零改动切换。

场景用例（S11-S13）：

S11 归因-绑定主路径
  开发者 install --product aishell → 用户说"补全太慢" → agent
  confirm → product 取绑定值 → 提交正确归属 aishell

S12 归因-未归因引导
  无绑定无传参 → 护栏 -32013 报错含三种解法+当前白名单
  （meta stale 时附 [stale] 提示）→ agent 询问用户 → 补齐提交

S13 meta 动态取
  引擎新增产品（如 AISHELL）→ meta 端点返回新白名单 → 插件
  24h 内自动跟进（缓存过期重拉）→ 无需发新版插件

## 三·四e、身份界定：归属 vs 认证（2026-11-03 对表定稿）

外部分析（归属/授权拆分 + 网关注入 + 回执 + 防滥用）与我们的设计
对表结论：核心拆分一致（独立推导出同一答案），三处不采纳，一处记 P2。

**已满足（印证项）**：
- 归属/授权分离，反馈场景归属更重要——身份=数据字段（customer/
  userType）流转，VOD 不建账号体系；授权=接入方 key 签发制
- **user_id 绝不进工具 Schema**——contract 无身份参数，模型只填内容
- 身份可信层注入——宿主 env>runtime.json>快照三层；clientInfo 自报
  不可信（"mcp"泛称实证）
- 失败关闭——令牌不可达拒写+引导，不存无归属记录
- 防滥用——零字段令牌+IP 限频+单批 50+内容边界（≤2000 字已落码）
  +低信任档打标

**不采纳（前提不符/超前）**：
- HMAC 签名 _meta.user：我们的信任模型不接收用户身份（无物可验签），
  将来宿主透传 on_behalf_of 时再评估
- 多租户 tenant_id：无需求
- TS Gateway 层：架构前提不符（方案 A 无 Gateway，宿主即 client）；
  不为外部分析重新加层

**记 P2 前置（真增量）**：签名回执（receipt 即凭证）——当前 voiceId
确定性可复述，不具备凭证性；将来做"用户自助查询/撤回自己的反馈"时，
须改服务端 UUID+HMAC 签名回执与声音同库存储。现阶段回执=taskId/voiceId
仅作 agent 对账主键（agent 内部使用，不给终端用户看，F2 纪律）。

场景用例 S14-S16：

S14 身份字段流转（混合形态的现状版）
  已登录宿主（如 CodeArts）→ 宿主侧知道用户 → 反馈的 userType/
  customer 由 agent 按会话上下文填数据字段（不填也允许）→ VOD 侧
  不感知"登录"概念，归属随数据入库

S15 失败关闭
  无 key+令牌端点不可达 → 拒绝提交+三步引导（不产生无归属记录）；
  修复后重试自动恢复

S16 回执凭证（P2 未来态，当前不做）
  用户要求"查我提过的反馈/撤回" → 需签名回执改造（UUID+HMAC，
  服务端生成与声音同库）→ 未实现前该诉求引导走管理台人工

## 三·四f、提交记录查询（两级设计，层级①已实现）

用户提交后追问"我提的反馈呢/提交成功了吗"是采集闭环的自然需求。
三级拆解：

- **层级① 本地账本（已实现）**：submit 成功落 runtime.json submissions
  账本（voiceId/taskId/title 摘要/product/时间，cap 200 环形截断）；
  新只读工具 vod_list_submitted（limit 1-100，最新在前）——agent 凭
  账本替用户回答进度。实现纪律：账本每次文件读改写、只动 submissions
  键（不从内存合并整体回写——曾把陈旧配置泄入调用方，被测试抓住）
- **层级② 引擎级查询（随 VOD-VOI）**：GET /external/voices?since=，按
  key/source 过滤返回该方提交列表——权威跨机；层级③ 终端用户自助
  查询维持 P2（签名回执前置）
- 边界：查的是"已提交记录"非"分析结果"（后者归运营前端）——
  只读工具入 collect pack，不破坏单写口架构

场景用例 S17-S19：

S17 提交后对账（主路径）
  用户："我上次那条提交了吗" → agent 调 vod_list_submitted →
  账本返回最新记录（voiceId+时间+摘要）→ agent 回答
  "已收录，11-03 15:02 那条"，用户全程不见编号

S18 换机/重装边界
  新机器装插件 → 账本为空 → vod_list_submitted 明示
  "本机提交记录（换机不保留）" → 引导理解范围（层级②上线后消除）

S19 引擎级查询（层级②未来态）
  开发者换机后要权威列表 → GET /external/voices?since= 按 key 过滤
  → 跨机一致（随 VOD-VOI 评审落地）

S20 传输协议守卫（2026-11-03 已实现）
  错配场景：VOD_JAVA_API_BASE 配成 http://公网地址 → 插件拒绝发起
  （-32014"Bearer key 明文外发被拒"）→ 引导改 https；本机回环的
  http（引擎同机部署/测试 recorder）正常放行——守卫只拦明文外发，
  不拦本地开发

S21 令牌端点信封契约（D-anon-verify，2026-11-05 真机实锤已修）
  引擎真实契约=ApiResponse 信封 {code,message,data:{token,...}}；
  插件曾顶层取 token 恒 None → 无 key 首提必 -32012"端点不可用"。
  教训=mock 契约未对齐真源（存量测试用扁平 {"token":...} 掩盖缺陷）。
  修复后 mock 全部对齐信封，_extract_anon_token 单函数可测。

S22 匿名链端到端（真机验证通过）
  runtime.json 无 java_key → 首提 401 → 自动 POST /external/token
  （空 body + X-Vod-Device-Id）→ 令牌以 java_key 槽落盘
  （token_tier=anonymous 标记档位）→ 重试 201 → 引擎落囤积区
  key_tier=anonymous、voiceId 带匿名锚点前缀 → 同令牌重提同
  voiceId 幂等（skipped 不烧配额）。

S23 老平台 key 移除语义（D-key-guard 配套）
  runtime.json 携带 legacy key 时提交走 legacy-shared 档（引擎侧
  external.legacy.enabled 接住）；移除后走匿名链。两档行为均在
  真机实测：带 key=legacy-shared、无 key=anonymous，迁移路径
  =删除 runtime.json java_key 即切换，无代码改动。

S24 产品归因安装时注入链（D-anon-ui，2026-11-05 已实现）
  安装配置（profile patch config.product）→ server 半
  ctx.on("webserver/index-inject") 注入页面全局 __VOD_DSH_UI_PRODUCT__
  → client 半模块顶层读取（原 T7d 契约零改动）。apiBase 为 server 半
  自用值，绝不注入页面；跨域部署显式 uiBase 才注入 base 全局。
  归因=安装时配置：使用时零设置、零追问。

S25 裸装散户形态（同源部署）
  散户 dsh plugin add 装包 → 部署方在宿主同源代理 /rest/（nginx
  location /rest/ → VOD 实例）→ UI base=同源相对路径 → 全链通。
  约束：web 宿主必须代理 /rest/（INSTALL.md 部署坑清单）。

S26 设备锚点纯 hex 约束（UI 半对齐 VOD-DEVICE）
  UI 设备 id 必须满足引擎 [0-9a-f]{8,64}——含连字符的 uuid 静默降
  legacy ip|ua 锚点，签发 5 次/天打满即 429（实锤）。生成时去 mask
  截 32 hex。

S27 内容编造防线（AIShell 事故收口）
  用户裸产品名/提问 → 模型不得编造情感结论（"体验不好"实锤）；
  工具描述硬约束（MUST be faithful transcription / NEVER invent
  sentiment / 名词提问不是反馈）+ SKILL.md 字段分级表与推断≠编造
  辨析 + 调用前三项预检。欺骗通道同步封堵：工具面无 product 参数，
  用户自报目标产品不采信、不改归因。

S28 历史页签·本机记录（2026-11-05 已实现）
  弹窗内"我的反馈（本机记录，N）"展开列表：时间/分类/F2 状态口径
  （已收录｜暂存，打开时自动重试）+ 标题截断。数据源=本机账本
  （不出浏览器）+ 本人令牌回执，无越权查询面（引擎按 key 过滤）。
  顶部固定标注"仅保存在当前浏览器；换浏览器或清除数据后不可见"。

S29 数据驻留显式不可用（--no-local-ledger 联动）
  部署配置 noLocalLedger → server 半 index-inject 注入
  __VOD_DSH_UI_LEDGER_DISABLED__ → UI 停写账本+历史面板显式不可用
  （提示"已按部署策略停用"）——不显示空列表（三主体边界拍板）。

S30 极简弹窗（话术纪律的 UI 面）
  弹窗只含：分类 chips/单输入框/历史面板/提交。无平台去向说明、
  无产品团队复核说教、无内部机制词汇——用户只做：选分类、写内容、提交。

S31 分类 UI 移除（2026-11-05 用户拍板，取代初版 hint 口语化方案）
  chips 曾保留枚举、口语化 hint——仍构成三层认知负担（用户分不清
  体验/缺陷边界），而 n01 引擎全量重判已覆盖分类信号、UI 预分类仅
  hint。拍板：撤 chips，表单=单输入框；分类信号回归引擎重判，
  云声回流走默认类型（功能建议）。

S32 设备锚点纯 hex（UI 半对齐 VOD-DEVICE）
  UI 设备 id 生成即纯 hex（32 位）；含非 hex 字符会在引擎侧静默降
  legacy 锚点（签发 5 次/天打满=429，实锤）。

S33 产品归因主键化解析矩阵（T7i，方案 A，2026-11-05 两仓拍板；D-product-id-1）
  ①配置/注入产品名 → meta productCatalog 解析平台 id 后提交（短码先归一再查目录）
  ②纯数字=平台 id 透传 ③目录无此名/不可达（老引擎无 productCatalog 键）→
  规范名兼容通道（引擎 name 命中同样补落 product_id），不静默丢提交。
  回归：tests/test_auth.py#test_product_id_resolution_t7i /
  #test_meta_catalog_cached_t7i（缓存命中零二次请求+老引擎兼容）。

S35 codex 原生插件接入（D-codex-plugin-1，2026-11-05）
  接入终态=原生插件：codex plugin marketplace add <仓>/plugins +
  plugin add vod-devkit@vod-local；插件打包 skills/vod-feedback-collect
  （SKILL.md 渐进式按需加载，采集工作流全量）+ .mcp.json（vod-devkit
  serve 可移植入口）；工具描述承载归因硬约束（含 S1 自报不采信）。
  安装时清理旧 config.toml 段与 AGENTS.md 块（同名双注册防）。
  回归：tests/test_installer.py#test_install_codex_native_plugin_and_legacy_cleanup
  （桩 codex 调用记录+遗留清理）；真机：提单不带 product 不反问、落库
  product_id=1（2026-11-05 实测）。

S36 插件自包含+缓存治理+校验设备锚点（D-codex-plugin-1 增补，devkit 对表三件）
  ①自包含：.mcp.json=python3+./vod_mcp/server.py（相对路径+cwd），插件包
  自带 server（sync_plugin.py 同步+build-info.json 烧录）——去 npm -g 全局
  命令前置，缓存隔离安装后仍可拉起；②stale 缓存治理：install 前清
  ~/.codex/plugins/{marketplaces,cache}/vod-local（codex 缓存不自动失效，
  不清=重装旧版残留）；③安装校验探针全程同 X-Vod-Device-Id+UA（S1 设备
  绑定：token 与 meta 必须同锚点，缺设备头=401 或烧 legacy 日额度）。
  回归：test_plugin_selfcontained_contract（相对路径/server 漂移 sha256/
  build-info 断言）+test_install_codex_native_plugin_and_legacy_cleanup
  （stale 缓存清除断言）；真机：重装后 codex exec 报 version=0.1.12。

S37 安装校验设备锚点一致性（协议级）
  安装器校验链 token 签发与 meta 查询必须携带同一 X-Vod-Device-Id 与 UA
  （S1 设备绑定语义）；每次装机生成新锚点（一次校验一枚令牌额度）。
  测试：tests/test_installer.py#test_validation_probe_uses_consistent_device_anchor
  （桩引擎捕获两请求头比对，协议级零外呼）。

S41 一键发版体系+包内容校验（D-release-1，2026-11-05；devkit release-please 对表）
  scripts/release.sh：bump 从提交历史推导（feat→minor/破坏→major）+版本落点
  表驱动 EXTRA_FILES+整行正则替换+全落点硬断言（根治静默 no-op 两连实锤）；
  npm 包内容门 scripts/pack_verify.py（pack --dry-run 必含/危险项断言，
  publish 前必跑；npm 分发必需 plugins/ 随包——0.2.0 漏项实锤）；RELEASING.md
  发版手册。事件：0.1.12 曾含 runtime.json 凭据残留——已 deprecate+0.2.0 起
  文件级白名单结构性排除。回归：test_plugin_selfcontained_contract（随包
  完整性）+pack_verify（发版流程执行）。

S38 技能拷贝件漂移锁（D-drift-lock，devkit 对表采纳①）
  install 记录技能拷贝件 sha256 指纹（manifest.skillHashes）→doctor/verify
  比对：拷贝件被改/缺失即 FAIL 并引导重装。动机=vendor 规则漂移实锤的
  针对性防线（不采纳 devkit 的 skills-as-MCP-data 架构——5 个静态技能
  拷贝够用，但漂移必须可检；架构迁移挂账到技能规模增长时）。
  回归：test_skill_drift_lock（篡改→doctor 1→重装→doctor 0）。

S39 opencode 自检命令 /vod-doctor（devkit 对表采纳②）
  install --target opencode 随装写入 command/vod-doctor.md（devkit_info/
  auth_status/list_submitted 自检序列+key 明文禁令）；卸载随删。
  回归：test_opencode_doctor_command_file。

S40 三宿主连通冒烟（devkit 对表采纳③）
  scripts/smoke_hosts.py：hermes/opencode/codex 各跑宿主 list 命令断言
  vod-devkit 注册可见；无宿主 CLI=SKIP 不 FAIL（CI 语义）；任一 FAIL 退出 1。
  真机基线（2026-11-05）：三宿主 PASS。

S42 doctor/verify 输出 golden 基线（D-golden-1，devkit doctor-golden 对表）
  用户可见输出快照比对：易变段（HOME/REPO 路径/commit SHA）归一化后锁
  doctor+verify 全输出（文案/判定顺序/新增行漂移即红）；有意变更必须
  UPDATE_GOLDEN=1 重录并在测试失败 diff 里人工过目。测试：
  tests/test_installer.py#test_doctor_verify_golden + tests/golden/
  doctor_verify.txt（无 key 基线，key 态由 auth_status 专项覆盖）。

S43 stdio 探针工具化+pack 门控装配锁（tests/probe.py）
  探针手法沉淀为可复用 Probe（initialize/tools/call/error 分流）；
  新增真实 server 装配层锁：VOD_PACKS=core 无写工具 / core,collect 全四
  工具（协议级，in-process 锁之外补装配层）。
  回归：test_stdio_probe_pack_gating_e2e。
S44 golden 扩展：status 原样契约+preset update 拒绝语
  status=manifest 原样输出（归一化 HOME/REPO/ORIGIN/SHA/installedAt，
  skillHashes 值由漂移锁专项不锁）+preset 形态 update 固定拒绝语。
  回归：test_golden_status_and_preset_update_refusal。

S34 安装期产品硬校验（D-product-id-2，2026-11-05 用户拍板 B，推翻宿主名宽容口径）
  install --product 必须命中 meta productCatalog（名字/平台主键 id），未命中或
  目录不可达一律拒绝安装（宁可不装不可装错）。回归：tests/test_installer.py
  #test_install_rejects_unregistered_product / #test_install_product_accepts_name_or_id
  / #test_install_rejects_when_catalog_unreachable（桩引擎协议级）。

## 三·五、安装溯源与宿主感知（新增需求）

### 背景与语义

插件被分发到外部产品（AIShell、CodeArts 码道等）后，插件方需要回答两个问题：
"这份插件从哪来"（来源溯源）与"它现在跑在谁家产品里"（宿主感知）。
两者均不依赖外部配合，粒度为"产品+版本"，不含终端用户身份（身份识别
属鉴权体系，见非目标）。

### 1. 来源溯源

- 安装时落 install-manifest.json：包版本、构建时烧录的 git commitSHA
  （40 位，构建脚本写入包内 build-info.json）、来源 git remote/ref、
  安装时间、目标 agent、启用的 packs
- 对账口径：来源主键 = commitSHA（不可漂移）；version 号与 tag 名仅为
  展示旁证，远端核验必须比对 commit 而非 tag
- `vod-devkit status/doctor` 读取并展示来源；`vod-devkit verify` 拿
  commitSHA 到 origin 仓库核验（commit 存在且 build-info 一致 = 可信；
  不一致或 commit 被改写 = 篡改告警）
- 分发不用浮动版本拉取（规避 devkit 的 npx -y 版本漂移坑），
  install 支持显式 --ref/--version，已装版本可复现（git show SHA 即全部源码）

### 2. 宿主感知

- 安装时：宿主探测（读写各家产品特征目录）结果写入 install-manifest
  的 target 字段——安装器能装进去即已感知，无需对方上报
- 运行时：MCP initialize 握手的 clientInfo（协议规定客户端必须自报
  name/version）由 vod-mcp 记录——宿主一连上即完成感知
- 新增只读工具 vod_devkit_info：返回本插件版本+commitSHA+当前宿主
  产品及版本，任何一方可随时验证当前会话跑在哪个产品里
- 遥测回传不做（对账数据从 install-manifest 直接获得；企业产品对
  外打点敏感，源头仓库在自己手里无此需求）

### 3. 感知边界

- 可感知：宿主产品名+版本、安装来源（commitSHA）、安装时间、启用 packs
- 不可感知（属鉴权层，P1 任务级 token 范畴）：具体公司/用户身份

---

## 三·八、端到端场景用例（S 系列）

S1 采集闭环（外部开发者主路径）
  开发者装 preset collect 到其 agent → 用户说"补全太慢" → 采集技能识别
  → 逐次征得同意（confirm）→ vod_submit_voices → Java /external/voices
  （Bearer VOD_JAVA_API_KEY）→ voiceId 回执告知用户已收录

S2 来源真实性（恶意场景）
  恶意方冒充其他产品提交：source 由插件握手身份注入 + 引擎侧以签发
  key 身份为准（覆盖 body.source）→ 冒充数据可按 key 圈出打标隔离

S3 恶意灌库
  某方高频提交：网关按 key 限流 429+告警 → 吊销秒级失效 → 已入库
  可疑数据"待复核"标，人工管理台处置（不自动删）

S4 护栏不误杀（E4 修复验证）
  用户反馈原文"系统把我的 password = abc 明文显示了" → content 不进
  文本规则 → 正常入库；scene 字段含 jdbc 直连意图 → 仍 deny

S5 库存消费闭环（内部）
  运营触发增量分析（Java 增量链路：analyzedVoiceIds 差集 →
  analyze/json）→ 采集进来的声音被分析 → 报告/看板 → 产品改进

S6 溯源与信任
  任何宿主调 vod_devkit_info → 版本+commitSHA+宿主身份；
  verify 到 origin 核 commit → 被改包告警

S7（已随方案 A 删除）分析发起归 vod-system 前端，插件不再承载

S8 零字段令牌首次提交（主路径）
  新用户 clone+install → 说"报反馈" → confirm → 插件发现无 key →
  POST /external/token（空 body）→ 令牌落 runtime.json → 重试提交成功
  → 用户全程未经历"注册"

S9 令牌限流与升级
  匿名令牌日提交达上限 → 429/限额提示（含升级引导）→ 用户联系运营
  补联系方式换正式 key → install --java-key 落位 → 限额解除

S10 滥用处置
  某令牌异常高频 → 引擎侧限流告警 → 管理台吊销 → 该令牌后续提交
  401（错误带引导，不是死胡同）→ 本机可重新取新令牌（重新限频）

### dsh 形态场景（S11-S16，2026-11-03 真机验证新增）

S11 dsh 宿主安装与激活（实测链；2026-11-06 起走安装器 D-dsh-install-1）
  `npx vod-devkit install --target dsh --profile <p> --product <产品>`
  装入依赖+产品硬校验+幂等写 profile cordis.patch.yml config 段
  （product/apiBase，工具壳唯一生效通道）→ `dsh --profile <p>` 启动
  日志出现 `[dsh-vod-devkit] Registered 3 tools ... product=<绑定值>`
  （直装 `dsh plugin add` 不写配置，装后须手工补 config 段）

S12 dsh 对话式提交与审批门禁（真机回放，taskId=427）
  用户对 agent 说"提交一个 codearts 问题：速度慢，联系杨爱武" →
  agent 归因 product=codearts → 调 vod_submit_voices → dsh 弹审批卡
  （tools/pre-execute kind:'ask'）→ 用户点 Allow once → 提交入库，
  回执 voiceId/taskId（会话日志 approval/asked→allowed-once 全程留痕）

S13 product 枚举归一（引擎大小写敏感实测）
  引擎 VALID_PRODUCTS 大小写敏感：小写 codearts → 400 且响应体为空
  （排障黑洞）；CodeArts → 201。dsh 壳与 Python 壳各自维护同款
  PRODUCT_MAP 归一映射（agentarts→AgentArts 等）；根治靠引擎侧
  大小写不敏感+错误体非空（已入 VOD-KEY M1-M3 meta 端点范围）

S14 无 key 兜底降级（灰度态真机踩实）
  插件未配 key → 提交 401 → 自动 POST /external/token（零字段匿名
  令牌）→ 引擎端点未实现（401）→ 降级返回 -32012 结构化三步引导
  （不是崩溃也不是裸 404）。灰度正确姿势=配置共用 key（profile
  cordis.patch.yml config 段）；引擎端点上线后该兜底即转主路径

S15 本地账本对账与边界（dsh/MCP 同构）
  dsh 侧 data/runtime.json 账本（cap 200 环形，读改写只动目标键）→
  vod_list_submitted 查本机已提交（scope=local-machine 明示换机不保
  留）；权威跨机查询等引擎侧 GET /external/voices（VOD-VOI V10-V11）

S16 双形态语义一致（架构约束回归）
  dsh 薄壳与 vod_mcp 服务器对同一引擎契约实现：voiceId 同构
  （f(source,content,nonce)、同调用幂等跨调用保声量）、归因三层同构
  （配置绑定>显式传参>报错引导，禁止静默默认）、护栏同构（写须审批/
  单批≤50/content≤2000 逐条拒）。契约变更必须双形态同步——此为
  contract/tools.schema.json 单一事实源纪律在宿主适配层的延伸

### dsh 安装硬校验与 description 截断预算（S45-S48，2026-11-06
### D-dsh-install-1 / D-desc-budget-1 新增）

S45 dsh 安装期产品硬校验（拒/放双路径，与三壳统一口径）
  `npx vod-devkit install --target dsh --profile <p> --product <产品>`：
  --product 必须命中引擎产品目录（复用 _validate_product_or_exit），
  未命中/目录不可达一律 exit 2 拒装；校验先于 `dsh plugin add`——
  拒绝时插件未装入、无「已装未配」半成品。dsh CLI 不在 PATH → exit 2。

S46 dsh 配置幂等落盘与失败修复指引
  add 成功后幂等 upsert profile cordis.patch.yml 的
  `- id: vod-devkit: config: {product, apiBase}` 段（工具壳唯一生效
  通道，真机实证 dsh 0.2.1-rc.5）：重复 install 原位替换不重复插入、
  不吞其它插件段；写失败 exit 1 并输出手动修复格式（插件已装但配置
  未写=半成品，指引必须可照抄）。uninstall 摘插件+移除配置段。

S47 description 截断预算存活（业界截断实测对表）
  宿主对工具 description 普遍硬截断：dsh 固定 500 字符窗口、Codex
  5440 字符硬预算（openai/codex#24299：119 技能 103 个被截断、均值
  232 字符）、OpenCode 共用通用截断。门禁锁死：同意先决条件必须落
  在前 500 字符内（B1，最严窗口存活）、description 总长有上限（B2，
  防挤占宿主预算）；contract 与 dsh 壳双载体同测（双载体漂移已实锤）。

S48 归因口径单源（dsh 无运行期通道）
  dsh 壳 schema 无 product 参数=归因部署配置权威的极限形态（无运行
  期入口即无错归入口）；description 禁止再现旧宽容口径句
  （「explicit arg → config → host identity」曾与实现矛盾——约束源
  三层最陈旧一层生效的复发形态，漂移锁防回流）。

### 追加反馈定性话术（S49-S51，2026-11-06 定稿）

S49 确认环节追加反馈：先定性再问
  用户在确认环节追加表达（如「我看怎么说，你才明白」这类对沟
  通过程的挫败）时，agent 先给一句定性（这句更像什么）再问提
  交范围——不把「这句话算不算反馈」的判断丢给用户（定性是
  agent 的职责，用户从零判断=决策成本转嫁）；定性、确认一轮
  说完，不拆两轮。依据：对 agent 沟通体验的挫败同样指向宿主
  产品体验，属真实信号。

S50 定性留口可纠正（标注理解，非事实断言）
  定性话术必须是「这句听起来更像是对刚才沟通没被理解的挫败
  ——我理解得对吗？」形态：「听起来更像」而非「就是」，显式
  留纠正口子；agent 不替用户下结论——否则「先定性」从降低
  决策成本变成越权定性。确认范围仅两个真实可执行选项：连同
  最初那句一起提交 / 只提交最初那句，一句话拍板，不加第三
  选项抬高决策成本。两个补口（2026-11-06 用户确认）：①只提
  交追加句的极端选择有括号兜底出口（「想只提交第二句也可以
  直接说」），不进并列选项；②纠正闭环——用户纠正定性后 agent
  不辩论、按纠正后的理解走，但 content 仍是用户原话逐字，
  禁止拿纠正后的「新定性」改写原话（话术尾句：「如果我理解
  得不对，直接纠正，我按你说的原话提交，不改写」）。

S51 禁空头承诺（无承载的机制不得进话术）
  不许向用户提供引擎/插件不存在的机制——如「这句作为过程反馈
  单独记录、不混入产品声量」：客户端无过程反馈通道，引擎无此
  分类档（content 入库后由引擎重判），承诺即空头支票，用户选了
  实际做不到。「过程反馈与产品声量分离」若确需，属引擎侧新
  承载，先有承载再进话术（每参数每逻辑都要有依据铁律的话术
  面应用）。

## 四、验收用例清单（在目标环境执行，工具不入库）

| # | 用例 | 预期 |
|---|---|---|
| U1 | agent 配置 mcpServers 指向 vod-devkit-mcp，重启会话 | 工具 4 个全部可列举 |
| U2 | ~~调用 vod_run_analysis（白名单 profile，≤上限条数）【内部形态 preset full】~~ | 已随方案 A 删除（运营归 vod-system 前端） |
| U3 | ~~未经用户确认调用 vod_run_analysis~~ | 同上（confirm 规则现由 vod_submit_voices 承载，见 U30） |
| U4 | ~~vod_task_status(taskId) 轮询 U2 任务~~ | 已删除 |
| U5 | ~~vod_task_result(taskId)~~ | 已删除 |
| U6 | ~~vod_kb_search("评分规则")~~ | 已删除（知识以 skills 形态本地分发，不走 HTTP 查询） |
| U7 | 提示词含 mysql/jdbc/t_vod_ 直连意图 | 被 deny 规则拦截 |
| U8 | VOD_PACKS=core 只装路由技能 | kb/工作流工具不出现 |
| U9 | vod-devkit install --target hermes | 落 MCP 配置+skills，doctor 全绿 |
| U10 | vod-devkit uninstall | 配置与 skills 清干净，引擎不受影响 |
| U11 | vod-devkit install 后查看 status | install-manifest 展示版本+commitSHA+来源 remote/ref+target+packs |
| U12 | vod-devkit verify | SHA 在 origin 存在且 build-info 一致=可信；改动包内容后 verify 报篡改 |
| U13 | 宿主以 MCP client 连接后调用 vod_devkit_info | 返回插件版本+commitSHA+宿主产品名与版本（来自握手 clientInfo） |
| U14 | git show <manifest.SHA> 于 origin | 与已装包内容一致（版本可复现） |
| U15 | 改 contract/tools.schema.json 后跑 CI | 实现侧 schema 未同步跟随契约即测试失败（单一事实源生效） |
| U16 | AIShell/CodeArts 等 MCP 客户端直连 vod-mcp | 不改 Python 核心即可列举并调用全部工具（宿主矩阵分流验证） |
| U21 | 协议级：所有上游调用抓包 | Authorization: Bearer 头必在（E1 回归锁） |
| U22 | 协议级：submit_voices 抓包 | 路径=Java 前缀 /rest/.../external/voices，用 VOD_JAVA_API_KEY（E2 回归锁） |
| U23 | 反馈 content 含凭据字样（password = abc） | 不被文本规则误杀，正常提交（E4/S4） |
| U24 | install --preset collect 后 tools/list | 无 workflow 工具（外部分层生效） |
| U25 | vod_auth_status 输出 | 单 javaKey 指纹（无 workflowKey）；无 key 时输出三步引导 |
| U26 | 无 key 首次提交（令牌端点在线） | 自动取令牌→落 runtime→重试成功，taskIds 正常返回 |
| U27 | 令牌端点不可用 | 结构化引导错误（含令牌/升级/宿主三步），不是裸 404 |
| U28 | auth_status 在 hermes 会话内调用 | 报 meta 状态（source/stale/产品数） |
| U29 | meta 端点在线，两次调用 _load_meta | 第二次命中缓存不再请求（TTL 内） |
| U30 | meta 端点不可达 | 快照兜底+stale 标记，引导文案含 [stale] |
| U31 | 绑定 product=aishell 后提交（无传参） | 归因取绑定值，白名单校验经 meta |
| U32 | 提交 2001 字反馈 | 逐条 rejected（content 超 2000），同批合法条照常提交 |
| U33 | 工具 Schema 审计 | 无任何身份参数（user_id/receipt_id 等） |
| U34 | userType/customer 填写 | 仅作数据字段入库，不作鉴权依据 |
| U35 | 提交 3 条后调 vod_list_submitted(limit=2) | total=3，返回最新 2 条（最新在前），含 voiceId/taskId/摘要 |
| U36 | 账本落盘审计 | runtime.json 只新增 submissions 键，其他配置（key/meta）零触碰 |
| U37 | 用户问"提交了吗"（会话内） | agent 经账本回答时间+内容摘要，编号不展示给用户（F2 纪律） |
| U38 | JAVA_BASE 配成 http://公网地址 | 拒绝（-32014），引导改 https；127.0.0.1/localhost 的 http 放行（回环） |
| U17 | 未确认调用 vod_submit_voices | confirm 拦截（逐次同意），零入库 |
| U18 | 单批 51 条声音提交 | deny（上限 50） |
| U19 | 调用方伪造 source=fake-host 提交 | 引擎收到的 source=握手 clientInfo.name，伪造无效 |
| U20 | 提交后用户拿 voiceId 追问 | 以 voiceId 对账受理状态（引擎端点 VOD-VOI V1-V7 上线后） |

---

## 四·五、终态目标（六维）

一句话终态：VOD 成为"被集成的能力"而不是"被使用的系统"——任何 agent/应用
想用 VOD 分析能力，集成成本趋近一条配置；每次集成的来源、宿主、行为可
对账、可审计、可吊销。

| 维度 | 终态标准 |
|---|---|
| 分发形态 | 独立仓 VodTeam/vod-devkit，git tag 发版，install 一条命令（探测/packs/manifest 全自动），verify 十秒内回答"这份是谁、从哪、改没改" |
| 宿主覆盖 | 适配层跟着月活走：Hermes + CodeArts 码道 + AIShell + ≥1 通用 agent 成熟即达标；连续一季零使用的适配层降级维护模式；新宿主接入成本 ≤1 周 |
| 能力面 | 任务四工具 + vod_devkit_info + KB 检索 + 看板只读查询；写口永远只有 run_analysis；技能与引擎侧规则单一真源同步（改一处，发版自动带出） |
| 安全治理 | 声明式护栏全量生效；任务级 token（P1）+ 管理台一键吊销传播；install/握手/写操作全量审计（SHA+宿主+taskId），可回放 |
| 引擎侧前提 | api.py 契约版本化（external-api-contract.md 带版本号，破坏性变更走 deprecation 期）；任务表唯一事实源，三方（插件/Java/前端）同源对账 |
| 质量 | 插件 CI 全绿门槛 + 每发版对 ≥1 真宿主做装→用→卸回环实测 |

终态刻意不做（已论证的生态位差异，不是缺件）：热更新链（git 即更新）、
遥测回传（manifest 直接对账）、无消费者的适配层（消费者经济性）。

### 独立成仓与规则真源（已决策）

- P0 在 VOD-Project 的 feat/vod-devkit-plugin 分支验证骨架（规则同步机制
  未定型，跨仓成本大于收益）
- 拆仓触发条件（定死）：P0 验收通过 且 第一个外部消费者出现（dsh/WorkBuddy
  上架或 CodeArts 宿主接入）之前，完成剥离到 VodTeam/vod-devkit
- 剥离后规则单一真源仍留 VOD-Project：插件仓构建脚本按 commitSHA 锁定
  vendor 规则文件进包（对齐 devkit 构建期再生 skills 树机制），漂移由
  构建 SHA 锁定+diff 门禁兜住
- 独立仓收益（分发物理事实）：消费者不背 76M 业务仓；访问半径单独控权；
  插件/引擎发版节奏解耦；commitSHA 只描述插件单一产品；满足 dsh 目录
  与 WorkBuddy 市场的独立 GitHub 仓硬门槛

---

## 五、已决策项（负责人确认）

| 决策 | 结论 |
|---|---|
| 插件形态 | 按 devkit 目标形态完整实现（安装器+MCP+技能+packs+护栏），不做最小化裁剪版 |
| 运行形态 | vod-mcp 随 agent 进程拉起，走内网 api.py；远端模式留配置项 |
| 写权限 | run_analysis 默认 confirm + 单次条数上限 |
| P0 技能范围 | 3 个领域规则技能 + vod-core 元技能全量交付 |
| 来源溯源与宿主感知 | P0 交付：install-manifest（commitSHA 主键）+ verify 子命令 + vod_devkit_info 工具；不做遥测回传 |
| 独立成仓 | 终态独立仓 VodTeam/vod-devkit；P0 先在 VOD-Project 验证，触发条件=P0 验收通过且首个外部消费者出现前完成剥离；规则真源留 VOD-Project，构建期按 SHA vendor（方案 A，已拍板） |
| 核心语言 | vod_mcp 用 Python。判定如实记录：5 工具均为 I/O 型（HTTP 转发），名义默认偏 TS；仍选 Python 的主依据=宿主 hook（Hermes .py）+团队栈（49 个 Python 模块）+MCP 窄腰下决策低风险可逆；"贴引擎同语言"降级为弱依据。推翻条件三项见 design.md 第三节 |
| 插件定位（2026-11-03 方案 A） | 纯采集：workflow 三工具+kb_search 删除（git 历史留档）；运营归 vod-system 前端；知识技能留作可选 knowledge pack（零工具）；P1 任务级 token 取消 |
| 工具契约 | JSON Schema 契约文件为唯一事实源，实现侧生成/校验，跨语言边界不做双边手写（含将来 TS 适配壳） |
| key 交付（2026-11-03 定稿） | 零字段自动令牌为默认入门（C 案）；B 自助注册降级为升级档；A 宿主代管为企业通道。比对分析见三·四节 |
| 反馈采集（2026-11-03 拍板） | agent 产品用户反馈进 VOD 闭环。两项均选 A：独立囤积端点（入库不触发分析，引擎侧 VOD-VOI 立项，复用 R0 网关）；插件侧逐次 confirm。source 以握手宿主身份为准不可手填；voiceId 为第二类对账主键 |
| dsh 壳安装硬校验（2026-11-06 D-dsh-install-1） | 方案 A：`install --target dsh` 包装命令——--profile 必填、产品安装期硬校验先于 plugin add、幂等写 profile cordis.patch.yml config 段（真机实证的唯一生效通道）；B（模板写全+README 标红）降级为配套防线。归因部署配置权威：dsh 壳无运行期 product 传参通道（7b 极限形态） |
| description 截断预算门禁（2026-11-06 D-desc-budget-1） | 同意先决条件必须存活于最严截断窗口（500 字符）内 + description 总长上限；contract 与 dsh 壳双载体同测，入 pytest 门禁（随 pre-push 生效）。业界依据：dsh 500 字窗口/Codex 5440 预算（openai/codex#24299）/OpenCode 通用截断，均已实锤核验 |

## 六、待办

- 设计文档评审（docs/vod-devkit-plugin/design.md）
- 评审通过后 P0 开工

---

## 七、分发形态与信任边界（D-key-guard-3，2026-11-05）

### 背景

产品部门将把插件集成进其 agent 随产品对外分发。现有实现默认
「安装者=使用者=运维者」三合一；分发把三者拆开后，每个装机时生成的
状态都成为分发污染源。诊断共 6 项（详见 decisions.md D-key-guard-2/3），
解法=统一形态位收口，不逐个打补丁。

### 方案：distribution 形态位

- `install --distribution devkit|preset`（缺省 devkit）：写入 install-manifest，
  构建期定死、客户机只读；
- devkit=开发/运维自装自管（现状语义）；preset=产品随 agent 分发；
- 逐条分支：①key 禁止随包（安装时忽略并告警环境变量 key，客户机走匿名令牌）
  ②update 禁用（版本随产品发版管理）③verify 降级为本地完整性校验
  （源端比对 unchecked，离线不 FAIL）④首启残留清理（构建机状态自动重生成）
  ⑤本地账本可关（--no-local-ledger，企业数据驻留）⑥日志 1MB 轮转。

### 信任模型三档（对外口径）

| 档位 | 主体 | key 位置 | 说明 |
|---|---|---|---|
| 匿名令牌 | 终端用户（对外分发形态） | 客户机每机自领 | 30 天/500 条+UA 绑定+per-install 命名空间；归因靠 install --product |
| host key | 宿主平台 | 宿主服务端/运维管控面 | 插件经代理访问 VOD，key 不落客户机 |
| formal key | VOD 运营 | 运营自有 | 内部自用 |

红线：**key 落在哪台机器，哪台机器就是信任边界——对外分发的插件产物
禁止预置任何 key**；共享服务器部署（一部署服务全公司）不适用匿名档，
必须走服务端代理。

### 场景用例（DG1-DG9）

| 用例 | 场景 | 断言 |
|---|---|---|
| DG1 | 产品构建机 install --distribution preset | manifest 写入 distribution=preset；缺省 devkit 不变 |
| DG2 | 构建机环境变量带 key 做 preset 安装 | key 不进宿主配置+当场告警；devkit 形态透传保持 |
| DG3 | 客户机打包者漏排 runtime.json | 首启检测残留（java_key/nonce/账本）自动清空重生成，保留 product/java_base，写 firstBootAt |
| DG4 | 客户机正常首启 | 只写 firstBootAt 不清理；二次启动不再触发（防误伤） |
| DG5 | 客户机执行 update | 拒绝并指引"随 agent 发版管理" |
| DG6 | 客户机离线执行 verify | 本地完整性通过即 OK（unchecked），不触 git；产物混装（manifest≠build-info）FAIL |
| DG7 | 企业客户要求数据不留痕 | --no-local-ledger 安装后提交不落账本，vod_list_submitted 返回空；缺省账本开启 |
| DG8 | 客户机长期运行 | /tmp 日志超 1MB 截断轮转，旧日志 .old 保留，新写入正常 |
| DG9 | 运营/宿主运维自己机器注入 key（devkit 形态） | 现有行为不变（fail fast/探针/写后验护栏继续生效） |

### 已决策（负责人确认）

- 对外分发形态禁止预置 appkey（D-key-guard-2 拍板）；appkey 通道 dormant
  保留，收窄为运营/宿主服务端专属（D-key-guard-1/2）
- 形态位写入=我们安装器的 --distribution 参数，产品侧打包流水线零改动
- preset 残留处置=自动清空重生成+告警，不拒绝启动（残留数据全为本机
  可再生，拒启会把误判放大成全功能瘫痪）
- 问题 3（共享服务器部署的令牌模型）落为红线约束（共享部署走服务端
  代理），代码不提前写死——插件侧 base URL 覆盖项已支持代理形态
