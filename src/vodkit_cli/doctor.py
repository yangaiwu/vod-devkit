"""诊断类子命令：status / doctor / verify / explain / detect。"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from vod_mcp import msgs
from vod_mcp import hosts as host_specs
from vod_mcp import paths as paths_mod
from vodkit_cli import common, remote


def cmd_status(args=None):
    target = (getattr(args, "target", "") or "") if args else ""
    p = common.manifest_path()
    if not p.exists():
        print("未安装（无 install-manifest）")
        sys.exit(1)
    if target:
        mf = json.loads(p.read_text(encoding="utf-8"))
        rows = common.install_rows(mf)
        # P1（2026-11-16）：dsh 的多 profile 是独立安装行，`--target dsh` 必须全部列出——
        # 只取第一条会让 headless（或 web）在用户视野里"不存在"。
        hits = [r for r in rows if r.get("target") == target]
        if not hits:
            print(f"没有该宿主的安装记录：{target}"
                  f"（现有：{', '.join(r.get('target','?') for r in rows) or '无'}）")
            sys.exit(1)
        for i, hit in enumerate(hits):
            if len(hits) > 1:
                prof = hit.get("dshProfile")
                print(f"[{target}{f':{prof}' if prof else ''}]", file=sys.stderr)
            print(json.dumps(hit, ensure_ascii=False, indent=2))
            if i != len(hits) - 1:
                print()
        return
    # golden 稳定性：apiBase 含安装期动态值（本地验证实例端口），归一化后输出
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'"apiBase": "http://127\.0\.0\.1:\d+"',
                  '"apiBase": "http://127.0.0.1:<PORT>"', text)
    # 载荷路径含 HOME/版本，按 <PAYLOAD> 归一（golden 不随环境漂）
    text = re.sub(r'"payloadDir": ".*?/payloads/[^"]+"',
                  '"payloadDir": "<PAYLOAD>"', text)
    print(text)


def _dsh_form_gap(facts: dict, want_mcp: bool) -> str:
    """形态缺口的判定（纯函数，便于用例锁真值表）。

    只认三种"结构不变量被破坏"的情形；字段值差异不属于缺口——那是 drift，只报告。
    """
    if want_mcp and not facts["present_mcp"]:
        return "缺 MCP 块"
    if not facts["present_shell"]:
        return "缺壳块"
    if want_mcp and not facts["register_tools_false"]:
        return "壳未 registerTools:false（会与 MCP 工具面双注册）"
    return ""


def _dsh_field_diffs(facts: dict, snap: dict, payload_s: str) -> list[str]:
    """块内字段与安装期记录的差异（纯函数）：只用于**报告**，永不驱动改写。

    `command` / `VOD_DEVKIT_HOME` / 入口路径都是安装期环境值；用户手工定制（如公网反代的
    `uiBase: /dsh`）不在比较面——自愈不该把它"纠正"回去。
    """
    diffs: list[str] = []
    if snap.get("command") and facts["command"] and facts["command"] != snap["command"]:
        diffs.append(f"command={facts['command']}（安装期 {snap['command']}）")
    if (snap.get("stateHome") and facts["state_home"]
            and facts["state_home"] != snap["stateHome"]):
        diffs.append(f"VOD_DEVKIT_HOME={facts['state_home']}（安装期 {snap['stateHome']}）")
    if payload_s and facts["server_py"]:
        want = str(Path(payload_s) / "vod_mcp" / "server.py")
        if facts["server_py"] != want:
            diffs.append(f"入口={facts['server_py']}（安装期 {want}）")
        # cwd / PYTHONPATH 同样指向载荷根：漂移会让 server 找不到包（import 失败）
        if facts.get("cwd") and facts["cwd"] != payload_s:
            diffs.append(f"cwd={facts['cwd']}（安装期 {payload_s}）")
        if facts.get("pythonpath") and facts["pythonpath"] != payload_s:
            diffs.append(f"PYTHONPATH={facts['pythonpath']}（安装期 {payload_s}）")
    # P5（2026-11-16）：这三项恰是"重装会改"的字段，旧报告面看不见它们的漂移
    for key, label, snap_key in (("product", "product", "product"),
                                 ("apibase", "apiBase", "apiBase"),
                                 ("packs", "VOD_PACKS", "packs")):
        rec = snap.get(snap_key)
        cur = facts.get(key)
        if rec and cur and str(cur) != str(rec):
            diffs.append(f"{label}={cur}（安装期 {rec}）")
    return diffs


def _repair_dsh_patch_block(mf: dict) -> str | None:
    """doctor 自愈（S58 → S152 重写：结构化不变量 + 安装期真源）。

    旧判据是「安装器整块文本 == patch 现有文本」，而块内嵌 sys.executable /
    state 根 / payload 路径，全按**当前 doctor 进程**求值 → 四条静默改写（0.5.16 实锤）：
    换解释器改 command、手工 uiBase=/dsh 被写回、PATH 无 dsh 时删 MCP 块退回 6 工具、
    manifest 缺 payloadDir 时写成相对路径。

    新口径（判定拆在两个纯函数里，真值表被 `test_doctor_repair_boundaries.py` 锁住）：
      · `_dsh_form_gap` 决定要不要补：缺 MCP 块 / 缺壳块 / 壳未 registerTools:false；
      · `_dsh_field_diffs` 只产出报告：字段与安装期记录不同 → 打印，不动字节；
      · 环境不可判定（无 payloadDir / 无 dshPatch 记录）→ 不动字节 + 打印指引。
    """
    prof = mf["dshProfile"]
    patch = Path(host_specs.load("dsh", prof)["configPath"])
    if not patch.exists():
        return None
    from vod_mcp import config_forms as cf
    from vod_mcp.host_adapters import dsh as _dsh
    text = patch.read_text(encoding="utf-8")
    try:
        verdict, reason = cf.classify_dsh_patch(text.splitlines())
    except cf.Refused as e:
        verdict, reason = "refuse", str(e)
    if verdict == "refuse":
        # 自愈也不越界：文件形态未知时只报告，不动字节
        print(f"[doctor] skip（cordis.patch.yml 形态不受支持，未自愈）：{reason}",
              file=sys.stderr)
        return None

    facts = _dsh.block_facts(text)
    snap = mf.get("dshPatch") or {}
    payload_s = str(mf.get("payloadDir") or "").strip()
    want_mcp = bool(snap.get("mcpClient"))

    gap = _dsh_form_gap(facts, want_mcp)
    if not gap:
        diffs = _dsh_field_diffs(facts, snap, payload_s)
        if diffs:
            print("[doctor] dsh patch 与安装期记录不一致（只报告，不改字节；"
                  "确认要恢复请重装：install --target dsh --profile " + prof + "）：\n  - "
                  + "\n  - ".join(diffs), file=sys.stderr)
        return None

    # R3（口径已定，2026-11-16）：无安装期记录（老账本）**一律不动字节**。
    # 按当前环境重建会把 VOD_DEVKIT_HOME / command 写成"跑 doctor 的那个进程"的派生值
    # （探针 G 实测）。老机器只提示重装一次，重装即固化真源。
    if "mcpClient" not in snap:
        print(f"[doctor] dsh patch 有形态缺口（{gap}），但 manifest 无安装期记录（老账本）"
              "——不动字节。请重装一次以固化真源："
              f"install --target dsh --profile {prof}", file=sys.stderr)
        return None

    if not payload_s:
        print("[doctor] dsh patch 需要补块，但 manifest 缺 payloadDir（老账本）——"
              "不动字节。请重装以生成安装期真源："
              f"install --target dsh --profile {prof}", file=sys.stderr)
        return None

    # R1：重建时**吸收 patch 里已有的定制值**（uiBase/product/apiBase/packs）——缺口
    # 只允许补缺的那几行，不许顺手把用户的定制重置回安装期默认（探针 E 实测：壳未关注册
    # 时整块重建把手工 uiBase=/dsh 回写成 apiBase，公网反代 CORS 复发）。
    args = SimpleNamespace(product=facts["product"] or mf.get("product") or "",
                           java_api_base=facts["apibase"] or mf.get("apiBase") or "")
    expected = _dsh._patch_block(args, snap.get("mcpClient"), Path(payload_s),
                                 facts["packs"] or str(mf.get("packs") or "core"),
                                 python_exe=snap.get("command"),
                                 state_home=snap.get("stateHome"),
                                 ui_base=facts["uibase"])
    try:
        # upsert 按托管标记划界（标记优先），不靠 "- " 猜边界：mcp 块的 args 列表项
        # 形如 "- /root/.../server.py"，旧实现会把块从中间切断，留下残块（0.5.15 实锤）。
        _dsh.upsert_patch(patch, expected)
    except Exception as e:  # noqa: BLE001  自愈失败只报告，不动字节
        print(f"[doctor] dsh patch 自愈失败（{e.__class__.__name__}: {e}）——"
              "多半是文件里有多份 vod-devkit 块；请人工确认后删掉多余那份"
              f"（本插件的块在 `# vod-devkit DSH integration start/end` 之间）：{patch}",
              file=sys.stderr)
        return None
    return str(patch)


def _provenance_problem(mf: dict) -> str | None:
    """安装记录与**安装产物**必须同源：manifest 的 commitSha == 载荷 build-info 的 commitSha。

    为什么取载荷不取仓根（S158 / D-doctor-provenance-1，2026-11-16 真机实锤）：
    根 `build-info.json` 是 tracked 文件，release 按 tag 口径把它写成 `v^`，而 `install`
    会按 HEAD 重烧——发版后的真机上二者永远不等，于是「工作树干净」与「doctor OK」互斥
    （实测 `git checkout -- build-info.json` 后 doctor 立即 FAIL）。载荷那份是 install
    与 manifest 同一次写入的真源，且不受工作树 git 状态影响。
    回落规则：老账本无 payloadDir / 载荷缺 build-info 时退回仓根（不新增误伤面）。
    """
    pd = mf.get("payloadDir")
    layers = []
    if pd:
        layers.append((Path(pd) / "build-info.json", "载荷"))
    layers.append((common.ROOT / "build-info.json", "仓根"))
    installed = (mf.get("source") or {}).get("commitSha")
    for path, where in layers:
        try:
            bi = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if installed != bi.get("commitSha"):
            return f"install-manifest 与{where} build-info 的 commitSHA 不一致"
        return None
    # S164-1：读不到 ≠ 通过。旧实现在这里 `return None`，等于「没有 provenance 也 OK」——
    # 载荷被删、仓根被清（npx 之外的干净检出）时 doctor/verify 会静默报成功。
    return "无法核验 provenance（载荷与仓根都没有可读的 build-info）"


def _hermes_hook_command_problems(text: str, want_router, want_guard) -> list:
    """hermes hook 行存在之后的下一条判据（S175-2）：命令本身必须是对的那一条。

    为什么要单独判：`upsert_hook` 旧实现「同 mark 即 unchanged」，于是换解释器/换脚本
    路径后旧行会一直留着；doctor 只判 mark 存在 → 全绿。真机实锤：pre_tool_call 用
    /usr/local/bin/python3.12、pre_llm_call 用 Hermes 3.14 venv（两次写入各按当时的
    sys.executable）。
    """
    out = []
    marks = (("vod_router.py", want_router, "预采集 hook"),
             ("vod_guard.py", want_guard, "读 Key 拦截 hook"))
    for mark, want, label in marks:
        cmds = [ln.strip() for ln in text.splitlines() if mark in ln and "command" in ln]
        if cmds and not any(str(want) in c for c in cmds):
            out.append(f"{label}的命令指向旧脚本（应为 {want}；实际 {cmds[0][:80]}）"
                       "——重跑 install --target hermes 替换")
    inters = {ln.split("command:", 1)[1].split()[0].strip("\"'")
              for ln in text.splitlines() if "command:" in ln
              and ("vod_router.py" in ln or "vod_guard.py" in ln)}
    inters = {i for i in inters if i}
    if len(inters) > 1:
        out.append("两条 hook 使用不同解释器（" + "、".join(sorted(inters))
                   + "）——重跑 install --target hermes 统一")
    return out


def _installed_targets(mf: dict) -> set:
    """账本里装过的宿主集合（S176）。

    为什么必须有：doctor 的逐宿主体检（hermes hook / codex 插件形态 / codearts 冒烟）曾用
    `mf.get("target")` 判——那是**最近一次安装**的宿主。多宿主机器上顶层 target 恒为最后一个
    （真机：11 行时是 dsh），于是这些体检整段不执行、doctor 却 OK。本轮实锤：hermes 两条 hook
    停在两个解释器上，doctor 全绿。
    """
    rows = common.install_rows(mf)
    out = {(r.get("target") or "").strip() for r in rows}
    out |= {(mf.get("target") or "").strip()}
    out.discard("")
    return out


def _hermes_host_problems() -> list:
    """hermes 侧 hook 体检（行存在 → 命令对 → 解释器一致）。S175-2 / S176。"""
    from vod_mcp.host_adapters import hermes as _hermes

    out = []
    cfg = Path(_hermes._profile_config())
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if _hermes.HOOK_MARK not in text:
        out.append(f"预采集 hook 未注册（{cfg} 的 hooks.pre_llm_call）"
                   "——重跑 install --target hermes")
    if _hermes.GUARD_MARK not in text:
        out.append(f"读 Key 拦截 hook 未注册（{cfg} 的 hooks.pre_tool_call）"
                   "——重跑 install --target hermes（技能里的"
                   "「只引指纹」靠它兜住 cat runtime.json）")
    if not _hermes._hook_script().exists():
        out.append(f"hook 脚本缺失：{_hermes._hook_script()}"
                   "（载荷不含 hooks/ 的旧版本？重跑 install）")
    if not paths_mod.guard_script().exists():
        out.append(f"读 Key 拦截脚本缺失：{paths_mod.guard_script()}"
                   "——重跑 install（或升级载荷）")
    out.extend(_hermes_hook_command_problems(
        text, _hermes._hook_script(), paths_mod.guard_script()))
    if (Path(_hermes._profile_config()).parent / "plugins" / _hermes.LEGACY_PLUGIN).exists():
        out.append("旧插件形态仍在（~/.hermes/plugins/vod-feedback-router）"
                   "= 与 hook 双份注入——重跑 install --target hermes 清理")
    return out


def _host_verify_problems(mf: dict) -> list:
    """装了 hermes/codex 但注册没落盘 → 报出来（S172，判据统一在 host_verify）。

    为什么是「报告」而不是「自动补写」：无 CLI 的降级安装只写备片，而自动把
    mcp_servers 块插进 config.yaml 需要写宿主主配置——那条写入目前非原子（P1），
    半截 YAML 会让宿主直接起不来，破坏半径远大于「工具连不上」。
    """
    from vod_mcp.host_adapters import host_verify

    seen, out = set(), []
    for row in common.install_rows(mf):
        target = (row.get("target") or "").strip()
        if target not in host_verify.SUPPORTED or target in seen:
            continue
        seen.add(target)
        for p in host_verify.problems(target):
            out.append(f"{target}: {p['message']}（{p['code']}）")
    return out


def _preset_provenance_problems(mf: dict) -> list:
    """preset 完整性：**逐行**判 manifest 与该行载荷是否同源（S164-2）。

    为什么必须遍历：旧实现只判 `installs[-1]`，多安装行时前几行的载荷被换掉也报 OK。
    报文带 target（dsh 再带 profile），一眼能看出是哪一台。
    """
    problems = []
    for row in common.install_rows(mf):
        view = common.row_view(mf, row)
        problem = _provenance_problem(view)
        if problem:
            who = row.get("target") or "?"
            if row.get("dshProfile"):
                who = f"{who}:{row.get('dshProfile')}"
            problems.append(f"{who}: {problem}")
    return problems


def _render_problems(problems) -> str:
    """分层报告（对表 devkit 的 doctor-report）：按 环境/载荷/配置/技能/网络/插件 分组，
    每条失败给「原因」与「动作」，避免运维只看到一堆 FAIL 文案。"""
    from vod_mcp import diagnose
    return diagnose.render_problems(problems)


# ── 出站面（P2，对表 devkit 的 proxy / regional awareness 两节） ──────
#
# 两条都只**报告**，不新建配置、不改路由、不 FAIL：
# - 代理：尊重既有 HTTP 约定（env 优先），devkit 也是"env 高于文件"；我们不建
#   proxy.json（没有第二种真相就不会有"我改了为什么不生效"）。代理 URL 可能含
#   口令，一律掩码后再打印。
# - 引擎可达：无 key 时此前完全没有网络结论（key 探针只在有 key 时跑）。这里
#   无条件探一次 meta 端点：401/403 也算**可达**（鉴权问题不等于网络问题）；
#   不可达只 warn——离线装机 doctor 必须还能用。

_PROXY_KEYS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY",
               "https_proxy", "http_proxy", "no_proxy")
_PROXY_CRED = re.compile(r"(://)[^/@]*:[^@]*@")


def _mask_proxy(url: str) -> str:
    return _PROXY_CRED.sub(r"\1***:***@", url)


def _proxy_summary() -> str:
    parts = [f"{k}={_mask_proxy(os.environ[k])}" for k in _PROXY_KEYS
             if os.environ.get(k)]
    return "；".join(parts) if parts else "未设（出站直连；urllib 会读 env，无需另配）"


def _probe_engine(base: str, timeout: float = 4.0) -> tuple:
    """(state, detail)；state ∈ ok / auth / unreachable。零依赖、不重试、不带 key。"""
    import urllib.error
    import urllib.request
    url = base.rstrip("/") + "/rest/developer/manager/hdvodmngservice/v1/external/meta"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return ("ok", f"HTTP {r.status} {url}")
    except urllib.error.HTTPError as e:
        return ("auth", f"HTTP {e.code}（可达；鉴权/路径响应）{url}")
    except Exception as e:  # noqa: BLE001  网络类异常一律只报告
        return ("unreachable", f"{type(e).__name__}: {e}（{url}）")


def _report_egress(api_base: str) -> None:
    print(f"[doctor] 出站代理：{_proxy_summary()}")
    if not api_base:
        print("[doctor] 引擎可达：未配置 apiBase（install 未写入？）")
        return
    state, detail = _probe_engine(api_base)
    if state == "ok":
        print(f"[doctor] 引擎可达：{detail}")
    elif state == "auth":
        print(f"[doctor] 引擎可达：{detail}")
    else:
        print(f"warn: 引擎不可达（离线环境可忽略；提交会失败）：{detail}")


def cmd_explain(args):
    """解释一条失败文案/错误码（-32010 等）：给层 + 原因 + 动作。"""
    from vod_mcp import diagnose
    text = " ".join(args.text).strip()
    if not text:
        print("用法：vod-devkit explain '<错误文案或错误码>'", file=sys.stderr)
        sys.exit(2)
    info = diagnose.explain(text)
    if not info["known"]:
        print(f"未收录该问题：{text[:120]}", file=sys.stderr)
        print("  排查入口：doctor 看分层报告；仍无头绪就把这段文案连同 doctor 输出一起贴出来",
              file=sys.stderr)
        sys.exit(2)
    print(f"层：{info['layer']}")
    print(f"原因：{info['cause']}")
    print(f"动作：{info['action']}")


def cmd_detect(args):
    """只读识别项目语言/框架/构建（给采集端补上下文；不写任何文件）。"""
    from vod_mcp import detect_framework
    try:
        info = detect_framework.detect(args.path or os.getcwd())
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("摘要：" + detect_framework.summary_line(info))


def cmd_doctor(args=None):
    target = (getattr(args, "target", "") or "") if args else ""
    problems = []
    p = common.manifest_path()
    if not p.exists():
        problems.append("无 install-manifest.json（未 install？）")
    else:
        mf = json.loads(p.read_text(encoding="utf-8"))
        rows = common.install_rows(mf)
        if rows:
            row_names = ", ".join(r.get("target", "?") for r in rows)
            if target:
                hit = next((r for r in rows if r.get("target") == target), None)
                if hit is None:
                    problems.append(f"没有该宿主的安装记录：{target}（现有：{row_names}）")
                else:
                    # --target：把该行的字段覆盖到视图上，检查按这一行走
                    mf = common.row_view(mf, hit)
                    print(f"[doctor] 检查安装行：{target}")
            elif len(rows) > 1:
                # 缺省视图=最近一次安装（顶层字段即最后一次写入）；多行只在末尾列出，
                # 要看单个宿主用 --target（避免在多宿主上把"某一行的问题"说成全局）
                print(f"[doctor] 安装行: {row_names}（--target <agent> 选择单个）")
        # dsh patch 块自愈（S58/A 止血，2026-11-06 真机实锤；S152 改写判据、S153 遍历全 profile）：
        # dsh 运行时序列化会冲掉 profile patch 里的 vod 块——只补形态缺口，字段差异只报告。
        # 遍历账本里**每一条 dsh 行**（web / headless 是独立安装对象），不是只看最近一条。
        dsh_rows = [r for r in rows if r.get("target") == "dsh" and r.get("dshProfile")]
        if not dsh_rows and mf.get("target") == "dsh" and mf.get("dshProfile"):
            dsh_rows = [mf]
        for row in dsh_rows:
            view = common.row_view(mf, row)
            patched = _repair_dsh_patch_block(view)
            if patched:
                print(f"[doctor] 已补 dsh patch 形态缺口（profile={row.get('dshProfile')}）："
                      f"{patched}（{msgs.effective_unit('dsh')}）")
        prov = _provenance_problem(mf)
        if prov:
            problems.append(prov)
        for hp in _host_verify_problems(mf):
            problems.append(hp)
        if (mf.get("source") or {}).get("released") is False:
            print("[doctor] 提示：安装期提交不在任何 tag 里（非发布构建）——版本号相同，"
                  "内容可能与该版本的 npm 包不同（R10-2）；要一字不差请用 "
                  "npx vod-devkit@<ver> install", file=sys.stderr)
        # ARCH-BLD-04：快照落后 HEAD 时明确提示「装的是哪个代码」。
        # 这不是 problem（tracked 快照按设计停在 v^，发版后必然与 HEAD 不等，
        # 判成 problem 会让每个发版后的真机 doctor 都红），而是**可见性提示**：
        # 运维按 commitSha 对账时要知道它代表发版快照、工作树实际是 worktreeHead。
        _src = mf.get("source") or {}
        _head = _src.get("worktreeHead")
        if _src.get("snapshotLagsHead"):
            print(f"[doctor] 提示：build-info 快照 {str(_src.get('commitSha'))[:12]} "
                  f"≠ 安装时工作树 HEAD {str(_head)[:12]}（snapshot={_src.get('snapshot')}）"
                  "——对账请用 source.worktreeHead 表示实际代码，"
                  "commitSha 仅是发版快照（ARCH-BLD-04）", file=sys.stderr)
        if mf.get("mcpConfig") and not Path(mf["mcpConfig"]).exists():
            problems.append("MCP 配置文件缺失")
        # D-token-machine-1（R4）：state 与旧位并存 = "静默不迁"要可见。
        # 非破坏（迁移只在 target 不存在时做），但旧账本/锚点没并进来，排障时得知道。
        try:
            from vod_mcp import paths as _paths
            st = _paths.machine_state_home() / "runtime.json"
            lg = _paths.legacy_runtime_json()
            if st.exists() and lg.exists():
                print(f"[doctor] 注意：机器级 state 与旧位并存（旧位 {lg} 已不再写入、"
                      "未并入 state；确认无用后可手工清理）")
        except Exception:  # noqa: BLE001  诊断不应因该项失败而中断
            pass
        # 载荷并存可见（0.5.12）：install 不删旧载荷——删错的后果是某个宿主配置里
        # 的 server.py 路径消失（白屏/工具全失），所以只报「谁在用哪份、哪份没人引用」，
        # 清理由人决定。真机实锤：机器上同时躺着 0.5.9/0.5.10/0.5.11 三份。
        # P2（2026-11-16 评审）：「在用」判定必须与 prune/uninstall 同一入口
        # （in_use_payloads：账本 ∪ dsh 各 profile patch）。旧实现只按账本算，报出的
        # 「未被任何安装行引用」可能是某个 profile 仍在用的载荷——照它删会白屏。
        try:
            from vod_mcp import payload as _payload
            raw = json.loads(p.read_text(encoding="utf-8"))
            all_rows = common.install_rows(raw)
            used = _payload.in_use_payloads(all_rows)
            labels: dict[str, list[str]] = {}
            for r in all_rows:
                d = (r.get("payloadDir") or "").strip()
                if not d:
                    continue
                try:
                    labels.setdefault(str(Path(d).resolve()), []).append(str(r.get("target")))
                except OSError:
                    labels.setdefault(d, []).append(str(r.get("target")))
            for k in sorted(used - set(labels)):
                labels.setdefault(k, []).append("dsh 配置面")
            if used:
                orphans = [ver for _d, ver, _sz in _payload.prune_candidates(rows=all_rows)]
                live = ", ".join(f"{Path(k).name}({'+'.join(sorted(set(v)))})"
                                 for k, v in sorted(labels.items()))
                print(f"[doctor] 载荷：在用 {live}"
                      + (f"；可清理（安装行与 dsh 配置都未引用）{orphans}"
                         "（不自动删——doctor 与 prune 是同一判定，删前仍建议看一眼）"
                         if orphans else ""))
        except Exception:  # noqa: BLE001  诊断项失败不阻断整体
            pass
        if mf.get("transport") == "remote" and mf.get("mcpUrl"):
            url = mf["mcpUrl"]
            token = (os.environ.get("VOD_MCP_TOKEN")
                     or os.environ.get("MCP_VOD_DEVKIT_API_KEY") or "").strip()
            try:
                names = remote._probe_remote(url, token, timeout=8)
                missing = remote._expected_remote_tools() - set(names)
                if missing:
                    problems.append(f"远程面工具面不符（缺 {sorted(missing)}）：{url}")
                else:
                    print(f"[doctor] 远程面可达：{url}（{len(names)} 工具）")
            except Exception as e:  # noqa: BLE001
                if not remote._remote_reachable(url):
                    problems.append(f"远程 MCP 端点不可达：{url}")
                elif not token:
                    print("[doctor] 远程端点可达，但未提供 token（401 属预期）："
                          "设 VOD_MCP_TOKEN 可验工具面")
                else:
                    problems.append(f"远程面探活失败（带 token）：{e}")
        if not Path(mf["skillsDir"]).exists():
            problems.append("skills 目录缺失")
        drifted = common._drifted_skills(mf)
        if drifted:
            problems.append("技能拷贝件与安装产物漂移（D-drift-lock）："
                            + "、".join(drifted) + "——重跑 install 恢复")
        # 名册对账（逐原生落点）：漏装/漂移按宿主点名（借鉴 devkit doctor）
        for si in mf.get("skillInstalls") or []:
            d = Path(si["dir"])
            if not d.exists():
                problems.append(f"技能原生副本缺失（{si['host']}）：{d} 不存在"
                                "——重跑 install 恢复")
                continue
            import hashlib
            expect = mf.get("skillHashes") or {}
            for rel, sha in expect.items():
                f = d / rel
                if not f.exists():
                    problems.append(f"技能文件缺失（{si['host']}）：{rel}")
                elif hashlib.sha256(f.read_bytes()).hexdigest() != sha:
                    problems.append(f"技能文件漂移（{si['host']}）：{rel}")
        # 载荷（D-payload-1）：MCP 入口指向副本 → 副本必须在且未被改
        from vod_mcp import payload as _payload
        pd = mf.get("payloadDir")
        if pd:
            if not Path(pd).is_dir():
                problems.append(f"载荷目录缺失：{pd}（MCP 入口指向它，宿主起不来）——重跑 install")
            else:
                bad = _payload.verify(Path(pd))
                if bad:
                    problems.append("载荷被改动：" + "；".join(bad[:5]))
                if _payload.marker_path().exists():
                    print(f"[doctor] 载荷已换（{pd}）——{msgs.effective()}")
        else:
            print("[doctor] 提示：本次安装无载荷副本（旧版），入口指向仓内路径；重跑 install 可固化")
        for res in _payload.residue():
            print(f"[doctor] 载荷残留（无 payload.json）：{res}——可手动删除")
        # 旧一代 AGENTS.md 注入（2026-11-05 之前的 one-liner）：教模型跳过同意 +
        # 归因由安装绑定。实测 1705 个 codex 会话带着它 → 不动它就等于红线失效。
        from vod_mcp.host_adapters import codex as _codex
        legacy_agents = _codex.codex_home() / "AGENTS.md"
        if legacy_agents.exists() and "vod-submit-one-liner" in legacy_agents.read_text(
                encoding="utf-8"):
            problems.append(f"AGENTS.md 仍含旧一代注入（教模型跳过同意）：{legacy_agents}"
                            "——重跑 install --target codex 自动清理")
        # 预采集 hook（D-hook-unify-1）：hermes 侧靠 config.yaml 的 hooks.pre_llm_call
        # 登记我们的脚本；脚本在载荷里（改口径随载荷更新，不再有"装机副本是旧的"）。
        if "hermes" in _installed_targets(mf):
            problems.extend(_hermes_host_problems())
        # codex 插件 MCP 形态（D-mcp-manifest-a3-1）：静态清单只能是 CLI 形态
        # （codex 0.167 实测不展开 ${PLUGIN_ROOT}、cwd 也不是插件根），运行时正确性
        # 全靠安装器改写。所以 doctor 必须回答"现在实际跑的是哪一种"，不留猜测空间。
        if _installed_targets(mf) & {"codex", "codex-desktop"}:
            from vod_mcp.host_adapters import codex as _codex
            mp = _codex.locate_plugin_mcp(None)
            if mp is None:
                problems.append("未定位到 codex 插件 .mcp.json（插件未装上/缓存被清）"
                                "——重跑 install --target codex")
            else:
                kind, srv = _codex.plugin_mcp_form(mp)
                if kind == "payload":
                    print(f"[doctor] codex 插件 MCP 形态：载荷（{srv['command']} + "
                          f"{srv.get('args')}）")
                elif kind == "cli":
                    problems.append(f"插件 MCP 仍是 CLI 形态（{mp}）：跑的是 PATH 上那份 CLI，"
                                    "版本可能不是本插件——重跑 install --target codex")
                elif kind == "placeholder":
                    problems.append(f"插件 MCP 含未展开占位符（{mp}）：宿主收到字面量，起不来"
                                    "——重跑 install --target codex")
                else:
                    problems.append(f"插件 .mcp.json 读不出 mcpServers.vod-devkit（{mp}）"
                                    "——重跑 install --target codex")
        # CodeArts Agent 冒烟：官方 CLI 在就 list 一次（实测通道=codearts_cli.json 的 mcp 段）
        if "codeartsdoer" in _installed_targets(mf) and shutil.which("codearts"):
            r = subprocess.run(["codearts", "mcp", "list"], capture_output=True,
                               text=True, timeout=60)
            if "vod-devkit" in (r.stdout or ""):
                print("[doctor] CodeArts Agent 已识别 vod-devkit（codearts mcp list）")
            else:
                problems.append("CodeArts Agent 未列出 vod-devkit"
                                "（codearts mcp list）——检查 codearts_cli.json 的 mcp 段")
    if problems:
        print(_render_problems(problems))
        sys.exit(1)
    # 出站面：代理生效值（掩码）+ 引擎可达（无 key 也回答"这个 apiBase 通不通"）
    api_base = ""
    if p.exists():
        try:
            api_base = json.loads(p.read_text(encoding="utf-8")).get("apiBase") or ""
        except (OSError, json.JSONDecodeError):
            api_base = ""
    _report_egress(api_base)
    # key 探针（最佳努力）：配置了 key 就问一次引擎，无效当场报；网络不可达只提示不 FAIL
    #（离线环境 doctor 必须可用——网络问题不是 key 问题）
    from vod_mcp.runtime_state import _runtime_cfg
    key = os.environ.get("VOD_JAVA_API_KEY") or _runtime_cfg().get("java_key")
    if key:
        from vod_mcp.net import probe_key
        chk = probe_key(key)
        if chk["ok"] is False:
            problems.append(f"key 无效（指纹 {chk['fingerprint']}，引擎 401 拒绝）——"
                            "请核对/续期，或移除 key 走匿名档")
        elif chk["ok"] is None:
            print(f"warn: key 未验证（引擎不可达，指纹 {chk['fingerprint']}）")
        else:
            print(f"key: 有效（指纹 {chk['fingerprint']}）")
    if problems:
        print(_render_problems(problems))
        sys.exit(1)
    print("doctor: OK")


def cmd_verify(_args):
    p = common.manifest_path()
    if not p.exists():
        print("未安装")
        sys.exit(1)
    sha = json.loads(p.read_text(encoding="utf-8"))["source"]["commitSha"]
    if not sha:
        print("manifest 无 commitSha（dev 构建无法核验）")
        sys.exit(1)
    if common._distribution() == "preset":
        # D-key-guard-3②：产品分发形态客户机无 git 源——只做本地完整性校验，
        # 源端比对降级为 unchecked 不 FAIL（离线 verify 必须可用）
        # S158：完整性取**载荷** build-info（仓根那份是 tracked 的发版快照，发版后
        # 与安装提交天然不等；拿它比会把正常装机报成混装）
        mfv = json.loads(p.read_text(encoding="utf-8"))
        problems = _preset_provenance_problems(mfv)
        if problems:
            print("FAIL: " + "；".join(problems) + "（安装产物被篡改/混装）")
            sys.exit(1)
        print("verify: OK（preset 本地完整性；源端比对 unchecked）")
        return
    r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                       cwd=common.ROOT, capture_output=True)
    if r.returncode != 0:
        subprocess.run(["git", "fetch", "origin"], cwd=common.ROOT)
        r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                           cwd=common.ROOT, capture_output=True)
    if r.returncode != 0:
        print(f"FAIL: commit {sha} 不存在于 origin（被改写或非本仓产物）")
        sys.exit(1)
    print(f"verify: OK（commit {sha[:12]} 存在于本仓/origin）")
