"""宿主适配公共件：MCP server 入口与环境（四宿主共用）。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def server_entry() -> str:
    return str(ROOT / "vod_mcp" / "server.py")


def server_env(args, packs: str) -> dict:
    # 无 key 不写空串（空串会让探针/严格解析器误当字面值；运行时空=未设置，
    # 自动兜底 runtime.json java_key 或首提申请匿名令牌）
    env = {"VOD_PACKS": packs,
           "VOD_JAVA_API_BASE": args.java_api_base}
    key = os.environ.get("VOD_JAVA_API_KEY", "")
    if key:
        env["VOD_JAVA_API_KEY"] = key
    return env
