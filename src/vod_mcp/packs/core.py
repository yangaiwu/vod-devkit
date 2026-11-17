"""core pack：自述、认证自检、版本提醒、产品候选检索（只读，零写盘副作用）。

例外：`auth_ensure` 是唯一有写盘副作用的认证工具（领匿名令牌后落 state），
显式 key 一律不覆盖、远程面不领取（见 D-token-machine-1）。
"""
import os

from vod_mcp import attribution as _attrib
from vod_mcp import net, provenance


def search_products(params: dict) -> dict:
    """产品候选检索（给模型 3-5 个候选去问用户，而不是从名录里瞎猜）。

    名录=引擎 meta 接口的 productCatalog（长度随运营变更，插件不内置）。
    S231：目录为空时懒领一次匿名令牌再取——否则独立部署冷启动（无 token/无缓存）
    恒返回 0 候选，"缺产品先给 3-5 候选问一次"（D-product-ask-1）不成立。
    这是本工具唯一的写盘例外（ensure 落 state），且只在目录为空时触发。
    """
    query = str(params.get("query") or "").strip()
    limit = int(params.get("limit") or 5)
    limit = max(1, min(limit, 20))
    meta = net._load_meta()
    catalog = meta.get("catalog") or []
    if not catalog:
        try:
            auth_ensure({})
        except Exception:          # 领不到令牌不是本工具的错，下面照实报不可用
            pass
        meta = net._load_meta(force=True)
        catalog = meta.get("catalog") or []
    if not catalog:
        # 不静默给空：回执要能让模型改问法（直接问产品名/ID），而不是编候选
        return {"candidates": [], "total": 0, "reason": "catalog_unavailable",
                "hint": "产品名录不可达（引擎或令牌不可用）：直接问用户产品名或 ID，不要编造候选"}
    if not query:
        # S232：空查询要分因。模型把入参写成 keyword/q 时这里静默返回 0 候选，
        # 看起来像"目录里没有这个产品"，实际是参数名不对——回执必须说清楚。
        return {"candidates": [], "total": len(catalog), "reason": "empty_query",
                "hint": "入参名是 query（其它名字会被当成空查询）；本次没有按任何关键词匹配"}
    idx = _attrib.build_alias_index(meta)
    hits = _attrib.match_products(query, idx)
    seen, cands = set(), []
    for h in hits:
        pid = str(h.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        cands.append({"id": pid, "name": h["product"],
                      "score": round(min(1.0, len(h["alias"]) / max(len(query), 1)), 2),
                      "matchReason": f"alias:{h['alias']}"})
    if not cands:                      # 别名没命中：退回名字子串（用户可能打错/只说一半）
        q = query.lower()
        for item in catalog:
            name = str(item.get("name") or "")
            if q and (q in name.lower() or name.lower() in q):
                cands.append({"id": str(item.get("id")), "name": name, "score": 0.5,
                              "matchReason": "name-substring"})
    if not cands:                      # 完全无关联词：给名录前 N 个当"可选项"（问用户用）
        for item in catalog[:limit]:
            cands.append({"id": str(item.get("id")), "name": str(item.get("name") or ""),
                          "score": 0.0, "matchReason": "catalog-default"})
    cands.sort(key=lambda c: (c["score"], len(c["name"])), reverse=True)
    out = {"candidates": cands[:limit], "total": len(catalog)}
    # S204：兜住模型**实际会走的那一步**。实测（0.5.32 + 最新 SKILL）模型连续两轮跳过
    # vod_devkit_info 直接来搜，然后拿 score 0.0 的 catalog-default 追问产品；而它能背出
    # 技能里「第一步永远是看本机绑定」——读得到、不照做。所以把绑定放进它一定会看的回执里。
    binding = provenance.install_binding()
    if binding:
        out["installBinding"] = binding
        # S208：不复制自指词表（真源 attribution.SELF_REFERENCE 有十几个词，这里举三个例子
        # 会被模型当成穷举，行为反而变窄）。只给事实 + 一句处置。
        out["nextStep"] = (f"本机安装绑定={binding}：原话含自指时直接用 installBinding 归因，"
                           f"不要再追问产品；也不要拿 catalog-default 的无分候选去问用户。")
    return out


def devkit_info(params: dict, client_info: dict | None = None) -> dict:
    return provenance.info_payload(client_info)


def _pack_ids(v) -> list:
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return []


def packs_configure(params: dict, client_info: dict | None = None) -> dict:
    """会话内开关能力包（stdio 面；远程面在 REMOTE_WITHHELD 里被摘除）。

    只改进程内状态：不写 env、不写宿主配置（持久化面是 CLI `packs
    enable|disable --apply`，一个概念只留一个写入口）。返回新生效面 + 工具清单，
    由 server 侧推 tools/list_changed。
    """
    from vod_mcp import packs as _packs
    reset = bool(params.get("reset"))
    enable = _pack_ids(params.get("enable") or [])
    disable = _pack_ids(params.get("disable") or [])
    if not reset and not enable and not disable:
        raise net.ToolError("参数为空：给 enable / disable（包 id）或 reset=true", code=-32602)
    current = _packs.effective_packs()
    try:
        if reset:
            new = _packs.set_runtime_packs(None)
        else:
            want = [p for p in current if p not in set(disable)] + enable
            new = _packs.set_runtime_packs(want)
    except _packs.UnknownPack as e:
        raise net.ToolError(str(e), code=-32602) from e
    except _packs.PackRefused as e:
        # 安全门禁拒绝（熔断）：不是参数错，别让模型以为改个拼写就能开
        raise net.ToolError(str(e), code=-32015) from e
    added = [p for p in new if p not in current]
    removed = [p for p in current if p not in new]
    return {
        "packs": list(new),
        "added": added,
        "removed": removed,
        "tools": _packs.enabled_tools(),
        "changed": bool(added or removed),
        "persisted": False,
        "note": ("会话内生效、重启即清；持久化用 CLI："
                 "vod-devkit packs enable|disable <id> --apply"),
    }


def auth_status(params: dict, client_info: dict | None = None) -> dict:
    """认证自检：指纹化输出（明文永不出现），无 key 也跑并给引导。

    远程面（HTTP）缺陷修正：keyCheck 探针旧实现只看本地 net.JAVA_KEY（env/runtime），
    远程面没有本地 key 时 keyCheck 永远 null——远程 agent 永远无法验证自己
    请求头里的 key（真实场景：坏 key 装上、提交才 401）。修法：服务面下探
    net._eff_key()（请求头 Bearer），本地态 javaKey 段照实报"本机未配置"，另加
    requestKey 段报请求头 key 的指纹与探针结果——身份随请求走，两段不混。
    """
    req_key = net._eff_key() if net._SERVER_FACE.get() else None
    out = {
        "javaKey": net._key_state(),
        "packs": sorted(__import__("vod_mcp.packs", fromlist=["effective_packs"]).effective_packs()),
    }
    if req_key:
        out["requestKey"] = {"fingerprint": net._fingerprint(req_key),
                             "note": "服务面：身份来自请求头 Bearer"}
        # 探针显式传请求头 key（net.probe_key 默认取本地 net.JAVA_KEY——服务面必须覆盖）
        out["keyCheck"] = net.probe_key(req_key)
    elif net.JAVA_KEY:
        # 主动探针（devkit auth init 真调 IAM 的廉价版）：用户问"key 好没好"有确定答案
        out["keyCheck"] = net.probe_key()
        if net._explicit_key():
            # 旧版残留凭据检测位（评审拍板项）：显式 key 存活即在位提示自愈路径，
            # 不等提交撞 401 才发现（codex 0.2.3 残留 key 挡匿名链的实锤教训）
            out["legacyKeyHint"] = net._legacy_key_hint()
    if not net.JAVA_KEY and not req_key:
        out["guidance"] = net._KEY_GUIDANCE
        out["tokenReady"] = "首次提交时将自动申请匿名令牌（零字段，日限额低）"
    return out


def check_update(params: dict, client_info: dict | None = None) -> dict:
    from vod_mcp import update_check as uc
    return uc.check(params)


def auth_ensure(params: dict, client_info: dict | None = None) -> dict:
    """判 + 领（D-token-machine-1）：幂等，显式 key 一律不覆盖。

    与 auth_status 的分工：status 只读，ensure 是唯一的"需要时替你领一枚"入口。
    判定表（返回值 source 指明身份从哪来，方便事后审计）：
      · VOD_JAVA_API_KEY 显式存在      → 只探针，source=env，绝不覆盖
      · runtime 有令牌且 verified      → source=runtime，changed=false（不重复领）
      · no-key / expired-anonymous /
        device-mismatch                → 领零字段匿名令牌 → 落 state → 复探
      · rejected（显式 key 被引擎拒）  → **不领**，fail fast（不静默降档）
      · unreachable                    → **不领**，verified=null（网络问题不是身份问题）

    远程面同样是这套语义（D-token-machine-1 定稿：本地/远程同一个效果）：
    请求头 Bearer 优先（调用方自带身份就用它）；没有就由服务端领/复用机器级匿名令牌。
    多租户部署要按调用方隔离时，各调用方带自己的 Bearer；匿名档就是"整机一份"的低信任档。
    """
    from vod_mcp import runtime_state as rt

    req_key = net._eff_key() if net._SERVER_FACE.get() else None
    has_key = bool(req_key) or bool(net._java_key())
    # source 要能回答问题"这身份是哪来的"：运行时显式 key（auth init 写入）、
    # 请求头身份、自动领的匿名令牌不是一回事——被拒后的处置也不同。
    if req_key:
        source = "request"
    elif os.environ.get("VOD_JAVA_API_KEY"):
        source = "env"
    elif has_key and net._explicit_key():
        source = "runtime-key"
    elif has_key:
        source = "runtime-anonymous"
    else:
        source = "none"

    if source in ("runtime-anonymous", "new-anonymous"):
        tier = "anonymous"
    elif source == "none":
        tier = "none"
    else:
        tier = "formal"

    probe = (net.probe_key(req_key) if req_key
             else (net.probe_key() if has_key else
                   {"ok": None, "reason": "no-key", "fingerprint": None}))
    if probe.get("ok") is True:
        return {"tier": tier, "source": source, "verified": True,
                "reason": probe.get("reason"), "fingerprint": probe.get("fingerprint"),
                "changed": False, "base": net._java_base()}

    reason = probe.get("reason")
    # 显式身份被拒：配置错误必须冒出来，静默换匿名 = 归因/额度双错位。
    # 显式=请求头 Bearer / env key / runtime 里的正式 key（tier≠anonymous）。
    if reason == "rejected" and (req_key or os.environ.get("VOD_JAVA_API_KEY")
                                 or net._explicit_key()):
        return {"tier": tier, "source": source, "verified": False, "reason": "rejected",
                "fingerprint": probe.get("fingerprint"), "changed": False,
                "base": net._java_base(),
                "guidance": [{"action": "fix-key", "label": "显式 key 被引擎拒绝：换一把有效 key"
                                                         "（auth init --key … --apply），不要落到匿名档"}]}
    if reason == "unreachable":
        return {"tier": tier, "source": source, "verified": None,
                "reason": "unreachable", "fingerprint": probe.get("fingerprint"),
                "changed": False, "base": net._java_base(),
                "note": "引擎不可达：未领取、未判定——网络问题不等于令牌问题"}

    # 需要领：no-key / expired-anonymous / device-mismatch（以及过期但探针没给原文）
    token = net._fetch_anon_token()
    if not token:
        hint = ("；远程面若绑定非回环地址，代领默认关闭——请带 Authorization: Bearer <key>，"
                "或服务端以 --allow-anon-mint 显式开启" if net.ANON_MINT_DISABLED else "")
        raise net.ToolError(
            "未配置接入 key 且匿名令牌端点不可用。引导："
            + "；".join(str(g["label"]) for g in net._KEY_GUIDANCE) + hint, code=-32012)
    rt._runtime_update({"java_key": token, "token_tier": "anonymous"})
    probe2 = net.probe_key()
    return {"tier": "anonymous", "source": "new-anonymous",
            "verified": probe2.get("ok"), "reason": probe2.get("reason") or reason,
            "fingerprint": probe2.get("fingerprint"), "changed": True,
            "base": net._java_base()}



