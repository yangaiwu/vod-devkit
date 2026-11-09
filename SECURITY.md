# 安全策略

## 支持版本

仅支持最新发布 tag（CHANGELOG 列出）。install 支持 `--ref` 显式锁定提交。

## 报告漏洞

**不要开公开 issue 报安全漏洞。** 请通过：

- 公开镜像仓（github.com/yangaiwu/vod-devkit）的 GitHub 私有漏洞报告
  （Security → Report a vulnerability）
- 或直接联系维护者（GitCode @xiaowu2119 私信）

报告请附：复现步骤、`vod-devkit build-info` 输出（含版本+commitSHA）、
`vod-devkit doctor` 输出。我们承诺 72 小时内响应。

## 安全模型（用户应知的边界）

- **令牌分档**：首次提交自动申请零字段匿名令牌（默认 30 天 / 5000 条天花板、日 500 条；引擎侧 vod.external.* 可配置），
  存 `vod_mcp/runtime.json`（0600，gitignore）。key 指纹仅显示 sha1[:8]，明文不落日志
- **传输**：非回环地址一律强制 https（-32014 拒绝 http）；Bearer 不明文过公网
- **护栏**：写操作逐批 confirm、单批 ≤50 条、content ≤2000 逐条校验
  （超长拒该条不拒整批）；`guard_scope` 剔除反馈正文，不误杀正文内的凭据引用
- **不做的事**：遥测回传（不做）；凭据写入 git / remote URL（禁止，PAT 走
  credential store 0600）
- **客户端身份可伪造**（clientInfo 自报）：防线是按档限流/吊销/配额，
  不依赖自报身份做信任决策——匿名档数据在分析侧默认排除（R2 过滤）

## 溯源对账

来源主键 = commitSHA（构建烧进 build-info.json，`vod-devkit verify`
到 origin 核对）。发现未知来源安装/调用，按 docs/design.md 灰度纪律
立即轮换 key 并收窄。
