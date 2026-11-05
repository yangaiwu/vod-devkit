"""stdio JSON-RPC 探针工具（tests 复用；真装配层协议验证）。

手法沉淀自多轮真机探针：护栏拒止返回 JSON-RPC error 对象（-32011 等），
只读 result.content 会误判空响应——调用方按 error 字段分流。
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Probe:
    """拉起 server.py 子进程，initialize 握手后提供 tools/call。"""

    def __init__(self, env_extra=None, python=None):
        cmd = python or os.environ.get("VOD_PROBE_PYTHON") or sys_executable()
        env = dict(os.environ, **(env_extra or {}))
        self.p = subprocess.Popen([cmd, str(ROOT / "vod_mcp" / "server.py")],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=env, text=True)
        self.nid = 0
        self.request({"method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"}}})
        self.notify("notifications/initialized")

    def request(self, params):
        self.nid += 1
        self.request_raw({"jsonrpc": "2.0", "id": self.nid, **params})
        return self._recv()

    def notify(self, method):
        self.request_raw({"jsonrpc": "2.0", "method": method})

    def request_raw(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def _recv(self):
        for line in self.p.stdout:
            if line.strip():
                return json.loads(line)
        return {}

    def list_tools(self):
        r = self.request({"method": "tools/list"})
        return r["result"]["tools"]

    def call(self, name, arguments):
        r = self.request({"method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})
        if "error" in r:
            return {"error": r["error"]}
        return {"content": (r.get("result", {}).get("content") or [{}])[0].get("text", "")}

    def close(self):
        self.p.terminate()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def sys_executable():
    import glob
    cands = glob.glob("/root/.hermes/installs/*/environments/*/venv/bin/python3")
    return cands[0] if cands else "python3"
