"""D-followup-impl-2：复现/预期追问补充透传回归锁。

引擎承载（V20261106110000003 repro_steps/expected_behavior + I21/I22 渲染）已就绪；
本文件锁插件侧三件：①仅 trim 非空才含键（未追问/答"没有"=键集合与旧流程完全一致）
②超长按引擎同口径截 2000 ③content 原话不受追问污染（逐字一致）。
固定问句逐字锁防话术漂移（话术固定化约束②）。
"""
import json

import pytest

from vod_mcp import tools

FIXED_QUESTION = ("方便的话，补充一下遇到这个问题时的操作步骤或期望的表现吗？"
                  "不方便回复\"没有\"，我直接提交。")


@pytest.fixture
def hoard_capture(monkeypatch):
    """桩引擎：捕获囤积端点请求体，回执单条 voiceId。"""
    captured = {}

    def fake_http(method, path, body=None, timeout=30, base=None, key=None):
        if path.endswith("/external/voices"):
            captured["body"] = body
            return {"code": 200, "voiceIds": ["ext_vod-agent_t1"]}
        if path.endswith("/external/token"):
            return {"code": 200, "message": "令牌已签发",
                    "data": {"token": "anon-token-xyz", "tier": "anonymous"}}
        return {}

    monkeypatch.setattr(tools, "JAVA_KEY", "k-test")
    monkeypatch.setattr(tools, "_http", fake_http)
    return captured


def _submit(tools, voices):
    return tools.submit_voices({"voices": voices, "product": "codearts",
                                "confirmed": True},
                               client_info={"name": "t"})


def test_followup_fields_passthrough(hoard_capture):
    """双字段非空 → 透传+trim；content 原话逐字不回流。"""
    out = _submit(tools, [{"content": "补全响应有点慢，希望优化一下",
                           "reproSteps": "  新建会话输入长文本时卡住  ",
                           "expectedBehavior": "补全不阻塞输入"}])
    assert out["accepted"] == 1
    hv = hoard_capture["body"]["voices"][0]
    assert hv["reproSteps"] == "新建会话输入长文本时卡住"
    assert hv["expectedBehavior"] == "补全不阻塞输入"
    assert hv["content"] == "补全响应有点慢，希望优化一下"  # 原话红线：追问不污染


def test_followup_absent_keys_unchanged(hoard_capture):
    """未追问/未答 → 载荷键集合与旧流程完全一致（字节级/键集合断言，非空值断言）。"""
    out = _submit(tools, [{"content": "补全响应有点慢，希望优化一下"}])
    hv = hoard_capture["body"]["voices"][0]
    assert set(hv.keys()) == {"title", "content"}, f"键集合漂移: {sorted(hv.keys())}"


def test_followup_declined_or_blank_omitted(hoard_capture):
    """答"没有"（话术层挡后的兜底）/空白/None → 两键均不出现。"""
    out = _submit(tools, [{"content": "补全响应有点慢，希望优化一下",
                           "reproSteps": "没有", "expectedBehavior": "   "}])
    hv = hoard_capture["body"]["voices"][0]
    assert "reproSteps" not in hv and "expectedBehavior" not in hv
    assert hv["content"] == "补全响应有点慢，希望优化一下"


def test_followup_oversize_truncated_engine_aligned(hoard_capture):
    """超 2000：按引擎同口径截断（非报错非丢弃），截断值不得混入 content。"""
    long_text = "步" * 2500
    out = _submit(tools, [{"content": "补全响应有点慢", "reproSteps": long_text}])
    hv = hoard_capture["body"]["voices"][0]
    assert len(hv["reproSteps"]) == 2000
    assert hv["content"] == "补全响应有点慢"


def test_fixed_question_verbatim_in_contract():
    """话术固定化：固定问句必须逐字在契约描述中，且恰好出现一次。"""
    c = json.load(open("contract/tools.schema.json"))
    desc = c["tools"]["vod_submit_voices"]["description"]
    assert desc.count(FIXED_QUESTION) == 1, "固定问句必须逐字出现且仅一次"
    # 数据分层纪律句在位
    assert "禁回填 content" in desc
    assert "禁止第二轮追问" in desc


def test_followup_two_phase_draft_carries_fields(tmp_path, monkeypatch):
    """两段式：draft 暂存追问字段（commit 复用 payload 原样上送）；
    拒答词集在 draft 路径同样拦截；content 原话不污染。
    HOME/仓内 runtime 隔离：_runtime_path 指 tmp（对齐 test_two_phase）。"""
    import hashlib, json as _json
    monkeypatch.setattr(tools, "_runtime_path", lambda: tmp_path / "runtime.json")
    monkeypatch.setattr(tools, "JAVA_KEY", "k-test")
    out = tools.draft_voices(
        {"voices": [
            {"content": "导出卡住", "reproSteps": "  点导出后转圈  ", "expectedBehavior": "应出文件"},
            {"content": "搜索不准", "reproSteps": "没有"},
         ], "product": "codearts"},
        client_info={"name": "t"})
    fresh = tools._runtime_cfg()
    store = fresh.get(tools._DRAFT_KEY) or {}
    d = store[out["draftId"]]
    v0, v1 = d["payload"]["voices"]
    assert v0["reproSteps"] == "点导出后转圈" and v0["expectedBehavior"] == "应出文件"
    assert "reproSteps" not in v1, "拒答词集在 draft 路径同样拦截"
    assert v0["content"] == "导出卡住" and v1["content"] == "搜索不准"
    # 载荷 sha 与暂存内容一致（commit 防调包链不断）
    payload = d["payload"]
    assert hashlib.sha256(_json.dumps(payload, sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest() == d["payloadSha256"]


def test_followup_fields_helper_single_source():
    """重构回归锁：单源 _followup_fields 的词集/截断/空白语义
    （submit 与 draft 双路径共用本函数，行为断言见上两路径用例）。"""
    out = tools._followup_fields({"reproSteps": " 没有了 ", "expectedBehavior": " 应出文件 "})
    assert out == {"expectedBehavior": "应出文件"}  # "没有了"含拒答词但非精确命中——精确词集语义
    assert tools._followup_fields({"reproSteps": "没有"}) == {}
    assert tools._followup_fields({"expectedBehavior": "x" * 2500}) == {"expectedBehavior": "x" * 2000}
    assert tools._followup_fields({}) == {}


def test_followup_skill_judgment_block_locked():
    """S64-S66 话术固定化补强（2026-11-08 负责人确认）：追问触发判定块必须
    在 SKILL 双副本逐字在位（三层判定=可执行规则，禁 agent 自由裁量）。
    四行为用例（已有现象不问/泛化抱怨问一次/未答引导补充问一次/答没有直接
    提交）属 agent 行为，文本锁钉死判定规则本身防漂移。"""
    blocks = []
    for p in ("skills/vod-feedback-collect/SKILL.md",
              "plugins/vod-devkit/skills/vod-feedback-collect/SKILL.md"):
        s = open(p, encoding="utf-8").read()
        blocks.append(s)
        # 触发前置
        assert "仅在用户明确说" in s and "至多一次" in s and "不得与引导补充连续两轮问" in s
        # 跳过条件（已并入 content 不再触发 + 不上送；不回溯摘入=来源唯一）
        assert "不触发固定追问" in s and "不回溯摘入新字段" in s
        assert "reproSteps/expectedBehavior 不上送" in s
        # 触发条件（泛化抱怨/未回应才带出，判定例可执行）
        assert "泛化抱怨" in s and '"未回应"=用户未针对引导补充给出任何具体信息' in s
        # 拒答即提交不追问
        assert '答"没有/' in s and "立即提交、不追问" in s
        # 一句话口径完整在位（可测原文：payload 键+issue 段+来源注记）
        assert ("跳过固定追问时，reproSteps/expectedBehavior 不上送，" in s
                and "payload 不含对应键" in s
                and "不作来源注记" in s)
    # 双副本一致（md5 语义由安装器纪律锁，此处锁判定块同源）
    assert blocks[0] == blocks[1], "SKILL 双副本必须逐字节一致"


def test_followup_skip_clause_in_contract():
    """S67-S70：契约 description 跳过句（引导补充已获实质内容不再追问）
    逐字在位——判定块三层与契约/SKILL 三载体同源。"""
    c = json.load(open("contract/tools.schema.json"))
    desc = c["tools"]["vod_submit_voices"]["description"]
    assert ("引导补充（说下具体现象）已获实质内容并并入 content 时不再追问、直接提交" in desc)
    assert ("仅引导补充未获回应或仅泛化抱怨且用户确认提交时才带出固定问句" in desc)


def test_followup_boundary_refinement_locked():
    """2026-11-08 二次微调（负责人确认）：①跳过条件不含"回溯摘入"歧义——
    新字段来源唯一=固定追问原样回答；②"未回应/泛化抱怨"可执行判定例；
    ③一句话口径=可测原文（payload 键+issue 段+来源注记三处诚实回退）。
    三载体（SKILL 双副本/契约/proposal）锚点断言。"""
    skill = open("skills/vod-feedback-collect/SKILL.md", encoding="utf-8").read()
    assert "不回溯摘入新字段" in skill
    assert "新字段仅承载固定追问的原样回答" in skill
    assert '"未回应"=用户未针对引导补充给出任何具体信息' in skill
    assert '"泛化抱怨"=仅表达负面评价、无具体现象/' in skill
    assert ("跳过固定追问时，reproSteps/expectedBehavior 不上送，" in skill
            and "payload 不含对应键" in skill
            and "不作来源注记" in skill
            and "符合诚实回退" in skill)
    c = json.load(open("contract/tools.schema.json"))
    assert "不回溯摘入新字段" in c["tools"]["vod_submit_voices"]["description"]
    # proposal 与 SKILL 口径同源
    prop = open("docs/proposal.md", encoding="utf-8").read()
    assert "不回溯摘入新字段" in prop and "判定例" in prop
