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
| 准备采集前确认身份（尤其 MCP 单独部署/无 key） | `vod_auth_ensure`（有可用令牌就复用，没有则由服务代理领匿名令牌；幂等，一次会话调一次） |
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

## 身份准备（MCP 单独部署 / 无 key）

采集前要确认身份时，调 **一次** `vod_auth_ensure`（幂等，不要每次工具调用都调）：

| 返回 | 处理 |
|---|---|
| `verified=true` | 直接继续采集；`source` 说明身份来源（`env` 显式 key / `runtime` 本机令牌 / `new-anonymous` 刚领的匿名令牌） |
| `verified=false` + `reason=rejected` | 显式 key 被引擎拒绝：告诉用户换一把有效 key，**不要**改走匿名档掩盖配置错误 |
| `verified=null` + `reason=unreachable` | 网络问题不是身份问题：如实说"暂时无法确认身份"，不要领新令牌 |

不读环境变量、不翻 `runtime.json`/state 文件判断身份——那是服务进程的事（读也会被 hook 拦回，
只引指纹）。匿名档额度是**整机共享**的：别的宿主用多了，这里也会提前撞上限，属于正常语义。

MCP 独立部署（同机常驻 server，agent 用 HTTP 连 127.0.0.1:9528）与本地 stdio **同一套流程**：
照样调 `vod_auth_ensure`（带 Authorization 就是请求头身份，不带就用整机匿名令牌）；
两段式 `vod_draft_voices`/`vod_commit_voices` 与 `vod_list_submitted` 在远程面同样可用，
但草稿只能由创建它的那个 agent 提交（按宿主隔离，串了会报"不属于当前客户端"）。
唯一远程没有的是 `vod_packs_configure`（进程内开关）。

## 宿主差异：dsh 的工具名带前缀

- dsh（装了 `@deepseek-ai/dsh-mcp-client` 的版本）**工具由 MCP 承载**，注册名是
  `mcp__vod-devkit__vod_search_products` / `mcp__vod-devkit__vod_auth_ensure` /
  `mcp__vod-devkit__vod_submit_voices` …（能力面与其它宿主一致）。
- 没有 mcp-client 的降级形态，工具由 dsh 壳自注册，只有 6 个**短名**
  （vod_submit_voices / vod_list_submitted / vod_devkit_info / vod_list_skills /
  vod_retrieve_skill / vod_check_update），没有 ensure / draft / commit。
- 调用前**以宿主 tools/list 里的实际名字为准**；两种形态的采集纪律、同意前置、原话逐字
  完全相同，只是名字前缀不同。