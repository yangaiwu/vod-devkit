# 架构设计缺陷台账（五维走查）

> 基线：`dev` @ `ba48d9d`（v0.5.44；QA 复核指出初稿走查树实为 `f6af880`、与抬头的 `6649fda`
> 不符，本次修订已把分支合并到 dev 头并将全部证据引用统一重钉到本基线）。
> 配套文件：整改方案见 [`architecture-remediation.md`](architecture-remediation.md)；
> 结构"应然"契约见 [`architecture.md`](architecture.md)，设计决策见 [`design.md`](design.md)，
> 安全模型见 [`safety-model.md`](safety-model.md)，远程面 ④⑤⑥ 专项见
> [`review-456-analysis.md`](review-456-analysis.md)。

## 一、本文件是什么、不是什么

**是什么**：把"当前实现与设计契约之间的差距"落成可核对的清单。每条缺陷都能落到
`path:line` 或一条 pytest 用例名，供后续按 P 级另开工单整改。

**不是什么**：

- 不是结构契约。`docs/architecture.md` 定义目录与根的"应然"，本文件只记录"实然与应然
  的差"，不改契约结论。
- 不是设计史。已拍板的决策（`D-*` 编号）在 [`decisions.md`](decisions.md) 与
  [`design.md`](design.md)，本文件引用而不复述。
- 不是风格清单。风格偏好、命名分歧、"我觉得可以更好"一律进第九节「建议」，不计缺陷。

### 1.1 缺陷判定三门槛（缺一不收录）

一条现象要进本台账，必须同时满足：

1. **可被捕获**：已被现有用例/门禁捕获（则本条目记"已捕获"），或可被新用例/文档守门稳定
   捕获（写出捕获方式）；
2. **有触发路径**：存在真实使用路径（安装、提交、远程对接、发版、排障）能走到它，不是
   理论上的死代码；
3. **影响面可描述**：能说清坏了谁（用户/宿主/运维/发布物），而不是"可能有问题"。

### 1.2 证据口径

| 证据类型 | 写法 | 核对方式 |
|---|---|---|
| 代码事实 | `src/…/x.py:123` | 直接打开该行 |
| 用例事实 | `tests/test_x.py::test_y` | `python3 -m pytest tests/test_x.py::test_y -q` |
| 门禁缺口 | "grep 无命中 + 未列入 CURRENT/门禁清单" | 按附录 10.1 的命令复跑 |
| 实测事实 | 附命令与结果摘要（附录第十节） | 同基线重跑 |

- **只记行号不记代码**：行号会随改动漂移，每条结论都配了可复跑的 grep 片段（附录 10.1），
  改完后按片段复扫即可重新定位。
- 凡"推断"不加引号：本台账没有"待验证"条目——未达三门槛的现象一律进第九节。

### 1.3 严重度口径

| 级别 | 判据 | 处置要求 |
|---|---|---|
| **P0** | 正确性/安全：用户数据或凭据暴露、服务进程可被普通配置错误打死 | 立即处置（单独热修，不等批量整改） |
| **P1** | 可维护性/发布风险：门禁不覆盖、双实现漂移、发布物与实际不一致 | 本里程碑内排队，按维度分批 |
| **P2** | 整洁/可读/单点改进：不修不致命，但持续抬高改造成本 | 随相关模块改动顺带做 |

工作量单位：**人日**，按"熟悉本仓的实现者"估算（含自测与用例，不含评审等待）。

## 二、结论摘要

五维共 **32** 条（P0 2 / P1 18 / P2 12），合计约 **55.5 人日**（BLD-02 的 release.sh 半步已由 `95217f1` 修复，工作量相应核减 1.0）。

> **整改状态**（2026-11-19 起维护，`✅完整` / `◐部分` / `⬜未动`）——查"哪条修了"看这一列，
> 不要翻决策记录反推。本轮落地的代码提交：`2b8bc15`（首批）、`fde04d0`（BLD-03）。

| 编号 | 标题 | 级别 | 人日 | 整改状态 |
|---|---|---|---|---|
| ARCH-DEP-01 | `net` ↔ `runtime_state` 双向依赖，靠函数内懒导入破环 | P2 | 2.0 | ✅完整（`2b8bc15`，另修了台账漏记的 hermes↔host_verify 环） |
| ARCH-DEP-02 | `host_adapters` 急切聚合导入 12 个适配器，与载荷边界冲突 | P1 | 3.0 | ✅完整（惰性注册 + `test_registry_is_lazy`） |
| ARCH-DEP-03 | 知识披露层反向依赖网络出口层（`skills_registry`/`packs.knowledge` → `net`） | P2 | 1.5 | ⬜未动 |
| ARCH-DEP-04 | 入口设根契约覆盖不全，`serve` 双分派两条路径根来源不同 | P1 | 2.0 | ⬜未动（**真机实测：`vod-devkit serve` 起不来，见下方实测注**） |
| ARCH-DEP-05 | 运行期安装代码依赖构建脚本 `sync_plugin.py` | P1 | 1.0 | ⬜未动 |
| ARCH-DEP-06 | 路径常量 import 期冻结，违反 `paths.py` 自陈纪律 | P2 | 1.0 | ⬜未动 |
| ARCH-CALL-01 | stdio 与 remote 两面各写一套 `tools/call` 管线，错误呈现层级不一 | P1 | 3.0 | ⬜未动 |
| ARCH-CALL-02 | `initialize` instructions 双份硬编码，用例只锁关键词 | P1 | 1.0 | ⬜未动 |
| ARCH-CALL-03 | 远程面哨兵会话以 `id(manager)` 登记，与 SDK 内部语义强耦合 | P2 | 3.0 | ⬜未动 |
| ARCH-CALL-04 | `collect` pack 单模块承载七件事（692 行 vs `knowledge` 17 行） | P2 | 4.0 | ⬜未动 |
| ARCH-CALL-05 | 协议面裸造 JSON-RPC，`protocolVersion` 与错误码多处硬编码 | P2 | 1.0 | ⬜未动（实测 **4** 处硬编码，台账写 3 处，漏 `remote.py:98`） |
| ARCH-CALL-06 | 引擎可达性判定两套实现（`net.probe_key` vs `doctor._probe_engine`） | P1 | 2.0 | ⬜未动 |
| ARCH-ERR-01 | 护栏读取位于异常保护之外，`policy.json` 缺失/损坏直接打死 server | **P0** | 1.0 | ✅完整（fail-closed + `-32017` + 主循环兜底） |
| ARCH-ERR-02 | 每次工具调用重读 policy 且无 schema 校验（坏规则 → `KeyError`） | P1 | 1.5 | ◐部分（schema 校验已做；**缓存未做**，仍每次重读） |
| ARCH-ERR-03 | 上游 HTTP 状态码进入 JSON-RPC `code` 域，explain 表与门禁均覆盖不到 | P1 | 2.0 | ⬜未动 |
| ARCH-ERR-04 | 26 处 `except` 体只有 `pass`，主链失败痕迹被吞 | P1 | 3.0 | ◐部分（主链 3 点已补；**实测仍剩 25 处**，全量收敛未做） |
| ARCH-ERR-05 | 可观测性＝固定 `/tmp` 文本日志：无级别、无请求关联、远程面请求日志静默 | P1 | 3.0 | ⬜未动（一行未改） |
| ARCH-ERR-06 | `explain` 按文案正则归层，错误码与文案双轨 | P2 | 2.0 | ⬜未动 |
| ARCH-CFG-01 | `pending-feedback.jsonl` 存用户原话却未收紧 0600 | **P0** | 1.0 | ✅完整（实测改前 0644 → 现 0600，含历史文件收紧） |
| ARCH-CFG-02 | 远程面 `CORS *` + 无 Host 校验 + 无内建鉴权 → 浏览器可跨域驱动本机端点 | P1 | 2.0 | ⬜未动（`transport_remote.py:440` 仍无条件 `*`） |
| ARCH-CFG-03 | 三套原子写实现并存，fsync/权限/符号链接语义不一致 | P1 | 2.0 | ✅完整（单源 + AST 门禁；遗留：通用路径 `mode=0o600` 会把 0400 放宽） |
| ARCH-CFG-04 | `secret_scan.py` 覆盖边界：只扫 tracked、无超时、git 失败即崩 | P1 | 1.0 | ⬜未动 |
| ARCH-CFG-05 | 凭据三入口（env / runtime / 请求头），优先级判据散落四处 | P2 | 2.0 | ⬜未动 |
| ARCH-CFG-06 | 机器级 state 目录权限只在迁移路径收紧 0700 | P2 | 0.5 | ⬜未动 |
| ARCH-CFG-07 | `guard_scope` 字段剔除靠"新字段记得加" | P2 | 1.0 | ⬜未动 |
| ARCH-BLD-01 | 双 CI 定义漂移：GitCode 只覆盖部分门禁，且两者都只在 `main` 触发 | P1 | 2.0 | ⬜未动（实测 GitCode 5 步 / GitHub 10 步，dev 仍零 CI 门禁） |
| ARCH-BLD-02 | 开发基线 `dev` 而 update/测试夹具仍钉 `main`（release.sh 半步已修） | P1 | 1.0 | ◐半步（release.sh 已于 `95217f1` 修；`update.py` 与测试夹具仍钉 `main`） |
| ARCH-BLD-03 | 版本六处落点，根 `plugin.json` 永久停在 `0.1.0` | P1 | 1.0 | ✅完整（`fde04d0`，8 处落点现全等） |
| ARCH-BLD-04 | 根 `build-info.json` 快照落后 HEAD，却被 install 与 provenance 当权威 | P1 | 1.5 | ⬜未动 |
| ARCH-BLD-05 | `.githooks/pre-push` 未接线，且含作者机绝对路径 | P1 | 1.0 | ⬜未动（脚本内仍有 `/root/.hermes/...` 与 `/tmp` 日志；新 clone 不生效） |
| ARCH-BLD-06 | `package.json` 的 `files` 逐文件枚举，靠发版后断言兜底 | P2 | 2.0 | ⬜未动（本轮新增模块即被它抓红一次，已手工补白名单——正是本条风险） |
| ARCH-BLD-07 | `sync_plugin.py` 用字符串切分解析 `__version__`，用例已打桩绕过 | P2 | 0.5 | ⬜未动 |

> **实测注（2026-11-19，本机）——含一次我的误判，如实记录**：
>
> ① **`vod-devkit serve` 是正常的**。用真实入口 `python bin/vod-devkit serve` 实测，
> initialize 正常返回 v0.5.45、工具面完整。我一度报「serve 起不来、装机不可用」，
> 原因是**我用错了入口**：`src/vodkit_cli/cli.py` 是被 import 的装配模块，
> **没有 `if __name__ == "__main__"`**，直接 `python cli.py serve` 什么都不会发生
> （进程正常退出、零输出）。那是测试方法错，不是产品缺陷。
> 已补 `tests/test_serve_entry.py`（4 条，走真实 `bin/vod-devkit` 端到端）锁住这条路径。
> **DEP-04 维持「可维护性」定级不变**：两条分派取根来源不同（前置分支 `paths.SRC_ROOT`
> vs 子命令 `common.ROOT`）在仓内形态同指、在插件/载荷副本形态可能分叉，仍是待修项。
>
> ② **真机抓到一条台账未记的缺陷（确认为真）**：`collect` 预设只装 core+collect，
> `vod_list_skills` / `vod_retrieve_skill` 未注册，而 `vod-core` 技能路由表第一条就教
> 模型用这两个工具 ⇒ 真模型首跑即失败（只能改去读载荷目录的 SKILL.md）。
> 这是**装机后第一次真实使用就撞墙**，优先级高于台账里多数 P1，需单独立项。
>
> ③ 另一条真机发现：`check_update` 报 `current 0.5.45 vs latest 0.5.43` ——
> npm registry 滞后于仓内 tag（0.5.44/0.5.45 均未 publish），用户侧更新链路是断的。

### 2.1 五维一句话判读

| 维度 | 判读 | 主要风险形态 |
|---|---|---|
| 模块依赖 | **分层大体成立，但"破环靠懒导入、边界靠注释"** | 循环依赖、聚合导入面、契约覆盖不全 |
| 核心调用链 | **两面（stdio/remote）共享业务实现，但各自重复装配** | 双实现漂移、错误呈现层级不一 |
| 错误处理与可观测性 | **错误码域混合，失败痕迹大量被吞** | 崩溃不可解释、排障只能靠猜 |
| 配置与安全 | **护栏有效，但权限与暴露面收紧不完整** | 用户原话可读、本机端点可被网页驱动 |
| 构建与发布 | **门禁"存在但未接线/未覆盖"** | 发布物与版本不符、dev 零门禁 |

## 三、维度 A：模块依赖

### 3.1 走查范围与结论

| 范围 | 判读 | 依据 |
|---|---|---|
| `src/vod_mcp` 内部依赖图 | 无顶层环；`net` ↔ `runtime_state` 为双向依赖，靠函数内懒导入断开 | 附录 10.1（`grep -n "def _is_remote_face"` 等） |
| `src/vodkit_cli` → `src/vod_mcp` | 单向（CLI 是装配层，可依赖 MCP 包），符合预期 | 附录 10.2 依赖图 |
| `host_adapters` | 唯一"包内聚合导入"点：`__init__` 拉入全部 12 个宿主模块 | `src/vod_mcp/host_adapters/__init__.py:8` |
| `packages/dsh`、`integrations/` | 与 `src/` 无 import 关系（JS / 宿主侧脚本），边界清晰 | 附录 10.2 |
| `scripts/`、`tests/` | `scripts/` 被运行期反向调用一处（见 DEP-05），`tests/` 只依赖公开面 | `src/vod_mcp/host_adapters/codex.py:289` |

**该维结论**：分层方向正确，缺陷集中在"破环手段"与"导入面宽度"，没有需要重画依赖图的硬伤。

---

### ARCH-DEP-01 `net` ↔ `runtime_state` 双向依赖，靠函数内懒导入破环

- **证据**：`src/vod_mcp/net.py:14`（顶层 `from vod_mcp import runtime_state as rt`）；
  `src/vod_mcp/runtime_state.py:438`（`_is_remote_face()` 函数体内 `from vod_mcp import net as _net`）；
  `src/vod_mcp/runtime_state.py:5`（模块 docstring 自陈"需要身份时**函数内懒导入**，避免
  `net` ↔ `runtime_state` 的循环"）。
- **影响面**：两个模块互为依赖，环只被"函数内 import"这一行代码维持。任何一侧把懒导入提到
  顶层（重构、格式化工具、静态分析自动整理 import）即 `ImportError`；错误呈现为
  "MCP server 起不来"，与本次要消灭的"静默失败"同型。同时该环让两个模块无法独立单测。
- **判定依据**：三门槛全满足——可捕获（用 `python3 -c "import vod_mcp.net"` 的变体，
  或把懒导入提层的变异测试）；有触发路径（任何一次 import 重排）；影响面＝全部工具调用不可用。
  当前**未被任何门禁捕获**（无 `test_import_order` 类用例，附录 10.1 无命中）。
- **整改措施**：把"身份读取"抽成不依赖 `net` 的窄接口（`runtime_state` 只消费
  `server_face` 标志的注入，而不是反向 import），见 `ARCH-RM-DEP-01`。
- **优先级**：P2
- **工作量**：2.0 人日
- **验收断言**：新增 `tests/test_import_graph.py::test_no_cycle_in_vod_mcp`——用 `ast` 建图
  （含函数内 import）断言无环，且该用例在 `dev` 上**先红后绿**（先在现状上证明它抓得到）。

---

### ARCH-DEP-02 `host_adapters` 急切聚合导入 12 个适配器，与载荷边界冲突

- **证据**：`src/vod_mcp/host_adapters/__init__.py:8`（一行导入 atomcode/codearts/
  codeartswork/codex/codex_desktop/dsh/generic/hermes/officeace/openclaw/opencode/workbuddy
  共 12 个模块）、`:12`（`REGISTRY` 12 条）；
  冲突实锤：`src/vod_mcp/transport_remote.py:54`（注释明写"**不许** import host_adapters：
  它的 `__init__` 会连带 import 各宿主适配模块，而载荷副本不含 `integrations/`
  （2026-11-12 实锤：请求线程 KeyError → 每个请求 500）"）。
- **影响面**：① 任何 `vod_mcp` 运行期代码误引 `host_adapters`（`from vod_mcp import
  host_adapters` 这类补全友好的写法很容易出现）会让**远程面每请求 500**；② 单模块改动
  （例如只修 `officeace`）会拖入 12 个模块的导入成本与依赖（`hermes` 563 行、`dsh` 438 行）；
  ③ 载荷副本形态与仓内形态的"可导入面"不一致，靠注释与人工记忆维持。
- **判定依据**：可捕获（构造载荷副本形态导入 `host_adapters` 即复现；现有
  `tests/test_plugin_copy_selfcontained.py` 只测插件副本自包含，未测"载荷形态禁引"）；
  有触发路径（远程面／载荷跑法）；影响面＝远程面不可用。
- **整改措施**：`REGISTRY` 改惰性加载（名字 → `importlib.import_module`），`__init__`
  只保留映射表；再补一条"载荷形态禁引"的门禁用例，见 `ARCH-RM-DEP-02`。
- **优先级**：P1
- **工作量**：3.0 人日
- **验收断言**：`tests/test_host_adapters.py::test_registry_is_lazy`——导入
  `vod_mcp.host_adapters` 后 `sys.modules` 不含任何 `vod_mcp.host_adapters.<宿主>` 子模块；
  `tests/test_payload.py::test_payload_face_cannot_import_host_adapters` 断言导入即失败。

---

### ARCH-DEP-03 知识披露层反向依赖网络出口层

- **证据**：`src/vod_mcp/packs/knowledge.py:2`（`from vod_mcp import net`，唯一用途是把
  `SkillError` 转成 `net.ToolError`，见 `:9`、`:17`）；
  `src/vod_mcp/skills_registry.py:18`（顶层只 import `paths`），但 `:67` 使用
  `net._SERVER_FACE`（函数内懒导入）。
- **影响面**：`knowledge` pack 的定位是"纯知识、零上游调用、零依赖"
  （`src/vod_mcp/packs/__init__.py:17`「只读、零上游调用、零依赖」），实际却依赖出口层的错误类与远端面标志。
  ① 知识包无法在"没有出口层"的上下文（纯离线、纯静态校验脚本）单测；
  ② `ToolError` 定义在 `net` 使"网络出口"承担了**领域错误基类**的角色，
  改 `net` 的异常面会影响全部 pack。
- **判定依据**：可捕获（在测试里 `sys.modules.pop("vod_mcp.net")` 后 import
  `packs.knowledge` 即 `ImportError`）；有触发路径（任何知识工具调用经 `knowledge.py`
  转译错误）；影响面＝知识包可测性与异常口径。
- **整改措施**：把 `ToolError` 迁到独立 `vod_mcp/errors.py`（`net` 与各 pack 共同依赖），
  远端面标志改为由传输层**注入**到 `runtime_state`，见 `ARCH-RM-DEP-03`。
- **优先级**：P2
- **工作量**：1.5 人日
- **验收断言**：`tests/test_structure_guards.py::test_packs_do_not_import_net_for_errors`——
  `packs/*.py` 不含 `id`（校验）。其中 `ToolError` 只允许来自 `vod_mcp.errors`。

---

### ARCH-DEP-04 入口设根契约覆盖不全，`serve` 双分派两条路径根来源不同

- **证据**：`src/vod_mcp/paths.py:8`（列出 5 个设置点：`bin/vod-devkit`、`npm/cli.js`、
  `server.main()`、`tests/conftest`、`scripts/host_matrix.py`）；
  实际还有三处未登记：① 根清单 `plugin.json:14`（直接声明 `"${PLUGIN_DIR}/vod_mcp/server.py"`
  ＋`:15-19` 的内联 env，一个根变量都不设，即"载荷平铺"形态）；② `src/vodkit_cli/cli.py:18`（`serve` 前置分支用
  `_paths.SRC_ROOT / "vod_mcp" / "server.py"`）、③ `src/vodkit_cli/cli.py:125`（argparse 的
  `serve` 子命令用 `common.ROOT / "vod_mcp" / "server.py"`）；
  `npm/cli.js:42` 用**覆盖**写 `VOD_DEVKIT_SRC_ROOT`，而 `bin/vod-devkit:41` 用 `setdefault`
  （不覆盖已存在值）并配 `:35-40` 的不一致告警——两条入口对同一变量语义相反。
- **影响面**：同一条 `vod-devkit serve` 命令有两条分派路径（`src/vodkit_cli/cli.py:13` 的前置分支与
  `src/vodkit_cli/cli.py:117` 的子命令），二者取的 server 脚本根不同（`SRC_ROOT` vs `common.ROOT`）。
  在仓内形态两者同指，**在插件/载荷副本形态两者不同**——一条能起、一条找不到脚本；
  且 `npm/cli.js` 的覆盖语义与 `bin/vod-devkit` 的"尊重继承值 + 告警"契约相矛盾。
- **判定依据**：可捕获（把 `VOD_DEVKIT_DIST_ROOT` 指到临时目录后跑 `serve --help` 对照
  两条路径；现无用例覆盖 `_serve` 分支）；有触发路径（npx 安装 + 插件副本形态）；
  影响面＝MCP server 起不来（宿主表现为掉线）。
- **整改措施**：删掉 `cli.py:13-22` 前置分支（保留 REMAINDER 子命令），所有入口统一走
  `paths.SRC_ROOT`；`npm/cli.js` 改 `setdefault` 语义并补告警，见 `ARCH-RM-DEP-04`。
- **优先级**：P1
- **工作量**：2.0 人日
- **验收断言**：`tests/test_p2_structure.py::test_serve_entry_resolves_single_root`——两种
  形态下 `serve` 解析出的脚本路径一致；`paths.describe()` 的 `srcRoot` 与 execve 目标同源。

---

### ARCH-DEP-05 运行期安装代码依赖构建脚本 `sync_plugin.py`

- **证据**：`src/vod_mcp/host_adapters/codex.py:288`（`if not (mp_root / "vod-devkit" /
  "vod_mcp").is_dir():`）→ `:289`（`_sync = ROOT / "scripts" / "sync_plugin.py"`）→
  `:291`（`subprocess.run([sys.executable, str(_sync), "--no-build-info"], ...)`）→
  `:297-299`（脚本不存在时打印"npm 包损坏？"并 `sys.exit(2)`）。
  对照：载荷清单 `src/vod_mcp/payload.py:39`（`OWNED = ("vod_mcp", "contract", "safety",
  "skills", "hooks", "build-info.json", "payload.json", "package.json")`）不含 `scripts/`。
- **影响面**：构建期脚本成为运行期安装路径的依赖。① 载荷/插件副本形态下
  `ROOT/scripts/sync_plugin.py` 不存在 → 走 `else` 直接拒绝安装，且错误文案把原因
  误导为"npm 包损坏"；② 生成物的生成逻辑与生成时机分散在两处（`package.json` 的
  `prepack` 与这里的子进程），任一处改动都要同步。
- **判定依据**：可捕获（把 `ROOT` 指到不含 `scripts/` 的目录跑 codex 安装，
  现无用例覆盖该分支）；有触发路径（npx/payload 形态 + `--target codex`）；
  影响面＝codex 原生插件装不上。
- **整改措施**：把"副本缺失"变成安装前的显式前置校验（`install` 阶段统一检查并给出
  可执行提示），不在适配器内部 shell 出构建脚本；或把 `sync_plugin.py` 随包分发并纳入
  `payload.OWNED`，见 `ARCH-RM-DEP-05`。
- **优先级**：P1
- **工作量**：1.0 人日
- **验收断言**：`tests/test_installer.py::test_codex_install_without_repo_never_shells_out`——
  桩掉 `subprocess.run` 后断言安装路径不出现 `sync_plugin.py` 调用，且失败文案指向"重跑
  install/重新 npm 安装"而非"包损坏"。

---

### ARCH-DEP-06 路径常量 import 期冻结，违反 `paths.py` 自陈纪律

- **证据**：`src/vod_mcp/paths.py:182`（模块内自陈"不提供模块级 RUNTIME_JSON 快照常量……
  违反本模块'路径类值不 import 期冻结'的纪律（D-state-read-1）"）；
  违反点：`src/vod_mcp/provenance.py:6`（`_ROOT = paths.ROOT`）、`:7`（`_BUILD_INFO =
  _ROOT / "build-info.json"`）、`:8`（`_MANIFEST = _ROOT / "install-manifest.json"`）、
  `src/vod_mcp/payload.py:28`（`ROOT = paths.ROOT`）。
- **影响面**：`provenance`/`payload` 在导入那一刻把根钉死。① 测试与重定位场景（改
  `VOD_DEVKIT_DIST_ROOT` 后再导入）读到旧根；② 长驻进程内"重装换了载荷目录"后，
  `install-manifest` / `build-info` 仍指向旧根（`provenance.info_payload` 是
  `vod_devkit_info` 的数据源）；③ 与 `net`/`runtime_state` 的"每次现读"纪律不一致，
  同一份代码里两种读法并存。
- **判定依据**：可捕获（`importlib.reload` 前后改 env 断言路径跟随）；有触发路径
  （任何 `vod_devkit_info` 调用、载荷重装）；影响面＝溯源信息指向旧根。
- **整改措施**：三个常量改为函数（`build_info_path()` / `manifest_path()`），调用点现读，
  与 `paths.runtime_json_path()` 同口径，见 `ARCH-RM-DEP-06`。
- **优先级**：P2
- **工作量**：1.0 人日
- **验收断言**：`tests/test_state_read.py::test_provenance_paths_are_live`——改
  `VOD_DEVKIT_DIST_ROOT` 后不重启即可读到新路径。

---

## 四、维度 B：核心调用链

### 4.1 调用链实测（三入口反推）

```
入口①  bin/vod-devkit:43            ─┐
入口②  npm/cli.js:40  → bin/vod-devkit ─┼→ vodkit_cli.cli:main:10
入口③  plugins/vod-devkit/.mcp.json ─────┘        │
                                                   ├─ serve → os.execve → vod_mcp/server.py:123
                                                   │              ├─ stdio: server.handle:44
                                                   │              └─ remote: transport_remote.serve:528
                                                   │                         → RemoteRuntime:77
                                                   │                         → remote_app.build_server:141
                                                   │                               └─ on_call_tool:152
                                                   └─ install/status/doctor/... → vodkit_cli/*
                                                                  ↓ 共用
                        server.handle:91 / on_call_tool:161  → guardrails.check:11
                        server.handle:95 / on_call_tool:170  → tools.dispatch:74
                                                              → packs.{core|collect|knowledge}
                                                              → net._http:172 → 引擎
                                                              → runtime_state.* → runtime.json
```

**走查判读**：业务实现（`packs/*`、`net`、`runtime_state`）在两面间**共享**，这层没有重复；
重复出现在**装配层**——协议响应构造、instructions 文案、错误包装、引擎探活各写两份。

| 链路段 | stdio 实现 | remote 实现 | 是否重复 |
|---|---|---|---|
| 工具面清单 | `src/vod_mcp/server.py:86` → `tools.tool_specs` | `src/vod_mcp/remote_app.py:147` → 同函数 | 共享 ✔ |
| 护栏 | `src/vod_mcp/server.py:91` | `src/vod_mcp/remote_app.py:161` | 共享 ✔ |
| 分派 | `src/vod_mcp/server.py:95` | `src/vod_mcp/remote_app.py:170`（`asyncio.to_thread`） | 共享 ✔ |
| 错误包装 | `src/vod_mcp/server.py:107` → JSON-RPC `error` | `src/vod_mcp/remote_app.py:171` → `is_error` 结果 | **各写一份** ✘ |
| instructions | `src/vod_mcp/server.py:60` | `src/vod_mcp/remote_app.py:29` | **各写一份** ✘ |
| 引擎可达性 | `net.probe_key:219` | `doctor._probe_engine:347` | **各写一份** ✘ |
| 协议版本 | `src/vod_mcp/server.py:32` | SDK 决定 | **口径不一** ✘ |

---

### ARCH-CALL-01 `tools/call` 两面各写一套管线，错误呈现层级不一

- **证据**：stdio 面 `src/vod_mcp/server.py:91`（护栏）→ `:94`（`try`）→ `:95`（dispatch）
  → `:107`（`except tools.ToolError` → `_error(req_id, e.code, str(e))`，错误进 **JSON-RPC
  `error` 对象**）；remote 面 `src/vod_mcp/remote_app.py:161`（护栏）→ `:169`（`try`）→
  `:170`（`asyncio.to_thread(tools.dispatch, …)`）→ `:171`（`except tools.ToolError` →
  `_text_result({"error": …, "code": …}, is_error=True)`，错误进**工具结果内容**）。
  另：`src/vod_mcp/remote_app.py:155` 对 `packs.REMOTE_WITHHELD`（`src/vod_mcp/packs/__init__.py:91`）
  的拒绝只在 remote 面实现，stdio 面无对应分支。
- **影响面**：同一个 `-32010`（缺产品归属）在 stdio 面是协议级错误、在 remote 面是
  工具级 `isError`。① 宿主侧"错误处理/重试/展示"逻辑必须按形态分叉；② 新增工具或改
  错误语义要改两处，漏一处即两面行为不同；③ `-32011`（confirm 未确认）在两面同样分叉，
  而"需用户逐次确认"是安全语义，不应随形态变化。
- **判定依据**：可捕获（同一入参分别走 `server.handle` 与 `remote_app.on_call_tool`，
  断言错误落在不同层级——现无用例做这个对照，`tests/test_remote_guards.py` 只测
  `-32010` 的 remote 侧）；有触发路径（远程 attach 形态）；影响面＝宿主错误处理契约。
- **整改措施**：抽 `vod_mcp/dispatch.py::call_tool(name, args, client_info) -> Result`
  作为唯一业务入口（返回结构含 verdict/code/payload），两面只做**协议适配**，见
  `ARCH-RM-CALL-01`。
- **优先级**：P1
- **工作量**：3.0 人日
- **验收断言**：`tests/test_remote_guards.py::test_two_faces_report_same_code_for_same_error`——
  同一 bad 入参在两面都给出 `code=-32010`，仅承载位置不同。
- **备注**：`notifications/tools/list_changed` 只在 stdio 面推送（`src/vod_mcp/server.py:104`），
  远程面因 `REMOTE_WITHHELD` 摘除该工具而**不构成**缺陷，本条不主张对称化这一处。

---

### ARCH-CALL-02 `initialize` instructions 双份硬编码，用例只锁关键词

- **证据**：`src/vod_mcp/server.py:60-75`（stdio instructions，含"征得用户明确同意""echo.contents
  必须逐条原样转述""product 未命中必须问一次"三段纪律）与 `src/vod_mcp/remote_app.py:29-39`
  （remote instructions，同样三段近乎逐字重复，尾句换成"本面不提供服务器本机路径"）。
  门禁：`tests/test_structure_guards.py:177`（断言 stdio 侧含归因设计关键词）、`:200`（断言
  remote 侧提到被摘除的工具名）——两边**各自**只锁关键词，不锁两段文本的共同部分一致。
- **影响面**：采集纪律（同意口径、逐字转述、产品追问）是**产品红线**，现在有两份真值。
  改一处漏一处 ⇒ 一个形态的模型行为与另一个不一致，且门禁仍然全绿。
- **判定依据**：可捕获（把两段文本按"共同句子"取交集后断言覆盖，或直接抽常量后断言
  单一来源）；有触发路径（任何一次 instructions 修订）；影响面＝模型行为与合规口径。
- **整改措施**：抽 `vod_mcp/instructions.py::COLLECT_DISCIPLINE` 常量，两面各自拼接
  形态专属尾句，见 `ARCH-RM-CALL-02`。
- **优先级**：P1
- **工作量**：1.0 人日
- **验收断言**：`tests/test_structure_guards.py::test_both_faces_share_collect_discipline`——
  两面 instructions 都 `startswith(COLLECT_DISCIPLINE)`，且形态尾句各自单独断言。

---

### ARCH-CALL-03 远程面哨兵会话以 `id(manager)` 登记，与 SDK 内部语义强耦合

- **证据**：`src/vod_mcp/transport_remote.py:223`（`_ensure_session_for_sideless`）→
  `:264`（`sid = await _sentinel_session(manager, scope)`）；`:336`（`key = id(manager)`，
  以对象地址做登记键）；`:277-283`（注释自陈"必须按 manager 绑定，不能只存一份全局 sid"
  以及"同进程第二个 runtime 起来后第一发就吃 Session not found"的实测）；`:290-297`
  （`_sentinel_ttl` 取 `SCOPE_TTL_SEC / 2`）。
- **影响面**：① `id()` 在对象回收后可被复用，登记表里可能命中**已死的旧 manager** 的
  sid；② 兜底逻辑依赖 SDK 的 `StreamableHTTPSessionManager` 语义（`stateless=False`、
  `session_idle_timeout`、`_server_instances`），SDK 升级改变会话召回即整段失效；
  ③ `transport_remote.py:85-97` 把 session TTL 与记忆 TTL 绑为同一常量，两个概念
  经一个数字耦合（`tests/test_token_machine_scope.py` 锁死了相等，但"必须相等"本身是推断）。
- **判定依据**：可捕获（`_reset_sideless_state(keep_sid=…)` 已提供测试注入点，可构造
  manager 重建后命中旧 sid 的用例——`tests/test_remote_transport.py` 未覆盖重建场景）；
  有触发路径（远程面重启 runtime / 多 runtime 同进程）；影响面＝裸客户端偶发 404。
- **整改措施**：登记键改为 manager 实例内的弱引用登记（`WeakKeyDictionary`）＋单调序号，
  不依赖对象地址；TTL 关系显式写成派生规则而不是"相等常量"，见 `ARCH-RM-CALL-03`。
- **优先级**：P2
- **工作量**：3.0 人日
- **验收断言**：`tests/test_remote_transport.py::test_sentinel_survives_manager_rebuild`——
  销毁并重建 manager 后不命中陈旧 sid，且新会话可用。

---

### ARCH-CALL-04 `collect` pack 单模块承载七件事

- **证据**：`src/vod_mcp/packs/collect.py`（692 行，模块 docstring `:1` 自陈"校验 → 归因 →
  提交/两段式 → 账本 → 回显 → pending"），内部函数 12 个（`:16`/`:35`/`:126`/`:179`/`:197`/
  `:209`/`:219`/`:267`/`:303`/`:327`/`:342`/`:356`/`:370`/`:382`）＋4 个工具入口（`:393`/`:497`/
  `:511`/`:633`）；对照同目录 `packs/core.py` 256 行、`packs/knowledge.py` 17 行。
  跨 pack 直连：`src/vod_mcp/packs/collect.py:7`（`from vod_mcp.packs import core`）＋
  `:75`/`:85`/`:145`/`:155`/`:171`（调 `core.search_products` / `core.format_candidates`）。
- **影响面**：① pack 粒度严重不均，"pack 可裁剪"在工具名层面成立、在代码层面不成立
  （`collect` 依赖 `core` 的两个函数）；② 单点改动回归面＝整个采集链；③ 归因、两段式、
  账本三类关注点混在一个模块，无法按关注点分层测试。
- **判定依据**：可捕获（结构用例可断言"每个工具入口与其依赖的关注点模块数"——
  现无用例，`tests/test_structure_guards.py` 只看 re-export 纪律）；有触发路径（任何采集
  相关改动）；影响面＝可维护性与测试成本。
- **整改措施**：按关注点纵切 `packs/collect/{validate,attribution,submit,pending}.py`
  （对 `tools._HANDLERS` 与 `packs.PACK_TOOLS` 保持零变化），见 `ARCH-RM-CALL-04`。
- **优先级**：P2
- **工作量**：4.0 人日
- **验收断言**：拆分后 `tests/test_skeleton.py`、`tests/test_two_phase.py`、
  `tests/test_pending_feedback.py` 全绿且无改动；新增断言：`packs/collect/__init__.py`
  单文件 ≤ 120 行（只做装配）。

---

### ARCH-CALL-05 协议面裸造 JSON-RPC，版本与错误码多处硬编码

- **证据**：`src/vod_mcp/server.py:32`（`_PROTOCOL_VERSION = "2025-06-18"`）、`:36-41`
  （`_result` / `_error` 手工拼 JSON-RPC 2.0 信封）；remote 面版本由 SDK 提供
  （`src/vod_mcp/remote_app.py:177` 只传 `name` / `version`）；安装器探活又硬编码一份
  （`src/vodkit_cli/remote.py:52`，`"protocolVersion": "2025-06-18"`）。
- **影响面**：协议版本字符串有 3 处独立真值（stdio 面、安装器探活、SDK 侧默认）；
  升版本时漏改一处，表现是"某类客户端握手失败/某形态装不上"，且不会有任何测试报警。
- **判定依据**：可捕获（断言 3 处取同一常量）；有触发路径（MCP 协议版本迭代）；
  影响面＝客户端互操作。
- **整改措施**：抽 `vod_mcp/protocol.py::PROTOCOL_VERSION`，三处引用同一常量，
  见 `ARCH-RM-CALL-05`。
- **优先级**：P2
- **工作量**：1.0 人日
- **验收断言**：`tests/test_skeleton.py::test_protocol_version_single_source`——源码内
  `2025-06-18` 只出现一次（常量定义处）。

---

### ARCH-CALL-06 引擎可达性判定两套实现

- **证据**：`src/vod_mcp/net.py:90`（`_META_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/meta"`）
  → `:219-260`（`probe_key`，**带 key**，返回 `ok` / `rejected` / `expired-anonymous` /
  `device-mismatch` / `unreachable` 五态）；`src/vodkit_cli/doctor.py:347-358`
  （`_probe_engine`，**不带 key**，手抄同一 URL 路径于 `:352`，返回 `ok` / `auth` /
  `unreachable` 三态）。
- **影响面**：① 同一份"引擎是否可达/凭据是否有效"的判断有两套状态机，`doctor` 说
  "可达（鉴权响应）"而提交侧报 `-32012`，或反之；② URL 路径重复书写，引擎侧改路径
  要改两处；③ `doctor` 的判定不带 key，无法区分"设备绑定不匹配"与"key 真坏"
  （`net.probe_key:248` 专门为这个区分做了解析）。
- **判定依据**：可捕获（同一 base 上分别调两个函数，构造 401/不可达两种响应，断言
  状态映射一致——无用例）；有触发路径（`vod-devkit doctor` / `status`）；
  影响面＝排障结论可信度。
- **整改措施**：`doctor._probe_engine` 改调 `net.probe_key`（或抽共享的
  `net.probe_reachable`），只保留"无 key 形态"的展示层映射，见 `ARCH-RM-CALL-06`。
- **优先级**：P1
- **工作量**：2.0 人日
- **验收断言**：`tests/test_doctor_egress.py::test_doctor_probe_uses_net_semantics`——
  桩住 `net._http` 后 doctor 的层报告与 `probe_key` 状态一一对应。

---

## 五、维度 C：错误处理与可观测性

### 5.1 现状判读

- **错误码域**：三套并存——JSON-RPC 保留段（`-32601`/`-32602`/`-32603`）、产品语义段
  （`-32001`/`-32010`…`-32016`）、上游 HTTP 状态码（`src/vod_mcp/net.py:209` 直接把 `e.code` 当
  错误码）。见 ARCH-ERR-03。
- **吞异常**：`src/` 下 169 个 `except` 处理器，其中捕 `Exception` 55 处、函数体只有
  `pass` 的 26 处（附录 10.1 有 `ast` 统计脚本，可复算）。见 ARCH-ERR-04。
- **日志**：唯一出口 `runtime_state._log`（固定 `/tmp` 路径），无级别、无请求标识；
  远程面 `BaseHTTPRequestHandler.log_message` 被置空。见 ARCH-ERR-05。
- **归因/溯源可追溯性**：`attribution_memory` 覆盖时留 10 条历史
  （`src/vod_mcp/runtime_state.py:537`），`provenance` 提供 build-info/install-manifest
  两个真源；**该子项未发现达到三门槛的缺陷**——历史快照有界但显式声明
  （`_ATTR_HISTORY_CAP = 10`）且有用例锁（`tests/test_attribution.py`），故只列建议，
  不进缺陷表。

---

### ARCH-ERR-01 护栏读取位于异常保护之外，`policy.json` 缺失/损坏直接打死 server

- **证据**：`src/vod_mcp/server.py:91`（`verdict, msg, code = guardrails.check(name, args)`
  ——位于 `:94` 的 `try:` **之前**）；`src/vod_mcp/guardrails.py:14`（每次
  `policy_mod.load_policy()`）；`src/vod_mcp/policy.py:15-17`（`open(...)` + `json.load`，
  无存在性/损坏兜底）；stdio 主循环 `src/vod_mcp/server.py:178`（`resp = handle(message)`
  无 `try`）。
  同型：`src/vod_mcp/tools.py:21`（`load_contract()` 直接 `open`），被
  `src/vod_mcp/server.py:78`（initialize）与 `src/vod_mcp/server.py:86`（tools/list）调用，同在异常保护之外。
- **影响面**：① `assets/safety/policy.json` 被删、被截断、或人工改出语法错 → 任意
  `tools/call` 抛未捕获异常 → **stdio 进程退出**（宿主侧表现为 MCP 掉线，且掉线原因
  只有一行 traceback）；② remote 面由 `transport_remote.py:509-512` 兜底成
  `-32603 Internal error`，原因被折叠成字符串；③ 与"声明式护栏"的定位冲突：护栏本应
  是"拒绝执行"，实际行为退化为"整体不可用"。
- **判定依据**：三门槛全满足——可捕获（构造 `policy.json` 坏内容后调
  `server.handle({"method":"tools/call",…})` 断言不抛）；有触发路径（运维/打包事故、
  人工编辑）；影响面＝全部工具不可用。**当前无用例覆盖**（`tests/` 无 policy 损坏类用例，
  附录 10.1）。
- **整改措施**：`guardrails.check` 内把装载失败映射成 `deny`（fail-closed）+ 明确错误码，
  `handle()` 外层加兜底 `try` 返回 `-32603` 并落日志，见 `ARCH-RM-ERR-01`。
- **优先级**：**P0**
- **工作量**：1.0 人日
- **验收断言**：`tests/test_remote_guards.py::test_corrupt_policy_denies_instead_of_crashing`
  （两面各一条）——坏 policy 下 `tools/call` 返回 `deny`/`-32603`，进程不退出；
  新增 `tests/test_policy_load.py::test_policy_fail_closed`。

---

### ARCH-ERR-02 每次工具调用重读 policy 且无 schema 校验

- **证据**：`src/vod_mcp/policy.py:12`（`_POLICY_PATH = paths.POLICY`）、`:15-17`
  （`load_policy()` 每次 `open` + `json.load`，无缓存）；调用点 `src/vod_mcp/guardrails.py:14`
  （每个 `tools/call` 一次）。规则消费处直接下标访问、无字段校验：`src/vod_mcp/policy.py:28`
  （`rule["match"]`）、`:96`（`r["severity"]`）、`:87`（`m["regex"]`）。
- **影响面**：① 热路径 IO：远程面每请求一次、stdio 面每调用一次 open+parse；
  ② 人工编辑 `policy.json` 时少一个 `severity`/`match` 字段 ⇒ `KeyError` 而非"规则非法"
  的可读报错，且该异常同样在 `src/vod_mcp/server.py:91` 的保护之外（与 ERR-01 叠加为硬崩）；
  ③ 规则集版本（`assets/safety/policy.json:2` 的 `version: 0.1.0`）与契约版本
  （`assets/contract/tools.schema.json` 的 `version: 0.5.44`）不同步，无人校验。
- **判定依据**：可捕获（删字段后调 `check` 断言错误可读且 fail-closed）；有触发路径
  （手工编辑规则是文档鼓励的操作）；影响面＝护栏可用性。
- **整改措施**：`load_policy()` 加进程内缓存（文件 mtime/size 失效）+ 装载期 schema 校验
  （字段缺失/类型错 → 明确拒绝启动并指出规则 id），见 `ARCH-RM-ERR-02`。
- **优先级**：P1
- **工作量**：1.5 人日
- **验收断言**：`tests/test_policy_load.py::test_rule_schema_violation_names_rule_id`；
  `tests/test_policy_load.py::test_policy_read_is_cached_until_mtime_changes`。

---

### ARCH-ERR-03 上游 HTTP 状态码进入 JSON-RPC `code` 域，explain 表与门禁均覆盖不到

- **证据**：`src/vod_mcp/net.py:209`（`raise ToolError(f"上游返回 {e.code}: {detail}",
  code=e.code)`——把 4xx/5xx 数字当 JSON-RPC 错误码）；对照 `:206`（401 归一为 `-32012`）、
  `:211`（网络不可达归一为 `-32001`）。
  解释表只覆盖产品语义码：`src/vod_mcp/diagnose.py:53-79`（`_EXPLAIN_EXTRA` 键为
  `-32010`/`-32011`/`-32012`/`-32014`/`-32015`/`-32016`/`-32001` 与文本键
  `"上游返回 429"`）。
  门禁扫描口径：`tests/test_explain_codes.py:25`（`re.finditer(r"code\s*=\s*(-320\d\d)", …)`）
  ——只扫 `-320xx` 字面量，`code=e.code` 与 `-3260x` 永不进入门禁。
- **影响面**：① 宿主看到 `code: 429`/`404`/`500`，与 JSON-RPC 保留段语义冲突（`500` 既不
  在 `-32xxx` 段也不在 `-32xxx` 保留段，客户端无法按协议分类）；② `vod-devkit explain 500`
  落到"未分类"（`diagnose.classify` 返回 `("未分类","","")`，`src/vod_mcp/diagnose.py:87`）；
  ③ 新增上游错误面（如 503）既不加解释也不被门禁拦住——错误码清单**没有单一真源**。
- **判定依据**：可捕获（`explain("上游返回 503…")` 断言 `known is False`，即现状；
  或用例扫描 `src/` 内所有 `code=` 赋值形态并断言 ⊆ 解释表）；有触发路径（引擎任何 4xx/5xx）；
  影响面＝宿主错误分类与排障。
- **整改措施**：全部错误码收敛到 `vod_mcp/errors.py` 的常量表（上游状态码映射到
  `-3202x` 段），`explain` 表由常量表派生；门禁改成"所有 `ToolError(code=…)` 的 code
  表达式 ⊆ 常量表"，见 `ARCH-RM-ERR-03`。
- **优先级**：P1
- **工作量**：2.0 人日
- **验收断言**：`tests/test_explain_codes.py::test_all_error_codes_come_from_table`——
  源码内不再出现裸数字 `code=`（除常量定义）；`explain` 对表内每个码 `known is True`。

---

### ARCH-ERR-04 26 处 `except` 函数体只有 `pass`，主链失败痕迹被吞

- **证据**（主链样例，均可打开核对；「形态」列标明是 `pass` 还是静默返回值）：

  | 位置 | 形态 | 被吞掉的事件 |
  |---|---|---|
  | `src/vod_mcp/server.py:119` | `pass` | 载荷标记消费失败（换载荷后"该重启"的信号丢了） |
  | `src/vod_mcp/server.py:153` | `pass` | 首启自诊/构建机残留清理失败（preset 形态唯一兜底） |
  | `src/vod_mcp/net.py:146` | `pass` | 匿名令牌写入 runtime 失败（后续仍报"令牌不可用"） |
  | `src/vod_mcp/net.py:157` | `pass` | meta 带令牌重试的第二次失败（原因整段消失） |
  | `src/vod_mcp/net.py:325` | 静默 `return None` | 领匿名令牌失败（调用方只见"端点不可用"，不见原因） |
  | `src/vod_mcp/runtime_state.py:39` | 静默取空值 | runtime.json 解析失败（读成空配置，`key` 看似"没配"） |
  | `src/vod_mcp/runtime_state.py:210` | `pass` | 日志出口自身写失败（**唯一排障真源**静默失效） |
  | `src/vod_mcp/runtime_state.py:143` | `pass` | 原子写 tmp 的 chmod 失败（0600 没生效，权限窗口无声打开） |
  | `src/vod_mcp/packs/core.py:28` | `pass` | `auth_ensure` 失败（领不到令牌不算本工具的错，但一行痕迹都没有） |

  规模（`ast` 统计，附录 10.1 给出脚本）：`src/` 共 **169** 个 `except` 处理器，
  其中捕获 `Exception` 的 **55** 处，**函数体只有 `pass` 的 26 处**（清单见附录 10.1）。
- **影响面**：失败没有痕迹 ⇒ 现象层只能看到"配了没生效/要重启/没 key"这类**下游症状**，
  与 `docs/design.md` 反复强调的"静默失败比崩溃更难查"直接冲突。典型：`runtime.json`
  被写坏 → 读成空 → 匿名令牌重领 → 设备锚点漂移 → 服务端判"设备绑定不匹配"，
  而插件侧没有任何一行日志指向"文件被写坏"。
- **判定依据**：可捕获（对每个吞点注入异常并断言至少有 `_log` 记录——现无用例）；
  有触发路径（磁盘满、权限、并发写、坏 JSON 都在真实用户机上出现过）；
  影响面＝可诊断性。
- **整改措施**：建立"允许吞"的三类白名单（`OSError`/`JSONDecodeError`/`AttributeError`
  且必须 `_log` 一行带上下文），其余收窄捕获；`_log` 失败时向 stderr 兜底一次，
  见 `ARCH-RM-ERR-04`。
- **优先级**：P1
- **工作量**：3.0 人日
- **验收断言**：`tests/test_error_trace.py::test_no_bare_except_pass`（AST 扫描，
  白名单逐条注明原因）；`tests/test_error_trace.py::test_swallowed_paths_leave_a_log_line`。

---

### ARCH-ERR-05 可观测性＝固定 `/tmp` 文本日志

- **证据**：`src/vod_mcp/runtime_state.py:197`（`def _log(line: str, path: str =
  "/tmp/vod_mcp_server.log")`——**默认参数**固定路径）；`:198-211`（超过 1MB 时 `read()`
  全量再 `write` 尾部 200KB，无锁）；`src/vod_mcp/transport_remote.py:436`（
  `log_message` 直接 `pass`，HTTP 访问日志整体静默）；`src/vod_mcp/server.py:155`
  （启动只记一行 pid/argv/env）；`src/vod_mcp/net.py:188`（记 `http METHOD url key=yes/no`，
  无耗时、无请求 id、无结果码）。
- **影响面**：① 多进程（每个宿主的 stdio server + 远程面）写同一文件，截断重写时互相
  覆盖；② 无法把"一次工具调用"的输入→出口→结果串起来（无 request/tool 关联标识）；
  ③ `/tmp` 在容器/受限沙箱里可能不可写或随重启清空，日志静默消失；④ 无级别 ⇒
  `warn` 与普通流水混排，`_warn` 的告警价值被淹没。
- **判定依据**：可捕获（断言日志行含 tool 名/耗时/结果码字段）；有触发路径（任何一次
  远程面请求或工具调用）；影响面＝线上排障。
- **整改措施**：`_log(event, level, **fields)` 结构化（JSONL）+ 落点可配置
  （`VOD_DEVKIT_LOG`，默认 `machine_state_home()/logs/`）+ 追加锁；远程面把访问日志与
  请求耗时接进同一出口，见 `ARCH-RM-ERR-05`。
- **优先级**：P1
- **工作量**：3.0 人日
- **验收断言**：`tests/test_observability.py::test_log_lines_are_structured_and_carry_tool_context`；
  `tests/test_observability.py::test_log_path_is_configurable_and_creates_private_dir`。

---

### ARCH-ERR-06 `explain` 按文案正则归层，错误码与文案双轨

- **证据**：`src/vod_mcp/diagnose.py:21-51`（`RULES` 15 条全部是正则/关键词，按序命中）、
  `:82-87`（`classify` 用 `re.search` **首个命中**，未收录返回 `("未分类","","")`）、
  `:126-128`（`matches` 对用户手输片段做大小写不敏感通配）。
  同一错误码在不同 raise 点文案不同，例：`-32012` 在 `src/vod_mcp/net.py:206`
  （"鉴权失败（base）"）与 `:335`（"未配置接入 key 且匿名令牌端点不可用"）两处，
  归层靠都不含关键词时落"未分类"。
- **影响面**：① 运维按 `explain` 得到的层/动作取决于文案措辞，改一句文案就换一个层；
  ② 归层由 `RULES` 的**顺序**决定而非错误码：`src/vod_mcp/diagnose.py:43` 的
  `远程面|探活|不可达|401` 排在 `:49` 的 `-32010|产品` 之前，于是"产品未命中且探活失败"
  这句会被判到"网络"，而只提"产品"时又判到"配置"——同一类错误两种归层，取决于措辞；
  ③ 表与 raise 点的一致性只靠 `tests/test_explain_codes.py:30` 的 `-320xx` 扫描，
  文案层无门禁。
- **判定依据**：可捕获（对每个错误码断言 `explain` 的层稳定，不随文案微调改变）；
  有触发路径（`vod-devkit explain` 是面向运维的命令）；影响面＝排障准确度。
- **整改措施**：把层/原因/动作登记为"码 → 元组"的主表，文案匹配降级为兜底；
  见 `ARCH-RM-ERR-06`。
- **优先级**：P2
- **工作量**：2.0 人日
- **验收断言**：`tests/test_explain_codes.py::test_layer_is_stable_per_code`——对每个码，
  改文案（换同义词）后 `explain` 的 `layer` 不变。

---

## 六、维度 D：配置与安全

### 6.1 现状判读

| 安全面 | 有效机制 | 缺口 |
|---|---|---|
| 提交护栏 | 声明式 `assets/safety/policy.json`（4 条规则）＋ `guardrails.check` 两面共用 | 规则损坏/缺失即崩（ERR-01/02） |
| 凭据存储 | `runtime.json` 0600 + 写后 stat 回验（`runtime_state.py:148-159`） | 同目录其它产物未收紧（CFG-01） |
| 凭据传播 | env > runtime > 请求头，401 归一 `-32012` | 三入口判据散落（CFG-05） |
| 远程面暴露 | 默认回环绑定；非回环需显式 `--allow-anon-mint`（`transport_remote.py:519-525`） | `CORS *`＋无 Host 校验＋无内建鉴权（CFG-02） |
| 载荷完整性 | `payload.verify` 逐文件 sha256＋远程面 503 拒绝服务（`transport_remote.py:490-496`） | 校验失败与"载荷未生成"共用一个判定（`src/vod_mcp/transport_remote.py:45` 的 `payload_problems()` 只看当前目录） |
| 凭据泄漏扫描 | `scripts/secret_scan.py`（8 条 secret 模式＋5 条高危模式） | 只扫 tracked（CFG-04） |

**该维结论**：安全模型的"应然"（[`safety-model.md`](safety-model.md)）与实现基本对齐；
缺陷集中在**收紧不完整**（权限、暴露面、扫描面），不是机制缺失。

---

### ARCH-CFG-01 `pending-feedback.jsonl` 存用户原话却未收紧 0600

- **证据**：`src/vod_mcp/pending.py:42-43`（`default_path()` = `~/.vod-devkit/pending-feedback.jsonl`
  ——与 0600 的 `state/runtime.json` 同属 `~/.vod-devkit`）；`:53-67`（条目含 `content`
  与 `originalLines`，即**用户原话全文**）；`:99-117`（`append_entry` / `save_entries`
  只做 `open(...,"a"/"w")` + `fsync` + `os.replace`，**全仓 chmod 清单内无 pending**
  ——附录 10.1 的 `grep -rn "chmod" src/` 只命中 `paths.py`/`runtime_state.py`/`install.py`/
  `remote.py`）。
- **影响面**：默认 umask 下文件权限 0644 ⇒ 同机其他用户可读真实用户抱怨原文（含可能的
  产品名、人名、内部系统名）。这既是对用户的数据承诺问题，也与
  [`safety-model.md`](safety-model.md) 的"本地留痕可控"口径不一致：
  runtime.json（含 key）被收紧到 0600，而"用户原话"这份更敏感的内容反而放开。
- **判定依据**：可捕获（写一条 pending 后 `stat` 断言 `0o600`；现无任何用例覆盖权限，
  附录 10.1）；有触发路径（采集断网时的补交队列，`collect._flush_pending:219` 写入）；
  影响面＝用户数据保密性。
- **整改措施**：`append_entry`/`save_entries` 统一走"原子写 + 0600 + 写后 stat 回验"，
  并对已存在的旧文件做一次宽松收紧（只在权限更宽时 chmod），见 `ARCH-RM-CFG-01`。
- **优先级**：**P0**
- **工作量**：1.0 人日
- **验收断言**：`tests/test_pending_feedback.py::test_pending_file_is_private`——
  创建/追加/重写三条路径后均为 `0o600`；WSL 类忽略 chmod 的环境走告警分支而非异常。

---

### ARCH-CFG-02 远程面 `CORS *` + 无 Host 校验 + 无内建鉴权

- **证据**：`src/vod_mcp/transport_remote.py:439-445`（`_cors()` 无条件发
  `Access-Control-Allow-Origin: *` 与 `Allow-Methods: GET, POST, OPTIONS`）；
  `:464-465`（`do_OPTIONS` 一律 204，预检被放行）；`:471-508`（`do_POST` 全程不校验
  `Origin`/`Host`，只取 `Authorization` 的 Bearer 作为可选身份）；
  `:528-536`（`serve` 默认 `127.0.0.1:9528`，非回环仅告警不拒绝）。
- **影响面**：① 任意网页可对 `http://127.0.0.1:9528` 发跨域 POST（预检被 `*` 放行）→
  在用户已装插件、机器级匿名令牌存在的形态下，网页可**代替用户提交声音**或改会话内
  工具面（`REMOTE_WITHHELD` 已摘 `vod_packs_configure`，但其它只读工具仍可被批量调用）；
  ② 无 `Host` 白名单 ⇒ DNS rebinding 可绕过同源限制，把"仅回环"变成"任意域可达"；
  ③ `--allow-anon-mint` 把"任何能连端口的进程都能用本机身份消耗额度"从默认变成显式，
  但缺 Host/Origin 校验时这条风险仍然成立。
- **判定依据**：可捕获（起远程面后带 `Origin: https://evil.example` 发 POST，断言被拒；
  现无用例）、有触发路径（文档鼓励的同机独立部署形态 `INSTALL.md` 远程模式）、
  影响面＝用户身份与配额被第三方页面消耗。
- **整改措施**：默认只答 `127.0.0.1`/`localhost` 的 Origin 与 Host（可配置白名单），
  预检只回允许的方法与头；非回环绑定要求显式 `--allow-origin`，见 `ARCH-RM-CFG-02`。
- **优先级**：P1
- **工作量**：2.0 人日
- **验收断言**：`tests/test_remote_transport.py::test_foreign_origin_is_rejected`；
  `::test_dns_rebinding_host_header_is_rejected`；`::test_loopback_origin_still_works`。

---

### ARCH-CFG-03 三套原子写实现并存

- **证据**：① `src/vod_mcp/paths.py:223-261`（`atomic_write_text`：同目录 tmp + `fsync` +
  `chmod` + `os.replace`，且带符号链接解析 `:236` 与只读保护 `:240`）；
  ② `src/vod_mcp/runtime_state.py:137-145`（`_write_cfg_unlocked`：固定 `.tmp` 名、
  `write_text` **无 fsync**、chmod 0600、`os.replace`，**无**符号链接/只读保护）；
  ③ `src/vod_mcp/pending.py:108-117`（`save_entries`：`.tmp` + fsync + replace，
  **无 chmod**）。
- **影响面**：① 修一处不修三处——`src/vod_mcp/paths.py:224` 的注释记录了"中断/磁盘满会留下半截
  JSON"的教训，而 `runtime_state` 这条主状态路径至今没有 fsync（掉电可留 0 字节
  `runtime.json`，后果是 key/账本/设备锚点一起丢）；② 只读保护（`chmod 444` 保护）
  只在 `paths.atomic_write_text` 生效，`runtime.json` 走的是另一条，用户"设为只读"
  的意图不被尊重；③ 符号链接被 `os.replace` 换成普通文件的问题在同一仓两套语义。
- **判定依据**：可捕获（对三条路径分别做"中断注入/只读目标/symlink 目标"断言，现无
  统一用例）；有触发路径（runtime.json 是每次提交都写的热路径）；影响面＝状态文件完整性。
- **整改措施**：`runtime_state._write_cfg_unlocked` 与 `pending.save_entries` 一律改调
  `paths.atomic_write_text(mode=0o600)`，删除重复实现，见 `ARCH-RM-CFG-03`。
- **优先级**：P1
- **工作量**：2.0 人日
- **验收断言**：`tests/test_runtime_atomic.py::test_single_atomic_writer`——AST 扫描断言
  仓内只有一处 `os.replace(`（白名单：测试夹具）；三条路径的权限/fsync 行为一致。

---

### ARCH-CFG-04 `secret_scan.py` 覆盖边界

- **证据**：`scripts/secret_scan.py:37-39`（`subprocess.run(["git","ls-files"])` **无
  `timeout`**，且 `out.stdout` 在 git 不存在/非 git 目录时可能为 `None` → `.splitlines()`
  抛 `AttributeError`）；`:45-58`（只遍历 `tracked_files()`）；`.gitignore:18-23`
  （`plugins/vod-devkit/vod_mcp|skills|hooks|contract|safety|build-info.json` 全部排除）
  ⇒ **插件副本内容不被扫**；`:17-33`（8 条凭据模式＋5 条高危模式，但无 `.env` 形态、无通用长十六进制串，
  也不认本仓实际字段名 `java_key`——`src/vod_mcp/runtime_state.py` 落盘用的正是它）。
- **影响面**：① 门禁绿但发布物（插件副本、载荷）里若有明文 key 不会被发现——而
  "副本零提交"正是为了让它不进 git，于是它天然落在扫描面之外；② 无 git 的打包机
  （tarball 解包环境）跑门禁直接崩；③ `git ls-files` 在超大仓上挂住会卡住整条门禁。
- **判定依据**：可捕获（在副本目录放一个形似 key 的字符串，断言扫描命中；现无用例，
  `tests/test_secret_scan.py` 只测模式命中）；有触发路径（CI/pre-push/打包）；影响面＝
  凭据泄漏防线。
- **整改措施**：扫描面改为"tracked 文件 + `plugins/`、载荷目录、`assets/` 全量（除
  二进制）"；`git ls-files` 加 `timeout` 与失败降级；模式表补三类缺口，见 `ARCH-RM-CFG-04`。
- **优先级**：P1
- **工作量**：1.0 人日
- **验收断言**：`tests/test_secret_scan.py::test_scans_generated_copies_too`；
  `::test_git_unavailable_degrades_without_crash`。

---

### ARCH-CFG-05 凭据三入口，优先级判据散落四处

- **证据**：`src/vod_mcp/net.py:29-58`（`_live`：env > runtime 文件 > 进程镜像）、
  `:83-87`（`_eff_key`：显式参数 > `_REQ_KEY` > `_java_key`）、`:269-281`
  （`_explicit_key`：env 或 `token_tier != "anonymous"`）；
  `src/vod_mcp/transport_remote.py:498-505`（Bearer → `scope["x_vod_key"]`）；
  写入口：`src/vodkit_cli/auth_cmd.py:45`（"唯一入口"）、`src/vodkit_cli/install.py:264-268`
  （install 也写 runtime）、`src/vod_mcp/net.py:145`（领到匿名令牌后自写）。
- **影响面**：`src/vodkit_cli/auth_cmd.py:1` 声明"凭据的唯一写入入口"，实际有第三处（`net` 领令牌后
  自行落盘）与第四处（`install` 写 `java_base`）。回答"这台机器为什么走了匿名档"
  需要读 4 个函数；新入口（如企业 SSO）接入时不知道该插在哪一层。
- **判定依据**：可捕获（断言"写入点集合"= 白名单；现状扫描到 3 处写 `java_key`
  ——附录 10.1）；有触发路径（换 key/首装/领令牌/远程头）；影响面＝凭据行为可解释性。
- **整改措施**：把"解析 + 判定 + 写入"收敛为 `vod_mcp/credentials.py`（`resolve()` /
  `explain()` / `store()` 三个函数），`auth_cmd` 与 `net` 只调用，见 `ARCH-RM-CFG-05`。
- **优先级**：P2
- **工作量**：2.0 人日
- **验收断言**：`tests/test_auth.py::test_credential_write_points_are_whitelisted`；
  `::test_credential_explain_reports_priority_chain`。

---

### ARCH-CFG-06 机器级 state 目录权限只在迁移路径收紧

- **证据**：`src/vod_mcp/paths.py:169-175`（`migrate_state_once` 里 `:171` 的 `chmod(target, 0o600)`、
  `:173` 的 `chmod(state, 0o700)`）；对照 `src/vod_mcp/runtime_state.py:174`
  （`_runtime_atomic` 里 `p.parent.mkdir(parents=True, exist_ok=True)`，**无 chmod**）。
- **影响面**：跳过迁移的新装机器上，`~/.vod-devkit/state/` 以默认 umask（0755）创建 ⇒
  同机其他用户可**枚举**目录内文件名（`.migrated`、`runtime.json.corrupt-<时间戳>` 等），
  内容本身仍 0600。属"半个口子"，但目录权限是安全基线的一部分。
- **判定依据**：可捕获（新装后 `stat` 目录断言 0700——`tests/test_token_machine_scope.py`
  未覆盖目录权限）；有触发路径（首次安装）；影响面＝状态目录可枚举。
- **整改措施**：`_runtime_atomic` 的 mkdir 后补一次 `chmod(dir, 0o700)`（失败只告警），
  与 `src/vod_mcp/paths.py:173` 同口径，见 `ARCH-RM-CFG-06`。
- **优先级**：P2
- **工作量**：0.5 人日
- **验收断言**：`tests/test_token_machine_scope.py::test_state_dir_is_private_on_fresh_install`。

---

### ARCH-CFG-07 `guard_scope` 字段剔除靠"新字段记得加"

- **证据**：`src/vod_mcp/policy.py:65-78`（`guard_scope`：只对 `data` 与 `voices[].content`
  做剔除，其它键原样进扫描面）、`:81-89`（`check_text` 把整份 `json.dumps(scope)` 拿去
  跑 deny 正则）。
- **影响面**：文本规则（DB 直连/凭据读取意图）会扫到新增的"用户原话类"字段。例：若把
  `originalLines`（`src/vod_mcp/pending.py:65` 已在用）或后续的自由文本字段加进 `voices[]`，
  用户抱怨里出现 "password 值" 这类字面就会被 `assets/safety/policy.json:43` 的规则误杀
  ——表现为"提交被拒但内容是正常反馈"。
- **判定依据**：可捕获（构造 `voices[].<新自由文本字段>` 含敏感词，断言不误杀；
  现无用例枚举"用户原话字段白名单"）；有触发路径（新增字段是最常见的演进）；
  影响面＝误拒采集。
- **整改措施**：把"用户原话字段"登记为显式常量集合并由 `guard_scope` 消费，
  新增字段必须显式登记；补一条"未登记自由文本字段"的结构用例，见 `ARCH-RM-CFG-07`。
- **优先级**：P2
- **工作量**：1.0 人日
- **验收断言**：`tests/test_tags_whitelist.py::test_free_text_fields_are_explicit`。

---

## 七、维度 E：构建与发布

### 7.1 现状判读

| 链路 | 唯一入口 | 缺口 |
|---|---|---|
| 版本号 | `scripts/release.sh:90-101`（表驱动 + 全落点断言） | 根 `plugin.json` 不在表内（BLD-03） |
| 副本生成 | `scripts/sync_plugin.py`（`prepack` + CI + 测试夹具同源） | 运行期也被调用（DEP-05） |
| 副本校验 | `scripts/verify_copies.py`（内容一致 + 零提交） | 依赖 git（`--no-git` 可降级） |
| 质量门禁 | `.github/workflows/ci.yml`（9 条） / `.gitcode/workflows/ci.yml`（4 条） | 两处漂移（BLD-01） |
| 本地门禁 | `.githooks/pre-push` | 默认未接线（BLD-05） |
| 发布后断言 | `scripts/release.sh:189-199`（现场 pack + `publish_verify`） | `files` 白名单逐文件枚举（BLD-06） |

**该维结论**：单点工具（sync/verify/release）设计成熟且有"为什么不能只看 diff"的
教训沉淀；缺陷在于**门禁的接线与覆盖面**，以及 dev/main 双基线的口径未统一。

---

### ARCH-BLD-01 双 CI 定义漂移，GitCode 只覆盖 3/9 门禁

- **证据**：`.github/workflows/ci.yml:3-6`（`push`/`pull_request` 仅 `main`）、`:22-51`
  （9 条门禁：pyflakes、双副本、secret_scan、用例花名册、规则溯源、mypy、发版对账、pytest、
  dsh 壳单测）＋ `:53-68`（第二个 job：build-info 烟雾 + host-matrix）；
  `.gitcode/workflows/ci.yml:3-6`（同样仅 `main`）、`:27-36`（**3 条门禁**：双副本一致性 / pyflakes / pytest；外加
  一个"不可静默"的定位步骤 `:22`。`install deps` 只装 `pytest pyflakes`，见 `:19`）。
- **影响面**：本仓实际托管在 GitCode，因此**真正跑的门禁只有那 3 条**（双副本一致性 /
  pyflakes / pytest）；`secret_scan`、`mypy`、花名册对账、规则溯源、发版对账、
  dsh 的 `npm test`、宿主矩阵**全部缺席**。
  ① 凭据泄漏与类型错误在 GitCode 侧无门禁；② 两份定义会持续漂移（改一处忘一处）；
  ③ 两者都只在 `main` 触发，而开发基线是 `dev`（见 BLD-02）⇒ **dev 上的提交零门禁**。
- **判定依据**：可捕获（对比两份 workflow 的 step 名集合，断言相等；现无用例）；
  有触发路径（任何 PR 合并）；影响面＝进入主干的代码质量。
- **整改措施**：抽出共用"门禁清单"（脚本级 `scripts/gate_all.py` 或 composite action），
  两份 workflow 都只调用它；触发分支补 `dev`，见 `ARCH-RM-BLD-01`。
- **优先级**：P1
- **工作量**：2.0 人日
- **验收断言**：`tests/test_release_and_pack_paths.py::test_both_ci_definitions_run_same_gates`
  ——解析两份 yaml，step 名集合相等；`::test_ci_triggers_cover_dev_branch`。

---

### ARCH-BLD-02 开发基线 `dev` 而 update/测试夹具仍钉 `main`（release.sh 半步已修）

- **证据**：`src/vodkit_cli/update.py:32`
  （`git rev-parse origin/main`）、`:37`（`git pull --ff-only`，**不带分支参数**）；
  `tests/test_installer.py:120-127`（`_git(SRC_REPO, "clone", "--bare", "--branch", "main", …)`，
  注释自陈"开发分支切到 dev/main 之外时…本文件两条 update 用例秒红、pre-push 门禁卡死"）；
  两份 CI 的 `branches: ["main"]`。**半步已修**：`scripts/release.sh` 的推送目标已由
  dev 头 `95217f1` 改为当前分支（`release.sh:170-176`，`CUR_BRANCH=$(git rev-parse
  --abbrev-ref HEAD)`），本条不再计入该半步。
- **影响面**：① 在 `dev`（或任何非 `main` 分支）上跑 `vod-devkit update`：`rev-parse
  origin/main` 为空 ⇒ `local != remote` ⇒ 走 `git pull --ff-only` ⇒ 失败 ⇒ `exit 1`
  （用户看到"更新失败（有本地改动阻挡 ff？）"，与真实原因无关）；
  ② 本地跑整套 pytest 在**没有 `main` 引用**的检出上出现大量 ERROR（本次实测 71 条，
  见附录 10.3）；③ CI 仍只在 `main` 触发，`dev` 上的提交零门禁（与 BLD-01 叠加）。
- **判定依据**：可捕获（`tests/test_p2_structure.py` 已有 update 语义锁——它锁的是
  "比较 origin/main"这个**错误前提**；改成"当前分支的上游"后该用例需同步）；
  有触发路径（开发者日常）；影响面＝本地与 CI 双红、update 命令失效。
- **整改措施**：`update` 比较"当前分支上游"（`@{upstream}`，缺失时回落 `origin/<branch>`）；
  测试夹具改成 `--branch <当前分支>`，见 `ARCH-RM-BLD-02`。
- **优先级**：P1
- **工作量**：1.0 人日
- **验收断言**：`tests/test_p2_structure.py::test_update_compares_current_upstream`；
  在 `dev` 与本分支上 `python3 -m pytest tests/test_installer.py -q` 无 `main` 依赖 ERROR。

---

### ARCH-BLD-03 版本六处落点，根 `plugin.json` 永久停在 `0.1.0`

- **证据**（同一时刻实测）：`package.json:3` = `0.5.44`；`pyproject.toml:3` = `0.5.44`；
  `src/vod_mcp/__init__.py:8` = `0.5.44`；`plugins/vod-devkit/.codex-plugin/plugin.json:3`
  = `0.5.44`；`build-info.json:2` = `0.5.44`；`assets/contract/tools.schema.json`
  的 `version` = `0.5.44`；而**根** `plugin.json:3` = `0.1.0`。
  机制原因：`scripts/release.sh:97-101`（`EXTRA_FILES` 只有 `.codex-plugin/plugin.json`、
  插件副本 `build-info.json`、`packages/dsh/package.json`）与 `:143-146`（`git add` 清单）
  都不含根 `plugin.json` ⇒ 该文件从写入日起再未被更新。
- **影响面**：根 `plugin.json` 是对外清单（`displayName`/`mcpServers`/`capabilities`/
  `permissions`），按 manifest 读版本的外部登记/校验会拿到 `0.1.0`；同时它与
  `.codex-plugin/plugin.json` 是同一逻辑包的两个 manifest，版本不一致会让"这个包到底是
  哪个版本"出现两个答案。`plugin.json:17` 还把 `VOD_JAVA_API_KEY` 声明为空串
  （无明文，合规）——但同一声明里的版本不可信，会连带削弱整份清单的可信度。
- **判定依据**：可捕获（断言 `release.sh` 的版本落点表覆盖仓内所有 `"version"` 清单文件；
  现无用例，`tests/test_release_and_pack_paths.py` 只测路径）；有触发路径（每次发版）；
  影响面＝对外版本口径。
- **整改措施**：把根 `plugin.json` 纳入 `EXTRA_FILES` 与 `git add` 清单，并补一条
  "清单文件版本落点覆盖"的用例（扫描仓内 `plugin.json`/`package.json`/`pyproject.toml` 等），
  见 `ARCH-RM-BLD-03`。
- **优先级**：P1
- **工作量**：1.0 人日
- **验收断言**：`tests/test_release_and_pack_paths.py::test_all_manifest_versions_agree`——
  七个落点版本全等；`::test_release_bump_table_covers_every_manifest`。

---

### ARCH-BLD-04 根 `build-info.json` 快照落后 HEAD，却被 install 与 provenance 当权威

- **证据**：`build-info.json:2-3`（`"version": "0.5.44"`, `"commitSha":
  "54909d030eb3e798eeb5d5c6f27c3f02ab8dcbd1"`）；同工作树 `git log -1 --format=%H` =
  `ba48d9d…`（快照钉在发版起点提交 `54909d0`，落后 HEAD 三个提交：一次发版 + 两次
  release 修复）。读点：`src/vodkit_cli/common.py:310`
  （`_write_install_manifest` 用 `build-info.json` 的 `version`/`commitSha` 写安装账本）、
  `src/vod_mcp/provenance.py:11-15`（`read_build_info()` 供 `vod_devkit_info`）、
  `src/vodkit_cli/doctor.py:183-193`（把根 `build-info.json` 与载荷那份并列做漂移判定）。
- **影响面**：① `vod_devkit_info` 报告的 `commitSha` 是发版快照而非当前代码 ⇒ 用户/运维
  按它去对账会对到错误的提交；② `install-manifest` 的 `source.commitSha` 同源写错，
  `reachable`/`released`（`common.py:319-321`）跟着判错；③ 该文件是 tracked 快照，
  设计上"根=发版快照 v^"（`src/vodkit_cli/doctor.py:183` 注释），但没有任何用例或脚本提示
  "工作树 HEAD 与快照不一致属于正常还是异常"。
- **判定依据**：可捕获（断言 `install-manifest.source.commitSha` 等于"安装时实际代码"
  ——现在两者可不等且无人报警）；有触发路径（任何非发版提交上安装）；影响面＝溯源可信度。
- **整改措施**：给 `build-info.json` 的 `commitSha` 加"来源标记"（`snapshot: released|worktree`），
  安装时若检测到工作树 HEAD 与快照不一致，在账本里记两个值并在 `doctor` 里显式提示；
  见 `ARCH-RM-BLD-04`。
- **优先级**：P1
- **工作量**：1.5 人日
- **验收断言**：`tests/test_info_binding.py::test_install_manifest_records_worktree_head_when_snapshot_lags`。

---

### ARCH-BLD-05 `.githooks/pre-push` 未接线，且含作者机绝对路径

- **证据**：`CONTRIBUTING.md:31`（"提交前跑 `.githooks/pre-push`（已 `git config core.hooksPath
  .githooks`）"）；实测 `git config --get core.hooksPath` **为空**（附录 10.3）⇒ 新克隆里
  门禁不生效；脚本内作者机硬编码：`.githooks/pre-push:3`（`PY=$(ls
  /root/.hermes/tools/python-3.14.7*/bin/python3 … || command -v python3)`）、`:4`
  （`LIBS=/root/.hermes/cache/scratch/pylibs`）、`:15`（日志写 `/tmp/prepush-dsh.log`）。
- **影响面**：① 开发者以为"push 前会跑 pytest/pyflakes/双副本/secret_scan"，实际默认不跑；
  与 BLD-01（GitCode 只 4 条门禁）叠加 ⇒ **本地与平台都没有 secret_scan/mypy**；
  ② `PY` 在非作者机上静默回落 `python3`（版本可能不是 3.10+ 的契约），
  失败原因容易误判为"环境问题"；③ `/tmp` 日志在受限环境不可写。
- **判定依据**：可捕获（`git config --get core.hooksPath` 断言等于 `.githooks`；或
  提供 `scripts/install_hooks.py` 并由 CONTRIBUTING 指向它——现在文档承诺了却没有机制）；
  有触发路径（每个新克隆）；影响面＝门禁可信度。
- **整改措施**：提供 `scripts/install_hooks.sh`（幂等设置 `core.hooksPath`），CONTRIBUTING
  改成"先跑安装钩子脚本"；`pre-push` 去掉作者机路径（`PY` 用 `command -v python3`，
  `LIBS` 可选），见 `ARCH-RM-BLD-05`。
- **优先级**：P1
- **工作量**：1.0 人日
- **验收断言**：`tests/test_release_and_pack_paths.py::test_pre_push_has_no_author_paths`
  （断言脚本内不含 `/root/.hermes`）；`::test_hook_install_script_is_idempotent`。

---

### ARCH-BLD-06 `package.json` 的 `files` 逐文件枚举

- **证据**：`package.json:10-57`（`files` 逐条列出 30+ 个 `src/vod_mcp/*.py`，含
  `src/vod_mcp/host_adapters/` 与 `src/vod_mcp/packs/` 两个目录条目，其余全是文件名）；
  兜底在后：`scripts/release.sh:189-199`（发版现场 `npm pack` 后断言包内代码指纹）；
  历史事故：`CHANGELOG.md` 记 "npm 0.4.1 实锤——包内缺 `pending.py`：`files` 白名单逐文件
  枚举漏新模块".
- **影响面**：新增模块忘加 `files` ⇒ npm 包缺文件，而仓内测试与 CI 全绿；只能靠发版后的
  现场 pack 断言或用户报"ImportError"发现。目录型条目（`packs/`、`host_adapters/`）与
  文件型条目混排，规则不统一，进一步增加"该加哪个"的判断成本。
- **判定依据**：可捕获（`npm pack --dry-run` 的文件清单 vs `src/vod_mcp/**/*.py` 全集，
  断言无缺失；现无用例在 CI 里跑这个对照）；有触发路径（每次发版）；影响面＝发布物完整性。
- **整改措施**：`files` 改为目录形态（`src/vod_mcp` 整包）或由 `prepack` 生成；
  补一条 CI 用例"包内代码指纹 == 仓内指纹"（可复用 `scripts/pack_verify.py`），
  见 `ARCH-RM-BLD-06`。
- **优先级**：P2
- **工作量**：2.0 人日
- **验收断言**：`tests/test_packaging.py::test_packed_files_cover_all_src_modules`。

---

### ARCH-BLD-07 `sync_plugin.py` 用字符串切分解析 `__version__`

- **证据**：`scripts/sync_plugin.py:51-52`（`return
  path.read_text(...).split('__version__ = "')[1].split('"')[0]`）；调用点 `:82`
  （`version = _version_from_init(root / "src" / "vod_mcp" / "__init__.py")`）；
  用例已把解析器打桩绕开：`tests/test_review_r2.py:207`
  （`monkeypatch.setattr(sync_plugin, "_version_from_init", lambda p: "9.9.9")`）。
- **影响面**：`src/vod_mcp/__init__.py:8` 一旦写成带类型注解（`__version__: str = "0.5.44"`）
  或加注释换行，`split` 索引即 `IndexError`。该函数在 `prepack`（`package.json:74`）、
  CI、发版链上都跑；失败时机集中在打包与发版，最贵的时候炸。用例打桩意味着这条
  解析路径**没有任何真实覆盖**。
- **判定依据**：可捕获（对三种写法（无注解/带注解/前后有注释）断言解析结果正确）；
  有触发路径（改一行版本声明）；影响面＝打包/发版中断。
- **整改措施**：改用 `ast.parse` 读取模块级 `__version__` 赋值（或 `importlib` 读包元数据），
  并补真实用例（不再打桩），见 `ARCH-RM-BLD-07`。
- **优先级**：P2
- **工作量**：0.5 人日
- **验收断言**：`tests/test_copies_generated.py::test_version_parser_handles_annotated_form`。

---

## 八、覆盖度自检（M1 判据）

| 维度 | 条目数 | 每条均有 path:line 证据 | 每条均有触发路径与影响面 | 每维 ≥2 条 | 无缺陷项 |
|---|---|---|---|---|---|
| A 模块依赖 | 6 | ✔ | ✔ | ✔ | — |
| B 核心调用链 | 6 | ✔ | ✔ | ✔ | 远程面 `tools/list` 门控、`REMOTE_WITHHELD` 的会话隔离结论**不是缺陷**（已在 `packs/__init__.py:79-91` 定论） |
| C 错误处理与可观测性 | 6 | ✔ | ✔ | ✔ | 归因历史 cap 10（有界但显式+有用例） |
| D 配置与安全 | 7 | ✔ | ✔ | ✔ | 护栏规则集本身、载荷 sha256 校验**有效** |
| E 构建与发布 | 7 | ✔ | ✔ | ✔ | 副本零提交 + 生成器/校验器成对**有效** |
| **合计** | **32** | — | — | — | — |

## 九、建议（不计缺陷，风格与体验）

以下三条不满足三门槛（或无明确触发路径，或影响面无法量化），按"建议"记录：

1. **`src/vod_mcp/tools.py:14` 的 `ToolError` re-export**：`src/vod_mcp/tools.py:14` 用 `noqa: F401` 保留
   `from vod_mcp.net import ToolError`，供 `except tools.ToolError` 沿用。文档已解释
   （`tools.py:7-9` 的 re-export 纪律），但与 ERR-03 建议的 "`errors.py` 单一真源"
   一起做会更干净。
2. **`src/vod_mcp/provenance.py:56` 的 `__import__` 反射**：`__import__("vod_mcp.packs",
   fromlist=["effective_packs"])` 可用普通 import 表达；属可读性问题，无行为差异。
3. **`src/vod_mcp/transport_remote.py:436` 的 `log_message` 全静默**：已被 ERR-05 吸收为缺陷的一部分，
   若要单独看，它是"访问日志缺失"的最小修法（改成结构化落点即可）。

## 十、附录：复核方式

### 10.1 证据复扫命令（同基线可直接跑）

```bash
# 双向依赖 + 懒导入（DEP-01）
grep -n "from vod_mcp import runtime_state" src/vod_mcp/net.py
grep -n "from vod_mcp import net" src/vod_mcp/runtime_state.py

# 聚合导入（DEP-02）
sed -n '8,25p' src/vod_mcp/host_adapters/__init__.py
grep -n "不许\* import host_adapters" src/vod_mcp/transport_remote.py

# 入口设根（DEP-04）
grep -n "SRC_ROOT\|DIST_ROOT\|VOD_DEVKIT_ROOT" src/vodkit_cli/cli.py npm/cli.js bin/vod-devkit

# 吞异常规模（ERR-04）：用 ast 数，别用 grep（grep 会把 except/else、续行混算）
python3 - <<'PY'
import ast, pathlib
handlers = only_pass = exc_only = 0
for p in sorted(pathlib.Path('src').rglob('*.py')):
    for n in ast.walk(ast.parse(p.read_text('utf-8'))):
        if not isinstance(n, ast.ExceptHandler):
            continue
        handlers += 1
        if isinstance(n.type, ast.Name) and n.type.id == 'Exception':
            exc_only += 1
        body = [b for b in n.body
                if not (isinstance(b, ast.Pass) or
                        (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)))]
        if not body:
            only_pass += 1
            print(f'{p}:{n.lineno}  except {ast.unparse(n.type) if n.type else ":"}')
print(f'handlers={handlers} except_Exception={exc_only} body_only_pass={only_pass}')
PY
# 期望（同基线）：handlers=169 except_Exception=55 body_only_pass=26

# 权限收紧面（CFG-01/03/06）
grep -rn "chmod\|0o600\|0o700" src/ --include=*.py

# 错误码域（ERR-03）
grep -rn "code=" src/ --include=*.py | grep -v "code=-32"
grep -n "\"-32" src/vod_mcp/diagnose.py

# 版本落点（BLD-03）
grep -rn '"version"' package.json plugin.json pyproject.toml \
  plugins/vod-devkit/.codex-plugin/plugin.json packages/dsh/package.json
grep -n "__version__" src/vod_mcp/__init__.py

# 门禁接线（BLD-01/05）
grep -n "branches:" .github/workflows/ci.yml .gitcode/workflows/ci.yml
git config --get core.hooksPath || echo "(未接线)"
```

### 10.2 依赖图复算

用 `ast` 抽 import 边（含函数内 import）后做环检测，步骤：

```bash
python3 - <<'PY'
import ast, pathlib, collections
paths = list(pathlib.Path('src').rglob('*.py'))
mods = {str(p)[4:-3].replace('/', '.') for p in paths}
edges = collections.defaultdict(set)
for p in paths:
    me = str(p)[4:-3].replace('/', '.'); tree = ast.parse(p.read_text('utf-8'))
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module in mods:
            edges[me].add(n.module)
            edges[me] |= {n.module + '.' + a.name for a in n.names if n.module + '.' + a.name in mods}
        elif isinstance(n, ast.Import):
            edges[me] |= {a.name for a in n.names if a.name in mods}
print(sum(len(v) for v in edges.values()), 'edges')
# 环：net <-> runtime_state（函数内 import 使其可运行）
PY
```

### 10.3 实测记录（2026-11-19，本基线工作树）

| 项目 | 命令 | 结果 |
|---|---|---|
| 依赖环 | 10.2 脚本 | 仅 `vod_mcp.net` ↔ `vod_mcp.runtime_state` 一组 |
| 吞异常 | 10.1 的 `ast` 脚本 | 169 个 `except` / 捕 `Exception` 55 处 / 体仅 `pass` 26 处 |
| 版本一致性 | 10.1 的 grep | 六处 `0.5.44`，根 `plugin.json` = `0.1.0` |
| 裸 HEAD 对比 | `git log -1 --format=%H` vs `build-info.json` | `ba48d9d…` vs `54909d0…` |
| 钩子接线 | `git config --get core.hooksPath` | 空（未接线） |
| 双 CI 门禁数 | 两份 workflow 的 step/name 计数 | 9 + host-matrix vs 4 |
| 整套 pytest（有 `main` 引用的可写检出） | `python3 -m pytest tests/ -q -p no:randomly` | 31 失败 / 0 错误；失败集中在 dsh 宿主与 state_read（环境性，见下注） |
| 整套 pytest（本工作树，无 `main` 引用） | 同命令 | 13 失败 / 71 错误（其中 71 ERROR 全部来自 `tests/test_installer.py` 的 `--branch main` 克隆夹具） |

> 注：上表 pytest 结果**不是本台账引入的**，是同基线既有状态。环境差异两处：① 本执行
> 环境额外装了 `pytest-randomly 5.0.0`（会打乱用例顺序，故用 `-p no:randomly` 取确定性
> 结果），CI 不装该插件；② 本工作树检出没有 `main` 引用且 `.git` 只读，`tests/test_installer.py:125`
> 的 `--branch main` 克隆夹具因此整体报错——这正是 ARCH-BLD-02 要修的口径。

### 10.4 与既有文档的边界

| 既有文档 | 关系 |
|---|---|
| [`architecture.md`](architecture.md) | 结构"应然"契约；本台账不改其结论，DEP-04 只记录"设根覆盖不全"这一实然差距 |
| [`design.md`](design.md) | 设计决策与 `D-*` 编号来源；本台账每条都指向已有决策而不是另造口径 |
| [`safety-model.md`](safety-model.md) | 安全"应然"；CFG-01/02 是实然缺口 |
| [`review-456-analysis.md`](review-456-analysis.md) | 远程面 ④⑤⑥ 专项（会话隔离、草稿归属）；本台账 CALL-03 只补"实现与 SDK 耦合"这一层，不重复其结论 |
| [`decisions.md`](decisions.md) | 决策台账；整改若推翻某条 `D-*`，须先在此追加决策再改代码（见 remediation 第 0 节） |