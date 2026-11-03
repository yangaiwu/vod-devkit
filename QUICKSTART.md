# QUICKSTART（外部开发者 · 3 分钟接入）

## 你能得到什么

把 vod-devkit 装进你的 AI agent / 应用后：

1. **采集你产品的用户反馈**进 VOD 分析平台（写口，需用户确认）
2. VOD 领域知识（分类匹配/问题分类/评分规则技能）
3. 插件自述与来源核验（vod_devkit_info / vod_auth_status）

> 首次提交时插件会自动申请零字段匿名令牌（无需注册）；
> 量大后再升级正式 key。

## 前置

- Python 3.10+
- 任意支持 MCP stdio 的宿主（Hermes/OpenCode/Codex/…）

## 方式一：Hermes（自动安装）

```bash
git clone <repo-url> vod-devkit && cd vod-devkit
bin/vod-devkit install --target hermes --preset collect
# 重启 Hermes 会话，工具以 mcp_vod_devkit_* 出现
```

## 方式二：任意 MCP 客户端（手动配置）

把以下片段并入你宿主的 mcpServers 配置：

```json
{
  "mcpServers": {
    "vod-devkit": {
      "command": "python3",
      "args": ["/path/to/vod-devkit/vod_mcp/server.py"],
      "env": {
        "VOD_JAVA_API_BASE": "https://vod-dev.topxtopx.com",
        "VOD_JAVA_API_KEY": "",
        "VOD_PACKS": "core,collect"
      }
    }
  }
}
```

配置好后重启会话。

## 验证

- 会话里让 agent 调用 `vod_auth_status` → key 状态（指纹）+ 三步引导
- 提交一条测试反馈：`vod_submit_voices`（voices + confirmed=true）

## 升级正式 key（提交量达匿名上限后）

联系 VOD 运营 → `bin/vod-devkit install --java-key <KEY>` 重新落位。

## 故障排查

| 症状 | 含义 |
|---|---|
| `上游不可达` | 引擎/网络未就绪，检查 VOD_JAVA_API_BASE |
| `-32012 鉴权失败` | key 无效或被吊销；无 key 会自动取令牌重试 |
| 工具不出现 | 确认 VOD_PACKS 含对应 pack；重启会话 |
