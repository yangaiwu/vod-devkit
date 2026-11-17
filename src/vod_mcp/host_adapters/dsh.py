"""DeepSeek Harness (dsh) 宿主适配：壳包 dsh-vod-devkit + profile patch 托管块。

D-dsh-mcp-b-1（2026-11-16，参照 huaweicloud-devkit 的成熟做法）：dsh 本体自带
`@deepseek-ai/dsh-mcp-client`，可把 python MCP server 挂成宿主工具（工具名
`mcp__vod-devkit__vod_*`，12 个工具 / 机器级 state / 两段式全在）。所以：

  ① 有 mcp-client → patch 里写**两条** insert 子项：mcp-client（工具面）+ 壳（只剩 UI 半，
     config 里 registerTools=false），整块用注释标记包裹（幂等替换、卸载只摘自己）；
  ② 无 mcp-client（版本门槛）→ 只写壳块（6 工具，降级形态，registerTools 缺省 true）。

MCP 模式暂只做 stdio；mcp-client 也支持 streamable-http（本机实测通），
SUPPORTS_REMOTE 仍是 False —— 远程 attach 单独一轮开，避免一次改两处语义。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs


HOST = "dsh"
SUPPORTS_REMOTE = False


def _dsh_root(dsh_cli: str) -> Path:
    """dsh 本体的安装根（`<root>/lib/...` 形态）；mcp-client 装在它的 node_modules 里，
    profile 的 node_modules 里没有——版本门槛必须按这个根探。"""
    return Path(os.path.realpath(dsh_cli)).parent.parent


def _mcp_client_version(dsh_root: Path) -> str | None:
    pkg = dsh_root / "node_modules" / "@deepseek-ai" / "dsh-mcp-client" / "package.json"
    if not pkg.is_file():
        return None
    try:
        return json.loads(pkg.read_text(encoding="utf-8")).get("version") or "unknown"
    except Exception:  # noqa: BLE001  坏包按不可用处理，降级而不是崩
        return None


def _registry_has(pkg: str, timeout: float = 10) -> bool:
    """registry 可达且该包存在。离线机器上先判这一步，再决定要不要跑 pnpm——
    直接把 `dsh plugin add` 甩出去会挂满 subprocess 超时（真机实锤 300s）才降级。"""
    try:
        r = subprocess.run(["npm", "view", pkg, "version", "--silent"],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0 and bool((r.stdout or "").strip())
    except Exception:      # noqa: BLE001  任何异常都按"不可达"处理（降级而非阻断）
        return False


def _ensure_mcp_client(dsh_cli: str, profile: str) -> str | None:
    """缺 mcp-client 时用 dsh 自己的安装通道补（参照物同做法）；可用 env 跳过。"""
    root = _dsh_root(dsh_cli)
    ver = _mcp_client_version(root)
    if ver:
        return ver
    pkg = "@deepseek-ai/dsh-mcp-client"
    if os.environ.get("VOD_DSH_SKIP_MCP_CLIENT_ADD") == "1":
        print("[vod-devkit] 跳过 mcp-client 自装（VOD_DSH_SKIP_MCP_CLIENT_ADD=1）→ 降级为壳工具面",
              file=sys.stderr)
        return None
    if not _registry_has(pkg):
        print(f"[vod-devkit] registry 不可达或查不到 {pkg} → 跳过自装，降级为壳工具面"
              "（联网后可 `dsh plugin --profile <p> add " + pkg + "` 补，再重装本插件）",
              file=sys.stderr)
        return None
    r = subprocess.run([dsh_cli, "plugin", "--profile", profile, "add", pkg],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print("[vod-devkit] mcp-client 自装失败（降级为壳工具面）："
              f"{(r.stderr or r.stdout).strip()[-200:]}", file=sys.stderr)
        return None
    ver = _mcp_client_version(root)
    if ver:
        print(f"已装 @deepseek-ai/dsh-mcp-client@{ver}（工具面走 MCP，12 工具）")
    return ver


def _patch_block(args, mcp_ver: str | None, payload: Path, packs: str,
                 python_exe: str | None = None,
                 state_home: str | None = None,
                 ui_base: str | None = None) -> str:
    """生成托管块：标记包裹 + 两条（或一条）insert 子项，全部缩进在 `- insert:` 下。

    嵌套铁律（真机实锤）：块必须缩进在 `- insert:` 之下——平铺会被 dsh 组合层丢弃，
    插件掉出组合树（banner/工具/UI 全消失）。壳的 `name:` 行必须保留（绑定 UI 半）。

    `python_exe` / `state_home`（S152）：doctor 重建时必须传**安装期记录值**，默认值只是
    安装器的行为。自愈拿"当前进程"的这两个值去比/去写，会把用户钉的解释器换掉、
    把 state 指到别的目录（0.5.16 评审实锤四条静默改写）。
    """
    from vod_mcp import config_forms as cf
    from vod_mcp import paths as _paths

    py = python_exe or sys.executable
    st = state_home or str(_paths.machine_state_home())

    prod_yaml = json.dumps(args.product, ensure_ascii=False) if args.product else "''"
    # P4（2026-11-16）：外部可控标量一律 JSON 双引号——YAML 里裸写 `product: A: B`
    # 是 ScannerError（整个 cordis.patch.yml 解析失败 = profile 起不来）；
    # json.dumps 的输出就是合法 YAML 双引号标量。
    api_y = json.dumps(args.java_api_base or "", ensure_ascii=False)
    ui_y = json.dumps(ui_base or args.java_api_base or "", ensure_ascii=False)
    packs_y = json.dumps(str(packs), ensure_ascii=False)
    shell_cfg = [
        f"        product: {prod_yaml}",
        f"        apiBase: {api_y}",
        f"        uiBase: {ui_y}",   # 浏览器半直连引擎（D-uiBase-direct）
        # headless 无审批通道：dsh 原生 ask 门禁会永久阻断写工具（四宿主实锤）。
        # 同意确认由 SKILL 话术层承担；web 端要硬门禁按 profile 覆盖回 true。
        "        confirmWrites: false",
    ]
    shell = ["    - id: vod-devkit", "      name: dsh-vod-devkit", "      config:"] + shell_cfg
    if not mcp_ver:
        return "\n".join([cf._DSH_MARK_START, "- insert:"] + shell + [cf._DSH_MARK_END])

    # B 模式：壳只留 UI 半（工具面交给 mcp-client，避免双注册/双 submit）
    shell_cfg.insert(0, "        registerTools: false")
    shell = ["    - id: vod-devkit", "      name: dsh-vod-devkit", "      config:"] + shell_cfg
    mcp = [
        "    - id: vod-devkit-mcp",
        "      name: '@deepseek-ai/dsh-mcp-client'",
        "      config:",
        "        serverName: vod-devkit",     # 工具名 = mcp__vod-devkit__vod_*
        "        transport: stdio",
        # stdio 形态零第三方依赖：用安装器自己的解释器即可（不抄显示层路径）
        f"        command: {py}",
        "        args:",
        f"          - {payload / 'vod_mcp' / 'server.py'}",
        "        env:",
        # mcp-client 只给「清洗过的父环境 + 显式 env」：凭据形状的变量会被丢掉，
        # 所以状态根/引擎地址/packs 必须显式传；key 故意不传（走机器级匿名令牌）。
        f"          PYTHONPATH: {payload}",
        f"          VOD_DEVKIT_HOME: {st}",
        f"          VOD_JAVA_API_BASE: {api_y}",
        f"          VOD_PACKS: {packs_y}",
        f"        cwd: {payload}",
        "        toolCallTimeoutMs: 30000",
        "        failOnStartupError: false",
    ]
    return "\n".join([cf._DSH_MARK_START, "- insert:"] + mcp + shell + [cf._DSH_MARK_END])


def skills_dir(args):
    prof = (getattr(args, "dsh_profile", "") or "").strip()
    if not prof:
        return None
    d = host_specs.load("dsh", prof).get("skillsDir")
    return Path(d) if d else None


def _installed_shell_version(profile: str) -> str:
    """profile 里已装壳的版本（读 node_modules/dsh-vod-devkit/package.json）。

    为什么必须读回（S174 真机实锤）：`dsh plugin add dsh-vod-devkit@<ver>` 在 registry
    未传播时失败，代码回落「不带版本」→ pnpm 认为依赖已满足直接跳过 → 壳停旧版，而
    install 返回成功、账本写新版本号；只有 host_matrix --audit 会报 DRIFT。壳版本错位
    正是「patch 写了 registerTools:false 而壳里没这个字段」那类双注册现场的来源。
    """
    cfg = host_specs.load("dsh", profile).get("configPath")
    if not cfg:
        return ""
    pkg = Path(cfg).parent / "node_modules" / "dsh-vod-devkit" / "package.json"
    try:
        return json.loads(pkg.read_text(encoding="utf-8")).get("version") or ""
    except (OSError, json.JSONDecodeError):
        return ""


def install(args, packs: str) -> Path:
    """dsh 工具壳（D-dsh-install-1，2026-11-06 用户拍板 A）：三壳口径统一——
    --product 安装期硬校验（cmd_install 已先行，到达此处必已过）+ 校验先于
    add + 幂等写 profile cordis.patch.yml config override。
    生效通道真机实测（2026-11-06，dsh 0.2.1-rc.5）：profile cordis.patch.yml
    的 id-targeted config override 是工具壳读取 product/apiBase/uiBase/
    confirmWrites 的唯一运行时通道（启动 banner + 桩引擎提交链实证）。
    uiBase（D-uiBase-direct）：浏览器半（反馈按钮）直连引擎——apiBase 是
    server 半（Node）自用，浏览器同源策略下用不上；缺 uiBase 时 UI 提交
    发往 dsh 同源（404→本地暂存），嵌入方真机实锤。dsh plugin add 会自建
    profile，无需前置。"""
    dsh = shutil.which("dsh")
    profile = (getattr(args, "dsh_profile", "") or "").strip()
    if not profile:
        # argparse 进入安装前校验（cmd_install 已兜底，直调防御）
        print("[vod-devkit] --profile 必填：dsh 按 profile 组织插件与配置"
              "（--profile <name>）", file=sys.stderr)
        sys.exit(2)
    if not dsh:
        print("[vod-devkit] 未找到 dsh CLI（PATH），拒绝安装（宁可不装不可装错）。"
              "前置：npm i -g @deepseek-ai/dsh（需 pnpm）", file=sys.stderr)
        sys.exit(2)
    # 版本必须钉死到本次安装器版本：profile 的 package.json 里是精确版本
    # （`"dsh-vod-devkit": "0.5.9"`），不带版本的 `add dsh-vod-devkit` 会被 pnpm
    # 当成"已满足"直接跳过 —— 真机实锤：0.5.10 装完 profile 里仍是 0.5.9，
    # patch 已写 registerTools:false 而壳里根本没这个字段，工具面静默双注册。
    # 带版本失败（本地开发/离线/registry 未传播）才回落不带版本。
    from vod_mcp import __version__ as _ver
    pkg = f"dsh-vod-devkit@{_ver}"
    r = subprocess.run([dsh, "plugin", "--profile", profile, "add", pkg],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"[vod-devkit] dsh plugin add {pkg} 失败，回落不钉版本："
              f"{(r.stderr or r.stdout).strip()[-200:]}", file=sys.stderr)
        r = subprocess.run([dsh, "plugin", "--profile", profile,
                            "add", "dsh-vod-devkit"],
                           capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"[vod-devkit] dsh plugin add 失败：{(r.stderr or r.stdout).strip()[-300:]}",
              file=sys.stderr)
        sys.exit(1)
    # S174：rc=0 不算数——回落到「不带版本」时 pnpm 认为已满足直接跳过，壳仍是旧版。
    # 读回 profile 里的壳版本：读到且不等 → 非零退出（此时 patch 还没写，不留半装状态）；
    # 完全读不到（该 dsh 版本没有 profile 的 node_modules 布局）→ 只告警，不阻断安装。
    got = _installed_shell_version(profile)
    if got and got != _ver:
        print(f"[vod-devkit] dsh 壳版本未达目标：profile={profile} 里是 {got}，"
              f"目标是 {_ver}（多半是 registry 未传播，回落到不带版本的 add 被 pnpm 跳过）\n"
              f"  处置：等 registry 传播后重跑 install，或手工 "
              f"`dsh plugin --profile {profile} add dsh-vod-devkit@{_ver}`",
              file=sys.stderr)
        sys.exit(1)
    if not got:
        print(f"[vod-devkit] warn: 读不到 profile={profile} 的壳版本"
              "（node_modules/dsh-vod-devkit/package.json 不存在）——请手工核对 "
              f"`dsh plugin list` 里的 dsh-vod-devkit 是否为 {_ver}", file=sys.stderr)
    print(f"已安装 dsh 插件 dsh-vod-devkit（profile={profile}，目标版本 {_ver}，"
          "dsh plugin list 可见）")

    patch = Path(host_specs.load("dsh", profile)["configPath"])
    # name 行必须保留：cordis.patch.yml 的 insert 块靠 name 绑定 client 半
    # （反馈按钮）——只写 id+config 会在重装幂等替换时把 name 吞掉，UI 静默
    # 失激活（2026-11-06 真机实锤：重装后入口消失）
    # 嵌套铁律（2026-11-10 真机实锤）：块必须缩进在 `- insert:` 之下——平铺
    # 形态被 dsh 组合层丢弃，插件掉出组合树（banner/工具/UI 全消失）。
    # 归因先验（D-attrib-B）：--product 可选；空值时写 '' 而非空值
    # （dsh 壳 config schema 是 z.string().default('')，YAML null 会校验失败）
    # D-dsh-mcp-b-1：B 模式判定——dsh 本体有没有 mcp-client（缺则尝试用 dsh 自己的
    # 安装通道补，补不上就降级成壳工具面）。块本身见 _patch_block。
    mcp_ver = _ensure_mcp_client(dsh, profile)
    from vod_mcp.host_adapters import base as _base
    payload = _base.payload_dir()
    if not payload:                      # 直调（测试/手工）没 stage：用分发根兜底
        from vod_mcp import paths as _paths
        payload = _paths.DIST_ROOT
    block = _patch_block(args, mcp_ver, Path(payload), packs)
    try:
        written = upsert_patch(patch, block)
    except Exception as e:
        # 回滚/修复指引：插件已装但配置未写 = 半成品，给明确的手动修复格式。
        # 区分两类失败：形态守卫拒绝（文件合法但不在已知形态内，字节未动）
        # 与真实 IO 失败——两者的处置动作不同，文案必须能分辨。
        print(f"[vod-devkit] 插件已装入 profile={profile}，但配置写入失败"
              f"（{e.__class__.__name__}: {e}；该文件未被改动）。请手动把下段并入 {patch}"
              f"（托管块：标记行 + `- insert:` 段，已有同标记块则整块原位替换）：\n"
              f"{block}", file=sys.stderr)
        sys.exit(1)
    mode = (f"MCP（mcp-client@{mcp_ver}，工具面 12 个，壳只留 UI）" if mcp_ver
            else "壳自注册（降级：6 工具）")
    if written:
        print(f"已写入 dsh 托管块（{mode}）：{patch}")
    else:
        print(f"配置未变化（幂等跳过，{mode}）：{patch}")
    # R4（2026-11-16）：dsh 的每个 profile 是独立安装对象（账本按 (target, profile) 记行），
    # 其余 profile 不会被这次安装带到——老机器/新机器都容易漏，这里直接给下一步命令。
    print(f"提示：dsh 的其它 profile 需要各跑一次 install（例：install --target dsh "
          f"--profile <name>）；本次只处理 profile={profile}")
    return patch


def find_dsh_block(lines):
    """定位 cordis.patch.yml 中 vod-devkit 块的 (start, end)。

    扫描/边界语义统一在 vod_mcp/config_forms.find_dsh_block（单一实现，
    install 的幂等 upsert、uninstall 摘除、doctor 自愈三处共用——两处扫描
    规则漂移在本仓 dsh 壳上实锤过）。本函数只保留名字兼容调用点。
    """
    from vod_mcp import config_forms as cf
    return cf.find_dsh_block(lines)


def upsert_patch(patch: Path, block: str) -> bool:
    """幂等写 profile cordis.patch.yml：已存在 `- id: vod-devkit` 段则原位整块
    替换（不重复插入）；无则追加。按行扫描块边界（下一行 `- ` 顶层元素或 EOF），
    不引 YAML 依赖（本仓零第三方依赖红线）。返回是否有写入。"""
    from vod_mcp import config_forms as cf
    lines = patch.read_text(encoding="utf-8").splitlines() if patch.exists() else []
    # 形态守卫（先分类后改字节）：非已知形态一律拒绝——这个文件坏掉等于
    # 整个 dsh profile 起不来（`[]` 占位实锤），比装不上代价高得多
    try:
        verdict, reason = cf.classify_dsh_patch(lines)
    except cf.Refused as e:
        raise RuntimeError(f"cordis.patch.yml 形态不受支持：{e}") from e
    if verdict == "refuse":
        raise RuntimeError(f"cordis.patch.yml 形态不受支持：{reason}")
    start, end = find_dsh_block(lines)
    if start is None:
        # 空数组占位清除（四宿主实测实锤：dsh plugin add 自建的模板含字面量
        # `[]` 顶层行，直接追加块 = `[]` 后跟 `- id:` 顶层元素 = 非法 YAML，
        # 整个 profile 启动崩溃）。`[]` 语义=空数组，被块 entries 取代即删。
        lines = [ln for ln in lines if ln.strip() != "[]"]
        new = lines + ([""] if lines and lines[-1].strip() else []) + block.splitlines()
    else:
        new = lines[:start] + block.splitlines() + lines[end:]
    new_text = "\n".join(new).rstrip("\n") + "\n"
    # 空 `- insert:` 组头清理（损坏态自愈）：孤儿组头（下一个顶层元素前无
    # 子项）来自历史平铺替换的残留——留它在 dsh 组合层是空组，可能拖垮
    # 整个 patch 解析。upsert 后顺手摘除（幂等，不碰正常组）。
    cleaned = []
    for idx, ln in enumerate(new):
        if ln.strip() == "- insert:":
            nxt = new[idx + 1] if idx + 1 < len(new) else ""
            if nxt.startswith("- ") or (not nxt.strip() and idx + 2 >= len(new)):
                continue  # 孤儿组头：下一行已是新顶层元素（无子项）→ 摘除
        cleaned.append(ln)
    new_text = "\n".join(cleaned).rstrip("\n") + "\n"
    old_text = patch.read_text(encoding="utf-8") if patch.exists() else ""
    if new_text == old_text:
        return False
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(new_text, encoding="utf-8")
    return True


def remove_patch_block(patch: Path) -> bool:
    """从 cordis.patch.yml 摘除 vod-devkit 块（uninstall 用）。返回是否摘除。"""
    if not patch.exists():
        return False
    from vod_mcp import config_forms as cf
    lines = patch.read_text(encoding="utf-8").splitlines()
    try:
        verdict, reason = cf.classify_dsh_patch(lines)
    except cf.Refused as e:
        verdict, reason = "refuse", str(e)
    if verdict == "refuse":
        # 卸载路径同样不动字节：文件已经坏了，再"尽力删"只会让故障更难定位
        print(f"[vod-devkit] skip（cordis.patch.yml 形态不受支持，未改动）：{reason}",
              file=sys.stderr)
        return False
    start, end = find_dsh_block(lines)
    if start is None:
        return False
    patch.write_text(
        "\n".join(lines[:start] + lines[end:]).rstrip("\n") + "\n",
        encoding="utf-8")
    return True


def install_remote(args, url, token):
    print("[vod-devkit] dsh 本轮只支持本地形态（MCP stdio）；远程 attach 待下一轮开"
          "（dsh-mcp-client 支持 streamable-http，本机已实测）。请用："
          "install --target dsh --profile <name>", file=sys.stderr)
    sys.exit(2)


# ── S152：托管块的结构化事实（自愈判据用它，不用"环境快照全等"）──────────────
def block_facts(text: str) -> dict:
    """把 patch 里的 vod-devkit 块解析成**结构字段**，供 doctor 判断形态与字段差异。

    为什么不比整块文本：块内嵌 command/VOD_DEVKIT_HOME/payload 路径，都是安装期环境值；
    拿"当前进程"重新生成再比，等于把环境变化当成配置损坏（0.5.16 实锤四条静默改写）。
    """
    import re

    from vod_mcp import config_forms as cf

    lines = text.splitlines()
    start, end = cf.find_dsh_block(lines)
    seg = lines[start:end] if start is not None else []
    joined = "\n".join(seg)

    def first(pattern):
        m = re.search(pattern, joined, re.MULTILINE)
        if not m:
            return None
        v = m.group(1).strip()
        # P4 起外部标量写成 JSON 双引号：解析时去引号，比较面才和安装期记录同形
        if len(v) >= 2 and v.startswith('"') and v.endswith('"'):
            try:
                v = json.loads(v)
            except Exception:      # noqa: BLE001  坏转义按字面比
                v = v.strip('"')
        return v

    def scalar(key):
        """外部标量按「JSON 双引号优先、裸标量兼容」读回（P1 读侧，2026-11-16）。

        写侧 P4 起把外部标量统一写成 JSON 双引号（`product: "AI 开发者空间"`）；
        读侧若还按「非空白捕获」（旧的 `(\\S+)`），空格处就截断（只捕到 `"AI`），去引号逻辑在捕获之后救不回来
        → product=None。真实名录 103 项里 22 项含空格：doctor 对这些产品永不报漂移，
        自愈补缺口还会用安装期值静默回写（破坏 R1「不重置定制」）。
        裸标量分支只为老装机（P4 之前）兼容，不是新写法。
        """
        m = re.search(rf"^\s*{re.escape(key)}:\s*(.*)$", joined, re.MULTILINE)
        if not m:
            return None
        v = m.group(1).strip()
        if not v:
            return None
        if v[0] == '"':
            try:
                val, _end = json.JSONDecoder().raw_decode(v)   # 容忍行尾注释/空白
                return val
            except Exception:      # noqa: BLE001  坏转义按字面比
                return v.strip('"')
        if v[0] == "'" and v.endswith("'"):
            return v[1:-1]
        return v

    return {
        "present": start is not None,
        "present_mcp": any(ln.strip() == "- id: vod-devkit-mcp" for ln in seg),
        "present_shell": any(ln.strip() == "- id: vod-devkit" for ln in seg),
        "register_tools_false": bool(re.search(r"^\s*registerTools:\s*false\s*$", joined,
                                               re.MULTILINE)),
        "command": scalar("command"),
        "server_py": first(r'^\s*-\s*"?([^"\n]+/vod_mcp/server\.py)"?\s*$'),
        "cwd": scalar("cwd"),
        "pythonpath": scalar("PYTHONPATH"),
        "state_home": scalar("VOD_DEVKIT_HOME"),
        "uibase": scalar("uiBase"),
        "apibase": scalar("apiBase"),
        "packs": scalar("VOD_PACKS"),
        "product": scalar("product"),
    }


def install_snapshot() -> dict:
    """安装期真源（落进 manifest 行，doctor 只跟它比）：解释器 / state 根 / mcp-client 版本。"""
    from vod_mcp import paths as _paths

    cli = shutil.which("dsh")
    ver = _mcp_client_version(_dsh_root(cli)) if cli else None
    return {"command": sys.executable,
            "stateHome": str(_paths.machine_state_home()),
            "mcpClient": ver}
