"""溯源与宿主身份：build-info.json（构建烧录）+ 握手 clientInfo + install-manifest。"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BUILD_INFO = _ROOT / "build-info.json"
_MANIFEST = _ROOT / "install-manifest.json"


def read_build_info() -> dict:
    if _BUILD_INFO.exists():
        with open(_BUILD_INFO, encoding="utf-8") as f:
            return json.load(f)
    return {"version": "dev", "commitSha": None, "builtAt": None, "sourceRemote": None}


def read_manifest() -> dict:
    if _MANIFEST.exists():
        with open(_MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return {}


def host_identity() -> dict:
    """安装清单的 target + 握手 clientInfo（由 server.py 注入 _HOST）。"""
    return read_manifest().get("target") or {}


def info_payload(client_info: dict | None = None) -> dict:
    bi = read_build_info()
    mf = read_manifest()
    host = client_info or mf.get("clientInfo") or {}
    return {
        "version": bi.get("version"),
        "commitSha": bi.get("commitSha"),
        "packs": sorted(__import__("vod_mcp.packs", fromlist=["enabled_packs"]).enabled_packs()),
        "hostClient": host,
        "manifestSummary": {
            "target": mf.get("target"),
            "installedAt": mf.get("installedAt"),
            "source": mf.get("source"),
        },
    }
