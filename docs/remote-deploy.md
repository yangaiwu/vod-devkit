# 远程部署手册（一套服务端服务多个 agent）

> 适用：多 agent / 多团队 / 客户机不允许出网，需要把「引擎出口 + 凭据 + 升级 + 审计」收敛到一台机器。
> 单机自用请走本地 stdio（`install --target <宿主>`），不要照本手册。
> 形态参考：README「三种部署模式」；能力边界见本节 §8。

---

## 1. 先决定：一套还是多套

| 你的情况 | 起几套实例 |
|---|---|
| 只有 1 个产品，日提交 < 400 条，不追究"谁提交的" | **1 套**（单实例直用） |
| 多个产品，或需要按团队/产品分开归因、额度、账本 | **每产品/团队 1 套**（同机多进程） |
| 需要"同一实例内按调用方区分身份" | 必须有可分发的正式 key（`--mcp-token`），否则做不到 |

> 匿名令牌是"一份 state 一份身份"（per-install nonce），所以**分实例 = 自动各领一份匿名令牌**，
> 零人工凭据也能隔离身份/配额/产品/账本。单实例多 agent 则共用一份身份。

---

## 2. 服务端准备

```bash
# 依赖：Python >= 3.10、Node >= 18（npx 引导）；远程面需要官方 MCP SDK
npm i -g vod-devkit
python3 -m pip install 'mcp>=1.0'          # 只有 remote 传输需要；stdio 形态零第三方依赖

vod-devkit serve --transport remote --host 127.0.0.1 --port 9528 --allow-host mcp.example.com
```

关键参数（都不是可选项，缺一项就报错或 403）：

| 参数 | 作用 | 坑 |
|---|---|---|
| `--transport remote` | Streamable HTTP，一个进程服务多个 agent | stdio 形态下这个参数不能给 |
| `--host/--port` | 只绑回环，对外由反代接 | **不要直接绑 0.0.0.0**，除非你已自己加鉴权 |
| `--allow-host <域名>` | 允许的 Host 头（可多次） | 经反代时 Host 是公网域名，**不给就所有 POST 403** |
| `--allow-origin <源>` | 允许的浏览器 Origin | 只有浏览器直连才需要；agent 调用不需要 |
| `--allow-anon-mint` | 非回环绑定时仍允许服务端代领匿名令牌 | 默认关闭；单机可信网络才开 |
| `--packs core,collect,knowledge` | 服务端固定的能力包 | 远程面**不能**会话内切包，必须在启动时定 |

---

## 3. 多实例（按产品隔离）目录与启动

```bash
# 每个实例三样东西各自独立：端口 / state / 安装账本
sudo mkdir -p /srv/vod/{codearts,obs}/{state,logs}
```

`/etc/vod/codearts.env`
```ini
VOD_DEVKIT_HOME=/srv/vod/codearts/state
VOD_DEVKIT_MANIFEST=/srv/vod/codearts/install-manifest.json
VOD_DEVKIT_LOG=/srv/vod/codearts/logs/server.log
```

`/etc/systemd/system/vod-mcp@.service`（模板单元，`%i` = 实例名）
```ini
[Unit]
Description=vod-devkit remote MCP (%i)
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=/etc/vod/%i.env
ExecStart=/usr/local/bin/vod-devkit serve --transport remote \
          --host 127.0.0.1 --port $PORT --allow-host $PUBLIC_HOST \
          --packs core,collect,knowledge
Restart=on-failure
RestartSec=3
User=vod
Group=vod

[Install]
WantedBy=multi-user.target
```

`/etc/vod/codearts.env` 再加两行：
```ini
PORT=9528
PUBLIC_HOST=mcp-codearts.example.com
```

启用：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vod-mcp@codearts
# 第二个产品：/etc/vod/obs.env（PORT=9529 / PUBLIC_HOST=mcp-obs.example.com）
sudo systemctl enable --now vod-mcp@obs
```

给实例钉产品（决定 `install_binding`，即"用户自指时归到谁"）：
```bash
sudo -u vod env $(cat /etc/vod/codearts.env | xargs) \
  vod-devkit install --target generic --mcp-config /tmp/throwaway.json --product CodeArts
```

---

## 4. 反代：TLS + 鉴权 + 限流（三者都要）

```nginx
# 网关鉴权：用**独立头**（X-Api-Token / basic / mTLS），
# 千万不要动 Authorization —— 那是给引擎的 Bearer，插件会原样透传向上。
map $http_x_api_token $gateway_ok {
  default             0;
  "team-a-3f9c1e"     1;      # 每个调用方/团队一把
}

# 按调用方限速（避免一个人刷满公共额度）
limit_req_zone $http_x_api_token zone=vod_req:10m rate=10r/s;

server {
  listen 443 ssl;
  server_name mcp-codearts.example.com;
  ssl_certificate     /etc/ssl/mcp-codearts.crt;
  ssl_certificate_key /etc/ssl/mcp-codearts.key;

  location /mcp {
    if ($gateway_ok = 0) { return 401; }
    limit_req zone=vod_req burst=20 nodelay;

    proxy_pass http://127.0.0.1:9528;
    proxy_http_version 1.1;
    proxy_set_header Host $host;              # 服务端 --allow-host 要包含它
    proxy_read_timeout 120s;
  }
}
```

> 引擎凭据走 `Authorization: Bearer <engine-key>`，由 agent 侧在 `install --mcp-token` 里给，
> 一路透传到引擎。不要用反代改写这个头，否则会把引擎 key 换掉。

---

## 5. 宿主侧接入（每个 agent 一条命令）

```bash
# 有正式 key：带自己的身份（推荐——配额/审计都按它算）
npx -y vod-devkit@latest install --target hermes \
     --mcp-url https://mcp-codearts.example.com/mcp --mcp-token <该 agent 的引擎 key>

# 没有 key：不传 --mcp-token，服务端按"该实例的匿名令牌"代提交（低信任档）
npx -y vod-devkit@latest install --target hermes \
     --mcp-url https://mcp-codearts.example.com/mcp
```

落点与注意事项：

- 宿主配置里只写 `{url, headers}`；**不落载荷、不起本地 server**。
- 技能仍拷到宿主技能目录（话术约束在宿主侧）；只拿 URL 的第三方 agent 靠
  `vod_list_skills` / `vod_retrieve_skill` 取规则全文（需服务端开 `knowledge` 包）。
- 远程装会**先探活再写入**：URL 不可达或 token 无效 → 拒绝写配置并给出原因，不留半套。
- `dsh` 本轮**不支持**远程 attach（只有本地 stdio）。

---

## 6. 验收（上线前必须全跑）

```bash
# ① 服务端自证（每个实例都跑一次）
curl -s -X POST https://mcp-codearts.example.com/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H 'X-Api-Token: team-a-3f9c1e' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' | head -c 200
#    期望：{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{"listChanged":true}}, "instructions":"vod-devkit …"}}
#    403 → --allow-host 没配；401 → 网关令牌不对；连接被拒 → 服务没起

# ② 宿主侧自证
npx -y vod-devkit@latest doctor     # 远程行 0 FAIL
npx -y vod-devkit@latest status     # 该宿主 transport=remote、mcpUrl 在位

# ③ 会话内自证（每个 agent 都做一次）
「调用 vod_devkit_info 原样打印 version 与 commitSha」   → 应回服务端当前版本
「调用 vod_auth_status」                                → 有 Bearer 时 requestKey 段有指纹、
                                                          keyCheck=verified
「调用 vod_submit_voices（confirmed=true + product）」   → 应回 accepted/voiceIds
```

---

## 7. 日常运维

| 事项 | 做法 |
|---|---|
| 升级 | 服务端 `npm i -g vod-devkit` 后逐实例 `systemctl restart vod-mcp@<name>`；客户端零改动 |
| 日志 | `VOD_DEVKIT_LOG` 指到实例目录；remote 面会打 `http_access`（req_id/tool/duration_ms） |
| 排障入口 | ① 反代 access log（谁被 401/429）② 实例日志（哪次调用失败、code）③ 客户端 `doctor` |
| 备份 | 只需备份各实例的 `state/`（令牌/账本/草稿），代码与载荷可重装 |
| 清旧载荷 | `vod-devkit prune --payloads`（dry-run）→ `--apply --yes`；只删载荷，不碰 state |
| 灰度 | 新实例先起在备用域名，验收通过再切反代 upstream |

---

## 8. 已知限制（别指望它做这些）

```
多租户 state 隔离     ❌ 一个实例一份 state：草稿/账本/令牌共用 → 要隔离请分实例
会话内切能力包        ❌ vod_packs_configure 在远程面被摘（多会话共用一个 Server 实例）
dsh 远程 attach      ❌ 本轮只有本地 stdio
内置鉴权/限流/配额    ❌ 由反代承担（见 §4）；插件只提供 Host/Origin 校验
匿名令牌额度          引擎侧硬上限（30 天 5000 条 / 日 500 条），插件无权调 → 量上来必须升正式 key
引擎侧来源字段        渠道由引擎固定为 vod-agent；要在报表里区分"哪个 agent 提交"，需引擎契约支持
```

---

## 9. 常见故障对照

| 现象 | 先查 |
|---|---|
| 所有 POST 403 | `--allow-host` 没包含反代传过来的 Host（或反代改了 Host） |
| 401 | 网关令牌（`X-Api-Token`）不对；或把网关头写成了 `Authorization`（会顶掉引擎 Bearer） |
| 429 | 反代 `limit_req` 触发；调额度或按调用方拆 key |
| 提交报 `-32012` | 服务端绑了非回环又没开 `--allow-anon-mint`，且调用方没带 Bearer |
| 提交报 `-32010` | 缺产品归属：该实例没钉 `--product`，且原话里没有产品线索 → 让模型按纪律问一次用户 |
| 工具面比预期少 | 服务端 `--packs` 没开对应包（远程面不能会话内切） |
| 客户端 doctor 全绿但会话无工具 | 宿主侧问题：WorkBuddy 需打开「信任」；桌面端宿主需完全退出重启 |