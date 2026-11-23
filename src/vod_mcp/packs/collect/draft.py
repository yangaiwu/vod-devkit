"""两段式提交（draft 暂存 + 一次性令牌 → commit 落库）。（ARCH-CALL-04：从 packs/collect.py 拆出）。"""
import json
from vod_mcp import errors
from vod_mcp import runtime_state as rt
from vod_mcp.packs.collect.attribution import _attach_attribution, _attribute_product, _followup_fields
from vod_mcp.packs.collect.tags import _filter_tags

import importlib


def _facade():
    """经门面取被测试打桩的函数（importlib 而非静态 import：避免 collect 包 ↔ 子模块成环）。"""
    return importlib.import_module("vod_mcp.packs.collect")



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
    allowed_tags = _facade()._allowed_tags(product)

    for i, v in enumerate(voices_in):
        content = str(v.get("content", "")).strip()
        if not content:
            raise errors.ToolError(f"第 {i + 1} 条 content 为空", code=-32602)
        if len(content) > 2000:
            raise errors.ToolError(f"第 {i + 1} 条 content 超 2000 字（{len(content)}）", code=-32602)
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
        raise errors.ToolError("voices 为必填且至少 1 条", code=-32602)
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
            # 草稿归属（D-token-machine-1 远程面放开两段式的前置）：
            # 同机多个 agent 共用一个远程 server 时草稿池是共享的，
            # 记录创建者、commit 时校验，避免"A 的草稿被 B 提交"。
            # 旧草稿无 owner 字段 → commit 兼容放行（升级不断回合）。
            # 🔴 审查 ④（2026-11-19）：用 _draft_owner（只认会话/进程）而非
            # _session_key —— 后者优先认 X-Vod-Agent-Id，同头的另一个连接能提交
            # 别人的草稿（实测放行）。归属跟对话走，不跟自我声明的头走。
            "owner": rt._draft_owner(client_info),
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


def _same_owner_kind(a: str | None, b: str | None) -> bool:
    """两个草稿归属指纹是否属于"同一个人自己漂了"（审查 ④ 话术分档判据）。

    只有**两个都只是会话标识**（`sess:<sid>`，无 agent 摘要）才算同类 ——
    那对应"同一条连接重连/进程重启换了会话"，用户只是接着刚才那件事提交。

    其余情况一律按"不属于当前客户端"回（不泄露存在性也无妨，因为错误码相同）：
      · 任一侧带 agent 摘要   → 两个不同的对话在抢同一份草稿，不能暗示"你自己重连了"
      · sess:* 与 proc:*      → 传输形态都变了，不是"重连"
      · 任一侧为空            → 无法判断，保守
    """
    sa = str(a or "")
    sb = str(b or "")
    if not sa or not sb:
        return False
    if "|agent:" in sa or "|agent:" in sb:
        return False
    ka = sa.split(":", 1)[0]
    kb = sb.split(":", 1)[0]
    return ka == kb == "sess"


def commit_voices(params: dict, client_info: dict | None = None) -> dict:
    """两段式第二步：令牌校验→单次消费→复用 submit_voices 既有提交链。

    D-resume-commit-1：approvalToken/payloadSha256 可省略——draftId 命中本地
    未过期草稿时自动恢复（断回合续提交）。显式传入仍走原校验（传了假 sha
    照样拒），恢复路径的完整性由签发时落盘的 sha/token 保证，语义不放宽。
    """
    draft_id = str(params.get("draftId", ""))
    if not draft_id:
        raise errors.ToolError("draftId 为必填（取自 vod_draft_voices 返回原样透传）", code=-32602)

    holder: dict = {}

    def _consume(cfg: dict) -> None:
        """校验 + 单次消费**同一事务内**完成。

        为什么不能在锁外读 store 再进锁里 pop：读到的是一份快照，覆盖回去会把别的
        draft 甚至已消费的草稿复活（跨进程时尤其明显）。
        """
        store = rt._drafts_purge(cfg.get(rt._DRAFT_KEY) or {})
        draft = store.get(draft_id)
        if draft is None:
            raise errors.ToolError("草稿不存在或已过期（10 分钟 TTL），请重新 vod_draft_voices",
                                code=-32011)
        owner = draft.get("owner")
        cur_owner = rt._draft_owner(client_info)
        if owner and owner != cur_owner:
            # 两类原因回同一错误码（不泄露"存在性"），但话术必须分档（审查 ④）：
            #   前缀同类（sess:/proc: 都是自己的边界）→ 会话漂移：重连/进程重启，
            #     用户只是"接着刚才那件事提交"，要告诉他重新暂存即可，不是被人截了。
            #   前缀不同类 / 一方是 agent: → 不是同一个对话，保持"不属于当前客户端"。
            if _same_owner_kind(owner, cur_owner):
                raise errors.ToolError(
                    "草稿绑定了原会话（重连/进程重启会换会话），这份草稿已不能提交："
                    "请重新调用 vod_draft_voices 暂存后再提交（内容按刚才确认的原样）",
                    code=-32011)
            raise errors.ToolError(
                "这份草稿不属于当前客户端（草稿按宿主/会话隔离：只能由创建它的那个 agent 提交）",
                code=-32011)
        token = str(params.get("approvalToken", "")) or str(draft.get("token", ""))
        payload_sha = str(params.get("payloadSha256", "")) or str(draft["payloadSha256"])
        if draft["tokenHash"] != rt._sha256(token):
            raise errors.ToolError("审批令牌不匹配（draft 返回的 approvalToken 原样透传）",
                                code=-32011)
        if draft["payloadSha256"] != payload_sha:
            raise errors.ToolError("载荷校验不符（payloadSha256 与 draft 签发值不一致，禁止改写已确认内容）",
                                code=-32011)
        # 单次消费：提交中途崩溃也不会二次提交（宁可丢一单重走流程）
        store.pop(draft_id)
        cfg[rt._DRAFT_KEY] = store
        holder["draft"] = draft

    rt._runtime_atomic(_consume)
    draft = holder["draft"]

    out = _facade().submit_voices(dict(draft["payload"]), client_info,
                        ledger_extra={"stage": "committed", "draftId": draft_id})
    out["twoPhase"] = True
    out["draftId"] = draft_id
    return out
