"""工具实现：唯一事实源=contract/tools.schema.json；HTTP 直调 VOD 两个后端。

双后端拓扑（E2 修复：单 base 寻址不了两个后端）：
  workflow 引擎（FastAPI api.py :8000）——analyze/status/result/kb
    base=VOD_API_BASE，key=VOD_API_KEY（nginx R0 Bearer）
  Java backend——声音提交，base=VOD_JAVA_API_BASE，key=VOD_JAVA_API_KEY
    （ExternalApiKeyFilter Bearer）

引擎端点（api.py 实测路由）：
  POST /api/vod/analyze/json   {data, product, limit, workers} -> {task_id, status}
  GET  /api/vod/status/{task_id}
  GET  /api/vod/result/{task_id}
  POST /api/vod/knowledge/query  <- 引擎侧前置缺口（api.py 尚无此路由）
Java 端点（external-api-contract.md 实测前缀）：
  POST /rest/developer/manager/hdvodmngservice/v1/external/voices（VOD-VOI）
"""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from vod_mcp import provenance

_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contract" / "tools.schema.json"

# 双后端配置（E2）
WF_BASE = os.environ.get("VOD_API_BASE", "http://127.0.0.1:8000")
WF_KEY = os.environ.get("VOD_API_KEY", "")            # nginx R0 Bearer
JAVA_BASE = os.environ.get("VOD_JAVA_API_BASE", "http://127.0.0.1:8090")
JAVA_KEY = os.environ.get("VOD_JAVA_API_KEY", "")     # ExternalApiKeyFilter Bearer
_JAVA_EXTERNAL = "/rest/developer/manager/hdvodmngservice/v1/external/voices"


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


def _http(method: str, path: str, body: dict | None = None,
          base: str | None = None, key: str | None = None, timeout: int = 30) -> dict:
    """统一出口：一律携带 Authorization Bearer（E1 修复：认证头缺失）。

    base/key 缺省在调用时解析模块级配置（不能用函数默认值——定义时即冻结，
    环境变更/测试 monkeypatch 均无法生效）。
    """
    base = base if base is not None else WF_BASE
    key = key if key is not None else WF_KEY
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        if e.code == 401:
            raise ToolError(
                f"鉴权失败（{base}）：检查 VOD_API_KEY/VOD_JAVA_API_KEY 配置",
                code=-32012) from e
        raise ToolError(f"上游返回 {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise ToolError(f"上游不可达（{base}）: {e.reason}", code=-32001) from e


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


def submit_voices(params: dict, client_info: dict | None = None) -> dict:
    """走 Java backend；source 由握手宿主身份注入（服务端最终以签发 key 为准）。"""
    host = (client_info or {}).get("name") or "unknown-host"
    payload = {"source": host, "voices": params["voices"]}
    out = _http("POST", _JAVA_EXTERNAL, payload, base=JAVA_BASE, key=JAVA_KEY)
    return {"accepted": out.get("accepted", 0),
            "voiceIds": out.get("voiceIds", []),
            "rejected": out.get("rejected", [])}


def devkit_info(params: dict, client_info: dict | None = None) -> dict:
    return provenance.info_payload(client_info)


# 工具名 → 处理器（是否接收 client_info）
_HANDLERS = {
    "vod_run_analysis": run_analysis,
    "vod_task_status": task_status,
    "vod_task_result": task_result,
    "vod_kb_search": kb_search,
    "vod_submit_voices": submit_voices,
    "vod_devkit_info": devkit_info,
}


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    needs_host = handler in (devkit_info, submit_voices)
    return handler(params, client_info) if needs_host else handler(params)
