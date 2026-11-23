"""安装器公共件：根定位、版本烧录、manifest 名册、技能指纹、分发形态位。

从 bin/vod-devkit 拆出（F8）：这些都跨多个子命令使用，属于"装配底座"。
"""
import datetime
import json
import os
import subprocess
import sys

from vod_mcp import paths
from pathlib import Path

from vod_mcp import hosts as host_specs


# 分发根（manifest / build-info / 载荷入口相对它）；包根在 src/，由 paths 负责
from vod_mcp import paths as _paths
from vod_mcp import trace as _trace

ROOT = _paths.DIST_ROOT


class ManifestCorrupt(RuntimeError):
    """账本存在但无法解析。写路径必须抛它，绝不用空账本覆盖（P4，2026-11-16）。"""


_HERMES_SPEC = host_specs.load("hermes")


HERMES_MCP_DIR = Path(_HERMES_SPEC["configPath"]).parent  # 约定：写入前打印供确认


HERMES_SKILLS_DIR = Path(_HERMES_SPEC["skillsDir"])


def git_sha(strict: bool) -> str | None:
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True).stdout.strip())
    if strict and dirty:
        print("工作区不干净，拒绝构建（构建纪律）", file=sys.stderr)
        sys.exit(1)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    return sha or None


def _safe_remote(url: str) -> str:
    """凭据脱敏：oauth2:xxx@ / https://user:pass@ 一律剥离。"""
    import re as _re
    return _re.sub(r"(https?://)([^@/]+@)", r"\1", url)


def source_dirty_paths(root: Path | None = None) -> list:
    """会随载荷/宿主配置一起发出去的源路径里，有没有未提交改动（D-provenance-1）。

    为什么必须挡在 install 前面：install 会用**工作树**内容物化载荷，而 build-info 记的是
    HEAD → 未提交补丁被装成"正式版"（2026-11-24 实锤两次：一次自带脏树重装、一次别人并行改）。
    只扫真源（src/assets/npm/integrations/打包元数据），构建产物（build-info.json、
    plugins/ 副本、__pycache__）不算——它们本来每次 install 都会变。
    """
    root = Path(root) if root else ROOT
    if not (root / ".git").exists():
        return []                     # npx/tarball 形态没有 .git，无从判断
    r = subprocess.run(["git", "status", "--porcelain", "--",
                        "src", "assets", "npm", "integrations",
                        "package.json", "pyproject.toml", "packages"],
                       cwd=str(root), capture_output=True, text=True)
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def build_info(strict: bool = False) -> dict:
    from vod_mcp import __version__
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    sha = git_sha(strict)
    head = git_sha(False)            # 当前 HEAD；strict 下与 sha 相同
    # ARCH-BLD-04：`snapshot` 标出这份 commitSha 的语义——是「发版快照」还是
    # 「工作树重烧」。没有这个标记时，读的人无法区分"落后 HEAD 是异常"还是
    # "tracked 快照本就停在 v^ 属正常"（台账实锤：0.5.44 快照落后 HEAD 三个提交，
    # 却被 install / provenance 当权威，运维按它对账会对到错的提交）。
    snapshot = "worktree" if sha and head and sha == head else "released"
    info: dict = {
        "version": __version__,
        "commitSha": sha,
        "builtAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "sourceRemote": _safe_remote(remote) if remote else None,
        "snapshot": snapshot,
    }
    # D-provenance-1：源脏时**必须**留下痕迹（内容≠commitSha 是事实，藏起来就成了谎报）。
    # 只在非空时写，保持干净装的 build-info 与旧版逐字相同（golden 用例依赖这一点）。
    dirty = source_dirty_paths()
    if dirty:
        info["dirtySources"] = dirty
    return info


def write_build_info(strict: bool):
    info = build_info(strict)
    # 隔离跑法（宿主矩阵/CI 用例）不许改真实仓的 build-info：它会被重烧成当前
    # HEAD，而包内副本停在发版提交 → 结构门禁"根/包内不一致"假红（本轮实锤）。
    if os.environ.get("VOD_DEVKIT_NO_BUILD_INFO"):
        print("build-info.json: 跳过写入（VOD_DEVKIT_NO_BUILD_INFO）")
        return
    # R10（2026-11-16 实测）：npx/tarball 形态没有 .git，重烧会把 provenance 写成
    # commitSha:null / sourceRemote:null 并随 stage() 进载荷——"载荷代表哪个提交"永久丢失
    #（doctor 两边都是 null 反而判 OK，假绿）。已有 provenance 时一律保留。
    if not (ROOT / ".git").exists() and (ROOT / "build-info.json").is_file():
        print("build-info.json: 保留包内 provenance（安装根无 .git 元数据，不重烧）")
        return
    (ROOT / "build-info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print("build-info.json:", json.dumps(info, ensure_ascii=False))


def manifest_path() -> Path:
    """安装名册位置：默认仓根；VOD_DEVKIT_MANIFEST 可覆盖（多安装根/隔离测试）。

    契约上 manifest 落在"安装器所在的仓根"——npx 缓存下的仓被清掉时名册一起消失，
    所以 doctor/uninstall 只在同一个仓上下文里自洽；需要另置一份或多份时用该 env。
    """
    override = (os.environ.get("VOD_DEVKIT_MANIFEST") or "").strip()
    return Path(override) if override else ROOT / "install-manifest.json"


PRESETS = {
    # 对外默认：开发者=反馈采集者（workflow 不进对外默认集）
    "collect": "core,collect",
    # 内部：运营/可信第三方全量。2026-11-06 修正（深审 P0-2）：原值
    # "core,workflow,kb,collect" 与运行期 ALL_PACKS=(core,collect,knowledge)
    # 命名漂移——workflow 包已随"运营归 vod-system 前端"净删、kb 是
    # knowledge 的旧称，按原值安装 workflow/kb 被静默丢弃（安装口说装了
    # 运行口不认=挪到别处而非消除）
    "full": "core,collect,knowledge",
}


def _skill_installs(manifest_path: Path, extra_dirs) -> list:
    """多宿主技能落点并集（名册对账）：manifest 按「最近一次安装」覆盖会
    互相冲掉落点（实锤：codex 装完 opencode 落点消失），按 host+dir
    去重保留历史落点。"""
    import json as _json
    import os
    home = str(Path.home()) + os.sep
    prev = {}
    if manifest_path.exists():
        try:
            for si in _json.loads(manifest_path.read_text(encoding="utf-8")).get("skillInstalls") or []:
                d = si.get("dir") or ""
                # 只保留「当前 HOME 之下且目录真实存在」的落点——隔离环境
                # （fake-home 测试）不吞真实 HOME 的历史落点，卸载残留自动剪枝
                if d.startswith(home) and Path(d).is_dir():
                    prev[(si["host"], d)] = si
        except Exception as e:
            _trace.suppress("common._skill_installs", e)
    for h, d in [("hermes", HERMES_SKILLS_DIR)] + list(extra_dirs or []):
        if d is not None:
            prev[(h, str(d))] = {"host": h, "dir": str(d)}
    return sorted(prev.values(), key=lambda x: (x["host"], x["dir"]))


def _dir_hashes(base: Path) -> dict:
    """对既有目录树计算相对 sha256 指纹（roster 对账用）。"""
    import hashlib
    out = {}
    for skill in sorted(Path(base).iterdir()):
        if skill.is_dir():
            for f in sorted(skill.rglob("*")):
                if f.is_file():
                    out[f"{skill.name}/{f.relative_to(skill)}"] = (
                        hashlib.sha256(f.read_bytes()).hexdigest())
    return out


def _skill_hashes() -> dict:
    """技能拷贝件指纹（D-drift-lock）：安装时记录 sha256，verify/doctor 比对
    ——拷贝件与安装产物漂移可检（vendor 规则漂移实锤的针对性防线）。"""
    import hashlib
    out = {}
    for entry in sorted((paths.ASSETS / "skills").iterdir()):
        if entry.is_dir():
            for f in sorted(entry.rglob("*")):
                if f.is_file():
                    rel = f"{entry.name}/{f.relative_to(entry)}"
                    out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _drifted_skills(manifest: dict) -> list:
    """比对 skillsDir 拷贝件与 manifest.skillHashes，返回漂移文件清单。"""
    import hashlib
    base = Path(manifest["skillsDir"])
    drifted = []
    for rel, sha in (manifest.get("skillHashes") or {}).items():
        f = base / rel
        if not f.exists():
            drifted.append(f"{rel}（缺失）")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            drifted.append(f"{rel}（内容被改）")
    return drifted


def atomic_write_text(path, text: str, mode: int | None = None) -> None:
    """原子写文本（P4）：实现在 `vod_mcp.paths`，安装器侧只做一层门面。"""
    _paths.atomic_write_text(path, text, mode)


def _read_manifest(*, strict: bool = False) -> dict:
    p = manifest_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("顶层不是 JSON 对象")
        return data
    except Exception as e:  # noqa: BLE001  两种处置：写路径拒绝，读路径报警
        if strict:
            raise ManifestCorrupt(
                f"{p} 无法解析（{e}）——拒绝写入：用空账本覆盖会把其它安装行一起丢掉。"
                "先还原备份（同目录 *.bak / 上一版 install-manifest）或修好该 JSON 再重跑") from e
        print(f"[vod-devkit] 警告：{p} 无法解析（{e}）——只读面按空账本继续；"
              "任何写操作都会拒绝覆盖", file=sys.stderr)
        return {}


def install_rows(manifest: dict) -> list:
    """账本里的全部安装行（**唯一读法**，S160 / D-single-entry-1）。

    - 新版：`manifest["installs"]`（一个宿主/profile 一行，D-installs-1 / D-installs-profile-1）
    - 老账本：顶层即单行；只有带 `target` 才算，空 manifest / `installs: []` 一律返回 `[]`

    为什么必须单入口：这条读法曾在 doctor / prune / packs / uninstall 各写一份，而且
    uninstall 那份无条件回落 `[mf]`——空 manifest 会被当成"有安装"，卸载链据此去动配置。
    """
    rows = manifest.get("installs")
    if rows:
        return list(rows)
    return [manifest] if manifest.get("target") else []


def row_view(manifest: dict, row: dict) -> dict:
    """合并视图：顶层键是最近一次安装，行内**非 None** 字段覆盖之（S160）。

    把行里显式的 None 也照抄上去会把顶层已知值擦掉（字段缺失 ≠ 该字段为 None）。
    """
    view = dict(manifest)
    for k, v in (row or {}).items():
        if v is not None:
            view[k] = v
    return view


def latest_row(manifest: dict) -> dict:
    """最近一次安装的行（`_install_rows` 按 installedAt 排序，故取末条）；空账本返回 `{}`。"""
    rows = install_rows(manifest)
    return rows[-1] if rows else {}


def _install_rows(prev: dict, row: dict) -> list:
    """按 (target, dshProfile) 去重的安装行（D-installs-1 / S153）：一个 manifest 记全部宿主安装。

    起因（结构债）：顶电平字段只记「最近一次安装」，装 hermes 再装 codearts 后
    uninstall 只清最后一个宿主的 MCP 条目，另一台宿主的配置永远留在那。

    S153：dsh 的多个 profile（web / headless）是**独立的安装对象**——只按 target 去重
    会让第二个 profile 顶掉第一个：doctor 只自愈最后装的那个、uninstall 只摘一个块、
    prune 的"在用"集合丢掉另一个 profile 仍在用的载荷（下次启动白屏）。
    """
    def _key(r):
        return (r.get("target"), (r.get("dshProfile") or ""))

    rows = [r for r in (prev.get("installs") or []) if _key(r) != _key(row)]
    rows.append(row)
    return sorted(rows, key=lambda r: r.get("installedAt") or "")


def _dsh_install_snapshot(target, product=None, api_base=None, packs=None):
    """dsh 安装期真源；非 dsh 宿主返回 None（S152）。探测失败不阻断安装。

    P5（2026-11-16）：除解释器/state/壳版本外，把 product / apiBase / packs 也记下来——
    这三项恰恰是"重装会改、自愈却看不见"的字段，doctor 只能报 command/入口差异时
    它们的漂移是盲区。
    """
    if target != "dsh":
        return None
    try:
        from vod_mcp.host_adapters import dsh as _dsh_ad
        snap = _dsh_ad.install_snapshot()
        snap.update({"product": product or "", "apiBase": api_base or "",
                     "packs": packs or ""})
        return snap
    except Exception:  # noqa: BLE001  记录缺失只是让自愈退化到"只报告"，不阻断安装
        return None


def _source_reachable(sha: str) -> bool | None:
    """安装期提交是否可达（R10）：三态。

    True  = 本地对象存在且被某个分支/远端引用包含；
    False = 有 .git 但该 sha 不可达（amend 后的 dangling / 未推送）；
    None  = 判不了（无 .git：npx 缓存/tarball 形态）——**不许当成 False 报**，
            那会把用户引向"amend/未推送"的错误方向（真机实测）。
    """
    if not (ROOT / ".git").exists():
        return None          # 包内没有 git 元数据，provenance 不可判定
    if not sha:
        return None          # 空 sha 同样是"判不了"，不是"不可达"（否则会打出"提交 None 不可达"）
    try:
        r = subprocess.run(["git", "rev-parse", "--verify", f"{sha}^{{commit}}"],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return False
        r2 = subprocess.run(["git", "branch", "-a", "--contains", sha],
                            cwd=ROOT, capture_output=True, text=True, timeout=10)
        return bool((r2.stdout or "").strip())
    except Exception:  # noqa: BLE001  没有 git / 超时 → 当作不可判定（不误报）
        return None


def _released(sha: str) -> bool | None:
    """该提交是否落在某个 tag 里（R10-2）：True=已发布构建；False=工作树/未打 tag；
    None=判不了（无 .git / 无 sha）。

    `reachable=True` 只证明"提交可达"，不代表"已发布"——真机曾把 46faccb（0 个 tag 包含）
    当成 0.5.17 装进机器，而 npm 上的 0.5.17 是 a5bbea1：同版本号两份代码，行为对不上。
    """
    if not (ROOT / ".git").exists() or not sha:
        return None
    try:
        r = subprocess.run(["git", "tag", "--contains", sha],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
        return bool((r.stdout or "").strip())
    except Exception:  # noqa: BLE001
        return None


def _write_install_manifest(args, target, packs, bound_product, mcp_conf,
                            extra_dirs, transport: str = "stdio",
                            mcp_url: str = "", payload_dir=None) -> None:
    """manifest 段：落安装名册（版本/来源/归因/落点指纹），并给出 key
    配置提示。名册对账口径见各字段注释（原 install.cmd_install 尾段，整段平移）。"""
    bi = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8"))
    # ARCH-BLD-04：`source.commitSha` 是 build-info 快照里的提交，未必等于安装时
    # 实际代码（tracked 快照按设计停在发版提交 v^）。所以另记一个 `worktreeHead`：
    # 两者不等时，运维能看见"装的是哪个代码"，而不是对着发版快照对账。
    _snapshot_sha = bi.get("commitSha")
    _worktree_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip() or None
    manifest = {
        "version": bi["version"],
        "source": {"type": "git", "remote": bi["sourceRemote"],
                   "ref": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                         cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                   "commitSha": bi["commitSha"],
                   # 快照来源标记（released=发版快照 / worktree=按当前 HEAD 重烧）
                   "snapshot": bi.get("snapshot", "unknown"),
                   # 安装时工作树真实 HEAD；与 commitSha 不等即为"快照落后"的现场
                   "worktreeHead": _worktree_head,
                   "snapshotLagsHead": bool(_snapshot_sha and _worktree_head
                                            and _snapshot_sha != _worktree_head),
                   # R10：提交不可达（amend 后的 dangling 对象）要能被审计看见，而不是
                   # 只在 doctor 里表现为"manifest 与 build-info 不一致"。
                   "reachable": _source_reachable(bi["commitSha"]),
                   # R10-2：同版本号两份代码的现场——"可达"不等于"已发布"，落盘供审计。
                   "released": _released(bi["commitSha"])},
        "target": target,
        # 传输形态（D-attach-1）：stdio=宿主本机拉起进程；remote=指向单独部署的
        # 远程端点；skills-only=只装技能（MCP 由别处注册）
        "transport": transport,
        "mcpUrl": mcp_url or None,
        "installedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "preset": args.preset,
        "distribution": getattr(args, "distribution", "devkit"),
        "product": bound_product,
        "packs": packs,
        "dshProfile": (getattr(args, "dsh_profile", "") or "").strip() or None,
        # dsh 修复用（S60/A 止血）：patch 块被 dsh 运行时序列化冲掉后，
        # doctor 可凭 product/apiBase 重建（块内容=安装期静态部署值）
        "apiBase": (getattr(args, "java_api_base", "") or "") or None,
        "mcpConfig": (str(mcp_conf) if mcp_conf else None),
        "skillsDir": str(HERMES_SKILLS_DIR),
        # 名册对账（huaweicloud-devkit doctor 模式借鉴，2026-11-06）：
        # 每个原生技能落点的独立指纹——漏装/漂移可被 doctor 逐落点抓出，
        # 不再只盯 hermes 单目录（opencode 漏拷静默失效的针对性防线）。
        # 多宿主并集合并：manifest 按「最近一次安装」覆盖会互相冲掉落点
        # （实锤：codex 装完 opencode 落点消失），按 host+dir 去重保留历史
        "skillInstalls": _skill_installs(manifest_path(), extra_dirs),
        "skillHashes": _skill_hashes(),
        # 载荷副本（D-payload-1）：宿主入口指向这里，而不是仓/npx 缓存路径
        "payloadDir": str(payload_dir) if payload_dir else None,
        # S152：dsh 安装期真源（解释器/state 根/mcp-client 版本）。doctor 自愈只跟这份
        # 记录比，不再拿"当前进程环境"重新生成整块去比——后者会把用户钉的解释器换掉。
        "dshPatch": _dsh_install_snapshot(target, bound_product,
                                          (getattr(args, "java_api_base", "") or ""), packs),
    }
    row = {k: manifest[k] for k in
           ("target", "transport", "mcpUrl", "installedAt", "product", "packs",
            "dshProfile", "apiBase", "mcpConfig", "skillsDir", "payloadDir", "dshPatch")}
    row["version"] = manifest["version"]
    row["commitSha"] = manifest["source"]["commitSha"]
    row["skillInstalls"] = [si for si in manifest["skillInstalls"]
                            if si["host"] == target]
    prev = _read_manifest(strict=True)
    manifest["installs"] = _install_rows(prev, row)
    atomic_write_text(manifest_path(),
                      json.dumps(manifest, ensure_ascii=False, indent=2))
    print("installed:", json.dumps(manifest, ensure_ascii=False, indent=2))
    reach = manifest["source"].get("reachable")
    if reach is False:
        print(f"[vod-devkit] 警告：安装期提交 {str(manifest['source'].get('commitSha'))[:12]} "
              "不可达（不在任何分支上：amend 改写历史 / 未推送）——manifest 已记 "
              "source.reachable=false。发版提交定稿后重装一次即可消除。", file=sys.stderr)
    elif reach is None:
        print("[vod-devkit] 提示：安装根没有 git 元数据（npx 缓存 / tarball 形态）——"
              "provenance 不可判定（manifest 记 reachable=null），不影响运行。", file=sys.stderr)
    if _released(str(manifest["source"].get("commitSha") or "")) is False:
        print(f"[vod-devkit] 提示：本次载荷来自**未打 tag 的提交** "
              f"{str(manifest['source'].get('commitSha'))[:12]}——版本号相同但内容可能与该版本的"
              "npm 包不同（真机实锤：0.5.17 装机是 46faccb，registry 是 a5bbea1）。"
              "要一字不差请用 npx vod-devkit@<ver> install，或等发版后再装。", file=sys.stderr)
    _exe = str(sys.executable or "")
    if volatile_interpreter(_exe):
        print(f"[vod-devkit] 警告：解释器在会被清理的位置 {_exe}——宿主配置会把它写成启动命令，"
              "缓存/临时目录被清后所有宿主一起起不来。建议先建稳定环境再装："
              "`python3 -m venv /root/.vod-devkit/venv`（或 /opt/<name>/venv）后用它的 python 跑 install。",
              file=sys.stderr)
    missing = [k for k in ("VOD_JAVA_API_KEY",) if
               not os.environ.get(k) and not _runtime_cfg_read().get("java_key")]
    if missing and transport == "stdio":
        print(f"提示：{missing} 未配置——首次提交将自动申请零字段匿名令牌（无需配置）")
    elif transport == "remote":
        _tok = (getattr(args, "mcp_token", "") or os.environ.get("VOD_MCP_TOKEN") or "").strip()
        if _tok:
            print("远程形态提示：身份随请求头走（token 已由宿主配置承载）；"
                  "本机 runtime.json 的匿名链不参与远程提交")
        else:
            print("远程形态提示：未带 token —— 服务端按**该实例的机器级匿名令牌**代提交"
                  "（同一实例上的 agent 共用一份身份与额度；要按 agent 隔离请带 --mcp-token，"
                  "或按产品/团队分实例）")



_VOLATILE_MARKERS = ("/cache/", "/scratch/", "/tmp/", "/temp/")


def volatile_interpreter(path: str) -> bool:
    """解释器路径是否落在会被清理的位置（缓存/临时目录）。

    实锤（2026-11-23）：11 个宿主配置都被写成
    `/root/.hermes/cache/scratch/.../bin/python`——那套 venv 一次 prune 就没了，
    配置看着对、宿主全起不来。装机器用哪个解释器就会把它写进配置，所以装的时候必须
    把"这个解释器会不会被清掉"告诉用户，而不是等他某天所有宿主一起失效。
    注：`/root/.vod-devkit/venv`、`/opt/...`、系统 `/usr/bin/python3` 都算稳定。
    """
    p = str(path or "")
    return any(m in p for m in _VOLATILE_MARKERS)

def _runtime_cfg_read() -> dict:
    """运行期状态现读（D-token-machine-1：单源在 paths.runtime_json_path()）。

    旧实现硬读 ROOT/vod_mcp/runtime.json——那是机器级改造前的落点，继续读会让
    "装机写 state、doctor/装机种读旧位"分叉（同一份状态两套读法，skill 明令禁止）。
    """
    from vod_mcp import paths as _paths
    p = _paths.runtime_json_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _distribution() -> str:
    """分发形态位（D-key-guard-3）：install --distribution 写入，构建期定死。
    devkit=开发/运维形态（自装自管）；preset=产品随 agent 分发（客户机只读）。"""
    p = manifest_path()
    if not p.exists():
        return "devkit"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("distribution", "devkit")
    except Exception:
        return "devkit"
