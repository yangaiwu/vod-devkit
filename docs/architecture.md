# 架构与目录结构（本仓的结构契约）

本文件是**结构层面的唯一契约**：目录放什么、什么可以生成、根目录能有多少条目，
以及为什么这么定。改结构先改这里，再改用例（`tests/test_structure_guards.py::test_s129_*`）。

对标对象：huaweicloud-devkit v2（commit adfd826，本机克隆通读）。我们只借**结构形态**，
不借业务面（云操作面在 S126 里被用例锁死不做）。

## 一、对方的结构是怎么组织的（实测，不是印象）

devkit 根目录（排除点文件与 11 个 `REPORT-*.md`）共 **26** 个条目，其中只有 6 个是目录：

```
plugins/huaweicloud-core/      ← 唯一的"宿主发布物"包（核心）
integrations/<host>/           ← 宿主专属安装件（commands/、hooks/）
rules/                         ← 共享风险规则
skills/                        ← 共享技能（顶层，与 src/packs 的源分开）
scripts/                       ← 构建/校验（build-plugin / sync-skills / validate-package / pack-verify）
test/                          ← 测试（node --test，含 e2e 驱动与夹具）
docs/                          ← 文档
```

`plugins/huaweicloud-core/` 内部（AGENTS.md 里画的那张图，实测一致）：

```
src/             ← 源码（TypeScript）
src/packs/       ← 能力包：每包 handlers/schemas/skills + registry（归属真源）+ enable
dist/            ← tsc 产物（零提交，运行时只读它）
skills/          ← **生成物**：由 src/packs/*/skills 汇总（零提交，npm run build 重生成）
safety/          ← policy.json + 风险规则
hooks/           ← PreToolUse 钩子（hooks.json 声明 + 脚本）
.codex-plugin/ .claude-plugin/ .cursor-plugin/ .workbuddy-plugin/ .hermes-plugin/  ← 各宿主清单
.mcp.json        ← MCP 入口
openclaw.plugin.json
```

四条可复用的纪律（它们的目录之所以不散，靠的就是这四条）：

1. **一个插件包**：所有宿主清单、钩子、技能、规则、运行时全在一个包里；根目录只有薄壳
   （`bin/setup.cjs`、`mcp.json`、`plugin.json`）与共享资产。
2. **源与生成物分离**：`src/` 是真源，`dist/`、`skills/` 是零提交生成物；生成有唯一入口
   （`scripts/build-plugin.mjs`、`scripts/sync-skills.mjs`），校验器与生成器成对（`--check`）。
3. **共享资产单一落点**：规则在 `rules/`（或包内 `safety/`），技能源在 `src/packs/*/skills`，
   发布树在包内 `skills/`——同一个东西不会有两个"真源"。
4. **门禁脚本化**：`validate-package.mjs`（结构校验）、`structure.test.ts`（结构用例）、
   jscpd/markdownlint 都挂在 `npm run validate` / CI 上，结构靠机器守，不靠人自觉。

## 二、迁移前的结构（实测快照，S3-A 之前；现状见第三节与第七章）

根目录（排除 `.git`/`.github`）**42 个条目**——比对方多 16 个，且混了运行时状态与产物：

```
源码/资产   vod_mcp/(38) vodkit_cli/(10) contract/(1) safety/(1) skills/(8) hooks/(1)
            integrations/(10) plugins/(58) npm/(1) bin/(1) dsh/(621) scripts/(16) tests/(65)
文档         docs/(12) README.md README.en.md INSTALL.md QUICKSTART.md RELEASING.md
            CHANGELOG.md CONTRIBUTING.md SECURITY.md SUPPORT.md CODE_OF_CONDUCT.md
            NOTICE OWNERS LICENSE.txt
元数据       package.json pyproject.toml plugin.json build-info.json（生成但入库）
运行期       install-manifest.json（gitignore） .e2e-*.json/.log（gitignore） *.tgz（gitignore）
缓存         .mypy_cache/ .pytest_cache/（gitignore）
```

问题不是"有脏文件"（脏文件都已 gitignore），而是**语义层面的散**：

- `contract/`、`safety/`、`skills/`、`hooks/` 四个共享资产挂在根上，与 `vod_mcp/`（运行时）、
  `vodkit_cli/`（安装器）平级——读者看不出"谁是源、谁是生成物、谁随包发"。
- 发布物散在两处：`plugins/vod-devkit/`（宿主清单 + 生成副本）与 `npm/`（npx 引导壳），
  中间没有"一个插件包"的边界。
- 生成物 `build-info.json` 在根且入库，与 `plugins/vod-devkit/build-info.json`（零提交）
  同名不同待遇，容易被当成同一件东西。
- 钩子曾以"hermes 专用插件目录"存在（`hermes-plugin/`），是宿主特例而不是统一机制——
  已按 D-hook-unify-1 改为 `hooks/` 下的宿主无关脚本（stdin JSON → stdout JSON）。

## 三、目标结构（vod-devkit 版，不照抄 TS 工程）

```
plugins/vod-devkit/            ← 唯一"宿主发布物"：清单 + 钩子 + 技能 + 规则 + 运行时副本
  plugin.json                    Agent Plugins 清单（$schema）
  .codex-plugin/plugin.json     codex 兼容清单
  .mcp.json                     MCP 入口（CLI 形态，见 D-mcp-manifest-a3-1）
  hooks/vod_router.py           宿主无关钩子（由 integrations/hermes/hooks/ 同步）
  skills/ contract/ safety/     发布树（生成物，零提交）
  vod_mcp/ build-info.json      运行时副本（生成物，零提交）

src/                           ← 唯一的可导入 Python 包根（S3 起，标准 src-layout）
  vod_mcp/                       运行时（MCP server、适配器、packs）
  vodkit_cli/                    安装器 CLI

assets/                        ← 项目级资产（不进 wheel；随 npm 载荷/插件副本分发）
  skills/ contract/ safety/      共享资产（发布/载荷布局仍是根级平铺，见 paths.ASSETS）

integrations/hermes/           ← 宿主规格 + 宿主侧 hook 脚本（hooks/vod_router.py）
  host.json
  hooks/vod_router.py           真源；载荷物化为 <payload>/hooks/vod_router.py

packages/dsh/                  ← dsh 壳（独立 npm 包）
npm/cli.js  bin/vod-devkit     ← 薄壳：找解释器 + 显式设两个根 + 透传参数
scripts/                       ← 生成器与校验器成对（sync_plugin ↔ verify_copies，case_roster 等）
tests/                         ← pytest（含结构/范围/用例花名册门禁）
docs/                          ← architecture(本文件) / design / proposal / decisions /
                                 safety-model / hooks / host-realverify / scheme-overview
```

根目录保留的条目（这就是"预算"，见门禁 S129）：

```
src/ assets/ packages/ plugins/ integrations/ scripts/ tests/ docs/ npm/ bin/
README.md README.en.md INSTALL.md QUICKSTART.md RELEASING.md CHANGELOG.md
CONTRIBUTING.md SECURITY.md SUPPORT.md CODE_OF_CONDUCT.md NOTICE OWNERS LICENSE.txt
package.json pyproject.toml
```

**运行期产物不进根目录**：`install-manifest.json`、`runtime.json`、载荷、`.e2e-*`、`*.tgz`
一律 gitignore，且（阶段 3 起）落到 `.state/` 或用户目录。

## 四、迁移分阶（每阶可独立回滚，每阶都有用例兜）

| 阶段 | 动作 | 触及点 | 风险 | 验收 |
|---|---|---|---|---|
| S1（已完成） | 落结构契约 + 根目录预算门禁 + README 对齐 | 文档 + 1 条用例 | 零（不改运行路径） | `test_s129_*` 绿；README 结构节与本文一致 |
| S2（已完成 2026-11-15） | `contract/ safety/ skills/ hooks/` → `src/`；**发布布局不变** | `paths.py` 增 `ASSETS`（仓内=src/，载荷/插件副本=根）、`sync_plugin.PAIRS`、`payload.sources`、`rules_provenance` 与 `registry_reconcile` 的路径解析、`package.json files`、约 16 处测试路径 | 中（路径是公共契约） | 全量 pytest 全绿；临时 HOME 装机实测载荷仍是 `skills/contract/safety/hooks` 平铺（50 文件）；hook 仍注册；doctor OK |
| S3（已完成 2026-11-15） | `vod_mcp/ vodkit_cli/` → `src/`，资产 → `assets/`，hook → `integrations/hermes/hooks/`，`dsh/` → `packages/dsh/` | `bin/vod-devkit`、`npm/cli.js`、`server_entry()`、载荷入口、CI、约 45 处测试路径 | 高（装机入口路径变了） | 全量 pytest 绿（54 文件）；`host_matrix` 9 宿主 8 PASS/1 已修；载荷仍平铺 `vod_mcp/skills/contract/safety/hooks` |
| S4 | 运行期状态收进 `~/.vod-devkit/state/`（状态跟机器不跟副本） | `paths.RUNTIME_JSON`、迁移一次、doctor 提示 | 中（语义变更，需负责人拍板） | key/账本升版不重置；旧副本自动迁移 |

S2/S3 的顺序不能反：先让"共享资产有唯一落点"，再动"运行时入口路径"——否则一次改动
同时换了"资产在哪"和"谁在跑"，出问题时无法二分定位。

## 五、为什么不用"devkit 的 dist/ 模式"

它们发的是编译产物（`dist/`），因为 Node 需要构建；我们是纯 Python 源码直跑（零依赖是
优势），所以对应物不是 `dist/`，而是**载荷副本**：`payloads/<ver>/`（用户目录，零提交、
版本隔离）。对应关系：

| devkit | 我们 | 说明 |
|---|---|---|
| `src/` → `dist/` | `src/`（真源）→ `payloads/<ver>/`（运行时副本） | 都不入库；都保证"跑的是构建出来的那份" |
| `skills/`（包内，由 src/packs 生成） | `plugins/vod-devkit/skills/`（由 `assets/skills/` 生成） | 生成器唯一入口 + 零提交 |
| `validate-package.mjs` + `structure.test.ts` | `scripts/verify_copies.py` + `tests/test_structure_guards.py` | 校验器/结构用例 |
| `REPORT-*.md` 堆根（他们也有噪声） | 不放根：报告进 `docs/reports/`（阶段 2 起） | 不复制这条噪声 |

## 六、这次通读后"补齐的短板"清单

| 短板 | 处理 |
|---|---|
| 根目录零散（42 条 vs 26 条） | 本文定预算 + S129 门禁用例；S2/S3 收敛 |
| 钩子以宿主特例存在（`hermes-plugin/`） | D-hook-unify-1：`hooks/vod_router.py` + 宿主注册机制（已落地，`hermes hooks list/test` 可验） |
| 结构没有可执行契约 | 本文 + `test_s129_*` |
| README 缺"每宿主四件套/钩子/能力包/安全模型/结构" | 本次补齐（见 README 对应节） |
| 生成物与源混在根上 | S2 |
| 运行期状态在仓根（`install-manifest.json`） | 已 gitignore；S4 迁到用户目录 |

## 七、S3 规格（2026-11-15 评审后拍死，实现以此为准）

### 7.1 两个根：取值表（三形态）

`SRC_ROOT` = 找**源码**（Python 包与共享资产）；`DIST_ROOT` = 找**分发态**（manifest、
build-info、载荷、指向 payload 的入口）。两者只在仓内分离，在载荷/插件副本里通常同指。

| 形态 | SRC_ROOT | DIST_ROOT | 说明 |
|---|---|---|---|
| 仓内直跑（pytest / host_matrix / `bin/vod-devkit` 直接跑） | `<repo>/src`（只含可导入包） | `<repo>` | 唯一分离形态；`install-manifest.json` / `build-info.json` 在 DIST_ROOT；项目级资产在 `<repo>/assets` |
| 载荷副本 `~/.vod-devkit/payloads/<v>/` | 载荷根 | 载荷根 | 代码与资产都在载荷内；`paths.ROOT` 语义不变（本阶段不动载荷布局） |
| 插件副本 `plugins/vod-devkit/` | 插件包根 | 插件包根 | **不做 src/ 内嵌**（见 7.2）；代码落点仍是 `plugins/vod-devkit/vod_mcp/` |

判定顺序（`paths.py` 里只写一次）：`(DIST_ROOT/"src"/"vod_mcp").is_dir()` → 仓内形态；
否则 → 载荷/插件形态（两根同指 DIST_ROOT）。

### 7.2 插件副本拒绝内嵌 `src/`

devkit 把源码放进插件包（`plugins/huaweicloud-core/src`），我们不跟：

- 插件副本是**发布物**，布局已被多处断言（`tests/test_installer.py::test_plugin_selfcontained_contract`
  断言 `plugins/vod-devkit/vod_mcp/server.py` 存在且与源码 hash 相同）；
- `.mcp.json` 是 CLI 形态 + 安装器改写（D-mcp-manifest-a3-1），改写产物的 entry 指向**载荷**，
  不是插件包内部路径；把代码挪进 `plugins/vod-devkit/src/vod_mcp/` 只会让发布物布局与
  老装机假设分叉，换不来任何能力。
结论：插件副本保持 `vod_mcp/ skills/ contract/ safety/` 平铺；`src/` 只属于仓内形态。

### 7.3 旧布局回落的生命周期（不许永久活着）

S3 落地后，仓内旧位置（`<repo>/vod_mcp/`、`<repo>/skills/`）不再存在。为了老分支/老脚本
在迁移期不炸，`paths.py` 保留**一段**回落：

- 触发：`DIST_ROOT/vod_mcp/` 存在但 `DIST_ROOT/src/vod_mcp/` 不存在；
- 行为：按旧布局解析，并发 `DeprecationWarning("仓内旧布局已弃用：请使用 src/（0.7.0 删除）")`；
- 退出条件：**0.7.0 删除该分支**（`docs/architecture.md` 与本条一起改），`tests/test_p2_structure.py`
  锁一条"回落只能存在于 0.6.x"的断言（版本号从 `vod_mcp.__init__` 读，≥0.7 时该分支必须不存在）；
- 载荷/插件副本**永不走**这条回落（它们从来是平铺布局）。

### 7.4 测试影响（实测，不是估算）

- `grep -rn "paths\.ROOT|monkeypatch.*ROOT|patch.*ROOT" tests/` → **0 处**：没有测试 patch 源码根；
- 18 处属于 `_runtime_path` / `VOD_DEVKIT_MANIFEST` 的单点覆盖——它们与 S3 无关（运行期状态与
  安装名册本来就通过这两个口重定向），迁移后不变；
- 真正的迁移面是**字面路径拼接**：`tests/ + scripts/` 里 `... / "vod_mcp"` 共 45 处（9 个文件，
  含 `tests/probe.py`、`scripts/e2e_nightly_behavior.py`）；S2 已收掉 16 处 skills/contract 拼接。
  这 45 处按三类处理：①指向"源码树" → 改用 `paths.SRC_ROOT`；②指向"载荷/插件副本" → 保持字面；
  ③测试夹具自建临时仓 → 同时建 `src/`（包）与 `assets/`（资产）+ 旧布局（验证回落）。

### 7.5 `hooks/` 归位：宿主侧资产，不进 `src/`

实测：`vod_router.py` **不被 server import**，只被 hermes 适配器按路径引用
（`paths.HOOKS / "vod_router.py"`）、被测试按路径加载。按"性质决定位置"：

- 源：`integrations/hermes/hooks/vod_router.py`（与 devkit 的 `integrations/<host>/hooks/` 同构）；
  将来 codex 侧要用，提升为 `integrations/hooks/` 共享，不复制文件；
- 发布：载荷仍是 `<payload>/hooks/vod_router.py`（装机路径不变），`payload.sources["hooks"]`
  改从 `integrations/hermes/hooks` 取；
- S2 把 hooks 放进 `src/` 是按"共享资产"归并，性质核对后纠正——记在这里，避免下次又按对称性摆。

### 7.6 PR 拆分（回滚粒度）

| PR | 范围 | 验证面 |
|---|---|---|
| S3-A | 两个根 + `src/{vod_mcp,vodkit_cli}` 迁移 + `packages/dsh/` + hook 归位 + 旧布局回落 + 测试路径 | 三形态都还在跑：pytest / 临时 HOME 装机 / host_matrix 9 PASS + dsh 41 例 |
| S3-B（单独） | `bin/` 与 `npm/cli.js` 合并成一个引导壳 | 三种入口都能起：npx / 插件副本 / 仓内直跑 |

合并壳不并进 S3-A：目录迁移的验证是"三种形态还在跑"，壳合并的验证是"三种入口都能起"，
验证面不同，混在一起回滚粒度太粗。

### 7.7 业界对照后的三处收紧（2026-11-15 二次评审）

**7.7.1 资产位置：仓根 `assets/`，不进 `src/`，也不用 `importlib.resources`。判据是"进不进 wheel"。**

- `pyproject` 的打包面只有 `vod_mcp` / `vodkit_cli` 两个包；`skills/contract/safety` **不进 wheel**，
  它们是**项目级资产**，随 npm 载荷分发（`<payload>/skills` 等）。
- `importlib.resources` 解决的是"包内数据在 zip/命名空间包/冻结分发下的可靠访问"。我们的资产既不在
  包内、又必须**以真实文件存在**（要拷进宿主技能目录；hook command 要可执行路径），所以 resources
  在这里不适用；硬套会把"读资源"和"物化到磁盘"拆成两条路径，反而制造漂移。
- 触发改用 resources 的条件（写死）：出现 wheel-only 或冻结分发（PyInstaller 等）时，资产打包进
  `vod_mcp/assets/`，读取走 `importlib.resources`，载荷仍由安装器物化——以物化目录为运行时真源。
- 因此 S2 把资产从仓根收进 `src/` 只完成了"收成一个资产根"；按性质，最终位置是仓根 `assets/`
  （S3-A 挪过去）。`src/` 从此只放**可导入的 Python 包**。

**7.7.2 根由入口显式设置，`paths.py` 只读不猜**

| 入口 | 设置的变量 | 备注 |
|---|---|---|
| `bin/vod-devkit`（仓内/载荷都走它） | `VOD_DEVKIT_SRC_ROOT` / `VOD_DEVKIT_DIST_ROOT` | 脚本位置已知，直接算 |
| `npm/cli.js` | 同上（透传给 python 子进程） | 只做引导，不猜布局 |
| `vod_mcp/server.py` 的 `main()` | 同上（入口未设时） | 载荷形态两根同指 |
| `tests/conftest.py`、`scripts/host_matrix.py` | 显式指向源码根 | 开发入口 |
| 插件副本 `.mcp.json` | 安装器改写时写入 env/args | 插件包根 |

`paths.py` 的职责收窄为：**读入口已设置的值**；读不到时用"`vod_mcp` 的父目录"derive-once 兜底
（仓内开发/旧脚本），并发 `DeprecationWarning`；两处都不可知时**硬失败**并提示应设哪个变量——
不再"猜自己在哪种形态下"。

**7.7.3 `packages/dsh/` 与 uv workspace**

- dsh 是**独立 npm 包**（`dsh-vod-devkit`），不是 Python 包；收进 `packages/dsh/` 只是归位，不引入 workspace。
- S3 后 Python 可导入包仍只有一组（`src/vod_mcp` + `src/vodkit_cli`，同一 pyproject）。uv workspace 的
  触发条件是"出现第二个可独立发布的 Python 成员包"（各自 pyproject + 版本），到那天再评估。

## 八、S3 落地：两个根 + 标准 src-layout（2026-11-15 实测）

### 8.1 两根取值表（唯一权威）

> 规格见第七章；本章是"实际做成了什么"的实测记录。

| 形态 | `SRC_ROOT` | `DIST_ROOT` | `ASSETS` | 说明 |
|---|---|---|---|---|
| 仓内直跑 | `<repo>/src` | `<repo>` | `<repo>/assets` | pytest、`scripts/*`、`bin/vod-devkit` |
| 载荷副本 `~/.vod-devkit/payloads/<v>/` | 载荷根 | 载荷根 | 载荷根（平铺） | 代码与资产都在载荷内，两根同指 |
| 插件副本 `plugins/vod-devkit/` | 插件包根 | 插件包根 | 插件包根（平铺） | 必须与 `.mcp.json` 的 `args` 路径对齐 |

**入口显式设根**（`paths.py` 只读不猜）：`bin/vod-devkit`、`npm/cli.js`、`server.main()`、
`tests/conftest.py`（仅 `sys.path`）、`scripts/host_matrix.py` 各自设
`VOD_DEVKIT_SRC_ROOT` / `VOD_DEVKIT_DIST_ROOT`；都不可知时 `paths._derive()` 按物理位置
推断一次，旧布局命中给 `DeprecationWarning`。

### 8.2 旧布局回落（只保留一个版本）

`paths.LEGACY_ALLOWED_UNTIL = "0.7.0"`：检测到"包在仓根"（S3 之前的检出）时告警并回落到
单根；版本 ≥ 0.7.0 直接 `RuntimeError`。`tests/test_p2_structure.py` 锁住"该分支只存在于
允许区间"。

### 8.3 生成物与打包边界

- **插件副本** `plugins/vod-devkit/` 拒绝内嵌 `src/`：`vod_mcp/` 直接平铺，由
  `scripts/sync_plugin.py`（`PAIRS` + `EXTRA_PAIRS`）生成，`verify_copies.py` 校验且零提交。
- **载荷** 仍平铺：`vod_mcp/`、`skills/`、`contract/`、`safety/`、`hooks/`
  （`payload.sources`：代码取 `SRC_ROOT`，资产取 `ASSETS`，hook 取其真实位置）。
- **npm files**：`src/vod_mcp/*` 逐文件枚举（防 `runtime.json` 入包），`src/vod_mcp/host_adapters/`
  与 `src/vod_mcp/packs/` 整目录，资产走 `assets/`，hook 走 `integrations/`。
- **运行期状态**：`runtime.json` 不再住在包目录，落 `DIST_ROOT/vod_mcp/runtime.json`
  （gitignore），安装器落盘前建父目录。

### 8.4 pip 入口修正（顺手修掉的存量缺陷）

`pyproject.toml` 的 `[project.scripts]` 原写 `vod-devkit = "bin.vod-devkit"`——不是合法
entry-point，`pip install -e .` 实测 `ValueError: must be python-entrypoint-reference`。
改为 `vodkit_cli.cli:main`；`bin/vod-devkit` 继续作为 npx/脚本入口。wheel 不含 `assets/`，
因此 pip 安装只面向开发/测试，正式分发仍是 npm 载荷与插件副本。

### 8.5 踩过的坑（写下来免得再踩）

1. **`bin/vod-devkit` 在 import 期写 `os.environ` 会污染整场测试**：测试用
   `SourceFileLoader` 加载它取 `PRESETS`，于是"外层仓的根"泄漏进所有子进程，
   "复制仓再跑安装器"的用例把 manifest 写到外层仓（症状：`install-manifest.json` 缺失）。
   改为只在 `__main__` 里设 env。
2. **`tests/conftest.py` 不要设 `PYTHONPATH`**：副本类用例的子进程会 import 到外层仓的包，
   掩盖副本布局问题（实测插件副本探针读到仓内 `assets/`）。仅把 `src/` 插 `sys.path`。
3. **路径替换不能机械**：载荷/插件副本布局是平铺的，`.../src/vod_mcp/server.py` 只在
   "仓内真源"成立；批量替换会同时改坏副本断言（`test_codearts_host`、`test_installer`、
   `host_matrix` 的 dsh 探测）。

