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
import stat
import urllib.request
import urllib.error
from pathlib import Path

from vod_mcp import provenance
from vod_mcp import DEFAULT_JAVA_BASE

_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contract" / "tools.schema.json"


def _runtime_path() -> Path:
    return Path(__file__).resolve().parent / "runtime.json"


def _runtime_cfg() -> dict:
    # 路径单源：一律走 _runtime_path()（曾与 _save_runtime 双写路径，
    # 注入/重定位场景读写分叉——测试实锤的真缺陷）
    p = _runtime_path()
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
    _log(f"http {method} {url} key={'yes' if key else 'no'}")
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
        raise ToolError(f"上游返回 {e.code}: {detail}", code=e.code) from e
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
_SUBMIT_HOARDING = "/rest/developer/manager/hdvodmngservice/v1/external/voices"
_EXISTING_SUBMIT = "/rest/developer/manager/hdvodmngservice/v1/external/voice/submit"  # 过渡期 404 回落
_TOKEN_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/token"

# 结构化引导（devkit error-table 模式：步骤=可执行动作，不是"参考文档"）
_KEY_GUIDANCE = [
    {"order": 1, "action": "auto-token", "label": "首次提交时插件自动申请零字段匿名令牌（默认路径，无需注册）"},
    {"order": 2, "action": "upgrade", "label": "提交量达上限后升级正式 key：联系 VOD 运营（低信任档→正式档）"},
    {"order": 3, "action": "host", "label": "宿主平台整体对接可获宿主 key：由宿主运维持有（高信任档）"},
]


def _install_nonce() -> str:
    """per-install 8 位 hex：runtime.json 首次生成常驻——legacy 共用 key 场景下
    source 命名空间 per-machine 化，杜绝不同用户提交同款内容被确定性
    voiceId 合并成一条（跨用户吞声量，切换补丁前置修复）。"""
    n = _RT.get("install_nonce")
    if not n:
        import uuid
        n = uuid.uuid4().hex[:8]
        try:
            _save_runtime({"install_nonce": n})
        except Exception:
            pass
    return str(n)


def _voice_id(source: str, content: str, nonce: str) -> str:
    """voiceId = f(source, content, 调用级nonce)。

    R1 修正（声量保真）：跨调用不去重——不同用户提交同款反馈必须各占
    一行（声量是分析核心信号）；同调用内重试复用同 nonce 保幂等。
    """
    import hashlib
    return f"ext_{source}_{hashlib.sha1((content + nonce).encode('utf-8')).hexdigest()[:12]}"


def _explicit_key() -> bool:
    """当前 JAVA_KEY 是否为显式配置（正式/宿主 key）而非本会话自动领取的匿名令牌。

    判据：环境变量显式注入（权威，env 优先级最高的既有口径）或
    token_tier != "anonymous"。匿名令牌过期/被吊销时 401 应走重领链；
    显式 key 被 401 拒绝时必须 fail fast（静默降级匿名=配置错误被吞=归因错位，
    「注入 appkey」场景的锚定承诺会变成假的）。
    """
    if bool(os.environ.get("VOD_JAVA_API_KEY")):
        return True
    return bool(JAVA_KEY) and str(_RT.get("token_tier") or "") != "anonymous"


def submit_voices(params: dict, client_info: dict | None = None) -> dict:
    """V16 切换：主路径=囤积端点 POST /external/voices（Bearer，批式，不触发分析）；
    引擎未部署（404）自动回落老链 /external/voice/submit（提交即分析，过渡语义，
    部署后 404 分支自然失效）。

    - voiceId：囤积链由引擎确定性计算（per-token/per-install 命名空间），回执
      voiceIds 为权威对账键；回落老链仍用客户端 nonce id（R1 声量保真）
    - title=用户原文截断；tags=采集层三分类（problem_type:）正式入库通道
    - source：key 持有者被引擎锚定为 host_name；legacy 共用 key 场景带
      per-install nonce 后缀（杜绝跨用户共享命名空间吞声量）
    """
    import uuid
    host = (client_info or {}).get("name") or "unknown-host"
    product = _resolve_product(params)
    accepted, voice_ids, task_ids, rejected = 0, [], [], []
    global JAVA_KEY
    voices_in = params.get("voices", [])
    items = []  # (index, voice_map, content)
    for i, v in enumerate(voices_in):
        content = str(v.get("content", "")).strip()
        if not content:
            rejected.append({"index": i, "reason": "content 为空"})
            continue
        if len(content) > 2000:  # 契约 maxLength 2000：内容边界（防超大 payload）
            rejected.append({"index": i, "reason": f"content 超 2000 字（{len(content)}）"})
            continue
        items.append((i, v, content))
    if not items:
        return {"accepted": 0, "voiceIds": [], "taskIds": [], "rejected": rejected}

    def _ledger(vids, tids):
        import time as _time
        entries = [{"voiceId": vid, "taskId": tid,
                    "title": items[min(i, len(items) - 1)][2][:40],
                    "product": product, "at": _time.strftime("%Y-%m-%dT%H:%M:%S")}
                   for i, (vid, tid) in enumerate(zip(vids, tids))]
        _ledger_append(entries)

    def _legacy_submit(i, v, content):
        """过渡回落：老链单条提交（提交即分析语义，仅 404 触发）。"""
        nonce = uuid.uuid4().hex[:8]  # 调用级：重试复用，跨调用不重复
        vid = _voice_id(host, content, nonce)
        desc = content if len(content) >= 10 else f"{content} [vod-devkit]"
        body = {
            "voiceId": vid,
            "title": content[:128],
            "description": desc,
            "source": f"{host}-{_install_nonce()}",  # per-install 命名空间（legacy 吞声量修复）
            "customer": v.get("userType"),
        }
        if product:
            body["product"] = product
        out = _http("POST", _EXISTING_SUBMIT, body, base=JAVA_BASE, key=JAVA_KEY)
        return vid, (out.get("data") or {}).get("taskId")

    # ---- 主路径：囤积端点批式提交 ----
    hoard_voices = []
    for i, v, content in items:
        hv = {"title": content[:60], "content": content}
        tags = v.get("tags")  # 采集层三分类（problem_type:值）→【类型名】标题前缀正式入库
        if tags:
            hv["tags"] = tags
        ut = v.get("userType")
        if ut:
            hv["userType"] = ut
        hoard_voices.append(hv)
    body = {"voices": hoard_voices}
    if product:  # 无归因不带 product（引擎 UNKNOWN 档），不本地拦截
        body["product"] = product
    out = None
    fallback = False
    try:
        out = _http("POST", _SUBMIT_HOARDING, body, base=JAVA_BASE, key=JAVA_KEY)
    except ToolError as ex:
        if ex.code == 404:
            fallback = True  # 囤积端点未部署 → 落到下方 legacy 回落
        elif not JAVA_KEY or ex.code == -32012:
            if _explicit_key():
                # 显式 key（安装注入/正式档）被引擎 401 拒绝 → fail fast：
                # 不取匿名令牌、不覆盖配置——静默降级匿名档=配置错误被吞
                #（归因错位比报错更糟，同 AIShell 错归病根）
                raise ToolError(
                    f"注入的 key 被引擎拒绝（指纹 {_fingerprint(JAVA_KEY)}）："
                    "请核对 key 是否过期/被吊销，或移除 key 走匿名档（删除 "
                    "VOD_JAVA_API_KEY 环境变量与 runtime.json java_key）",
                    code=-32012)
            # 缺 key/匿名令牌失效 → 零字段匿名令牌 → 落 runtime.json → 重试一次
            token = _fetch_anon_token()
            if not token:
                raise ToolError(
                    "未配置接入 key 且匿名令牌端点不可用。引导：" +
                    "；".join(g["label"] for g in _KEY_GUIDANCE), code=-32012)
            JAVA_KEY = token
            _save_runtime({"java_key": token, "token_tier": "anonymous"})
            out = _http("POST", _SUBMIT_HOARDING, body, base=JAVA_BASE, key=JAVA_KEY)
        else:
            raise  # 网络/413 等如实上抛
    if not fallback:
        server_ids = (out.get("voiceIds") or out.get("data", {}).get("voiceIds")
                      or [])
        accepted = len(server_ids) or len(hoard_voices)
        voice_ids.extend(server_ids if server_ids else [""] * len(hoard_voices))
        task_ids.extend([None] * len(hoard_voices))  # 囤积语义：无即时任务
        result = {"accepted": accepted, "voiceIds": voice_ids,
                  "taskIds": task_ids, "rejected": rejected,
                  "analysis": "deferred",  # 囤积语义明示（V6 运营批量消费）
                  "path": "hoarding"}
        if out.get("productRegistered") is not None:
            result["productRegistered"] = out.get("productRegistered")
        _ledger(voice_ids, task_ids)
        return result
    # ---- 过渡回落：老链单条提交（仅囤积端点 404 触发） ----
    for i, v, content in items:
        try:
            vid, tid = _legacy_submit(i, v, content)
            accepted += 1
            voice_ids.append(vid)
            task_ids.append(tid)
        except ToolError as e:
            msg = str(e)
            if "Duplicate entry" in msg:  # 极端重放场景：DB 唯一键兜底
                accepted += 1
                voice_ids.append(vid)
                task_ids.append(None)
            elif (not JAVA_KEY or e.code == -32012) and not voice_ids:
                if _explicit_key():
                    # 显式 key 被拒 → fail fast（同囤积主路径口径，防静默降级）
                    raise ToolError(
                        f"注入的 key 被引擎拒绝（指纹 {_fingerprint(JAVA_KEY)}）："
                        "请核对 key 是否过期/被吊销，或移除 key 走匿名档", code=-32012)
                # 零字段匿名令牌：缺 key/401 → 自动取令牌 → 落 runtime.json → 重试一次
                token = _fetch_anon_token()
                if token:
                    JAVA_KEY = token
                    _save_runtime({"java_key": token, "token_tier": "anonymous"})
                    vid, tid = _legacy_submit(i, v, content)
                    accepted += 1
                    voice_ids.append(vid)
                    task_ids.append(tid)
                else:
                    raise ToolError(
                        "未配置接入 key 且匿名令牌端点不可用。引导：" +
                        "；".join(g["label"] for g in _KEY_GUIDANCE), code=-32012)
            else:
                rejected.append({"index": i, "reason": msg[:120]})
    result = {"accepted": accepted, "voiceIds": voice_ids,
              "taskIds": task_ids, "rejected": rejected,
              "path": "legacy-fallback"}
    _ledger(voice_ids, task_ids)
    return result

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


def probe_key(key: str | None = None, timeout: int = 8) -> dict:
    """key 有效性探针：带 key 调只读端点 GET /external/meta（Filter 网内）。

    判定语义（引擎是唯一权威，本地零判定）：
    - 200 → {"ok": True}：key 有效且在网内
    - 401/-32012 → {"ok": False, "reason": "rejected"}：引擎判无效（过期/吊销/不存在）
    - 其他错误（网络不可达/超时/5xx）→ {"ok": None, "reason": "unreachable"}：
      不判定——网络问题不是 key 问题，报"无法验证"而非"无效"
    """
    key = key if key is not None else JAVA_KEY
    fp = _fingerprint(key)
    if not key:
        return {"ok": None, "reason": "no-key", "fingerprint": None}
    try:
        _http("GET", _META_PATH, None, key=key, timeout=timeout)
        return {"ok": True, "reason": "verified", "fingerprint": fp}
    except ToolError as ex:
        code = ex.code
        if code == 401 or code == -32012:
            return {"ok": False, "reason": "rejected", "fingerprint": fp}
        return {"ok": None, "reason": "unreachable", "fingerprint": fp}


_META_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/meta"


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
    if JAVA_KEY:
        # 主动探针（devkit auth init 真调 IAM 的廉价版）：用户问"key 好没好"有确定答案
        out["keyCheck"] = probe_key()
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
    合并（陈旧配置会整体回写，覆盖其他键，且把无关配置泄入调用方）。
    D-key-guard-3④：local_ledger=false（企业数据驻留要求）→ 账本关闭，
    vod_list_submitted 随之不可用——留痕是可选项不是义务。"""
    if not entries:
        return
    fresh = _runtime_cfg()
    if fresh.get("local_ledger") is False:
        return
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


_RUNTIME_STATE_KEYS = ("java_key", "token_tier", "install_nonce", "submissions",
                       "meta_cache")


def _distribution() -> str:
    """分发形态位（D-key-guard-3）：install --distribution preset 写入 manifest。
    devkit=自装自管；preset=产品随 agent 分发（客户机首启重生成运行时状态）。"""
    p = Path(__file__).resolve().parent.parent / "install-manifest.json"
    if not p.exists():
        return "devkit"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("distribution", "devkit")
    except Exception:
        return "devkit"


def _ensure_first_boot(rt_path: Path | None = None) -> dict:
    """首启标记 + 构建机残留清理（D-key-guard-3①，preset 形态兜底）。

    主防线是打包排除（分发产物不含 runtime.json）；本函数兜底打包者漏排：
    preset 形态 + runtime.json 存在但无 firstBootAt + 携带运行时状态
    （key/nonce/账本/缓存）→ 判构建机残留 → 自动清空这些状态（保留
    product/java_base 等装机配置）+ 重新生成 per-install nonce + 告警。
    处置用自动重生成而非拒绝启动：残留状态全是本机可再生数据，
    自动清零伤害半径为零，拒启会把误判放大成全功能瘫痪。
    firstBootAt 首启写入，此后不再触发（防误伤正常运行中的安装）。"""
    p = rt_path or _runtime_path()
    if not p.exists():
        return {"action": "none"}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"action": "none"}
    if cfg.get("firstBootAt"):
        return {"action": "none"}
    residual = [k for k in _RUNTIME_STATE_KEYS if cfg.get(k)]
    import time as _t
    if _distribution() == "preset" and residual:
        # 残留清理=整体重建（合并删不掉旧键），但保留装机配置（product/java_base 等）
        _save_runtime({**{k: v for k, v in cfg.items() if k not in _RUNTIME_STATE_KEYS},
                       "firstBootAt": _t.strftime("%Y-%m-%dT%H:%M:%S")},
                      replace=True)
        _warn(f"检测到构建机残留状态（{','.join(residual)}）已自动清空重生成——"
              "分发产物应只含代码与配置，不含安装结果（D-key-guard-3①）")
        return {"action": "cleaned", "removed": residual}
    _save_runtime({"firstBootAt": _t.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"action": "stamped"}


def _save_runtime(update: dict, replace: bool = False) -> None:
    p = _runtime_path()
    cfg = {}
    if p.exists() and not replace:
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.update(update)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    # S1 式写后验（借 huaweicloud-devkit ensurePrivateMode 模式）：写完 chmod 0600
    # 并 stat 回验——不假设 chmod 按文档工作（WSL/drvfs 会静默忽略 chmod），
    # 验的是效果不是动作；runtime.json 含 java_key 明文，权限失效必须告警
    try:
        os.chmod(p, 0o600)
        mode = stat.S_IMODE(os.stat(p).st_mode)
        if mode != 0o600:
            _warn(f"runtime.json 权限异常（{oct(mode)}，期望 0600）——"
                  "key 可能被同机其他用户读取，请检查文件系统（WSL 挂载盘建议移回 Linux 原生盘）")
    except OSError as e:
        _warn(f"runtime.json 权限校验失败：{e}")


def _log(line: str, path: str = "/tmp/vod_mcp_server.log") -> None:
    """统一日志出口，1MB 截断轮转
    （D-key-guard-3⑤：客户机长期运行防无限增长；截断保留尾部近期日志）。"""
    try:
        p = path
        if os.path.exists(p) and os.path.getsize(p) > 1024 * 1024:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                tail = f.read()[-200 * 1024:]
            os.replace(p, p + ".old")
            with open(p, "w", encoding="utf-8") as f:
                f.write("== truncated ==\n" + tail)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def _warn(msg: str) -> None:
    """告警出口：server 日志（排障真源），失败静默——不阻断业务主链。"""
    _log(f"warn {msg}")


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
