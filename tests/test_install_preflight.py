"""P1/P2（2026-11-16 评审）：坏账本时 install 必须零副作用退出，且不许裸 traceback。

实锤（评审 + 本地复现）：HOME=<tmp> + 坏 install-manifest.json 跑
`install --target workbuddy`，旧行为是
  载荷已 stage → 宿主 mcp.json/skills 已写 → 最后写账本才抛 ManifestCorrupt
  → RC=1 + 原始堆栈，账本仍是坏的
留下"宿主已指向 vod-devkit、账本没有这行"的半装状态：uninstall 报没有记录、
doctor 看不见、prune 不知道它在用。

修法：入口先 strict 预检账本（任何副作用之前），失败 exit 2 + 还原指引；
写账本处再兜一层（并发写坏也不裸栈）。本文件打的是**真实 CLI**，
不是源码文本断言——旧的 test_install_write_path_reads_strict 抓不到这条。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(argv, home: Path, extra=None):
    env = {
        "HOME": str(home),
        "VOD_DEVKIT_MANIFEST": str(home / "install-manifest.json"),
        "VOD_DEVKIT_NO_BUILD_INFO": "1",   # 不重烧仓内 build-info
        "VOD_MATRIX": "1",
        "VOD_SKIP_PRODUCT_CHECK": "1",
        "VOD_JAVA_API_BASE": "http://127.0.0.1:9/stub",
        "PATH": os.environ.get("PATH", ""),
    }
    env.update(extra or {})
    return subprocess.run([sys.executable, str(ROOT / "bin" / "vod-devkit"), *argv],
                          env=env, capture_output=True, text=True, timeout=180)


def _shim_cli(home: Path, name: str = "hermes") -> dict:
    """隔离跑里把宿主 CLI 挡掉（立即失败）：空 HERMES_HOME 下 hermes CLI 会自举依赖卡到超时。

    适配器对 CLI 失败是 best-effort（打印提示继续），这里要验的是安装器写出的条目
    与"真实 config.yaml 一个字节都没动"这条不变量。
    """
    d = home / "bin"
    d.mkdir(parents=True, exist_ok=True)
    shim = d / name
    shim.write_text("#!/bin/sh\necho 'test: host CLI disabled' >&2\nexit 1\n", encoding="utf-8")
    shim.chmod(0o755)
    return {"PATH": str(d) + os.pathsep + os.environ.get("PATH", "")}


def test_install_refuses_corrupt_manifest_with_zero_side_effects(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "install-manifest.json").write_text('{ broken', encoding="utf-8")
    r = _run(["install", "--target", "workbuddy"], home)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 2, out
    assert "无法解析" in out and "拒绝写入" in out, out
    assert "Traceback" not in out, f"坏账本必须友好退出，不许裸栈：{out[-400:]}"
    assert not (home / ".workbuddy" / "mcp.json").exists(), (
        "预检必须在写宿主配置之前——否则宿主已指向我们而账本没有这行")
    assert not (home / ".vod-devkit" / "payloads").exists(), "载荷也不许先 stage"
    assert (home / "install-manifest.json").read_text(encoding="utf-8") == "{ broken"
    assert not list(home.glob("install-manifest.json.*")), "失败不留半截账本"


def test_install_with_good_manifest_still_writes_manifest(tmp_path):
    """对照：账本正常时照常安装（预检不能把正常路径也拦掉）。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "install-manifest.json").write_text(json.dumps({"installs": []}), encoding="utf-8")
    r = _run(["install", "--target", "workbuddy"], home)
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    mf = json.loads((home / "install-manifest.json").read_text(encoding="utf-8"))
    rows = mf.get("installs") or []
    assert any(row.get("target") == "workbuddy" for row in rows), rows
    assert (home / ".workbuddy" / "mcp.json").exists()


def test_hermes_isolated_home_never_writes_real_config(tmp_path):
    """HOME 隔离且 HERMES_HOME 未设：CLI 落点跟随 HOME，**真实 config.yaml 一个字节都不许动**。

    判据从"必须拒绝"改成"必须不写真实家目录"（2026-11-16 评审：拒绝会让所有隔离跑法
    被迫改环境；重定向既保住隔离，也堵住写真机配置这条破坏面）。
    """
    home = tmp_path / "home"
    home.mkdir()
    real_conf = Path(os.path.expanduser("~")) / ".hermes" / "config.yaml"
    before = real_conf.read_bytes() if real_conf.exists() else None
    r = _run(["install", "--target", "hermes"], home, extra=_shim_cli(home))
    out = (r.stdout or "") + (r.stderr or "")
    after = real_conf.read_bytes() if real_conf.exists() else None
    assert before == after, "隔离跑的 install 改到了真实 ~/.hermes/config.yaml"


def test_hermes_isolated_home_ignores_inherited_real_hermes_home(tmp_path):
    """网关派生的 env 恒带 HERMES_HOME=/root/.hermes：隔离跑也不许照它写真机配置。"""


def test_server_py_path_with_space_is_read_back(tmp_path):
    """P5：载荷路径含空格时，args 项也要能读回（同一类"读侧没全改"）。"""
    from vod_mcp.host_adapters import dsh as dsh_adapter
    payload = tmp_path / "with space" / "payloads" / "0.5.23"
    payload.mkdir(parents=True)
    from types import SimpleNamespace
    block = dsh_adapter._patch_block(
        SimpleNamespace(product="CodeArts", java_api_base="https://e"),
        "0.2.1-rc.5", payload, "core,collect",
        python_exe="/x/python3", state_home="/s")
    facts = dsh_adapter.block_facts(block)
    assert facts["server_py"] == str(payload / "vod_mcp" / "server.py"), facts["server_py"]

def test_hermes_isolated_home_ignores_inherited_real_hermes_home(tmp_path):
    """网关派生的 env 恒带 HERMES_HOME=/root/.hermes：隔离跑也不许照它写真机配置。"""
    home = tmp_path / "home"
    home.mkdir()
    real = Path(os.path.expanduser("~")) / ".hermes"
    before = (real / "config.yaml").read_bytes() if (real / "config.yaml").exists() else None
    r = _run(["install", "--target", "hermes"], home,
             extra={**_shim_cli(home), "HERMES_HOME": str(real)})
    after = (real / "config.yaml").read_bytes() if (real / "config.yaml").exists() else None
    assert before == after, f"隔离跑照 HERMES_HOME 写到了真实家目录：{r.stderr[-300:]}"
