"""S145：一台机器一个匿名令牌（D-token-machine-1）的用例承载。

覆盖面：
1. 跨宿主/跨进程共享同一份 state（同一 VOD_DEVKIT_HOME → 同一 nonce/令牌）；
2. 升级换载荷版本目录后身份不变（旧路径是按版本分的，这是本次要消灭的隐患）；
3. 首启迁移保留 install_nonce（改造当天不换设备锚点）；
4. vod_auth_ensure 五个分支（有 key / 复用 / 领新 / 显式被拒 / 不可达）；
5. 装机 env 注入 VOD_DEVKIT_HOME；6. --clean-global 回收 state；
7. 测试自身不落真机 state（门禁第 4 项的用例侧自检）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from vod_mcp import net, paths
from vod_mcp import runtime_state as rt
from vod_mcp.packs import core

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"


def _run_probe(dist: Path, state_home: Path) -> dict:
    """子进程读身份：真实跨进程（模块级缓存会掩盖 bug），但不碰网络。"""
    code = (
        "import json;from vod_mcp import paths,net,runtime_state as rt;"
        "print(json.dumps({'runtime':str(paths.runtime_json_path()),"
        "'nonce':rt._install_nonce(),"
        "'fp':net._fingerprint(net._java_key())}))"
    )
    env = {**os.environ, "PYTHONPATH": str(_SRC),
           "VOD_DEVKIT_HOME": str(state_home),
           "VOD_DEVKIT_SRC_ROOT": str(_SRC), "VOD_DEVKIT_DIST_ROOT": str(dist)}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_s145_machine_scope_shared_across_hosts_and_versions(tmp_path):
    """S145-1/2：不同宿主的载荷根（0.5.9 / 0.5.10）→ 同一 state、同一 nonce、同一指纹。"""
    state_home = tmp_path / "state"
    a = _run_probe(tmp_path / "payloads" / "0.5.9", state_home)
    b = _run_probe(tmp_path / "payloads" / "0.5.10", state_home)
    assert a["runtime"] == b["runtime"], "机器级 state 必须跨载荷版本一致"
    assert a["runtime"] == str(state_home / "runtime.json")
    assert a["nonce"] == b["nonce"], "跨版本必须复用同一设备锚点"
    assert a["fp"] == b["fp"]


def test_s145_migrate_keeps_install_nonce(tmp_path, monkeypatch):
    """S145-3：旧版本目录里的 runtime 迁到机器级 state，install_nonce/账本原样保留。"""
    dist = tmp_path / "old-payload"
    legacy = dist / "vod_mcp"
    legacy.mkdir(parents=True)
    cfg = {"install_nonce": "deadbeef", "java_key": "k" * 24,
           "token_tier": "anonymous", "product": "CodeArts",
           "submissions": [{"voiceId": "v-1"}]}
    (legacy / "runtime.json").write_text(json.dumps(cfg), encoding="utf-8")

    state_home = tmp_path / "state"
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(state_home))
    # 兼容位是 DIST_ROOT 派生的（import 期常量）：测试里直接钉住模块值，
    # 而不是设 env——paths.DIST_ROOT 的固化是设计（入口显式设置），不该为测试改成现读。
    monkeypatch.setattr(paths, "DIST_ROOT", dist)

    res = paths.migrate_state_once()
    assert res["migrated"] is True
    moved = json.loads((state_home / "runtime.json").read_text(encoding="utf-8"))
    assert moved["install_nonce"] == "deadbeef"
    assert moved["submissions"] == [{"voiceId": "v-1"}]
    assert (legacy / "runtime.json").exists(), "迁移不得删除旧文件（破坏性留给 clean-global）"
    assert (state_home / "runtime.json").stat().st_mode & 0o777 == 0o600
    # 幂等：第二次不再迁移（且带 .migrated 标记，state 被清也不回灌旧文件）
    assert paths.migrate_state_once()["reason"] == "already-migrated"
    (state_home / "runtime.json").unlink()
    assert paths.migrate_state_once()["migrated"] is False, "state 被清后旧文件不得复活"
    assert not (state_home / "runtime.json").exists()


def test_s145_ensure_acquires_when_no_key(tmp_path, monkeypatch):
    """S145-4：无 key → 代理领匿名令牌 → 落 state → 返回 new-anonymous/verified。"""
    rt._runtime_update({}, replace=True)
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setattr(net, "_fetch_anon_token", lambda: "anon-token-0001")
    monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
        "ok": True, "reason": "verified", "fingerprint": "abcd1234"})

    out = core.auth_ensure({})
    assert out["changed"] is True and out["source"] == "new-anonymous"
    assert out["tier"] == "anonymous" and out["verified"] is True
    assert out["fingerprint"] == "abcd1234"
    assert rt._runtime_cfg().get("token_tier") == "anonymous"
    assert rt._runtime_cfg().get("java_key") == "anon-token-0001"


def test_s145_ensure_reuses_verified_token_without_refetch(tmp_path, monkeypatch):
    """S145-5：已有 token 且 verified → 不重复领（一次网络探针都没有多余领取）。"""
    rt._runtime_update({"java_key": "existing-token", "token_tier": "anonymous"}, replace=True)
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(net, "_fetch_anon_token", lambda: calls.append(1) or "x")
    monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
        "ok": True, "reason": "verified", "fingerprint": "aaaa0000"})

    out = core.auth_ensure({})
    assert out["changed"] is False and out["source"] == "runtime-anonymous"
    assert out["verified"] is True
    assert calls == [], "verified 令牌不得重新领取"


def test_s145_ensure_runtime_explicit_key_is_not_downgraded(tmp_path, monkeypatch):
    """S145-6b：runtime 里的显式 key（auth init 写入，tier!=anonymous）被拒同样不降级。"""
    rt._runtime_update({"java_key": "init-key-0001", "token_tier": "formal"}, replace=True)
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(net, "_fetch_anon_token", lambda: calls.append(1) or "anon")
    monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
        "ok": False, "reason": "rejected", "fingerprint": "cccc2222"})

    out = core.auth_ensure({})
    assert out["source"] == "runtime-key" and out["verified"] is False
    assert calls == [], "runtime 显式 key 被拒也不得换匿名"
    assert rt._runtime_cfg().get("java_key") == "init-key-0001"


def test_s145_ensure_never_overwrites_rejected_explicit_key(tmp_path, monkeypatch):
    """S145-6：显式 key 被引擎拒 → 不领、不覆盖、如实报错（fail fast）。"""
    rt._runtime_update({}, replace=True)
    monkeypatch.setenv("VOD_JAVA_API_KEY", "formal-key-0001")
    calls = []
    monkeypatch.setattr(net, "_fetch_anon_token", lambda: calls.append(1) or "anon")
    monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
        "ok": False, "reason": "rejected", "fingerprint": "ffff0000"})

    out = core.auth_ensure({})
    assert out["verified"] is False and out["reason"] == "rejected"
    assert out["source"] == "env" and out["changed"] is False
    assert calls == [], "显式 key 被拒时不得静默降级匿名"
    assert rt._runtime_cfg().get("java_key") in (None, ""), "不得覆盖已有配置"


def test_s145_ensure_does_not_fetch_when_unreachable(tmp_path, monkeypatch):
    """S145-7：引擎不可达 → 不领、不判定（网络问题不是身份问题）。"""
    rt._runtime_update({"java_key": "existing", "token_tier": "anonymous"}, replace=True)
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(net, "_fetch_anon_token", lambda: calls.append(1) or "anon")
    monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
        "ok": None, "reason": "unreachable", "fingerprint": "bbbb1111"})

    out = core.auth_ensure({})
    assert out["verified"] is None and out["changed"] is False
    assert calls == []
    assert rt._runtime_cfg().get("java_key") == "existing"


def test_s145_ensure_remote_face_uses_request_key(monkeypatch):
    """远程面：请求头 Bearer 优先，不领匿名（本地/远程同语义）。"""
    tok_face = net._SERVER_FACE.set(True)
    tok_req = net._REQ_KEY.set("tenant-key-A")
    try:
        calls = []
        monkeypatch.setattr(net, "_fetch_anon_token", lambda: calls.append(1) or "x")
        monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
            "ok": True, "reason": "verified", "fingerprint": "dddd3333"})
        out = core.auth_ensure({})
        assert out["source"] == "request" and out["verified"] is True
        assert out["tier"] == "formal"
        assert calls == [], "请求头已给身份时不得代领匿名令牌"
    finally:
        net._REQ_KEY.reset(tok_req)
        net._SERVER_FACE.reset(tok_face)


def test_s145_ensure_remote_face_without_request_key_acquires(monkeypatch):
    """远程面无 Bearer 时与本地同效果：由服务端领机器级匿名令牌。"""
    tok_face = net._SERVER_FACE.set(True)
    try:
        rt._runtime_update({}, replace=True)
        monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
        monkeypatch.setattr(net, "_fetch_anon_token", lambda: "anon-remote-0001")
        monkeypatch.setattr(net, "probe_key", lambda key=None, timeout=10: {
            "ok": True, "reason": "verified", "fingerprint": "eeee4444"})
        out = core.auth_ensure({})
        assert out["source"] == "new-anonymous" and out["verified"] is True
        assert out["tier"] == "anonymous" and out["changed"] is True
        assert rt._runtime_cfg().get("java_key") == "anon-remote-0001"
    finally:
        net._SERVER_FACE.reset(tok_face)


def test_s145_install_env_carries_machine_state(tmp_path, monkeypatch):
    """S145-8：装机把 VOD_DEVKIT_HOME 写进每个宿主 env（单点 server_env）。"""
    from vod_mcp.host_adapters import base
    state = tmp_path / "state"
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(state))
    env = base.server_env(SimpleNamespace(java_api_base="https://vod-dev.topxtopx.com"), "core")
    assert env["VOD_DEVKIT_HOME"] == str(state)


def test_s145_clean_global_reclaims_state(tmp_path, monkeypatch):
    """S145-9：--clean-global 回收机器级 state（逐条打印、只删认得的文件名）。"""
    from vodkit_cli import uninstall
    home = tmp_path / "home"
    state = home / ".vod-devkit" / "state"
    state.mkdir(parents=True)
    (state / "runtime.json").write_text("{}", encoding="utf-8")
    (state / "runtime.json.lock").write_text("", encoding="utf-8")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(state))
    monkeypatch.setattr(uninstall, "_SHARED_CONFIG_NAMES", set())
    from vod_mcp import payload as _payload
    monkeypatch.setattr(_payload, "residue", lambda: [])
    uninstall._clean_global([])
    assert not (state / "runtime.json").exists()
    assert not state.exists()


def test_s145_tests_do_not_touch_machine_state(tmp_path):
    """S145-10：门禁第 4 项的用例侧自检——测试进程的 state 必须落在**本次 tmp**。

    不许用环境字面量判（`"/tmp"`、目录名里含 `"pytest"`）：`--basetemp` 一换就假红，
    与"golden 不许锁环境值"是同一类问题（真机实锤：换成 .../pt-run 就红，而隔离本身
    是好的）。判据改成 pytest 注入的 tmp_path + fixture 显式设置的 VOD_DEVKIT_HOME。
    """
    resolved = Path(paths.machine_state_home())
    real = Path(os.path.expanduser("~")) / ".vod-devkit" / "state"
    assert resolved != real, f"测试读到了真机 state：{resolved}"
    assert resolved.is_relative_to(tmp_path), f"state 不在本次 tmp 下：{resolved}（tmp={tmp_path}）"
    assert str(os.environ.get("VOD_DEVKIT_HOME") or "") == str(resolved), (
        "conftest 必须显式把 VOD_DEVKIT_HOME 指到 tmp——靠默认值派生不算隔离")


def test_s145_anon_mint_policy_follows_binding(monkeypatch):
    """S145-18：回环绑定开启代领（同机部署默认）；非回环默认关闭，需显式开关。"""
    from vod_mcp import net as _net, transport_remote as _tr
    old = _net.ANON_MINT_DISABLED
    try:
        assert _tr._apply_anon_mint_policy("127.0.0.1", False) is True
        assert _net.ANON_MINT_DISABLED is False
        assert _tr._apply_anon_mint_policy("0.0.0.0", False) is False
        assert _net.ANON_MINT_DISABLED is True
        assert _tr._apply_anon_mint_policy("0.0.0.0", True) is True
        assert _net.ANON_MINT_DISABLED is False
    finally:
        _net.ANON_MINT_DISABLED = old


def test_s145_disabled_mint_never_calls_engine(monkeypatch):
    """代领被禁用时不发任何外呼（不是"发了再失败"）。"""
    from vod_mcp import net as _net
    calls = []
    monkeypatch.setattr(_net, "_http", lambda *a, **k: calls.append(1) or {})
    old = _net.ANON_MINT_DISABLED
    _net.ANON_MINT_DISABLED = True
    try:
        assert _net._fetch_anon_token() is None
        assert calls == [], "禁用态下不得请求令牌端点"
    finally:
        _net.ANON_MINT_DISABLED = old


def test_s145_install_read_side_matches_server_read_side(tmp_path, monkeypatch):
    """收口断言：装机/doctor 的读侧与 server 的读侧是同一个 runtime 路径。

    历史病：装机写 <repo>/vod_mcp/runtime.json、server 读 <state>/runtime.json →
    装机绑定的 product/java_base 在运行期读不到（静默失效）。
    """
    state = tmp_path / "state"
    state.mkdir()
    (state / "runtime.json").write_text('{"product": "GTD"}', encoding="utf-8")
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(state))
    from vodkit_cli import common
    assert paths.runtime_json_path() == state / "runtime.json"
    assert common._runtime_cfg_read().get("product") == "GTD"


def test_s145_remote_tool_surface_matches_local_except_packs_switch():
    """远程面与本地同面：只摘 packs_configure（进程内状态），其余全部可用。"""
    from vod_mcp import packs
    local = set(packs.enabled_tools())
    remote = set(packs.enabled_tools(remote=True))
    assert remote == local - {"vod_packs_configure"}, (sorted(local), sorted(remote))
    assert {"vod_draft_voices", "vod_commit_voices",
            "vod_list_submitted"} <= remote


def test_s145_draft_is_owned_by_creating_client(monkeypatch):
    """草稿按宿主隔离：A 暂存的草稿 B 不能提交（同机多 agent 共用远程进程的场景）。"""
    from vod_mcp.packs import collect

    monkeypatch.setattr(collect, "_allowed_tags", lambda product: set())
    a = {"name": "hermes", "version": "1"}
    b = {"name": "codex", "version": "1"}
    draft = collect.draft_voices({"voices": [{"content": "导出太慢了"}], "product": "1"}, a)
    assert draft["draftId"]

    with pytest.raises(net.ToolError) as ei:
        collect.commit_voices({"draftId": draft["draftId"],
                               "approvalToken": draft["approvalToken"]}, b)
    assert "不属于当前客户端" in str(ei.value)

    submitted = {}

    def _fake_submit(params, client_info=None, ledger_extra=None):
        submitted["by"] = (client_info or {}).get("name")
        return {"accepted": len(params.get("voices") or []), "voiceIds": ["v-1"],
                "rejected": [], "echo": {"contents": []}}

    monkeypatch.setattr(collect, "submit_voices", _fake_submit)
    out = collect.commit_voices({"draftId": draft["draftId"],
                                 "approvalToken": draft["approvalToken"]}, a)
    assert out["twoPhase"] is True and submitted["by"] == "hermes"