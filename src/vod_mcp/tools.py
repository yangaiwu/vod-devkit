"""工具面装配入口（P2 后的 shim）：契约装载 + tools/list 规格 + 分派表。

实现已按 pack 纵切到 vod_mcp/packs/{core,collect,knowledge}.py，共享件在
vod_mcp/net.py（出口/身份）与 vod_mcp/runtime_state.py（状态）。本文件只保留
"契约 → 规格 → 分派"这三件装配职责，不承载任何业务逻辑。

纪律：此处**不 re-export 私有符号**（_http/_save_runtime/...）。历史测试用
monkeypatch.setattr(tools, "_http", fake) 打桩，迁到实现模块后若仍在 shim 上打桩
会静默不生效——宁可直接 AttributeError（tests/test_structure_guards.py 有断言）。
"""
import json

from vod_mcp import paths
from vod_mcp.net import ToolError  # noqa: F401  唯一异常类，供 `except tools.ToolError`
from vod_mcp.packs import collect, core, knowledge

_CONTRACT_PATH = paths.CONTRACT


def load_contract() -> dict:
    with open(_CONTRACT_PATH, encoding="utf-8") as f:
        return json.load(f)


def tool_specs(only: list) -> list:
    """按 packs 启用清单生成 tools/list 的 MCP 工具描述。"""
    contract = load_contract()
    specs = []
    for name, spec in contract["tools"].items():
        if name not in only:
            continue
        specs.append({
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["input"],
        })
    return specs


_HANDLERS = {
    "vod_search_products": core.search_products,
    "vod_check_update": core.check_update,
    "vod_list_skills": knowledge.list_skills,
    "vod_retrieve_skill": knowledge.retrieve_skill,
    "vod_submit_voices": collect.submit_voices,
    "vod_list_submitted": collect.list_submitted,
    "vod_devkit_info": core.devkit_info,
    "vod_auth_status": core.auth_status,
    "vod_packs_configure": core.packs_configure,
    "vod_draft_voices": collect.draft_voices,
    "vod_commit_voices": collect.commit_voices,
}


def _needs_client_info(handler) -> bool:
    """handler 是否吃 client_info（按签名判，不靠手写清单）。

    为什么不用元组白名单：新增双参 handler 忘登记时**静默收到 None**，宿主归因/
    设备标识这类字段就丢了，不报错也不告警（本次 vod_packs_configure 只因不吃
    client_info 才没暴露）。签名判参把这类漏登记一次性消掉。
    """
    import inspect
    try:
        params = list(inspect.signature(handler).parameters.values())
    except (TypeError, ValueError):      # 内建/不可反射：按单参处理（原行为）
        return False
    positional = [p for p in params
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    has_varargs = any(p.kind == p.VAR_POSITIONAL for p in params)
    return has_varargs or len(positional) >= 2


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    return handler(params, client_info) if _needs_client_info(handler) else handler(params)
