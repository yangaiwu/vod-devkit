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

# 护栏侧两类 deny 的专用码（2026-11-19，fix-list 问题 3）。
#
# 判据是**处置动作不同 ⇒ 码不同**，而不是"不同规则名 ⇒ 码不同"：
#   -32010 = 去问产品（语义 owner 在 collect.py 的归因链路，护栏侧不许产出）
#   -32023 = 删除敏感信息后重提（凭据/凭据读取意图命中，category=exfil）
#   -32024 = 这不是你能调的 / 收敛到允许范围内（越权、超范围，category=write 且 deny）
#   -32011 = 用户确认后重提（同意闸，confirm）
#   -32017 = 修 policy.json 后重启（规则不可载入，fail-closed）
#
# ⚠️ 码位取用纪律：-32021/-32022 已由 architecture-remediation.md:294 预留给上游 429/5xx
# 映射，且 decisions.md 写明"-32020..22 一旦对外发布就不能复用"——不得占用。故新开 -32023/-32024。
CODE_EXFIL = -32023
CODE_SCOPE = -32024

# 命中规则 → 护栏码的映射。按规则的 category 分派（规则自带 category 字段，
# check_tool_call / check_text 返回的就是原始规则字典，不需要新增数据结构）。
_CATEGORY_CODES = {
    "exfil": CODE_EXFIL,   # 凭据/数据库直连等"读取意图"类：删除敏感信息后重提
    "write": CODE_SCOPE,   # 写操作越界：收敛范围后再提
}


def _code_for_hits(hits: list) -> int:
    """按命中规则的 category 定码；未登记的 category 退回 -32024（越权兜底）。

    为什么不退回 -32010：那是"缺产品"，护栏侧给这个码会把用户指向错误方向——
    正是这条缺陷本身。宁可粗一档，也不谎报原因。
    """
    for rule in hits:
        cat = (rule or {}).get("category")
        code = _CATEGORY_CODES.get(cat) if isinstance(cat, str) else None
        if code is not None:
            return code
    return CODE_SCOPE


def _policy_broken(pol: dict) -> tuple:
    return ("deny",
            f"[guard:deny] 护栏规则不可载入（{pol['broken']}）——"
            "已拒绝本次执行，修复 policy.json（或重跑 install 恢复随包规则）后重启宿主",
            CODE_POLICY_BROKEN)


def check(name: str, args: dict) -> tuple:
    """返回 (verdict, message, code)；verdict ∈ allow/confirm/deny。

    码不是固定的：deny 按**命中规则的 category** 分派（-32023 凭据 / -32024 越权），
    confirm=-32011，policy 坏=-32017，allow 时 code=None。
    **护栏侧永不返回 -32010**——那是「缺产品」的专用码（owner 在 collect 归因链路），
    混用会把「凭据泄露/越权」误报成「请补产品」，把排查引向错误方向。
    """
    pol = policy_mod.try_load_policy()
    if pol.get("broken"):
        return _policy_broken(pol)
    hits = policy_mod.check_tool_call(pol, name, args) if name else []
    verdict, msg = policy_mod.decide(hits)
    if verdict == "deny":
        return "deny", f"[guard:deny] {msg}", _code_for_hits(hits)
    if verdict == "confirm":
        return "confirm", f"[guard:confirm] {msg}", -32011
    text_hits = policy_mod.check_text(
        pol, json.dumps(policy_mod.guard_scope(args), ensure_ascii=False))
    if text_hits:
        return ("deny", f"[guard:deny] {policy_mod.decide(text_hits)[1]}",
                _code_for_hits(text_hits))
    return "allow", "", None