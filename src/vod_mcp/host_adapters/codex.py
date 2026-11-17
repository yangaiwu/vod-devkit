"""Codex 宿主适配（D-codex-agents-1 终态）：原生插件路径 + 历史遗留清理。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import paths as _paths
from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters.base import ROOT, server_env, server_entry

HOST = "codex"


def codex_home() -> Path:
    """codex 家目录（CODEX_HOME 优先，S177）。

    宿主自己认的是 CODEX_HOME；写死 `Path.home()/.codex` 时设了变量的机器上会出现
    「配置写给我们以为的落点、宿主读另一处」，且 doctor/巡检读同一份错落点，自洽地错。
    """
    from vod_mcp import paths
    return paths.host_home("CODEX_HOME", ".codex")


_codex_home = codex_home   # 兼容内部旧叫法
SUPPORTS_REMOTE = True
_AGENTS_MARKER_BEGIN = "<!-- vod-devkit:feedback-skill BEGIN -->"
# 更早一代注入（2026-11-05 之前）：AGENTS.md 里教模型"立即提交 confirmed=true、
# 不要追问、归因由安装绑定"——与现行红线（先征得同意、归因从原话解析）矛盾，
# 且 1705 个历史会话带着它跑（实测）。清理逻辑必须认这个标记，否则残留继续生效。
_LEGACY_ONE_LINER = "<!-- vod-submit-one-liner -->"
_AGENTS_MARKER_END = "<!-- vod-devkit:feedback-skill END -->"
_SPEC: dict | None = None


def _spec() -> dict:
    """调用期解析宿主配置（模块 import 期读 integrations/ 会在载荷副本里炸）。

    2026-11-12 实锤：载荷副本不含 integrations/，import 期 host_specs.load("codex")
    直接 KeyError → 远程面每个请求 500。宿主配置只在 install 期用得上，运行期
    server 不需要它。
    """
    global _SPEC
    if _SPEC is None:
        _SPEC = host_specs.load("codex")
    return _SPEC


def skills_dir(args):
    d = _spec().get("skillsDir")
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


def locate_plugin_mcp(mp_name: str | None = "vod-local"):
    """定位 codex 插件缓存里的 .mcp.json（最近写入的那份）。找不到返回 None。

    mp_name=None 时扫所有 marketplace（doctor 用：装机实例的 marketplace 名可能是
    `personal`/`vod-local` 等，按名找会漏）。
    """
    import glob as _glob
    mkt = mp_name or "*"
    hits = sorted(
        _glob.glob(str(_codex_home() / "plugins" / "cache"
                       / mkt / "vod-devkit" / "*" / ".mcp.json")),
        key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return Path(hits[0]) if hits else None


def plugin_mcp_form(mcp_path) -> tuple:
    """判定装机清单的**实际生效形态**，给 doctor 报，别让人猜。

    三类（顺序即优先级）：
        ("payload", srv)    —— command 是绝对路径：版本正确（我们改写成功）
        ("placeholder", srv)—— args 含未展开的 ${...}：宿主收到字面量，起不来
        ("cli", srv)        —— command 是裸 CLI 名：跑的是 PATH 上那份，版本不确定
        ("unreadable", None)—— 读不出 mcpServers.vod-devkit
    """
    p = Path(mcp_path)
    try:
        srv = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["vod-devkit"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return ("unreadable", None)
    args = srv.get("args") or []
    if any("${" in str(a) for a in args):
        return ("placeholder", srv)
    cmd = str(srv.get("command") or "")
    if "/" in cmd or "\\" in cmd:
        return ("payload", srv)
    return ("cli", srv)


class PluginMcpRewriteError(RuntimeError):
    """插件 .mcp.json 改写失败，按 kind 分类（安装器据此决定 warn 还是 fail）。

    kind:
      bad-json     —— 缓存内文件不是合法 JSON / 缺 mcpServers.vod-devkit（上游格式变更或人工改过）
      not-writable —— 读写抛 OSError（只读挂载 / 权限）
    这两类都**不该**把整个安装判死：插件自带的静态形态（`python3` +
    `${PLUGIN_ROOT}/vod_mcp/server.py`）本身就能跑，只是解释器版本靠 PATH。
    """

    REMEDY = {
        "bad-json":
            "缓存内 .mcp.json 结构不符（codex 换了 Agent Plugins 解析形态，或该文件被改过）。"
            "静态形态仍可运行；要改成载荷形态请删插件缓存重装，或改走 "
            "`vod-devkit install --target generic --mcp-config <file>` 手写条目。",
        "not-writable":
            "插件缓存目录不可写（只读挂载/权限）。静态形态仍可运行；若机器上 PATH 的 "
            "python3 < 3.10，请把该文件 command 指向 3.10+ 解释器绝对路径（安装器无法代写）。",
    }

    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def rewrite_plugin_mcp(mcp_path, python: str = "", entry: str = "", env: dict | None = None) -> dict:
    """把插件自带 .mcp.json 改写成「绝对解释器 + 载荷副本」，并**读回验证**。

    为什么必须读回（2026-11-12 矩阵实锤的后续）：写成功 ≠ 落盘就是我们要的
    形态——并发改写（宿主升级、另一次安装）会把它改回去，而宿主只会静默跑
    改回去的那份。所以写完再解析一次，逐字段比对。

    失败语义分三层，安装器按层处置：
      - PluginMcpRewriteError（bad-json / not-writable）→ warn + 分类补救指引，安装继续
      - RuntimeError（读回与期望不一致）→ 安装失败（半写状态不能留给宿主）
      - 正常 → 返回读回的 server 条目
    """
    python = python or sys.executable
    entry = entry or server_entry()
    want_env = dict(env or {})
    path = Path(mcp_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PluginMcpRewriteError("not-writable", f"{path}: {e}") from e
    try:
        mj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PluginMcpRewriteError("bad-json", f"{path}: {e.msg}") from e
    servers = mj.get("mcpServers") if isinstance(mj, dict) else None
    if not isinstance(servers, dict):
        raise PluginMcpRewriteError("bad-json", f"{path} 缺 mcpServers 对象")
    srv = servers.get("vod-devkit")
    if not isinstance(srv, dict):
        raise PluginMcpRewriteError("bad-json", f"{path} 缺 mcpServers.vod-devkit")
    srv["command"] = python
    srv["args"] = [entry]
    merged = dict(srv.get("env") or {})
    merged.update(want_env)
    srv["env"] = merged
    try:
        _paths.atomic_write_text(path, json.dumps(mj, ensure_ascii=False, indent=2) + "\n")
    except OSError as e:
        raise PluginMcpRewriteError("not-writable", f"{path}: {e}") from e
    try:
        back = json.loads(path.read_text(encoding="utf-8"))
        got = back["mcpServers"]["vod-devkit"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise RuntimeError(f"改写后读回失败（{path}）：{e}") from e
    if got.get("command") != python or got.get("args") != [entry]:
        raise RuntimeError(
            f"改写后验证不通过（{path}）：期望 {(python, [entry])}，"
            f"读回 {(got.get('command'), got.get('args'))}——可能有并发改写该文件")
    got_env = got.get("env") or {}
    missing = {k: v for k, v in want_env.items() if got_env.get(k) != v}
    if missing:
        raise RuntimeError(f"改写后验证不通过（{path}）：env 未落全 {missing}")
    return got


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
    spec = _spec()
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
            _paths.atomic_write_text(conf, cleaned + "\n")
            print(f"已移除旧 config.toml MCP 段（原生插件取代）：{conf}")
    agents = _codex_home() / "AGENTS.md"
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
            _paths.atomic_write_text(agents, cleaned + "\n")
            print(f"已移除旧 AGENTS.md 技能块（原生 skill 取代）：{agents}")
    mp_root = ROOT / "plugins"
    # 插件副本是生成物（v0.5.9 起零提交，见 .gitignore）。仓内直跑安装时若还没生成，
    # 这里补一次——否则 codex 只会报“marketplace 里找不到 vod-devkit”，看不出是没 sync。
    if not (mp_root / "vod-devkit" / "vod_mcp").is_dir():
        _sync = ROOT / "scripts" / "sync_plugin.py"
        if _sync.is_file():
            r = subprocess.run([sys.executable, str(_sync), "--no-build-info"], cwd=ROOT,
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                print(f"[vod-devkit] 生成插件副本失败：{r.stderr[-300:]}", file=sys.stderr)
                sys.exit(2)
            print("已生成插件副本（scripts/sync_plugin.py）")
        else:
            print(f"[vod-devkit] 插件副本缺失：{mp_root / 'vod-devkit'}（npm 包损坏？）", file=sys.stderr)
            sys.exit(2)

    def _run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} → {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout

    mp_name = "vod-local"
    # devkit 卫生实践：stale cache 先清——codex 插件缓存不自动失效，不清则
    # 重装/升级后旧版本残留（marketplace 指向与 cache 内容漂移）
    for stale in (_codex_home() / "plugins" / "marketplaces" / mp_name,
                  _codex_home() / "plugins" / "cache" / mp_name):
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
    # plugin add 后把缓存内 .mcp.json 改写成「绝对解释器 + 载荷副本」并做
    # 读回验证（静态形态是 `python3` + ${PLUGIN_ROOT}，解释器版本靠 PATH；
    # 改写解决的是解释器选择，载荷锚定已由 ${PLUGIN_ROOT} 解决）。
    mcp_path = locate_plugin_mcp(mp_name)
    if mcp_path is not None:
        try:
            rewrite_plugin_mcp(mcp_path, python=sys.executable,
                               entry=server_entry(), env=server_env(args, packs))
        except PluginMcpRewriteError as e:
            # 分类处置：改不了缓存文件不等于装不上（静态形态本身能跑），
            # 但必须说清是哪一类 + 怎么补救，不笼统 catch 后 exit 1。
            print(f"[vod-devkit] warn({e.kind}): 插件 MCP 未改写成载荷形态：{e.detail}",
                  file=sys.stderr)
            print(f"[vod-devkit] 补救：{PluginMcpRewriteError.REMEDY.get(e.kind, '见 INSTALL.md')}",
                  file=sys.stderr)
        except RuntimeError as e:
            # 读回与期望不一致 = 留了半写状态给宿主，这类必须让安装失败
            print(f"[vod-devkit] 安装失败：{e}", file=sys.stderr)
            sys.exit(2)
        else:
            print(f"已对齐插件 MCP（解释器 + 载荷副本 + packs）：{mcp_path}"
                  f"（VOD_PACKS={packs}）")
        return mcp_path
    # 深审 P0-3：绝不再返回 ~/.codex/config.toml——它是用户整份 codex 配置，
    # uninstall 对 mcpConfig 是删除语义，指向它=卸载删光用户配置（破坏性）
    print("[vod-devkit] warn: 未定位到插件 .mcp.json（uninstall 将跳过 MCP 清理，"
          "可手动删除插件缓存目录）", file=sys.stderr)
    return None


def install_remote(args, url, token):
    """codex mcp add --url [+ --bearer-token-env-var]（token 由用户环境提供）。

    token 可选（D-token-machine-1）：给了才加 --bearer-token-env-var；
    没给就不带 Bearer，由远程 server 用机器级匿名令牌提交。
    """
    codex = shutil.which("codex")
    if not codex:
        print("[vod-devkit] 未找到 codex CLI，无法走远程注册", file=sys.stderr)
        sys.exit(2)
    cmd = [codex, "mcp", "add", "vod-devkit", "--url", url]
    if token:
        cmd += ["--bearer-token-env-var", "VOD_MCP_TOKEN"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"[vod-devkit] codex mcp add（remote）失败：{(r.stderr or r.stdout).strip()[-200:]}",
              file=sys.stderr)
        sys.exit(1)
    stale = _codex_home() / "plugins"
    if stale.exists():
        print("提示：codex 若曾用插件形态安装过 vod-devkit，请先 "
              "`codex plugin remove vod-devkit@vod-local` 避免双注册（stdio 插件 .mcp.json "
              "与本次 remote 配置同名）", file=sys.stderr)
    print(f"已注册 Codex 远程 MCP（{url}）。" + (
        "token 由环境变量 VOD_MCP_TOKEN 提供：\n  export VOD_MCP_TOKEN=<你的 key>（写入 shell 配置或宿主 env）"
        if token else "未带 token：提交走远程 server 侧的机器级匿名令牌（同机部署默认形态）"))
    return None
