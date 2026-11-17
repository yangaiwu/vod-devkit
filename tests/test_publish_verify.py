"""发版终态断言的回归锁（scripts/publish_verify.py）。

事故：v0.4.2 tag 推了、npm 没上——`publish 回执成功` 与会话横幅都不是证据。
本脚本挡住三类：registry 没上线、包内容缺文件（files 白名单漏）、契约版本
漏同步。这里用桩 npm + 自制 tarball 把三条路径都跑真（零网络）。
"""
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "publish_verify.py"

STUB_NPM = """#!/bin/sh
# npm view <pkg>[@ver] <field> --json
pkg="$2"; field="$3"
case "$pkg" in
  *@*) base="${pkg%%@*}"; ver="${pkg#*@}" ;;
  *)   base="$pkg";       ver="" ;;
esac
case "$field" in
  version)
    if [ -n "$ver" ]; then
      f="$STUB_DIR/specific_${base}_${ver}"
      [ -f "$f" ] && cat "$f" || echo '""'
    else
      f="$STUB_DIR/version_$base"
      [ -f "$f" ] && cat "$f" || echo '"0.0.0"'
    fi
    ;;
  dist.tarball)
    f="$STUB_DIR/tarball_$pkg"
    [ -f "$f" ] && printf '"%s"\\n' "$(cat "$f")" || echo '""'
    ;;
  *) echo '""' ;;
esac
"""


def _make_tarball(path, members):
    with tarfile.open(path, "w:gz") as tf:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def _env(tmp_path, versions, tarballs):
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    npm = stub / "npm"
    npm.write_text(STUB_NPM)
    npm.chmod(0o755)
    for pkg, ver in versions.items():
        (tmp_path / f"version_{pkg}").write_text(json.dumps(ver))
    for pkg, p in tarballs.items():
        (tmp_path / f"tarball_{pkg}").write_text("file://" + str(p))
    e = os.environ.copy()
    e["PATH"] = f"{stub}{os.pathsep}{e['PATH']}"
    e["STUB_DIR"] = str(tmp_path)
    return e


def _run(env, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=env, timeout=120)


def _good_members(version="0.4.5"):
    return {
        "package/src/vod_mcp/server.py": "print('srv')\n",
        "package/src/vod_mcp/pending.py": "print('pending')\n",
        "package/src/vod_mcp/config_forms.py": "print('forms')\n",
        "package/assets/contract/tools.schema.json": json.dumps({"version": version}),
    }


def test_pass_when_registry_and_tarball_match(tmp_path):
    tgz = tmp_path / "good.tgz"
    _make_tarball(tgz, _good_members("0.4.5"))
    env = _env(tmp_path, {"vod-devkit": "0.4.5"},
               {"vod-devkit": tgz})
    r = _run(env, "--version", "0.4.5", "--pkg", "vod-devkit",
             "--timeout", "2", "--interval", "0.1")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "已上线" in r.stdout and "内容与版本已核验" in r.stdout


def test_fail_when_registry_still_on_old_version(tmp_path):
    """核心场景：publish 回执成功但 registry/CDN 还是旧版（v0.4.2 形态）。"""
    tgz = tmp_path / "good.tgz"
    _make_tarball(tgz, _good_members())
    env = _env(tmp_path, {"vod-devkit": "0.4.2"}, {"vod-devkit": tgz})
    r = _run(env, "--version", "0.4.5", "--pkg", "vod-devkit",
             "--timeout", "0.5", "--interval", "0.1")
    assert r.returncode == 1
    assert "查不到 0.4.5" in r.stderr and "0.4.2" in r.stderr


def test_fail_when_tarball_misses_a_module(tmp_path):
    """files 白名单漏新模块（0.4.1 缺 pending.py 的形态）。"""
    members = _good_members()
    members.pop("package/src/vod_mcp/pending.py")
    tgz = tmp_path / "bad.tgz"
    _make_tarball(tgz, members)
    env = _env(tmp_path, {"vod-devkit": "0.4.5"}, {"vod-devkit": tgz})
    r = _run(env, "--version", "0.4.5", "--pkg", "vod-devkit",
             "--timeout", "2", "--interval", "0.1")
    assert r.returncode == 1
    assert "pending.py" in r.stderr


def test_fail_when_contract_version_not_synced(tmp_path):
    """契约 version 落点漏同步（版本三处同步静默 no-op 的家族）。"""
    members = _good_members("0.4.4")
    tgz = tmp_path / "stale.tgz"
    _make_tarball(tgz, members)
    env = _env(tmp_path, {"vod-devkit": "0.4.5"}, {"vod-devkit": tgz})
    r = _run(env, "--version", "0.4.5", "--pkg", "vod-devkit",
             "--timeout", "2", "--interval", "0.1")
    assert r.returncode == 1
    assert "契约版本" in r.stderr


def test_skip_tarball_mode_only_checks_version(tmp_path):
    env = _env(tmp_path, {"vod-devkit": "0.4.5"}, {})
    r = _run(env, "--version", "0.4.5", "--pkg", "vod-devkit",
             "--timeout", "2", "--interval", "0.1", "--skip-tarball")
    assert r.returncode == 0, (r.stdout, r.stderr)

def test_pass_when_target_version_visible_but_latest_lags(tmp_path):
    """v0.5.3 形态：包已上线（目标版本可查），latest 还停在旧版 → 不该判失败。"""
    tgz = tmp_path / "good.tgz"
    _make_tarball(tgz, _good_members())
    env = _env(tmp_path, {"vod-devkit": "0.4.2"}, {"vod-devkit": tgz})
    (tmp_path / "specific_vod-devkit_0.4.5").write_text(json.dumps("0.4.5"))
    r = _run(env, "--version", "0.4.5", "--pkg", "vod-devkit",
             "--timeout", "2", "--interval", "0.1")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "dist-tag latest 仍指向 0.4.2" in r.stdout


# --- S213：registry 查询超时 ≠ 未发布（发版脚本不许把网络抖动判成业务失败）-------------
# 实锤（2026-11-17 0.5.33）：两颗包都已 publish 成功、tarball 200，但
# `npm view vod-devkit version --json` 一次 60s 超时 → publish_verify 抛 TimeoutExpired
# （裸 traceback）→ release.sh 打出 "FAIL: 发版终态断言未过"，RELEASE_RC=1。
# 这与 S187（引擎 502 打断整轮 e2e）是同一类错：把**不可判**当成了**失败**。
def test_s213_npm_view_retries_on_timeout(monkeypatch):
    import subprocess
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import publish_verify as pv

    calls = {"n": 0}

    def fake_run(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd="npm", timeout=kw.get("timeout", 60))
        class R:
            returncode = 0
            stdout = '"0.5.33"'
        return R()

    monkeypatch.setattr(pv.subprocess, "run", fake_run)
    monkeypatch.setattr(pv.time, "sleep", lambda *_: None)
    assert pv._npm_view("vod-devkit", "version") == "0.5.33"
    assert calls["n"] == 2, "第一次超时必须重试"


def test_s213_indeterminate_is_not_failure(monkeypatch):
    import subprocess
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import publish_verify as pv

    def always_timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="npm", timeout=kw.get("timeout", 60))

    monkeypatch.setattr(pv.subprocess, "run", always_timeout)
    monkeypatch.setattr(pv.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sys, "argv",
                        ["publish_verify.py", "--version", "0.5.33", "--pkg", "vod-devkit",
                         "--timeout", "1", "--interval", "0"])
    rc = pv.main()
    assert rc == 3, f"不可判必须是 3（不是 1=失败）：{rc}"
