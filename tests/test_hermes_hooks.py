"""Hermes hooks/插件那一半的回归锁：路由插件安装 + plugins.enabled 自动启用。

负责人要求宿主覆盖里「hermes（含 hooks / hook 插件）」也要具备。上一版只把插件
目录拷到 ~/.hermes/plugins 并打印"请手动加进 plugins.enabled"——等于装了一半：
插件在盘上但不生效。这里锁住自动启用且幂等的三条：
- 名单里没有 → set 一次，把现有名字全部保留（不覆盖用户已有的插件）
- 名单里已有 → 不再 set（vacuous write 会反复改用户 config）
- 没有 hermes CLI → 只提示不改文件
"""
import json
import subprocess

import pytest

from vod_mcp.host_adapters import hermes


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(hermes.shutil, "which", lambda _n: "/usr/bin/hermes")
    return tmp_path


def test_plugin_added_while_keeping_existing(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[1:4] == ["config", "get", "plugins.enabled"]:
            return _R(out="  - another-plugin\n")
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hermes.enable_plugin() == "created"
    sets = [c for c in calls if c[1:3] == ["config", "set"]]
    assert len(sets) == 1
    assert json.loads(sets[0][4]) == ["another-plugin", "vod-feedback-router"]


def test_plugin_already_enabled_is_noop(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _R(out="  - vod-feedback-router\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hermes.enable_plugin() == "unchanged"
    assert not [c for c in calls if c[1:3] == ["config", "set"]]


def test_no_cli_only_warns(monkeypatch, capsys):
    monkeypatch.setattr(hermes.shutil, "which", lambda _n: None)
    assert hermes.enable_plugin() == "skipped"
    assert "plugins.enabled" in capsys.readouterr().out


def test_set_failure_does_not_raise(monkeypatch):
    def fake_run(cmd, **kw):
        if cmd[1:4] == ["config", "get", "plugins.enabled"]:
            return _R(out="")
        return _R(rc=1, err="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hermes.enable_plugin() == "skipped"


def test_install_deploys_plugin_dir(fake_home, monkeypatch):
    """install 把插件目录拷进 ~/.hermes/plugins 并自动启用（幂等）。"""
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _R(out=""))
    monkeypatch.setattr(hermes, "server_entry", lambda: "/x/vod_mcp/server.py")

    class A:
        java_api_base = "http://stub.local"

    hermes.install(A(), "core")
    assert (fake_home / ".hermes" / "plugins" / "vod-feedback-router" / "router.py").exists()