"""声明式护栏：safety/policy.json 规则执行（deny/confirm）。

规则匹配分两类：
- 工具参数规则（match.tool 指定）：在 tools/call 前置检查
- 文本规则（match.field=text）：供 hook 层与工具参数串一起检查
"""
import json
import re
from pathlib import Path

_POLICY_PATH = Path(__file__).resolve().parent.parent / "safety" / "policy.json"


def load_policy() -> dict:
    with open(_POLICY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_ref(policy: dict, value):
    """match 里 'maxVoicesPerTask' 这类引用政策顶层的值。"""
    if isinstance(value, str) and value in policy:
        return policy[value]
    return value


def _match_tool_rule(rule: dict, tool: str, params: dict) -> bool:
    m = rule["match"]
    if m.get("tool") != tool:
        return False
    p = m.get("param")
    if p is None:
        return True
    actual = params.get(p)
    if actual is None and "equals" in m and m["equals"] is False:
        actual = False  # 缺省视为未确认
    if "equals" in m:
        return actual == m["equals"]
    if "gt" in m:
        limit = _resolve_ref(load_policy(), m["gt"])
        try:
            if isinstance(actual, list):
                return len(actual) > int(limit)
            return actual is not None and int(actual) > int(limit)
        except (TypeError, ValueError):
            return False
    if "notIn" in m:
        whitelist = _resolve_ref(load_policy(), m["notIn"])
        if not isinstance(whitelist, (list, tuple)):
            return False
        return actual not in whitelist
    return False


def check_tool_call(policy: dict, tool: str, params: dict) -> list:
    """返回命中的规则列表（空=放行）。deny 命中=拒绝；confirm 命中=要求确认。"""
    hits = []
    for rule in policy.get("rules", []):
        if "tool" in rule.get("match", {}):
            if _match_tool_rule(rule, tool, params):
                hits.append(rule)
    return hits


def guard_scope(params: dict) -> dict:
    """文本规则的扫描面（E4 修复）：剔除用户内容字段——拦"凭据读取意图"
    不误杀"反馈内容里引用凭据"。voices[].content 与 data 是用户原话，
    不进文本规则；scene/tags/query/product 等结构性字段仍扫描。"""
    scope = {}
    for k, v in (params or {}).items():
        if k in ("data",):           # run_analysis 的声音数据=用户原话
            scope[k] = "<%d records>" % len(v) if isinstance(v, list) else "..."
        elif k == "voices":          # 采集的反馈内容=用户原话，仅扫非 content 字段
            scope[k] = [{kk: vv for kk, vv in (item or {}).items() if kk != "content"}
                        for item in v] if isinstance(v, list) else v
        else:
            scope[k] = v
    return scope


def check_text(policy: dict, text: str) -> list:
    """文本类 deny 规则（DB 直连/凭据模式），供 hook 与参数串调用。"""
    hits = []
    for rule in policy.get("rules", []):
        m = rule.get("match", {})
        if m.get("field") == "text":
            if re.search(m["regex"], text or ""):
                hits.append(rule)
    return hits


def decide(hits: list) -> tuple:
    """(verdict, message)；verdict ∈ {allow, confirm, deny}。"""
    if not hits:
        return "allow", ""
    denies = [r for r in hits if r["severity"] == "deny"]
    if denies:
        return "deny", denies[0]["message"]
    return "confirm", hits[0]["message"]
