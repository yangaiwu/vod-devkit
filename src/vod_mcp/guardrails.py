"""工具调用前置护栏（唯一实现，stdio 与 HTTP 两面共用）。

两条面（stdio 的 handle、SDK 的 on_call_tool）必须走同一判定，否则远程面就是
护栏缺口——新增一个传输方式不等于新增一套策略。

装载纪律（ARCH-ERR-01，2026-11-19 走查）：**policy 坏了要 deny，不是要崩**。
护栏本应是"拒绝执行"，退化成"整体不可用"（进程被打死）就违背了它自己的定位。
"""
import json

from vod_mcp import policy as policy_mod

# policy 不可载入时的专用码。与 -32010（缺产品）分开，是因为处置动作不同：
# -32010 = 去问产品；-32017 = 去修 policy.json 后重启。混用一个码会把排障引向错误方向。
# ⚠️ 为什么是新码而不是复用 -32013：-32013 是**已废除的归因拦截码**
# （D-attrib-binding-1，见 decisions.md:87、design.md:140、safety-model.md:33、
# proposal.md:135/168 四处记载）。它"零 raise 点"不是空位，是策略被推翻后的结果；
# 在它上面叠加"policy 不可载入"会让同一码位有两种互不相关的说法。
CODE_POLICY_BROKEN = -32017


def _policy_broken(pol: dict) -> tuple:
    return ("deny",
            f"[guard:deny] 护栏规则不可载入（{pol['broken']}）——"
            "已拒绝本次执行，修复 policy.json（或重跑 install 恢复随包规则）后重启宿主",
            CODE_POLICY_BROKEN)


def check(name: str, args: dict) -> tuple:
    """返回 (verdict, message, code)；verdict ∈ allow/confirm/deny，code 为
    MCP 约定的错误码（deny=-32010，confirm=-32011，policy 坏=-32017），allow 时 code=None。"""
    pol = policy_mod.try_load_policy()
    if pol.get("broken"):
        return _policy_broken(pol)
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