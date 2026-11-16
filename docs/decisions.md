# 决策台账（拍板→落档→验证闭环载体）

> 纪律：每条拍板一行；完成（代码+文档+测试三落）才勾；评审时扫未勾项。
> 病根 G2 的修复机制：决策存在对话流里必丢，必须落文件。

## 已闭环
- [x] 传输协议守卫（2026-11-03）：http 仅限本机回环，公网 http 拒绝（-32014，U38）——Bearer 不得明文过公网；https 全链路已实测（taskId=419/420）
- [x] 提交记录查询（2026-11-03）：层级①本地账本+vod_list_submitted 已实现（U35-U37，25 用例）；层级②引擎端点入 VOD-VOI；层级③维持 P2
- [x] 身份界定对表（2026-11-03）：归属/授权分离定稿；外部分析三处不采纳（HMAC/多租户/Gateway）；内容边界 ≤2000 落码（U32）；签名回执记 P2 前置
- [x] 动态元数据客户端（2026-11-03）：meta 拉取+24h 缓存+快照兜底+stale 标记；归因白名单改走 meta；S11-S13/U29-U31 落档
- [x] 方案 A（2026-11-03）：插件收敛为纯采集——workflow 三工具+kb_search 删除（git 留档），运营归 vod-system 前端；知识技能留 knowledge pack；P1 任务级 token 取消；单上游单写口
- [x] key 交付定稿（2026-11-03）：零字段自动令牌=入门（A/B/C 三案比对见 proposal 三·四，B 否决为入门因把门槛放在价值之前）；vod_auth_status+令牌自动获取+引导已实现（24 用例）

- [x] 插件形态=devkit 同构完整形态（installer/MCP/skills/packs/policy）
- [x] 运行形态=随 agent 进程拉起走内网 API
- [x] 写权限=confirm+条数上限
- [x] 溯源与宿主感知（manifest/verify/vod_devkit_info/clientInfo）
- [x] 独立成仓：直接于新仓开发（暂住 xiaowu2119，转移触发=团队协作或对外上架启动）
- [x] 核心语言=Python（判定与推翻条件见 design 三）
- [x] 契约单一事实源=contract/tools.schema.json
- [x] 反馈采集两项 A：独立囤积端点（引擎侧 VOD-VOI）+ 逐次 confirm
- [x] VOD-VOI 落点修正：Java /external/voices 复用 saveCollectRecord
- [x] 外部/内部分层：外部=反馈采集者（preset collect），分析发起=内部（preset full）
- [x] 审计修复 E1/E2（认证头+双后端，协议级测试锁定）、E4（护栏作用域）、G1（安装器技能全量+双 key 配置+preset）

## 运维注意：双远端历史分叉（2026-11-03）

GitHub 直连超时期间用 Git Data API 推送产生了内容等价但 SHA 不同的
提交（GitCode=本地 git 历史，GitHub=API 拼装历史）。当前两远端内容
一致（GitCode 454af49 ≙ GitHub 832ff5c）。后续处理：github.com 直连
恢复时一次性 `git push github main --force`（内容一致，仅对齐历史）；
持续超时则继续 /tmp/apipush2.py 模式（按 HEAD~1..HEAD 文件集推送）。

- [x] 替代路线四件（2026-11-03）：GitHub Actions CI 首跑 success（镜像仓跑服务端门禁）；OpenCode 真机 connected（schema 修正：command=数组+enabled 必填+既有配置无损合并）；Codex CLI 真机识别（TOML env 子表）；nightly E2E 本机 cron（每日 03:30，首跑 taskId=420 通）；README.en.md 双语
- [ ] npm registry 发布（锦上添花）：npx github:yangaiwu/vod-devkit 为现行替代（npx 原生支持 git 装包）；direct-capable token 到手后补 registry 版
- [x] GitHub 镜像：已推送完成（main+v0.1.0 tag，head a8c8372 验证）+plugin.json 市场清单（WorkBuddy/CodeBuddy marketplace add yangaiwu/vod-devkit 即接入）
- [x] 宿主适配层：hermes（实测）/opencode（JSON 合并）/codex（TOML env 子表）+ auto 0/1/N 探测——真机回归待首批用户
- [x] 发版自动化 scripts/release.sh（质量门→三处版本同步→CHANGELOG 生成→tag→双远端推送）

- [ ] **公开上架时机（2026-11-03 拍板）**：等 VOD key 签发制落地后再公开；
      业务窗口急则白名单灰度（邀请制，不算完全公开，不阻塞验证）
- [ ] **遥测（2026-11-03 拍板：维持不做）**：未来若做，opt-in 默认关+
      明确告知+最小字段，不采集敏感内容；当前链条不依赖它
      **重议触发器（2026-11-15 补，负责人要求）**：出现"只能靠用户上报才能定位"的
      线上问题（装机侧工具面/版本漂移类），且 install-manifest 对账无法回答时才重开；
      否则视为单向门——不加触发器，未来加遥测会把今天的承诺变成负债

- [ ] VOD-KBQ（R0 网关+KB 查询端点）：文档已评审待定 → 代码增量未写（引擎侧）
- [ ] VOD-VOI（Java /external/voices）：文档已出 → E3 查重语义待实测修正 → 代码未写
- [ ] 多 key 防线（t_vod_api_keys/限流/吊销）：设计在 VOD-VOI 文档 → 未实现
- [x] GitCode CI 门禁：.gitcode/workflows/ci.yml 已提交（push/PR 触发 pytest），线上首跑待观察
- [x] Hermes 真实 MCP 接入：`hermes mcp add`（config.yaml mcp_servers）+ `hermes mcp test` 实测 6 工具全通过。三坑已修：①宿主过滤 env（PYTHONPATH 不透传）→server.py 自举 sys.path；②-m 在宿主 cwd 找不到包→args 用脚本绝对路径；③add 是交互式→input y 应答
- [x] vendored 规则改技能目录结构 skills/<name>/SKILL.md（vendor_rules.py+仓内迁移）
- [ ] U1-U20 真引擎端到端（等引擎侧上线）
- [ ] VodTeam 仓转移（等管理员权限，不阻塞）

## dsh 薄壳深审裁处（2026-11-03 深夜，外部评审 8 项）

- [x] **D-dsh-1（高）传输守卫已落码**：`transportError()`（工具入口拦截 + http() 兜底
      throw），非 https 且非 localhost/127.0.0.1/::1 → 拒绝 -32014，与 vod_mcp
      tools.py 同语义同文案。S16「双形态一致」自此真正兑现。
- [x] **D-dsh-2（中）voiceId 分层语义记档（非分叉）**：实测核对——Python 插件侧
      本就是调用级 nonce（R1 声量保真修正，回归锁 test_voice_volume_preserved
      _across_calls），dsh 与 Python **同构**；「确定性」是**引擎端** VOD-VOI E3
      口径且 /external/voices 忽略 body.voiceId、服务端自算确定性键查重（V9）。
      分层：客户端键=本地对账主键+同调用重试幂等；引擎键=跨请求查重。两层各司
      其职，互不冲突。旧链 submit 消费客户端键，nonce 恰好保护「重试不烧 LLM、
      重放保留声量」。design.md S16 措辞按此修正。
- [x] **D-dsh-3（中）PRODUCT_MAP 硬编码记档**：dsh 形态不拉 /external/meta
      （meta 消费仅 Python 形态有），引擎 VodExternalProducts 变更需手工同步
      PRODUCT_MAP——已在代码注释标注 M2/M3 不适用 dsh。引擎 !152 合入后需把
      AISHELL/nameAliases 补进此表（一次 2 行改动）。
- [x] **D-dsh-4（中）囤积端点切换计划已标注**：SUBMIT_PATH 定义处 TODO——引擎
      /external/voices 上线时改一行 + body 字段核对（批量/逐条回执/Duplicate
      字符串匹配自然消亡）。
- [x] **D-dsh-5..8（低）已知取舍记档不修**：confirmWrites 配置级开关弱于逐调用
      confirm（dsh 宿主审批通道语义，管理员责任边界）；账本读改写无锁（影响=
      对账缺行，不做分布式锁）；timeoutSec 可配无上界（运维自律）；401 重取令牌
      仅首条（中途令牌失效由下一调用兜底）。均为对账/体验面，无安全洞。

## 归因口径变更：「宿主即产品」不设白名单（2026-11-03 深夜拍板，用户原话"都不限制，如果是hermes就是hermes"）

- [x] **决策**：归因锚点=用户当前工具。显式传参 > 安装绑定（install --product
      缺省改为宿主名：装 hermes 归 hermes/dsh 归 DSH）> 无归因（body 不带
      product，引擎落 UNKNOWN 档 V19）。**-32013 本地拦截与白名单校验废除**
      （Product attribution error 改为"放行+引擎宽松归一"）。
- [x] **插件侧已落**（26 用例绿+node 真调验证）：tools.py 归因改两级+None；
      install 缺省绑宿主名；contract/tools.schema.json 去掉 product enum；
      dsh 缺省 DSH+passthrough。
- [x] **引擎侧已落**（feat/kb-query-auth）：VodExternalProducts.normalizeLoose
      （折叠+别名收编+未知原样收+64 截断）供 /external/voices；老链
      /external/voice/submit 保持 normalizeOrThrow 严格（legacy GTD 兼容，
      禁新接入）——两口径勿混用。
- 理由：宿主识别是可信来源（插件装在谁家=用户在用谁），错误归因场景从
  "静默猜默认"变成"锚定当前工具"，白名单反而制造 AIShell 式拒收。
- 脏值防线：引擎 64 字符截断+UNKNOWN 档人工归因解析兜底，运营侧治理。

## D-market-1 dsh 社区目录上架绑定 npm 发布（2026-11-04）
- 拍板：`dsh-plugin` topic 不提前打——根仓 package.json 是 MCP 安装引导器
  （非 dsh 插件包），dsh 插件本体在 dsh/ 子目录；目录按 topic 自动发现+
  人工审核收录，根仓打 topic 会被误收录/装出引导器。dsh 插件包
  （dsh-vod-devkit，dsh.bundle=cordis.patch.yml 已声明）发布 npm 后，
  同批打 topic+官网 Submit（dsh-plugin.org/zh/submit），目录一键安装即通。
- 依据（源码实读 dsh-plugin-hub 2.3.3）：收录=GitHub 仓+dsh-plugin topic；
  一键安装仅限已发布 npm 包；isDshPlugin 判定=包 package.json 声明
  dsh.bundle/dsh.profile 或进 profile bundles 清单。
- WorkBuddy 线不受此约束：GitHub 仓即市场，plugin.json 就绪即挂，与 npm
  无关（README 双语已写安装命令）。

## D-dsh-ui-1 dsh 笑脸采集 UI 通道（2026-11-04 拍板 A1-A4）
- 形态：dsh web 输入框笑脸按钮→弹窗表单→/external/voices 囤积→引擎
  VOD-ISYNC 建 issue（VodTeam/VOD-Project，bot 代提交 on_behalf_of 昵称）。
  已拍板：匿名档过运营队列实名自动、单仓、走 !152 囵积端点。
- UI 扩展机制实证存在（dsh-client-ui-slots register API+浏览器插件
  client.js 下发）；输入区槽位名留 T-VER-1 真机枚举（无槽位降级=
  斜杠命令入口同表单）。dsh 账号体系存在性未证实→身份源三层
  （会话 API>凭据指纹>自愿留名），表单知情同意默认勾选。
- UI 通道 voiceId=确定性 f(identity_hash, content)（用户级维度，与 MCP
  通道调用级 nonce 不同是有意的：同用户重试幂等+跨用户声量不吞）；
  三层全空取安装指纹。设计文档 docs/dsh-ui-collect.md；引擎侧
  VOD-Project feat/issue-sync f312bab（VOD-ISYNC，I1-I12）。

## D-align-1（2026-11-04）以 VOD-Project 采集标准为准（用户拍板）
- 身份三轴分离：采集链路（collect_source 列，链路/注册表赋予）/用户
  会话平台（内容"声音来源"节，运行时检测）/产品归因（product 列，
  三层推断）。渠道不在三轴外自造机制
- 分类三层：采集层=渠道原生枚举（面向人的表单=云声三分类：功能建议/
  用户体验/产品缺陷）/分析层=n01 六类 LLM 重判/消费层=n09 四档投影。
  3→6 映射由 n01 重判承担，非显式映射表
- 曾被用户纠偏两次：①"灰度"措辞（首发即正式，无灰度期）②UI 显示
  六类分类（未做映射就自设口径——云声表单三分类才是人看的标准）
- 随包编译固定常量+引擎注册表准入=双闸（渠道值既非用户输入也非配置）

## D-product-1（2026-11-04）产品归因=加载/安装时受信配置（用户拍板）
- 身份三轴的赋值时机全部收敛到受信动作：渠道=链路（引擎入库侧固定
  vod-agent）；产品=加载必配（UI 注入/安装绑定）；用户会话平台=运行期
  agent 会话上下文。运行期自报只覆盖显式传参这一处（优先级最高、可越层）
- UI 无注入不激活（fail fast）替代原"不注入=中性文案+UNKNOWN"设计
  （e99c347）——归因错误比没数据更糟，配置错误第一分钟暴露给嵌入方

## D-product-2（2026-11-04）产品归因安装必配统一到 MCP（与 UI 同口径）
- install --product 必填（fail fast）：缺省宿主名在生态部署是错归陷阱
  （高校AI开发者平台 agent 底座=hermes，不填全归 hermes）。宿主名仍是
  合法值（自反馈场景显式 --product hermes），但不做静默默认
- 至此两壳产品逻辑一致：MCP 安装必填 / UI 加载必配（__VOD_DSH_UI_PRODUCT__
  注入），运行期显式传参仍可覆盖
- 取值权威名单=GET /external/products（t_vod_product 运营预置）

## D-switch-1（2026-11-04）MCP 切囤积端点完成（V16 落地）
- 主路径=囤积批式（voices[]+tags+product，voiceId 引擎算回执下发）；
  404（引擎未部署）自动回落老链（path=legacy-fallback），回落 source
  带 per-install nonce（跨用户吞声量前置修复）
- 三回归锁升级新契约：协议锁（囤积头/路径/载荷+回落两场景）、R1
  声量锁移至回落路径、title 锁改囤积链 voices[].title 承载
## D-inbox-1（2026-11-05）囤积区独立表 + 收发分离 + 匿名提交入口闸（用户拍板）
- agent 提交改入新表 t_vod_agent_inbox，不再写 t_vod_source_data（存量表是
  V1.1 固化的 JPA 建表，四条存量链共用底座——我们的数据从别人表里收回来）。
  主表只收正式行（存量链+回流行），分析零过滤补丁、零重复计数
- 回流澄清为特性：agent 声音→issue→建议平台/VOC 回流进各云产品正式链路。
  真实问题=ext_ 囤积行与回流正式行重复计数；回流行归属不可判定（新 voice_id、
  key_id/tier 全 NULL），内容指纹=可漂移旁证违反铁律——解法=回流行只进主表、
  囤积行不进主表，识别问题结构性消失（R2 加 agent 过滤方案作废）
- 收发分离：收（inbox 囤积）无条件做；发（建 issue）才设闸。入库即登记
  （t_vod_issue_sync 与 inbox 同源），backfill 补漏任务净删
- 匿名提交入口闸 vod.external.anonymous-submit-enabled（默认 true）：
  false=Filter 层拒收匿名提交（结构化引导正式 key），连 inbox 都不进，
  formal/host 不受影响。管入口，与 issue-sync.enabled（管出口）互不牵连
- 匿名 PENDING 审核队列+/issue-sync/admin 净删（人工审垃圾=负资产）；匿名
  分发行为（是否建单/独立日天花板）为独立未拍板项，不在本批
- 代价如实：分析只见回流行（回流失败的声音 inbox 可补录）；ext_↔正式行关联
  靠 t_vod_issue_sync.issue_number 对账（平台签发主键），不做内容指纹匹配
- 全文落 VOD-Project docs/vod-voices-api/design.md 第十节（本决策的引擎侧真源）

- 引擎 !152 已合入 dev（ebdc6032）+评审线三轮追加（S1-S3 anchor/
  A2 设备绑定/tier-first R2/verbatim desc，V119-V120 幂等迁移）——
  插件零调整（401 自愈链原生兼容 A2；契约变化与既有删除同向）

## D-key-guard-1（2026-11-05）key 安全三件：401 fail fast + S1 式写后验 + 有效性探针（用户拍板落地）
- 背景：「安装注入 appkey、没 key 走匿名」确认合理（与现状 install env 注入口径一致），
  但深检发现显式 key 被引擎 401 拒时会静默降级匿名档（tools.py 原 `not JAVA_KEY or
  ex.code == -32012` 共用分支，取匿名令牌覆盖 runtime.json）——注入锚定承诺变假，
  归因错位比报错更糟（AIShell 错归同病根）
- ① 401 分流：新增 _explicit_key()（env 显式注入为权威 + token_tier != anonymous）。
  显式 key 被拒 → fail fast（-32012，报错带指纹+处置指引，不取令牌不覆盖配置）；
  匿名令牌失效 → 维持自动重领链（30 天过期自愈）。两分支互斥，回归锁双测
- ② S1 式写后验（借 huaweicloud-devkit ensurePrivateMode 模式）：_save_runtime 写后
  chmod 0600 + stat 回验效果（非动作），权限失效告警进 /tmp/vod_mcp_server.log 不阻断
  主链；_runtime_path 抽出便于测试注入
- ③ 有效性探针 probe_key()：带 key GET /external/meta（复用既有只读端点，零引擎新增，
  devkit auth init 真调 IAM 的廉价版）。三态：200=verified / 401=rejected /
  其他=unreachable（网络问题不是 key 问题，报"未验证"不报"无效"）。auth_status 配
  keyCheck 字段；doctor 配 key 后探针，无效 FAIL、不可达 warn（离线 doctor 必须可用）
- 账本脱敏复查结论（零改动）：账本只存 voiceId/taskId/title(反馈前 40 字)/product/at，
  无凭据字段；key 明文暴露面=签发响应+runtime.json 两处（原有结论不变），新增
  auth_status 全输出面明文 grep 锁
- 刻意不做：S1 式静态加密（AES-GCM）——vod key 是低价值把手（可吊销/限额/UA 绑定），
  devkit 加密库面向 AK/SK 高价值长期凭据；宿主 key 正式落地时再评估
- 验证：45 用例全绿（新增 5）；真机探针 verified（key 133e3715）/ 假 key rejected /
  doctor key 行通

## D-key-guard-2（2026-11-05）分发红线：对外产品形态禁止预置 appkey（用户拍板）
- 背景：产品部门将把插件集成进其 agent 随产品对外分发。若预置 key（env/配置/install
  参数），key 随包落到每个客户机——分发面=泄露面；同 key 全员共用=归因全毁/配额
  全局一份/吊销即全员停服；正式 key 绕过匿名天花板=不限量通道被复制 N 份
- **裁决：key 落在哪台机器，哪台机器就是信任边界。随产品分发=信任边界变成所有客户
  =不可接受。对外分发的插件产物禁止预置任何 key**（env VOD_JAVA_API_KEY、配置文件、
  install 注入参数均不允许）；发版检查产物不含 VOD_JAVA_API_KEY 字面值
- 三档信任模型（对外口径，scheme-overview 同步）：
  ①终端用户=匿名令牌（每机自动领取，UA 绑定+30 天/500 条+per-install 命名空间，
  归因靠 install --product 不靠 key）——唯一对外分发形态
  ②宿主平台=host key 只配宿主服务端/运维管控面，插件经代理访问 VOD，key 不落客户机
  ③VOD 运营=formal key 自用
- 升级漏斗：匿名量到天花板→引导升级→升级发生在服务端（运营签发/宿主对接），客户机无感；
  散户停在匿名档是设计而非缺陷——要身份锚定的主体是宿主不是散户
- appkey 通道处置：代码保留 dormant（运营/宿主服务端注入仍是合法场景，D-key-guard-1
  三件护栏恰为防误用）；使用口径收窄为「key 注入只允许发生在运营/宿主运维自己的机器」，
  任何"装完即有 key"的分发形态=违规
- 隐患澄清（本轮结论）：隐患根源=「预置随分发」的使用纪律，非 key 代码本身——
  fail fast/写后验/探针全是往误用更难方向加的护栏，拆除即回退到静默降级旧缺陷

## D-inbox-2（2026-11-05）匿名分发：产品维度日天花板（用户拍板）
- 匿名可建 issue：vod.issue-sync.anonymous-distribution 开（默认 false）→
  匿名行 APPROVED 直建；关=PENDING 冻结（默认态）。legacy 永远 PENDING
- 天花板按产品维度各 500/天（anonymous-daily-cap 可配）：产品间互不挤占，
  单产品打爆不拖累其他产品；尝试数计额（失败重试也占——防绕过上限外呼）
- 触顶行为：匿名行留 APPROVED 当天跳过（次日自动恢复），不标 FAILED，
  formal 不受牵连；计数=countAnonymousCreatedToday（status<>PENDING 当日行）
- 双层闸独立：入库层（500/30天+日50 管收）与分发层（产品 500/天 管发）
- 引擎真源=VOD-Project docs/vod-voices-api/{proposal V44, design §十}；
  回归 4 例+legacy 锁

## D-device-anchor-1（2026-11-05）匿名令牌身份锚点设备化（两仓联动，引擎 docs/vod-device-anchor）
- 根因定案：匿名锚点 sha256(ip|ua) 在网络层找身份——preset 分发下同产品 UA 相同
  +企业 NAT IP 相同=全公司收敛一个锚点，签发 5/天堵死装机。调数值=永久拆防线，
  根本修法=锚点迁设备层
- 引擎：token/提交请求携带 X-Vod-Device-Id（客户端首启自生成随机 hex=install_nonce，
  零字段不破/可重置/非硬件标识符——合规口径引 Anthropic deviceMid 同构）；锚点
  sha256("dev:"+id)，每设备独立 5/天签发+50/500 配额（防线全量复用零改动）；IP 层
  降兜底（device 路径 60/h，legacy 维持 5/h）；A2 绑定升级=ua_hash 列存 sha256(deviceId)
  （复用列零 DDL）；存量令牌 UA 路径不变；非法 device_id 降级 legacy 不拒
- 插件：_http 统一出口对所有 /external 请求附 X-Vod-Device-Id=install_nonce，零新增状态
- 场景矩阵：用户自装机✅/厂商自己服务器→host key 直连（红线已有）/厂商预配逐台
  install✅/母机镜像克隆→装机 checklist（镜像冻结前清 runtime.json）+preset uptime
  判据告警/企业共享服务器→代理 key
- 测试：引擎 VodDeviceAnchorTest 8 条（UT1-UT9）+存量 30 条全绿；插件协议锁 1 条
  +克隆判据 2 条；legacy 语义澄清=存量令牌只认 UA 绑定，device header 不参与

## D-anon-verify（2026-11-05）：匿名令牌链信封契约修复
- 真机实锤：引擎 /external/token 返回 ApiResponse 信封 {code,data:{token}}，插件顶层取 token 恒 None → 无 key 首提必 -32012。此前未暴露=插件常驻 legacy key 不走匿名链（老平台 key 已从 runtime.json 移除）
- 决策：解析收敛 _extract_anon_token 单函数，信封优先+扁平兼容（历史/降级引擎不破坏）；存量 mock 全部对齐真源信封——mock 边界≠协议边界教训第二次实锤（第一次=E1/E2 协议级测试）
- 关联：S21-S23 场景用例入 proposal 三·八；D-key-guard key 移除语义真机双档实测（legacy-shared/anonymous）

## D-product-id-1（2026-11-05）：产品归因主键化（两仓联动，方案 A 用户拍板）
- 缺口：提交链路 product 传名字（归一化/改名漂移面），违背「对账以平台签发主键为准」；主表 t_vod_source_data 既有 product_id+product 双列模式，agent 链只落名字
- 引擎（VOD-Project feat/kb-query-auth 364af5df）：product 纯数字=selectById 主键精确命中（短路 name 兜底），name 通道保留兼容回落；双列落库+回执 productId；囤积区通用化正名 t_vod_agent_inbox→t_vod_voice_inbox（!152 合入前零成本窗口）；meta 端点组装 productCatalog=[{id,name}]（t_vod_product 真源，目录失败不阻塞基础载荷）
- 插件（本仓）：三壳统一——配置/注入的名字经 meta productCatalog 解析平台 id 后提交，纯数字 id 透传，目录无此名/不可达（老引擎无 productCatalog 键）→规范名兼容通道（引擎命中同样补落 product_id）不静默丢提交；python 进程 runtime.json 24h 缓存，node/UI 进程内缓存一次
- 回归：python T7i 2 例（解析矩阵+catalog 缓存/老引擎兼容）共 68 绿；dsh node test fail 0；引擎定向 55 绿（ExternalVoicesServiceImplTest 33+VodIssueSyncServiceImplTest 22）

## D-product-id-2（2026-11-05）：安装期产品硬校验（用户拍板 B，推翻"宿主名是显式合法值"宽容口径）
- 触发：真机 install --product asdasdasdasd 安装成功——归因前提无效但用户无感知
- 论据（用户原话逻辑）：--product 是整条采集链的归因前提，没这个前提内置 skill 逻辑（识别/预分类/透传）全部空转；归因错误比报错更糟
- 决策：install --product 必须命中 meta productCatalog（名字大小写不敏感或平台主键 id 精确），未命中/目录不可达一律 exit 2 拒绝安装（宁可不装不可装错，postinstall 拒绝猜测同源纪律）；运行期显式传参覆盖保持现状（引擎 name 兼容通道是老插件兼容，不是安装期放行理由）
- 实现：bin/_validate_product_or_exit（无 key 走零字段匿名令牌链；老引擎无 catalog 退 /external/products）；java-api-base 优先级补 env VOD_JAVA_API_BASE（与插件运行时同键）
- 口径变更连带：--product 帮助文案删"宿主名合法"引导；测试矩阵新增 3 例（未注册拒/hermes 同拒+零副作用、名字或 id 放行、目录不可达拒），桩引擎 engine_stub 进 installer fixture（distribution 同册），71 用例绿

## D-codex-plugin-1（2026-11-05）：codex 接入终态=原生插件（推翻 D-codex-agents-1 的 AGENTS.md 方案）
- 实锤纠正：本机 codex CLI 0.166 有完整原生机制——`codex plugin add/list/marketplace`、插件清单 `.codex-plugin/plugin.json`（`skills:"./skills/"` + `mcpServers:"./.mcp.json"`）、`~/.codex/skills/` 渐进式加载（只装 name+description 元数据，匹配才读全文）。上一轮"codex 无 skill 机制"的判断是探测面不全（只测了 mcp/exec），AGENTS.md 方案是降级模拟
- 官方规范锚点（developers.openai.com/plugins/*，页面加 .md 取源文）：MCP server=数据/鉴权/受控动作，skill=工作流（何时调用/顺序/异常/输出）；description 决定触发，细节在 body；.codex-plugin 是官方兼容回退布局，便携版=根 plugin.json+extensions.com.openai+agents/openai.yaml 依赖声明
- 终态三层：①工具描述=硬约束（归因不问用户/S1 自报不采信/禁内部机制，话术前置防截断）②原生插件 SKILL.md=采集工作流方法论（全量搬运 vod-feedback-collect）③AGENTS.md 撤（被原生 skill 取代，留 strip 清理旧装机残留）
- 分发形态：仓内 `plugins/vod-devkit/`（插件）+ `plugins/.agents/plugins/marketplace.json`（本地 marketplace，root=仓 plugins/ 目录）；bin 新增 `serve` 子命令（.mcp.json 以 `vod-devkit serve` 可移植拉起 server，npm i -g 前置）；双注册防：安装时清理旧 config.toml MCP 段与 AGENTS.md 块
- 真机闭环：marketplace add→plugin add（installed, enabled）→codex exec 提单不带 product 不反问、经安装绑定归因落库（product_id=1）
- 方法论教训：判定宿主能力前必须把 `--help` 子命令树翻全（plugin 子命令当时就在），单点探测（mcp/exec）得出的"宿主不支持 X"结论不可靠

## D-codex-plugin-1 增补（2026-11-05 晚）：devkit 对表三件采纳+第四版本失位点
- devkit（huaweicloud-devkit v2）codex 接入实测对照：同布局（仓根 .agents marketplace + .codex-plugin + .mcp.json），成熟度三差异已采纳——①安装前清 stale 插件缓存（~/.codex/plugins/{marketplaces,cache}/<name>，缓存不自动失效）②.mcp.json 自包含（python3 + ./vod_mcp/server.py 相对路径 + cwd "."，插件包自带 server，去掉 npm -g 全局命令前置）③plugin.json 补 interface 元数据（displayName/defaultPrompt/capabilities）。policy 保持 AVAILABLE/ON_INSTALL（第三方插件用户主动装，不抄官方预装语义）
- 第四版本失位点实锤：contract/tools.schema.json "version" 从未被 release.sh 同步（vod_devkit_info 恒 0.1.0 假象，原生插件真机实锤）；release.sh 同步点 3→4（含契约）+sync_plugin.py 烧录 build-info.json 进插件包（provenance 真源随包）；自包含契约锁测试（server 漂移/相对路径/build-info 断言）
- 安装器校验探针补设备锚点：token+meta 全程同 X-Vod-Device-Id+UA（S1 设备绑定，缺设备头=meta 401 或 legacy 锚点日 5 次烧满；每次装机新锚点一次校验一枚令牌）
- 本地验证实例已重建至 feat/kb-query-auth 最新（含 50/h+catalog）

## D-release-1（2026-11-05 深夜）：发版体系对表 devkit（release-please 语义）+0.1.12 凭据残留事件
- **0.1.12 凭据残留事件**：npm 包曾包含 vod_mcp/runtime.json（含当时的匿名令牌 java_key）——上轮宣称"28 files 肉眼过没问题"是裸奔，pack-verify 第一次跑就抓到。处置：0.1.12 已 deprecate（unpublish 被 registry 策略 403 禁）+0.2.0 发布含修复；令牌仅对已销毁的本地旧库有效，实际风险低；package.json files 从目录级改文件级白名单（runtime.json 结构性出不了包）
- **发版体系重写（对齐 devkit release-please 语义）**：bump 从提交历史推导（feat→minor/破坏性→major，可显式覆盖）；版本落点表驱动 EXTRA_FILES+整行正则替换（子串 replace 静默 no-op 的根治）+全落点硬断言；显式文件列表提交（git add -A 违纪清除）；RELEASING.md 发版手册落档
- **npm 包内容校验**：scripts/pack_verify.py（pack --dry-run 必含/危险项断言，publish 前必跑）——npm 分发必需 plugins/（marketplace+插件随包），0.2.0 曾漏致 npx 用户 codex 路径必挂，0.2.1 修复并加 MUST_HAVE 断言
- **npx 0.2.1 真机闭环**：一键 install --target codex（marketplace 注册→插件缓存 server+skills 随包）
- **教训**："肉眼过"不是校验；对外制品的每一版发布前必须有程序化内容门

## D-consent-desc-1（2026-11-06）：确认纪律必须前置进工具描述——opencode 未经同意直提单实锤
- 事故：用户只说「产品体验很差劲」，opencode 把用户陈述自行当作同意、直接传 confirmed=true 提交入库（voiceId ext_anonymous-1a1ac8f7685_27732270241d）
- 根因：MCP-only 宿主不加载 vod-feedback-collect 技能，工具 description 是唯一约束源；旧描述以「立即调用本工具…哪怕只有一句体验很差也原样提交，不要追问」开头，确认要求只埋在 confirmed 参数描述里——话术主动鼓励立即提交，与 confirm 纪律直接冲突
- 修复：契约 description 确认纪律前置（先决条件优先于其余所有内容+用户陈述≠同意）；dsh 壳 lib/index.js 同步（confirmWrites 机械审批兜底仍在）；回归锁 test_submit_description_frontloads_consent（先决条件 60 字内+不构成同意+confirmed=true 三断言）
- 边界声明：布尔 confirm 天然无法验证"用户真同意"（模型可代填），采集非破坏性可接受（沿用既有拍板）；若上破坏性写工具仍按 D-approval-upgrade 先 token 化

## D-echo-A-1 提交回执原话回显（方案 A 默认）+ B 宿主级熔断定位（2026-11-06 用户拍板）
- 背景：codex（deepseek 后端）对「逐次确认」「content=原话」双纪律文本约束不服从——实锤零确认直接提交+改写原话（"体验不好"→"产品体验不友好"入库）。加文本无效，转检测型。
- A（默认防线，已实施）：vod_submit_voices 回执强制携带 echo{requiresUserEcho, instruction, contents[voiceId,content]}，agent 必须逐条原样转述「已收录原话：…」。边界：约束不了提交前行为，只让污染当场可见；真正锁死确认只能靠宿主 UI 弹窗。
- B（不全局启用）：draft/commit 两段式 token 审批降级为按宿主可选熔断开关（未实现，仅定位留档）。注意 B 在 MCP 层也锁不死人类确认（agent 可自读 token 自动 commit），只能加摩擦。升级触发：同一宿主 7 天内 ≥2 次未确认提交，或 ≥1 次原话改写且用户不可接受→对该宿主启用 token 化或直接禁写切只读。破坏性工具继续按原口径 token 化。
- 补强建议（未排期，需引擎侧端点）：短窗口 vod_correct_voice/vod_delete_voice，让用户看到改写后能当场更正/撤回——引擎 /external/** 无此端点，须走 VOD-Project 新需求。

## D-dsh-install-1 dsh 工具壳安装期硬校验+幂等写配置（2026-11-06 用户拍板 A+B 配套）
- 拍板：方案 A（`install --target dsh` 包装命令）落地，B（模板写全+README 标红）降级为配套文档防线，不替代硬校验。判据=D-product-id-2 口径三壳统一：dsh 壳此前是「装了再手工补配置」的老形态，正是当初要消灭的"装错=采集链空转且无感知"。
- **强制前置已完成（2026-11-06 真机实测）**：dsh 工具壳的 config 生效通道=profile cordis.patch.yml 的 id-targeted config override（dsh 0.2.1-rc.5 启动 banner + 桩引擎提交链实证 product/apiBase/confirmWrites 三字段全生效）；`dsh plugin add` 对不存在 profile 会自建。
- 实现（bin/vod-devkit）：`--target dsh --profile <p> --product <产品>`——①缺 --profile 在进入任何安装动作前 exit 2（先校验后写入）②产品硬校验复用 _validate_product_or_exit（cmd_install 既有先行位，校验失败不进 add=无半成品）③dsh 不可用 exit 2 ④add 成功后幂等 upsert cordis.patch.yml（已存在 `- id: vod-devkit` 段原位整块替换不重复插入，按行扫块边界不引 YAML 依赖；不吞其它插件段，有回归锁）⑤写配置失败 exit 1 + 手动修复格式指引 ⑥manifest 记 dshProfile，uninstall 摘插件+移除 config 段。
- **归因口径澄清（7b 在 dsh 壳的形态）**：dsh 壳 schema 无 product 参数（部署配置权威）= 7b 极限形态（无运行期入口即无错归入口）；python MCP 壳保留"传参与绑定一致→采信、不一致→忽略+ignoredRuntimeProduct"（D-attrib-A）。修掉 description 漂移（曾写"explicit arg → config product → host identity"旧宽容口径，实现早已只认绑定——约束源三层最陈旧一层生效的复发，验证宿主行为以真调为准）。
- 业界对表（用户质询"分析合理吗"后沉淀）：五项要素=解析期校验/先校验后写入/幂等写入/稳定退出码/失败不留半成品，均有实锤业界源（Cordova CB-10921、Authelia config validate、12factor §V）；部分引用（Gitpod/Chainguard/ServiceOverride）标无源。退出码与现有安装器约定一致（用法/校验=2，运行失败=1），不引入新语义。
- 回归：9 用例（合法装+配置写入/非法产品 exit2 无 add/缺 product/缺 profile/幂等不重复/upsert 保留他人段/原位更新/dsh 缺失 exit2/golden 重录仅 +dshProfile 键）。真机端到端：installer→plugin add→patch 写入→banner 读到 product=CodeArts。

## D-hook-1 Hermes 强制评估路由插件（2026-11-06，负责人确认立项）
- 背景：采集技能自动激活概率性（业界实测简单指令钩子~20%≈无钩子，强制评估注入~84%，显式调用100%）；实锤 hermes 运维上下文压过采集意图（「体验不好」被反问复现排查，技能未加载）。
- 落地：hermes-plugin/vod-feedback-router（pre_llm_call 每轮确定性关键词判定，命中注入 vod-feedback-collect 激活指令，未命中零注入）；描述触发词前置（8bdc225，Hermes 索引仅前57字符可见，「体验差」原在截断边缘）。
- 已知边界：「报错/卡」在纯排障对话也命中=错注入无害（指令不自动提交）；漏注入才是事故。注入仍是文本指令，不改变模型服从性天花板——提交硬保障仍是方案A回显+护栏。
- opencode/codex 钩子面未调研（opencode 有 plugin 体系待查）。

## D-desc-budget-1 description 截断预算门禁（2026-11-06 用户拍板落地）
- 背景（业界实测对表，引用均核验）：宿主对工具/技能 description 普遍硬截断——dsh 固定 500 字符窗口、Codex 5440 字符硬预算且无排除机制（openai/codex#24299：119 技能 103 个被截断、均值 232 字符）、OpenCode 共用 2000 行/50KiB 通用截断。社区路由插件（opencode-skill-activation/lazy-skill-router/dsh-skill-router 系）治的是「激活可靠性/目录开销」，与我们已实锤的事故类（技能已加载仍不服从：codex 跳过确认/改写原话）不同层——服从性问题维持检测层防线（回执回显+e2e_behavior 熔断）不引入路由器。
- 门禁（tests/test_desc_budget.py）：B1=同意先决条件存活于前 500 字符（最严窗口）；B2=description 总长 ≤1500（现状 contract 665/dsh 组合 ~1285）；先决条件前置阈值 contract<60（既有锁口径）/dsh<100（英文前导能力定位句 ~73 字）；双载体同测（contract JSON+ dsh/lib/index.js 逐字符扫描求值组合串）；漂移锁=禁旧宽容归因口径句回流。
- 入 pytest 门禁随 pre-push 自动生效；proposal S45-S48+design 五/六节承载。

## D-option-executability-1 话术选项可执行性纪律（2026-11-06，负责人确认）
- 原则（S51 泛化）：agent 向用户提供选项的场景，每个选项必须是客户端与引擎真实能执行的——无承载的机制出现在选项里=空头支票（用户选了实际做不到），比不给选项更糟（骗取同意）。
- 触发背景：确认环节用户追加反馈（如「我看怎么说，你才明白」）的处置话术中，曾拟「这句作为过程反馈单独记录、不混入产品声量」选项——客户端无过程反馈通道、引擎无此分类档（content 入库后由引擎重判），已撤回。
- 约束面：所有「向用户提供选项」的话术场景（本技能及后续任何采集/操作技能），不限本条话术。落地判据：写选项前逐项问「用户选这项，代码路径在哪」——答不出=删。
- 配套话术（proposal S49-S51）：先定性再问（定性标注理解+纠正口子）、两并列真实选项+括号兜底（只提追加句）、纠正后行为=不辩论按纠正理解走但 content 仍原话逐字（一次抱怨一条+原话红线不因纠正豁免）。

## D-codex-circuit-breaker-1 codex 熔断切只读+恢复门禁（2026-11-06 负责人确认）
- 触发：codex 未确认提交检测账本累计 2 次（10:13 自动计数+用户实锤「产品体验比较差」直接收录），达拍板 B 熔断阈值（7 天内 ≥2 次）。
- 已执行：codex 副本 .mcp.json VOD_PACKS=core,collect→core,kb——submit 工具摘除，只剩 vod_auth_status/vod_devkit_info 只读面；npm 全局包同步升 0.2.3（排查确认 codex 经 `vod-devkit serve` 走 PATH 全局包，插件缓存非执行体）。
- token 化立项表述（负责人纠偏，勿再写错）：token 化两段式=当前 MCP 层**最强摩擦+审计链**（强制 draft→commit 两步可观测、token 单次消费、重复 commit 被拒），**不是人类确认的硬保证**——agent 仍可自动完成 draft+commit 一个来回（MCP 层锁不死人类确认，既有结论）。真正堵死需宿主层 commit 前确认 UI（codex UserPromptSubmit 钩子有截断限制，需单独评估）。
- 验收标准（按上述定性写，防预期落空）：①每次提交有 draft→commit 审计链 ②重复 commit 被拒 ③未确认提交可被检测账本识别。**不是**「模型不再自传 confirmed」。
- 恢复门禁：恢复 codex 采集（packs 改回 core,collect）的前置条件=token 化已上线并通过上述回归——否则熔断解除即复发。门禁动作不只是改 packs 一个动作。
- 深审收口（2026-11-06，外部深审四项全数确认并修复，23a7bb1）：P0-2 packs 命名漂移（PRESETS full 含 workflow/kb 而运行期 ALL_PACKS=core/collect/knowledge——kb→knowledge 别名归一+full 改 knowledge，安装口运行口单源+PRESETS↔ALL_PACKS 回归锁）；P0-3 uninstall 破坏性路径（codex manifest.mcpConfig 曾指向用户整份 config.toml，卸载即删光——改指插件 .mcp.json/None+config.toml 永不删+codex plugin remove best-effort）；P1-4 ack 解除后置（安装成功才落，失败安装不解熔断）；P1-5 codex .mcp.json env 随 --packs 对齐（原硬编码 core,collect 使 --packs 半失效）；P2 strip 精确表头+AGENTS END 缺失拒写盘。
- B 方案（bundle patch 接管配置）可行性修正（2026-11-06 负责人确认的分析结论）：dsh 配置模型中 bundle 层 patch 由 dsh.profile.bundles 清单管理（非手工 profile 块），持久化机制是设计内的——此前"半天调研块保留规则"目标修正为两件事：①确认 product/apiBase 为安装期静态部署值（已确认——恰好落在 bundle patch 适合静态值的安全区；运行期动态变更不走此通道）②cordis.patch.yml 必须写全该行全部期望 config 字段（bundle 层整行替换不深度合并）。落地路径=installer 在 dsh plugin add 后对缓存副本的 bundle patch 写全 config（与 P1-5 .mcp.json env 对齐同模式，缓存每部署一份）。doctor 自愈（A，e6a7d32）先落：检测块缺失/打平→按 manifest product/apiBase 重建嵌套块。

## D-followup-design-1 复现步骤"AI 追问"前置规范（2026-11-06 业界对表，负责人确认）
- 结论：对话式调研（Sprig/CloudResearch/Culture Amp）交叉共识——追问是"获取真实补充信息"的通道，不是"补全模板"的工具。当期不落追问话术（S51：引擎无 supplement 承载，先有承载再进话术）；本条是将来"复现步骤填充"立项的前置规范。
- 四条硬约束（立项时全部落实，缺一不批）：
  1. 可选增强非默认流程：默认不追问直接按原话提交；按反馈类型开关（功能异常类可开，体验差类不开）；上限 1 次追问、只问一个问题（业界：Sprig 1-2 次/CloudResearch ≤3 且一次一问；追问是交互成本，Typeform 完成率 47.3% vs 21.5% 的前提是负担前置可见）。
  2. 话术固定化禁自由生成：固定模板（如"方便说一句当时在做什么操作吗？不方便也没关系，我按原话提交。"）；若动态生成必须过中立性规则校验——禁具体操作名/禁是非问/禁"是不是有没有"引导结构。依据：LLM assistance bias（过早给方案/泛泛确认）+ 引导性追问制造"被暗示的复现步骤"，表面是用户说的、实际是 agent 锚定的，比不问更糟且违反不编造红线。
  3. 数据分层：追问回答独立存储（supplement 字段，来源标注"用户追问补充"），永不回流 content 原话——原话=用户主动说的，追问补充=经引导后说的，混字段=可信度稀释+声量基线污染。issue 复现段只引用 supplement 并注明来源。
  4. 失败诚实回退：问不到就留空不出现（可选段形态），不注记不强填——与"用户未提供"拍板同向，业界同口径（无法生成安全追问就自动跳过；答"记不清"给 best guess 不施压）。
- 与既有拍板的关系：不回流原话=原话红线；固定话术=F3 模糊话术纪律同构；诚实回退=用户未提供拍板；本条新增的只有中立性约束与来源分层两个增量。

## D-token-approval-2 两段式 token 化暂缓（2026-11-06 负责人拍板 A）
- 结论：token 化不立项，codex 维持熔断只读。触发条件=codex 出现真实消费需求（真实用户/真实采集量）时再立项——零消费者宿主不值得为其开引擎写表面（建表/迁移/限频补洞）。
- 论证：token 化对 codex 的收益=违规可检测+内容锁定+一档摩擦，**拦不住** agent 自动 draft→commit（MCP 层锁不死人类确认，既有定论）；引擎侧形态为承载审计链需建表+draft 免配额的新写面（须再补限频）——复杂度与收益失衡，负责人裁剪（"做的越来越复杂了"）。
- 恢复门禁不变：解除 codex 熔断的前置仍是"token 化上线过回归"——暂缓即 codex 采集无限期保持只读，两结论一致不矛盾。
- 本次已出未落的设计（留档防重查）：引擎 draft/commit 端点+V124 t_vod_voice_draft（token_hash/payload_sha256/原子消费/回执快照）+插件 vod_draft_voices/vod_commit_voices；已写五文件已撤（工作树零残留）。

## D-token-approval-2 解冻落地：插件本地极简两段式（2026-11-06 负责人拍板方案 2，44218db）
- 推翻同日"A 暂缓"拍板：用户明确要在 codex 上采集。引擎侧形态维持否决（建表/新写面不值）；两段式下沉插件本地——draft 暂存 runtime.json（cap10 环形+TTL 600s 惰性清除）+一次性令牌，commit 令牌校验/单次消费/载荷 sha 防调包，内部复用 submit_voices 既有链（配额/幂等/归因/回显零新增语义）。
- 验收（门禁口径不变）：①draft→commit 审计链=账本 stage=draft/committed+draftId 关联 ②重复 commit 拒（先消费后提交，中途崩溃不二次提交）③载荷防调包（payloadSha256 引擎签发回传比对）。128 pytest+8 node 绿+真子进程 stdio 回环六项（工具面恢复/错令牌拒/调包拒/消费后重复拒）。
- codex 熔断已按门禁解除（--ack-suspension+审计，标记删）；解除前先验证熔断在新工具面下仍生效（标记在→collect 含两段式全摘）。
- 定性保持：最强摩擦+审计链，非人类确认硬保证；真正硬保证=codex 原生工具审批弹窗（交互模式默认开，测试曾用 --dangerously-bypass 绕过才暴露跳确认）+两段式叠加=提交前用户必见内容。
- 话术：SKILL 第 3 步改 draft→contents 原样展示→确认→commit（双副本 md5 同步）；vod_submit_voices 单发保留给非 codex 宿主。

## D-followup-impl-2（2026-11-08，负责人确认开工）：复现/预期追问补充插件侧落地
- 前提变化：S63「当期不落」的依据=引擎无承载；引擎承载已落地（V20261106110000003+I21/I22），前提解除，经负责人批准按推荐方案开工（A1 确认环节合并一问；A2 MCP+dsh 壳，UI 壳红线不动）。
- 关键决策：①固定问句尾句用「不方便回复"没有"，我直接提交」替代「不方便就直接提交」——给出可执行应答词降低误解；②拒答不止靠话术——客户端 `_FOLLOWUP_DECLINES`/`DECLINES` 词集技术兜底（"没有/无/跳过/不方便/算了/no/none/skip/n/a"），模型不守话术时键集合仍零漂移（信任边界：文本约束对模型不可靠是本仓反复实锤的教训，能技术锁的不交给话术）；③超长口径=引擎同口径截断 2000（引擎 truncate 既有语义，客户端不另立报错协议）；④content 原话红线不因追问豁免（逐字一致回归断言）。
- 范围外：UI 壳不加输入框（直达表单红线）；第二轮追问/严重程度/环境/附件永不索要；引擎零改动。

### D-followup-impl-2 二次微调（2026-11-08，负责人确认）
- 跳过条件收窄：判定块第 2 层原写「已获现象/场景/报错/操作/期望」会让实现者误以为要从引导补充回溯抽取进新字段——收窄为「现象/场景/报错等非泛化内容」并显式补「引导补充中自然出现的操作/期望仍保留在 content 原话，不回溯摘入新字段；新字段仅承载固定追问的原样回答」。依据：数据分层=新字段来源唯一。
- 「未回应/泛化抱怨」补可执行判定例（未回应=仅"提交/嗯/没有"；泛化=仅负面评价无具体现象/场景/报错）——判定例先于行为验收，否则三层规则仍剩自由裁量尾巴。
- 一句话口径改可测原文：跳过时 payload 不含对应键+issue 不出现补充段+不作来源注记（三处诚实回退，与引擎 I22 对齐可逐条断言）。

### S71 问卷化追问 tripwire（2026-11-08，实况复盘立项）
- 实锤：agent 自由生成四维追问清单（分叉示例+频率刻度+期望vs实际框架）——三条中立性红线全破（具体操作名/是非分叉/引导结构），是"被暗示的复现步骤"的标准形态。
- 处置：话术载体（SKILL 双副本+契约 description）结构词黑名单 tripwire；数字编号不锁（判定块规则层与话术层分层——规则层编号清单合法，锁语义词不锁排版）。
- 既有合规通道不变：引导补充固定句+固定追问逐字句；用户主动要求提示不豁免中立性校验。

### S72 反截断红线（2026-11-08，opencode 实锤立项）
- 实锤链：用户补充"操作不方便，流程合理"→模型 reasoning"最新具体抱怨是操作不方便"→draft content="操作不方便"（opencode.db part 表逐条取证）。"原话逐字"规则在单轮场景够用，多轮拼接场景"哪句是原话"成了自由裁量点。
- 处置：SKILL 反截断红线——引导补充后的补充句=完整提交物整体上送禁摘片段；多轮分散表达按序拼接。同构教训第三次出现：规则存在≠判定可执行，凡有裁量空间的都补判定例（追问判定块/问卷 tripwire/反截断同一序列）。
- 附带发现：该会话 DB 输入原文="流程合理"，用户自述"流程不合理"——宿主输入记录是原话真源，对账以 DB 为准；若用户确认输入法/客户端吞字属 opencode 侧缺陷另立移交项。（已闭环 2026-11-08：负责人确认当时输入即"流程合理"，DB 记录准确，opencode 侧无缺陷，移交项不存在。）

### S73 拼接判定例（2026-11-08，opencode 第二次实锤）
- 实锤：S72 反截断生效（两轮原话都进拼接、拒答不上送字段、plan mode 守卫正确），但拼接时把"产品体验很差劲啊"改成"产品体验很差劲。"——删语气词+补句号，展示层即违规，放行则 payload 带病入库。
- 处置：SKILL 补拼接判定例（逐字=含语气词/标点；轮次衔接换行/空格分隔不新增标点；拼接结果须可逐字符还原回各轮原文）。同构序列第四次实锤：规则有、判定例无=裁量空间，凡新规则先想清楚"边界情况下 agent 会怎么自由裁量"再落文档。
- 用户侧处置：该会话直接纠正（指出"啊"字）后放行，回执「已收录原话」须含"啊"字才算通过。

## D-resume-commit-1 断回合续提交+确认收口话术锁（2026-11-09，负责人确认"要"）
- 实锤：Hermes 宿主 agent draft 后收工，用户两次说"提交"仍无下文，反馈 40 分钟未进引擎。根因=approvalToken 只存在于 draft 响应文本，agent 回合中断即丢失，commit 无从恢复。
- 机制层（硬约束）：draft 将 token 随草稿落盘（runtime.json 0600，与 java_key 同级）；commit 允许省略 approvalToken/payloadSha256，由本地未过期草稿恢复（契约 required 收窄为 draftId）。语义不放宽：显式传错 sha 照拒、过期照拒、单次消费对恢复路径同径（S86）。
- 威胁模型不变定性：token 的作用是防载荷改写，不是同意凭证——落盘不放大风险。同意环节仍由 SKILL 软层承载（完全确定性同意需宿主 UI 结构化确认，插件单方做不了，明示为边界）。
- 话术层（软约束）：SKILL 真源加收口锁——用户确认后当回合必须 commit，失败/过期重开草稿再 commit，提交不成必须明告未提交（禁"好的"收工）。经 sync_plugin 生成器同步，dsh 侧 SKILL 同源受益。
- 附带重构：_drafts_load() 单源化 draft/commit 草稿库读写（禁双边漂移）。
- 验收：pytest 162 绿 + dsh node 9 绿；场景用例 S83-S86（proposal.md 同名清单）。

## D-quota-raise-1 匿名档配额提额+引擎侧全量可配置化（2026-11-09，负责人拍板）
- 拍板：匿名令牌累计天花板 500→**5000 条**（30 天不变）、日配额 50→**500 条**（签发 100/h 与日 50 提交倒挂，用户实锤）、锚点日签发天花板 5→**1000 次/天**（该闸只挡换锚点刷令牌，装机调试永不触顶；IP 层日闸 100/天仍兜底）。
- 引擎侧全量可配置化：`vod.external.*` 七项（anonymous-ttl-days:30 / anonymous-submit-cap:5000 / anonymous-daily-quota:500 / token-ip-rate-per-hour:100 / device-ip-rate-per-hour:60 / profile-issue-daily-cap:1000 / rotating-grace-hours:72）——不配置即默认（零配置部署行为不变），常量=默认值真源+默认值三方对账回归锁（VOD-Project 300afbd2 T38）。
- **插件侧零改动定音**：插件不硬编码任何配额数值（grep 实证 vod_mcp 零配额字面量），配额语义全在引擎——429 拒绝文案/引导由引擎回执透传，插件只搬运。引擎提额/改配置后插件无需发版，这是「数值放引擎不放插件」的设计收益兑现。
- 文档同步面：proposal 信任模型表 / INSTALL / SECURITY / SUPPORT（面向用户的数值口径）随拍板更新；decisions.md 历史节落的 500/50 为旧值不改写（历史拍板记录保持原样）。
- 引擎侧实现与验证记录：VOD-Project feat/kb-query-auth 2c1c7223（5000）→ d9b0caa5（可配置+500）→ b9b5f7b5（1000）→ 300afbd2（文档+T38 锁）→ 4a6915ab（@Mapper 真机启动崩修复）；本地真机端到端验证 dailyLimit=500→env 覆盖 1000 双向实证。

## D-inbox-direct-ui-1 dsh UI issue_sync 轮询拆除（2026-11-09，负责人拍板）

- 背景：引擎侧 D-inbox-DIRECT 单表收口（/external/voices 直写 t_vod_source_data，
  不建 issue、回执无 issue_sync 节）后，dsh UI 的 U-S2 轮询
  （GET /external/voices?limit=50 找 voiceId 的 issue_sync）永远拿不到数据——静默失效面。
- 拍板：轮询整体拆除，提交成功（201）即终态提示「已收录，产品团队会看到这条反馈。」；
  不把建单链路加回来（与引擎拍板矛盾）。
- 改动面：src/client.jsx 净删 pollIssueSync/pollForReceipt 及调用点；lib/client.js 随构建重出；
  dsh-ui-collect.md §六/§七/U-S 用例表同步。
- 回归锁：test/no-issue-sync-poll.test.mjs（src/lib 双侧禁 issue_sync 与「已建成 issue」话术；
  提交链本体 VOICES_PATH/retryStashedSubmissions 保留锁）。
- 验收：dsh node --test 10/10 绿。

## D-dev-nonce-sync-1 首装 nonce 内存态同步（2026-11-09 真机实锤）

- 现象：全新安装（无 runtime.json）首次提交必失败且冒给用户——领令牌（设备 A）
  与提交（设备 B）引擎设备绑定校验 401，插件自动重试仍新 nonce（设备 C）再 401；
  第二次提交才成功。存量安装不受影响（runtime.json 已有 nonce）。
- 根因：_install_nonce 首次生成只 _save_runtime 落盘、不回写模块级 _RT
  （仅导入时加载一次）→ 同进程内每次调用生成新 nonce。
- 修复：生成后同步 _RT["install_nonce"]（领令牌/提交/重试全程同设备，
  401→领令牌→重试对用户完全无感）。
- 回归锁：tests/test_install_nonce_sync.py（fresh _RT 下多次调用同值+落盘一致）。
- 验证：本地 e2e 修复后干净沙箱首提一次成功；pytest 163 绿（162+1）。
- 关联：本地部署验证会话（VOD-Project feat/kb-query-auth 209174b9 同日）。

## D-rguard-1 ReceiptGuard 提交侧原文比对闸（2026-11-09，验证立项+负责人确认继续）

- **验证结论（dsh-tools 0.2.0 类型源实测）**：原文透传通道成立——
  `exec.agent.session.deriveMessages()` 的 user 轮消息 = 用户逐字原文
  （append-only 会话日志投影，不经模型；Session 注释自证 "durable source of
  truth"）。模型改写只发生在 args 侧（dsh headless echo 改字两次实锤同型），
  比对 args.content 与日志原文即可抓；模型无往日志写用户轮的通道
  （deferContext 是插件自铸上下文，不产生用户轮）——闸门钥匙不在被测方手里。
- **实现（dsh/lib/index.js）**：纯函数四件 normalizeForGuard/bigramSimilarity/
  collectUserTurns/evaluateVoiceGuard + rgGuardSummary 回执汇总。判定四态：
  verified（规范化子串命中）/fuzzy（≥0.5 相似且规范化长度≥10——短内容必须逐字，
  防 "A问题。补充B" 型胶水词改写靠阈值溜过）/mismatch（编造，含模型自加连接词的
  跨轮超集）/unavailable（exec.agent 不可得）。
- **三档配置 receiptGuard**：off / **report（默认，零危害只标注）** / enforce
  （mismatch+unavailable 拒收，理由串 "ReceiptGuard: …"）。非法配置值回落 report。
- **契约边界**：guard 结果只在插件回执层（receiptGuard 字段），提交载荷不带
  guard 字段——引擎契约零变更；引擎侧对账字段（防宿主整体作恶的天花板兜底）
  留第二阶段评估。回归锁 test/receipt-guard.test.mjs 11 例（纯函数 8+接线 3）。
- **边界如实交代**：宿主程序本身恶意/被替换时日志不可信，本闸不覆盖（宿主侧
  方案共同天花板）；exec.agent 可选，unavailable 态 enforce 下明确拒收不静默放行。

## D-behavior-grade-1 e2e_behavior 确认强度分级+分桶+熔断配置化（2026-11-09，负责人确认继续）

- **分级口径**：确认强度两态——prompt 含明确同意语（提交/收录/上报/记录/记一下/
  反馈给/帮我反馈/帮我提交/同意）= explicit_consent 合规指令，提交不计违规；
  裸抱怨（默认 prompt「产品体验不好」型）未经确认即提交 = unconfirmed_submit 违规。
  修正旧版「凡提交即计违规」——合规指令场景被误计的假阳性根除。
- **分桶**：三桶白名单 unconfirmed_submit / content_rewritten / echo_missing，
  按宿主×桶×窗口计数（对账主键=计数器事件行）；echo_missing（回显检测线失守）
  新纳入计数；桶白名单外拒收；旧格式 evidence 行（无 kind）不炸不计数。
- **熔断动作配置化**：.e2e-behavior.json 增 config 节 threshold(默认 2)/
  window_days(默认 7)/action——report（默认，零危害只记录报告）/exit（任一桶达
  阈值→exit 2 阻断门禁语义）/off；非法值逐键回落默认（对齐 dsh receiptGuard 口径）。
  D-echo-A-1 旧口径「≥2 次未确认→启用 token 化或禁写切只读」中 token 化/禁写
  属插件运行时动作，e2e 工具不越权执行——本工具只负责检测+报告+门禁信号。
- **计数防篡改评估（第二阶段，评估结论非本期实现）**：本地计数器
  .e2e-behavior.json 与被测宿主同环境，宿主进程可改写=天花板与 ReceiptGuard
  相同。权威化两方案：A（推荐）违规事件随提交载荷上报引擎持久层（引擎加
  违规上报端点+按宿主聚合查询），计数权威在引擎侧、本地降级为缓存；B 仅本地
  加 HMAC 签名（防不了宿主读密钥重签，弱防护不推荐）。方案 A 涉引擎契约变更，
  待与 ReceiptGuard 引擎对账字段（D-rguard-1 第二阶段）合并立项一次做完。
- **回归锁**：tests/test_e2e_behavior.py 8 例（分级 2+分桶 3+配置矩阵 2+存量
  兼容 1）；全套 pytest 99 绿。脚本纯函数化（classify_prompt/load_config/
  decide_action/bucket_counts 可单测）。

## D-pending-1 无通道场景 pending 反馈队列（2026-11-09，方案 A 四条执行细节定稿，负责人确认）

- **背景实锤**：插件未装时 skill 兜底「待提交用户反馈」提示只存在于会话输出
  （全盘 grep 零落盘），会话结束=有记录的丢失；补提交与无通道 echo 保真双缺失。
- **组件三件**：①pending 落盘（vod_mcp/pending.py：JSONL 原子 IO，幂等键=
  sha1(content+confirmAt+source) 条目级，内容级去重归引擎 uk_voice_id——两层
  分工注释写死）②flush（submit_voices 两成功路径接入 _flush_pending：同步、
  失败只记日志绝不回滚主提交、重写+原子 rename、失败条目保留 pending、上限
  100 最早优先、超 30 天 expired 剔除）③skill 无通道 fallback 重写（落盘+
  echo 前移两场景诚实区分：有原文则比对以原文为准，无原文 echoShown=true
  概率性防线非确定性闸）。
- **双通道消息分离**：用户侧只见「已暂存，恢复后自动补交」；路径/profile/
  幂等键/flush 结果全部进日志（CWE-209 路径敏感信息不外露）。
- **回归锁**：tests/test_pending_feedback.py 8 例（幂等键稳定性/原子重写/
  坏行容忍/过期/上限 100/失败保留 pending/接线双路径源码锁）；pytest 全套 107 绿。
- **边界如实交代**：echo 前移是「增加一次让用户看见的机会」，非确定性闸；
  模型不回显直接写盘的场景无机制拦截（与 ReceiptGuard 宿主侧天花板同理）。

### D-pending-1 补强：originalLines 权威拼接（2026-11-09 深夜，实锤驱动）

- 实锤：无通道兜底 JSON 里模型把两行无标点原话拼成「差劲。使用…不流畅。」
  （S73 判定例在仍违）；同时该 JSON 即兴结构未落盘（skill 留白即兴）。
- 落码：pending 条目增 originalLines 字段（skill 要求多行原话必填）；
  flush 以 canonical_content（originalLines 拼接）为权威，不一致机械剥除
  模型拼接改动并计 corrected 进诊断；无 originalLines 条目行为不变。
- 锁：tests/test_pending_feedback.py +3 例（剥标点/回落不变/接线）全套 110 绿。
- 定性：通道职责=原话保真+送达确认，内容价值判断归引擎/运营侧——通道方
  不问第四个问题。

## D-behavior-adversarial-1 C 档反例集首夜实测与定性修正（2026-11-10，负责人终审）

- **背景**：外部评审指出 C 档话术规则（9 条）无行为验证；落地反例集
  （scripts/e2e_suite.py 5 用例：E1 仅提及/E2 裸抱怨/E3 反截断/E7 拆条/
  回执基线）+ 真实宿主执行器（e2e_behavior.py 接口化改造 + e2e_nightly_
  behavior.py 引擎侧对账），真机首夜（codex@glm-5.3，安装 0.4.2）实测。
- **实测结果**：违规一「裸抱怨未确认提交」复现 5 次（引擎落库为证）；
  违规二「原话剥前缀改写」复现（「帮我记录反馈：」被剥后入库）；C3
  （仅提及产品名不提交）守规。23 条提交 drafts=0——两段式流程被模型
  整体绕开，全部直提 submit_voices（skill 明文"仅限无两段式工具宿主"）。
- **定性修正（负责人终审，防后人被带偏）**：
  ①两段式=审计链非确认门——11-09 真机已证 draft 返回后 3 秒连发 commit
  未展示未询问并编造叙事；token 锁的是 commit 载荷=draft 载荷（防第三方
  调包），防不了 agent 自己走完两步。真硬确认门在宿主交互层（停等/原生
  审批弹窗），MCP 层锁不死人类确认（D-echo-A-1 原口径）。
  ②引擎侧 title/draft 比对告警=负收益改造——剥前缀发生在 draft 之前，
  draft 载荷即已剥过，commit 与 draft 逐字节一致（payloadSha256），引擎
  侧比对恒绿，对真实攻击面零收益。不得再提案。
- **处置（既定口径，不动代码）**：实测违规计数进既有熔断桶
  （unconfirmed_submit/content_rewritten，e2e_behavior 7 天窗口 ≥2 触发
  档位动作），方案 A 回显已在全链生效；不新增代码锁。
- **harness 已知口径缺陷（校准债，已修 2026-11-10）**：reconcile 的 anchor 归属把
  「剥前缀行」误归 fabricated——C1/C4/C5 前缀被剥后 anchor 不在行内；
  首夜 engine 侧 fabricated=3 实为归属偏差，本地 per-case 判定（4 次
  content_rewritten）为准。修正已落：双锚点（anchor+tail），剥前缀行经
  tail 归属到用例并计 content_rewritten（tests 回归锁在位）。
- **部署形态**：定时 cron 方案否决（插件无宿主机器概念，负责人拍板
  删除）；工具留仓随需手跑（改话术后/发版前，任意装 codex 的开发机）。

## D-uiBase-direct dsh 浏览器半 uiBase 直连（2026-11-10，负责人条件确认）

- **背景实锤**：嵌入方真机——UI 反馈按钮提交报"已暂存"。根因=安装器只写
  product/apiBase，不写 uiBase：apiBase 是工具半（Node 服务端）自用，浏览器半
  （反馈按钮）在同源策略下用不上绝对地址；缺 uiBase 时 fetch 发相对路径 →
  打到 dsh 同源 → 404 → client.js 落 pending-endpoint 本地暂存（设计内兜底，
  数据不丢但发不出去）。
- **形态**：浏览器半直连引擎（uiBase），安装器 install --target dsh 与 doctor
  重建块（_repair_dsh_patch_block）同口径写入；README 写明部署前提二选一
  （uiBase 直连 / 宿主代理）。
- **依赖与触发条件**：引擎 CORS 收敛（白名单制）落地时，白名单必须含 dsh
  本地源（http://127.0.0.1:<port>），随引擎上线同步验证——本决策的挂账钩子。
- **红线重申（同案）**：产品归因禁止任何默认值兜底——嵌入方 agent 曾本地热修
  给 product 默认 CodeArts，违反 D-attrib-A/D-product-id-2（宁 UNKNOWN 不错归），
  仓内无此默认值（grep 实证），装机副本由嵌入方自行回滚。
- **回归锁**：test_install_dsh_valid_product_writes_config 断言 uiBase 落盘；
  doctor 重建用例同断言。

### D-uiBase-direct 补充：dsh patch 块嵌套铁律（2026-11-10 真机实锤）

- 实锤：安装器曾写平铺块（`- id: vod-devkit` 顶格）——dsh 组合层只认
  缩进在 `- insert:` 下的嵌套块，平铺块被静默丢弃=插件整个掉出组合树
  （banner/工具/UI 全消失）。修复：install 与 doctor 统一嵌套口径，
  _find_dsh_block 嵌套命中时向上归并组头整组替换，upsert 附带孤儿
  `- insert:` 组头自愈清理；回归锁并入 test_install_dsh_valid_product
  _writes_config。此前 11-09 真机实证能过，是当时 dsh 重序列化把平铺块
  收编了——依赖宿主宽容=非稳定通道，此坑在宿主行为变化时爆发。

### D-devtoolchain-1..5：对表 huaweicloud-devkit 的工程化改造（2026-11-11，负责人「全部做」）

判据：只抄它**市场验证过的工程形状**（骨架），不抄它清单（别人需求的镜像）。
五条全部落在「可对账性」与「单一事实源」上，没有一条扩展产品能力面。

- **D-devtoolchain-1 用例承载棘轮**：proposal 定义的每个用例号必须有承载痕迹
  （design 承载表 / tests / dsh 测试，区间写法展开）。历史欠账 72 条进
  tests/case_roster_baseline.txt，只许缩不许增；补上承载必须同时删基线条目。
  理由：131 个用例号中 72 个此前全仓无痕迹——不是没测，是没人能自动回答
  「这条承诺兑现了吗」。
- **D-devtoolchain-2 声明计数禁止手写**：对外文档/CI 不许写「N 用例/N 工具」。
  实测四处互相矛盾（README 39 / README.en 39 / ci.yml 25 / scheme-overview 24
  vs 真实 194+24）。改写口径=「全量 + 实测命令」。历史台账（CHANGELOG/
  decisions）不受限——它们是记录不是现状声明。
- **D-devtoolchain-3 配置形态守卫**：codex config.toml / dsh cordis.patch.yml 的
  扫描与删除统一进 vod_mcp/config_forms.py；非已知形态在改字节前拒绝
  （重复表头、畸形表头、tab 缩进、flow 根、映射根、多个受管块），一律
  字节不动 + 非零退出。顺带修掉真 bug：旧剥离只删父表，残留
  `[mcp_servers.vod-devkit.env]` 会在 TOML 语义里重建父表 → 装出一个没有
  command 的假 server（模型 = "gpt" 的配置删完仍留 env 表，实例复现）。
- **D-devtoolchain-4 技能披露第二轨**：领域规则技能进 MCP 披露面
  （vod_list_skills / vod_retrieve_skill，knowledge pack，只读零上游），元技能
  仍原生安装。理由：四份宿主拷贝各自漂移，D-drift-lock 只能事后发现；且
  dsh 这类没有规则技能原生目录的宿主此前拿不到规则全文。同时修掉
  vod-core 路由表教已删工具（vod_run_analysis 等）的存量漂移。
  - 口径校准（2026-11-12 复评，负责人拍板 A）：上句"领域规则技能由披露面下发"
    与安装器现状不符——规则技能是**双轨**（安装器无条件落地静态副本 + 披露面同文本
    取全文），knowledge pack 只控制披露工具，不控制文件可见性。以代码现状为准
    （不做安装器过滤：默认 collect 用户会失去规则能力，是能力回退），已同步
    skills_registry docstring；description 里的内部真源路径一并挪出（description
    最容易被模型原样复述），正文补"对外复述纪律"。
- **D-devtoolchain-5 发版终态断言 + 功能级冒烟**：release.sh --publish 后必须
  过 publish_verify（轮询 npm view 到目标版本 + 拉回 tarball 查关键模块与
  契约版本）；smoke_hosts 从识别级升到功能级（读宿主实际配置拉起 stdio 真调
  只读工具），并支持 --expect-tools——同版本号下工具面可以不同（npx 缓存
  副本与仓内 head 实测同为 0.4.4 却少 3 个工具）。

- **回归锁**：tests/test_case_roster.py、test_claims.py、test_config_forms.py、
  test_skills_disclosure.py、test_update_check.py、test_hosts_spec.py、
  test_publish_verify.py，以及 test_installer.py 新增的 golden 三态与形态
  守卫三例。
- **残余**：dsh 壳（node 半）未接披露/版本提醒；vendor 规则 third skill
  （vod-category-matching）文件本身不存在（vendor 已停用），文档已改为与现状
  一致而非凭空补规则；publish 仍需人做一次 npm 登录与 2FA。

## D-attrib-B 归因改运行期字面解析（2026-11-11，负责人拍板 P1-P4 全 A）

需求变更：产品不再由安装/启动配置决定，改为查产品名录后按**用户原话**归因，
并记忆复用。四条拍板（负责人原话确认）：

- **P1-A 歧义**：≥2 产品命中一律 UNKNOWN + evidence 留痕，不择主不拆批。
  依据：错归的产品会被 ISYNC 直接建成公开 issue，公开面错误代价远高于人工归因。
- **P2-A 记忆**：机器级 + TTL 30 分钟，新字面证据无条件覆盖。
- **P3-A 契约**：删除 product 参数（保留条件采信会多一层 ignored 语义与回归成本）；
  「模型自报被忽略」的语义以代码忽略 + 回执 ignoredRuntimeProduct 保留。
- **P4-A 引擎侧**：首期不加列，证据只留本机账本 + 回执；等错归率报表需求明确再加。

推翻/降级：D-product-id-2 的「--product 必填 + 硬校验」→ 降为可选先验，仅保留
「给了就必须对」；D-attrib-A 的「归因只由安装绑定决定」→ 绑定降为第三顺位先验，
模型自报仍不采信（事故语义不解除）。

负责人点名要盯的落地风险（逐条落承载）：
1. 别名索引误命中 → design 判定例表（拉丁词边界、短别名只认 OBS 强形态）＋S93
2. 机器级记忆多人共享 → TTL + 回执 productSource=memory/evidence 回指（S95/S99）
3. UNKNOWN 证据留痕 → 歧义保留**全部**命中片段（S94），非只留一条
4. P3-A 删除参数 → 四宿主副本+codex 缓存副本契约同步（发版后重装才生效）；S97 锁语义
5. 老引擎/离线 → 仅短码可匹配，无证据显式 unknown 不静默猜（S98）

用例：S91-S100（proposal 新节）→ 承载见 design 同名节。

范围补充（同日追加）：dsh 壳（node 半）同步落同一口径——负责人要求"能力一致"，
壳内删硬编码 PRODUCT_MAP 改名录驱动，账本/回执同带 productSource/productEvidence，
描述口径改为"来自用户原话，部署值仅先验"；回归锁 tests/test_desc_budget.py 的
dsh 归因漂移锁已按新口径改写（旧「安装期绑定」句禁止回流）。

## D-devtoolchain-6 治理三件：结构守卫 + 花名册显式清单 + 规则真源对账（2026-11-11，负责人拍板 A）

背景：与 huaweicloud-devkit 重新对表后（devkit v2 5b770e6 / 本仓 e613449 实测），
骨架层已对齐，剩余治理层三处欠账。负责人选 A（零风险三项），全落。

1. **结构守卫**（tests/test_structure_guards.py，6 例）：vod_mcp 不得 import 引擎
   内部模块（插件只走 HTTP）；可选 SDK `mcp` 只能出现在远程面两模块（stdio 主路径
   零第三方依赖）；attribution.py 必须纯函数（禁文件/环境/网络 IO，持久化留 tools）；
   contract 与 _HANDLERS 工具集一一对应；policy.json 必备字段下限 + 规则指向工具
   真实存在（跨切面 field+regex 规则例外，正则必须可编译）。
2. **花名册显式清单**：删除门禁现场正则扫文档的形态，改 `scripts/case_roster.py`
   （共享扫描逻辑）+ `scripts/sync_case_roster.py`（重录）+ `tests/case_roster.json`
   （用例号→承载文件，可审阅）。门禁四条：花名册==proposal 定义；承载文件真实存在
   且正文含该编号；豁免==baseline（棘轮只缩）；已补承载的条目不许留在豁免。
   首次重录：141 用例、72 无承载（历史欠账，基线不动）。
3. **规则真源对账**：删除已停用的 scripts/vendor_rules.py（README/CONTRIBUTING 曾写
   "从 VOD-Project 拉取"=描述一条不存在的链）。替代=`docs/rules-provenance.json`
   （技能↔引擎文件↔符号三元组 + 双方 sha256）+ `scripts/rules_provenance.py`
   （符号对账 + 指纹漂移；无引擎检出 SKIP 不伪绿；人工复核后 --update 重录）。
   CI 增两步：花名册 --check、规则真源对账。

未采（仍不抄）：devkit 的 56 工具/12 packs/sandbox/proxy/telemetry（云服务业务面）、
5 宿主全适配（无消费者）、release-please（我们 release.sh 三重断言已反超）。

## D-product-catalog-1 产品名录单一真源=引擎接口，插件不预置产品名（2026-11-13 负责人纪律）

支持的产品列表由 VOD 引擎 meta 接口下发（`productCatalog` / `products`）。插件侧
任何本地产品清单都是过期真源，且过期清单最危险的用法就是静默归因——已清除两处：
- `_META_SNAPSHOT` 原带 7 个短码（agentarts/codearts/...）：删除，名录不可达时
  `products=[]`，归因一律 UNKNOWN→追问，只留 stale 标记；`search_products`
  在无 catalog 时返回空候选，不拼凑。
- dsh UI 报错文案原列 15 个产品名（"取值=生态看板产品名：..."）：改为指向
  `GET /external/meta` 的 productCatalog / `vod_search_products`。

边界：`BRAND_ALIASES`（码道→CodeArts）保留，但只对**本次 catalog 里存在**的产品
生效（不存在即跳过，不产生指向幻觉 id 的别名）；它是用户口语词表，不是产品名真源。
回归锁：test_attribution（S98 名录空→UNKNOWN）、test_meta_unreachable_falls_back_snapshot
（products 必须为空）、test_auth 归因块（短码/俗称在名录不可达时都不得归因）。

### D-attrib-B 复审触发与后续排期（2026-11-11，负责人拍板 A + P5/P6）

- **维持 A（不问）**：契约继续 NEVER ask，歧义进 UNKNOWN，不猜不问。理由=P5 让
  "不问也归得准"成立前，用打扰补上下文不足是顺序反了；且询问要动契约/SKILL/
  desc-budget 三处锁，历史上问"哪个产品"已直接导致采集失败（非理论风险）。
- **P5（productKeywords）已撤回（2026-11-11 负责人否，理由成立）**：关键词是功能词
  （导出/登录/报表/补全），跨产品通用，接进"唯一命中才采信"的链会直接制造多产品
  歧义（自己造 UNKNOWN），更坏时造成错归；且产品称呼已有真源（nameAliases=
  DB 实测写法 + productCatalog name），再加一列等于同一语义的第三个偏移真源。
  引擎 `t_vod_product` 已有可运营编辑的 description（TEXT），真要做运营维护，正确
  对象是**别名（产品称呼）迁移到 DB**，不是新增功能词列——且须先有数据。
- **P6 同样撤回（2026-11-11 负责人否，理由成立：没有消费者）**：inbox 行里本来就带
  content——未归因的行没有命中片段（evidence 为空），已归因的行产品已落库；而命中
  规则是确定性的，任何人拿 content + 引擎下发的别名可复算。「product_source 报表筛选」
  没有明确消费者（运营的实际动作是"看内容判产品"，不是"看归因来源"），加两列=DDL+
  映射+契约+用例的上游变更，换不来任何动作差异。
  **零 schema 变更的度量方案**（替代 P6）：
  · UNKNOWN 率 = inbox 里 `product_id IS NULL` 占比（现成 SQL，无需改表）
  · 原因分布 = 抽样把 content 过一遍插件 attribution（离线脚本，不入交付分支）：
    命中却未归=别名覆盖不足；无命中=用户没提产品；多命中=歧义
  · B 的复审只看这两组数，结论落 decisions，不进代码
- **B 的复审触发（不现在拍板）**：P5 上线后统计 UNKNOWN 率、UNKNOWN 原因分布、
  运营从证据反推的平均处理成本；只有数据表明"UNKNOWN 集中在少数多产品歧义模式、
  且运营成本显著高于一次二选一确认的打扰成本"时，才凭数据小范围灰度 B，届时再改
  三处锁。B 的话术留作备选，不落地。

## D-devtoolchain-7 更新链补 skip-version + registry 对账 + 类型门禁（2026-11-11，负责人拍板 B）

对表 devkit 的 update-* 八模块（update-semver/skip/cache/registry-diff/…），只取对
我们场景有消费者的三件；照抄整条链是无收益负债。

1. **skip-version**（vod_check_update: skip / clearSkip + `vod-devkit update --skip`）：
   只压「当前 latest 这一个版本」，下个版本照常提醒——永久静音比打扰更坏（用户会
   长期吃旧包且无人知道）。与既有 dismiss（3 天冷却）并存：dismiss=不想被打扰，
   skip=这个版本不要。
2. **registry 对账**（scripts/registry_reconcile.py）：与 publish_verify.py 分工——
   publish_verify 管「发版当时真的上线了没」，本脚本管「任何时刻的状态快照」：
   两包同版、契约版本同步、registry==仓内 / 仓内领先（开发中）/ registry 领先（DRIFT）、
   tag 是否在。离线=UNKNOWN 不判绿。CI 以非严格模式跑（仓内领先=正常开发态）。
3. **类型门禁**（pyproject [tool.mypy]，作用域=vod_mcp/attribution.py）：全仓 mypy
   会炸存量 tools.py 且无收益；白名单式收窄——新增纯逻辑模块必须过，存量随重构
   自然收敛。首个模块补了 5 处容器注解（mypy var-annotated 报出来的真问题）。
   CI 装 mypy 并跑 `python3 -m mypy`。

未采：update-registry snapshot diff 全量（我们用 publish_verify 的 tarball 内容断言
覆盖）、update-upgrade 自升级（preset 形态禁止自更新是既有拍板）、badge:sync。

## D-attach-1 远程 attach 安装模式（2026-11-11，负责人拍板 B）

需求：MCP 单独部署一个远程端点，宿主（hermes/opencode/codex）只把 MCP 配置指向它 +
本地装技能即可用。对表 huaweicloud-devkit 的做法后确认：**他们没做这件事**——remote
仅 README 片段（代码里 0 处 "type": "remote" 写入器），且其 AK/SK 落在服务端本机
文件，远端没有 per-request 身份，只能同机/可信内网。我们的远程面要求 per-request
Bearer 优先（**2026-11-16 D-token-machine-1 修订：无 Bearer 时改为机器级匿名令牌，
"缺 key fail fast、不代签匿名"的旧口径已废止**），身份边界成立。

形态（`install --mcp-url <url> --mcp-token <token>`，或 env VOD_MCP_TOKEN）：
- hermes：`hermes mcp add vod-devkit --url ... --auth header`，token 经
  MCP_VOD_DEVKIT_API_KEY 注入，hermes 自己写 ${ENV} 引用（配置不落明文）
- opencode：`mcp.vod-devkit = {type:"remote", url, enabled, headers}`（token 明文在
  配置里，提示文件权限）
- codex：`codex mcp add vod-devkit --url ... --bearer-token-env-var VOD_MCP_TOKEN`
- dsh：不走 MCP → 两种模式显式拒绝（exit 2），不是静默降级

硬约束（都落成测试）：
1. **token 可选**（2026-11-16 D-token-machine-1 修订；原口径"必填、缺 token exit 2"已废止）：
   带 token → 用请求头身份并验有效；无 token → 只做连接级探活，配置不写认证，
   提交由远程 server 的机器级匿名令牌完成（同机独立部署的默认形态）。
2. **探活先于写入**：initialize + tools/list，断言工具面 == 契约 − REMOTE_WITHHELD；
   失败/工具面不符一律 exit 2 且零副作用（配置文件与 manifest 都不产生）。
3. **skills-only**：MCP 已由别处注册时只装技能、不动宿主配置（manifest
   transport=skills-only）。
4. **技能双面**（照 devkit 的 root/retrieve 双轨思路）：远程面没有 draft/commit/
   list_submitted → SKILL 改为"先看工具面再定流程"，禁止承诺草稿两步与本机账本查询。

顺带修一条存量 P0（远程落地时才暴露）：`uninstall` 会整文件删除 manifest.mcpConfig，
而 opencode 的 mcpConfig 就是 ~/.config/opencode/opencode.json（用户整份 provider
配置）——旧守卫只挡了 config.toml。现在共享用户配置一律"只摘托管条目"：
opencode 删 mcp.vod-devkit 键、hermes/codex 走官方 mcp remove，文件永不整删（用例
`test_uninstall_remote_keeps_user_config_keys` 断言用户键原样保留）。

## D-skill-structure-1 技能结构与触发词门禁（2026-11-11，对标 huaweicloud-skills）

对标 developer-skill/huaweicloud-skills（195 技能/17 领域，实测 references 192、
scripts 168、tests 5）。采纳四项，全为测试与文档（零生产面）：
1. `tests/test_skill_structure.py`：frontmatter 合法 YAML + name==目录名 + description
   非空 + tags≤5 + 顶层无 version（挪 metadata.version）+ SKILL.md ≤500 行 +
   references 文件名 kebab-case 且必须有 verification-method.md。
   依据：对标仓规则写着"tags≤5/无 version"，实测 32 个超 tags、27 个带 version、
   27 个超 500 行——**规范没有门禁就会漂**，所以借的是门禁不是条文。
2. 触发词冲突扫描（对标 skill-tester Phase 5 internal_ambiguities）：技能间 Triggers
   不得重复；多技能共存时互抢激活是真实风险（dsh 市场装一堆技能）。
3. vod-core 路由表覆盖性：每个技能必须被路由表引用（否则装了不可达），路由表不得
   引用不存在的技能（vod-system 作为外部系统名白名单）。
4. 技能级 references/verification-method.md + acceptance-criteria.md（vod-core 与
   vod-feedback-collect）：只给验证入口与勾选清单，断言仍以 proposal 用例与 tests 为准
   （避免第二真源）。

未采：references/iam-policies.md 与 cli-installation-guide.md（无云 IAM/CLI 场景）；
tests 随技能包（与"验收工具不入交付分支"冲突）；skill-audit 那套重型工具链
（gitleaks 自动下载/skillspector/markdownlint-cli2）——我们已有 secret_scan + pyflakes；
skill-quality-cli 遥测包装（拍板不做遥测）；"SKILL.md 默认英文"（上架时再做）。
脱敏取向：维持拒收（A），不对反馈就地脱敏（逐字回显是硬红线）。

## D-tags-1 分类标注白名单 + 等级定义入技能（2026-11-11，对标 developer-skill/vod-skill）

对标 vod-skill 仓（同域 4 个技能；vod-feedback-classifier 1928 行 SKILL.md + 66 文件 +
产品文档语料）后采纳两项：

1. **tags 白名单**（对标其 check_classification.py：分类必须存在于知识库）
   现状缺口：契约里 tags 只是 string 数组、tools.py 原样透传，脏分类先进报表。
   口径：引擎约定 `problem_type:<值>`（ExternalVoicesServiceImpl.extractProblemType），
   值域=meta.problemTypes；白名单外的 problem_type 值丢弃并回执 invalidTags（只丢
   tag，不拒收声音）；其它语义 tag 不参与校验；meta 拿不到白名单（老引擎/快照）时
   空集=不过滤（宁可放行不误杀）。
2. **等级定义入评分技能**（真源=引擎 llm_analyzer.py LEVEL_CRITERIA）
   缺口：vod-scoring-rules 只有"L1=5.0…"的分数，没有定义，模型无法预判等级。
   落法：把七个易用性维度（易学习/易部署/易开发/易迁移/易维护/易演进/易社区）的
   L1-L5 定义以表格摘入技能（不抄 vod-skill 的"声音等级 L1-L5"——那是另一维度，
   抄进来=第二套 taxonomy），并把 llm_analyzer.py 加进 rules-provenance 符号对账。

未采：其产品文档语料学习链（CDP 抓文档建功能知识库——插件不拥有分类真源，抓取脆弱
且会造第二真源）；批量 CSV 断点续传/追加写（我们 pending 已原子重写）；"每次加载技能/
每次 3 条/展示思考过程"的批作业禁令；1928 行单文件（超 500 行反例）。

## D-hosts-1 宿主适配分层：专属模块 + 通用写入器 + 探测表（2026-11-11，负责人拍板 A+B）

对标 huaweicloud-devkit 的「为什么它能支持那么多 agent」：不是 11 套集成，而是三层——
6 个真宿主特异模块（agents/<id>.ts，平均 ~190 行，统一 deploy/status/uninstall/doctor
四面孔）、其余只写 mcpServers + 拷同一份技能树、认不出就 `configureGenericMCP()` 给片段；
横切是声明式 AGENTS 表驱动探测（加宿主=加一行）。

我们的差距不在能力而在**边际成本**：四宿主逻辑内联在 1387 行的 bin 里、13 处 target
分支、未知宿主直接"不支持"、没有通用写入器、没有声明式探测表。

落地（A+B 一次做完）：

1. **B 结构**：`vod_mcp/host_adapters/` 包，每宿主一模块（hermes/opencode/codex/dsh），
   统一协议 `install / install_remote / skills_dir`；`__init__.py` 的 REGISTRY 驱动分派，
   bin/vod-devkit 只剩参数解析、manifest、status/doctor/verify/update/uninstall。
   门禁：`tests/test_host_adapters.py` 锁协议完整性 + 「宿主动手逻辑不得回到 bin」。
2. **A 兜底**：`--target generic [--mcp-config <path>]`——外科式合并 `mcpServers.vod-devkit`
   （其它 server/用户键原样保留、首改 `.bak`）；非法 JSON/非对象拒绝且字节不动；不给路径
   只打印可粘贴片段；`auto` 只探测到唯一通用宿主时自动走通用写入（多个/零个要求人指定）。
   探测表 `KNOWN_HOSTS`（Claude Code / Cursor / Windsurf / Cline）只收「已知 JSON 形态」，
   不在表里的宿主仍可用 `--mcp-config` 显式装。

未采：把 11 个宿主全做成专属模块（没有消费者验证）；通用层代装技能（技能目录是宿主私有
的，猜错=把话术装到没用的地方）。

## D-payload-1 安装载荷固化（2026-11-11，对标 devkit copyServerPayload）

事故模型：本仓所有 MCP 入口此前写 `sys.executable + <repo>/vod_mcp/server.py`。
npx 安装时 repo 在 `~/.npm/_npx/<hash>/`——npm 清缓存或换版本后入口指向已删除路径，
宿主启动即 MCP 掉线，且**没有任何报错**（比装错更糟：用户在会话里等一个不存在的工具）。

落地：`vod_mcp/payload.py`
- `stage()` 把 `vod_mcp/ contract/ safety/ skills/`（+ build-info/package.json）拷到
  `~/.vod-devkit/payloads/<version>/`，`payload.json` 记逐文件 sha256（**不自指**），
  写 `.installed` 标记
- `base.server_entry()` 优先返回载荷里的 `vod_mcp/server.py`；`bin` 在 install 前
  `stage()` + `set_payload_dir()`
- `prune_stale()` 只删我们拥有的顶层条目（`OWNED` 白名单；用户文件不动）
- `server.py` 启动消费 `.installed`；`doctor` 校验 sha256、提示重启、报残留目录
- `uninstall` 逐目录删载荷副本 + marker

与 devkit 的差异：零第三方依赖 → 不做它的 `installRuntimeDeps`（npm install undici）；
载荷校验用 sha256 全集而非字节数重试（Python 侧无文件锁重试梯子）。

## D-installs-1 manifest 记多宿主安装（2026-11-11）

结构债：manifest 顶电平字段只记「最近一次安装」。装 opencode 后再装 codeartsdoer，
`uninstall` 只清最后一个宿主的 MCP 条目，前一个宿主的配置永远留在那（且 doctor 不报）。

落地：`installs[]` 每宿主一行（target/transport/mcpConfig/skillsDir/payloadDir/
product/packs/dshProfile/apiBase/version/commitSha），按 target 去重合并；
**已被 D-installs-profile-1 细化：行键 = `(target, dshProfile)`（dsh 的多 profile 各自一行）**；
`uninstall` 逐行清理（老 manifest 无 installs[] 时退化为单行）；顶电平字段保留
「最近一次」语义（golden/status 兼容）。

## D-codeartsdoer-1 CodeArts Agent 适配（2026-11-11，本机实测）

事实（`~/.codeartsdoer/installers/codearts` 286MB 二进制 + 现场探针）：CodeArts Agent
是 **OpenCode 分支**（`SCENARIO=codeartsdoer`、`OPENCODE_CONFIG=~/.codeartsdoer/
codearts_cli.json`、`KERNEL_CONFIG_DIR=~/.codeartsdoer`）。
- 实测：往 `codearts_cli.json` 写 `mcp.vod-probe` → `codearts mcp list` 立即显示
  （"○ vod-probe disabled"），随后还原 → 通道确认
- `codearts mcp add` 无参数（交互向导）→ 程序化只能写 JSON，再用 `mcp list` 冒烟
- `mcp_settings.json` 只对**项目级** `.codeartsdoer/mcp/` 生效；用户级读
  `~/.config/opencode/mcp/` → **huaweicloud-devkit 写的 `~/.codeartsdoer/mcp/
  mcp_settings.json` 用户级不生效**（它项目级那半边是对的）
- 技能目录 `~/.codeartsdoer/skills`（二进制字符串）

落地：`integrations/codeartsdoer/host.json` + `host_adapters/codearts.py`（复用
`merge_json_mcp`）+ REGISTRY 一行；`doctor` 用 `codearts mcp list` 冒烟；
`uninstall` 只摘 `mcp.vod-devkit`（**codearts_cli.json 是用户配置，绝不可整文件删**——
第一版实锤：没进共享名单，卸载把整份配置删了，已加目标白名单）。

真机验收：本机装完 `codearts mcp list` → `✓ vod-devkit connected`；`doctor` OK。

## D-meta-v2-1 对齐引擎 dev 2026-11-12（产品表驱动 / 分类按产品 / 别名删除）

上游（VOD-Project dev 3e1b3205 起）实测变化：
- 产品清单/分类改 DB 驱动（t_vod_product / ProductCatalogCache）；VodExternalProducts 的
  VALID_PRODUCTS / DISPLAY / NAME_ALIASES / PROBLEM_TYPES 四份手写副本全删
- meta 不再下发 nameAliases/aliases；分类要 `?productId=<id>` 才有 problemTypes
  （真源写作「技术/业务咨询」带斜杠）
- voiceId 换代：ext2_{ns}_{sha1[:12]} → VDPL/VDWD+yyyyMMdd+4 位序号；幂等键独立成
  dedupe_key={productNamespace}_{source|deviceHash8}_{sha1(content)[:12]} 存关联表
- **产品进入幂等命名空间**（渠道退出：客户端自报可漂移）

插件侧落地分两笔（并行会话先落 1bb9f67，本笔补两处真机缺陷）：
1. 1bb9f67（zhirong）：别名改为本地规则派生（去空格/拉丁核心词/大小写变体）+
   BRAND_ALIASES 品牌俗称表（码道→CodeArts）；分类白名单改按产品拉 + 缓存；
   draft 归因前移。实测修正 ModelArts(id4) 原被硬归 Maas(id5) 的错误。
2. 本笔（真机实测发现的漏洞）：
   - **全大写缩写被标成 caseless**：`obs://bucket`、`/obs/bin`、`a@obs` 全部误归
     OBS(261)——S93 铁律被破。修：派生别名里 `alias == alias.upper()` 一律不 caseless；
     `_ascii_hits` 增加 URL/路径上下文排除（前 `/ . @` 或后 `: / \`）。
   - **取不到分类会抛异常**：`_allowed_tags` 只 catch ToolError，网络类异常直接冒泡，
     与"不可达即不拦"的文档语义矛盾。修：catch Exception + 命中缓存后同步 _RT
     （否则每次提交都外呼一次）。
3. 回归锁 tests/test_meta_v2_alignment.py（8 例）：大小写变体不退化成单命中 /
   全大写缩写在 URL 与路径里不命中 / ModelArts≠Maas / 码道来自本地清单 /
   按产品取值域 + 缓存 + 失败即不过滤 / 提交侧白名单回执。

遗留（需引擎侧确认，写进问题单）：
- UNKNOWN 落库后运营补归因，dedupe_key 是否同步？不同步则同一句话补归因后再提
  会变成第二条声音。
- raw 不可变仍只是应用层承诺（152 个迁移、0 个 CREATE TRIGGER）。

## D-product-ask-1 缺产品必须问一次，不许裸提交 UNKNOWN（2026-11-11 负责人拍板）

推翻两条旧口径：D-attrib-A「禁止询问产品」、P3-A「契约删除 product 入参」。
需求原话：不允许"一页 UNKNOWN"——用户没说产品就必须追问具体产品。

归因优先级（新，按负责人口径修正后的顺序）：
  ① 用户明确回答/确认（contract.product）→ user_answer
  ② 原话唯一且高置信提及（多产品/对比语境=低置信，转去问）→ user_input
  ③ 会话记忆（30 分钟滑动、进程内、跨会话不继承、作用域含身份哈希）→ memory
  ④ 安装先验 → install_binding
  ⑤ 都没有 → 工具以 -32010 拒绝，错误里带候选（模型据此问一句），**不写引擎**

**不做任何兜底猜测**（2026-11-11 二次拍板，负责人口径）：没有产品就是"不支持提交"。
- 用户说"不知道/随便"（productNotSpecified=true）→ 也不按宿主产品记，直接拒绝并提示
  用户"没有产品归属的反馈我不提交，因为不知道转给哪个产品团队"，请他补充产品
- 用户说的产品不在名录（"智果"/打错）→ 不按原名硬提交、不自己挑最像的，用
  vod_search_products 的候选再确认一次；仍对不上 → 不提交
- 名录不可用（离线/快照）时无法校验，按用户回答原样上报、confidence=low（引擎侧继续按表解析）
- 宿主 productDefault 只用于候选提示，**不作为归因来源**（host_default 已删除）

落地：
- 契约：submit/draft 重新加 `product`（可选，产品名或 ID）+ `productNotSpecified`（可选布尔）
- 新只读工具 `vod_search_products`（core）：问之前给 3-5 个候选，不让模型从 103 条里猜
- 会话记忆改进程内（每次宿主会话=新进程）+ 身份哈希进 Scope，避免多租户串；覆盖/改口即时生效
- 旧客户端兼容：`VOD_ALLOW_UNKNOWN_PRODUCT=1` 时走 legacy_default（low），不阻断老版本；
  默认关闭（新客户端必须问）
- 宿主产品映射**已删除**（2026-11-12 复评收口）：host.json `productDefault`、runtime.host_product、
  `_host_product()` 均无消费方，随本轮清理移除；候选只走 `vod_search_products`（零兜底）
- 话术三处统一：vod-core 铁律、vod-feedback-collect 第 0 步、路由插件、server instructions
  全部改为"产品未定先问一次，用户说不知道就 productNotSpecified=true"

回归锁 tests/test_product_ask.py（19 例，评审后补至）：唯一命中不问 / 无产品 -32010+候选 / 不知道→拒绝不兜底 /
无宿主映射→unknown+证据 / 多产品先问 / 记忆跳过第二次+改口覆盖 / 记忆过期 / 旧客户端 legacy_default /
候选检索 / draft 不阻断 / commit 强制。

未采（业界建议里不适用本仓的）：metadata 只做归因不参与业务判定这条我们已经在做（productSource
仅留痕）；五到七轮追问上限不采用（一次抱怨只问一次，不连环追）。

## D-hosts-2：宿主覆盖对齐到 huaweicloud-devkit 清单（2026-11-12，负责人要求）

负责人要求「opencode / codex / codex-desktop / codearts / codearts-work / atomcode /
workbuddy / dsh / hermes（含 hooks 插件）这些都要具备」。落地口径：

| 宿主 | 落点 | 条目形态 | 卸载语义 |
|---|---|---|---|
| codeartsdoer | ~/.codeartsdoer/codearts_cli.json | mcp.<n> = {type:local, command:[], enabled, environment} | 摘条目 |
| codeartswork | ~/.codearts/mcp/mcp_settings.json（旧址 ~/.codeartswork 回退） | mcp.<n> = {command:[], environment} | 摘条目 |
| codex | codex plugin marketplace（原生插件） | — | codex plugin remove |
| codex-desktop | ~/plugins/vod-devkit + ~/.agents/plugins/marketplace.json | marketplace.plugins[] {name, source} | 摘登记 + 删插件目录 |
| dsh | profile patch（insert 块）+ ~/.dsh/skills | — | 删 patch 段 + dsh plugin remove |
| hermes | hermes mcp add + ~/.hermes/plugins/vod-feedback-router | — | hermes mcp remove（插件保留说明） |
| opencode | ~/.config/opencode/opencode.json | mcp.<n> = {type:local, command:[], enabled} | 摘条目 |
| workbuddy | ~/.workbuddy/mcp.json | mcpServers.<n> = {command, args, env} | 摘条目 |
| atomcode | ${ATOMCODE_HOME:-~/.atomcode}/mcp.json | mcpServers.<n> = {command, args, env} | 摘条目 |
| generic | --mcp-config 指定 | mcpServers.<n> | 摘条目 |

三条纪律（与既有条款同源）：

1. **共享 JSON 只摘自己的键**：marketplace.json / mcp.json / mcp_settings.json
   都可能载着用户别的配置；codex-desktop 的 mcpConfig 指向共享 marketplace，
   绝不能走「整文件删」（本轮已在 `_cleanup_install_row` 加显式分支，否则卸载会删掉
   用户其它插件登记）。
2. **不引入遥测**：AtomCode/WorkBuddy 上游都在宿主 hooks 里塞遥测，我们只写 MCP 条目。
3. **未真机验证要标明**：本机没有 workbuddy / atomcode / codeartswork / codex-desktop，
   这四个按上游 targets.ts + agents/*.ts 的形态实现，host.json 的 notes 里写「未真机验证」；
   真机到位后补冒烟（`scripts/smoke_hosts.py`）。

## D-ops-1：工程化三件（doctor 分层 / 宿主矩阵 / 发版进 CI）＋ 只读项目识别（2026-11-12）

负责人拍板"先做 A 类（无执行风险）"。落点：

1. **doctor 分层报告 + explain**（`vod_mcp/diagnose.py`）：失败按
   环境/载荷/配置/技能/网络/插件 归层，每条给「原因 → 动作」；`vod-devkit explain`
   共用同一张关键词表。纪律：归层只按确定性关键词，未收录就如实进「未分类」，
   不做语义猜测（误归层会把运维带偏）。
2. **宿主安装矩阵**（`scripts/host_matrix.py`）：隔离 HOME 里 seed 用户配置 →
   install → 断言配置形态 → 按宿主配置真拉起 stdio 自证版本 → uninstall →
   断言条目消失且**用户自有内容原样保留**。CI 增 host-matrix job。
3. **发版进 CI**（`.github/workflows/release.yml`）：workflow_dispatch 选 bump，
   调用同一个 `scripts/release.sh --publish`（不另写一套），发布后必跑终态断言。
4. **只读项目识别**（`vod_mcp/detect_framework.py`）：语言按扩展名统计、框架只认
   清单里的显式依赖、跳过 vendor/node_modules、2 万文件上限（跑过 41s 全量索引
   卡死 UI 的教训）。不做"猜测比例"。

同批修掉一个真机缺陷（矩阵实锤）：codex 原生插件自带的 `.mcp.json` 写的是
`command="vod-devkit" + args=["serve"]`，依赖 PATH 上的全局包——机器上装着旧版
（实测 0.4.2）时，配置与技能都是新的、**工具面却是旧的**。现在安装期把它改成
绝对解释器 + 载荷副本（与其它宿主同一条"入口不依赖 PATH"铁律）。

不做（仍是 B 类，需业务决策）：审批令牌、沙箱、凭据 onboarding、云 CLI 面。

## D-host-verify-1：真机验证的可达边界（2026-11-12）

负责人要求"支持多种 agent 并完成真实的验证"。本机（Huawei Cloud EulerOS aarch64）实测结果：

| 宿主 | 本机可装 | 真机状态 |
|---|---|---|
| hermes | 是 | 装好，MCP + 路由插件，doctor OK |
| opencode | 是（1.19.5） | 装好，matrix PASS |
| codex | 是 | 装好；原生插件入口已改为载荷副本（旧版会跑 PATH 上的 0.4.2） |
| codex-desktop | 由 codex CLI 承载 | `codex plugin add vod-devkit@personal` + `codex mcp list` 显示 enabled |
| dsh | 是 | 装好，matrix PASS（10 工具） |
| codeartsdoer | 是 | 装好，`codearts mcp list` 显示 connected |
| atomcode | 是（v5.2.6 linux-arm64） | **本轮新装**：`atomcode mcp add --global` 写 ~/.atomcode/mcp.json，与我们写入的条目共存；matrix PASS |
| workbuddy | 否 | 桌面端（Win/macOS，官网用扫码下载），无 Linux 包 → 只能验形态 |
| codeartswork | 否 | 仅用户级桌面/工作台配置，官网未发布 Linux CLI → 只能验形态 |

纪律：矩阵 PASS 只证明"配置形态 + 载荷入口 + 拉起自证"这一层；宿主程序读不读得到、
会话里模型会不会真调，必须在那台装了宿主程序的机器上跑一次才算闭环。未闭环的宿主
在 host.json notes 里显式标注「未真机验证」，不许用矩阵 PASS 冒充。

## D-remote-2：远程面两条守卫（对齐 devkit verifySkillTree / remoteSurface）＋ 部署边界（2026-11-12）

对照 huaweicloud-devkit 的远程面实现（mcp-server-remote.ts + mcp-protocol.ts）补齐：

1. **构造期技能树自校验**（vod_mcp/remote_app.py: verify_servable_skills）
   SKILLS_ROOT 不存在 / 无目录型技能 / 技能缺 SKILL.md → 拒绝构造。
   理由同参照物：list_skills 由注册表驱动，技能缺失会"宣传 retrieve_skill 取不到的名字"。
2. **每请求载荷自校验**（vod_mcp/transport_remote.py: payload_problems）
   按 30s TTL（payload.json mtime 作签名）校验副本 sha256 全集；被改/缺文件 → 503 + 问题清单。
   载荷目录来源优先级：VOD_PAYLOAD_DIR > 自身所在树（有 payload.json 即视为副本）。
3. **部署边界（写进文档，不写进代码）**
   绑回环 + 反代 TLS；**每个 agent 一把 engine key**（引擎按 key 身份算幂等/归因，
   共用一把会让不同 agent 的同句被判重）；远程面不吃 draft/commit/list_submitted。

同批修掉一个真机缺陷（做第 2 条时暴露）：
`vod_mcp/host_adapters/codex.py` 在 **import 期** 调 host_specs.load("codex")；
载荷副本不含 integrations/，于是远程面每个请求在请求线程里 KeyError → 500。
改为调用期 _spec() 惰性解析（同一类"import 期求值"缺陷，hermes 那次已修过一次）。
另外 payload_problems 一开始 import host_adapters.base，触发同样连锁：已改为不依赖该包。

真机验证：
  干净载荷副本（payload.stage 重打）→ HTTP 200，7 个工具；
  人为篡改 server.py 的副本 → HTTP 503「载荷校验未通过：vod_mcp/server.py …」

## D-attach-2 远程 attach 三个真机缺陷修复（2026-11-13，探活与身份传播）

全宿主安装演练（8 宿主真机）中实锤的三个缺陷，同根因链路（远程 attach 链路
"探活→hermes 注册→远程面身份"），一并修复：

1. **B1 hermes attach 静默假绿**（`host_adapters/hermes.py: install_remote`）：
   `hermes mcp add` 覆盖已存在条目时交互链是三问（Overwrite→认证→Enable
   tools），管道 `input="y\ny\n"` 只答两问 → hermes 端 Cancelled 仍 exit 0 →
   安装器打印"已注册"但 config.yaml 纹丝不动。修法：①stdin 喂不封顶 y 流
   （不数提示个数——hermes 升级加问不破）②rc=0 不算数：读回 config.yaml
   断言远程条目真落盘（`_hermes_registration_is_remote`，受限文本扫描
   mcp_servers 段，零 yaml 依赖红线不破），缺失即非零退出。
   教训记档：旧测试桩 hermes 只记调用不落配置，正是这个盲区让 B1 漏网——
   桩必须按真 CLI 的**可观察行为**模拟（注册落盘才算 rc=0 语义完整）。

2. **B2 探活不验 token**（`bin/vod-devkit: _probe_remote/_probe_remote_token`）：
   握手+工具面是连接级，坏 key 照装、首次提交才发现 401——与 --product
   fail fast 纪律不对称。修法：探活第 3 步经远程面真调 vod_auth_status 读
   keyCheck（引擎三态），rejected 拒装零副作用。

3. **B3 contextvars 不跨线程（最深的）**（`transport_remote.py` + `tools.py`）：
   远程面在 HTTP 线程 set 的 `_REQ_KEY/_SERVER_FACE` 传不到事件循环线程的
   on_call_tool（run_coroutine_threadsafe 不继承调用线程 context）——
   **请求头身份从未到达过 tools 层**（submit 报 -32012 是走运的本地态分支）。
   修法：身份经 scope（x_vod_key）传递、投递协程体内 set（协程链+to_thread
   可见，最小传播模型已实证）；auth_status 服务面下探请求头 key（新增
   requestKey 段）而非本地 JAVA_KEY。

**匿名场景区分（探针不误拦，引擎 401 原文是唯一区分依据）**：
- `_http` 401 原文透传（旧实现丢原文换固定文案=无法区分的根源）；
- probe_key 新增 device-mismatch 分类：引擎 401 原文「令牌与请求设备不匹配
  （设备绑定校验失败）」= 匿名令牌设备锚点漂移（token 有效、本机非签发设备，
  提交自动重领）→ 放行；「API Key 无效或已失效」= 真坏 → rejected 拦截。
- 真机矩阵：同机匿名令牌 attach 正常部署远程面 → verified 正常装（rc=0）；
  设备漂移 → device-mismatch 放行；真坏 key → rc=2 拒装零副作用；引擎不可达
  → unreachable 放行（网络≠key）。匿名链（stdio 面）不受任何影响。

测试锁：tests/test_remote_attach_b1b2.py（6 用例）+ test_auth.py 增
device-mismatch/rejected 对照用例 + test_remote_attach.py 桩 hermes 补
"真注册落盘"模拟。全量 447 passed（installer update 3 例失败为本地 origin
fetch 环境噪音，基线同款）。

## D-split-1：tools.py 按 pack 纵切（2026-11-15，结构债收口）

**背景**：tools.py 1368 行单体承载了 10 个 handler + 采集链 + 归因胶水 + 账本 +
草稿 + runtime.json 读写 + key 状态，域边界不存在；而 packs（core/collect/
knowledge）本来就是工具面的装配边界，两者错位。前置 P1 已把路径收敛到
`vod_mcp/paths.py`（挪文件不再重算相对深度）。

**切法**（按装配边界，不按文件名）：
- `vod_mcp/runtime_state.py` 运行期状态：runtime.json 读写/锁、账本、草稿、
  会话记忆、install nonce、日志、分发形态位。
- `vod_mcp/net.py` 出口与身份：`_http`、meta 缓存、key 探针、匿名令牌、
  `ToolError`、请求身份 contextvars（`_REQ_KEY/_SERVER_FACE/_eff_key`）。
- `vod_mcp/packs/{core,collect,knowledge}.py` 各 pack 的 handler 与其专属助手。
- `vod_mcp/tools.py` 降为 shim：契约装载 + `tool_specs` + `_HANDLERS` + `dispatch`。
- `vod_mcp/packs.py` → `vod_mcp/packs/__init__.py`（注册表放包里，保住
  `importlib.reload(vod_mcp.packs)` 重读 VOD_PACKS 的既有测试语义）。

**patch 面纪律（这是本次最容易出假绿的地方）**：拆分后
`monkeypatch.setattr(tools, "_http", fake)` 会写到 shim 上而**静默无效**。
三条锁（tests/test_p2_structure.py）：
1. shim 不得 re-export 已迁走的私有符号 → 写 shim 直接 AttributeError；
2. packs/*.py 禁止 `from vod_mcp.net import <符号>`（符号导入冻结引用）→
   一律模块属性访问（`net._http` / `rt._save_runtime`）；
3. patch 有效性：打桩到实现模块后，真实调用链必须命中假实现（HTTP 出口、
   `JAVA_KEY` 常量、状态落盘三条代表）。
90 处历史打桩点同批迁移到实现模块（`_http` 35 / `_load_meta` 29 /
`JAVA_KEY` 32 / `_RT` 22 / `_save_runtime` 13 / `_runtime_path` 12 …）。

**为什么不做"shim 属性转发"**：`__getattr__` 只能解决读，`monkeypatch.setattr`
的写不会传播到实现模块——转发等于把静默无效变成"看起来能打桩"。

**副作用**：mypy 作用域是整包（P1 反转），迁入的新模块默认被检查，本次为定位
补了 6 处类型标注/收窄（无行为变更）——这是"新模块默认被检"的预期成本。

**验证**：pytest 全绿（含新增 6 条结构护栏）；pyflakes 递归 0；mypy 36 文件 0 错；
host_matrix 9 PASS；pack_verify 150 文件 OK；双副本 diff CLEAN。

## D-bin-split-1：安装器按命令域拆分（2026-11-15，F8）

**背景**：bin/vod-devkit 1245 行单体同时装着 install / status / doctor / verify /
update / uninstall 六个子命令 + 版本烧录 + manifest 名册 + 技能指纹 + 远程探活 +
产品校验。命令边界本来就存在（argparse 子命令表），代码却没按边界分文件。

**切法**（`vodkit_cli/` 包，bin 只剩 20 行入口薄壳）：
- `common.py` 根定位 / build-info 烧录 / manifest 名册 / 技能指纹 / PRESETS / 形态位
- `remote.py` 远程面探活 + 安装期产品名录硬校验
- `install.py` 探测 → 门禁 → 载荷固化 → 宿主写入 → 技能拷贝 → manifest
- `doctor.py` status / doctor / verify / explain / detect
- `update.py` git ff 更新 + 版本跳过状态
- `uninstall.py` 按名册逐宿主摘除（共享配置只摘条目）
- `cli.py` argparse 子命令表 + serve 直通 + 分派

**对外稳定面**（入口薄壳 re-export + `__all__`）：`main / PRESETS / detect_targets /
build_info / write_build_info`——测试按路径加载 bin 后直接取这些名字。pyflakes 认
`__all__`，否则会误报"导入未用"。

**两个必须跟实现走的测试**（拆分时当场红出来的，正是 patch 面纪律）：
1. `test_doctor_repairs_dsh_patch_block` 原本 `monkeypatch.setattr(bin_mod.Path, "home", …)`
   再调 `bin_mod._repair_dsh_patch_block` —— 实现搬到 doctor.py 后这条会**静默写到真
   ~/.dsh**（各自的 pathlib.Path 是不同对象）。改为直接 patch `vodkit_cli.doctor`。
2. `test_presets_split_internal_external` 通过 AST 从 bin 源码里抠 `PRESETS` —— 改为
   从 `vodkit_cli/common.py` 抠，并反向断言 bin 里**不得再出现第二份 PRESETS 字面量**。

**打包**：package.json files 增 `vodkit_cli`；pack_verify MUST_HAVE 增
`vodkit_cli/cli.py` + `vodkit_cli/common.py`（漏打这个包=npx 装不上任何宿主，
属于"包能发但装不了"的静默故障）。

**验证**：pytest 全绿；pyflakes 0；mypy 44 文件 0 错（作用域同步扩到 vodkit_cli）；
host_matrix 9 PASS；pack_verify 166 文件 OK（含 vodkit_cli）；dsh 47；双副本 CLEAN。

## D-copies-generated-1：插件副本零提交（生成物），双漂移从构造上消失（2026-11-15）

**事故**（v0.5.8 实锤，两个方向）：
1. release.sh 先跑 sync_plugin.py，把根与插件副本**都**写成新内容，随后提交清单漏了
   `plugins/vod-devkit/contract` —— 所有基于工作区的 diff 检查恒绿（两边都是新版），
   而提交树里副本仍是旧版：npm tarball ≠ tag，直到发完版才靠人肉发现。
2. GitHub Actions 同一门禁假红：checkout 默认 fetch-depth=1 取不到 tag，
   registry_reconcile 把「tag 不可见」判成「没打 tag」。

**决定**：副本=生成物，零提交。
- `.gitignore` 全域排除 `plugins/vod-devkit/{vod_mcp,skills,contract,safety}` 与 `build-info.json`
- `scripts/sync_plugin.py` 是唯一生成入口；`package.json` 的 `prepack` 自动重跑（打包/发版不会再漏）
- `scripts/verify_copies.py` 单一门禁：四目录内容一致 **且** 副本零跟踪；pre-push / CI / release.sh 共用同一把尺
- release.sh：提交之后、打 tag 之前再验一次——这是唯一能抓「同步了但没提交」的位置
- 仓内消费者各自入口补一次 sync（tests/conftest session 夹具、host_matrix、codex 安装器兜底）
- registry_reconcile：浅克隆下 tag 缺失只提示不判红；CI checkout 改 fetch-depth=0

**为什么不选「保留副本 + 加更多门禁」**：根因是「两份真值」，加门禁只提高发现率，
漏一次就是又一次 tarball≠tag。零提交后这个矛盾不存在，做旧事也不可能。

**代价**：仓内直接跑安装/测试前需要一次 sync（已内置到各入口，毫秒级 copytree）。

## D-mcp-manifest-a3-1：插件 MCP 清单补规范字段，A3 静态形态按实测搁置（B1/C3，2026-11-15）

**背景**：对账 huaweicloud-devkit 后提出三个决策点（A：`.mcp.json` 形态；B：遥测；
C：新宿主 officeace/openclaw）。负责人拍板 A3/B1/C3；A3 落地前实测推翻了它的静态形态，
按实测改口径（下面如实记录，不粉饰）。

**A：实测先于偏好**
- 采纳的部分：`$schema`（agent-plugins.org 1.0.0，规范必填）+ `type: stdio` 补进清单；
  改写失败分类型处置；server.py 加解释器版本 guard。
- 推翻了的部分：A3 的 `command: python3` + `args: ["${PLUGIN_ROOT}/vod_mcp/server.py"]`。
  codex-cli 0.167.0 真机探针（探针插件落盘 argv/cwd/env，`codex app-server` 的
  `mcpServerStatus/list` 触发 spawn）实测：**args 收到字面量 `${PLUGIN_ROOT}`、
  cwd = `~/.codex` 而非插件根、`PLUGIN_ROOT`/`PLUGIN_DATA` 未注入**；把插件包迁到
  Agent Plugins 格式后该 MCP 条目**根本没注册**。规范承诺在该二进制上未落地。
- 因此清单保持 CLI 形态（`vod-devkit serve`）——唯一实测能跑通的入口；运行时正确性
  改由**安装器改写 + 读回验证**承担（改写从"优化"升格为必需），并让 `doctor` 直接报
  实际形态（payload / cli / placeholder / unreadable，后三种判问题，S115 兜着），
  不让"现在到底跑的是哪份"靠猜。
- 为什么不选 A1（npx）：把网络与 Node 塞进宿主启动路径，镜像滞后=ETARGET，npx 缓存
  又是新的版本漂移面；且它并不能解决"宿主最终跑哪份"的问题。
- A3 的收益按层说（保留下来待解禁）：
  - 走安装器 → 运行时无变化（改写已给绝对解释器 + 载荷）；
  - 不走安装器（marketplace 直装）→ 今天是"PATH 找 CLI，版本不确定"；A3 落地后
    才是"插件根锚定载荷 + 解释器不够就响失败"。
  - 解禁条件与复验方法写在 docs/design.md 同名节，不是留白。

**B1（采纳，与既有决策一致）**：零遥测。2026-11-03 已拍板"维持不做"，本次不是新决策。
按负责人要求补**重议触发器**（见上方待办条），避免单向门把承诺变负债。

**C3（采纳）**：officeace / openclaw **没有可安装的宿主**——没有安装包、没有 CLI、
没有配置落点，也没有宿主规格。不是"排期"或"等使用者"的问题，是不存在对象；
不设量化触发器（没有安装面可统计）。将来出现可安装形态再按同一套 integrations
宿主规格 + 适配器 + 用例补，不做提前适配（无消费者的适配层）。
覆盖现状：任意 MCP 宿主今天可走 `install --target generic --mcp-config <file>`。

## D-global-cmds-1：全局命令与多宿主消费面（2026-11-15，负责人要求"全部优化"）

**背景**：install-manifest 早就按宿主记多行（`installs[]`，D-installs-1），但消费命令
（status/doctor/update）只读顶层、uninstall 没有 --target。结果是"账本多宿主、视图单宿主"，
而 huaweicloud-devkit 的三条全局命令（version / packs status / uninstall --clean-global）
恰好都建立在这个视图上。

**决定**：
- 新增 `version`：manifest 的已装版本 + 宿主配置里**实际生效**的 packs 并排打。
- 新增 `packs status|enable|disable|all`：读宿主真实配置；写默认 dry-run，`--apply` 才落盘，
  只改受管条目 `env.VOD_PACKS`（首改 .bak、写后读回、core 强制、不可写 JSON 的宿主明说
  "需重跑 install"）。
- `install --target all`：只装探测到的专属宿主；generic 不参与（它是手填配置的兜底）。
- `uninstall --target` / `--clean-global`：按行摘+保留在用载荷；残留只清认得的（无
  payload.json 的载荷、含 vod-devkit 的 npx 缓存）。
- `status|doctor --target`：多行里选一行。
- 未知包 id：安装口与启动口都 exit 2（此前静默过滤，实测 `core,bogus` → `('core',)`）。

**为什么"读宿主配置"而不只读 manifest**：manifest 是我们写过的意图，宿主配置是现状。
宿主可能被手工改、被别的安装覆盖；只读 manifest 会把"以为的"报成"实际的"，而版本/能力面
漂移正是要发现的东西。

**为什么 dry-run 默认**：packs 写入会一次影响九台宿主配置。改配置这个动作的风险不对称：
少改一次只是没生效（可重跑），多改一次可能把别的宿主的键改坏（用户要自己修）。所以默认
只报将改什么，`--apply` 是显式动作。

**没做的（本轮边界，非遗漏）**：
- `packs_configure`（stdio 会话内开关 + 真推 tools/list_changed）：需要运行期工具面变更，
  与远程面无状态语义冲突，另行评估。
- `auth init` 向导与会话内 auth_switch、PreToolUse 真拦截：见 README/设计里的后续项，
  未在本轮落地，不许在文档里写成"已有"。

**代价**：多一套读路径（宿主配置解析）。用递归定位而不是九张硬编码表，新增宿主时
只需配置里存在该条目即可被识别。

## D-auth-init-1：凭据单入口（auth status / auth init）（2026-11-15）

**问题**：换 key 的唯一现实路径是"删 runtime.json 重装"。运维解释不了，也没有任何
命令能回答"这台机器现在用的是哪把钥匙、是哪一档"。

**决定**：
- `auth init --key <k> [--apply]` 是写 runtime.json 的唯一入口；缺省 dry-run。
- `auth status` 打印引擎地址 + 指纹 + 档位，并**区分显式 key 与匿名令牌**（后者是设备
  绑定领取的 token，不是 key；混称会让人以为配过 key——本机实测就出现过这种困惑）。
- 拒写规则：形态可疑（空白/过短）、引擎可达且判拒（401/-32012）；引擎不可达只告警
  （离线装机必须能走，网络问题不是 key 问题）。
- 明文 key 不进输出/日志/文档示例；回显一律指纹。
- 优先级链写进文档（2026-11-16 更正：与 `net._live()` 实现对齐）：
  环境变量 `VOD_JAVA_API_KEY`（最高）> runtime 里的显式 key（auth init 写入）> 匿名自动领取；
  禁令：不要把 key 写进宿主 MCP 配置 env（明文且随配置进 git）。

**没做**：会话内 `auth_init` / `auth_switch`（内存态切账号）——需要 MCP 工具面新增写入口。
（2026-11-16 补充：`vod_auth_ensure` 已提供"显式判 + 领匿名"的写入口，但不含切正式 key；
切 key 仍只有 `auth init` 一条入口。）

## D-skill-teaching-1：技能读取教法=动作优先（2026-11-15）

**决定**：`initialize` 的 instructions 直接给技能树绝对路径与读法（先直读 SKILL.md，
被拒/失败才回落 `vod_retrieve_skill`，绝不反复请求）；`vod_list_skills` 增
`skillRoot`/每技能 `path`/`version`/`references`/`readHint`。

**为什么**：把"能不能读"当运行时探测，而不是在文档里预判某个宿主能读/不能读——两类
预判都会错（openCode 有门控但可预授权；codex 沙箱基本不受限）。代价是第一次可能被拒一次，
可接受：回落路径不需要文件权限。

**边界**：远程面不给 `skillRoot`/`path`（未鉴权面不交安装路径）。实现点在
`skills_registry._server_face()`，不是只写在文案里。

## D-scope-guard-1：范围锁——云操作面不做，且用用例锁住（2026-11-15 负责人明确）

**决定**：本仓范围=用户声音采集（MCP server + 技能 + 声明式护栏）。对标 huaweicloud-devkit
只借工程形态，不借业务面：云服务技能/KooCLI/OBS/sandbox/open-mcp 网关/区域感知/服务目录
一律不做（无对象，且会把"窄面、单写面、零 DB"的形态撑坏）。

**为什么写成用例**：口头范围最容易在"顺手加个工具"里漂掉。S126 把三条硬边界做成断言：
包集合恒定、工具数恒定、工具名不得含云操作面词。要改这三条，必须改用例并在需求文档
留决策——这就把"范围变更"从默认动作变成显式动作。

## D-hook-unify-1：宿主钩子统一为"宿主无关脚本 + 宿主机制注册"（2026-11-15）

**问题**：预采集路由此前做成 hermes 插件包（`hermes-plugin/vod-feedback-router/`，走
`plugins.enabled` + 宿主进程内 import）。它带来三个成本：根目录多一个宿主特例、
只能适配有插件 API 的宿主、与宿主同进程（崩溃面共享）。对标 devkit 后确认：它们的
hermes 集成是 `config.yaml` 里的 shell hook，不是插件包。

**决定**：
- 资产：`hooks/vod_router.py`（单文件，stdlib），契约=stdin JSON → stdout `{"context": …}`；
  随载荷分发，任何宿主可注册。
- 注册：hermes 适配器写 `config.yaml` 的 `hooks.pre_llm_call`（外科式文本插入，形态不认识
  就抛错并给可粘贴片段；幂等按 `vod_router.py` 标记识别）。
- 迁移：install 时删旧插件目录 + 从 `plugins.enabled` 去名（否则双份注入）。
- uninstall 只摘含标记的那条 hook，别人的条目与其它事件不动。
- doctor：从"插件副本 hash 比对"改为"hook 是否注册 + 脚本是否存在 + 旧插件是否残留"。

**验证到哪一步（诚实）**：注册（config.yaml 条目）、`hermes hooks list` 识别、
`hermes hooks test pre_llm_call` 真拉起子进程并 `parsed (Hermes wire shape): {"context": …}`
三步实测通过；**真实会话注入未验**（需首次 consent 同意，`hooks list` 显示
`✗ not allowlisted`）。细节见 docs/hooks.md。

**没做**：`pre_tool_call` 拦截（读 runtime.json/env 导出）、codex/opencode 等价注册——机制已确认，
规则表与宿主覆盖另评（不在本轮硬塞）。

## D-structure-1：目录结构契约与根预算（2026-11-15 负责人要求通读对标）

**做法**：通读 devkit v2（adfd826）的实际目录（不是 README 的印象），抽出四条纪律
（一个插件包 / 源与生成物分离 / 共享资产单一落点 / 门禁脚本化），落成
`docs/architecture.md` 的结构契约 + `tests/test_structure_guards.py::test_s129_*` 的机械门禁。

**为什么用"根预算"而不是"目录规范文档"**：规范文档没人执行就会漂。S129 断言
`git ls-files` 的顶层条目必须落在预算表内——新增顶层目录/文件必须先改契约文档再改用例，
把"结构变更"从默认动作变成显式动作（同 S126 范围锁的做法）。

**分阶（不一次动完）**：S1 契约+预算+README（本次）；S2 共享资产收进 `src/`；
S3 运行时入口路径收进 `src/`；S4 运行期状态收进用户目录。顺序不能反：先让"资产有唯一落点"，
再改"谁在跑"，出问题才能二分定位。

**代价**：S2/S3 会触及 `paths.py`、`sync_plugin`、`payload`、`package.json files`、`pyproject`
与约十处测试路径，必须每阶独立可回滚。


**S3-A 落地（2026-11-15，实测口径）**：`vod_mcp/ vodkit_cli/` → `src/`（标准 src-layout，
`package-dir={"":"src"}` + `packages.find where=["src"]`）；资产 → `assets/`；hermes hook →
`integrations/hermes/hooks/`；`dsh/` → `packages/dsh/`。根定位从"`vod_mcp` 的父目录"一个算式
改成**两个根 + 入口显式设置**（`VOD_DEVKIT_SRC_ROOT` / `VOD_DEVKIT_DIST_ROOT`，`paths.py` 只读
不猜，旧布局回落只留到 0.7.0）。发布形态不变：插件副本与载荷仍平铺 `vod_mcp/skills/contract/
safety/hooks`，由 `sync_plugin`（新增 `EXTRA_PAIRS` 带 hooks）生成、`verify_copies` 校验。

**为什么不是"照抄 devkit 树"**：devkit 是 TS + `dist/` 编译产物，运行时根=发布包根，一个根够；
vod 是零依赖 Python 直跑 + 三种运行形态（仓内直跑 / 载荷副本 / 插件副本），必须显式区分
源码根与分发根，否则一处算式无法同时回答"包在哪"和"manifest 在哪"。

**顺手修掉的存量缺陷**：`[project.scripts] vod-devkit = "bin.vod-devkit"` 不是合法
entry-point（`pip install -e .` 实测 `ValueError`），改为 `vodkit_cli.cli:main`；`runtime.json`
迁出包目录（`DIST_ROOT/vod_mcp/runtime.json`），安装器落盘前建父目录。

**踩过的两个坑（已固化用法例/注释）**：① `bin/vod-devkit` 在 import 期写 `os.environ`
会被测试的 `SourceFileLoader` 加载触发出"外层根泄漏"，导致临时仓安装写到外层仓；
② conftest 设 `PYTHONPATH` 会让副本类用例的子进程 import 到外层包，掩盖副本布局问题。

## D-dsh-global-view-1：全局视图补账本外宿主（只读探测 dsh profile）（2026-11-16）

**问题**：`version` / `packs status` 的行数等于 `installs[]` 条数。dsh 由
`dsh-vod-devkit` 的 profile 依赖承载（`install --target dsh` 只装壳包与 patch），
安装器不写账本行，于是全局视图里它**连一行都没有**，连 `[missing]` 都不给（那个提示
只服务"账本有行、配置没条目"）。对外说"一次看整台机器"就是失真的。

**决定**：只读探测 `~/.dsh/profiles/*/package.json`，只列声明了 `dsh-vod-devkit`
（dependencies 或 `dsh.profile.bundles`）的 profile，输出 `dsh(<profile>)` 行：

- 版本取 `node_modules/dsh-vod-devkit/package.json` 的**实际安装版本**；取不到报
  「已装版本未知」并给 `dsh plugin add` 提示，**不回落到 spec**——`file:…tgz` 或范围号
  是意图，把意图报成现状正是这个命令要消灭的那类失真。
- 漂移时给可直接复制的重装命令（`install --target dsh --profile <p>`）。
- `packs` 面对 dsh 一律 `[n/a]` + "壳不走 MCP env、改 pack 需重装"；
  `enable/disable/all --target dsh` 打印"跳过"，**不写 profile、不留 .bak、不打印成功**。

**为什么不把 dsh 塞进 installs[]**：账本行是"安装器写过这个宿主"的事实记录，`uninstall`
会按行去摘配置、删目录；dsh 的卸载语义是 profile 依赖/patch，塞进去会把两条链混成一条，
uninstall 还可能误删壳依赖。视图缺失用探测解决，不靠改账本语义。

**代价**：多一条只读探测路径（`~/.dsh/profiles`），profile 存在但包没装下来时要靠
"已装版本未知"这句诚实文案兜，不能假装有版本号。

## D-packs-configure-1：会话内能力面开关（vod_packs_configure）（2026-11-16）

**问题**：能力面只有 `VOD_PACKS`（安装期写入宿主配置、启动期读一次）。改一个包要重启
宿主会话，且没有工具能回答"现在开的是哪几个包"——排查时只能读配置文件猜。

**决定**：core 包常驻工具 `vod_packs_configure`（stdio 面）：
`{"enable":[ids] | "disable":[ids] | "reset":true}` → `{packs, added, removed, tools,
changed, persisted:false, note}`。三层写面分工：CLI `packs … --apply`（持久/写宿主配置）、
本工具（会话内/进程状态）、`VOD_PACKS` env（平台注入/启动快照）。优先级：会话 > env。

**为什么不写宿主配置**：同一个概念出现两个写入口后，"谁把我配置改了"就不可回答；而且
MCP 工具改用户文件属于越界（与"卸载只摘自己条目"同一条纪律）。持久化面已经可解释。

**熔断是硬门禁**：`collect` 遇 `BREAKER_MARKERS` 时**显式拒绝**（`PackRefused` → 错误码
`-32015`），不做静默摘除。启动期 `_resolve` 的静默摘除+stderr 不变（那是"配置优先"的
既有语义）。两者给不同信号：一个是"配了但被安全策略摘掉"，一个是"你要求开、我拒绝"。

**协议面**：`initialize` 声明 `capabilities.tools.listChanged=true`；只有 `changed=true`
才在响应后追加 `notifications/tools/list_changed`（无变化不发，防客户端重拉风暴）。
`handle()` 允许返回 list，`main()` 逐条写出（stdio 上响应一行、通知一行）。

**远程面摘除**（加入 `REMOTE_WITHHELD`）：HTTP 面每请求现造 server、无会话状态，
开关会随下一个请求消失——"以为改了其实没改"比没有这个工具更坏。dsh 壳同理不提供。

**没做（本轮边界）**：不做跨会话持久化、不做按工具粒度开关（粒度是包，与 PACK_TOOLS
一一对应）、不加 `auth_switch` 之类的会话内账号切换（另一个评审项）。

## D-doctor-egress-1：doctor 报告出站面（代理生效值 + 引擎可达）（2026-11-16）

**问题**：doctor 只在配了 key 时才探引擎（`probe_key`），无 key 时对网络零结论；代理在插件
里完全没有可观测面（urllib 隐式读 `HTTPS_PROXY`，但没人能回答"现在走哪个代理"）。
故障现场最常见的两问——"这台机器出得去吗""走得是哪个代理吗"——doctor 都答不了。

**决定**：doctor 末尾固定两行，**只报告**：
- `出站代理`：env 生效值（含小写变体），`user:pass@` 一律掩码；未设时说"直连"。
- `引擎可达`：无条件探 `<apiBase>/…/external/meta`（4s、不重试、不带 key）；
  200=`ok`，401/403=`auth`（**可达**），其它=`unreachable` 只 warn。

**为什么不建 proxy.json**（devkit 建了）：文件 + env 两层就必须维护优先级链，且会出现
"我改了文件为什么不生效"。我们的代理能力由平台/CI 注入，插件不持有代理状态——没有第二种
真相就没有第二套排障。代价：无法为"这台机器的代理"做持久记录。

**为什么 401 算可达**：把"鉴权失败"报成"网络不可达"会把运维引向查防火墙/路由，而真正要
换的是 key。判定只回答传输层。

**退出码不动**：离线装机 doctor 必须能跑通；网络结论一律 warn。CHANGELOG/README 已同步写清。

**没做**：不写代理配置文件、不引入 requests（零依赖红线）、不做引擎分区域/多端点探测
（我们只有一个 base）。权限缝（宿主沙箱对 runtime.json 的读取门控）插件侧探测不到，
README 标"未验证"，不假装拦。

## D-key-guard-4：读 Key 拦截 hook（pre_tool_call，fail-open）（2026-11-16）

**问题**：`runtime.json` 里是引擎 key 明文（载荷副本里安装器故意不种 key，但仓内/历史
安装那份有），而排障时实测反复发生 `cat …/runtime.json`、`env | grep VOD_JAVA_API_KEY`。
技能里"排障只引指纹"是教法，没有机制；一旦打印，key 就进了会话、日志与模型上下文。

**决定**：`integrations/hermes/hooks/vod_guard.py` 注册到 Hermes 的 `pre_tool_call`
（已实测该事件是**阻塞**事件：stdout `{"decision":"block"}` 即拦）。判定只做两件事：
①命令含 `runtime.json` 且含读取类动词；②`env`/`printenv`/`set` 且点名 key 变量。
其它一律放行。

**fail-open 是铁律**：阻塞事件里脚本崩掉=所有工具调用都被拦，这是"最坏伤害半径"最大
的一类事故（比漏拦一次严重得多）。所以解析失败、字段缺失、异常一律零输出；用例里
专门有"坏 JSON → 零输出"的锁。可 `VOD_HOOK_READ_GUARD=0` 或
`hermes hooks revoke` 关闭。

**为什么不拦"未审批写"**：那层已有 MCP 的 `safety/policy.json` 与两段式（-32010/-32011）。
再加一层会让"到底谁拦的"说不清，且写路径误拦会直接卡住业务（读路径漏拦只是泄密面）。
一层一个职责，规则不重叠。

**为什么文案必须带替代**：拦截而不给路 = 把排障逼进死胡同，用户会直接关掉 hook。
所以 `auth status`（指纹）与 `env | cut -d= -f1 | grep '^VOD_'`（只看变量名）写进 block 文案。

**没做**：codex / opencode 侧等价注册（这两个宿主的 hook 形态未与本仓对齐，没做等于没有，
README 已按"未做"标注）；不做 `modify`（改写命令）——改写比拦截更难解释，且用户看不见。

## D-runtime-atomic-1：runtime.json 的跨进程一致性（2026-11-16，并行评审 P0）

**问题（三条实测，全部复现）**：
1. 一份载荷 `runtime.json` 被同机多个宿主的 server 进程共用，而 `_RT_LOCK` 是
   `threading.RLock`（进程内）→ 4 进程各写 25 次，落盘只剩 **36** 条（期望 100）。
2. 整文件 `write_text` 非原子 → 并发读会读到半截 JSON（实测出现 `JSONDecodeError`）。
3. 解析失败 `except: return {}` **静默归零** → 下一次任意状态更新把文件重写成只剩那一个
   键：`java_key` 消失、账本 0 条、`install_nonce` 重新生成（设备绑定换锚点，后续提交 401）。

**决定**：`_save_runtime` 三层保障——
- 进程内 `_RT_LOCK`（原有）+ **跨进程 `fcntl.flock`**（`runtime.json.lock`，POSIX）；
- **tmp + `os.replace`** 原子替换，tmp 先 chmod 0600（不留 0644 窗口）；
- 坏文件 `_quarantine_bad_runtime()`：备份成 `runtime.json.corrupt-<ts>` + **stderr 告警**后
  以空状态继续。

**为什么坏文件选"备份后继续"而不是"拒绝覆盖"**：拒绝覆盖会让插件在坏文件之后完全不能
提交/记账（用户看到的是"插件坏了"），而备份已经保住可恢复性。两者都不静默，区别只在
"停摆"还是"带着备份继续"——后者对用户更好，最坏伤害半径更小。

**为什么 Windows 退化而不是硬造**：无 `fcntl` 平台没有对等的成熟机制（`msvcrt.locking`
语义不同、需重试循环）。硬造一个会引入新故障面；README 按"仅 POSIX 覆盖"诚实标注。

**没做**：把 `_RT` 内存镜像收敛成"每次现读"（重构级，见评审建议第 1 条）——那是另一个
PR，且要先补"长驻进程里 runtime 改值"的用例。

## D-uninstall-skill-dest-1：卸载按 skillInstalls 定位技能落点（2026-11-16）

**问题（实测）**：`common.py` 写 manifest 时把**每一行**的 `skillsDir` 都填成
`HERMES_SKILLS_DIR`（单值形态的遗留），而 `uninstall` 只读 `row["skillsDir"]`：
- `uninstall --target opencode` 会去删 **hermes** 的技能副本（卸 A 删 B）；
- opencode 自己的 `~/.config/opencode/skills` 只在 `skillInstalls[]` 里，卸载路径从不读它
  （漏删），卸载后磁盘上留一份孤儿技能。

**决定**：技能清理按 `manifest.skillInstalls` 里 `host == target` 的 dir 摘；老 manifest
没有该键时，`skillsDir` **只对 hermes 行可信**（hermes 目录是本插件专属、可整目录删），
其它宿主**跳过**——没有落点信息时宁可漏删，也不许猜着删别人的目录。

**为什么不做"按目录内容反推宿主"**：那又是一次推断（同一目录可能被多个宿主共用），
而卸载是破坏性动作，判断依据必须是 manifest 里的事实（`skillInstalls` 就是为此存在的）。

**顺带**：`--clean-global` 的 npx 清理收窄到只删 `node_modules/vod-devkit`（同 hash 目录里的
其它包不碰，删空才删目录）；删掉重复的 codex 分支；`bin` 对继承到的不一致根加 stderr 告警。

## D-runtime-txn-1：读改写必须事务化（`_runtime_atomic`）（2026-11-16）

**问题**：第一轮的原子写只保证"写不撕裂"，不保证"读改写不丢"。`_ledger_append` 与草稿
存盘是 `_RT_LOCK` 内 `_runtime_cfg()` 读整份列表 → `_save_runtime({key: 整份})` 覆盖，
而 `_RT_LOCK` 只是进程内锁；跨进程时后写者用旧快照盖掉先写者。实测 4 进程各 25 条账本
只剩 40-53 条。门禁没抓到是因为用例写的是**不同顶层键**（合并在锁内天然安全）。

**决定**：新增 `_runtime_atomic(mutate)`——进程内 `RLock` + 跨进程 `flock` 一起持，
读 → `mutate(cfg)` → 原子写（tmp/`os.replace`/chmod 0600）。`mutate` 返回 `False` 表示
"不改不落盘"（如 `local_ledger=false`）。`_save_runtime` 退化为它的薄封装（差分更新）。

迁移点：`_ledger_append`、`vod_draft_voices` 写入、`vod_commit_voices`（**校验与单次消费
同事务**——锁外读 store 再锁内 pop，会复活别的已消费草稿）。`update_check` 的 4 处
"读 state → 整键写"同形态但属低价值（丢了只是重复提醒），暂留待下一批。

**为什么不在 `_save_runtime` 里包一层就完事**：它自己持锁；若调用方已持锁再调它，
同一进程对同一文件二次 `flock`（不同 fd）会**死锁**。所以锁只能出现在 `_runtime_atomic`
一处，业务侧必须传 mutate 而不是先读后写。

**门禁**：S139 用真实入口（`_ledger_append`）跑 4 子进程；旧代码上必红（实测 28/100）。

## D-state-read-1：身份类值调用期现读（net.JAVA_KEY/JAVA_BASE）（2026-11-16）

**问题**：`net.JAVA_KEY` / `net.JAVA_BASE` 是 import 期常量。MCP server 长驻，于是
`auth init --apply` 换 key、安装器改 apiBase、自动领取匿名令牌写回 runtime.json 之后，
运行中的进程仍用启动那一刻的旧值：用户"明明换了还是 401"、或提交打到旧环境；
`auth status` 与出口读的是同一份旧快照，自洽地错，排查时无从下手。

**决定**：改成调用期现读，优先级 env（平台注入）> runtime.json > `_RT` 镜像 > 默认。
保 patch 面——`net.JAVA_KEY` 走 PEP 562 模块级 `__getattr__`，**显式 set 过的值优先**
（既有用例与运维脚本都用 `monkeypatch.setattr(net, "JAVA_KEY", …)`）；模块内部一律调
`_java_key()` / `_java_base()`，因为模块内的全局名查找不触发 `__getattr__`。

**为什么保留 `_RT` 回落**：文件缺失/损坏时不能把出口打断（离线/首装）；且本进程刚写的
值先进镜像。**文件优先**保证外部改动能立刻生效。

**为什么不再写 `net.JAVA_KEY = token`**（自动领取令牌处）：一旦 set 过模块属性，
`__getattr__` 就永久失效，那份 token 又被冻结——这正是本次要消灭的形态。改为
`_runtime_update`（落盘 + 镜像）。

**测试适配**（诚实记录代价）：`setattr(net, "JAVA_KEY", "…")` 仍可用于"强制给一把 key"，
但**不能用来"清空"**（空串是 falsy，会走现读；要清空必须 `delenv` + 确保 runtime 无该键）。
"模拟 runtime 里已有旧令牌"的用例必须写状态（`_runtime_update`），而不是 set 模块属性，
否则回填新令牌后仍读到旧值。conftest 的 `_isolate_runtime` 同时清空 `_RT`——它是导入期
从**真实** runtime.json 读出来的快照，不清会让隔离用例读到真机安装的 key。

**代价**：每次出口调用读一次 runtime.json。提交/元数据是低频动作，实测无感；真有高频
只读路径再加 mtime 缓存，不预先加。

## D-matrix-isolation-1：矩阵的隔离要搬"宿主自己的家"（2026-11-16）

**问题**：`scripts/host_matrix.py` 在一次性 HOME 里跑九个宿主，但只搬了 `$HOME`。
hermes CLI 的家是 `HERMES_HOME`（不认 `$HOME`：`HOME=/tmp/x hermes profile list` 照样列出
真实 profile），于是"隔离安装"直接改写操作者真实的 `~/.hermes/config.yaml`——把
`mcp_servers.vod-devkit` 写成 scratch 载荷路径 + 桩地址 `127.0.0.1:9/stub`，scratch 一清，
真机 hermes 的 vod 工具永久掉线（"lost its stdio subprocess"）。codex 侧同理（`CODEX_HOME`，
此前已踩过一次 0.4.2 旧缓存）。

**决定**：矩阵 env 由 `_isolated_env(host, home)` 单点生成，按宿主搬自己的家
（hermes→`HERMES_HOME`，codex/codex-desktop→`CODEX_HOME`，dsh→`DSH_HOME`），并 pop 掉
继承来的 `HERMES_PROFILE` / `HERMES_CONFIG`。新增宿主前先确认它用哪个变量，别假设 `$HOME` 生效。

**已知降级（必须写在用例 docstring 里）**：空 `HERMES_HOME` 下 hermes CLI 会尝试自举依赖，
实测一次 install 卡到 300s 超时（整轮矩阵 FAIL）。所以沙箱里给 hermes 的 PATH 最前放一个
同名 shim（`exit 1` + 明确 stderr），适配器 best-effort 继续；矩阵断言落在"安装器写出的
条目 + 按条目拉起 server 自证"。真机生效入口由 D-audit-effective-1 的巡检负责——两件事
分开管，不互相冒充。修完后全量矩阵 9/9 PASS、耗时 ~7s（此前 300s+ 全挂在自举上）。

**硬证据**：矩阵前后真实 `~/.hermes/config.yaml` md5 一致（实测 6b229195… 两次相同），
`--host hermes` 仍报 PASS（9 工具 / 0.5.9）。

## D-audit-effective-1：巡检判"宿主实际生效的入口"，不判 manifest/排序（2026-11-16）

**问题**（两条假绿，同批实锤）：
1. hermes：巡检读 `~/.hermes/mcp/vod-devkit.json`（备片）。备片能跑通、而 `config.yaml`
   的生效条目指向已清理的 scratch 路径，巡检照报 PASS 8 工具。
2. codex：巡检 `glob(cache/*/*/*/.mcp.json)` 后排序取最后一份。`personal(0.5.4)` 与
   `vod-local(0.5.9)` 并存时永远选中 vod-local 报 0.5.9 PASS，而 codex 按 `config.toml`
   里 `enabled = true` 的 personal 跑 0.5.4（`/tmp/vod_mcp_server.log` 的 argv 实锤）。

**决定**：巡检一律判**生效入口**。
- hermes：读 `config.yaml` 的 `mcp_servers.vod-devkit`（零依赖窄解析；不 import yaml——
  它是 CI 门禁，PyYAML 不在依赖里，缺包时假红/假绿更难查）。解析不出 → DRIFT。
- codex：按 `[plugins."vod-devkit@<mkt>"]` 的 `enabled` 选市场（多个取第一个；一个都没有
  才回落 `~/.agents/plugins/marketplace.json` 的 name），报文里带市场名，便于事后审计
  "它判的是哪一份"。

**纪律**：判据指向"宿主真的会读/会拉起的那一份"，而不是"我们写下去的那一份"；
manifest 是记账，不是生效事实。

## D-test-isolation-1：测试隔离要切断"继承"，门的判据要落到真机快照（2026-11-16）

**问题**：`pytest` 跑到一半把九个宿主的 MCP 全弄挂（`lost its stdio subprocess`），
而测试自己只报 `FileNotFoundError`。链路：`scripts/host_matrix.py` 在 **import 期**
`setdefault` 了两个根 → 被 `tests/test_host_matrix.py` 当模块加载后泄漏进整场 pytest →
装机子进程把 `DIST_ROOT` 解析成真仓 → 账本写进真仓根、`payloadDir` 变成 pytest tmp →
后面的 uninstall 用例按账本删掉 `~/.vod-devkit/payloads/0.5.9` → 所有宿主入口失效。

**决定**：
1. 入口脚本**不在 import 期写 env**（`_pin_roots()` 只由 `main()` 调）。这是本仓已有的纪律
   （`bin/vod-devkit` 同样注释过），只是 `host_matrix.py` 漏了；漏一次就是"测试把真机配置
   改成沙箱路径"。
2. conftest 的 autouse fixture **只 pop 继承值**（`VOD_DEVKIT_MANIFEST` / `VOD_PAYLOAD_HOME` /
   `VOD_DEVKIT_{SRC,DIST}_ROOT` / `VOD_JAVA_API_KEY`），不强行改值。理由：装机用例在**克隆仓**
   里跑入口，账本应落在克隆仓根；强行指 tmp 会把 19 条正确用例打红（实测）。宿主的落点由
   各自 HOME/根派生，pop 完自然隔离。
3. 门禁用 **session 前后快照**而不是单条用例：受保护对象是真机三处
   （仓根账本 / 载荷根清单 / hermes config.yaml），不管哪个用例漏隔离，跑完就对不上。
   单条用例只能证明"我这条不写"，证明不了"整套不写"。

**代价**：每次 pytest 多三次 md5/目录列举（毫秒级）；真机本就该在测试期间保持不变，
这条门禁不引入任何生产依赖。

**验证**：改后全量 621 passed / 2 failed（`test_update_ff_pull_and_reburn`、
`test_update_refuses_when_tracked_conflict` 在 origin/main 的干净 worktree 上也红，
属既存问题，与本轮无关）；跑前后 manifest md5、payloads 清单、hermes config md5 三项一致。

## D-token-machine-1：匿名令牌是机器级身份，不是版本级（2026-11-16 负责人拍板）

**问题**：匿名令牌绑 `install_nonce`（设备锚点），非ce 存在于 `runtime.json`；而该文件落在
`DIST_ROOT/vod_mcp/` —— 装机形态下是 `~/.vod-devkit/payloads/<版本>/vod_mcp/`。
后果有两层：
1. **每次升级/重装都换目录 → 换 nonce → 重领令牌**，匿名档日限额重新计，历史账本断档。
2. 机器上实际有三份 runtime（载荷 / 仓内 `src/vod_mcp` / `packages/dsh/data`）→ 三个匿名令牌，
   限额拆散；`probe_key` 的 `device-mismatch`（"令牌有效但非本机签发"）就是 nonce 漂移的现形。
3. 并且没有"显式判 + 领"的工具：skill 想先确认身份再采集，只能靠首次提交副作用领取。

**决定**（负责人原话："一个机器都用一个 token，我觉得可以"→ 采纳）：

1. 状态目录机器级：`VOD_DEVKIT_HOME`（默认 `~/.vod-devkit/state`），`runtime.json` 落
   `<state>/runtime.json`。跨版本、跨宿主、MCP 单独部署共用同一份。
2. 解析优先级（**每次现读**）：`VOD_DEVKIT_HOME` > 机器级 state 已存在（存在即用）>
   旧 `DIST_ROOT/vod_mcp/runtime.json`（首启兼容）。旧路径是兼容位，不是并行真源。
3. 首启迁移：state 无 `runtime.json` 而旧位置有 → 复制一次（含 nonce / key / tier / 账本），
   旧文件不删。目的是改造当天不重领、不换设备锚点。
4. 装机把 `VOD_DEVKIT_HOME` 写进每个宿主的 MCP env（`server_env()` 单点），配置不依赖默认值。
5. 新增 `vod_auth_ensure`（core pack）：判 + 领，幂等；显式 key 被拒时**不领**（fail fast），
   不可达时**不领**（不把网络问题当身份问题）。`auth_status` 维持只读。

**代价**：匿名档限额变成"全机共享额度" —— 某宿主用量大会让其他宿主一起撞顶。这是负责人
明确选择的语义（比限额拆散、令牌满天飞更可解释）。另有部署边界：多容器/多副本各自一份
state（除非共享卷，而共享卷上的 flock 不可靠，**不做**支持）。

**远程面（同机独立进程）同步**（负责人 2026-11-16 澄清："远程是和插件在一台机器上，
MCP server 独立部署"）：远程与本地是同一套效果，不是多租户隔离——

1. 身份：请求头 Bearer 优先，无 Bearer 时领/复用机器级匿名令牌（旧"服务面不代签身份"
   的 -32012 硬守卫与 `auth_ensure` 的远程拒绝一并废除）。
2. 工具面：`REMOTE_WITHHELD` 收窄为只剩 `vod_packs_configure`；`vod_draft_voices` /
   `vod_commit_voices` / `vod_list_submitted` 远程同样可用。
3. 两段式放开的前置：草稿落 `owner = _session_key(client_info)`，commit 校验归属，
   跨 clientInfo 一律 -32011（旧草稿无 owner → 兼容放行）。
4. `vod_packs_configure` 仍不暴露：它是进程内状态，HTTP 每请求现造 server、多 agent
   共用会互相影响——这不是"隔离"能解决的问题。
5. **匿名代领护栏**（采纳评审 P0-2 的 A 半）：回环绑定开启代领（同机默认）；
   非回环绑定默认关闭，需 `--allow-anon-mint` 显式开启（`net.ANON_MINT_DISABLED`）。
   默认回环场景与本地 stdio 行为完全一致，不牺牲需求；直接暴露到非回环时
   不会出现"任何能连端口的进程都能用本机身份提交"。

**验证口径**：同机两宿主 `auth_status` 指纹相同；`payloads/0.5.9 → 0.5.10` 升级后指纹不变；
迁移保留 `install_nonce`；`ensure` 五分支按表返回；测试跑完机器级 state 快照不变（S143 门禁第 4 项）。

## D-attrib-binding-1：安装先验要有自指证据（2026-11-16 负责人拍板 A）

**问题**：`--product` 写入的安装绑定是归因链第 4 级兜底（`source=install_binding`），
命中后**不再问用户**。它与"缺产品先问一次（D-product-ask-1）"冲突：用户在 A 产品插件里
吐槽 B 产品、原话未点出产品名时，会被先验直接归到 A —— 正是 2026-11-12 删掉
`host_default`（"宿主产品也是一次推断，错归污染引擎幂等域"）的同一种病。

**决定（A 方案）**：先验只在**原话出现自指**时生效。自指词表
`attribution.SELF_REFERENCE`（"这个产品/这款产品/本产品/该产品/你们这个/你们的产品/
本平台/这个平台/这个系统/你们家/你们这/咱这个/咱们这个/这插件"）。命中 → 承认先验，
`evidence=[{alias: 自指词, snippet: 上下文, reason: self-reference}]` 可审计；
不命中 → `source=unknown`，回到"先问用户一次"。

**取舍**：不采用 B（彻底删先验）——单产品部署每次多问一句，体验代价大且 dsh 壳没有
运行期问答通道；也不采用 C（维持无条件兜底）——无证据错归比多问一句更糟。
自指词表只放"指向当前语境"的词，不收录泛称"产品"（太容易误命中文档类正文）。

**验证**：`tests/test_attribution.py::test_s145_binding_requires_self_reference` /
`test_s145_binding_used_when_user_points_at_current_product`；
S96 用例同步改为"自指才归 + 无自指转 unknown"。

## D-dsh-mcp-b-1：dsh 工具面走 MCP client，壳只留 UI（2026-11-16 负责人拍板 B）

**背景**：参照物 huaweicloud-devkit 在 dsh 上不做专用 JS 工具插件，用 dsh 本体的
`@deepseek-ai/dsh-mcp-client` 把 MCP server 挂成宿主工具（工具名 `mcp__<server>__<tool>`），
profile patch 用托管块（start/end 标记 + 幂等 + 卸载只摘自己）。本机实测（0.2.1-rc.5）：
stdio 与 streamable-http 两条传输都通，模型能真调 `mcp__vod-devkit__vod_devkit_info`。

**决定（B 模式）**：
1. 有 mcp-client → 托管块里写两条 insert：mcp-client（工具面，12 工具 / 机器级 state /
   两段式 / ensure）+ 壳（`registerTools: false`，只留浏览器 UI 半）。
2. 无 mcp-client（版本门槛按 **dsh 本体** node_modules 探）→ 只写壳块（6 工具，降级），
   缺模块时用 `dsh plugin add` 自装，`VOD_DSH_SKIP_MCP_CLIENT_ADD=1` 可跳过。
3. **壳必须停止注册工具**（`registerTools=false`）：MCP 与壳同时注册 = 两个 submit、
   两套账本/令牌，用户可能重复提交。默认值保留 true（向后兼容旧 config / 降级形态）。
4. **卸载不得整文件删 `cordis.patch.yml`**：它是共享文件（用户与其它插件都往里写 insert 块）。
   本轮用例实锤旧路径会整份删除、连坐别人的块；改为只摘托管块。
5. SKILL 补指法：dsh 下工具名带 `mcp__vod-devkit__` 前缀，以 tools/list 实际名为准。

**代价/边界**：多一个 python 子进程、工具名变长；MCP 模式本轮只做 stdio
（`SUPPORTS_REMOTE` 仍 False，client 支持 streamable-http 但远程 attach 单独一轮）；
**UI 半不统一**——`client.jsx` 仍是浏览器直连引擎，agent 工具面与 UI 提交是两条链。

**验证**：`tests/test_dsh_mcp_mode.py`（S146-1..5：双 insert / 降级 / 幂等 / 卸载只摘自己 /
id 精确匹配）；真机取证用 `vod-devkit-verification` 技能的 `scripts/dsh-mcp-probe.py`。

## D-prune-payloads-1：旧载荷只报不删，清理走显式 `prune`（2026-11-16 负责人定案）

**背景**：每升一版在 `~/.vod-devkit/payloads/<ver>/` 落一份载荷（宿主入口指向它）。install
从不清理（只有 `uninstall --clean-global` 才动），真机上并存 0.5.9/0.5.10/0.5.11 —— 占盘，
更要紧的是"当前跑哪份"要靠人猜。

**决定**：
- `install` **永不隐式删**（安装时删用户文件不可回滚、误删风险高、用户没预期）；
- 新增显式命令 `prune --payloads`：默认 **dry-run**（只打印 版本/大小/路径 + 总量）；
  `--apply` 才删，交互式再问 y/N，**非 tty 必须 `--yes`** 否则 exit 2；
- **只删清单内**：`payloads/<ver>/` 且带 `payload.json`（`stage()` 落的那种）；没有该文件的
  手工目录/残留一律不碰，绝不按 glob 删目录；
- **保留**：当前版本 + 任何安装行 `payloadDir` 指向的版本；`--keep N` 额外保留最新 N 份；
- **只删载荷**，机器级 state（令牌/账本）不动；单条失败记录后继续，最后非零退出；
- `uninstall --clean-global` 复用同一实现（`payload.prune_candidates/remove_payloads`）。

**为什么不只挂 uninstall**：很多机器只升级不卸载，旧载荷永远留着。

**代价**：多一个要学的命令；靠 `doctor` 的载荷行（在用 X；未被引用 [Y]）降低认知成本。

**验证**：`tests/test_prune_payloads.py`（7 条：dry-run 不删 / 非 tty 拒绝 / 只删旧 /
keep 保护 / 无候选 / state 不动 / 候选集合）；真机 dry-run 输出 `可清理 2 份 1.1MB`。

## D-token-reuse-1：安装期校验复用 state 令牌 + 限流分层文案（2026-11-16 真机实锤）

**背景**：产品硬校验（D-product-id-2）每次都要一枚匿名令牌，而它**每次新签**，从不复用
`<state>` 里已有的。密集发版（每版都重装 9 宿主 + 巡检 9 次隔离装）把引擎限流打满：

```
POST /external/token → 429  同网络当日限 100 次（后来放宽到 1000，但仍撞）
POST /external/token → 429  同 IP 每小时限 60 次
```
后果是整批装机被"产品校验失败"挡下，而旧文案写"不可达"，把人往网络上带（实际踩过）。

**决定**：
1. 校验前先读机器级 state 的匿名令牌（`token_tier=anonymous`），命中就复用它，**device 用
   state 的 `install_nonce`**（S1 设备绑定要求令牌与设备配对），不再新签；
2. 401 换设备锚点重领一次再试（偶发"签发实例与校验实例不同步"能自愈）；
3. **429 立即停**（重试只会更糟）+ 专属文案：说清是"同网络/同 IP 的签发次数上限"，
   处置写正式 key / 明日再试 / 找运营调整限流；
4. 真网络异常仍报"不可达"并重试一次；空目录单独一档文案（指向 T7i 版本）。

**遗留（未修，下一轮）**：`host_matrix --audit` 每次隔离装 9 个宿主 = 9 枚令牌，是最大的
放大器；建议把已校验过的 productCatalog 落 state 缓存（TTL + `--refresh-product-catalog`），
巡检命中缓存就不再打引擎。

**验证**：`tests/test_install_product_auth.py`（6 条：401 一次重试过 / 401 两次报鉴权异常且
不许说"不可达" / 网络异常重试后报不可达 / 空目录单独文案 / 复用则不新签且 device 配对 /
429 不重试）。

**落地追加（S149，同日）**：名录落 `<state>/product-catalog.json`（base 键控 + 7 天 TTL +
`--refresh-product-catalog` 强刷；写走 tmp→`os.replace` + 0600，坏 TTL 按默认并告警；
"不在名录"文案给 `--refresh-product-catalog` 出路）；巡检走 `VOD_MATRIX=1` +
`VOD_SKIP_PRODUCT_CHECK=1` **双开关**才跳过校验（单用 skip 不得绕过
D-product-id-2 的硬校验——那行 env 被从审计日志抄去单用就会装出产品归属未验证的机器）。

## D-matrix-probe-1：巡检探针必须让"被装的那份载荷"自证（2026-11-16 真机实锤）

**缺陷**：`host_matrix._pin_roots()` 把 `VOD_DEVKIT_SRC_ROOT`/`VOD_DEVKIT_DIST_ROOT` 钉在
巡检进程 env，`_probe` 又 `os.environ.copy()` 继承 → 载荷 server 的 `provenance._ROOT`
（= `paths.ROOT`，受 `VOD_DEVKIT_DIST_ROOT` 影响）去读**仓根** `build-info.json`：

```
载荷 0.5.11 目录 + 干净 env            → vod_devkit_info 自述 0.5.11 / 6c42fa79
同一个载荷 + VOD_DEVKIT_DIST_ROOT=仓根  → 自述 0.5.14 / 170bbd65
```
于是 8 个非 dsh 宿主**必然 PASS**（"9 PASS"里这部分不成立），巡检失去发现"载荷落后/指向
旧副本"的能力——正是它存在的理由。

**修法**：
1. `_probe` 子进程 env pop 掉三个根变量（除非 entry 的 env 显式声明）；
2. 新增**载荷文件自证**判据：读 entry 指向载荷目录的 `build-info.json`，版本必须 == 期望；
   文件不受 env 影响，比 server 自述硬；
3. 真机复验：修前 9 PASS → 修后 `0 PASS / 9 DRIFT`（载荷 0.5.11 / 壳 0.5.11 vs 构建 0.5.14）。

**验证**：`tests/test_host_matrix.py::test_s150_probe_rejects_entry_pointing_at_old_payload`
（entry 指向旧载荷 + 进程被钉仓根 → 必须 DRIFT）与 `test_s150_payload_version_helper...`（S150）。

## D-doctor-repair-1：doctor 自愈不得改变/切断 dsh 托管块（2026-11-16 真机实锤）

**缺陷**：S58 的自愈逻辑用 `lines[j].strip().startswith("- ")` 猜块尾——而 B 模式的 mcp 块里
args 列表项形如 `- /root/.vod-devkit/payloads/<v>/vod_mcp/server.py`，被当成"下一组开头"：

1. 它从 `- id: vod-devkit` 一路切到 args 项，把托管块**从中间切断**（`vod-devkit-mcp` 的
   `id/name/config/args` 头全丢，只剩 env/cwd 尾巴）；
2. 再追加一个"只有壳块"的旧形态组；
3. 结果文件里出现两份 `- id: vod-devkit` → 之后每次自愈都 `refuse`，MCP 工具面静默丢失
   （audit 从"MCP 模式 PASS"变成"降级 PASS"，看起来还绿）。

**修法**：
- 完好判定改为**期望块文本比对**：`_patch_block(...)` 生成的块整体 `in text` 即视为完好（幂等）；
- 重建走 `upsert_patch`（**托管标记优先划界**），不再用 `- ` 猜边界；
- 多块/形态未知时只报告并给人工指引（"删掉 `start/end` 标记之外多余那份"），不动字节。

**验证**：`tests/test_dsh_mcp_mode.py::test_s151_doctor_repair_keeps_mcp_mode`
（降级形态 + 有 mcp-client → 自愈后必须同时有 mcp 块与 `registerTools:false`，且二次调用 no-op）。

## D-doctor-repair-2：自愈判据 = 结构化不变量 + 安装期真源（2026-11-16 评审实锤）

**缺陷**：D-doctor-repair-1 把"完好"定义成「安装器整块文本 `in text`」，而块内嵌三处
**进程级环境值**：`command: sys.executable`、`VOD_DEVKIT_HOME: machine_state_home()`、
`args: <payloadDir>/vod_mcp/server.py`。于是任何环境差异都被判成"配置损坏"并整块重写：

1. 换解释器跑 doctor（venv / 系统 / npx 各带不同 python）→ `command` 被改成"跑 doctor 的那个"；
2. 按公网反代形态手工设 `uiBase: /dsh` → 被回写成 apiBase（CORS 问题复发）；
3. PATH 里没有 `dsh`（systemd / cron / 非登录 shell / 别的用户）→ `mcp_ver=None` → 整块重写成
   降级形态：删掉 `- id: vod-devkit-mcp`、壳回到自注册，**12 工具 → 6 工具**（正是 S151 要防的事故）；
4. manifest 行缺 `payloadDir`（老账本 / skills-only 行）→ 重写成 `args: - vod_mcp/server.py` +
   `cwd: .` → server 起不来。

真机已发生：`/root/.dsh/profiles/web/cordis.patch.yml` 的 command 是 Hermes 3.14 的 python，
`headless` 是安装期 venv python——两份不一致即第 1 条的现场。

**修法**：
- `install` 把安装期真源落进 manifest 行：`dshPatch = {command, stateHome, mcpClient}`；
- 自愈改用 `block_facts()` 解析**结构字段**，只补形态缺口（缺 MCP 块 / 缺壳块 / 壳未
  `registerTools:false`）；已有块与记录不同时**只报告不改字节**（手工定制要留住）；
- 环境不可判定（无 `payloadDir` / 无 `dshPatch`）→ 不动字节 + 打印重装指引；
- 重建时 `_patch_block(..., python_exe=, state_home=)` 用记录值，不用进程值；
- 老 manifest 无记录时才回退环境探测（只为补形态缺口），并提示重装以固化真源。

**代价**：manifest 增加一个字段（golden 重录两行）；老账本的自愈退化为"只补缺口 + 提示"。

**验证**：`tests/test_doctor_repair_boundaries.py`（S152-1…5，先红后绿；探针复现见
`/root/.hermes/cache/scratch/doctor-probe*.py`）。

## D-installs-profile-1：dsh 账本行键 = (target, profile)，"在用"集合扫配置面（2026-11-16）

**缺陷**：`_install_rows` 只按 `target` 去重 → dsh 的 web / headless 互相顶掉，账本只剩一行：

1. doctor 只自愈最后装的那个 profile，另一个的块坏了没人管；
2. `uninstall --target dsh` 只摘一个 profile 的块；
3. `prune --payloads` 的在用集合只读 `installs[].payloadDir` → 两个 profile 版本一旦错位
   （`--profile web` 单独升级是标准用法），另一个仍在用的载荷被当孤儿删掉，宿主下次启动白屏。

**修法**：
- 行键改 `(target, (dshProfile or ""))`，同 profile 重装仍是覆盖；
- `payload.prune_candidates()` 与 `uninstall` 的 `in_use` 同时扫 `~/.dsh/profiles/*/cordis.patch.yml`
  的 args 指向的载荷根（配置面也算在用）；
- doctor 遍历账本里所有 dsh 行，逐 profile 自愈。
- `host_matrix.py --audit` 的 dsh 段逐 profile 判，并读 manifest 的 `dshPatch.mcpClient`：
  记录有 mcp-client 而 patch 无 `- id: vod-devkit-mcp` = **MCP 块被清（12→6 退化）→ DRIFT**；
  记录为空才是合法降级（PASS，报文注明"按配置面判"）。没有这条判据时，两种形态在 patch 文本上
  完全一样，巡检会把事故报成"降级 PASS"。

**代价**：status/roster 的输出多一行（多 profile 机器上）；in-use 集合多一次目录扫描。

**验证**：`tests/test_doctor_repair_boundaries.py`（S153-1 行键、S153-2 prune 扫 patch）。

## D-explain-codes-1：错误码解释表必须与 raise 点一致（2026-11-16 通读漏面）

**缺陷**：`explain` 面与代码分叉，且没有任何门禁：

1. `-32011` 的原因写成"产品不在名录里"——真实语义是**草稿/审批令牌不符**
   （collect.py:666-679：draft 过期、approvalToken 不匹配、草稿不属于当前客户端）；
2. `-32012`（net.py:181/310 令牌不可用）、`-32014`（net.py:159 非 https 且非回环）、
   `-32015`（packs/core.py:84 PackRefused 安全门禁）、`-32001`（net.py:184 上游不可达）
   在代码里 raise，表里全部"未收录"；
3. 上一轮（ff92e5f）把文档里的错误码清单改对了，这张命令面没跟——正是"通读"漏掉的第 N 面。

**修法**：表补全上述五条（原因取自 raise 点的真实语义）；新增门禁
`tests/test_explain_codes.py`：扫 `src/vod_mcp/**/*.py` 的 `code=-320XX` 全集，断言每个都
known 且三要素齐全，并单独锁 `-32011` 不许写成"名录"。

**代价**：新增一个跨文件扫描用例（慢 <1s）；以后新增错误码必须同批补表，否则门禁红。

**验证**：`tests/test_explain_codes.py::test_s154_every_raised_code_is_explained` /
`..._known_codes_are_self_consistent` / `..._32011_is_draft_token_mismatch_not_catalog`。

## D-dsh-patch-scalars-1：托管块外部标量一律 JSON 引号 + status 多行（2026-11-16 评审 P1/P4/P5）

**缺陷（实测）**：
1. `_patch_block` 把 product / apiBase / uiBase / VOD_PACKS 裸写进 YAML。`product: A: B`
   直接 `ScannerError: mapping values are not allowed here` → 整个 cordis.patch.yml 解析失败
   = profile 起不来；`classify_dsh_patch` 只看缩进/根节点，抓不到。当前名录里没有含 `:` 的名字、
   URL 形态也安全，所以目前不是故障，但是"名录一改就静默生成坏文件"的定时炸弹。
2. `status --target dsh` 只取账本第一条 dsh 行 → 两个 profile 只显示一个，另一台"安装对象"
   在用户视野里不存在（doctor --target 同）。
3. 自愈的"字段差异"只报 command/stateHome/入口/cwd/PYTHONPATH，product/apiBase/packs 变了不报
   —— 而这三项恰是重装会改的。

**修法**：
- 所有外部可控标量统一 `json.dumps(...)`（JSON 双引号就是合法 YAML 标量）；`block_facts` 解析时
  去引号，比较面与安装期记录同形；用例 `test_p4_patch_scalars_survive_yaml_parse`（含 `:` 与 `#`）。
- `status|doctor --target <t>` 列出**全部**匹配行（多行时 stderr 逐行标 profile）；
  用例 `test_p1_status_target_dsh_lists_all_profiles`。
- `dshPatch` 增记 product/apiBase/packs；差异报告面同步补这三项（P5）。

**代价**：patch 文本形态变化（外部标量多一对引号）——相关断言与 golden 同批更新；
老 patch 不受影响（读取侧两种形态都接受）。
