"""MCP stdio server（JSON-RPC 2.0，行分隔）。

依赖：Python 3.10+，零第三方依赖（内网友好）。
握手记录 clientInfo（宿主感知）；工具调用前过声明式护栏。
"""
import json
import os
import sys
from pathlib import Path

# 自举包路径（对任意 MCP 宿主成立：不依赖宿主透传 PYTHONPATH——
# Hermes 等宿主出于安全过滤环境变量，stdio 子进程只继承白名单）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vod_mcp import guardrails, packs, tools  # noqa: E402

_PROTOCOL_VERSION = "2025-06-18"
_client_info = {}


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(message: dict, client_info: dict | None = None) -> dict | None:
    """JSON-RPC 分派（两面共用：stdio 逐行调用；HTTP 面每请求调用一次）。

    client_info 由传输层提供（HTTP 面=固定标识 + 认证形态，stdio 面=握手自报）。
    """
    method = message.get("method", "")
    req_id = message.get("id")
    if method == "initialize":
        global _client_info
        _client_info = client_info or (message.get("params") or {}).get("clientInfo") or {}
        return _result(req_id, {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "instructions": (
                "vod-devkit 采集资产与纪律：技能 vod-feedback-collect 处理用户对"
                "本产品的不满/建议/期望（触发词：慢/报错/体验差/希望支持/提单等）。"
                "提交前必须征得用户明确同意（用户抱怨本身不构成同意）；提交回执"
                "echo.contents 必须逐条原样转述给用户（「已收录原话：<content>」），"
                "禁止改写、概括、增删字词。product 归因由安装绑定完成，禁止询问用户。"
            ),
            "serverInfo": {
                "name": "vod-devkit",
                "version": tools.load_contract()["version"],
            },
        })
    if method == "notifications/initialized":
        return None  # 通知无响应
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": tools.tool_specs(packs.enabled_tools())})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        verdict, msg, code = guardrails.check(name, args)
        if verdict != "allow":
            return _error(req_id, code, msg)
        try:
            out = tools.dispatch(name, args, _client_info)
            return _result(req_id, {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                "structuredContent": out,
                "isError": False,
            })
        except tools.ToolError as e:
            return _error(req_id, e.code, str(e))
    if req_id is not None:
        return _error(req_id, -32601, f"未知方法: {method}")
    return None


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="vod-mcp-server",
                                 description="vod-devkit MCP server（默认 stdio）")
    ap.add_argument("--transport", choices=["stdio", "remote"], default="stdio",
                    help="stdio（默认，宿主拉起子进程）；remote（Streamable HTTP，"
                         "一个进程服务多个 agent）")
    ap.add_argument("--port", type=int, default=9528, help="remote 端口（默认 9528）")
    ap.add_argument("--host", default="127.0.0.1", help="remote 绑定地址（默认回环）")
    args, _unknown = ap.parse_known_args()

    # 启动自诊（排障：写 /tmp，宿主过滤环境变量时可观察实际 env）
    try:
        tools._ensure_first_boot()  # D-key-guard-3①：首启标记+构建机残留清理（preset 兜底）
    except Exception:
        pass
    tools._log(f"started pid={os.getpid()} argv={sys.argv} "
               f"VOD_PACKS={os.environ.get('VOD_PACKS')!r} "
               f"distribution={tools._distribution()} "
               f"cwd={os.getcwd()}")
    if args.transport == "remote":
        try:
            from vod_mcp import transport_remote
        except ImportError as e:  # 零依赖红线：远程面才需要 SDK
            print("[vod-devkit] 远程面需要官方 MCP SDK：\n"
                  "  pip install 'vod-devkit[remote]'   # 或 pip install 'mcp>=1.0'\n"
                  f"（stdio 形态不需要任何第三方依赖；导入失败：{e}）", file=sys.stderr)
            sys.exit(2)
        sys.exit(transport_remote.serve(args.host, args.port))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            resp = _error(None, -32700, "解析错误")
        else:
            resp = handle(message)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
