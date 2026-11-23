"""D-desc-budget-1：采集 description 截断预算门禁。

业界实锤（2026-11-06 核验）：宿主对工具/技能 description 普遍存在硬性截断——
dsh 固定 500 字符窗口（dsh-tool-skill 默认值同源）、Codex 5440 字符硬预算
（openai/codex#24299：119 技能 103 个被截断，平均仅剩 232 字符）、OpenCode
共用 2000 行/50KiB 通用截断。被截断的先决条件=确认纪律对模型不可见。

本门禁锁死两个不变量：
  B1 先决条件（同意前置）必须落在最严截断窗口（500 字符）之内——超过即
     在 dsh 上对自动路由不可见；
  B2 description 总长有上限（防无界增长挤占宿主预算）。

载体两处：contract/tools.schema.json（python/MCP 单一事实源）与
dsh/lib/index.js（node 手同步双载体——漂移已实锤过，须双测）。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRECONDITION_MARK_CN = "先决条件"
PRECONDITION_MARK_EN = "PRECONDITION"
CONSENT_MARKS = ("confirmed=true", "confirmed=true")  # 同意闸出现的标志串
DESC_LEN_CAP = 1500        # B2：总长上限（现状 665，留升级余量防挤占宿主预算）
TRUNC_WINDOW = 500         # B1：最严截断窗口（dsh 固定 500 字符）


def _contract_desc() -> str:
    c = json.loads((ROOT / "assets" / "contract" / "tools.schema.json").read_text("utf-8"))
    return c["tools"]["vod_submit_voices"]["description"]


def _dsh_composed_desc() -> str:
    """从 dsh/lib/index.js 提取 vod_submit_voices 的组合后 description：
    截取 `description: '` 到 `parameters:` 的源码段，按 JS 单引号字符串
    字面量逐字符扫描求值后拼接（与运行时组合串等价；处理 \\' 与 \\\\ 转义）。"""
    src = (ROOT / "packages" / "dsh" / "lib" / "index.js").read_text("utf-8")
    start = src.index("description: '") + len("description: '")
    end = src.index("parameters: buildParameters", start)
    seg, out, i, in_str = src[start:end], [], 0, True  # start 已跳过起始引号
    while i < len(seg):
        ch = seg[i]
        if in_str:
            if ch == "\\":
                out.append(seg[i + 1])
                i += 2
                continue
            if ch == "'":
                in_str = False
                out.append("\n")  # JS 相邻字符串拼接处的分段标记（不计入预算判定的语义位置无关紧要）
                i += 1
                continue
            out.append(ch)
        elif ch == "'":
            in_str = True
        i += 1
    return "".join(out)


def _assert_budget(desc: str, pre_mark: str, carrier: str, pre_limit: int):
    assert len(desc) <= DESC_LEN_CAP, \
        f"{carrier} description 总长 {len(desc)} 超上限 {DESC_LEN_CAP}（B2，防挤占宿主截断预算）"
    pre = desc.find(pre_mark)
    assert pre != -1, f"{carrier} description 缺先决条件标记（确认纪律前置）"
    assert pre < pre_limit, \
        f"{carrier} 先决条件位于第 {pre} 字（须 <{pre_limit} 话术前置）"
    gate = min((desc.find(m) for m in CONSENT_MARKS if desc.find(m) != -1),
               default=-1)
    assert 0 <= gate < TRUNC_WINDOW, \
        f"{carrier} 同意闸（confirmed=true）位于第 {gate} 字——超出 {TRUNC_WINDOW} " \
        f"字符截断窗口即在 dsh 上对自动路由不可见（B1）"


def test_contract_desc_survives_truncation_budget():
    _assert_budget(_contract_desc(), PRECONDITION_MARK_CN, "contract", 60)


def test_dsh_desc_survives_truncation_budget():
    # 英文壳前置阈值放宽到 100：前导一句能力定位（~73 字）为触发上下文所需
    _assert_budget(_dsh_composed_desc(), PRECONDITION_MARK_EN, "dsh", 100)


def test_dsh_desc_no_stale_permissive_attribution():
    """归因口径漂移锁（D-attrib-B → D-product-ask-1，2026-11-18 更新）：dsh 壳归因已改
    运行期字面解析，且 S243 起缺产品时**先问一次**（不再一味禁问）。本锁防两种回退：
    ①宽容链「explicit arg → config → host identity」（D-dsh-install-1 实锤）
    ②「绑定在安装期且无运行期解析」（D-attrib-B 前的旧口径）
    以及防「禁造产品名」这句被压缩掉——它现在与「问一次」并存，不是互相取消。"""
    desc = _dsh_composed_desc()
    assert "explicit arg" not in desc, "旧宽容归因口径句回流"
    assert "install/deploy time" not in desc and "bound at install" not in desc, \
        "旧「安装期绑定」口径句回流（须为运行期字面解析口径）"
    assert "user's own words" in desc, "缺「来自用户原话」口径句"
    # 2026-11-18 口径：问一次（needsProductAsk）在前，禁造产品名在后，两句必须同时在场
    assert "needsProductAsk" in desc, "缺「缺产品先问一次」口径句（D-product-ask-1）"
    assert "NEVER invent a product" in desc, "缺禁造产品名句"


def test_dsh_desc_precondition_semantics():
    """先决条件语义完整性：不构成同意 + 禁止未同意传 confirmed=true 两句齐备
    （D-consent-desc-1 拍板双要素，防截断重建时丢句）。"""
    desc = _dsh_composed_desc()
    assert "NOT consent" in desc, "缺「用户陈述不构成同意」句"
    assert "without it" in desc or "confirmed=true" in desc


# ── B3：技能全文预算门禁（dsh/Python 双向 retrieve_skill 硬截断）──────────
#
# 为什么需要这道门禁（2026-11-18 实测立项）：
#   dsh 是唯一没有 MCP 的宿主，纪律/话术全靠 vod_retrieve_skill 拉取 SKILL.md；
#   而两侧 retrieve 实现都会在超限时**静默截断尾部**：
#     packages/dsh/lib/index.js:749      const SKILL_CAP = 12000;
#     src/vod_mcp/skills_registry.py:29  _BODY_CAP = 12000
#   references/ 在 dsh 面不可达（只 readFileSync(SKILL.md)），所以纪律必须全在
#   SKILL.md 内且必须落在 cap 之内——否则尾部的隐私红线/同意闸会被物理截掉。
#
# 目标定为 11950 而非 12000：留 50 字余量，避免任何一次微调即触线。
SKILL_MD = ROOT / "assets" / "skills" / "vod-feedback-collect" / "SKILL.md"
RETRIEVE_CAP = 12000       # 两侧 retrieve 实现的上限（dsh SKILL_CAP / py _BODY_CAP）
SKILL_LEN_TARGET = 11950   # 留 50 字余量


def test_skill_md_fits_retrieve_cap():
    """SKILL.md 必须装得下 retrieve_skill 的 12000 字上限，否则尾部纪律静默丢失。"""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert len(text) <= SKILL_LEN_TARGET, (
        f"SKILL.md {len(text)} 字超出目标 {SKILL_LEN_TARGET}"
        f"（retrieve cap {RETRIEVE_CAP}）——超出部分在 dsh/Python 面会被静默截断")


def test_skill_md_tail_disciplines_survive_cap():
    """尾部关键纪律必须落在 cap 内（回归锁：曾因文件增长被截掉全部 6 条）。

    这 6 条是隐私红线/同意闸第二层/防伪造/对账——被截断=安全约束对模型不可见。
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    tail_disciplines = [
        "逐次确认：每批提交前用户点头一次",   # 同意闸第二层
        "来源标记由插件自动注入",             # 防伪造
        "content 是用户原话，agent 不加",     # 原话红线
        "不提交用户身份信息",                 # 隐私红线
        "voiceId 是回执主键",                 # 对账
        "单批上限 50 条",                     # 边界
    ]
    for item in tail_disciplines:
        pos = text.find(item)
        assert pos != -1, f"技能正文缺关键纪律：{item}"
        assert pos < RETRIEVE_CAP, (
            f"「{item}」位于第 {pos} 字，超出 retrieve cap {RETRIEVE_CAP}——"
            f"dsh 面不可见")


def test_retrieve_cap_constants_in_sync():
    """两侧 retrieve cap 必须相等（一改一漏会造成表面通、端上仍截断）。"""
    import re as _re
    dsh = (ROOT / "packages" / "dsh" / "lib" / "index.js").read_text(encoding="utf-8")
    py = (ROOT / "src" / "vod_mcp" / "skills_registry.py").read_text(encoding="utf-8")
    m_dsh = _re.search(r"SKILL_CAP\s*=\s*(\d+)", dsh)
    m_py = _re.search(r"_BODY_CAP\s*=\s*(\d+)", py)
    assert m_dsh and m_py, "未找到 cap 常量（dsh SKILL_CAP / py _BODY_CAP）"
    assert m_dsh.group(1) == m_py.group(1), (
        f"两侧 retrieve cap 不一致：dsh={m_dsh.group(1)} py={m_py.group(1)}")
    assert int(m_dsh.group(1)) >= SKILL_LEN_TARGET, (
        f"cap {m_dsh.group(1)} 低于目标 {SKILL_LEN_TARGET}")
