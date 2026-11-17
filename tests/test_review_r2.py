"""评审第二轮的门禁（D-review-r2-1）：落点等价性 / 结构门口径 / provenance 假绿 / 子进程超时 / 死守卫。

这批全部来自 2026-11-16 的真机评审（基于 v0.5.28）：
  S162 落点的「不变量」：spec 的落点根必须恒等于 cli_env 的 HERMES_HOME —— 不按场景抽样，
       而是对 env 组合断言等式（S159 只锁了分场景，抓不到新组合又分叉）。
  S163 结构门禁不许给「自己刚改过的文件」打分：测试期的 sync 不得写 tracked 的根 build-info，
       判据口径按 release.sh 已有的 {v^, v} 集合走，而不是要求两份逐字相等。
  S164 provenance 的假绿面：两处 build-info 都读不到时不许报 OK；verify 的 preset 分支必须
       遍历**每一行**安装（旧实现只判 installs[-1]）。
  S165 hermes 的 `mcp add` 子进程必须有 timeout（空/异常 HERMES_HOME 下 CLI 会自举依赖挂住）。
  S166 `_guard_isolated_home()` 已是纯 no-op（每个分支只 return、无输出），留着误导后来人。
"""
import json
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("home_kind,hh_kind", [
    ("isolated", "outside"), ("isolated", "inside"), ("isolated", "unset"),
    ("real", "outside"), ("real", "unset"),
])
def test_s162_landing_parent_matches_cli_home(monkeypatch, tmp_path, home_kind, hh_kind):
    """S162：任意 env 组合下，文件落点根 == CLI 的 HERMES_HOME（不变量，不是抽样）。"""
    from vod_mcp.host_adapters import hermes

    if home_kind == "real":
        real = hermes._real_home()
        if real is None:                    # 平台无 pwd：跳过该组合
            pytest.skip("无 pwd，判不出真实家目录")
        home = real
    else:
        home = tmp_path / "home"
        home.mkdir()

    if hh_kind == "unset":
        monkeypatch.delenv("HERMES_HOME", raising=False)
    elif hh_kind == "inside":
        hh = home / "hermes-home"
        hh.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("HERMES_HOME", str(hh))
    else:
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "shared"))
    monkeypatch.setenv("HOME", str(home))

    spec_root = Path(hermes._spec()["configPath"]).parent.parent
    cli_root = Path(hermes._cli_env().get("HERMES_HOME") or (home / ".hermes"))
    assert spec_root == cli_root, (
        f"落点分裂：文件写 {spec_root}，CLI 写 {cli_root}（HOME={home}, "
        f"HERMES_HOME={hh_kind}）")


def test_s163_test_sync_must_not_write_tracked_build_info():
    """S163-1：测试期的 sync 不许改 tracked 的根 build-info（否则门禁在给自己打分）。

    机制（实测）：conftest 的 session 夹具调 sync()，它把根与插件副本都写成当前 HEAD；
    一旦走 VOD_DEVKIT_NO_BUILD_INFO（host_matrix 恒设 / CI 先 sync 再 pytest），两份停在
    v^ 与 HEAD，`test_build_info_root_and_plugin_copy_agree` 必红 —— 同一提交结果依赖执行顺序。
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_plugin

    root_bi = ROOT / "build-info.json"
    before = root_bi.read_bytes()
    sync_plugin.sync(ROOT, quiet=True, write_build_info=False)
    assert root_bi.read_bytes() == before, "测试期 sync 改写了 tracked 的根 build-info"
    assert json.loads(before)["version"], "根 build-info 本身必须仍可解释"


def test_s164_provenance_unreadable_is_reported(tmp_path, monkeypatch):
    """S164-1：载荷与仓根都读不到 build-info 时，必须报「无法核验」，不许静默 OK。"""
    from vodkit_cli import common, doctor

    monkeypatch.setattr(common, "ROOT", tmp_path)      # 仓根无 build-info
    payload = tmp_path / "payload"
    payload.mkdir()                                    # 载荷也无 build-info
    mf = {"source": {"commitSha": "a" * 40}, "payloadDir": str(payload)}
    problem = doctor._provenance_problem(mf)
    assert problem and "无法核验" in problem, problem


def test_s164_preset_walks_every_install_row(tmp_path, monkeypatch):
    """S164-2：preset 完整性必须遍历每一行安装（旧实现只判 installs[-1]）。"""
    from vodkit_cli import common, doctor

    root = tmp_path / "root"
    root.mkdir()
    (root / "build-info.json").write_text(
        json.dumps({"version": "1.0.0", "commitSha": "a" * 40}), encoding="utf-8")
    monkeypatch.setattr(common, "ROOT", root)

    p1, p2 = tmp_path / "p1", tmp_path / "p2"
    for p, sha in ((p1, "a" * 40), (p2, "b" * 40)):
        p.mkdir()
        (p / "build-info.json").write_text(
            json.dumps({"version": "1.0.0", "commitSha": sha}), encoding="utf-8")
    mf = {"installs": [
        {"target": "host-a", "payloadDir": str(p1), "source": {"commitSha": "a" * 40}},
        {"target": "host-b", "payloadDir": str(p2), "source": {"commitSha": "b" * 40}},
    ]}
    assert doctor._preset_provenance_problems(mf) == []

    mf["installs"][0]["source"]["commitSha"] = "c" * 40      # 破坏第一行（不是最后一行）
    problems = doctor._preset_provenance_problems(mf)
    assert problems and any("host-a" in p for p in problems), problems


def test_s165_hermes_mcp_add_has_timeout(monkeypatch, tmp_path):
    """S165：`hermes mcp add` 子进程必须有 timeout（远程面早有 180s，本地面没有）。

    PATH 前置桩：`remove_legacy_plugin()` 等处是裸 `subprocess.run(["hermes", …])`，
    不经过 `shutil.which`——只 patch which 会打到**真** hermes CLI 上（实测它在这里
    `completing source-update dependencies...` 挂满 60s）。
    """
    import os

    monkeypatch.setenv("HOME", str(tmp_path))
    from vod_mcp.host_adapters import hermes

    stub = tmp_path / "bin"
    stub.mkdir()
    fake = stub / "hermes"
    fake.write_text('#!/bin/sh\ncase "$1 $2" in\n  "mcp add") sleep 5 ;;\nesac\nexit 0\n', encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(stub) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(hermes, "_CLI_TIMEOUT", 1)
    args = types.SimpleNamespace(java_api_base="https://vod.example")

    t0 = time.time()
    conf = hermes.install(args, "core,collect")
    elapsed = time.time() - t0
    assert conf.exists(), "超时也要保住 JSON 片段（降级不失败）"
    assert elapsed < 6, f"mcp add 未受 timeout 约束（{elapsed:.1f}s）"


def test_s166_no_dead_isolated_guard():
    """S166：纯 no-op 的 `_guard_isolated_home()` 不许留着假装还有守卫。"""
    for rel in ("src/vod_mcp/host_adapters/hermes.py", "src/vodkit_cli/uninstall.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "_guard_isolated_home" not in text, (
            f"{rel} 仍引用死守卫；落点安全性由 _effective_hermes_home() 保证")

@pytest.mark.parametrize("hh_kind", ["container-mount", "gateway-leak", "inside-home"])
def test_s168_hermes_landing_three_way(monkeypatch, tmp_path, hh_kind):
    """S168：隔离 HOME 下的 HERMES_HOME 分三类——隔离根内的认、指向真实家的忽略、其余显式值认。

    上一轮（S161）只认「在隔离 HOME 之内」，把容器形态（HOME=/app、HERMES_HOME=/data/hermes
    挂载卷）的显式运维配置静默忽略：配置与技能写进镜像层，重建即丢，只剩一行 stderr。
    三分支各对应一个真实形态，且 CLI 与文件落点仍同源（不重新引入分裂）：
      1) 位于当前隔离 HOME 之内   → 认（矩阵 / 显式钉根）
      2) 位于真实家目录之下        → 忽略（网关派生的 HERMES_HOME=/root/.hermes 泄漏面）
      3) 其余                      → 认（容器挂载卷等显式配置）
    """
    from vod_mcp.host_adapters import hermes

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # 真实家目录用假的：pytest 的 tmp_path 落在 /root 下，用真 real 会把每个临时路径都判成
    # "位于真实家目录之下"（第 2 支），三分支的边界就测不出来。
    fake_real = tmp_path / "realhome"
    fake_real.mkdir()
    monkeypatch.setattr(hermes, "_real_home", lambda: fake_real)
    if hh_kind == "container-mount":
        hh = tmp_path / "data-hermes"
        hh.mkdir()
        expect_root = hh
    elif hh_kind == "gateway-leak":
        hh = fake_real / ".hermes"
        expect_root = home / ".hermes"
    else:
        hh = home / "pinned"
        hh.mkdir()
        expect_root = hh
    monkeypatch.setenv("HERMES_HOME", str(hh))

    spec_root = Path(hermes._spec()["configPath"]).parent.parent
    cli_root = Path(hermes._cli_env().get("HERMES_HOME") or (home / ".hermes"))
    assert spec_root == expect_root, f"{hh_kind}: 文件落点 {spec_root}，期望 {expect_root}"
    assert cli_root == expect_root, f"{hh_kind}: CLI 落点 {cli_root}，期望 {expect_root}"


def test_s169_sync_missing_copy_burns_head_not_root(tmp_path, monkeypatch):
    """S169：`--no-build-info` 下副本缺失时按**当前 HEAD** 烧副本，不拿根的发版快照顶替。

    旧实现按「根 build-info 的现有内容」补写副本：根是 v^ 发版快照时，副本会把自己标成 v^
    而代码是 HEAD —— 结构门禁查不出（sha 确实是真实提交），provenance 语义却错。
    触发面窄（副本被清 + 走 --no-build-info，如 CI 首跑/手删副本），但一旦发生就永久错标。
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_plugin

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "build-info.json").write_text(
        json.dumps({"version": "9.9.9", "commitSha": "a" * 40}), encoding="utf-8")
    root_before = (repo / "build-info.json").read_bytes()
    monkeypatch.setattr(sync_plugin, "_git", lambda args, root: "b" * 40)
    monkeypatch.setattr(sync_plugin, "_version_from_init", lambda p: "9.9.9")

    sync_plugin.sync(repo, quiet=True, write_build_info=False)

    pkg = json.loads((repo / "plugins/vod-devkit/build-info.json").read_text(encoding="utf-8"))
    assert pkg["commitSha"] == "b" * 40, f"副本应标当前 HEAD，实际 {pkg['commitSha']}"
    assert (repo / "build-info.json").read_bytes() == root_before, "根 build-info 不许被改"


def test_s170_local_mcp_add_must_be_read_back(monkeypatch, tmp_path):
    """S170：本地注册不能只看 rc==0——交互确认被跳过时 hermes 仍 exit 0 但不落配置。

    实测（2026-11-17）：PATH 里桩 hermes 对 `mcp add` 返回 0 且不改 config.yaml，install 仍
    rc=0 并打印「已注册」，config.yaml 只有 hooks 段 → 用户侧「工具连不上、自检全绿」。
    远端点（install_remote）早有读回 + exit 1，本地这条缺同款。
    """
    import os

    monkeypatch.setenv("HOME", str(tmp_path))
    from vod_mcp.host_adapters import hermes

    stub = tmp_path / "bin"
    stub.mkdir()
    fake = stub / "hermes"
    fake.write_text(
        "#!/bin/sh\ncase \"$1 $2\" in\n  \"config get\") echo \"\" ;;\nesac\nexit 0\n",
        encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(stub) + os.pathsep + os.environ.get("PATH", ""))
    args = types.SimpleNamespace(java_api_base="https://vod.example")

    with pytest.raises(SystemExit) as exc:
        hermes.install(args, "core,collect")
    assert exc.value.code == 1, "rc=0 但配置无条目 → 必须非零退出，不能静默成功"


def test_s171_remote_readback_uses_spec_profile_config(monkeypatch, tmp_path):
    """S171：读回函数必须走 _spec()["profileConfig"]，不许再用 Path.home()/.hermes。

    实测：HOME=…/home、HERMES_HOME=…/home/custom-hermes、config.yaml 里有 url 条目，
    读回仍返回 False —— 自定义 HERMES_HOME（隔离/容器/数据盘）时远程安装被自己判失败。
    """
    from vod_mcp.host_adapters import hermes

    home = tmp_path / "home"
    hh = home / "custom-hermes"
    hh.mkdir(parents=True)
    url = "http://127.0.0.1:9528/mcp"
    (hh / "config.yaml").write_text(
        f"mcp_servers:\n  vod-devkit:\n    url: {url}\n    enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(hh))
    assert hermes._hermes_registration_is_remote(url) is True


def test_s172_doctor_flags_missing_hermes_entry(monkeypatch, tmp_path):
    """S172：doctor 必须校验 configPath 里真有 mcp_servers.vod-devkit。

    无 CLI 的降级安装只写备片 + hooks，config.yaml 没有 mcp_servers —— 旧 doctor 报 OK，
    用户看到「自检全绿但工具连不上」。处置取「检测 + 报告」：不自动写宿主主配置（那条写入
    目前非原子，半截 YAML 会让宿主起不来）。
    """
    from vodkit_cli import doctor

    home = tmp_path / "home"
    (home / ".hermes").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    mf = {"target": "hermes", "installs": [{"target": "hermes"}]}

    problem = doctor._host_verify_problems(mf)
    assert problem and any("mcp_servers" in p for p in problem), problem

    (home / ".hermes" / "config.yaml").write_text(
        "mcp_servers:\n  vod-devkit:\n    command: x\n", encoding="utf-8")
    assert doctor._host_verify_problems(mf) == []


def test_s173_degraded_install_exits_zero_but_says_missing(monkeypatch, tmp_path, capsys):
    """S173：无 CLI 的降级安装仍是 rc=0（片段已写），但必须**明说**没注册。

    与 S170 分界：没有写入动作发生（无 CLI）≠ 写入动作发生了却没落盘。
    前者不该让 install 失败（用户可能压根没装宿主），但静默成功正是本轮 bug 的一半；
    文案与 doctor 同源（host_verify 的 missing 码），两侧不会各说一套。
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))   # 空目录：没有 hermes CLI
    from vod_mcp.host_adapters import hermes, host_verify

    args = types.SimpleNamespace(java_api_base="https://vod.example")
    conf = hermes.install(args, "core,collect")          # 不许抛 SystemExit
    err = capsys.readouterr().err
    assert conf.is_file(), "降级也要写出备片 JSON"
    assert "缺 mcp_servers.vod-devkit" in err and "手工" in err, err
    assert host_verify.problems("hermes", degraded=True)[0]["code"] == "missing"
