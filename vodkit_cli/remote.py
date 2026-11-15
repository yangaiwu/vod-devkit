"""远程面探活与安装期校验（远程 attach / 产品名录硬校验）。"""
import json
import os
import sys

from vodkit_cli import common


def _expected_remote_tools() -> set:
    """远程面应当暴露的工具集 = 契约全集 - REMOTE_WITHHELD（写面本机工具不进远程）。"""
    from vod_mcp import packs as _packs
    contract = json.loads((common.ROOT / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
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


def _validate_product_or_exit(product: str, base: str) -> bool:
    """D-product-id-2：安装期产品硬校验（B 案，2026-11-05 拍板）。
    --product 命中 meta productCatalog（名字大小写不敏感或 id 精确）才放行；
    未命中/目录不可达一律拒绝安装并给可执行引导（宁可不装不可装错）。"""
    import urllib.request
    import urllib.error
    import uuid
    api_prefix = "/rest/developer/manager/hdvodmngservice/v1"
    key = os.environ.get("VOD_JAVA_API_KEY", "")
    token = ""
    # 全程一致的设备锚点（S1 设备绑定：token 与后续请求必须同 device/UA，
    # 否则 meta 401 设备不匹配；每次装机一个新锚点，一次校验只耗一枚令牌）
    device = uuid.uuid4().hex[:32]
    ua = "vod-devkit-installer/1"

    def _get(url: str):
        auth = key or token
        req = urllib.request.Request(url, headers={
            "content-type": "application/json",
            "X-Vod-Device-Id": device,
            "User-Agent": ua,
            **({"authorization": f"Bearer {auth}"} if auth else {}),
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")

    try:
        if not key:
            req = urllib.request.Request(  # 零字段匿名令牌（方案 C 同链）
                f"{base}{api_prefix}/external/token", data=b"{}",
                headers={"content-type": "application/json", "X-Vod-Device-Id": device,
                         "User-Agent": ua}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace") or "{}")
            token = (body.get("data") or {}).get("token") or body.get("token") or ""
        catalog = None
        status, text = _get(f"{base}{api_prefix}/external/meta")
        data = (json.loads(text) or {}).get("data") or {}
        catalog = data.get("productCatalog")
        if not catalog and token:  # 老引擎 meta 无目录 → 退 /external/products
            status, text = _get(f"{base}{api_prefix}/external/products") if not key else (None, None)
            if text:
                data = (json.loads(text) or {}).get("data") or []
                catalog = data
        if not catalog:
            print("[vod-devkit] 产品校验失败：引擎 meta 无 productCatalog 且 /external/products 不可用。\n"
                  "  不执行安装（宁可不装不可装错）。请核对 --java-api-base 指向的引擎是否已部署 T7i 版本。",
                  file=sys.stderr)
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
                  f"  权威名单：GET {api_prefix}/external/products（共 {len(catalog)} 项），示例：{sample} …",
                  file=sys.stderr)
            sys.exit(2)
        return True
    except SystemExit:
        raise
    except Exception as e:
        print(f"[vod-devkit] 产品校验不可达（{e.__class__.__name__}），拒绝安装（宁可不装不可装错）。\n"
              "  请核对网络与 --java-api-base；确需离线安装请联系 VOD 运营。",
              file=sys.stderr)
        sys.exit(2)
