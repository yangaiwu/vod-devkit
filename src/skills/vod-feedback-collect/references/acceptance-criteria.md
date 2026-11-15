# 验收标准（vod-feedback-collect）

上线/改版前逐条勾选；每条都指向可执行的验证入口（见 references/verification-method.md）。

## 功能

- [ ] content = 用户原话逐字（含语气词与原标点），模型不补写、不概括
- [ ] 用户明确同意才提交；"用户说了一条抱怨"不构成同意
- [ ] 回执 `echo.contents` 原样转述，每条以「已收录原话：」开头
- [ ] 固定追问至多一次、逐字使用；答"没有/跳过"=两字段不上送
- [ ] 电话/路径类敏感内容按 policy 处理（当前策略=拒收，不脱敏）
- [ ] 无通道场景落盘 `pending-feedback.jsonl`，恢复后自动补交，用户侧只说人话

## 归因（D-attrib-B）

- [ ] 字面证据唯一命中才采信；多命中落 UNKNOWN 且保留全部片段
- [ ] 记忆只在 0 命中时启用（30 分钟窗口），新证据无条件覆盖
- [ ] 模型自报 product 不采信（仅回执 `ignoredRuntimeProduct`）

## 传输面

- [ ] stdio 面：两段式工具可用时走 draft→commit
- [ ] 远程面：无 draft/commit/list_submitted 时不承诺两段式与本机账本查询

## 非功能

- [ ] `SKILL.md` ≤ 500 行；改动后四个宿主装机副本已刷新（md5 对上）
- [ ] `tests/test_skill_structure.py` 与 `sync_case_roster.py --check` 全绿