"""CodeArts Agent 宿主适配（实测 2026-11-11）。

事实（本机 codearts 二进制 + 现场探针）：
- CodeArts Agent 是 OpenCode 分支：SCENARIO=codeartsdoer，
  OPENCODE_CONFIG=~/.codeartsdoer/codearts_cli.json
- 往 codearts_cli.json 写 mcp.<name> 后 `codearts mcp list` 立即可见（已实测）
- `codearts mcp add` 无任何参数（交互式向导）→ 程序化只能写 JSON
- mcp_settings.json 只对**项目级** .codeartsdoer/mcp/ 生效；用户级读
  ~/.config/opencode/mcp/ —— 所以绝不能写 ~/.codeartsdoer/mcp/
- 技能目录 ~/.codeartsdoer/skills
"""
import json
from pathlib import Path

import pytest

from vod_mcp.host_adapters import base, codearts


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codeartsdoer").mkdir()
    cfg = tmp_path / ".codeartsdoer" / "codearts_cli.json"
    cfg.write_text(json.dumps({"$schema": "x", "provider": {"deepseek": {}},
                               "model": "deepseek-chat", "mcp": {}}), encoding="utf-8")
    monkeypatch.setattr(base, "_PAYLOAD_DIR", None)
    return tmp_path


def _args(**kw):
    a = {"java_api_base": "http://stub", "dsh_profile": ""}
    a.update(kw)
    return type("A", (), a)()


def test_install_preserves_user_keys_and_backs_up(home):
    codearts.install(_args(), "core,collect")
    cfg_path = home / ".codeartsdoer" / "codearts_cli.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["model"] == "deepseek-chat"
    assert cfg["provider"] == {"deepseek": {}}
    entry = cfg["mcp"]["vod-devkit"]
    assert entry["type"] == "local"
    assert "python" in Path(entry["command"][0]).name
    assert entry["command"][1].endswith(str(Path("vod_mcp") / "server.py"))
    assert entry["enabled"] is True
    assert entry["environment"]["VOD_PACKS"] == "core,collect"
    assert (home / ".codeartsdoer" / "codearts_cli.json.bak").exists()


def test_install_is_idempotent(home):
    codearts.install(_args(), "core,collect")
    cfg_path = home / ".codeartsdoer" / "codearts_cli.json"
    bak = Path(str(cfg_path) + ".bak")
    bak.write_text("sentinel", encoding="utf-8")
    codearts.install(_args(), "core,collect")
    assert bak.read_text(encoding="utf-8") == "sentinel"   # 值一致不再备份


def test_install_refuses_invalid_json_without_touching(home):
    cfg_path = home / ".codeartsdoer" / "codearts_cli.json"
    cfg_path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(RuntimeError):
        codearts.install(_args(), "core,collect")
    assert cfg_path.read_text(encoding="utf-8") == "{ broken"


def test_remote_entry_shape(home):
    codearts.install_remote(_args(), "https://gw/mcp", "tok")
    cfg = json.loads((home / ".codeartsdoer" / "codearts_cli.json").read_text(encoding="utf-8"))
    entry = cfg["mcp"]["vod-devkit"]
    assert entry == {"type": "remote", "url": "https://gw/mcp", "enabled": True,
                     "headers": {"Authorization": "Bearer tok"}}


def test_skills_dir_is_codeartsdoer(home):
    assert codearts.skills_dir(_args()) == home / ".codeartsdoer" / "skills"


def test_entry_points_into_payload_when_staged(home, tmp_path, monkeypatch):
    payload = tmp_path / "payloads" / "9.9.9"
    (payload / "vod_mcp").mkdir(parents=True)
    (payload / "vod_mcp" / "server.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(base, "_PAYLOAD_DIR", payload)
    codearts.install(_args(), "core")
    cfg = json.loads((home / ".codeartsdoer" / "codearts_cli.json").read_text(encoding="utf-8"))
    assert cfg["mcp"]["vod-devkit"]["command"][1] == str(payload / "vod_mcp" / "server.py")