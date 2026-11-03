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

# 双后端配置（E2）：env 优先，runtime.json 兜底——不依赖宿主 env 透传
# （实测部分 MCP 宿主对子进程 env 过滤/丢失，如 Hermes 多 --env 只存活一个）


def _runtime_cfg() -> dict:
    p = Path(__file__).resolve().parent.parent / "vod_mcp" / "runtime.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


_RT = _runtime_cfg()
WF_BASE = os.environ.get("VOD_API_BASE") or _RT.get("workflow_base") or "http://127.0.0.1:8000"
WF_KEY = os.environ.get("VOD_API_KEY", "") or _RT.get("workflow_key", "")            # nginx R0 Bearer
JAVA_BASE = os.environ.get("VOD_JAVA_API_BASE") or _RT.get("java_base") or "http://127.0.0.1:8090"
JAVA_KEY = os.environ.get("VOD_JAVA_API_KEY", "") or _RT.get("java_key", "")     # ExternalApiKeyFilter Bearer
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
    try:
        with open("/tmp/vod_mcp_server.log", "a", encoding="utf-8") as _f:
            _f.write(f"http {method} {url} key={'yes' if key else 'no'}\n")
    except Exception:
        pass
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


_PRODUCT_MAP = {  # 插件白名单值 -> 引擎 product 枚举名（ExternalVoiceController 实测）
    "agentarts": "AgentArts", "codearts": "CodeArts", "dataarts": "DataArts",
    "maas": "MaaS", "obs": "OBS", "officeclaw": "OfficeClaw",
}
_EXISTING_SUBMIT = "/rest/developer/manager/hdvodmngservice/v1/external/voice/submit"


def _voice_id(source: str, content: str, nonce: str) -> str:
    """voiceId = f(source, content, 调用级nonce)。

    R1 修正（声量保真）：跨调用不去重——不同用户提交同款反馈必须各占
    一行（声量是分析核心信号）；同调用内重试复用同 nonce 保幂等。
    """
    import hashlib
    return f"ext_{source}_{hashlib.sha1((content + nonce).encode('utf-8')).hexdigest()[:12]}"


def submit_voices(params: dict, client_info: dict | None = None) -> dict:
    """走 Java 现有 POST /external/voice/submit（Bearer；单条循环提交）。

    - voiceId=确定性生成 f(source, content-hash)：同源同内容天然幂等
      （DB uk_voice_id 兜底；Duplicate 映射为 already-accepted 回执）
    - description 引擎校验 ≥10 字：短反馈自动补场景说明
    - 提交即分析（现有链路语义）；囤积端点 VOD-VOI 上线后切换
    """
    import uuid
    host = (client_info or {}).get("name") or "unknown-host"
    product = _PRODUCT_MAP.get(str(params.get("product", "codearts")).lower(), "CodeArts")
    accepted, voice_ids, task_ids, rejected = 0, [], [], []
    for i, v in enumerate(params.get("voices", [])):
        content = str(v.get("content", "")).strip()
        if not content:
            rejected.append({"index": i, "reason": "content 为空"})
            continue
        nonce = uuid.uuid4().hex[:8]  # 调用级：重试复用（见 _voice_id 重试路径），跨调用不重复
        vid = _voice_id(host, content, nonce)
        # R3 修正：title=用户原文（分析消费原话）；description 仅满足引擎
        # ≥10 字校验时才追加采集后缀，且后缀固定为可识别标记
        desc = content if len(content) >= 10 else \
            f"{content} [vod-devkit]"
        body = {
            "voiceId": vid,
            "title": content[:128],
            "description": desc,
            "product": product,
            "source": host,
            "customer": v.get("userType"),
        }
        global JAVA_KEY
        try:
            out = _http("POST", _EXISTING_SUBMIT, body, base=JAVA_BASE, key=JAVA_KEY)
            accepted += 1
            voice_ids.append(vid)
            data = out.get("data") or {}
            task_ids.append(data.get("taskId"))
        except ToolError as e:
            msg = str(e)
            if "Duplicate entry" in msg:  # 同源同内容已提交过 → 幂等回执
                accepted += 1
                voice_ids.append(vid)
                task_ids.append(None)
            elif (not JAVA_KEY or e.code == -32012) and i == 0:
                # 零字段匿名令牌：缺 key/401 → 自动取令牌 → 落 runtime.json → 重试一次
                token = _fetch_anon_token()
                if token:
                    JAVA_KEY = token
                    _save_runtime({"java_key": token, "token_tier": "anonymous"})
                    out = _http("POST", _EXISTING_SUBMIT, body, base=JAVA_BASE, key=JAVA_KEY)
                    accepted += 1
                    voice_ids.append(vid)
                    task_ids.append((out.get("data") or {}).get("taskId"))
                else:
                    raise ToolError(
                        "未配置接入 key 且匿名令牌端点不可用。引导：" +
                        "；".join(g["label"] for g in _KEY_GUIDANCE), code=-32012)
            else:
                rejected.append({"index": i, "reason": msg[:120]})
    return {"accepted": accepted, "voiceIds": voice_ids,
            "taskIds": task_ids, "rejected": rejected}


def _fingerprint(key: str) -> str | None:
    import hashlib
    return hashlib.sha1(key.encode()).hexdigest()[:8] if key else None


_TOKEN_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/token"

# 结构化引导（devkit error-table 模式：步骤=可执行动作，不是"参考文档"）
_KEY_GUIDANCE = [
    {"order": 1, "action": "auto-token", "label": "首次提交时插件自动申请零字段匿名令牌（默认路径，无需注册）"},
    {"order": 2, "action": "upgrade", "label": "提交量达上限后升级正式 key：联系 VOD 运营（低信任档→正式档）"},
    {"order": 3, "action": "host", "label": "宿主平台整体对接可获宿主 key：由宿主运维持有（高信任档）"},
]


def _key_state(name: str, key: str, base: str) -> dict:
    return {"configured": bool(key), "fingerprint": _fingerprint(key),
            "base": base, "note": f"{'已配置' if key else '未配置（' + name + '）'}"}


def auth_status(params: dict, client_info: dict | None = None) -> dict:
    """认证自检：指纹化输出（明文永不出现），无 key 也跑并给引导。"""
    out = {
        "javaKey": _key_state("VOD_JAVA_API_KEY", JAVA_KEY, JAVA_BASE),
        "workflowKey": _key_state("VOD_API_KEY", WF_KEY, WF_BASE),
        "packs": sorted(__import__("vod_mcp.packs", fromlist=["enabled_packs"]).enabled_packs()),
    }
    if not JAVA_KEY:
        out["guidance"] = _KEY_GUIDANCE
        out["tokenReady"] = "首次提交时将自动申请匿名令牌（零字段，日限额低）"
    return out


def _save_runtime(update: dict) -> None:
    p = Path(__file__).resolve().parent / "runtime.json"
    cfg = {}
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.update(update)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_anon_token() -> str | None:
    """零字段匿名令牌：不问任何信息，POST 空 body，引擎侧 IP 限频。"""
    try:
        out = _http("POST", _TOKEN_PATH, {}, base=JAVA_BASE, key="", timeout=15)
        token = out.get("token")
        if isinstance(token, str) and token:
            return token
    except ToolError:
        return None
    return None


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
    "vod_auth_status": auth_status,
}


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    needs_host = handler in (devkit_info, submit_voices, auth_status)
    return handler(params, client_info) if needs_host else handler(params)
