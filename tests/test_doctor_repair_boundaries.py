"""S152：doctor 自愈的边界（自愈判据不许用"当前进程环境"）。

背景（2026-11-16 评审实锤，探针复现）：旧判据是「安装器完整块文本 == patch 里已有文本」，
而块里内嵌 sys.executable / machine_state_home() / payloadDir，全按**当前 doctor 进程**求值。
于是四条静默改写：换解释器改 command、手工 uiBase=/dsh 被写回、PATH 无 dsh 时删掉 MCP 块
退回 6 工具、manifest 缺 payloadDir 时写成相对路径。

新口径（结构化不变量 + 安装期真源）：
- 缺 MCP 块 / 缺壳块 / 壳未 registerTools:false  → 补（形态坏，S151 的目标仍成立）
- 已有块但与安装期记录字段不同               → 只报告，不动字节
- 环境不可判定（manifest 无 payloadDir / 无 dshPatch / 无 mcpClient 记录）→ 不动字节 + 指引

S153：dsh 多 profile 的账本与 prune 的"在用"集合。
"""
import json
from types import SimpleNamespace

from tests.test_dsh_mcp_mode import env as env_fixture  # noqa: F401  （fixture 同册）
from tests.test_dsh_mcp_mode import engine_stub as engine_stub_fixture  # noqa: F401
from tests.test_dsh_mcp_mode import _fake_dsh_root  # noqa: F401

env = env_fixture
engine_stub = engine_stub_fixture

from vod_mcp.host_adapters import dsh as _dsh
from vod_mcp import payload as P
from vodkit_cli import common as _common
from vodkit_cli import doctor as _doc


def _patch_path(env, prof="web"):
    p = env["home"] / ".dsh" / "profiles" / prof / "cordis.patch.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _payload(env, ver="0.5.16"):
    d = env["home"] / ".vod-devkit" / "payloads" / ver
    (d / "vod_mcp").mkdir(parents=True, exist_ok=True)
    (d / "vod_mcp" / "server.py").write_text("# stub\n", encoding="utf-8")
    (d / "payload.json").write_text(json.dumps({"version": ver}), encoding="utf-8")
    return d


def _mf(env, prof="web", **over):
    mf = {"dshProfile": prof, "product": "CodeArts", "apiBase": "https://e",
          "payloadDir": str(_payload(env)), "packs": "core,collect"}
    mf.update(over)
    return mf


def _block(mf, mcp_ver="0.2.1-rc.5"):
    args = SimpleNamespace(product=mf.get("product") or "", java_api_base=mf.get("apiBase") or "")
    return _dsh._patch_block(args, mcp_ver, __import__("pathlib").Path(mf["payloadDir"]),
                             mf.get("packs") or "core")


# ── S152-1 解释器：安装期记录优先，不许换成"跑 doctor 的那个 python" ────────────
def test_s152_doctor_keeps_recorded_interpreter(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    monkeypatch.setenv("PATH", str(env["stub"]) + ":/usr/bin:/bin")
    mf = _mf(env, dshPatch={"command": "/opt/app/venv/bin/python3",
                            "stateHome": "/tmp/st", "mcpClient": "0.2.1-rc.5"})
    p = _patch_path(env)
    p.write_text(_block(mf).replace(str(__import__("sys").executable),
                                    "/opt/app/venv/bin/python3"), encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert "/opt/app/venv/bin/python3" in before
    _doc._repair_dsh_patch_block(mf)
    after = p.read_text(encoding="utf-8")
    assert "/opt/app/venv/bin/python3" in after, f"自愈把安装期解释器换掉了：{after}"
    assert after == before or "command: /opt/app/venv/bin/python3" in after


# ── S152-2 手工定制（公网反代 uiBase=/dsh）不许被回写成 apiBase ────────────────
def test_s152_doctor_does_not_overwrite_manual_uibase(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    monkeypatch.setenv("PATH", str(env["stub"]) + ":/usr/bin:/bin")
    mf = _mf(env, dshPatch={"command": __import__("sys").executable,
                            "stateHome": "/tmp/st", "mcpClient": "0.2.1-rc.5"})
    p = _patch_path(env)
    text = _block(mf).replace("        uiBase: https://e", "        uiBase: /dsh")
    p.write_text(text, encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    _doc._repair_dsh_patch_block(mf)
    after = p.read_text(encoding="utf-8")
    assert "uiBase: /dsh" in after, f"自愈把手工 uiBase 覆盖了：{after}"
    assert after == before, "字段级差异只报告，不该改字节"


# ── S152-3 PATH 里没有 dsh：不许因此降级成 6 工具 ─────────────────────────────
def test_s152_doctor_without_dsh_cli_keeps_mcp_block(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    # 故意不给桩 dsh：模拟 systemd / 非登录 shell
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    mf = _mf(env, dshPatch={"command": __import__("sys").executable,
                            "stateHome": "/tmp/st", "mcpClient": "0.2.1-rc.5"})
    p = _patch_path(env)
    p.write_text(_block(mf), encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert "- id: vod-devkit-mcp" in before
    _doc._repair_dsh_patch_block(mf)
    after = p.read_text(encoding="utf-8")
    assert "- id: vod-devkit-mcp" in after, f"PATH 无 dsh 就把 MCP 块删了：{after}"
    assert after == before, "环境不可判定时不许动字节"


# ── S152-4 manifest 缺 payloadDir：不许重写成相对路径 ──────────────────────────
def test_s152_doctor_missing_payloaddir_does_not_touch(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    monkeypatch.setenv("PATH", str(env["stub"]) + ":/usr/bin:/bin")
    mf = _mf(env, dshPatch={"command": __import__("sys").executable,
                            "stateHome": "/tmp/st", "mcpClient": "0.2.1-rc.5"})
    p = _patch_path(env)
    p.write_text(_block(mf), encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    blind = dict(mf)
    blind.pop("payloadDir")
    fixed = _doc._repair_dsh_patch_block(blind)
    after = p.read_text(encoding="utf-8")
    assert fixed is None and after == before, f"payloadDir 缺失却改了字节：{after}"


# ── S152-5 正向：真的缺 MCP 块时要补（S151 行为不得回退）───────────────────────
def test_s152_doctor_repairs_missing_mcp_block(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    monkeypatch.setenv("PATH", str(env["stub"]) + ":/usr/bin:/bin")
    mf = _mf(env, dshPatch={"command": __import__("sys").executable,
                            "stateHome": "/tmp/st", "mcpClient": "0.2.1-rc.5"})
    p = _patch_path(env)
    p.write_text("- insert:\n    - id: vod-devkit\n      name: dsh-vod-devkit\n"
                 "      config:\n        product: CodeArts\n", encoding="utf-8")
    fixed = _doc._repair_dsh_patch_block(mf)
    assert fixed, "MCP 块缺失时必须自愈"
    text = p.read_text(encoding="utf-8")
    assert "- id: vod-devkit-mcp" in text and "registerTools: false" in text, text


# ── S153-1 账本行键 = (target, profile)：两个 dsh profile 两行 ─────────────────
def test_s153_install_rows_keyed_by_dsh_profile():
    prev = {"installs": [{"target": "dsh", "dshProfile": "headless", "installedAt": "1"}]}
    row = {"target": "dsh", "dshProfile": "web", "installedAt": "2"}
    rows = _common._install_rows(prev, row)
    assert len(rows) == 2, f"第二个 profile 顶掉了第一个：{rows}"
    assert {r["dshProfile"] for r in rows} == {"headless", "web"}
    # 同一 profile 重装仍是覆盖，不是新增
    rows2 = _common._install_rows({"installs": rows}, dict(row, installedAt="3"))
    assert len(rows2) == 2


# ── S153-2 prune 的"在用"集合要扫 profile patch，不只 manifest 的 payloadDir ────
def test_s153_prune_respects_payload_referenced_by_profile_patch(tmp_path, monkeypatch):
    home = tmp_path / "vk"
    home.mkdir()
    monkeypatch.setenv("VOD_PAYLOAD_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path))

    def mk(ver):
        d = home / "payloads" / ver
        (d / "vod_mcp").mkdir(parents=True, exist_ok=True)
        (d / "vod_mcp" / "server.py").write_text("# stub\n", encoding="utf-8")
        (d / "payload.json").write_text(json.dumps({"version": ver}), encoding="utf-8")
        return d

    cur = mk("0.5.16")
    old = mk("0.5.15")
    # 账本只记了 web（最新一次安装），而 headless 的 patch 仍指向 0.5.15
    prof = tmp_path / ".dsh" / "profiles" / "headless"
    prof.mkdir(parents=True)
    (prof / "cordis.patch.yml").write_text(
        "- insert:\n    - id: vod-devkit-mcp\n      config:\n"
        f"        args:\n          - {old}/vod_mcp/server.py\n", encoding="utf-8")
    rows = [{"target": "dsh", "dshProfile": "web", "payloadDir": str(cur)}]
    cands = P.prune_candidates(rows)
    versions = [v for _p, v, _s in cands]
    assert "0.5.15" not in versions, f"headless patch 仍在用的载荷被列为可删：{cands}"


# ── S152 辅助纯函数真值表（重构后锁住判定面，防止"顺手改回整块比对"）──────────
def test_s152_form_gap_matrix():
    from vodkit_cli import doctor as _doc
    ok = {"present_mcp": True, "present_shell": True, "register_tools_false": True}
    assert _doc._dsh_form_gap(ok, True) == ""
    assert _doc._dsh_form_gap(dict(ok, present_mcp=False), True) == "缺 MCP 块"
    assert _doc._dsh_form_gap(dict(ok, present_shell=False), True) == "缺壳块"
    assert _doc._dsh_form_gap(dict(ok, register_tools_false=False), True).startswith("壳未")
    # 降级形态（want_mcp=False）：缺 MCP 块与壳自注册都不算缺口
    assert _doc._dsh_form_gap(
        dict(ok, present_mcp=False, register_tools_false=False), False) == ""


def test_s152_field_diffs_are_report_only():
    from vodkit_cli import doctor as _doc
    facts = {"command": "/a/python", "state_home": "/s1",
             "server_py": "/old/payloads/0.5.9/vod_mcp/server.py"}
    snap = {"command": "/b/python", "stateHome": "/s2"}
    diffs = _doc._dsh_field_diffs(facts, snap, "/p/new")
    assert len(diffs) == 3, diffs
    assert any("command=" in d for d in diffs)
    assert any("VOD_DEVKIT_HOME=" in d for d in diffs)
    assert any("入口=" in d for d in diffs)
    # 无安装期记录 / 无 payloadDir → 不产出差异（不许凭猜判 drift）
    assert _doc._dsh_field_diffs(facts, {}, "") == []


# ── S152-6（R1）形态缺口不许吃掉手工定制：重建要吸收 facts 里已有的值 ─────────
def test_s152_gap_repair_preserves_manual_fields(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    monkeypatch.setenv("PATH", str(env["stub"]) + ":/usr/bin:/bin")
    mf = _mf(env, dshPatch={"command": __import__("sys").executable,
                            "stateHome": "/tmp/st", "mcpClient": "0.2.1-rc.5"})
    p = _patch_path(env)
    # E 场景：壳未关注册（形态缺口）+ 手工 uiBase=/dsh（公网反代定制）
    p.write_text(_block(mf).replace("        uiBase: https://e", "        uiBase: /dsh")
                 .replace("        registerTools: false\n", ""), encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert "uiBase: /dsh" in before and "registerTools: false" not in before
    fixed = _doc._repair_dsh_patch_block(mf)
    assert fixed, "形态缺口必须补（壳未关注册）"
    after = p.read_text(encoding="utf-8")
    assert "registerTools: false" in after, after
    assert "uiBase: /dsh" in after, f"补缺口时把手工 uiBase 重置了：{after}"


# ── S152-7（R3）无安装期记录一律不动字节（老账本只提示重装）──────────────────
def test_s152_no_snapshot_never_rewrites(env, monkeypatch):
    _fake_dsh_root(env)
    monkeypatch.setenv("HOME", str(env["home"]))
    monkeypatch.setenv("PATH", str(env["stub"]) + ":/usr/bin:/bin")
    mf = _mf(env)                     # 故意不给 dshPatch（老账本形态）
    p = _patch_path(env)
    p.write_text(_block(mf).replace("        registerTools: false\n", ""), encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert _doc._repair_dsh_patch_block(mf) is None
    assert p.read_text(encoding="utf-8") == before


# ── S153-3（R2）巡检必须逐个 profile 判，且报文带 profile 名 ─────────────────
def _load_host_matrix():
    import importlib.util
    from pathlib import Path as _P
    path = _P(__file__).resolve().parent.parent / "scripts" / "host_matrix.py"
    spec = importlib.util.spec_from_file_location("hm_audit_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mk_profile(home, prof, good: bool):
    d = home / ".dsh" / "profiles" / prof
    pkg = d / "node_modules" / "dsh-vod-devkit"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "package.json").write_text(json.dumps({"version": "0.5.16"}), encoding="utf-8")
    mcp = ("    - id: vod-devkit-mcp\n      name: '@deepseek-ai/dsh-mcp-client'\n"
           "      config:\n        serverName: vod-devkit\n")
    shell = ("    - id: vod-devkit\n      name: dsh-vod-devkit\n      config:\n"
             + ("        registerTools: false\n" if good else "")
             + "        product: CodeArts\n")
    (d / "cordis.patch.yml").write_text("- insert:\n" + mcp + shell, encoding="utf-8")


def test_s153_dsh_audit_checks_every_profile(tmp_path):
    hm = _load_host_matrix()
    _mk_profile(tmp_path, "web", good=False)      # 有 mcp 块但壳未关注册 → 纸面 DRIFT
    _mk_profile(tmp_path, "headless", good=True)
    verdict, msg = hm.audit_host("dsh", "0.5.16", home=tmp_path)
    assert verdict == "DRIFT", f"web 坏了却报 PASS：{verdict} {msg}"
    assert "[web]" in msg, f"报文没点名是哪个 profile：{msg}"

    _mk_profile(tmp_path, "web", good=True)
    verdict2, msg2 = hm.audit_host("dsh", "0.5.16", home=tmp_path)
    assert verdict2 == "PASS", msg2
    assert "[web]" in msg2 and "[headless]" in msg2, f"PASS 报文也要逐个列出：{msg2}"