# 钩子（hook）规则模型

本仓只有一个宿主钩子：**预采集路由**（`hooks/vod_router.py`）。它回答一个具体问题——
"这一轮用户的话，该不该进入采集流程"，而不做安全拦截（安全拦截在 MCP 护栏与两段式里，
见 docs/safety-model.md）。

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

判据（确定性规则，模型不参与）：

- 显式前缀「提交反馈」→ 强指令（短路，不再判意图）；
- 命中 `TRIGGER_WORDS`（体验差/太慢/卡/报错/希望支持…）→ 常规采集指令；
- 其它 → 零注入（不刷屏）。
- 载荷不可解析 / 非字符串消息 → 不做任何事、退出码 0（钩子绝不能打断宿主这一轮）。

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

## 尚未做的（诚实标注，不假装）

- `pre_tool_call` 拦截（读 `runtime.json`、`env` 导出、未审批写）：机制已确认存在
  （shell hook 支持 `block`/`fail_closed`，`exit 2` 也能拦），但规则表与 host 覆盖还没做。
- codex / opencode 侧的等价注册：未探。
- 远程面：钩子只在客户端本地生效，远程面不提供（无对象）。