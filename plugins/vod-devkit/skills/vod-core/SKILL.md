---
name: vod-core
description: 'VOD 用户声音分析插件路由入口。任何"分析用户声音/反馈、发起 VOD 分析任务、查任务状态/结果、VOD 评分/分类规则、KB 检索"类请求先经本技能路由到对应工具与领域技能。写操作（发起分析）必须先获用户确认（confirm 护栏）。'
version: 1
---

# VOD Core

VOD 分析能力入口。按意图路由：

| 意图 | 动作 |
|---|---|
| 发起分析 | 工具 vod_run_analysis（confirm：必须用户确认后传 confirmed=true；taskId 为对账主键） |
| 查任务进度/结果 | vod_task_status / vod_task_result |
| 知识库检索 | vod_kb_search |
| 插件自述/来源核验 | vod_devkit_info |
| 分类匹配/问题分类/评分规则 | 领域技能（由 vendor 机制从 VOD-Project 真源拉取：vod-category-matching / vod-problem-classification / vod-scoring-rules） |

纪律：
1. 任务 ID 是唯一对账主键，发起后一切追问以 taskId 对账，不凭记忆描述
2. 单任务条数上限、product 白名单由护栏强制，超限直接拒
3. 任何 DB 直连/凭据读取意图会被 deny——不要尝试
4. 领域规则以 vendored 技能文件为准，不凭训练数据回答 VOD 评分口径
