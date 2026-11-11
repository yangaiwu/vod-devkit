"""宿主适配层结构门禁（B）。

对标 huaweicloud-devkit：加宿主 = 一个模块 + 注册表一行，而不是在 1300 行的
安装器里改五处。这个门禁就是那条纪律的可执行版本——它红了说明有人把宿主
逻辑又写回 bin/vod-devkit 了。
"""
from pathlib import Path

from vod_mcp.host_adapters import REGISTRY

ROOT = Path(__file__).resolve().parent.parent
BIN = (ROOT / "bin" / "vod-devkit").read_text(encoding="utf-8")


def test_every_registered_adapter_implements_protocol():
    for host, mod in REGISTRY.items():
        assert mod.HOST == host, f"{host}: HOST 与注册键不一致（{mod.HOST}）"
        for attr in ("install", "install_remote", "skills_dir"):
            assert callable(getattr(mod, attr, None)), f"{host} 缺 {attr}"


def test_supported_hosts_match_integrations_or_are_generic():
    """专属宿主的 id 必须与 integrations/<id>/host.json 对应；generic 是兜底层。"""
    integrations = {p.name for p in (ROOT / "integrations").iterdir()
                    if (p / "host.json").exists()}
    for host in REGISTRY:
        if host == "generic":
            continue
        assert host in integrations, f"{host} 没有 integrations/{host}/host.json（数据缺失）"


def test_no_per_host_install_logic_left_in_bin():
    """宿主安装逻辑必须住在 vod_mcp/host_adapters/，bin 只做分派。"""
    offenders = [name for name in ("_install_hermes", "_install_opencode",
                                   "_install_codex", "_install_dsh",
                                   "_install_remote", "_upsert_dsh_patch")
                  if f"def {name}" in BIN]
    assert not offenders, ("这些函数又回到 bin/vod-devkit 了：" + "、".join(offenders)
                           + "——加宿主的边际成本会重新涨回去，请搬进 host_adapters/")


def test_host_adapters_package_is_packed():
    """适配器是运行期代码：不进 npm 包 = 装出来的安装器 import 崩。"""
    import json
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "vod_mcp/host_adapters/" in pkg["files"]


def test_detect_targets_survives_profile_placeholder(tmp_path, monkeypatch):
    """实锤回归：dsh host.json 的 configPath 含必填 {profile}，探测走 load()
    会 ValueError → --target auto 直接崩（重构前就存在的坑，本次收口）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "opencode").mkdir(parents=True)   # opencode detect.path
    import importlib.machinery
    import importlib.util
    import sys
    loader = importlib.machinery.SourceFileLoader("vd_bin_detect", str(ROOT / "bin" / "vod-devkit"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("vd_bin_detect", loader))
    sys.modules["vd_bin_detect"] = mod
    loader.exec_module(mod)
    assert "opencode" in mod.detect_targets()


def test_generic_declares_known_hosts_table():
    from vod_mcp.host_adapters import generic
    assert generic.KNOWN_HOSTS, "通用探测表为空——未知宿主会退化成『不支持』"
    for h in generic.KNOWN_HOSTS:
        assert {"id", "paths", "config", "label"} <= set(h)