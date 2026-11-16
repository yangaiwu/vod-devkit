# dsh 反馈插件接入安装手册（dsh-vod-devkit）

适用：给 DeepSeek Harness（dsh）接入 VOD 用户反馈采集插件。装完后一个 dsh profile 里有**两半**：
浏览器「反馈」按钮（UI 半）+ agent 工具面（工具半）。

版本：dsh-vod-devkit 0.5.16（配套 vod-devkit 0.5.16）
实测环境：dsh 0.2.1-rc.5、`@deepseek-ai/dsh-mcp-client` 0.2.1-rc.5、Node ≥ 18、Linux/macOS

---

## 〇、先搞清两种形态（0.5.10 起）

dsh 本体自带 MCP client，所以工具面有两条路，装载时自动选：

| 形态 | 触发条件 | agent 看到的工具 | 壳做什么 |
|---|---|---|---|
| **MCP 模式（默认）** | dsh 本体 `node_modules/@deepseek-ai/dsh-mcp-client` 存在 | `mcp__vod-devkit__vod_*`，**12 个**（含 draft/commit、auth_ensure） | 只留 UI，`registerTools: false`，不注册任何工具 |
| **降级形态** | 没有 mcp-client（版本旧/自装被跳过） | 壳自注册的 **6 个短名**（vod_submit_voices、vod_list_submitted、vod_devkit_info、vod_list_skills、vod_retrieve_skill、vod_check_update） | 工具面由壳提供 |

- MCP 模式下 agent 侧与 hermes/opencode/codex **完全同一条链**：机器级 state（`~/.vod-devkit/state/runtime.json`）、
  两段式 draft→commit、`vod_auth_ensure`、packs 裁剪。
- 两种形态的采集纪律、同意前置、原话逐字完全相同，只差工具名前缀 —— **以宿主 tools/list 里的实际名字为准**。
- 壳同时注册工具是大忌（两个 submit、两套账本），所以 MCP 模式下安装器一定会写 `registerTools: false`。

## 一、前置条件

1. dsh CLI：
   ```
   npm i -g @deepseek-ai/dsh        # 需 pnpm；确认 dsh --version 有输出
   ```
2. 已有一个 dsh profile（如 web）：
   ```
   ls ~/.dsh/profiles
   ```
3. 准备两个值：
   - `产品名`：这条反馈归属的产品（生态看板口径，如 CodeArts），**无默认值**，
     装错=污染别的产品数据；
   - `引擎地址`：VOD 引擎根地址（形如 https://vod-dev.topxtopx.com），需引擎已部署外部 API
     （`/external/token`、`/external/voices`、`/external/meta`）。

## 二、安装

### A. 官方安装器（推荐）

```
npx vod-devkit@0.5.16 install --target dsh --profile web \
  --product CodeArts \
  --java-api-base https://vod-dev.topxtopx.com
```

> 在**任意空目录**执行（不要在 devkit 源码仓里跑——npx 会优先用本地包，版本可能滞后）。

安装器依次做四件事：

1. `dsh plugin --profile web add dsh-vod-devkit@0.5.16`（**版本是钉死的**——profile 的
   `package.json` 是精确版本，不带版本的 add 会被 pnpm 判"已满足"而跳过，升级后跑的还是旧壳）；
2. 探测 dsh 本体有没有 `@deepseek-ai/dsh-mcp-client`；缺则
   `dsh plugin --profile web add @deepseek-ai/dsh-mcp-client` 自装
   （离线/不想动 profile 时用 `VOD_DSH_SKIP_MCP_CLIENT_ADD=1` 跳过 → 降级形态）；
3. 幂等写 `~/.dsh/profiles/web/cordis.patch.yml` 的**托管块**（见 §三）；
4. 落技能文件 + 装机绑定（product/apiBase 写进 `~/.vod-devkit/state/runtime.json`）。

### B. 一键脚本（离线渠道，需手工补配置）

```
bash /opt/vod-install/vod-install.sh web   # 或从 http://<分发机>/vod-install/vod-install.sh 取
```
脚本只做「装包 + 覆盖技能文件」，**不写配置**——装完必须按 §三 补
`cordis.patch.yml`，否则插件起来了但没有 product，UI 入口不激活。

### C. 手工安装

```
dsh plugin --profile web add dsh-vod-devkit@0.5.16
dsh plugin --profile web add @deepseek-ai/dsh-mcp-client      # 想要 12 工具面就必须有它
```
然后按 §三 写配置。

## 三、配置（cordis.patch.yml）

文件：`~/.dsh/profiles/<profile>/cordis.patch.yml`

**MCP 模式**（有 mcp-client）——两条 insert，整块用注释标记包住（安装器幂等替换、卸载只摘这块）：

```yaml
# vod-devkit DSH integration start
- insert:
    - id: vod-devkit-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: vod-devkit                 # 工具名 = mcp__vod-devkit__vod_*
        transport: stdio
        command: /path/to/python3              # 安装器写自身解释器（stdio 零第三方依赖）
        args:
          - /root/.vod-devkit/payloads/0.5.16/vod_mcp/server.py
        env:
          PYTHONPATH: /root/.vod-devkit/payloads/0.5.16
          VOD_DEVKIT_HOME: /root/.vod-devkit/state
          VOD_JAVA_API_BASE: https://vod-dev.topxtopx.com
          VOD_PACKS: core,collect
        cwd: /root/.vod-devkit/payloads/0.5.16
        toolCallTimeoutMs: 30000
        failOnStartupError: false
    - id: vod-devkit
      name: dsh-vod-devkit                     # 不能省：靠它绑定浏览器半（按钮）
      config:
        registerTools: false                   # 关键：工具面交给 MCP，壳不再注册
        product: CodeArts
        apiBase: https://vod-dev.topxtopx.com  # Node 侧（降级形态的工具半）
        uiBase: https://vod-dev.topxtopx.com   # 浏览器半；公网反代时见 §五
        confirmWrites: false
# vod-devkit DSH integration end
```

**降级形态**（无 mcp-client）——同一托管块里只留第二个子项，且**不写** `registerTools`
（缺省 true = 壳照常注册 6 工具）。

四条硬规则（都踩过）：

1. **必须嵌套在 `- insert:` 下**（顶格的 `- id:` 会被 dsh 组合层静默丢弃，插件整个掉出组合树：
   banner、工具、UI 全消失）；
2. **`name: dsh-vod-devkit` 不能省**（靠它绑定浏览器半，省了=按钮不出现）；
3. **`- id: vod-devkit-mcp` 与 `- id: vod-devkit` 是两个条目**——手工改时别把 id 写成前缀重复，
   巡检/卸载按精确 id 认块；
4. 手工改完重启 profile。

## 四、验证（五项，缺一不算装好）

```sh
# 1) 壳的形态自述（MCP 模式一定打这一句）
dsh --profile web --no-open
#   MCP 模式：[dsh-vod-devkit] UI only（registerTools=false）：工具面由 MCP client 提供（serverName=vod-devkit，工具名 mcp__vod-devkit__vod_*）
#   降级形态：[dsh-vod-devkit] Registered 6 tools, apiBase=…, product=CodeArts

# 2) 块结构（两条 id + 标记 + registerTools）
grep -cE "vod-devkit-mcp|registerTools: false" ~/.dsh/profiles/web/cordis.patch.yml   # MCP 模式应为 2

# 3) 插件在册
dsh plugin --profile web list | grep vod

# 4) 页面入口（UI 半）：输入框右上角有「反馈」按钮，点击弹出「提交反馈」表单，
#    提交收到「已收录，产品团队会看到这条反馈」（回执里不显示编号属正常）

# 5) agent 工具面（MCP 模式）——让模型真调一次，看回执版本
dsh --profile headless "调用 MCP 工具 mcp__vod-devkit__vod_devkit_info，把 version 原样打印"
```

第 5 步是**唯一能证明工具面真活着的检查**：banner/配置都可能是旧的，模型回执与
server 日志（`/tmp/vod_mcp_server.log` 里 `started pid=… argv=[...server.py]`）才是证据。

宿主矩阵巡检（多宿主机器上用）：`python3 scripts/host_matrix.py --audit`，
dsh 那条应报 `MCP 模式（工具面 mcp__vod-devkit__*，壳只留 UI，壳 0.5.16）`。

## 五、公网部署（nginx 反代）补充配置

dsh 默认只监听 127.0.0.1；对外发布需 `--trusted-host <公网域名或IP>`（不在名单的 Host 会被 403），
并用 nginx 反代：

```nginx
location /dsh/ {
    proxy_pass http://127.0.0.1:3180/;
    proxy_set_header Host $host;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}

# 浏览器半的同源 API 通道：绕开引擎 CORS 白名单
location /dsh/rest/ {
    proxy_pass https://vod-dev.topxtopx.com/rest/;
    proxy_ssl_server_name on;
    proxy_set_header Host vod-dev.topxtopx.com;
    proxy_set_header Origin "";          # 引擎 CORS 只认自家域名，不剥 Origin 会 403
    proxy_http_version 1.1;
    client_max_body_size 1m;
}
```

公网形态把配置里的 `uiBase` 改成同源前缀：
```yaml
        uiBase: /dsh        # 页面实际请求 /dsh/rest/...，由 nginx 转到引擎
```
（`apiBase` 保持引擎绝对地址。）直接给远端绝对 `uiBase` 的症状：页面 console 报
`blocked by CORS policy … origin http://<公网IP>`，提交必失败。

## 六、身份与账本：两半各一份（重要，别混）

- **agent 侧（工具面）**：身份与账本在 `<VOD_DEVKIT_HOME>/runtime.json`
  （默认 `~/.vod-devkit/state/runtime.json`），**机器级**——同机 9 个宿主、跨版本升级、
  MCP 单独部署共用同一枚匿名令牌与同一条账本。
- **浏览器侧（UI 半）**：`packages/dsh/lib/client.js` 自带设备锚点
  （`localStorage: vod_dshui_device` + `X-Vod-Device-Id` 头）与自己的 token（`/external/token`），
  账本记在 `localStorage: vod_dshui_ledger`（环形 200 条）。
- 后果（当前设计，不是 bug）：**同一个人在页面点提交与让 agent 提交，是两套设备、两份额度、
  两条账本**；agent 的 `vod_list_submitted` 看不到页面提交，反之亦然。
- 要让两半合一，需要把 UI 提交改成经宿主后端代理调 MCP 工具（附机器级身份）——另行演进，
  在此之前**统一走 agent 工具面采集**可保证账本一致。

## 七、常见问题

| 症状 | 原因 | 处理 |
|---|---|---|
| banner 打 `Registered 6 tools` 但你以为该是 12 | 走了降级形态（没 mcp-client） | `dsh plugin --profile web add @deepseek-ai/dsh-mcp-client` 后重启 |
| banner 打 `UI only…` 但模型调不到 `mcp__vod-devkit__*` | MCP 块没生效 / 载荷路径不存在 | 按 §三 核对 command/args，`ls` 一下 payload 里的 server.py |
| grep 到 `registerTools: false` 但壳仍 `Registered 6 tools` | profile 里壳是旧版本（没有该字段） | `dsh plugin --profile web add dsh-vod-devkit@0.5.16` 显式钉版本 |
| 页面有 dsh 界面但无「反馈」按钮 | ① `name` 行缺失；② 装机副本旧；③ Host 不在 trusted-host | `dsh plugin list` 看版本；重装后重启 |
| 提交报「已暂存本机稍后重试」 | uiBase 缺失/不可达，浏览器请求落到 dsh 同源 404 | 按 §五 配同源通道或绝对 uiBase |
| console 报 CORS blocked | 跨域直连引擎，引擎白名单不含该 Origin | 用 §五 同源反代 |
| 重启后页面一直 `connection lost` / `ws failed` | 旧页面会话 cookie 随重启失效 | 用新 URL 重开页面 |
| 装了新版但跑的还是旧壳 | profile 依赖 specifier 钉在旧版本 | 用带 `@<版本>` 的 `dsh plugin add` 重装（0.5.16 起安装器已钉版本） |

## 八、升级 / 卸载

升级（**必须带版本**，否则 pnpm 认为已满足会跳过）：
```
dsh plugin --profile web add dsh-vod-devkit@<新版本>
```
或用安装器重跑一遍（等效，且会顺手更新 MCP 块里的载荷路径）：
```
npx vod-devkit@<新版本> install --target dsh --profile web --product CodeArts
```

卸载（0.5.16 起 `uninstall` 会正确摘块）：
```
npx vod-devkit uninstall --target dsh
# 或手工：dsh plugin --profile web remove dsh-vod-devkit
#         再从 cordis.patch.yml 删掉 `# vod-devkit DSH integration start/end` 之间那整块
```
> `cordis.patch.yml` 是**共享文件**（用户与其它插件也往里写 insert 块）：
> 只删标记之间的内容，别整份删。

## 九、交付物清单

- npm 包：`dsh-vod-devkit@0.5.16`（壳：UI 半 + 降级工具半）、`vod-devkit@0.5.16`（安装器 + MCP server 半）
- 技能文件：`vod-core` / `vod-feedback-collect` / `vod-problem-classification-rules` / `vod-scoring-rules`
  （安装器落 `~/.dsh/skills`）
- 支持渠道：VOD 运营；引擎接口变更需双方对账（外部 API 三个端点见 §一）