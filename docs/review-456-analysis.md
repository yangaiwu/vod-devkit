# vod-devkit 远程面 ④⑤⑥ 专项分析（2026-11-19）

> 范围：2026-11-18 review 留下的三项低优先级问题。
> **状态：三项已全部实施完毕（2026-11-19）**，实施时对本文有两处修正，见 §8。
> 所有结论都标注了「已核实」或「推断」，核对到文件:行号。

## 0. 一句话结论

| # | 问题 | 真实严重度 | 建议 |
|---|---|---|---|
| ④ | 草稿 owner 跟着作用域漂 | **比审查描述更严重**：不只是自己草稿失效，而是 A 的草稿能被 C 提交 | 修（P1），成本低 |
| ⑤ | 无 session 兜底每请求新建会话 | 确认成立。TTL 内**真占额**，非无限累积；但裸客户端高频 = 会话池被灌满 → **503 是会话上限，不是 413** | 修（P1），有哨兵方案 |
| ⑥ | `X-Vod-Agent-Id` 自由头可冒用 | 成立，但**危害被高估**：它不能越过"会话 owner"校验，只在无 session 时分桶出错 | 文档注记 + 一处校验（P2） |

## 1. 背景：作用域怎么算（后面三项都依赖这段）

`_resolve_scope`（`src/vod_mcp/runtime_state.py:330-394`）按优先级出 key：

| 序 | 条件 | key | grain | 代码位置 |
|---|---|---|---|---|
| ① | 有 `X-Vod-Agent-Id` 头（不含 `session:` 前缀） | `agent:<aid>` | request | `:363-366` |
| ② | 有 `mcp-session-id` | `sess:<sid>` | request | `:368-373` |
| ③ | stdio 面 | `proc:@<HOME>` 或 `proc:<pid>` | process | `:375-390` |
| ④ | 远程面且无任何标识 | **None（读写皆禁）** | — | `:392-394` |

`_session_key()`（`:416-422`）就是 `_resolve_scope()["key"]` 的一层包装。
**所有隔离能力（记忆、追问计数、nonce、草稿 owner）都建立在这一个 key 上。**

## 2. ④ 草稿 owner 跟着作用域漂——实测比描述严重

### 2.1 现状代码

草稿创建时把 owner 写成**当时的 key**：

```python
# src/vod_mcp/packs/collect.py:575
"owner": rt._session_key(client_info),
```

提交时比对：

```python
# src/vod_mcp/packs/collect.py:632-636
owner = draft.get("owner")
if owner and owner != rt._session_key(client_info):
    raise net.ToolError("这份草稿不属于当前客户端…", code=-32011)
```

### 2.2 审查描述的"自己草稿失效"——成立

三种会让**同一个 agent 的 key 变化**的场景（已核实代码路径）：

| 场景 | 为何 key 变 |
|---|---|
| 进程重启 | stdio 面 `proc:<pid>` 换 pid；远程面 `mcp-session-id` 全丢 |
| 重新 initialize | 新 sid → `sess:<新sid>`；旧草稿 owner 是 `sess:<旧sid>` |
| 客户端升级/重连不带 agent 头 | 从 `agent:X` 掉回 `sess:Y` |

后果：用户已经确认了内容、正要提交，突然报"不属于当前客户端"。**这是可用性事故，且话术完全误导**——用户会以为被人截了。

### 2.3 审查**没说到**的问题：跨 agent 冒用（真安全问题）

关键在 `:363-366`——**`X-Vod-Agent-Id` 的优先级高于 session**。于是：

```
A（带 X-Vod-Agent-Id: alice）draft_voices → owner = "agent:alice"
C（带 X-Vod-Agent-Id: alice）commit_voices → _session_key = "agent:alice" → owner 相等 → 放行 ✅
```

C 与 A 不是同一个会话、也不在同一台机器（只要 A 的 agent id 被猜到/在日志里露过），
**C 就能提交 A 的草稿**。而两段式设计的初衷（`design.md:1294`）恰恰是
"草稿归属隔离，不同 clientInfo 提交一律 -32011"。

同理反向：A 用 `session:` 建草稿，之后同一个人带 `X-Vod-Agent-Id` 来提交 →
`agent:alice` ≠ `sess:xxx` → 自己的草稿被拒。**两人共用同一个 owner 字段，
职责已经混了：它既当"隔离边界"又当"找回凭据"。**

### 2.4 方案（两个，成本差别很大）

**方案 A（推荐，改动小）：owner 只认会话边界，不认 agent 头**

```python
# collect.py:575 —— owner 用"会话指纹"，与记忆分桶解耦
"owner": rt._draft_owner(client_info),   # sess:<sid> / proc:<pid> / None
# collect.py:633 —— 比对同一个函数
if owner and owner != rt._draft_owner(client_info): raise -32011
```

- 新增 `runtime_state._draft_owner()`：只取 `session_id` 或 `proc`，**永远不看 `X-Vod-Agent-Id`**
- 效果：C 冒用 `X-Vod-Agent-Id: alice` **不再能提交** A 的草稿（修复 2.3）
- 代价：agent 头跨会话共享记忆的能力不受影响（记忆仍走 `_session_key`），
  但"跨会话续草稿"本来就不该支持——草稿 10 分钟 TTL + 一次性消费，本来就绑会话
- 对 2.2 的"自己草稿失效"**不修复**（进程重启换 pid 仍是换 owner）——这是**正确行为**，
  因为跨进程无法证明是同一个调用方；但话术必须改

**方案 B：owner 改成"多凭据集"，任一匹配即放行**
把 `sess:`/`agent:` 都记进去，比对时取交集。能修 2.2 的 agent 头场景，
但**同时放大了 2.3 的冒用面**（A 的草稿被记了 agent 维度，C 带上就进）。
不推荐。

### 2.5 顺带的必须项：话术分档

现在两种完全不同的原因返回**同一句话**（`collect.py:634`）：

| 真实原因 | 现在的话术 | 应改成 |
|---|---|---|
| 会话变了（重启/重连） | "不属于当前客户端" | "草稿绑定了原会话（进程重启/重连会変），请重新 vod_draft_voices" |
| 别的 agent 冒用 | 同上 | "不属于当前客户端"（保持，不泄露存在性） |

判据：`owner` 的**前缀**——`sess:` 变化 ≈ 自己；`agent:` 完全不匹配 ≈ 可疑。
两者都回 -32011，但 hint 不同。

## 3. ⑤ 无 session 兜底每请求新建会话——确认成立，但要精确化

### 3.1 现状代码

`transport_remote.py:155-161` → 每个请求先走 `_ensure_session_for_sideless()`：

```python
# transport_remote.py:238-239
if (headers.get("mcp-session-id") or "").strip():
    return None          # 已有会话 → 标准路径
```

没有 session 的非 initialize 请求，就**当场内部握手一次拿新 sid**（`:251-284`），
然后把 sid 塞进 scope 交给 manager。所以：

```
裸客户端 POST tools/call（无 session）
  → 内部 initialize → 新 sid #1 → 执行
  → 下次 POST tools/call（还是无 session）
  → 内部 initialize → 新 sid #2 → 执行
```

**每次调用一个新会话，确认。** 记忆也不延续（README:426 已如实写"记忆不延续"）。

### 3.2 精确定量（已核实 SDK 源码）

| 事实 | 证据 |
|---|---|
| 默认会话上限 **10000** | `DEFAULT_MAX_SESSIONS = 10000`（`mcp.server.streamable_http_manager`） |
| 超限返回 **503 "Too many open sessions"** | `_handle_stateful_request` 里 `_admit_session() is None` → `_error_response(..., 503, INTERNAL_ERROR)` |
| 会话**不会**随请求结束销毁 | `_serve_opening_request()` 里 `run_server` 常驻，只有 idle timeout / DELETE / crash 才 `_discard_session` |
| idle timeout 从"最后一个在飞请求完成"起算 | `streamable_http.py`：`_requests_in_flight` 归零后才起算 |
| TTL = 1800s | `transport_remote.py:96` `session_idle_timeout=_rt_ttl.SCOPE_TTL_SEC`，`SCOPE_TTL_SEC = _SESSION_TTL` |

所以审查者算的 **1 req/s × 1800s = 1800 个常驻会话**是**对的**。
但要说准一点：**不是无限累积**，是 30 分钟滑动窗口内"无 session 请求速率 × 1800"。
达到 10000 的门槛是持续 **5.6 req/s** 的裸客户端，或 6 个 1req/s 的并发裸客户端。

补充一条我需要纠正审查口径的：`ack 说 413` 是 `max_request_body_size` 的行为，
**会话超限是 503**（SDK 文档字符串明确写 "receives a 503 response"）。两者别混。

### 3.3 危害分级（诚实版）

| 场景 | 是否真受害 |
|---|---|
| 裸客户端低频（人工调试、一次性脚本） | **不受害**。几个会话，30 分钟后自己回收 |
| 裸客户端常驻高频（自研集成 1 req/s） | **受害**。~5.6 req/s 撑满，之后**所有客户端（含标准客户端）拿 503**——因为上限是进程级共享的 |
| 标准客户端 | **不受害**，走 `mcp-session-id` 正常路径 |

所以这是个**可用性放大**问题：一个不守规矩的客户端能打挂守规矩的。
**不是安全问题**（不串桶、不越权，每次都是独立会话 + `key=None` 读写皆禁）。

## 4. ⑥ `X-Vod-Agent-Id` 自由头当身份用——成立，但危害要降级

### 4.1 现状

```python
# remote_app.py:67 —— 直接取头，无任何校验
aid = h.get("x-vod-agent-id", "").strip()
```
`:74` `"agent_id": aid or (f"session:{sid}" if sid else "")`，然后
`_resolve_scope:363` 就把它当成 `agent:<aid>` 用。**无签名、无绑定、无格式约束。**

### 4.2 危害到底有多大（逐一核对，别夸大）

| 声称的危害 | 核实结果 |
|---|---|
| 冒用他人身份读他人记忆 | **可以**。带 `X-Vod-Agent-Id: alice` 就能命中 `agent:alice` 的记忆桶，读到 A 说过的产品/追问计数 |
| 冒用身份提交他人草稿 | **可以** —— 见 §2.3，这是 ④ 和 ⑥ 的合成漏洞 |
| 越过鉴权提交声音 | **不能**。提交仍走 Bearer / 匿名令牌，`X-Vod-Agent-Id` 不参与认证 |
| 消耗他人额度 | **不能直接**。额度绑令牌，不绑 agent id |
| 跨机冒用 | **可以**，只要网络能连到端口（默认只绑回环，风险限于同机/内网） |

结论：**它是"分桶标签被当成了身份"，不是"认证被绕过"。**
真实危害 = 记忆串味 + 草稿越权（后者靠 §2.4 方案 A 直接消掉）。

### 4.3 建议（三档，按成本递增）

| 档 | 做法 | 收益 |
|---|---|---|
| 1（最低） | 文档明确"`X-Vod-Agent-Id` 是**提示不是身份**，不提供安全性；对外必须靠反代注入" | 消除误解 |
| 2（推荐） | 加格式约束：`^[A-Za-z0-9._:-]{1,64}$`，非法值**忽略并降级**到 session（不报错，只告警一行） | 挡住注入换行/日志伪造/超长 key |
| 3（重） | 绑 Bearer 指纹：`agent:<sha256(token)[:8]>:<aid>`，同一令牌下的 agent id 才互认 | 真正防冒用，但要改 key 格式，**存量记忆全失效** |

我建议 **1 + 2**，第 3 档等真有跨机多 agent 需求再上（现在负责人已澄清
`design.md:1285` 远程面就是同机单进程，跨机共享不在范围）。

## 5. ⑤ 的可实现方案（需单独拍板）

审查提的"哨兵复用"——**技术上可行，但必须绑一个绑定关系，否则等于把 §3 的
会话泄漏变成"所有裸客户端共用一个桶"，那是另一种串味。** 两种形态：

### 5.1 方案 ①哨兵（推荐）：按"客户端指纹"复用无 session 会话

```
裸请求 → 算指纹 fp = sha256(UA + 客户端IP + 可选 X-Vod-Agent-Id)
       → 内存表 _sideless_sessions[fp] = (sid, last_used)
       → 有且未过期 → 直接补这个 sid
       → 没有 → 内部握手建一个，登记
       → 表满/过期 LRU 淘汰（上限 max_sessions/4 = 2500）
```

- 复用后 `_resolve_scope` 走 `sess:<sid>`，**记忆在裸客户端内也能延续**
  （比现在"每次都是 key=None"更好用）
- 但两个不同客户端若 UA+IP 相同 → 共桶 → **串味**。所以指纹必须包含
  客户端自愿提供的 `X-Vod-Agent-Id`（或 `X-Vod-Client-Id`），并在文档里说清
  "不提供就按 IP+UA 聚合，同 IP 同 UA 视为同一客户端"
- 淘汰：LRU + TTL，且**上限远低于 max_sessions**，避免把标准客户端挤出去
- 会话释放：登记时记下 sid，淘汰时主动 `terminate`（现在做不到 DELETE，内部可以）

### 5.2 方案 ②反过来：**让兜底不建会话**（我更推荐）

刚查到的关键事实：`_resolve_scope:392` 对"远程面 + 无会话"**已经是 `key=None` 读写皆禁**。
也就是说**兜底建立的那个会话，在业务上根本没被用起来**——它只是为了让
SDK 不返回 400 而存在。既然是空壳，就没必要养 1800 个：

```
无 session 的非 initialize 请求：
  → 不建真会话，改为一次性 synthetic transport（复用同一个，用完即还）
  → 或：把 stateless=True 的路径单独引进来处理这类请求
```

- 会话池占用：**恒定 1 个**，彻底消灭 503 风险
- 代价：无 session 请求确实无记忆（**和现状一样**，现在是 `key=None` 也是无记忆）
- 不动标准客户端路径，不动 `max_sessions`
- 风险：要确认 SDK 允许"同一 manager 既 stateful 又有旁路"，实现上可能是
  在 `_ensure_session_for_sideless` 里维持**一个**长期复用的 sid（"哨兵会话"），
  而不是每次新建——这比 5.1 更简单，且不引入串味：

```
_ensure_session_for_sideless():
   if _SENTINEL_SID is None or 已失效:
       内部 initialize 一次，记下 sid
   返回补了这个 sid 的 scope
```

**这就是审查说的"哨兵"最朴素的形态**：所有裸请求共用一个哨兵会话。
串味风险 = **所有裸客户端共享记忆桶**。但现在它们本来就是 `key=None`（无记忆），
所以**哨兵会话必须同时把 `_resolve_scope` 对它的处理改成 `key=None`**，
否则就从"一人一桶"退化成"大家一桶"。

**我的建议：5.2 的哨兵 + 强制 `key=None`。** 会话占用从 O(请求数) 降到 O(1)，
业务行为与现状**完全一致**（都是无记忆），风险面最小。5.1 的按指纹复用是"更好的功能"
但不是修 bug，可以之后单独做。

## 6. 建议实施顺序

| 序 | 项 | 性质 | 成本 | 风险 |
|---|---|---|---|---|
| 1 | ④ 方案 A：owner 改用 `_draft_owner()` + 话术分档 | 修 bug（含越权） | 小（~40 行 + 4 测试） | 低 |
| 2 | ⑤ 哨兵会话 + 强制 `key=None` | 修 bug（可用性） | 小（~30 行 + 3 测试） | 中（要确认 SDK 复用 sid 的行为） |
| 3 | ⑥ 档 1+2：文档 + 格式约束 | 加固 | 很小 | 极低 |
| 4 | ⑥ 档 3：绑 Bearer 指纹 | 设计变更 | 大（存量失效） | 高，缓 |

## 7. 本次已核实的事实清单（供复核）

| # | 结论 | 证据 |
|---|---|---|
| 1 | owner = `_session_key`，创建与校验用同一函数 | `collect.py:575`、`:633` |
| 2 | `X-Vod-Agent-Id` **优先于** session | `runtime_state.py:363` vs `:368` |
| 3 | 因此同 agent id 可跨会话提交他人草稿 | §2.3 推演（基于 1+2） |
| 4 | 兜底每次请求内部 initialize 一次 | `transport_remote.py:222-285` |
| 5 | 会话上限默认 10000，超限 **503** | SDK `DEFAULT_MAX_SESSIONS`、`_handle_stateful_request` |
| 6 | 会话不随请求结束销毁，靠 idle timeout | SDK `_serve_opening_request` + `_discard_session` |
| 7 | 远程面无会话 → `key=None` 读写皆禁 | `runtime_state.py:392-394` |
| 8 | 1 req/s × 1800s = 1800 常驻（审查口径正确） | #4+#5+#6 |
| 9 | 打挂门槛 ≈ 5.6 req/s 持续 | 10000 / 1800s |

> 标注「推断」的：§2.3 的跨 agent 冒用链路是**基于代码阅读的推演**，
> 实施前应先写一个两会话真机测试复现（预期：C 提交 A 的草稿返回成功而非 -32011）。
> 该测试本身就是修复的回归锁。

## 8. 实施记录与对本文的两处修正（2026-11-19）

实施落地在 `src/vod_mcp/runtime_state.py`（`_draft_owner` / `agent_id_accepted`）、
`src/vod_mcp/packs/collect.py`（`_same_owner_kind` + 话术分档）、
`src/vod_mcp/transport_remote.py`（`_sentinel_session` / `_handshake_once`）、
`src/vod_mcp/remote_app.py`（`_req_scope` 清洗 + `x-vod-sideless` 标）。
回归锁：`tests/test_review_456.py`（13 例）。

### 修正 1：§2.5 的话术判据「按 owner 前缀」在真实入参下不成立

真实 `client_info` 由 `remote_app._req_scope` 产出，agent 头存在时是
`agent_id = "<aid>"`、**无头时是 `agent_id = "session:<sid>"`**。照 §2.5 的
「前缀不同 → 可疑」实现，跨 agent 冒用（A 记 `sess:s1`、C 是 `sess:s9`）会落到
"sess 前缀同类"→ 被说成"你自己重连了"，话术直接指错方向。

**改为**：`_draft_owner` 把 agent 头作为**摘要附加**进指纹
（`sess:<sid>|agent:<aid>`），判据改为
「两侧都是纯 `sess:` 且无 agent 摘要 → 会话漂移；其余 → 不属于当前客户端」。
连带好处：同会话不同 agent 头也不互认（§2.4 方案 B 担心的放大面被关掉）。

### 修正 2：§5.2 的哨兵必须按 manager 实例绑定，不能只存一份全局 sid

第一版把哨兵 sid 存成模块级一份全局值。测试串行跑时暴露：前一个 fixture 的
runtime 已 shutdown，其 sid 被下一个 runtime 复用 → 第一发就
`404 Session not found`（会话归属 manager 的 `_server_instances`）。
**生产同样会中**：runtime 重建/多实例同进程时全部 404。

**改为**：`_SENTINEL[id(manager)] = {"sid", "at"}`，manager 换实例即自动失效。

### 实测数据（供复核）

- 修复前：`test_draft_owner_ignores_agent_header` → `DID NOT RAISE ToolError`（越权坐实）
- 修复后：`tests/test_review_456.py` 13 passed
- 真 SDK 链路：3 次裸 `tools/call` 只握手 1 次（`test_compat_vendor_sideless_multiple_calls` 绿）
- 全量：`pytest tests/` 1003 passed / 0 failed；dsh 壳 `npm test` 74/74
- 静态：`pyflakes src/` 干净；`mypy src/vod_mcp` Success（40 files）
