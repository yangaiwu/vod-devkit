"""通用 MCP 宿主层（A）行为锁。

对标 huaweicloud-devkit 的 configureGenericMCP：没有专属适配模块的宿主不该
"不支持"，而是外科式写入 mcpServers + 给可粘贴片段。

铁律在本文件里被锁死：
  ① 只动 mcpServers["vod-devkit"]，其它 server 与用户自有键原样保留
  ② 首次改动前落 .bak；值已一致时返回 unchanged（不重复备份）
  ③ 现有文件非法 JSON / 顶层非对象 / mcpServers 非对象 → RuntimeError，字节不动
  ④ 探测到唯一通用宿主时 auto 才自动写；多个/零个要求人指定
"""
import json
from pathlib import Path

import pytest

from vod_mcp.host_adapters import generic


def _entry():
    return {"command": "python3", "args": ["/repo/vod_mcp/server.py"], "env": {}}


def test_merge_preserves_other_servers_and_backs_up(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}},
                               "projects": {"/a": 1}}), encoding="utf-8")
    action = generic.merge_mcp_servers(cfg, _entry())
    assert action == "created"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["vod-devkit"] == _entry()
    assert data["projects"] == {"/a": 1}                      # 用户自有键保留
    assert Path(str(cfg) + ".bak").exists()                   # 首改备份


def test_merge_is_idempotent_and_does_not_rebackup(tmp_path):
    cfg = tmp_path / "mcp.json"
    generic.merge_mcp_servers(cfg, _entry())
    bak = Path(str(cfg) + ".bak")
    bak.write_text("sentinel", encoding="utf-8")
    assert generic.merge_mcp_servers(cfg, _entry()) == "unchanged"
    assert bak.read_text(encoding="utf-8") == "sentinel"


def test_merge_refuses_invalid_json_without_touching_bytes(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text("{ not json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        generic.merge_mcp_servers(cfg, _entry())
    assert cfg.read_text(encoding="utf-8") == "{ not json"


def test_merge_refuses_non_object_top_level(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(RuntimeError):
        generic.merge_mcp_servers(cfg, _entry())


def test_merge_refuses_non_object_mcpservers(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": []}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        generic.merge_mcp_servers(cfg, _entry())


def test_detect_known_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".claude.json").write_text("{}", encoding="utf-8")
    ids = [h["id"] for h in generic.detect_known()]
    assert ids == ["claude-code", "cursor"]


def test_install_without_path_prints_snippet_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    args = type("A", (), {"mcp_config": "", "java_api_base": "http://stub"})()
    assert generic.install(args, "core,collect") is None
    assert list(tmp_path.iterdir()) == []          # 未给路径=零写入


def test_install_with_path_writes_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / "mcp.json"
    args = type("A", (), {"mcp_config": str(cfg), "java_api_base": "http://stub"})()
    assert generic.install(args, "core,collect") == cfg
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["vod-devkit"]["env"]["VOD_PACKS"] == "core,collect"
    assert data["mcpServers"]["vod-devkit"]["env"]["VOD_JAVA_API_BASE"] == "http://stub"


def test_install_remote_requires_explicit_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    args = type("A", (), {"mcp_config": ""})()
    with pytest.raises(SystemExit) as e:
        generic.install_remote(args, "https://x/mcp", "tok")
    assert e.value.code == 2


def test_install_remote_writes_bearer_header(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / "mcp.json"
    args = type("A", (), {"mcp_config": str(cfg)})()
    generic.install_remote(args, "https://x/mcp", "tok")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["vod-devkit"]["url"] == "https://x/mcp"
    assert data["mcpServers"]["vod-devkit"]["headers"]["Authorization"] == "Bearer tok"