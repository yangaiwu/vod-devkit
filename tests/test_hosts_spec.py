"""宿主适配层（integrations/<host>/host.json + vod_mcp/hosts.py）的回归锁。

动机：新增宿主此前要在 1074 行安装器里改多处常量与字面量路径，改漏一处就是
半个安装。数据外置后，本文件锁三件事：四个宿主的数据齐备、路径解析正确
（含 dsh 的 profile 占位与 opencode 的 windows 分叉）、代码里的安装器不许
出现没有 host.json 的宿主（否则等于悄悄回到硬编码）。
"""
import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from vod_mcp import hosts

ROOT = Path(__file__).resolve().parent.parent


def test_all_four_hosts_have_specs():
    assert set(hosts.hosts()) == {"hermes", "opencode", "codex", "dsh"}
    for h in hosts.hosts():
        spec = hosts.load(h, "web")
        assert spec["id"] == h
        assert spec["configPath"] is not None, f"{h} 缺配置落点"
        assert str(spec["configPath"]).startswith(str(Path.home())), (
            f"{h} 的路径必须解析到 HOME 之下（安装器只动用户自己的目录）")


def test_dsh_path_requires_profile():
    with pytest.raises(ValueError):
        hosts.load("dsh")
    spec = hosts.load("dsh", "web")
    assert spec["configPath"] == Path.home() / ".dsh/profiles/web/cordis.patch.yml"


def test_opencode_windows_branch(monkeypatch):
    monkeypatch.setattr(hosts.platform, "system", lambda: "Windows")
    spec = hosts.load("opencode")
    assert "AppData/Local/opencode" in str(spec["configPath"])


def test_unknown_host_is_loud():
    """未知宿主必须报错而不是回落某个默认——静默降级=装到错的地方。"""
    with pytest.raises(KeyError) as ei:
        hosts.load("windsurf")
    assert "hermes" in str(ei.value), "报错要列出可选宿主"


def test_generated_templates_exist():
    for g in hosts.load("opencode")["generated"]:
        assert Path(g["template"]).exists(), f"模板缺失：{g['template']}"
        assert g["dest"].name == "vod-doctor.md"


def _bin_module():
    bin_path = ROOT / "bin" / "vod-devkit"
    loader = SourceFileLoader("vod_devkit_bin_spec", str(bin_path))
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("vod_devkit_bin_spec", loader))
    sys.modules.setdefault("vod_devkit_bin_spec", mod)
    loader.exec_module(mod)
    return mod


def test_every_installer_has_a_host_spec():
    """反向锁：适配器注册表里的宿主必须有 host.json（generic 是兜底层，豁免）。"""
    from vod_mcp.host_adapters import REGISTRY
    assert {h for h in REGISTRY if h != "generic"} <= set(hosts.hosts())


def test_host_specs_are_packed():
    """integrations/ 是运行期数据（安装器要读）——不进包=装的时候崩。"""
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "integrations/" in pkg["files"]


def test_no_second_source_of_host_paths_in_installer():
    """安装器源码里不许再出现宿主路径字面量（防悄悄回潮）。"""
    src = (ROOT / "bin" / "vod-devkit").read_text(encoding="utf-8")
    for literal in ('".hermes/mcp"', '".config/opencode"', '".codex/config.toml"',
                    '".dsh/profiles"'):
        assert literal not in src, f"安装器里仍硬编码宿主路径 {literal}——应读 host.json"