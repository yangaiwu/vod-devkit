# VOD 反馈采集意图路由 设计文档

版本：v1.0（2026-11-06）

## 一、架构

```
用户消息 ──► Hermes pre_llm_call 钩子（每轮，主循环前）
                │
                ▼
        router.route(user_message)   ← 纯函数，确定性关键词判定
                │
        ├─ 命中「提交反馈」前缀（前20字符内）──► 强指令注入
        ├─ 命中 TRIGGER_WORDS 任一 ────────► 采集流程指令注入
        └─ 未命中 ────────────────────────► None（零注入）
```

- 载体：Hermes 插件 `~/.hermes/plugins/vod-feedback-router/`
  （plugin.yaml provides_hooks: pre_llm_call；__init__.py register(ctx)
  注册钩子；router.py 纯逻辑+组装）
- 注入点：返回文本追加到当轮 user message（保 prompt cache，不动
  system prompt）；每轮一次，不漏轮次

## 二、规则表（单一事实源）

TRIGGER_WORDS 元组（提交反馈/提单/体验不好/体验差/体验很差/体验糟/太慢/
很慢/回复慢/响应慢/卡顿/卡死/卡/不好用/很难用/报错/有bug/有 bug/出bug/
希望支持/建议增加/要是能/为什么不能），正则由 `re.escape` 自动组装——
新增触发词零正则知识。指令文案为 DIRECTIVE/STRONG_DIRECTIVE 常量。

## 三、用例承载表

| 用例 | 场景 | 预期 | 代码承载 | 测试承载 |
|---|---|---|---|---|
| H1 | 显式「提交反馈：」前缀（含句中前20字符出现） | 强指令（含「无需再判断意图」） | route() 前缀分支 | test_h1 |
| H2 | 口语抱怨变体（体验差/太慢/卡/报错/希望支持/为什么不能…） | 采集流程指令（含禁问产品+禁排查模式） | TRIGGER_WORDS 正则 | test_h2 |
| H3 | 普通对话/操作请求（部署/日志/重构…） | None 零注入 | route() 未命中分支 | test_h3 |
| H4 | 边界：None/空串/纯空白/非字符串 | None 不抛 | route() 入口守卫 | test_h4 |
| R5 | 长句内嵌抱怨词（非开头） | 命中（正则全文搜索） | 同 H2 | R5 补测 |
| R6 | 多行消息（含换行的组合反馈） | 归一后正常判定 | strip+search | R6 补测 |
| R7 | 规则表单一事实源 | 正则由 TRIGGER_WORDS 组装，改表即生效无双处漂移 | 模块组装行 | R7 补测 |
| R8 | register 契约 | 注册到 pre_llm_call，回调透传 user_message | register()/_on_pre_llm_call | R8 补测 |

## 四、业界对表（2026-11-06）

见 docs/hermes-router.md（激活率数据/截断预算/多宿主矩阵）。本设计取
「确定性触发词表短路」层，语义路由不做（M5 红线同口径）。

## 五、边界与已知取舍

- 错注入无害：指令不自动提交，只要求走采集确认流程；漏注入才是事故
- 路由规则与「复现排查」场景存在词面重叠（报错/卡）——接受误命中，
  由模型在技能流程内先确认意图二次消歧
- 提交侧硬保障不在本层：方案 A 回显 + confirmed=false 护栏不变

## 五、多宿主对表与来源分级（2026-11-06 复核，负责人确认）

完整矩阵见 docs/hermes-router.md。要点：

- **opencode**：强制评估可做已结案（官方通道=prompt admission hook +
  session.prompt 合成消息注入；社区先例 opencode-skill-activation）——
  P2 保留，缺的是自研实现不是能力
- **codex**：钩子面存在（官方 Hooks 事件表含 UserPromptSubmit）但不做——
  钩子输出自身截断（实测 ~4,866 tokens）+ 注入路径不一致（#37463）收益
  不抵成本；预算参照官方默认 8,000 字符（2% 上下文，可调
  skills.max_context_tokens；5,440 为本机实测值非官方常量）
- **dsh**：500 字符描述窗口由 D-desc-budget-1 门禁锁死（先决条件<500）；
  壳=工具常驻注册无激活环节；UI=部署注入形态天然免疫
- **来源分级纪律**：官方文档可引用（codex/opencode）与内部拍板/实测
  （hermes 57 字符预算、dsh 500 窗口）分行标注，不得混写

### 场景用例（M1，测试承载 tests/test_desc_frontload.py）

| 用例 | 场景 | 预期 | 测试承载 |
|---|---|---|---|
| M1a | 描述前置可见预算 | SKILL.md description 前 57 字符含核心触发词（体验差/提单/太慢） | test_m1_trigger_words_within_visible_budget |
| M1b | 描述长度上限 | ≤400 字符（Anthropic 指南量级，防挤占预算） | test_m1b_description_length_bounded |
| M1c | 词表一致性 | description 触发词 ⊆ router.TRIGGER_WORDS（两处防漂移） | test_m1c_description_triggers_aligned_with_router_table |
