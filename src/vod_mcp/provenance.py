"""溯源与宿主身份：build-info.json（构建烧录）+ 握手 clientInfo + install-manifest。"""
import json

from vod_mcp import paths
from vod_mcp import trace as _trace

def _build_info_path():
    """路径每次现读（ARCH-DEP-06）：import 期冻结会在"重装换根"后继续指向旧根。"""
    return paths.ROOT / "build-info.json"


def _manifest_path():
    return paths.ROOT / "install-manifest.json"


def read_build_info() -> dict:
    p = _build_info_path()
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"version": "dev", "commitSha": None, "builtAt": None, "sourceRemote": None}


def read_manifest() -> dict:
    p = _manifest_path()
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def host_identity() -> dict:
    """安装清单的 target + 握手 clientInfo（由 server.py 注入 _HOST）。"""
    return read_manifest().get("target") or {}


def install_binding() -> str | None:
    """本机安装期绑定的产品（S196）：让「自指命中就别问产品」这句话**可执行**。

    优先 runtime state 的 `product`（安装器写进去的绑定，与归因链第 4 级同源）；
    回落 manifest 里唯一的产品绑定；多产品并存（多宿主装了不同产品）时不挑一个——
    错归会污染引擎幂等域，那种情况宁可让模型继续按「先问一次」处理。
    """
    try:
        from vod_mcp import runtime_state as _rt
        val = str(_rt._RT.get("product") or "").strip()
        if val:
            return val
    except Exception as e:           # noqa: BLE001 — 读不到不阻断，回落 manifest
        _trace.suppress("provenance.install_binding", e)
    prods = {str(r.get("product")).strip() for r in (read_manifest().get("installs") or [])
             if r.get("product")}
    return next(iter(prods)) if len(prods) == 1 else None


def info_payload(client_info: dict | None = None) -> dict:
    bi = read_build_info()
    mf = read_manifest()
    host = client_info or mf.get("clientInfo") or {}
    return {
        "version": bi.get("version"),
        "commitSha": bi.get("commitSha"),
        "packs": sorted(__import__("vod_mcp.packs", fromlist=["effective_packs"]).effective_packs()),
        "hostClient": host,
        "manifestSummary": {
            "target": mf.get("target"),
            "installedAt": mf.get("installedAt"),
            "source": mf.get("source"),
            # S196：安装绑定产品（模型据此执行「自指命中不再追问」；空=多绑定/未绑定）
            "product": install_binding(),
        },
    }
