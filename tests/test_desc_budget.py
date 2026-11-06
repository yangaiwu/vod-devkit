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
    c = json.loads((ROOT / "contract" / "tools.schema.json").read_text("utf-8"))
    return c["tools"]["vod_submit_voices"]["description"]


def _dsh_composed_desc() -> str:
    """从 dsh/lib/index.js 提取 vod_submit_voices 的组合后 description：
    截取 `description: '` 到 `parameters:` 的源码段，按 JS 单引号字符串
    字面量逐字符扫描求值后拼接（与运行时组合串等价；处理 \\' 与 \\\\ 转义）。"""
    src = (ROOT / "dsh" / "lib" / "index.js").read_text("utf-8")
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
    """归因口径漂移锁：dsh 壳实现只认配置绑定（无运行期 product 参数），
    description 禁止再现旧宽容口径「explicit arg → config → host identity」
    （D-dsh-install-1 实锤的约束源漂移——最陈旧一层生效）。"""
    desc = _dsh_composed_desc()
    assert "explicit arg" not in desc, "旧宽容归因口径句回流（须为部署配置权威口径）"
    assert "install/deploy time" in desc or "bound at install" in desc


def test_dsh_desc_precondition_semantics():
    """先决条件语义完整性：不构成同意 + 禁止未同意传 confirmed=true 两句齐备
    （D-consent-desc-1 拍板双要素，防截断重建时丢句）。"""
    desc = _dsh_composed_desc()
    assert "NOT consent" in desc, "缺「用户陈述不构成同意」句"
    assert "without it" in desc or "confirmed=true" in desc
