---
description: 自检 VOD DevKit 就绪状态（MCP 连通/版本/key/账本）。
---

使用 vod-devkit 工具做就绪自检，按序执行并汇总 OK/缺失：
1. 调用 vod_devkit_info：确认 version 与 commitSha 非空（版本/来源溯源）。
2. 调用 vod_auth_status：报告 key 配置态与引擎连通性；无 key 属正常（首次提交自动取匿名令牌）。
3. 调用 vod_list_submitted（limit 5）：报告本机已提交反馈数（本地账本口径）。
4. 汇总：installed（OK）vs 缺失（需处理项）。不要打印任何 key/令牌明文。
若 MCP 工具不可用（刚装完未重启），提示用户重启 OpenCode 会话。
