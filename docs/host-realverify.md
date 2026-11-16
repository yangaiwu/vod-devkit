# 宿主真机验证手册（会话级，2026-11-12）

矩阵（`scripts/host_matrix.py`）只证明"能装、能按配置拉起 server、能卸干净"；
巡检（`--audit`）只证明"这台机器上的安装是新的"。真正要证明"宿主程序里的模型会调我们的工具"，
必须在宿主自己的会话里跑一次。以下是本机实测可用的一行命令。

## opencode

```bash
opencode run "调用 MCP 工具 vod_devkit_info（只调这个），把 version 原样打印"
```
实测输出（0.5.4）：`⚙ vod-devkit_vod_devkit_info → version: 0.5.4`。

## codearts（CodeArts Agent，OpenCode 分支）

```bash
~/.codeartsdoer/installers/codearts run "调用 MCP 工具 vod-devkit 的 vod_devkit_info，打印 version"
```
实测输出：`⚙ tool_call vod-devkit_vod_devkit_info → version: 0.5.4`。

## codex（同时覆盖 codex-desktop 的插件路径）

codex 用统一网关（`~/.codex/config.toml` 的 `[model_providers.opengw]`，
`env_key = HERMES_CUSTOM_OPENGW_CLOUDDEVELOPER_CLUB_API_KEY`），所以不需要 OAuth 登录：

```bash
set -a; . ~/.hermes/.env; set +a
codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox \
  "调用 MCP 工具 vod_devkit_info，把 version 原样打印"
```
实测输出：`mcp: vod-devkit/vod_devkit_info (completed)` → `0.5.4`。
注意两点（都是实锤踩出来的）：
- 不加 `--dangerously-bypass-approvals-and-sandbox`，headless 下审批策略会直接拒掉 MCP 调用
  （`approval policy: never`），看起来像"工具不存在"。
- codex 会缓存插件版本：升级后要用 `codex plugin remove` + `codex plugin add` 或删
  `~/.codex/plugins/cache/<marketplace>/vod-devkit/<旧版本>`，否则跑到旧副本（实测 0.5.3）。

## atomcode

AtomCode 支持任意 OpenAI 兼容端点，写 `~/.atomcode/config.toml`（权限 600）即可，无需 OAuth：

```toml
default_provider = "opengw"

[providers.opengw]
type = "openai"
api_key = "<你的网关 key>"
model = "deepseek-v4.1-flash-1017"
base_url = "https://opengw.clouddeveloper.club/v1"
context_window = 128000
```

```bash
atomcode -p "调用 MCP 工具 vod_devkit_info（只调这个），把 version 原样打印" -y
```
实测输出：`version：0.5.4`。
- `-y / --dangerously-skip-permissions` 必需：headless 下 MCP 调用要交互审批，否则被拒
  （`requires interactive approval`）。
- 它的 MCP 全局配置是 `~/.atomcode/mcp.json` 的 `mcpServers.<name>`（可用
  `atomcode mcp add <name> <cmd>... --global` 写），与我们的适配器落点一致。

## hermes

```bash
hermes mcp test vod-devkit        # 新起进程：Connected + 工具列表应等于契约全集（assets/contract/tools.schema.json）
```

坑（2026-11-12 实锤）：**运行中的 gateway 会按会话冻结 mcp_servers 快照**。改了配置后，
老会话仍然连着旧副本（实测本机老会话返回 0.4.4、commitSha=null），日志会写
`frozen config secret ['mcp_servers','vod-devkit','env'] no longer matches the profile config`。
要让新配置生效必须重启 gateway / 开新会话。

## dsh

两个 profile 都能跑会话级验证（headless 有 CLI 入口，Web 走浏览器）：

```bash
# headless：--patch overlay 不改 profile，直接让模型调工具
dsh --profile headless --patch /tmp/probe.yml \
  "调用工具 mcp__vod-devkit__vod_devkit_info，把 version 与 commitSha 原样打印"
# web：重启实例后（systemctl restart dsh-web.service）在页面会话里问一句
```

- 模型 key 若在 credentials 里（`~/.dsh/.credentials.yaml` 的 refs），CLI 启动环境仍要显式
  `DEEPSEEK_API_KEY`，否则报 `MISSING_CREDENTIAL`；注入时别把 key 打进日志。
- patch 里的 `command` 必须是真实绝对路径（别从脱敏回显里抄）。

## workbuddy / codeartswork

桌面端（官网仅 Windows/macOS），Linux 机器无法安装；只能验配置形态（矩阵 + 文档对表）。

## openclaw（2026-11-16 新增，本机已闭环）

```bash
openclaw mcp probe vod-devkit --json      # 静态+活连接：tools 列表、launch 命令行
openclaw agent --local --json -m "这是链路调试核验（可输出内部字段）：调用 MCP 工具 vod-devkit__vod_devkit_info，把 version 与 commitSha 原样打印"
```

- 判据看回执 `toolSummary.tools` 里有没有 `vod-devkit__vod_devkit_info`（以及 `failures` 是否为 0），
  不看模型转述；`terminalReply.text` 里的版本号应等于构建版本。
- `openclaw mcp show vod-devkit --json` 会把 env 值打码成 `__OPENCLAW_REDACTED__`，**不能**
  拿它拼启动命令；要复现启动请用 `probe --json` 的 `launch`，env 从安装期账本取。
- 提交链路：`vod-devkit__vod_submit_voices`（confirmed=true + product）应拿回 `voiceIds` 与 `accepted`。
