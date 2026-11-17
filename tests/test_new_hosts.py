"""四个新增宿主适配的用例（WorkBuddy / AtomCode / CodeArts Work / Codex Desktop）。

形态来源：huaweicloud-devkit head adfd826 的 src/targets.ts 与 agents/*.ts。
本机没装这四个宿主，所以用例锁的是**配置形态与破坏性边界**，不是真机连通性：
- 装：写入正确的 section/键名（mcp / mcpServers / marketplace.plugins[]）
- 幂等：重装 unchanged、不动字节
- 保用户键：其它 server、provider、其它插件原样保留
- 卸载：只摘自己的条目；共享文件绝不整文件删
"""
import json
from pathlib import Path

import pytest

from vod_mcp import hosts as host_specs
from vod_mcp.host_adapters import atomcode, codeartswork, codex_desktop, workbuddy


class Args:
    java_api_base = "http://stub.local"

    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ATOMCODE_HOME", raising=False)
    # S178 起安装收尾会读回条目并校验 server.py 真实存在：给夹具一个真文件
    fake = tmp_path / "payload" / "vod_mcp" / "server.py"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text("", encoding="utf-8")
    for mod in (atomcode, codeartswork, workbuddy, codex_desktop):
        monkeypatch.setattr(mod, "server_entry", lambda: str(fake))
    return tmp_path


# ── WorkBuddy ─────────────────────────────────────────────

def test_workbuddy_writes_mcpservers_entry(fake_home):
    workbuddy.install(Args(), "core,collect")
    cfg = json.loads((fake_home / ".workbuddy" / "mcp.json").read_text(encoding="utf-8"))
    entry = cfg["mcpServers"]["vod-devkit"]
    assert entry["args"][0].endswith("vod_mcp/server.py")
    assert entry["env"]["VOD_PACKS"] == "core,collect"


def test_workbuddy_keeps_other_servers_and_is_idempotent(fake_home):
    p = fake_home / ".workbuddy" / "mcp.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}},
                             "theme": "dark"}), encoding="utf-8")
    workbuddy.install(Args(), "core")
    before = p.read_bytes()
    workbuddy.install(Args(), "core")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    assert cfg["mcpServers"]["other"] == {"command": "x"} and cfg["theme"] == "dark"
    assert len(cfg["mcpServers"]) == 2
    assert p.read_bytes() == before, "重装应 unchanged（不动字节）"


def test_workbuddy_refuses_invalid_json(fake_home):
    p = fake_home / ".workbuddy" / "mcp.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        workbuddy.install(Args(), "core")
    assert p.read_text(encoding="utf-8") == "{not json", "拒绝改动时必须字节不动"


def test_workbuddy_remote_entry(fake_home):
    workbuddy.install_remote(Args(), "https://vod.example/mcp", "tok-123")
    cfg = json.loads((fake_home / ".workbuddy" / "mcp.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"]["vod-devkit"]["url"] == "https://vod.example/mcp"


# ── AtomCode ──────────────────────────────────────────────

def test_atomcode_default_home(fake_home):
    atomcode.install(Args(), "core")
    assert (fake_home / ".atomcode" / "mcp.json").exists()
    assert atomcode.skills_dir(Args()) == fake_home / ".atomcode" / "skills"


def test_atomcode_honours_env_home(fake_home, monkeypatch):
    alt = fake_home / "custom-atom"
    monkeypatch.setenv("ATOMCODE_HOME", str(alt))
    atomcode.install(Args(), "core")
    assert (alt / "mcp.json").exists()
    assert not (fake_home / ".atomcode").exists()
    assert atomcode.skills_dir(Args()) == alt / "skills"


def test_atomcode_does_not_touch_host_hooks(fake_home):
    """刻意不装上游的 pre_tool_use 遥测 hook：没有遥测就不写 hooks.json。"""
    atomcode.install(Args(), "core")
    assert not (fake_home / ".atomcode" / "hooks.json").exists()


# ── CodeArts Work ─────────────────────────────────────────

def test_codeartswork_uses_mcp_section_and_environment_key(fake_home):
    codeartswork.install(Args(), "core,collect")
    p = fake_home / ".codeartswork" / "mcp" / "mcp_settings.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    entry = cfg["mcp"]["vod-devkit"]
    assert isinstance(entry["command"], list) and entry["command"][1].endswith("server.py")
    assert entry["environment"]["VOD_PACKS"] == "core,collect"
    assert "env" not in entry, "CodeArts Work 用 environment，不是 env"


def test_codeartswork_prefers_new_layout_dir(fake_home):
    (fake_home / ".codearts" / "mcp").mkdir(parents=True)
    codeartswork.install(Args(), "core")
    assert (fake_home / ".codearts" / "mcp" / "mcp_settings.json").exists()
    assert not (fake_home / ".codeartswork").exists()


def test_codeartswork_keeps_user_provider_keys(fake_home):
    p = fake_home / ".codeartswork" / "mcp" / "mcp_settings.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"mcp": {"mine": {"command": ["x"]}},
                             "provider": {"model": "m1"}}), encoding="utf-8")
    codeartswork.install(Args(), "core")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    assert cfg["provider"] == {"model": "m1"}
    assert cfg["mcp"]["mine"] == {"command": ["x"]}


# ── Codex Desktop ─────────────────────────────────────────

def test_codex_desktop_writes_plugin_dir_and_marketplace(fake_home):
    codex_desktop.install(Args(), "core,collect")
    pdir = fake_home / "plugins" / "vod-devkit"
    assert (pdir / ".mcp.json").exists()
    assert json.loads((pdir / ".codex-plugin" / "plugin.json").read_text())["name"] == "vod-devkit"
    mp = json.loads((fake_home / ".agents" / "plugins" / "marketplace.json").read_text())
    assert mp["plugins"] == [{"name": "vod-devkit",
                              "source": {"source": "local", "path": "./plugins/vod-devkit"}}]


def test_codex_desktop_preserves_other_plugins(fake_home):
    mp_path = fake_home / ".agents" / "plugins" / "marketplace.json"
    mp_path.parent.mkdir(parents=True)
    mp_path.write_text(json.dumps({"name": "personal", "plugins": [
        {"name": "other-tool", "source": {"source": "local", "path": "./plugins/other"}}],
        "extra": 1}), encoding="utf-8")
    codex_desktop.install(Args(), "core")
    mp = json.loads(mp_path.read_text())
    names = [p["name"] for p in mp["plugins"]]
    assert names == ["other-tool", "vod-devkit"] and mp["extra"] == 1


def test_codex_desktop_uninstall_only_removes_own_entry(fake_home):
    mp_path = fake_home / ".agents" / "plugins" / "marketplace.json"
    mp_path.parent.mkdir(parents=True)
    mp_path.write_text(json.dumps({"name": "personal", "plugins": [
        {"name": "other-tool", "source": {"source": "local", "path": "./plugins/other"}}]}),
        encoding="utf-8")
    codex_desktop.install(Args(), "core")
    codex_desktop.uninstall()
    mp = json.loads(mp_path.read_text())
    assert [p["name"] for p in mp["plugins"]] == ["other-tool"]
    assert not (fake_home / "plugins" / "vod-devkit").exists()
    assert mp_path.exists(), "共享的 marketplace.json 不能被整体删除"


# ── 注册表与探测 ───────────────────────────────────────────

def test_all_new_hosts_are_registered_and_detected(fake_home):
    from vod_mcp.host_adapters import REGISTRY
    for name in ("workbuddy", "atomcode", "codeartswork", "codex-desktop"):
        assert name in REGISTRY, name
        spec = host_specs.load(name)
        assert spec["configPath"] and spec["skillsDir"], name


def test_host_specs_paths_point_where_upstream_does():
    """与上游 targets.ts 对齐（路径漂移是"装了一半"的经典来源）。"""
    assert host_specs.load("workbuddy")["configPath"] == Path.home() / ".workbuddy" / "mcp.json"
    assert host_specs.load("atomcode")["configPath"] == Path.home() / ".atomcode" / "mcp.json"
    assert (host_specs.load("codeartswork")["configPath"]
            == Path.home() / ".codeartswork" / "mcp" / "mcp_settings.json")
    assert (host_specs.load("codex-desktop")["configPath"]
            == Path.home() / ".agents" / "plugins" / "marketplace.json")