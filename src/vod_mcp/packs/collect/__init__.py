"""collect pack：用户声音采集全链（ARCH-CALL-04：692 行单模块拆成五个关注点）。

七件事的归属：
  attribution 归因与追问（产品定位 / 缺产品拒绝 / 回执与账本附加字段）
  tags        分类白名单（problem_type 校验与过滤）
  submit      单条式提交链（校验 → 归因 → 囤积提交 → 回执 → pending 补交）
  draft       两段式提交（draft 暂存 + 一次性令牌 → commit 落库）
  ledger      本机账本查询

本文件只做**再导出**：`packs.collect.X` 的既有调用面（含测试使用的私有符号）不变，
拆分的目的是让"改提交链"不必读全 692 行。
"""
from vod_mcp.packs.collect.attribution import (  # noqa: F401
    _FOLLOWUP_DECLINES, _UNRESOLVED_CODE, _attach_attribution, _attribute_product, _followup_fields, _merge_ledger, _require_product_or_ask,
)
from vod_mcp.packs.collect.tags import (  # noqa: F401
    _PROBLEM_TYPE_PREFIX, _allowed_tags, _filter_tags,
)
from vod_mcp.packs.collect.submit import (  # noqa: F401
    _SUBMIT_HOARDING, _collect_voice_items, _echo_plan, _flush_pending, _hoard_voice, _ledger_submit, _raise_explicit_key_rejected, _voice_id, submit_voices,
)
from vod_mcp.packs.collect.draft import (  # noqa: F401
    _same_owner_kind, commit_voices, draft_voices,
)
from vod_mcp.packs.collect.ledger import (  # noqa: F401
    list_submitted,
)

__all__ = [
    "_FOLLOWUP_DECLINES", "_UNRESOLVED_CODE", "_attach_attribution", "_attribute_product", "_followup_fields", "_merge_ledger", "_require_product_or_ask",
    "_PROBLEM_TYPE_PREFIX", "_allowed_tags", "_filter_tags",
    "_SUBMIT_HOARDING", "_collect_voice_items", "_echo_plan", "_flush_pending", "_hoard_voice", "_ledger_submit", "_raise_explicit_key_rejected", "_voice_id", "submit_voices",
    "_same_owner_kind", "commit_voices", "draft_voices",
    "list_submitted",
]
