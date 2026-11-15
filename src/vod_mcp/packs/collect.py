"""collect pack：用户声音采集全链（校验 → 归因 → 提交/两段式 → 账本 → 回显 → pending）。"""
import json
import os

from vod_mcp import attribution as _attrib
from vod_mcp import net, runtime_state as rt
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
      ④ 安装先验
    四级都拿不到（含用户明确说"不知道/随便"= params.productNotSpecified）→
    返回 source=unknown + confidence=low，由调用方抛可执行错误要求追问。
    **不做 host_default 兜底**（2026-11-12 复评删除：宿主产品也是一次推断，
    错归的产品会进引擎幂等/判重域，污染静默且难追溯）。
    """
    text = "\n".join(content for _i, _v, content in items)
    meta = net._load_meta()
    answer = str(params.get("product") or "").strip()
    mem = rt._memory_get(client_info)
    binding = str(rt._RT.get("product") or "").strip() or None

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
    mem = rt._memory_get(client_info)
    fails = int(mem.get("ask_failures") or 0) + 1
    rt._memory_put(client_info, ask_failures=fails)
    stop = fails > 2
    tail = "（已追问 2 次仍未确认：别再问了，直接告诉用户这条反馈因为没有产品归属而不提交）"

    if attr.get("unmatched_answer"):
        cands = attr.get("candidates") or []
        hint = "、".join(f"{c['name']}（{c['id']}）" for c in cands) or "（名录为空）"
        raise net.ToolError(
            f"用户说的产品「{attr['rawText']}」不在产品名录里，不能按它提交。"
            f"请按名录再确认一次是哪一个：{hint}；用户仍说不出来就说明这条先不提交。"
            + (tail if stop else ""),
            code=_UNRESOLVED_CODE)
    if attr.get("not_specified"):
        # 兼容 Python 3.10/3.11：PEP 701 之前 f-string 表达式内不允许反斜杠
        # （'\n' 会触发 SyntaxError），故先在 f-string 外计算查询串再引用。
        _query = "\n".join(x[2] for x in items)
        raise net.ToolError(
            "用户没有提供产品，这条反馈**不能提交**：请告诉用户「没有产品归属的反馈我不提交，"
            "因为不知道要转给哪个产品团队」，并请他补充是哪个产品；他仍不想说就说明这条先不提交。"
            f"可选候选：{'、'.join(c['name'] + '（' + str(c['id']) + '）' for c in core.search_products({'query': _query, 'limit': 5})['candidates'])}"
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
    hint = "、".join(f"{c['name']}（{c['id']}）" for c in cands) or "（名录未命中，可问用户直接说产品名）"
    raise net.ToolError(
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


_SUBMIT_HOARDING = "/rest/developer/manager/hdvodmngservice/v1/external/voices"


_EXISTING_SUBMIT = "/rest/developer/manager/hdvodmngservice/v1/external/voice/submit"  # 过渡期 404 回落


def _voice_id(source: str, content: str, nonce: str) -> str:
    """voiceId = f(source, content, 调用级nonce)。

    R1 修正（声量保真）：跨调用不去重——不同用户提交同款反馈必须各占
    一行（声量是分析核心信号）；同调用内重试复用同 nonce 保幂等。
    """
    import hashlib
    return f"ext_{source}_{hashlib.sha1((content + nonce).encode('utf-8')).hexdigest()[:12]}"


def _flush_pending(product):
    """补提交 ~/.vod-devkit/pending-feedback.jsonl 里 status=pending 的条目。

    口径（D-pending-1 定稿）：同步执行但失败只记日志、绝不回滚主提交；
    幂等键=条目级（sha1(content+confirmAt+source)），内容级去重由引擎
    uk_voice_id 承担（同内容重提=skipped）；重写+原子 rename，失败条目
    保留 pending；单次上限 100 条最早优先，超 30 天标记 expired 剔除。
    双通道消息分离：本函数结果只进工具内部诊断（result.pendingFlush），
    用户侧话术由 skill 层承担（已暂存/自动补交，禁止出现路径）。
    """
    from vod_mcp import pending as _pq
    path = _pq.default_path()
    entries = _pq.load_entries(path)
    if not entries:
        return {"scanned": 0}
    plan = _pq.plan_flush(entries)
    kept = list(plan["kept"])
    flushed, failed, corrected = 0, 0, 0
    for e in plan["to_flush"]:
        content = _pq.canonical_content(e)  # D-pending-1 补强：originalLines 权威拼接，剥模型加的标点
        if content != str(e.get("content", "")):
            corrected += 1
            rt._log("pending flush: content 与 originalLines 拼接不一致，以 originalLines 为准（剥除模型拼接改动）")
        hv = {"title": str(content)[:60], "content": str(content)}
        if e.get("tags"):
            hv["tags"] = e["tags"]
        body = {"voices": [hv]}
        if product:
            body["product"] = product
        try:
            out = net._http("POST", _SUBMIT_HOARDING, body, base=net.JAVA_BASE, key=net._eff_key())
            ids = (out or {}).get("voiceIds") or ((out or {}).get("data") or {}).get("voiceIds")
            if ids is None:
                failed += 1
                kept.append(e)
                rt._log("pending flush: 回执未含 voiceIds，条目保留")
            else:
                flushed += 1  # 含幂等 skipped（同内容重提=引擎 skipped，零重复）
        except Exception as err:
            failed += 1
            kept.append(e)
            rt._log(f"pending flush failed (kept pending): {err}")
    _pq.save_entries(path, kept)
    return {"scanned": len(entries), "flushed": flushed,
            "failed": failed, "expired": len(plan["expired"]),
            "corrected": corrected}


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


def _collect_voice_items(params: dict) -> tuple[list, list]:
    """校验段：content 非空+≤2000 字（契约 maxLength，防超大 payload）。
    返回 (items[(index, voice, content)], rejected 明细)。"""
    items, rejected = [], []
    for i, v in enumerate(params.get("voices", [])):
        content = str(v.get("content", "")).strip()
        if not content:
            rejected.append({"index": i, "reason": "content 为空"})
        elif len(content) > 2000:
            rejected.append({"index": i, "reason": f"content 超 2000 字（{len(content)}）"})
        else:
            items.append((i, v, content))
    return items, rejected


def _echo_plan(items: list, vids: list) -> dict:
    """回显段（方案 A，2026-11-06 拍板）：提交回执强制携带原话回显。
    检测型防线——宿主模型改写用户原话（实锤："体验不好"→"不友好"）
    在回执处当场可见；agent 必须原样转述，改写露馅。"""
    ok = [(vid, items[min(i, len(items) - 1)][2])
          for i, vid in enumerate(vids) if vid]
    return {
        "requiresUserEcho": bool(ok),
        "instruction": ("请向用户原样转述已收录内容：每条以「已收录原话：」开头，"
                        "后接 content 全文。禁止改写、概括、增删字词。"),
        "contents": [{"voiceId": vid, "content": c} for vid, c in ok],
    }


def _ledger_submit(items: list, vids: list, tids: list, product: str | None,
                    extra: dict | None = None) -> None:
    """账本段：回执 voiceIds/taskIds 逐条落本地账本（层级①查询的源）。"""
    import time as _time
    entries = [{"voiceId": vid, "taskId": tid,
                "title": items[min(i, len(items) - 1)][2][:40],
                "product": product, "at": _time.strftime("%Y-%m-%dT%H:%M:%S")}
               for i, (vid, tid) in enumerate(zip(vids, tids))]
    if extra:
        for e in entries:
            e.update(extra)  # 两段式：stage=committed + draftId 关联（验收③）
    rt._ledger_append(entries)


def _hoard_voice(v: dict, content: str) -> dict:
    """载荷段：单条囤积端点 voice 载荷（title/content + tags/userType +
    D-followup-impl-2 追问补充透传：单源 _followup_fields，拒答词集兜底）。"""
    hv = {"title": content[:60], "content": content}
    if v.get("tags"):  # 采集层三分类（problem_type:值）→正式入库
        hv["tags"] = v["tags"]
    if v.get("userType"):
        hv["userType"] = v["userType"]
    hv.update(_followup_fields(v))
    return hv


def _raise_explicit_key_rejected(key: str) -> None:
    """显式 key（安装注入/正式档）被引擎 401 拒绝 → fail fast：
    不取匿名令牌、不覆盖配置——静默降级匿名档=配置错误被吞
    （归因错位比报错更糟，同 AIShell 错归病根）。囤积/legacy 两路径同口径。"""
    raise net.ToolError(
        f"注入的 key 被引擎拒绝（指纹 {net._fingerprint(key)}）："
        "请核对 key 是否过期/被吊销，或移除 key 走匿名档。"
        + net._legacy_key_hint(),
        code=-32012)


def submit_voices(params: dict, client_info: dict | None = None,
                  ledger_extra: dict | None = None) -> dict:
    """V16 切换：主路径=囤积端点 POST /external/voices（Bearer，批式，不触发分析）；
    引擎未部署（404）自动回落老链 /external/voice/submit（提交即分析，过渡语义，
    部署后 404 分支自然失效）。

    - voiceId：囤积链由引擎确定性计算（per-token/per-install 命名空间），回执
      voiceIds 为权威对账键；回落老链仍用客户端 nonce id（R1 声量保真）
    - title=用户原文截断；tags=采集层三分类（problem_type:）正式入库通道
    - source：key 持有者被引擎锚定为 host_name；legacy 共用 key 场景带
      per-install nonce 后缀（杜绝跨用户共享命名空间吞声量）
    """
    import uuid
    host = (client_info or {}).get("name") or "unknown-host"
    accepted = 0
    voice_ids: list[str] = []
    task_ids: list[object] = []
    items, rejected = _collect_voice_items(params)
    if not items:
        return {"accepted": 0, "voiceIds": [], "taskIds": [], "rejected": rejected}
    # 归因（D-attrib-B）：证据来自用户原话，模型自报不参战
    # 归因（D-product-ask-1）：身份/鉴权优先于产品追问，产品校验放在下面 key 守卫之后
    attr = _attribute_product(items, params, client_info)
    product = attr["product"]

    def _legacy_submit(i, v, content):
        """过渡回落：老链单条提交（提交即分析语义，仅 404 触发）。"""
        nonce = uuid.uuid4().hex[:8]  # 调用级：重试复用，跨调用不重复
        vid = _voice_id(host, content, nonce)
        desc = content if len(content) >= 10 else f"{content} [vod-devkit]"
        body = {
            "voiceId": vid,
            "title": content[:128],
            "description": desc,
            "source": f"{host}-{rt._install_nonce()}",  # per-install 命名空间（legacy 吞声量修复）
            "customer": v.get("userType"),
        }
        if product:
            body["product"] = product
        out = net._http("POST", _EXISTING_SUBMIT, body, base=net.JAVA_BASE, key=net._eff_key())
        return vid, (out.get("data") or {}).get("taskId")

    # 服务面（HTTP）：身份只能来自请求头。缺 key 时 fail fast——不先打引擎再
    # 靠 401 兜底（那会多一次无意义外呼，且引擎若宽容 200 就绕过了守卫）。
    if net._SERVER_FACE.get() and not net._eff_key():
        raise net.ToolError(
            "服务面（HTTP 传输）不代签身份：请在本请求带上 Authorization: Bearer "
            "<VOD key>（插件只搬运身份，不产生身份；落库与配额都在服务端）",
            code=-32012)

    # 缺产品且用户没说不知道 → 可执行错误（先问一次），不许裸提交 UNKNOWN
    _require_product_or_ask(attr, items, client_info)
    # ---- 主路径：囤积端点批式提交 ----
    # 分类白名单按产品取（引擎 ?productId= 下发）；product 非数字 id 时取不到→不过滤
    allowed_tags = _allowed_tags(product)
    hoard, invalid_tags = [], []
    for i, v, content in items:
        hv = _hoard_voice(v, content)
        if hv.get("tags"):
            kept, dropped = _filter_tags(hv["tags"], allowed_tags)
            if kept:
                hv["tags"] = kept
            else:
                hv.pop("tags", None)
            if dropped:
                invalid_tags.append({"index": i, "tags": dropped})
        hoard.append(hv)
    body = {"voices": hoard}
    if product:  # 无归因不带 product（引擎 UNKNOWN 档），不本地拦截
        body["product"] = product
    out = None
    fallback = False
    try:
        out = net._http("POST", _SUBMIT_HOARDING, body, base=net.JAVA_BASE, key=net._eff_key())
    except net.ToolError as ex:
        if ex.code == 404:
            fallback = True  # 囤积端点未部署 → 落到下方 legacy 回落
        elif not net._eff_key() or ex.code == -32012:
            if net._SERVER_FACE.get():
                # 服务面（HTTP）：不代签身份。匿名令牌按设备锚点签发，一进程
                # 一锚点会把配额/声量/归因全搅在一起（服务端多用户形态的
                # 已拍板口径：formal/host key + 按请求透传）。
                raise net.ToolError(
                    "服务面（HTTP 传输）不代签身份：请在本请求带上 "
                    "Authorization: Bearer <VOD key>，或改用 stdio 形态的匿名链",
                    code=-32012)
            if net._explicit_key():
                _raise_explicit_key_rejected(net._eff_key())
            # 缺 key/匿名令牌失效 → 零字段匿名令牌 → 落 runtime.json → 重试一次
            token = net._acquire_anon_token_or_raise()
            # 统一状态入口（落盘 + 镜像）；net 的 key 是调用期现读，不再写模块属性——
            # 写属性会让 __getattr__ 失效、这份 token 又被冻结在进程里（D-state-read-1）
            rt._runtime_update({"java_key": token, "token_tier": "anonymous"})
            out = net._http("POST", _SUBMIT_HOARDING, body, base=net.JAVA_BASE, key=net._eff_key())
        else:
            raise  # 网络/413 等如实上抛
    if not fallback:
        out = out or {}   # 类型收窄：非回落分支必然已赋值（初值 None 只是失败占位）
        server_ids = (out.get("voiceIds") or out.get("data", {}).get("voiceIds")
                      or [])
        # 引擎侧 rejected（产品校验拒绝等）透出，不吞（对齐 widget rejected 口径）
        engine_rejected = ((out or {}).get("rejected")
                           or ((out or {}).get("data") or {}).get("rejected")
                           or [])
        if server_ids:
            accepted = len(server_ids)
            voice_ids.extend(server_ids)
        else:
            # 回执缺失/整批被拒 → 不得兜底计成功（实锤缺陷：空 voiceId 记成功
            # 且宿主模型据此谎报"已提交"）。accepted 以真实回执为准。
            accepted = 0
            voice_ids.extend([""] * len(items))
            if not engine_rejected:
                engine_rejected = [{"reason": "引擎回执未含 voiceIds（提交结果未知），请勿视为已收录"}]
        task_ids.extend([None] * len(items))  # 囤积语义：无即时任务
        result = {"accepted": accepted, "voiceIds": voice_ids,
                  "taskIds": task_ids, "rejected": rejected + engine_rejected,
                  "analysis": "deferred",  # 囤积语义明示（V6 运营批量消费）
                  "path": "hoarding",
                  "echo": _echo_plan(items, voice_ids)}
        if invalid_tags:  # 分类白名单外值被丢弃（不拒收声音，只丢 tag）
            result["invalidTags"] = invalid_tags
        if out.get("productRegistered") is not None:
            result["productRegistered"] = out.get("productRegistered")
        _attach_attribution(result, attr)      # 来源+证据留痕（S99）
        rt._remember_attribution(attr, client_info)   # 会话记忆 + 审计（S95/S100）
        _ledger_submit(items, voice_ids, task_ids, product,
                        _merge_ledger(ledger_extra, attr))
        result["pendingFlush"] = _flush_pending(product)
        return result
    # ---- 过渡回落：老链单条提交（仅囤积端点 404 触发） ----
    for i, v, content in items:
        try:
            vid, tid = _legacy_submit(i, v, content)
            accepted += 1
            voice_ids.append(vid)
            task_ids.append(tid)
        except net.ToolError as e:
            msg = str(e)
            if "Duplicate entry" in msg:  # 极端重放场景：DB 唯一键兜底
                accepted += 1
                voice_ids.append(vid)
                task_ids.append(None)
            elif (not net._eff_key() or e.code == -32012) and not voice_ids:
                if net._SERVER_FACE.get():
                    rejected.append({"index": i, "reason":
                        "服务面（HTTP 传输）不代签身份：请带 Authorization: Bearer <VOD key>"})
                    continue
                if net._explicit_key():
                    _raise_explicit_key_rejected(net._eff_key())
                # 零字段匿名令牌：缺 key/401 → 自动取令牌 → 落 runtime.json → 重试一次
                token = net._acquire_anon_token_or_raise()
                rt._runtime_update({"java_key": token, "token_tier": "anonymous"})
                vid, tid = _legacy_submit(i, v, content)
                accepted += 1
                voice_ids.append(vid)
                task_ids.append(tid)
            else:
                rejected.append({"index": i, "reason": msg[:120]})
    result = {"accepted": accepted, "voiceIds": voice_ids,
              "taskIds": task_ids, "rejected": rejected,
              "path": "legacy-fallback",
              "echo": _echo_plan(items, voice_ids)}
    _attach_attribution(result, attr)
    if accepted:
        rt._remember_attribution(attr, client_info)
    _ledger_submit(items, voice_ids, task_ids, product,
                   _merge_ledger(ledger_extra, attr))
    result["pendingFlush"] = _flush_pending(product)
    return result


def list_submitted(params: dict, client_info: dict | None = None) -> dict:
    """查询本机已提交的声音（只读，采集者对账闭环）。
    引擎级跨机查询随 VOD-VOI 列表端点；终端用户自助查询维持 P2（签名回执）。"""
    limit = params.get("limit", 20)
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20
    ledger = rt._runtime_cfg().get(rt._LEDGER_KEY) or []  # 文件现读（进程内账本可能刚更新）
    return {"total": len(ledger),
            "submissions": ledger[-limit:][::-1],  # 最新在前
            "scope": "本机提交记录（换机/重装不保留；引擎级查询随 VOD-VOI）"}


def draft_voices(params: dict, client_info: dict | None = None) -> dict:
    """两段式第一步：校验+暂存草稿+签发一次性令牌（不提交任何数据）。"""
    import time as _time
    voices_in = params.get("voices", [])
    invalid_tags = []
    clean = []

    # 归因（D-attrib-B）前移：分类白名单按产品下发（?productId=），必须先知道
    # 产品才能取到该产品的分类集，否则过滤会拿到空集而静默失效。
    # 归因只看 content，不依赖 tags，前移不改变其它语义。
    _attr_items = []
    for i, v in enumerate(voices_in):
        _c = str(v.get("content", "")).strip()
        if _c:
            _attr_items.append((i, v, _c))
    attr = (_attribute_product(_attr_items, params, client_info)
            if _attr_items else {"product": None, "source": "unknown",
                                 "confidence": "low"})
    product = attr.get("product")
    allowed_tags = _allowed_tags(product)

    for i, v in enumerate(voices_in):
        content = str(v.get("content", "")).strip()
        if not content:
            raise net.ToolError(f"第 {i + 1} 条 content 为空", code=-32602)
        if len(content) > 2000:
            raise net.ToolError(f"第 {i + 1} 条 content 超 2000 字（{len(content)}）", code=-32602)
        item = {"content": content}
        if v.get("tags"):
            kept, dropped = _filter_tags(v["tags"], allowed_tags)
            if kept:
                item["tags"] = kept
            if dropped:
                invalid_tags.append({"index": i, "tags": dropped})
        if v.get("userType"):
            item["userType"] = v["userType"]
        # D-followup-impl-2：追问补充随 draft 暂存（commit 复用 payload 原样上送），
        # 单源 _followup_fields 与主路径同口径
        item.update(_followup_fields(v))
        clean.append(item)
    if not clean:
        raise net.ToolError("voices 为必填且至少 1 条", code=-32602)
    rt._remember_attribution(attr, client_info)

    import secrets
    draft_id = "draft_" + secrets.token_hex(8)
    token = secrets.token_hex(16)
    payload: dict[str, object] = {"voices": clean}
    if product:
        payload["product"] = product
    # 载荷 sha（防 draft→commit 间改写：commit 校验插件侧重算值一致）
    import hashlib
    payload_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def _mutate(cfg: dict):
        store = rt._drafts_purge(cfg.get(rt._DRAFT_KEY) or {})
        store[draft_id] = {
            "payload": payload, "payloadSha256": payload_sha,
            "tokenHash": rt._sha256(token),
            # D-resume-commit-1：token 明文随草稿落盘（runtime.json 0600，与 java_key
            # 同级保护）。token 的威胁模型是"防载荷改写"而非"同意凭证"——落盘不放大
            # 风险，换断回合可续：agent 回合中断后凭 draftId 即可恢复提交（此前
            # approvalToken 只存在于 draft 响应文本，回合断即丢失，只能重开草稿）
            "token": token,
            "product": product, "productSource": attr.get("source"),
            "productEvidence": attr.get("evidence") or [],
            "createdAt": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "expiresAt": _time.time() + rt._DRAFT_TTL,
        }
        while len(store) > rt._DRAFT_CAP:  # 环形：最旧先淘汰
            store.pop(next(iter(store)))
        cfg[rt._DRAFT_KEY] = store

    rt._runtime_atomic(_mutate)   # 读整键→改→写整键必须整段在锁内（跨进程）

    out = {
        "draftId": draft_id,
        "approvalToken": token,
        "payloadSha256": payload_sha,
        "expiresInSeconds": rt._DRAFT_TTL,
        "contents": [{"index": i, "content": it["content"]} for i, it in enumerate(clean)],
        "instruction": ("把 contents 逐条原样展示给用户核对（禁止改写概括），明确问"
                        "「确认提交吗」。用户明确同意前禁止调用 vod_commit_voices；"
                        "不同意则停（草稿 10 分钟后自动作废）。"),
    }
    _attach_attribution(out, attr)  # 草稿阶段也让归因来源可审（commit 回执沿用）
    if invalid_tags:
        out["invalidTags"] = invalid_tags
    return out


def commit_voices(params: dict, client_info: dict | None = None) -> dict:
    """两段式第二步：令牌校验→单次消费→复用 submit_voices 既有提交链。

    D-resume-commit-1：approvalToken/payloadSha256 可省略——draftId 命中本地
    未过期草稿时自动恢复（断回合续提交）。显式传入仍走原校验（传了假 sha
    照样拒），恢复路径的完整性由签发时落盘的 sha/token 保证，语义不放宽。
    """
    draft_id = str(params.get("draftId", ""))
    if not draft_id:
        raise net.ToolError("draftId 为必填（取自 vod_draft_voices 返回原样透传）", code=-32602)

    holder: dict = {}

    def _consume(cfg: dict) -> None:
        """校验 + 单次消费**同一事务内**完成。

        为什么不能在锁外读 store 再进锁里 pop：读到的是一份快照，覆盖回去会把别的
        draft 甚至已消费的草稿复活（跨进程时尤其明显）。
        """
        store = rt._drafts_purge(cfg.get(rt._DRAFT_KEY) or {})
        draft = store.get(draft_id)
        if draft is None:
            raise net.ToolError("草稿不存在或已过期（10 分钟 TTL），请重新 vod_draft_voices",
                                code=-32011)
        token = str(params.get("approvalToken", "")) or str(draft.get("token", ""))
        payload_sha = str(params.get("payloadSha256", "")) or str(draft["payloadSha256"])
        if draft["tokenHash"] != rt._sha256(token):
            raise net.ToolError("审批令牌不匹配（draft 返回的 approvalToken 原样透传）",
                                code=-32011)
        if draft["payloadSha256"] != payload_sha:
            raise net.ToolError("载荷校验不符（payloadSha256 与 draft 签发值不一致，禁止改写已确认内容）",
                                code=-32011)
        # 单次消费：提交中途崩溃也不会二次提交（宁可丢一单重走流程）
        store.pop(draft_id)
        cfg[rt._DRAFT_KEY] = store
        holder["draft"] = draft

    rt._runtime_atomic(_consume)
    draft = holder["draft"]

    out = submit_voices(dict(draft["payload"]), client_info,
                        ledger_extra={"stage": "committed", "draftId": draft_id})
    out["twoPhase"] = True
    out["draftId"] = draft_id
    return out
