# 验证方法（vod-feedback-collect）

本文只给**验证入口**：断言细节以 `docs/proposal.md` 的用例与 `tests/` 的实现为准，
不在本文件复制断言（避免第二真源）。改技能正文后按本文件跑一遍。

## 1. 静态门禁（本地/CI，秒级）

```bash
python3 -m pytest tests/test_desc_budget.py tests/test_attribution.py \
                 tests/test_pending_feedback.py tests/test_two_phase.py -q
python3 -m pytest tests/test_skill_structure.py -q   # frontmatter/触发词/路由一致性
python3 scripts/sync_case_roster.py --check
```

期望：全绿；技能文件与 `plugins/vod-devkit/skills/` 副本逐字节一致（CI 双副本 diff）。

## 2. 会话内自检（模型侧，无外部依赖）

- 可用工具里有 `vod_draft_voices` → 两段式；没有 → 单发 `vod_submit_voices`（远程面）
- 回执必须带 `echo.contents`，逐字转述；被改写即为失败
- 归因看 `productSource`：`user_input`/`memory`/`install_binding`/`unknown` 之一
- 多产品命中（`unknown` + evidence>1）不得自行择一提交

## 3. 端到端（真宿主）

对应 `docs/decisions.md` 里的四宿主验证配方：装新 skill 副本 → 新会话说一条抱怨 →
查账本 voiceId 与引擎行；行为类回归见 `scripts/e2e_behavior.py`（仅本机运行）。

## 关联用例

话术 S49-S53；追问与拼接 S63-S73；无通道 pending S87-S90；归因链 S91-S100。