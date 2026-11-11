# vod-devkit

[English](README.en.md) | 中文

VOD 用户声音采集插件（方案 A 纯采集形态）：MCP server + 技能 +
声明式护栏，把 agent 产品的用户反馈安全送进 VOD。运营能力归
vod-system 前端，不在本插件。对齐 huaweicloud-devkit v2 的工程骨架（installer /
MCP / skills / packs / policy），面向"服务面插件"的护栏更保守。

- 需求/设计：docs/proposal.md、docs/design.md（VOD-PLUGIN）
- 贡献：CONTRIBUTING.md ｜ 安全策略与边界：SECURITY.md
- 支持：SUPPORT.md ｜ 行为准则：CODE_OF_CONDUCT.md ｜ 第三方素材：NOTICE
- 真源纪律：领域规则技能与引擎代码的对账由 scripts/rules_provenance.py 执行
  （docs/rules-provenance.json 记「技能↔引擎文件↔符号」与双方指纹：引擎改了
  分类/评分口径 → 对账红，技能复核后 --update 重录；无引擎检出时 SKIP 不伪绿）
- 对账主键：引擎任务 taskId；插件来源主键=commitSHA（build-info.json 构建烧录，
  install-manifest.json 安装落盘，`vod-devkit verify` 到 origin 核对 commit）

## 安装（外部用户，零配置）

完整分宿主指南见 [INSTALL.md](INSTALL.md)。速览：

```bash
# 任意 MCP 宿主（Hermes / OpenCode / Codex 客户端等）：npm 公网已发布
npx --yes vod-devkit install --target opencode --product codearts   # --product 可选先验（归因默认从用户原话解析）

# WorkBuddy / CodeBuddy（GitHub 仓即市场，无审核）：
/plugin marketplace add yangaiwu/vod-devkit

# DeepSeek Harness (dsh)：薄壳包 dsh-vod-devkit（npm 同名）；目录收录审核中
dsh plugin --profile <profile> add dsh-vod-devkit
```

安装后即用：平台地址有默认值，首次提交自动申请零字段匿名令牌。
手动配置片段与故障排查见 [QUICKSTART.md](QUICKSTART.md)。

## 快速使用

```bash
# 安装到 Hermes（写 MCP 配置+skills+install-manifest）
bin/vod-devkit install --target hermes --preset collect   # 对外默认（采集者）
# 唯一上游 Java backend（key 未配置时首提自动申请匿名令牌）：
VOD_JAVA_API_BASE / VOD_JAVA_API_KEY

bin/vod-devkit update   # git fetch+ff 拉取+重烧 build-info
bin/vod-devkit status   # 看 install-manifest（版本+来源+宿主+packs）
bin/vod-devkit verify   # commitSHA 到 origin 核验（篡改/改写告警）
bin/vod-devkit doctor   # 配置+skills+build-info 三查
bin/vod-devkit uninstall

# 直接以 MCP server 运行（任意 MCP 客户端可连）
python3 -m vod_mcp.server          # stdio，JSON-RPC
VOD_PACKS=core,collect python3 -m vod_mcp.server   # packs 裁剪
```

## 远程面（Streamable HTTP）

默认形态是 stdio（各宿主拉起子进程，零端口）。如果你的 agent 支持
`type: "remote"`（Streamable HTTP），可以单独起一个常驻进程，供多个 agent 共用：

```bash
pip install 'vod-devkit[remote]'          # 远程面依赖官方 MCP SDK（stdio 形态不需要）
vod-devkit serve --transport remote      # 默认 http://127.0.0.1:9528
```

```jsonc
{ "mcp": { "vod-devkit": {
    "type": "remote", "url": "http://localhost:9528", "enabled": true } } }
```

端口被占用用 `--port <port>`（同步改 url）；`--host 0.0.0.0` 可开 LAN 访问。

边界（与 stdio 形态的实质差别）：

- **身份从请求头来**：每个请求带 `Authorization: Bearer <VOD key>`；缺 key 时
  `vod_submit_voices` 直接结构化拒绝，**不代签匿名令牌**（匿名令牌按设备锚点签发，
  一进程一锚点会把配额、声量、归因搅在一起）。
- **工具面收窄**：草稿/本地账本类工具（`vod_draft_voices` / `vod_commit_voices` /
  `vod_list_submitted`）不在远程面提供——它们写"本机状态"，而一个共享进程没有
  "本机"。
- **插件不写库**：远程面能做的仍然只是调用引擎 HTTP API；落库、配额、审计都在
  服务端。插件不持有数据库连接，也没有任何 DB 代码路径。
- **无内建鉴权**：本进程不校验身份，默认只绑回环。要对外必须在反代上加 TLS 与
  身份校验——不要把它匿名暴露到公网。

## 工具面（契约唯一事实源：contract/tools.schema.json）

| 工具 | pack | 类型 | 护栏 |
|---|---|---|---|
| vod_submit_voices | collect | 写 | confirm 逐次同意 + 单批≤50 + source 取握手宿主身份；走 Java /external/voices |
| vod_draft_voices | collect | 写（暂存） | 本机暂存 cap10/TTL600s，逐字回显 contents；不触上游 |
| vod_commit_voices | collect | 写 | 一次性令牌 + payloadSha256 防调包，内部复用提交链 |
| vod_list_submitted | collect | 只读 | 本机提交账本（cap 200）——agent 替用户对账进度 |
| vod_devkit_info | core | 只读 | 返回版本/commitSHA/宿主 clientInfo |
| vod_auth_status | core | 只读 | key 指纹化自检+三步引导（无 key 可跑） |
| vod_check_update | core | 只读 | npm registry latest（24h 缓存/失败静默）；只提醒不自升级 |
| vod_list_skills / vod_retrieve_skill | knowledge | 只读 | 领域规则技能的披露面（pack 裁剪即拒绝并给恢复命令） |

安全：deny 拦 DB 直连意图与凭据读取（safety/policy.json 声明式规则；
文本规则只扫结构性字段，不误杀反馈内容里的凭据引用）。

测试：pytest + node:test 全量（单元+护栏+packs+安装器矩阵四宿主+真进程 stdio 回环+
**协议级真 HTTP 服务器**锁定认证头/双后端路径——E1/E2 的永久回归门）。
用例数以本地实测为准（`python3 -m pytest tests/ -q`），文档不手写计数——
手写计数必然漂移，tests/test_claims.py 会拦。决策闭环见 docs/decisions.md。

## 质量门禁

GitCode Actions 平台侧当前对本账号不可用（运行 0ms FAILED 零 job、
公开实验仓同样不触发，平台问题非代码问题，已实测隔离）。期间的机器
门禁=pre-push 钩子（pytest+pyflakes，红了禁推）：

```bash
git config core.hooksPath .githooks   # clone 后执行一次
```

`.gitcode/workflows/ci.yml` 已就位，平台恢复后自动叠加服务端门禁。

## 测试

零第三方运行时依赖；测试需 pytest。真进程 stdio 回环覆盖握手、工具
列举、confirm 护栏、宿主感知（U1/U3/U13/U15/U16）。
