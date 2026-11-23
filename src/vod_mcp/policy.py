"""声明式护栏：safety/policy.json 规则执行（deny/confirm）。

规则匹配分两类：
- 工具参数规则（match.tool 指定）：在 tools/call 前置检查
- 文本规则（match.field=text）：供 hook 层与工具参数串一起检查
"""
import json
import os
import re

from vod_mcp import paths

_POLICY_PATH = paths.POLICY

# 装载失败/规则非法时的占位策略：rules 为空 + broken 记录原因。
# 语义是 **fail-closed**（guardrails 见到 broken 一律 deny），不是 fail-open。
_BROKEN_POLICY = {"rules": [], "broken": None, "brokenRule": None}

_SEVERITIES = ("deny", "confirm")

# ARCH-ERR-02：装载缓存。指纹用 (路径, mtime_ns, size) 而非 TTL——
# TTL 会让"改完规则要等 N 秒才生效"变成新的排障陷阱；文件指纹则改完立刻生效。
# 命中缓存时连 open() 都不发生，热路径（每次 tools/call 都过护栏）不再重复读盘。
_CACHE = {"sig": None, "policy": None, "regex": {}}


def _stat_sig(path) -> tuple:
    st = os.stat(path)
    return (str(path), st.st_mtime_ns, st.st_size)


def _regex_for(rule_id: str):
    """取装载期已编译的规则正则（未编译说明规则没走校验，返回 None）。"""
    return _CACHE["regex"].get(rule_id)


def _read_policy_cached():
    """带指纹缓存的读盘：返回 (policy, None) 或 (None, 异常)。

    缓存命中 = 同一次 mtime/size 下不再 open()（验收断言：一次调用序列内 open 只 1 次）。
    读失败（OSError/JSONDecodeError）**不缓存**：坏文件通常是人手在修，隔一次重读才是对的。
    """
    sig = _stat_sig(_POLICY_PATH)          # 文件不存在 → OSError，交给调用方按 fail-closed 处理
    if _CACHE["sig"] == sig and _CACHE["policy"] is not None:
        return _CACHE["policy"], None
    with open(_POLICY_PATH, encoding="utf-8") as f:
        pol = json.load(f)
    # 读后再取一次指纹：读期间被改的话，用后一次指纹缓存（宁可多读一次，不缓存错位内容）
    _CACHE["sig"] = _stat_sig(_POLICY_PATH)
    _CACHE["policy"] = pol
    return pol, None


def load_policy() -> dict:
    """严格装载（规则文件坏了就抛）——给"我要确认 policy 是好的"的调用方用。

    工具调用路径不要用它：那会把一个可修复的配置问题升级成进程级不可用。
    改用 `try_load_policy()`（fail-closed）。
    """
    pol, _ = _read_policy_cached()
    bad = _validate(pol)
    if bad:
        raise ValueError(f"policy 规则非法（{bad[0]}）：{bad[1]}")
    return pol


def _validate(policy: dict) -> tuple | None:
    """结构校验：返回 (rule_id, 原因) 或 None。

    键集合必须与消费点一一对应，否则"校验过了代码照样 KeyError"：
    `:28 rule["match"]` / `:87 m["regex"]` / `:96 r["severity"]` / `:98/99 message`。
    """
    compiled = {}
    rules = policy.get("rules")
    if not isinstance(rules, list):
        return ("<policy>", "rules 必须是数组")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            return (f"rules[{i}]", "规则必须是对象")
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid:
            return (f"rules[{i}]", "缺 id（报错与 explain 要靠它定位）")
        if rule.get("severity") not in _SEVERITIES:
            return (rid, f"severity 必须是 {'/'.join(_SEVERITIES)}，实际 {rule.get('severity')!r}")
        if not isinstance(rule.get("message"), str):
            return (rid, "缺 message（deny 时要展示给用户）")
        m = rule.get("match")
        if not isinstance(m, dict):
            return (rid, "缺 match 对象")
        if "field" in m:
            if m["field"] != "text":
                return (rid, f"未知 field {m['field']!r}（目前只支持 text）")
            regex = m.get("regex")
            if not isinstance(regex, str) or not regex:
                return (rid, "field=text 必须给 regex")
            try:
                compiled[rid] = re.compile(regex)     # 装载期编译一次，消费点不再重复编译
            except re.error as e:
                return (rid, f"regex 编译失败：{e}")
        elif "tool" in m:
            if "equals" not in m and "gt" not in m and "notIn" not in m:
                return (rid, "match.tool 必须给 equals/gt/notIn 之一（否则规则恒真）")
        else:
            return (rid, "match 必须含 tool 或 field")
    _CACHE["regex"] = compiled
    return None


def try_load_policy() -> dict:
    """容错装载：**永不抛**，失败时返回带 `broken` 原因的占位策略。

    调用方（guardrails）见到 `broken` 非空必须 deny —— 护栏坏了等于没有护栏，
    "放行"是最差的处理（会把本该拦的写操作放出去）。
    """
    try:
        pol, _ = _read_policy_cached()
    except (OSError, json.JSONDecodeError) as e:
        return {**_BROKEN_POLICY, "broken": f"{type(e).__name__}: {e}（{_POLICY_PATH}）"}
    bad = _validate(pol)
    if bad:
        return {**_BROKEN_POLICY, "broken": f"规则 {bad[0]} 非法：{bad[1]}", "brokenRule": bad[0]}
    return pol


def _resolve_ref(policy: dict, value):
    """match 里 'maxVoicesPerTask' 这类引用政策顶层的值。"""
    if isinstance(value, str) and value in policy:
        return policy[value]
    return value


def _match_tool_rule(policy: dict, rule: dict, tool: str, params: dict) -> bool:
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
        limit = _resolve_ref(policy, m["gt"])
        try:
            if isinstance(actual, list):
                return len(actual) > int(limit)
            return actual is not None and int(actual) > int(limit)
        except (TypeError, ValueError):
            return False
    if "notIn" in m:
        whitelist = _resolve_ref(policy, m["notIn"])
        if not isinstance(whitelist, (list, tuple)):
            return False
        return actual not in whitelist
    return False


def check_tool_call(policy: dict, tool: str, params: dict) -> list:
    """返回命中的规则列表（空=放行）。deny 命中=拒绝；confirm 命中=要求确认。"""
    hits = []
    for rule in policy.get("rules", []):
        if "tool" in rule.get("match", {}):
            if _match_tool_rule(policy, rule, tool, params):
                hits.append(rule)
    return hits


# ARCH-CFG-07：用户自由文本字段**显式白名单**（此前是"新字段记得加"的反向黑名单）。
# 这些键下的内容不进文本规则扫描——否则"反馈内容里引用了凭据"会被误判成凭据读取意图。
# 新增任何"装用户原话"的字段，必须同时：① 加进这里 ② tests/test_tags_whitelist.py 的
# test_free_text_fields_are_explicit 会强制它出现在本表里（漏加即红）。
USER_TEXT_KEYS = ("content", "reproSteps", "expectedBehavior", "originalLines", "echo", "summary")
# 整块用户数据（run_analysis 的声音数据集）：只报条数，不扫内容
USER_BLOB_KEYS = ("data",)


def guard_scope(params: dict) -> dict:
    """文本规则的扫描面（E4 修复 / ARCH-CFG-07 白名单化）。

    递归剥离用户自由文本：`voices[].content`、`reproSteps`、`expectedBehavior`、
    `originalLines`、`echo`、`summary` 与 `data` 不计入扫描；结构性字段（tool 名、
    product、scene、tags、query…）照常扫描——护栏管的**意图**，不是用户的原话内容。
    """
    def _strip(value):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k in USER_TEXT_KEYS:
                    continue                     # 用户原话字段：不参与扫描（也不落进 scope）
                if k in USER_BLOB_KEYS:
                    out[k] = "<%d records>" % len(v) if isinstance(v, list) else "..."
                else:
                    out[k] = _strip(v)
            return out
        if isinstance(value, list):
            return [_strip(item) for item in value]
        return value

    stripped = _strip(params or {})
    return stripped if isinstance(stripped, dict) else {}


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
