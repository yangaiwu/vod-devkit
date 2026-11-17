"""S190：行为回归用例集合必须带「自指」——否则正向用例测不到提交链（D-attrib-binding-1）。

实测（2026-11-17，glm-5.3-flash 下的 C1）：宿主确实走完了工具链
（`vod_search_products` → `vod_auth_ensure`），然后停在归因
「你说的『批量导入』是哪个产品的功能？」——**这是纪律要求的正确行为**：安装绑定先验只在原话
出现自指（「这个产品/你们家/本平台…」）时才生效，缺自指就该问一次、不许裸提交。

问题是套件基准：C1/C4/C5 的期望是「确认→提交→逐字收录」，但提示词里没有自指，于是按纪律
永远不会提交——用例在验一个纪律禁止的结果。C2/C3 期望不提交，必须保持无自指（否则会把
「该问却提交」误判成合规）。

判据=正向用例（expect 为 submit_consent / single_row）提示词必须含 attribution.SELF_REFERENCE
中的任一词；负向用例（no_submit）必须不含。这样以后改提示词不会静默丢掉自指、也不会让负向
用例失去「不该提交」的前提。
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_REPO / "src"))

from e2e_suite import SUITE, expected_row_count  # noqa: E402
from vod_mcp.attribution import SELF_REFERENCE  # noqa: E402


def _positive(case) -> bool:
    return case.get("expect") in ("submit_consent", "single_row")


def _self_ref(text: str) -> str | None:
    return next((w for w in SELF_REFERENCE if w in text), None)


def test_s190_positive_cases_carry_self_reference():
    """正向用例（要验提交链）必须带自指，否则安装绑定先验不生效、纪律要求先问产品。"""
    for case in SUITE:
        if not _positive(case):
            continue
        assert _self_ref(case["prompt"]), (
            f"{case['id']} 缺自指（{SELF_REFERENCE}）：按 D-attrib-binding-1 宿主要先问产品，"
            f"该用例的『提交』期望永远达不到")


def test_s190_negative_cases_are_not_explicit_consent():
    """负向用例（期望不提交）不得被判成「明确同意」——否则合规口径被破坏。

    注意 C3 是带自指的（「AIShell 这个产品…」），它的前提是**没有抱怨词**（提及≠抱怨），
    不是「没有自指」；所以不变量只钉「不是明确同意」，别把自指一刀切禁掉。
    """
    from e2e_behavior import classify_prompt
    for case in SUITE:
        if _positive(case):
            continue
        assert classify_prompt(case["prompt"]) != "explicit_consent", (
            f"{case['id']} 被判成明确同意，但它的期望是不提交")


def test_s190_self_reference_table_is_the_single_source():
    """自指词表只有一份（attribution.SELF_REFERENCE），用例文件不许自带清单。"""
    src = (_SCRIPTS / "e2e_suite.py").read_text(encoding="utf-8")
    assert "SELF_REFERENCE" not in src, "用例文件不该复制自指词表；需要校验就用本用例"
    assert "你们家" in SELF_REFERENCE

# --- S205：要验"落库"的用例必须带明确提交指令，否则模型按纪律只建草稿 ------------
# 实测（2026-11-17，0.5.32+S204 装机）C1：「帮我记录反馈：……」→ 模型归因正确（从 search_products
# 的 installBinding 拿到 CodeArts）、建了草稿、内容逐字，然后停在「确认提交吗？」。
# 那是**纪律要求**的二次确认（D-resume-commit-1 的另一面）："记录/反馈"只算承接意愿。
# 但 C1/C4 的期望是落库（反截断/单条），于是用例永远达不到——第三次用例基准问题（前两次 S190/S205 同源）。
_SUBMIT_MARKERS = ("提交", "收录", "上报")


def test_s205_cases_expecting_rows_carry_explicit_submit():
    for case in SUITE:
        rows = expected_row_count(case)
        if rows == 0:
            continue
        head = case["prompt"].split("{content_start}")[0]
        assert any(m in head for m in _SUBMIT_MARKERS), (
            f"{case['id']} 期望落库，但提示词没有明确提交指令（只写「记录/反馈」时纪律要求二次确认）："
            f"{head!r}")


# --- S206：嵌套锚点按最长匹配归属（顺序依赖的 substring 匹配是错归属源头）--------
# 实测：把 C5 前缀写成「请帮我提交反馈：」后，C5 的行内容里包含 C1 的锚点「帮我提交反馈」，
# 而 case_by_anchor 按 SUITE 顺序返回第一个命中 → C5 的行被判成 C1（归属错乱会让改写/回显
# 桶记到别的用例上）。判据：命中多个锚点时按最长锚点归属，不按列表顺序。
def test_s206_nested_anchor_resolves_to_longest_match():
    from e2e_suite import SUITE, case_by_anchor, render

    c5 = next(x for x in SUITE if x["id"] == "C5-baseline-consent")
    row = render(c5, "11-17 17:00:00")
    assert case_by_anchor(row)["id"] == "C5-baseline-consent", "嵌套锚点必须按最长归属"

    nested = [(a["id"], b["id"]) for a in SUITE for b in SUITE
              if a is not b and a["anchor"] and b["anchor"] and a["anchor"] in b["anchor"]]
    for inner_id, outer_id in nested:
        outer = next(x for x in SUITE if x["id"] == outer_id)
        assert case_by_anchor(render(outer, "11-17 17:00:00"))["id"] == outer_id, \
            f"{inner_id} 的锚点嵌在 {outer_id} 里，归属被抢"


# --- S207：幂等盐必须落在原话区之外（末尾），否则判据把盐当改写 ----------------------
# 实测（2026-11-17，C1 已落库）：引擎 content 是「11-17 17:55:40试着用你们家的批量导入功能…」，
# 而比对基准是 content_start 之后的「试着用你们家的…」→ 第 1 字起不同，判成"改写"。
# 根因=模板把 {t} 放在 {content_start} 之前：模型把紧挨正文的时间戳自然当成原话的一部分。
# 盐对引擎去重本来就没作用（voiceId=f(source,content,调用级nonce)），它只需要区分轮次，
# 所以放到**提示词末尾**——原话区保持纯正文。
def test_s207_salt_sits_outside_the_verbatim_region():
    for case in SUITE:
        tpl = case["prompt"]
        if "{content_start}" not in tpl:
            continue
        before = tpl.split("{content_start}")[0]
        assert "{t}" not in before, f"{case['id']} 的盐出现在原话起点之前：{before!r}"


def test_s207_rendered_ref_starts_with_user_words():
    from e2e_suite import render_with_offset
    for case in SUITE:
        text, off = render_with_offset(case, "11-17 17:00:00")
        if off == 0:
            continue
        ref = text[off:]
        assert not ref.startswith("11-17 "), f"{case['id']} 的原话区以盐开头：{ref[:30]!r}"


# --- S217：回显判据必须剥轮次盐（否则正常行为被记违规）-----------------------------
# 实测（2026-11-17 评审）：盐挪到原话末尾后，模型把它当插注元数据丢掉是**正常行为**，
# 但判据基准 verbatim_full/ref 仍含「（MM-DD HH:MM:SS）」→ 自然回显被判 incomplete/missing，
# 这两个桶喂熔断（记的是产品违规，实际是判据把盐当原话）。
def test_s217_echo_basis_has_no_salt():
    from e2e_suite import SUITE, render_with_offset, strip_salt_offset
    for cid in ("C1", "C4", "C5"):
        case = next(c for c in SUITE if c["id"].startswith(cid))
        prompt, start = render_with_offset(case, "11-17 18:20:00")
        assert "18:20:00" in prompt, "前提：盐确实渲染进了提示词"
        assert "18:20:00" not in strip_salt_offset(prompt, start), f"{cid} 的判据基准仍含盐"


def test_s217_natural_echo_is_ok():
    """模型只丢掉末尾括号时间戳（原话一字不差）→ 必须判 ok，不许 incomplete/missing。"""
    from e2e_behavior import echo_status
    from e2e_suite import SUITE, render_with_offset, strip_salt_offset

    for cid, window in (("C1", 60), ("C4", 60), ("C5", 60)):
        case = next(c for c in SUITE if c["id"].startswith(cid))
        prompt, start = render_with_offset(case, "11-17 18:20:00")
        full = strip_salt_offset(prompt, start)
        reply = "已收录原话：" + full
        status = echo_status(reply, full, full[:window])
        assert status == "ok", f"{cid} 自然回显被判 {status}"
