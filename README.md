# vod-devkit

[![CI](https://github.com/yangaiwu/vod-devkit/actions/workflows/ci.yml/badge.svg)](https://github.com/yangaiwu/vod-devkit/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/vod-devkit)](https://www.npmjs.com/package/vod-devkit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.txt)

**成熟度：Beta（0.5.x）** —— 运行时接口与契约面稳定，安装/配置面在小版本间可能有
形态调整（每次在 CHANGELOG 写明）；对外采集口径（两段式同意、原话逐字、归因不问用户）
视为红线，不随版本放宽。

[English](README.en.md) | 中文

把 **AI agent 产品的用户反馈**原话送进 VOD（Voice of Developer）囤积区：MCP server +
技能 + 声明式护栏。纯采集形态——分析与运营归 vod-system 前端，不在本插件。

三条纪律（比骨架更重要）：

- **只采集**：插件的唯一写动作是调用引擎 HTTP API（`POST /external/voices`）。
  落库、配额、审计、身份判定全在服务端；本仓没有任何数据库连接代码路径。
- **身份随请求走**：stdio 面走本机匿名令牌（机器级一份，跨版本/跨宿主共享）；远程面优先取
  请求头 Bearer，没有时与本地同链——由服务端领/复用同一枚机器级匿名令牌（`vod_auth_ensure`
  可显式确认）。即"配置了就用配置的，没配置就领匿名"，本地/远程同一套语义。
- **归因不问用户**：产品由插件从用户原话字面解析（引擎名录别名），唯一命中才采信；
  多产品命中=歧义 → 落 UNKNOWN 由运营判。安装时的 `--product` 只是可选先验，**且只在原话
  出现自指（"这个产品/你们家/本平台"）时才生效**——没有语境支撑就不拿先验硬归，回到"先问一次"。
- **作用域隔离**：记忆/追问计数/voiceId 按作用域分桶，三种部署形态共用一条解析链
  （`_resolve_scope`）：stdio 用进程身份、远程用 MCP 标准会话、显式 agent 头用于跨会话共享。
  **拿不到任何标识时不读也不写**——宁可多问用户一次，也不把 A 的归因写进 B 的桶
  （错归进引擎幂等域，静默且难追溯）。
  `X-Vod-Agent-Id` 是**分桶提示不是身份凭证**：格式非法（含空白/换行/超长/非 ASCII）时
  忽略并降级到会话分桶，不报错；它不参与鉴权，也不提供任何安全性——对外场景需要
  可信身份时由反代注入并自己承担校验。

> **三种部署形态**（一 agent 一本地 / 一 agent 一远程 / 多 agent 共用远程）的安装命令、
> 隔离边界与自检方法见「[三种部署模式](#三种部署模式按场景选)」。

> **同机不要同时启用两个反馈采集技能**：若宿主已装 `huawei-cloud-vod-collector`（反馈→GitCode 工单）等同类技能，请二选一，或明确告之模型通道分工（建单 vs 收录进 VOD）。两边触发词重叠（体验差/有 bug/报告问题），同时启用会让同一条抱怨随机进其中一个通道。技能内已写「渠道边界」判据（看用户要的产物，不看词）。

## 前置条件

| 依赖 | 要求 | 说明 |
|---|---|---|
| Node | >= 18 | `npx` 引导器；dsh 宿主请按其官方要求（Node 24.9+） |
| Python | >= 3.10 | 安装器与 MCP server；可用 `VOD_PYTHON` 指定解释器 |
| 宿主 | hermes / opencode / codeartsdoer / codeartswork / codex / codex-desktop / dsh / workbuddy / atomcode / openclaw / officeace 任一（officeace 为桌面端，仅 Windows 上有安装面）（另支持 claude-code / cursor / windsurf / cline 等走 `--target generic`） | 用 `--target auto` 探测，或显式指定 |
| 网络 | 可达你的 VOD 引擎 | 缺省 `https://vod-dev.topxtopx.com`，可 `--java-api-base` 覆盖 |

远程面额外需要官方 MCP SDK：`pip install 'vod-devkit[remote]'`（stdio 形态零第三方依赖）。

### 装不上怎么办（四类实测失败，先按这个自查）

| 现象 | 判据 | 修法 |
|---|---|---|
| `No module named mcp` | 起了 `--transport remote` 却没装 SDK | `pip install 'vod-devkit[remote]'`（stdio 不需要） |
| 宿主侧工具面为空 / 启动失败 | 宿主 PATH 里没有能用的解释器（沙箱/精简 PATH） | 安装时钉解释器：`VOD_PYTHON=/usr/bin/python3.12 npx -y vod-devkit@latest install ...`；`doctor` 看 MCP 实际形态 |
| `ETARGET` / 拿到的还是旧版本 | npm 镜像滞后（npmmirror、内部镜像常见） | `npx --yes --registry=https://registry.npmjs.org vod-devkit@latest ...` |
| 更新了但行为没变 | codex 插件缓存跑旧副本（实测 0.4.2） | 重跑 `install --target codex`；`doctor` 会报"CLI 形态 / 载荷形态" |
| 安装期 `exit 2`：产品不在名录（拼写正确） | 名录缓存默认 7 天（`~/.vod-devkit/state/product-catalog.json`），刚上线的新产品查不到 | `install --refresh-product-catalog` 强刷；TTL 用 `VOD_PRODUCT_CATALOG_TTL`（秒，`0` = 禁用缓存，示例 `604800`）；矩阵/巡检内部可 `VOD_SKIP_PRODUCT_CHECK=1` 跳过校验 |
| 装机报"令牌签发被限流（429）" | 每次产品校验要一枚匿名令牌，密集重装会打满当日配额 | 等窗口或配正式 key；名录缓存会把"重复校验"从每次一枚降到 7 天一次 |

## 快速开始

```bash
npx -y vod-devkit@latest install --target auto
```

省略 `--target` 时安装器会自动扫描机器上的宿主（判据=宿主 CLI 在 PATH 或配置目录存在，
数据在 `integrations/<host>/host.json`，不硬编码）：

- 扫到 **1 个** → 直接装到它；
- 扫到 **多个** → 交互终端列出编号让你多选（`1` / `1,3` / `all`，回车取消）；
  非交互（CI/重定向）**不猜**，报错并提示 `--target <agent>` 或 `--target all`；
- 扫到 **0 个** → 交互终端问一次 target 名；非交互报错并列出支持列表；
- 一步全量：`install --target all`（`dsh` 缺 `--profile` 时跳过并说明，不算失败）。

装完**重启会话**才生效（宿主在启动时读取 MCP 配置）。插件只写配置、落载荷、doctor 读回——
宿主的进程/服务/重启方式归宿主自己，插件不声明也不执行（D-boundary-1）。随后自检：

```bash
npx -y vod-devkit@latest doctor   # 配置 + 技能名册 + build-info 三查（针对已装实例）
npx -y vod-devkit@latest status   # install-manifest：版本 / 来源 / 宿主 / 传输形态
```

`--product <产品名>` 是可选先验（仅在无字面证据且无记忆时兜底）；给了就会做名录
硬校验，拼错直接 `exit 2`，不给也能装。

### 全局命令（一次性看整台机器）

```bash
npx -y vod-devkit@latest version                        # CLI 版本 + 每个宿主已装版本 + 生效的能力包
npx -y vod-devkit@latest packs status                   # 各宿主实际生效的 VOD_PACKS（读宿主真实配置）
npx -y vod-devkit@latest packs enable collect           # 将改什么（默认不写盘）
npx -y vod-devkit@latest packs enable collect --apply   # 真写：只改受管条目的 env，重启用生效
npx -y vod-devkit@latest install --target all           # 所有探测到的宿主一步装全（缺 CLI 的跳过）
npx -y vod-devkit@latest uninstall --target codex       # 只摘这一个宿主，其它安装行保留
npx -y vod-devkit@latest uninstall --target codex --clean-global   # 并清载荷残留与 npx 缓存
npx -y vod-devkit@latest auth status                     # 引擎地址 + 凭据指纹 + 档位（key / 匿名令牌）
npx -y vod-devkit@latest auth init --key <k>             # 校验并显示指纹（缺省不写盘）
npx -y vod-devkit@latest auth init --key <k> --apply     # 写 runtime.json（唯一入口，0600）
npx -y vod-devkit@latest prune --payloads                # 列出可清旧载荷（默认 dry-run，不删）
npx -y vod-devkit@latest prune --payloads --apply --yes  # 真删（保留当前版本与在用的版本）
```

### 旧载荷清理（prune）

每升一版会在 `~/.vod-devkit/payloads/<版本>/` 落一份载荷（宿主入口指向它，与 npx 缓存解耦）。
旧版本**不会自动删**——install 永不隐式删用户文件（删错=某宿主配置指向的 `server.py` 消失）。
要收空间用显式命令：

- **只清清单内**：`payloads/<版本>/` 且带 `payload.json`（安装器 `stage()` 落的）；
  没有该文件的手工目录与残留一律不在此列，绝不按 glob 删目录；
- **保留**：当前版本 + 任何安装行 `payloadDir` 在用的版本 **+ `~/.dsh/profiles/*/cordis.patch.yml`
  里 args 指向的版本**（配置面也算在用——多 profile 各指一份时，另一个 profile 的在用载荷不许被删）；
  `--keep N` 额外保留最新 N 份；
- **默认 dry-run**（打印 版本/大小/路径 + 总量）；`--apply` 才删，交互式再问 y/N，
  非 tty 必须 `--yes`，否则拒绝执行（exit 2）；
- **只删载荷**，不碰机器级 state（令牌/账本）；单条删除失败记录后继续，最后非零退出；
- 拿不准先看 `doctor` 的 `[doctor] 载荷：在用 …；未被任何安装行引用 […]` 那一行。

### 装机失败：先分清"限流 / 鉴权 / 网络"（别一上来查网络）

`install` 会做**产品硬校验**（`--product` 必须在引擎产品名录里），校验需要一枚令牌。
引擎对令牌**签发次数**有限流，所以三种失败各有专属文案：

| 文案 | 含义 | 处置 |
|---|---|---|
| `令牌签发被限流（HTTP 429…当日/每小时…）` | 同网络/同 IP 的签发次数用满（密集装机、反复巡检、联调都会打满） | 配正式 key `VOD_JAVA_API_KEY`（不占匿名配额）；或等窗口（当日/整点）；或让运营调限流 |
| `引擎鉴权异常（HTTP 401）…刚签发的匿名令牌被校验侧拒绝` | 引擎多实例的令牌存储/缓存不同步 | 稍后重跑（安装器已自动重试一次）；持续出现找运营核对引擎 |
| `产品校验不可达（HTTPError/URLError…）` | 真网络/证书/代理问题 | 查 `--java-api-base`、出站代理、DNS |
| `引擎 meta 无 productCatalog…` | 引擎部署不完整/版本过旧 | 核对引擎是否已部署外部 API（T7i 及以上） |

安装器**优先复用**机器上已有的匿名令牌（`~/.vod-devkit/state`）而不是每次新签——所以正常
机器重装/巡检不会再撞限流；仍撞说明这台机器在密集装机（例如批量重装 + 反复跑巡检）。

凭据优先级：显式 key（`auth init` 写入）> 环境变量 `VOD_JAVA_API_KEY`（平台/CI 注入）
> 匿名令牌自动领取（设备绑定）。**换 key 不需要重启宿主会话**：插件在每次调用引擎前现读
runtime.json 的身份值（`auth init --apply` 之后的下一次提交立刻用新 key）。**不要把 key 写进宿主 MCP 配置的 `env`**——明文，且会随
配置进 git；`env` 只留给平台注入。

多宿主账本在 `install-manifest.json` 的 `installs[]`（按 `(target, dshProfile)` 去重——
dsh 的 web / headless 是独立安装对象，各一行）。`--target` 缺省
作用于全部行；`packs` 的写操作默认 dry-run，`--apply` 才落盘（首改留 `.bak`，写后读回验证，
`core` 强制包含）。`VOD_PACKS` 里出现未知包 id 时**安装口与 server 启动口都会报错退出**
——不静默过滤，免得"配了没生效"。

dsh 不在账本里（它是 `dsh-vod-devkit` 的 profile 依赖，安装器不写行），所以 `version` /
`packs status` 会额外**只读探测** `~/.dsh/profiles/*/package.json`，为每个装了壳的 profile
打一行 `dsh(<profile>)`：版本取 `node_modules` 里实际装的那份，漂移时直接给出
`install --target dsh --profile <p>`；`packs` 对它是 `[n/a]`（壳不走 MCP env，改面要重装）。

## 按宿主安装

五个宿主的装法一致（`install` 带 `--target`），差异在配置落点与注意点。
`doctor` / `status` / `verify` / `update` / `uninstall` 都是**针对已装实例**
（读 install-manifest），不带 `--target`。

### Hermes

```bash
npx -y vod-devkit@latest install --target hermes
# 验证 / 更新 / 卸载
npx -y vod-devkit@latest doctor
npx -y vod-devkit@latest status
npx -y vod-devkit@latest install --target hermes      # 更新=幂等重装
npx -y vod-devkit@latest uninstall
```

- 落点：`hermes mcp add` 写 `~/.hermes/config.yaml`，另存 `~/.hermes/mcp/vod-devkit.json`；
  技能装到 `~/.hermes/skills/devops/vod-devkit`
- 卸载只摘托管的 MCP 条目（走 `hermes mcp remove`），不动你的其它 server

### OpenCode

```bash
npx -y vod-devkit@latest install --target opencode
npx -y vod-devkit@latest doctor && npx -y vod-devkit@latest status
npx -y vod-devkit@latest uninstall
```

- 落点：`~/.config/opencode/opencode.json` 的 `mcp.vod-devkit`（无损合并，保留你的
  provider 等既有键）；技能装到 `~/.config/opencode/skills`
- **卸载只摘 `mcp.vod-devkit` 与本次装进去的技能目录**——共享配置文件与其它插件的
  技能永不整文件/整目录删除

### Codex

```bash
npx -y vod-devkit@latest install --target codex
npx -y vod-devkit@latest doctor
npx -y vod-devkit@latest uninstall        # 摘原生插件，不删你的 config.toml
```

- 形态：走 codex 原生插件（`codex plugin marketplace add` + `plugin add`），技能随插件
  渐进加载；`.mcp.json` 是 Agent Plugins 规范字段（`$schema` + `type: stdio`），入口为
  `vod-devkit serve`。安装器随后会把缓存里那份改写成「绝对解释器 + 载荷副本」并读回验证
  ——**这是运行时正确性的来源**：codex 0.167 实测不展开 `${PLUGIN_ROOT}`、cwd 也不是
  插件根，静态清单只能走 CLI，所以请用 `install --target codex` 装，别绕过安装器直装
- 采集熔断：未确认提交累计触发后 install 会拒绝装 collect，恢复需
  `--ack-suspension`（审计日志落在 `~/.codex/`）

### CodeArts Agent（codeartsdoer）

```bash
npx -y vod-devkit@latest install --target codeartsdoer
npx -y vod-devkit@latest doctor      # 会用 `codearts mcp list` 冒烟一次
npx -y vod-devkit@latest uninstall   # 只摘 mcp.vod-devkit，provider/model 保留
```

- CodeArts Agent 是 OpenCode 分支（`SCENARIO=codeartsdoer`，配置在
  `~/.codeartsdoer/codearts_cli.json`），MCP 段同 opencode schema；技能装到
  `~/.codeartsdoer/skills`
- 实测口径：写入后 `codearts mcp list` 显示 `✓ vod-devkit connected`
- **不要**写 `~/.codeartsdoer/mcp/mcp_settings.json`——那是项目级路径；用户级
  mcp_settings 读的是 `~/.config/opencode/mcp/`

### CodeArts Work（codeartswork）

```bash
npx -y vod-devkit@latest install --target codeartswork
```

- 落点：`~/.codearts/mcp/mcp_settings.json`（平台迁移后的新址；目录不存在时回退
  `~/.codeartswork/mcp/mcp_settings.json`），条目形态 `mcp.vod-devkit =
  {command: 数组, environment}`——环境键名是 `environment`，不是 `env`
- 技能装到 `~/.codeartswork/skills`

### Codex Desktop（codex-desktop）

```bash
npx -y vod-devkit@latest install --target codex-desktop
```

- 插件目录 `~/plugins/vod-devkit`（内含 `.mcp.json` 与 `.codex-plugin/plugin.json`），
  并在 `~/.agents/plugins/marketplace.json` 的 `plugins[]` 里登记一条
  `{name, source:{source:"local", path:"./plugins/vod-devkit"}}`
- 卸载只摘自己那条登记 + 删插件目录，不碰 `~/.agents/skills` 等原生目录

### WorkBuddy（workbuddy）

```bash
npx -y vod-devkit@latest install --target workbuddy
# 重启会话后：验证 / 更新 / 卸载
npx -y vod-devkit@latest doctor
npx -y vod-devkit@latest status
npx -y vod-devkit@latest install --target workbuddy      # 更新=幂等重装（不动其它键）
npx -y vod-devkit@latest uninstall
```

- 落点：`~/.workbuddy/mcp.json` 的 `mcpServers.vod-devkit`；技能装到 `~/.workbuddy/skills`
- 坑：WorkBuddy 只在 Windows/macOS 有客户端；Linux 上装它等于预置配置，宿主那边不读

### AtomCode（atomcode）

```bash
npx -y vod-devkit@latest install --target atomcode
# 重启会话后：验证 / 更新 / 卸载
npx -y vod-devkit@latest doctor
npx -y vod-devkit@latest status
npx -y vod-devkit@latest install --target atomcode      # 更新=幂等重装
npx -y vod-devkit@latest uninstall
```

- 配置根可由 `ATOMCODE_HOME` 覆盖（默认 `~/.atomcode`），落点 `mcp.json` 的
  `mcpServers.vod-devkit`；技能装到 `<home>/skills`
- 不装宿主的 `hooks.json` 遥测 hook（本插件不引入遥测）

### OpenClaw（openclaw）

```bash
npx -y vod-devkit@latest install --target openclaw      # 更新=幂等重装
npx -y vod-devkit@latest doctor
```

- 落点：`~/.openclaw/openclaw.json` 的 `mcp.servers.vod-devkit`。**该文件是 JSON5（可能带注释），
  安装器不直读也不直写**：一律经 `openclaw mcp add`（新装，带探活）/ `mcp set`（更新）/
  `mcp unset`（卸载），写后读回自证 command/args。
- 技能装到它的个人技能根 `~/.agents/skills`（`openclaw skills list` 里 source=agents-skills-personal）；
  `~/.openclaw/skills` 是 OpenClaw 自己的 managed 根，不往里写。
- 真机验证（2026-11-16，openclaw 2026.11.4 / Node 24.19 / aarch64 Linux）：`mcp probe` 报出的工具面与契约一致；
  `openclaw agent --local` 会话真调 `vod-devkit__vod_devkit_info`（版本=构建版本）；
  会话内 `vod-devkit__vod_submit_voices` 提交成功（accepted=1，voiceId 由引擎下发）。
- 坑：`npm i -g openclaw` 可能跑完 exit 0 却没落 `/usr/local/bin/openclaw`（本机实锤：只剩临时软链、
  node_modules 缺依赖）——装完先 `openclaw --version` 自检，必要时 `ln -sf ../lib/node_modules/openclaw/openclaw.mjs /usr/local/bin/openclaw`。

### 果办 OfficeAce（officeace，桌面端）

```bash
npx -y vod-devkit@latest install --target officeace      # 仅 Windows 有意义
```

- 无 Linux 包（官方只发 Windows 10/11、macOS 13+、HarmonyOS；npm 侧也无 CLI 包），
  **非 Windows 平台安装器直接拒绝**（exit 2），不做"看着装了"的假动作。
- 落点不是 JSON 而是它的 sqlite：`<InstallDir>/data/mcp-connectors.sqlite` 的 `mcp_connectors` 行
  （type=custom / transport=stdio / name=vod-devkit）；InstallDir 依次取
  `OFFICE_CLAW_CONFIG_ROOT` → `HKCU\SOFTWARE\OfficeAce\OfficeAce` 的 InstallDir → `%LOCALAPPDATA%/Programs/OfficeAce`。
- 写库前用 **sqlite 一致性快照**（`backup()` 在线备份，不是复制文件——远处桌面端可能开着库、WAL 里有未落盘事务）、事务写、写后读回校验；失败用快照回滚；不建表不改 schema（schema 不是我们的）；快照按天保留 7 天。
- **未真机验证**（本机无对象）：形态按参照实现（huaweicloud-devkit officeace-registry.ts）对齐，
  门禁只锁"非 Windows 拒绝 + sqlite 行域（幂等/只删自己/不建表）+ 回滚"。

### DeepSeek Harness (dsh)

> **每个 profile 是独立安装对象**：`install --target dsh` 一次只处理一个 profile（账本按
> `(target, profile)` 记账）。机器上有 web / headless 等多个 profile 时，升级要**各跑一次**
> `install --target dsh --profile <名>`；漏跑的 profile 会留在旧版本（或 MCP 块被清后退化成
> 只注册壳自带的工具面），`doctor` / `host_matrix.py --audit` 会逐 profile 报出来。

```bash
npx -y vod-devkit@latest install --target dsh --profile <profile名>
# 重启 dsh 后：验证 / 更新 / 卸载
npx -y vod-devkit@latest doctor
npx -y vod-devkit@latest status
npx -y vod-devkit@latest install --target dsh --profile <profile名>   # 更新
npx -y vod-devkit@latest uninstall
```

- `--profile` 必填（profile 名 = `ls ~/.dsh/profiles` 的目录名）；装的是壳包
  `dsh-vod-devkit`（npm 同名），配置幂等写进 profile 的 `cordis.patch.yml`
- **形态自动选择（0.5.10 起）**：dsh 本体有 `@deepseek-ai/dsh-mcp-client` 时，托管块写两条
  insert —— MCP stdio（工具名 `mcp__vod-devkit__vod_*`）+ 壳 `registerTools: false`（只留 UI 半）；
  缺依赖时安装器尝试 `dsh plugin add` 自装（`VOD_DSH_SKIP_MCP_CLIENT_ADD=1` 可跳过），
  仍补不上就降级为壳自带的采集面。判断形态只看 banner/工具计数这类**运行态自述**，不看 patch 缩进。
- `--mcp-url` / `--skills-only` 对 dsh 显式报错（远程 attach 仍未开）；远程面模式不覆盖 dsh
- 卸载会摘插件并从 patch 移除本插件的 config 块，不删其它插件段
- **降级形态（MCP 块拉不起来）才是"半套"**：只剩壳自带的采集面（submit / list_submitted / info /
  list_skills / retrieve_skill / check_update，没有 MCP 侧的 search_products / auth_* / draft / commit / packs_configure），
  并且**不共享机器级 state**（它有自己的
  `packages/dsh/data/runtime.json` 与 cap 200 环形账本）。MCP 形态下工具面与身份/账本与其它宿主一致。

## 其它 MCP 宿主（通用层）

没有专属适配模块的宿主不再"不支持"——通用层负责写配置或给片段：

```bash
# 已知形态（Claude Code / Cursor / Windsurf / Cline）：合并 mcpServers 条目
npx -y vod-devkit@latest install --target generic --mcp-config ~/.claude.json
npx -y vod-devkit@latest install --target generic --mcp-config ~/.cursor/mcp.json

# 不指定路径：只打印可粘贴片段，不写任何文件
npx -y vod-devkit@latest install --target generic
```

- **外科式合并**：只写 `mcpServers.vod-devkit`，其它 server 与用户自有键原样保留；
  首次改动前落 `.bak`
- 文件不是合法 JSON / 顶层不是对象 → 报错退出、字节不动（宁可不装不可装错）
- `--target auto` 在只探测到一个通用宿主时自动走通用写入；多个/零个要求显式指定
- 通用层只装 MCP 条目，不装技能（技能目录是宿主私有的；要话术层用 hermes/opencode/codex）

手写片段（把 `<repo>` 换成本仓绝对路径）：

```jsonc
{ "mcpServers": { "vod-devkit": {
    "command": "python3", "args": ["<repo>/vod_mcp/server.py"] } } }
```

MCP 已由别处注册、只想装技能话术时：

```bash
npx -y vod-devkit@latest install --target <hermes|opencode|codex> --skills-only
```

## 三种部署模式（按场景选）

| 模式 | 形态 | 隔离 | 适用 |
|---|---|---|---|
| **① 一 agent 一本地 MCP** | stdio，每 agent 一个进程 | 进程天然隔离 | 默认推荐，最简单 |
| **② 一 agent 一远程 MCP** | 每 agent 一个远程进程 + 独立 `VOD_DEVKIT_HOME` | 进程 + 目录 | 想集中部署但保持隔离 |
| **③ 多 agent 共用远程 MCP** | 一个远程进程服务多个 agent | **MCP 标准会话** | 一台桌面/一台机器多个 agent |

三者的归因、记忆、追问计数都按**作用域**隔离，业务行为一致。

### 模式 ① 一 agent 一本地 MCP（stdio）

在各 agent 自己的机器上装，进程随 agent 拉起：

```bash
npx -y vod-devkit@latest install --target <宿主> --product <产品名>
# 例：--target dsh --profile web --product CodeArts
```

- 零第三方依赖（stdio 形态不需要 MCP SDK）
- skill 文件随包本地部署，agent 可直接读 `skillRoot`
- 产品绑定写在本机 state，`--product` 可用

### 模式 ② 一 agent 一远程 MCP（独立进程 + 独立目录）

```bash
pip install 'vod-devkit[remote]'

# 每个产品独立目录 + 独立端口
VOD_DEVKIT_HOME=/opt/vod/codearts npx -y vod-devkit@latest install --target generic --product CodeArts
VOD_DEVKIT_HOME=/opt/vod/aishell  npx -y vod-devkit@latest install --target generic --product AIShell

VOD_DEVKIT_HOME=/opt/vod/codearts VOD_SINGLE_TENANT=1 \
  python -m vod_mcp.server --transport remote --port 9528 --host 127.0.0.1
VOD_DEVKIT_HOME=/opt/vod/aishell VOD_SINGLE_TENANT=1 \
  python -m vod_mcp.server --transport remote --port 9529 --host 127.0.0.1
```

⚠️ **`VOD_DEVKIT_HOME` 必须各不相同**，否则两个产品会互相覆盖同一份 `runtime.json`
（product 被后装的覆盖、nonce 相同导致 voiceId 撞车、账本互相盖掉）。

⚠️ **`VOD_SINGLE_TENANT=1` 决定安装期 `--product` 是否生效**（审查 P1-1，2026-11-19）：
远程面默认禁用安装先验（多 agent 共用时必错归），模式② 需要**显式声明单租户**才放开。
三个条件缺一不可：`VOD_SINGLE_TENANT=1` + `VOD_DEVKIT_HOME` 非空 + 请求不带 `sess:`/`agent:`
标识。不设这个变量时行为与多 agent 共用一致——**用户原话里没提产品就会 -32010 问一次**，
不会用安装绑定兜底。

宿主侧 attach：

```bash
npx -y vod-devkit@latest install --target hermes   --mcp-url https://<网关>/mcp --mcp-token <key>
npx -y vod-devkit@latest install --target opencode --mcp-url https://<网关>/mcp --mcp-token <key>
npx -y vod-devkit@latest install --target codex    --mcp-url https://<网关>/mcp --mcp-token <key>
```

写入前先探活（三步）：`initialize`（连接）+ `tools/list`（工具面必须等于
远程面工具集）+ **key 真伪**（经远程面真调 `vod_auth_status`，引擎三态：
`rejected` = API Key 无效 → 拒装且**不写任何配置**；`device-mismatch` =
匿名令牌设备锚点漂移（token 有效、本机非签发设备）→ 放行，首次提交或
`vod_auth_ensure` 时自动重领；引擎不可达 → 放行，网络问题不是 key 问题）。

### 模式 ③ 多 agent 共用远程 MCP

一台机器上多个 agent 连同一个远程端点。**服务端不要设 `--product`**（一份
runtime.json 代表不了所有 agent，硬用就是错归）：

```bash
npx -y vod-devkit@latest install --target generic        # 不给 --product
python -m vod_mcp.server --transport remote --port 9528 --host 127.0.0.1
```

隔离靠 **MCP 标准会话**：`initialize` 下发 `mcp-session-id`，客户端后续请求
自动回传，记忆/追问计数/voiceId 按会话隔离。**客户端无需任何额外配置**。

厂商兼容（自研裸 HTTP 客户端不握手时）：服务端自动内部握手兜底，客户端无感；
日志会出现 `[vod-devkit] 兼容模式：无 session 请求已内部握手`。看到这行说明
客户端未走标准握手 —— 能用，但每次调用独立会话（记忆不延续）。

自检：连上后看 server 日志
- **没有** `兼容模式` 那行 → 标准客户端，隔离完全生效 ✅
- **有**那行 → 客户端不标准，走兜底（可用、不串味、但记忆不跨请求）

### 远程面的通用约束（模式 ②③）

- **工具面 = stdio 减去 `vod_packs_configure`**（该工具是进程内开关，远端所有会话共用一个
  `Server`、包状态是模块级全局，一个会话 disable 会摘掉同进程其他 agent 的工具，故不提供；
  数量以运行期 `tools/list` 为准）。两段式草稿与本机账本同样可用——草稿按
  **会话**隔离（`_draft_owner`，只认会话/进程边界，**不认** `X-Vod-Agent-Id`），
  别的会话提交会被拒（`-32011`）；同一个客户端重连后会话变了会提示重新暂存，
  而不是报"不属于当前客户端"。
- **极端客户端兜底**：不支持 `mcp-session-id`、裸 POST `tools/call` 的客户端不会被
  400 拒绝，服务端内部握手补一个**共享哨兵会话**（进程内只占 1 个，不是每请求一个），
  并强制按"无会话"处理（不写记忆、不持久计数）——会话池不会因为这类客户端涨到上限。
- **身份**：请求头 Bearer 优先；没有时与本地同链，用机器级匿名令牌。
- token 承载：hermes 走 env `MCP_VOD_DEVKIT_API_KEY`（配置里只留 `${...}` 引用）；
  opencode 写在 `headers`（注意文件权限）；codex 走 `VOD_MCP_TOKEN`；**不给 token 也行**
  （配置里不写认证，提交走服务端匿名令牌）。
- **远程面不发布本机路径**：不给 `skillRoot` / `path`，规则文本用 `vod_retrieve_skill` 取。
- **`--product` 的边界**：它写进的是**执行安装那台机器**的 state。远程面与插件同机时
  server 读同一份 state（有效）；模式 ③ 下建议不设（见上）。
- **无内建鉴权**：本进程不校验身份，默认只绑回环；对外必须反代 TLS + 身份校验。
  **非回环绑定（`--host 0.0.0.0`）默认关闭匿名代领**，调用方必须带 Bearer；
  确需在可信内网共享本机身份，加 `--allow-anon-mint`。

端口被占用用 `--port <port>`（同步改 url）；`--host 0.0.0.0` 可开 LAN 访问。

## 遥测与数据

- **收集什么**：无。本插件不上报任何使用数据——没有遥测、没有埋点、没有用量统计，
  技能加载与工具调用都不回传。
- **不收集什么**：全部。反馈内容只在用户明确同意后发往**你配置的引擎地址**；插件
  不自建任何回传通道。
- **传输路径**：stdio 面由宿主进程直连引擎；远程面由请求头里的 key 标识调用方，
  身份不落服务器。
- **如何关闭**：无需关闭（本就没有）。若要不连引擎：`uninstall`，或把
  `--java-api-base` 指向你自己的实例。

## 工具面（契约唯一事实源：assets/contract/tools.schema.json）

| 工具 | pack | 类型 | 护栏 |
|---|---|---|---|
| vod_submit_voices | collect | 写 | confirm 逐次同意 + 单批<=50；走 Java `/external/voices` |
| vod_draft_voices | collect | 写（暂存） | 本机暂存 cap10/TTL600s，逐字回显；不触上游 |
| vod_commit_voices | collect | 写 | 一次性令牌 + payloadSha256 防调包，内部复用提交链 |
| vod_list_submitted | collect | 只读 | 本机提交账本（cap 200）——agent 替用户对账进度 |
| vod_devkit_info | core | 只读 | 版本 / commitSHA / 宿主 clientInfo |
| vod_auth_status | core | 只读 | key 指纹化自检 + 三步引导（无 key 可跑） |
| vod_auth_ensure | core | 写（身份） | 判定 + 领取匿名令牌（幂等；唯一有副作用的认证工具） |
| vod_search_products | core | 只读 | 名录检索（含主键 ID）：问用户"是哪个产品"前给候选 |
| vod_packs_configure | core | 写（会话内） | 会话内开关能力包；**仅 stdio 提供，remote 不提供**（远端所有会话共用一个 `Server`、包状态是模块级全局，一个会话 disable 会摘掉同进程其他 agent 的工具，2026-11-18 二次修正起继续摘除） |
| vod_check_update | core | 只读 | registry latest（24h 缓存 / 失败静默）；只提醒不升级 |
| vod_list_skills / vod_retrieve_skill | knowledge | 只读 | 领域规则技能披露（pack 裁剪即拒绝并给恢复命令） |

安全：`assets/safety/policy.json` 声明式规则拦 DB 直连意图与凭据读取；文本规则只扫结构性
字段，不误杀反馈内容里的凭据引用（引用与读取是两件事）。

## 质量与可验证性

```bash
python3 -m pytest tests/ -q        # 全量（单元 + 护栏 + packs + 安装器矩阵 + 协议级真 HTTP + stdio 回环）
python3 -m pyflakes src/vod_mcp src/vodkit_cli integrations/hermes/hooks tests
python3 -m mypy                    # 作用域见 pyproject [tool.mypy]（新增纯逻辑模块）
python3 scripts/secret_scan.py
python3 scripts/sync_case_roster.py --check   # docs 与花名册对账
python3 scripts/rules_provenance.py           # 技能与引擎真源对账（无引擎检出时 SKIP）
```

门禁清单：pre-push 钩子（pytest + pyflakes + secret_scan）+ GitHub Actions（镜像仓）+
双副本一致性（`vod_mcp` / `skills` 与插件副本逐字节）+ description 截断预算 +
install-manifest 名册对账（doctor 逐落点）+ 声明计数对账（对外文档不手写用例或工具数）。

本文档不放用例数/工具数——手写计数必然漂移；数字一律现场测量。

## 预采集钩子（hermes）

hermes 侧装一个**宿主无关的钩子脚本** `integrations/hermes/hooks/vod_router.py`，由 `~/.hermes/config.yaml` 的
`hooks.pre_llm_call` 注册：每轮对用户消息做确定性意图判定（关键词，模型不参与），命中就
往本轮用户消息追加一段采集指令，未命中零注入。

```bash
# 装完即可核对注册与真拉起（hermes 自带测试面，不需要开会话）
hermes hooks list
hermes hooks test pre_llm_call --payload-file payload.json
```

- 首次真实使用 hermes 会弹一次同意（consent 按 `(event, command)` 记）；`hooks list` 里
  `✗ not allowlisted` 就是"等你点同意"，不是装坏了
- 老版本装过插件形态（`~/.hermes/plugins/vod-feedback-router`）的机器，本次 install 会
  自动清理并摘掉 `plugins.enabled` 里的旧名字——否则插件与 hook 双份注入
- 细节（线协议、判据、验证到哪一步、两条 hook 的边界）见
  [docs/hooks.md](docs/hooks.md)

## 能力包与技能披露

- `VOD_PACKS` 三层：环境变量（平台/CI 注入，启动生效）；**会话内开关** `vod_packs_configure`
  工具（stdio 面：`enable`/`disable`/`reset`，立即改工具面并推 `tools/list_changed`，
  **不落盘、重启即清**）；CLI `packs enable/disable/all --apply`
  （持久，直接改写各宿主配置里的 `VOD_PACKS`，缺省 dry-run，`core` 强制包含）
  ⚠️ **`vod_packs_configure` 在远程面不提供**（工具面 = stdio 减去它）：远端所有会话共用
  同一个 `Server` 实例、包状态是模块级全局，一个会话 disable 会摘掉同进程其他 agent 的工具，
  等于一条调用打断所有人的采集。这是**进程级共享、当前 SDK 下做不到按会话隔离**，不是漏实现。
- 三层分工一句话：要**当前会话立刻变**用工具，要**以后都变**用 CLI，平台注入用 env。
  MCP 工具不写你的配置文件（持久化只走 CLI 这一个入口）
- 未知包 id：安装口、server 启动口与 `vod_packs_configure` 都报错并列出可用 id——不静默过滤
  （"配了没生效"最难查）；采集熔断期间开启 `collect` 会被拒（`-32015`，安全门禁不可绕过）
- 技能读取：stdio 面 `vod_list_skills` 给 `skillRoot` 与每技能 `path`，教法是**动作优先**
  （先直读 `<skillRoot>/<name>/SKILL.md`，被拒/失败才回落 `vod_retrieve_skill`，绝不反复请求）；
  远程面不给服务器本机路径，规则文本走 `vod_retrieve_skill`

## 安全模型

三层，顺序就是从便宜到贵：

1. **技能教**：`vod-feedback-collect` 规定先承接、再征得同意、原话逐字、不猜产品。
2. **钩子提醒**：pre_llm_call 命中采集意图时注入指令（防止模型把抱怨当排障问题去复现）。
3. **运行期护栏**：`assets/safety/policy.json` 的声明式规则 + 两段式草稿/令牌
   （`-32010` deny、`-32011` 草稿/令牌不符、`-32012` 无凭据/令牌不可用、`-32014` 非回环 http；
   归因**没有**本地错误码——`-32013` 已废除，改为运行期引导：原话唯一命中 > 显式参数 >
   会话记忆 > 安装先验，都没有就先问用户一次）
   + 护栏 deny 直连数据库意图。

诚实残留（写清楚，不掩）：

- 钩子分两条：`pre_llm_call` 只"提醒"（不拦）；`pre_tool_call`（hermes）会**真正阻断**
  "读 `runtime.json`"与"`env` 导出点名 key"两类动作，并给替代命令（`auth status` 只出指纹）。
  脚本任何异常都 fail-open（阻塞事件里崩溃会拦掉所有工具调用）；可 `VOD_HOOK_READ_GUARD=0`
  关闭。**codex/opencode 侧的等价注册未做**——那两个宿主上仍只有技能教法。
- 宿主对 `runtime.json` 的读取门控（沙箱规则 / allow 列表）**未验证**：插件侧探测不到宿主的
  权限策略，因此不声称"已拦"。降低暴露面的做法是 `runtime.json` 不种 key（安装器故意不把
  `java_key` 写进载荷副本，运行期走匿名令牌）+ `auth status` 只输出指纹。
- 远程面**不内置鉴权**：默认只绑回环，对外必须自建 TLS 反代与身份校验；身份优先取请求头
  Bearer，没有时按整机匿名令牌（同一台机器上的多 agent 共用一份，多租户场景请各带 Bearer）。
- 不允许把 key 写进宿主 MCP 配置的 `env`（明文且随配置进 git）——用 `auth init`。

## 目录结构（摘要）

```
src/            可导入 Python 包（真源）：vod_mcp/ 运行时、vodkit_cli/ 安装器
assets/         项目级资产（真源）：skills/ 技能树、contract/ 工具契约、safety/ 护栏策略
integrations/   宿主规格 host.json（探测/落点）+ hermes/hooks/vod_router.py（宿主侧钩子）
packages/dsh/   dsh 壳（独立 npm 包）              scripts/   生成器与门禁（成对）
plugins/        宿主发布物（清单 + 生成副本，副本零提交）  tests/  pytest（含结构/范围/花名册门禁）
docs/           架构/设计/需求/决策/安全/钩子      npm/ bin/  薄壳（找解释器 + 设根 + 透传）
```

**技能在哪**：真源是 `assets/skills/<技能名>/SKILL.md`（4 个：vod-core、
vod-feedback-collect、vod-problem-classification-rules、vod-scoring-rules）。
`plugins/vod-devkit/skills/` 与载荷 `~/.vod-devkit/payloads/<ver>/skills/` 都是**生成副本**
（v0.5.9 起零提交，`scripts/sync_plugin.py` 生成），不要在仓里找它们。

根目录条目受**预算**约束（`tests/test_structure_guards.py::test_s129_*`）：新增顶层目录/文件
必须先改 [docs/architecture.md](docs/architecture.md)（结构契约与迁移分阶）。

## 文档

- 结构契约：[docs/architecture.md](docs/architecture.md) ｜ 需求 / 设计：[docs/proposal.md](docs/proposal.md) · [docs/design.md](docs/design.md)
- 钩子规则：[docs/hooks.md](docs/hooks.md) ｜ 安全边界：[docs/safety-model.md](docs/safety-model.md)
- 一页纸：[docs/scheme-overview.md](docs/scheme-overview.md) ｜ 安全边界：[docs/safety-model.md](docs/safety-model.md)
- 决策台账：[docs/decisions.md](docs/decisions.md) ｜ 规则真源：[docs/rules-provenance.json](docs/rules-provenance.json)
- 架构缺陷台账（五维走查）：[docs/architecture-defects.md](docs/architecture-defects.md) ｜ 整改方案：[docs/architecture-remediation.md](docs/architecture-remediation.md)
- 手动配置与排障：[QUICKSTART.md](QUICKSTART.md) ｜ 分宿主细节：[INSTALL.md](INSTALL.md)
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md) ｜ 安全策略：[SECURITY.md](SECURITY.md) ｜ 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## 许可

MIT（见 LICENSE.txt）。第三方素材见 NOTICE。

## 诊断与识别（0.5.4 起）

```bash
vod-devkit doctor                 # 分层报告：环境/载荷/配置/技能/网络/插件，每条给动作
vod-devkit explain -32010         # 解释一条错误码/错误文案：层 + 原因 + 动作
vod-devkit detect --path .        # 只读识别项目语言/框架/构建（不写任何文件）
python3 scripts/host_matrix.py    # 全宿主安装矩阵：装→断言→拉起 server→卸→验干净（桌面端宿主在本机 SKIP；真实机器用 --audit）
```

矩阵 PASS 的**含义边界**（2026-11-16 收窄，别读成"宿主装得上"）：沙箱里的宿主 CLI 一律用
`exit 1` 的 shim 挡住（空 `HERMES_HOME` 下 hermes CLI 会自举依赖、实测卡到 300s），所以矩阵
验的是"安装器写出的条目 + 按该条目拉起 server 自证"，**不验 CLI 注册段**；真机生效入口用
`python3 scripts/host_matrix.py --audit` 判（它读 config.yaml 的生效条目与 codex 的启用市场，
报文里带判据来源）。

`doctor` 的失败按层分组，不再平铺一列 `FAIL`；`explain` 与它共用同一张规则表
（`vod_mcp/diagnose.py`），所以"报告里出现的层/原因"和"解释出来的动作"永远一致。

`doctor` 末尾固定打两行**出站面**（只报告、不改退出码，离线环境仍可用）：

```
[doctor] 出站代理：HTTPS_PROXY=http://***:***@proxy:3128；NO_PROXY=127.0.0.1
[doctor] 引擎可达：HTTP 401（可达；鉴权/路径响应）http://…/external/meta
```

- 代理只报 env 生效值（`HTTPS_PROXY/HTTP_PROXY/ALL_PROXY/NO_PROXY`），**不建配置文件**
  ——尊重既有 HTTP 约定；URL 里的口令一律掩码（doctor 输出常被贴进工单）。
- 引擎可达**无 key 也探**：401/403 算「可达」（鉴权问题≠网络问题），连不上只 `warn`
  （离线装机 doctor 必须还能用），且不因此改退出码。

状态文件（`runtime.json`）的并发与损坏处理：

- 同机多个宿主的 server 进程**共用**一份载荷 `runtime.json` → 写入走 tmp + `os.replace`
  （原子替换）+ POSIX `fcntl.flock`（`runtime.json.lock`）。**Windows 没有对等机制，未覆盖**，
  如实标注（那里仍是进程内锁）。
- 解析失败**不静默归零**：原文件备份为 `runtime.json.corrupt-<时间戳>` 并在 stderr 告警，
  随后以空状态继续——可人工恢复；不会出现"key 和账本一起消失且无人知道"。
