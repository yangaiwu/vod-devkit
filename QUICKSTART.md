# QUICKSTART（外部开发者 · 3 分钟接入）

## 你能得到什么

把 vod-devkit 装进你的 AI agent / 应用后：

1. **采集你产品的用户反馈**进 VOD（唯一写口，需用户确认）
2. VOD 领域知识技能（问题分类/分类匹配/评分规则，采集预分类用）
3. 插件自述与来源核验（vod_devkit_info / vod_auth_status）

> 首次提交时插件会自动申请零字段匿名令牌（无需注册）；
> 量大后再升级正式 key。

## 前置

- Node >= 18（`npx` 引导器；dsh 宿主按其官方要求 Node 24.9+）
- Python 3.10+（可用 `VOD_PYTHON` 指定解释器）
- 宿主任选其一：hermes / opencode / codeartsdoer / codeartswork / codex /
  codex-desktop / dsh / workbuddy / atomcode / openclaw / officeace（officeace 仅
  Windows 有安装面；其它 MCP 客户端走 `--target generic`）
- 网络可达 VOD 引擎（缺省 `https://vod-dev.topxtopx.com`）

## 方式一：npm（推荐，一条命令）

```bash
npx -y vod-devkit@latest install --target auto --product <你的产品>
# --target auto 探测已装宿主；显式指定如 --target hermes / opencode / openclaw
```

## 方式二：从仓库装

```bash
git clone https://gitcode.com/xiaowu2119/vod-devkit.git && cd vod-devkit
bin/vod-devkit install --target hermes --product <你的产品>   # 宿主任选
# 重启宿主会话后工具出现（宿主在启动时读 MCP 配置）
```

## 方式三：任意 MCP 客户端（手动配置）

把以下片段并入你宿主的 mcpServers 配置：

```json
{
  "mcpServers": {
    "vod-devkit": {
      "command": "python3",
      "args": ["/path/to/vod-devkit/vod_mcp/server.py"],
      "env": {
        "VOD_JAVA_API_BASE": "https://vod-dev.topxtopx.com",
        "VOD_PACKS": "core,collect,knowledge"
      }
    }
  }
}
```

配置好后重启会话。装完自检：`npx -y vod-devkit@latest doctor` /
`status`（针对已装实例，读 install-manifest）。

## 方式四：远程部署（MCP 单独服务多 agent）

```bash
# 1) 服务端：起远程面（需官方 MCP SDK；对外自建 TLS 反代）
pip install 'vod-devkit[remote]'
vod-devkit serve --transport remote --port 9528 --host 127.0.0.1
# 开放到非回环地址时：匿名代领默认关闭（调用方须带 Bearer）；
# 可信内网确需共享本机身份，再加 --allow-anon-mint

# 2) agent 侧 attach（token 可选：给了用请求头身份，不给走服务端机器级匿名令牌）
npx -y vod-devkit@latest install --target opencode \
    --mcp-url http://<host>:9528/mcp --product <你的产品>
# 需要按调用方隔离身份时再加 --mcp-token <VOD key>
# 注：--product 写的是本机 state；server 与插件同机才对该 server 的归因生效
```

attach 前安装器会**探活**：连接（initialize）、工具面（tools/list 与契约
比对）、**key 真伪**（经远程面真调 vod_auth_status，引擎判定）。坏 key 当场
拒装零副作用；匿名令牌设备漂移（`device-mismatch`）和引擎不可达会放行——
网络问题不是 key 问题。详见 [INSTALL.md](INSTALL.md) 远程部署节。

## 验证

- 会话里让 agent 调用 `vod_auth_status` → key 状态（指纹）+ 引导
- 提交一条测试反馈：`vod_submit_voices`（voices + confirmed=true）

## 升级正式 key（提交量达匿名上限后）

联系 VOD 运营拿 key → 安装/更新时经 env 提供（安装器写入宿主 MCP 配置）：

```bash
VOD_JAVA_API_KEY=<KEY> npx -y vod-devkit@latest \
    install --target <宿主> --product <你的产品>
```

升级后 `vod_auth_status` 的 keyCheck 会显示 `verified`。

## 故障排查

| 症状 | 含义 |
| --- | --- |
| `上游不可达` | 引擎/网络未就绪，检查 VOD_JAVA_API_BASE |
| `-32012 鉴权失败` | key 无效或被吊销；无 key 会自动取令牌重试 |
| `token 无效（引擎判定 rejected）` | attach 时坏 key——确认 VOD 平台签发的 key |
| `设备绑定校验失败` | 匿名令牌跨设备使用——本设备首次提交会自动重领 |
| 工具不出现 | 确认 VOD_PACKS 含对应 pack；重启会话 |
| 安装期「产品不在名录」exit 2 | 名录缓存 7 天；`install --refresh-product-catalog` 强刷，TTL 用 `VOD_PRODUCT_CATALOG_TTL`（秒）|

更多：[INSTALL.md](INSTALL.md)（每宿主安装细节/故障表/安全边界）。
