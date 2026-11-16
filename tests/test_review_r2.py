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