"""packs 裁剪：VOD_PACKS=core,workflow,kb（逗号分隔，默认全装）。

core 常驻（vod_devkit_info + vod-core 技能）；未启用的 pack 工具不注册。
"""
import os
import sys

ALL_PACKS = ("core", "collect", "knowledge")

PACK_TOOLS = {
    "core": ["vod_devkit_info", "vod_auth_status", "vod_check_update"],
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
    raw = os.environ.get("VOD_PACKS", "").strip()
    if not raw:
        return ALL_PACKS
    # kb=knowledge 旧称别名（历史文档/用户习惯；深审 P0-2 配套：安装口
    # 旧值不因运行口改名而静默失效）
    packs = tuple(p.strip() for p in raw.split(","))
    packs = tuple("knowledge" if p == "kb" else p for p in packs)
    packs = tuple(p for p in packs if p in ALL_PACKS)
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
