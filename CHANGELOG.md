# Changelog

## v0.1.0（2026-11-03）

首个可用版本：VOD 用户声音采集插件（方案 A 纯采集形态）。

- 3 工具：vod_submit_voices（confirm+单批≤50+归因三层+零字段匿名令牌
  自动获取+声量保真 voiceId）、vod_devkit_info、vod_auth_status
- 动态元数据：meta 拉取+24h 缓存+快照兜底+stale 标记
- 声明式护栏 + 契约单一事实源 + 溯源（commitSHA verify）+ preset 安装
- 端到端已实测：真 Hermes 会话→测试环境 Java /external/voice/submit
  →taskId 回执（零引擎侧改动，复用现有接口）
- 23 用例（单元+护栏+packs+协议级真 HTTP+stdio 回环+meta）
