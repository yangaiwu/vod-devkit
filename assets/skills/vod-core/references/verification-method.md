# 验证方法（vod-core）

本文给**验证入口**，断言以 `docs/proposal.md` 与 `tests/` 为准，不在此复制。

## 1. 路由一致性（静态，秒级）

```bash
python3 -m pytest tests/test_skill_structure.py -q   # 路由表引用真实技能 + 触发词不互抢
python3 -m pytest tests/test_structure_guards.py -q  # 契约==实现、policy 结构
python3 -m pytest tests/test_desc_budget.py -q       # 描述截断预算
```

期望：路由表里出现的每个 `vod-*` 技能真实存在于 `skills/`；反向每个技能都被
路由表覆盖（否则装了不可达）。

## 2. 会话内自检

- 列出可用工具，逐一对照本文路由表：表里写了但工具面没有的条目 = 当前传输面裁剪
  （远程面没有 draft/commit/list_submitted，属预期，不是故障）
- 问"有哪些技能"时用 `vod_list_skills` 回答，不自报记忆里的名单

## 3. 装机面

`vod-devkit doctor` 全绿（技能名册逐落点对账）；`vod-devkit status` 的
`transport` 字段决定按哪个面解释路由表。

## 关联用例

路由与披露 S11-S16 / S45-S48；归因链 S91-S100（productSource 口径）。