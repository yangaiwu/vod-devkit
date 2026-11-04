# vod-devkit

[English](README.en.md) | 中文

VOD 用户声音采集插件（方案 A 纯采集形态）：MCP server + 技能 +
声明式护栏，把 agent 产品的用户反馈安全送进 VOD。运营能力归
vod-system 前端，不在本插件。对齐 huaweicloud-devkit v2 的工程骨架（installer /
MCP / skills / packs / policy），面向"服务面插件"的护栏更保守。

- 需求/设计：docs/proposal.md、docs/design.md（VOD-PLUGIN）
- 贡献：CONTRIBUTING.md ｜ 安全策略与边界：SECURITY.md
- 支持：SUPPORT.md ｜ 行为准则：CODE_OF_CONDUCT.md ｜ 第三方素材：NOTICE
- 真源纪律：领域规则技能由 scripts/vendor_rules.py 从 VodTeam/VOD-Project
  按 commitSHA 锁定拉取（规则只改一处）
- 对账主键：引擎任务 taskId；插件来源主键=commitSHA（build-info.json 构建烧录，
  install-manifest.json 安装落盘，`vod-devkit verify` 到 origin 核对 commit）

## 安装（外部用户，零配置）

```bash
# 任意 MCP 宿主（Hermes / OpenCode / Codex 客户端等）：
npx github:yangaiwu/vod-devkit          # 引导器自动探测宿主并安装

# WorkBuddy / CodeBuddy（GitHub 仓即市场，无审核）：
/plugin marketplace add yangaiwu/vod-devkit

# DeepSeek Harness (dsh)：npm 包 dsh-vod-devkit（薄壳同语义）；
# npm 首发后可在 dsh 社区目录一键安装，暂可用本地包：
dsh plugin --profile <profile> add dsh/dsh-vod-devkit-0.1.0.tgz
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

## 工具面（契约唯一事实源：contract/tools.schema.json）

| 工具 | 类型 | 护栏 |
|---|---|---|

| vod_submit_voices | 写 | confirm 逐次同意 + 单批≤50 + source 取握手宿主身份；走 Java /external/voices |
| vod_devkit_info | 只读常驻 | 返回版本/commitSHA/宿主 clientInfo |
| vod_auth_status | 只读常驻 | key 指纹化自检+三步引导（无 key 可跑） |
| vod_list_submitted | 只读 | 本机提交账本（cap 200）——agent 替用户对账进度 |

安全：deny 拦 DB 直连意图与凭据读取（safety/policy.json 声明式规则；
文本规则只扫结构性字段，不误杀反馈内容里的凭据引用）。

测试：39 用例（单元+护栏+packs+安装器矩阵三宿主+真进程 stdio 回环+**协议级真 HTTP 服务器**
锁定认证头/双后端路径——E1/E2 的永久回归门）。决策闭环见 docs/decisions.md。

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
