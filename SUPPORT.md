# Support

使用 vod-devkit 遇到问题时，按以下分层排查：

## 自助排查（先走这条）

1. `bin/vod-devkit doctor` —— 环境自检（python 版本 / 配置 / 令牌状态）
2. `bin/vod-devkit status` —— 安装状态与 build-info（版本 + commitSHA）
3. [QUICKSTART.md](QUICKSTART.md) —— 各 MCP 客户端手动配置片段 + 故障排查表
   （上游不可达 / -32012 鉴权 / 工具不出现）
4. [SECURITY.md](SECURITY.md) —— 疑似安全漏洞走私有通道，不开公开 issue

## Bug 与功能请求

- **GitCode issue**（主仓，私有）：gitcode.com/xiaowu2119/vod-devkit/issues
- **GitHub issue**（公开镜像）：github.com/yangaiwu/vod-devkit/issues

提 issue 请附：宿主产品与版本、`vod-devkit status` 输出、doctor 输出、
`/tmp/vod_mcp_server.log` 相关片段（已自动脱敏 key）。

## 环境限制说明

- 无 key 可用：首次提交自动申请零字段匿名令牌（30 天 / 500 条天花板），
  达上限按引导升级
- 引擎测试环境：https://vod-dev.topxtopx.com（可用性以 VOD 团队公告为准）
