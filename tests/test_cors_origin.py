"""远程面 Origin/Host 收紧（ARCH-CFG-02，2026-11-19 走查 P1）。

**原缺陷**：`_cors()` 无条件发 `Access-Control-Allow-Origin: *`，`do_OPTIONS` 一律 204，
`do_POST` 全程不校验 Origin/Host ⇒ 用户机器上已装插件时，**任意网页都能跨域驱动本机端点**
（DNS rebinding 还能绕过"仅回环"）。

**修法**：默认只接受回环 Origin/Host，其余 403；非回环需显式 `--allow-origin/--allow-host`。

⚠️ 判据要点：CORS 头只约束浏览器，挡不住本机进程 —— 所以**403 必须在 do_POST 里显式判**。
本文件测的是**真实 HTTP 行为**（起真 server、发真请求），不是断言源码里有没有某行。
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError(f"远程面 {port} 未在 {timeout}s 内就绪")


@pytest.fixture()
def remote_server():
    """起一个真远程面（回环），返回 (proc, port)。用完必杀。"""
    port = _free_port()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "VOD_PACKS": "core"}
    env.pop("VOD_DEVKIT_SRC_ROOT", None)
    env["VOD_DEVKIT_HOME"] = env.get("VOD_DEVKIT_HOME") or "/tmp/vod-cfg02-state"
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "src" / "vod_mcp" / "server.py"),
         "--transport", "remote", "--host", "127.0.0.1", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _wait_ready(port)
        yield proc, port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _post(port: int, headers: dict) -> tuple:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=body,
                                 method="POST", headers={"Content-Type": "application/json",
                                                         **headers})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def test_foreign_origin_is_rejected(remote_server):
    """`Origin: https://evil.example` → 403（且不回 CORS 放行头）。"""
    _, port = remote_server
    code, headers = _post(port, {"Origin": "https://evil.example"})
    assert code == 403, f"外域 Origin 未被拒：{code}"
    acao = headers.get("Access-Control-Allow-Origin")
    assert not acao or acao == "", f"403 仍回了 CORS 放行头：{acao}"


def test_loopback_origin_still_works(remote_server):
    """回环 Origin（任意端口）必须照常工作——本地 dev server 端口不固定。"""
    _, port = remote_server
    for origin in ("http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1"):
        code, _ = _post(port, {"Origin": origin})
        assert code != 403, f"{origin} 被误拒：{code}"


def test_origin_prefix_trick_is_rejected(remote_server):
    """`http://127.0.0.1.evil.com` 不许被前缀匹配误放行（S180 同源教训）。"""
    _, port = remote_server
    code, _ = _post(port, {"Origin": "http://127.0.0.1.evil.com"})
    assert code == 403, f"前缀伪装 Origin 被放行：{code}"


def test_dns_rebinding_host_is_rejected(remote_server):
    """`Host: evil.example`（把域名解析到 127.0.0.1 的 rebinding）→ 403。"""
    _, port = remote_server
    code, _ = _post(port, {"Host": "evil.example"})
    assert code == 403, f"DNS rebinding Host 未被拒：{code}"


def test_no_origin_client_still_works(remote_server):
    """curl/SDK 不带 Origin → 不能拒（否则把非浏览器客户端全打挂）。"""
    _, port = remote_server
    code, _ = _post(port, {})
    assert code != 403, f"无 Origin 的正常客户端被拒：{code}"


def test_loopback_host_allowed_with_port(remote_server):
    """`Host: 127.0.0.1:<port>` 是浏览器正常形态，必须放行。"""
    _, port = remote_server
    code, _ = _post(port, {"Host": f"127.0.0.1:{port}"})
    assert code != 403, f"回环 Host 被误拒：{code}"


def test_origin_matcher_unit():
    """纯函数层：精确命中 / 任意端口命中 / 伪装域名不命中。"""
    from vod_mcp.transport_remote import DEFAULT_ALLOWED_ORIGINS, origin_allowed
    assert origin_allowed("http://127.0.0.1", DEFAULT_ALLOWED_ORIGINS)
    assert origin_allowed("http://127.0.0.1:8080", DEFAULT_ALLOWED_ORIGINS)
    assert origin_allowed("http://localhost:3000", DEFAULT_ALLOWED_ORIGINS)
    assert not origin_allowed("https://evil.example", DEFAULT_ALLOWED_ORIGINS)
    assert not origin_allowed("http://127.0.0.1.evil.com", DEFAULT_ALLOWED_ORIGINS)
    assert not origin_allowed("http://localhost.evil.com", DEFAULT_ALLOWED_ORIGINS)