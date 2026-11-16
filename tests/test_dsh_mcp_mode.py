"""dsh B 模式（D-dsh-mcp-b-1）：工具面走 @deepseek-ai/dsh-mcp-client，壳只留 UI。

锁定四件：
1. 有 mcp-client → 托管块里两条 insert 子项（mcp-client + 壳），壳 config 写
   registerTools=false、env 显式带 VOD_DEVKIT_HOME/VOD_JAVA_API_BASE/VOD_PACKS；
2. 无 mcp-client（或显式跳过自装）→ 降级成壳工具面（无 mcp 块、registerTools 不写）；
3. 幂等：重复 install 只有一份托管块；uninstall 只摘自己那块（用户其它内容不动）；
4. `- id: vod-devkit-mcp` 不得被旧的前缀匹配当成 vod-devkit（否则 classify refuse）。
"""
import json

from tests.test_installer import cli
from tests.test_installer import env as _installer_env_fixture
from tests.test_installer import engine_stub as _engine_stub_fixture  # env 依赖它，须同册

env = _installer_env_fixture
engine_stub = _engine_stub_fixture

MC_PKG = "@deepseek-ai/dsh-mcp-client"


def _dsh_stub(env) -> None:
    """PATH 里放一个 dsh 桩：否则 shutil.which('dsh') 落到**真机** dsh，
    版本探测会读到真机的 mcp-client（实测：降级用例被误判成 MCP 模式）。"""
    s = env["stub"] / "dsh"
    s.write_text("#!/bin/sh\necho \"$@\" >> " + str(env["stub"].parent / "dsh-calls.log")
                 + "\nexit 0\n", encoding="utf-8")
    s.chmod(0o755)


def _fake_dsh_root(env) -> None:
    """桩 dsh 在 <tmp>/bin/dsh → 本体根 = <tmp>；mcp-client 装在本体 node_modules。"""
    _dsh_stub(env)
    root = env["stub"].parent
    d = root / "node_modules" / "@deepseek-ai" / "dsh-mcp-client"
    d.mkdir(parents=True, exist_ok=True)
    (d / "package.json").write_text(json.dumps({"version": "0.2.1-rc.5"}), encoding="utf-8")


def _patch_path(env):
    """profile patch 落点：~/.dsh/profiles/<p>/cordis.patch.yml（HOME=fake home）。

    直接按 home 推导，不走 hosts.load——后者读的是**当前进程** HOME，
    测试里切 HOME 容易读到真机 profile（同类事故本仓实锤过）。
    """
    return env["home"] / ".dsh" / "profiles" / "web" / "cordis.patch.yml"


def _read_patch(env) -> str:
    p = _patch_path(env)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_dsh_mcp_mode_writes_two_inserts_and_ui_only_shell(env):
    _fake_dsh_root(env)
    r = cli(env, "install", "--target", "dsh", "--profile", "web",
            "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    text = _read_patch(env)
    assert "# vod-devkit DSH integration start" in text
    assert "# vod-devkit DSH integration end" in text
    assert "    - id: vod-devkit-mcp" in text, "工具面必须挂 mcp-client"
    assert "    - id: vod-devkit\n" in text, "壳块要保留（UI 半）"
    assert "registerTools: false" in text, "壳不得再注册工具（避免双注册/双 submit）"
    assert f"name: '{MC_PKG}'" in text
    assert "serverName: vod-devkit" in text
    assert "VOD_DEVKIT_HOME:" in text and "VOD_JAVA_API_BASE:" in text and "VOD_PACKS:" in text
    assert "MCP（mcp-client@0.2.1-rc.5" in r.stdout


def test_dsh_degrades_to_shell_tools_without_mcp_client(env):
    # 桩 dsh（不造 mcp-client）；并用 env 关掉自装（否则桩会把"装成功"当成模块在）
    _dsh_stub(env)
    e = dict(env["env"])
    e["VOD_DSH_SKIP_MCP_CLIENT_ADD"] = "1"
    env2 = dict(env, env=e)
    r = cli(env2, "install", "--target", "dsh", "--profile", "web",
            "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    text = _read_patch(env2)
    assert "# vod-devkit DSH integration start" in text
    assert "- id: vod-devkit-mcp" not in text, f"无 client 不得写 MCP 块；installer stdout={r.stdout!r}"
    assert "registerTools" not in text, "降级形态保持壳注册（缺省 true）"
    assert "壳自注册（降级：6 工具）" in r.stdout


def test_dsh_plugin_add_pins_installer_version(env):
    """`dsh plugin add` 必须钉死到安装器版本：profile 的 package.json 是精确版本，
    不带版本的 add 会被 pnpm 当成"已满足"跳过 → 升级时装到旧壳（真机 0.5.10 实锤：
    patch 写了 registerTools:false，壳里根本没这个字段，工具面静默双注册）。"""
    _dsh_stub(env)
    assert cli(env, "install", "--target", "dsh", "--profile", "web",
               "--product", "CodeArts").returncode == 0
    calls = (env["stub"].parent / "dsh-calls.log").read_text(encoding="utf-8")
    from vod_mcp import __version__
    assert f"add dsh-vod-devkit@{__version__}" in calls, calls


def test_dsh_managed_block_is_idempotent(env):
    _fake_dsh_root(env)
    assert cli(env, "install", "--target", "dsh", "--profile", "web",
               "--product", "CodeArts").returncode == 0
    first = _read_patch(env)
    assert cli(env, "install", "--target", "dsh", "--profile", "web",
               "--product", "CodeArts").returncode == 0
    second = _read_patch(env)
    assert second == first, "重复安装不得产生第二份块"
    assert second.count("# vod-devkit DSH integration start") == 1
    assert second.count("    - id: vod-devkit-mcp") == 1


def test_dsh_uninstall_removes_only_managed_block(env):
    _fake_dsh_root(env)
    assert cli(env, "install", "--target", "dsh", "--profile", "web",
               "--product", "CodeArts").returncode == 0
    p = _patch_path(env)
    p.write_text(p.read_text(encoding="utf-8") + "- insert:\n    - id: someone-else\n",
                 encoding="utf-8")
    r = cli(env, "uninstall", "--target", "dsh")
    assert r.returncode == 0, r.stderr
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    assert "# vod-devkit DSH integration start" not in text
    assert "vod-devkit-mcp" not in text
    assert "someone-else" in text, "别人的块必须原样保留"


def test_config_forms_distinguishes_mcp_id_from_shell_id():
    """`- id: vod-devkit-mcp` 与 `- id: vod-devkit` 必须判成不同条目。"""
    from vod_mcp import config_forms as cf
    lines = ["- insert:", "    - id: vod-devkit-mcp", "    - id: vod-devkit"]
    verdict, reason = cf.classify_dsh_patch(lines)
    assert verdict == "ok", reason
    start, end = cf.find_dsh_block(lines)
    assert (start, end) == (0, 3), "无标记旧形态：向上归并到组头，整组一块"
    assert cf._is_dsh_id_line("- id: vod-devkit") is True
    assert cf._is_dsh_id_line("- id: vod-devkit-mcp") is False


def test_dsh_skips_mcp_install_when_registry_unreachable(env):
    """registry 不可达时不跑 pnpm（否则离线机器要挂满子进程超时才降级），直接降级。
    PATH 只留桩目录 → 子进程里 npm 不可见，等价于离线机器。"""
    _dsh_stub(env)
    e = dict(env["env"])
    # 桩目录 + 系统目录：有 git（安装器要用），但没有 npm（node 装在 /usr/local/bin）
    e["PATH"] = str(env["stub"]) + ":/usr/bin:/bin"
    env2 = dict(env, env=e)
    r = cli(env2, "install", "--target", "dsh", "--profile", "web", "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    text = _read_patch(env2)
    assert "- id: vod-devkit-mcp" not in text, "registry 不可达时不得写 MCP 块"
    assert "registry 不可达" in r.stderr, r.stderr


def test_doctor_reports_unreferenced_payloads(env):
    """载荷并存要可见：旧版本目录留在盘上，doctor 报出来并明确"不自动删"。"""
    _dsh_stub(env)
    assert cli(env, "install", "--target", "dsh", "--profile", "web",
               "--product", "CodeArts").returncode == 0
    pdir = env["home"] / ".vod-devkit" / "payloads"
    (pdir / "0.0.1").mkdir(parents=True, exist_ok=True)
    r = cli(env, "doctor")
    out = (r.stdout or "") + (r.stderr or "")
    assert "未被任何安装行引用" in out and "0.0.1" in out, out
    assert "不自动删" in out, out