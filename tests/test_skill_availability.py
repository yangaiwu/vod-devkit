"""`--preset collect` 下的技能可用性：模型必须有一条**实际能走通**的路。

背景（2026-11-19 真机）：collect 预设只装 core+collect ⇒ 工具面没有
`vod_list_skills` / `vod_retrieve_skill`，而 `assets/skills/vod-core/SKILL.md` 的路由表
原来教模型用这两个工具 ⇒ 真模型照着调就失败。

**选用方案 B（改路由表，不动预设）**——依据是 `decisions.md:23`「外部=反馈采集者
(preset collect)，分析发起=内部(preset full)」的分层已拍板，不因这条缺陷推翻。

B 可行的三个前提，本文件逐条锁住（任一失效则 B 不再成立，必须回到 A 方案重议）：

1. **规则技能真的被装进本机技能目录**（不是"以为会拷"）：`_install_skills` 只对
   `vod-core` / `vod-feedback-collect` 做 pack 过滤，其余技能照拷。已在隔离 HOME
   真跑 `install --preset collect` 实测：4 个技能全在。
2. **模型能拿到技能树路径**：`initialize` 的 instructions 里带绝对路径
   （`技能树：<path>`），不依赖任何工具。
3. **路由表不再把 knowledge 工具说成无条件可用**：话术里必须标 `仅 knowledge pack`，
   并给出「读技能树/<技能名>/SKILL.md」这条替代路。
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE_SKILL = ROOT / "assets" / "skills" / "vod-core" / "SKILL.md"


def test_install_copies_all_skills_under_collect_preset(tmp_path):
    """前提 1：collect 预设下 4 个技能全部落到本机技能目录。

    ⚠️ 隔离纪律（S143）：子进程必须显式拿到 MANIFEST/PAYLOAD 的 tmp 落点。
    只给 HOME 不够——conftest 的 `_isolate_machine_writes` 只作用于**当前进程**，
    用 `env=` 整体替换时子进程会继承不到，账本就会写进真仓（本文件首版踩到，
    触发 `[S143] 机器状态被改动了` 告警）。
    """
    env = {
        "HOME": str(tmp_path),
        "HERMES_HOME": str(tmp_path / ".hermes"),
        "PYTHONPATH": str(ROOT / "src"),
        "PATH": "/usr/bin:/bin",
        "VOD_DEVKIT_MANIFEST": str(tmp_path / "install-manifest.json"),
        "VOD_PAYLOAD_HOME": str(tmp_path / ".vod-devkit"),
        "VOD_DEVKIT_HOME": str(tmp_path / "machine-state"),
    }
    r = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "vod-devkit"), "install",
         "--target", "hermes", "--preset", "collect",
         "--java-api-base", "https://vod-dev.topxtopx.com"],
        capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == 0, f"安装失败：{r.stderr[-500:]}"
    installed = sorted(p.parent.name for p in
                       (tmp_path / ".hermes" / "skills").rglob("SKILL.md"))
    for skill in ("vod-core", "vod-feedback-collect",
                  "vod-problem-classification-rules", "vod-scoring-rules"):
        assert skill in installed, f"{skill} 未被安装；实际装到：{installed}"


def test_initialize_carries_skill_tree_path(tmp_path):
    """前提 2：instructions 必须带技能树绝对路径（模型唯一的兜底入口）。"""
    payload = ('{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
               '{"protocolVersion":"2025-06-18","capabilities":{},'
               '"clientInfo":{"name":"t","version":"1"}}}\n')
    r = subprocess.run([sys.executable, str(ROOT / "src" / "vod_mcp" / "server.py")],
                       input=payload, capture_output=True, text=True, timeout=90,
                       env={"PYTHONPATH": str(ROOT / "src"), "VOD_PACKS": "core,collect",
                            "PATH": "/usr/bin:/bin"})
    ins = r.stdout
    m = re.search(r"技能树[：:]\s*(\S+)", ins)
    assert m, f"instructions 里没有技能树路径；stdout={ins[:300]!r}"
    assert "assets/skills" in m.group(1) or "skills" in m.group(1), m.group(1)


def test_route_table_flags_knowledge_tools_as_optional():
    """前提 3：路由表必须把这两个工具标成「仅 knowledge pack」并给替代路径。"""
    t = CORE_SKILL.read_text(encoding="utf-8")
    for tool in ("vod_list_skills", "vod_retrieve_skill"):
        line = next((x for x in t.splitlines() if tool in x and x.startswith("|")), None)
        assert line is not None, f"路由表里找不到 {tool}"
        assert "knowledge pack" in line, f"{tool} 未标注仅 knowledge pack：{line}"
    assert "SKILL.md" in t, "路由表未给出读 SKILL.md 的替代路径"


def test_collect_preset_still_excludes_knowledge_pack():
    """决策锁：collect 预设**不许**含 knowledge（否则推翻 decisions.md:23 的分层）。

    若将来真要改预设，本用例会红——那时必须同步改 decisions.md 并重新评估
    上面三条前提是否还需要。
    """
    from vodkit_cli.common import PRESETS
    assert set(PRESETS["collect"].split(",")) == {"core", "collect"}, (
        f"collect 预设变了：{PRESETS['collect']}——请同步 decisions.md:23 的分层口径")
    assert "knowledge" in PRESETS["full"]