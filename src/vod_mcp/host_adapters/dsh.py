"""DeepSeek Harness (dsh) 宿主适配：壳包 dsh-vod-devkit + profile patch upsert。

dsh 壳不走 MCP（工具/UI 都由壳进程提供）→ SUPPORTS_REMOTE=False。
"""
import shutil
import subprocess
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs


HOST = "dsh"
SUPPORTS_REMOTE = False


def skills_dir(args):
    prof = (getattr(args, "dsh_profile", "") or "").strip()
    if not prof:
        return None
    d = host_specs.load("dsh", prof).get("skillsDir")
    return Path(d) if d else None


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
    r = subprocess.run([dsh, "plugin", "--profile", profile,
                        "add", "dsh-vod-devkit"],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"[vod-devkit] dsh plugin add 失败：{(r.stderr or r.stdout).strip()[-300:]}",
              file=sys.stderr)
        sys.exit(1)
    print(f"已安装 dsh 插件 dsh-vod-devkit（profile={profile}，dsh plugin list 可见）")

    patch = Path(host_specs.load("dsh", profile)["configPath"])
    # name 行必须保留：cordis.patch.yml 的 insert 块靠 name 绑定 client 半
    # （反馈按钮）——只写 id+config 会在重装幂等替换时把 name 吞掉，UI 静默
    # 失激活（2026-11-06 真机实锤：重装后入口消失）
    # 嵌套铁律（2026-11-10 真机实锤）：块必须缩进在 `- insert:` 之下——平铺
    # 形态被 dsh 组合层丢弃，插件掉出组合树（banner/工具/UI 全消失）。
    # 归因先验（D-attrib-B）：--product 可选；空值时写 '' 而非空值
    # （dsh 壳 config schema 是 z.string().default('')，YAML null 会校验失败）
    prod_yaml = args.product or "''"
    block = ("- insert:\n"
             "    - id: vod-devkit\n"
             "      name: dsh-vod-devkit\n"
             "      config:\n"
             f"        product: {prod_yaml}\n"
             f"        apiBase: {args.java_api_base}\n"
             f"        uiBase: {args.java_api_base}\n"  # D-uiBase-direct：浏览器半直连引擎
             "        # headless 无审批通道：原生 ask 门禁会永久阻断写工具（四宿主实测实锤：\n"
             "        # requires approval, but no approval channel）。同意确认由 SKILL 话术层\n"
             "        # 承担（draft→用户确认→commit / 明确指令直发），web 端如需硬门禁按\n"
             "        # profile 覆盖回 true。\n"
             "        confirmWrites: false\n")
    try:
        written = upsert_patch(patch, block)
    except Exception as e:
        # 回滚/修复指引：插件已装但配置未写 = 半成品，给明确的手动修复格式。
        # 区分两类失败：形态守卫拒绝（文件合法但不在已知形态内，字节未动）
        # 与真实 IO 失败——两者的处置动作不同，文案必须能分辨。
        print(f"[vod-devkit] 插件已装入 profile={profile}，但配置写入失败"
              f"（{e.__class__.__name__}: {e}；该文件未被改动）。请手动把下段并入 {patch}"
              f"（顶层 YAML 数组元素，已有 - id: vod-devkit 段则原位替换）：\n"
              f"{block}", file=sys.stderr)
        sys.exit(1)
    if written:
        print(f"已写入归因/引擎配置（幂等 upsert）：{patch}")
    else:
        print(f"配置未变化（幂等跳过）：{patch}")
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
    print("[vod-devkit] dsh 壳不走 MCP，不支持远程 attach；请用本地形态："
          "install --target dsh --profile <name>", file=sys.stderr)
    sys.exit(2)
