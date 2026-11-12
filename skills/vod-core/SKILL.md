---
name: vod-core
description: 'VOD 用户声音采集插件的路由入口与纪律速查。遇到"提交反馈/采集用户声音/这条反馈入库没有/问题分类与评分规则是什么/插件版本与来源/key 认证状态"类请求先读本技能，再按表路由到具体工具或领域技能。采集写操作必须先获用户明确同意。'
tags: [vod, feedback, routing]
metadata:
  version: 2
---

# VOD Core（路由与纪律）

本插件只做**用户声音采集**：把用户对本产品的抱怨/建议/期望原话送进 VOD 囤积区。
分析与运营归 vod-system 前端，插件没有、也不该有发起分析的入口。

## 意图 → 工具

| 意图 | 动作 |
|---|---|
| 用户抱怨/建议，要提交 | `vod_submit_voices`（先征得明确同意，再传 `confirmed=true`）；话术见 `vod-feedback-collect` |
| 想先暂存、等用户确认后再提交 | `vod_draft_voices` → 用户确认 → `vod_commit_voices`（一次性令牌 + payload 校验）**仅 stdio 面可用**：远程 MCP 面没有这两个工具，改用 `vod_submit_voices` 单发 |
| 本机已提交过哪些（进度追问） | `vod_list_submitted`（本地账本口径，换机不保留）**仅 stdio 面可用**；远程面改答"本条收录状态" |
| 插件版本/来源核验 | `vod_devkit_info`（version + commitSha） |
| key/认证状态、引擎连通性 | `vod_auth_status`（只报指纹，不下发明文） |
| 有哪些技能、规则技能是否可用 | `vod_list_skills` |
| 取规则技能全文（分类/评分口径） | `vod_retrieve_skill`（owner pack 被裁剪时返回恢复指引） |

## 意图 → 领域技能

| 主题 | 技能 | 加载方式 |
|---|---|---|
| 采集话术/确认时机/原话逐字纪律 | `vod-feedback-collect` | 宿主原生加载（元技能，已装进本机技能目录） |
| 六类问题分类口径（引擎 v2.2 真源） | `vod-problem-classification-rules` | 原生副本优先；读不到或怀疑过期时用 `vod_retrieve_skill` |
| 四项评分公式（引擎 v2 真源） | `vod-scoring-rules` | 同上 |

## 纪律（违反即事故）

1. **同意前置**：用户陈述反馈 ≠ 同意提交。先承接、再问"要提交给产品团队吗"、
   再用一句固定的引导补充话术，一次说完。
2. **原话逐字**：`content` 放用户原话，禁改写/概括/增删语气词；回执
   `echo.contents` 必须逐字转述给用户（「已收录原话：…」）。
3. **归因必问一次（D-product-ask-1）**：产品未定时，先问用户"这条是哪个产品的反馈？"
   （用 `vod_search_products` 给 3-5 个候选），回答填 `product`；
   用户说的产品不在名录（"智果"/打错）→ 不按原名提交，用 `vod_search_products` 给候选
   再确认一次；仍对不上就不提交。
   用户明确说不知道/随便 → `productNotSpecified=true`，插件**不猜也不提交**，
   由你告知用户"没有产品归属的反馈不提交"并请他补充产品。
   **不许不填直接提交**（插件会以 -32010 拒绝并给候选）。
4. **篇幅边界**：content ≤ 2000 字、单批 ≤ 50 条（护栏强制，超限直接拒）。
5. **不碰内部面**：不尝试数据库直连、不读取或打印凭据；被 deny 时如实告知，
   不要换措辞重试。
6. **规则口径以技能/披露内容为准**：不凭训练数据回答 VOD 分类与评分——
   vendored 文本与引擎代码同源。