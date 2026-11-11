"""工具调用前置护栏（唯一实现，stdio 与 HTTP 两面共用）。

两条面（stdio 的 handle、SDK 的 on_call_tool）必须走同一判定，否则远程面就是
护栏缺口——新增一个传输方式不等于新增一套策略。
"""
import json

from vod_mcp import policy as policy_mod


def check(name: str, args: dict) -> tuple:
    """返回 (verdict, message, code)；verdict ∈ allow/confirm/deny，code 为
    MCP 约定的错误码（deny=-32010，confirm=-32011），allow 时 code=None。"""
    pol = policy_mod.load_policy()
    verdict, msg = policy_mod.decide(
        policy_mod.check_tool_call(pol, name, args) if name else [])
    if verdict == "deny":
        return "deny", f"[guard:deny] {msg}", -32010
    if verdict == "confirm":
        return "confirm", f"[guard:confirm] {msg}", -32011
    text_hits = policy_mod.check_text(
        pol, json.dumps(policy_mod.guard_scope(args), ensure_ascii=False))
    if text_hits:
        return "deny", f"[guard:deny] {policy_mod.decide(text_hits)[1]}", -32010
    return "allow", "", None