"""宿主适配注册表（数据驱动分派）。

加宿主 = 一个模块 + REGISTRY 一行；bin/vod-devkit 不再出现宿主分支
（对标 huaweicloud-devkit 的 agents/<id>.ts + switch 分派形态）。

REGISTRY 里的模块必须实现 protocol 的三件事：install / install_remote / skills_dir。

惰性加载（ARCH-DEP-02，2026-11-19 走查）：`REGISTRY` 只存**模块名字符串**，首次 `get()`
时才 import。原因见 `transport_remote.py` 的注释：急切聚合导入会让"误引 host_adapters"
变成**远程面每请求 500**（载荷副本不含 `integrations/`，2026-11-12 实锤），且单改一个
适配器要拖进 12 个模块的导入成本。`get()` 的 KeyError 语义保持不变。
"""
import importlib

# 名字 → 子模块名（惰性）。与旧 REGISTRY 的键集合**必须**完全一致（宿主要求的
# target 名是产品契约，不许改名；改名 = 安装器找不到宿主）。
REGISTRY = {
    "hermes": "hermes",
    "opencode": "opencode",
    "codeartsdoer": "codearts",
    "codeartswork": "codeartswork",
    "codex": "codex",
    "codex-desktop": "codex_desktop",
    "dsh": "dsh",
    "workbuddy": "workbuddy",
    "atomcode": "atomcode",
    "openclaw": "openclaw",
    "officeace": "officeace",
    "generic": "generic",
}

_CACHE: dict = {}


def get(target: str):
    """按需加载宿主适配器；未知宿主抛 KeyError（调用方给"不支持目标"提示，不许静默降级）。"""
    modname = REGISTRY[target]          # 未知 target 仍在这里抛 KeyError（语义不变）
    mod = _CACHE.get(modname)
    if mod is None:
        mod = importlib.import_module(f"vod_mcp.host_adapters.{modname}")
        _CACHE[modname] = mod
    return mod


def loaded() -> list:
    """已加载的宿主模块名（供诊断/测试断言惰性性）。"""
    return sorted(_CACHE)


def modules() -> dict:
    """名字 → 子模块名映射（惰性：值仍是字符串，调用方要用模块请走 get()）。"""
    return dict(REGISTRY)


def _reset_cache() -> None:
    """测试钩子：清空惰性缓存（等价于旧实现每次 import 都拿到模块的语义）。"""
    _CACHE.clear()
