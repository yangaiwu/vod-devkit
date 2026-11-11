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
    for p in sorted((ROOT / "vod_mcp").glob("*.py")):
        bad = _imports(p) & _FORBIDDEN_IMPORTS
        if bad:
            offenders[p.name] = sorted(bad)
    assert not offenders, (
        "vod_mcp 出现引擎内部模块 import（插件是引擎的 HTTP 客户端，跨仓 import 断链）：\n"
        + json.dumps(offenders, ensure_ascii=False, indent=2))


def test_optional_mcp_sdk_stays_in_remote_modules():
    """可选 SDK（mcp）只能出现在远程面两个模块——stdio 主路径必须零第三方依赖。"""
    offenders = {}
    for p in sorted((ROOT / "vod_mcp").glob("*.py")):
        if p.name in _SDK_ALLOWED_FILES:
            continue
        bad = _imports(p) & _OPTIONAL_SDK
        if bad:
            offenders[p.name] = sorted(bad)
    assert not offenders, json.dumps(offenders, ensure_ascii=False, indent=2)


def test_attribution_module_is_pure():
    """归因模块只做计算：不许开文件/读环境/发网络请求（否则单测会带副作用）。"""
    p = ROOT / "vod_mcp" / "attribution.py"
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
    contract = json.loads((ROOT / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
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
    policy = json.loads((ROOT / "safety" / "policy.json").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
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

def test_build_info_root_and_plugin_copy_agree():
    """溯源双副本一致：根 build-info.json 与 plugins 副本必须同版本、同 SHA。

    实锤（2026-11-11）：根副本停在 0.4.2/0bbe0dd 五个发版周期，而包内副本已 0.5.0/
    4d4e6cb——`vod-devkit status/verify/doctor` 读根副本，报的版本与真实包不符，
    正是「版本号相同≠内容相同」那一类静默漂移。
    """
    import json
    root_bi = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8"))
    pkg_bi = json.loads((ROOT / "plugins" / "vod-devkit" / "build-info.json")
                        .read_text(encoding="utf-8"))
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert root_bi.get("version") == pkg["version"], (
        f"根 build-info 版本 {root_bi.get('version')} ≠ package.json {pkg['version']}"
        "（跑 python3 bin/vod-devkit build-info 重烧）")
    for field in ("version", "commitSha"):
        assert root_bi.get(field) == pkg_bi.get(field), (
            f"根/包内 build-info 的 {field} 不一致："
            f"{root_bi.get(field)} vs {pkg_bi.get(field)}")
