"""单条式提交链（校验 → 归因 → 囤积提交 → 回执 → pending 补交）。（ARCH-CALL-04：从 packs/collect.py 拆出）。"""
from vod_mcp import errors
from vod_mcp import net
from vod_mcp import runtime_state as rt
from vod_mcp.packs.collect.attribution import _attach_attribution, _attribute_product, _followup_fields, _merge_ledger, _require_product_or_ask
from vod_mcp.packs.collect.tags import _filter_tags

import importlib


def _facade():
    """经门面取被测试打桩的函数（importlib 而非静态 import：避免 collect 包 ↔ 子模块成环）。"""
    return importlib.import_module("vod_mcp.packs.collect")



_SUBMIT_HOARDING = "/rest/developer/manager/hdvodmngservice/v1/external/voices"


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
    （归因错位比报错更糟，同 AIShell 错归病根）。囤积端点单一路径同口径（S238）。"""
    raise errors.ToolError(
        f"注入的 key 被引擎拒绝（指纹 {net._fingerprint(key)}）："
        "请核对 key 是否过期/被吊销，或移除 key 走匿名档。"
        + net._legacy_key_hint(),
        code=-32012)


def submit_voices(params: dict, client_info: dict | None = None,
                  ledger_extra: dict | None = None) -> dict:
    """唯一提交路径=囤积端点 POST /external/voices（Bearer，批式，不触发分析）。

    S238：删除过渡期 404 回落老链（/external/voice/submit）——引擎已上线囤积端点，
    回落分支是死代码，且两套语义（提交即分析 vs 延迟分析）会让同一插件在不同引擎上
    行为不同。404 现在明确报错（-32016），不假装成功、不偷偷换链。

    - voiceId：由引擎确定性计算（per-token/per-install 命名空间），回执 voiceIds
      为权威对账键
    - title=用户原文截断；tags=采集层三分类（problem_type:）正式入库通道
    - source：key 持有者被引擎锚定为 host_name（legacy 共用 key 场景已随 S238 删除）
    """
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

    # 服务面（HTTP）：身份优先取请求头 Bearer；没有就同本地一样走机器级匿名令牌
    # （D-token-machine-1 定稿：本地/远程同一套身份语义。远程多租户若需按调用方隔离，
    #  由调用方带 Bearer 显式给出身份；匿名是"整机一份"的低信任档）

    # 缺产品且用户没说不知道 → 可执行错误（先问一次），不许裸提交 UNKNOWN
    _require_product_or_ask(attr, items, client_info)
    # ---- 主路径：囤积端点批式提交 ----
    # 分类白名单按产品取（引擎 ?productId= 下发）；product 非数字 id 时取不到→不过滤
    allowed_tags = _facade()._allowed_tags(product)
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
    try:
        out = net._http("POST", _SUBMIT_HOARDING, body, base=net.JAVA_BASE, key=net._eff_key())
    except errors.ToolError as ex:
        if ex.upstream_status == 404 or ex.code == 404:
            # S238：不再回落老链。引擎未部署囤积端点时如实报错，不假装成功、不换语义
            # ARCH-ERR-03：`_http` 不再把上游状态码塞进 code（改放 upstream_status），
            # 这里两个都认——兼容历史抛点（老插件可能仍透传 404）。
            raise errors.ToolError(
                "囤积端点未上线（POST /external/voices 返回 404）：本条**未提交**。"
                "引擎部署该端点后自动可用；不要改用老链 /external/voice/submit。",
                code=-32016) from ex
        elif not net._eff_key() or ex.code == -32012:
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
