# Changelog

## v0.1.0（2026-11-03）

首个可用版本：VOD 用户声音采集插件（方案 A 纯采集形态）。

- 3 工具：vod_submit_voices（confirm+单批≤50+归因三层+零字段匿名令牌
  自动获取+声量保真 voiceId）、vod_devkit_info、vod_auth_status
- 动态元数据：meta 拉取+24h 缓存+快照兜底+stale 标记
- 声明式护栏 + 契约单一事实源 + 溯源（commitSHA verify）+ preset 安装
- 端到端已实测：真 Hermes 会话→测试环境 Java /external/voice/submit
  →taskId 回执（零引擎侧改动，复用现有接口）
- 23 用例（单元+护栏+packs+协议级真 HTTP+stdio 回环+meta）

## v0.1.11（2026-11-05）

- f3040fc feat(D-product-id-2 安装期产品硬校验): 用户拍板 B——install --product 必须命中 meta productCatalog（名字大小写不敏感/平台主键 id），未命中或目录不可达一律 exit 2 拒绝（归因前提无效=内置采集技能全部空转且用户无感知；宁可不装不可装错）；推翻'宿主名是显式合法值'宽容口径（hermes 同拒）；bin/_validate_product_or_exit（无 key 匿名令牌链，老引擎退 /external/products）+ java-api-base 补 env VOD_JAVA_API_BASE 优先级；installer fixture 进桩引擎（协议级零外呼），新增 3 例回归锁；71 用例绿
- 5a9431c docs(T7i): S33 场景用例归位到 S30-S32 块内（上笔误插文件尾，结构修正）
- 22f1deb docs(T7i): proposal 增 S33 插件侧主键化解析矩阵场景用例（D-product-id-1 关联）
- 15e2eb0 feat(T7i 产品归因主键化): 三壳 product 经 meta productCatalog 解析平台 id 后提交——python _resolve_product（纯数字透传/短码归一后查目录/目录缺失回规范名兼容通道，不静默丢提交）+node resolveProductId（进程内缓存）+dsh UI submit 时解析（token 复用）；meta 载荷新增 productCatalog=[{id,name}]（引擎 364af5df 组装，t_vod_product 真源）；decisions.md 记 D-product-id-1；pytest 68 绿（T7i 新增 2 例）+dsh node test fail 0
- 2f39647 chore: vod-devkit v0.1.10（V16 随版）+ dsh-vod-devkit 0.1.1 版本记录
- db2b256 chore: v0.1.10（V16 dsh server 半囤积切换随版）
- 07a2936 feat(V16 dsh server 半): 提交切囤积端点——主路径 POST /external/voices 批量（title=原文截取、content=用户原话不补模板、无 scene），404 回落旧单条；http() 统一带 X-Vod-Device-Id（runtime 常驻纯 hex nonce，对齐 VOD-DEVICE）；确认话术修正（'入库即触发分析'为旧单条口径残留，囤积语义=入库不触发分析）——用户实锤的模型话术源头即此
- 8ceb1d0 fix(D-anon-ui 输出契约): 工具描述加 OUTPUT CONTRACT 禁句——禁止向用户解释内部机制（声音来源/渠道字段/计数规则/配额/归因）；实锤：会话模型把'声音来源：DSH Web GUI'与'入库就计算'当答案讲给用户（渠道统一 vod-agent 客户端不自报；净新增才计数——两句都半错且吓人）。根因=dsh 侧模型约束仅工具描述覆盖、SKILL 按需加载不保证生效
- e542f8a chore: v0.1.9（持久标签随版）
- a8ad44e fix(D-anon-ui a11y): 输入框补持久可见标签+aria 关联提示（对标业界共识：可见标签比 placeholder 可靠——placeholder 输入即消失；label for/aria-describedby 全关联，提示常驻不随输入消失）。真机验证 label/hint 可见、aria 关联生效
- 8e081a8 docs: S31/三·十一 同步 chips 移除拍板（取代 hint 口语化初版方案）
- a6344e4 chore: v0.1.8（撤分类 chips 随版）
- 05ce5fb fix(D-anon-ui 极简): 撤分类 chips（用户拍板）——n01 引擎全量重判已覆盖分类信号，UI 预分类仅 hint 且用户分不清边界（三层认知负担换不来信号质量）；表单收敛为单输入框+提交+历史入口；真机验证 chips 消失、公网同源提交落库（外网终验 ✅）
- 4fbcdb6 docs(D-anon-ui 收口): proposal 增 S28-S32 场景用例（历史页签本机边界/数据驻留显式不可用/极简弹窗/hint 口语化/设备锚点 hex）；design 增 三·十一 反馈页面职责与历史面板（三主体边界实现/设备锚点/SKILL 话术三层结构）
- c8392f2 chore: v0.1.7（弹窗极简随版）
- 5f81d3c fix(D-anon-ui 极简弹窗): 删反馈弹窗说教块（'你的反馈将进入 VOD…产品团队会结合内容复核'）——内部流程解释对用户无信息量，职责单一句口径下表单只留：分类/输入框/历史面板/提交。真机验证 hint 已除、其余组件在位
- 4dee727 chore: v0.1.6（历史页签+noLocalLedger 禁用链随版）
- cf118eb feat(D-anon-ui 历史页签): '我的反馈（本机记录）'面板落地——三主体边界拍板实现：①数据=本机账本（不出浏览器）+本人令牌回执，无越权查询面 ②顶部标注'仅保存在当前浏览器；换浏览器或清除数据后不可见' ③--no-local-ledger 经 index-inject 注入禁用旗标：UI 停写账本+面板显式不可用（部署策略提示），不显示空列表 ④状态 F2 口径（已收录/暂存自动重试）
- 643b96c chore: v0.1.5（D-anon-ui 收口：uiGlobals 重构+契约锁测试+S24-S27+design 三·十）
- cbf0260 docs+test+refactor(D-anon-ui): 收口——①重构：注入行抽纯函数 uiGlobals(config)（可单测）②新增 node:test 契约锁 7 用例（uiGlobals 四态/schema 无 product+内容纪律在位/SKILL.md 纪律标记防回退）③proposal 三·八 增 S24-S27 场景用例（安装时注入链/裸装同源/设备锚点 hex/内容编造防线）④design 三·十 配置通道设计节（index-inject 机制+键位分工+apiBase 禁注页面+过时口径警示）。node --test 7/7 绿
- ce1a8f1 feat(D-anon-ui): 借鉴 VOD-Project gitcode-issue-creator 的声音生成方法论——字段处理分级表（content🔒原样/title🧠摘要/分类🧠推断）、推断≠编造正反例辨析（AIShell 实锤事故入例）、调用前强制预检三项、不追问原则。根因对照：我们只写防御性'禁止编造'，缺正向推断规则，模型在'忠实转写'与'反馈要有用'张力下选择编造情感结论
- 632a669 fix(D-anon-ui): index-inject 不再注入 __VOD_DSH_UI_BASE__（apiBase 是 server 半自用值，127.0.0.1 注给公网浏览器=Failed to fetch 复现根因）；UI base 默认同源，仅跨域部署显式配 uiBase 才注入
- fe7206c chore: v0.1.4（三竞品借鉴项随版：触发条件结构化/草稿自动保存/部署坑文档）
- d32605c feat(D-anon-ui 借鉴落地): 三竞品借鉴三项——①SKILL.md 触发条件结构化（三条件可判定清单，combined feedback-adapter 同款写法）②UI 草稿自动保存（content/category 实时落 localStorage，重开恢复，成功提交清除；借鉴 bridge）③INSTALL.md 补 dsh 部署已知坑五条（全部实锤：id=包名/设备锚点纯 hex//rest/ 同源代理/patch config 不下发 client 半/排障日志位置）
- 5f72c4e docs(D-anon-ui 职责正向定义): 借鉴三竞品职责写法——SKILL.md 置顶一句话正向职责（整理为一条声音+用户同意+提交+人话回执；模型只做识别意图/忠实转写/征得同意三件事，决定权在用户），禁令降级为三件事的实施边界而非职责主体；对照=官方 log-only/bridge 整理者/combined 补一环
- 20cfc4f chore: v0.1.3（分类 hint 文案随版）
- 746e5c8 fix(D-anon-ui 文案): 分类 chips 副标签口语化——id/label=云声平台标准枚举不可动（引擎 T7c 映射锚点），hint 改为覆盖典型现象的用户口语（慢/难找/确认烦/答非所问/结果不符合预期）引导对号入座；真机渲染验证通过
- 20d3396 fix(D-anon-ui 话术): 工具名/机制词/主语纪律——实锤 'vod_submit_voices 被我调用后你拒绝了它'：内部工具名与机制词(调用/被拒/护栏/参数/配额)不外露，对用户统一说'提交反馈'；主语纪律=动作主体是'我'，系统行为说'系统/稍后自动'，不把内部裁决说成用户的行为。SKILL.md F2+工具描述双处落码
- 1ef4c91 fix(D-anon-ui 职责收敛): 用户拍板——本技能职责=采集-确认-提交-回执一条线，不发散：SKILL.md 前置职责边界（产品问答/机制解释不在职责内，不读文档作答不科普，一句'不在反馈功能范围内'交回宿主）；products-external.md 未入库即撤（发散产物）
- 7f4229f docs(D-anon-ui): 增设面向用户的产品定义层 products-external.md——AIShell 问答暴露的分层缺失：仓库只有内部归因文档，模型被问'XX是什么'只能拿内部口径凑答（归因/白名单/文档行号端给用户）。纪律：对外问答只引用产品定义层；AIShell 定义标注待 VOD 复核
- 4215c7e docs(D-anon-ui): 过时口径修正——'VALID_PRODUCTS 拒收 AIShell'为 MR !152 前旧口径，normalizeLoose 后不设白名单（未注册落 UNKNOWN+productRegistered 软标记，实测 VOD/AIShell 均落库）；scheme-overview 里程碑同步引擎合入现状。dsh 会话模型引用的即此过时文本
- a23b63e fix(D-anon-ui 内容编造): 用户单字/提问被模型编造成带情感结论的反馈（'AIShell 产品体验不好'实锤——用户原话只是问 AIShell 是什么）——①工具描述加内容纪律硬约束：content 必须忠实转写用户原话，禁止发明情感结论；名词/提问不是反馈，需澄清 ②测试库清除 3 条编造脏数据（id12/13/15，含 ISYNC 登记）③遗留：AIShell 产品定义缺失（文档 gap，移交 VOD 团队）；囤积区无撤回语义（引擎侧 gap，待提案：管理台作废/by-voice-id 撤回）
- 7b5f737 chore: v0.1.2（0.1.1 已被 CDN 复制占用；D-anon-ui 全套修复随版）
- 669dc34 fix(D-anon-ui): UI 设备锚点纯 hex 化——getDeviceId 产出 uuid 带连字符，引擎 [0-9a-f]{8,64} 校验不过静默降 legacy ip|ua 锚点（签发 5 次/天打满=散户 token 429 实锤）；uuid 去 mask 截 32 hex，与 MCP/dsh-server 半同口径。真机：新锚点签发→提交落库 tier=anonymous product=VOD 全绿
- 46663d7 fix(D-anon-ui): dsh UI 部署配置链与话术纪律收口——①server 半经官方 webserver/index-inject 通道把 patch config(product/apiBase) 注入页面全局（对齐 settings-account __DSH_CONTACT_CONFIG__ 机制），client 半零改动读全局：产品归因=安装时配置，零使用时设置 ②base 默认同源相对路径（宿主代理 /rest/，公网/内网/本地同构；nginx /rest/ 反代部署件）③UI 表单对齐云声：placeholder 本地化（XX 模板字在 per-product 弹窗是冗余+污染源）、单输入框不加标题摩擦（voice_title=原文前64字）④UI 半补 X-Vod-Device-Id（对齐 VOD-DEVICE，legacy ip|ua 锚点 5 次/天易打满实锤）⑤欺骗通道封堵：SKILL.md 删'用户点名另一产品→确认覆盖'（S1 用户自报不可信，防话术投毒）；dsh 工具 schema 删 product 参数（部署配置权威）⑥F2 失败路径同口径：SKILL.md+工具描述禁止向用户暴露 HTTP 码/fingerprint/tokenTier 等内部字段；devkit_info 匿名态显式标注'默认正常态非故障'（防模型误诊'凭据未配置'）。真机：纸飞机渲染+表单全链+落库 anonymous 全绿
- 13ee747 docs(INSTALL): 对标 devkit 增补安装指南——每宿主一节（前置/安装/连接级+功能级+写链路三级验证/常用命令），npm 公网一行装口径替换 github 引导，含 legacy key 勿带警告、-32011/-32012/-32013/-32014 故障表、与 devkit 的安全边界刻意差异节；README 安装节收窄为速览+指向 INSTALL
- 9a0fef1 chore: npm/cli.js 补可执行位（publish 流程实测需要；bin 引导器入口）
- ffdfe78 chore(npm 首发): vod-devkit@0.1.0 已上 npm 公网（staging 型 token 实测：npm publish 首包直接落暂存、CDN 复制延迟致 npm view 短暂不可见——0.1.0 已 latest）；0.1.1 版本号随提交；npx 一行装真机验证：npx --yes vod-devkit install --target opencode → 配置生成 → stdio 真调匿名链提交 → DB tier=anonymous 落库
- 0805475 docs+test(D-anon-verify): 匿名令牌链信封契约收口——proposal 三·八新增 S21-S23 场景用例（信封契约/匿名链端到端/legacy key 移除语义）；design 二·八令牌端点契约修正为 ApiResponse 信封并标注真机实锤依据；decisions.md 记 D-anon-verify 台账；测试重构：_extract_anon_token 单函数化，存量 mock 从扁平形态对齐引擎真实信封（mock 边界≠协议边界教训二次落码），新增 4 用例（信封解析/扁平兼容/垃圾输入拒止/无 key 匿名链 e2e 时序锁）；全量 65 用例绿
- d17ef1d fix(D-anon-verify): 匿名令牌链真机实锤修复——引擎令牌端点返回 ApiResponse 信封 {code,data:{token}}，_fetch_anon_token 顶层取 token 恒 None → 无 key 首提必 -32012『端点不可用』；改为信封兼容解析（data.token 优先、顶层扁平兼容）。此前未暴露因插件常驻 legacy key 不走匿名链；本地部署真机验证：无 key 首提自动签发→key_tier=anonymous 落囤积区→同令牌重提同 voiceId 幂等
- 09eb1e7 feat(D-device-anchor-1): 匿名令牌设备锚点插件侧——_http 统一出口对全部 /external 请求附 X-Vod-Device-Id=install_nonce（首启自生成常驻，零新增状态），引擎据此建每设备独立锚点（NAT/产品分发不再收敛）；preset 克隆镜像 uptime 判据告警（母机镜像未清状态检测，仅告警不阻断）；协议锁+克隆判据 3 用例；62 用例绿
- 17e9cfb lint: test_distribution 夹具 re-export 改赋值别名+清未用 import（pyflakes 门禁）
- e75646b feat(D-key-guard-3): 分发形态位 distribution=preset 收口产品分发六项——①install --distribution preset 写 manifest+key 禁随包（env pop+告警）②update 禁用（随 agent 发版）③verify 降级本地完整性（离线不 FAIL，混装 FAIL）④首启残留清理（firstBootAt 标记+preset 残留自动重生成，弃时间戳启发式）⑤--no-local-ledger 账本出口 ⑥日志 1MB 轮转；重构实锤：_runtime_cfg/_save_runtime 路径双写修复+_save_runtime replace 语义；proposal 七节+design 七节+用例 DG1-DG9；59 用例绿
- 5132cc7 docs(D-key-guard-2): 分发红线拍板落档——对外产品形态禁止预置 appkey（key 落在哪台机器哪台就是信任边界），三档信任模型（终端=匿名/宿主=服务端持 key/运营=formal），appkey 通道收窄 dormant 保留；scheme-overview 对外交付形态同步
- b8d1a73 feat(D-key-guard-1): key 安全三件——①显式 key 被 401 拒 fail fast（防静默降级匿名=假锚定），匿名令牌维持自动重领，_explicit_key 分流（env 注入权威+token_tier）②_save_runtime S1 式写后验 0600（chmod 效果回验+告警不阻断）③probe_key 有效性探针（GET /external/meta 复用，三态 verified/rejected/unreachable），auth_status.keyCheck+doctor 接入；45 用例绿（新增 5），真机探针/假 key/doctor 三场景实测
- 588a9ae docs: 引擎 !152 合入后行为变化落档——UI 囤积直通在即（部署前 404 暂存/部署后 201 直通同一代码）、A2/锚点配额/verbatim desc 与 UI 的关系核验（401 自愈链原生兼容，零调整）、MCP 切换完成记录（D-switch-1）；40 用例绿
- 059c072 feat(V16 切换): MCP 主路径切囤积端点 /external/voices（用户拍板立即切）——①批式提交（voices[]+tags 透传+product），voiceId 由引擎确定性计算回执下发（客户端不再自造 id），taskIds 囤积语义置空 ②引擎未部署 404 自动回落老链（过渡语义，path=legacy-fallback 标注；404 判定对齐真实 _http code 语义）③legacy 吞声量修复：回落 source 带 per-install nonce（_install_nonce runtime.json 常驻，杜绝跨用户共享 mcp 命名空间）④匿名令牌自动获取链同步支持囤积主路径 ⑤协议锁/声量锁/title 锁三个回归测试升级到新契约（囤积主路径断言+404 回落两场景+E4 结构化字段锁改 title 承载）；40 用例绿；schema 契约描述同步
- 3586fc9 feat(T7d 统一): install --product 必填——MCP 与 dsh UI 产品归因同口径（安装必配/加载必配），缺省宿主名在生态部署是错归陷阱（高校AI开发者平台底座=hermes 不填全归 hermes）；宿主名保留为合法显式值；报错引导含生态产品名示例+/external/products 权威名单；新增必填+显式绑定两用例（原缺省宿主名用例语义废止），40 用例绿
- 3775763 fix(深检二轮): 三个小缺口收口——①UI 暂存重试体补 scene（row.scene 存账本但重试重建体漏带，断网补提时场景静默丢失）②productRegistered 软提示消费（引擎 T7f 回执标记→未注册时提示'产品名尚未注册，请联系部署方核对'，防配置错误静默）③重试分支不动（静默不打扰）。MCP 侧软提示随切换补丁（老链无此标记）；39 用例绿+重建
- 2b6e83a docs+fix(T7d): 对接产品清单落档——产品归因取值=生态看板 14 产品（高校AI开发者平台/成长中心/各实践中心/AI 开发者空间/AI Agent 集成/AI 工具集成/AI 运行环境/开放能力/Skills门户/GTD/VOD），UI 必配提示示例修正（CodeArts 系旧 profile 词汇非对接清单）；t_vod_product 同名注册=部署前置项
- 3250b60 feat(T7d): 产品归因=加载必配（用户拍板：加载插件时主动提供产品）——UI 半无 __VOD_DSH_UI_PRODUCT__ 注入=入口不激活+console 报错（fail fast；替代 e99c347 的'不注入=中性+UNKNOWN'设计，归因错误比没数据更糟：缺省宿主名在嵌入场景会静默错归）；提交体 product 恒带；MCP 半 install 绑定不动（宿主即产品缺省成立）；真机双路径验证（无注入不激活/注入 CodeX 激活+提交体带 product）；39 用例绿
- f09934f fix(align): T7b 定稿——渠道=引擎囤积入库侧固定赋值 vod-agent（链路即渠道，客户端不自报），插件两侧取令牌回归零字段（方案 C 原样）：UI ensureToken 空 body、MCP _fetch_anon_token 空 body；docs 同步（渠道机制三版演进：客户端自报→白名单→引擎固定，最终对齐 VOD-Project 链路即渠道模式）；39 用例绿+client.js 重建
- ea16b61 fix(align): 渠道收敛单一值 vod-agent（用户纠偏：渠道就是渠道，传输形态 dsh UI/MCP 不拆渠道）——UI_HOST 与 MCP 取令牌 host 均改 vod-agent，引擎注册表/展示枚举/矩阵同步单值（对应 VOD-Project c946583a 后提交）；重建 client.js
- d36da24 feat(align): 对齐 VOD-Project 采集标准三件（T7b/T7c 插件侧）——①渠道标注：取令牌 body 带 host 常量（dsh-ui/MCP 侧 mcp，随包编译），引擎 VodCollectChannels 注册表准入，匿名档 collect_source 可按渠道分组 ②分类收敛云声三分类（功能建议/用户体验/产品缺陷，suggestionType 逐字对齐；六类=n01 分析层内部枚举不进人看表单，用户纠偏：原六类未做映射属自设口径）→ tags problem_type 正式入库，description 模板文案移除（无承载物）③title 显式传入引擎尊重+文案对齐（场景 placeholder 产品×功能×场景引导、hint 补分类复核语义）；入口按钮加「反馈」文字标签（用户拍板：纯图标不友好）。真机端到端验证：token body host/voices body tags/无 description/账本 category+scene+accepted/按钮图标+文字框外定位全过；39 用例绿；引擎对应 VOD-Project 2af44b6e 之后提交（V26-V29 用例）
- b086d76 fix(dsh-ui): 入口图标换纸飞机线稿（用户拍板：对齐 dsh 发送/纸飞机形态，非消息反馈的点赞图标——上轮理解错图标指代）
- 4e93133 fix(dsh-ui): 入口图标三处纠偏（用户实测）——①真移到输入框外上方（原 top+5 实为框内，改 top-h-6，DOM 断言 outside=true）②图标换 👍 点赞线稿（对齐官方 message-feedback 的 IconLike 气质）③弹窗标题 反馈一句→提交反馈（与动作一致，footer 键改「提交」避免重复）；真机验证位置/标题/图标
- 7f074bf feat(dsh-ui): U-S2/S3 闭环尾款——提交成功后 issue_sync 回执轮询（10s×6：CREATED 展示 issue 链接/REJECTED 显示未采纳，引擎 !152 部署后自动生效）+暂存自动重试（会话首挂载补提 pending-endpoint/failed 行 cap 5，账本行补 content/description 重试重建字段）；对应引擎 proposal §八 S1-S7 与本文档 U-S1~U-S7 场景用例；真机验证表单/降级/账本结构
- 932a986 docs: dsh-ui-collect 补实现状态（解耦自研组件/动态产品名注入/crypto 安全上下文坑及 FNV 兜底/官方三坑/公网 trusted-host/测试盲区教训）+场景用例 U-S1~U-S7 对应引擎 proposal §八
- e99c347 feat(dsh-ui): 三处 dsh 硬编码改动态——文案/product/description 前缀统一走 __VOD_DSH_UI_PRODUCT__ 注入（嵌入方装前设置，任何支持本插件能力的 agent 通用），不注入=中性文案+不带 product（引擎 UNKNOWN 档，不静默猜纪律）；真机双路径验证：无注入中性/注入 CodeX 文案随动
- 81fa03c fix(dsh-ui): crypto.subtle 公网 http 访问为 undefined 崩溃（安全上下文限制，实测踩坑：127.0.0.1 验证是安全上下文测不出）——sha1Hex 加 FNV-1a 双种子兜底（账本键无密码学要求），crypto.randomUUID 原有兜底保留
- ae23261 refactor(dsh-ui): 解耦官方组件——移除 @deepseek-ai/dsh-client-ui-primitives 依赖，自研 SelfModal/PrimaryBtn（视觉参考官方 message-feedback：遮罩+488px 卡片+✕ 关闭+44px footer 主键），dsw 令牌降级为可选增强（CSS 变量在则跟主题、不在用硬编码兜底，非 dsh 宿主可用）；图标本就内联 SVG 无依赖——client 半核心 UI（弹窗/表单/提交/账本）现零宿主组件耦合，可移植到任意宿主 web UI；真机验证弹窗/表单/提交键
- 519d547 feat(dsh-ui): 表单换官方 Modal/Button 原语+全套 dsw 设计令牌（对齐官方 message-feedback：Modal open/title/closeLabel/footer、Button variant=primary 44px 提交键、chips/输入框全走 --dsw-alias 变量跟主题）——require @deepseek-ai/dsh-client-ui-primitives 走 shell 模块表（官方 bundle 同款）；真机验证 Modal 渲染/chips/提交键
- 535519b fix(dsh-ui): scene 按引擎契约独立字段提交（voices[].scene ≤128，VOD-VOI design.md 实锤）——不再塞 description 前缀；旧 submit 链无此字段场景下引擎本就丢弃，改后 !152 部署即生效
- 7d8e91f feat(dsh-ui): 分类换 VOD 引擎 v2.2 六类口径（产品缺陷/技术业务咨询/体验改进/功能需求/主观评价，无效问题不给用户选项）——默认不选=引擎 LLM 全量重判（技能纪律：错误预分类比留空更糟），选中仅作 problem_type hint 落 tags；图标 emoji→SVG 对话气泡（emoji 跨平台渲染不稳）；真机验证 chips/SVG/可取消交互
- 0929b6b feat(dsh-ui): 入口迁至输入框右上角（用户拍板）——挂载仍走官方 composer.dock 槽，组件自算输入框矩形 fixed 定位角位（实测 btn(1097,518) vs input 右上(1129,513) 精确命中），ResizeObserver+轮询兜底跟随布局；图标 💬+悬停反馈提示；脆弱性（contenteditable 选择器依赖官方改版需回归）记档 design §十
- f98309a feat(dsh-ui): 表单加分类 chips——参考官方 message-feedback 七分类（任务结果/指令理解与遵循/产品功能与交互/稳定性和速度/资源使用与费用/安全隐私与权限/其他），单选默认其他，随提交落 description 前缀+账本 category 字段；真机验证 chips 渲染与交互；另记官方可借鉴：dialog 渲 conversation.input.overlay 槽/结构化错误码/可撤回评分
- fb41664 refactor(dsh-ui): 删手填昵称+同意勾选——身份改登录态二值（用户纠偏：昵称手填是账号体系未证实期的过渡产物；登录→取 dsh 账号快照 user_masked，未登录→纯匿名无身份字段，表单只剩内容+场景）；v1.1 接账号快照 API 待真机确认读取通道；真机重验表单通过
- 240f3db feat(dsh-ui): 笑脸采集 UI client 半实现+真机验证——conversation.composer.dock 槽注册 😊 按钮→弹窗表单（内容≤2000/场景/昵称+知情同意勾选）→匿名令牌+POST /external/voices，失败优雅降级+localStorage 确定性账本键；浏览器直连 VOD（CORS 已实测通）。构建三坑记档：dsh.client.platform 声明、exports.inject=[slots] 缺则内核不激活、React 不 vendor 走 shell 模块表（esbuild transform 模式+wrap_client.py 官方 factory 包装）。tgz 重建待 npm 发布
- bfc6572 docs: T-VER 真机验证落档——boot dsh web 实测笑脸按钮落点=conversation.composer.dock 槽（官方 activity pill 同款注册模式 ctx.slots.inject+register，无降级路径需要）；账号面升级=dsh 有账号体系（settings-account：平台授权 URL/account.view.status credential-stored/avatar details），身份源层1从待证实升为存在
- 1481e26 docs: dsh 采集 UI（笑脸入口）设计——UI 扩展机制实证（ui-slots register/client.js 下发）+身份源三层知情同意+UI 通道确定性 voiceId（用户级维度幂等，区别 MCP nonce 有意为之）+回执 F2+护栏对齐；decisions.md 记 D-dsh-ui-1
- 943d766 docs: README 双语安装节补市场命令（npx github:/WorkBuddy marketplace add/dsh 本地 tgz+npm 后目录一键安装）+用例数 20→39+单上游文案修双后端残留；decisions.md 记 D-market-1（dsh-plugin topic 不提前打：根仓=引导器非 dsh 插件包，目录上架绑定 npm 发布同批做）
- b625301 fix(install): 无 key 不写 VOD_JAVA_API_KEY 空串进宿主配置（空串会被严格解析器当字面值；空=未设置，运行时兜底 runtime.json/匿名令牌）；+1 用例，38 用例全绿；本机重装清洗配置
- 5411aea fix(install): 平台地址缺省值改为真实环境——默认常量 DEFAULT_JAVA_BASE=https://vod-dev.topxtopx.com（单一定义，bin/tools 共用），废除 127.0.0.1:8090 回环默认（外部用户本机无 VOD，装完即坏）；--java-api-base 变可选仅覆盖用；+1 用例锁缺省双落，38 用例全绿
- d27f904 feat(install): --java-api-base 双落 runtime.json java_base 兜底——宿主 env 透传不稳时不再静默落回 127.0.0.1:8090（优先级链 env>文件不变）；+1 用例锁双落
- 2feacb4 fix+test: codex 幂等剥离 bug 修复 + 安装器矩阵测试 10 例（fake-home+桩 hermes+本地 bare origin 隔离，零网络不碰真实仓/真实 HOME）。bug：旧正则在 args=["…"] 行内 [ 处断块，旧 env 子表残留→二次安装 env 表×2、换 preset 不生效；改按行整块剥离。测试覆盖 opencode schema/无损合并/幂等、codex TOML 幂等、hermes 官方 mcp add 通道、归因绑定（缺省=宿主名/显式优先）、packs 过滤、update ff+重烧/tracked 冲突拒改、doctor 缺配置检出、uninstall 清场。36 用例全绿
- 5071787 docs: 治理可选件三件——CODE_OF_CONDUCT.md（Contributor Covenant 2.1 适配）+ SUPPORT.md（分层自助排查/GitCode+GitHub 双 issue 渠道）+ NOTICE（VOD-Project vendored 素材溯源+devkit 骨架参考声明，无代码复制），README 双语入口链接
- 1653295 docs: 治理四件套必做两件——CONTRIBUTING.md（定位边界/契约纪律/提交流程）+ SECURITY.md（漏洞报告渠道/安全模型与不做的事/溯源对账），README 双语入口链接
- 66196b3 feat: 归因口径变更「宿主即产品」不设白名单（用户拍板：都不限制，hermes 就归 hermes）
- f1e925d fix(dsh): 深审 D-dsh-1 传输守卫落码（-32014 非 https 非回环拒绝，对齐 vod_mcp）+D-dsh-2/3/4 记档与代码标注
- 9ecda4a docs: 对齐纯采集实况+dsh 形态章节——能力清单/U2-U6 标注已删除（方案A f1103df 留档）、护栏表对齐 policy.json 真实规则 id、新增 S11-S16 dsh 场景用例（安装激活/审批门禁/枚举归一/兜底降级/账本对账/双形态一致）、design 新增三·九 dsh 薄壳形态（结构/配置面/语义对齐/四实测坑）；另 PAT 移出 remote URL 进 credential store（600）
- 43e323f feat(dsh): dsh 薄壳插件 R3 落地——3 采集工具（submit/list/info），cordis 形态真机验证通过
- a00654f docs: 传输守卫设计节+S20 场景+双远端分叉收敛说明
- 454af49 security: 传输协议守卫——http 仅限本机回环，公网 http 拒绝（-32014/U38），Bearer 不得明文过公网，26 用例绿
- 85baa18 feat: 差距替代路线四件闭环——OpenCode 真机 connected（schema 修正）/Codex 真机识别/nightly E2E cron（首跑 taskId=420）/README.en.md；GitHub Actions CI 首跑 success
- 1ff0a7a ci: GitHub Actions 质量门（镜像仓跑服务端 CI——绕行 GitCode Actions 平台不可用）
- 47e6752 feat: plugin.json 市场清单（WorkBuddy/CodeBuddy marketplace 准入）——GitHub 镜像推送完成
- a8c8372 feat: 分发三件套——npm 包（cli.js 引导器+pack 27 files 实测）/宿主适配层（opencode JSON 合并+codex TOML env 子表+auto 0/1/N 探测，fake-home 配置写出验证）/发版脚本 release.sh（质量门+三处版本同步+CHANGELOG+tag+双远端）
- fad2bc4 feat: 提交记录查询层级①——本地账本（cap 200 只动 submissions 键）+vod_list_submitted 只读工具；修复账本从内存合并回写陈旧配置缺陷（测试实锤）；S17-S19/U35-U37，25 用例全绿
- 66d5a61 docs: 拍板落档——公开上架等 key 签发制（急则白名单灰度）；遥测维持不做（未来 opt-in 默认关）
- a0bd37f feat: 身份界定定稿（归属/授权分离，外部分析对表：三处不采纳+签名回执记P2）；内容边界≤2000落码（U32）；方案一页纸；S14-S16/U32-U34，24 用例全绿
- 01e61cc ci: pre-push 本地机器门禁（平台 Actions 不可用期间的替代，实测隔离为账号级平台问题）


## v0.2.0（2026-11-05）

- cd37786 feat(D-drift-lock+宿主接入对表): devkit 对表三件落地——①技能拷贝件漂移锁：install 记 skillHashes 指纹→doctor 比对（篡改/缺失 FAIL 引导重装；拒绝 skills-as-MCP-data 架构迁移的依据=规模变量，漂移可检先落地）②opencode /vod-doctor 自检命令随装（devkit_info/auth_status/list_submitted+key 禁令）③scripts/smoke_hosts.py 三宿主连通冒烟（无宿主 SKIP 语义；真机三 PASS）。hooks 层拒绝理由修正为威胁面对照（devkit hook=封 shell 里 hcloud 绕行路 2665 行对抗；囤积链无破坏面无绕行路）。proposal S38-S40+design 九节对照表；75 用例绿
- 80117b4 docs+test(D-codex-plugin-1 收口): ①proposal 新增 S36（插件自包含+stale 缓存治理+校验设备锚点）/S37（设备锚点一致性协议级）场景用例 ②design 增第八节 Codex 原生插件接入（机制实测/约束三层分工表/自包含与缓存治理/宿主能力判定纪律）③新增 S37 协议级测试：桩引擎捕获 token/meta 请求头比对设备锚点+UA 一致性+纯 hex 断言；73 用例绿
- 4c65af6 feat(D-codex-plugin-1 增补): devkit 对表三件采纳——①install 前清 stale 插件缓存（~/.codex/plugins/{marketplaces,cache}/vod-local，缓存不自动失效）②插件自包含：.mcp.json 改 python3+./vod_mcp/server.py 相对路径+cwd（去 npm -g 前置），sync_plugin.py 同步 vod_mcp+烧录 build-info.json 进插件包（第四版本失位点实锤：契约 version 滞留 0.1.0，vod_devkit_info 假象——release.sh 同步点 3→4）③plugin.json 补 interface 元数据；安装器校验探针补设备锚点（token/meta 同 device+UA，S1 设备绑定）；自包含契约锁测试新增；72 用例绿；真机闭环：重装→codex exec 报 version=0.1.12
- 3ea554b feat(D-codex-plugin-1 codex 原生插件接入终态): 实测推翻'codex 无 skill 机制'——0.166 有 codex plugin add/marketplace+.codex-plugin/plugin.json(skills+mcpServers)+skills 渐进式加载；AGENTS.md 方案作废（降级模拟），改原生插件：仓内 plugins/vod-devkit（SKILL.md 采集工作流全量+.mcp.json）+本地 marketplace 清单；bin 新增 serve 子命令（.mcp.json 可移植入口）；install --target codex 切原生路径+清理旧 config.toml 段/AGENTS.md 块（同名双注册防）；工具描述修 S1 口径冲突（用户自报产品不采信不覆盖）。proposal S35+decisions D-codex-plugin-1（含方法论教训：判定宿主能力必须翻全 --help 子命令树）；真机闭环（marketplace→add→提单不反问→product_id 落库）；72 用例绿
- 599478b feat(D-codex-agents-1): codex 技能层载体落地——codex 无 skill 机制，采集质量方法论（触发三条件/content🔒字段分级/推断≠编造禁例/预检三项/不追问/回执话术/职责边界）此前在 codex 上裸奔（工具描述只装硬约束）。install --target codex 随装幂等写入 ~/.codex/AGENTS.md 技能紧凑块（标记剥离幂等，用户自有内容保留）。工具描述同步修口径冲突：删除'用户明确要求其他产品可显式传参覆盖'（违背 S1 同源原则——用户自报产品一律不采信不覆盖，照部署产品提交正文原样）。tags 语义注释（problem_type:云声三分类入标题前缀，非 n01 六类）。新增 AGENTS.md 幂等/内容保留测试锁；72 用例绿
- acfcc4d fix(D-product-id-2 收口): submit_voices 描述补归因话术并前置——codex 等 MCP-only 宿主不加载 skill，模型唯一约束源是工具描述；原描述零归因话术导致用户提单时被反问'什么产品'（T7d 后已废除的旧职责话机复活）。话术前置防宿主描述截断；外部对表建议采纳：约束三层（工具描述/参数描述/非required 结构）+AGENTS.md 仅冗余；其 .codex-plugin/capability_directories 体系与本机 codex CLI v0.166 实测机制不符未采纳（待证据）。71 用例绿；codex 真机行为验证：提单不带 product 不再反问、直接安装绑定归因提交落库


## v0.2.1（2026-11-05）



## v0.2.2（2026-11-06）

- e2928cb test(D-codex-plugin-1 增补2 补): 自包含契约锁断言更新为 serve 入口形态（相对路径断言随 .mcp.json 定稿移除，失败原因留注释）；skills 随包断言补入
- 4cd6d84 fix(D-codex-plugin-1 增补2): ①SKILL.md 清除 V16 前废弃旧职责残留（四节 content 模板/声音来源字段/detect_channel——与工具描述新契约直接冲突，codex 真机会话实锤模型按旧模板走偏：翻仓库找提交规范→要工单字段→用户原话丢失未提交）；frontmatter 触发词补 提单/提 issue②工具描述补提单语义+话术前置强化（content=原话即完整提交物，禁止追问补齐/索要开发者字段）③.mcp.json 定稿 vod-devkit serve（相对路径+cwd 在 codex 0.166 实测不解析到插件目录）④sync_plugin.py 补 skills 同步（此前只同步 vod_mcp=又一漂移面）
- 4418a91 feat(D-golden-1 扩展+D-probe-1 探针工具化): ①tests/probe.py 可复用 stdio 探针（initialize/tools/call/护栏 error 分流——多轮真机手法沉淀）+pack 门控真实装配层锁（VOD_PACKS 两种取值 tools/list 协议级断言）②golden 扩展：status 原样 manifest 契约（HOME/REPO/ORIGIN/SHA/installedAt 归一化+skillHashes 值不锁归漂移锁专项）+preset update 固定拒绝语；_assert_golden 复用 helper；78 用例绿。proposal S43/S44
- 2782f5e feat(D-golden-1 doctor/verify golden 基线): 用户可见输出快照比对（devkit doctor-golden 对表，差距清单①第一步）——易变段归一化（HOME/REPO/SHA12），口径漂移即红，有意变更 UPDATE_GOLDEN=1 重录并在失败 diff 人工过目；无 key 确定性基线（key 探针行含易变指纹不入基线）；顺带修测试基建 bug：shutil.ignore_patterns 只匹配基名，'vod_mcp/runtime.json' 带斜杠模式永不命中致 clone 混入真源账本。proposal S42+design golden 节；76 用例绿
- 28c1f80 feat(D-release-1 一键发版体系+包内容门): release.sh 重写对齐 devkit release-please 语义——bump 从提交历史推导+版本落点表驱动 EXTRA_FILES+整行正则替换+全落点硬断言（根治静默 no-op）；新增 scripts/pack_verify.py 包内容门（pack --dry-run 必含/危险项断言）——首跑即实锤 0.1.12 曾含 runtime.json 凭据残留（已 deprecate，0.2.0 起文件级白名单结构性排除，npm 0.1.12 残留令牌仅对已销毁本地库有效）；package.json files 改文件级白名单+npm 分发补 plugins/ 随包（0.2.0 漏项致 npx codex 路径必挂，0.2.1 修复）；RELEASING.md 发版手册；proposal S41+decisions D-release-1；一键发版真机闭环 v0.2.0/v0.2.1（npx codex 原生插件安装复验通过）


## v0.2.3（2026-11-06）

- b3a9a19 S52/S53 场景用例独立成条（极端选择兜底/纠正闭环，从S50补口拆出）+design话术分层同步至S49-S53+D-option引用；router冗余前缀判断合并（in text[:20]为startswith超集，语义不变，既有回归锁覆盖两分支）
- d30c76a S50 补两口（用户确认）：只提追加句括号兜底不进并列选项+纠正闭环（不辩论/按纠正理解走/content仍原话逐字/禁新定性改写）；S51 泛化落档 D-option-executability-1（话术选项可执行性纪律：写选项前逐项问代码路径在哪）；7例回归锁（115绿）
- 54d08e3 S49-S51 追加反馈定性话术定稿：先定性再问+留纠正口子+禁空头承诺（无承载机制不得进话术选项）；双副本同步锁+frontmatter完整性回归（plugins副本漏同步太慢/吞frontmatter实锤修复）；proposal/design/test 三件套齐（113例绿）
- 5e926b1 skill(collect): 追加反馈定性话术——确认环节用户追加表达时先定性再问（定性是 agent 职责，用户只拍板范围），补模糊话术闭环
- a16f52d test+docs(router): M1 描述前置回归锁（57字符可见预算+长度上限+词表一致性三断言）——实锤补「太慢」缺失进四副本 description；design §五 多宿主对表与来源分级+M 用例承载表
- cd4f995 docs(router): 矩阵来源分级+官方文档校正——codex 预算参照改官方 8000 默认（5440=实测值）、钩子事件表官方依据；opencode 官方通道正名 prompt admission hook+description 1-1024 官方上限；dsh/hermes 行标注内部依据（可追溯性纪律）
- 087f005 docs(router): 矩阵修正——codex「无钩子面」事实错误更正（钩子面存在但输出截断+注入路径不一致方为不做理由，两行合一）；hermes 预算表述精确化（57字符索引预算由描述前置吸收）；opencode 补截断阈值依据
- 02f68f5 docs+test+refactor(router): 需求/设计文档正式化（docs/hermes-feedback-router/）+场景用例 H1-H4/R5-R8 承载映射+触发词表单一事实源重构（TRIGGER_WORDS 正则自动组装，补「很糟糕/太糟糕」变体——R5 长句用例暴露覆盖缺口实锤）+register 契约回归锁；修指令文案笔误
- 37af96f docs(router): 多宿主矩阵更新——opencode 钩子能力实锤结案（chat.message+合成消息双通路，前提高不成立）；codex 注入路径不一致风险补记（#37463/#33945）
- e7d2bf3 docs(router): 多宿主对表——opencode/codex/dsh 激活现状/截断暴露/强制评估可行性矩阵
- 4a4e095 docs(router): hermes-router.md 补入版本库（上笔提交遗漏 add，untracked 实锤——多会话并行时提交前必须核对文件清单）
- 5ca9960 feat(docs+gate): S45-S48 场景用例+D-desc-budget-1 截断预算门禁+安装器块扫描重构——①proposal 三·八新增 S45-S48（dsh 安装硬校验拒/放/幂等落盘/修复指引、description 500 字窗口与 Codex 5440 预算存活、归因口径单源）+S11 刷新安装器通道+决策表两行；design 五节 dsh target/六节预算门禁承载；②tests/test_desc_budget.py 4 用例：B1 先决条件<500 字符（dsh 最严窗口）/B2 总长≤1500/双载体（contract+dsh lib 组合串提取）/漂移锁禁旧宽容口径回流；③重构 _find_dsh_block 单一实现供 upsert/uninstall 共用（防双处扫描规则漂移），uninstall 净化；101 pytest+7 node 绿，pyflakes 净
- e8a21f9 feat(hook): D-hook-1 强制评估路由插件 vod-feedback-router——pre_llm_call 确定性意图路由（业界 forced-eval ~84% 模式），H1-H4 回归锁+installer 集成+decisions 记档
- 50f754c feat(installer+dsh): D-dsh-install-1 安装期硬校验落 dsh 壳——install --target dsh（--profile 必填先校验后 add、产品 meta 硬校验复用、幂等 upsert profile cordis.patch.yml config 段、dsh 缺失 exit2、写失败 exit1 带修复指引、manifest dshProfile+uninstall 摘除）；生效通道真机实证（profile patch config override，banner+桩提交链）；dsh 壳 description 归因漂移修复（旧宽容口径句→部署配置权威）；INSTALL/dsh README 口径更新；9 回归+golden 重录（仅 +dshProfile 键）；93 pytest+7 node 绿
- 8bdc225 fix(collect-skill): description 触发词前置（Hermes 索引仅前57字符可见，「体验差」原在截断边缘——业界截断静默失败教训）+禁复现排查模式句
- 7261ec0 docs(dsh): 归因注释对齐 D-attrib-A（实现本就只读配置绑定，模型传参不采信——天然免疫宿主名错归）
- 53579b0 feat(attribution): D-attrib-A 归因只由安装绑定决定——运行期显式传参仅绑定一致才采信（宿主名自报忽略+ignoredRuntimeProduct 留痕+productSource 可观测），6 回归锁覆盖拍板五场景；推翻 2026-11-03 宽容口径
- 8f8dca9 fix(collect-skill): 一次抱怨=一条声音红线——禁拆分禁改写变体（实锤：一次抱怨被宿主改写成两条入库建两 issue，引擎逐字幂等被绕过）
- cd4cccc fix(roster): 多宿主落点并集合并+HOME 隔离剪枝（实锤：按最近安装覆盖互相冲掉落点；fake-home 吞真实 HOME 历史落点）
- d67ad1b chore(plugin): sync+重烧 build-info
- a14b857 feat(doctor+instructions+e2e): 名册对账逐宿主核对技能副本+codex 目录补拷；initialize instructions 主动披露采集纪律；free-choice 行为回归脚本（B 熔断违规计数）——huaweicloud-devkit 三防线借鉴落地
- b3d6030 feat(echo): 提交回执强制原话回显（方案 A 拍板落地）——echo{requiresUserEcho,instruction,contents}+契约 schema/description+2 回归锁；decisions.md 记 D-echo-A-1（A 默认/B 宿主级熔断触发条件）
- ede20d7 fix(installer): manifest 重复 product 死键删除+golden 键序重录（值不变，product 移至绑定位置）
- 28c8f5f fix(installer): opencode 目标补拷原生技能到 ~/.config/opencode/skills/（opencode 原生 skill 机制实测识别，此前仅工具描述单通道）
- 0f4b9d2 feat(contract): vod_submit_voices 描述前置模糊反馈固定话术（MCP-only 宿主唯一约束源，opencode 交互三件套补齐）
- 5b97527 chore(plugin): sync vod_mcp+skills 自包含包+重烧 build-info（8bfb9f6）
- 8bfb9f6 fix(submit): 囤积回执缺 voiceIds 不得兜底计成功+引擎 rejected 透出（codex 谎报成功实锤修复）；采集技能模糊反馈固定话术（F3 观测定稿）
- bb312e3 test: golden status 重录版本号 0.2.1→0.2.2（v0.2.2 发版漏重录，pre-push 门禁被存量红挡）
- b111900 fix(D-consent-desc-1): 确认纪律前置进工具描述——opencode 把用户陈述反馈当同意直提单实锤（契约 description 立即调用话术与 confirm 纪律冲突，MCP-only 宿主不加载技能唯描述可依）+dsh 壳同步+回归锁


## v0.3.0（2026-11-08）

- 370ee37 fix(gate): secret_scan 测试正例改常量承载+行内豁免——门禁拦自测样例的自指问题终解（正例即豁免机制的真实用法自证）；新增 query token 模式用例
- 2600638 fix(gate): secret_scan 正例载体行内豁免——测试自身样例串被门禁拦推的 自指问题（gitleaks 同款 allow 标注机制首用即验证）
- 0bffc9b feat(gate): pre-push 第三检查=凭据泄漏+高危运行模式静态扫描（对标 huaweicloud-skills 市场采纳清单①）——零依赖 secret_scan.py（oauth2:token@host/query token/私钥块/AK-SK/Bearer 等模式+eval/exec/pickle/shell=True 高危面；行内 secret-scan:allow 豁免留痕；测试正例反例双锁抓出首版 URL token 模式顺序反写缺陷已修）；vod-feedback-collect description 补显式 Triggers 词表（中英 19 词，市场惯例=显式词表比散文召回稳，采纳清单②；SKILL 双副本+五宿主装机副本 md5 对齐）；pytest 147 绿+node 9 绿+scan OK
- 350b0a8 fix(skill): S73 拼接判定例——逐字=含语气词/标点，禁删'啊'补句号式改写（opencode 第二次实锤：S72 拼接生效但标点裁量漏网）；轮次衔接换行/空格分隔不新增标点+可逐字符还原判据；SKILL 双副本+四宿主副本刷齐；proposal S73+design+decisions 同构序列第四次记档；pytest 141 绿
- ef1ebbd docs(decisions): S72 附带发现闭环——负责人确认输入原文即'流程合理'，DB 记录准确，opencode 输入链路无缺陷，移交项不存在
- f4681bd fix(skill): S72 反截断红线——引导补充句整体=content 逐字上送禁摘片段（opencode 实锤：'操作不方便，流程合理'被截成'操作不方便'，reasoning 日志取证）；多轮分散表达按序拼接；SKILL 双副本+四宿主副本刷齐；proposal S72+design 承载+decisions 取证链；pytest 140 绿
- f3fde9e feat(followup): S71 问卷化追问 tripwire——话术载体结构词黑名单锁（自由生成四维追问清单实锤复盘：分叉示例+频率刻度+期望vs实际三红线全破）；数字编号不锁（规则层/话术层分层）；proposal S71 用例+design 承载+decisions 记档；pytest 139 绿
- d158bad chore(lint): test_followup 未使用变量清理（pre-push pyflakes 门禁）
- e223467 docs(followup): 二次微调落档 design 承载行+decisions 决策记录（跳过条件收窄依据/判定例先于行为验收/一句话口径三处诚实回退与 I22 对齐）；pytest 138 绿
- 6f16aad docs(followup): 判定块二次微调（负责人确认）——跳过条件收窄去"操作/期望"回溯歧义（新字段来源唯一=固定追问原样回答，引导补充自然出现的操作/期望留在 content）；"未回应/泛化抱怨"补可执行判定例；一句话口径改可测原文（payload 键+issue 段+来源注记三处诚实回退）；契约跳过句补不回溯边界（939/1500）；SKILL 判定块锁+边界锁双更新；四宿主副本刷齐；pytest 138 绿
- e7e8c48 docs(followup): S67-S70 追问触发判定块场景用例落档——proposal 判定块三层+四场景表（S67 已有实质回应不触发/S68 泛化+确认出现一次/S69 未回应+答没有键不存在/S70 防漂移锁）；契约 description 补跳过句（831→903/1500）；design S67-S70 承载行（dsh desc 无余量由宿主技能层承载的边界显式化）；+契约跳过句回归锁；pytest 137 绿
- 716371e feat(followup): SKILL 追问触发判定块三层显式化（触发前置/跳过条件/触发条件，负责人确认）——引导补充已有实质回应并入 content 则不再触发固定追问（reproSteps/expectedBehavior 不上送=诚实回退）；仅泛化抱怨或未回应且确认提交才原样带出至多一次；+SKILL 判定块文本回归锁（双副本逐字一致+四行为用例口径）；四宿主装机副本已刷齐；pytest 136 绿
- adee656 refactor(followup): 透传逻辑单源化 _followup_fields（submit/draft 双路径共用，禁双边漂移）+拒答词集补全（没有了/不方便说）+design §三 S63→S64-S66 落地承载映射表（含重复节头修复）+helper 单元回归锁；pytest 135 绿+node 9 绿
- 4b43427 feat(followup): D-followup-impl-2 复现/预期追问补充插件侧落地（S64-S66，负责人确认开工，A1 确认环节合并一问/A2 MCP+dsh 壳）——契约 submit+draft 双工具 voices[] 增可选 reproSteps/expectedBehavior（maxLength 2000）；固定问句逐字锁死+拒答词集技术兜底（_FOLLOWUP_DECLINES/DECLINES，模型不守话术键集合仍零漂移）；仅 trim 非空含键+超 2000 引擎同口径截断+content 原话禁污染；draft 路径随 payload 暂存 commit 原样上送；SKILL 双副本+四宿主装机副本 md5 对账齐；引擎零改动旧路径不变；pytest 134 绿+node 9 绿
- 44218db feat(two-phase): 两段式提交插件本地极简形态（D-token-approval-2 解冻，负责人拍板方案 2）——vod_draft_voices（暂存+一次性令牌+contents 原话回显）+vod_commit_voices（令牌校验/单次消费/载荷 sha 防调包，内部复用 submit 既有链零新增语义）；draft cap10 环形+TTL600s 惰性清除；账本 stage=draft/committed+draftId 关联（验收③绕过两段式可检测）；SKILL 话术改两步流程（双副本 md5 同步）；128 pytest+8 node 绿
- 31908e0 decisions: D-token-approval-2 token 化暂缓（负责人拍板 A）——触发条件=codex 真实消费需求；复杂度收益失衡裁剪（引擎写表面不值），恢复门禁口径不变（暂缓=codex 保持只读）
- fec386e docs+test：S63 复现步骤 AI 追问前置规范落档（业界对表 D-followup-design-1 四约束：可选增强/话术固定化/数据分层/诚实回退；当期不落话术——引擎无 supplement 承载 S51）+S63 tripwire 锁（采集话术禁追问承诺，立项随承载更新）
- 7a9eb08 decisions: D-followup-design-1 复现步骤 AI 追问前置规范（业界对表，负责人确认）——四条硬约束（可选增强/话术固定化/数据分层/诚实回退），当期不落话术（无承载 S51），立项前置
- 0ab66ce decisions: B 方案（bundle patch 接管）可行性修正落档——机制确定（bundles 清单管理），调研目标收敛为静态值确认+整行 config 完整性；A 自愈已落（e6a7d32）
- e6a7d32 feat(doctor): dsh patch 块自愈（A 止血，用户拍板）——doctor 检测 vod 块缺失/打平后按 manifest product/apiBase 重建嵌套块；manifest 补记 apiBase；status 输出归一化动态端口（golden 稳定性）；+三态自愈回归锁（123 绿）
- 6afeb4e decisions: D-codex-circuit-breaker-1 补深审收口记录（P0-2/P0-3/P1-4/P1-5/P2 修复清单）
- 23a7bb1 fix(installer+packs): 深审四项收口——P0-2 packs 命名漂移（PRESETS full 对齐 ALL_PACKS+kb→knowledge 别名归一，安装口与运行口单源）；P0-3 uninstall 破坏性路径（codex mcpConfig 改指插件 .mcp.json/None+config.toml 永不删+codex plugin remove best-effort+doctor None 守卫）；P1-4 ack 解除后置到安装成功（失败安装不解熔断）；P1-5 codex .mcp.json env 对齐本次 packs；P2 strip 精确表头+AGENTS END 缺失拒写盘；+5 回归锁（122 绿）
- 4309a41 docs：S60-S62 codex 熔断与恢复门禁场景用例落档（熔断触发/双层门禁安装+运行期/显式解除语义与审计）+design 承载映射（D-codex-circuit-breaker-1）；118 绿
- 525826f feat(breaker): codex 熔断恢复门禁代码化（D-codex-circuit-breaker-1 收口）——①install 门禁：标记在+collect 拒装 exit2 ②--ack-suspension=显式解除（删标记+审计日志，语义与实现一致）③运行期门禁：serve enabled_packs 同查标记强制降级只读（堵 VOD_PACKS 绕过）④probe/packs 测试 HOME 隔离（真实标记不可被测试触碰）；118 绿
- f30d0d8 decisions: D-codex-circuit-breaker-1 落档——熔断执行记录+token 化立项表述纠偏（最强摩擦+审计链，非人类确认硬保证）+恢复门禁（token 化上线前禁恢复采集）+验收标准改写
- 3a4a519 docs：S58（dsh patch 块 name 绑定+嵌套铁律，入口消失事故）/S59（回执话术=行为实况，S51 回执面应用）落档 proposal+design；116 pytest+8 node 绿
- 76a3c9d fix(UI): 回执话术=行为实况（S51，用户抓出）——删「审核后将以 issue 形式跟进」空头承诺（匿名直建无人工审核闸，issue 链接由 pollForReceipt 真实建成后补出）；+回执实况回归锁（禁审核跟进句/REJECTED 须有引擎状态承载）
- 87cc0d0 fix(installer): dsh patch 块模板补 name 绑定行——重装幂等替换吞掉 name=client 半静默失激活（入口消失真机实锤：工具壳正常而按钮不在）；+name 回归锁（116 绿）
- 43c57ee docs+test：S54-S57 场景用例落档（暂存恢复补提示/禁拉伸/legacy 清退/widget E_AUTH 兜底）+design 话术分层承载节；ux-sync 回归锁扩容（resize none/恢复话术要素/用户面 key 明文禁令），115 pytest+8 node 绿
- 856b1db legacy 共用 key 用户面清退（负责人拍板'不合理逻辑去掉'）：INSTALL 删明文 legacy key 警告句（公开文档泄露 key 值+教唆反效果）；nightly E2E 切匿名令牌主路径（legacy 属 GTD 兼容收尾不进健康检查）+清 scene 残留字段；测试归因绑定显式桩定（曾依赖仓内 runtime 偶发绑定假绿，D-attrib-A 无绑定分支新增回归锁）；115 绿
- 592999e UI：弹窗输入框禁拉伸（resize none，用户反馈拉角顶破布局）——随后台重试补提示一版
- f90e130 UX 修复：后台重试成功不再静默——暂存反馈自动重试成功后落旗标，下次打开弹窗补提示（逐条原话回显，voice-id 不出用户面 F2；措辞「已自动重试成功」说清=完成用户此前点提交的指令非绕过确认；产品名不带——用户不感知归因拍板）
- a3cdd6d dsh 壳 UX 定稿同步（web widget 拍板漏同步各壳漂移实锤）：提示语去括号后缀与受理引导句、撤 maxlength 计数器（硬帽保留）、撤「我的反馈」入口（账本写入保留）；+ux-sync 回归锁（src+构建产物双级）


## v0.3.1（2026-11-09）

- 141dce4 fix(auth): probe_key 匿名令牌 401 报 expired-anonymous 而非 rejected——runtime 残留过期匿名令牌曾被误读为正式 key 失效（本机实锤：指纹 712c0ae4 实为 anonymous 档过期令牌）；显式 key 被拒仍 rejected（fail fast 口径不变），note 指明下次提交自动重领；+回归锁（匿名档 expired-anonymous+重领提示、显式档 rejected 保持）
- 84cc6f1 fix(installer+dsh): 四宿主全链模拟两项实锤修复——①重装吃掉配置：dsh plugin add 模板含字面量 [] 顶层行，幂等追加块后 = 非法 YAML 整 profile 启动崩溃（upsert 追加路径清除空数组占位+回归锁）；②headless 审批死锁：dsh 原生 ask 门禁无通道永久阻断写工具（requires approval, but no approval channel 实锤，此前靠 11-06 手工配置 confirmWrites:false 残留掩盖）——installer 显式写 confirmWrites:false（同意由 SKILL 话术层承担，web 端按 profile 覆盖回 true）；dsh 真机重装→提交成功复验 ✅
- 9b87594 feat(followup-status): 插件侧 followupStatus 上报对接（引擎 V55-V57 契约增量，proposal S74-S76）——单源 _followup_fields 扩展三态白名单归一（strip+lower，白名单外/缺失省键，submit/draft 双路径共用禁双边漂移；commit 随 draft 暂存冻结防调包语义不变）；契约 draft/submit 双工具 items 增枚举字段（工具 description 零增量，预算门禁不回退）；dsh 壳透传同口径扩展（desc 1495/1500 无预算不宣讲，SKILL 宿主技能层承载）；SKILL 判定块第 5 条三态映射话术锁（七副本 md5 对齐）；+5 回归锁；pytest 153 绿+node 9 绿
- e40fafe fix(auth): 旧版残留凭据检测与自愈提示（评审拍板项，优先于公告）——codex 0.2.3 残留 legacy key 挡匿名链四宿主实测实锤；三处提交失败路径错误消息追加可操作自愈指引（_legacy_key_hint：当前版本+npx 重装命令+匿名档出口，不发公告靠用户撞）；vod_auth_status 显式 key 在位即挂 legacyKeyHint 检测位（不等提交撞 401 才发现）；不静默删 key 不静默重装（提示用户确认更新口径）；+回归锁（提示含版本与重装命令+四处调用点在位）；pytest 148 绿
- 1ac4b48 fix(release): GitCode 推送失败改硬失败 exit 1——本次发版 push 被 pre-push 拦后脚本吞错仍误报'发版完成'的实锤修复
- 87ac1ee test: golden status 版本快照随 v0.3.0 发版重录——release.sh 推送失败被 '|| echo 跳过' 吞掉的实锤（本次 push 被 pre-push 拦后仍误报发版完成，脚本待修：push 失败应 exit 1）


## v0.4.0（2026-11-09）

- 3c54786 feat(two-phase): D-resume-commit-1 断回合续提交+确认收口话术锁——实锤：agent draft 后收工，用户两次说提交仍无下文（approvalToken 只存于 draft 响应文本，回合断即丢失）。①draft 将 token 随草稿落盘（runtime 0600，与 java_key 同级；token 威胁模型=防载荷改写非同意凭证，落盘不放大）；commit 允许省略 token/sha 由本地未过期草稿恢复，显式传错仍拒（语义不放宽）；契约 required 收窄为 draftId。②SKILL 真源加话术锁：用户确认后当回合必须 commit、不成必须明告未提交（真源生成+sync 同步，禁自由裁量）。+4 回归锁（恢复成功/错 sha 仍拒/过期拒/token 落盘+0600）；pytest 159 绿+node 9 绿
- ca84c3a test: conftest autouse runtime 隔离——test_followup 等 _submit 用例桩了 _http 未重定向 _runtime_path，账本追加写穿仓内真实 runtime.json（本机 200 条账本被测试数据灌满实锤）；autouse 重定向 tmp，用例内显式 setattr 仍可覆盖；pytest 155 绿
- f35cd0e test: golden status 版本快照随 v0.3.1 重录（仅 version 字段，diff 已过目）


## v0.4.1（2026-11-09）

- a0cf5c2 chore(dsh-release): dsh-vod-devkit 0.2.0——首装 nonce 同步+issue_sync 轮询拆除随包（tgz 本地重打包不入 git，嵌入方经 dsh plugin add <tgz> 或重装升级）
- 4e9a015 fix(nonce-sync): D-dev-nonce-sync-1 首装 nonce 内存态同步——真机实锤：全新安装首次提交必失败冒给用户（_install_nonce 首次生成只落盘不回写 _RT，同进程每次新 nonce→领令牌与提交设备不同→绑定校验 401，重试仍新 nonce 再 401；二次提交才成功）；修复=生成后同步 _RT[install_nonce]，领令牌/提交/重试同设备 401→领令牌→重试全程无感；存量安装不受影响；回归锁 tests/test_install_nonce_sync.py；pytest 163 绿（162+1）+ 本地 e2e 修复后干净沙箱首提一次成功；decisions.md D-dev-nonce-sync-1
- b8eed60 feat(dsh-ui)+docs: D-inbox-direct-ui-1 issue_sync 轮询拆除——引擎单表收口后回执无 issue_sync 节，原 U-S2 轮询（GET ?limit=50 找 voiceId）永远空转静默失效；净删 pollIssueSync/pollForReceipt 及调用点，提交成功（201）即终态提示「已收录，产品团队会看到」（对齐 D-inbox-DIRECT 不建 issue 拍板）；提交链本体（POST+断线自动重提）保留不动；lib 随构建重出；docs：dsh-ui-collect §六/§七/U-S 用例表同步、decisions.md D-inbox-direct-ui-1 决策条目；回归锁 +1（no-issue-sync-poll.test.mjs：src/lib 双侧禁 issue_sync 与已建成 issue 话术+提交链本体保留锁）；dsh node --test 10/10 绿
- b0f121c docs(quota): D-quota-raise-1 匿名档配额提额+引擎侧可配置化文档化——面向用户数值口径同步（5000/日500），proposal 信任模型表/decisions 决策条目/design 数值归属节（插件零配额数值，429 文案引擎透传）
- fa9c92b refactor(two-phase)+docs: D-resume-commit-1 文档化+场景用例 S83-S86+草稿库读写单源化——docs: decisions.md 决策条目/design.md 承载补充（分层治理口径）/proposal.md 场景用例清单（S83 全链回执逐字、S84 断回合恢复、S85 过期重开链、S86 消费后不可复活）；refactor: _drafts_load() 单源化 draft/commit 草稿库读写（现读+TTL 惰性清除，禁双边漂移）；+3 场景回归锁；pytest 162 绿+node 9 绿
- 9b5e6ec test: golden status 版本快照随 v0.4.0 重录（仅 version 字段，diff 已过目）


## v0.4.2（2026-11-10）

- 8d59aa7 chore(ci): 双副本同步门禁三处落地——CI diff 步骤+release.sh 双门禁+npm 包自证
- 5a8cb00 fix(tools): _warn_if_cloned 可测化——uptime 源注入 + except Exception:pass 收窄
- a906e82 refactor(tools): 复杂度收敛——submit_voices 四段拆分(207→126 行)+cmd_install 技能/manifest 段抽出+policy 逐规则重读盘收口
- fdb2f43 docs(pending): D-pending-1 需求/设计文档四件套收尾——S87-S90 场景用例+设计承载补充
- 03cc4b8 fix(pending): pyflakes f-string 无占位符
- 4532dee feat(pending): D-pending-1 补强——originalLines 权威拼接，机械剥除模型拼接改字
- e7660c0 chore(sync): plugins/ 副本同步 D-pending-1 skill 段（双副本同步锁）
- 14027c4 feat(pending): D-pending-1 无通道场景 pending 反馈队列——落盘+flush+echo 前移（方案 A 四条细节定稿）
- 53fc675 chore(dsh-release): dsh-vod-devkit 0.2.1——ReceiptGuard 随包（tgz 本地重打包不入 git，dsh-vod-devkit-0.2.1.tgz）
- baa60b6 feat(scripts): D-behavior-grade-1 e2e_behavior 确认强度分级+分桶+熔断配置化
- fb62b74 feat(dsh): D-rguard-1 ReceiptGuard 提交侧原文比对闸——会话日志 user 轮原文为真源
- 3dfdb1c chore(release): golden 随 v0.4.1 重录（仅版本值漂移，人工过目合规）

