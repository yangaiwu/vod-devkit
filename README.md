# vod-devkit

[English](README.en.md) | 中文

把 **AI agent 产品的用户反馈**原话送进 VOD（Voice of Developer）囤积区：MCP server +
技能 + 声明式护栏。纯采集形态——分析与运营归 vod-system 前端，不在本插件。

三条纪律（比骨架更重要）：

- **只采集**：插件的唯一写动作是调用引擎 HTTP API（`POST /external/voices`）。
  落库、配额、审计、身份判定全在服务端；本仓没有任何数据库连接代码路径。
- **身份随请求走**：stdio 面走本机匿名令牌；远程面只从请求头取 Bearer，缺 key
  直接拒绝、**不代签匿名令牌**（插件只搬运身份，不产生身份）。
- **归因不问用户**：产品由插件从用户原话字面解析（引擎名录别名），唯一命中才采信；
  多产品命中=歧义 → 落 UNKNOWN 由运营判。安装时的 `--product` 只是可选先验。

## 前置条件

| 依赖 | 要求 | 说明 |
|---|---|---|
| Node | >= 18 | `npx` 引导器；dsh 宿主请按其官方要求（Node 24.9+） |
| Python | >= 3.10 | 安装器与 MCP server；可用 `VOD_PYTHON` 指定解释器 |
| 宿主 | hermes / opencode / codeartsdoer / codeartswork / codex / codex-desktop / dsh / workbuddy / atomcode 任一（另支持 claude-code / cursor / windsurf / cline 等走 `--target generic`） | 用 `--target auto` 探测，或显式指定 |
| 网络 | 可达你的 VOD 引擎 | 缺省 `https://vod-dev.topxtopx.com`，可 `--java-api-base` 覆盖 |

远程面额外需要官方 MCP SDK：`pip install 'vod-devkit[remote]'`（stdio 形态零第三方依赖）。

## 快速开始

```bash
npx -y vod-devkit@latest install --target auto
```

装完**重启会话**才生效（宿主在启动时读取 MCP 配置）。随后自检：

```bash
npx -y vod-devkit@latest doctor   # 配置 + 技能名册 + build-info 三查（针对已装实例）
npx -y vod-devkit@latest status   # install-manifest：版本 / 来源 / 宿主 / 传输形态
```

`--product <产品名>` 是可选先验（仅在无字面证据且无记忆时兜底）；给了就会做名录
硬校验，拼错直接 `exit 2`，不给也能装。

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
```

- 落点：`~/.workbuddy/mcp.json` 的 `mcpServers.vod-devkit`；技能装到 `~/.workbuddy/skills`

### AtomCode（atomcode）

```bash
npx -y vod-devkit@latest install --target atomcode
```

- 配置根可由 `ATOMCODE_HOME` 覆盖（默认 `~/.atomcode`），落点 `mcp.json` 的
  `mcpServers.vod-devkit`；技能装到 `<home>/skills`
- 不装宿主的 `hooks.json` 遥测 hook（本插件不引入遥测）

### DeepSeek Harness (dsh)

```bash
npx -y vod-devkit@latest install --target dsh --profile <profile名>
npx -y vod-devkit@latest doctor
npx -y vod-devkit@latest uninstall
```

- `--profile` 必填（profile 名 = `ls ~/.dsh/profiles` 的目录名）；装的是壳包
  `dsh-vod-devkit`（npm 同名），配置幂等写进 profile 的 `cordis.patch.yml`
- **dsh 壳不走 MCP**：`--mcp-url` / `--skills-only` 对它显式报错；远程面模式不覆盖 dsh
- 卸载会摘插件并从 patch 移除本插件的 config 块，不删其它插件段

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

## 远程部署：MCP 单独部署 + 宿主 attach

一个远程端点服务多个宿主；身份随请求头走，不落服务器：

```bash
pip install 'vod-devkit[remote]'
vod-devkit serve --transport remote --port 9528 --host 127.0.0.1   # 前面需自建 TLS 反代
```

```jsonc
{ "mcp": { "vod-devkit": {
    "type": "remote", "url": "http://localhost:9528", "enabled": true } } }
```

宿主 attach（token 必填——远程面不代签匿名身份，缺 key 会被拒装 `exit 2`）：

```bash
npx -y vod-devkit@latest install --target hermes   --mcp-url https://<网关>/mcp --mcp-token <key>
npx -y vod-devkit@latest install --target opencode --mcp-url https://<网关>/mcp --mcp-token <key>
npx -y vod-devkit@latest install --target codex    --mcp-url https://<网关>/mcp --mcp-token <key>
```

写入前先探活（三步）：`initialize`（连接）+ `tools/list`（工具面必须等于
远程面工具集）+ **key 真伪**（经远程面真调 `vod_auth_status`，引擎三态：
`rejected` = API Key 无效 → 拒装且**不写任何配置**；`device-mismatch` =
匿名令牌设备锚点漂移（token 有效、本机非签发设备）→ 放行，首次提交自动
重领；引擎不可达 → 放行，网络问题不是 key 问题）。`doctor` 复查端点与
工具面。远程面与 stdio 面的实质差别：

- **工具面收窄**：草稿/本机账本类工具（`vod_draft_voices` / `vod_commit_voices` /
  `vod_list_submitted`）不在远程面——它们写"本机状态"，共享进程没有"本机"
- token 承载：hermes 走 env `MCP_VOD_DEVKIT_API_KEY`（配置里只留 `${...}` 引用）；
  opencode 写在 `headers`（注意文件权限）；codex 走 `VOD_MCP_TOKEN`
- **无内建鉴权**：本进程不校验身份，默认只绑回环；对外必须反代 TLS + 身份校验
- 技能自带传输面自适应：没有草稿工具 → 单发 + 回显，不承诺"草稿/两步"；没有本机
  账本工具 → 不承诺查询历史反馈

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

## 工具面（契约唯一事实源：contract/tools.schema.json）

| 工具 | pack | 类型 | 护栏 |
|---|---|---|---|
| vod_submit_voices | collect | 写 | confirm 逐次同意 + 单批<=50；走 Java `/external/voices` |
| vod_draft_voices | collect | 写（暂存） | 本机暂存 cap10/TTL600s，逐字回显；不触上游 |
| vod_commit_voices | collect | 写 | 一次性令牌 + payloadSha256 防调包，内部复用提交链 |
| vod_list_submitted | collect | 只读 | 本机提交账本（cap 200）——agent 替用户对账进度 |
| vod_devkit_info | core | 只读 | 版本 / commitSHA / 宿主 clientInfo |
| vod_auth_status | core | 只读 | key 指纹化自检 + 三步引导（无 key 可跑） |
| vod_check_update | core | 只读 | registry latest（24h 缓存 / 失败静默）；只提醒不升级 |
| vod_list_skills / vod_retrieve_skill | knowledge | 只读 | 领域规则技能披露（pack 裁剪即拒绝并给恢复命令） |

安全：`safety/policy.json` 声明式规则拦 DB 直连意图与凭据读取；文本规则只扫结构性
字段，不误杀反馈内容里的凭据引用（引用与读取是两件事）。

## 质量与可验证性

```bash
python3 -m pytest tests/ -q        # 全量（单元 + 护栏 + packs + 安装器矩阵 + 协议级真 HTTP + stdio 回环）
python3 -m pyflakes vod_mcp/*.py tests/*.py scripts/*.py bin/vod-devkit
python3 -m mypy                    # 作用域见 pyproject [tool.mypy]（新增纯逻辑模块）
python3 scripts/secret_scan.py
python3 scripts/sync_case_roster.py --check   # docs 与花名册对账
python3 scripts/rules_provenance.py           # 技能与引擎真源对账（无引擎检出时 SKIP）
```

门禁清单：pre-push 钩子（pytest + pyflakes + secret_scan）+ GitHub Actions（镜像仓）+
双副本一致性（`vod_mcp` / `skills` 与插件副本逐字节）+ description 截断预算 +
install-manifest 名册对账（doctor 逐落点）+ 声明计数对账（对外文档不手写用例或工具数）。

本文档不放用例数/工具数——手写计数必然漂移；数字一律现场测量。

## 文档

- 需求 / 设计：[docs/proposal.md](docs/proposal.md) · [docs/design.md](docs/design.md)
- 一页纸：[docs/scheme-overview.md](docs/scheme-overview.md) ｜ 安全边界：[docs/safety-model.md](docs/safety-model.md)
- 决策台账：[docs/decisions.md](docs/decisions.md) ｜ 规则真源：[docs/rules-provenance.json](docs/rules-provenance.json)
- 手动配置与排障：[QUICKSTART.md](QUICKSTART.md) ｜ 分宿主细节：[INSTALL.md](INSTALL.md)
- 贡献：[CONTRIBUTING.md](CONTRIBUTING.md) ｜ 安全策略：[SECURITY.md](SECURITY.md) ｜ 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## 许可

MIT（见 LICENSE.txt）。第三方素材见 NOTICE。

## 诊断与识别（0.5.4 起）

```bash
vod-devkit doctor                 # 分层报告：环境/载荷/配置/技能/网络/插件，每条给动作
vod-devkit explain -32010         # 解释一条错误码/错误文案：层 + 原因 + 动作
vod-devkit detect --path .        # 只读识别项目语言/框架/构建（不写任何文件）
python3 scripts/host_matrix.py    # 9 宿主安装矩阵：装→断言→拉起 server→卸→验干净
```

`doctor` 的失败按层分组，不再平铺一列 `FAIL`；`explain` 与它共用同一张规则表
（`vod_mcp/diagnose.py`），所以"报告里出现的层/原因"和"解释出来的动作"永远一致。
