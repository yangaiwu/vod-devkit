"""Hermes 侧钩子的回归锁（D-hook-unify-1：插件包 → config.yaml shell hook）。

统一架构的理由：同一个"stdin JSON → stdout context"脚本，由各宿主用**自己的**机制
注册；hermes 的机制是 `hooks.pre_llm_call`（子进程隔离、按 (event, command) 首次同意），
不需要 plugins.enabled，也不需要在宿主进程里 import 我们的代码。老装机里的插件包
必须被清理，否则插件 + hook 双份注入。

覆盖：
- S128a 新建/追加/幂等（不重复插）
- S128b 只插进 hooks.pre_llm_call，别人的条目与 hooks 段内其它事件原样保留
- S128c 形态不认识（hooks 内联）→ 抛错，绝不猜着改用户 config.yaml
- S128d 摘除只摘我们那条（含 timeout 行），空事件段保留
- S128e install 真的把 hook 写进当前 HOME 的 config.yaml，并清旧插件目录/启用名
"""
import json
import subprocess

import pytest

from vod_mcp.host_adapters import hermes


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _run_writing_cfg(cfg):
    """桩 subprocess.run：`mcp add` 必须像真 CLI 那样把条目写进 config.yaml。

    S170 之后安装器会读回 configPath；桩只回 rc=0 不落配置 = 交互确认被跳过的形态，
    install 会（正确地）非零退出，用例就会红得像产品坏了。
    """
    from pathlib import Path

    cfg = Path(cfg)

    def fake(cmd, **kw):
        if list(cmd[1:3]) == ["mcp", "add"]:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
            if "  vod-devkit:" not in text:
                if "mcp_servers:" not in text:
                    text += "mcp_servers:\n"
                text += "  vod-devkit:\n    command: stub\n"
                cfg.write_text(text, encoding="utf-8")
        return _R(out="")

    return fake


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


CMD = "/usr/bin/python3 /payload/hooks/vod_router.py"


# ── S128a ────────────────────────────────────────────────

def test_s128a_creates_hooks_section_when_absent():
    text = "model: x\n"
    new, state = hermes.upsert_llm_hook(text, CMD)
    assert state == "created"
    assert "hooks:\n  pre_llm_call:\n" in new
    assert f'- command: "{CMD}"' in new and "timeout: 10" in new
    assert new.startswith("model: x"), "原有键必须在前面原样保留"


def test_s128a_append_into_existing_event_is_idempotent():
    text = ("hooks:\n  pre_llm_call:\n"
            "    - command: \"other-tool run\"\n      timeout: 5\n"
            "  post_tool_call:\n    - command: \"fmt\"\n")
    new, state = hermes.upsert_llm_hook(text, CMD)
    assert state == "added"
    assert '- command: "other-tool run"' in new, "别人的 hook 不许动"
    assert '  post_tool_call:' in new
    again, state2 = hermes.upsert_llm_hook(new, CMD)
    assert state2 == "unchanged" and again == new, "重复装必须幂等"


def test_s128a_event_absent_inside_hooks_is_added():
    text = "hooks:\n  post_tool_call:\n    - command: \"fmt\"\n"
    new, state = hermes.upsert_llm_hook(text, CMD)
    assert state == "added"
    assert "  pre_llm_call:\n" in new
    assert new.index("pre_llm_call") < new.index("post_tool_call"), "插在 hooks 段头部"


# ── S128b ────────────────────────────────────────────────

def test_s128b_preserves_unrelated_top_level_keys():
    text = "model: x\nplugins:\n  enabled:\n    - a\n"
    new, _ = hermes.upsert_llm_hook(text, CMD)
    assert new.startswith(text.rstrip("\n")), "顶层其它段落必须逐字保留"


# ── S128c ────────────────────────────────────────────────

def test_s128c_refuses_inline_hooks_shape():
    with pytest.raises(RuntimeError) as e:
        hermes.upsert_llm_hook("hooks: {}\n", CMD)
    assert "不是块形态" in str(e.value)


# ── S128d ────────────────────────────────────────────────

def test_s128d_remove_hook_only_ours():
    text = ("hooks:\n  pre_llm_call:\n"
            '    - command: "other"\n      timeout: 5\n'
            f'    - command: "{CMD}"\n      timeout: 10\n')
    new, removed = hermes.remove_llm_hook(text)
    assert removed is True
    assert 'command: "other"' in new
    assert hermes.HOOK_MARK not in new
    new2, removed2 = hermes.remove_llm_hook(new)
    assert removed2 is False and new2 == new, "摘除必须幂等"


# ── S128e ────────────────────────────────────────────────

def test_s128e_install_writes_hook_and_cleans_legacy(fake_home, monkeypatch, capsys):
    cfg = fake_home / ".hermes" / "config.yaml"
    monkeypatch.setattr(subprocess, "run", _run_writing_cfg(cfg))
    monkeypatch.setattr(hermes, "server_entry", lambda: "/payload/vod_mcp/server.py")
    legacy = fake_home / ".hermes" / "plugins" / hermes.LEGACY_PLUGIN
    legacy.mkdir(parents=True)
    (legacy / "router.py").write_text("old", encoding="utf-8")

    class A:
        java_api_base = "http://stub.local"

    hermes.install(A(), "core,collect")
    cfg = fake_home / ".hermes" / "config.yaml"
    assert cfg.exists()
    text = cfg.read_text(encoding="utf-8")
    assert "pre_llm_call:" in text and hermes.HOOK_MARK in text
    assert not legacy.exists(), "旧插件目录必须被清（否则双份注入）"
    out = capsys.readouterr().out
    assert "已注册预采集 hook" in out and "已清理旧插件形态" in out


def test_s128e_install_keeps_existing_config(fake_home, monkeypatch):
    cfg = fake_home / ".hermes" / "config.yaml"
    monkeypatch.setattr(subprocess, "run", _run_writing_cfg(cfg))
    monkeypatch.setattr(hermes, "server_entry", lambda: "/payload/vod_mcp/server.py")
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("model: keep-me\n", encoding="utf-8")

    class A:
        java_api_base = "http://stub.local"

    hermes.install(A(), "core")
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith("model: keep-me"), "用户已有配置逐字保留"


def test_s128e_legacy_plugin_removed_from_enabled(fake_home, monkeypatch):
    """老装机的 plugins.enabled 里还有旧插件名 → 必须摘掉（返回说明里可见）。"""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[1:4] == ["config", "get", "plugins.enabled"]:
            return _R(out="  - other\n  - vod-feedback-router\n")
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(hermes.shutil, "which", lambda _n: "/usr/bin/hermes")
    out = hermes.remove_legacy_plugin()
    assert "plugins.enabled" in out
    sets = [c for c in calls if c[1:3] == ["config", "set"]]
    assert sets and json.loads(sets[0][4]) == ["other"], "只摘旧插件名，保留其它"