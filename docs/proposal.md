# VOD 插件化（vod-devkit）需求文档

- 需求编号：VOD-PLUGIN（特性分支 feat/vod-devkit-plugin，基于 yangaiwu 分支）
- 版本：v0.1（2026-11-03）
- 状态：待评审
- 仓址修订（2026-11-03，已决策）：直接于独立新仓开发（本仓）；原「P0 先在 VOD-Project 验证、触发条件后剥离」作废。当前暂住 xiaowu2119/vod-devkit，VodTeam org 建仓/转移需组织管理员权限（API 已试：403/transfer 需 admin），有权限后一步转移，仓内容零改动。
- 引擎前置缺口（实测 api.py 路由）：vod_kb_search 依赖 POST /api/vod/knowledge/query，api.py 尚无此路由——U6 验收前须引擎侧补端点。analyze/json、status、result 已按真实路由对接。

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
| 发起分析任务 | 写 | vod_run_analysis | confirm + 条数上限 |
| 任务状态查询 | 读 | vod_task_status | 放行 |
| 任务结果获取 | 读 | vod_task_result | 放行 |
| KB 精准检索 | 读 | vod_kb_search | 放行 |
| 分类匹配规则 | 知识 | 技能 vod-category-matching | 只读 |
| 问题分类规则 | 知识 | 技能 vod-problem-classification | 只读 |
| 评分规则 | 知识 | 技能 vod-scoring-rules | 只读 |
| 插件路由入口 | 知识 | 元技能 vod-core | 只读 |
| 安装溯源与宿主感知 | 元信息 | install-manifest + vod_devkit_info 工具 | 只读 |
| 用户反馈声音采集 | 写 | vod_submit_voices + vod-feedback-collect 技能 | confirm 逐次+单批≤50+source 取握手身份 |

明确不暴露：Excel 批量导入、数据库直连、任何 DB 写操作。

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
**实测发现的引擎缺口**：submit 白名单=代码常量 VALID_PRODUCTS
（六值，无 AIShell）——AIShell/AI shell 类产品反馈当前会被引擎拒收，
需引擎侧扩白名单（挂 VOD-KEY/meta 端点一并解决）。
**可漂移值经接口取最新（设计定稿）**：product 白名单/分类六类定义/
功能子类词典都是引擎侧会漂移的枚举字典（本次技能过期即实证），
静态嵌入必漂移。方案=引擎新增只读 meta 端点（GET /external/meta/*：
products 白名单+归一规则、problem-types 六类、dictionaries），
插件安装/首次调用拉取+缓存（runtime.json，TTL 24h）+快照兜底+
stale 标记。/external/products 实测存在但属报告侧全集，与 submit
白名单不是一个集合——meta 端点须以 submit 校验常量为源。
三个技能已按引擎代码重写（真源=n01_classify/workflow_v2/
category_matcher @2bb3fc82；vendor 源 skills md 已过期停用）。

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

## 四、验收用例清单（在目标环境执行，工具不入库）

| # | 用例 | 预期 |
|---|---|---|
| U1 | agent 配置 mcpServers 指向 vod-devkit-mcp，重启会话 | 工具 4 个全部可列举 |
| U2 | 调用 vod_run_analysis（白名单 profile，≤上限条数）【内部形态 preset full】 | 返回 taskId；任务表新增记录 |
| U3 | 未经用户确认调用 vod_run_analysis | 被 confirm 规则拦截，零副作用 |
| U4 | vod_task_status(taskId) 轮询 U2 任务 | 状态与引擎侧一致 |
| U5 | vod_task_result(taskId) | 与 vod-system 前端同任务结果一致 |
| U6 | vod_kb_search("评分规则") | 命中评分规则卡片，含出处 |
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
| U28 | auth_status 在 hermes 会话内调用 | 7 工具含 vod_auth_status，指纹正确显示 |
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

## 六、待办

- 设计文档评审（docs/vod-devkit-plugin/design.md）
- 评审通过后 P0 开工
