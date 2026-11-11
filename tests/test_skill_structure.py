"""技能结构门禁（对标 huaweicloud-skills 的 skillcheck 纪律，但只做我们需要的四条）。

为什么要有：对标仓 195 个技能里实测 27 个带 `version` 字段、32 个 tags 超限、
27 个 SKILL.md 超 500 行——**规范写在文档里没人执行就会漂**。所以借的不是规则条文，
而是"规则必须有门禁"这件事本身。

本门禁四条：
1. frontmatter 必须是合法 YAML，且 name==目录名 / description 非空 / tags ≤5 /
   version 只能在 metadata 下（上市场规范要求顶层不出现 version）
2. SKILL.md ≤ 500 行（超了拆进 references/）
3. references/ 文件名 kebab-case，且 references 目录存在时必须有 verification-method.md
4. 触发词与路由：技能间 Triggers 不得重复（互抢激活）；vod-core 的路由表必须覆盖
   每个技能，且不得引用不存在的技能
"""
import re
from pathlib import Path

import pytest

try:
    import yaml  # noqa: F401
except ImportError:  # pragma: no cover
    pytest.fail("需要 PyYAML：pip install pyyaml（frontmatter 严格校验不允许降级跳过）",
                pytrace=False)

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
MAX_LINES = 500


def _dirs() -> list:
    return sorted(p for p in SKILLS.iterdir() if p.is_dir() and (p / "SKILL.md").exists())


def _parts(skill_dir: Path) -> tuple:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{skill_dir.name}: SKILL.md 缺少 --- frontmatter 块"
    return yaml.safe_load(m.group(1)) or {}, text


def _triggers(meta: dict) -> set:
    """从 description 里取 `Triggers: "a","b"` 列表（我们与对标仓同一写法）。"""
    desc = str(meta.get("description") or "")
    m = re.search(r"Triggers\s*:\s*(.+)", desc, re.S)
    if not m:
        return set()
    return {t.strip().lower() for t in re.findall(r'"([^"]+)"', m.group(1))}


def test_frontmatter_is_valid_and_market_shaped():
    problems = []
    for d in _dirs():
        meta, _text = _parts(d)
        if not isinstance(meta, dict):
            problems.append(f"{d.name}: frontmatter 根不是映射")
            continue
        if str(meta.get("name") or "") != d.name:
            problems.append(f"{d.name}: name 必须等于目录名（现在 {meta.get('name')}）")
        desc = str(meta.get("description") or "").strip()
        if len(desc) < 20:
            problems.append(f"{d.name}: description 为空或过短")
        tags = meta.get("tags")
        if tags is not None and (not isinstance(tags, list) or len(tags) > 5):
            problems.append(f"{d.name}: tags 必须是 ≤5 的列表（现在 {tags}）")
        if "version" in meta:
            problems.append(f"{d.name}: 顶层不许有 version（挪到 metadata.version）")
    assert not problems, "frontmatter 不合规：\n  " + "\n  ".join(problems)


def test_skill_md_within_line_budget():
    over = []
    for d in _dirs():
        n = len((d / "SKILL.md").read_text(encoding="utf-8").splitlines())
        if n > MAX_LINES:
            over.append(f"{d.name}: {n} 行（上限 {MAX_LINES}，超出的拆进 references/）")
    assert not over, "SKILL.md 超长：\n  " + "\n  ".join(over)


def test_references_follow_naming_and_carry_verification_method():
    problems = []
    for d in _dirs():
        refs = d / "references"
        if not refs.is_dir():
            continue
        for f in refs.iterdir():
            if f.is_file() and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*\.md", f.name):
                problems.append(f"{d.name}: references 文件名非 kebab-case：{f.name}")
        if not (refs / "verification-method.md").exists():
            problems.append(f"{d.name}: 有 references/ 但缺 verification-method.md"
                            "（'怎么验'必须随技能走）")
    assert not problems, "references 不合规：\n  " + "\n  ".join(problems)


def test_triggers_do_not_collide_between_skills():
    """触发词冲突扫描（对标 skill-tester Phase 5 的 internal_ambiguities）。"""
    seen = {}
    dup = []
    for d in _dirs():
        meta, _ = _parts(d)
        for t in _triggers(meta):
            if t in seen and seen[t] != d.name:
                dup.append(f"「{t}」同时出现在 {seen[t]} 与 {d.name}（互抢激活）")
            seen[t] = d.name
    assert not dup, "触发词冲突：\n  " + "\n  ".join(dup)


def test_core_routing_table_covers_every_skill():
    core = SKILLS / "vod-core" / "SKILL.md"
    text = core.read_text(encoding="utf-8")
    names = {d.name for d in _dirs()}
    referenced = {n for n in names if n in text}
    missing = sorted(names - referenced - {"vod-core"})
    assert not missing, (
        "以下技能没有被 vod-core 路由表引用（装了也不可达）：\n  " + "、".join(missing))


# 路由表里合法允许出现的"非技能"名字（外部系统/组件），不是幽灵技能
_ROUTE_ALLOW = {"vod-system", "vod-devkit"}


def test_route_table_entries_exist():
    text = (SKILLS / "vod-core" / "SKILL.md").read_text(encoding="utf-8")
    names = {d.name for d in _dirs()}
    referenced = set(re.findall(r"vod-[a-z0-9-]+", text))
    ghosts = sorted(n for n in referenced
                    if n not in names and n not in _ROUTE_ALLOW
                    and "_" not in n and "devkit" not in n)
    assert not ghosts, ("vod-core 路由表引用了不存在的技能/组件：\n  " + "、".join(ghosts))