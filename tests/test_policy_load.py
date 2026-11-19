"""ARCH-ERR-01 / ARCH-ERR-02：护栏装载失败必须 deny，不许打死 server（2026-11-19 五维走查 P0）。

背景（台账 ARCH-ERR-01/02，实测复现）：
- `policy.load_policy()` 裸 `open()+json.load()`，`guardrails.check()` 在 `server.handle`
  的 `try` 之外，`server.main` 主循环的 `handle(message)` 也无 try ⇒ policy.json 被删/
  截断/手改坏 ⇒ 任意 `tools/call` 抛未捕获异常 ⇒ **stdio 进程退出**（宿主只见 MCP 掉线）。
- 规则消费处直接下标访问（`rule["match"]` / `r["severity"]` / `m["regex"]`），少一个字段
  报的是 `AttributeError`/`KeyError` 而不是"规则非法"。

纪律（fail-closed）：护栏不可载入 = 拒绝执行，不是"整体不可用"，更不是"放行"。
本文件是这三条路的回归锁。
"""
import json

import pytest

from vod_mcp import guardrails, policy

_CORRUPT = '{"rules": ['                      # 半截 JSON（人工编辑/掉电的典型形态）


@pytest.fixture()
def broken_policy(tmp_path, monkeypatch):
    """把 _POLICY_PATH 指到坏文件；返回该路径，调用方自行写内容。"""
    p = tmp_path / "policy.json"
    monkeypatch.setattr(policy, "_POLICY_PATH", p)
    return p


def test_corrupt_policy_denies_instead_of_raising(broken_policy):
    """半截 JSON ⇒ deny + -32017，且不抛异常（现状：JSONDecodeError 直穿）。"""
    broken_policy.write_text(_CORRUPT, encoding="utf-8")
    verdict, msg, code = guardrails.check("vod_submit_voices", {"voices": []})
    assert verdict == "deny", f"坏 policy 必须 fail-closed，实际 {verdict}"
    assert code == -32017, f"坏 policy 要用专用码 -32017，实际 {code}"
    assert "policy" in msg.lower() or "护栏" in msg, msg


def test_missing_policy_denies_with_actionable_message(broken_policy):
    """文件不存在（被删）同样 fail-closed，消息要指向可执行动作。"""
    assert not broken_policy.exists()
    verdict, msg, code = guardrails.check("vod_submit_voices", {"voices": []})
    assert (verdict, code) == ("deny", -32017), (verdict, code)
    assert "重启" in msg or "修复" in msg, f"消息缺可执行动作：{msg}"


def test_rule_schema_violation_names_rule_id(broken_policy):
    """规则缺 severity ⇒ 报"规则非法"并点名 rule id，不是 AttributeError/KeyError。"""
    broken_policy.write_text(json.dumps({"rules": [
        {"id": "bad-rule-42", "message": "m",
         "match": {"tool": "vod_submit_voices", "param": "voices"}},
    ]}), encoding="utf-8")
    verdict, msg, code = guardrails.check("vod_submit_voices", {"voices": []})
    assert (verdict, code) == ("deny", -32017), (verdict, code)
    assert "bad-rule-42" in msg, f"必须点名违规规则 id，实际：{msg}"


def test_text_rule_without_regex_is_rejected(broken_policy):
    """field=text 但没有 regex ⇒ 装载期就拒（现状：调用时 KeyError 'regex'）。"""
    broken_policy.write_text(json.dumps({"rules": [
        {"id": "no-regex", "severity": "deny", "message": "m", "match": {"field": "text"}},
    ]}), encoding="utf-8")
    verdict, msg, code = guardrails.check("vod_submit_voices", {"voices": []})
    assert (verdict, code) == ("deny", -32017), (verdict, code)
    assert "no-regex" in msg, msg


def test_shipped_policy_still_passes_validation():
    """资产里的 policy.json 必须过 schema 校验（否则新版护栏把所有提交都拒了）。"""
    pol = policy.try_load_policy()
    assert not pol.get("broken"), f"随包 policy.json 未过校验：{pol.get('broken')}"
    assert len(pol["rules"]) >= 4, pol["rules"]


def test_deny_rule_still_denies_after_validation(broken_policy):
    """校验不许改变既有语义：超批量仍 deny（不是被 -32017 顶掉）。

    ⚠️ 期望码从 -32010 改为 -32024（2026-11-19，fix-list 问题 3）：护栏四类 deny 曾共用
    -32010（"缺产品"），把"越权/超范围"报成"请补产品"；现按命中规则的 category 分派。
    注意本用例的 policy **没有 category 字段**，走 `_code_for_hits` 的兜底档 -32024。
    """
    broken_policy.write_text(json.dumps({
        "version": "0.1.0", "maxVoicesPerSubmit": 2,
        "rules": [{"id": "limit", "severity": "deny", "message": "单批超上限",
                   "match": {"tool": "vod_submit_voices", "param": "voices",
                             "gt": "maxVoicesPerSubmit"}}],
    }), encoding="utf-8")
    verdict, msg, code = guardrails.check("vod_submit_voices",
                                          {"voices": [{"content": "a"}, {"content": "b"},
                                                      {"content": "c"}]})
    assert (verdict, code) == ("deny", -32024), (verdict, code)
    assert code != -32017, "校验失败态（-32017）不该覆盖正常的 deny 规则"
    assert code != -32010, "护栏侧不得再产出「缺产品」码"
    assert "单批超上限" in msg, msg


def test_policy_013_is_explained():
    """新码 -32017 必须进 explain 表（否则 test_explain_codes 的 raise 点 ⊆ 表 会红）。"""
    from vod_mcp import diagnose
    got = diagnose.explain("-32017")
    assert got["known"] and got["cause"] and got["action"], got