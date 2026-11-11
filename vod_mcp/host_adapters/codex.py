"""Codex 宿主适配（D-codex-agents-1 终态）：原生插件路径 + 历史遗留清理。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import ROOT

HOST = "codex"
SUPPORTS_REMOTE = True
_AGENTS_MARKER_BEGIN = "<!-- vod-devkit:feedback-skill BEGIN -->"
# 更早一代注入（2026-11-05 之前）：AGENTS.md 里教模型"立即提交 confirmed=true、
# 不要追问、归因由安装绑定"——与现行红线（先征得同意、归因从原话解析）矛盾，
# 且 1705 个历史会话带着它跑（实测）。清理逻辑必须认这个标记，否则残留继续生效。
_LEGACY_ONE_LINER = "<!-- vod-submit-one-liner -->"
_AGENTS_MARKER_END = "<!-- vod-devkit:feedback-skill END -->"
_SPEC = host_specs.load("codex")


def skills_dir(args):
    d = _SPEC.get("skillsDir")
    return Path(d) if d else None


def strip_codex_vod_blocks(text: str) -> str:
    """幂等剥离：删除 [mcp_servers.vod-devkit] **及其全部子表**。

    不能用行内正则截断式剥离——args = ["…"] 行内的 '[' 会让正则提前断块。
    也不能只删父表（旧实现）：留下 [mcp_servers.vod-devkit.env] 在 TOML
    语义里会重建父表，装出一个没有 command 的假 server。扫描/删除语义
    统一在 vod_mcp/config_forms.py（单一实现），形态不受支持时抛
    RuntimeError——调用方必须原样放弃修改。
    """
    from vod_mcp import config_forms as cf
    try:
        verdict, reason = cf.classify_codex_toml(text)
    except cf.Refused as e:
        raise RuntimeError(f"codex config.toml 形态不受支持：{e}") from e
    if verdict == "refuse":
        raise RuntimeError(f"codex config.toml 形态不受支持：{reason}")
    cleaned, _removed = cf.strip_managed_toml(text)
    return cleaned


def strip_legacy_one_liner(text: str) -> tuple:
    """剥离旧一代 one-liner 注入块 → (new_text, changed)。

    边界取法（宁可少删不可误删）：从标记行删到下一个 `<!--` 标记 / 一级标题 `# ` /
    `---` 分隔线；都没有则删到 EOF。绝不动用户的其它 markdown 段。
    """
    lines = text.splitlines()
    idx = next((i for i, ln in enumerate(lines) if ln.strip() == _LEGACY_ONE_LINER), None)
    if idx is None:
        return text, False
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("<!--") or s.startswith("# ") or s == "---":
            end = j
            break
    out = lines[:idx] + lines[end:]
    return "\n".join(out).rstrip() + ("\n" if out else ""), True


def strip_agents_vod_block(text: str) -> str:
    """幂等剥离 AGENTS.md 中带标记的 vod-devkit 技能块（历史方案清理）。

    P2（深审 2026-11-06）：只有 BEGIN 没有 END 时不得静默吞掉文件剩余
    全部内容——抛错拒绝（调用方 exit 2 不落盘），宁可装不上不可删用户文件。
    """
    lines, skipping, out = text.splitlines(), False, []
    for line in lines:
        if line.strip() == _AGENTS_MARKER_BEGIN:
            skipping = True
            continue
        if line.strip() == _AGENTS_MARKER_END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    if skipping:
        raise RuntimeError(
            "AGENTS.md 存在 vod-devkit BEGIN 标记但缺失 END 标记"
            "（文件可能被手动截断）——拒绝自动清理，请手动检查该文件")
    return "\n".join(out).rstrip()


def install(args, packs: str) -> Path:
    """Codex（D-codex-agents-1 终态）：原生插件路径——
    codex plugin marketplace add <仓>/plugins + plugin add vod-devkit@vod-local，
    打包 skills（渐进式按需加载的采集工作流）+ .mcp.json（vod-devkit serve）。
    历史遗留清理：旧 config.toml [mcp_servers.vod-devkit] 段与 AGENTS.md 技能块
    一并移除（与原生插件同名会双注册；AGENTS.md 方案被原生 skill 取代）。
    前置：codex CLI 与 vod-devkit 命令在 PATH（npm i -g vod-devkit ≥0.1.12）。"""
    codex = shutil.which("codex")
    if not codex:
        print("[vod-devkit] 未找到 codex CLI，无法走原生插件安装", file=sys.stderr)
        sys.exit(2)
    spec = host_specs.load("codex")
    conf = Path(spec["configPath"])
    if conf.exists():  # 历史遗留：config.toml MCP 段与插件同名=双注册，移除
        text = conf.read_text(encoding="utf-8")
        try:
            cleaned = strip_codex_vod_blocks(text)
        except RuntimeError as e:
            # 形态守卫：非已知形态宁可不装——改坏用户整份 codex 配置的代价
            # 远高于装不上（字节未动）
            print(f"[vod-devkit] {e}。安装中止，未改动该文件。", file=sys.stderr)
            sys.exit(2)
        if cleaned != text.rstrip():
            conf.write_text(cleaned + "\n", encoding="utf-8")
            print(f"已移除旧 config.toml MCP 段（原生插件取代）：{conf}")
    agents = Path.home() / ".codex" / "AGENTS.md"
    if agents.exists():  # 历史遗留：AGENTS.md 技能块已被原生 skill 取代
        text = agents.read_text(encoding="utf-8")
        cleaned = text
        if _LEGACY_ONE_LINER in cleaned:
            # 旧一代 one-liner（"立即提交/不要追问/归因由安装绑定"）必须清掉：
            # 它是 consent 红线的真实破口（实测 1705 个历史会话带着它跑）
            import datetime as _dt
            bak = agents.with_name(f"AGENTS.md.bak-{_dt.datetime.now():%Y%m%d%H%M%S}")
            bak.write_text(text, encoding="utf-8")
            cleaned, _ = strip_legacy_one_liner(cleaned)
            print(f"已移除旧 AGENTS.md one-liner 注入（备份 {bak.name}）：{agents}")
        try:
            cleaned = strip_agents_vod_block(cleaned)
        except RuntimeError as e:
            print(f"[vod-devkit] {e}", file=sys.stderr)
            sys.exit(2)
        if cleaned.strip() == "":
            agents.unlink()          # 整份都是我们的注入 → 文件本身也不留
            print(f"已删除空的 AGENTS.md（内容全为旧注入）：{agents}")
        elif cleaned != text.rstrip():
            agents.write_text(cleaned + "\n", encoding="utf-8")
            print(f"已移除旧 AGENTS.md 技能块（原生 skill 取代）：{agents}")
    mp_root = ROOT / "plugins"

    def _run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} → {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout

    mp_name = "vod-local"
    # devkit 卫生实践：stale cache 先清——codex 插件缓存不自动失效，不清则
    # 重装/升级后旧版本残留（marketplace 指向与 cache 内容漂移）
    for stale in (Path.home() / ".codex" / "plugins" / "marketplaces" / mp_name,
                  Path.home() / ".codex" / "plugins" / "cache" / mp_name):
        if stale.exists():
            shutil.rmtree(stale)
            print(f"已清理 stale 插件缓存：{stale}")
    ml = subprocess.run([codex, "plugin", "marketplace", "list"], capture_output=True, text=True, timeout=120).stdout
    if mp_name not in ml:
        _run([codex, "plugin", "marketplace", "add", str(mp_root)])
        print(f"已注册本地 marketplace：{mp_root}")
    _run([codex, "plugin", "add", f"vod-devkit@{mp_name}"])
    print("已安装 codex 原生插件 vod-devkit（skills + MCP，重启 Codex 会话生效）")
    # P1-5（深审 2026-11-06）：插件自带的 .mcp.json 硬编码 env.VOD_PACKS=
    # core,collect——--packs 对 codex 半失效（运行期仍注册 collect 工具）。
    # plugin add 后把缓存内 .mcp.json 的 packs 对齐本次安装值。
    import glob as _glob
    mcp_jsons = sorted(
        _glob.glob(str(Path.home() / ".codex" / "plugins" / "cache"
                       / mp_name / "vod-devkit" / "*" / ".mcp.json")),
        key=lambda p: Path(p).stat().st_mtime, reverse=True)
    if mcp_jsons:
        try:
            mj = json.loads(Path(mcp_jsons[0]).read_text(encoding="utf-8"))
            srv = mj.get("mcpServers", {}).get("vod-devkit")
            if srv is not None:
                srv.setdefault("env", {})["VOD_PACKS"] = packs
                Path(mcp_jsons[0]).write_text(
                    json.dumps(mj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                print(f"已对齐插件 MCP packs：{mcp_jsons[0]}（VOD_PACKS={packs}）")
        except Exception as e:
            print(f"[vod-devkit] warn: 插件 .mcp.json packs 对齐失败（{e}）——"
                  "运行期熔断门禁仍会兜底", file=sys.stderr)
        return Path(mcp_jsons[0])
    # 深审 P0-3：绝不再返回 ~/.codex/config.toml——它是用户整份 codex 配置，
    # uninstall 对 mcpConfig 是删除语义，指向它=卸载删光用户配置（破坏性）
    print("[vod-devkit] warn: 未定位到插件 .mcp.json（uninstall 将跳过 MCP 清理，"
          "可手动删除插件缓存目录）", file=sys.stderr)
    return None


def install_remote(args, url, token):
    """codex mcp add --url + --bearer-token-env-var（token 由用户环境提供）。"""
    codex = shutil.which("codex")
    if not codex:
        print("[vod-devkit] 未找到 codex CLI，无法走远程注册", file=sys.stderr)
        sys.exit(2)
    r = subprocess.run([codex, "mcp", "add", "vod-devkit", "--url", url,
                        "--bearer-token-env-var", "VOD_MCP_TOKEN"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"[vod-devkit] codex mcp add（remote）失败：{(r.stderr or r.stdout).strip()[-200:]}",
              file=sys.stderr)
        sys.exit(1)
    stale = Path.home() / ".codex" / "plugins"
    if stale.exists():
        print("提示：codex 若曾用插件形态安装过 vod-devkit，请先 "
              "`codex plugin remove vod-devkit@vod-local` 避免双注册（stdio 插件 .mcp.json "
              "与本次 remote 配置同名）", file=sys.stderr)
    print(f"已注册 Codex 远程 MCP（{url}）。token 由环境变量 VOD_MCP_TOKEN 提供：\n"
          f"  export VOD_MCP_TOKEN=<你的 key>（写入 shell 配置或宿主 env）")
    return None
