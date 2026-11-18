"""双 CI 定义必须同源（ARCH-BLD-01，2026-11-19 走查 P1）。

**此前实锤**：`.github/workflows/ci.yml` 10 步门禁、`.gitcode/workflows/ci.yml` 5 步
（`secret_scan`/`mypy`/花名册/规则溯源/发版对账/dsh 单测/宿主矩阵全缺席），
而本仓实际托管在 GitCode ⇒ **真跑的门禁只有那 5 步**。且两份都只在 `main` 触发，
而开发主干是 `dev` ⇒ dev 上的提交零 CI 门禁。

修法：门禁清单只写 `scripts/gate_all.py`，两份 yaml 都只调它。本文件锁三件事：
  ① 两份 yaml 调用的门禁名**集合相等**（漂移即红）
  ② 两份 yaml 都触发 `dev`
  ③ `gate_all.py` 里声明的门禁名，全部真实存在（防止调一个不存在的名字静默通过）
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GITHUB = ROOT / ".github" / "workflows" / "ci.yml"
GITCODE = ROOT / ".gitcode" / "workflows" / "ci.yml"
GATE = ROOT / "scripts" / "gate_all.py"


def _gate_names_in(yaml_path: pathlib.Path) -> set:
    """从 yaml 里抽出 `gate_all.py <名> <名> ...` 调用到的门禁名。

    只取**连续的门禁名 token**：遇到第一个不像门禁名的 token（注释、中文、引号）
    就停，否则 `# 注释` 里的字也会被当成门禁名（首版踩到）。
    """
    text = yaml_path.read_text(encoding="utf-8")
    names = set()
    for m in re.finditer(r"gate_all\.py([^\n]*)", text):
        for tok in m.group(1).split():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", tok):
                break                      # 注释/中文/重定向：后面都不是门禁名
            names.add(tok)
    return names


def _declared_gates() -> set:
    """gate_all.py 的 GATES 字典键（用 ast 读，不 import 以免跑副作用）。"""
    import ast
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "GATES" for t in node.targets):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("gate_all.py 里找不到 GATES 定义")


def test_both_ci_run_same_gate_set():
    """① 两份 CI 的门禁名集合必须相等（允许 GitHub 侧多跑 dsh/hostmatrix 这类需工具的项）。"""
    gh, gc = _gate_names_in(GITHUB), _gate_names_in(GITCODE)
    assert gh, "GitHub CI 没有调用 gate_all.py"
    assert gc, "GitCode CI 没有调用 gate_all.py"
    # GitCode runner 无 node、无宿主 CLI：这两项在那边 SKIP 而非缺席，
    # 所以允许 GitCode 少调它们，但**其它全部必须一致**。
    tool_gates = {"dsh", "hostmatrix"}
    assert gh - tool_gates == gc - tool_gates, (
        "两份 CI 的门禁清单漂移（这是 BLD-01 的原缺陷）：\n"
        f"  仅 GitHub 有：{sorted(gh - gc)}\n  仅 GitCode 有：{sorted(gc - gh)}")


def test_ci_triggers_cover_dev_branch():
    """② 两份 CI 都必须触发 dev（开发主干，此前零门禁）。"""
    for path in (GITHUB, GITCODE):
        text = path.read_text(encoding="utf-8")
        assert re.search(r'branches:\s*\[[^\]]*"dev"', text), (
            f"{path.name} 未触发 dev 分支——dev 上的提交不跑门禁")


def test_every_called_gate_is_declared():
    """③ yaml 里调用的门禁名必须都在 gate_all.py 的 GATES 里（否则调个空名字静默通过）。"""
    declared = _declared_gates()
    called = _gate_names_in(GITHUB) | _gate_names_in(GITCODE)
    assert called, "两份 yaml 都没调门禁"
    unknown = called - declared
    assert not unknown, f"CI 调了未声明的门禁名：{unknown}（可用：{sorted(declared)}）"


def test_gate_all_has_the_critical_gates():
    """关键门禁一个都不许从清单里消失（防止有人"精简"掉它们）。"""
    declared = _declared_gates()
    for must in ("lint", "copies", "secret", "tests"):
        assert must in declared, f"关键门禁 {must} 不在清单里"


def test_gate_script_is_runnable_and_lists_gates():
    """`--list` 必须能跑通并输出全部门禁名（CI 的第一步就是它）。"""
    import subprocess
    r = subprocess.run([sys.executable, str(GATE), "--list"], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    listed = set(r.stdout.split())
    assert listed == _declared_gates(), f"--list 输出与 GATES 不一致：{listed}"