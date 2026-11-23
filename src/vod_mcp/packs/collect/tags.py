"""分类白名单（problem_type 校验与过滤）。（ARCH-CALL-04：从 packs/collect.py 拆出）。"""
from vod_mcp import net
from vod_mcp import runtime_state as rt


def _allowed_tags(product_id=None) -> set:
    """分类白名单（引擎 meta.problemTypes，单一真源）。

    2026-11-12 引擎契约变更：problemTypes 不再随无参 meta 下发（那是"全部分类"
    的假全集），改为 `GET /external/meta?productId=<id>` 按产品下发——真源是
    t_vod_problem_category 按 product_id 分组，不同产品的分类集不同。

    取不到（无 product_id / 老引擎 / 快照降级 / 该产品无分类）→ 空集=不知道
    白名单 → 不过滤：宁可放行也不误杀采集。
    """
    pid = str(product_id or "").strip()
    if not pid or not pid.isdigit():
        return set()
    import time
    cache = rt._RT.get("ptype_cache") or {}
    now = time.time()
    if now - float(cache.get("at") or 0) < net._META_TTL and pid in (cache.get("by") or {}):
        return set(cache["by"][pid] or [])
    by = dict(cache.get("by") or {})
    try:
        path = f"{net._META_PATH}?productId={pid}"
        out = net._http("GET", path, None, base=net.JAVA_BASE, key=net._eff_key(), timeout=10)
        data = out.get("data") or {}
        types = [str(t) for t in (data.get("problemTypes") or []) if str(t).strip()]
        by[pid] = types
        cache = {"at": int(now), "by": by}
        rt._runtime_update({"ptype_cache": cache})
        return set(types)
    except Exception:
        # 任何取不到（网络/超时/引擎异常）= 不知道值域 → 不过滤，绝不阻断提交
        return set(by.get(pid) or [])


_PROBLEM_TYPE_PREFIX = "problem_type:"


def _filter_tags(tags, allowed: set) -> tuple:
    """tags 白名单过滤 → (kept, dropped)。

    引擎约定（ExternalVoicesServiceImpl.extractProblemType）：分类标注写
    `problem_type:<值>`，值域=meta.problemTypes（六类）。其它语义的 tag 不参与
    分类校验、原样保留；只有 problem_type 的值会被白名单过滤——脏值丢弃不拒收
    声音（对标 vod-skill 的 check_classification：分类必须存在于知识库）。
    """
    kept, dropped = [], []
    for t in tags or []:
        s = str(t).strip()
        if not s:
            continue
        if allowed and s.startswith(_PROBLEM_TYPE_PREFIX):
            val = s[len(_PROBLEM_TYPE_PREFIX):].strip()
            if val not in allowed:
                dropped.append(s)
                continue
            s = _PROBLEM_TYPE_PREFIX + val  # 归一（去多余空白）
        if s not in kept:
            kept.append(s)
    return kept, dropped
