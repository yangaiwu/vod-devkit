"""归因与追问（产品定位、缺产品拒绝、回执/账本附加字段）。（ARCH-CALL-04：从 packs/collect.py 拆出）。"""
import os
from vod_mcp import attribution as _attrib
from vod_mcp import errors
from vod_mcp import net
from vod_mcp import runtime_state as rt
from vod_mcp.packs import core


_FOLLOWUP_DECLINES = frozenset({
    "没有", "无", "没有。", "没了", "跳过", "不方便", "不用了", "不用",
    "不补充", "算了", "没有了", "没有了。", "不方便说", "no", "none", "skip", "n/a",
})


def _followup_fields(voice: dict) -> dict:
    """D-followup-impl-2 单源提取（submit 主路径与 draft 暂存共用，禁双边漂移）：
    仅 trim 非空且非拒答词才含键；引擎同口径截 2000；内容永不回流 content。
    followupStatus（评审八点 #3 引擎侧承载的插件上报）：三态白名单归一
    （strip+lower），白名单外/缺失省键——引擎侧降 NULL 不拒收，插件侧同口径双保险。"""
    out = {}
    for _f in ("reproSteps", "expectedBehavior"):
        _val = str(voice.get(_f) or "").strip()
        if _val and _val.lower() not in _FOLLOWUP_DECLINES:
            out[_f] = _val[:2000]
    _st = str(voice.get("followupStatus") or "").strip().lower()
    if _st in ("not_asked", "declined", "answered"):
        out["followupStatus"] = _st
    return out


_UNRESOLVED_CODE = -32010       # 「需要先问用户是哪个产品」的可执行错误码


def _attribute_product(items: list, params: dict, client_info: dict | None = None) -> dict:
    """归因（D-product-ask-1，2026-11-11 负责人拍板：不许裸 UNKNOWN，缺产品先问）。

    优先级（按拍板口径，不是"原话永远第一"）：
      ① 用户明确回答/确认（params.product，仅问过用户后由模型填）
      ② 原话唯一且高置信提及（多产品/歧义=低置信，转去问）
      ③ 会话记忆（30 分钟滑动，进程内；跨会话不继承）
      ④ 安装先验（**仅在原话出现自指时生效**：D-product-ask-1 修订 A，2026-11-16）
    四级都拿不到（含用户明确说"不知道/随便"= params.productNotSpecified）→
    返回 source=unknown + confidence=low，由调用方抛可执行错误要求追问。
    **不做 host_default 兜底**（2026-11-12 复评删除：宿主产品也是一次推断，
    错归的产品会进引擎幂等/判重域，污染静默且难追溯）。
    """
    text = "\n".join(content for _i, _v, content in items)
    meta = net._load_meta()
    answer = str(params.get("product") or "").strip()
    mem = rt._memory_get(client_info)
    # D-scope-1：请求级产品优先于安装绑定；安装先验只在 product_prior=True 时可用。
    # 共用远程进程（多租户）下必须禁用安装先验——一份 runtime.json 代表不了所有
    # agent，硬用就是错归（与"错归比不归更糟"同源）。
    scope = rt._resolve_scope(client_info)
    binding = (scope["product"]
               or (str(rt._RT.get("product") or "").strip() if scope["product_prior"] else "")
               or None)

    if answer:
        rid = _attrib.resolve_id(answer, meta)
        hit = [c for c in (meta.get("catalog") or [])
               if str(c.get("id")) == str(rid)
               or str(c.get("name") or "").lower() == answer.lower()]
        if not hit and not (meta.get("catalog") or []):
            # 名录不可用（离线/快照/老引擎）：没有校验依据，不能假装能核。
            # 按用户回答原样上报，标 low（引擎侧仍会按表解析，未命中落未知池）。
            return {"product": answer, "productName": answer, "source": "user_answer",
                    "confidence": "low", "rawText": answer,
                    "evidence": [{"reason": "catalog-unavailable", "rawText": answer}],
                    "ignored": None}
        if not hit:
            # 用户说了名录里没有的产品（"智果"/"XYZ"/打错）：**不拿原名硬提交**，
            # 也不要自己猜最像的——把候选交回去，让模型按名录再问一次。
            cands = core.search_products({"query": answer, "limit": 5})["candidates"]
            return {"product": None, "productName": None, "source": "unknown",
                    "confidence": "low", "rawText": answer, "unmatched_answer": answer,
                    "candidates": cands,
                    "evidence": [{"reason": "unmatched-answer", "rawText": answer}],
                    "ignored": None}
        name = hit[0].get("name")
        if hit[0].get("id") is None:
            # S231：目录条目没有主键（老引擎/半坏目录）→ 不能拿名字冒充 productId
            # （str(None) 会写成 "None"，更要拦），交给模型按候选再问一次。
            cands = core.search_products({"query": answer, "limit": 5})["candidates"]
            return {"product": None, "productName": None, "source": "unknown",
                    "confidence": "low", "rawText": answer, "unmatched_answer": answer,
                    "candidates": cands,
                    "evidence": [{"reason": "id_unresolved", "rawText": answer}],
                    "ignored": None}
        return {"product": str(hit[0].get("id")), "productName": name,
                "source": "user_answer", "confidence": "high", "rawText": answer,
                "evidence": [{"product": name, "alias": "用户回答", "snippet": answer}],
                "ignored": None}

    result = _attrib.attribute(text, meta,
                               memory={k: v for k, v in mem.items()
                                       if k in ("product", "productName", "alias",
                                                "snippet", "at")},
                               binding=binding)
    result["rawText"] = None
    result["ignored"] = None
    if result["source"] == "user_input":
        result["confidence"] = "high"
        return result
    if result["source"] == "memory" and mem.get("product") and not mem.get("not_specified"):
        result["confidence"] = "medium"
        return result
    if result["source"] == "install_binding":
        result["confidence"] = "medium"
        return result

    # 用户明确说"不知道/随便"：同样是"不猜、不提交"——只影响回执原因字段
    # （productNotSpecified=true），不做任何兜底推断。
    not_specified = bool(params.get("productNotSpecified")) or bool(mem.get("not_specified"))
    ev = list(result.get("evidence") or [])
    if not_specified:
        ev = [{"reason": "user-not-specified"}] + ev
    return {"product": None, "productName": None, "source": "unknown",
            "not_specified": not_specified,
            "confidence": "low", "rawText": None,
            "evidence": (ev or [{"reason": "no-evidence"}]),
            "ignored": None}


def _require_product_or_ask(attr: dict, items: list, client_info: dict | None = None) -> None:
    """缺产品且用户没说不知道 → 可执行错误：先问一次（D-product-ask-1）。

    错误里带候选（来自原话关键词），模型照着问一句就能补齐；不是"参考文档"。
    """
    if attr.get("product"):
        return
    # 追问轮次上限（2026-11-12 评审采纳）：同一会话最多追问 2 次，之后明确终止——
    # 避免"用户连续给两个都查不到的名字"时模型无限重问。
    # D-scope-1：跨请求持久化计数依赖作用域 key；降级（key=None）时读写皆禁用，
    # 计数自然退化为单轮内计数——不产生跨 agent 污染，正当的"同轮别重复追问"仍成立。
    mem = rt._memory_get(client_info)
    fails = int(mem.get("ask_failures") or 0) + 1
    rt._memory_put(client_info, ask_failures=fails)
    stop = fails > 2
    tail = "（已追问 2 次仍未确认：别再问了，直接告诉用户这条反馈因为没有产品归属而不提交）"

    if attr.get("unmatched_answer"):
        cands = attr.get("candidates") or []
        hint = core.format_candidates(cands, "（名录为空）")
        raise errors.ToolError(
            f"用户说的产品「{attr['rawText']}」不在产品名录里，不能按它提交。"
            f"请按名录再确认一次是哪一个：{hint}；用户仍说不出来就说明这条先不提交。"
            + (tail if stop else ""),
            code=_UNRESOLVED_CODE)
    if attr.get("not_specified"):
        # 兼容 Python 3.10/3.11：PEP 701 之前 f-string 表达式内不允许反斜杠
        # （'\n' 会触发 SyntaxError），故先在 f-string 外计算查询串再引用。
        _query = "\n".join(x[2] for x in items)
        _cands_hint = core.format_candidates(
            core.search_products({"query": _query, "limit": 5})["candidates"],
            "（名录不可用：请让用户直接说产品名）")
        raise errors.ToolError(
            "用户没有提供产品，这条反馈**不能提交**：请告诉用户「没有产品归属的反馈我不提交，"
            "因为不知道要转给哪个产品团队」，并请他补充是哪个产品；他仍不想说就说明这条先不提交。"
            f"可选候选：{_cands_hint}"
            + (tail if stop else ""),
            code=_UNRESOLVED_CODE)
    if os.environ.get("VOD_ALLOW_UNKNOWN_PRODUCT") == "1":
        # 旧客户端兼容（业界口径：可选字段 + 明确默认值，不做破坏性变更）：
        # 缺 product 的老客户端不让它直接失败，回执标 legacy_default/low，可追溯。
        attr["source"] = "legacy_default"
        attr["confidence"] = "low"
        return
    text = "\n".join(c for _i, _v, c in items)
    cands = core.search_products({"query": text, "limit": 5})["candidates"]
    hint = core.format_candidates(cands, "（名录未命中，可问用户直接说产品名）")
    raise errors.ToolError(
        "这条反馈还没确定是哪个产品：请先问用户一次『这条是哪个产品的反馈？』，"
        "把回答填进 product（产品名或 ID）；用户明确说不知道/随便时，传 productNotSpecified=true。"
        f"候选：{hint}", code=_UNRESOLVED_CODE)


def _attach_attribution(result: dict, attr: dict) -> None:
    """回执留痕（D-product-ask-1）：来源 + 置信 + 原始回答 + 证据。

    productSource 枚举：user_input | user_answer | memory | install_binding |
    host_default（后者恒 confidence=low，必须可人工修正）。
    """
    result["productSource"] = attr.get("source") or "unknown"
    result["productConfidence"] = attr.get("confidence") or "low"
    if attr.get("productName"):
        result["productName"] = attr["productName"]
    if attr.get("product") is not None:
        result["productId"] = str(attr["product"])
    if attr.get("rawText"):
        result["productRawText"] = attr["rawText"]
    if attr.get("evidence"):
        result["productEvidence"] = attr["evidence"]


def _merge_ledger(extra: dict | None, attr: dict) -> dict:
    """账本条目带上归因来源与证据：错归可回溯到用户原话（S99）。"""
    out = dict(extra or {})
    out["productSource"] = attr.get("source") or "unknown"
    if attr.get("evidence"):
        out["productEvidence"] = attr["evidence"]
    return out
