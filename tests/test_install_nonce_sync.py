"""D-dev-nonce-sync（2026-11-09 真机实锤）：首装 nonce 内存态同步回归锁。

缺陷：_install_nonce 首次生成只写 runtime.json 不回写模块级 _RT（仅导入时
加载一次）→ 同进程内每次调用生成新 nonce → 领令牌与提交设备不同 → 引擎
设备绑定校验 401，重试仍新 nonce 再 401——全新安装首次提交必失败冒给用户。
修复：生成后同步 _RT["install_nonce"]（真源=vod_mcp/tools.py）。
"""
import json


def test_install_nonce_stable_within_process(tmp_path, monkeypatch):
    from vod_mcp import tools

    rt_file = tmp_path / "runtime.json"
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt_file)
    monkeypatch.setattr(tools, "_RT", {})  # 模拟全新安装（_RT 无 nonce）

    n1 = tools._install_nonce()
    n2 = tools._install_nonce()
    n3 = tools._install_nonce()
    # 同进程多次调用必须同值（领令牌/提交/重试同设备）
    assert n1 == n2 == n3
    # 回写内存态 _RT（缺陷根因断言：修复前 _RT 始终无值 → 每次新 nonce）
    assert tools._RT.get("install_nonce") == n1
    # 落盘一致（重启后 _RT 从文件加载亦同值）
    assert json.loads(rt_file.read_text(encoding="utf-8"))["install_nonce"] == n1
