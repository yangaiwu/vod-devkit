"""插件副本零提交（D-copies-generated-1）的场景级护栏。

对应场景：S103（副本零提交）/ S104（单一生成入口·fresh clone）/ S106（发版顺序）/
S107（指纹区间）/ S110（消费入口兜底 sync）。内容一致与漂移判定在
tests/test_verify_copies.py（S105）。

为什么单独成文件：这批断言讲的不是某个函数的行为，而是**仓库形态**——
「哪份文件才是真值、生成物从哪来、发版在哪个点复验」。它一旦回退，
单测全绿也挡不住（v0.5.8 就是所有门禁全绿却 tarball ≠ tag）。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sync_plugin  # noqa: E402
import verify_copies as vc  # noqa: E402

COPY_DIRS = [dst for _, dst in sync_plugin.PAIRS]


def _bootstrap_repo(base: Path) -> Path:
    """造一个最小仓：四个源目录 + 版本号，副本刻意不存在（等价 fresh clone）。"""
    (base / "src" / "vod_mcp").mkdir(parents=True)
    (base / "src" / "vod_mcp" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    (base / "src" / "vod_mcp" / "server.py").write_text("print('hi')\n", encoding="utf-8")
    for rel in ("assets/skills/core", "assets/contract", "assets/safety"):
        (base / rel).mkdir(parents=True, exist_ok=True)
        (base / rel / "f.txt").write_text("x\n", encoding="utf-8")
    (base / "src" / "vod_mcp" / "runtime.json").write_text('{"java_key": "secret"}\n', encoding="utf-8")
    return base


def test_S103_copies_are_not_tracked_by_git():
    """S103：副本零提交——.gitignore 覆盖四目录与插件 build-info，git 里一条都没有。"""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rel in COPY_DIRS:
        assert rel + "/" in ignore, f".gitignore 漏了 {rel}"
    assert "plugins/vod-devkit/build-info.json" in ignore, ".gitignore 漏了插件 build-info"
    assert vc.tracked_paths(ROOT, COPY_DIRS) == [], "副本又被 git 跟踪了（两份真值复活）"


def test_S104_single_generator_rebuilds_from_fresh_clone(tmp_path):
    """S104：单一入口——无副本的干净检出跑一次 sync 即可自足，且幂等。"""
    repo = _bootstrap_repo(tmp_path / "repo")
    for rel in COPY_DIRS:
        assert not (repo / rel).exists(), "fresh clone 不该带副本"

    bi = sync_plugin.sync(repo, quiet=True)
    assert bi["version"] == "9.9.9"
    assert json.loads((repo / "plugins/vod-devkit/build-info.json").read_text())["version"] == "9.9.9"
    assert (repo / "plugins/vod-devkit/vod_mcp/runtime.json").exists() is False, \
        "runtime.json 带 key/账本，绝不能进副本"
    assert vc.check(repo, git_check=False) == []

    # 再跑一次：幂等（内容仍一致），不残留第二次的差异
    sync_plugin.sync(repo, quiet=True)
    assert vc.check(repo, git_check=False) == []


def test_S104_packaging_runs_generator_before_pack():
    """S104：npm 打包/发布路径自动重跑生成器——不靠人记得先 sync。"""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    prepack = (pkg.get("scripts") or {}).get("prepack", "")
    assert "sync_plugin.py" in prepack, f"prepack 没挂生成器：{prepack!r}"
    files = pkg.get("files") or []
    for rel in ("plugins/vod-devkit/vod_mcp", "plugins/vod-devkit/skills",
                "plugins/vod-devkit/contract", "plugins/vod-devkit/safety",
                "plugins/vod-devkit/build-info.json"):
        assert rel in files, f"npm files 白名单漏了生成物 {rel}"


def test_S106_release_verifies_after_commit_before_tag():
    """S106：发版顺序锁——提交之后、打 tag 之前复验；顺序反了等于没防（v0.5.8 教训）。"""
    sh = (ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    i_commit = sh.index('git commit -qm "release: v$BUMP"')
    i_tag = sh.index('git tag "v$BUMP"')
    # 发版起点还有一次前置门禁（sync 之后），这里要的是**提交之后**那一处：
    # 从 commit 位置往后找，不能拿全文第一个匹配（v0.5.9 实锤：会命中前置那次）。
    i_verify = sh.find("scripts/verify_copies.py", i_commit)
    assert i_verify != -1, "提交之后没有复验（sync 了但没提交这一类就抓不到了）"
    assert i_commit < i_verify < i_tag, (
        f"发版复验位置不对（commit={i_commit} verify={i_verify} tag={i_tag}）："
        "必须在提交之后、打 tag 之前")


def test_S107_tarball_fingerprint_accepts_release_commit_or_parent():
    """S107：prepack 重跑 sync 后 build-info 指向发版提交；断言必须接受 {tag^, tag}。"""
    sh = (ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    assert 'TAG_COMMIT=$(git rev-parse "v$BUMP")' in sh, "没有取发版提交 sha"
    assert '"$BI_SHA" != "$TAG_PARENT"' in sh and '"$BI_SHA" != "$TAG_COMMIT"' in sh, \
        "指纹断言不是区间断言（只认父提交会在 prepack 后误杀）"


def test_S110_consumers_sync_before_reading_copies():
    """S110：仓内消费入口（测试/矩阵/安装器）在读副本前各自兜底一次 sync。"""
    targets = {
        "tests/conftest.py": "sync_plugin",
        "scripts/host_matrix.py": "sync_plugin",
        "src/vod_mcp/host_adapters/codex.py": "sync_plugin.py",
    }
    for rel, needle in targets.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel} 没有副本缺失时的兜底 sync（{needle}）"


def test_S105_gate_is_single_entry_shared_by_ci_hook_and_release():
    """S105：一致性门禁只有一个入口，三处都调它（各写一份 diff = 迟早各错各的）。

    ARCH-BLD-01（2026-11-19）后入口层次变了：CI 不再直接写 `verify_copies.py`，
    而是调统一的 `gate_all.py copies`（门禁清单单一真源）。S105 的**意图不变**
    ——"只有一个实现入口、多处引用"——所以这里改为断言：CI 调 gate_all 的 copies
    门禁，而 `gate_all.py` 内部必须走 `verify_copies.py`（不许自己拼 diff）。
    """
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    gc = (ROOT / ".gitcode" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    gate = (ROOT / "scripts" / "gate_all.py").read_text(encoding="utf-8")
    hook = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    rel = (ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")

    # 门禁实现本身必须走单入口
    assert "verify_copies.py" in gate, "gate_all.py 的 copies 门禁没走 verify_copies 单入口"
    assert "diff -r" not in gate, "gate_all.py 自己拼 diff -r（会与门禁分叉）"

    # CI 两份都要调 copies 门禁
    for name, text in (("github ci.yml", ci), ("gitcode ci.yml", gc)):
        assert "gate_all.py" in text and "copies" in text, f"{name} 没调 copies 门禁"

    # pre-push 与 release.sh 仍直调（它们不受 gate_all 管辖）
    for name, text in (("pre-push", hook), ("release.sh", rel)):
        assert "verify_copies.py" in text, f"{name} 没走 verify_copies 单入口"

    assert "diff -r" not in ci, "ci.yml 还在自己拼 diff -r（会与门禁分叉）"
    assert "diff -r" not in hook, "pre-push 还在自己拼 diff -r"


@pytest.mark.parametrize("dst", COPY_DIRS)
def test_S103_each_copy_dir_is_ignored(dst):
    """S103（逐目录）：四个目录各自被忽略——漏一个就漏一个漂移面。"""
    assert dst + "/" in (ROOT / ".gitignore").read_text(encoding="utf-8")

def test_version_parser_handles_annotated_form(tmp_path):
    """ARCH-BLD-07 验收：`__version__` 解析必须吃得住类型注解/单引号，且坏文件要显式失败。

    历史形态：`split('__version__ = "')[1]` —— 写成 `__version__: str = "0.5.48"`
    就 IndexError；改成单引号就取到空串。而用例用桩绕过了这条路径，发版时才炸。
    """
    import importlib.util
    import pathlib as _p

    root = _p.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("vdk_sync_plugin", root / "scripts" / "sync_plugin.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cases = {
        '__version__ = "1.2.3"\n': "1.2.3",
        '__version__: str = "1.2.4"\n': "1.2.4",
        "__version__ = '1.2.5'\n": "1.2.5",
        '__version__ : str = "1.2.6"  # 行尾注释\n': "1.2.6",
    }
    for i, (text, want) in enumerate(cases.items()):
        f = tmp_path / f"init_{i}.py"
        f.write_text(text, encoding="utf-8")
        assert mod._version_from_init(f) == want, (text, want)

    bad = tmp_path / "bad.py"
    bad.write_text("VERSION = '1.0.0'\n", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        mod._version_from_init(bad)
