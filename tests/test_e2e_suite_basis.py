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

from e2e_suite import SUITE  # noqa: E402
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