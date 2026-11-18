"""审查 P1-1：模式②「一 agent 一远程（独立进程 + 独立 VOD_DEVKIT_HOME）」

安装期 `--product` 先验在远程面被一刀切禁用（runtime_state.py:385 `if not remote:`），
导致模式②虽然物理上「进程私有、只有一个 agent」，却拿不到 install_binding 的产品，
用户原话没提产品时就 -32010 拒绝。design.md:763 表里写明该形态「product 先验=可用」，
代码与文档对立 —— 这是功能回归，不是文案问题。

本文件先复现（红），再加 --single-tenant 放开。
"""

import pytest

from vod_mcp import net
from vod_mcp import runtime_state as rt


@pytest.fixture(autouse=True)
def _remote_face(monkeypatch):
    """全文件按远程 HTTP 面跑（stdio 面的既有行为不在这里验证）。"""
    token = net._SERVER_FACE.set(True)
    yield
    net._SERVER_FACE.reset(token)


def _ci(**kw):
    base = {"name": "http-remote", "agent_id": ""}
    base.update(kw)
    return base


def test_mode2_single_tenant_allows_install_prior(monkeypatch):
    """模式②：独立进程 + 独立 HOME ⇒ 单租户，安装先验应可用。

    复现口径：远程面 + 配置了 VOD_DEVKIT_HOME（=进程隔离已成立）+ 开了单租户开关。
    期望 product_prior=True；修复前恒为 False。
    """
    monkeypatch.setenv("VOD_DEVKIT_HOME", "/tmp/vdk-mode2-home")
    monkeypatch.setenv("VOD_SINGLE_TENANT", "1")
    scope = rt._resolve_scope(_ci())
    assert scope["product_prior"] is True, (
        "模式②（独立进程+独立 HOME）应可用安装先验，"
        f"实际 product_prior={scope['product_prior']} "
        f"(grain={scope.get('grain')}, reason={scope.get('degraded_reason')})"
    )
    assert scope["degraded"] is False or scope["key"], "模式②不应降级到读写皆禁"


def test_mode2_without_flag_stays_disabled(monkeypatch):
    """未开单租户开关时维持现状：多 agent 共用远程 → 必须禁用安装先验。

    这条是**不许破坏既有安全默认**的回归锁。
    """
    monkeypatch.setenv("VOD_DEVKIT_HOME", "/tmp/vdk-mode2-home")
    monkeypatch.delenv("VOD_SINGLE_TENANT", raising=False)
    scope = rt._resolve_scope(_ci())
    assert scope["product_prior"] is False, "未声明单租户时不得放开安装先验（多 agent 共用会错归）"


def test_mode3_shared_remote_never_allows_prior(monkeypatch):
    """模式③：多 agent 共用远程、无独立 HOME —— 即便开了开关也不得放开。

    判据：VOD_DEVKIT_HOME 缺失 ⇒ 无法证明进程私有 ⇒ 保持禁用。
    """
    monkeypatch.delenv("VOD_DEVKIT_HOME", raising=False)
    monkeypatch.setenv("VOD_SINGLE_TENANT", "1")
    scope = rt._resolve_scope(_ci())
    assert scope["product_prior"] is False, (
        "无独立 HOME 时无法证明单租户，必须禁用安装先验（错归比不归更糟）"
    )