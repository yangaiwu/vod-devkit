"""宿主安装矩阵的门禁用例（scripts/host_matrix.py 的子集跑法）。

完整矩阵在 CI 的 host-matrix job 里跑（9 个宿主）；这里只跑 3 个不需要宿主 CLI 的
代表项，确保"矩阵脚本本身没坏"能进日常 pytest：
- workbuddy：mcpServers + env 形态
- codeartsdoer：mcp 段 + command 数组（CodeArts 家族）
- codex-desktop：marketplace 登记 + 插件目录

断言：脚本退出 0，且输出里这三项都是 PASS（SKIP 不算通过——它们不依赖 CLI）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "host_matrix.py"


def test_matrix_subset_passes():
    r = subprocess.run([sys.executable, str(SCRIPT),
                        "--host", "workbuddy", "--host", "codeartsdoer",
                        "--host", "codex-desktop"],
                       capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    for host in ("workbuddy", "codeartsdoer", "codex-desktop"):
        assert f"[{host}] PASS" in out, out
    assert "0 FAIL" in out, out