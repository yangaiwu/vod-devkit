"""S237：面向用户的用语纪律（禁词表）——模型实测会对用户说"归因"。

真机（2026-11-18，codex 宿主 + 0.5.38）：C3/C5 两条被 e2e 判「回复外露机制词：['归因']」。
技能里原有「不向用户解释机制（归因/白名单/配额）」，但那是**职责边界**（别科普），
没写成"回答里禁用这些词 + 换成什么说法"，模型照旧说"已按 X 归因"。

落法：技能加禁词表 + 三条替换口径；e2e 禁词表同步扩充（令牌/幂等/引擎/草稿/主键/配额/名单）。
门禁锁两件事：技能有这张表且含替换示例；判定函数对这些词真能报出来、且不误伤回执话术。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import e2e_suite as es  # noqa: E402

SKILL = ROOT / "assets" / "skills" / "vod-feedback-collect" / "SKILL.md"


def test_s237_skill_has_banned_word_list_and_replacements():
    text = SKILL.read_text(encoding="utf-8")
    assert "禁词表" in text and "面向用户的用语纪律" in text
    for w in ("归因", "白名单", "令牌", "幂等", "引擎", "草稿", "主键"):
        assert w in text, f"禁词表缺 {w}"
    assert "产品归属：" in text, "缺替换口径示例"
    assert "这不在反馈功能范围内" in text, "缺追问处置话术"


def test_s237_suite_forbidden_words_cover_mechanism_terms():
    want = {"归因", "白名单", "令牌", "幂等", "引擎", "草稿", "主键", "配额", "名单", "voiceid"}
    assert want <= set(es.FORBIDDEN_REPLY_WORDS)


def test_s237_reply_leaks_flags_mechanism_words_and_spares_required_echo():
    leaks = es.reply_leaks("已按 CodeArts 归因，草稿已签发令牌，进幂等域")
    assert {"归因", "令牌", "幂等"} <= set(leaks)
    ok = es.reply_leaks("产品归属：CodeArts\n已收录原话：你们家网页卡，回复也慢。")
    assert ok == [], ok


def test_s237_required_echo_prefix_is_not_a_banned_word():
    """回执必需话术不能被禁词表误伤（否则每条正向用例都会红）。"""
    assert not any(w in es.REQUIRED_ECHO_PREFIX.lower() for w in es.FORBIDDEN_REPLY_WORDS)