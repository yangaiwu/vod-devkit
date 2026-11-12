"""远程面守卫（对齐 devkit 的 verifySkillTree / 每请求自校验）。

两个缺口是这轮补齐的：
1 构造期：技能树缺失就不许对外服务（list_skills 会宣传取不到的技能）；
2 每请求：服务端载荷被改/缺文件 → 503 拒绝服务，而不是继续拿旧数据对外跑。

另外把"远程面拒绝在无技能状态下服务"的判定做成可测的纯函数，避免门禁靠注释。
"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_remote_build_refuses_without_skill_tree(monkeypatch, tmp_path):
    from vod_mcp import remote_app, skills_registry
    monkeypatch.setattr(skills_registry, "SKILLS_ROOT", tmp_path / "no-skills")
    with pytest.raises(RuntimeError) as ei:
        remote_app.build_server(remote=True)
    assert "技能树不存在" in str(ei.value)


def test_remote_build_refuses_empty_skill_tree(monkeypatch, tmp_path):
    from vod_mcp import remote_app, skills_registry
    empty = tmp_path / "skills"
    empty.mkdir()
    monkeypatch.setattr(skills_registry, "SKILLS_ROOT", empty)
    with pytest.raises(RuntimeError) as ei:
        remote_app.build_server(remote=True)
    assert "没有任何目录型技能" in str(ei.value)


def test_stdio_build_does_not_require_skills(monkeypatch, tmp_path):
    """stdio 面（本地直跑）不受这条约束：技能由宿主自己装。"""
    from vod_mcp import remote_app, skills_registry
    monkeypatch.setattr(skills_registry, "SKILLS_ROOT", tmp_path / "no-skills")
    assert remote_app.build_server(remote=False) is not None


def test_payload_problems_detects_tampering(tmp_path, monkeypatch):
    from vod_mcp import payload, transport_remote

    monkeypatch.setenv("HOME", str(tmp_path))
    dest = payload.stage(quiet=True)
    monkeypatch.setenv("VOD_PAYLOAD_DIR", str(dest))  # 显式 env 优先（安装期注入同款）
    try:
        assert transport_remote.payload_problems(force=True) == []
        target = dest / "vod_mcp" / "server.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
        problems = transport_remote.payload_problems(force=True)
        assert problems and any("server.py" in p for p in problems)
    finally:
        monkeypatch.delenv("VOD_PAYLOAD_DIR", raising=False)


def test_no_payload_dir_means_no_guard(monkeypatch):
    from vod_mcp import transport_remote
    monkeypatch.delenv("VOD_PAYLOAD_DIR", raising=False)
    # 仓内直跑：ROOT 没有 payload.json → 不校验（stdio 形态不误伤）
    assert transport_remote.payload_problems(force=True) == []


def test_http_returns_503_when_payload_tampered(monkeypatch):
    """端点层：载荷校验不过 → 503，不进入工具面。"""
    from vod_mcp import transport_remote as tr
    monkeypatch.setattr(tr, "payload_problems", lambda force=False: ["vod_mcp/server.py sha256 不符"])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), tr._Handler)
    httpd.runtime = type("R", (), {"request": lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该进传输层"))})()
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/mcp"
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("应当返回 503")
        except urllib.error.HTTPError as e:
            assert e.code == 503
            payload = json.loads(e.read().decode())
            assert "载荷校验未通过" in payload["error"]["message"]
    finally:
        httpd.shutdown()