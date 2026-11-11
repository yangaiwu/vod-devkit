"""领域技能披露（MCP 侧，devkit 双轨模型的第二轨）。

为什么需要第二轨：领域规则技能（分类/评分）目前靠"安装器把 SKILL.md 拷进
宿主的原生技能目录"分发，而各宿主目录是独立副本——本仓实锤过多次漂移
（skillHashes 只能事后发现，装完就分叉）。disclosure 让技能文本成为
**server data**：任何 MCP 宿主（包括没有原生技能目录的宿主，如 dsh headless）
都能按需取到与包内完全一致的规则全文，且改规则不必碰四份宿主拷贝。

分工（与 devkit 一致）：
- 元技能（vod-core / vod-feedback-collect）仍原生安装——它们的价值在
  宿主侧自动激活（触发词命中），走工具调用会丢掉激活时机。
- 领域规则技能由本模块披露，归属 knowledge pack：pack 被裁剪时拒绝并
  给恢复指引，不静默返回空。
"""
import re
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"

# 技能 → 归属 pack（core 常驻；knowledge 可裁剪）
SKILL_PACK = {
    "vod-problem-classification-rules": "knowledge",
    "vod-scoring-rules": "knowledge",
}
META_SKILLS = ("vod-core", "vod-feedback-collect")

_BODY_CAP = 12000  # 单技能全文上限（超出截断并标注，不静默丢内容）

# 契约纪律：披露内容里的内部机制词不因"技能是内部文档"而豁免——
# 这些文本会进模型上下文并可能被复述给终端用户。
_INTERNAL_WORDS = re.compile(r"(t_vod_[a-z_]+|jdbc:|mysql://)")


class SkillError(Exception):
    """披露失败（未知技能/未启用 pack）——调用方转成 MCP error 对象。"""

    def __init__(self, message: str, code: int = -32010):
        super().__init__(message)
        self.code = code


def _frontmatter(text: str) -> dict:
    """取 SKILL.md 的 YAML frontmatter 键值（只认一层，不引 yaml 依赖）。"""
    out = {}
    if not text.startswith("---"):
        return out
    body = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    for line in body.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


def _skill_dirs() -> list:
    if not SKILLS_ROOT.is_dir():
        return []
    return sorted(p for p in SKILLS_ROOT.iterdir()
                  if p.is_dir() and (p / "SKILL.md").exists())


def _server_face() -> bool:
    from vod_mcp import tools
    return bool(tools._SERVER_FACE.get())


def list_skills(params: dict) -> dict:
    """列出可披露的技能（元技能一并列出，标出 pack 与是否原生安装）。"""
    from vod_mcp import packs
    enabled = set(packs.enabled_packs())
    items = []
    for d in _skill_dirs():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        meta = _frontmatter(text)
        pack = SKILL_PACK.get(d.name, "core")
        items.append({
            "name": d.name,
            "pack": pack,
            "enabled": pack in enabled,
            "native": d.name in META_SKILLS,
            "description": meta.get("description", ""),
            "chars": len(text),
        })
    return {"skills": items, "packs": sorted(enabled),
            "note": "领域规则技能用 vod_retrieve_skill 取全文；元技能由宿主原生"
                    "加载，只在本工具里列名以便路由。"}


def retrieve_skill(params: dict) -> dict:
    """按名取技能全文（含 frontmatter + 正文）。owner-pack 裁剪即拒绝。"""
    from vod_mcp import packs
    name = (params or {}).get("name") or ""
    name = name.strip()
    if not name:
        raise SkillError("name 必填（先用 vod_list_skills 查名字）", -32602)
    d = SKILLS_ROOT / name
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", name) or not (d / "SKILL.md").exists():
        known = [p.name for p in _skill_dirs()]
        raise SkillError(f"未知技能 {name!r}；可用：{'、'.join(known)}", -32602)
    pack = SKILL_PACK.get(name, "core")
    enabled = set(packs.enabled_packs())
    if pack not in enabled:
        raise SkillError(
            f"技能 {name} 属于 {pack} pack，当前安装未启用（VOD_PACKS="
            f"{','.join(sorted(enabled))}）——如需启用，重跑 install 并带上 "
            f"--packs {','.join(sorted(enabled | {pack}))}", -32010)
    text = (d / "SKILL.md").read_text(encoding="utf-8")
    truncated = False
    if len(text) > _BODY_CAP:
        text = text[:_BODY_CAP]
        truncated = True
    if _INTERNAL_WORDS.search(text):
        # 不拦内容（规则文本是内部资产），但给出复述纪律提醒
        note = "注意：本技能含内部表名/连接串字样，向终端用户复述时不要照抄。"
    else:
        note = ""
    out = {"name": name, "pack": pack, "chars": len(text), "truncated": truncated,
           "content": text, "note": note}
    # 服务面（HTTP）不发布服务器本机路径——对齐 devkit「remote 不给 skillRoot」：
    # 未鉴权的远程面不该把自己的安装路径交出去。
    if not _server_face():
        out["path"] = str(d / "SKILL.md")
    return out