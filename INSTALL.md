# vod-devkit 安装指南

对标 [huaweicloud-devkit](https://www.npmjs.com/package/huaweicloud-devkit) 的
INSTALL.md 结构：每宿主一节（前置条件 → 安装 → 验证 → 常用命令）。
本插件的前置条件刻意做到最少：**Python ≥ 3.10，零第三方依赖，无账号要求**。

## 通用前置条件

- Python ≥ 3.10（宿主机任一 python3；安装器自动探测宿主运行环境）
- 无需 VOD 账号：未配置 key 时首次提交自动申请零字段匿名令牌
  （匿名档默认 30 天 / 5000 条、日 500 条，2026-11-09 提额；到上限或需要正式档时联系 VOD 运营升级）

## 安装（任意 MCP 宿主）

```bash
npx --yes vod-devkit install --target opencode --product codearts
```

- `--target`：`hermes` | `opencode` | `codeartsdoer` | `codex` | `dsh` | `generic` | `auto`
  （auto=探测已装宿主，0/1/N 个时提示；generic=任意 MCP 宿主，配 `--mcp-config <文件>`）
- `--product`：必填，采集反馈默认归属的产品（`--help` 内含权威名单；归因错误比报错糟，故 fail fast）
- `--java-api-base`：VOD 平台地址（缺省 `https://vod-dev.topxtopx.com`；本机同机部署可用 `http://127.0.0.1:<port>`——传输守卫只拦"非回环明文 http"）
- `--distribution preset`：产品随 agent 分发形态（禁 key 随包/禁自更新/客户机首启重生成状态；自装运维不要用）
- 不传 key = 匿名档（推荐）：首次提交自动签发零字段匿名令牌，无 key 配置、无凭据托管。legacy 共用 key 已随 VOD-KEY 上线进入兼容收尾（引擎 `external.legacy.enabled=false` 即关闭），自装场景不应也不会再拿到它——装了即匿名档。

安装器做三件事：写宿主 MCP 配置段（无损合并，只动 vod-devkit 自己的键）、按 packs 拷贝技能、写 install-manifest.json（commitSHA 来源主键）。

## 远程部署（MCP 单独服务多 agent）

```bash
# 1) 单独部署远程面（Streamable HTTP；需要官方 MCP SDK：pip install 'vod-devkit[remote]'）
npx --yes vod-devkit serve --transport remote --port 9528 --host 127.0.0.1

# 2) agent 侧 attach（配置指向远程端点 + 本地装技能）
npx --yes vod-devkit install --target opencode --mcp-url http://<host>:9528/mcp \
    --mcp-token <VOD key> --product codearts
```

- `--mcp-token` **可选**：远程面身份只从请求头 Bearer 走；不传时与本地同链领/复用
  机器级匿名令牌（D-token-machine-1；旧"不代签匿名单层"口径已废除），此时安装期只做连接级探活。
  传了则按 key 真伪探活（fail fast）。hermes/codex 的 token 落 env 引用，opencode
  明文入配置（注意文件权限）。dsh 不走 MCP，此模式显式拒绝。
- **token 探活**（安装期 fail fast）：attach 前探活三步——连接（initialize）、
  工具面（tools/list 必须等于契约 − 远程面裁剪集）、**key 真伪**（经远程面真调
  `vod_auth_status`，引擎三态判定）：
  - 引擎判 `rejected`（API Key 无效或已失效）→ 拒装，零副作用；
  - `device-mismatch`（引擎 401 原文「令牌与请求设备不匹配」）→ **放行**：
    匿名令牌是设备锚点绑定的，token 本身有效只是本机不是签发设备，提交时
    自动重领——匿名令牌不能当跨机远程 token 用，但同机部署（nonce 一致）
    探活即 `verified`，正常装；
  - 引擎不可达/超时 → 放行（网络问题不是 key 问题，不误伤断网环境）。
- `--skills-only`：MCP 已由别处注册时只装技能不动宿主配置。
- 远程面无 draft/commit/本地账本三个本机工具（面语义裁剪，非缺陷）；技能
  双面按 SKILL 的「先看工具面再定流程」走。

## 按宿主验证

**连接级**（配置被接受，≠能用）：

```bash
opencode mcp list        # vod-devkit connected
hermes mcp list          # vod-devkit enabled
codex mcp list           # vod-devkit enabled
```

**功能级**（真调一次只读工具，这步才算数）：

```bash
opencode run "调用 vod_auth_status 工具，告诉我 javaKey.base 和 meta.productCount"
hermes mcp test vod-devkit
codex exec "调用 vod_devkit_info 并报告 commitSha"
```

**写链路**（可选，验真实提交）：

```bash
opencode run "调用 vod_submit_voices 提交反馈：content=「我的测试反馈」，product=CodeArts，confirmed=true，告诉我 voiceId"
```

- 返回 `ext_anonymous-…` 开头 voiceId = 匿名链全通（首提自动签发令牌）
- 不带 `confirmed=true` 会被护栏拦下（-32011 逐次确认）——有意设计
- 同内容同令牌重提 → 同 voiceId 幂等（skipped，不烧配额）

## 常用命令

```bash
npx --yes vod-devkit status      # install-manifest：版本/来源/宿主/packs
npx --yes vod-devkit doctor      # 健康自检（含 key 探针 keyCheck 三态）
npx --yes vod-devkit verify      # commitSHA 到 origin 比对（来源对账）
npx --yes vod-devkit update      # fetch + ff 拉取 + 重烧 build-info
npx --yes vod-devkit uninstall
```

## WorkBuddy / CodeBuddy（GitHub 仓即市场，无审核）

```
/plugin marketplace add yangaiwu/vod-devkit
```

## DeepSeek Harness (dsh)

```bash
npx --yes vod-devkit install --target dsh --profile <profile> --product <产品>
```

- 包装命令做三件事：`dsh plugin add dsh-vod-devkit` → 产品安装期硬校验
  （--product 必须命中产品目录，未命中/不可达 exit 2 拒装，与三壳统一口径）→
  幂等写入 profile 的 cordis.patch.yml config 段（product/apiBase，工具壳的
  唯一生效通道，真机实证）。校验先于 add，不留半成品。
- dsh 壳无运行期 product 传参通道（部署配置权威）；重复 install 原位更新不重复插入。

薄壳包 `dsh-vod-devkit` 与主包同语义（同 PRODUCT_MAP/护栏码/匿名链）；
dsh 社区目录收录依赖 `dsh.bundle` manifest + `dsh-plugin` topic，随
npm 首发已解锁，收录审核进行中。

## dsh 部署已知坑（全部实锤，装前必读）

- **激活 id 必须等于包名**：client bundle 内嵌的 `__ModuleLoader__.load`
  注册 id ≠ package name → 激活审计报 `loaded without registering`；
- **设备锚点必须纯 hex**：`X-Vod-Device-Id` 含连字符等非 `[0-9a-f]` 字符
  → 引擎静默降 legacy ip|ua 锚点 → 签发 5 次/天易打满（429）；
- **web 宿主必须同源代理 /rest/**：dsh 页面经相对路径 `/rest/…` 访问
  VOD 外部 API——nginx 需加 `location /rest/ → VOD 实例`（参见
  `/etc/nginx/conf.d` 示例），否则提交报 `Failed to fetch`；
- **profile patch config 不下发 client 半**：client 侧配置经 server 半
  `ctx.on("webserver/index-inject")` 注入页面全局（同款机制参考
  `__DSH_CONTACT_CONFIG__`），不要指望 client `apply(ctx, config)`
  的第二参能拿到 patch config；
- **端点 429/401 的日志在哪**：服务端看 `/opt/vod/logs/vod-system/vod-system.log`；
  排障时勿用 `pgrep -f` 带 jar/脚本名自匹配杀进程。

## 故障排查

- **401/`-32012` 且提示"匿名令牌端点不可用"**：引擎侧 VOD-KEY（!152 线）未部署，
  匿名端点 404——等待部署或改用正式 key
- **`-32014` 非 https 且非回环**：`--java-api-base` 配了公网 http——改 https 或回环地址
- **`-32011` confirm 拦截**：写操作需逐次确认，重试并带 `confirmed=true`
- **产品归因**：安装期 `--product` 做名录硬校验（不在名录 `exit 2`）；运行期**没有** `-32013`
  这类本地拦截码——归因顺序=原话字面唯一命中 > 显式参数 > 会话记忆 > 安装先验，都没有就先问用户一次
- **attach 时 `token 无效（引擎判定 rejected）`**：坏 key 被探活拦下——确认是
  VOD 平台签发的 key（引擎 401 原文「API Key 无效或已失效」）
- **`设备绑定校验失败`**：匿名令牌跨设备使用——token 有效但本机不是签发设备，
  在本设备首次提交时自动重领（探活归 `device-mismatch` 放行，不拦）
- **安装期 `exit 2：产品不在名录`**（拼写正确也拒）：名录缓存默认 7 天，新上线产品查不到——
  `install --refresh-product-catalog` 强刷；`VOD_PRODUCT_CATALOG_TTL=<秒>` 改 TTL（`0`=禁用缓存）
- **安装期 `令牌签发被限流（429）`**：产品校验每次要一枚匿名令牌，密集重装会打满配额——
  等窗口滑过或配正式 key；名录缓存已把重复校验降到 7 天一次
- 更多：[QUICKSTART.md](QUICKSTART.md)（任意 MCP 客户端手动配置片段）
- 排障日志：`/tmp/vod_mcp_server.log`（每次 HTTP 的 URL/key 有无）

## 安全边界（与 huaweicloud-devkit 的刻意差异）

- 身份模型：key 档位（formal/host/anonymous）而非 AK/SK——key 是可限流/
  可吊销/可计数的把手，不是身份；匿名档可写但引擎侧打标可过滤
- 零遥测；零 DB 直连路径（护栏 deny 规则拦截直连意图，不误杀反馈原话）
- preset 分发形态禁 key 随包：key 落在哪台机器哪台就是信任边界
