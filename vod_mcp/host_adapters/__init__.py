"""宿主适配注册表（数据驱动分派）。

加宿主 = 一个模块 + REGISTRY 一行；bin/vod-devkit 不再出现宿主分支
（对标 huaweicloud-devkit 的 agents/<id>.ts + switch 分派形态）。

REGISTRY 里的模块必须实现 protocol 的三件事：install / install_remote / skills_dir。
"""
from vod_mcp.host_adapters import codex, dsh, generic, hermes, opencode

REGISTRY = {
    "hermes": hermes,
    "opencode": opencode,
    "codex": codex,
    "dsh": dsh,
    "generic": generic,
}


def get(target: str):
    """未知宿主抛 KeyError（调用方给"不支持目标"提示，不许静默降级）。"""
    return REGISTRY[target]


def modules() -> dict:
    return dict(REGISTRY)
