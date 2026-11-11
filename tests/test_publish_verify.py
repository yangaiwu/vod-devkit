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
# npm view <pkg> <field> --json
pkg="$2"; field="$3"
case "$field" in
  version)
    f="$STUB_DIR/version_$pkg"
    [ -f "$f" ] && cat "$f" || echo '"0.0.0"'
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
        "package/vod_mcp/server.py": "print('srv')\n",
        "package/vod_mcp/pending.py": "print('pending')\n",
        "package/vod_mcp/config_forms.py": "print('forms')\n",
        "package/contract/tools.schema.json": json.dumps({"version": version}),
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
    assert "未上线" in r.stderr and "0.4.2" in r.stderr


def test_fail_when_tarball_misses_a_module(tmp_path):
    """files 白名单漏新模块（0.4.1 缺 pending.py 的形态）。"""
    members = _good_members()
    members.pop("package/vod_mcp/pending.py")
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