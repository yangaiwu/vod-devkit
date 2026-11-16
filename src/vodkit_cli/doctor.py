"""诊断类子命令：status / doctor / verify / explain / detect。"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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
        rows = mf.get("installs") or ([mf] if mf.get("target") else [])
        hit = next((r for r in rows if r.get("target") == target), None)
        if hit is None:
            print(f"没有该宿主的安装记录：{target}"
                  f"（现有：{', '.join(r.get('target','?') for r in rows) or '无'}）")
            sys.exit(1)
        print(json.dumps(hit, ensure_ascii=False, indent=2))
        return
    # golden 稳定性：apiBase 含安装期动态值（本地验证实例端口），归一化后输出
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'"apiBase": "http://127\.0\.0\.1:\d+"',
                  '"apiBase": "http://127.0.0.1:<PORT>"', text)
    # 载荷路径含 HOME/版本，按 <PAYLOAD> 归一（golden 不随环境漂）
    text = re.sub(r'"payloadDir": ".*?/payloads/[^"]+"',
                  '"payloadDir": "<PAYLOAD>"', text)
    print(text)


def _repair_dsh_patch_block(mf: dict) -> str | None:
    """doctor 自愈（S58/A + B 模式 D-dsh-mcp-b-1）：profile 的 vod-devkit 块缺失/打平/
    形态与当前环境不符时，按 manifest 重建。

    关键（0.5.15 真机实锤）：重建必须**复用安装器的 `_patch_block`**——有 mcp-client 就写
    `vod-devkit-mcp` + 壳两条 insert（壳 `registerTools:false`）。旧实现手写"只有壳块"的
    形态，doctor 跑一次就把 MCP 工具面打回 6 工具降级（headless 的 vod-devkit-mcp 被抹掉，
    audit 从"MCP 模式 PASS"变成"降级 PASS"）——自愈不能改变形态。

    嵌套铁律（真机实锤）：id/name/config 必须缩进在 `- insert:` 之下。
    """
    prof = mf["dshProfile"]
    patch = Path(host_specs.load("dsh", prof)["configPath"])
    if not patch.exists():
        return None
    from vod_mcp import config_forms as cf
    from vod_mcp.host_adapters import dsh as _dsh
    text = patch.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        verdict, reason = cf.classify_dsh_patch(lines)
    except cf.Refused as e:
        verdict, reason = "refuse", str(e)
    if verdict == "refuse":
        # 自愈也不越界：文件形态未知时只报告，不动字节
        print(f"[doctor] skip（cordis.patch.yml 形态不受支持，未自愈）：{reason}",
              file=sys.stderr)
        return None

    dsh_cli = shutil.which("dsh")
    mcp_ver = _dsh._mcp_client_version(_dsh._dsh_root(dsh_cli)) if dsh_cli else None
    payload = Path(str(mf.get("payloadDir") or ""))
    args = SimpleNamespace(product=mf.get("product") or "",
                           java_api_base=mf.get("apiBase") or "")
    expected = _dsh._patch_block(args, mcp_ver, payload, str(mf.get("packs") or "core"))
    if expected in text:
        # 已是安装器该写的样子（有 mcp 块 + 壳 registerTools:false，或降级形态）→ 不动
        return None
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
        rows = mf.get("installs") or ([mf] if mf.get("target") else [])
        if rows:
            row_names = ", ".join(r.get("target", "?") for r in rows)
            if target:
                hit = next((r for r in rows if r.get("target") == target), None)
                if hit is None:
                    problems.append(f"没有该宿主的安装记录：{target}（现有：{row_names}）")
                else:
                    # --target：把该行的字段覆盖到视图上，检查按这一行走
                    mf = {**mf, **{k: v for k, v in hit.items() if v is not None}}
                    print(f"[doctor] 检查安装行：{target}")
            elif len(rows) > 1:
                # 缺省视图=最近一次安装（顶层字段即最后一次写入）；多行只在末尾列出，
                # 要看单个宿主用 --target（避免在多宿主上把"某一行的问题"说成全局）
                print(f"[doctor] 安装行: {row_names}（--target <agent> 选择单个）")
        # dsh patch 块自愈（S58/A 止血，2026-11-06 真机实锤）：dsh 运行时
        # 序列化会冲掉 profile patch 里的 vod 块（配置树不含手工块）——
        # doctor 检测缺失/打平后按 manifest 的 product/apiBase 重建嵌套块
        if mf.get("target") == "dsh" and mf.get("dshProfile"):
            patched = _repair_dsh_patch_block(mf)
            if patched:
                print(f"[doctor] 已重建 dsh patch 的 vod-devkit 块：{patched}"
                      "（重启 dsh 生效）")
        bi = json.loads((common.ROOT / "build-info.json").read_text(encoding="utf-8"))
        if mf["source"]["commitSha"] != bi.get("commitSha"):
            problems.append("install-manifest 与 build-info 的 commitSHA 不一致")
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
        # 的 server.py 路径消失（白屏/工具全失），所以只报"谁在用哪份、哪份没人引用"，
        # 清理由人决定。真机实锤：机器上同时躺着 0.5.9/0.5.10/0.5.11 三份。
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            all_rows = raw.get("installs") or ([raw] if raw.get("target") else [])
            used = {}
            for r in all_rows:
                d = (r.get("payloadDir") or "").strip()
                if d:
                    used.setdefault(str(Path(d)), []).append(str(r.get("target")))
            if used:
                parent = Path(next(iter(used))).parent
                if parent.is_dir():
                    orphans = sorted(x.name for x in parent.iterdir()
                                     if x.is_dir() and str(x) not in used)
                    live = ", ".join(f"{Path(k).name}({'+'.join(v)})" for k, v in sorted(used.items()))
                    print(f"[doctor] 载荷：在用 {live}"
                          + (f"；未被任何安装行引用 {orphans}"
                             "（不自动删——确认没宿主配置指向后再 rm -rf）" if orphans else ""))
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
                    print(f"[doctor] 载荷已换（{pd}）——重启宿主会话生效")
        else:
            print("[doctor] 提示：本次安装无载荷副本（旧版），入口指向仓内路径；重跑 install 可固化")
        for res in _payload.residue():
            print(f"[doctor] 载荷残留（无 payload.json）：{res}——可手动删除")
        # 旧一代 AGENTS.md 注入（2026-11-05 之前的 one-liner）：教模型跳过同意 +
        # 归因由安装绑定。实测 1705 个 codex 会话带着它 → 不动它就等于红线失效。
        legacy_agents = Path.home() / ".codex" / "AGENTS.md"
        if legacy_agents.exists() and "vod-submit-one-liner" in legacy_agents.read_text(
                encoding="utf-8"):
            problems.append(f"AGENTS.md 仍含旧一代注入（教模型跳过同意）：{legacy_agents}"
                            "——重跑 install --target codex 自动清理")
        # 预采集 hook（D-hook-unify-1）：hermes 侧靠 config.yaml 的 hooks.pre_llm_call
        # 登记我们的脚本；脚本在载荷里（改口径随载荷更新，不再有"装机副本是旧的"）。
        if mf.get("target") == "hermes":
            from vod_mcp.host_adapters import hermes as _hermes
            cfg = Path(_hermes._profile_config())
            text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
            if _hermes.HOOK_MARK not in text:
                problems.append(f"预采集 hook 未注册（{cfg} 的 hooks.pre_llm_call）"
                                "——重跑 install --target hermes")
            if _hermes.GUARD_MARK not in text:
                problems.append(f"读 Key 拦截 hook 未注册（{cfg} 的 hooks.pre_tool_call）"
                                "——重跑 install --target hermes（技能里的"
                                "「只引指纹」靠它兜住 cat runtime.json）")
            if not _hermes._hook_script().exists():
                problems.append(f"hook 脚本缺失：{_hermes._hook_script()}"
                                "（载荷不含 hooks/ 的旧版本？重跑 install）")
            if not paths_mod.guard_script().exists():
                problems.append(f"读 Key 拦截脚本缺失：{paths_mod.guard_script()}"
                                "——重跑 install（或升级载荷）")
            if (Path.home() / ".hermes" / "plugins" / _hermes.LEGACY_PLUGIN).exists():
                problems.append("旧插件形态仍在（~/.hermes/plugins/vod-feedback-router）"
                                "= 与 hook 双份注入——重跑 install --target hermes 清理")
        # codex 插件 MCP 形态（D-mcp-manifest-a3-1）：静态清单只能是 CLI 形态
        # （codex 0.167 实测不展开 ${PLUGIN_ROOT}、cwd 也不是插件根），运行时正确性
        # 全靠安装器改写。所以 doctor 必须回答"现在实际跑的是哪一种"，不留猜测空间。
        if mf.get("target") == "codex":
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
        if mf.get("target") == "codeartsdoer" and shutil.which("codearts"):
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
        bi = json.loads((common.ROOT / "build-info.json").read_text(encoding="utf-8"))
        if sha != bi.get("commitSha"):
            print("FAIL: manifest 与 build-info commitSHA 不一致（安装产物被篡改/混装）")
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
