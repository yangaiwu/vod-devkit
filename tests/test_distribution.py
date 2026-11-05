"""分发形态位（D-key-guard-3）测试：preset 形态下禁 key 随包/禁自更新/
verify 本地降级/首启残留清理/账本出口/日志轮转。
安装器级用例复用 test_installer 的 fake-home 隔离骨架；工具级用例直调 tools。"""
import json
import subprocess
import sys
from pathlib import Path

from tests.test_installer import cli
from tests.test_installer import env as _installer_env_fixture

env = _installer_env_fixture  # pytest 夹具 re-export（赋值别名，避免 import 未用误报）


# ---- 安装器级：形态位写入与红线 ----

def test_install_writes_distribution_field(env):
    r = cli(env, "install", "--target", "hermes", "--product", "GTD",
            "--distribution", "preset")
    assert r.returncode == 0, r.stderr
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    assert mf["distribution"] == "preset"


def test_install_default_distribution_devkit(env):
    cli(env, "install", "--target", "hermes", "--product", "GTD")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    assert mf["distribution"] == "devkit"


def test_install_preset_strips_env_key(env):
    """红线①：preset 安装时环境变量里的 key 不透传进宿主配置（客户机走匿名令牌）。"""
    e = dict(env["env"])
    e["VOD_JAVA_API_KEY"] = "leaky-key-do-not-ship"
    env2 = dict(env, env=e)
    r = cli(env2, "install", "--target", "hermes", "--product", "GTD",
            "--distribution", "preset")
    assert r.returncode == 0
    assert "warn" in r.stderr and "VOD_JAVA_API_KEY" in r.stderr, "必须当场告警"
    mcp_cfg = Path(json.loads((env2["repo"] / "install-manifest.json")
                              .read_text())["mcpConfig"])
    assert "leaky-key-do-not-ship" not in mcp_cfg.read_text(), \
        "key 明文禁止进入任何分发配置"


def test_install_devkit_keeps_key_passthrough(env):
    """对照：devkit 形态 key 透传保持（运营/宿主服务端注入是合法场景）。"""
    e = dict(env["env"])
    e["VOD_JAVA_API_KEY"] = "ops-key-local-only"
    env2 = dict(env, env=e)
    cli(env2, "install", "--target", "hermes", "--product", "GTD")
    mcp_cfg = Path(json.loads((env2["repo"] / "install-manifest.json")
                              .read_text())["mcpConfig"])
    assert "ops-key-local-only" in mcp_cfg.read_text()


def test_update_refused_in_preset(env):
    cli(env, "install", "--target", "hermes", "--product", "GTD",
        "--distribution", "preset")
    r = cli(env, "update")
    assert r.returncode == 0
    assert "不支持自更新" in r.stdout, "preset 下 update 必须拒绝并指引走发版"
    # 铁证：确实没执行 git pull（本地 bare 没有新提交也无所谓——消息即语义）


def test_verify_preset_local_integrity_no_git(env):
    """红线②：preset 下 verify 不触 git，只做本地完整性；离线必须 OK。"""
    cli(env, "install", "--target", "hermes", "--product", "GTD",
        "--distribution", "preset")
    e = dict(env["env"])
    e["PATH"] = "/nonexistent-bin"  # 无 git 可用——离线模拟
    r = subprocess.run([sys.executable, str(env["repo"] / "bin" / "vod-devkit"),
                        "verify"], env=e, capture_output=True, text=True)
    assert r.returncode == 0 and "unchecked" in r.stdout, r.stdout + r.stderr


def test_verify_preset_fails_on_mixed_artifacts(env):
    cli(env, "install", "--target", "hermes", "--product", "GTD",
        "--distribution", "preset")
    bi = env["repo"] / "build-info.json"
    d = json.loads(bi.read_text())
    d["commitSha"] = "0" * 40
    bi.write_text(json.dumps(d))
    r = cli(env, "verify")
    assert r.returncode == 1 and "不一致" in r.stdout, "产物混装必须 FAIL"


def test_install_no_local_ledger_flag(env):
    cli(env, "install", "--target", "hermes", "--product", "GTD",
        "--no-local-ledger")
    cfg = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert cfg["local_ledger"] is False


# ---- 工具级：首启残留清理 / 账本出口 / 日志轮转 ----

def _write_manifest_preset(repo: Path):
    (repo / "install-manifest.json").write_text(json.dumps(
        {"distribution": "preset", "product": "GTD"}))


def test_first_boot_cleans_build_machine_residual(tmp_path, monkeypatch):
    """①兜底：preset + 无 firstBootAt + 携带状态 → 自动清空重生成，保留装机配置。"""
    from vod_mcp import tools
    rt = tmp_path / "runtime.json"
    rt.write_text(json.dumps({"product": "GTD", "java_base": "https://x",
                              "java_key": "build-machine-key",
                              "install_nonce": "deadbeef",
                              "submissions": [{"voiceId": "v1"}]}))
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt)
    monkeypatch.setattr(tools, "_distribution",
                        lambda: "preset") if hasattr(tools, "_distribution") else None
    out = tools._ensure_first_boot(rt)
    assert out["action"] == "cleaned"
    assert sorted(out["removed"]) == ["install_nonce", "java_key", "submissions"]
    cfg = json.loads(rt.read_text())
    assert "java_key" not in cfg and "install_nonce" not in cfg and "submissions" not in cfg
    assert cfg["product"] == "GTD" and cfg["java_base"] == "https://x", "装机配置保留"
    assert cfg["firstBootAt"]


def test_first_boot_devkit_no_clean(tmp_path, monkeypatch):
    """devkit 形态首启只打标，不清理（自装自管场景无残留概念）。"""
    from vod_mcp import tools
    rt = tmp_path / "runtime.json"
    rt.write_text(json.dumps({"java_key": "k", "product": "hermes"}))
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt)
    monkeypatch.setattr(tools, "_distribution", lambda: "devkit")
    out = tools._ensure_first_boot(rt)
    assert out["action"] == "stamped"
    cfg = json.loads(rt.read_text())
    assert cfg["java_key"] == "k" and cfg["firstBootAt"]


def test_first_boot_second_run_noop(tmp_path, monkeypatch):
    from vod_mcp import tools
    rt = tmp_path / "runtime.json"
    rt.write_text(json.dumps({"java_key": "k", "firstBootAt": "2026-01-01T00:00:00"}))
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt)
    monkeypatch.setattr(tools, "_distribution", lambda: "preset")
    assert tools._ensure_first_boot(rt) == {"action": "none"}, "已标记首启不再触发"


def test_ledger_opt_out(tmp_path, monkeypatch):
    """④：local_ledger=false → 提交不落账本，vod_list_submitted 返回空。"""
    from vod_mcp import tools
    rt = tmp_path / "runtime.json"
    rt.write_text(json.dumps({"local_ledger": False}))
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt)
    tools._ledger_append([{"voiceId": "v1", "taskId": None, "title": "t",
                           "product": "GTD", "at": "now"}])
    assert json.loads(rt.read_text()).get("submissions") is None, "账本关闭不落盘"
    out = tools.list_submitted({"limit": 10})
    assert out["total"] == 0


def test_ledger_default_on(tmp_path, monkeypatch):
    from vod_mcp import tools
    rt = tmp_path / "runtime.json"
    rt.write_text(json.dumps({}))
    monkeypatch.setattr(tools, "_runtime_path", lambda: rt)
    tools._ledger_append([{"voiceId": "v1", "taskId": None, "title": "t",
                           "product": "GTD", "at": "now"}])
    assert len(json.loads(rt.read_text())["submissions"]) == 1


def test_log_rotation_cap(tmp_path):
    """⑤：日志超 1MB 截断轮转，保留尾部，新写入追加成功。"""
    from vod_mcp import tools
    big = tmp_path / "vod_mcp_server.log"
    big.write_text("x" * (1024 * 1024 + 4096))
    tools._log("new-line-after-rotation", path=str(big))
    assert big.stat().st_size < 1024 * 1024 + 4096, "轮转后不得继续超限膨胀"
    assert "new-line-after-rotation" in big.read_text()
    assert (tmp_path / "vod_mcp_server.log.old").exists(), "旧日志轮转保留"
