# vod-devkit

VOD 插件包：MCP server + 技能 + 声明式护栏，供 AI agent / 外部应用集成
VOD 用户声音分析能力。对齐 huaweicloud-devkit v2 的工程骨架（installer /
MCP / skills / packs / policy），面向"服务面插件"的护栏更保守。

- 需求/设计：docs/proposal.md、docs/design.md（VOD-PLUGIN）
- 真源纪律：领域规则技能由 scripts/vendor_rules.py 从 VodTeam/VOD-Project
  按 commitSHA 锁定拉取（规则只改一处）
- 对账主键：引擎任务 taskId；插件来源主键=commitSHA（build-info.json 构建烧录，
  install-manifest.json 安装落盘，`vod-devkit verify` 到 origin 核对 commit）

## 快速使用

```bash
# 安装到 Hermes（写 MCP 配置+skills+install-manifest）
bin/vod-devkit install --target hermes --api-base http://127.0.0.1:8000

bin/vod-devkit status   # 看 install-manifest（版本+来源+宿主+packs）
bin/vod-devkit verify   # commitSHA 到 origin 核验（篡改/改写告警）
bin/vod-devkit doctor   # 配置+skills+build-info 三查
bin/vod-devkit uninstall

# 直接以 MCP server 运行（任意 MCP 客户端可连）
python3 -m vod_mcp.server          # stdio，JSON-RPC
VOD_PACKS=core,workflow python3 -m vod_mcp.server   # packs 裁剪
```

## 工具面（契约唯一事实源：contract/tools.schema.json）

| 工具 | 类型 | 护栏 |
|---|---|---|
| vod_run_analysis | 写 | confirm（confirmed=true 才执行）+ 条数上限 500 + product 白名单 |
| vod_task_status / vod_task_result | 读 | 放行 |
| vod_kb_search | 读 | 引擎侧前置：/api/vod/knowledge/query 待补（VOD-KBQ R1） |
| vod_submit_voices | 写 | confirm 逐次同意 + 单批≤50 + source 取握手宿主身份（用户反馈采集闭环） |
| vod_devkit_info | 只读常驻 | 返回版本/commitSHA/宿主 clientInfo |

安全：deny 拦 DB 直连意图与凭据读取（safety/policy.json 声明式规则）。

## 测试

零第三方运行时依赖；测试需 pytest。真进程 stdio 回环覆盖握手、工具
列举、confirm 护栏、宿主感知（U1/U3/U13/U15/U16）。
