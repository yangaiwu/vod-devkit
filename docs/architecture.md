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

## 二、我们现在的结构（实测，2026-11-15）

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
  hooks/vod_router.py           宿主无关钩子（hermes hooks.pre_llm_call 注册它）
  skills/ contract/ safety/     发布树（生成物，零提交）
  vod_mcp/ build-info.json      运行时副本（生成物，零提交）

src/                           ← 真源（S2 后：资产已在此；S3 再把两个包搬进来）
  skills/ contract/ safety/ hooks/  共享资产（发布/载荷布局仍是根级平铺，见 paths.ASSETS）
  vod_mcp/                       运行时（S3 迁入）
  vodkit_cli/                    安装器 CLI（S3 迁入）

integrations/<host>/host.json  ← 宿主规格（探测/落点/技能目录），不写死在代码里
npm/cli.js  bin/vod-devkit     ← 薄壳：只找解释器、透传参数
dsh/                           ← dsh 壳（独立 npm 包，保持独立）
scripts/                       ← 生成器与校验器成对（sync_plugin ↔ verify_copies，case_roster 等）
tests/                         ← pytest（含结构/范围/用例花名册门禁）
docs/                          ← architecture(本文件) / design / proposal / decisions /
                                 safety-model / hooks / host-realverify / scheme-overview
```

根目录保留的条目（这就是"预算"，见门禁 S129）：

```
src/ plugins/ integrations/ scripts/ tests/ docs/ dsh/ npm/ bin/
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
| S3 | `vod_mcp/ vodkit_cli/` → `src/`，`bin/` 与 `npm/` 只做 `sys.path` 注入 | `bin/vod-devkit`、`npm/cli.js`、`server_entry()`、载荷入口、CI | 高（装机入口路径变了） | 干净检出装 9 宿主 + `version` 输出一致 + 老装机 `doctor` 不误报 |
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
| `skills/`（包内，由 src/packs 生成） | `plugins/vod-devkit/skills/`（由 `src/skills/` 生成） | 生成器唯一入口 + 零提交 |
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
| 仓内直跑（pytest / host_matrix / `bin/vod-devkit` 直接跑） | `<repo>/src` | `<repo>` | 唯一分离形态；`install-manifest.json` / `build-info.json` 在 DIST_ROOT |
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
  ③测试夹具自建临时仓 → 改为同时建 `src/` 与旧布局（验证回落）。

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
