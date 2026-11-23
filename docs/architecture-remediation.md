# 架构缺陷整改方案（P0 → P1 → P2）

> 缺陷台账：[`architecture-defects.md`](architecture-defects.md)（编号一一对应，`ARCH-XX-NN`
> → `ARCH-RM-XX-NN`）。
> 基线：`dev` @ `ba48d9d`（v0.5.44；随台账修订统一重钉）。本文只给方案，不在本 Issue 改代码——**每项按 P 级另开工单**，
> 工单号建议见第六节。

## 零之一、实施偏差（方案 ≠ 落地形态，查代码前先读这一节）

本文件是**方案稿**，落地时有三处按实现约束改了形态（全部在 `D-arch-remediation-1/2` 有记录）：

| 方案里的写法 | 实际落地 | 原因 |
|---|---|---|
| `scripts/install_hooks.sh` | `scripts/install_hooks.py` | 仓内脚本统一 Python（承 `__version__`/路径解析逻辑），shell 只留 `.githooks/pre-push` |
| 新建 `src/vod_mcp/dispatch.py`（`CALL` 批） | 未新建；两面共用逻辑留在 `guards`/`tools` 既有入口 | 实测两面差异只在承载位置（协议强制），拆文件换不来能力 |
| `tests/test_error_codes.py`（`ERR-03` 验收） | 并入 `tests/test_protocol_codes.py` | 错误码常量表与协议保留段同源，合并后一处维护 |
| `src/vod_mcp/packs/collect.py`（单文件） | `src/vod_mcp/packs/collect/`（五模块 + 门面） | `ARCH-CALL-04` 拆包；调用面与私有符号经 `__init__` 再导出保持不变 |

其余编号（`ARCH-RM-*`）的验收用例名与本文件、缺陷台账一致，可直接照名检索。

## 零、整改前置纪律（先读，不然会返工）

1. **先决策再改码**：任何改变既有 `D-*` 结论的整改（例如"更新比较哪个分支""远程面是否
   加鉴权"），必须先在 [`decisions.md`](decisions.md) 追加一条决策，再改代码。本文每一项
   都标了它是否触碰决策。
2. **一竖切片一提交**：一项整改 = 一个分支 + 一次提交（含用例），禁止把 P0 与 P2 混在
   同一提交里——回滚点必须可按项独立。
3. **红→绿纪律**：先写能复现缺陷的用例（在现状上必须红），再改实现。任何"先改后补用例"
   的整改在本仓已复现过"门禁看着绿实际没覆盖"（`scripts/sync_plugin.py:5` 记录的教训）。
4. **回滚点只写"可执行的恢复动作"**：不写"回滚代码"这种废话，要写"删哪个用例/还原哪个
   文件/执行哪条命令能让门禁回到绿"。
5. **每批整改后必须同跑的基线门禁**（第六节 6.3）：少跑一项等于把回归风险交给下一位。

## 一、优先级总表

排序原则：**P0（用户数据/进程可用性）→ P1（门禁与发布口径、运行时健壮性、分层边界）
→ P2（整洁与单点改进）**。同一 P 级内按"依赖关系 + 影响面"排。

### 1.1 P0（2 项，2.0 人日，建议本周内单独热修）

| 编号 | 标题 | 人日 | 触碰决策 | 阻塞其它项 |
|---|---|---|---|---|
| ARCH-ERR-01 | 护栏读取在异常保护外，policy 缺失/损坏打死 server | 1.0 | 否 | 是（ERR-02/ERR-03 的用例要复用它） |
| ARCH-CFG-01 | `pending-feedback.jsonl` 存用户原话未收紧 0600 | 1.0 | 否 | 否 |

### 1.2 P1（18 项，34.0 人日）

| 批次 | 编号 | 标题 | 人日 |
|---|---|---|---|
| **B1 门禁与发布口径**（先做，防后续整改"改了没人守"） | ARCH-BLD-01 | 双 CI 定义漂移 + 只跑 main | 2.0 |
| | ARCH-BLD-02 | dev 基线与 main 口径冲突（release.sh 半步已修） | 1.0 |
| | ARCH-BLD-05 | pre-push 未接线 + 作者机路径 | 1.0 |
| | ARCH-CFG-04 | secret_scan 覆盖边界 | 1.0 |
| | ARCH-BLD-03 | 根 plugin.json 版本漂移 | 1.0 |
| | ARCH-BLD-04 | build-info 快照落后却被当权威 | 1.5 |
| **B2 运行时健壮性** | ARCH-ERR-02 | policy 重读 + 无 schema 校验 | 1.5 |
| | ARCH-ERR-03 | 错误码域混合 | 2.0 |
| | ARCH-ERR-04 | 26 处 `pass` 吞异常 | 3.0 |
| | ARCH-ERR-05 | 可观测性＝/tmp 文本日志 | 3.0 |
| **B3 分层与边界** | ARCH-DEP-02 | host_adapters 急切聚合导入 | 3.0 |
| | ARCH-DEP-04 | 入口设根 + serve 双分派 | 2.0 |
| | ARCH-DEP-05 | 运行期依赖构建脚本 | 1.0 |
| | ARCH-CALL-01 | 两面 tools/call 管线 | 3.0 |
| | ARCH-CALL-02 | instructions 双份 | 1.0 |
| | ARCH-CALL-06 | 引擎可达性两套实现 | 2.0 |
| **B4 暴露面** | ARCH-CFG-02 | 远程面 CORS/Host/鉴权 | 2.0 |
| | ARCH-CFG-03 | 三套原子写 | 2.0 |

### 1.3 P2（12 项，20.5 人日）

| 编号 | 标题 | 人日 | 建议时机 |
|---|---|---|---|
| ARCH-DEP-01 | net ↔ runtime_state 双向依赖 | 2.0 | B3 之后（依赖 errors.py 先落地） |
| ARCH-DEP-03 | 知识层依赖出口层 | 1.5 | 与 DEP-01 同批（共用 errors.py） |
| ARCH-DEP-06 | 路径常量 import 期冻结 | 1.0 | 任意 |
| ARCH-CALL-03 | 哨兵会话 id(manager) | 3.0 | 有远程面改动时一起做 |
| ARCH-CALL-04 | collect pack 拆分 | 4.0 | 采集侧有大需求时再做（收益随改动量增长） |
| ARCH-CALL-05 | 协议版本单源 | 1.0 | 任意 |
| ARCH-ERR-06 | explain 按码归层 | 2.0 | 与 ERR-03 同批 |
| ARCH-CFG-05 | 凭据三入口收敛 | 2.0 | 有认证类需求时 |
| ARCH-CFG-06 | state 目录权限 | 0.5 | 与 CFG-01 同批（同一处写盘） |
| ARCH-CFG-07 | 自由文本字段白名单 | 1.0 | 新增 voices 字段时 |
| ARCH-BLD-06 | files 白名单 | 2.0 | 下次发版前 |
| ARCH-BLD-07 | 版本解析切分 | 0.5 | 与 BLD-03 同批 |

### 1.4 依赖关系（做之前先看这张）

```
errors.py（ERR-03 引入） ──┬─→ DEP-01（破环走 errors，不再 net↔runtime_state）
                          ├─→ DEP-03（ToolError 迁出 net）
                          └─→ ERR-06（explain 由码表派生）

policy 装载收敛（ERR-02） ──→ ERR-01（fail-closed 的落点）

atomic_write 单源（CFG-03） ──┬─→ CFG-01（pending 复用，顺带 0600）
                             └─→ CFG-06（state 目录同批）

CI 门禁收敛（BLD-01） ──→ 其余所有项（新用例才有地方跑） ──→ BLD-02（dev 基线）
```

**结论**：B1 批次先做（否则新用例无处执行）；`errors.py` 是 B2/B3 的公共前置；
`atomic_write` 单源是 CFG 组的前置。

---

## 二、P0 整改（立即处置）

### ARCH-RM-ERR-01 护栏 fail-closed，坏 policy 不再打死 server

- **是否触碰决策**：否（`docs/safety-model.md` 只要求"护栏生效"，未规定"装载失败即不可用"）。
- **实施步骤**：
  1. `src/vod_mcp/policy.py`：`load_policy()` 拆成 `load_policy(strict=True)` 与
     `try_load_policy()`；后者捕获 `OSError`/`json.JSONDecodeError` 并返回
     `_BROKEN_POLICY = {"rules": [], "broken": "<原因>"}`。
  2. `src/vod_mcp/guardrails.py`：`check()` 改用 `try_load_policy()`；当 `broken` 非空时
     返回 `("deny", f"[guard:deny] 护栏规则不可载入（{reason}）——拒绝执行，修复 policy.json 后重启", -32013)`
     （新增码，同时登记进 `diagnose._EXPLAIN_EXTRA`——见 ERR-03 的常量表方案，先手工加一条亦可）。
  3. `src/vod_mcp/server.py`：`handle()` 主体外包一层 `try/except Exception`，返回
     `_error(req_id, -32603, "内部错误（已记录日志）")` 并 `runtime_state._log` 落上下文；
     注意**不要**吞掉 `KeyboardInterrupt`/`SystemExit`。
  4. 同步 `src/vod_mcp/remote_app.py` 的 `on_call_tool`（它已有 try，但要覆盖 `guardrails.check`
     这一步——目前 `:161` 在 `try` 之外）。
  5. `src/vod_mcp/diagnose.py`：新增 `-32013` 条目（层=配置，动作=修复 policy 后重启宿主）。
- **影响文件**：`src/vod_mcp/policy.py`、`src/vod_mcp/guardrails.py`、`src/vod_mcp/server.py`、
  `src/vod_mcp/remote_app.py`、`src/vod_mcp/diagnose.py`、`tests/test_policy_load.py`（新）。
- **回归用例**：
  - `tests/test_policy_load.py::test_corrupt_policy_denies_instead_of_crashing`
  - `tests/test_policy_load.py::test_missing_policy_denies_with_actionable_message`
  - `tests/test_remote_guards.py::test_http_face_policy_broken_returns_is_error`
  - `tests/test_explain_codes.py::test_s154_every_raised_code_is_explained`（新码必须进表）
- **回滚点**：还原五个文件的本次改动 + 删除 `tests/test_policy_load.py`；门禁回到
  "坏 policy 崩" 的旧行为（红→绿对照可在提交说明里附上复现命令）。
- **验收断言**：坏/缺 policy 下 `tools/call` 返回 `deny` 与 `-32013`，**进程不退出**；
  日志里有一行含 `policy` 与文件路径。

### ARCH-RM-CFG-01 pending 文件私有化

- **是否触碰决策**：否（`D-pending-1` 只定"补交队列的存在"，未定权限）。
- **实施步骤**：
  1. `src/vod_mcp/pending.py`：`append_entry()` / `save_entries()` 改调
     `paths.atomic_write_text(path, mode=0o600)`（追加语义改为"读→追加→原子写"，
     或保留追加但补 `os.chmod(path, 0o600)` + 写后 `stat` 回验）。
  2. 新增 `_ensure_private(path)`：存在且权限比 0600 宽时收紧，`OSError` 只告警不阻断
     （WSL/drvfs 会静默忽略 chmod，与本仓 `runtime_state._verify_perms` 同口径）。
  3. `src/vod_mcp/pending.py` 的 `default_path()` 不变（路径稳定，避免迁移）。
- **影响文件**：`src/vod_mcp/pending.py`、`tests/test_pending_feedback.py`。
- **回归用例**：
  - `tests/test_pending_feedback.py::test_pending_file_is_private`（append/save/旧文件收紧三条路径）
  - `tests/test_pending_feedback.py::test_chmod_ignored_warns_not_raises`
- **回滚点**：还原 `pending.py` 两处写实现；权限断言用例删除即可回到旧行为。
- **验收断言**：三条写路径后 `stat.S_IMODE(...) == 0o600`；旧 0644 文件被收紧。

---

## 三、P1 整改

### 批次 B1：门禁与发布口径（先做）

#### ARCH-RM-BLD-01 门禁单源 + 触发分支补齐

- **是否触碰决策**：否。
- **实施步骤**：
  1. 新建 `scripts/gate_all.py`：把 `.github/workflows/ci.yml:22-51` 的 9 条门禁
     收敛成子命令（`copies / lint / secret / roster / rules / mypy / registry / pytest /
     packaging / dsh`），每步失败即非零退出。
  2. `.github/workflows/ci.yml` 与 `.gitcode/workflows/ci.yml` 都只调用
     `python3 scripts/gate_all.py --all`（GitCode 侧保留 `repo_workspace` 的目录定位段，
     但定位失败必须红——`:20-26` 的教训不要退回）。
  3. 两份 workflow 的 `branches` 都补 `dev`（`on.push.branches: ["main","dev"]`、
     `pull_request.branches` 同）。
  4. 新增用例：解析两份 yaml，比较 step 名集合。
- **影响文件**：`scripts/gate_all.py`（新）、`.github/workflows/ci.yml`、
  `.gitcode/workflows/ci.yml`、`tests/test_release_and_pack_paths.py`。
- **回归用例**：
  - `tests/test_release_and_pack_paths.py::test_both_ci_definitions_run_same_gates`
  - `tests/test_release_and_pack_paths.py::test_ci_triggers_cover_dev_branch`
  - 手动：`python3 scripts/gate_all.py --all` 本地全绿
- **回滚点**：两份 workflow 还原到各自内联 step；`gate_all.py` 删除；用例删除。
  回滚后门禁覆盖面退回 GitCode 4 条（即现状），不影响运行时代码。
- **验收断言**：两份 workflow 的 step 名集合相等；`dev` 分支的 push 会触发。

#### ARCH-RM-BLD-02 更新/夹具改用当前分支口径（release.sh 半步已落地）

> 注：dev 头 `95217f1` 已先行落地 release 侧半步（`scripts/release.sh:170-176` 改为推
> 当前分支 `CUR_BRANCH`），本项收敛为 update 语义与测试夹具两件事。

- **是否触碰决策**：**是**——`tests/test_installer.py:120-125` 的注释把"比较 origin/main"
  当作语义锁。整改前先向 [`decisions.md`](decisions.md) 追加一条
  `D-update-branch-1`：**"update 比较当前分支的上游；无上游时回落 `origin/<当前分支>`，
  缺失则报可执行错误而不是尝试 pull"**。
- **实施步骤**：
  1. `src/vodkit_cli/update.py`：`origin/main` → `@{upstream}`（`git rev-parse
     --abbrev-ref --symbolic-full-name @{upstream}`）；无上游时用
     `origin/<current>`；两者都拿不到 → 打印"当前分支没有上游，无法判断更新"并 `return`
     （不 `exit 1`，那是误报）。
  2. `tests/test_installer.py:125`：`--branch main` → `--branch <当前分支>`
     （用 `git rev-parse --abbrev-ref HEAD` 传参）。
  3. `tests/test_p2_structure.py` 的 update 语义锁同步改口径。
- **影响文件**：`src/vodkit_cli/update.py`、`tests/test_installer.py`、
  `tests/test_p2_structure.py`、`docs/decisions.md`（新增决策）。
- **回归用例**：
  - `tests/test_p2_structure.py::test_update_compares_current_upstream`
  - `tests/test_installer.py`（在无 `main` 引用的检出上不再 ERROR）
  - `tests/test_installer.py::test_update_refuses_when_tracked_conflict`（保持）
- **回滚点**：还原 `update.py:29-42`、两个用例；`decisions.md`
  的那条决策**不要删**，改为标注"已撤回（原因）"——决策台账按追加制。
- **验收断言**：在 `feat/*`/`dev` 分支上 `vod-devkit update` 不再报"更新失败"；
  `python3 -m pytest tests/test_installer.py -q` 在无 `main` 的检出上是绿。

#### ARCH-RM-BLD-05 pre-push 接线脚本化

- **实施步骤**：
  1. 新增 `scripts/install_hooks.sh`：`git config core.hooksPath .githooks`（幂等，打印当前值）。
  2. `.githooks/pre-push:3-5`：`PY` 改 `command -v python3`（保留 `VOD_SYNTAX_PY` 风格的可选覆盖），
     删除 `/root/.hermes/**`；`:15` 日志改 `"${TMPDIR:-/tmp}/prepush-dsh.log"`。
  3. `CONTRIBUTING.md:31` 改成"新克隆先跑 `bash scripts/install_hooks.sh`"。
  4. 补用例：脚本幂等（跑两次结果相同）、脚本内无作者机绝对路径。
- **影响文件**：`scripts/install_hooks.sh`（新）、`.githooks/pre-push`、`CONTRIBUTING.md`、
  `tests/test_release_and_pack_paths.py`。
- **回归用例**：`::test_hook_install_script_is_idempotent`、`::test_pre_push_has_no_author_paths`。
- **回滚点**：删脚本、还原 CONTRIBUTING 措辞与 `pre-push` 头部；门禁回到"需手工接线"。
- **验收断言**：新克隆 `bash scripts/install_hooks.sh` 后 `git config --get core.hooksPath`
  = `.githooks`；`pre-push` 在无 `/root/.hermes` 的机器上跑通。

#### ARCH-RM-CFG-04 secret_scan 扫描面扩到生成物

- **实施步骤**：
  1. `scripts/secret_scan.py:37-39`：`tracked_files()` 加 `timeout=30`；`returncode != 0` 或
     `stdout is None` → 打印 warn 并降级为"文件系统扫描"（跳过 `.git`/`__pycache__`）。
  2. 扫描面 = tracked ∪ (`plugins/**`、`assets/**`、载荷目录（存在时）)。
  3. 模式表补：`.env` 形态、`"java_key": "<16+ 非空>"`、通用 `[A-Fa-f0-9]{32,}`（只在
     `key/token/secret` 同行为真时命中，避免 sha256 误报）。
  4. 用例：副本目录放形似 key 的串必须命中；无 git 时降级不崩。
- **影响文件**：`scripts/secret_scan.py`、`tests/test_secret_scan.py`。
- **回归用例**：`::test_scans_generated_copies_too`、`::test_git_unavailable_degrades_without_crash`。
- **回滚点**：还原扫描面与模式表；新增两条用例删除。
- **验收断言**：`plugins/vod-devkit/` 内的假 key 被报出；非 git 目录下退出码为 1（因为命中）
  或 0（干净），**不是**异常退出。

#### ARCH-RM-BLD-03 版本落点补根 `plugin.json`

- **实施步骤**：
  1. `scripts/release.sh:97-101` 的 `EXTRA_FILES` 加 `("plugin.json", "json")`。
  2. `scripts/release.sh:143-146` 的 `git add` 清单加 `plugin.json`。
  3. 把当前值从 `0.1.0` 修正为当前包版本（一次提交，单独说明"补历史漂移"）。
  4. 用例：扫描仓内所有清单文件（`package.json`、`pyproject.toml`、`plugin.json`、
     `.codex-plugin/plugin.json`、`packages/dsh/package.json`、`build-info.json`、
     `assets/contract/tools.schema.json`）断言版本相等；断言 `EXTRA_FILES` 覆盖全部清单。
- **影响文件**：`scripts/release.sh`、`plugin.json`、`tests/test_release_and_pack_paths.py`。
- **回归用例**：`::test_all_manifest_versions_agree`、`::test_release_bump_table_covers_every_manifest`。
- **回滚点**：还原 `release.sh` 两处清单（版本值本身不回滚——回滚会重新制造不一致）。
- **验收断言**：七个落点全等于 `src/vod_mcp/__init__.py:8` 的版本。

#### ARCH-RM-BLD-04 build-info 快照来源可辨

- **实施步骤**：
  1. `scripts/sync_plugin.py:83-85` 的 `bi` 增加 `"snapshot": "released"|"worktree"`
     （判据：`git describe --tags --exact-match HEAD` 成功 → released，否则 worktree）。
  2. `src/vodkit_cli/common.py:305-321`（`_write_install_manifest`）：除 `commitSha` 外
     记录 `worktreeHead`（安装时 `git rev-parse HEAD`；无 `.git` 时为 None）。
  3. `src/vodkit_cli/doctor.py:179-207`（`_provenance_problem`）：当 `snapshot == "worktree"`
     且 `worktreeHead != commitSha` 时给"提示"而不是 FAIL（这是开发态的正常形态）。
  4. `src/vod_mcp/provenance.py:49-65`（`info_payload`）：多返回 `snapshot` 字段。
- **影响文件**：`scripts/sync_plugin.py`、`src/vodkit_cli/common.py`、`src/vodkit_cli/doctor.py`、
  `src/vod_mcp/provenance.py`、`tests/test_info_binding.py`、`tests/test_distribution.py`。
- **回归用例**：`tests/test_info_binding.py::test_install_manifest_records_worktree_head_when_snapshot_lags`。
- **回滚点**：还原四处字段与提示；新增用例删除。已落盘的旧 manifest 无需迁移（缺字段
  按"未知"处理）。
- **验收断言**：非发版提交上安装后，`install-manifest.source` 同时有 `commitSha` 与
  `worktreeHead`，`doctor` 不把差异判成 FAIL。

### 批次 B2：运行时健壮性

#### ARCH-RM-ERR-02 policy 装载：缓存 + schema 校验

- **实施步骤**：
  1. `src/vod_mcp/policy.py`：新增 `_CACHE = {"sig": None, "policy": None}`；sig =
     `(path, mtime_ns, size)`；命中即复用（与 `transport_remote.payload_problems` 的
     TTL 缓存同思路，但用文件指纹而非时间，避免"改完等 30 秒"）。
  2. `_validate(policy)`：`rules` 必须是 list；每条必须有 `id`/`severity`
     （∈{deny,confirm}）/`match`（含 `tool` 或 `field`）/`message`；`field:"text"` 必须
     有 `regex` 且可编译。违规 → 抛 `PolicyInvalid(rule_id, field, reason)`。
  3. `guardrails.check` 把 `PolicyInvalid` 映射成 `deny` + 可读消息（复用 ERR-01 的 fail-closed 路）。
  4. 版本对账：`assets/safety/policy.json:2` 的 `version` 与 `assets/contract/tools.schema.json`
     的 `version` 不必相同，但必须显式声明两者关系（在文件里加注释字段或 doctor 检查项）。
- **影响文件**：`src/vod_mcp/policy.py`、`src/vod_mcp/guardrails.py`、`assets/safety/policy.json`、
  `tests/test_policy_load.py`。
- **回归用例**：`::test_rule_schema_violation_names_rule_id`、
  `::test_policy_read_is_cached_until_mtime_changes`、
  `::test_regex_is_compiled_at_load`.
- **回滚点**：删缓存与校验函数，`load_policy` 回到每次直读；三条用例删除。
- **验收断言**：同一次 `tools/call` 序列内 `open()` 只发生 1 次（用 `mock_open` 计数）；
  删字段时报错含 `rule.id`。

#### ARCH-RM-ERR-03 错误码单一真源 `errors.py`

- **是否触碰决策**：是（错误码段位是产品对外契约，须在 `docs/design.md` 记一条
  `D-error-codes-1`：**-32xxx 为产品语义段；上游 4xx/5xx 一律映射到 -3202x 段；
  -3260x 保留给 JSON-RPC 协议语义**）。
- **实施步骤**：
  1. 新建 `src/vod_mcp/errors.py`：
     ```
     PROTOCOL = {UNKNOWN_METHOD: -32601, INVALID_PARAMS: -32602, INTERNAL: -32603}
     PRODUCT  = {NO_PRODUCT: -32010, NEED_CONFIRM: -32011, AUTH: -32012,
                 POLICY_BROKEN: -32013, TRANSPORT: -32014, PACK_REFUSED: -32015,
                 NOT_DEPLOYED: -32016, NET_UNREACHABLE: -32001}
     UPSTREAM = {"4xx": -32020, "429": -32021, "5xx": -32022}
     def from_http(status: int) -> int: ...
     ```
     并把 `ToolError` 迁到这里（为 DEP-01/DEP-03 铺路，`net.ToolError` 保留别名一个版本）。
  2. 替换全部 raise 点（附录 A 的文件清单）为常量引用；`src/vod_mcp/net.py:209` 改
     `code=from_http(e.code)`，消息仍保留原始 `上游返回 <status>: <detail>`（人可读性不变）。
  3. `diagnose._EXPLAIN_EXTRA` 由 `PRODUCT` 表派生（码 → 层/原因/动作），保留文案正则
     作兜底（ERR-06）。
  4. 门禁改写：`tests/test_explain_codes.py` 的扫描从 `code\s*=-320\d\d` 改为
     "所有 `ToolError(` 调用的 `code=` 实参 ⊆ 常量表取值或 `from_http(` 调用"。
  5. `tests/test_error_codes.py`（新）：断言 `from_http` 对 400/401/429/500/503 的映射。
- **影响文件**：`src/vod_mcp/errors.py`（新）、`src/vod_mcp/net.py`、`src/vod_mcp/packs/*.py`、
  `src/vod_mcp/tools.py`、`src/vod_mcp/diagnose.py`、`tests/test_explain_codes.py`。
- **回归用例**：`::test_all_error_codes_come_from_table`、`::test_from_http_mapping`、
  既有 `tests/test_s238_no_legacy_fallback.py`（-32016 语义不得变）。
- **回滚点**：`errors.py` 保留但 raise 点回退到字面量；门禁改回旧正则。注意 `-32020..22`
  一旦对外发布就不能复用给别的语义。
- **验收断言**：源码内除 `errors.py` 外无裸数字 `code=`；宿主收到的 code 全部落在
  `-32xxx` 段。

#### ARCH-RM-ERR-04 吞异常收窄 + 必留痕

- **实施步骤**：
  1. 新建 `src/vod_mcp/errors.py` 的辅助函数（或 `runtime_state.tolerant()` 上下文管理器）：
     ```
     with rt.tolerant("consume_payload_marker", swallow=(OSError, ValueError)):
         ...
     ```
     语义 = 捕获白名单异常 + 必写一行 `_log("suppress <where>: <exc>")`；白名单外照常上抛。
  2. 逐条替换 26 处 `except` 体仅 `pass` 的吞点（清单由 `ast` 脚本产出，见缺陷台账
     附录 10.1；主链样例见 ERR-04 表格）。重点：
     - `src/vod_mcp/server.py:119`（载荷标记）：吞 + 记日志 + **在 tools/list 响应里带一个 `payloadMarker` 提示**
       （可选，若判定会改变对外契约则只记日志）。
     - `src/vod_mcp/runtime_state.py:210`（日志自身失败）：改为 stderr 兜底一次
       （`print(..., file=sys.stderr)`），否则排障真源失效无痕迹。
     - `src/vod_mcp/net.py:325`（领令牌失败）：把 `ToolError` 的 message/reason 记进日志，
       调用方的 `-32012` 保持。
  3. 新建结构用例：`tests/test_error_trace.py`——AST 扫描 `src/` 内 `except` 处理器，
     断言"裸 `pass`" 只出现在白名单（白名单写成 `(file, lineno)` 之外更稳：断言
     `pass` 前必须有 `_log(`/`warn(`/`tolerant(`）。
  4. 对每个吞点补"注入异常 → 断言日志有一行"的行为用例（选 5 个主链点即可，其余由
     结构用例兜）。
- **影响文件**：`src/vod_mcp/server.py`、`src/vod_mcp/net.py`、`src/vod_mcp/runtime_state.py`、
  `src/vod_mcp/payload.py`、`src/vod_mcp/host_adapters/codex.py`、`tests/test_error_trace.py`（新）。
- **回归用例**：`::test_no_bare_except_pass`、`::test_swallowed_paths_leave_a_log_line`。
- **回滚点**：结构用例删除 + `pass` 处还原；注意**不要**回滚 `src/vod_mcp/runtime_state.py:210` 的
  stderr 兜底（那一条属于纯收益）。
- **验收断言**：AST 用例绿；`runtime.json` 被写坏时日志里能搜到 `runtime.json` 与原因。

#### ARCH-RM-ERR-05 结构化日志

- **实施步骤**：
  1. `src/vod_mcp/runtime_state.py`：
     ```
     def _log(event: str, level: str = "info", **fields) -> None
     ```
     行格式 = `{"ts":…, "level":…, "event":…, **fields}`（JSONL，`ensure_ascii=False`）；
     落点 = `VOD_DEVKIT_LOG` env > `machine_state_home()/logs/server.jsonl`；
     目录 0700、文件 0600；追加写加 `fcntl.flock`（复用 `_file_lock` 同套路）；
     轮转改"按大小改名"（`os.replace` 到 `.1`），不做"读全文再写回"。
  2. `src/vod_mcp/server.py:155`：启动事件带 `pid/argv/packs/distribution/cwd`；
     `tools/call` 前后各一行：`tool`, `client`（scope 的 `id_source`）, `duration_ms`, `code`。
  3. `src/vod_mcp/net.py:188`：`_http` 改 `_log("http", level="debug", method=…, path=…,
     has_key=…, status=…, duration_ms=…)`（状态码在异常路径补记）。
  4. `src/vod_mcp/transport_remote.py:436`：`log_message` 改为落 `http_request` 事件
     （method/path/status/duration），不再静默。
  5. `_warn()` 保留为 `_log(..., level="warn")` 的别名（调用点不用改）。
- **影响文件**：`src/vod_mcp/runtime_state.py`、`src/vod_mcp/server.py`、`src/vod_mcp/net.py`、
  `src/vod_mcp/transport_remote.py`、`tests/test_observability.py`（新）。
- **回归用例**：`::test_log_lines_are_structured_and_carry_tool_context`、
  `::test_log_path_is_configurable_and_creates_private_dir`、
  `::test_rotations_do_not_lose_concurrent_writes`（两个线程各写 200 行，断言 400 行都在）。
- **回滚点**：还原 `_log` 签名与四个调用点；日志格式回退到纯文本（旧日志文件不需迁移，
  `doctor` 不解析日志）。
- **验收断言**：`tools/call` 后日志里有 `{"event":"tool_call", "tool":…, "code":…, "duration_ms":…}`；
  `VOD_DEVKIT_LOG` 生效；并发写不丢行。

### 批次 B3：分层与边界

#### ARCH-RM-DEP-02 host_adapters 惰性注册

- **实施步骤**：
  1. `src/vod_mcp/host_adapters/__init__.py`：`REGISTRY` 改 `{name: "module"}` 字符串表；
     `get(target)` 用 `importlib.import_module(f"vod_mcp.host_adapters.{mod}")` 并缓存；
     `modules()` 改为"按需返回已加载的"。
  2. 现有调用点适配：`src/vodkit_cli/common.py:27`（`host_specs.load("hermes")` 与适配器无关，
     不受影响）、`install.py`/`doctor.py`/`packs_cmd.py`/`uninstall.py` 的 `host_adapters.get(...)`
     语义不变。
  3. 新增载荷形态门禁：在载荷副本（不含 `integrations/`）里 import 任一适配器必须
     快速失败且给出可读原因，而不是 KeyError→500。
- **影响文件**：`src/vod_mcp/host_adapters/__init__.py`、`src/vod_mcp/host_adapters/*.py`（按需）、
  `tests/test_host_adapters.py`、`tests/test_payload.py`。
- **回归用例**：`::test_registry_is_lazy`、`tests/test_payload.py::test_payload_face_cannot_import_host_adapters`、
  既有 `tests/test_new_hosts.py`、`tests/test_host_matrix.py` 全绿。
- **回滚点**：还原 `__init__.py` 为急切导入；两条新用例删除。
- **验收断言**：`import vod_mcp.host_adapters` 后 `sys.modules` 无子模块；`get("dsh")` 后才加载 `dsh`。

#### ARCH-RM-DEP-04 入口设根单源

- **实施步骤**：
  1. 删除 `src/vodkit_cli/cli.py:13-22` 的前置 `serve` 分支（`:117-131` 的子命令已覆盖，
     `nargs=argparse.REMAINDER` 保证参数透传）。
  2. `src/vodkit_cli/cli.py:125` 的 `common.ROOT / "vod_mcp" / "server.py"` → `paths.SRC_ROOT / "vod_mcp" / "server.py"`
     （与前置分支同源，仓内/载荷/插件三形态一致）。
  3. `npm/cli.js:42`：`VOD_DEVKIT_SRC_ROOT`/`VOD_DEVKIT_DIST_ROOT` 改 `setdefault` 语义
     （用 `env: {...process.env}` 之后只在缺失时补），并在不一致时 stderr 告警
     （与 `bin/vod-devkit:35-40` 同口径）。
  4. `src/vod_mcp/paths.py:8` 的设置点清单补 `src/vodkit_cli/cli.py`。
  5. 用例：两种形态（仓内/插件副本）下 `serve` 解析出的脚本路径一致且存在。
- **影响文件**：`src/vodkit_cli/cli.py`、`npm/cli.js`、`src/vod_mcp/paths.py`、`tests/test_p2_structure.py`。
- **回归用例**：`::test_serve_entry_resolves_single_root`、`tests/test_package tests 的 serve 用例`
  （`tests/test_remote_attach.py` 的 `serve --transport remote` 路径）、`tests/test_mcp_manifest_a3.py`。
- **回滚点**：恢复前置分支与 `common.ROOT` 用法、`npm/cli.js` 覆盖语义；用例删除。
  回滚后"npx 形态 serve 可能找不到脚本"的老风险回来。
- **验收断言**：`vod-devkit serve --help` 与 `vod-devkit serve --transport remote --port 0` 在
  插件副本目录下都能起；`paths.describe()['srcRoot']` 与 execve 目标同源。

#### ARCH-RM-DEP-05 去运行期构建依赖

- **实施步骤**：
  1. `src/vod_mcp/host_adapters/codex.py:288-299`：删除 `subprocess.run(sync_plugin.py)`；
     改为"副本缺失 → 抛出 `InstallPrecondition`（新异常）"，由 `install.cmd_install`
     统一捕获并打印**可执行**提示（"请先 `npm install` 或重跑安装器；仓内开发态执行
     `python3 scripts/sync_plugin.py`"）。
  2. 若判定"copies 必须随包分发"，替代方案是把 `sync_plugin.py` 纳入 `payload.OWNED`
     与 `package.json.files`——两者选一，按"发布物自包含"原则建议选前者（不加脚本）。
  3. 前置校验前置到 `install` 的 preflight（`src/vodkit_cli/install.py` 的 `_install_many` 之前），
     让失败发生在写任何配置之前。
- **影响文件**：`src/vod_mcp/host_adapters/codex.py`、`src/vodkit_cli/install.py`、
  `tests/test_installer.py`。
- **回归用例**：`::test_codex_install_without_repo_never_shells_out`、
  `::test_codex_install_precondition_message_is_actionable`、既有 `tests/test_installer.py`
  的 codex 原生插件用例全绿。
- **回滚点**：恢复子进程调用与 `sys.exit(2)`；用例删除。
- **验收断言**：桩掉 `subprocess.run` 后 codex 安装路径无 `sync_plugin.py` 调用；
  失败文案含"npm install / 重跑安装器"关键词。

#### ARCH-RM-CALL-01 两面共用 `call_tool`

- **实施步骤**：
  1. 新建 `src/vod_mcp/dispatch.py`：
     ```
     @dataclass
     class Result: verdict: str; code: int | None; message: str; payload: dict | None
     def call_tool(name, args, client_info) -> Result   # 护栏 → dispatch → 统一错误映射
     ```
     内部捕获 `ToolError`（→ Result.code/message）与未预期异常（→ INTERNAL）。
  2. `src/vod_mcp/server.py:87-108`：改为调 `dispatch.call_tool`，只保留"Result → JSON-RPC
     信封"的适配（`verdict=="deny"` → `_error`，`payload` → `result`）。
  3. `src/vod_mcp/remote_app.py:152-175`：改为调 `dispatch.call_tool`，只保留"Result →
     `CallToolResult`"的适配。
  4. `REMOTE_WITHHELD` 的拒绝分支下沉进 `dispatch`（`remote` 标志作为参数），两面行为一致。
  5. 明确"协议承载位置不同"这一不可消除差异，并在 `docs/design.md` 记一条：
     **同码不同承载是设计事实，不是缺陷**——但**码与消息必须同源**。
- **影响文件**：`src/vod_mcp/dispatch.py`（新）、`src/vod_mcp/server.py`、`src/vod_mcp/remote_app.py`、
  `docs/design.md`、`tests/test_remote_guards.py`、`tests/test_packs_configure.py`。
- **回归用例**：`tests/test_remote_guards.py::test_two_faces_report_same_code_for_same_error`、
  `::test_withheld_tool_rejected_both_faces`、既有 `tests/test_mcp_standard_transport.py`、
  `tests/test_two_phase.py` 全绿。
- **回滚点**：两面恢复各自管线；`dispatch.py` 删除。风险：`notifications/tools/list_changed`
  的触发点在 `src/vod_mcp/server.py:104`，回滚时注意保留。
- **验收断言**：同一入参两面 `code` 相同；`tests/test_skeleton.py` 的工具清单断言不变。

#### ARCH-RM-CALL-02 instructions 单源

- **实施步骤**：
  1. 新建 `src/vod_mcp/instructions.py`：`COLLECT_DISCIPLINE`（同意/逐字转述/产品追问三段，
     与 `server.py:60-75` 现有文本逐字一致）+ `stdio_instructions()` / `remote_instructions()`
     （各自拼形态尾句）。
  2. `src/vod_mcp/server.py:60` 与 `src/vod_mcp/remote_app.py:29` 改为引用；删除重复字面量。
  3. 门禁：两面都 `startswith(COLLECT_DISCIPLINE)`；保留现有 `test_structure_guards.py:177/200`
     的关键词断言（它们锁的是"设计口径"，与单源不冲突）。
- **影响文件**：`src/vod_mcp/instructions.py`（新）、`src/vod_mcp/server.py`、
  `src/vod_mcp/remote_app.py`、`tests/test_structure_guards.py`。
- **回归用例**：`::test_both_faces_share_collect_discipline`、`tests/test_consent_wording.py`
  （归因口径不得退回安装绑定）、`tests/test_remote_transport.py:103`（远程面不暴露本机路径）。
- **回滚点**：恢复两处内联文本；新用例删除。
- **验收断言**：`grep -c "征得用户明确同意" src/` 只命中 `instructions.py` 一处。

#### ARCH-RM-CALL-06 引擎探活单源

- **实施步骤**：
  1. `src/vod_mcp/net.py`：抽出 `probe_reachable(base, key=None, timeout=4.0)`，
     `probe_key` 复用它；URL 路径仍取 `_META_PATH`。
  2. `src/vodkit_cli/doctor.py:347-358`：删除手抄 URL 与 urllib 逻辑，改调
     `net.probe_reachable`（无 key 形态），只保留"层/动作"的展示映射。
  3. 明确三态→五态的展示口径：`unreachable` → warn（离线可忽略）；`rejected` → FAIL；
     `device-mismatch` → 提示重领（不 FAIL）。
- **影响文件**：`src/vod_mcp/net.py`、`src/vodkit_cli/doctor.py`、`tests/test_doctor_egress.py`。
- **回归用例**：`::test_doctor_probe_uses_net_semantics`、既有
  `tests/test_doctor_repair_boundaries.py`、`tests/test_state_read.py` 全绿。
- **回滚点**：恢复 `_probe_engine` 独立实现；新用例删除。
- **验收断言**：`grep -c "external/meta" src/` = 1（只在 `net.py`）。

### 批次 B4：暴露面

#### ARCH-RM-CFG-02 远程面收紧

- **是否触碰决策**：是——`D-token-machine-1` 只定"代领开关"，未定 Origin/Host 校验。
  追加 `D-remote-origin-1`：**默认只接受回环 Origin/Host；非回环须显式白名单**。
- **实施步骤**：
  1. `transport_remote.py:_cors()`：`Access-Control-Allow-Origin` 只回显白名单内的
     Origin（回环默认 `http://127.0.0.1`/`http://localhost` + 任意端口）；不在白名单 →
     不发 CORS 头（浏览器自然拦），且 `do_POST` 直接 403 带原因。
  2. `do_POST` 前置：校验 `Host` 头 ∈ 白名单（默认 `127.0.0.1[:port]`、`localhost[:port]`、
     `[::1][:port]`）；不符 → 403 + `_log("http", level="warn", event="host_rejected")`。
  3. 新增 `--allow-origin <origin>`（可多次）与 `--allow-host <host>`；非回环绑定下二者
     缺一即拒绝启动（比现状"告警后照跑"硬）。
  4. `INSTALL.md`/`docs/architecture.md` 的远程形态说明同步（**不改**结构契约结论，只补
     安全参数）。
- **影响文件**：`src/vod_mcp/transport_remote.py`、`INSTALL.md`、`docs/decisions.md`、
  `tests/test_remote_transport.py`、`tests/test_remote_attach.py`。
- **回归用例**：`::test_foreign_origin_is_rejected`、`::test_dns_rebinding_host_header_is_rejected`、
  `::test_loopback_origin_still_works`、既有 `tests/test_mcp_standard_transport.py` 全绿。
- **回滚点**：删除 Origin/Host 校验与两个新参数，恢复无条件 `*`。回滚会重新打开
  "网页可驱动本机端点"的风险面，须在提交说明里显式记录。
- **验收断言**：`Origin: https://evil.example` → 403；`Host: evil.example` → 403；
  `Origin: http://127.0.0.1:3000` → 正常 200。

#### ARCH-RM-CFG-03 原子写单源

- **实施步骤**：
  1. `src/vod_mcp/runtime_state.py:137-145`：`_write_cfg_unlocked` 删除，改
     `paths.atomic_write_text(p, json.dumps(cfg, …), mode=0o600)`。
  2. `src/vod_mcp/pending.py:108-117`：`save_entries` 改调 `paths.atomic_write_text(path,
     text, mode=0o600)`（与 CFG-01 同一提交做最省）。
  3. 保留 `_verify_perms` 写后回验（`runtime_state.py:148-159`），它验的是"效果"。
  4. 结构用例：`grep`/AST 断言"仓内只有 `paths.atomic_write_text` 一处 `os.replace("
     （白名单：`scripts/`、测试夹具）。
- **影响文件**：`src/vod_mcp/runtime_state.py`、`src/vod_mcp/pending.py`、`tests/test_runtime_atomic.py`。
- **回归用例**：`::test_single_atomic_writer`、既有 `tests/test_runtime_atomic.py`
  的跨进程用例（`test_runtime_atomic.py:26-75` 的 4 进程并发）全绿、
  `tests/test_pending_feedback.py` 全绿。
- **回滚点**：恢复两处私有实现；结构用例删除。
- **验收断言**：`runtime.json` 在只读目标上抛 `PermissionError`（与 `src/vod_mcp/paths.py:240` 一致）；
  掉电注入（`os.replace` 前杀进程）后文件不存在或完整，不出现半截 JSON。

---

## 四、P2 整改（按建议时机）

> P2 项的步骤粒度与 P1 一致（都要用例 + 回滚点），但允许"随相关模块改动顺带做"。
> 下面每项给出**最小可交付形态**。

| 编号 | 实施步骤（最小形态） | 影响文件 | 回归用例 | 回滚点 | 人日 |
|---|---|---|---|---|---|
| ARCH-RM-DEP-01 | ①`runtime_state._is_remote_face` 改为读模块内注入的标志 `_SERVER_FACE_LOCAL`；②`transport_remote` 在协程体里同时 set `net._SERVER_FACE` 与 `rt.set_server_face(True)`；③删掉 `src/vod_mcp/runtime_state.py:438` 的反向 import | `runtime_state.py`、`transport_remote.py`、`net.py` | `tests/test_import_graph.py::test_no_cycle_in_vod_mcp`、`tests/test_remote_transport.py` 全绿 | 恢复反向懒导入；新用例删除 | 2.0 |
| ARCH-RM-DEP-03 | ①`errors.py`（ERR-03 引入）承载 `ToolError`；②`net.ToolError = ToolError` 保留别名一个版本；③`src/vod_mcp/packs/knowledge.py:2` 改 `from vod_mcp import errors`；④`src/vod_mcp/skills_registry.py:67` 改读 `rt` 的标志（与 DEP-01 同源） | `errors.py`、`net.py`、`packs/*.py`、`skills_registry.py` | `::test_packs_do_not_import_net_for_errors` | 恢复 `net.ToolError` 与两处 import | 1.5 |
| ARCH-RM-DEP-06 | `provenance.py:6-8` 与 `src/vod_mcp/payload.py:28` 的常量改函数 `build_info_path()`/`manifest_path()`/`dist_root()`；调用点改函数调用 | `provenance.py`、`payload.py`、`common.py` | `tests/test_state_read.py::test_provenance_paths_are_live` | 恢复常量；用例删除 | 1.0 |
| ARCH-RM-CALL-03 | ①`_SENTINEL` 改 `weakref.WeakKeyDictionary`（键=manager 实例）；②`_sentinel_ttl` 从 `SCOPE_TTL_SEC` 派生改为显式常量 `SENTINEL_FRESH_SEC`；③补"manager 重建"用例 | `transport_remote.py`、`runtime_state.py`、`tests/test_remote_transport.py` | `::test_sentinel_survives_manager_rebuild` | 恢复 dict + `id(manager)` | 3.0 |
| ARCH-RM-CALL-04 | ①`packs/collect/` 拆 `validate.py`（`_collect_voice_items`/`_filter_tags`/`_allowed_tags`）、`attribution.py`（`_attribute_product`/`_require_product_or_ask`/`_attach_attribution`）、`submit.py`（`submit_voices`/`_hoard_voice`/`_echo_plan`）、`two_phase.py`（`draft_voices`/`commit_voices`/`_draft_owner`）、`pending.py`（`_flush_pending`）；②`collect/__init__.py` 只做入口装配（≤120 行） | `src/vod_mcp/packs/collect/**`、`tools.py`（不变）、`packs/__init__.py`（不变） | `tests/test_two_phase.py`、`tests/test_pending_feedback.py`、`tests/test_collect_qualify.py`、`tests/test_skeleton.py` 零改动全绿 | 恢复单文件 `collect.py`；`__init__` 删除 | 4.0 |
| ARCH-RM-CALL-05 | 新建 `src/vod_mcp/protocol.py::PROTOCOL_VERSION`；`src/vod_mcp/server.py:32`、`src/vodkit_cli/remote.py:52` 引用；SDK 侧通过 `remote_app` 的 `_PROTOCOL_VERSION` 覆盖（若 SDK 允许）或文档声明"以 SDK 为准" | `protocol.py`（新）、`server.py`、`remote.py`、`remote_app.py` | `::test_protocol_version_single_source` | 恢复字面量 | 1.0 |
| ARCH-RM-ERR-06 | `diagnose._EXPLAIN_EXTRA` 改由 `errors.PRODUCT` 派生（码→(层,原因,动作)）；文案正则 `RULES` 降为兜底（未命中码时才用） | `diagnose.py`、`errors.py` | `::test_layer_is_stable_per_code` | 恢复手工表 | 2.0 |
| ARCH-RM-CFG-05 | 新建 `credentials.py`：`resolve()`（env>文件>镜像）、`explain()`（返回档位+依据）、`store()`（唯一写入口）；`auth_cmd`/`net._fetch_anon_token`/`install` 改调用 | `credentials.py`（新）、`auth_cmd.py`、`net.py`、`install.py` | `tests/test_auth.py::test_credential_write_points_are_whitelisted`、`::test_credential_explain_reports_priority_chain` | 恢复三处直写 | 2.0 |
| ARCH-RM-CFG-06 | `src/vod_mcp/runtime_state.py:174` mkdir 后补 `chmod(parent, 0o700)`（`OSError` 只告警） | `runtime_state.py` | `::test_state_dir_is_private_on_fresh_install` | 删除一行 | 0.5 |
| ARCH-RM-CFG-07 | `policy.py` 新增 `FREE_TEXT_KEYS = {"content", "originalLines"}`；`guard_scope` 按集合剔除（不再只认 `content`） | `policy.py`、`tests/test_tags_whitelist.py` | `::test_free_text_fields_are_explicit` | 恢复单字段硬编码 | 1.0 |
| ARCH-RM-BLD-06 | `package.json.files` 改目录形态（`src/vod_mcp` 整包 + 现有白名单项）；CI 加 `python3 scripts/pack_verify.py --check-files`（`scripts/pack_verify.py` 已有，补"包内==仓内"对照） | `package.json`、`scripts/pack_verify.py`、`tests/test_packaging.py` | `::test_packed_files_cover_all_src_modules` | 恢复逐文件列表 | 2.0 |
| ARCH-RM-BLD-07 | `sync_plugin.py:51-52` 改 `ast.parse` 取模块级赋值；`tests/test_review_r2.py:207` 的打桩删除，改真实解析用例 | `sync_plugin.py`、`tests/test_review_r2.py`、`tests/test_copies_generated.py` | `::test_version_parser_handles_annotated_form` | 恢复 `split` 解析 | 0.5 |

---

## 五、批量实施建议（怎么排）

### 5.1 三批 + 一个热修

| 阶段 | 内容 | 完成判据 |
|---|---|---|
| **热修（本周）** | ERR-01、CFG-01（P0） | 两条验收断言绿；作为独立 patch 版本发布 |
| **第 1 批（≈4 天）** | B1 六项（BLD-01/02/05、CFG-04、BLD-03/04） | 门禁在 `dev` 上生效；两份 CI 一致；版本全等 |
| **第 2 批（≈9 天）** | B2 四项（ERR-02..05）＋ errors.py | 错误码单源；日志可关联；吞异常有痕 |
| **第 3 批（≈11 天）** | B3 六项（DEP-02/04/05、CALL-01/02/06） | 两面同码；入口单源；导入面无冲突 |
| **第 4 批（≈4 天）** | B4 两项（CFG-02/03） | 远程面默认收紧；原子写单源 |
| **随需（≈20.5 天）** | 12 项 P2 | 各自最小形态 |

### 5.2 与既有决策的关系

| 整改项 | 触碰的决策 | 处置 |
|---|---|---|
| BLD-02 | 测试夹具的"比较 origin/main"语义锁 | 追加 `D-update-branch-1` |
| ERR-03 | 错误码段位（对外契约） | 追加 `D-error-codes-1` |
| CFG-02 | `D-token-machine-1` 的代领开关 | 追加 `D-remote-origin-1`（不推翻原决策） |
| CALL-01 | 远程面 `REMOTE_WITHHELD` 的会话隔离结论 | **不触碰**——只统一码与消息，不动工具面 |
| CALL-04 | pack 划分（`D-packs-*`） | 不触碰——拆分不改变工具面与 pack 归属 |

> 纪律：任何"追加决策"都要写清**为什么现在改**（新证据/新场景），并在
> [`decisions.md`](decisions.md) 保留原决策不删。

### 5.3 不建议早做的两项

- **ARCH-RM-CALL-04（collect 拆分）**：收益随采集侧改动量增长；没有并行需求时先做
  CALL-01（两面统一）更有价值。
- **ARCH-RM-CALL-03（哨兵会话）**：依赖 SDK 版本行为，最好与一次 SDK 升级或远程面
  改动合并做，单独做收益低、回归面大。

---

## 六、全局回归与回滚总则

### 6.1 每项整改的自检四问

1. 用例先在旧代码上**红**了吗？（红→绿截图或提交说明里贴复现命令）
2. 新用例进 CI 了吗？（只在本地跑的用例等于没有——见 BLD-01）
3. 回滚点是否可执行？（能一条命令回到绿）
4. 是否有"跨形态"漏测？（stdio/remote、仓内/载荷/插件副本 —— 本仓缺陷大多藏在这里）

### 6.2 通用回滚总则

- **代码回滚**：`git revert <该整改的提交>`（一竖切片一提交保证可单独 revert）。
- **数据兼容**：涉及落盘格式的整改（ERR-03 的 code 表、ERR-05 的日志格式、
  BLD-04 的 manifest 字段）必须"向前兼容读"——新字段缺失按未知处理，旧字段不删。
- **决策回滚**：`decisions.md` 只追加不删；撤回写成"已撤回（原因）+ 指向新决策"。
- **发版回滚**：`release.sh` 的改动回滚后，**已发布的版本号不回退**（回退会造成
  "同版本号两份代码"，本仓有过此实况，见 `src/vodkit_cli/common.py:288-293`）。

### 6.3 每批整改后必须同跑的门禁（现在就该全跑，不依赖 CI）

```bash
python3 -m pyflakes src/vod_mcp src/vodkit_cli integrations/hermes/hooks tests
python3 scripts/sync_plugin.py && python3 scripts/verify_copies.py
python3 scripts/secret_scan.py
python3 scripts/sync_case_roster.py --check      # 若新增用例，先 --write 再 check
python3 -m mypy
python3 -m pytest tests/ -q
```

> 注：`python3 -m pytest tests/ -q` 在当前环境上有两处**既有**基线噪音，不代表整改回归：
> ① 本执行环境额外装了 `pytest-randomly`（CI 不装），确定性结果请加 `-p no:randomly`；
> ② 无 `main` 引用的检出会让 `tests/test_installer.py` 的克隆夹具整体 ERROR——这正是
> BLD-02 要修的口径。详见 [`architecture-defects.md`](architecture-defects.md) 附录 10.3。

### 6.4 验收断言汇总（对应缺陷台账每条）

| 编号 | 断言（用例名） | 所属批次 |
|---|---|---|
| DEP-01 | `tests/test_import_graph.py::test_no_cycle_in_vod_mcp` | P2 |
| DEP-02 | `tests/test_host_adapters.py::test_registry_is_lazy`；`tests/test_payload.py::test_payload_face_cannot_import_host_adapters` | B3 |
| DEP-03 | `tests/test_structure_guards.py::test_packs_do_not_import_net_for_errors` | P2 |
| DEP-04 | `tests/test_p2_structure.py::test_serve_entry_resolves_single_root` | B3 |
| DEP-05 | `tests/test_installer.py::test_codex_install_without_repo_never_shells_out` | B3 |
| DEP-06 | `tests/test_state_read.py::test_provenance_paths_are_live` | P2 |
| CALL-01 | `tests/test_remote_guards.py::test_two_faces_report_same_code_for_same_error` | B3 |
| CALL-02 | `tests/test_structure_guards.py::test_both_faces_share_collect_discipline` | B3 |
| CALL-03 | `tests/test_remote_transport.py::test_sentinel_survives_manager_rebuild` | P2 |
| CALL-04 | `tests/test_skeleton.py` 等零改动全绿 + `packs/collect/__init__.py` ≤120 行 | P2 |
| CALL-05 | `tests/test_skeleton.py::test_protocol_version_single_source` | P2 |
| CALL-06 | `tests/test_doctor_egress.py::test_doctor_probe_uses_net_semantics` | B3 |
| ERR-01 | `tests/test_policy_load.py::test_policy_fail_closed`（两面各一条） | **热修** |
| ERR-02 | `tests/test_policy_load.py::test_rule_schema_violation_names_rule_id` | B2 |
| ERR-03 | `tests/test_explain_codes.py::test_all_error_codes_come_from_table` | B2 |
| ERR-04 | `tests/test_error_trace.py::test_no_bare_except_pass` | B2 |
| ERR-05 | `tests/test_observability.py::test_log_lines_are_structured_and_carry_tool_context` | B2 |
| ERR-06 | `tests/test_explain_codes.py::test_layer_is_stable_per_code` | P2 |
| CFG-01 | `tests/test_pending_feedback.py::test_pending_file_is_private` | **热修** |
| CFG-02 | `tests/test_remote_transport.py::test_foreign_origin_is_rejected` | B4 |
| CFG-03 | `tests/test_runtime_atomic.py::test_single_atomic_writer` | B4 |
| CFG-04 | `tests/test_secret_scan.py::test_scans_generated_copies_too` | B1 |
| CFG-05 | `tests/test_auth.py::test_credential_write_points_are_whitelisted` | P2 |
| CFG-06 | `tests/test_token_machine_scope.py::test_state_dir_is_private_on_fresh_install` | P2 |
| CFG-07 | `tests/test_tags_whitelist.py::test_free_text_fields_are_explicit` | P2 |
| BLD-01 | `tests/test_release_and_pack_paths.py::test_both_ci_definitions_run_same_gates` | B1 |
| BLD-02 | `tests/test_p2_structure.py::test_update_compares_current_upstream` | B1 |
| BLD-03 | `tests/test_release_and_pack_paths.py::test_all_manifest_versions_agree` | B1 |
| BLD-04 | `tests/test_info_binding.py::test_install_manifest_records_worktree_head_when_snapshot_lags` | B1 |
| BLD-05 | `tests/test_release_and_pack_paths.py::test_hook_install_script_is_idempotent` | B1 |
| BLD-06 | `tests/test_packaging.py::test_packed_files_cover_all_src_modules` | P2 |
| BLD-07 | `tests/test_copies_generated.py::test_version_parser_handles_annotated_form` | P2 |

## 七、附录 A：raise 点清单（ERR-03 替换工作量实测）

按 `grep -rn "ToolError(" src/`（同基线，已剔除 `src/vod_mcp/net.py:166` 的类定义行）
共 **26 处抛点**，分布：

| 文件 | 处数 | 现有码（行号） |
|---|---|---|
| `src/vod_mcp/packs/collect.py` | 14 | `-32602`×4（`:535`/`:537`/`:552`/`:642`）、`-32011`×4（`:655`/`:669`/`:675`/`:678`）、默认 `-32000`×6（`:146`/`:158`/`:173`/`:386`/`:447`/`:665`） |
| `src/vod_mcp/packs/core.py` | 4 | `-32602`×2（`:112`/`:121`）、`-32015`×1（`:124`）、`-32012`×1（`:245`） |
| `src/vod_mcp/net.py` | 5 | `-32014`×1（`:184`）、`-32012`×2（`:206`/`:335`）、`-32001`×1（`:211`）、`e.code`×1（`:209`，HTTP 状态码） |
| `src/vod_mcp/packs/knowledge.py` | 2 | 透传 `SkillError.code`（`SkillError` 默认 `-32010`） |
| `src/vod_mcp/tools.py` | 1 | `-32601`（`:77`） |

`ToolError` 默认码定义在 `src/vod_mcp/net.py:167`（`code: int = -32000`）。

> 替换要点：① 默认 `-32000` 的 6 处要逐处判定语义（"参数非法" `-32602` / "业务前置条件
> 不满足" / "状态不可用"），不要机械替换；② `-32602` 的 4 处是**参数非法**，
> 语义上可保留在协议段，但必须显式引用常量；③ `-32011` 的语义是"草稿/审批令牌不符"
> （`tests/test_explain_codes.py:48` 锁死），迁移时不得改语义。这是 ERR-03 里唯一需要
> 人判断的部分，也是估 2 人日的原因。

## 八、附录 B：本方案与缺陷台账的一一对应

| 维度 | 缺陷编号 | 整改编号 | 批次 |
|---|---|---|---|
| A 模块依赖 | DEP-01..06 | RM-DEP-01..06 | B3（02/04/05）、P2（01/03/06） |
| B 核心调用链 | CALL-01..06 | RM-CALL-01..06 | B3（01/02/06）、P2（03/04/05） |
| C 错误处理 | ERR-01..06 | RM-ERR-01..06 | 热修（01）、B2（02..05）、P2（06） |
| D 配置与安全 | CFG-01..07 | RM-CFG-01..07 | 热修（01）、B4（02/03）、B1（04）、P2（05..07） |
| E 构建与发布 | BLD-01..07 | RM-BLD-01..07 | B1（01..05）、P2（06/07） |

无一项"仅记录不整改"：本方案对台账 32 条全部给出步骤、文件、用例与回滚点。