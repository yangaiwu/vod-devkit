"""插件副本自包含护栏（红→绿钉 bug）。

plugins/vod-devkit 是 codex-desktop 等宿主“隔离安装”的独立根：宿主把该目录
整个拷进 ~/plugins/<name> 后，副本内的 .mcp.json 与 vod_mcp/ 必须能只靠自身
内容工作。因此副本必须是仓库根的等价物，而不是“只带 server 代码”的子集。

实锤（2026-11-15 实测）：副本里 ROOT 塌到 plugins/vod-devkit，
tools._CONTRACT_PATH → plugins/vod-devkit/contract/tools.schema.json（不存在）、
policy._POLICY_PATH → plugins/vod-devkit/safety/policy.json（不存在），
tools.load_contract() 直接 FileNotFoundError。之所以线上没爆，只是因为它
.mcp.json 写 `command: vod-devkit serve` 走了 PATH 上的 CLI（ROOT 在包根），
副本内的 server.py 从没被真跑过——宿主 PATH 上没有 CLI 时这条登记就是死链。

本用例用子进程 + cwd 隔离装载，避免与测试进程里已导入的仓内 vod_mcp 混淆。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY = ROOT / "plugins" / "vod-devkit"

PROBE = r"""
import json, os
from vod_mcp import policy, skills_registry, tools

out = {
    "cwd": os.getcwd(),
    "contract_exists": tools._CONTRACT_PATH.is_file(),
    "contract_path": str(tools._CONTRACT_PATH),
    "policy_path": str(policy._POLICY_PATH),
    "skills_root": str(skills_registry.SKILLS_ROOT),
    "skills_exists": skills_registry.SKILLS_ROOT.is_dir(),
}
out["tools"] = len(tools.load_contract().get("tools", {}))
out["policy_rules"] = len(policy.load_policy().get("rules", []))
print(json.dumps(out))
"""


def _probe() -> tuple[int, str, str]:
    proc = subprocess.run([sys.executable, "-c", PROBE], cwd=COPY,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def test_plugin_copy_ships_its_own_runtime():
    """副本必须自带 server 入口（否则宿主隔离安装后无入口可跑）。"""
    assert (COPY / "vod_mcp" / "server.py").is_file(), "插件副本缺 vod_mcp/server.py"


def test_plugin_copy_is_self_contained():
    """只靠插件副本自身内容：契约 + 策略 + 技能 + 一次真实装载。"""
    code, out, err = _probe()
    assert code == 0, f"插件副本无法独立装载（退出码 {code}）：{err.strip()[-1200:]}"
    got = json.loads(out.strip().splitlines()[-1])
    assert Path(got["cwd"]) == COPY, f"探测没在副本目录下跑：{got['cwd']}"
    assert got["contract_exists"], f"副本缺契约：{got['contract_path']}"
    assert got["policy_path"].startswith(str(COPY)), got["policy_path"]
    assert got["skills_exists"], f"副本缺技能树：{got['skills_root']}"
    assert got["tools"] > 0, "副本装载到的工具数为 0"
    assert got["policy_rules"] > 0, "副本装载到的护栏规则数为 0"