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
    "vod_draft_voices": collect.draft_voices,
    "vod_commit_voices": collect.commit_voices,
}


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    needs_host = handler in (core.devkit_info, collect.submit_voices, core.auth_status,
                             collect.draft_voices, collect.commit_voices)
    return handler(params, client_info) if needs_host else handler(params)
