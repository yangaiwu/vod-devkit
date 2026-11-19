"""结构守卫测试（借鉴 huaweicloud-devkit 的 structure-*.test.ts 纪律）。

守卫的是「后来者顺手加一条反向依赖/重复真源」这类结构腐化，不是行为：
  1. vod_mcp 只许 HTTP 说引擎——不得 import 引擎内部模块
  2. attribution.py 保持纯函数（无文件/环境/网络 IO）
  3. contract/tools.schema.json 是工具面单一真源（与 _HANDLERS 一一对应）
  4. safety/policy.json 必备字段下限 + 规则指向的工具必须真实存在
任何一条红都是结构问题，不许用"只是测试"绕过。
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 引擎/云侧模块名：一旦 import 进来就等于把插件焊在引擎实现上（跨仓 import 断链）
_FORBIDDEN_IMPORTS = {
    "workflow", "vod_system", "vodsystem", "langgraph", "langgraph2",
    "providers", "n01_classify", "n02_feature", "n03_analysis", "workflow_v2",
}
# 允许的第三方：远程面可选 SDK 只能出现在两个远程模块
_OPTIONAL_SDK = {"mcp"}
_SDK_ALLOWED_FILES = {"remote_app.py", "transport_remote.py"}


def _imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_vod_mcp_never_imports_engine_internals():
    offenders = {}
    for p in sorted((ROOT / "src" / "vod_mcp").glob("*.py")):
        bad = _imports(p) & _FORBIDDEN_IMPORTS
        if bad:
            offenders[p.name] = sorted(bad)
    assert not offenders, (
        "vod_mcp 出现引擎内部模块 import（插件是引擎的 HTTP 客户端，跨仓 import 断链）：\n"
        + json.dumps(offenders, ensure_ascii=False, indent=2))


def test_optional_mcp_sdk_stays_in_remote_modules():
    """可选 SDK（mcp）只能出现在远程面两个模块——stdio 主路径必须零第三方依赖。"""
    offenders = {}
    for p in sorted((ROOT / "src" / "vod_mcp").glob("*.py")):
        if p.name in _SDK_ALLOWED_FILES:
            continue
        bad = _imports(p) & _OPTIONAL_SDK
        if bad:
            offenders[p.name] = sorted(bad)
    assert not offenders, json.dumps(offenders, ensure_ascii=False, indent=2)


def test_attribution_module_is_pure():
    """归因模块只做计算：不许开文件/读环境/发网络请求（否则单测会带副作用）。"""
    p = ROOT / "src" / "vod_mcp" / "attribution.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))
    forbidden_names = {"open", "write_text", "read_text", "write_bytes",
                       "read_bytes", "urlopen", "socket", "getenv", "environ"}
    banned_modules = {"os", "json", "urllib", "socket", "pathlib", "subprocess"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in forbidden_names:
            hits.append(f"调用 {node.func.id}()（行 {node.lineno}）")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in forbidden_names:
            hits.append(f"调用 .{node.func.attr}()（行 {node.lineno}）")
        if isinstance(node, ast.Import):
            hits += [f"import {a.name}" for a in node.names
                     if a.name.split(".")[0] in banned_modules]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                and node.module.split(".")[0] in banned_modules:
            hits.append(f"from {node.module} import …")
    assert not hits, "attribution.py 不再是纯函数（持久化/IO 应留在 tools 层）：\n  " + "\n  ".join(hits)


def test_contract_and_handlers_are_one_set():
    """契约是工具面单一真源：契约里的工具 == dispatch 注册的 handler。"""
    from vod_mcp import tools as impl
    contract = json.loads((ROOT / "assets" / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
    declared = set(contract["tools"])
    implemented = set(impl._HANDLERS)
    assert declared == implemented, (
        "契约与实现工具集不一致（新增工具必须双写，且契约先行）：\n"
        f"  只在契约：{sorted(declared - implemented)}\n"
        f"  只在实现：{sorted(implemented - declared)}")
    for name, tool in contract["tools"].items():
        assert tool.get("description", "").strip(), f"{name} 缺 description"
        assert isinstance(tool.get("input"), dict), f"{name} 缺 input schema"


def test_policy_rules_have_required_fields_and_real_tools():
    """护栏策略必备字段下限 + 规则指向的工具必须存在（防悬空规则）。"""
    policy = json.loads((ROOT / "assets" / "safety" / "policy.json").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "assets" / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
    tools = set(contract["tools"])
    rules = policy.get("rules") or []
    assert rules, "policy.json 没有规则——护栏静默失效"
    problems = []
    for i, r in enumerate(rules):
        for field in ("id", "category", "severity", "match", "message"):
            if not r.get(field):
                problems.append(f"规则 #{i} 缺 {field}")
        match = r.get("match") or {}
        if match.get("tool"):
            if match["tool"] not in tools:
                problems.append(f"规则 {r.get('id')} 指向不存在的工具 {match['tool']}")
        elif match.get("field") and match.get("regex"):
            # 跨切面文本扫描规则（凭据/DB 意图）：不挂工具，但正则必须可编译
            try:
                import re as _re
                _re.compile(match["regex"])
            except Exception as e:  # noqa: BLE001
                problems.append(f"规则 {r.get('id')} 正则非法：{e}")
        else:
            problems.append(f"规则 {r.get('id')} match 既无 tool 也无 field+regex（悬空规则）")
        if r.get("severity") not in ("confirm", "deny", "warn"):
            problems.append(f"规则 {r.get('id')} severity 非法：{r.get('severity')}")
    assert not problems, "policy 结构问题：\n  " + "\n  ".join(problems)
    ids = [r.get("id") for r in rules]
    assert len(ids) == len(set(ids)), "policy 规则 id 重复"

def _commit_exists(sha: str) -> bool | None:
    """该 sha 是否为本仓真实存在的提交；无 `.git`（tarball 形态）返回 None=判不了。

    S163-2：门禁只要求「可解释」——根是 tracked 的发版快照（release 记 v^），插件副本是
    打包/同步时刻烧的（常常是 HEAD），要求两份逐字相等就会在 NO_BUILD_INFO 现场必红
    （host_matrix / CI 顺序，实测 root=9e6182d vs pkg=d49f424）。真正的硬不变量是
    version 三方相等（防 0.4.2 那种"版本号停五个周期"），commitSha 只需是真实提交。
    """
    import subprocess

    if not sha or not (ROOT / ".git").exists():
        return None
    r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                       cwd=ROOT, capture_output=True)
    return r.returncode == 0


def test_build_info_root_and_plugin_copy_agree():
    """溯源双副本一致（口径 S163-2）：version 三方相等；commitSha 落在发布集合内。

    实锤（2026-11-11）：根副本停在 0.4.2/0bbe0dd 五个发版周期，而包内副本已 0.5.0/
    4d4e6cb——`vod-devkit status/verify/doctor` 读根副本，报的版本与真实包不符，
    正是「版本号相同≠内容相同」那一类静默漂移。

    2026-11-16 评审第二轮：旧断言要求两份 commitSha 逐字相等，而测试期 sync 会把两份
    都写成当前 HEAD（已改为 write_build_info=False）——在 NO_BUILD_INFO 现场（host_matrix、
    CI 顺序）两份停在 v^ 与 HEAD，门禁必红，属"门禁给自己打分"。version 与 package.json
    的三方相等仍是硬断言（0.4.2 那类漂移照样红）。
    """
    import json
    root_bi = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8"))
    pkg_bi = json.loads((ROOT / "plugins" / "vod-devkit" / "build-info.json")
                        .read_text(encoding="utf-8"))
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert root_bi.get("version") == pkg["version"], (
        f"根 build-info 版本 {root_bi.get('version')} ≠ package.json {pkg['version']}"
        "（跑 python3 bin/vod-devkit build-info 重烧）")
    assert pkg_bi.get("version") == pkg["version"], (
        f"包内 build-info 版本 {pkg_bi.get('version')} ≠ package.json {pkg['version']}"
        "（跑 python3 scripts/sync_plugin.py）")
    for name, bi in (("根", root_bi), ("包内", pkg_bi)):
        ok = _commit_exists(str(bi.get("commitSha") or ""))
        assert ok is not False, (
            f"{name} build-info 的 commitSha {bi.get('commitSha')} 不是本仓的提交"
            "（被 amend/rebase 掉，或非本仓产物）")


def test_server_instructions_match_attribution_design():
    """真机实锤的文案漂移锁：D-attrib-B 改成运行期字面解析后，server 的
    instructions 仍写着"归因由安装绑定完成"——宿主会照这句话去绑定安装期的
    product，等于把已推翻的语义重新说给模型听。

    2026-11-16 扩到全部"说给模型听"的面：远程面 REMOTE_INSTRUCTIONS 与工具契约
    description 当时仍是 D-attrib-B 旧口径（"禁止询问用户"），而实现已经按
    D-product-ask-1 以 -32010 要模型先问一次——只锁 server.py 一个文件的用例漏掉了它们。
    """
    surfaces = (
        # ARCH-CALL-02 起，两面的"说给模型听"文本收敛到 instructions.py。
        # 仍按文件正文读的两个面：instructions（运行时真实下发内容）+ 工具契约。
        # server.py / remote_app.py 已不再承载正文，读它们只会读到拼接表达式。
        "src/vod_mcp/instructions.py",
        "assets/contract/tools.schema.json",
    )
    for rel in surfaces:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "安装绑定完成" not in text, f"{rel} 的归因口径退回旧语义"
        assert "禁止询问用户" not in text, (
            f"{rel} 写着「禁止询问用户」——与 D-product-ask-1（缺产品先 -32010 拒绝、"
            "要求模型问用户一次）冲突，远程宿主里的模型会据此不问并自行编造产品")
        assert "问用户一次" in text, f"{rel} 缺少「缺产品必须先问一次」的正面规则"


def test_remote_instructions_match_withheld_tools():
    """远程面的工具面自述必须与 REMOTE_WITHHELD 一致：只有进程内开关被摘。

    实锤（2026-11-16）：远程文案当时写着"写本机状态的工具（草稿/本地账本）不在本面
    提供"，而 tools/list 实测 11 个工具里 draft/commit/list_submitted 全在——模型
    会以为没有账本/草稿能力，用户问"我提交过哪些"时直接回"没有这个功能"。

    ARCH-CALL-02 起改为校验**实际下发的文本**（REMOTE_INSTRUCTIONS）而不是 remote_app.py
    的文件正文——文本已收敛到 instructions.py，按文件读会漏（也是本用例原本的教训：
    "只锁一个文件"就会漏）。
    """
    from vod_mcp import packs, remote_app
    text = remote_app.REMOTE_INSTRUCTIONS
    assert "不在本面提供" not in text, (
        "远程面只摘 vod_packs_configure，不得声称其它工具缺失")
    for name in packs.REMOTE_WITHHELD:
        assert name in text, f"远程 instructions 没说明摘除了 {name}"


# ── S129 目录结构契约（根预算 / 运行期状态零跟踪）───────────

_ROOT_ALLOW = {
    # 目录
    "assets", "bin", "docs", "integrations", "npm", "packages",
    "plugins", "scripts", "src", "tests",
    # 顶层文件（元数据 + 门面文档）
    "CHANGELOG.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "INSTALL.md",
    "LICENSE.txt", "NOTICE", "OWNERS", "QUICKSTART.md", "README.en.md",
    "README.md", "RELEASING.md", "SECURITY.md", "SUPPORT.md",
    "build-info.json", "package.json", "plugin.json", "pyproject.toml",
}


def test_s129_root_budget_no_new_top_level_entries():
    """根目录预算（D-structure-1）：新增顶层条目=结构变更，必须先改
    docs/architecture.md 与这里。不设上限的根目录必然越用越散——devkit 26 条、
    我们 2026-11-15 是 42 条，这条用例是把它拉回契约的机械手段。
    """
    import subprocess
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=ROOT).stdout
    tops = set()
    for line in out.splitlines():
        first = line.split("/", 1)[0]
        if first.startswith("."):        # 点目录/点文件（.github/.gitignore/...）不计
            continue
        tops.add(first)
    extra = sorted(tops - _ROOT_ALLOW)
    assert not extra, (
        "根目录出现契约外的条目：" + "、".join(extra)
        + "；先改 docs/architecture.md 的预算表与本用例，再落目录")


def test_s129_runtime_state_is_never_tracked():
    """运行期状态绝不入库（install-manifest 含宿主路径/产品绑定；runtime.json 含 key）。

    2026-11-15 之前的真实事故面：0.1.12 npm 包曾带上 vod_mcp/runtime.json（含匿名令牌）。
    回退方式是把它们 gitignore + 打包白名单，而不是靠人记得别 add。
    """
    import subprocess
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=ROOT).stdout
    tracked = set(out.splitlines())
    for p in ("install-manifest.json", "src/vod_mcp/runtime.json",
              "src/vod_mcp/runtime.local.json"):
        assert p not in tracked, f"运行期状态被跟踪：{p}（必须 gitignore 且不入包）"


def test_s129_structure_doc_exists_and_matches_rules():
    """结构契约必须写在文件里（docs/architecture.md），不是只活在 review 评论里。"""
    doc = (ROOT / "docs" / "architecture.md")
    assert doc.exists(), "缺 docs/architecture.md"
    text = doc.read_text(encoding="utf-8")
    for needle in ("唯一的\"宿主发布物\"", "源与生成物分离", "共享资产单一落点",
                   "门禁脚本化", "迁移分阶"):
        assert needle in text, f"结构契约缺少：{needle}"


# ── ARCH-CALL-02：采集纪律单一真源 ───────────────────────────────────────────
#
# 曾是两份近乎逐字重复的文本（server.py 的 instructions 与 remote_app.py 的
# REMOTE_INSTRUCTIONS），采集纪律是**产品红线**（同意口径 / 逐字转述 / 产品追问），
# 改一处漏一处 ⇒ 一个形态的模型行为与另一个不一致，而两边门禁各自只锁关键词，全绿放行。
def test_both_faces_share_collect_discipline():
    """两面 instructions 都必须以同一个 COLLECT_DISCIPLINE 开头。"""
    from vod_mcp import instructions, remote_app, skills_registry
    c = instructions.COLLECT_DISCIPLINE
    stdio = instructions.stdio_instructions(skills_registry.SKILLS_ROOT)
    remote = remote_app.REMOTE_INSTRUCTIONS
    assert stdio.startswith(c), "stdio 面不再以公共纪律开头（纪律被就地改写了）"
    assert remote.startswith(c), "remote 面不再以公共纪律开头（又维护了第二份）"


def test_collect_discipline_covers_the_three_redlines():
    """三条红线逐条在位：同意口径、echo 逐字转述、product 末命中必须问一次。"""
    from vod_mcp import instructions
    c = instructions.COLLECT_DISCIPLINE
    assert "征得用户明确同意" in c
    assert "echo.contents 必须逐条原样转述" in c and "禁止改写" in c
    assert "必须问用户一次" in c and "不要猜" in c


def test_form_specific_tails_are_separate():
    """形态尾句各自独立：stdio 带本机路径，remote 不带。"""
    from vod_mcp import instructions, remote_app, skills_registry
    stdio = instructions.stdio_instructions(skills_registry.SKILLS_ROOT)
    remote = remote_app.REMOTE_INSTRUCTIONS
    assert str(skills_registry.SKILLS_ROOT) in stdio, "stdio 面丢了技能树路径"
    assert "本机路径" in stdio or "skillRoot" in stdio
    assert str(skills_registry.SKILLS_ROOT) not in remote, \
        "remote 面不许泄漏服务器本机路径"
    assert "不提供服务器本机路径" in remote
