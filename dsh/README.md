# dsh-vod-devkit

VOD 用户声音采集插件 —— DeepSeek Harness (dsh) 薄壳。

## 形态

- 纯采集：3 工具（`vod_submit_voices` / `vod_list_submitted` / `vod_devkit_info`）
- 插件=引擎客户端，只走 HTTPS（VOD external API），不 import 任何引擎模块
- 与 vod-devkit（MCP 形态，同仓 `../vod_mcp`）语义对齐：
  - voiceId = f(source, content, 调用级 nonce)：同调用幂等、跨调用保声量
  - product 归一映射（小写 codearts → CodeArts；引擎实测小写 400）
  - 归因三层：配置绑定 → 显式传参 → 报错引导（绝不静默默认）
  - 无 key/401 → POST /external/token 零字段匿名令牌 → 本地落盘 → 重试一次
  - 本地账本 data/runtime.json（cap 200 环形，读改写只动目标键）

## 安装

```
npx --yes vod-devkit install --target dsh --profile <name> --product <产品>   # 推荐（安装期硬校验+幂等写配置，一条命令完成全部部署）
```

> ⚠️ 不要用 `dsh plugin add dsh-vod-devkit` 裸装：只装插件本体不写配置——
> product 缺失时反馈入口不激活（fail fast，宁可不装不可装错）；apiBase/uiBase
> 缺失时工具半不可用、UI 提交会发往 dsh 同源（404 → 本地暂存发不出去，
> 嵌入方真机实锤）。裸装后补救：跑一次上面的 npx 命令即可（幂等）。

装后配置落在 profile 的 cordis.patch.yml（npx 包装命令自动写入）：

```yaml
- id: vod-devkit
  config:
    product: codearts        # 归因绑定（安装时定）；无运行期传参通道
    # apiBase: https://vod-dev.topxtopx.com   # 工具半（Node 服务端）用，缺省即此
    # uiBase: https://vod-dev.topxtopx.com     # 浏览器半（反馈按钮）直连用，缺省即此
```

### UI 半（反馈按钮）部署前提——二选一

- **uiBase 直连**（默认，本包形态）：浏览器直接请求 uiBase 指向的引擎地址。
  依赖：引擎侧 CORS 允许 dsh 页面源（本地 dsh 为 `http://127.0.0.1:<port>`）。
  引擎 CORS 收敛（白名单制）落地时，白名单必须含 dsh 本地源，随其上线同步验证。
- **宿主代理**（嵌入方自建，可选）：由 dsh 部署侧把 `/external/*` 反代到引擎，
  此时 uiBase 可留空走同源。当前 dsh 不自带此代理，默认勿依赖。

## 配置（dsh 插件设置）

| 字段 | 默认 | 说明 |
|---|---|---|
| apiBase | https://vod-dev.topxtopx.com | VOD external API 基址（工具半/服务端用） |
| uiBase | 同 apiBase | 浏览器半（反馈按钮）直连基址；同源代理形态可留空 |
| apiKey | （空） | 缺省走零字段匿名令牌；灰度期可用运营签发 key |
| product | （空） | 本机产品归因绑定（如 codearts）；空且调用未传参时报错引导 |
| confirmWrites | true | 写操作走 dsh 审批通道（tools/pre-execute → ask） |
| timeoutSec | 30 | HTTP 超时 |

## 安全

- apiKey 标记 `.role('secret')`：不跨 wire 回传，展示一律 sha1[:8] 指纹
- 写操作默认弹确认；单批 ≤50；content ≤2000 逐条校验
