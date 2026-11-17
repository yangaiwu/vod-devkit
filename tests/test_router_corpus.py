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