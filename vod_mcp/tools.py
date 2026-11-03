"""工具实现：唯一事实源=contract/tools.schema.json；HTTP 直调 workflow/api.py。

引擎端点（api.py 实测路由）：
  POST /api/vod/analyze/json   {data, product, limit, workers} -> {task_id, status}
  GET  /api/vod/status/{task_id}
  GET  /api/vod/result/{task_id}
  POST /api/vod/knowledge/query  <- 引擎侧前置缺口（api.py 尚无此路由）
"""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from vod_mcp import provenance

_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contract" / "tools.schema.json"
_API_BASE = os.environ.get("VOD_API_BASE", "http://127.0.0.1:8000")


class ToolError(Exception):
    def __init__(self, message: str, code: int = -32000):
        super().__init__(message)
        self.code = code


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


def _http(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    url = _API_BASE.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise ToolError(f"引擎返回 {e.code}: {e.read().decode()[:200]}") from e
    except urllib.error.URLError as e:
        raise ToolError(f"引擎不可达（{_API_BASE}）: {e.reason}", code=-32001) from e


def run_analysis(params: dict, client_info: dict | None = None) -> dict:
    payload = {
        "data": params["data"],
        "product": params["product"],
        "limit": params.get("max_voices", 500),
    }
    out = _http("POST", "/api/vod/analyze/json", payload)
    return {"taskId": out["task_id"], "status": out.get("status", "pending")}


def task_status(params: dict) -> dict:
    out = _http("GET", f"/api/vod/status/{params['taskId']}")
    return {
        "taskId": params["taskId"],
        "status": out.get("status"),
        "current_step": out.get("current_step"),
        "updatedAt": out.get("updated_at") or out.get("created_at"),
    }


def task_result(params: dict) -> dict:
    out = _http("GET", f"/api/vod/result/{params['taskId']}")
    return {"taskId": params["taskId"], "results": out.get("results", out)}


def kb_search(params: dict) -> dict:
    out = _http("POST", "/api/vod/knowledge/query",
                {"query": params["query"], "top_k": params.get("top_k", 5)})
    return {"hits": out.get("hits", out)}


def devkit_info(params: dict, client_info: dict | None = None) -> dict:
    return provenance.info_payload(client_info)


# 工具名 → 处理器（是否接收 client_info）
_HANDLERS = {
    "vod_run_analysis": run_analysis,
    "vod_task_status": task_status,
    "vod_task_result": task_result,
    "vod_kb_search": kb_search,
    "vod_devkit_info": devkit_info,
}


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    return handler(params, client_info) if handler in (devkit_info,) else handler(params)
