"""core pack：自述、认证自检、版本提醒、产品候选检索（只读，零写盘副作用）。"""
from vod_mcp import attribution as _attrib
from vod_mcp import net, provenance


def search_products(params: dict) -> dict:
    """产品候选检索（只读）：给模型 3-5 个候选去问用户，而不是从名录里瞎猜。
    名录=引擎 meta 接口的 productCatalog（长度随运营变更，插件不内置）。"""
    query = str(params.get("query") or "").strip()
    limit = int(params.get("limit") or 5)
    limit = max(1, min(limit, 20))
    meta = net._load_meta()
    catalog = meta.get("catalog") or []
    if not query:
        return {"candidates": [], "total": len(catalog)}
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
    return {"candidates": cands[:limit], "total": len(catalog)}


def devkit_info(params: dict, client_info: dict | None = None) -> dict:
    return provenance.info_payload(client_info)


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
        "packs": sorted(__import__("vod_mcp.packs", fromlist=["enabled_packs"]).enabled_packs()),
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
