"""MCP stdio server（JSON-RPC 2.0，行分隔）。

依赖：Python 3.10+，零第三方依赖（内网友好）。
握手记录 clientInfo（宿主感知）；工具调用前过声明式护栏。
"""
import json
import os
import sys
from pathlib import Path

# 自举包路径（对任意 MCP 宿主成立：不依赖宿主透传 PYTHONPATH——
# Hermes 等宿主出于安全过滤环境变量，stdio 子进程只继承白名单）。
# 这里是全仓唯一保留物理相对深度的位置：本文件会被当脚本直跑
# （python vod_mcp/server.py），此时包还不可导入，无法先 import paths。
# 其余所有资源路径一律走 vod_mcp/paths.py（含 VOD_DEVKIT_ROOT 覆盖）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 解释器版本 guard 必须在 import vod_mcp 之前：本模块与下游（tools/guardrails）
# 的注解用了 PEP 604（`dict | None`），在 3.9 上会在 def 求值时抛 TypeError
# traceback——那是"响失败"但不可读。一行 guard 把残余风险变成可读诊断。
if sys.version_info < (3, 10):
    sys.stderr.write(
        "[vod-devkit] MCP server 需要 Python >= 3.10（当前 %d.%d）。\n"
        "  插件 .mcp.json 的 command 若走 PATH 上的 python3，请指向 3.10+ 解释器"
        "（如 /usr/bin/python3.12），\n"
        "  或重跑安装器由它用本机 3.10+ 解释器重写该文件。\n"
        % sys.version_info[:2])
    sys.exit(2)

from vod_mcp import guardrails, packs, runtime_state, skills_registry, tools  # noqa: E402

_PROTOCOL_VERSION = "2025-06-18"
_client_info = {}


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(message: dict, client_info: dict | None = None) -> dict | list | None:
    """JSON-RPC 分派（两面共用：stdio 逐行调用；HTTP 面每请求调用一次）。

    client_info 由传输层提供（HTTP 面=固定标识 + 认证形态，stdio 面=握手自报）。
    返回 list 时=一条响应后跟通知（当前只有 tools/list_changed 这一处）。
    """
    method = message.get("method", "")
    req_id = message.get("id")
    if method == "initialize":
        global _client_info
        _client_info = client_info or (message.get("params") or {}).get("clientInfo") or {}
        return _result(req_id, {
            "protocolVersion": _PROTOCOL_VERSION,
            # listChanged：会话内开关（vod_packs_configure）改工具面后由服务端推
            # notifications/tools/list_changed；不声明的话合规客户端不会重拉 tools/list。
            "capabilities": {"tools": {"listChanged": True}},
            "instructions": (
                "vod-devkit 采集资产与纪律：技能 vod-feedback-collect 处理用户对"
                "本产品的不满/建议/期望（触发词：慢/报错/体验差/希望支持/提单等）。"
                "提交前必须征得用户明确同意（用户抱怨本身不构成同意）；提交回执"
                "echo.contents 必须逐条原样转述给用户（「已收录原话：<content>」），"
                "禁止改写、概括、增删字词。product 归因：原话唯一命中可直接用；"
                "未命中或多产品歧义时必须问用户一次\"这条是哪个产品的反馈\"，"
                "回答填 product；用户说不知道就告知他缺产品不能提交，不要猜。不许不填直接提交。"
                # 技能读取教法（对齐 devkit 的"动作优先"）：树路径在 initialize 就给，
                # 让 agent 不必先调目录工具；先直读、被拒再回落、不反复请求。
                " 技能树：" + str(skills_registry.SKILLS_ROOT)
                + "（本机路径）。读法=动作优先：先直接读 "
                  "skillRoot/<技能名>/SKILL.md（尝试本身即可达性检查，不做预判）；"
                  "被拒或读取失败才用 vod_retrieve_skill 取全文（无需文件权限），"
                  "绝不反复请求。"
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
            resp = _result(req_id, {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                "structuredContent": out,
                "isError": False,
            })
            # 会话内开关改了工具面 → 按 MCP 规范推通知（stdio 面只有这一处增量输出；
            # 远程面每请求现造 server 无会话，该工具已在 REMOTE_WITHHELD 里摘除）
            if name == "vod_packs_configure" and isinstance(out, dict) and out.get("changed"):
                return [resp, {"jsonrpc": "2.0",
                               "method": "notifications/tools/list_changed"}]
            return resp
        except tools.ToolError as e:
            return _error(req_id, e.code, str(e))
    if req_id is not None:
        return _error(req_id, -32601, f"未知方法: {method}")
    return None


def _consume_payload_marker() -> None:
    """载荷标记：install 换完载荷写它=该重启；被真正跑起来的进程消费掉。"""
    try:
        from vod_mcp import payload as _payload
        _payload.consume_marker()
    except Exception:
        pass


def main():
    # 入口显式设根（宿主直接按脚本路径拉起时，这里就是"入口"）
    from vod_mcp import paths as _paths
    os.environ.setdefault("VOD_DEVKIT_SRC_ROOT", str(_paths.SRC_ROOT))
    os.environ.setdefault("VOD_DEVKIT_DIST_ROOT", str(_paths.DIST_ROOT))
    _consume_payload_marker()
    import argparse
    ap = argparse.ArgumentParser(prog="vod-mcp-server",
                                 description="vod-devkit MCP server（默认 stdio）")
    ap.add_argument("--transport", choices=["stdio", "remote"], default="stdio",
                    help="stdio（默认，宿主拉起子进程）；remote（Streamable HTTP，"
                         "一个进程服务多个 agent）")
    ap.add_argument("--port", type=int, default=9528, help="remote 端口（默认 9528）")
    ap.add_argument("--host", default="127.0.0.1", help="remote 绑定地址（默认回环）")
    ap.add_argument("--allow-anon-mint", action="store_true",
                    help="非回环绑定时仍允许服务端代领匿名令牌（默认关闭；"
                         "单机可信网络才开，见 D-token-machine-1）")
    args, _unknown = ap.parse_known_args()

    # VOD_PACKS 未知 id 启动即报错（D-packs-config-1，对齐 devkit 口径）：
    # 静默过滤会让"配了"和"生效"分叉，排障时没人能看出是拼写错还是没装。
    try:
        packs.enabled_packs()
    except packs.UnknownPack as e:
        print(f"[vod-devkit] {e}", file=sys.stderr)
        sys.exit(2)

    # 启动自诊（排障：写 /tmp，宿主过滤环境变量时可观察实际 env）
    try:
        runtime_state._ensure_first_boot()  # D-key-guard-3①：首启标记+构建机残留清理（preset 兜底）
    except Exception:
        pass
    runtime_state._log(f"started pid={os.getpid()} argv={sys.argv} "
                       f"VOD_PACKS={os.environ.get('VOD_PACKS')!r} "
                       f"distribution={runtime_state._distribution()} "
                       f"cwd={os.getcwd()}")
    if args.transport == "remote":
        try:
            from vod_mcp import transport_remote
        except ImportError as e:  # 零依赖红线：远程面才需要 SDK
            print("[vod-devkit] 远程面需要官方 MCP SDK：\n"
                  "  pip install 'vod-devkit[remote]'   # 或 pip install 'mcp>=1.0'\n"
                  f"（stdio 形态不需要任何第三方依赖；导入失败：{e}）", file=sys.stderr)
            sys.exit(2)
        sys.exit(transport_remote.serve(args.host, args.port, args.allow_anon_mint))

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            resp = _error(None, -32700, "解析错误")
        else:
            try:
                resp = handle(message)
            except Exception as e:     # noqa: BLE001  ARCH-ERR-01：任何未捕获异常都不许打死进程
                # 不含 Exception 之外的 KeyboardInterrupt/SystemExit（那两个必须照常退出）
                runtime_state._log(f"handle uncaught: {type(e).__name__}: {e}")
                print(f"[vod-devkit] error: {type(e).__name__}: {e}", file=sys.stderr)
                resp = _error(message.get("id") if isinstance(message, dict) else None,
                              -32603, "内部错误（已记录日志）")
        out_msgs = resp if isinstance(resp, list) else ([resp] if resp is not None else [])
        for m in out_msgs:
            sys.stdout.write(json.dumps(m, ensure_ascii=False) + "\n")
        if out_msgs:
            sys.stdout.flush()


if __name__ == "__main__":
    main()
