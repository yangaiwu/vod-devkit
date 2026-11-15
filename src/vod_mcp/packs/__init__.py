"""packs 裁剪：VOD_PACKS=core,workflow,kb（逗号分隔，默认全装）。

core 常驻（vod_devkit_info + vod-core 技能）；未启用的 pack 工具不注册。
"""
import os
import sys

ALL_PACKS = ("core", "collect", "knowledge")

PACK_TOOLS = {
    # vod_search_products：问用户"是哪个产品"前给候选（只读，D-product-ask-1）
    "core": ["vod_devkit_info", "vod_auth_status", "vod_check_update",
             "vod_search_products"],
    # 两段式（D-token-approval-2 极简形态）随 collect 下发；codex 话术走 draft→commit
    "collect": ["vod_submit_voices", "vod_draft_voices", "vod_commit_voices", "vod_list_submitted"],
    # 领域规则技能披露（第二轨）：知道有哪几本规则、按需取全文。
    # 只读、零上游调用、零依赖——与"纯知识包"的定位一致。
    "knowledge": ["vod_list_skills", "vod_retrieve_skill"],
}


BREAKER_MARKERS = (
    # 熔断标记（D-codex-circuit-breaker-1）：install 门禁可被
    # `VOD_PACKS=core,collect serve` 绕过——运行期同查标记强制降级
    os.path.expanduser("~/.codex/vod-collect-suspended.json"),
)


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
    if "collect" in packs and any(os.path.isfile(m) for m in BREAKER_MARKERS):
        # 运行期熔断门禁：collect 强制摘除（非静默——stderr 告警）。
        # 解除=删熔断标记（install --ack-suspension 即此语义）
        packs = tuple(p for p in packs if p != "collect")
        print("[vod-devkit] 采集熔断生效（codex 未确认提交 ≥2 次，"
              "D-codex-circuit-breaker-1）：collect 已强制摘除。"
              "恢复前置=token 化上线并过回归；--ack-suspension 解除安装门禁，"
              "运行期解除须删熔断标记", file=sys.stderr)
    return packs


# 服务面（HTTP 传输）摘除的"写本机状态"工具——对齐 huaweicloud-devkit 的
# remoteSurface 门控语义：远程面没有"本机"这个概念。
#   draft/commit：草稿暂存在本机 runtime.json，HTTP 面由多客户端共享一个进程，
#                 "本机草稿"既不隔离也不可审计；
#   list_submitted：本地账本是装机维度的记录，服务面读它不是客户端想要的答案
#                 （跨机对账走引擎端点）。
# 注意：submit 不摘——它对 VOD 的唯一动作是调用引擎 HTTP API，落库是服务端的事。
REMOTE_WITHHELD = ("vod_draft_voices", "vod_commit_voices", "vod_list_submitted")


def enabled_tools(remote: bool = False) -> list:
    tools = []
    for pack in enabled_packs():
        tools.extend(PACK_TOOLS[pack])
    if remote:
        tools = [t for t in tools if t not in REMOTE_WITHHELD]
    return tools
