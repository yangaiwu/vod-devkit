"""远程面探活与安装期校验（远程 attach / 产品名录硬校验）。"""
import json
import os
import sys

from vod_mcp import paths


def _expected_remote_tools() -> set:
    """远程面应当暴露的工具集 = 契约全集 - REMOTE_WITHHELD（只摘进程内开关 packs_configure）。"""
    from vod_mcp import packs as _packs
    contract = json.loads((paths.ASSETS / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
    return set(contract["tools"]) - set(_packs.REMOTE_WITHHELD)


def _probe_remote(url: str, token: str, timeout: int = 15,
                  verify_token: bool = True) -> list:
    """远程 MCP 端点探活：initialize + tools/list，返回工具名清单（失败抛 RuntimeError）。

    走 stdlib urllib（安装器零第三方依赖红线）；Accept 双类型，兼容 SSE 单事件响应。
    探活在**写入任何配置之前**执行——装不上就不留半成品。

    B2（2026-11-13 真机实锤）：握手+工具面是连接级，token 有效性没验——坏 key
    照样装上，用户首次提交才发现 401。与"--product fail fast（归因错误比报错
    糟）"纪律不对称。verify_token=True 时追加第 3 步：经远程面真调一次
    vod_auth_status（远程面把请求头 Bearer 透传引擎做 keyCheck 探针），引擎判
    无效（探针回 rejected）→ RuntimeError 拒装；探针不可达（引擎/网络问题）→
    放行（网络问题不是 key 问题，不许误伤断网环境安装）。doctor 的旧调用途
    （用户可能没配 token）与安装期不同，verify_token=False 保持旧连接级语义。
    """
    import urllib.request

    def _post(payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers={"content-type": "application/json",
                     "accept": "application/json, text/event-stream",
                     **({"Authorization": f"Bearer {token}"} if token else {})})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        if body.startswith("event:") or body.startswith("data:"):
            for line in body.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    break
        data = json.loads(body or "{}")
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"JSON-RPC 错误：{data['error']}")
        return data

    _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2025-06-18",
                      "clientInfo": {"name": "vod-devkit-installer", "version": "1"},
                      "capabilities": {}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    listed = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t.get("name") for t in (listed.get("result") or {}).get("tools") or []]
    if not names:
        raise RuntimeError("tools/list 返回空——端点可能不是 Streamable HTTP MCP")
    if verify_token and token and "vod_auth_status" in names:
        _probe_remote_token(url, token, timeout)
    return names


def _probe_remote_token(url: str, token: str, timeout: int) -> None:
    """B2 第 3 步：经远程面真调 vod_auth_status 验 token（引擎是唯一权威）。

    远程面把请求头 Bearer 透传给 keyCheck 探针打引擎 GET /external/meta：
    - keyCheck.ok=True（verified）→ 通过
    - keyCheck.reason=rejected → RuntimeError（坏 key 拒装，零副作用）
    - reason ∈ {no-key, unreachable, expired-anonymous, device-mismatch} 或
      keyCheck 缺失/探针不可用 → 放行（无法验证≠无效；三态判定语义与
      tools.probe_key 一致——device-mismatch 是匿名令牌设备锚点漂移的正常
      场景：token 有效只是本机不是签发设备，提交时会自动重领）
    """
    import urllib.request
    import urllib.error

    def _post(payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers={"content-type": "application/json",
                     "accept": "application/json, text/event-stream",
                     "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        if body.startswith("event:") or body.startswith("data:"):
            for line in body.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    break
        data = json.loads(body or "{}")
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"JSON-RPC 错误：{data['error']}")
        return data

    _post({"jsonrpc": "2.0", "id": 10, "method": "initialize",
           "params": {"protocolVersion": "2025-06-18",
                      "clientInfo": {"name": "vod-devkit-installer", "version": "1"},
                      "capabilities": {}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    called = _post({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                    "params": {"name": "vod_auth_status", "arguments": {}}})
    content = ((called.get("result") or {}).get("content") or [{}])[0]
    try:
        status = json.loads(content.get("text") or "{}")
    except ValueError:
        return  # 回执异常（旧版远程面等）：无法验证≠无效，放行
    check = status.get("keyCheck")
    if not isinstance(check, dict):
        return  # 远程面未透传 keyCheck（旧版）：连接级已过，放行
    if check.get("reason") == "rejected":
        fp = check.get("fingerprint")
        raise RuntimeError(
            f"token 无效（引擎判定 rejected，指纹 {fp}）——"
            "请确认 VOD 平台签发的 key；探活先于写入，未装任何配置")


def _remote_reachable(url: str, timeout: int = 6) -> bool:
    """端点是否可达：GET 得到任何 HTTP 响应（405 是远程面契约的正常应答）即算通。"""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True      # 405/401/406 都证明端点活着
    except Exception:
        return False


def _catalog_cache_path():
    """产品名录缓存落在机器级 state 目录（与令牌同域，0600）。

    为什么缓存：产品名校验每跑一次就要一枚匿名令牌，而引擎对"同网络当日/同 IP 每小时"
    的**签发次数**限流（真机撞到 100/日、60/小时）。名录 7 天不变的东西不该每次去问引擎。
    """
    from vod_mcp import paths as _paths
    return _paths.machine_state_home() / "product-catalog.json"


def _ttl_seconds() -> float:
    """名录缓存 TTL（秒）。配错（如 `7d`）按默认 7 天并告警——不许因为一个 env 值
    把安装整个打断（真机实锤：VOD_PRODUCT_CATALOG_TTL=7d 直接抛 ValueError traceback）。"""
    raw = os.environ.get("VOD_PRODUCT_CATALOG_TTL")
    if raw is None or not str(raw).strip():
        return 7 * 86400
    try:
        return float(str(raw).strip())
    except ValueError:
        print(f"[vod-devkit] VOD_PRODUCT_CATALOG_TTL={raw!r} 不是秒数，按默认 7 天处理"
              "（示例：604800 = 7 天，0 = 禁用缓存）", file=sys.stderr)
        return 7 * 86400


def _read_catalog_cache(base: str):
    """命中返回 (catalog, age_secs)，否则 None。TTL 可用 VOD_PRODUCT_CATALOG_TTL 覆盖（秒）。"""
    import time
    ttl = _ttl_seconds()
    if ttl <= 0:
        return None
    p = _catalog_cache_path()
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if str(d.get("base") or "") != str(base):
        return None           # 换了引擎地址 → 缓存作废
    age = time.time() - float(d.get("at") or 0)
    if age > ttl:
        return None
    cat = d.get("catalog")
    return (cat, age) if isinstance(cat, list) and cat else None


def _write_catalog_cache(base: str, catalog: list) -> None:
    """原子写（tmp → os.replace，0600）：与 state 其它写入口同款纪律，
    并发读到半截会当 miss（可接受，但不要留下半文件）。"""
    import time
    p = _catalog_cache_path()
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"base": str(base), "at": time.time(), "catalog": catalog},
                                  ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError as e:  # noqa: BLE001  权限设不上要能看见（缓存里有产品名录，不算密钥）
            print(f"[vod-devkit] 产品名录缓存权限设置失败（{e}），继续使用", file=sys.stderr)
        os.replace(tmp, p)
    except OSError:
        pass                  # 缓存写不进不是安装的失败条件
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _validate_product_or_exit(product: str, base: str, refresh: bool = False) -> bool:
    """D-product-id-2：安装期产品硬校验（B 案，2026-11-05 拍板）。
    --product 命中 meta productCatalog（名字大小写不敏感或 id 精确）才放行；
    未命中/目录不可达一律拒绝安装并给可执行引导（宁可不装不可装错）。

    0.5.12（真机实锤）：引擎多实例时「签发令牌的实例」与「校验令牌的实例」可能不同步——
    POST /external/token 刚拿到的匿名令牌，紧随其后 GET /external/meta 就 401
    「API Key 无效或已失效」。这不是网络故障，文案必须点明（实际踩过：照「不可达」
    去查网络，白查）；401 时换设备锚点重领一次令牌能救掉偶发的那一半。
    """
    base = str(base).rstrip("/")   # S152/P5：尾斜杠一处归一——否则 http://h/ 拼出 //rest，
    # 且同一引擎地址在缓存键里会变成两个条目（换写法 = 缓存失效）
    import urllib.request
    import urllib.error
    import uuid
    from vod_mcp import net as _net
    # ARCH-CALL-06：路径前缀单一真源在 net（此前这里硬编码一份，与 net/doctor 各一份）
    api_prefix = _net.API_PREFIX
    key = os.environ.get("VOD_JAVA_API_KEY", "")
    ua = "vod-devkit-installer/1"

    def _mint(device: str) -> str:
        """零字段匿名令牌（方案 C 同链）；设备锚点必须与后续请求一致（S1 设备绑定）。"""
        req = urllib.request.Request(
            f"{base}{api_prefix}/external/token", data=b"{}",
            headers={"content-type": "application/json", "X-Vod-Device-Id": device,
                     "User-Agent": ua}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        return (body.get("data") or {}).get("token") or body.get("token") or ""

    def _get(url: str, auth: str, device: str):
        req = urllib.request.Request(url, headers={
            "content-type": "application/json",
            "X-Vod-Device-Id": device,
            "User-Agent": ua,
            **({"authorization": f"Bearer {auth}"} if auth else {}),
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    def _state_identity() -> tuple:
        """机器级 state 里已存的匿名令牌 + 它的设备锚点（install_nonce）。

        装机校验**不该每次新签一枚**：引擎对"同网络当日签发次数"有限流
        （实测撞到 100/日 → 429，整批装机全被挡）。复用 state 的令牌既省配额，
        又避免一次新的设备锚点漂移；device 必须用 state 的 install_nonce，
        否则令牌与设备不配对（S1 设备绑定）。
        """
        try:
            from vod_mcp import runtime_state as _rt
            cfg = _rt._runtime_cfg() or {}
            if str(cfg.get("token_tier") or "") != "anonymous":
                return ("", "")
            tok = str(cfg.get("java_key") or "")
            dev = str(_rt._install_nonce() or "")
            return (tok, dev) if (tok and dev) else ("", "")
        except Exception:  # noqa: BLE001  读不到就当没有，回落新签
            return ("", "")

    def _catalog_once():
        """一个回合：有 state 令牌就复用，否则新设备锚点 + 领令牌 → 读目录。"""
        reuse_tok, reuse_dev = _state_identity()
        if key:
            device, token = uuid.uuid4().hex[:32], key
        elif reuse_tok:
            device, token = reuse_dev, reuse_tok
        else:
            device = uuid.uuid4().hex[:32]
            token = _mint(device)
        status, text = _get(f"{base}{api_prefix}/external/meta", token, device)
        data = (json.loads(text) or {}).get("data") or {}
        cat = data.get("productCatalog")
        if not cat and not key:  # 老引擎 meta 无目录 → 退 /external/products
            status, text = _get(f"{base}{api_prefix}/external/products", token, device)
            data = (json.loads(text) or {}).get("data") or []
            cat = data if isinstance(data, list) else None
        return cat

    # 只认巡检内部注入：必须**同时**有 VOD_MATRIX=1。这行 env 若被从审计日志里抄去单用，
    # 就等于绕过 D-product-id-2 的"宁可不装不可装错"，装出一台产品归属未验证的机器。
    if os.environ.get("VOD_SKIP_PRODUCT_CHECK") == "1" and os.environ.get("VOD_MATRIX") == "1":
        print("[vod-devkit] 跳过产品校验（巡检内部注入：VOD_MATRIX=1 + "
              "VOD_SKIP_PRODUCT_CHECK=1；归因名单在装机时已验过）", file=sys.stderr)
        return True

    catalog, unauthorized, rate_limited = None, False, False
    last_exc: BaseException | None = None
    if not refresh:
        cached = _read_catalog_cache(base)
        if cached:
            catalog = cached[0]
            print(f"[vod-devkit] 产品校验：命中本地缓存（{cached[1] / 3600:.1f} 小时前拉取，"
                  "未请求引擎；要强刷用 --refresh-product-catalog）")
    for attempt in (1, 2):
        if catalog is not None:      # 缓存命中：本地比对即可，不打引擎
            break
        try:
            catalog = _catalog_once()
            if catalog:
                _write_catalog_cache(base, catalog)
            last_exc = None
            break
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code == 401:
                unauthorized = True
            if e.code == 429:
                # 限流：重试只会更糟（配额头是"当日/网络"），立刻停
                rate_limited = True
                break
            if attempt == 2:
                break
        except Exception as e:  # noqa: BLE001  网络抖动也重试一次
            last_exc = e
            if attempt == 2:
                break

    if catalog is None:
        if rate_limited:
            print("[vod-devkit] 产品校验失败：令牌签发被限流（HTTP 429，同网络当日签发次数上限）。\n"
                  "  这不是装机器本身的问题——安装器每校验一次都要一枚匿名令牌，"
                  "密集重装/联调会把日配额打满。\n"
                  "  处置：配 VOD_JAVA_API_KEY 走正式 key（不占匿名配额）；或明天再试；"
                  "或找 VOD 运营调整限流。", file=sys.stderr)
        elif unauthorized:
            print("[vod-devkit] 产品校验失败：引擎鉴权异常（HTTP 401）——刚签发的匿名令牌被"
                  "校验侧拒绝。\n"
                  "  典型原因：引擎多实例的令牌存储/缓存不同步（重试一次通常就过），"
                  "或该环境只接受正式 key。\n"
                  "  这不是网络故障，别先查网络。处置：稍后重跑 install / 配 "
                  "VOD_JAVA_API_KEY / 找 VOD 运营核对引擎。", file=sys.stderr)
        elif last_exc is not None:
            print(f"[vod-devkit] 产品校验不可达（{last_exc.__class__.__name__}），"
                  "拒绝安装（宁可不装不可装错）。\n"
                  "  请核对网络与 --java-api-base；确需离线安装请联系 VOD 运营。",
                  file=sys.stderr)
        else:
            print("[vod-devkit] 产品校验失败：引擎 meta 无 productCatalog 且 "
                  "/external/products 不可用。\n"
                  "  不执行安装（宁可不装不可装错）。请核对 --java-api-base 指向的引擎"
                  "是否已部署 T7i 版本。", file=sys.stderr)
        sys.exit(2)

    p = product.strip()
    hit = any(
        (str(x.get("name") or "").lower() == p.lower())
        or (str(x.get("id")) == p)
        for x in catalog if isinstance(x, dict))
    if not hit:
        sample = " / ".join(str(x.get("name")) for x in catalog[:8] if isinstance(x, dict))
        print(f"[vod-devkit] --product '{product}' 不在产品名录（t_vod_product），拒绝安装。\n"
              "  归因前提无效=内置采集技能/分类/透传全部空转且用户无感知（归因错误比报错更糟）。\n"
              f"  权威名单：GET {api_prefix}/external/products（共 {len(catalog)} 项），"
              f"示例：{sample} …\n"
              "  提示：若该产品刚上线（本地名录缓存可能还是 7 天前的），"
              "加 --refresh-product-catalog 重拉后再试。",
              file=sys.stderr)
        sys.exit(2)
    return True
