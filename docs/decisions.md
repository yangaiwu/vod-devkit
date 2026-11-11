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
Bearer（缺 key fail fast、不代签匿名），身份边界成立，所以这条路我们能走而他们不能。

形态（`install --mcp-url <url> --mcp-token <token>`，或 env VOD_MCP_TOKEN）：
- hermes：`hermes mcp add vod-devkit --url ... --auth header`，token 经
  MCP_VOD_DEVKIT_API_KEY 注入，hermes 自己写 ${ENV} 引用（配置不落明文）
- opencode：`mcp.vod-devkit = {type:"remote", url, enabled, headers}`（token 明文在
  配置里，提示文件权限）
- codex：`codex mcp add vod-devkit --url ... --bearer-token-env-var VOD_MCP_TOKEN`
- dsh：不走 MCP → 两种模式显式拒绝（exit 2），不是静默降级

硬约束（都落成测试）：
1. **token 必填**：远程面不代签身份，无 token 装上也提交不了 → 直接 exit 2。
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
