"""install 子命令：探测 → 门禁 → 载荷固化 → 宿主写入 → 技能拷贝 → manifest。"""
import argparse
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

from vod_mcp import hosts as host_specs
from vod_mcp import packs as packs_mod
from vod_mcp.host_adapters import REGISTRY as HOST_ADAPTERS
from vod_mcp.host_adapters import generic as generic_host
from vod_mcp import paths
from vodkit_cli import common, remote

# 可显式指定（含 generic）的目标清单：交互输入按它校验，不随 HOST_ADAPTERS 的
# 运行期替换而变（测试与"适配器被裁剪"场景都不该让提示变成骗人的选项）
KNOWN_TARGETS = tuple(sorted(HOST_ADAPTERS)) + ("generic",)


def _is_tty() -> bool:
    """交互判定：stdin 与 stdout 都是终端才问（重定向/CI 一律不猜）。"""
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _ask(prompt: str) -> str:
    print(prompt, end="", flush=True)
    return sys.stdin.readline().strip()


def _interactive_choose(found: list) -> list | None:
    """检测到多个时的多选（对齐 devkit）。返回选中 targets；取消/无输入返回 None。

    输入约定固定（可测）：编号逗号分隔，或 all；回车=取消。非法输入不猜，重问一次。
    """
    for i, t in enumerate(found, 1):
        print(f"  {i}) {t}")
    for attempt in range(2):
        raw = _ask("选择要安装的宿主（编号逗号分隔 / all / 回车取消）：")
        if not raw:
            return None
        if raw.lower() == "all":
            return list(found)
        picked: list[str] = []
        for part in raw.replace("，", ",").split(","):
            part = part.strip()
            if not part.isdigit() or not (1 <= int(part) <= len(found)):
                picked = []
                break
            picked.append(found[int(part) - 1])
        if picked:
            return list(dict.fromkeys(picked))
        print("输入不合法（示例：1 或 1,3 或 all）", file=sys.stderr)
    return None


def _install_many(targets: list, args) -> None:
    """对多个宿主逐个安装（--target all 与交互多选共用这一条实现）。

    缺落点的宿主跳过并说清（dsh 需 --profile），单个失败不阻塞其它——
    但每条失败都打出来，不静默吞。
    """
    for t in targets:
        if t == "dsh" and not (getattr(args, "dsh_profile", "") or "").strip():
            print("[vod-devkit] 跳过 dsh：需 --profile <name>"
                  "（--target dsh --profile web ...）", file=sys.stderr)
            continue
        ns = argparse.Namespace(**vars(args))
        ns.target = t
        print(f"== install --target {t}")
        try:
            cmd_install(ns)
        except SystemExit as e:
            if e.code:
                print(f"[vod-devkit] {t} 安装未完成（exit {e.code}），继续下一个",
                      file=sys.stderr)


def detect_targets() -> list:
    """0/1/N 探测：按 host.json 的 detect 段判断宿主是否在场（CLI 或配置目录）。"""
    found = []
    for host in host_specs.hosts():
        spec = host_specs.raw(host)   # 探测不解析路径（dsh 的 {profile} 占位符必填）
        if spec.get("detectCLI") and shutil.which(spec["detectCLI"]):
            found.append(host)
        elif spec.get("detectPath") and Path(spec["detectPath"]).exists():
            found.append(host)
    return found


def cmd_install(args):
    from vod_mcp import DEFAULT_JAVA_BASE
    if not args.java_api_base:
        # 优先级：--java-api-base > env VOD_JAVA_API_BASE > DEFAULT_JAVA_BASE
        #（env 与插件运行时同键，安装器跟随同链；测试/CI 用 env 指桩引擎零外呼）
        args.java_api_base = os.environ.get("VOD_JAVA_API_BASE") or DEFAULT_JAVA_BASE
    common.write_build_info(strict=False)
    target = args.target
    if target == "all":
        # 一步全量（对齐 devkit `--target all`）：只装探测到的专属宿主；
        # 缺 CLI 的跳过并说明（不猜、不代装宿主）。generic 不参与 all——
        # 它是"手给配置文件"的兜底，不是可探测的专属宿主。
        found = detect_targets()
        if not found:
            print("未探测到可自动安装的宿主；--target all 无可装宿主"
                  "（可 --target <agent> 显式指定）", file=sys.stderr)
            sys.exit(2)
        only = getattr(args, "_only", None) or None
        if only:
            found = [t for t in found if t in only]
        _install_many(found, args)
        return
    if target == "auto":
        found = detect_targets()
        generic_found = generic_host.detect_known()
        if len(found) == 1:
            target = found[0]
            print(f"探测到宿主: {target}")
        elif not found and len(generic_found) == 1:
            # A 层兜底：没有专属模块但有已知通用 MCP 宿主 → 走通用写入
            #（探到唯一一个才自动写，多个/零个都要人选定，不许猜）
            target = "generic"
            if not getattr(args, "mcp_config", ""):
                args.mcp_config = str(generic_host._expand(generic_found[0]["config"]))
            print(f"探测到通用 MCP 宿主: {generic_found[0]['label']} → 通用写入 "
                  f"（{args.mcp_config}）")
        elif not found:
            known = "、".join(h["label"] + "（" + h["config"] + "）" for h in generic_found)
            hint = ("未探测到可自动安装的宿主；用 --target "
                    "hermes|opencode|codeartsdoer|codeartswork|codex|codex-desktop|"
                    "dsh|workbuddy|atomcode 显式指定"
                    + (f"，或通用写入：--target generic --mcp-config <配置>（探测到 {known}）"
                       if generic_found else ""))
            picked_name: str | None = None
            if _is_tty():
                # 交互终端：给一次机会（输入 target 名），非交互一律报错不猜
                print(hint)
                ans = _ask("输入 target 名（如 hermes；回车取消）：").strip().lower()
                if ans in KNOWN_TARGETS:
                    picked_name = ans
            if not picked_name:
                print(hint, file=sys.stderr)
                sys.exit(2)
            target = picked_name
            print(f"探测到宿主: {target}")
        else:
            print("探测到多个宿主: " + ", ".join(found + [h["id"] for h in generic_found]))
            picked_list = _interactive_choose(found) if _is_tty() else None
            if not picked_list:
                print("非交互环境不猜：请用 --target <agent> 或 --target all 显式指定",
                      file=sys.stderr)
                sys.exit(2)
            if len(picked_list) == 1:
                target = picked_list[0]
                print(f"探测到宿主: {target}")
            else:
                # 多选 = 对选中的那几个跑同一套 all 循环（语义只有一处实现）
                print(f"探测到宿主: {', '.join(picked_list)}")
                _install_many(picked_list, args)
                return
    adapter = HOST_ADAPTERS.get(target)
    if adapter is None:
        g = [(h["id"], h["config"]) for h in generic_host.detect_known()]
        hint = ("\n  探测到通用 MCP 宿主：" + "；".join(f"{i}（{c}）" for i, c in g)
                if g else "")
        print(f"不支持目标: {target}（可选 hermes|opencode|codeartsdoer|codeartswork|codex|codex-desktop|dsh|workbuddy|atomcode|generic|auto）{hint}\n"
              "  通用宿主：install --target generic --mcp-config <配置文件>",
              file=sys.stderr)
        sys.exit(2)
    packs = args.packs or common.PRESETS.get(args.preset, "")
    # 未知包 id 在安装口就拒（D-packs-config-1）：与运行期启动检查同一套解析，
    # 免得"装的时候通过、跑起来报错"，也免得把拼写错写进九份宿主配置。
    try:
        packs_mod.parse_packs(packs)
    except packs_mod.UnknownPack as e:
        print(f"[vod-devkit] {e}", file=sys.stderr)
        sys.exit(2)
    # 恢复门禁（D-codex-circuit-breaker-1，2026-11-06 负责人确认）：
    # 熔断标记存在（~/.codex/vod-collect-suspended.json）时，codex 装 collect
    # 被拒——恢复采集的前置=token 化上线并过回归，不是改回 packs 一个动作；
    # --ack-suspension=显式解除（P1-4 修正：解除动作后置到安装成功之后——
    # 若产品校验/安装中途失败，熔断不得已被解除）。
    pending_ack = False
    if target == "codex" and "collect" in (packs or "").replace(" ", "").split(","):
        marker = Path.home() / ".codex" / "vod-collect-suspended.json"
        if marker.is_file() and getattr(args, "ack_suspension", False):
            pending_ack = True  # 解除后置：安装成功才落
        elif marker.is_file():
            print("[vod-devkit] 恢复门禁：codex 采集处于熔断状态"
                  "（未确认提交 ≥2 次，详见 docs/decisions.md"
                  " D-codex-circuit-breaker-1）。"
                  "恢复前置=token 化两段式上线并通过回归"
                  "（draft→commit 审计链/重复 commit 被拒/未确认可检测）。",
                  file=sys.stderr)
            sys.exit(2)
    # 归因绑定降级（D-attrib-B，2026-11-11 负责人拍板 P1-P4 全 A）：--product
    # 由必填改为**可选先验**——归因主路径改成运行期从用户原话解析（证据唯一
    # 命中才采信），安装绑定只在「无字面证据且无记忆」时兜底。保留「给了就
    # 必须对」：显式提供时仍做名录硬校验（拼错照样 exit 2），不给不拦装。
    # D-dsh-install-1：--profile 必填在进入任何安装动作前校验（先校验后写入）
    if target == "dsh" and not (args.dsh_profile or "").strip():
        print("[vod-devkit] --profile 必填：dsh 按 profile 组织插件与配置。\n"
              "  例：npx vod-devkit install --target dsh --profile web --product CodeArts",
              file=sys.stderr)
        sys.exit(2)
    bound_product = args.product
    # D-product-id-2（2026-11-05 用户拍板 B，推翻"宿主名是显式合法值"宽容口径）：
    # 安装期产品硬校验——--product 必须命中 meta productCatalog（名字大小写不敏感
    # 或平台主键 id 精确）。理由：--product 是整条采集链（内置采集技能/分类/透传）
    # 的归因前提，装错=全套 skill 逻辑空转且用户无感知；归因错误比报错更糟。
    # 目录不可达（离线/引擎异常）同样拒绝——宁可不装不可装错（postinstall 拒绝
    # 猜测同源纪律）。插件提交链的 name 兼容通道不受影响（那是老版本插件兼容，
    # 不是安装期放行理由）。
    if args.product:  # 可选先验：给了就校验，不给不拦装（D-attrib-B）
        remote._validate_product_or_exit(args.product, args.java_api_base,
                                         refresh=bool(getattr(args, "refresh_product_catalog", False)))
    # D-key-guard-2 红线：preset（产品分发）形态下 key 禁止随包——环境变量里的
    # key 不透传给宿主配置（客户机一律走匿名令牌自领），并当场告警
    distribution = args.distribution
    if distribution == "preset" and os.environ.pop("VOD_JAVA_API_KEY", None):
        print("[vod-devkit] warn: preset 形态下 VOD_JAVA_API_KEY 已忽略且不写入宿主配置"
              "（key 落在哪台机器哪台就是信任边界；客户机走匿名令牌）", file=sys.stderr)
    # 运行期状态单源（D-token-machine-1）：装机写的是**机器级 state**，
    # 不再是 "仓根/vod_mcp/runtime.json"——后者在改造后只有 server 的首启迁移会读，
    # 写在那里等于 product/java_base 绑定在运行期读不到（这是路径统一时必须同步的点）。
    from vod_mcp import paths as _paths
    rt = _paths.runtime_json_path()
    cfg = {}
    if rt.exists():
        try:
            cfg = json.loads(rt.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg["product"] = bound_product
    if getattr(args, "no_local_ledger", False):
        # D-key-guard-3④：企业数据驻留要求可关本地账本（代价 vod_list_submitted 不可用）
        cfg["local_ledger"] = False
    # base 同步落 runtime.json：宿主 env 透传不稳是实测坑，透传挂了静默落回
    # 127.0.0.1:8090；文件兑底与 env 同值不构成双真源（优先级链 env>文件）
    # 宿主产品（host_default）已删除（2026-11-12 复评）：宿主产品也是一次推断，
    # 错归会进引擎幂等/判重域。候选只走 vod_search_products，这里不再写 host_product。
    cfg["java_base"] = args.java_api_base
    rt.parent.mkdir(parents=True, exist_ok=True)
    rt.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:                      # 含 key/锚点：立刻收紧（与运行期写盘同口径）
        os.chmod(rt, 0o600)
    except OSError:
        pass

    # ── 远程 attach / skills-only（D-attach-1）───────────────────────────
    # 形态：MCP 单独部署一个远程端点，宿主只把 MCP 配置指向它（+ 本地技能）。
    # 约束（2026-11-16 D-token-machine-1 修订）：远程面与本地同一套身份语义——
    # 带 token 就用请求头身份（并验有效）；不带 token 时由**服务端**领/复用机器级
    # 匿名令牌（同机部署的默认形态）。所以 token 从"必填"改为"可选"：
    #   · 有 token → verify_token=True（坏 key 拒装，零副作用）
    #   · 无 token → 只做连接级探活（不注入 Authorization，提交走匿名链）
    # 探活一律先于写入，失败零副作用。dsh 壳不走 MCP，这两种模式对 dsh 无意义（显式拒绝）。
    remote_url = (getattr(args, "mcp_url", "") or "").strip()
    skills_only = bool(getattr(args, "skills_only", False))
    if remote_url or skills_only:
        if not getattr(adapter, "SUPPORTS_REMOTE", False):
            what = ("dsh 本轮只支持本地形态（远程 attach 待开）" if target == "dsh"
                    else f"{target} 不走 MCP")
            print(f"[vod-devkit] {what}，不支持 --mcp-url / --skills-only\n"
                  f"  {target} 请用本地形态：install --target {target} "
                  + ("--profile <name>" if target == "dsh" else ""),
                  file=sys.stderr)
            sys.exit(2)
        token = (getattr(args, "mcp_token", "") or os.environ.get("VOD_MCP_TOKEN") or "").strip()
        if remote_url:
            try:
                names = remote._probe_remote(remote_url, token, verify_token=bool(token))
            except Exception as e:  # noqa: BLE001
                print(f"[vod-devkit] 远程 MCP 探活失败（未写入任何配置）：{e}", file=sys.stderr)
                sys.exit(2)
            expected = remote._expected_remote_tools()
            missing = expected - set(names)
            if missing:
                print(f"[vod-devkit] 远程面工具面不符：缺 {sorted(missing)}\n"
                      f"  实际 = {sorted(names)}\n"
                      "  该端点可能不是 vod-devkit 远程面，或版本/角色不匹配；拒绝安装",
                      file=sys.stderr)
                sys.exit(2)
            print(f"远程面探活通过：{len(names)} 个工具（{', '.join(sorted(names))}）")
            if not token:
                # 评审 B 半（P0-2）：必须说清"没给 token = 共享本机身份"
                print("[vod-devkit] 未提供 token：本机所有 agent 将共享同一枚机器级匿名令牌"
                      "（同一设备锚点、额度共用；要按 agent 隔离请带 --mcp-token）")
        mcp_conf = None if skills_only else adapter.install_remote(args, remote_url, token)
        extra_dirs = _install_skills(target, packs, args,
                                     (getattr(args, "dsh_profile", "") or "").strip() or None)
        common._write_install_manifest(args, target, packs, bound_product, mcp_conf, extra_dirs,
                                transport=("skills-only" if skills_only else "remote"),
                                mcp_url=remote_url)
        return

    payload_dir = _stage_payload()      # 载荷固化：入口指向这份副本，不再指向 npx 缓存
    mcp_conf = adapter.install(args, packs)

    # P1-4 修正：ack 解除后置——安装全部成功才落（解除先于安装=失败安装
    # 也绕过了恢复门禁语义）
    if pending_ack:
        marker = Path.home() / ".codex" / "vod-collect-suspended.json"
        if marker.is_file():
            marker.unlink()
        audit = Path.home() / ".codex" / "vod-collect-suspension-audit.log"
        with audit.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t"
                    f"ack_suspension\tpacks={packs}\n")
        print(f"[vod-devkit] 已显式解除 codex 采集熔断（安装成功），审计已记录：{audit}")

    # G1 修复：技能全量拷贝（目录型技能+平铺规则文档），按 packs 过滤
    extra_dirs = _install_skills(target, packs, args,
                                 (getattr(args, "dsh_profile", "") or "").strip() or None)

    common._write_install_manifest(args, target, packs, bound_product, mcp_conf,
                            extra_dirs, payload_dir=payload_dir)


def _stage_payload():
    """把 server/contract/safety/skills 拷进 ~/.vod-devkit/payloads/<ver>/ 并指过去。

    对标 devkit 的 copyServerPayload（D-payload-1）：npx 安装时仓在
    ~/.npm/_npx/<hash>/，npm 清缓存/换版本后入口指向已删除路径 → 宿主 MCP 静默掉线。
    """
    from vod_mcp import payload as _payload
    from vod_mcp.host_adapters import base as _base
    dest = _payload.stage()
    # 种运行配置到载荷副本的旧做法已删除（D-token-machine-1）：运行期状态单源在
    # 机器级 state（paths.runtime_json_path()），server 不再读 '<载荷>/vod_mcp/runtime.json'。
    # 继续种会在已迁移机器上成为"死写"，并让装机读侧/服务读侧看起来有两个落点。
    _base.set_payload_dir(dest)
    return dest


def _install_skills(target: str, packs: str, args, profile: str | None = None):
    """技能段：按 packs 过滤后拷到 hermes 主目录 + 目标宿主的技能发现目录。

    目标宿主列表由 integrations/<host>/host.json 的 skillsDir 决定——2026-11-11
    实锤：dsh 此前不在拷贝分支里，npx 装 dsh 只拿到工具、拿不到任何技能文
    件（同意前置/逐字回显/追问判定这些话术纪律整层缺失），而 ~/.dsh/skills
    下的副本是 /opt/vod-install 脚本手工刷的，不是安装器产物。
    返回 [(host, Path)] 落点清单（供 manifest 名册对账）。"""
    common.HERMES_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    # opencode 原生技能目录（2026-11-06 实测：opencode 自动发现
    # ~/.config/opencode/skills/ 并经 skill 工具按需加载——此前安装器漏拷，
    # opencode 只有工具描述一条约束通道，话术类约束全部失效）
    extra_dirs = []  # [(host, Path)]
    adapter = HOST_ADAPTERS.get(target)
    dst = adapter.skills_dir(args) if adapter and target != "hermes" else None
    if dst is not None:
        dst.mkdir(parents=True, exist_ok=True)
        extra_dirs.append((target, dst))
    pack_set = set(p for p in packs.split(",") if p)
    for entry in sorted((paths.ASSETS / "skills").iterdir()):
        if entry.is_dir():  # vod-core / vod-feedback-collect
            skill = entry.name
            if skill == "vod-core" and "core" not in pack_set:
                continue
            if skill == "vod-feedback-collect" and "collect" not in pack_set:
                continue
            dst = common.HERMES_SKILLS_DIR / skill
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(entry, dst)
            for _host, oc_dst in extra_dirs:
                dst2 = oc_dst / skill
                if dst2.exists():
                    shutil.rmtree(dst2)
                shutil.copytree(entry, dst2)
        # 领域规则技能为静态副本，与引擎真源的对账见 scripts/rules_provenance.py
    return extra_dirs
