"""安装载荷（D-payload-1）行为锁。

对标 huaweicloud-devkit 的 copyServerPayload：把 server/契约/安全策略/技能拷到
用户自己的稳定目录，入口指向副本 —— npx 缓存被清也不会让宿主 MCP 掉线。

锁五件：
  ① 载荷落到 <VOD_PAYLOAD_HOME>/payloads/<ver>/，payload.json 记录逐文件 sha256
     且不把自己算进指纹（否则每次校验都报"被改"——第一版实锤）
  ② prune 只删我们拥有的顶层条目（用户/别的工具放进去的东西不动）
  ③ server_entry() 指向载荷副本（base.set_payload_dir）
  ④ 标记 .installed：install 写、server 启动消费
  ⑤ 没有 payload.json 的目录=残留，residue() 报出来
"""
import json
from pathlib import Path

import pytest

from vod_mcp import payload
from vod_mcp.host_adapters import base


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOD_PAYLOAD_HOME", str(tmp_path / "pay"))
    return tmp_path


def test_stage_places_payload_with_hashes(home):
    dest = payload.stage(quiet=True)
    assert dest == home / "pay" / "payloads" / payload.payload_dir().name
    for rel in ("vod_mcp/server.py", "contract/tools.schema.json",
                "safety/policy.json", "skills/vod-core/SKILL.md"):
        assert (dest / rel).is_file(), rel
    pj = json.loads((dest / "payload.json").read_text(encoding="utf-8"))
    assert pj["files"], "载荷必须记录文件指纹"
    assert "payload.json" not in pj["files"], "payload.json 不能自指"
    assert payload.verify(dest) == []


def test_stage_excludes_runtime_json(home):
    dest = payload.stage(quiet=True)
    assert not (dest / "vod_mcp" / "runtime.json").exists()


def test_verify_reports_tampering(home):
    dest = payload.stage(quiet=True)
    (dest / "vod_mcp" / "server.py").write_text("# tampered\n", encoding="utf-8")
    problems = payload.verify(dest)
    assert any("载荷文件被改" in p for p in problems)


def test_prune_only_removes_owned_stale_entries(home):
    dest = payload.stage(quiet=True)
    (dest / "skills" / "vod-retired").mkdir(parents=True)
    (dest / "user-notes.txt").write_text("keep me", encoding="utf-8")
    from vod_mcp import payload as p2
    removed = p2.prune_stale(dest, set(p2.OWNED) | {"user-notes.txt"})
    assert "skills" not in removed          # 源里有 skills，不能整目录删
    assert (dest / "user-notes.txt").exists()
    # 顶层 owned 但源里没有的目录会被清（模拟退役的技能树）
    (dest / "hermes-plugin").mkdir(exist_ok=True)
    removed = p2.prune_stale(dest, {"vod_mcp", "contract", "safety", "skills",
                                    "user-notes.txt"})
    assert "hermes-plugin" in removed


def test_server_entry_points_into_payload(home):
    dest = payload.stage(quiet=True)
    base.set_payload_dir(dest)
    try:
        assert base.server_entry() == str(dest / "vod_mcp" / "server.py")
    finally:
        base.set_payload_dir(None)
    assert base.server_entry().endswith(str(Path("vod_mcp") / "server.py"))


def test_marker_written_then_consumed(home):
    payload.stage(quiet=True)
    assert payload.marker_path().exists()
    payload.consume_marker()
    assert not payload.marker_path().exists()


def test_residue_lists_dirs_without_payload_json(home):
    payload.stage(quiet=True)
    junk = payload.payload_home() / "payloads" / "0.4.2"
    junk.mkdir(parents=True)
    assert junk in payload.residue()