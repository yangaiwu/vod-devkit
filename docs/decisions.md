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
- 引擎 !152 已合入 dev（ebdc6032）+评审线三轮追加（S1-S3 anchor/
  A2 设备绑定/tier-first R2/verbatim desc，V119-V120 幂等迁移）——
  插件零调整（401 自愈链原生兼容 A2；契约变化与既有删除同向）
