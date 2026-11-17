"""S193：路由词表与 S184 分型现象词并表；元讨论只认工程语汇，裸「卡」加边界。

评审实测语料（2026-11-17，确定性秒级复现）暴露两组偏差：

漏注入（真实用户抱怨被压掉）——7 条里 6 条是**触发词表缺词**，1 条是 META 过宽：
  你们这个接口老报错，能不能修一下      ← 「接口」∈META_WORDS 把用户的抱怨压掉
  配置太麻烦了，每次都要手填一堆字段    ← 「麻烦」不在触发词表
  上传附件一直失败 / 版本更新之后打不开  ← 「失败/打不开」不在触发词表
  我们客户的页面打不开，急              ← 同上（有锚点也没用，先卡在触发词）
  批量导入老是超时 / 上传完就崩了        ← 「超时/崩」不在触发词表

误注入（工程讨论仍被拐）：
  数据库连接池卡住了，排查一下          ← 「排查」是工程动作，但没有元语汇判据
  帮我把卡片组件的样式调一下            ← 裸「卡」子串命中「卡片」

两条根因都不是调词能蒙过去的：
a) 触发词表与 SKILL 的 S184 现象词表漂移（SKILL 教 报错/卡死/失败/打不开/超时/崩/没反应，
   路由只认前三个 + 白屏/没反应）——两份词表违反单一事实源；
b) 元讨论排除没有「谁在说话」的信号：「接口/配置/字段/日志」是用户与工程师共用词，放进
   META 就直接压掉用户视角；真正的元讨论信号是**工程动作词**（改成/抽成/重构/评审/实现/
   写死/解耦/排查/调一下）。

判据：
- 触发词表 ⊇ SKILL 的 S184 现象词（本文件第 1 条用例，读 SKILL 文本逐词比）；
- META 只留纯工程语汇 + 工程动作词；共用词（接口/配置/字段/日志/版本）移出；
- 裸「卡」必须带边界（排除卡片/卡号/卡券/卡通/卡位/卡口/车牌/卡车）。
"""
from pathlib import Path

from test_router import router   # 复用同一加载方式（importlib，进程边界外的真实文件）

_REPO = Path(__file__).resolve().parent.parent
_SKILL = (_REPO / "assets" / "skills" / "vod-feedback-collect" / "SKILL.md").read_text(encoding="utf-8")

SHOULD_FIRE = (
    "你们这个接口老报错，能不能修一下",
    "配置太麻烦了，每次都要手填一堆字段",
    "上传附件一直失败",
    "版本更新之后打不开",
    "我们客户的页面打不开，急",
    "批量导入老是超时",
    "上传完就崩了",
)

SHOULD_SILENT = (
    "数据库连接池卡住了，排查一下",
    "帮我把卡片组件的样式调一下",
    "建议增加一条门禁用例，覆盖 dsh 多 profile 的场景",
    "这个报错的文案要改，代码里写死了中文",
)


def test_s193_trigger_words_cover_s184_phenomenon_words():
    """单一事实源：S184 教给模型的现象词，路由必须同样认（不许两份词表）。"""
    s184 = ("报错", "卡死", "失败", "打不开", "超时", "崩", "没反应")
    for w in s184:
        assert w in _SKILL, f"S184 现象词「{w}」不在 SKILL 里，本用例已过时"
        assert w in router.TRIGGER_WORDS, f"S184 现象词「{w}」路由不认（双词表漂移）"


def test_s193_user_complaints_are_not_suppressed():
    for msg in SHOULD_FIRE:
        assert router.route(msg) is not None, f"真实抱怨被压掉：{msg}"


def test_s193_engineering_discussion_stays_silent():
    for msg in SHOULD_SILENT:
        assert router.route(msg) is None, f"工程讨论被误注入：{msg}"


def test_s193_bare_ka_has_boundary():
    """裸「卡」不得命中卡片类名词；口语抱怨（网页卡/卡住了）仍要命中。"""
    for msg in ("帮我把卡片组件的样式调一下", "卡号填错了要重来", "卡券用不了"):
        assert router.route(msg) is None, f"「卡」子串误命中：{msg}"
    for msg in ("网页卡", "卡住了", "太卡了"):
        assert router.route(msg) is not None, f"口语抱怨漏判：{msg}"


def test_s193_shared_vocabulary_not_in_meta():
    """接口/配置/字段/日志/版本 是用户与工程师共用词，放进 META 等于压掉用户视角。"""
    for w in ("接口", "配置", "字段", "日志", "版本"):
        assert w not in router.META_WORDS, f"共用词「{w}」不该进元讨论词表"

# --- S195：工程第二层 + 礼貌「麻烦」的误注入（2026-11-17 评审 P2b）----------------
# 并表修好了上一轮 9 条，但「同病换词」：工程第二层（构建/编译/发布/流水线）不在 META，
# 「麻烦」当触发词太宽（礼貌句被当抱怨）。另：评审那条消息本身就被路由注入了，属同类现场。
ENGINEERING_LAYER = (
    "构建失败，帮我查下 CI 日志",
    "编译失败了看下报错",
    "发布失败了回滚吧",
    "流水线超时了",
)


def test_s195_engineering_second_layer_stays_silent():
    for msg in ENGINEERING_LAYER:
        assert router.route(msg) is None, f"工程第二层被误注入：{msg}"


def test_s195_polite_mafan_is_not_complaint():
    for msg in ("麻烦你重发一下邮件", "麻烦确认下会议时间", "谢谢，麻烦你了"):
        assert router.route(msg) is None, f"礼貌句被当抱怨：{msg}"
    # 真抱怨仍要命中
    for msg in ("操作太麻烦了", "这个流程麻烦死了"):
        assert router.route(msg) is not None, f"真实抱怨漏判：{msg}"


# --- S199：词表不变量（新增词时的机械护栏，不依赖某条语料）---------------------
# 为什么需要：S185/S193/S195 三轮都是「修一条、换词又长一条」。语料用例只能钉住**已知**
# 的误判；新增词时的结构性问题（同一个词既算抱怨又算元语汇、词表里塞空串/带空格、
# 重复项）没有断言就会静默漂移。这里锁的是词表本身的不变量，与语料互补。
def test_s199_word_tables_have_no_overlap_or_junk():
    tables = {"TRIGGER": router.TRIGGER_WORDS, "META": router.META_WORDS,
              "ANCHOR": router.ANCHOR_WORDS}
    for name, words in tables.items():
        assert len(words) == len(set(words)), f"{name} 有重复项"
        for w in words:
            assert isinstance(w, str) and w and w == w.strip(), f"{name} 含空串/带空格的词：{w!r}"
    tri, meta, anch = (set(tables[k]) for k in ("TRIGGER", "META", "ANCHOR"))
    assert not (tri & meta), f"同一个词不能既算抱怨又算工程语汇：{sorted(tri & meta)}"
    assert not (tri & anch), f"触发词与锚点重叠会让优先级失效：{sorted(tri & anch)}"
    assert not (meta & anch), f"元语汇与锚点重叠会让排除判据自相矛盾：{sorted(meta & anch)}"


def test_s199_ka_guard_is_the_only_special_case():
    """装配正则里只允许裸「卡」一处特殊处理——别悄悄长出第二套规则。"""
    pattern = router._trigger_pattern()
    assert pattern.count("(?!") == 1, "出现了第二处边界规则，需在词表纪律里显式登记"
    assert router._KA_GUARD in pattern


# --- S202：第三轮"同病换词"——"发布/环境"把用户视角压掉 ---------------------------
# 实测（评审语料，2026-11-17）："你们刚发布的版本打不开"/"生产环境卡死了"/"升级环境之后白屏了"
# 全部零注入，因为 META 收了裸词「发布」「环境」——而同一份提交里的 hermes-router.md 明写
# 「共用词（接口/配置/字段/日志/版本）不算元语汇」。文档与实现自相矛盾。
# 判据：META 只收**工程搭配**（发布流水线/发布流程/环境变量/测试环境/预发环境/构建产物），
# 不收裸词；用户视角句必须注入。
USER_PERSPECTIVE = (
    "你们刚发布的版本打不开",
    "生产环境卡死了，整个流程走不下去",
    "升级环境之后白屏了",
    "版本发布后登录不上了",
)


def test_s202_release_and_env_are_not_meta_words():
    for w in ("发布", "环境"):
        assert w not in router.META_WORDS, f"共用词「{w}」不该进元讨论词表（文档与实现要一致）"
    for w in ("发布流水线", "环境变量", "测试环境"):
        assert w in router.META_WORDS, f"工程搭配「{w}」应在 META 里（工程语境才该排除）"


def test_s202_user_perspective_sentences_still_inject():
    for msg in USER_PERSPECTIVE:
        assert router.route(msg) is not None, f"用户视角被压掉：{msg}"


def test_s202_engineering_release_contexts_stay_silent():
    for msg in ("发布流水线挂了，看下日志", "环境变量没配对，构建失败了",
                "测试环境连不上，排查一下"):
        assert router.route(msg) is None, f"工程语境误注入：{msg}"
