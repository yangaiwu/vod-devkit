"""出口与身份：HTTP 调用、meta 缓存、key 探针、匿名令牌、请求身份 contextvars。

与 runtime_state 的分工：本模块负责"跟引擎说话"，状态落盘一律转调 runtime_state。
共享符号必须用**模块属性访问**（net._http / net.JAVA_KEY）——`from net import _http`
会把引用冻结在导入期，测试 monkeypatch 就静默失效（P2 的 patch 面纪律）。
"""
import contextvars
import json
import os
import urllib.error
import urllib.request

from vod_mcp import DEFAULT_JAVA_BASE
from vod_mcp import runtime_state as rt
from vod_mcp import server_face


_REQ_KEY = contextvars.ContextVar("vod_req_key", default=None)


# 传输面标志（ARCH-DEP-01，2026-11-19 走查）：真源已抽到零依赖的 `vod_mcp.server_face`。
# 这里保留同名别名，是为了不让 `net._SERVER_FACE.set()/reset()` 与既有测试的
# monkeypatch 失效——别名与真源是**同一个 ContextVar 对象**，不存在两份状态。
_SERVER_FACE = server_face.SERVER_FACE

# 匿名令牌代领总开关（D-token-machine-1 安全护栏）：进程级布尔，启动期由
# transport_remote 按绑定地址决定——非回环绑定（可能被反代/公网触达）默认关闭
# 代领，避免"任何能连端口的进程都能用这台机的身份提交、消耗额度"。
# 回环绑定（同机部署的默认形态）保持开启，与本地 stdio 完全一致。
ANON_MINT_DISABLED = False


def _live(field: str, default: str = "") -> str:
    """身份类值的**调用期**解析：env（平台注入）> runtime.json 现读 > 默认。

    为什么不能在 import 期定常量（D-state-read-1）：MCP server 是长驻进程，
    `auth init --apply` 换 key、自动领取匿名令牌、安装器改 apiBase 都会改
    runtime.json；常量把进程启动那一刻的值冻结住，表现是"明明配了/换了 key，
    工具仍用旧的"（401 或打到旧环境）。读失败回落默认，不阻断出口。
    """
    env_key = "VOD_JAVA_API_KEY" if field == "java_key" else "VOD_JAVA_API_BASE"
    env = os.environ.get(env_key, "")
    if env:
        return env
    try:
        val = rt._runtime_cfg().get(field)
    except Exception:      # noqa: BLE001  状态文件坏/不可读时不阻断出口
        val = None
    if val:
        return str(val)
    # 镜像回落：本进程刚写的值（_runtime_update 同步镜像）与测试桩都走这条路；
    # 文件优先保证"外部（auth init / 重装）改过的值"立刻生效。
    return str(rt._RT.get(field) or default)


def _java_key() -> str:
    # 显式 set 过的模块属性优先（monkeypatch / 历史赋值）：这是仓内已有的 patch 面契约
    # （"共享符号用模块属性访问"），现读只在**没人 set** 时生效。
    override = globals().get("JAVA_KEY")
    if override:
        return str(override)
    return _live("java_key", "")


def _java_base() -> str:
    override = globals().get("JAVA_BASE")
    if override:
        return str(override)
    return _live("java_base", DEFAULT_JAVA_BASE)


def __getattr__(name: str):
    """`net.JAVA_KEY` / `net.JAVA_BASE` 一律**现读**（PEP 562 模块级 __getattr__）。

    保留这两个名字只为不动既有调用点与测试的 patch 面：属性被显式 set 过
    （monkeypatch / 历史赋值）时优先用 set 的值，否则每次现读 runtime。
    模块**内部**必须直接调 `_java_key()` / `_java_base()`——模块内部的全局名查找
    不会触发 __getattr__，写成 `JAVA_KEY` 会 NameError 或读到旧值。
    """
    if name == "JAVA_KEY":
        return _java_key()
    if name == "JAVA_BASE":
        return _java_base()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _eff_key(explicit=None) -> str:
    """当前生效的 key：显式参数 > 请求头（HTTP 面）> env/runtime（stdio 面）。"""
    if explicit is not None:
        return explicit
    return _REQ_KEY.get() or _java_key()


_META_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/meta"


_META_TTL = 24 * 3600


_META_SNAPSHOT: dict = {"products": []}


def _load_meta(force: bool = False) -> dict:
    """可漂移值动态取：缓存 TTL 24h，引擎端点不可达时回退快照并标 stale。
    真源=引擎 meta 接口（productCatalog/products）——**本模块不维护任何产品
    清单**，离线时宁可不归因也不拿本地表猜。

    T7i：productCatalog=[{id,name}]（t_vod_product 运营预置，meta 组装）——
    提交产品归因按平台主键 id 的解析真源；老引擎无该键=catalog 空。

    **2026-11-12 引擎契约收紧**：
      · `nameAliases` / `aliases` 已由引擎删除 → 本函数不再读取；别名能力改由
        attribution 的规则派生 + BRAND_ALIASES 提供。
      · `problemTypes` 改为按产品下发（`?productId=`）：**无参请求不含该键**。
        分类白名单必须用 `collect._allowed_tags(product_id)` 按产品取，见下。
    """
    import time
    cache = rt._RT.get("meta_cache") or {}
    now = time.time()
    if not force and cache.get("data") and now - cache.get("fetchedAt", 0) < _META_TTL:
        return {"products": cache["data"].get("products", _META_SNAPSHOT["products"]),
                "catalog": cache["data"].get("productCatalog") or [],
                "dictVersion": cache["data"].get("dictVersion"),
                "stale": False, "source": "cache"}
    auth_failed = False
    try:
        out = _http("GET", _META_PATH, None, base=_java_base(), key=_eff_key(), timeout=10)
        data = out.get("data") or {}
        if isinstance(data.get("products"), list) and data["products"]:
            rt._runtime_update({"meta_cache": {"fetchedAt": int(now), "data": data}})
            return {"products": data["products"],
                    "catalog": data.get("productCatalog") or [],
                    "dictVersion": data.get("dictVersion"),
                    "stale": False, "source": "meta"}
    except ToolError as e:
        # D-meta-anon-1：只有 401（已归一为 -32012）才值得走匿名领取链。
        # 网络不可达/超时时若也去领令牌，等于再等 15s 且失败不写缓存 →
        # 每次 collect 调用重复这 25s（引擎抖动时把采集拖垮）。非鉴权错误
        # 直接落快照，把"引擎不可达"如实暴露，不伪装成"没 key"。
        auth_failed = (e.code == -32012)
    # D-meta-anon-1（2026-11-18 真机实锤，与 dsh 侧同构）：未配 key 的默认形态下
    # meta 请求先于「提交遇 401 才领令牌」发生 → 401 → 名录恒空 → 归因必失败
    # → 而领令牌要提交成功、提交成功要归因成功 → 默认形态下一条声音都提交不了。
    # 修法：401 先领匿名令牌，带 key 重试一次。
    if auth_failed and not _eff_key():
        token = _fetch_anon_token()
        if token:
            try:
                rt._runtime_update({"java_key": token, "token_tier": "anonymous"})
            except Exception:
                pass
            try:
                out = _http("GET", _META_PATH, None, base=_java_base(), key=token, timeout=10)
                data = out.get("data") or {}
                if isinstance(data.get("products"), list) and data["products"]:
                    rt._runtime_update({"meta_cache": {"fetchedAt": int(now), "data": data}})
                    return {"products": data["products"],
                            "catalog": data.get("productCatalog") or [],
                            "dictVersion": data.get("dictVersion"),
                            "stale": False, "source": "meta-anon"}
            except ToolError:
                pass
    # 快照不含分类白名单：collect._allowed_tags 取不到产品分类时 allowed 为空=不校验
    # （宁可放行也不误杀采集）
    return {"products": _META_SNAPSHOT["products"], "catalog": [],
            "dictVersion": None,
            "stale": True, "source": "snapshot"}


class ToolError(Exception):
    def __init__(self, message: str, code: int = -32000):
        super().__init__(message)
        self.code = code


def _http(method: str, path: str, body: dict | None = None,
          base: str | None = None, key: str | None = None, timeout: int = 30) -> dict:
    """统一出口：一律携带 Authorization Bearer（E1 修复：认证头缺失）。

    base/key 缺省在调用时解析模块级配置（不能用函数默认值——定义时即冻结，
    环境变更/测试 monkeypatch 均无法生效）。
    """
    base = base if base is not None else _java_base()
    key = key if key is not None else _java_key()
    # 传输协议守卫：非本机回环一律要求 https（Bearer 不得明文过公网）
    _host = base.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if not base.startswith("https://") and _host not in ("127.0.0.1", "localhost", "::1"):
        raise ToolError(
            f"上游 {base} 非 https 且非本机回环——Bearer key 明文外发被拒"
            "（配置 VOD_JAVA_API_BASE 为 https:// 地址）", code=-32014)
    url = base.rstrip("/") + path
    rt._log(f"http {method} {url} key={'yes' if key else 'no'}")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json",
               # VOD-DEVICE：设备锚点（install_nonce=首启自生成常驻，零新增状态）——
               # 引擎据此建每设备独立锚点（NAT/产品分发不再收敛）；服务端缺失回落 legacy
               "X-Vod-Device-Id": rt._install_nonce()}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        if e.code == 401:
            # 引擎 401 原文透传（probe_key 靠它区分"设备绑定校验失败"=匿名令牌
            # 跨设备（token 有效,本机没用过）vs "API Key 无效"=真坏 key；丢原文
            # 会让探针把正常匿名场景误判成 rejected）
            raise ToolError(
                f"鉴权失败（{base}）：{detail or '检查 VOD_JAVA_API_KEY 配置'}",
                code=-32012) from e
        raise ToolError(f"上游返回 {e.code}: {detail}", code=e.code) from e
    except urllib.error.URLError as e:
        raise ToolError(f"上游不可达（{base}）: {e.reason}", code=-32001) from e


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
    explicit = key is not None  # 显式传参（服务面=请求头 Bearer）按显式口径判
    key = key if key is not None else _java_key()
    fp = _fingerprint(key)
    if not key:
        return {"ok": None, "reason": "no-key", "fingerprint": None}
    try:
        _http("GET", _META_PATH, None, key=key, timeout=timeout)
        return {"ok": True, "reason": "verified", "fingerprint": fp}
    except ToolError as ex:
        code = ex.code
        msg = str(ex)
        if code == 401 or code == -32012:
            # 引擎 401 两类语义（原文区分，实锤 2026-11-13）：
            # - "设备绑定校验失败"：匿名令牌是设备锚点绑定的——token 本身有效，
            #   只是本机（nonce）不是签发设备。这是正常场景（换机/重装/仓内与
            #   payloads 两份 runtime 的 nonce 漂移），不是 key 坏。归
            #   device-mismatch：不拦（放行），提示在本设备重领。
            # - "API Key 无效或已失效"：真坏 key → rejected（fail fast 不变）。
            # 旧语义（显式→rejected / 非显式→expired-anonymous）保留为无原文
            # 时的兜底分类。
            if "设备绑定校验失败" in msg:
                return {"ok": False, "reason": "device-mismatch", "fingerprint": fp,
                        "note": "匿名令牌与本设备不匹配：令牌本身有效，"
                                "在本设备重新申请令牌后可继续（POST /external/token，"
                                "首次提交或 vod_auth_ensure 时自动完成）"}
            if not (explicit or _explicit_key()):
                # 匿名令牌 401 ≠ 配置错误：报"过期待重领"而非"rejected"，
                # 避免 runtime 残留过期匿名令牌时被误读为正式 key 失效
                # （显式 key 被拒仍报 rejected——fail fast 口径不变）
                return {"ok": False, "reason": "expired-anonymous", "fingerprint": fp,
                        "note": "匿名令牌已过期：下次提交自动重领，无需操作"}
            return {"ok": False, "reason": "rejected", "fingerprint": fp}
        return {"ok": None, "reason": "unreachable", "fingerprint": fp}


def _key_state() -> dict:
    return {"configured": bool(_java_key()), "fingerprint": _fingerprint(_java_key()),
            "base": _java_base(),
            "note": "已配置" if _java_key() else "未配置（首次提交或 vod_auth_ensure 时自动取匿名令牌）"}


def _explicit_key() -> bool:
    """当前 JAVA_KEY 是否为显式配置（正式/宿主 key）而非本会话自动领取的匿名令牌。

    判据：环境变量显式注入（权威，env 优先级最高的既有口径）或
    token_tier != "anonymous"。匿名令牌过期/被吊销时 401 应走重领链；
    显式 key 被 401 拒绝时必须 fail fast（静默降级匿名=配置错误被吞=归因错位，
    「注入 appkey」场景的锚定承诺会变成假的）。
    """
    if bool(os.environ.get("VOD_JAVA_API_KEY")):
        return True
    tier = str(rt._runtime_cfg().get("token_tier")
               or rt._RT.get("token_tier") or "")
    return bool(_java_key()) and tier != "anonymous"


def _legacy_key_hint() -> str:
    """旧版残留凭据自愈提示（评审拍板项）：出错时给可操作路径，不发公告靠用户撞。
    含当前插件版本与重装命令——重装会刷新 runtime/清掉旧 key 残留。"""
    version = getattr(__import__("vod_mcp"), "__version__", "unknown")
    return ("若为旧版安装残留凭据：更新插件（当前 v" + version + "）并重装即可清除——"
            "npx vod-devkit@latest install --target <宿主> --product <产品名>；"
            "或移除 VOD_JAVA_API_KEY 环境变量走匿名档")


_KEY_GUIDANCE: list[dict[str, object]] = [
    {"order": 1, "action": "auto-token", "label": "首次提交时插件自动申请零字段匿名令牌（默认路径，无需注册）"},
    {"order": 2, "action": "upgrade", "label": "提交量达上限后升级正式 key：联系 VOD 运营（低信任档→正式档）"},
    {"order": 3, "action": "host", "label": "宿主平台整体对接可获宿主 key：由宿主运维持有（高信任档）"},
]


_TOKEN_PATH = "/rest/developer/manager/hdvodmngservice/v1/external/token"


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
    顶层取 token 恒 None → 无 key 首提必 -32012，信封解析为必经路径。

    ARCH-ERR-04（2026-11-19 走查）：失败必须留痕。此前整段 `except ToolError: return None`
    让"端点不可用/401/网络断"三种原因一起消失，调用方只看到笼统的"令牌不可用"，
    排障只能靠猜。
    """
    try:
        if ANON_MINT_DISABLED:
            rt._log("anon-token: 跳过（非回环远程面未开 --allow-anon-mint）")
            return None      # 非回环远程面：不代领（调用方须自带 Bearer）
        out = _http("POST", _TOKEN_PATH, {}, base=_java_base(), key="", timeout=15)
        token = _extract_anon_token(out)
        if not token:
            rt._log(f"anon-token: 响应里没有 token（信封形态可能变了）：{str(out)[:200]}")
        return token
    except ToolError as e:
        rt._log(f"anon-token: 领取失败 code={e.code}：{e}")
        return None


def _acquire_anon_token_or_raise() -> str:
    """缺 key/匿名令牌失效 → 领零字段匿名令牌；端点不可用则如实报错。"""
    token = _fetch_anon_token()
    if not token:
        hint = ("；远程面若绑定非回环地址，代领默认关闭——请带 Authorization: Bearer <key>，"
                "或服务端以 --allow-anon-mint 显式开启" if ANON_MINT_DISABLED else "")
        raise ToolError(
            "未配置接入 key 且匿名令牌端点不可用。引导："
            + "；".join(str(g["label"]) for g in _KEY_GUIDANCE) + hint, code=-32012)
    return token
