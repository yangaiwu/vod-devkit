"""packs 裁剪：VOD_PACKS=core,workflow,kb（逗号分隔，默认全装）。

core 常驻（vod_devkit_info + vod-core 技能）；未启用的 pack 工具不注册。
"""
import os
import sys

ALL_PACKS = ("core", "collect", "knowledge")

PACK_TOOLS = {
    # vod_search_products：问用户"是哪个产品"前给候选（只读，D-product-ask-1）
    "core": ["vod_devkit_info", "vod_auth_status", "vod_auth_ensure", "vod_check_update",
             "vod_search_products", "vod_packs_configure"],
    # 两段式（D-token-approval-2 极简形态）随 collect 下发；codex 话术走 draft→commit
    "collect": ["vod_submit_voices", "vod_draft_voices", "vod_commit_voices", "vod_list_submitted"],
    # 领域规则技能披露（第二轨）：知道有哪几本规则、按需取全文。
    # 只读、零上游调用、零依赖——与"纯知识包"的定位一致。
    "knowledge": ["vod_list_skills", "vod_retrieve_skill"],
}


BREAKER_MARKERS = ()
# 熔断标记（D-codex-circuit-breaker-1）：install 门禁可被 `VOD_PACKS=core,collect serve`
# 绕过——运行期同查标记强制降级。默认值**调用期解析**（不用 import 期 expanduser：
# 测试 monkeypatch HOME 时模块常量会钉在真机 HOME 上，标记就查错了机器）；
# 非空即视为测试注入的显式清单（monkeypatch.setattr(packs, "BREAKER_MARKERS", ...)）。
def breaker_markers() -> tuple:
    if BREAKER_MARKERS:
        return tuple(BREAKER_MARKERS)
    return (os.path.expanduser("~/.codex/vod-collect-suspended.json"),)


def enabled_packs() -> tuple:
    return _resolve(os.environ.get("VOD_PACKS", "").strip())


class UnknownPack(ValueError):
    """VOD_PACKS 里出现未知包 id。

    对齐 devkit 口径：**启动即报错**，不静默过滤。静默过滤=操作者以为关掉的还开着、
    以为打开的其实没装——"看起来配了没生效"是比崩溃更难查的一类故障。
    """


def parse_packs(raw: str) -> tuple:
    """解析 VOD_PACKS 字面值（逗号分隔，kb=knowledge 旧称）。未知 id 抛 UnknownPack。"""
    if not raw:
        return ALL_PACKS
    ids = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        ids.append("knowledge" if p == "kb" else p)
    unknown = [p for p in ids if p not in ALL_PACKS]
    if unknown:
        raise UnknownPack(
            f"VOD_PACKS 含未知包 id: {','.join(unknown)}；可用: {','.join(ALL_PACKS)}")
    return tuple(ids) or ALL_PACKS


def _resolve(raw: str) -> tuple:
    if not raw:
        return ALL_PACKS
    packs = parse_packs(raw)
    if "core" not in packs:
        packs = ("core",) + packs
    if "collect" in packs and any(os.path.isfile(m) for m in breaker_markers()):
        # 运行期熔断门禁：collect 强制摘除（非静默——stderr 告警）。
        # 解除=删熔断标记（install --ack-suspension 即此语义）
        packs = tuple(p for p in packs if p != "collect")
        print("[vod-devkit] 采集熔断生效（codex 未确认提交 ≥2 次，"
              "D-codex-circuit-breaker-1）：collect 已强制摘除。"
              "恢复前置=token 化上线并过回归；--ack-suspension 解除安装门禁，"
              "运行期解除须删熔断标记", file=sys.stderr)
    return packs


# 服务面（HTTP 传输）摘除的工具。
# 2026-11-18 D-scope-1 起：**清空**。此前摘 vod_packs_configure 的理由是
# 「HTTP 面每请求现造 server、无会话，开关会在下一个请求消失、多 agent 共用时互相影响」；
# 该理由随标准 stateful 传输落地而失效——现在服务端在 initialize 下发
# mcp-session-id，会话内状态由 SDK session 持有，跨请求存活，且按会话隔离。
# 因此远程面与 stdio 面工具面完全一致（不阉割能力），差异只在传输形态。
REMOTE_WITHHELD: tuple = ()


def enabled_tools(remote: bool = False) -> list:
    tools = []
    for pack in effective_packs():
        tools.extend(PACK_TOOLS[pack])
    if remote:
        tools = [t for t in tools if t not in REMOTE_WITHHELD]
    return tools


# ── 会话内开关（D-packs-configure-1） ─────────────────────
#
# 与 CLI `packs enable|disable --apply` 分工：CLI 写宿主配置（持久，重启用），
# 这里只改进程内状态（立即生效，重启即清）。**不写 env、不写配置**——MCP 工具
# 去改宿主配置文件会把"谁改的"变成猜谜，而持久化面已经有一个可解释入口。

_RUNTIME: tuple | None = None


class PackRefused(PermissionError):
    """运行期拒绝（安全门禁，如采集熔断）。与 UnknownPack（拼写错）分开报。"""


def effective_packs() -> tuple:
    """当前生效的包：会话内开关优先，否则按 VOD_PACKS（含 core 强制与熔断）。"""
    return _RUNTIME if _RUNTIME is not None else enabled_packs()


def normalize_packs(ids) -> tuple:
    """归一请求的包列表：去重、kb 别名、core 强制、未知 id 报错、熔断拦截。"""
    want = []
    for p in ids:
        p = (p or "").strip()
        if not p:
            continue
        p = "knowledge" if p == "kb" else p
        if p not in ALL_PACKS:
            raise UnknownPack(
                f"未知包 id: {p}；可用: {','.join(ALL_PACKS)}")
        if p not in want:
            want.append(p)
    if "collect" in want and any(os.path.isfile(m) for m in breaker_markers()):
        # 熔断是安全门禁：显式开启也不能绕过。静默摘掉等于"配了没生效"。
        raise PackRefused(
            "采集熔断生效（codex 未确认提交 ≥2 次，D-codex-circuit-breaker-1）："
            "会话内不能开启 collect；解除须删熔断标记")
    return tuple(dict.fromkeys(["core"] + want))


def set_runtime_packs(ids) -> tuple:
    """设置会话内生效包；ids 为 None 时恢复按 VOD_PACKS。返回新生效 tuple。"""
    global _RUNTIME
    _RUNTIME = None if ids is None else normalize_packs(ids)
    return effective_packs()
