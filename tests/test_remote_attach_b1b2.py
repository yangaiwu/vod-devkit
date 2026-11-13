"""B1/B2 修复的行为锁（真机实锤的两个远程 attach 缺陷）。

B1：hermes install_remote 静默失败——subprocess 管道 input="y\\ny\\n" 对 hermes
    mcp add 的交互链（Overwrite? → 认证? → Enable all tools?）不够答，且
    hermes 端 Cancelled 后仍 exit 0 → 安装器以为成功，内部注册表纹丝不动。
    真机复现（2026-11-13）：stdio 装过 vod-devkit 的 hermes 上跑
    install --mcp-url，安装器输出"已注册"，config.yaml 的 mcp_servers 仍是
    stdio 条目。三个 y 才答完；但数提示个数是脆的——hermes 升级多问一问就再
    静默。锁两件事：①喂不封顶的 y 流 ②装完读回 config.yaml 断言 url 真的在
    （防"rc=0 即成功"的假绿，静默失败必须炸出来）。

B2：探活不验 token——_probe_remote 只做 initialize+tools/list（连接级），坏
    token 照样装上，用户首次提交才发现 401。与"--product fail fast（归因错误
    比报错糟）"的纪律不对称。修法：探活加第 3 步——经远程面真调 vod_auth_status
    读 keyCheck（远程面透传请求头 key 给引擎探针），rejected 拒装、unreachable
    放行（网络问题不是 key 问题）。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "tenant-key-A"
REMOTE_TOOLS = ["vod_submit_voices", "vod_devkit_info", "vod_auth_status",
                "vod_list_skills", "vod_retrieve_skill", "vod_check_update",
                "vod_search_products"]


class _Mcp(BaseHTTPRequestHandler):
    """远程面桩：握手 + 工具面 + tools/call(vod_auth_status) 的 keyCheck 回执。

    keyCheck 三态由 server.mode 控制：
    - "rejected"：坏 key → {"ok": False, "reason": "rejected", "fingerprint": ...}
    - "verified"：好 key → {"ok": True, "reason": "verified", ...}
    - "unreachable"：引擎不可达 → {"ok": None, "reason": "unreachable"}（放行）
    - None：旧版远程面（无 keyCheck 段）→ 放行
    """

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        method = msg.get("method")
        if method == "initialize":
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                             "result": {"protocolVersion": "2025-06-18",
                                        "serverInfo": {"name": "vod-devkit", "version": "0.5.5"},
                                        "capabilities": {"tools": {"listChanged": True}}}})
        elif method == "tools/list":
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"),
                             "result": {"tools": [{"name": n, "description": "x",
                                                   "inputSchema": {"type": "object"}}
                                                  for n in self.server.tools]}})
        elif method == "tools/call":
            mode = self.server.keycheck_mode
            if mode is None:
                result = {"content": [{"text": json.dumps({"javaKey": {"configured": False}}),
                                       "type": "text"}]}
            else:
                check = {"ok": mode == "verified",
                         "reason": mode if mode != "verified" else "verified",
                         "fingerprint": "ab12cd34"}
                result = {"content": [{"text": json.dumps({"keyCheck": check}, ensure_ascii=False),
                                       "type": "text"}]}
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"), "result": result})
        else:
            self._json(200, {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}})


@pytest.fixture
def remote_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Mcp)
    srv.tools = REMOTE_TOOLS
    srv.keycheck_mode = "verified"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"url": f"http://127.0.0.1:{srv.server_port}/mcp", "srv": srv}
    srv.shutdown()


@pytest.fixture
def env(tmp_path):
    """fake-home：仓库副本 + 桩 hermes（可编程：写不写 config.yaml / 记 stdin 行数）。"""
    home = tmp_path / "home"
    home.mkdir()
    stub = tmp_path / "bin"
    stub.mkdir()
    calls = tmp_path / "calls.log"
    hermes_stub = stub / "hermes"
    hermes_stub.write_text(
        "#!/bin/sh\n"
        'echo "hermes $@ stdin_lines=$(wc -l)" >> ' + str(calls) + "\n"
        'if [ "${VOD_STUB_HERMES_WRITES:-0}" = "1" ]; then\n'
        '  mkdir -p "$HOME/.hermes"\n'
        '  printf "mcp_servers:\\n  vod-devkit:\\n    url: %s\\n    enabled: true\\n" "${VOD_STUB_URL}" >> "$HOME/.hermes/config.yaml"\n'
        "fi\n"
        "exit 0\n")
    hermes_stub.chmod(0o755)
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


# ---- B1：hermes remote add 的输入与防静默 ----

def test_hermes_remote_feeds_unbounded_yes_stream(env, remote_server):
    """桩 hermes 真写配置：安装成功，且 stdin 必须喂 ≥3 行 y（B1 的输入面）。"""
    r = cli(env, "install", "--target", "hermes", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN,
            extra_env={"VOD_STUB_HERMES_WRITES": "1", "VOD_STUB_URL": remote_server["url"]})
    assert r.returncode == 0, r.stderr
    m = re.search(r"stdin_lines=(\d+)", env["calls"].read_text())
    assert m
    assert int(m.group(1)) >= 3, "hermes 交互链三问只喂两个 y 会静默 Cancelled（B1 实锤）"


def test_hermes_remote_fails_loud_when_registration_missing(env, remote_server):
    """防假绿：hermes mcp add rc=0 但没写真配置（Cancelled 场景）必须炸，不许静默。"""
    r = cli(env, "install", "--target", "hermes", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)  # 桩默认不写 config.yaml
    assert r.returncode != 0, "桩 hermes 未写任何配置，安装器必须检测到并报错"
    assert "未落盘" in r.stderr or "未注册" in r.stderr or "失败" in r.stderr


# ---- B2：探活必须验 token（keyCheck 三态） ----

def test_probe_rejects_bad_token_before_writing(env, remote_server):
    """坏 key：远程面 keyCheck 回 rejected → 拒装（零副作用），不许等首次提交才发现。"""
    remote_server["srv"].keycheck_mode = "rejected"
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", "definitely-bad-key")
    assert r.returncode == 2
    assert "token 无效" in r.stderr or "无效" in r.stderr
    assert not (env["home"] / ".config/opencode/opencode.json").exists()
    assert not (env["repo"] / "install-manifest.json").exists()


def test_probe_passes_valid_token(env, remote_server):
    """好 key：keyCheck verified → 正常装。"""
    remote_server["srv"].keycheck_mode = "verified"
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    assert (env["home"] / ".config/opencode/opencode.json").exists()


def test_probe_tolerates_engine_unreachable(env, remote_server):
    """引擎不可达：keyCheck unreachable → 放行（网络问题不是 key 问题，不误伤）。"""
    remote_server["srv"].keycheck_mode = "unreachable"
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
    assert (env["home"] / ".config/opencode/opencode.json").exists()


def test_probe_tolerates_legacy_remote_without_keycheck(env, remote_server):
    """旧版远程面（keyCheck 段缺失）：连接级已过 → 放行（无法验证≠无效）。"""
    remote_server["srv"].keycheck_mode = None
    r = cli(env, "install", "--target", "opencode", "--mcp-url", remote_server["url"],
            "--mcp-token", TOKEN)
    assert r.returncode == 0, r.stderr
