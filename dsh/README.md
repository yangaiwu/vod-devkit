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
dsh plugin --profile <name> add dsh-vod-devkit   # npm 发布后
dsh plugin --profile <name> add github:yangaiwu/vod-devkit#dsh  # 亦可
```

装后在 profile 的 cordis.patch.yml 激活（与包内 cordis.patch.yml 同语义）：

```yaml
- insert:
    - id: vod-devkit
      name: 'dsh-vod-devkit'
```

## 配置（dsh 插件设置）

| 字段 | 默认 | 说明 |
|---|---|---|
| apiBase | https://vod-dev.topxtopx.com | VOD external API 基址 |
| apiKey | （空） | 缺省走零字段匿名令牌；灰度期可用运营签发 key |
| product | （空） | 本机产品归因绑定（如 codearts）；空且调用未传参时报错引导 |
| confirmWrites | true | 写操作走 dsh 审批通道（tools/pre-execute → ask） |
| timeoutSec | 30 | HTTP 超时 |

## 安全

- apiKey 标记 `.role('secret')`：不跨 wire 回传，展示一律 sha1[:8] 指纹
- 写操作默认弹确认；单批 ≤50；content ≤2000 逐条校验
