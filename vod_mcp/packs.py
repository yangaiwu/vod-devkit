"""packs 裁剪：VOD_PACKS=core,workflow,kb（逗号分隔，默认全装）。

core 常驻（vod_devkit_info + vod-core 技能）；未启用的 pack 工具不注册。
"""
import os

ALL_PACKS = ("core", "collect", "knowledge")

PACK_TOOLS = {
    "core": ["vod_devkit_info", "vod_auth_status"],
    "collect": ["vod_submit_voices"],
    "knowledge": [],  # 纯技能包：3 个领域规则技能，零工具零依赖
}


def enabled_packs() -> tuple:
    raw = os.environ.get("VOD_PACKS", "").strip()
    if not raw:
        return ALL_PACKS
    packs = tuple(p.strip() for p in raw.split(",") if p.strip() in ALL_PACKS)
    if "core" not in packs:
        packs = ("core",) + packs
    return packs


def enabled_tools() -> list:
    tools = []
    for pack in enabled_packs():
        tools.extend(PACK_TOOLS[pack])
    return tools
