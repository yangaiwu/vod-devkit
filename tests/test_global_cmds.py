"""全局命令与多宿主消费面的用例（S116-S123）。

背景（D-global-cmds-1，对齐 huaweicloud-devkit 的三条全局命令）：
多宿主分发必然产生版本碎片与能力面漂移。install-manifest.json 的 installs[]
（D-installs-1）早就记了全部宿主，但消费方还是单宿主——本组把读路径统一：
version 报碎片、packs 查/改启用面、--target all 一步装全、uninstall 能挑宿主、
--clean-global 清外部残留、未知包 id 启动即报错。

纪律：所有写操作先 dry-run（缺省不写盘），写后读回验证；只改受管条目的 env。
"""
import json

import pytest

from vod_mcp import packs as packs_mod
from vodkit_cli import packs_cmd, uninstall


# ── S116 未知包 id 启动即报错 ─────────────────────────────

def test_s116_parse_packs_rejects_unknown():
    with pytest.raises(packs_mod.UnknownPack) as e:
        packs_mod.parse_packs("core,bogus")
    assert "bogus" in str(e.value) and "core" in str(e.value)


def test_s116_parse_packs_accepts_kb_alias():
    assert packs_mod.parse_packs("core,kb") == ("core", "knowledge")


def test_s116_server_exits_loudly_on_unknown_pack(tmp_path):
    """装错了要在启动时就喊，不是静默把包摘掉（配了不生效最难查）。"""
    import subprocess
    import sys
    root = __import__("pathlib").Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "src" / "vod_mcp" / "server.py")],
                       input="", capture_output=True, text=True, timeout=60,
                       env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
                            "VOD_PACKS": "core,bogus"})
    assert r.returncode == 2
    assert "未知包 id" in r.stderr and "bogus" in r.stderr


# ── 夹具：一份两行 manifest + 两份宿主配置 ─────────────────

def _env(tmp_path, monkeypatch):
    manifest = tmp_path / "install-manifest.json"
    hermes_cfg = tmp_path / "hermes-mcp.json"
    hermes_cfg.write_text(json.dumps({
        "name": "vod-devkit", "command": "/py", "args": ["/payload/vod_mcp/server.py"],
        "env": {"VOD_PACKS": "core,collect", "VOD_JAVA_API_BASE": "http://x"}},
        ensure_ascii=False), encoding="utf-8")
    atom_cfg = tmp_path / "atom-mcp.json"
    atom_cfg.write_text(json.dumps({"mcpServers": {"vod-devkit": {
        "command": "/py", "args": ["/payload/vod_mcp/server.py"],
        "env": {"VOD_PACKS": "core,knowledge"}}}, "other": {"keep": 1}},
        ensure_ascii=False), encoding="utf-8")
    from vod_mcp import __version__
    manifest.write_text(json.dumps({
        "version": __version__, "target": "atomcode",
        "installs": [
            {"target": "hermes", "version": __version__, "mcpConfig": str(hermes_cfg),
             "skillsDir": str(tmp_path / "sk"), "payloadDir": str(tmp_path / "p1")},
            {"target": "atomcode", "version": "0.0.1", "mcpConfig": str(atom_cfg),
             "skillsDir": str(tmp_path / "sk2"), "payloadDir": str(tmp_path / "p2")},
        ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VOD_DEVKIT_MANIFEST", str(manifest))
    return manifest, hermes_cfg, atom_cfg


class _A:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ── S118 version ───────────────────────────────────────

def test_s118_version_reports_fragments(tmp_path, monkeypatch, capsys):
    _env(tmp_path, monkeypatch)
    packs_cmd.cmd_version(_A())
    out = capsys.readouterr().out
    assert "vod-devkit CLI:" in out
    assert "hermes" in out and "同版" in out
    assert "atomcode" in out and "≠ CLI" in out
    assert "生效 packs: core,collect" in out


# ── S119/S120 packs status / enable / disable ────────────

def test_s119_packs_status_reads_real_config(tmp_path, monkeypatch, capsys):
    _env(tmp_path, monkeypatch)
    packs_cmd.cmd_packs(_A(packs_action="status", target="", apply=False))
    out = capsys.readouterr().out
    assert "core,collect" in out and "core,knowledge" in out


def test_s120_disable_is_dry_run_by_default(tmp_path, monkeypatch, capsys):
    _, _, atom = _env(tmp_path, monkeypatch)
    before = atom.read_text(encoding="utf-8")
    packs_cmd.cmd_packs(_A(packs_action="disable", ids="knowledge", target="atomcode",
                           apply=False))
    out = capsys.readouterr().out
    assert "未写盘" in out and "加 --apply 生效" in out
    assert atom.read_text(encoding="utf-8") == before, "dry-run 不许改字节"


def test_s120_enable_apply_writes_only_managed_env(tmp_path, monkeypatch, capsys):
    _, _, atom = _env(tmp_path, monkeypatch)
    packs_cmd.cmd_packs(_A(packs_action="enable", ids="collect", target="atomcode",
                           apply=True))
    cfg = json.loads(atom.read_text(encoding="utf-8"))
    entry = cfg["mcpServers"]["vod-devkit"]
    assert entry["env"]["VOD_PACKS"] == "core,knowledge,collect"
    assert cfg["other"] == {"keep": 1}, "宿主其它键必须原样保留"
    assert (tmp_path / "atom-mcp.json.bak").exists(), "首改要落备份"


def test_s120_core_is_forced(tmp_path, monkeypatch, capsys):
    _, hermes, _ = _env(tmp_path, monkeypatch)
    packs_cmd.cmd_packs(_A(packs_action="disable", ids="core", target="hermes",
                           apply=True))
    cfg = json.loads(hermes.read_text(encoding="utf-8"))
    assert cfg["env"]["VOD_PACKS"].startswith("core"), "core 强制包含，禁不掉"


def test_s120_all_sets_every_pack(tmp_path, monkeypatch, capsys):
    _env(tmp_path, monkeypatch)
    packs_cmd.cmd_packs(_A(packs_action="all", ids="", target="hermes", apply=True))
    cfg = json.loads((tmp_path / "hermes-mcp.json").read_text(encoding="utf-8"))
    assert cfg["env"]["VOD_PACKS"] == ",".join(packs_mod.ALL_PACKS)


# ── S121 install --target all ───────────────────────────

def test_s121_target_all_loops_detected_hosts(monkeypatch, capsys):
    from vodkit_cli import install
    called = []
    orig = install.cmd_install          # 保留原实现：--target all 内部递归调的是模块名
    monkeypatch.setattr(install, "detect_targets", lambda: ["hermes", "atomcode"])
    monkeypatch.setattr(install, "cmd_install", lambda a: called.append(a.target))
    monkeypatch.setattr(install.common, "write_build_info", lambda strict=False: None)
    orig(_A(target="all", java_api_base="http://x", packs="", preset="collect"))
    assert called == ["hermes", "atomcode"]


def test_s121_target_all_without_hosts_is_loud(monkeypatch, capsys):
    from vodkit_cli import install
    monkeypatch.setattr(install, "detect_targets", lambda: [])
    monkeypatch.setattr(install.common, "write_build_info", lambda strict=False: None)
    with pytest.raises(SystemExit) as e:
        install.cmd_install(_A(target="all", java_api_base="http://x", packs="",
                               preset="collect"))
    assert e.value.code == 2
    assert "未探测到可自动安装的宿主" in capsys.readouterr().err


# ── S122 uninstall --target / --clean-global ────────────

def test_s122_uninstall_target_keeps_other_rows(tmp_path, monkeypatch, capsys):
    manifest, hermes_cfg, atom_cfg = _env(tmp_path, monkeypatch)
    uninstall.cmd_uninstall(_A(target="atomcode", clean_global=False))
    left = json.loads(manifest.read_text(encoding="utf-8"))
    assert [r["target"] for r in left["installs"]] == ["hermes"]
    assert hermes_cfg.exists()


def test_s122_uninstall_unknown_target_is_loud(tmp_path, monkeypatch, capsys):
    _env(tmp_path, monkeypatch)
    uninstall.cmd_uninstall(_A(target="dsh", clean_global=False))
    assert "没有该宿主的安装记录" in capsys.readouterr().out


def test_s122_clean_global_removes_only_known_residue(tmp_path, monkeypatch, capsys):
    _env(tmp_path, monkeypatch)
    residue = tmp_path / ".vod-devkit" / "payloads" / "0.0.9"
    residue.mkdir(parents=True)
    (residue / "vod_mcp").mkdir()
    keep = tmp_path / "not-ours"
    keep.mkdir()
    uninstall.cmd_uninstall(_A(target="hermes", clean_global=True))
    assert not residue.exists(), "无 payload.json 的历史载荷=残留，应清"
    assert keep.exists(), "不认得的目录一律不碰"


# ── S123 doctor/status --target ─────────────────────────

def test_s123_status_target_selects_row(tmp_path, monkeypatch, capsys):
    from vodkit_cli import doctor
    _env(tmp_path, monkeypatch)
    doctor.cmd_status(_A(target="atomcode"))
    out = capsys.readouterr().out
    assert '"target": "atomcode"' in out
    assert '"hermes"' not in out


def test_s123_status_unknown_target_exits(tmp_path, monkeypatch, capsys):
    from vodkit_cli import doctor
    _env(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        doctor.cmd_status(_A(target="dsh"))
    assert "没有该宿主的安装记录" in capsys.readouterr().out


# ── S126 范围守护：这仍是声音采集插件 ──────────────────────

def test_s126_scope_is_voice_collection_not_cloud_ops():
    """范围锁（负责人 2026-11-15 明确）：本仓只做"用户声音采集"。

    huaweicloud-devkit 的云操作面（KooCLI/OBS/sandbox/网关/区域感知）无对象——
    它们服务"操作云资源"，我们服务"把声音送进 VOD"。把它做成可执行断言，避免
    以后有人"顺手加个云工具"。
    """
    from vod_mcp import packs
    import json as _json
    from pathlib import Path as _P
    root = _P(__file__).resolve().parent.parent
    contract = _json.loads((root / "assets" / "contract" / "tools.schema.json").read_text(encoding="utf-8"))
    tools = contract.get("tools", contract)
    names = list(tools) if isinstance(tools, dict) else [t["name"] for t in tools]
    assert packs.ALL_PACKS == ("core", "collect", "knowledge"), "新增能力包=范围变更，必须先拍板"
    assert len(names) == 10, f"工具面变了（{len(names)}）：新增工具需同步契约与需求文档"
    assert all(n.startswith("vod_") for n in names)
    banned = ("hcloud", "koocli", "obs_", "sandbox", "region", "gateway", "openapi")
    hit = [n for n in names if any(b in n for b in banned)]
    assert not hit, f"云操作面工具不得进入本仓：{hit}"

# ── S127 自动扫描后的交互选择（对齐 devkit 的 0/1/N 体验）──────

import io as _io
from vodkit_cli import install as _install


def _fake_tty(monkeypatch, text: str):
    monkeypatch.setattr(_install, "_is_tty", lambda: True)
    monkeypatch.setattr("sys.stdin", _io.StringIO(text))


def test_s127_multiselect_picks_indices(monkeypatch, capsys):
    called = []
    orig = _install.cmd_install
    monkeypatch.setattr(_install, "detect_targets",
                        lambda: ["hermes", "opencode", "atomcode"])
    monkeypatch.setattr(_install, "cmd_install", lambda a: called.append(a.target))
    monkeypatch.setattr(_install.common, "write_build_info", lambda strict=False: None)
    _fake_tty(monkeypatch, "1,3\n")
    orig(_A(target="auto", java_api_base="http://x", packs="", preset="collect"))
    assert called == ["hermes", "atomcode"]


def test_s127_invalid_then_valid_reprompts(monkeypatch, capsys):
    orig = _install.cmd_install
    monkeypatch.setattr(_install, "detect_targets", lambda: ["hermes", "opencode"])
    monkeypatch.setattr(_install, "HOST_ADAPTERS", {})   # 选择完成即到此为止
    monkeypatch.setattr(_install.common, "write_build_info", lambda strict=False: None)
    _fake_tty(monkeypatch, "9\n2\n")
    with pytest.raises(SystemExit):
        orig(_A(target="auto", java_api_base="http://x", packs="", preset="collect"))
    out = capsys.readouterr().out
    assert "探测到宿主: opencode" in out, "非法输入重问一次，第二次生效"


def test_s127_cancel_exits_without_installing(monkeypatch, capsys):
    called = []
    orig = _install.cmd_install
    monkeypatch.setattr(_install, "detect_targets", lambda: ["hermes", "opencode"])
    monkeypatch.setattr(_install, "cmd_install", lambda a: called.append(a.target))
    monkeypatch.setattr(_install.common, "write_build_info", lambda strict=False: None)
    _fake_tty(monkeypatch, "\n")
    with pytest.raises(SystemExit) as e:
        orig(_A(target="auto", java_api_base="http://x", packs="", preset="collect"))
    assert e.value.code == 2 and not called


def test_s127_non_tty_never_guesses(monkeypatch, capsys):
    orig = _install.cmd_install
    monkeypatch.setattr(_install, "detect_targets", lambda: ["hermes", "opencode"])
    monkeypatch.setattr(_install, "_is_tty", lambda: False)
    monkeypatch.setattr(_install.common, "write_build_info", lambda strict=False: None)
    with pytest.raises(SystemExit) as e:
        orig(_A(target="auto", java_api_base="http://x", packs="", preset="collect"))
    assert e.value.code == 2
    assert "非交互环境不猜" in capsys.readouterr().err


def test_s127_zero_detected_asks_for_target_name(monkeypatch, capsys):
    orig = _install.cmd_install
    monkeypatch.setattr(_install, "detect_targets", lambda: [])
    from vod_mcp.host_adapters import generic as _g
    monkeypatch.setattr(_g, "detect_known", lambda: [])
    monkeypatch.setattr(_install, "HOST_ADAPTERS", {})   # 只验选择：适配器缺=到此为止
    monkeypatch.setattr(_install.common, "write_build_info", lambda strict=False: None)
    _fake_tty(monkeypatch, "hermes\n")
    with pytest.raises(SystemExit):
        orig(_A(target="auto", java_api_base="http://x", packs="", preset="collect"))
    assert "探测到宿主: hermes" in capsys.readouterr().out


def test_s127_all_skips_dsh_without_profile(monkeypatch, capsys):
    called = []
    orig = _install.cmd_install
    monkeypatch.setattr(_install, "detect_targets", lambda: ["dsh", "hermes"])
    monkeypatch.setattr(_install, "cmd_install", lambda a: called.append(a.target))
    monkeypatch.setattr(_install.common, "write_build_info", lambda strict=False: None)
    orig(_A(target="all", java_api_base="http://x", packs="", preset="collect",
            dsh_profile=""))
    assert called == ["hermes"]
    assert "跳过 dsh" in capsys.readouterr().err

