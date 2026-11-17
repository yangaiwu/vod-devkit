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

## 行为回归（e2e_behavior.py）的判定口径与退出码

跑法：`python3 scripts/e2e_behavior.py --host codex --suite [--model <名>]`
（`--model` 只改本轮 argv，不改宿主配置；网关模型在工具调用轮掉流时用它续验，见
`D-e2e-model-override-1`）。每轮头部打一行 `[e2e] host=… model=… argv=…`，
收尾打一行 `e2e[exit]=N reason=…`——**日志必须带模型名**，否则换模型跑出的结论事后无法审计。

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | 全绿 | 无 |
| 1 | **真违规**（有 fails） | 按违规桶处置；优先级最高，不会被环境结论盖住 |
| 2 | **熔断**（`config.action=exit` 且窗口内桶达阈值） | 停发版，查桶 |
| 3 | **不可判**：宿主回合无产出（空回复 + 零落库）或回执不可判（空回复 + 有落库） | 环境恢复后重跑；禁止记违规、禁止写成产品回归 |
| 4 | **鉴权或引擎 4xx**（`EngineAuthError`：401/403 等鉴权档/设备绑定/契约漂移） | 查 key 档位与 `X-Vod-Device-Id`（=install_nonce）；不是网络故障也不重试 |

三档「不是结论」的区别（别混报）：
- **引擎 5xx/不可达** → `EngineUnavailable`，exit 3；5xx 会先退避重试 4 次（S187）。
- **回执不可判**（S192）：回复为空但**有落库**——内容判据照跑（真改写仍记违规），只是回显线
  没结论；旧实现把这句塞进 fails → exit 1，等于把「流在最后一帧断」记成产品回归。
- **4xx**（S192）：按 ADR 是判定依据，要原样上抛、有明确出口；旧实现裸 traceback → exit 1。

## codex 的技能副本有三处，生效的是插件缓存那份（2026-11-17 实锤）

改 `assets/skills/**/SKILL.md` 后只同步 `~/.codex/skills/` 是不够的——codex 插件模式实际读的是：

| 落点 | 谁写 | 是否生效 |
|---|---|---|
| `~/.codex/plugins/cache/<market>/vod-devkit/<ver>/skills/…` | `codex plugin add` / 安装器改写 | **生效（实测：只有它影响模型行为）** |
| `~/.codex/skills/<名>/SKILL.md` | 安装器技能拷贝 | 存在但本轮实测不影响 |
| `~/.vod-devkit/payloads/<ver>/skills/…` | 安装器 stage | 载荷真源（prov 用），不直接生效 |

判据（改话术后必须三处一起对账）：`find ~/.codex ~/.vod-devkit -name SKILL.md -path '*<技能名>*' -exec md5sum {} +`
——出现两个不同 md5 就说明生效副本没刷新。实测过程：把新 SKILL 只拷进 `~/.codex/skills/` 后重跑 C1，
模型仍然追问产品；把同一份拷进插件缓存路径后才按新话术走。所以「话术改了但模型不照做」先查这条，
不要先怀疑措辞。
