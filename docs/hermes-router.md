# vod-feedback-router：Hermes 强制评估路由钩子（D-hook-1）

## 背景

采集技能自动激活是概率性的（业界实测：无钩子/简单指令钩子 ~20%，与无钩子
无统计差异；强制评估注入 ~84%；显式调用 100%）。实锤事故：本机 hermes
运维上下文压过采集意图——用户说「产品体验不好」被反问「哪个产品？要截图
复现」，技能正文根本未加载。描述触发词前置（8bdc225）只修「可见预算」，
修不了概率路由本身。

## 机制（forced-eval 模式）

Hermes 插件钩子 `pre_llm_call`：每轮用户消息进入主循环前触发，回调返回
文本注入当轮 user message。本插件 `router.route()` 做**确定性关键词判定**
（非模型判断）：命中采集意图 → 注入短指令（承诺机制）；未命中 → None
（零注入零噪音）。

- 显式前缀「提交反馈」→ 强指令（无需再判断意图，100% 语义）
- 口语变体（体验差/太慢/卡/报错/希望支持…）→ 采集流程指令
- 已知边界（拍板接受）：「报错/卡」在纯排障对话也会命中——错注入无害
  （指令只要求走采集确认流程，不自动提交）；漏注入才是事故

## 安装

```
cp -r hermes-plugin/vod-feedback-router ~/.hermes/plugins/
hermes config set plugins.enabled <已有列表> + "vod-feedback-router"
```
plugins.enabled 是显式同意门（第三方代码默认不运行），需手动加名。

## 用例（tests/test_router.py）

| 用例 | 场景 | 预期 |
|---|---|---|
| H1 | 显式「提交反馈：」前缀 | 强指令（无需判断意图） |
| H2 | 口语抱怨变体 | 采集流程指令（含禁问产品/禁排查模式） |
| H3 | 普通对话/操作请求 | None 零注入 |
| H4 | 空/非字符串边界 | None |

## 边界与不做

- 注入仍是给模型的指令，不改变模型服从性天花板——提交侧硬保障仍是
  方案 A 回显 + 护栏 confirmed=false 拒绝
- 仅 Hermes 宿主可装（pre_llm_call 是 Hermes 插件面）；opencode/codex
  的对应能力待各宿主钩子面调研（opencode 有 plugin 体系待查）

## 多宿主对表（2026-11-06，opencode/codex/dsh 是否需要同款路由）

| 宿主 | 激活现状（实测） | 截断暴露 | 强制评估可行性 | 结论 |
|---|---|---|---|---|
| hermes | 概率性，运维上下文实锤压过 | 57 字符索引预算（触发词已前置） | ✅ pre_llm_call 钩子（已落本插件） | 已覆盖 |
| opencode | 实测自动激活成功一次（`→ Skill vod-feedback-collect`）；业界反馈自动触发概率低 | 官方 Skills 文档：description 限 1–1024 字符（可断言上限）；工具输出另有 2000 行/50KiB 通用截断——本仓描述远低于两者，非瓶颈 | ✅ 可做：官方通道=prompt admission hook（钩子收到可变 draft，编辑即成持久化用户输入）+ session.prompt 合成消息注入（noReply+synthetic）；社区先例 opencode-skill-activation（主动建议候选技能） | P2 保留，前提高已结案——缺的是自研实现，不是能力 |
| codex | 技能已装（~/.codex/skills，5 个远低于 #24299 的 20+ 截断阈值）；$ 显式调用是官方激活路径（Build skills 文档：/skills 或 $ 提及） | 技能少无忧（官方默认预算=上下文 2%/8,000 字符，可调 skills.max_context_tokens 至 10k tokens；5440 为本机实测值非官方常量）；注入路径不一致（#37463） | **不做：钩子面存在（官方 Hooks 文档列 UserPromptSubmit/PreToolUse/Stop 等事件），但钩子输出自身被截断（实测 ~4,866 tokens）+ 注入路径不一致（#37463），收益不抵成本**；官方同时推荐描述前置（截断时仍可匹配）与惰性路由方向（#33945） | 接受显式兜底（「提交反馈：」前缀），不上 wrapper |
| dsh 壳 | MCP 工具常驻注册，无激活问题 | **500 字符描述窗口——D-desc-budget-1 门禁已锁**（先决条件<500） | cordis 侧理论可实现消息钩子 | 已由预算门禁覆盖；路由插件低优先 |
| dsh UI | 部署注入形态（fail-fast 必配），无激活环节 | 不适用 | 不适用 | 天然免疫 |

通用兜底（全宿主）：「提交反馈：」显式前缀 = 100% 确定性入口。
语义路由不做（M5 相似度未校准红线同款）。

## 来源分级（2026-11-06 复核）

- **官方文档可引用**：codex（learn.chatgpt.com Build skills/Hooks：8000 字符默认预算、
  UserPromptSubmit 等事件表、$ 显式调用、描述前置官方推荐）；opencode
  （docs.opencode.ai skills：1–1024 字符 description、prompt admission hook、
  skill tool 按需加载）
- **内部拍板/实测（无公开官方文档，复核只能回到内部记录）**：hermes 57 字符
  索引预算（实测观察）；dsh 500 字符描述窗口（D-desc-budget-1 门禁+实测）；
  dsh 壳无激活环节/UI 免疫（架构设计推论）
- 复核纪律：引用本矩阵时按行区分「官方依据」与「内部依据」，二者不得混写
