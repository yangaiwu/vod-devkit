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
