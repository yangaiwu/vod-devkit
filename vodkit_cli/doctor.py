"""诊断类子命令：status / doctor / verify / explain / detect。"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vodkit_cli import common, remote


def cmd_status(_args):
    p = common.manifest_path()
    if not p.exists():
        print("未安装（无 install-manifest）")
        sys.exit(1)
    # golden 稳定性：apiBase 含安装期动态值（本地验证实例端口），归一化后输出
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'"apiBase": "http://127\.0\.0\.1:\d+"',
                  '"apiBase": "http://127.0.0.1:<PORT>"', text)
    # 载荷路径含 HOME/版本，按 <PAYLOAD> 归一（golden 不随环境漂）
    text = re.sub(r'"payloadDir": ".*?/payloads/[^"]+"',
                  '"payloadDir": "<PAYLOAD>"', text)
    print(text)


def _repair_dsh_patch_block(mf: dict) -> str | None:
    """doctor 自愈（S58/A）：profile cordis.patch.yml 的 vod-devkit 块缺失或
    打平（未缩进在 - insert: 之下）时，按 manifest 的 product/apiBase 重建
    正确嵌套块。返回修复的文件路径；块完好返回 None。

    嵌套铁律（真机实锤）：id/name/config 必须缩进在 `- insert:` 之下——
    dsh 的配置序列化只保留它能识别的块，手工游离块会被下次写盘冲掉。
    """
    prof = mf["dshProfile"]
    patch = Path(host_specs.load("dsh", prof)["configPath"])
    if not patch.exists():
        return None
    from vod_mcp import config_forms as cf
    lines = patch.read_text(encoding="utf-8").splitlines()
    try:
        verdict, reason = cf.classify_dsh_patch(lines)
    except cf.Refused as e:
        verdict, reason = "refuse", str(e)
    if verdict == "refuse":
        # 自愈也不越界：文件形态未知时只报告，不动字节
        print(f"[doctor] skip（cordis.patch.yml 形态不受支持，未自愈）：{reason}",
              file=sys.stderr)
        return None
    vod_idx = next((i for i, ln in enumerate(lines)
                    if ln.strip().startswith("- id: vod-devkit")), None)
    if vod_idx is not None and lines[vod_idx].startswith((" ", "\t")):
        # 已嵌套且在 insert 组内（简化判定：缩进+前文存在 - insert: 行）→ 完好
        has_insert = any(ln.strip() == "- insert:" for ln in lines[:vod_idx])
        has_name = any("name: dsh-vod-devkit" in ln
                       for ln in lines[vod_idx:vod_idx + 3])
        if has_insert and has_name:
            return None
    # 需要重建：先摘除旧块（块边界=下一个 `- ` 群组项，任何缩进），再追加正确嵌套组
    if vod_idx is not None:
        end = next((j for j in range(vod_idx + 1, len(lines))
                    if lines[j].strip().startswith("- ")), len(lines))
        del lines[vod_idx:end]
    if lines and lines[-1].strip():
        lines.append("")
    product = mf.get("product") or ""
    api_base = mf.get("apiBase") or ""
    lines += [
        "- insert:",
        "    - id: vod-devkit",
        "      name: dsh-vod-devkit",
        "      config:",
        f"        product: {product}",
        f"        apiBase: {api_base}",
        f"        uiBase: {api_base}",  # D-uiBase-direct：浏览器半直连，与 install 同口径
    ]
    patch.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return str(patch)


def _render_problems(problems) -> str:
    """分层报告（对表 devkit 的 doctor-report）：按 环境/载荷/配置/技能/网络/插件 分组，
    每条失败给「原因」与「动作」，避免运维只看到一堆 FAIL 文案。"""
    from vod_mcp import diagnose
    return diagnose.render_problems(problems)


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


def cmd_doctor(_args):
    problems = []
    p = common.manifest_path()
    if not p.exists():
        problems.append("无 install-manifest.json（未 install？）")
    else:
        mf = json.loads(p.read_text(encoding="utf-8"))
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
        # 路由插件副本（hermes）：仓内话术改了但装机副本没刷新 → 宿主还在注入旧口径
        # （2026-11-11 实锤：仓里已把"归因由安装绑定决定"改成"原话解析"，装机副本仍是旧的）
        rp_dst = Path.home() / ".hermes" / "plugins" / "vod-feedback-router" / "router.py"
        rp_src = common.ROOT / "hermes-plugin" / "vod-feedback-router" / "router.py"
        if rp_dst.exists() and rp_src.exists() and rp_dst.read_text(encoding="utf-8") != \
                rp_src.read_text(encoding="utf-8"):
            problems.append(f"路由插件副本落后于仓内：{rp_dst}（重跑 install --target hermes）")
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
