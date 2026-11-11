"""远程 attach 安装模式（D-attach-1）的行为锁。

形态：MCP 单独部署一个 Streamable HTTP 端点，宿主只把 MCP 配置指向它 + 本地装技能。
锁六件：①三宿主各自配置形态 ②缺 token 拒装（远程面不代签身份）③探活先于写入
（失败零副作用）④工具面不符拒装 ⑤skills-only 不动 MCP 配置 ⑥卸载只摘托管条目
（opencode.json 里用户自己的键必须原样保留）。
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "tenant-key-A"

# 远程面工具集（契约 - REMOTE_WITHHELD）
REMOTE_TOOLS = ["vod_submit_voices", "vod_devkit_info", "vod_auth_status",
                "vod_list_skills", "vod_retrieve_skill", "vod_check_update"]


class _Mcp(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_response(405)
        self.send_header("Allow", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        auth = self.headers.get("authorization") or ""
        if auth != f"Bearer {TOKEN}":
            self._json(401, {"error": "unauthorized"})
            return
        msg = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        self.server.seen.append(msg.get("method"))
        if msg.get("method") == "initialize":
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                             "result": {"protocolVersion": "2025-06-18",
                                        "serverInfo": {"name": "vod-devkit", "version": "0.5.1"},
                                        "capabilities": {"tools": {"listChanged": True}}}})
        elif msg.get("method") == "tools/list":
            tools = self.server.tools
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                             "result": {"tools": [{"name": n, "description": "x",
                                                   "inputSchema": {"type": "object"}}
                                                  for n in tools]}})
        else:
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}})


@pytest.fixture
def remote_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mcp)
    srv.seen = []
    srv.tools = REMOTE_TOOLS
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"url": f"http://127.0.0.1:{srv.server_port}/mcp", "srv": srv}
    srv.shutdown()


@pytest.fixture
def env(tmp_path):
    """轻量 fake-home：仓库副本（避免污染真实 build-info/runtime）+ 桩 hermes/codex。"""
    home = tmp_path / "home"
    home.mkdir()
    stub = tmp_path / "bin"
    stub.mkdir()
    calls = tmp_path / "calls.log"
    for name in ("hermes", "codex"):
        p = stub / name
        p.write_text(
            "#!/bin/sh\n"
            f'echo "{name} $@ env_token=${{MCP_VOD_DEVKIT_API_KEY:-}} vmt=${{VOD_MCP_TOKEN:-}}" '
            f">> {calls}\n"
            "exit 0\n")
        p.chmod(0o755)
    repo = tmp_path / "repo"
    shutil.copytree(ROOT, repo, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "node_modules", ".smoke", "*.tgz", "runtime.json",
        "install-manifest.json", ".e2e-nightly.log", ".e2e-behavior-nightly.log"))
    e = os.environ.copy()
    e["HOME"] = str(home)
    e["PATH"] = str(stub) + os.pathsep + e["PATH"]
    e.pop("VOD_JAVA_API_KEY", None)
    e.pop("VOD_MCP_TOKEN", None)
    return {"home": home, "repo": repo, "calls": calls, "env": e}


def cli(env, *args, extra_env=None):
    e = dict(env["env"])
    e.update(extra_env or {})
    return subprocess.run([sys.executable, str(env["repo"] / "bin" / "vod-devkit"), *args],
                          env=e, capture_output=True, text=True, timeout=180)


def _manifest(env):
    return json.loads((env["repo"] / "install-manifest.json").read_text(encoding="utf-8"))


# ---- 三宿主配置形态 ----

def test_opencode_remote_writes_url_and_headers(env, remote_server):
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    cfg = json.loads((env["home"] / ".config/opencode/opencode.json").read_text(encoding="utf-8"))
    entry = cfg["mcp"]["vod-devkit"]
    assert entry == {"type": "remote", "url": remote_server["url"], "enabled": True,
                     "headers": {"Authorization": f"Bearer {TOKEN}"}}
    mf = _manifest(env)
    assert mf["transport"] == "remote" and mf["mcpUrl"] == remote_server["url"]
    # 技能照装（远程形态下技能是本地话术载体）
    assert (env["home"] / ".config/opencode/skills/vod-feedback-collect/SKILL.md").exists()


def test_hermes_remote_uses_cli_url_and_env_token(env, remote_server):
    r = cli(env, "install", "--target", "hermes", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    calls = env["calls"].read_text()
    assert "hermes mcp add vod-devkit --url" in calls
    assert "--auth header" in calls
    assert f"env_token={TOKEN}" in calls, "token 走 env 注入（hermes 自己写 ${{ENV}} 引用）"
    side = json.loads((env["home"] / ".hermes/mcp/vod-devkit.json").read_text(encoding="utf-8"))
    assert side["url"] == remote_server["url"]
    assert "MCP_VOD_DEVKIT_API_KEY" in side["headers"]["Authorization"]


def test_codex_remote_uses_bearer_env_var(env, remote_server):
    r = cli(env, "install", "--target", "codex", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    calls = env["calls"].read_text()
    assert "codex mcp add vod-devkit --url" in calls
    assert "--bearer-token-env-var VOD_MCP_TOKEN" in calls


# ---- 拒装路径（都要零副作用） ----

def test_missing_token_exits2(env, remote_server):
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"])
    assert r.returncode == 2
    assert "必须提供 --mcp-token" in r.stderr
    assert not (env["home"] / ".config/opencode/opencode.json").exists()


def test_probe_failure_exits2_before_writing(env):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # 端口关闭 = 连不上
    r = cli(env, "install", "--target", "opencode",
            "--mcp-url", f"http://127.0.0.1:{port}/mcp", "--mcp-token", TOKEN)
    assert r.returncode == 2
    assert "探活失败" in r.stderr
    assert not (env["home"] / ".config/opencode/opencode.json").exists()
    assert not (env["repo"] / "install-manifest.json").exists()


def test_tool_surface_mismatch_exits2(env, remote_server):
    remote_server["srv"].tools = ["vod_submit_voices"]  # 缺 5 个
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 2
    assert "工具面不符" in r.stderr


def test_dsh_rejects_remote_mode(env, remote_server):
    r = cli(env, "install", "--target", "dsh", "--profile", "web",
            "--mcp-url", remote_server["url"], "--mcp-token", TOKEN)
    assert r.returncode == 2
    assert "dsh 壳不走 MCP" in r.stderr


# ---- skills-only ----

def test_skills_only_does_not_touch_mcp_config(env):
    r = cli(env, "install", "--target", "opencode", "--skills-only")
    assert r.returncode == 0, r.stderr
    assert not (env["home"] / ".config/opencode/opencode.json").exists()
    assert (env["home"] / ".config/opencode/skills/vod-core/SKILL.md").exists()
    assert _manifest(env)["transport"] == "skills-only"


# ---- 卸载只摘托管条目 ----

def test_uninstall_remote_keeps_user_config_keys(env, remote_server):
    conf = env["home"] / ".config/opencode/opencode.json"
    conf.parent.mkdir(parents=True)
    conf.write_text(json.dumps({"provider": {"x": {"apiKey": "user-own"}},
                                "mcp": {"other": {"type": "local", "command": ["x"]},
                                        "vod-devkit": {"type": "remote", "url": "old"}}},
                               ensure_ascii=False), encoding="utf-8")
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    # 覆盖安装后用户键仍在
    cfg = json.loads(conf.read_text(encoding="utf-8"))
    assert cfg["provider"]["x"]["apiKey"] == "user-own" and "other" in cfg["mcp"]
    r = cli(env, "uninstall")
    assert r.returncode == 0, r.stderr
    assert conf.exists(), "共享配置文件绝不能被整文件删除"
    cfg = json.loads(conf.read_text(encoding="utf-8"))
    assert "vod-devkit" not in (cfg.get("mcp") or {})
    assert cfg["provider"]["x"]["apiKey"] == "user-own"
    assert "other" in cfg["mcp"]


# ---- doctor 远程三查 ----

def test_doctor_reports_remote_ok(env, remote_server):
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    r = cli(env, "doctor", extra_env={"VOD_MCP_TOKEN": TOKEN})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "远程面可达" in r.stdout