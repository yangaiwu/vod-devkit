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
    assert "src/vod_mcp/host_adapters/" in pkg["files"]


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

def test_hermes_install_without_cli_degrades_instead_of_crashing(monkeypatch, tmp_path):
    """无 hermes CLI 时 install 必须降级（写配置片段 + 提示），不得裸 exec 崩掉。

    2026-11-15 CI host-matrix 失败根因：hermes 分支没有 CLI 守卫，
    FileNotFoundError 直接把整条矩阵打红。
    """
    import types
    monkeypatch.setenv("HOME", str(tmp_path))
    from vod_mcp.host_adapters import hermes
    monkeypatch.setattr(hermes.shutil, "which", lambda _name: None)
    args = types.SimpleNamespace(java_api_base="https://vod.example")
    conf = hermes.install(args, "core,collect")
    assert conf.exists(), "JSON 片段仍要落盘（用户可手工并入 config.yaml）"
    payload = conf.read_text(encoding="utf-8")
    assert "vod-devkit" in payload and "server.py" in payload
    # 无 CLI 时：hook 仍写进 config.yaml（脚本是载荷里的，不依赖 CLI），
    # 只有"清理旧插件启用名"这一步跳过——降级但不崩
    cfg = tmp_path / ".hermes" / "config.yaml"
    assert hermes.HOOK_MARK in cfg.read_text(encoding="utf-8")
    assert hermes.remove_legacy_plugin() == "" or "plugins.enabled" not in hermes.remove_legacy_plugin()


def test_s159_hermes_spec_reroot_when_home_contains_dot_hermes(monkeypatch, tmp_path):
    """S159：隔离 HOME 落在含 `.hermes` 分量的路径下时，spec 重定向不得自我嵌套。

    实机（2026-11-16 host_matrix）：HOME=`<tmp>/.hermes/cache/.../home` 时，
    `_spec()` 用 `parts.index(".hermes")` 取路径里**第一个** `.hermes` 分量——
    命中的是外层 Hermes 缓存那层，于是 configPath 被拼成
    `<HERMES_HOME>/cache/.../home/.hermes/config.yaml`：安装器写到鬼路径，
    矩阵报「配置未落盘：.hermes/mcp/vod-devkit.json」（用户机器 HOME 正常时不触发，
    所以只在隔离/容器形态暴露）。
    判据：重定向后必须等于 `<HERMES_HOME>/mcp/vod-devkit.json`。
    """
    import os

    from vod_mcp.host_adapters import hermes

    home = tmp_path / ".hermes" / "cache" / "scratch" / "home"
    home.mkdir(parents=True)
    hh = home / ".hermes"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(hh))
    spec = hermes._spec()
    assert Path(spec["configPath"]) == hh / "mcp" / "vod-devkit.json", spec["configPath"]
    assert str(home) not in str(spec["configPath"]).replace(str(hh), "", 1)
    assert os.environ["HERMES_HOME"] == str(hh)


def test_s159_hermes_spec_reroot_leaves_foreign_paths_alone(monkeypatch, tmp_path):
    """S159 反向锁：不在 `HOME/.hermes` 之下的路径不许被重定向（防重写别人钉的落点）。"""
    from vod_mcp.host_adapters import hermes

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "elsewhere"))
    foreign = "/opt/custom/hermes/mcp.json"
    monkeypatch.setattr(hermes.host_specs, "load",
                        lambda _h: {"configPath": foreign, "skillsDir": str(home / ".hermes" / "skills")})
    spec = hermes._spec()
    assert spec["configPath"] == foreign


def test_s161_hermes_landing_judged_once(monkeypatch, tmp_path):
    """S161：CLI 落点与文件落点必须由同一判据决定（隔离 HOME 下只认位于该 HOME 之内的 HERMES_HOME）。

    实机背景：`_cli_env()` 曾用「root 不在真实家目录之下」判"隔离 root"，
    `_spec()` 用「root 在 HOME 之下」。两条判据对 `HERMES_HOME=/tmp/shared` 给出**相反**结论：
    CLI 认为自己写 /tmp/shared，文件却写在 `<HOME>/.hermes` —— 正是 0.5.25 修过的分裂形态。
    收敛后两边都跟随 HOME（并在 stderr 说明忽略），显式钉在隔离 HOME 之内的才认。
    """
    from vod_mcp.host_adapters import hermes

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "shared"))   # 隔离 HOME 之外
    spec = hermes._spec()
    assert Path(spec["configPath"]) == home / ".hermes" / "mcp" / "vod-devkit.json"
    env = hermes._cli_env()
    assert env["HERMES_HOME"] == str(home / ".hermes")


def test_s161_hermes_landing_accepts_root_inside_isolated_home(monkeypatch, tmp_path):
    """S161 正向：显式钉在该隔离 HOME 之内的 HERMES_HOME 两边都认（矩阵形态）。"""
    from vod_mcp.host_adapters import hermes

    home = tmp_path / "home"
    hh = home / "state-hermes"
    hh.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HERMES_HOME", str(hh))
    assert Path(hermes._spec()["configPath"]) == hh / "mcp" / "vod-devkit.json"
    assert hermes._cli_env()["HERMES_HOME"] == str(hh)


def test_s161_hermes_landing_respects_root_on_real_home(monkeypatch, tmp_path):
    """S161 真实 HOME：HERMES_HOME 照旧生效（不引入新的忽略规则）。"""
    from vod_mcp.host_adapters import hermes

    real = hermes._real_home()
    if real is None:                       # 平台无 pwd：本机不适用
        return
    monkeypatch.setenv("HOME", str(real))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "rh"))
    assert Path(hermes._spec()["configPath"]) == tmp_path / "rh" / "mcp" / "vod-devkit.json"
    assert hermes._cli_env()["HERMES_HOME"] == str(tmp_path / "rh")
