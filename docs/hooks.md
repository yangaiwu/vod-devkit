# 钩子（hook）规则模型

本仓有两条宿主钩子，同一套脚本形态、各自事件注册：

1. **预采集路由**（`hooks/vod_router.py`，`pre_llm_call`）：回答"这一轮用户的话，该不该
   进入采集流程"，不阻塞任何动作。
2. **读 Key 拦截**（`hooks/vod_guard.py`，`pre_tool_call`，D-key-guard-4）：只拦"把引擎 key
   读进对话"的动作（`cat runtime.json`、`env` 导出点名 key 变量），其余一律放行；脚本
   任何异常都 **fail-open**（阻塞事件里崩溃=所有工具调用被拦，伤害远大于漏拦一次）。

两条都不做业务拦截（业务护栏在 MCP 的 `safety/policy.json` 与两段式里，见 docs/safety-model.md）。

## 为什么是"宿主无关脚本"，不是宿主插件

| 维度 | 插件包（旧） | 宿主无关脚本（现行，D-hook-unify-1） |
|---|---|---|
| 谁来加载 | 宿主进程内 import 我们的 Python 包 | 宿主按 `config.yaml` 的 `hooks:` 声明**拉子进程** |
| 生效开关 | `plugins.enabled` 名单 | 宿主自己的 consent 机制（hermes 按 `(event, command)` 首次同意） |
| 进程隔离 | 无（与宿主同进程） | 有（子进程，崩溃不牵连宿主） |
| 换宿主成本 | 每个宿主一套插件 API 适配 | 脚本不动，换注册方式即可 |
| 目录占用 | 根上一套 `hermes-plugin/` 特例 | `hooks/` 一个目录，跟载荷一起发 |

线协议（hermes shell hook，见其 docs「Shell Hooks → JSON wire protocol」）：

```
stdin:  {"hook_event_name":"pre_llm_call","extra":{"user_message":"…"},"session_id":…,"cwd":…}
stdout: {"context":"要追加到本轮用户消息的文本"}    命中
        （空输出）                                  未命中 = 零注入
```

判据（确定性规则，模型不参与；详细口径见 design.md「预采集路由的判定链与词表纪律」）：

- 信封（内部通知/后台回执/压缩摘要/【内部通知】…）→ 先剥掉；剥完若没有「用户在说话」
  的标记就不判（S212/S219：宿主信封不是用户原话，但信封后面跟的用户指令不许被吞）；
- 显式前缀「提交反馈」→ 强指令（短路，不再判意图；任何排除规则都不得压掉它）；
- 命中 `TRIGGER_WORDS`（现象词：报错/卡死/失败/打不开/超时/崩/白屏/没反应…；建议词：
  希望支持/建议增加/能不能…；口语词：太慢/太麻烦…）→ 常规采集指令；
  词表必须覆盖 SKILL 里教模型的现象词（同一份真源，别造两份）；
- 只命中 `DISABLE_WORDS`（失能词：用不了/没法用/挂了/闪退/丢了/没动静/转圈/不回/难用…）
  → 同样算采集意图（S211），但若同时命中**工程对象**（配置文件/字段/数据集/缓存/模板/
  日志/库表/服务/脚本…）且没有用户视角锚点 → 零注入（S218：工程师在说自己的代码）；
- 命中 `META_WORDS`（代码/用例/门禁/文档/评审/方案/工程动作词/工程第二层 CI·构建·编译·
  流水线·发布…）且不含 `ANCHOR_WORDS`（页面/按钮/登录/导出/加载/点击/体验…）→ **零注入**：
  这是在讨论产品反馈这件事，不是用户的反馈；
- 其它 → 零注入（不刷屏）。
- 载荷不可解析 / 非字符串消息 → 不做任何事、退出码 0（钩子绝不能打断宿主这一轮）。

每个结论都带可审计标签（`empty`/`envelope`/`strong-prefix`/`no-trigger`/
`engineering-object`/`meta-discussion`/`trigger`/`disable`），由 `vod_router.REASONS`
声明并有用例断言与文档同步。

已知边界（明写成本）：词表是子串匹配，「工程对象 + 用户抱怨」的混合句（如「构建太麻烦了」）
会被压掉；用户用了未收录的口语名词会漏。收敛方式是**加语料**（`tests/test_router_corpus.py`）
而不是加词——每轮新发现的误判/漏判原文都要登记成语料用例。

## 我们验证到哪一步（诚实记录）

| 环节 | 证据 |
|---|---|
| 链路 A：install 写注册 | `install --target hermes` 后 `~/.hermes/config.yaml` 出现 `hooks.pre_llm_call` 条目（临时 HOME 实测） |
| 链路 B：宿主识别条目 | `hermes hooks list` 列出该条目（`✗ not allowlisted` = 等首次同意） |
| 链路 C：真拉起子进程 | `hermes hooks test pre_llm_call --payload-file <flat>` → `exit=0`、`parsed (Hermes wire shape): {"context": …}` |
| 链路 D：真实会话注入 | **未验**：需真实会话里批准一次 consent（`✗ not allowlisted` 就是它）。不写成"已生效"。 |

`hermes hooks test` 的载荷合并只到顶层：把 `user_message` 放在 `extra` 里时测试工具看不到
（脚本本身两种形状都能读，真实会话给的是 `extra`）。这条差异写在这里，免得下次又当成"脚本坏"。

## 迁移与回滚

- 老装机（0.3.x-0.5.x 的插件形态）在 install 时被清理：删 `~/.hermes/plugins/vod-feedback-router`
  并从 `plugins.enabled` 去名——**否则插件与 hook 双份注入**（每轮两段指令，行为不可预测）。
- 回滚：`uninstall --target hermes` 摘 hook 条目（只摘含 `vod_router.py` 的那条）与旧插件，
  其它事件与别人的 hook 一律不动。

## 读 Key 拦截（`pre_tool_call`，已落地，本机实测口径）

| 维度 | 取值 |
|---|---|
| 触发条件 | ①命令含 `runtime.json` 且含读取类动词（cat/head/tail/grep/jq/python…）；②`env`/`printenv`/`set` 且点名 `VOD_*KEY`/`java_key` |
| 动作 | stdout `{"decision":"block","reason":…}`（Hermes 的阻塞方言） |
| 放行 | 其它工具、其它命令、空/坏载荷、脚本异常 —— **fail-open** |
| 关闭 | env `VOD_HOOK_READ_GUARD=0`，或 `hermes hooks revoke <command>` |
| 替代路径 | 想看凭据档位 → `vod-devkit auth status`（只出指纹）；只想确认变量名 → `env \| cut -d= -f1 \| grep '^VOD_'` |

为什么只做这两类：它们是**已经实测发生过**的泄漏路径（技能里的"排障只引指纹"被反复违反）。
「未审批写」已有 MCP 护栏与两段式，不在这里重复一层——两层规则会让"到底谁拦的"说不清。

## 尚未做的（诚实标注，不假装）

- codex / opencode 侧的等价注册：未探（这两个宿主的 hook 机制形态与本仓未对齐，没做就等于没有）。
- 远程面：钩子只在客户端本地生效，远程面不提供（无对象）。