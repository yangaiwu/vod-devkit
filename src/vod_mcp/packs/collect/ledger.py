"""本机账本查询（已提交声音）。（ARCH-CALL-04：从 packs/collect.py 拆出）。"""
from vod_mcp import runtime_state as rt


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
