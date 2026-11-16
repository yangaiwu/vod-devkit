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

ROOT = _paths.DIST_ROOT


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


def build_info(strict: bool = False) -> dict:
    from vod_mcp import __version__
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    return {
        "version": __version__,
        "commitSha": git_sha(strict),
        "builtAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "sourceRemote": _safe_remote(remote) if remote else None,
    }


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
        except Exception:
            pass
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


def _read_manifest() -> dict:
    p = manifest_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


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


def _dsh_install_snapshot(target):
    """dsh 安装期真源；非 dsh 宿主返回 None（S152）。探测失败不阻断安装。"""
    if target != "dsh":
        return None
    try:
        from vod_mcp.host_adapters import dsh as _dsh_ad
        return _dsh_ad.install_snapshot()
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
        return False
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
    manifest = {
        "version": bi["version"],
        "source": {"type": "git", "remote": bi["sourceRemote"],
                   "ref": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                         cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                   "commitSha": bi["commitSha"],
                   # R10：提交不可达（amend 后的 dangling 对象）要能被审计看见，而不是
                   # 只在 doctor 里表现为"manifest 与 build-info 不一致"。
                   "reachable": _source_reachable(bi["commitSha"])},
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
        "dshPatch": _dsh_install_snapshot(target),
    }
    row = {k: manifest[k] for k in
           ("target", "transport", "mcpUrl", "installedAt", "product", "packs",
            "dshProfile", "apiBase", "mcpConfig", "skillsDir", "payloadDir", "dshPatch")}
    row["version"] = manifest["version"]
    row["commitSha"] = manifest["source"]["commitSha"]
    row["skillInstalls"] = [si for si in manifest["skillInstalls"]
                            if si["host"] == target]
    prev = _read_manifest()
    manifest["installs"] = _install_rows(prev, row)
    manifest_path().write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                               encoding="utf-8")
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
    missing = [k for k in ("VOD_JAVA_API_KEY",) if
               not os.environ.get(k) and not _runtime_cfg_read().get("java_key")]
    if missing and transport == "stdio":
        print(f"提示：{missing} 未配置——首次提交将自动申请零字段匿名令牌（无需配置）")
    elif transport == "remote":
        print("远程形态提示：身份随请求头走（token 已由宿主配置承载）；"
              "本机 runtime.json 的匿名链不参与远程提交")


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
