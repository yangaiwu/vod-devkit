"""运行期归因（D-attrib-B，2026-11-11 负责人拍板 A/A/A/A）。

产品不再由安装/启动配置决定：从**用户原话**里解析产品名录别名，唯一命中才
采信；0 命中依次回落到记忆（短 TTL）与安装先验；多产品命中=歧义，一律
UNKNOWN 并保留全部命中片段（宁可人工归因，不可公开错归）。

本模块只做纯计算（索引/匹配/优先级链），不读写 runtime.json——持久化归
tools 层，便于单测零副作用。

数据源单一真源=引擎 meta（GET /external/meta）：
    productCatalog [{id,name}]  提交主键（t_vod_product）与产品名
    products       [显示名]      codearts 之类的短码由显示名大写派生

**2026-11-12 变更（引擎侧 meta 契约收紧）**：
引擎已删除 `nameAliases` / `aliases` 两个下发字段（理由：编造数据、无消费方、
且掩盖主数据问题）。别名能力改为**本地派生 + 显式品牌俗称表**，不再依赖后端下发：

    ① 规则派生（从 productCatalog 的真实名字推导，不是编造）：
       原名 / 大小写不敏感 / 去空格（"AI 开发者空间"→"AI开发者空间"）/
       括号与前缀剥离的核心词（"对象存储服务 OBS"→"OBS"）/
       中文长名里的拉丁片段（"软件开发生产线 CodeArts"→"CodeArts"）
    ② BRAND_ALIASES（下方常量）：人工确认的品牌俗称，只放**无法从表名推导**
       且用户口语高频的词（如「码道」= CodeArts 中文品牌名）。
       这是本地维护的已知清单，诚实标注为本地数据，不再假装来自后端。

`problemTypes` 同理：引擎改为 `?productId=` 按产品下发，不带参数时不含该键。
分类白名单的获取见 tools._allowed_tags(product_id)。
"""
import re

MEM_TTL = 30 * 60  # 记忆窗口：负责人拍板 P2-A（机器级 + 30 分钟）

_SNIPPET_PAD = 20
_SNIPPET_MAX = 80
_BOUNDARY = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_SHORT_ALIAS_MAX = 5

# 品牌俗称表（本地维护，2026-11-12 用户拍板方案 b）：
#   目标产品名（必须能在 canvas productCatalog 里找到，大小写不敏感匹配）→ 口语俗称列表
# 收录标准（缺一不可）：
#   ① 无法从表内登记名通过规则派生（否则交给规则）
#   ② 用户原话里高频真实出现（有真机语料支撑）
#   ③ 品牌官方称谓，不是臆造简称
# 空表也安全：派生规则独立工作，本表只是补口语盲区。
BRAND_ALIASES = {
    "CodeArts": ["码道", "华为云码道"],
}

# 派生核心词时的中文尾缀噪音（"对象存储服务 OBS" → 取拉丁 "OBS"）
_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9 ._-]*[A-Za-z0-9]|[A-Za-z]")


def _is_ascii(text: str) -> bool:
    return all(ord(c) < 128 for c in text)


def _resolve_name(raw: str, names: list) -> str:
    """别名表里的枚举键（CODEARTS）→ catalog/显示名（CodeArts）。"""
    low = str(raw or "").strip().lower()
    for n in names:
        if str(n).lower() == low:
            return str(n)
    return str(raw or "").strip()


def _derive_aliases(name: str) -> list:
    """从单个登记名派生可用别名（全部来自真实名字，非编造）。

    "AI 开发者空间"      → 原名 / 去空格 "AI开发者空间" / 拉丁 "AI"（过短，弃用）
    "对象存储服务 OBS"   → 原名 / 拉丁核心 "OBS"
    "软件开发生产线 CodeArts" → 原名 / 拉丁核心 "CodeArts"
    "DataArts Studio"    → 原名 / 去空格 / "DataArts"（拉丁首段）
    过短(<5)的拉丁别名会被 _ascii_hits 的精确大小写规则保护，但仍可能撞词，
    所以这里只保留长度>=3 的拉丁片段，且不做大写化（保留原样）。
    """
    raw = str(name or "").strip()
    if not raw:
        return []
    out = [raw]
    compact = re.sub(r"\s+", "", raw)
    if compact and compact != raw:
        out.append(compact)
    # 拉丁片段：整串是纯拉丁时取首段与全串；含中文时取最长的拉丁连续段
    runs = [m.group(0).strip() for m in _LATIN_RUN.finditer(raw)]
    runs = [r for r in runs if len(r) >= 3]
    if runs:
        out.extend(runs)
        if " " in raw and runs[0] != raw:
            head = runs[0].split()[0] if runs[0].split() else runs[0]
            if len(head) >= 3:
                out.append(head)
    # 短拉丁名的大小写变体：表里存 "Maas"、用户写 "MaaS"（真实高频差异）。
    # _ascii_hits 对 <5 字符的短别名走精确大小写，只靠原样会漏。
    # 关键限制：**全大写缩写（OBS/CCE/EIP）不生成小写变体**——用户不会把小写
    # "obs" 当产品名，而 "obs://bucket" 这类 URL/路径反会被误命中（S93 铁律）。
    # 只对非全大写的混写名（Maas/CodeArts）补变体。
    for run in list(runs):
        if len(run) <= 8 and _is_ascii(run) and run != run.upper():
            for variant in (run.lower(), run.capitalize()):
                if variant != run:
                    out.append(variant)
    # 去重、保序
    seen, uniq = set(), []
    for a in out:
        if a and a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq


def build_alias_index(meta: dict) -> list:
    """meta → 别名条目列表（按别名长度降序，长别名优先）。

    真机实锤的两个坑（2026-11-11 用线上 meta 实测）：
      ① catalog 名与展示名不一致：t_vod_product 里 MaaS 存成 "Maas"、OBS 存成
         "对象存储服务 OBS"，而 meta.products 是展示名 "MaaS"/"OBS"——只按名字
         对不齐会把同一产品拆成两条（一条有 id 一条没有）。
      ② 别名去重不能用大小写不敏感：短别名按大小写精确匹配，"MaaS" 会被
         "Maas" 顶掉。
    做法：以展示名为产品标签，用**规则派生 + BRAND_ALIASES**把多种写法桥接，
    再按 catalog id 合并成一条；去重键保留大小写（alias 原样）。

    2026-11-12：引擎已不再下发 nameAliases/aliases，改用 _derive_aliases + 本地表。
    """
    meta = meta or {}
    catalog = meta.get("catalog") or []
    products = [str(p) for p in (meta.get("products") or []) if p]
    id_by_lower = {}
    for item in catalog:
        name = str(item.get("name") or "").strip()
        if name:
            id_by_lower[name.lower()] = str(item.get("id")) if item.get("id") is not None else None

    canon: dict[str, dict] = {}  # lower(name) -> {"label","id","aliases":set(),"brand":bool}

    def _slot(name, brand):
        key = str(name).strip().lower()
        cur = canon.get(key)
        if cur is None:
            canon[key] = {"label": str(name).strip(), "id": None,
                          "aliases": set(), "brand": brand, "derived": set()}
            cur = canon[key]
        elif brand and not cur["brand"]:
            cur["label"], cur["brand"] = str(name).strip(), True
        cur["aliases"].add(str(name).strip())
        return cur

    for name in products:          # 展示名优先成为标签
        _slot(name, True)
    for item in catalog:           # catalog 名补位（无展示名时用库内名）
        if item.get("name"):
            _slot(item["name"], False)

    # ① 规则派生：每个登记名派生多种写法（去空格 / 拉丁核心词 / 大小写变体）
    # 注意：登记名「原样」不标 caseless——它由 _ascii_hits 的短别名精确规则保护
    # （OBS 不能因此变成小写 obs 而命中 "obs://bucket"，S93 铁律）。
    for slot in list(canon.values()):
        raw_label = slot["label"]
        for derived in _derive_aliases(raw_label):
            slot["aliases"].add(derived)
            if derived != raw_label:
                slot["derived"].add(derived)

    # ② 品牌俗称表：把无法从表名推导的口语词挂到目标产品上
    for target_name, colloquials in (BRAND_ALIASES or {}).items():
        slot = canon.get(str(target_name).lower())
        if slot is None:
            # 目标产品不在本次 catalog（引擎换库/改名）：别名不落地，避免指向
            # 不存在的 id。宁可丢俗称，也不产生错归。
            continue
        for word in (colloquials or []):
            if word:
                slot["aliases"].add(str(word).strip())

    # ③ 兼容：若引擎仍下发旧字段（回滚场景），继续采纳，避免双向改造期丢能力
    for key, aliases in (meta.get("nameAliases") or {}).items():
        aliases = [str(a) for a in (aliases or []) if a]
        target = canon.get(str(key).lower())
        if target is None:
            for a in aliases:
                if a.lower() in canon:
                    target = canon[a.lower()]
                    break
        if target is None:
            target = _slot(key, True)
        for a in aliases:
            target["aliases"].add(a)
        target["aliases"].add(str(key))
    for key, target_name in (meta.get("aliases") or {}).items():
        slot = canon.get(str(target_name).lower())
        if slot is None:  # 目录/展示名都没有该目标：按别名目标建槽，别丢别名
            slot = _slot(target_name, False)
        slot["aliases"].add(str(key))

    for slot in canon.values():          # 名字/别名任一命中 catalog → 拿 id
        for alias in list(slot["aliases"]) + [slot["label"]]:
            if alias.lower() in id_by_lower:
                slot["id"] = id_by_lower[alias.lower()]
                break

    merged: list = []                    # 同 id 合并（展示名那条为准）
    by_id: dict = {}
    for slot in canon.values():
        pid = slot["id"]
        if pid is not None and pid in by_id:
            by_id[pid]["aliases"] |= slot["aliases"]
            continue
        if pid is not None:
            by_id[pid] = slot
        merged.append(slot)

    entries: list = []
    seen: set = set()
    for slot in merged:
        for alias in slot["aliases"]:
            key = (slot["label"].lower(), alias)  # 大小写敏感：保留 MaaS/Maas 两种写法
            if not alias or key in seen:
                continue
            seen.add(key)
            entries.append({"product": slot["label"], "id": slot["id"], "alias": alias,
                            # 派生写法允许大小写不敏感（见 _ascii_hits 说明）
                            "caseless": alias in (slot.get("derived") or set())})
    entries.sort(key=lambda e: len(e["alias"]), reverse=True)
    return entries


def _ascii_hits(text: str, alias: str, caseless: bool = False) -> list:
    """拉丁别名：词边界 + 大小写策略（短别名精确大小写）。

    caseless=True 用于**从登记名派生**的写法（如表里 "Maas" 派生的 "MaaS"）：
    这类变体本就来自同一登记名，允许大小写不敏感，否则用户写 "MaaS" 会漏。
    手写简称（meta 下发/品牌表）仍走精确匹配，避免 obs≠OBS 之类误伤。
    """
    exact_case = (not caseless) and len(alias) < _SHORT_ALIAS_MAX
    hay = text if exact_case else text.lower()
    needle = alias if exact_case else alias.lower()
    out: list = []
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return out
        j = i + len(needle)
        ok_before = i == 0 or hay[i - 1] not in _BOUNDARY
        ok_after = True
        if j < len(hay):
            nxt = hay[j]
            if nxt in _BOUNDARY:
                ok_after = False
            elif nxt == "." and j + 1 < len(hay) and hay[j + 1].isalnum():
                ok_after = False  # codearts.yaml 这类文件名不是产品名
        if ok_before and ok_after:
            out.append((i, j))
        start = i + 1


def _snippet(text: str, start: int, end: int) -> str:
    lo = max(0, start - _SNIPPET_PAD)
    hi = min(len(text), end + _SNIPPET_PAD)
    frag = " ".join(text[lo:hi].split())
    return frag[:_SNIPPET_MAX]


def match_products(text: str, index: list) -> list:
    """在用户原话里找产品别名 → 命中列表（长别名优先，重叠不重复计）。

    [{"product","id","alias","start","end","snippet"}]
    """
    text = str(text or "")
    if not text or not index:
        return []
    taken: list = []
    hits: list = []
    for entry in index:
        alias = entry["alias"]
        spans = _ascii_hits(text, alias, entry.get("caseless", False)) if _is_ascii(alias) else [
            (m.start(), m.end()) for m in re.finditer(re.escape(alias), text)]
        for start, end in spans:
            if any(not (end <= s or start >= e) for s, e in taken):
                continue  # 被更长别名覆盖（「软件开发生产线 CodeArts」不吃子串）
            taken.append((start, end))
            hits.append({"product": entry["product"], "id": entry["id"],
                         "alias": alias, "start": start, "end": end,
                         "snippet": _snippet(text, start, end)})
    hits.sort(key=lambda h: h["start"])
    return hits


def _group(hits: list) -> dict:
    """按产品合并（同产品多别名命中取最长片段作证据）。"""
    grouped: dict = {}
    for h in hits:
        key = h["product"].lower()
        cur = grouped.get(key)
        if cur is None or len(h["alias"]) > len(cur["alias"]):
            grouped[key] = dict(h)
    return grouped


def resolve_id(product: str, meta: dict) -> str:
    """产品名/短码/主键 → 提交值：目录命中给 id，否则规范名（引擎 name 兼容通道）。"""
    product = str(product or "").strip()
    if not product:
        return ""
    if product.isdigit():
        return product
    idx = build_alias_index(meta)
    low = product.lower()
    for entry in idx:
        if entry["product"].lower() == low and entry["id"]:
            return str(entry["id"])
    for entry in idx:
        if entry["alias"].lower() == low and entry["id"]:
            return str(entry["id"])
    return product


def attribute(text: str, meta: dict, memory: dict | None = None,
              binding: str | None = None, ttl: int = MEM_TTL,
              now: float | None = None) -> dict:
    """归因优先级链：字面证据 > 记忆 > 安装先验 > UNKNOWN。

    返回 {"product": 提交值或 None, "source": user_input|memory|install_binding|unknown,
          "evidence": [{"product","alias","snippet","reason"?}]}
    """
    import time
    now = time.time() if now is None else now
    hits = match_products(text, build_alias_index(meta))
    grouped = _group(hits)

    if len(grouped) == 1:
        hit = next(iter(grouped.values()))
        return {"product": str(hit["id"]) if hit["id"] else hit["product"],
                "productName": hit["product"], "source": "user_input",
                "evidence": [{"product": hit["product"], "alias": hit["alias"],
                               "snippet": hit["snippet"]}]}

    if len(grouped) > 1:
        # P1-A：歧义一律 UNKNOWN，全部命中留痕（人工归因要有上下文）
        return {"product": None, "productName": None, "source": "unknown",
                "evidence": [{"product": h["product"], "alias": h["alias"],
                               "snippet": h["snippet"], "reason": "ambiguous"}
                              for h in hits]}

    mem = memory or {}
    if mem.get("product") and now - float(mem.get("at") or 0) <= ttl:
        return {"product": str(mem["product"]),
                "productName": mem.get("productName") or None, "source": "memory",
                "evidence": [{"product": mem.get("productName") or str(mem["product"]),
                               "alias": mem.get("alias"), "snippet": mem.get("snippet"),
                               "at": mem.get("at"), "reason": "memory"}]}

    if binding:
        return {"product": resolve_id(binding, meta), "productName": str(binding),
                "source": "install_binding", "evidence": []}

    return {"product": None, "productName": None, "source": "unknown",
            "evidence": [{"reason": "no-evidence"}]}


def remember_if_evidenced(result: dict) -> dict | None:
    """只有「字面证据唯一命中」的归因才写记忆（S100：歧义/无证据不污染）。"""
    if result.get("source") != "user_input":
        return None
    ev = (result.get("evidence") or [{}])[0]
    import time
    return {"product": result.get("product"),
            "productName": ev.get("product") or result.get("productName"),
            "alias": ev.get("alias"), "snippet": ev.get("snippet"),
            "at": int(time.time())}