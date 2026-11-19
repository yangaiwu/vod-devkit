"""采集纪律的唯一真值（ARCH-CALL-02）。

`initialize` 的 instructions 在 stdio 与 remote 两面各有一份，**同一段采集纪律
（同意口径 / echo 逐字转述 / product 追问）曾经近乎逐字抄了两遍**：改一处漏一处，
一个形态的模型行为就与另一个不一致，而两边门禁各自只锁关键词，全绿放行。

这里抽成单一常量；两面只拼接**形态专属的尾句**（本机路径 / 摘除哪些工具）。
改纪律只改这里一处，两面自动同步。
"""
from __future__ import annotations

# 采集纪律（两面逐字相同，不许各写一份）
COLLECT_DISCIPLINE = (
    "vod-devkit 采集资产与纪律：技能 vod-feedback-collect 处理用户对"
    "本产品的不满/建议/期望（触发词：慢/报错/体验差/希望支持/提单等）。"
    "提交前必须征得用户明确同意（用户抱怨本身不构成同意）；提交回执 "
    "echo.contents 必须逐条原样转述给用户（「已收录原话：<content>」），"
    "禁止改写、概括、增删字词。product 归因：原话唯一命中可直接用；"
    "未命中或多产品歧义时必须问用户一次\"这条是哪个产品的反馈\"，"
    "回答填 product；用户说不知道就告知他缺产品不能提交，不要猜。不许不填直接提交。"
)

# 形态专属尾句
STDIO_TAIL = (
    " 技能树：{skills_root}（本机路径）。读法=动作优先：先直接读 "
    "skillRoot/<技能名>/SKILL.md（尝试本身即可达性检查，不做预判）；"
    "被拒或读取失败才用 vod_retrieve_skill 取全文（无需文件权限），绝不反复请求。"
)
REMOTE_TAIL = (
    "本面不提供服务器本机路径（skillRoot），规则文本用 vod_retrieve_skill 取；"
    "工具面与本地一致，只摘进程内开关 vod_packs_configure。"
)


def stdio_instructions(skills_root) -> str:
    """stdio 面 instructions：公共纪律 + 本机技能树路径。"""
    return COLLECT_DISCIPLINE + STDIO_TAIL.format(skills_root=skills_root)


def remote_instructions() -> str:
    """remote 面 instructions：公共纪律 + 远程面形态说明（不含本机路径）。"""
    return COLLECT_DISCIPLINE + REMOTE_TAIL


__all__ = ["COLLECT_DISCIPLINE", "STDIO_TAIL", "REMOTE_TAIL",
           "stdio_instructions", "remote_instructions"]