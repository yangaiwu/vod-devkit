"""工具实现：唯一事实源=contract/tools.schema.json；单上游（纯采集插件）。

方案 A 收敛（2026-11-03 拍板）：插件只做用户声音采集，运营能力归
vod-system 前端（既有工作台）。workflow 三工具与 kb_search 已删除
（git 历史可查；删除依据=零真实使用+受众耦合，负复杂度决策）。

唯一上游：Java backend（VOD_JAVA_API_BASE + VOD_JAVA_API_KEY，
ExternalApiKeyFilter Bearer）。
  POST …/external/voice/submit（现有接口，提交即分析）
  POST …/external/token（VOD-KEY，零字段匿名令牌）
"""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from vod_mcp import provenance
from vod_mcp import DEFAULT_JAVA_BASE

_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contract" / "tools.schema.json"


def _runtime_cfg() -> dict:
    p = Path(__file__).resolve().parent.parent / "vod_mcp" / "runtime.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


# 上游配置：env 优先，runtime.json 兜底——不依赖宿主 env 透传
# （实测部分 MCP 宿主对子进程 env 过滤/丢失，如 Hermes 多 --env 只存活一个）
_RT = _runtime_cfg()
JAVA_BASE = os.environ.get("VOD_JAVA_API_BASE") or _RT.get("java_base") or DEFAULT_JAVA_BASE
JAVA_KEY = os.environ.get("VOD_JAVA_API_KEY", "") or _RT.get("java_key", "")   # ExternalApiKeyFilter Bearer

_META_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/meta"
_META_TTL = 24 * 3600
# 快照兜底（引擎 meta 端点未上线/不可达时用；stale 语义见 _load_meta）
_META_SNAPSHOT = {"products": ["agentarts", "codearts", "dataarts", "maas", "obs",
                               "officeclaw", "modelarts"]}


def _load_meta(force: bool = False) -> dict:
    """可漂移值（product 白名单等）动态取：缓存 TTL 24h，
    引擎端点不可达时回退快照并标 stale。真源=引擎 submit 校验常量。"""
    import time
    cache = _RT.get("meta_cache") or {}
    now = time.time()
    if not force and cache.get("data") and now - cache.get("fetchedAt", 0) < _META_TTL:
        return {"products": cache["data"].get("products", _META_SNAPSHOT["products"]),
                "stale": False, "source": "cache"}
    try:
        out = _http("GET", _META_PATH, None, base=JAVA_BASE, key=JAVA_KEY, timeout=10)
        data = out.get("data") or {}
        if isinstance(data.get("products"), list) and data["products"]:
            _save_runtime({"meta_cache": {"fetchedAt": int(now), "data": data}})
            return {"products": data["products"], "stale": False, "source": "meta"}
    except ToolError:
        pass
    return {"products": _META_SNAPSHOT["products"], "stale": True, "source": "snapshot"}


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
    base = base if base is not None else JAVA_BASE
    key = key if key is not None else JAVA_KEY
    # 传输协议守卫：非本机回环一律要求 https（Bearer 不得明文过公网）
    _host = base.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if not base.startswith("https://") and _host not in ("127.0.0.1", "localhost", "::1"):
        raise ToolError(
            f"上游 {base} 非 https 且非本机回环——Bearer key 明文外发被拒"
            "（配置 VOD_JAVA_API_BASE 为 https:// 地址）", code=-32014)
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
                f"鉴权失败（{base}）：检查 VOD_JAVA_API_KEY 配置",
                code=-32012) from e
        raise ToolError(f"上游返回 {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise ToolError(f"上游不可达（{base}）: {e.reason}", code=-32001) from e


# 引擎 submit 校验白名单（ExternalVoiceServiceImpl.VALID_PRODUCTS 实测：
# CODEARTS/AGENTARTS/OFFICECLAW/DATAARTS/MAAS/OBS + 别名归一 MODELARTS→MAAS）
_PRODUCT_MAP = {
    "agentarts": "AgentArts", "codearts": "CodeArts", "dataarts": "DataArts",
    "maas": "MaaS", "obs": "OBS", "officeclaw": "OfficeClaw",
    "modelarts": "MaaS",  # 引擎别名归一实测
}


def _resolve_product(params: dict) -> str | None:
    """归因（「宿主即产品」口径，2026-11-03 拍板·不设白名单）：
    ①调用方显式传参 ②安装绑定（runtime.json product——安装器默认写入宿主名，
    hermes/opencode/codex 装在哪就归哪）③都没有 → 返回 None（body 不带
    product，引擎落 UNKNOWN 档人工归因解析，V19）——不再 -32013 本地拦截。
    白名单校验已废除：宿主工具自报产品原样上送，由引擎宽松归一收编。"""
    raw = str(params.get("product") or _RT.get("product") or "").strip()
    if not raw:
        return None
    return _PRODUCT_MAP.get(raw.lower(), raw)
_EXISTING_SUBMIT = "/rest/developer/manager/hdvodmngservice/v1/external/voice/submit"
_TOKEN_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/token"

# 结构化引导（devkit error-table 模式：步骤=可执行动作，不是"参考文档"）
_KEY_GUIDANCE = [
    {"order": 1, "action": "auto-token", "label": "首次提交时插件自动申请零字段匿名令牌（默认路径，无需注册）"},
    {"order": 2, "action": "upgrade", "label": "提交量达上限后升级正式 key：联系 VOD 运营（低信任档→正式档）"},
    {"order": 3, "action": "host", "label": "宿主平台整体对接可获宿主 key：由宿主运维持有（高信任档）"},
]


def _voice_id(source: str, content: str, nonce: str) -> str:
    """voiceId = f(source, content, 调用级nonce)。

    R1 修正（声量保真）：跨调用不去重——不同用户提交同款反馈必须各占
    一行（声量是分析核心信号）；同调用内重试复用同 nonce 保幂等。
    """
    import hashlib
    return f"ext_{source}_{hashlib.sha1((content + nonce).encode('utf-8')).hexdigest()[:12]}"


def submit_voices(params: dict, client_info: dict | None = None) -> dict:
    """走 Java 现有 POST /external/voice/submit（Bearer；单条循环提交）。

    - voiceId=调用级唯一（R1 声量保真；同调用内重试幂等）
    - title=用户原文（R3：分析消费原话，模板只允许出现在 description）
    - 提交即分析（现有链路语义）；囤积端点 VOD-VOI 上线后切换
    """
    import uuid
    host = (client_info or {}).get("name") or "unknown-host"
    product = _resolve_product(params)
    accepted, voice_ids, task_ids, rejected = 0, [], [], []
    global JAVA_KEY
    for i, v in enumerate(params.get("voices", [])):
        content = str(v.get("content", "")).strip()
        if not content:
            rejected.append({"index": i, "reason": "content 为空"})
            continue
        if len(content) > 2000:  # 契约 maxLength 2000：内容边界（防超大 payload）
            rejected.append({"index": i, "reason": f"content 超 2000 字（{len(content)}）"})
            continue
        nonce = uuid.uuid4().hex[:8]  # 调用级：重试复用，跨调用不重复
        vid = _voice_id(host, content, nonce)
        desc = content if len(content) >= 10 else f"{content} [vod-devkit]"
        body = {
            "voiceId": vid,
            "title": content[:128],
            "description": desc,
            "source": host,
            "customer": v.get("userType"),
        }
        if product:  # 无归因不带 product（引擎 UNKNOWN 档），不本地拦截
            body["product"] = product
        try:
            out = _http("POST", _EXISTING_SUBMIT, body, base=JAVA_BASE, key=JAVA_KEY)
            accepted += 1
            voice_ids.append(vid)
            task_ids.append((out.get("data") or {}).get("taskId"))
        except ToolError as e:
            msg = str(e)
            if "Duplicate entry" in msg:  # 极端重放场景：DB 唯一键兜底
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
    # 本地账本落账（层级①查询的源）
    import time as _time
    _contents = [str(v.get("content", ""))[:40]
                 for v in params.get("voices", []) if str(v.get("content", "")).strip()]
    ledger_entries = [
        {"voiceId": vid, "taskId": tid,
         "title": (_contents[i] if i < len(_contents) else ""),
         "product": product, "at": _time.strftime("%Y-%m-%dT%H:%M:%S")}
        for i, (vid, tid) in enumerate(zip(voice_ids, task_ids))
    ]
    _ledger_append(ledger_entries)
    return {"accepted": accepted, "voiceIds": voice_ids,
            "taskIds": task_ids, "rejected": rejected}


def _fingerprint(key: str) -> str | None:
    import hashlib
    return hashlib.sha1(key.encode()).hexdigest()[:8] if key else None


def _key_state() -> dict:
    return {"configured": bool(JAVA_KEY), "fingerprint": _fingerprint(JAVA_KEY),
            "base": JAVA_BASE,
            "note": "已配置" if JAVA_KEY else "未配置（首次提交自动取匿名令牌）"}


def auth_status(params: dict, client_info: dict | None = None) -> dict:
    """认证自检：指纹化输出（明文永不出现），无 key 也跑并给引导。"""
    out = {
        "javaKey": _key_state(),
        "packs": sorted(__import__("vod_mcp.packs", fromlist=["enabled_packs"]).enabled_packs()),
    }
    meta = _load_meta()
    out["meta"] = {"source": meta["source"], "stale": meta["stale"],
                   "productCount": len(meta["products"])}
    if not JAVA_KEY:
        out["guidance"] = _KEY_GUIDANCE
        out["tokenReady"] = "首次提交时将自动申请匿名令牌（零字段，日限额低）"
    return out


_LEDGER_KEY = "submissions"
_LEDGER_CAP = 200


def _ledger_append(entries: list) -> None:
    """本地提交账本（层级①）：本机提交记录，供 vod_list_submitted 对账。
    cap 200 条（环形截断，防 runtime.json 膨胀）。
    实现纪律：每次从文件读改写、只动 submissions 键——不从内存 _RT
    合并（陈旧配置会整体回写，覆盖其他键，且把无关配置泄入调用方）。"""
    if not entries:
        return
    fresh = _runtime_cfg()
    ledger = (fresh.get(_LEDGER_KEY) or [])[-_LEDGER_CAP:]
    ledger.extend(entries)
    _save_runtime({_LEDGER_KEY: ledger[-_LEDGER_CAP:]})


def list_submitted(params: dict, client_info: dict | None = None) -> dict:
    """查询本机已提交的声音（只读，采集者对账闭环）。
    引擎级跨机查询随 VOD-VOI 列表端点；终端用户自助查询维持 P2（签名回执）。"""
    limit = params.get("limit", 20)
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20
    ledger = _runtime_cfg().get(_LEDGER_KEY) or []  # 文件现读（进程内账本可能刚更新）
    return {"total": len(ledger),
            "submissions": ledger[-limit:][::-1],  # 最新在前
            "scope": "本机提交记录（换机/重装不保留；引擎级查询随 VOD-VOI）"}


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
    """零字段匿名令牌（T7b 定稿）：渠道由引擎囤积入库侧固定赋值 vod-agent
    （链路即渠道，客户端不自报）——本端保持空 body（方案 C 原样）。"""
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
    "vod_submit_voices": submit_voices,
    "vod_list_submitted": list_submitted,
    "vod_devkit_info": devkit_info,
    "vod_auth_status": auth_status,
}


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    needs_host = handler in (devkit_info, submit_voices, auth_status)
    return handler(params, client_info) if needs_host else handler(params)
