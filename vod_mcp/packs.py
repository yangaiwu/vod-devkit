"""packs 裁剪：VOD_PACKS=core,workflow,kb（逗号分隔，默认全装）。

core 常驻（vod_devkit_info + vod-core 技能）；未启用的 pack 工具不注册。
"""
import os

ALL_PACKS = ("core", "workflow", "kb")

PACK_TOOLS = {
    "core": ["vod_devkit_info"],
    "workflow": ["vod_run_analysis", "vod_task_status", "vod_task_result"],
    "kb": ["vod_kb_search"],
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
