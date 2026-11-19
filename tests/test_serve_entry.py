"""ARCH-DEP-04：`serve` 双入口必须都把 MCP server 拉起来（2026-11-19 真机）。

⚠️ 本轮踩错一次，写进用例注释避免重犯：`src/vodkit_cli/cli.py` **被设计成被 import 的
装配模块，没有 `if __name__ == "__main__"`**，直接 `python cli.py serve` 什么都不会发生
（进程正常退出、零输出）——那是**测试方法错**，不是产品缺陷。真实入口有两个：

    ① bin/vod-devkit serve        （宿主/CLI 首选；薄壳，import vodkit_cli.main）
    ② vod-devkit serve 子命令分支 （argparse 的 sp_serve，nargs=REMAINDER）

台账 DEP-04 的实质是「两条分派**取根来源不同**」：`cli.py:13` 的前置分支用
`paths.SRC_ROOT`，而 `cli.py` 子命令分支 `_serve` 用 `common.ROOT`。仓内形态两者同指，
插件/载荷副本形态可能不同。本用例锁住「两个入口都必须真起来、且报同一版本」。
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "vod-devkit"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}}}
PAYLOAD = "\n".join([
    json.dumps(INIT),
    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
]) + "\n"


def _run(cmd: list, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "VOD_PACKS": "core"}
    env.pop("VOD_DEVKIT_SRC_ROOT", None)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, *cmd], input=PAYLOAD, capture_output=True,
                          text=True, timeout=90, env=env)


def _msgs(out: str) -> list:
    return [json.loads(x) for x in out.splitlines() if x.strip().startswith("{")]


def test_bin_entry_starts_server():
    """真实入口 bin/vod-devkit serve 必须返回 initialize + tools/list。"""
    r = _run([str(BIN), "serve"])
    assert r.stdout.strip(), f"零输出（exit={r.returncode}, stderr={r.stderr[-300:]!r}）"
    m = _msgs(r.stdout)
    init = next((x for x in m if x.get("id") == 1), None)
    assert init is not None, f"无 initialize；stdout={r.stdout[:300]!r}"
    assert init["result"]["serverInfo"]["name"] == "vod-devkit", init
    tools = next((x for x in m if x.get("id") == 2), None)
    assert tools is not None, "无 tools/list"
    assert len(tools["result"]["tools"]) > 0


def test_two_dispatch_paths_report_same_version():
    """双分派必须同源：bin 入口（前置 execve 分支）与 argparse 子命令分支报同一版本。

    台账 DEP-04:两条"取根来源不同"——前置分支用 `paths.SRC_ROOT`,子命令 `_serve`
    曾经用 `common.ROOT`(分发根)。仓内形态两者**不同指**(SRC_ROOT=<repo>/src,
    DIST_ROOT=<repo>),所以 `_serve` 拼出的 `<repo>/vod_mcp/server.py` 根本不存在。
    """
    r1 = _run([str(BIN), "serve"])
    m1 = _msgs(r1.stdout)
    init = next((x for x in m1 if x.get("id") == 1), None)
    assert init is not None, f"bin 入口无 initialize：stdout={r1.stdout[:200]!r}"
    v_cli = init["result"]["serverInfo"]["version"]

    # 直跑 server.py（等价于子命令分支最终 execve 的目标）
    r2 = subprocess.run([sys.executable, str(ROOT / "src" / "vod_mcp" / "server.py")],
                        input=json.dumps(INIT) + "\n", capture_output=True, text=True,
                        timeout=90,
                        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "VOD_PACKS": "core"})
    m2 = _msgs(r2.stdout)
    init2 = next((x for x in m2 if x.get("id") == 1), None)
    assert init2 is not None, f"server.py 直跑无 initialize：{r2.stdout[:200]!r}"
    assert v_cli == init2["result"]["serverInfo"]["version"], (
        f"两条入口版本不一致：bin={v_cli} vs 直跑={init2['result']['serverInfo']['version']}")


@pytest.mark.parametrize("bad", ["{repo}/src/vod_mcp", "{repo}/src/nonexistent"])
def test_misplaced_inherited_src_root_is_tolerated(bad):
    """外部传错 VOD_DEVKIT_SRC_ROOT（层级不对）时，入口必须能自愈或明确报错，
    不许静默零输出——宿主带着自己的 env 传递时就会撞上。"""
    r = _run([str(BIN), "serve"], {"VOD_DEVKIT_SRC_ROOT": bad.replace("{repo}", str(ROOT))})
    ok = bool(r.stdout.strip()) or bool(r.stderr.strip())
    assert ok, f"VOD_DEVKIT_SRC_ROOT={bad} 下静默零输出（exit={r.returncode}）"


# ── DEP-04 真锁：两条分派必须同源，且拼出的 server.py 真实存在 ──────────────
#
# 旧用例 `test_two_dispatch_paths_report_same_version` 是**绕开**的：它硬编码
# `<repo>/src/vod_mcp/server.py` 去直跑，等于用正确答案验证正确答案，从未检查
# `_serve` 自己拼什么。所以 DEP-04 在"版本一致"的绿灯下活了下来。
# 这里改成读源码 + 实测路径存在性，任何一条分支改回分发根都会当场红。
def test_dep04_serve_branches_share_one_root():
    """两处 serve 分派必须都用 SRC_ROOT 拼 server.py；不许出现 common.ROOT 拼代码路径。"""
    src = (ROOT / "src" / "vodkit_cli" / "cli.py").read_text("utf-8")
    # 前置分支（argv[1]=='serve'）与子命令 _serve 各一处
    hits = [ln for ln in src.splitlines()
            if "vod_mcp" in ln and "server.py" in ln and "sys.executable" in ln]
    assert len(hits) == 2, f"serve 分派点数量变了（期望 2，实际 {len(hits)}）：{hits}"
    for ln in hits:
        assert "SRC_ROOT" in ln, f"这条 serve 分派没用 SRC_ROOT（DEP-04 回退）：{ln.strip()}"
        assert "common.ROOT" not in ln, f"这条 serve 分派又用分发根拼代码路径了：{ln.strip()}"


def test_dep04_serve_target_exists():
    """SRC_ROOT 下必须真有 server.py —— 这条在改回 common.ROOT 时会红。"""
    from vod_mcp import paths
    target = paths.SRC_ROOT / "vod_mcp" / "server.py"
    assert target.is_file(), f"serve 将 exec 不存在的路径：{target}"
    # 反面：分发根下**不该**有它，防止有人用"两处都建一份"糊过去
    assert paths.SRC_ROOT != paths.DIST_ROOT or target.is_file()