"""工具实现：唯一事实源=contract/tools.schema.json；单上游（纯采集插件）。

方案 A 收敛（2026-11-03 拍板）：插件只做用户声音采集，运营能力归
vod-system 前端（既有工作台）。workflow 三工具与 kb_search 已删除
（git 历史可查；删除依据=零真实使用+受众耦合，负复杂度决策）。

唯一上游：Java backend（VOD_JAVA_API_BASE + VOD_JAVA_API_KEY，
ExternalApiKeyFilter Bearer）。
  POST …/external/voice/submit（现有接口，提交即分析）
  POST …/external/token（VOD-KEY，零字段匿名令牌）
"""
import contextvars
import json
import os
import stat
import urllib.request
import urllib.error
from pathlib import Path

from vod_mcp import attribution as _attrib
from vod_mcp import provenance
from vod_mcp import DEFAULT_JAVA_BASE

# ── 服务面（HTTP 传输）上下文 ────────────────────────────────────────────
# 每个请求由 transport_remote 注入，逐请求隔离（contextvars 随 asyncio 任务/
# 线程传播），因此并发客户端不会互相覆盖 key。
#   身份：stdio 面=装在哪台机器；HTTP 面=这个请求带了谁的 key。
#   插件自己不产生身份（不代签、不落盘），只把请求头的 Bearer 转成引擎鉴权。
_REQ_KEY = contextvars.ContextVar("vod_req_key", default=None)
_SERVER_FACE = contextvars.ContextVar("vod_server_face", default=False)


def _eff_key(explicit=None) -> str:
    """当前生效的 key：显式参数 > 请求头（HTTP 面）> env/runtime（stdio 面）。"""
    if explicit is not None:
        return explicit
    return _REQ_KEY.get() or JAVA_KEY


# D-followup-impl-2：追问拒答语义词集（答"没有"类=两字段不上送）。
# 契约话术承诺了"不方便回复没有"，客户端必须技术兜底——模型不守话术纪律时
# 键集合仍零漂移（test_followup_declined_or_blank_omitted 回归锁）。
_FOLLOWUP_DECLINES = frozenset({
    "没有", "无", "没有。", "没了", "跳过", "不方便", "不用了", "不用",
    "不补充", "算了", "没有了", "没有了。", "不方便说", "no", "none", "skip", "n/a",
})


def _followup_fields(voice: dict) -> dict:
    """D-followup-impl-2 单源提取（submit 主路径与 draft 暂存共用，禁双边漂移）：
    仅 trim 非空且非拒答词才含键；引擎同口径截 2000；内容永不回流 content。
    followupStatus（评审八点 #3 引擎侧承载的插件上报）：三态白名单归一
    （strip+lower），白名单外/缺失省键——引擎侧降 NULL 不拒收，插件侧同口径双保险。"""
    out = {}
    for _f in ("reproSteps", "expectedBehavior"):
        _val = str(voice.get(_f) or "").strip()
        if _val and _val.lower() not in _FOLLOWUP_DECLINES:
            out[_f] = _val[:2000]
    _st = str(voice.get("followupStatus") or "").strip().lower()
    if _st in ("not_asked", "declined", "answered"):
        out["followupStatus"] = _st
    return out

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
    引擎端点不可达时回退快照并标 stale。真源=引擎 submit 校验常量。
    T7i：productCatalog=[{id,name}]（t_vod_product 运营预置，meta 组装）——
    提交产品归因按平台主键 id 的解析真源；老引擎无该键=catalog 空。"""
    import time
    cache = _RT.get("meta_cache") or {}
    now = time.time()
    if not force and cache.get("data") and now - cache.get("fetchedAt", 0) < _META_TTL:
        return {"products": cache["data"].get("products", _META_SNAPSHOT["products"]),
                "catalog": cache["data"].get("productCatalog") or [],
                "aliases": cache["data"].get("aliases") or {},
                "nameAliases": cache["data"].get("nameAliases") or {},
                "problemTypes": cache["data"].get("problemTypes") or [],
                "dictVersion": cache["data"].get("dictVersion"),
                "stale": False, "source": "cache"}
    try:
        out = _http("GET", _META_PATH, None, base=JAVA_BASE, key=_eff_key(), timeout=10)
        data = out.get("data") or {}
        if isinstance(data.get("products"), list) and data["products"]:
            _save_runtime({"meta_cache": {"fetchedAt": int(now), "data": data}})
            return {"products": data["products"],
                    "catalog": data.get("productCatalog") or [],
                    "aliases": data.get("aliases") or {},
                    "nameAliases": data.get("nameAliases") or {},
                    "problemTypes": data.get("problemTypes") or [],
                    "dictVersion": data.get("dictVersion"),
                    "stale": False, "source": "meta"}
    except ToolError:
        pass
    return {"products": _META_SNAPSHOT["products"], "catalog": [],
            "aliases": {}, "nameAliases": {},
            # 快照不含分类白名单：allowed 为空=不校验（宁可放行也不误杀）
            "problemTypes": [], "dictVersion": None,
            "stale": True, "source": "snapshot"}


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
    headers = {"Content-Type": "application/json",
               # VOD-DEVICE：设备锚点（install_nonce=首启自生成常驻，零新增状态）——
               # 引擎据此建每设备独立锚点（NAT/产品分发不再收敛）；服务端缺失回落 legacy
               "X-Vod-Device-Id": _install_nonce()}
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


def _attribute_product(items: list, params: dict) -> dict:
    """归因（D-attrib-B，2026-11-11 负责人拍板 A/A/A/A；推翻 D-attrib-A 的
    绑定独占与 D-product-id-2 的安装必配）：

    优先级=用户原话字面证据 > 记忆（TTL 30 分钟）> 安装先验 > UNKNOWN。
    - 唯一命中才采信；多产品命中=歧义 → UNKNOWN + 全部命中片段留痕
    - 模型自报 product 一律不采信（事故语义不解除），只回执 ignoredRuntimeProduct
    - 记忆只在 0 命中时启用，且只复用「有字面证据」的历史归因
    返回 {"product","productName","source","evidence","ignored"}。
    """
    raw = str(params.get("product") or "").strip()
    result = _attrib.attribute(
        "\n".join(content for _i, _v, content in items),
        _load_meta(),
        memory=_RT.get("attribution_memory") or {},
        binding=str(_RT.get("product") or "").strip() or None,
    )
    result["ignored"] = raw or None
    return result


def _attach_attribution(result: dict, attr: dict) -> None:
    """回执留痕：来源 + 证据（S99）。模型自报只留 ignoredRuntimeProduct，
    不进 productSource（自报永远不是归因来源）。"""
    result["productSource"] = attr.get("source") or "unknown"
    if attr.get("evidence"):
        result["productEvidence"] = attr["evidence"]
    if attr.get("ignored"):
        result["ignoredRuntimeProduct"] = attr["ignored"]


def _merge_ledger(extra: dict | None, attr: dict) -> dict:
    """账本条目带上归因来源与证据：错归可回溯到用户原话（S99）。"""
    out = dict(extra or {})
    out["productSource"] = attr.get("source") or "unknown"
    if attr.get("evidence"):
        out["productEvidence"] = attr["evidence"]
    return out


_ATTR_HISTORY_CAP = 10


def _remember_attribution(result: dict) -> None:
    """写记忆：只接受「字面证据唯一命中」，歧义/无证据/记忆本身不写（S100）。

    覆盖时留快照（D-attrib-B 追加，评审意见采纳项）：旧条目进
    attribution_history（cap 10，带 replacedAt），事后能回答「当时为什么归
    到 A 而不是 B」——单条记忆被覆盖后判据不可追是排障黑洞。
    """
    mem = _attrib.remember_if_evidenced(result)
    if not mem:
        return
    prev = _RT.get("attribution_memory") or {}
    if prev and prev.get("product"):
        hist = list(_RT.get("attribution_history") or [])
        hist.append({**prev, "replacedAt": mem["at"]})
        hist = hist[-_ATTR_HISTORY_CAP:]
        _save_runtime({"attribution_history": hist})
        _RT["attribution_history"] = hist  # 进程内同步：否则同会话读不到新记忆
    _save_runtime({"attribution_memory": mem})
    _RT["attribution_memory"] = mem


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
        # 首装 nonce 必须同步回写内存态 _RT（D-dev-nonce-sync，2026-11-09 真机实锤）：
        # _RT 仅模块导入时加载一次，_save_runtime 只落盘——不同步则同进程内每次调用
        # 生成新 nonce：领令牌（设备 A）与提交（设备 B）设备绑定校验失败，重试仍
        # 新 nonce（设备 C）再 401——全新安装首次提交必失败冒给用户（存量安装
        # runtime.json 已有 nonce 不受影响）。同步后领令牌/提交同设备，401→领令牌
        # →重试全程进程内无感。
        _RT["install_nonce"] = n
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


def _legacy_key_hint() -> str:
    """旧版残留凭据自愈提示（评审拍板项）：出错时给可操作路径，不发公告靠用户撞。
    含当前插件版本与重装命令——重装会刷新 runtime/清掉旧 key 残留。"""
    version = getattr(__import__("vod_mcp"), "__version__", "unknown")
    return ("若为旧版安装残留凭据：更新插件（当前 v" + version + "）并重装即可清除——"
            "npx vod-devkit@latest install --target <宿主> --product <产品名>；"
            "或移除 VOD_JAVA_API_KEY 环境变量走匿名档")


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


# ── D-pending-1：无通道期 pending 反馈 flush（方案 A，2026-11-09）──

def _flush_pending(product):
    """补提交 ~/.vod-devkit/pending-feedback.jsonl 里 status=pending 的条目。

    口径（D-pending-1 定稿）：同步执行但失败只记日志、绝不回滚主提交；
    幂等键=条目级（sha1(content+confirmAt+source)），内容级去重由引擎
    uk_voice_id 承担（同内容重提=skipped）；重写+原子 rename，失败条目
    保留 pending；单次上限 100 条最早优先，超 30 天标记 expired 剔除。
    双通道消息分离：本函数结果只进工具内部诊断（result.pendingFlush），
    用户侧话术由 skill 层承担（已暂存/自动补交，禁止出现路径）。
    """
    from vod_mcp import pending as _pq
    path = _pq.default_path()
    entries = _pq.load_entries(path)
    if not entries:
        return {"scanned": 0}
    plan = _pq.plan_flush(entries)
    kept = list(plan["kept"])
    flushed, failed, corrected = 0, 0, 0
    for e in plan["to_flush"]:
        content = _pq.canonical_content(e)  # D-pending-1 补强：originalLines 权威拼接，剥模型加的标点
        if content != str(e.get("content", "")):
            corrected += 1
            _log("pending flush: content 与 originalLines 拼接不一致，以 originalLines 为准（剥除模型拼接改动）")
        hv = {"title": str(content)[:60], "content": str(content)}
        if e.get("tags"):
            hv["tags"] = e["tags"]
        body = {"voices": [hv]}
        if product:
            body["product"] = product
        try:
            out = _http("POST", _SUBMIT_HOARDING, body, base=JAVA_BASE, key=_eff_key())
            ids = (out or {}).get("voiceIds") or ((out or {}).get("data") or {}).get("voiceIds")
            if ids is None:
                failed += 1
                kept.append(e)
                _log("pending flush: 回执未含 voiceIds，条目保留")
            else:
                flushed += 1  # 含幂等 skipped（同内容重提=引擎 skipped，零重复）
        except Exception as err:
            failed += 1
            kept.append(e)
            _log(f"pending flush failed (kept pending): {err}")
    _pq.save_entries(path, kept)
    return {"scanned": len(entries), "flushed": flushed,
            "failed": failed, "expired": len(plan["expired"]),
            "corrected": corrected}



def _allowed_tags() -> set:
    """分类白名单（引擎 meta.problemTypes，单一真源）。

    空集=不知道白名单（老引擎/快照/未上线）→ 不过滤：宁可放行也不误杀采集。
    """
    return set(_load_meta().get("problemTypes") or [])


_PROBLEM_TYPE_PREFIX = "problem_type:"


def _filter_tags(tags, allowed: set) -> tuple:
    """tags 白名单过滤 → (kept, dropped)。

    引擎约定（ExternalVoicesServiceImpl.extractProblemType）：分类标注写
    `problem_type:<值>`，值域=meta.problemTypes（六类）。其它语义的 tag 不参与
    分类校验、原样保留；只有 problem_type 的值会被白名单过滤——脏值丢弃不拒收
    声音（对标 vod-skill 的 check_classification：分类必须存在于知识库）。
    """
    kept, dropped = [], []
    for t in tags or []:
        s = str(t).strip()
        if not s:
            continue
        if allowed and s.startswith(_PROBLEM_TYPE_PREFIX):
            val = s[len(_PROBLEM_TYPE_PREFIX):].strip()
            if val not in allowed:
                dropped.append(s)
                continue
            s = _PROBLEM_TYPE_PREFIX + val  # 归一（去多余空白）
        if s not in kept:
            kept.append(s)
    return kept, dropped


def _collect_voice_items(params: dict) -> tuple[list, list]:
    """校验段：content 非空+≤2000 字（契约 maxLength，防超大 payload）。
    返回 (items[(index, voice, content)], rejected 明细)。"""
    items, rejected = [], []
    for i, v in enumerate(params.get("voices", [])):
        content = str(v.get("content", "")).strip()
        if not content:
            rejected.append({"index": i, "reason": "content 为空"})
        elif len(content) > 2000:
            rejected.append({"index": i, "reason": f"content 超 2000 字（{len(content)}）"})
        else:
            items.append((i, v, content))
    return items, rejected


def _echo_plan(items: list, vids: list) -> dict:
    """回显段（方案 A，2026-11-06 拍板）：提交回执强制携带原话回显。
    检测型防线——宿主模型改写用户原话（实锤："体验不好"→"不友好"）
    在回执处当场可见；agent 必须原样转述，改写露馅。"""
    ok = [(vid, items[min(i, len(items) - 1)][2])
          for i, vid in enumerate(vids) if vid]
    return {
        "requiresUserEcho": bool(ok),
        "instruction": ("请向用户原样转述已收录内容：每条以「已收录原话：」开头，"
                        "后接 content 全文。禁止改写、概括、增删字词。"),
        "contents": [{"voiceId": vid, "content": c} for vid, c in ok],
    }


def _ledger_submit(items: list, vids: list, tids: list, product: str | None,
                    extra: dict | None = None) -> None:
    """账本段：回执 voiceIds/taskIds 逐条落本地账本（层级①查询的源）。"""
    import time as _time
    entries = [{"voiceId": vid, "taskId": tid,
                "title": items[min(i, len(items) - 1)][2][:40],
                "product": product, "at": _time.strftime("%Y-%m-%dT%H:%M:%S")}
               for i, (vid, tid) in enumerate(zip(vids, tids))]
    if extra:
        for e in entries:
            e.update(extra)  # 两段式：stage=committed + draftId 关联（验收③）
    _ledger_append(entries)


def _hoard_voice(v: dict, content: str) -> dict:
    """载荷段：单条囤积端点 voice 载荷（title/content + tags/userType +
    D-followup-impl-2 追问补充透传：单源 _followup_fields，拒答词集兜底）。"""
    hv = {"title": content[:60], "content": content}
    if v.get("tags"):  # 采集层三分类（problem_type:值）→正式入库
        hv["tags"] = v["tags"]
    if v.get("userType"):
        hv["userType"] = v["userType"]
    hv.update(_followup_fields(v))
    return hv


def _raise_explicit_key_rejected(key: str) -> None:
    """显式 key（安装注入/正式档）被引擎 401 拒绝 → fail fast：
    不取匿名令牌、不覆盖配置——静默降级匿名档=配置错误被吞
    （归因错位比报错更糟，同 AIShell 错归病根）。囤积/legacy 两路径同口径。"""
    raise ToolError(
        f"注入的 key 被引擎拒绝（指纹 {_fingerprint(key)}）："
        "请核对 key 是否过期/被吊销，或移除 key 走匿名档。"
        + _legacy_key_hint(),
        code=-32012)


def _acquire_anon_token_or_raise() -> str:
    """缺 key/匿名令牌失效 → 领零字段匿名令牌；端点不可用则如实报错。"""
    token = _fetch_anon_token()
    if not token:
        raise ToolError(
            "未配置接入 key 且匿名令牌端点不可用。引导："
            + "；".join(g["label"] for g in _KEY_GUIDANCE), code=-32012)
    return token


def submit_voices(params: dict, client_info: dict | None = None,
                  ledger_extra: dict | None = None) -> dict:
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
    global JAVA_KEY
    accepted, voice_ids, task_ids = 0, [], []
    items, rejected = _collect_voice_items(params)
    if not items:
        return {"accepted": 0, "voiceIds": [], "taskIds": [], "rejected": rejected}
    # 归因（D-attrib-B）：证据来自用户原话，模型自报不参战
    attr = _attribute_product(items, params)
    product = attr["product"]

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
        out = _http("POST", _EXISTING_SUBMIT, body, base=JAVA_BASE, key=_eff_key())
        return vid, (out.get("data") or {}).get("taskId")

    # 服务面（HTTP）：身份只能来自请求头。缺 key 时 fail fast——不先打引擎再
    # 靠 401 兜底（那会多一次无意义外呼，且引擎若宽容 200 就绕过了守卫）。
    if _SERVER_FACE.get() and not _eff_key():
        raise ToolError(
            "服务面（HTTP 传输）不代签身份：请在本请求带上 Authorization: Bearer "
            "<VOD key>（插件只搬运身份，不产生身份；落库与配额都在服务端）",
            code=-32012)

    # ---- 主路径：囤积端点批式提交 ----
    allowed_tags = _allowed_tags()
    hoard, invalid_tags = [], []
    for i, v, content in items:
        hv = _hoard_voice(v, content)
        if hv.get("tags"):
            kept, dropped = _filter_tags(hv["tags"], allowed_tags)
            if kept:
                hv["tags"] = kept
            else:
                hv.pop("tags", None)
            if dropped:
                invalid_tags.append({"index": i, "tags": dropped})
        hoard.append(hv)
    body = {"voices": hoard}
    if product:  # 无归因不带 product（引擎 UNKNOWN 档），不本地拦截
        body["product"] = product
    out = None
    fallback = False
    try:
        out = _http("POST", _SUBMIT_HOARDING, body, base=JAVA_BASE, key=_eff_key())
    except ToolError as ex:
        if ex.code == 404:
            fallback = True  # 囤积端点未部署 → 落到下方 legacy 回落
        elif not _eff_key() or ex.code == -32012:
            if _SERVER_FACE.get():
                # 服务面（HTTP）：不代签身份。匿名令牌按设备锚点签发，一进程
                # 一锚点会把配额/声量/归因全搅在一起（服务端多用户形态的
                # 已拍板口径：formal/host key + 按请求透传）。
                raise ToolError(
                    "服务面（HTTP 传输）不代签身份：请在本请求带上 "
                    "Authorization: Bearer <VOD key>，或改用 stdio 形态的匿名链",
                    code=-32012)
            if _explicit_key():
                _raise_explicit_key_rejected(_eff_key())
            # 缺 key/匿名令牌失效 → 零字段匿名令牌 → 落 runtime.json → 重试一次
            token = _acquire_anon_token_or_raise()
            JAVA_KEY = token
            _save_runtime({"java_key": token, "token_tier": "anonymous"})
            out = _http("POST", _SUBMIT_HOARDING, body, base=JAVA_BASE, key=_eff_key())
        else:
            raise  # 网络/413 等如实上抛
    if not fallback:
        server_ids = (out.get("voiceIds") or out.get("data", {}).get("voiceIds")
                      or [])
        # 引擎侧 rejected（产品校验拒绝等）透出，不吞（对齐 widget rejected 口径）
        engine_rejected = ((out or {}).get("rejected")
                           or ((out or {}).get("data") or {}).get("rejected")
                           or [])
        if server_ids:
            accepted = len(server_ids)
            voice_ids.extend(server_ids)
        else:
            # 回执缺失/整批被拒 → 不得兜底计成功（实锤缺陷：空 voiceId 记成功
            # 且宿主模型据此谎报"已提交"）。accepted 以真实回执为准。
            accepted = 0
            voice_ids.extend([""] * len(items))
            if not engine_rejected:
                engine_rejected = [{"reason": "引擎回执未含 voiceIds（提交结果未知），请勿视为已收录"}]
        task_ids.extend([None] * len(items))  # 囤积语义：无即时任务
        result = {"accepted": accepted, "voiceIds": voice_ids,
                  "taskIds": task_ids, "rejected": rejected + engine_rejected,
                  "analysis": "deferred",  # 囤积语义明示（V6 运营批量消费）
                  "path": "hoarding",
                  "echo": _echo_plan(items, voice_ids)}
        if invalid_tags:  # 分类白名单外值被丢弃（不拒收声音，只丢 tag）
            result["invalidTags"] = invalid_tags
        if out.get("productRegistered") is not None:
            result["productRegistered"] = out.get("productRegistered")
        _attach_attribution(result, attr)      # 来源+证据留痕（S99）
        _remember_attribution(attr)            # 只记有字面证据的归因（S95/S100）
        _ledger_submit(items, voice_ids, task_ids, product,
                        _merge_ledger(ledger_extra, attr))
        result["pendingFlush"] = _flush_pending(product)
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
            elif (not _eff_key() or e.code == -32012) and not voice_ids:
                if _SERVER_FACE.get():
                    rejected.append({"index": i, "reason":
                        "服务面（HTTP 传输）不代签身份：请带 Authorization: Bearer <VOD key>"})
                    continue
                if _explicit_key():
                    _raise_explicit_key_rejected(_eff_key())
                # 零字段匿名令牌：缺 key/401 → 自动取令牌 → 落 runtime.json → 重试一次
                token = _acquire_anon_token_or_raise()
                JAVA_KEY = token
                _save_runtime({"java_key": token, "token_tier": "anonymous"})
                vid, tid = _legacy_submit(i, v, content)
                accepted += 1
                voice_ids.append(vid)
                task_ids.append(tid)
            else:
                rejected.append({"index": i, "reason": msg[:120]})
    result = {"accepted": accepted, "voiceIds": voice_ids,
              "taskIds": task_ids, "rejected": rejected,
              "path": "legacy-fallback",
              "echo": _echo_plan(items, voice_ids)}
    _attach_attribution(result, attr)
    if accepted:
        _remember_attribution(attr)
    _ledger_submit(items, voice_ids, task_ids, product,
                   _merge_ledger(ledger_extra, attr))
    result["pendingFlush"] = _flush_pending(product)
    return result


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
            # 匿名令牌 401 ≠ 配置错误：报"过期待重领"而非"rejected"，
            # 避免 runtime 残留过期匿名令牌时被误读为正式 key 失效
            # （显式 key 被拒仍报 rejected——fail fast 口径不变）
            if not _explicit_key():
                return {"ok": False, "reason": "expired-anonymous", "fingerprint": fp,
                        "note": "匿名令牌已过期：下次提交自动重领，无需操作"}
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
        if _explicit_key():
            # 旧版残留凭据检测位（评审拍板项）：显式 key 存活即在位提示自愈路径，
            # 不等提交撞 401 才发现（codex 0.2.3 残留 key 挡匿名链的实锤教训）
            out["legacyKeyHint"] = _legacy_key_hint()
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
        _warn_if_cloned(cfg, p)
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


def _uptime_seconds() -> float:
    """本机 uptime（秒）。独立函数：测试可 monkeypatch，消除对宿主机器的依赖
    （实锤：test_clone_image_detection_warns 曾硬编码 boot_age=7 天与真机
    /proc/uptime 实值比较，uptime>7 天的机器必红——环境相关测试缺陷）。"""
    return float(open("/proc/uptime").read().split()[0])


def _warn_if_cloned(cfg: dict, p: Path) -> None:
    """preset 克隆镜像检测（D-key-guard-3①延伸，仅告警不阻断）：
    firstBootAt 距今显著超过本机 uptime（>1h 容差）→ 本机状态大概率来自
    母机镜像克隆——所有克隆机共享同一 device 锚点/账本，声量与配额会收敛。
    判据：firstBootAt 的"年龄" > uptime+容差 ⇒ 首启发生在"这台机器"存在之前。"""
    import time as _t
    if _distribution() != "preset":
        return
    try:
        boot = _t.mktime(_t.strptime(cfg["firstBootAt"], "%Y-%m-%dT%H:%M:%S"))
        uptime_s = _uptime_seconds()
    except (KeyError, ValueError, OSError) as ex:
        # 收窄捕获（原 except Exception: pass 吞掉真实异常，告警失效不可见）：
        # 只吞解析类异常（缺字段/格式坏/读不到 /proc），其余如实上抛
        _log(f"clone 检测跳过（无法解析 firstBootAt/uptime）：{ex}")
        return
    if _t.time() - boot > uptime_s + 3600:
        _warn("疑似镜像克隆机：firstBootAt 早于本机 uptime——克隆分发未清 "
              "runtime.json，所有克隆机共享同一设备锚点/账本。请在镜像冻结前 "
              "uninstall 或删除 runtime.json（装机 checklist ②）")


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


def _extract_anon_token(out: object) -> str | None:
    """从令牌端点响应提取 token（真源契约：引擎 ApiResponse 信封
    {"code":200,"data":{"token":...}}；顶层扁平 {"token":...} 兼容历史形态）。"""
    if not isinstance(out, dict):
        return None
    data = out.get("data")
    token = data.get("token") if isinstance(data, dict) else None
    if not token:
        token = out.get("token")
    return token if isinstance(token, str) and token else None


def _fetch_anon_token() -> str | None:
    """零字段匿名令牌（T7b 定稿）：渠道由引擎囤积入库侧固定赋值 vod-agent
    （链路即渠道，客户端不自报）——本端保持空 body（方案 C 原样）。
    D-anon-verify（2026-11-05 真机实锤）：引擎返回 ApiResponse 信封，
    顶层取 token 恒 None → 无 key 首提必 -32012，信封解析为必经路径。"""
    try:
        out = _http("POST", _TOKEN_PATH, {}, base=JAVA_BASE, key="", timeout=15)
        return _extract_anon_token(out)
    except ToolError:
        return None


def devkit_info(params: dict, client_info: dict | None = None) -> dict:
    return provenance.info_payload(client_info)


# 工具名 → 处理器（是否接收 client_info）


# ---- 两段式提交（D-token-approval-2 极简形态：插件本地 draft→commit，引擎零改动）----
# 定性：最强摩擦+审计链，非人类确认硬保证（decisions 既有纠偏）。
# draft 暂存 runtime.json（cap 10 环形+TTL 600s），commit 单次消费后内部复用
# submit_voices 既有链——配额/幂等/归因/回显语义零新增。stage=draft/committed
# 入账本：绕过两段式的直接提交在账本层面可检测（验收③）。

_DRAFT_KEY = "drafts"
_DRAFT_CAP = 10
_DRAFT_TTL = 600  # 秒；过期 commit 拒收，草稿自动作废


def _drafts_purge(store: dict) -> dict:
    """过期草稿清除（读时惰性，无后台任务）。"""
    import time as _time
    now = _time.time()
    return {k: v for k, v in store.items()
            if v.get("expiresAt", 0) > now}


def _drafts_load() -> dict:
    """草稿库现读 + 过期惰性清除（draft/commit 单源共用，禁双边漂移）。"""
    return _drafts_purge(_runtime_cfg().get(_DRAFT_KEY) or {})


def draft_voices(params: dict, client_info: dict | None = None) -> dict:
    """两段式第一步：校验+暂存草稿+签发一次性令牌（不提交任何数据）。"""
    import time as _time
    voices_in = params.get("voices", [])
    allowed_tags = _allowed_tags()
    invalid_tags = []
    clean = []
    for i, v in enumerate(voices_in):
        content = str(v.get("content", "")).strip()
        if not content:
            raise ToolError(f"第 {i + 1} 条 content 为空", code=-32602)
        if len(content) > 2000:
            raise ToolError(f"第 {i + 1} 条 content 超 2000 字（{len(content)}）", code=-32602)
        item = {"content": content}
        if v.get("tags"):
            kept, dropped = _filter_tags(v["tags"], allowed_tags)
            if kept:
                item["tags"] = kept
            if dropped:
                invalid_tags.append({"index": i, "tags": dropped})
        if v.get("userType"):
            item["userType"] = v["userType"]
        # D-followup-impl-2：追问补充随 draft 暂存（commit 复用 payload 原样上送），
        # 单源 _followup_fields 与主路径同口径
        item.update(_followup_fields(v))
        clean.append(item)
    if not clean:
        raise ToolError("voices 为必填且至少 1 条", code=-32602)
    # 归因（D-attrib-B）：草稿与提交同一优先级链，证据入库可审
    attr = _attribute_product([(i, v, v["content"]) for i, v in enumerate(clean)], params)
    product = attr["product"]
    _remember_attribution(attr)

    import secrets
    draft_id = "draft_" + secrets.token_hex(8)
    token = secrets.token_hex(16)
    payload = {"voices": clean}
    if product:
        payload["product"] = product
    # 载荷 sha（防 draft→commit 间改写：commit 校验插件侧重算值一致）
    import hashlib
    payload_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    store = _drafts_load()
    store[draft_id] = {
        "payload": payload, "payloadSha256": payload_sha, "tokenHash": _sha256(token),
        # D-resume-commit-1：token 明文随草稿落盘（runtime.json 0600，与 java_key
        # 同级保护）。token 的威胁模型是"防载荷改写"而非"同意凭证"——落盘不放大
        # 风险，换断回合可续：agent 回合中断后凭 draftId 即可恢复提交（此前
        # approvalToken 只存在于 draft 响应文本，回合断即丢失，只能重开草稿）
        "token": token,
        "product": product, "productSource": attr.get("source"),
        "productEvidence": attr.get("evidence") or [],
        "createdAt": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "expiresAt": _time.time() + _DRAFT_TTL,
    }
    while len(store) > _DRAFT_CAP:  # 环形：最旧先淘汰
        store.pop(next(iter(store)))
    _save_runtime({_DRAFT_KEY: store})

    out = {
        "draftId": draft_id,
        "approvalToken": token,
        "payloadSha256": payload_sha,
        "expiresInSeconds": _DRAFT_TTL,
        "contents": [{"index": i, "content": it["content"]} for i, it in enumerate(clean)],
        "instruction": ("把 contents 逐条原样展示给用户核对（禁止改写概括），明确问"
                        "「确认提交吗」。用户明确同意前禁止调用 vod_commit_voices；"
                        "不同意则停（草稿 10 分钟后自动作废）。"),
    }
    _attach_attribution(out, attr)  # 草稿阶段也让归因来源可审（commit 回执沿用）
    if invalid_tags:
        out["invalidTags"] = invalid_tags
    return out


def commit_voices(params: dict, client_info: dict | None = None) -> dict:
    """两段式第二步：令牌校验→单次消费→复用 submit_voices 既有提交链。

    D-resume-commit-1：approvalToken/payloadSha256 可省略——draftId 命中本地
    未过期草稿时自动恢复（断回合续提交）。显式传入仍走原校验（传了假 sha
    照样拒），恢复路径的完整性由签发时落盘的 sha/token 保证，语义不放宽。
    """
    draft_id = str(params.get("draftId", ""))
    if not draft_id:
        raise ToolError("draftId 为必填（取自 vod_draft_voices 返回原样透传）", code=-32602)

    store = _drafts_load()
    draft = store.get(draft_id)
    if draft is None:
        raise ToolError("草稿不存在或已过期（10 分钟 TTL），请重新 vod_draft_voices", code=-32011)
    token = str(params.get("approvalToken", "")) or str(draft.get("token", ""))
    payload_sha = str(params.get("payloadSha256", "")) or str(draft["payloadSha256"])
    if draft["tokenHash"] != _sha256(token):
        raise ToolError("审批令牌不匹配（draft 返回的 approvalToken 原样透传）", code=-32011)
    if draft["payloadSha256"] != payload_sha:
        raise ToolError("载荷校验不符（payloadSha256 与 draft 签发值不一致，禁止改写已确认内容）",
                        code=-32011)
    # 单次消费：先摘除再提交——提交中途崩溃也不会二次提交（宁可丢一单重走流程）
    store.pop(draft_id)
    _save_runtime({_DRAFT_KEY: store})

    out = submit_voices(dict(draft["payload"]), client_info,
                        ledger_extra={"stage": "committed", "draftId": draft_id})
    out["twoPhase"] = True
    out["draftId"] = draft_id
    return out


def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()

def check_update(params: dict, client_info: dict | None = None) -> dict:
    from vod_mcp import update_check as uc
    return uc.check(params)


def list_skills(params: dict, client_info: dict | None = None) -> dict:
    from vod_mcp import skills_registry as sr
    try:
        return sr.list_skills(params)
    except sr.SkillError as e:
        raise ToolError(str(e), code=e.code)


def retrieve_skill(params: dict, client_info: dict | None = None) -> dict:
    from vod_mcp import skills_registry as sr
    try:
        return sr.retrieve_skill(params)
    except sr.SkillError as e:
        raise ToolError(str(e), code=e.code)


_HANDLERS = {
    "vod_check_update": check_update,
    "vod_list_skills": list_skills,
    "vod_retrieve_skill": retrieve_skill,
    "vod_submit_voices": submit_voices,
    "vod_list_submitted": list_submitted,
    "vod_devkit_info": devkit_info,
    "vod_auth_status": auth_status,
    "vod_draft_voices": draft_voices,
    "vod_commit_voices": commit_voices,
}


def dispatch(name: str, params: dict, client_info: dict | None = None) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"未知工具: {name}", code=-32601)
    needs_host = handler in (devkit_info, submit_voices, auth_status, draft_voices, commit_voices)
    return handler(params, client_info) if needs_host else handler(params)
