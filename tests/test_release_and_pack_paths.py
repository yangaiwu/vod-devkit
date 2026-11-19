"""发版链路路径锁（S3-A 后的回归门）。

守两类事故，都是"本地 pytest 全绿、发版/CI 才炸"：
1. 脚本里还钉着迁移前的路径（`vod_mcp/`、`contract/`、`dsh/`）——S3-A 实测：
   release.sh、pack_verify、publish_verify、e2e_nightly 全都还写旧路径，
   registry_reconcile 甚至在 GitHub CI 上直接红。
2. npm 包把字节码/缓存带进 tarball——整目录白名单会把 `__pycache__` 一起打包，
   实测 0.5.9 包内 51 个 .pyc（根 `.npmignore` 对 files 白名单不生效，
   必须目录内嵌套）。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 迁移后不该再出现在"源码路径"语境里的前缀（载荷/插件副本里的平铺路径是另一回事，
# 那些写法是 `<root>/vod_mcp`，不会带 `vod_mcp/` 前导斜杠语境；这里只锁脚本常量）
FORBIDDEN_PATTERNS = [
    # 裸前缀：`"vod_mcp/server.py"` 命中；`src/vod_mcp`、`plugins/vod-devkit/vod_mcp` 不命中
    r'(?<![/\w])vod_mcp/',       
    r'"contract/tools\.schema\.json"',
    r'"dsh/package\.json"',
    r'\bcd dsh\b',
    r'"dsh/dsh-vod-devkit',
    r"hermes-plugin",
    r"/root/vod-devkit/vod_mcp/",
]


def test_release_and_verify_scripts_have_no_pre_s3_paths():
    offenders = []
    targets = [(ROOT / "scripts" / n) for n in
               ("release.sh", "pack_verify.py", "publish_verify.py", "e2e_nightly.py")]
    targets.append(ROOT / ".githooks" / "pre-push")
    for path in targets:
        name = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        for pat in FORBIDDEN_PATTERNS:
            for m in re.finditer(pat, text):
                # 允许注释里说明历史（以 # 开头的行）
                line = text[text.rfind("\n", 0, m.start()) + 1: text.find("\n", m.start())]
                if line.lstrip().startswith("#"):
                    continue
                offenders.append(f"{name}: {line.strip()[:80]}")
    assert not offenders, "发版脚本仍钉着迁移前路径：\n  " + "\n  ".join(offenders)


def test_release_version_landings_exist():
    """release.sh 的版本落点必须在真实树里存在（路径搬家后忘改=静默不 bump）。"""
    text = (ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    landings = set(re.findall(r'sub_line\("([^"]+)"', text))
    landings |= set(re.findall(r'\n\s*\("([^"]+\.json)", "json"\)', text))
    assert landings, "没解析到任何版本落点——release.sh 结构变了，调整本用例"
    missing = sorted(l for l in landings if not (ROOT / l).exists())
    assert not missing, f"版本落点不存在：{missing}"


@pytest.mark.skipif(shutil.which("npm") is None, reason="本机无 npm，跳过打包内容检查")
def test_npm_pack_contains_no_bytecode():
    r = subprocess.run(["npm", "pack", "--dry-run", "--json"], cwd=ROOT,
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        pytest.skip(f"npm pack 不可用：{r.stderr[-200:]}")
    files = [f["path"] for f in json.loads(r.stdout)[0]["files"]]
    bad = [f for f in files if "__pycache__/" in f or f.endswith(".pyc")]
    assert not bad, f"tarball 里混入字节码（整目录白名单 + 缺 .npmignore）：{bad[:5]}"
    must = ["package.json", "bin/vod-devkit", "src/vod_mcp/server.py",
            "src/vodkit_cli/cli.py", "assets/contract/tools.schema.json",
            "integrations/hermes/hooks/vod_router.py",
            "plugins/vod-devkit/vod_mcp/server.py"]
    missing = [m for m in must if m not in files]
    assert not missing, f"tarball 缺关键文件：{missing}"

# ---- ARCH-BLD-05：pre-push 未接线 + 作者机绝对路径 ----

def test_pre_push_has_no_author_paths():
    """pre-push 里不许出现作者机绝对路径（原 `/root/.hermes/...` 两处 + 硬编码 /tmp 日志）。

    台账 ARCH-BLD-05 实锤：新克隆在别人机器上跑，`PY` 会静默回落 `python3`
    （版本可能不符契约），失败原因会被误判成环境问题。
    """
    src = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    bad = [p for p in ("/root/.hermes", "/home/", "C:\\Users") if p in src]
    assert not bad, f"pre-push 含作者机绝对路径：{bad}"
    # 找不到解释器必须显式失败，而不是静默继续（原形态是 `|| command -v python3` 兜底）
    assert "找不到 python3" in src, "解释器缺失时应显式失败并给出可读原因"


def test_hook_install_script_is_idempotent(tmp_path):
    """`scripts/install_hooks.py` 必须幂等，且只改本仓（不 --global）。

    用临时 git 仓实测两次调用：第一次接线、第二次报「已接线」且不改动配置。
    """
    script = ROOT / "scripts" / "install_hooks.py"
    assert script.exists(), "缺 scripts/install_hooks.py（BLD-05 整改措施）"

    repo = tmp_path / "hookrepo"
    repo.mkdir()
    (repo / ".githooks").mkdir()
    hook = repo / ".githooks" / "pre-push"
    hook.write_text("#!/bin/bash\nexit 0\n")
    hook.chmod(0o644)                      # 故意不给执行位，验证安装器会补
    (repo / "scripts").mkdir()
    shutil.copy2(script, repo / "scripts" / "install_hooks.py")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    def _run(*extra):
        # 脚本按 __file__ 定位 ROOT，所以复制一份到临时仓里跑，才是真的「在别人的克隆上安装」
        return subprocess.run(["python3", "scripts/install_hooks.py", *extra],
                              cwd=repo, capture_output=True, text=True)

    first = _run()
    assert first.returncode == 0, first.stderr
    cfg = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    assert cfg == ".githooks", f"core.hooksPath 未接线：{cfg!r}"
    assert hook.stat().st_mode & 0o111, "安装器未补执行位（git 会静默跳过该钩子）"
    # 不许写 --global
    glb = subprocess.run(["git", "config", "--global", "--get", "core.hooksPath"],
                         capture_output=True, text=True).stdout.strip()
    assert glb != ".githooks", "安装器污染了 --global 配置（会影响用户其他仓库）"

    second = _run()
    assert second.returncode == 0, second.stderr
    assert "已接线" in second.stdout, f"第二次调用不幂等：{second.stdout!r}"
    # --check 也必须绿
    assert _run("--check").returncode == 0
