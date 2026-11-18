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
比报错更糟；护栏 -32013 引导三种解法——**该本地拦截码后已废除，见 D-attrib-binding-1：
改为运行期引导（无证据就问用户一次），不再有错误码**）。
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
  无绑定无传参 → **不猜产品**，agent 询问用户一次（旧口径"护栏 -32013 报错含三种解法"已废除，
  见 D-attrib-binding-1；meta stale 时附 [stale] 提示）→ 补齐提交

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
  日志出现 `[dsh-vod-devkit] Registered 6 tools ... product=<绑定值>`（壳自注册固定 6 个，S233 校正）
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
  assets/contract/tools.schema.json 单一事实源纪律在宿主适配层的延伸

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
  选项抬高决策成本。纠正后的具体行为见 S53。

S51 禁空头承诺（无承载的机制不得进话术）
  不许向用户提供引擎/插件不存在的机制——如「这句作为过程反馈
  单独记录、不混入产品声量」：客户端无过程反馈通道，引擎无此
  分类档（content 入库后由引擎重判），承诺即空头支票，用户选了
  实际做不到。「过程反馈与产品声量分离」若确需，属引擎侧新
  承载，先有承载再进话术（每参数每逻辑都要有依据铁律的话术
  面应用；泛化纪律已落 decisions.md D-option-executability-1）。

S52 极端选择兜底（只提交追加句）
  用户可能只想提交追加句（如「我看怎么说，你才明白」）而不提
  交最初那句——话术模板括号兜底「想只提交第二句也可以直接
  说」留出口：不作为并列选项展示（不抬高常规决策成本），但
  agent 收到该诉求时必须有对应动作（按用户指定范围提交，content
  仍原话逐字）。

S53 纠正闭环（用户纠正定性后的行为，2026-11-06 用户确认）
  用户纠正 agent 定性（如「不是沟通问题，就是产品卡」）时：
  不辩论，按用户纠正后的理解走，但提交内容仍是用户原话逐字
  ——禁止拿纠正后的「新定性」改写 content（一次抱怨一条+
  原话红线不因纠正豁免）。话术模板尾句：「如果我理解得不对，
  直接纠正，我按你说的原话提交，不改写」。

### 暂存恢复与 UI 收口（S54-S57，2026-11-06 实锤修复）

S54 暂存自动重试成功补提示（dsh 壳，静默重试事故形态）
  提交失败暂存本机后，后台自动重试（U-S3）成功不再静默：
  成功计数+逐条原话落旗标，下次打开弹窗补提示「你之前提交的
  N 条反馈已自动重试成功（当时提交临时失败），产品团队会看到：
  “原话”…」。边界：①voice-id 不出用户面（F2）；②措辞「已自
  动重试成功」说清因果=完成用户此前点提交的指令，非绕过确认
  （暂存仅产生于用户点提交后的技术失败分支，同意前提成立——
  恢复提示不适用于未经确认的内容）；③items 为空时话术降级为
  纯状态告知，禁止「产品团队会看到：」残句；④不承诺更正/撤回
  （引擎无 correct/delete 端点，S51 禁空头承诺）；⑤不带产品名
  （用户不感知归因拍板）。

S55 弹窗输入框禁拉伸（dsh 壳）
  反馈弹窗 textarea resize:none——弹窗内输入框不提供用户拉伸
  角（拉拽顶破布局）；高度由 minHeight 96 承担，内容滚动。

S56 legacy 共用 key 用户面清退
  ①INSTALL.md 删「不要手动塞 legacy 共用 key（明文）」警告句
  ——在面向安装者的文档复述 key 明文=泄漏+提醒存在，反效果；
  改正面口径：不传 key=匿名档（首次提交自动签发零字段令牌），
  legacy 已进兼容收尾（引擎 external.legacy.enabled 开关），
  自装场景装了即匿名档。②nightly E2E 健康检查切匿名令牌主
  路径（零 key）——legacy 属 GTD 兼容收尾，不进健康检查；
  顺带清契约已删的 scene 残留字段。全仓用户面（README/
  QUICKSTART/dsh 壳/MCP 壳/INSTALL）无 key 明文残留。

S57 widget E_AUTH 暂存兜底（VOD-Project 网页壳，对齐 dsh 壳）
  内部清令牌重试后仍 401=提交状态过期，非用户错——草稿必须
  保留（saveDraft 扩 E_AUTH），401 话术人话化：「提交状态过期，
  反馈已暂存，请重新打开后提交」。widget 无后台自动重试链
  （草稿回填+用户手动重提），故无 dsh 壳的静默重试缺口。

S58 dsh patch 块 name 绑定与嵌套铁律（2026-11-06 入口消失事故）
  真机实锤：installer 幂等 upsert 的块模板无 name 行，重装时整
  块替换吞掉 `name: dsh-vod-devkit`——无 name 绑定=client 半
  （反馈按钮）静默失激活，工具壳正常而入口消失（双通道不对称
  掩盖故障）。且 patch 文件被打平（`- id:` 未缩进在 `- insert:`
  之下）时 insert 不生效，工具壳+UI 双双静默消失。修复：①块
  模板自带 name 行（重装不吞）②现网 patch 恢复正确嵌套③回归
  锁（tests/test_installer.py name 绑定断言）。铁律：cordis.patch.yml
  的 id/name/config 必须缩进在 `- insert:` 之下；改动 installer
  块模板必须过 name 断言。

S59 回执话术=行为实况（S51 在回执面的应用，用户抓出）
  匿名直建模式无人工审核闸（提交后引擎自动建 issue），回执
  禁止出现「审核后将以 issue 形式跟进」类不存在的流程承诺；
  issue 链接由 pollForReceipt 在引擎真实建成后补出（U-S2），
  不靠话术许诺。「反馈经审核未采纳」保留——REJECTED 是引擎
  状态闭包真实值（仅引擎明确拒绝时出现），有承载非空头。
  回归锁：回执文案禁「审核后将以」；REJECTED 话术必须挂在
  sync.status==='REJECTED' 判断上。

### codex 熔断与恢复门禁（S60-S62，2026-11-06，D-codex-circuit-breaker-1）

S60 熔断切只读（检测账本触发）
  codex 未确认提交检测账本累计 ≥2 次（7 天窗）→ 触发拍板 B
  熔断：宿主副本 VOD_PACKS 去 collect（submit 摘除，只剩
  vod_auth_status/vod_devkit_info 只读面）+写熔断标记
  （~/.codex/vod-collect-suspended.json，含原因与恢复门禁说明）。

S61 恢复门禁双层（安装面+运行期，缺一可绕）
  ①安装面：标记存在时 codex 装 collect 被拒（exit 2，指引
  token 化前置）；②运行期：serve 的 enabled_packs 同查标记，
  `VOD_PACKS=core,collect serve` 强制降级摘除 collect（stderr
  告警非静默）——缺②则安装门禁可被一条命令绕过（实锤）。
  只读 packs（无 collect）不进门禁。

S62 显式解除=删标记+审计（语义与实现一致）
  --ack-suspension 解除 codex 采集熔断：删标记+追加审计行
  （~/.codex/vod-collect-suspension-audit.log：时间戳+packs，
  可追溯）。语义=真解除（后续安装不再拦），非「每次放行不
  解除」。恢复前置不变：token 化上线并过回归（审计链/重复
  commit 拒/未确认可检测——验收三件套，见
  D-codex-circuit-breaker-1；token 化=最强摩擦+审计链，非
  人类确认硬保证）。

### 复现步骤"AI 追问"前置规范（S63，当期不落，2026-11-06 业界对表）

S63 追问=可选增强，四条硬约束前置（D-followup-design-1）
  复现步骤/预期行为的未来填充通道=AI 追问用户补充，业界共识
  （Sprig/CloudResearch/Culture Amp）：追问是"获取真实补充信息"
  的通道，不是"补全模板"的工具。**当期不落追问话术**（引擎无
  supplement 承载，S51 先有承载再进话术）；立项时四条硬约束
  全部落实缺一不批：
  ①可选增强非默认流程——默认不追问直接按原话提交，按反馈类
    型开关，上限 1 次、一次一问；
  ②话术固定化禁自由生成——固定模板，动态生成必须过中立性
    校验（禁具体操作名/禁是非问/禁引导结构）——引导性追问
    制造"被暗示的复现步骤"，比不问更糟且违反不编造红线；
  ③数据分层——追问回答独立存储（supplement 字段，来源标注
    "用户追问补充"），永不回流 content 原话；issue 复现段只
    引用 supplement 并注明来源；
  ④失败诚实回退——问不到就不出现（可选段形态），不注记不
    强填。
  回归锁（当期）：采集技能话术不得出现追问承诺（无承载），
  见 ux-sync 锁；issue 模板不含复现/预期段（I20 锁）。

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
| U15 | 改 assets/contract/tools.schema.json 后跑 CI | 实现侧 schema 未同步跟随契约即测试失败（单一事实源生效） |
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
| 匿名令牌 | 终端用户（对外分发形态） | 客户机每机自领 | 30 天/5000 条+日 500 条（引擎默认值，vod.external.* 可配置，2026-11-09 提额，见 D-quota-raise-1）+设备锚点绑定+per-install 命名空间；归因靠 install --product |
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

### 复现/预期追问补充落地（S64-S66，D-followup-impl-2，2026-11-08 负责人确认开工）

引擎承载已就绪（V20261106110000003 repro_steps/expected_behavior 列 + I21/I22
issue 渲染「用户追问补充」来源注记 + NULL 诚实回退），S63「当期不落」前提解除，
本节落插件侧生产端。A1=确认环节合并一问（拍板）；A2=MCP 宿主+dsh agent 壳，
UI 壳不加输入框（UX 红线：直达表单不藏门槛）。四约束逐条兑现：
①可选增强非默认流程——仅确认环节内、至多 1 次、一次一问；
②话术固定化——固定问句逐字锁死（回归锁禁改写）：「方便的话，补充一下遇到
  这个问题时的操作步骤或期望的表现吗？不方便回复"没有"，我直接提交。」
  （"不方便回复没有"替代原稿"不方便就直接提交"——减少用户误解，负责人认可）；
③数据分层——答案只进 reproSteps/expectedBehavior 独立字段，只摘录不改写不
  总结，无法拆分落最相关字段，任何内容禁回填 content（content 与旧流程逐字
  一致断言）；issue 侧引擎渲染带「（用户追问补充）」来源注记（I21）；
④诚实回退——答"没有/跳过/不方便"/空白/NULL=两字段不上送立即提交；客户端
  技术兜底拒答词集（_FOLLOWUP_DECLINES/DECLINES），模型不守话术纪律时键集合
  仍零漂移。

验收：
- S64 透传正例：双字段非空 → 囤积载荷含键+trim+content 原话逐字不污染
- S65 键集合零漂移：未追问/未答/拒答/空白 → 载荷键集合={title,content(,tags,userType)}
  与旧流程完全一致（键集合断言非空值断言）；超 2000 引擎同口径截断
- S66 话术锁：固定问句逐字出现在契约 description（恰好 1 次）+SKILL.md 双副本
  +dsh 壳描述；dsh 组合 desc 总长 ≤1500（desc 预算门禁既有锁复验通过）

承载：assets/contract/tools.schema.json（submit+draft 双工具 voices[] 新增可选字段
maxLength 2000）+vod_mcp/tools.py+dsh/lib/index.js+skills/vod-feedback-collect
（双副本 md5 同步+四宿主装机副本已刷）。tests/test_followup.py（5 例）+
dsh/test/followup.test.mjs（行为级 stub fetch）。引擎零改动、旧路径不变。

### 追问触发判定块三层显式化（S67-S70，2026-11-08 负责人确认）

S63-S66 落地后实况复盘发现：「引导补充」（F3 三件一轮，答案并入 content）
与「固定追问」（答案进独立字段）两通道分界靠 agent 自由裁量，与话术固定化
纪律有张力。判定块三层显式化（SKILL 逐字锁 + 契约 description 同步）：

1. 触发前置：用户明确"提交/提吧"后、确认环节内、至多一次，不得与引导补充连续两轮问
2. 跳过条件：引导补充已获具体现象/场景/报错等非泛化反馈内容且并入 content
   → 不触发固定追问；引导补充中自然出现的操作/期望仍保留在 content 原话，
   不回溯摘入新字段——新字段仅承载固定追问的原样回答（来源唯一）
3. 触发条件：引导补充未回应或仅泛化抱怨 + 确认提交 → 原样带出固定问句至多一次。
   判定例："未回应"=未给出任何具体信息（仅"提交/嗯/没有"）；"泛化抱怨"=仅负面
   评价无具体现象/场景/报错（"就是有问题/不好用/赶紧修"）
一句话口径（可测原文）：跳过固定追问时，reproSteps/expectedBehavior 不上送，
payload 不含对应键，issue 不出现「（用户追问补充）」段、不作来源注记，符合诚实回退。

| # | 场景 | 旅程与断言 | 覆盖 |
|---|---|---|---|
| S67 | 已有实质回应 | 用户对引导补充说了具体现象（并入 content）→ 确认提交 → 固定问句不出现、新字段不上送 | SKILL 判定块第 2 层 + 契约 description 跳过句 |
| S68 | 泛化抱怨+确认 | 用户只说"就是不好用"→ 确认提交 → 固定问句原样出现至多一次 | 判定块第 3 层 |
| S69 | 引导补充未回应 | 用户不补现象直接确认 → 固定问句出现一次；答"没有"→ 直接提交、新字段键不存在 | 判定块第 1+3 层 + _FOLLOWUP_DECLINES 兜底 |
| S70 | 判定规则防漂移 | SKILL 双副本判定块逐字一致 + 契约跳过句在位 | test_followup_skill_judgment_block_locked + 契约逐字断言 |

四行为用例（S67-S69）属 agent 话术行为，验收=目标环境真实会话走查（F3 同法）；
自动化锁钉死判定规则文本本身（S70）。

### 问卷化追问 tripwire（S71，2026-11-08 实况复盘）

实况：agent 在引导补充轮自由生成四维度追问清单（哪里卡顿/操作不方便在哪/
期望 vs 实际/大概频率，每点带分叉示例）——违反话术固定化（约束②，分叉示例
制造"被暗示的复现步骤"）与一次一问（约束①，四问+频率刻度）。

| # | 用例 | 断言 | 承载 |
|---|---|---|---|
| S71 | 话术载体禁问卷结构词 | SKILL 双副本+契约 description 禁出现「偶尔还是每次/大概频率/期望 vs 实际/找不到入口/步骤太多/哪个功能难用/打开页面慢」等问卷化措辞；数字编号不锁（判定块规则层合法） | tests/test_followup.py::test_followup_questionnaire_structure_words_banned |

边界：固定追问原句本身已含"操作步骤**或**期望的表现"的合法自由度（只补充
一两条也行）；合规补充引导上限=引导补充固定句+固定追问逐字句，此外不扩写。
用户主动要求提示时同样不豁免中立性校验。

### 反截断红线（S72，2026-11-08 opencode 实锤）

实况：用户引导补充轮说「操作不方便，流程合理」，模型 reasoning 自行判断
"最新具体抱怨是操作不方便"（会话日志原文），提交 content 只带了半句——
原话红线在多轮拼接场景下被自由裁量击穿（"原话逐字"有、但"整句才=原话"
没显式化，模型把补充句当了可挑选素材库）。

| # | 用例 | 断言 | 承载 |
|---|---|---|---|
| S72 | 反截断 | 补充句整体=content 逐字全量上送，禁摘片段；多轮分散表达按序拼接禁增删改写 | SKILL 双副本反截断红线 + test_anti_truncation_redline_locked |

（取证：opencode.db part 表会话原文与 draft 载荷对照——取证手法入库
references 惯例：宿主会话日志是行为举报的第一证据。）

### 拼接判定例（S73，2026-11-08 opencode 第二次实锤）

S72 落地后首次真实观测即抓到拼接层裁量：用户两轮原话"产品体验很差劲啊"+
"产品很垃圾甚至不想用了…"，agent 拼接展示为"产品体验很差劲。产品很垃圾…"
——删语气词"啊"、补句号。S72"禁增删改写"已写但"逐字=含语气词/标点"未
显式化，拼接环节再次自由裁量（同构模式第四次：规则→实锤→补判定例）。

| # | 用例 | 断言 | 承载 |
|---|---|---|---|
| S73 | 拼接逐字 | 各轮原话逐字保留（含语气词/标点），轮次衔接用换行或空格不新增标点，拼接结果可逐字符还原回各轮原文 | SKILL 拼接判定例 + test_concat_verbatim_judgment_example_locked |

## S74-S76 追问环节状态上报（followupStatus，2026-11-08 引擎侧 V55-V57 的插件对接）

引擎契约增量（VOD-Project fc54cca3）：voices[].followupStatus 可选三态，囤积列
followup_status 平台侧承载（issue 不渲染）。插件侧对齐：

S74 三态判定映射随行上送
  判定块三层结果→followupStatus：not_asked（已有实质回应/泛化未触发）/ 
  declined（问了未答或答"没有"）/ answered（已答随两字段）。SKILL 判定块
  第 5 条话术锁；契约 draft/submit 双工具 items 增可选枚举字段。
  回归：test_followup#followup_status_passthrough_submit / #followup_status_stashed_in_draft。

S75 白名单归一双保险
  插件侧与引擎侧同口径：strip+lower 归一，白名单外/缺失省键（不拒收不报错）。
  单源 _followup_fields（submit/draft 共用，禁双边漂移——S64 实锤教训的机制化）。
  回归：test_followup#followup_status_invalid_omitted。

S76 dsh 壳行为对齐、desc 不宣讲
  dsh/lib/index.js 透传循环同口径扩展；desc 1495/1500 无预算不宣讲
  （宿主技能层 SKILL 第 5 条承载口径显式化）。
  回归：node --test 全绿 + dsh desc 预算门禁不回退。

## 断回合续提交与确认收口（S83-S86，D-resume-commit-1，2026-11-09 负责人确认）

实锤：agent draft 后收工，用户两次说"提交"仍无下文，反馈 40 分钟未进引擎
（approvalToken 只存在于 draft 响应文本，agent 回合中断即丢失，只能重开草稿）。

S83 正常确认提交全链
  draft→commit→回执 echo 与上送 payload 均与用户原话逐字一致（改写即违规）。
  回归：test_two_phase#test_s83_full_chain_echo_verbatim。

S84 断回合续提交（机制层）
  agent 回合中断后，凭 draftId 即可 commit（token/sha 由本地未过期草稿恢复）。
  语义不放宽：显式传错 sha 照拒；过期草稿照拒；token 落盘 runtime.json 0600
  （与 java_key 同级保护；token 威胁模型=防载荷改写，非同意凭证，落盘不放大）。
  契约：vod_commit_voices required 收窄为 draftId。
  回归：test_two_phase#test_commit_resumes_from_local_draft /
  #test_commit_resume_wrong_explicit_sha_still_rejected /
  #test_commit_resume_expired_draft_rejected / #test_draft_persists_token_for_resume。

S85 草稿过期重开链
  过期 commit 拒收→重新 draft→commit 成功（SKILL 话术锁"失败就重开草稿"的
  机制可行性验证）。
  回归：test_two_phase#test_s85_expired_then_redraft_commits。

S86 单次消费对恢复路径同径
  commit 成功后凭同一 draftId 再恢复=拒（防二次提交；先消费后提交的既有
  语义对省略参数路径同等生效）。
  回归：test_two_phase#test_s86_consumed_draft_not_resurrectable。

边界（明示）：用户"是否同意"是对话语义，无法确定性判定——同意环节仍由
SKILL 软层承载（D-resume-commit-1 话术锁：确认后当回合必须 commit，不成
必须明告未提交）；完全确定性同意需宿主 UI 结构化确认，属宿主侧协议改动，
不在插件单方范围内。

## 无通道 pending 队列与拼接保真（S87-S90，D-pending-1 及补强，2026-11-09 负责人拍板方案 A）

需求背景：插件未安装/无 vod 工具时，agent 兜底「暂存」只存在于会话输出
（实锤：即兴 JSON 零落盘），会话结束=有记录的丢失；且拼接改字（S73 家族）
在无通道场景无任何比对。拍板方案 A：落盘+flush+echo 前移，四条执行细节
（幂等键分工/原子重写/echo 诚实边界/过期策略）定稿后落码。

| # | 场景 | 断言 |
|---|---|---|
| S87 | 无通道暂存落盘 | 反馈追加写入 pending-feedback.jsonl（字段含 idempotencyKey=sha1(content+confirmAt+source)/originalLines/echoShown/status）；对用户只说人话禁路径 |
| S88 | 恢复后自动补交 | 任一次 vod_submit_voices 成功触发 flush：pending 条目补交落库，文件重写后仅剩未完成项（原子 rename） |
| S89 | 拼接改字机械剥除 | 条目带 originalLines 时 flush 以 `
` 拼接为权威 content（模型新增标点被剥除，corrected 计数）；无 originalLines 条目行为不变 |
| S90 | 失败与生命周期 | flush 失败条目保留 pending 不标已处理；单次上限 100 最早优先；超 30 天标记 expired 剔除；坏行容忍不炸 |

回归：tests/test_pending_feedback.py 11 例（幂等键/原子重写/坏行/过期/上限/
失败保留/接线源码锁/originalLines 三例）；pytest 全套 110 绿。
边界（明示）：echo 前移为概率性防线非确定性闸；宿主程序整体恶意时 pending
文件本身不可信（与 ReceiptGuard 宿主侧天花板同理）。

## 归因改为运行期字面解析（S91-S100，D-attrib-B，2026-11-11 负责人拍板 A/A/A/A）

需求变更：产品不再由安装/启动配置决定，改为**运行期从用户原话解析**，配合
产品名录（引擎 meta）下发与短 TTL 记忆复用。归因优先级（证据强度降序）：
用户原话字面证据 > 记忆（TTL 30 分钟）> 安装 `--product` 先验 > UNKNOWN。
硬规则：唯一命中才采信；多产品命中一律 UNKNOWN 并保留全部命中片段；模型自报
product 不采信（契约删除该参数）；0 命中且无记忆/先验时落 UNKNOWN 人工归因池。

| # | 场景 | 断言 |
|---|---|---|
| S91 | 中文别名命中 | 原话含「码道」→ 提交 catalog 主键 id，productSource=user_input，productEvidence 含 alias=码道 与原文片段 |
| S92 | 长别名/别名归一 | 「软件开发生产线 CodeArts」「对象存储服务 OBS」「modelarts」分别命中 CodeArts/OBS/MaaS；长别名优先于其子串 |
| S93 | 误命中反例 | `codearts.yaml`、`mycodearts`、`obs://bucket`、小写 `obs` 均不命中（拉丁词边界 + 短别名只认 OBS 强形态） |
| S94 | 多产品命中 | 一条反馈同时命中 CodeArts 与 MaaS → product 留空（UNKNOWN），productEvidence 保留两条命中（含 alias/片段/reason=ambiguous） |
| S95 | 记忆复用 | 无字面证据时复用 TTL 内最近一次字面归因：productSource=memory，evidence 回指历史命中与时间 |
| S96 | 记忆过期与先验回退 | 记忆超 30 分钟 → 落安装 `--product` 先验（productSource=install_binding）；先验也没有 → unknown |
| S97 | 模型自报忽略 | 契约已无 product 参数；调用方仍塞 product 时被忽略并回执 ignoredRuntimeProduct（D-attrib-A 语义保留） |
| S98 | 名录不可用 | meta 不可达/老引擎（无 productCatalog/nameAliases）→ 只走短码匹配；仍无字面证据则 UNKNOWN，回执 productSource=unknown 明示不静默猜 |
| S99 | 留痕可追 | 回执与本机账本同带 productSource + productEvidence（含命中文本片段），人工可回溯到用户原话 |
| S100 | 歧义不写记忆 | 多命中/无证据的调用不更新 attribution_memory，避免歧义污染后续归因 |
| S101 | 原话逐字（反例） | 用户"产品体验很糟糕" → content 只能是这一句；模型补"操作不流畅，使用不方便"=违规（2026-11-11 CodeArts Agent 真机实锤，已落进引擎） |
| S102 | tags 值域 | 只允许 `problem_type:<六类之一>`；自造"易用性"被白名单丢弃并回执 invalidTags（同次真机实锤） |

回归：tests/test_attribution.py（别名/边界/歧义/记忆 TTL/自报忽略/老引擎/
账本留痕/歧义不写记忆）+ 既有 D-attrib-A 用例改造。


## 双副本零提交与发版对账门禁（S103-S110，D-copies-generated-1，2026-11-15 负责人确认）

需求变更：插件副本（`plugins/vod-devkit/{vod_mcp,skills,contract,safety}`）从
「入库的第二份源码」改为**生成物**。发版与推送链上的每道检查只对一份真值断言，
不再依赖「两边 diff 相同」这种在同步之后恒真的判据。

背景（v0.5.8 两个方向的事故）：① release.sh 先跑 sync 把源与副本**都**写成新内容，
提交清单漏了 `plugins/vod-devkit/contract` → 提交树里副本是旧版、npm tarball ≠ tag，
而所有基于工作区的 diff 门禁全绿；② 同一门禁在 CI 上假红——checkout 默认
fetch-depth=1 取不到 tag，对账脚本把「tag 不可见」判成「没打 tag」。

硬规则：
- 副本四目录与插件 `build-info.json` 一律不进 git；`.gitignore` 全域排除。
- 生成只有一个入口 `scripts/sync_plugin.py`（暴露 `sync(root)`，幂等整目录覆盖）；
  npm `prepack` 自动重跑，不靠人记得先同步。
- 一致性门禁只有一个入口 `scripts/verify_copies.py`：内容一致 **且** 副本零跟踪；
  pre-push / CI / release.sh 共用同一把尺，禁止各写一份 `diff -r`。
- 发版在**提交之后、打 tag 之前**复验（顺序错误=没防）；tarball 指纹断言接受
  `{v$BUMP^, v$BUMP}` 区间（prepack 重跑后 sha 前移一格，两者是同一份代码）。
- 仓内消费入口（pytest、宿主矩阵、codex 安装器）在读副本前各自兜底一次 sync。

| # | 场景 | 断言 |
|---|---|---|
| S103 | 副本零提交 | `.gitignore` 覆盖四目录 + 插件 build-info；`git ls-files` 对四目录为空；任一被跟踪即门禁红 |
| S104 | 单一生成入口 | 干净检出（无副本）跑一次 `sync()` 即自足：四目录生成、内容与源一致、`runtime.json` 不入副本；重复跑幂等；`package.json` 的 `prepack` 挂生成器且 `files` 白名单含全部生成物 |
| S105 | 一致性门禁单入口 | `verify_copies.py` 同时断言内容一致与副本零跟踪；ci.yml / pre-push / release.sh 三处都调它，且不再各自拼 `diff -r` |
| S106 | 发版复验时序 | release.sh 中 `git commit` → `verify_copies` → `git tag` 的先后顺序被锁；漏项在打 tag 之前失败 |
| S107 | 指纹区间断言 | prepack 重跑后 build-info 的 `commitSha` ∈ `{v$BUMP^, v$BUMP}`；两者皆非=包内不是本 tag 的代码，禁止发布 |
| S108 | 浅克隆不假红 | 浅克隆下 tag 不可见只提示不判 DRIFT；CI checkout 取全量历史（fetch-depth: 0）让 tag 对账权威 |
| S109 | 用例环境无关 | 断言不得依赖本机 runtime.json（auth_status 有无 keyCheck）：用例显式钉住所需要状态，CI 与开发机同结论 |
| S110 | 消费入口兜底 | tests/conftest 会话夹具、host_matrix、codex 安装器在读副本前各自 sync；缺副本时给可读错误而不是「找不到插件」 |

回归承载：`tests/test_copies_generated.py`（S103/S104/S106/S107/S110，含逐目录参数化）、
`tests/test_verify_copies.py`（S105）、`tests/test_registry_reconcile.py`（S108）、
`tests/test_p2_structure.py`（S109）；设计侧写法见 `docs/design.md`
「插件副本生成物边界」一节。

验收口径（目标环境执行，工具不入库）：干净检出 → `python3 scripts/sync_plugin.py` →
`python3 scripts/verify_copies.py` 绿；`git status --porcelain` 对四目录为空；
`npm pack --dry-run` 含四目录与 build-info；故意 `git add -f plugins/vod-devkit/vod_mcp`
后门禁必须红（反向验证）。


## 插件 MCP 清单形态（S111-S114，D-mcp-manifest-a3-1，2026-11-15）

需求变更：codex 原生插件的 `.mcp.json` 补全规范字段（`$schema` + `type`），并把
codex 适配器的改写失败改为按类型处置。**原计划的 `${PLUGIN_ROOT}` 形态未采用——实测不可用。**

背景与实测（codex-cli 0.167.0，本机 app-server 真机探针，`mcpServerStatus/list` 触发 spawn）：
1. 旧静态形态 `command: vod-devkit` + `args: [serve]` 把 CLI 名交给 PATH——机器上装着
   旧版（实测 0.4.2）时宿主静默跑旧副本：配置和技能是新的，工具面却是旧的。
2. 规范（agent-plugins.org §7.2.1 / §9.2）承诺：stdio server 默认 cwd = 插件根；
   `args`/`env`/`cwd` 里 `${PLUGIN_ROOT}`、`${PLUGIN_DATA}` 会展开。
3. **实测结果（决定性）**：探针 server 把收到的 `sys.argv`/`cwd`/env 落盘——
   args 里原样收到字面量 `${PLUGIN_ROOT}/vod_mcp/server.py`；`cwd` 是 `~/.codex`
   而不是插件根；`PLUGIN_ROOT`/`PLUGIN_DATA` 也没注入环境；`VOD_PACKS` 正常传入。
   再把插件包迁到 Agent Plugins 格式（根 `plugin.json` + `mcp.json` + `$schema`）重装，
   该 MCP 条目在 0.167 下**根本没注册**（`codex mcp list` 为空，插件事务本身 installed/enabled）。
   → 规范承诺在该二进制上未落地，A3 的静态形态今天会静默坏。

硬规则（据此定稿）：
- 静态清单**保留 CLI 形态**（`command: vod-devkit` + `args: ["serve"]`）：唯一实测能跑通的
  入口；同时补 `$schema`（约定值）与 `type: stdio`，顶层只允许这两个字段。
- 清单里**禁止出现任何 `${...}`**：0.167 不展开 → 宿主收到字面量，静默坏。
- 运行时正确性由安装器改写承担（`codex plugin add` 后把缓存 .mcp.json 改写成
  「绝对解释器 + 载荷副本」并**读回验证**）。这不是可选优化：静态形态本身无法
  摆脱 PATH 上 CLI 的版本不确定性。
- 改写失败分层：`bad-json`/`not-writable` → warn + 分类补救指引，安装继续；
  读回与期望不一致（并发改写/半写状态）→ 安装失败。禁止一个 catch 全 exit 1。
- `vod_mcp/server.py` 顶部加解释器 guard（`sys.version_info < (3, 10)` → 可读诊断 +
  exit 2），把 PEP 604 语法 traceback 换成一句人话。

| # | 场景 | 断言 |
|---|---|---|
| S111 | 静态清单形态 | `$schema` 命中约定值、顶层字段只有两个、`type=stdio`、`command/args` 为 CLI 形态（附实测理由）、清单里不出现 `${`、`env.VOD_PACKS` 显式存在、改写入口存在 |
| S112 | 运行时形态 | 改写产物 = 绝对解释器 + 载荷路径、args 不含占位符、读回内容与落盘一致 |
| S113 | 工具面不静默收缩 | `VOD_PACKS` 缺省（空值）= 全 packs（历史默认），显式 `core,collect` = 有意收窄；用例把 HOME 指到临时目录规避熔断标记（环境无关） |
| S114 | 改写失败分类 | 正常改写读回绝对形态；`bad-json`/`not-writable` 抛分类错误且都有补救文案；读回不一致抛 RuntimeError（安装失败）；新增分类必须同时给补救指引 |
| S115 | doctor 报实际形态 | doctor 对 codex 必须区分 payload（绝对解释器+载荷）/ cli（PATH 名）/ placeholder（未展开占位符）/ unreadable，并把后三种判为问题；形态判定与 doctor 报点都有用例兜（文档说"doctor 可查"就必须可查） |

A3（`${PLUGIN_ROOT}` 静态形态）的当前处置：**搁置，不废弃**。前提是宿主支持保留变量
展开（或迁移到 Agent Plugins 插件格式并被 0.167+ 正确注册）。复验方法写在此处，
不是"以后有人再看"：① 探针插件 + `codex app-server` 的 `mcpServerStatus/list` 触发 spawn，
落盘 `sys.argv`/`cwd`/env；② 看到 `${PLUGIN_ROOT}` 被替换成绝对路径且 `cwd` = 插件根
→ 切回 A3，并按 S111 的红反推清单改动；③ 届时改写逻辑降级为"解释器版本兜底"（推荐而非必须），
不要同时拆掉。

验收口径（目标环境执行，工具不入库）：`python3 -m pytest tests/test_mcp_manifest_a3.py -q`
全绿；装机后 `codex mcp get vod-devkit --json` 的 command 是本机 3.10+ 绝对路径且
args 指向载荷；把 PATH 上的 python3 换成 3.9 再启动 → stderr 出现版本 guard 文案而非 traceback。


## 全局命令与多宿主消费面（S116-S123，D-global-cmds-1，2026-11-15）

需求变更：install-manifest 早就记了全部宿主（`installs[]`，D-installs-1），但消费方
还是单宿主。本组把读路径统一成"整台机器一个视图"，并给能力包一个可解释的写入面。

- `version`：CLI 版本 + 每个宿主已装版本（同版/≠CLI）+ 该宿主**实际生效**的 VOD_PACKS。
- `packs status`：读每个宿主的真实配置回答"现在跑的是哪一套"（不是读 manifest 猜）。
- `packs enable|disable|all [--apply]`：缺省 dry-run；`--apply` 只改受管条目的
  `env.VOD_PACKS`，首改留 `.bak`，写后读回验证；`core` 强制包含；宿主配置不是可写
  JSON 的（dsh 等）明确报"需重跑 install"，不假装改成功。
- `install --target all`：只装探测到的专属宿主，缺 CLI 的跳过（generic 不参与）。
- `uninstall --target <agent>`：只摘该行，其它安装行保留；`--clean-global` 逐条清
  载荷残留与 npx 缓存里的旧副本——**在用载荷与不认得的目录一律不碰**。
- `status|doctor --target <agent>`：从多行里选一行检查；缺省视图=最近一次安装（顶层
  字段即最后一次写入），多行时打印安装行清单提示用 `--target`。
- 未知包 id：安装口与 server 启动口都 `exit 2` 并列出可用 id（此前静默过滤——实测
  `VOD_PACKS=core,bogus` 会静默变成 `('core',)`，属"配了不生效"）。

| # | 场景 | 断言 |
|---|---|---|
| S116 | 未知包 id 即报错 | `parse_packs("core,bogus")` 抛 UnknownPack 且列出可用 id；`kb` 别名仍映射 knowledge；server 子进程以该 env 启动 → exit 2 + stderr 文案 |
| S117 | 前置与排障段 | README 有"装不上怎么办"四类（SDK 缺失/解释器不在 PATH/镜像滞后/插件缓存旧副本），每条给判据与修法，且不引用不存在的参数（`VOD_PYTHON` 存在，`--python` 不存在） |
| S118 | version 全局视图 | 两行 manifest（同版 / 落后）分别输出"同版"与"≠ CLI"，并同时打印各自生效 packs |
| S119 | packs status 读真实配置 | 从宿主配置文件读出 VOD_PACKS（不是从 manifest 推断） |
| S120 | packs 写纪律 | 缺省 dry-run 不改字节；`--apply` 只改 env.VOD_PACKS、宿主其它键原样保留、首改落 .bak、读回验证；`core` 禁不掉；`all` 置全包 |
| S121 | --target all | 只循环探测到的宿主（缺 CLI 跳过）；零宿主时 exit 2 并说明 |
| S122 | uninstall 收窄与清残留 | `--target` 只摘该行且保留其它行与在用载荷；`--clean-global` 只删无 payload.json 的载荷与含 vod-devkit 的 npx 缓存目录，不认得的目录不碰 |
| S127 | 探测后的交互选择 | 扫到多个且终端可交互 → 列编号多选（`1`/`1,3`/`all`/回车取消，非法输入重问一次）；非交互一律报错不猜；扫到 0 个时交互问一次 target 名；`--target all` 里 dsh 缺 `--profile` 跳过并说明（不伪装成失败） |
| S123 | status/doctor --target | 选中行输出该行 JSON；未知 target 明确报"没有该宿主的安装记录"并列出已有 |

验收口径（目标环境执行，工具不入库）：`python3 -m pytest tests/test_global_cmds.py -q`
全绿；真机上 `version` 逐行列出 installs[] 的每个宿主 + 每个装了壳的 dsh profile
（本机实测 8 行账本宿主 + `dsh(headless)`/`dsh(web)`）；
`packs disable knowledge`（不带 `--apply`）打印"未写盘"，文件 mtime 不变。


## 全局视图覆盖账本外宿主（S130-S131，D-dsh-global-view-1，2026-11-16）

需求变更：`version` / `packs status` 的行数 = `installs[]` 条数。dsh 由
`dsh-vod-devkit` 的 profile 依赖承载、安装器不写账本行，于是全局视图里**连一行都没有**，
也没有 `[missing]` 提示（那个提示只给"账本有行、配置没条目"的宿主）——用户会读成
"这台机器没装 dsh"。本组补只读探测，**不改安装/卸载语义**。

- `version`：遍历 `~/.dsh/profiles/*/package.json`，只列**声明了** `dsh-vod-devkit`
  （dependencies 或 `dsh.profile.bundles`）的 profile，输出 `dsh(<profile>)` 行：
  已装版本（取 `node_modules/dsh-vod-devkit/package.json` 的实际版本）+ 同版/≠CLI 判定
  + 重装命令（`install --target dsh --profile <p>`）。
- 声明了但 `node_modules` 里没有该包 → 报「已装版本未知」，**不回落到 spec**（`file:…tgz`
  或范围号是意图，不是现状）。
- `packs status`：dsh 行标 `[n/a]` 并说明"壳不走 MCP env、能力面由包内固定、改 pack
  需重装"；`packs enable|disable|all --target dsh` 打印"跳过 + 重装命令"，
  **不写 profile、不留 .bak、不打印成功**。
- `--target dsh` / `--target dsh(<profile>)` 都可选中；只读，命令前后 profile 字节不变。

| # | 场景 | 断言 |
|---|---|---|
| S130 | version 覆盖账本外宿主 | 假 HOME 造 profile：输出现 `dsh(web)` 行、已装版本取自 node_modules、≠CLI 时给出 `--profile web` 重装命令；node_modules 缺失时报「已装版本未知」；未声明该包的 profile 不出现；命令前后 profile 字节不变（只读） |
| S131 | packs 对 dsh 不可写 | `packs status --target dsh` 出行且带 `[n/a]`+「需重装」；`packs enable … --target dsh --apply` 打印「跳过」与重装命令，profile 字节不变且**不生成 .bak**（不假装改过） |


## 会话内能力面开关（S132-S133，D-packs-configure-1，2026-11-16）

需求变更：能力面此前只有安装期/启动期的 `VOD_PACKS` 一个入口——改了要重启宿主会话，
且没有任何工具能回答"现在开的是哪几个包"。对标 devkit 的 `packs_configure`（stdio 会话内
开关 + 推 `tools/list_changed`）。

- 新增 core 工具 `vod_packs_configure`：`enable` / `disable`（包 id 列表）或 `reset=true`；
  返回新生效面、增删项、当前工具清单、`changed`、`persisted:false` 与持久化命令提示。
- **只改进程内状态**：不写 env、不写宿主配置（持久化面仍只有 CLI `packs … --apply`）。
- `core` 强制包含；未知包 id 报 `-32602` 并列出可用 id；**采集熔断期间开启 collect 报
  `-32015`**（安全门禁，显式动作也不能绕过，且不做静默摘除）。
- 形态变更才推 `notifications/tools/list_changed`（无变化不发，避免客户端重拉风暴）；
  `initialize` 的 capabilities 声明 `tools.listChanged=true`。
- ~~远程面（HTTP）摘除该工具：远程面每请求现造 server、无会话，开关会在下一个请求消失。~~
  **2026-11-18 D-scope-1 推翻**：远程面已回归 MCP 标准 stateful 传输（initialize 下发
  `mcp-session-id`，会话跨请求存活并按会话隔离），「无会话」前提失效，故恢复该工具，
  两形态工具面完全一致。

| # | 场景 | 断言 |
|---|---|---|
| S132 | 会话内开关生效 | disable 后 `tools/list` 立即少掉该包工具、enable 后回来；`reset` 回到 VOD_PACKS；core 强制；未知 id `-32602`；空参数拒绝；熔断期 enable collect `-32015` 且状态不变；调用前后 `os.environ` 逐键不变（不写 env） |
| S133 | 协议面与远程边界 | capabilities 声明 `listChanged=true`；有变化时同一次调用输出「响应 + 通知」两条（stdio 上各占一行）、无变化只输出响应；通知后 `tools/list` 反映新区面；**`REMOTE_WITHHELD == ()` 且远程 `tool_specs` 含该工具**；契约含三参数 |

## 远程传输标准实现与作用域隔离（S146，2026-11-18）

远程面必须按 MCP 标准实现（不自造一套），才能与外部服务互操作；且 stdio 与 remote
只是传输形态不同，**工具能力不得阉割**。多 agent 共用一个 server 时，记忆/追问计数/
voiceId 必须按作用域隔离，否则静默污染（错归进引擎幂等域、跨 agent 拒绝服务、voiceId
撞车丢声量）。

| # | 场景 | 断言 |
|---|---|---|
| S146-1 | 标准握手 | `initialize` 响应头下发 `mcp-session-id`；带该头调用工具成功；两次握手得到不同会话且互不干扰 |
| S146-2 | 厂商兼容 | 官方 SDK 客户端、旧协议（2024-11-05）、不带 `Accept` 头、裸 HTTP 不握手（兜底放行且可连续多次）、无 session 直调 五类均可接入 |
| S146-3 | 能力对齐 | `enabled_tools(remote=True) == enabled_tools(remote=False)`；`REMOTE_WITHHELD == ()` |
| S146-4 | 作用域隔离 | 不同会话/agent → 不同 key（`sess:`/`agent:` 前缀分工），A 的记忆不泄漏给 B；无标识 → `key=None` 且**读写皆禁用**（宁可多问，不可错归） |
| S146-5 | 产品优先级 | 请求级 product 优先于安装绑定；两者皆空走原话归因 + 问用户；**共用远程进程下 `product_prior=False`**（安装先验禁用，防多租户错归） |
| S146-6 | 粒度与身份正交 | `scope.grain`(process/request) 与 `scope.id_source`(proc/proc_home/sess/agent) 分别成列，不压成一个字段 |
| S146-7 | 隔离维度进 key | `VOD_DEVKIT_HOME` 进入 stdio 远程独立进程的 key（`proc:@<home>`）；stdio 主键为进程身份，`name` 仅二级后缀 |
| S146-8 | TTL 同源 | `session_idle_timeout` 与记忆 TTL 同取 `SCOPE_TTL_SEC`，两者相等由测试锁定 |
| S146-9 | 无写盘副作用 | `_resolve_scope` 不得调用 `_install_nonce()`（会写盘）；"显式 key 被拒"路径不得污染 runtime.json |

### D-meta-anon-1 匿名档 meta 死循环（2026-11-18 真机实锤，跨端同构）

未配 key 的默认形态下，产品名录加载先于「提交遇 401 才领令牌」发生 →
meta 401 → 异常被吞 → 回退空快照 → 名录恒空 → 归因必失败（needsProductAsk）→
而领令牌要提交成功、提交成功要归因成功 → **一条声音都提交不了**。
dsh 侧先修，Python 侧同构补上。

| # | 场景 | 断言 |
|---|---|---|
| S147-1 | 无 key 时 meta 401 → 领令牌 → 重试 | 首次 meta 无 auth；随后调 `/external/token`；重试那次带 key；`source=meta-anon` 且名录非空（本轮实测 103 项） |
| S147-2 | 已配 key 不额外领令牌 | `source=meta`；不调用 `/external/token`；首次 meta 即带 auth |
| S147-3 | 完全不可达 | `source=snapshot`、`stale=true`，不阻断采集 |
| S147-4 | 跨端同构 | dsh `loadMeta` 与 Python `_load_meta` 都有 401→领令牌→重试；真机 stdio/remote 均可提交（voiceId 非空） |


## 凭据单入口与技能读取教法（S124-S125，2026-11-15）

需求变更（两条，都是"把已有的东西收成可解释的入口"，不新增数据面）：

**S124 凭据单入口**（D-auth-init-1）：换 key 此前只有"删 runtime.json 重装"一条路。
- `auth status`：打印引擎地址 + 当前凭据**指纹**与档位；区分"显式 key"与
  "匿名令牌（设备绑定领取）"——后者不是 key，混着说会让人以为配过 key。
- `auth init --key <k> [--apply]`：写 runtime.json 的唯一入口。缺省 dry-run（只校验 +
  显示指纹，明文永不打印，写后读回一致才算成功）；引擎可达且判拒 → 拒写 exit 2；
  引擎不可达 → 告警后允许（网络问题不是 key 问题）；形态可疑（含空白/过短）拒写。
- 优先级链（实现口径）：显式 key（`auth init` 写入）> 环境变量 `VOD_JAVA_API_KEY`
  （平台/CI 注入）> 匿名令牌自动领取。禁令：不要把 key 写进宿主 MCP 配置的 `env`
  （明文且随配置进 git）。

**S125 技能读取教法**（D-skill-teaching-1）：对齐 devkit 的"动作优先"。
- `vod_list_skills` 增字段：`skillRoot`（stdio 面）、每技能 `path`、`version`（有则给）、
  `references`（有则给）、`readHint`（教法一句话）。
- `initialize` 的 instructions 直接给技能树绝对路径与读法：先直读
  `skillRoot/<name>/SKILL.md`（尝试本身即可达性检查，不做预判），被拒/失败才回落
  `vod_retrieve_skill`，绝不反复请求。
- 远程面继续不给服务器本机路径（既有纪律：未鉴权面不交出安装路径）。

| # | 场景 | 断言 |
|---|---|---|
| S124 | 凭据单入口 | 无 key 时 status 报匿名档；init 缺省 dry-run 不写盘且输出只含指纹不含明文；`--apply` 写入并读回一致、档位置 key；引擎判拒则 exit 2 且不落盘；引擎不可达告警后允许；含空白/过短拒写 |
| S125 | 技能读取教法 | stdio 面的目录含 skillRoot/readHint/每技能 path；远程面三者都不给；initialize instructions 含"技能树/动作优先/绝不反复请求"，且远程文案仍写明不给本机路径 |

验收口径（目标环境执行，工具不入库）：`python3 -m pytest tests/test_auth_and_skills.py -q`
全绿；真机 `auth status` 能区分匿名令牌与显式 key（本机实测显示"匿名令牌：已缓存"）。

## 范围守护：这只是声音采集插件（S126，2026-11-15 负责人明确）

本仓的范围不因对标而扩张：huaweicloud-devkit 的**云操作面**（20+ 服务技能、KooCLI、
OBS、sandbox/DevStation、open-mcp 网关、区域感知、服务目录）在本仓**无对象**——它服务
"agent 操作云资源"，我们服务"把用户声音送进 VOD"。对标只借工程形态（分发/诊断/凭据/
教法/门禁），不借业务面。

可执行锁（不是口号）：

| # | 场景 | 断言 |
|---|---|---|
| S126 | 范围不漂移 | `ALL_PACKS` 恒为 `core,collect,knowledge`（新增包=范围变更，需先拍板）；工具面恒为 10 个且全部 `vod_` 前缀；工具名不得含 hcloud/koocli/obs_/sandbox/region/gateway/openapi 等云操作面词 |

验收口径：`python3 -m pytest tests/test_global_cmds.py::test_s126_scope_is_voice_collection_not_cloud_ops -q`。


## 目录结构契约与根预算（S129，D-structure-1，2026-11-15 负责人要求通读对标）

对标 huaweicloud-devkit v2（adfd826）通读后的结论：它根目录 26 条（排除点文件与 11 份
`REPORT-*.md`），靠四条纪律不散——一个插件包、源与生成物分离、共享资产单一落点、门禁脚本化。
我们 2026-11-15 是 **42 条**，散在语义层：四个共享资产挂在根上、发布物分两处、
生成物 `build-info.json` 入库与零提交副本同名不同待遇、钩子曾以宿主特例
（`hermes-plugin/`）存在。

| # | 场景 | 断言 |
|---|---|---|
| S129 | 结构契约可执行 | ① 根目录**跟踪条目**（`git ls-files` 顶层）必须落在 `docs/architecture.md` 的预算表内，新增即红；② 运行期状态（`install-manifest.json`/`vod_mcp/runtime.json`）绝不入库；③ `docs/architecture.md` 存在且包含四条纪律与迁移分阶（不是只活在 review 评论里） |

结构迁移分四阶（S1 本次：契约+预算门禁+README 对齐；S2 共享资产收进 `src/`；
S3 运行时入口路径收进 `src/`；S4 运行期状态收进用户目录），详见 `docs/architecture.md`。

验收口径：`python3 -m pytest tests/test_structure_guards.py -q`；`git ls-files | cut -d/ -f1`
与预算表逐项比对。



## doctor 出站面报告（S134，D-doctor-egress-1，2026-11-16）

需求变更：doctor 有 key 时才探引擎，没 key 时对网络一无所知；代理在插件里完全没有可观测面
（urllib 隐式读 env，但没人能回答"现在走哪个代理"）。两条都只**报告**，不建配置、不改路由、
不 FAIL（离线装机 doctor 必须可用）。

- `[doctor] 出站代理：…`：读 `HTTPS_PROXY/HTTP_PROXY/ALL_PROXY/NO_PROXY`（含小写）生效值，
  **URL 里的口令一律掩码**（输出会被贴进工单）；未设时明说"直连，urllib 会读 env、无需另配"。
- `[doctor] 引擎可达：…`：无条件探一次 `apiBase` 的 `/external/meta`（4s 超时、不重试、不带 key）。
  200=`ok`；401/403=`auth`（**可达**，鉴权问题≠网络问题）；连不上=`unreachable` 只 warn，
  退出码不变。
- 诚实标注：宿主权限缝（沙箱/allow 对 `runtime.json` 的读取门控）插件侧**探测不到**，
  写进 README 的「诚实残留」而不是假装拦住了。

| # | 场景 | 断言 |
|---|---|---|
| S134 | 出站面只报告 | 代理含口令时输出无 `user`/`secret`；未设代理时说"直连"；引擎 200→ok、401→auth 且文案含"可达"、死端口→unreachable 且只 warn；空 apiBase 明说未配置 |


## 读 Key 拦截 hook（S135，D-key-guard-4，2026-11-16）

需求变更：`runtime.json` 里是引擎 key 明文，而排障路径（`cat …/runtime.json`、
`env | grep VOD_JAVA_API_KEY`）实测反复发生——技能里写"只引指纹"靠模型自觉，没有机制。
Hermes 的 shell hook 已确认支持 `pre_tool_call`（**阻塞事件**），本组把它接上。

- 新脚本 `integrations/hermes/hooks/vod_guard.py`：stdin 收载荷，命中时 stdout 回
  `{"decision":"block","reason":…}`，不命中零输出。
- 判定窄：①命令含 `runtime.json` 且含读取类动词；②`env`/`printenv`/`set` 且点名
  `VOD_*KEY`/`java_key`。非 shell 类工具、其它命令、空/坏载荷一律放行。
- **fail-open 是铁律**：阻塞事件里脚本崩掉=所有工具调用被拦，伤害远大于漏拦一次；
  用例专门锁"坏 JSON → 零输出"。
- 拦截文案必须给替代（`vod-devkit auth status` 只出指纹；只看变量名用
  `env | cut -d= -f1 | grep '^VOD_'`）与关闭开关（`VOD_HOOK_READ_GUARD=0`）。
- 注册：`install --target hermes` 同时写 `hooks.pre_llm_call`（路由）与
  `hooks.pre_tool_call`（拦截），两条幂等、互不连坐；`uninstall` 各摘各的。
- codex / opencode 侧等价注册**未做**（机制形态未对齐，不假装已覆盖）。

| # | 场景 | 断言 |
|---|---|---|
| S135 | 读 Key 拦截 | `cat runtime.json`/管道读取/`env \| grep VOD_JAVA_API_KEY` 命中 block 且文案含替代与关闭开关；`env \| cut -d= -f1` 放行；非 shell 工具与空/坏载荷零输出（fail-open）；`VOD_HOOK_READ_GUARD=0` 放行；两条 hook 注册幂等、摘除互不连坐、别人的 hook 原样保留 |


## 跨面一致性与状态原子性（S136-S137，2026-11-16，并行评审收口）

需求变更（两件，都是评审实测出的真缺陷）：

**S136 会话内开关必须"三面同口径"**：`vod_packs_configure` 首版只改了工具面——
`vod_devkit_info` / `vod_auth_status` 仍报 `VOD_PACKS` 旧包、技能枚举按旧包算，
`vod_retrieve_skill` 会回"重跑 install 带上 --packs"。一个开关两种答案是比没有开关更坏
的形态（模型会拿着旧答案要求用户重装）。修法=四处读取方统一走 `effective_packs()`
（provenance 自述、auth_status、skills list/retrieve）。附带修 `dispatch` 的手写
needs_host 清单 → 按签名判参（漏登记会静默丢 client_info）。

**S137 runtime.json 的跨进程一致性**（唯一会造成生产事故的一条）：
一份载荷 `runtime.json` 被同机多个宿主的 server 进程共用，而 `_RT_LOCK` 只是
`threading.RLock`（进程内）。实测 4 进程各写 25 条 → 落盘只剩 36 条；整文件
`write_text` 让读者读到半截 JSON（实测出现 JSONDecodeError），而解析失败
`except: return {}` 静默归零 → 下一次任意更新把 key/账本冲成空。
修法三条：跨进程 `fcntl.flock`（无 fcntl 平台退化并标注）+ tmp/`os.replace` 原子替换
（先 chmod 0600 再替换）+ 坏文件 `runtime.json.corrupt-<ts>` 备份并 stderr 告警后继续。

| # | 场景 | 断言 |
|---|---|---|
| S136 | 开关三面一致 | 关掉 knowledge 后 `vod_devkit_info`/`vod_auth_status` 的 packs、`vod_list_skills` 的 packs 与 enabled 标记、`vod_retrieve_skill` 的拒绝文案都与 `effective_packs()` 一致；`dispatch` 按签名给双参 handler 传 client_info、单参不传 |
| S137 | 状态原子性 | 4 子进程各写 25 次 → 落盘 100 条；写 300 次期间并发读 0 次半截 JSON；坏文件产生 `.corrupt-*` 备份且 stderr 告警、新文件可用；正常文件不产生备份 |


## 卸载面收口（S138，2026-11-16，并行评审 P2）

需求变更（三条，都是实测出的状态/破坏性问题）：

- **技能落点用 skillInstalls（按 host）而不是 row.skillsDir**：历史 manifest 把每一行的
  `skillsDir` 都写成 hermes 目录（`common.py` 单值形态），于是 `uninstall --target opencode`
  会去删 hermes 的技能副本（卸 A 删 B），而 opencode 自己的 `~/.config/opencode/skills`
  永远漏删。老 manifest 没有 `skillInstalls` 时，`skillsDir` 只对 hermes 行可信，
  其它行**宁可漏删也不猜**。
- `--clean-global` 的 npx 缓存只删 `node_modules/vod-devkit` 这一份；一个 hash 目录里若
  还有别的包，整目录 rmtree 会连带删掉用户其它缓存（删空才删目录）。
- `uninstall` 里重复的 `elif target == "codex"` 分支（后者永不执行）删除；
  `bin/vod-devkit` 对"继承到不一致的根"必须 stderr 告警（此前依赖 `setdefault` 静默用错根，
  表现是"未知宿主 xxx（可选：）"这类无从解释的错）。

| # | 场景 | 断言 |
|---|---|---|
| S138 | 卸载只碰自己的落点 | 双宿主假 HOME：`uninstall --target opencode` 后 hermes 技能副本仍在、opencode 自己的被摘；hermes 专属目录只摘技能子目录（目录与别人的技能保留）；落点在当前 HOME **之外**一律拒绝删除并打印原因 |


## 状态事务化与守卫覆盖面（S139，2026-11-16，第二轮评审）

需求变更（两条，都是"修了一半"的实测证据）：

**S139-a 读改写必须事务化**：第一轮只给"写"上了锁（tmp+os.replace），但 `_ledger_append`
与草稿存盘是"锁外读整键 → 锁内整键覆盖"——4 进程各写 25 条账本只剩 40-53 条（写原子了，
条目照样丢）。修法=新增 `_runtime_atomic(mutate)`：进程内 `_RT_LOCK` + 跨进程 `flock`
一起持，读 → mutate → 原子写；`_ledger_append`、`vod_draft_voices`、`vod_commit_voices`
（校验+单次消费同事务）全部搬进去。`_save_runtime` 退化为它的薄封装。
门禁同步换成**真实入口**（此前 S137 子进程写的是不同顶层键，合并在锁内天然安全，
证明的是"不丢键"而不是"不丢条目"）。

**S139-b 读 Key 拦截要覆盖文件/代码工具**：只拦 shell 类工具等于没拦——模型读
`runtime.json` 的常规路径是 `read_file(path=…)` / `execute_code(open(...).read())` /
`search_files(pattern=java_key)`，这三个当时全部放行（白名单外一律 allow）。
修法=按工具分类判定：文件类看 path 是否点名 runtime.json、搜索类看 pattern 是否点名
key 变量、代码类看代码里是否点名 runtime.json；其余仍 fail-open。

| # | 场景 | 断言 |
|---|---|---|
| S139 | 事务与覆盖面 | 4 进程各 25 次 `_ledger_append`（真实入口）→ 落盘 100 条；`read_file`/`execute_code`/`search_files` 点名 runtime.json 或 key 变量 → BLOCK，正常读文件/普通代码/普通搜索 → ALLOW |


## 身份类值的读取口径（S140，D-state-read-1，2026-11-16）

需求变更：`net.JAVA_KEY` / `net.JAVA_BASE` 此前是**模块导入期常量**，而 MCP server 是长驻
进程。于是 `auth init --apply` 换 key、安装器改 apiBase、自动领取的匿名令牌写回 runtime.json
之后，运行中的进程仍用启动那一刻的旧值——用户侧表现是"我明明配了/换了，还是 401 或打到
旧环境"，而 `auth status` 报的档位也可能与出口实际用的一致但不自洽。

- 改为**调用期现读**：env（平台注入）> `runtime.json` > 默认；文件缺失/损坏时回落进程内
  镜像（`_RT`），不打断出口。
- 保留模块属性 patch 面：`net.JAVA_KEY` / `net.JAVA_BASE` 走 PEP 562 模块级 `__getattr__`，
  **显式 set 过的值优先**（既有用例与运维脚本都靠 `monkeypatch.setattr(net, "JAVA_KEY", …)`）；
  模块内部一律调 `_java_key()` / `_java_base()`（模块内全局名查找不触发 `__getattr__`）。
- 自动领取匿名令牌处不再写模块属性（写属性会让 `__getattr__` 永久失效、token 又被冻住），
  统一走 `_runtime_update`（落盘 + 镜像）。

| # | 场景 | 断言 |
|---|---|---|
| S140 | 身份值热生效 | 改 runtime.json 的 java_key/java_base → `net.JAVA_KEY`/`JAVA_BASE` 立刻反映（无需重启）；env 高于 runtime；显式 set 过的模块属性优先；`token_tier=anonymous` 时 `_explicit_key()` 为 False；runtime 缺失时回落镜像 |


## 隔离矩阵与巡检判据（S141-S142，D-matrix-isolation-1 / D-audit-effective-1，2026-11-16，第三轮评审）

需求变更（两条都是真机实测出来的）：`scripts/host_matrix.py` 是 CI 门禁，却在**改操作者的
真实配置**；`--audit` 是"这台装得对不对"的唯一只读判据，却在**报假绿**。

**S141-a 隔离 HOME 必须搬每个宿主自己的家**：矩阵只设了 `$HOME`，而 hermes CLI 认
`HERMES_HOME`（不认 `$HOME`）。实测：一次全量矩阵跑完，真机 `~/.hermes/config.yaml` 的
`mcp_servers.vod-devkit` 被改成 `<scratch>/vod-matrix-XXXX/home/.vod-devkit/payloads/…` +
桩地址 `http://127.0.0.1:9/stub`；scratch 一清，hermes 的 vod 工具就永久掉线
（会话里报 `lost its stdio subprocess`）。修法=矩阵 env 按宿主搬自己的家
（`HERMES_HOME` / `CODEX_HOME` / `DSH_HOME`），并 pop 掉继承来的 `HERMES_PROFILE` /
`HERMES_CONFIG`。

**S141-c 沙箱里的宿主 CLI 必须立刻失败，不能等它自举**：只搬 `HERMES_HOME` 会换来第二个
问题——hermes CLI 在空家里会尝试自举依赖，实测一次 `install --target hermes` 卡到 300s
超时（那一轮全量矩阵因此 FAIL）。修法=矩阵给 hermes 的 PATH 最前面放一个同名 shim
（`exit 1` + 明确 stderr），适配器本来就是 best-effort（rc≠0 打印提示后继续），矩阵断言
落在"安装器写出的条目 + 按该条目拉起 server 自证"。**已知覆盖降级**：矩阵不验 CLI 注册段，
真机生效入口由 S142 的巡检负责——两件事分开管，不互相冒充。全量矩阵耗时从 300s+ 回到 ~7s。

**S141-b 硬证据形态**：矩阵前后对真实 `~/.hermes/config.yaml` 取 md5，必须一致。

**S142-a 巡检读"生效入口"**：hermes 的生效入口是 `config.yaml` 的
`mcp_servers.vod-devkit`，`~/.hermes/mcp/vod-devkit.json` 只是备片；旧判据读备片，
于是"备片能跑通、生效入口指向已删路径"时报 PASS。改为读 `config.yaml`（零依赖窄解析，
不做完整 YAML），解析不出直接 DRIFT（宁可报挂，不许静默跳过）。

**S142-b codex 按启用的市场判**：codex 同时存在 `personal(0.5.4)` 与 `vod-local(0.5.9)` 两份
缓存，`config.toml` 里启用的是 personal；旧判据按目录名排序取最后一份 → 报 0.5.9 PASS，
而 codex 实际拉起 0.5.4（server 日志 argv 实锤）。改为按 `[plugins."vod-devkit@<mkt>"]`
的 enabled 选市场，报文里带市场名（可审计"它到底判的是哪一份"）。

| # | 场景 | 断言 |
|---|---|---|
| S141 | 隔离矩阵不碰真机 | hermes 的隔离 env 含 `HERMES_HOME` 且落在隔离 HOME 内、不继承外层值；全量矩阵前后真实 `~/.hermes/config.yaml` md5 不变 |
| S142 | 巡检判据 | 备片可跑通但 `config.yaml` 指向死路径 → DRIFT 且报文点明 `config.yaml`；codex 两份市场并存且 config.toml 启用 personal → 报文点明 personal（不得按排序取 vod-local 报假绿） |


## 测试隔离：不写真机（S143，D-test-isolation-1，2026-11-16）

现象（本机实测）：`python3 -m pytest tests/` 跑完，九个宿主的 MCP 全部 `lost its stdio
subprocess`；巡检 1 PASS / 8 DRIFT（清一色"server 无响应"）；`~/.vod-devkit/payloads/`
里 0.5.9 整个消失，而所有宿主入口都指向它。

根因是**两处继承**而不是两处默认值：
1. `scripts/host_matrix.py` 在 import 期 `os.environ.setdefault(VOD_DEVKIT_SRC_ROOT/DIST_ROOT)`。
   被 `tests/test_host_matrix.py` 当模块加载后，这两个值留在 pytest 进程里，所有装机子进程
   把 `DIST_ROOT` 解析成**真仓** → 账本写到真仓根（`installs[].payloadDir` 变成 pytest tmp）。
2. 随后 `uninstall` 用例按那份账本把真机载荷目录删掉（`~/.vod-devkit/payloads/0.5.9`），
   于是所有宿主入口指向不存在的路径；pytest 自己只看到一串 `FileNotFoundError`，
   与真正的伤害没有任何一条报错对得上。

**修法（两条，别只做一条）**：
- `host_matrix.py` 不在 import 期写 env（改成 `_pin_roots()`，只由 `main()` 调）。
- `tests/conftest.py` 新增 `_isolate_machine_writes`：pop 掉继承来的
  `VOD_DEVKIT_MANIFEST` / `VOD_PAYLOAD_HOME` / `VOD_DEVKIT_{SRC,DIST}_ROOT` / `VOD_JAVA_API_KEY`。
  **不做**"把 manifest 一律指到 tmp"——装机器用例在克隆仓里跑 `bin/vod-devkit`，账本本来就该
  落在克隆仓根（第一版这么改，19 条用例立刻红：它们读 `<clone>/install-manifest.json`）。

**门禁（S143）**：`tests/conftest.py` 的 session 前后快照——真仓根 `install-manifest.json`、
`~/.vod-devkit/payloads/` 目录清单、`~/.hermes/config.yaml` md5。任一漂移 → 打
`[S143] 测试写到了真机（隔离缺失）` 并 `exit 1`。探针验证过：临时写一个
`~/.vod-devkit/payloads/9.9.9-gate-probe` 目录 → `rc=1` + 该行输出；删掉探针后恢复绿。

| # | 场景 | 断言 |
|---|---|---|
| S143 | 整套测试不写真机 | 全量跑完，真仓根账本 md5、`~/.vod-devkit/payloads` 清单、`~/.hermes/config.yaml` md5 三者不变；故意写真机 → session 门禁 `exit 1` 并指名漂移项 |


## 机器级匿名令牌与显式身份确认（S145，D-token-machine-1，2026-11-16 负责人拍板）

**需求（负责人原话）**：MCP 单独部署时，skill 先判断当前有没有 token —— 有且有效就继续用，
没有就由 MCP 服务代理去服务端领匿名令牌；**一台机器一个 token**（"我觉得可以"）。

**现象（本机实测）**：
1. 匿名令牌绑 `install_nonce`（设备锚点），而 nonce 存在 `runtime.json` 里；该文件旧位置是
   `DIST_ROOT/vod_mcp/`，装机形态即 `~/.vod-devkit/payloads/<版本>/vod_mcp/`。**升级/重装换
   目录就换 nonce、重领令牌**，匿名档日限额重新计、账本断档。
2. 机器上同时存在三份 runtime（载荷 `payloads/0.5.9` / 仓内 `src/vod_mcp` /
   `packages/dsh/data`）→ 三个匿名令牌，限额被拆散；`probe_key` 的 `device-mismatch`
   （"令牌有效但非本机签发"）就是这类 nonce 漂移的现形。
3. MCP 单独部署（无装机、无 key、独立 HOME）实测可用链路已成立：11 工具全在、匿名令牌
   端点可达并领到（32 字符，指纹 `8a33ef89`）、`probe_key` 返回 `verified`。**缺的只是
   "显式判 + 领"的入口** —— 现在只能在首次提交时副作用领取，skill 无法先确认身份再采集。
4. 优先级现状已符合"配置了就用"：`net._live()` 每次现读 env `VOD_JAVA_API_KEY` >
   runtime > 内存镜像 > 默认 base；实测 env 注入坏 key → `auth_status` 报 `rejected`
   且不降级（`legacyKeyHint` 在位）。

**修法（四条，缺一条需求就不成立）**：

1. **机器级 state**（`paths.machine_state_home()` / `runtime_json_path()`）：`VOD_DEVKIT_HOME`
   （默认 `~/.vod-devkit/state`）下的 `runtime.json`；解析优先级 `VOD_DEVKIT_HOME` >
   机器级 state 已存在（存在即用）> 旧 `DIST_ROOT/vod_mcp/runtime.json`（首启兼容）。
   每次现读，不冻结（D-state-read-1 同纪律）。"机器级"的准确含义是**该用户/服务账户下的
   安装实例级**：多用户共机时各用户各一份（系统级共享需显式配 `VOD_DEVKIT_HOME` 并处理
   多账户权限，本轮不默认开启）。权限：文件 0600、目录 0700。
2. **首启迁移**（`migrate_state_once()`）：state 无 runtime 而旧位置有 → 复制一次，
   `install_nonce` / `java_key` / `token_tier` / `product` / 账本原样保留，旧文件不删，
   并落 `<state>/.migrated` 标记防止回灌（state 被手工清掉后旧文件不得复活）；
   此后旧位置只读（全仓写点只有 `paths.runtime_json_path()` 一处）。
3. **`vod_auth_ensure`（core pack）**：唯一有副作用的认证工具，幂等；判定表 ——
   显式 env key → 只探针不覆盖；runtime 显式 key（`auth init` 写入）→ 只探针、被拒 fail fast；
   runtime 匿名令牌 verified → 原样返回（`changed=false`）；
   `no-key` / `expired-anonymous` / `device-mismatch` → 代理领匿名 → 落 state → 复探；
   `rejected`（显式 key）→ **不领**，fail fast；`unreachable` → **不领**，`verified=null`。
   返回 `source ∈ {env, runtime-key, runtime-anonymous, new-anonymous, none}`（身份来源可审计）。
   远程 HTTP 面拒绝（多租户共享进程不代领）。`auth_status` 保持只读。
   并发语义写死：两宿主同时 ensure 可能各领一枚（最后写入者生效）；状态写本身事务化
   （RLock + flock + tmp→replace + 0600），只可能重复领取，不会丢更新或写坏文件。
4. **装机注入 + 回收 + 隔离**：`host_adapters/base.server_env()` 统一写
   `VOD_DEVKIT_HOME` 进各宿主 env（全部已装宿主一致，不依赖默认值）；`uninstall --clean-global`
   逐条打印后回收 state；`tests/conftest.py` 把 `VOD_DEVKIT_HOME` 显式指向 tmp，S143
   session 门禁增加第 4 项（`state` 目录清单 + runtime md5）。

**门禁（S145）**：`tests/conftest.py` 的 `_machine_state()` 四项快照（账本 / 载荷清单 /
hermes config / **机器级 state**）任一漂移 → `[S143] 测试写到了真机（隔离缺失）` 并 `exit 1`。
机器级 state 用"目录清单 + runtime md5"双判：目录不变但内容被改写同样算漂移。

用例承载：`tests/test_token_machine_scope.py`（S145-1..S145-10）。

| # | 场景 | 断言 |
|---|---|---|
| S145-1 | 跨宿主/跨进程共享一份 state | 两个子进程，载荷根分别为 `payloads/0.5.9` 与 `0.5.10`，同一 `VOD_DEVKIT_HOME` → `runtime_json_path()` 相同、`install_nonce` 相同、指纹相同 |
| S145-2 | 升级不换身份 | 版本目录变化不影响 nonce/令牌（同上用例的第二条断言） |
| S145-3 | 首启迁移保留锚点 | 旧 `DIST_ROOT/vod_mcp/runtime.json` 有 `install_nonce=deadbeef` + 账本 → 迁移后 state 里原样；旧文件保留；文件 0600；二次调用幂等 |
| S145-4 | 无 key 时 ensure 领取 | 代理领匿名令牌 → `changed=true`、`source=new-anonymous`、`tier=anonymous`，state 落 `token_tier=anonymous` 与令牌 |
| S145-5 | 已有有效令牌不重领 | `probe_key=verified` → `source=runtime`、`changed=false`、领取函数调用次数 0 |
| S145-6 | 显式 key 被拒不降级 | env key + `probe_key=rejected` → 返回 `verified=false/reason=rejected`、领取调用 0 次、state 不被覆盖 |
| S145-7 | 不可达不领取不判定 | `probe_key=unreachable` → `verified=null`、领取调用 0 次、state 原样 |
| S145-8 | 装机 env 注入 | `base.server_env()` 输出含 `VOD_DEVKIT_HOME=<机器级 state>` |
| S145-9 | clean-global 回收 state | state 下 runtime/lock 被删、空目录被 rmdir、逐条打印 |
| S145-10 | 测试不落真机 state | 测试进程 `machine_state_home()` ≠ `~/.vod-devkit/state`；session 门禁第 4 项跑完不漂移 |
| S145-11 | `.migrated` 防回灌 | 迁移后手工删 state/runtime → 再调迁移不复活旧文件（`migrated=false`，state 仍为空） |
| S145-12 | runtime 显式 key 不降级 | runtime 里 tier≠anonymous 的 `auth init` key 被拒 → `source=runtime-key`、`verified=false`、领取调用 0 次、key 不被覆盖 |
| S145-13 | 远程面与本地同效果（身份） | 远程 HTTP 面：带 Bearer → `source=request`、不代领；不带 → 领/复用机器级匿名令牌并完成提交（引擎 401→领令牌→重试 200） |
| S145-14 | 远程面工具面~~收窄~~**对齐** | ~~`enabled_tools(remote=True)` = 本地 − `{vod_packs_configure}`~~ → **2026-11-18 D-scope-1：两者完全相等**（`REMOTE_WITHHELD = ()`）；draft/commit/list_submitted 均在；`vod_packs_configure` 亦在（stateful 下会话内开关有效） |
| S145-15 | 草稿按宿主隔离 | A 的草稿 B 提交 → `-32011`「不属于当前客户端」；A 自己提交成功且 `twoPhase=true`；旧草稿无 owner 兼容放行 |
| S145-16 | 安装先验需自指证据 | 装着 `--product=CodeArts`，原话「导出太慢了」无自指 → `source=unknown`（转去问用户）；不得凭先验归因 |
| S145-17 | 自指时先验成立 | 原话「你们这个产品导出太慢了」→ `source=install_binding`、`product=31`、`evidence=[{reason:self-reference, alias, snippet}]` 可回指 |
| S145-18 | 代领护栏随绑定地址 | 回环 → 允许代领；非回环无开关 → 关闭（`net.ANON_MINT_DISABLED=True`）；非回环 + `--allow-anon-mint` → 开启 |
| S145-19 | 禁用态不外呼 | `ANON_MINT_DISABLED=True` 时 `_fetch_anon_token()` 返回 None 且**一次引擎请求都不发**（不是"发了再失败"） |


## dsh B 模式：工具面走 MCP client，壳只留 UI（S146，D-dsh-mcp-b-1，2026-11-16）

**背景（参照物实读 + 本机实测）**：dsh 本体自带 `@deepseek-ai/dsh-mcp-client`
（0.2.1-rc.5，stdio + streamable-http），可把 python MCP server 挂成宿主工具
（`mcp__vod-devkit__vod_*`）。huaweicloud-devkit 走的就是这条路，且用托管块写 profile patch。
本仓现状是 JS 壳自注册 6 工具 + 另一份 `data/runtime.json` 账本 → 同一插件两套工具面/两份身份。

**修法**：
1. 版本门槛按 **dsh 本体** `node_modules` 探（profile 里没有该模块）；缺则自装
   （`dsh plugin add @deepseek-ai/dsh-mcp-client`，env `VOD_DSH_SKIP_MCP_CLIENT_ADD=1` 可跳过）。
2. profile patch 改**托管块**：`# vod-devkit DSH integration start/end` 包裹，
   有 client → 两条 insert（mcp-client + 壳`registerTools:false`）；无 client → 只壳块（降级）。
3. 幂等/卸载语义：重复安装只有一份块；卸载只摘自己那块。
4. **卸载不再整文件删 patch**（共享文件，用户/其它插件也写 insert 块——旧路径实锤会连坐）。
5. SKILL 补"dsh 工具名带 `mcp__vod-devkit__` 前缀，以 tools/list 实际名为准"。

**边界**：只做 stdio（`SUPPORTS_REMOTE` 仍 False）；UI 半（`client.jsx` 浏览器直连引擎）不随之统一。

| # | 场景 | 断言 |
|---|---|---|
| S146-1 | 有 client → 双 insert | patch 含托管标记、`id: vod-devkit-mcp` 与 `id: vod-devkit`、壳 `registerTools: false`、env 三键（HOME/BASE/PACKS）都在；stdout 报 `MCP（mcp-client@…` |
| S146-2 | 缺 client → 降级 | 无 mcp 块、无 `registerTools` 键（缺省 true）、stdout 报 `壳自注册（降级：6 工具）` |
| S146-3 | 幂等 | 连装两次：文件逐字节相同、标记与 mcp 块各 1 处 |
| S146-4 | 卸载只摘自己 | 用户追加的 `someone-else` 块保留、托管块消失、patch 文件本身仍在 |
| S146-5 | id 精确匹配 | `- id: vod-devkit-mcp` 不被当成 `vod-devkit`（否则 classify refuse，托管块写不进去） |


## 安装期产品校验：凭据复用与限流分层（S147，D-token-reuse-1，2026-11-16）

**背景**：校验每次新签匿名令牌 → 密集发版（重装全部宿主 + 每次巡检各一次隔离装）把引擎限流打满
（`同网络当日 100` 后放宽到 1000，仍撞 `同 IP 每小时 60`），整批装机被挡；旧文案"不可达"
把人往网络上带。

**修法**：取令牌顺序 = 正式 key → state 已存匿名令牌（device 用 `install_nonce` 配对）→ 新签；
失败四档文案（401 重试一次 / 401 两次报鉴权异常 / 429 立即停 / 网络异常重试一次 / 空目录单独）。

| # | 场景 | 断言 |
|---|---|---|
| S147-1 | 401 一次 | 换设备锚点重领后成功放行；`mint` 与 `meta` 各 2 次 |
| S147-2 | 401 两次 | exit 2，文案含"鉴权异常/401/不同步"，**不得**含"不可达" |
| S147-3 | 网络异常 | 重试一次后报"不可达"（与鉴权区分） |
| S147-4 | 目录空 | 单独文案（指 `productCatalog`/T7i），与上面三档不混 |
| S147-5 | state 复用 | 有匿名令牌时不新签（`mint` 不触发），Authorization=`Bearer <state>` 且 device=`install_nonce` |
| S147-6 | 429 | 文案含 429/限流，且**不再重试签发**（`mint` 只 1 次） |

## 旧载荷显式清理（S148，D-prune-payloads-1，2026-11-16）

| # | 场景 | 断言 |
|---|---|---|
| S148-1 | 默认 dry-run | 不传 `--apply` 时所有目录原样保留，输出含"dry-run/--apply" |
| S148-2 | 非 tty 无 `--yes` | exit 2 且提示 `--yes`，目录不动 |
| S148-3 | 只删旧载荷 | 旧版本删除；当前版本、安装行在用版本、无 `payload.json` 的手工目录都保留 |
| S148-4 | `--keep N` | 保留最新 N 份旧载荷（更旧的删） |
| S148-5 | 无候选 | 只剩在用版本时报"没有可清理"且 exit 0 |
| S148-6 | 不碰 state | 删除后 `state/runtime.json` 仍在 |
| S148-7 | 候选集合 | `prune_candidates()` 只含旧版本，不含在用/当前/手工目录 |


## 产品名录缓存与巡检跳过校验（S149，D-token-reuse-1 后继，2026-11-16）

**背景**：S147 只做到"装机复用 state 令牌"，`host_matrix --audit` 每次巡检对每个宿主各做一次隔离装（各自
独立 HOME → 各自一枚令牌）仍是最大放大器。名录 7 天不变，不该每跑一次巡检就问一次引擎。

**修法**：
1. 校验成功的名录落 `<state>/product-catalog.json`（0600，含 base + at + catalog）；
   `VOD_PRODUCT_CATALOG_TTL`（秒，默认 7 天，0=禁用）；换引擎地址即作废；
   `install --refresh-product-catalog` 强制重拉；
2. 巡检路径用 `VOD_SKIP_PRODUCT_CHECK=1`（`host_matrix._run_install` 自动设）跳过校验——
   巡检验的是装载面，归因名单在装机时已验过。

| # | 场景 | 断言 |
|---|---|---|
| S149-1 | 缓存命中 | 一次外呼都不发，输出"命中本地缓存" |
| S149-2 | TTL 过期 | 重拉引擎并刷新缓存 |
| S149-3 | 换了引擎地址 | 旧缓存作废（按 base 键控） |
| S149-4 | `--refresh-product-catalog` | 绕过缓存强制重拉 |
| S149-5 | `VOD_PRODUCT_CATALOG_TTL=0` | 等于禁用缓存 |
| S149-6 | `VOD_SKIP_PRODUCT_CHECK=1` | 直接放行且零外呼（巡检路径） |


## 巡检探针自证（S150，D-matrix-probe-1，2026-11-16 真机实锤）

**背景**：巡检进程被钉了 `VOD_DEVKIT_DIST_ROOT`，`_probe` 继承后载荷 server 的 provenance
读的是**仓根** `build-info.json` → 载荷 0.5.11 自述 0.5.14，8 个非 dsh 宿主假 PASS。

**修法**：子进程 env pop 三个根变量（entry 显式声明才保留）+ 新增载荷文件自证判据。

| # | 场景 | 断言 |
|---|---|---|
| S150-1 | entry 指向旧载荷 | 即使巡检进程被钉仓根，也必须 DRIFT 且报文含"载荷版本 0.5.11" |
| S150-2 | 载荷版本读取 | 从 entry 的 `vod_mcp/server.py` 反推载荷目录读 `build-info.json`；没有则 None |
| S150-3 | 单用 skip 不生效 | 只设 `VOD_SKIP_PRODUCT_CHECK=1`（无 `VOD_MATRIX=1`）仍走校验并拒绝（S149 边界）|


## doctor 自愈不破坏托管块（S151，D-doctor-repair-1，2026-11-16 真机实锤）

**背景**：旧自愈用 `- ` 猜块边界，把 mcp 块的 args 项当成下一组开头 → 托管块被切断 + 追加旧形态块
→ 两份 `- id: vod-devkit` → 后续自愈全 refuse，MCP 工具面静默丢失（audit 变"降级 PASS"假绿）。

| # | 场景 | 断言 |
|---|---|---|
| S151-1 | 降级形态 + 环境有 mcp-client | 自愈后必须**同时**有 `- id: vod-devkit-mcp` 与壳 `registerTools: false` |
| S151-2 | 幂等 | 形态已正确（期望块文本在场）时再调自愈 → 返回 None 且不改写 |


## doctor 自愈的结构化判据（S152，D-doctor-repair-2，2026-11-16 评审实锤）

**背景**：S151 的判据是「安装器整块文本 == patch 现有文本」，而块内嵌 `sys.executable` /
`machine_state_home()` / `payloadDir`，全按**当前 doctor 进程**求值。四条静默改写（探针复现）：
换解释器改 `command`、手工 `uiBase=/dsh` 被写回 `apiBase`、PATH 无 `dsh` 时删 MCP 块退回 6 工具、
manifest 缺 `payloadDir` 时写成相对入口。

**口径**：`manifest.installs[].dshPatch` 记录安装期真源（command / stateHome / mcpClient），
自愈只补**形态缺口**（缺 MCP 块 / 缺壳块 / 壳未 `registerTools:false`），字段差异只报告，
环境不可判定不动字节。

| # | 场景 | 断言 |
|---|---|---|
| S152-1 | 解释器 | 块内 `command` 等于安装期记录时，自愈不改写（不换成"跑 doctor 的那个 python"）|
| S152-2 | 手工定制 | `uiBase: /dsh` 等字段差异只报告，字节不变 |
| S152-3 | PATH 无 dsh | 有安装期 `mcpClient` 记录时保持 MCP 块，不降级为 6 工具 |
| S152-4 | 缺 payloadDir | 不动字节（入口无法判定），打印重装指引 |
| S152-5 | 形态缺口 | 真缺 MCP 块时仍必须补（S151 行为不回退）|


## dsh 多 profile 的账本与"在用"集合（S153，D-installs-profile-1，2026-11-16 评审实锤）

**背景**：`_install_rows` 只按 `target` 去重，dsh 的 web / headless 两个 profile 互相顶掉：
doctor 只自愈最后装的那个、uninstall 只摘一个块、`prune` 的"在用"集合丢掉另一个 profile
仍在用的载荷（版本一错位就删掉 → 宿主下次启动白屏）。

| # | 场景 | 断言 |
|---|---|---|
| S153-1 | 账本行键 | 行键 = `(target, dshProfile)`；两个 profile 两行，同 profile 重装仍覆盖 |
| S153-2 | prune 在用集合 | `prune --payloads` 的"在用"同时扫 `~/.dsh/profiles/*/cordis.patch.yml` 里 args 指向的载荷 |
| S153-3 | 巡检逐 profile | `--audit` 的 dsh 段对每个 profile 各判一次，报文带 profile 名；任一非 PASS 即 DRIFT |
| S153-4 | 块被清 ≠ 合法降级 | 安装期记录有 `dshPatch.mcpClient`、patch 里却无 `- id: vod-devkit-mcp` → DRIFT（12→6 退化）；记录为空的才是合法降级 PASS |


## 错误码解释表与 raise 点一致（S154，D-explain-codes-1，2026-11-16 通读漏面）

**背景**：`explain` 与代码长期分叉——`-32011` 被写成"产品不在名录里"（真实语义是草稿/审批
令牌不符），`-32012` / `-32014` / `-32015` / `-32001` 在代码里 raise 却"未收录"。上一轮把
文档错误码清单改成 -32010/11/12/14，这张表没跟上，于是命令与文档两套说法。

| # | 场景 | 断言 |
|---|---|---|
| S154-1 | 覆盖 | 代码里出现的 `code=-320XX` 全集 ⊆ explain 表，`known=true` 且三要素（层/原因/动作）齐全 |
| S154-2 | 语义 | `-32011` 的原因必须落在"草稿/审批令牌"，不得再出现"名录" |

## 状态完整性：账本/载荷在用/读侧标量（S155，D-state-integrity-1，2026-11-16 评审）

**背景**：三条评审缺陷同属"状态没有单一真源"——账本可半截且坏账本会被空账本覆盖、
"在用载荷"有两套读法（doctor 会建议删掉仍在用的那份）、托管块写侧加引号后读侧没跟
（含空格产品名读回 None）。另修 hermes 不认隔离 `HOME`（会把真实 `config.yaml` 改成探针路径）。

| # | 场景 | 断言 |
|---|---|---|
| S155-1 | 账本写入 | 所有账本写点走 `atomic_write_text`；`os.replace` 失败时旧文件逐字节完好、不留 `*.tmp` |
| S155-2 | 坏账本 | 写路径 strict 读抛 `ManifestCorrupt`；install 在任何副作用前退出（exit 2、无裸栈、宿主配置与载荷均未写） |
| S155-3 | 在用载荷 | `in_use_payloads` = 账本 ∪ dsh patch；doctor 的"可清理"必须等于 `prune_candidates` 的输出 |
| S155-4 | 读侧 roundtrip | 含空格/冒号/井号/中文的标量与 `server_py` 路径写→读逐字相等；裸标量老装机仍可读 |
| S155-5 | hermes 隔离 | `HOME` 改动而 `HERMES_HOME` 未设 → 拒绝安装；设了 `HERMES_HOME` → 全部落点（含 CLI 写入）都在该根下 |

## 新增 OpenClaw 宿主与 OfficeAce 桌面端登记（S156，D-host-3，2026-11-16）

**背景**：OpenClaw 本机可装可验（npm 包 + `mcp` 注册表 + `agent --local`）；OfficeAce 官方只发
Windows/macOS/HarmonyOS 客户端，本机 Linux 属「无对象」。两者此前只能手写配置，装机不入账。

| # | 场景 | 断言 |
|---|---|---|
| S156-1 | OpenClaw 写入面 | 适配器源码不出现对 `openclaw.json` 的 `write_text`/`merge_mcp_servers`/`atomic_write_text`；安装只调 `mcp add`/`set`，卸载只调 `mcp unset` |
| S156-2 | OpenClaw 隔离性 | 假 CLI 全链路：配置文件字节不变（JSON5 注释不被吃）；无 CLI 时 exit 2 |
| S156-3 | OpenClaw 巡检 | `host_matrix --audit` 经 `mcp probe` 的 launch 拉起 server 自证版本（env 从账本取，不用被打码的 `show`） |
| S156-4 | OfficeAce 平台门 | 非 Windows `install --target officeace` exit 2 且零写入 |
| S156-5 | OfficeAce 行域 | upsert 幂等、保留已有 `owner_user_id`、uninstall 只删 `name=vod-devkit`、表不存在时报错不建表 |
| S156-6 | 注册表一致性 | 两个新宿主都在 `hosts.hosts()` 与适配器 REGISTRY 里，host.json 具备 configPath/skillsDir |

### S156 补记（2026-11-16 第二轮收口）

| # | 场景 | 断言 |
|---|---|---|
| S156-7 | OpenClaw 护栏兜底 | `mcp unset` 被 `size-drop-vs-last-good` 拒时：严格 JSON → 先 `.bak` 再原子摘单键，别人 server/其它键原样；JSON5 带注释 → 字节不动 |
| S156-8 | 在用载荷配置面 | 账本缺行时，openclaw/hermes 配置里引用的载荷仍算在用（prune 不许删） |
| S156-9 | 装了没入账 | 巡检在"注册表有条目、账本缺行"时判 DRIFT |
| S156-10 | OfficeAce 身份 | owner_user_id 默认 NULL，仅显式 env 生效；不抄库里别人的值 |
| S156-11 | hermes 隔离 | 隔离 HOME 时 CLI 落点跟随 HOME；真实 config.yaml 字节不变（含继承 HERMES_HOME 的网关场景） |
| S156-12 | 宿主门禁 | 宿主集合由 integrations/ 派生，REGISTRY 覆盖不全必红 |

## 类型门禁与 OfficeAce 快照（S157，D-gate-mypy-1，2026-11-16 评审）

| # | 场景 | 断言 |
|---|---|---|
| S157-1 | 类型门禁 | `release.sh` 质量门包含 mypy；mypy 非零即拒绝发版（本地与 CI 不再分裂） |
| S157-2 | 备份一致性 | OfficeAce 备份由 sqlite `backup()` 产出（开头是 `SQLite format 3`），不是文件复制 |
| S157-3 | 回滚 | 失败时用快照 backup 回在线库，回滚后条目恢复、行数一致（不覆盖文件） |
| S157-4 | 备份保留 | 超期快照被清理（默认 7 天），同秒多次不互覆盖（名含 pid） |
| S157-5 | 兜底触发 | OpenClaw 卸载兜底只看"条目是否仍在"，错误文案变化不影响行为 |

## doctor provenance 判据改读载荷（S158，D-doctor-provenance-1，2026-11-16 真机实锤）

**背景**：`doctor` 用仓根 `build-info.json`（tracked 文件）比对 manifest 的 commitSha，
而 release 按 tag 口径把根那份写成 `v^`、`install` 却按 HEAD 重烧；两者在发版后的真机上
永远不相等 → 「工作树干净」与「doctor OK」互斥（实测 `git checkout -- build-info.json`
后 doctor 立刻 FAIL）。载荷里的那份是 install 与 manifest 同一次写入的真源。

| # | 场景 | 断言 |
|---|---|---|
| S158-1 | 根 build-info 记 v^（≠ 安装提交） | doctor 仍 OK，不报 commitSHA 不一致 |
| S158-2 | 载荷 build-info ≠ manifest | 必须报「载荷 build-info 的 commitSHA 不一致」（退化回读根即红） |

## hermes spec 重定向按前缀而非分量名（S159，D-hermes-reroot-1，2026-11-16 真机实锤）

**背景**：`_spec()` 把 `~/.hermes/...` 重定向到 `HERMES_HOME` 时用 `parts.index(".hermes")`
取路径里**第一个** `.hermes` 分量。隔离 HOME 落在 `<tmp>/.hermes/cache/...` 下时命中外层
缓存目录，configPath 被拼成 `<HERMES_HOME>/cache/.../home/.hermes/config.yaml` —— 安装器写到
鬼路径，`host_matrix` 报「配置未落盘」（矩阵抓到的，本机真实 HOME 不触发）。

| # | 场景 | 断言 |
|---|---|---|
| S159-1 | HOME 含 `.hermes` 分量 + 设 HERMES_HOME | configPath == `<HERMES_HOME>/mcp/vod-devkit.json`，不得自我嵌套 |
| S159-2 | 落点不在 `HOME/.hermes` 之下 | 原样保留，不许被重定向（防改写别人钉的路径） |

## 共享语义收敛到单一入口（S160/S161，D-single-entry-1，2026-11-16 评审）

**背景**：两处「同一语义多份实现」已经分叉——①安装行读法
`manifest.get("installs") or ([manifest] if … else [])` 在 doctor / prune / packs / uninstall
各写一份，且 uninstall 那份无条件回落 `[mf]`（空 manifest 会被当成"有安装"）；行视图（非 None
覆盖）在 doctor 的两处与 verify 又各拼一遍。②hermes 落点判据两份：`_cli_env()` 用「root 不在
真实家目录之下」、`_spec()` 用「root 在 HOME 之下」，对 `HERMES_HOME=/tmp/shared` 给出相反结论
（CLI 写 /tmp/shared、文件写 `<HOME>/.hermes`，即 0.5.25 修过的分裂形态）。

| # | 场景 | 断言 |
|---|---|---|
| S160-1 | 账本两种形态 | 新版取 `installs[]`；老账本（顶层有 target）退化为单行；空/无 target 返回 `[]`；`installs: []` 不回落顶层 |
| S160-2 | 行视图 | 行内非 None 字段覆盖顶层；None 不覆盖；不改入参 |
| S160-3 | 最新行 | 取 `install_rows()` 最后一条；空账本返回 `{}` |
| S160-4 | 反散落门禁 | `src/` 除 `common.py` 外不许再出现「整份 manifest 顶替安装行」（`or []` 形态合法） |
| S161-1 | 隔离 HOME + HERMES_HOME 在该 HOME 之外 | 文件落点与 CLI 落点**都**跟随 `<HOME>/.hermes` |
| S161-2 | 隔离 HOME + HERMES_HOME 在其内 | 两边都认该 root（矩阵形态） |
| S161-3 | 真实 HOME | HERMES_HOME 照旧生效（不引入新的忽略规则） |

## 评审第二轮：落点不变量 / 门禁口径 / provenance 严格性（S162-S166，D-review-r2-1，2026-11-16 评审）

**背景**（真机评审实测，基于 v0.5.28）：

1. S159 只锁了分场景，没锁**不变量**——新 env 组合仍可能让 `_spec()` 与 `_cli_env()` 分叉；
2. 结构门禁 `test_build_info_root_and_plugin_copy_agree` 在正常发版现场必红（`NO_BUILD_INFO=1`
   下实测 root=9e6182d(v^) vs pkg=HEAD），根因是测试期 sync 会写 tracked 根，门禁在给自己打分；
3. `_provenance_problem()` 有两处假绿：两处 build-info 都读不到时返回 None（等于放行）；
   verify 的 preset 分支只判 `installs[-1]`；
4. hermes 的 `hermes mcp add` 子进程没有 timeout（远程面有 180s），空/异常 HERMES_HOME 下会挂住；
5. `_guard_isolated_home()` 已是纯 no-op（每分支只 return、无输出）。

| # | 场景 | 断言 |
|---|---|---|
| S162 | 落点不变量 | 任意 env 组合下 `Path(spec["configPath"]).parent.parent == Path(_cli_env()["HERMES_HOME"])`（隔离/真实 HOME × HERMES_HOME 在外/在内/未设，5 组） |
| S163-1 | 测试不写 tracked 根 | `sync(write_build_info=False)` 前后根 build-info 字节不变 |
| S163-2 | 门禁口径 | 根/包内 **version** 必须相等且等于 package.json；commitSha 只要求「是本仓真实提交」（可解释），不再要求两份逐字相等、也不锁 v^/v 单值 |
| S164-1 | 不可核验必须报 | 载荷与仓根都读不到 build-info → 报「无法核验 provenance」，不许 OK |
| S164-2 | preset 遍历全行 | 多安装行时逐行判，破坏**第一行**也必须报（报文带 target） |
| S165 | 子进程超时 | `hermes mcp add` 受 `_CLI_TIMEOUT`（默认 60s）约束；超时后仍保住 JSON 片段并打印降级指引 |
| S166 | 删死守卫 | 源码不再出现 `_guard_isolated_home`；落点安全性由 `_effective_hermes_home()` 保证 |

## 引擎 429 的诊断口径（S167，D-engine-429-1，2026-11-17 接口核对）

**背景**：VOD-Project dev（1d4fba8d）把 voiceId 取号改成序列表原子分配；极端异常
（序列行写不进去、并发删行）抛 `VoiceIdExhaustedException`，`POST /external/voices`
回 429「提交排队繁忙，请稍后再试」，明确不造假号。插件 `_http` 对非 401 一律透传
`上游返回 <code>: <detail>`，但 `explain` 表里没有这一条 → 用户看到的是"未收录"，
容易被判成插件/配置故障。

| # | 场景 | 断言 |
|---|---|---|
| S167 | HTTP 429 解释 | `explain("上游返回 429: …")` known，动作含「重试」，且不得指向本机配置（不含 VOD_JAVA） |

## 隔离 HOME 下 HERMES_HOME 的三分支与副本 provenance（S168/S169，D-hermes-root-3way-1，2026-11-17 评审）

**背景**（真机评审第二轮，基于 ab4f7ca）：

1. S161 把判据收窄成「隔离 HOME 下只认位于该 HOME 之内」→ 容器形态
   `HOME=/app` + `HERMES_HOME=/data/hermes`（挂载卷）的显式运维配置被**静默忽略**，
   配置与技能写进镜像层、重建即丢，只剩一行 stderr。属本轮引入的破坏路径。
2. `sync --no-build-info` 在副本缺失时按「根 build-info 的现有内容」补写：根是 v^ 发版快照
   时副本会把自己标成 v^ 而代码是 HEAD——结构门禁查不出（sha 确实真实），provenance 语义错。

| # | 场景 | 断言 |
|---|---|---|
| S168-1 | 隔离 HOME + HERMES_HOME 在该 HOME 之外、也不在真实家目录下（容器挂载卷） | 文件与 CLI 落点**都**用它（显式配置被尊重） |
| S168-2 | 隔离 HOME + HERMES_HOME 在真实家目录之下（网关派生的 `/root/.hermes`） | 两边都跟随 `<HOME>/.hermes`（泄漏面继续挡住） |
| S168-3 | 隔离 HOME + HERMES_HOME 在该 HOME 之内 | 两边都用它（矩阵/显式钉根） |
| S169 | 副本缺失 + `--no-build-info` | 副本按**当前 HEAD** 烧，根 build-info 字节不变 |

## 安装期读回缺口的第二轮收口（S174/S175，D-install-readback-2，2026-11-17 真机）

**背景**（v0.5.29 发版后的真机复验）：

1. `dsh plugin add dsh-vod-devkit@<ver>` 在 registry 尚未传播时失败 → 代码回落「不带版本」
   → pnpm 认为依赖已满足直接跳过 → profile 里的壳仍停在旧版本，而 `install` 三条 RC 全 0、
   账本写入新版本号。本轮实锤：0.5.29 装完两个 dsh profile 壳仍是 0.5.28，只有
   `host_matrix --audit` 报 DRIFT 才暴露。
2. `upsert_hook` 的幂等判据是「同 mark 的行存在即 unchanged」→ 解释器/脚本路径变了永不更新。
   本轮实锤：真机 `pre_tool_call` 用 `/usr/local/bin/python3.12`、`pre_llm_call` 用 Hermes 3.14
   venv，两条 hook 停在两个解释器上，而 doctor 只判 mark 存在 → 全绿。

| # | 场景 | 断言 |
|---|---|---|
| S174 | dsh 装壳：版本化 add 失败回落成功、但 profile 壳版本 ≠ 目标版本 | `install` 必须非零退出（不许账本写新版、壳停旧版），且不写 patch |
| S175-1 | 同 mark 的 hook 行存在但命令不同 | 替换该行命令并返回 `updated`（不再 `unchanged`） |
| S175-2 | doctor 校验 hook 命令里的脚本路径 == 当前装好的 hook 脚本 | 不一致 / 脚本不存在 → FAIL 指向重跑 install |
| S176 | 账本多行时 doctor 的宿主体检（hermes hook / codex 形态 / codearts 冒烟） | 按 `install_rows` 的 target 集合判，不许用顶层 `target`（多宿主机器上它恒为最后一次安装的宿主，整段体检会不执行而报 OK） |

## 宿主家目录重定向与 JSON 宿主读回（S177/S178，D-host-home-verify-2，2026-11-17 真机）

**背景**：

1. 适配层与 CLI 里有 20 余处写死 `Path.home()/".codex"`、`Path.home()/".dsh"`——宿主自己认
   `CODEX_HOME` / `DSH_HOME`。设了变量的机器上「我们写 A、宿主读 B」，写对了却看不见；更糟的是
   doctor/巡检读同一份错落点，自洽地错。
2. opencode / atomcode / workbuddy / codeartswork / codeartsdoer 是 JSON 合并写入：写完就打印成功，
   没有读回。被别的进程覆盖、写成 enabled:false、指向的 server.py 被删，install 与 doctor 都看不见
   （只有 `host_matrix --audit` 会报 DRIFT）。

| # | 场景 | 断言 |
|---|---|---|
| S177 | 设 `CODEX_HOME` / `DSH_HOME` | `hosts.load()` 的 configPath 与 `paths.host_home()` 都跟随变量；不设时回落 `~/<sub>` |
| S178-1 | JSON 宿主配置无 `vod-devkit` 条目 | `host_verify.problems(host)[0].code == "no-entry"`；`require_ok` 非零退出 |
| S178-2 | 条目 `enabled: false` | code == "disabled"（宿主不会加载） |
| S178-3 | 条目指向的 server.py 不存在 | code == "mismatch"（载荷被删/路径写错） |
| S178-4 | 条目健康 | 返回 `[]`（不误报） |

## 宿主配置写入原子化（S179，D-atomic-host-writes-1，2026-11-17 真机）

**背景**：`write_text` 写宿主主配置与共享 JSON 是「半截文件」制造机——写到一半被中断/磁盘满，
宿主拿到的是残缺 config.yaml / cordis.patch.yml / codex config.toml，**直接起不来**；而
install 已经把账本写成"装好了"。此前只有账本、openclaw、officeace、merge_json_mcp 走了
atomic（同目录 tmp → fsync → chmod → replace），其余十余处仍是裸写。

| # | 场景 | 断言 |
|---|---|---|
| S179 | 扫描 `src/vod_mcp/host_adapters/*.py`、`paths.py`、`vodkit_cli/{install,uninstall,packs_cmd}.py` | 除 `atomic_write_text` / `tmp.` / `bak.` / `dest.` / `# atomic-ok` 之外不得出现裸 `.write_text(` |
| S180 | 目标文件是符号链接（dotfiles 场景） | 先 `resolve()` 再 tmp+replace：软链保持、真实文件被更新（不许把链接换成普通文件） |
| S180-2 | 目标文件是 chmod 444（用户显式保护） | 抛 PermissionError、内容不变（tmp+replace 会绕过 write_text 的旧语义） |

## 巡检与 doctor 的判据一致性（S181，D-two-judges-1，2026-11-17）

**背景**：`host_verify`（doctor/install 面）与 `scripts/host_matrix.py --audit`（巡检面）各判一次
同一份宿主配置。两侧曾出现相反结论（audit DRIFT / doctor OK），根因就是两套判据各自演化。
doctor 侧已统一到 `host_verify`；audit 侧因还带"按配置拉起 server 自证"不能直接替换，先落
**同结论门禁**：同一份合成配置上，两侧不得一个说可用、一个说不可用。

| # | 场景 | 断言 |
|---|---|---|
| S181 | 合成 hermes config.yaml 四态（无文件 / 无条目 / enabled:false / 健康） | `host_matrix._hermes_effective_entry()` 与 `host_verify.problems("hermes")` 的可用性判定逐态一致 |

## 行为回归判定口径与话术分型（S182-S184，2026-11-17）

**背景**：C1 长期报"原话被改写"，实测是三种故障混在一句报文里：①比较基线用 `prompt[:60]`
（含「帮我记录反馈：」命令前缀，引擎按纪律会剥）→ 长句必假红；②引擎只回 title 前 60 字，
把"截断"也算成"改写"；③真实改写（「重新导又」在第 58 字被写成「重新导入又」）淹没在前两条里。

| # | 场景 | 断言 |
|---|---|---|
| S182 | e2e 判定口径 | `content_not_paraphrased`：引擎 content 必须是「剥前缀原话取前 60 字」的**前缀**（截断 PASS，窗口内增删改 FAIL）；`echo_status` 三态 ok/incomplete/missing，incomplete 单独记 `echo_incomplete` 桶；模板用 `{content_start}` 标记算 offset，不靠字符串搜索 |
| S183 | 草稿展示缺字段 | 展示 contents 时缺失的 reproSteps/expectedBehavior 明写「（…：用户未提供）」；只出现在展示，不进 content 不上送，不写推测 |
| S184 | 引导话术分型 | 现象词优先（报错/卡死/失败/打不开/超时/崩/没反应）→ 缺陷型；否则含建议词（希望/建议/能不能/要是…就好/太繁琐/不方便）→ 建议型；都无→缺陷型。建议型只问「场景 + 希望什么样」，禁索要复现步骤；本轮只做话术分流，不写 problem_type 标签 |
| S187 | 行为回归的引擎可用性 | 5xx/连接类错误退避重试（4 次）→ 用尽抛 `EngineUnavailable`，脚本 exit 2 报「不可判（环境故障）」；401/403 不重试不吞（判定依据）；无 key 不发请求 |
| S188 | 宿主模型临时覆盖 | `--model`：codex `-m` / opencode `--model` 插在 prompt 之前；不给时 argv 与旧版逐字一致；未知宿主显式失败；只改本轮 argv、不改宿主配置 |
| S189 | 回合无产出 | 回复为空且零落库 → `indeterminate`：无 fails、零记账、`[不可判]` 打印并 exit 2（与违规 exit 1 分档）；有落库或有回复照常判 |
| S190 | 用例基准的自指前提 | 正向用例（submit_consent/single_row）必须含 `attribution.SELF_REFERENCE` 任一词；负向用例不得被判成 explicit_consent；自指词表单一真源、用例文件不复制 |
| S191 | 自指命中后不追问产品 | 原话含自指词（attribution.SELF_REFERENCE）且安装绑定过产品 → 按安装先验归因、不再问产品；草稿回执 `attribution.source=install_binding` 为佐证；自指与先验都没有才追问 |
| S200 | 绑定检查是第零步 | 采集流程 0 步首句=先调一次 `vod_devkit_info` 读 `manifestSummary.product`；有值+自指 → 不许先调 `vod_search_products`、不许追问产品，直接承接+征得同意 |
| S201 | 日志写即可见 | `Tee.write` 逐行 flush（日志文件按行缓冲）；`run_suite` 每案先打 `[case i/n] id` 心跳——被 kill 的轮次也要留下已产生的行与进度 |
| S202 | 元语汇只收工程搭配 | META 去掉裸「发布」「环境」，改收 发布流水线/发布流程/环境变量/测试环境/预发环境/构建产物；补「登录不上/登录不了/登不上」现象词；用户视角句（刚发布的版本打不开 / 生产环境卡死了）必须注入 |
| S203 | 判定可解释 | `route_detail()` 返回 decision（strong/inject/silent）+ reason（strong-prefix/trigger/no-trigger/meta-discussion/empty）+ 命中的 trigger/meta 词；`route()` 是薄包装——单一判定路径 |
| S204 | 绑定兜在工具回执 | `vod_search_products` 在有安装绑定时回 `installBinding` + `nextStep`（自指命中直接用、不要再追问；不要拿 catalog-default 无分候选问用户）；无绑定不给 |
| S205 | 用例基准的提交指令 | 期望落库的用例（submit_consent/single_row）提示词头部必须含明确提交指令（提交/收录/上报）——只写「记录/反馈」时纪律要求二次确认，用例永远达不到 |
| S206 | 锚点归属 | 命中多个 anchor 时按**最长**归属（不按 SUITE 顺序）；嵌套锚点必须归到外层用例，配套「任一 anchor 是别人的子串 → 归属仍正确」的参数化断言 |
| S207 | 盐不落进原话区 | 模板把 `{t}` 放到提示词末尾（原话区保持纯正文）；渲染后 offset 之前只有命令前缀，且 `text[off:]` 不以盐开头 |
| S208 | 回执不许复制真源词表 | `nextStep` 不得出现 `attribution.SELF_REFERENCE` 任一词（举例会被当穷举，收窄模型行为） |
| S209 | 回执字段进契约 | `vod_search_products.output` 登记 `installBinding`/`nextStep`；用例断言handler 返回键 ⊆ 契约 properties |
| S210 | 巡检按 commitSha 对账 | `_payload_drift()`：版号相等不算对账，载荷 commitSha ∉ 账本该版本的 sha 集 → DRIFT（同版号换内容必须报） |
| S211 | 第二判定路径 | `DISABLE_WORDS`（用不了/没法用/挂了/闪退/丢了/空的/没动静/不相关/难用/不回/转圈/自动刷新）+ TRIGGER 任一命中即采集意图；META 且无 ANCHOR 仍零注入 |
| S212 | 框架信封零注入 | 内部通知/后台回执/压缩摘要/prior context（`[INTERNAL NOTIFICATION`、`[IMPORTANT: Background process`、`[PRIOR CONTEXT`、`[CONTEXT COMPACTION`、gateway 自述）→ `reason=envelope` 静默；`[OUT-OF-BAND USER MESSAGE …]` 是用户本人消息，仍正常判定 |
| S213 | 发版终态不许把超时当未发布 | `_npm_view()` 超时重试 3×90s、耗尽抛 `RegistryQueryTimeout`；`publish_verify` 打「不可判」并 exit 3（1=未上线，3=不可判）；`release.sh` 区分二者，exit 3 只提示不清账、不重发 |
| S214 | 落库线三态（设备/key 锚点漂移的兜底；初版归因「查询不覆盖囤积档」已修订） | 有引擎行=可判；无引擎行但本机账本有回执=**不可判**（exit 3，不记违规）；两者皆空=真违规。引擎侧待办：GET /external/voices 需覆盖囤积档或提供新端点 |
| S215 | 门禁漂移先归因 | S143 快照漂移时扫描并发写入者（install/巡检/真机 e2e）：有 → 打印归因、不判隔离缺失（不再让全绿测试轮 RC=1）；无 → 保持 exit 1 |
| S216 | 等待看两个源 | `_await_engine_rows` 每轮同时查账本：账本已有 expect_rows 条引擎回执即收工，不再空等 poll_s=600s（判据不变，仍由三态裁决） |
| S217 | 判据基准剥轮次盐 | `strip_salt_offset()`：回显/逐字判据用剥掉末尾盐的文本；模型把括号时间戳当插注丢掉 = 正常行为，不再记 echo_incomplete/echo_missing |
| S218 | 失能词路径排除工程对象 | `ENGINE_OBJ_WORDS`（配置文件/字段/数据集/缓存/模板/日志/索引/库表/服务/进程/脚本/证书/密钥/集群）：纯失能词 + 工程对象 + 无用户锚点 → 零注入；产品视角（页面/按钮/导出…）仍注入 |
| S219 | 信封剥掉再判 | 信封标记行与载荷先剥除，余文含用户意图标记（提交反馈/帮我/我要/我们…）则继续判定；另补中文信封（【内部通知】/【系统通知】/【后台任务】） |
| S220 | 账本走单入口解析 | `ledger_rows_since` 走 `vod_mcp.paths.runtime_json_path()`（VOD_DEVKIT_HOME > 文件 > 物理位置），删除拼字符串绕钩子的写法；自定义 HOME/企业部署不再静默退化成「真违规」 |
| S221 | 空回合不空等 | 宿主回复为空（`task_complete.last_agent_message=None`）时观察窗取 30s，不再等满 600s；判据不变（空回合=不可判） |
| S222 | 判定层纯函数化 | `judge_case()` 抽成无副作用单元（输入=引擎行/账本行/回复/原话基准，输出=fails+违规桶+不可判）；`run_case` 只做编排与入桶；表格驱动用例穷举 8 类结论 |
| S223 | 原因标签与文档同步 | `vod_router.REASONS` 声明全部结论标签，用例断言实际产出相等且每个标签在 design 登记 |
| S224 | 退出码单一说法 | 环境故障=3（不可判）、熔断=2、鉴权 4xx=4 三处（代码表/实现自述/`docs/host-realverify.md`）必须一致；用例断言自述与表同步 |
| S225 | 判据两侧都剥盐 | `strip_salt_anywhere()`：引擎落库内容里的首/尾时间戳同样剥掉再比对——盐是提示词的一部分，模型会把它当正文提交，基准剥了候选没剥即假「改写」（实测 C4/C5） |
| S226 | 反馈渠道边界（A 方案） | 技能内新增「渠道边界」：判据=用户要的产物（提个单/建 issue→建单渠道；提交反馈/收录→VOD；只抱怨→问一次去向），**同一句抱怨只进一个通道**，且该条优先于其它触发规则；README/README.en 增加「同机不要同时启用两个采集技能」须知；触发动词不删 |
| S227 | 信封不许自注自判 | 信封余文的用户意图判据改为**行首**锚定，且剥掉 `[vod-router]` 自身输出行——否则后台回执引用我方指令里的「提交反馈」会再触发一次注入（死循环） |
| S228 | 插件不托管宿主生命周期 | 插件职责固定三件（写宿主配置/落载荷与技能/doctor 读回）；`src/` 零 `systemctl|systemd|launchctl|restart`，用户文案不出现宿主命令行；边界写入 design 九·五 + D-boundary-1（含 Falsifier）；门禁 `tests/test_boundary_host_lifecycle.py::test_s228_*`（含反向锁：用户文案不许教人跑 systemctl） |
| S229 | 生效口径单一真源 | 用户可见「重启…生效」只由 `vod_mcp.msgs` 拼：11 个宿主适配器 + doctor/update/packs/auth 全部改走它（措辞逐字不变，golden 不动）；门禁断言除 msgs.py 外无第二拼写点，且每个适配器都必须 import 并调用 msgs |
| S230 | 现役文档路径卫生 | 现役文档（README/README.en/RELEASING/docs 现役篇）零坏链；不得出现旧布局裸路径（`contract/…`、`safety/…`、`skills/vod-core/…`、`hooks/vod_*.py`），须写 `assets/…` 或 `integrations/hermes/hooks/…`（载荷平铺语境与历史台账 decisions.md/CHANGELOG 不追溯）；门禁 `tests/test_docs_path_hygiene.py` |
| S231 | 冷启动目录与主键纪律 | 独立部署冷启动时 `vod_search_products` 先懒领一次匿名令牌再取目录（本工具唯一写盘例外，仅目录为空时触发）；仍不可用 → 回执 `reason=catalog_unavailable` + 处置提示，不静默给空；`productId` 禁止用产品名冒充主键：目录有该条但无 id → `source=unknown`+`evidence.reason=id_unresolved`，展示名只在 products（catalog 用库名，如 OBS vs 对象存储服务 OBS）→ 保留并标 `name_only`，老引擎（无 catalog）→ `name_legacy`；用户回答命中无主键 → 回候选而非写 `"None"`；门禁 `tests/test_s231_catalog_cold.py`（5 条） |
| S232 | 空查询分因 + 安全面可查 | `vod_search_products` 空查询回 `reason=empty_query`+hint（入参名是 query），不再静默 0 候选；`host_matrix --audit` 每行追加 `hook 层：有/无`（HOOK_LAYER/hook_layer_label），把"只有 hermes 有 hook、其余只有技能教法"变成机器可查；运维文档补 CI/矩阵段（隔离 HOME=新设备锚点、令牌机器级、钉 VOD_DEVKIT_HOME、目录 TTL 7 天）；门禁 `tests/test_s232_reason_and_hooks.py` |
| S233 | 候选串单一拼写点 + 计数不由文档手写 | `core.format_candidates()` 收掉 collect 三处候选串拼写（含一处为绕 f-string 用 `+` 拼接的写法）；文档/注释里写死的工具数改为由代码真值推导：proposal 里 dsh 的 `Registered N tools` 由 3 校正为真值 6（壳自注册计数），壳注释「12 工具」改为「随 packs（默认 10 / 含 knowledge 12）」；门禁 `tests/test_s233_counts.py`（从壳源码数工具 + 文档 `Registered N tools` 对账 + 候选串契约） |
| S234 | 功能级验证入口单一来源 | 新增 `scripts/probe_tools.py`：按宿主自身配置起 server 调只读工具（默认 info+auth_status，可选 search_products），只验不提交；入口解析统一走 `host_matrix.resolve_entry()`（巡检与探针同源，禁止各解析一份配置）；环境变量 `env`/`environment` 两种键都读（裸探针只读前者会把 10 工具报成 12，实测）；设计六「验收脚本不入库」校正为「放 scripts/、不进 npm files 白名单」；门禁 `tests/test_s234_probe_tools.py`（7 条，含 scripts/ 不随包发） |
| S236 | e2e 判据按本轮 voiceId 收窄 | `scope_engine_rows()`：引擎行以本机账本本轮回执 voiceId 为白名单，排除时间窗内并发/外来提交（实测 C1/C4 因外来行报假「改写」）；收窄后为空且有回执 → 落库线「不可判」而非违规；回执 notes 写明排除行数；纪律：e2e 不与其他提交并发跑；门禁 `tests/test_s236_engine_scope.py`（4 条） |
| S237 | 面向用户禁词表 | 技能新增「面向用户的用语纪律（禁词表）」：归因/白名单/令牌/配额/幂等/引擎/端点/提交链/囤积/草稿/主键/名单/voiceId/插件/MCP 不许出现在回复里，并给三条替换口径（产品归属：X / 已受理请确认 / 整句删除只说结果）；e2e FORBIDDEN_REPLY_WORDS 同步扩充；门禁 tests/test_s237_reply_wording.py（4 条，含不误伤回执必需话术）；发版后复跑 C3/C5 |
| S238 | 删除老链回落 | 移除 `_EXISTING_SUBMIT` 与 404 回落分支：囤积端点 `POST /external/voices` 成为唯一提交路径；404 → `ToolError(-32016)`「本条未提交」，不假装成功、不换链；契约 backend 说明与设计单上游出口图同步；门禁 `tests/test_s238_no_legacy_fallback.py`（3 条：无老链调用/404 明确失败/正常路径只打囤积）|
| S239 | 老链表述残留清理 | 契约 `vod_submit_voices` 描述删掉「引擎未部署 404 自动回落老链」（改为「唯一提交路径，404=本条未提交」）；`collect.py` 注释「囤积/legacy 两路径」改为单一路径；门禁 `tests/test_s239_stale_wording.py`（契约/注释不得再写老链为可用路径，且必须写明囤积端点）|
| S240 | 计划/反例路径必须显式标注 | 文档里出现的「不存在的路径」分两类处理：真正的计划项（`docs/reports/`、`integrations/hooks/`）标「计划内/尚未存在」，反例（`plugins/vod-devkit/src/vod_mcp/`）标「反例，勿照做」；设计里引用的技能侧探针路径写明「在本仓之外」；门禁 `tests/test_s240_plan_paths_marked.py`（这些 token 只能以标注形态出现，防下一个人照着去找）|
| S241 | dsh 壳删除旧单条提交链 | 删除 `SUBMIT_PATH`（`/external/voice/submit`）、404/非 2xx 回落代码段与仅供旧链使用的本地 `voiceId()` 键；囤积端点 `POST /external/voices` 成为唯一提交路径，失败如实报错（404→-32016「本条未提交」，其他→-32002），与 Python 侧对齐。回归锁 `packages/dsh/test/no-legacy-submit.test.mjs`（常量/路径/回落判定/POST 目标）|
| S242 | dsh 回执完整性 + 失败话术 | 三处缺陷：①引擎 `rejected` 被吞（用户被告知「已收录」而实际未入库）→ 合并透出；②`voiceIds` 缺失时按空回执记账（本地账本被空 voiceId 污染）→ `accepted=0`+`receiptIncomplete=true` 且不写账本/不记归因；③dsh 壳无本地 pending 队列却被 SKILL 教成「已暂存、稍后自动重试」（谎报）→ 失败回执加 `notStored=true`+`userFacingHint`，SKILL 区分「有插件提交失败」与「插件未安装走无通道落盘」。门禁 `packages/dsh/test/receipt-integrity.test.mjs`（5 条）|
| S243 | dsh 采集语义对齐 vod_mcp | ①补契约必填的 `echo` 回显（`requiresUserEcho/instruction/contents`，与 `_echo_plan` 同构）；②补 `tags` 采集层三分类（`problem_type:` 按产品白名单过滤，`GET /external/meta?productId=` 取 problemTypes 24h 缓存，取不到=不过滤不误杀，脏值丢弃并报 `invalidTags`）；③补缺产品先问一次（`code=-32010`+`needsProductAsk`+候选串，计数封顶 3、成功归零；歧义不追问——引擎 UNKNOWN 池接得住）。门禁 `packages/dsh/test/parity-collect.test.mjs`（6 条，含行为级 stub 断言）|
| S192 | 退出码与回执不可判 | 0 全绿 / 1 违规 / 2 熔断 / 3 不可判 / 4 鉴权或引擎 4xx（优先级 1>2>3>4）；空回复+有落库 → `reply_indeterminate` 不进 fails、内容判据照跑；横幅打 model+argv、收尾打 `e2e[exit]` |
| S193 | 路由词表并表 | `TRIGGER_WORDS` ⊇ SKILL 的 S184 现象词（失败/打不开/超时/崩）+ 口语词；裸「卡」加边界；META 移出共用词（接口/配置/字段/日志/版本）、改收工程动作词 |
| S194 | 不可判只管网线 | 回执不可判不清空 fails（内容线结论保留）；单出口 `decide_exit` 让异常路径带已收违规（有违规 exit 1）；异常报文逐条打 FAIL、未完成数取剩余 |
| S195 | 路由工程第二层 | META 补 CI/构建/编译/流水线/发布/回滚/单测/环境/栈；裸「麻烦」换成语境化（太麻烦/很麻烦/麻烦死了）；语料含反向断言 |
| S196 | 安装绑定可观测 | `vod_devkit_info` 的 `manifestSummary.product`：state 优先、manifest 唯一绑定回落、多绑定回 null（不猜）；SKILL 据该字段执行「自指→不问产品→直接建草稿」 |
| S197 | 每轮日志留痕 | 脚本 tee 到 `.e2e-runs/<ts>-<host>-<model>.log`（未指定模型写 default）；kill 也留下已产生的行；目录进 .gitignore |

## 预采集路由的判定口径（S185/S186，D-router-scope-1，2026-11-17）

**背景**：`vod_router`（hermes `pre_llm_call` 钩子）只判「消息里有没有触发词」，于是把
**讨论产品反馈这件事**当成**用户的反馈**。本轮实测复现 7 条元讨论里 6 条误判：拿「建议增加」
「希望支持」「为什么不能」「报错」「卡」当采集意图，注入的指令要求模型「必须按采集流程处理、
先问产品」，把一轮设计评审拐去提单（真机发生过一次）。同时抓到反方向漏判：「体验太差 / 白屏 /
没反应」不在现象词表里，真实抱怨零注入。旧口径把「错注入无害」当拍板结论，实测不成立——注入
会改变当轮任务走向，不只多一段话。

| # | 场景 | 断言 |
|---|---|---|
| S185 | 元讨论（工程对象语汇命中且无用户视角锚点） | `route()` 返回 `None`：7 条评审/方案/代码/文档语句全部零注入 |
| S185-2 | 显式「提交反馈：」前缀 + 元语汇 | 仍走强指令（`无需再判断意图`）——排除不得压掉用户指令 |
| S185-3 | 真实自身遭遇（带页面/按钮/登录/导出/加载等锚点） | 照旧注入采集指令（排除不得扩大成漏判） |
| S186 | 现象词变体 | 「体验太差 / 白屏 / 没反应」必须命中（实测漏判原话） |

## 套件编排的可测化与词表不变量（S198/S199，2026-11-17 代码整理）

**背景**：前几轮（S187→S197）都是「真机事故 → 补口子」，`scripts/e2e_behavior.py` 因此长成了
补丁摞补丁：退出码在**三处**各算一次（正常收尾 / EngineUnavailable / EngineAuthError），
上一轮评审抓到的 P2a（异常路径丢掉已收违规）就是这个重复的直接后果；而路由词表连着三轮
「修一条、换个词又长一条」，语料用例只能钉住已知误判，新增词的结构性问题没有护栏。

本次是**语义保持的整理**（行为不变，只消除重复与不可测面）：

| # | 场景 | 断言 |
|---|---|---|
| S198 | 套件编排 | 抽取 `run_suite()` 返回聚合 `Summary`（fails/indeterminate/reply_unjudged/total_rows/processed/abort）；退出码只在 `main` 一处计算；异常路径与正常路径吃同一个聚合；`processed` = 已完成条数（抛异常那条不算）；重复的 `decide_exit` 删除 |
| S199 | 词表不变量 | 三张词表（TRIGGER/META/ANCHOR）无重复、无空串/带空格；两两不相交（同一个词不能既算抱怨又算工程语汇/锚点）；装配正则里只允许裸「卡」一处边界规则（出现第二处必须显式登记） |

门禁价值：S198 让「异常路径丢违规」这类回归在单测里就能抓住（不用起宿主、不用真引擎）；
S199 把「新增词静默破坏优先级」变成必红。语料用例（既有 16 条）继续负责已知误判的回归。
