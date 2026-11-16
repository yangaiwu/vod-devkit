"""宿主安装矩阵的门禁用例（scripts/host_matrix.py 的子集跑法）。

完整矩阵在 CI 的 host-matrix job 里跑（9 个宿主）；这里只跑 3 个不需要宿主 CLI 的
代表项，确保"矩阵脚本本身没坏"能进日常 pytest：
- workbuddy：mcpServers + env 形态
- codeartsdoer：mcp 段 + command 数组（CodeArts 家族）
- codex-desktop：marketplace 登记 + 插件目录

断言：脚本退出 0，且输出里这三项都是 PASS（SKIP 不算通过——它们不依赖 CLI）。
"""
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "host_matrix.py"


def test_matrix_subset_passes():
    r = subprocess.run([sys.executable, str(SCRIPT),
                        "--host", "workbuddy", "--host", "codeartsdoer",
                        "--host", "codex-desktop"],
                       capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    for host in ("workbuddy", "codeartsdoer", "codex-desktop"):
        assert f"[{host}] PASS" in out, out
    assert "0 FAIL" in out, out


def _load_matrix():
    """把脚本当模块加载（它有 __main__ 守卫，import 不执行矩阵）。"""
    spec = importlib.util.spec_from_file_location("host_matrix_mod", SCRIPT)
    assert spec is not None and spec.loader is not None, f"无法加载 {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── S141：隔离 HOME 必须真的隔离每个宿主的"家目录" ──────────────
#
# 实锤（2026-11-16）：hermes CLI 不认 $HOME，只认 HERMES_HOME。矩阵只设了 HOME，
# 于是在隔离 HOME 里装 hermes 时，真实 ~/.hermes/config.yaml 被改写成
# `<scratch>/vod-matrix-XXXX/home/.vod-devkit/payloads/...` + 桩地址 127.0.0.1:9/stub；
# scratch 一清，真机 hermes 的 vod 工具就永久掉线（"lost its stdio subprocess"）。
# 这条锁的就是"矩阵 env 里必须有 HERMES_HOME，且它指向隔离 HOME"。

def test_s141_hermes_install_runs_with_isolated_hermes_home(tmp_path, monkeypatch):
    m = _load_matrix()
    monkeypatch.setattr(m.shutil, "which", lambda name: "/usr/bin/" + name)
    seen = {}

    class _Short(Exception):
        pass

    def fake_install(env, host, extra=()):
        seen.update(env)
        raise _Short()   # 只验 env，不真装

    monkeypatch.setattr(m, "_run_install", fake_install)
    try:
        m.run_host("hermes", tmp_path, "0.0.0")
    except _Short:
        pass
    hh = seen.get("HERMES_HOME")
    assert hh, ("矩阵给 hermes 的 env 里没有 HERMES_HOME——hermes CLI 不认 $HOME，"
                "缺它就会把真实 ~/.hermes/config.yaml 改成隔离 HOME 的路径（2026-11-16 实锤）")
    assert hh.startswith(str(tmp_path)), f"HERMES_HOME 不在隔离 HOME 内：{hh}"


def test_s141_hermes_home_dir_is_seeded_so_cli_does_not_touch_real_one(tmp_path, monkeypatch):
    m = _load_matrix()
    real = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).resolve()
    monkeypatch.setenv("HERMES_HOME", str(real))      # 模拟"外层会话已经指了真实 profile"
    env = m._isolated_env("hermes", tmp_path)
    home = Path(env["HERMES_HOME"])
    assert home.parent == tmp_path, f"HERMES_HOME 应落在隔离 HOME 下：{home}"
    assert home.resolve() != real, "继承了外层的 HERMES_HOME（隔离失效，会写真实 profile）"


def test_s141_hermes_cli_is_shimmed_so_matrix_never_hangs(tmp_path):
    """空 HERMES_HOME 下 hermes CLI 会自举依赖 → 实测卡到 300s 超时，整轮矩阵 FAIL。

    沙箱里的 CLI 一律用"立刻失败"的 shim 挡住：适配器 best-effort 继续，
    矩阵断言落在条目 + 载荷自证（真机生效入口由 --audit 判）。
    """
    m = _load_matrix()
    env = m._isolated_env("hermes", tmp_path)
    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path / "bin"), "shim 目录必须在 PATH 最前"
    r = subprocess.run(["hermes", "profile", "list"], env=env, capture_output=True,
                       text=True, timeout=15)
    assert r.returncode != 0, "沙箱里的 hermes 不应被真跑（会把依赖装进沙箱/真机）"
    assert "sandbox" in (r.stderr or r.stdout).lower(), r.stderr


# ── S142：巡检要看"宿主实际生效的入口"，不是 manifest/备片 ─────────────────
#
# 实锤（2026-11-16）：
# ① codex 同时存在 personal(0.5.4) 与 vod-local(0.5.9) 两份缓存，config.toml 里
#    personal 是 enabled；巡检按 `cache/*/*/*/.mcp.json` 排序取最后一份 → 报 0.5.9 PASS，
#    而 codex 实际跑 0.5.4（server 日志 argv 实锤）。
# ② hermes 的生效入口是 config.yaml 的 mcp_servers.vod-devkit；巡检读的是备片
#    ~/.hermes/mcp/vod-devkit.json → 报 PASS，而 config.yaml 指向已被清理的路径。

STUB_SERVER = textwrap.dedent('''
    import json, sys
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg.get("method") == "initialize":
            print(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"),
                              "result": {"protocolVersion": "2025-06-18",
                                         "capabilities": {"tools": {}},
                                         "serverInfo": {"name": "stub", "version": "0"}}}), flush=True)
        elif msg.get("method") == "tools/list":
            print(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": {"tools": [
                {"name": "vod_submit_voices", "description": "", "inputSchema": {"type": "object"}},
                {"name": "vod_devkit_info", "description": "", "inputSchema": {"type": "object"}}]}}), flush=True)
        elif msg.get("method") == "tools/call":
            print(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": {
                "structuredContent": {"version": "9.9.9"},
                "content": [{"type": "text", "text": "{\\"version\\": \\"9.9.9\\"}"}], "isError": False}}), flush=True)
''')


def _stub(tmp_path: Path) -> Path:
    p = tmp_path / "stub_server.py"
    p.write_text(STUB_SERVER, encoding="utf-8")
    return p


def test_s142_audit_hermes_reads_effective_config_yaml_entry(tmp_path):
    m = _load_matrix()
    stub = _stub(tmp_path)
    (tmp_path / ".hermes").mkdir()
    # 备片（旧判据读它）：指向可跑通的 stub —— 旧代码因此 PASS
    (tmp_path / ".hermes" / "mcp").mkdir()
    (tmp_path / ".hermes" / "mcp" / "vod-devkit.json").write_text(json.dumps({
        "name": "vod-devkit", "command": sys.executable, "args": [str(stub)], "env": {}}),
        encoding="utf-8")
    # 生效入口（新判据读它）：指向已删路径
    (tmp_path / ".hermes" / "config.yaml").write_text(textwrap.dedent(f"""
        mcp_servers:
          vod-devkit:
            command: {sys.executable}
            args:
              - {tmp_path}/gone/payloads/0.5.9/vod_mcp/server.py
            env:
              VOD_PACKS: core,collect
            enabled: true
        """), encoding="utf-8")
    state, msg = m.audit_host("hermes", "9.9.9", home=tmp_path)
    assert state == "DRIFT", f"备片能跑通但生效入口是死路径，巡检必须报 DRIFT；实际 {state}: {msg}"
    assert "config.yaml" in msg or "生效" in msg, msg


def test_s142_audit_codex_uses_enabled_marketplace_not_sorted_last(tmp_path, monkeypatch):
    m = _load_matrix()
    stub = _stub(tmp_path)
    codex = tmp_path / ".codex"
    (codex / "plugins" / "cache" / "personal" / "vod-devkit" / "0.5.4").mkdir(parents=True)
    (codex / "plugins" / "cache" / "vod-local" / "vod-devkit" / "0.5.9").mkdir(parents=True)
    (codex / "config.toml").write_text(textwrap.dedent(f"""
        [plugins."vod-devkit@personal"]
        enabled = true

        [marketplaces.personal]
        source_type = "local"
        source = "{tmp_path}/personal-src"
        """), encoding="utf-8")
    for mkt in ("personal", "vod-local"):
        (codex / "plugins" / "cache" / mkt / "vod-devkit" / ("0.5.4" if mkt == "personal" else "0.5.9")
         / ".mcp.json").write_text(json.dumps({"mcpServers": {"vod-devkit": {
             "command": sys.executable, "args": [str(stub)],
             "env": {"VOD_MARKET": mkt}}}}), encoding="utf-8")
    monkeypatch.setenv("VOD_MARKET", "")
    state, msg = m.audit_host("codex", "9.9.9", home=tmp_path)
    # stub 恒回 9.9.9，唯一能区分"读了哪份"的信号必须在报文里说出市场名
    assert "personal" in msg, f"巡检没说清 codex 实际生效的市场（报文={msg!r}）——排序取最后一份会报 vod-local 假绿"


def _dsh_profile(home: Path, *, mcp: bool, register_tools: bool, shell_ver: str) -> None:
    prof = home / ".dsh" / "profiles" / "web"
    prof.mkdir(parents=True, exist_ok=True)
    lines = ["- insert:"]
    if mcp:
        lines += ["    - id: vod-devkit-mcp", "      name: '@deepseek-ai/dsh-mcp-client'"]
    lines += ["    - id: vod-devkit", "      config:"]
    if register_tools is False:
        lines.append("        registerTools: false")
    (prof / "cordis.patch.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if shell_ver:
        pkg = prof / "node_modules" / "dsh-vod-devkit"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "package.json").write_text(json.dumps({"version": shell_ver}), encoding="utf-8")


def test_s146_audit_dsh_reports_mcp_mode_only_when_shell_stops_registering(tmp_path):
    """D-dsh-mcp-b-1：dsh 巡检必须看"双块 + 壳不注册"，否则半坏态（patch 写了
    registerTools:false 而 profile 里壳还是旧版本、字段根本不存在）会报假 PASS。"""
    m = _load_matrix()
    # ① 完整 B 模式
    _dsh_profile(tmp_path, mcp=True, register_tools=False, shell_ver="0.5.10")
    state, msg = m.audit_host("dsh", "0.5.10", home=tmp_path)
    assert state == "PASS", f"完整 B 模式必须 PASS；实际 {state}: {msg}"
    assert "MCP 模式" in msg and "壳只留 UI" in msg, msg
    # ② 有 mcp 块但壳仍注册 → 双 submit
    _dsh_profile(tmp_path, mcp=True, register_tools=True, shell_ver="0.5.10")
    state, msg = m.audit_host("dsh", "0.5.10", home=tmp_path)
    assert state == "DRIFT" and "双 submit" in msg, f"壳未关注册必须 DRIFT；实际 {state}: {msg}"
    # ③ 壳版本没升（add 未钉版本的真机实锤）
    _dsh_profile(tmp_path, mcp=True, register_tools=False, shell_ver="0.5.9")
    state, msg = m.audit_host("dsh", "0.5.10", home=tmp_path)
    assert state == "DRIFT" and "0.5.9" in msg, f"壳旧版本必须 DRIFT；实际 {state}: {msg}"
    # ④ 无 mcp-client → 降级形态，壳自注册（不是 FAIL）
    _dsh_profile(tmp_path, mcp=False, register_tools=True, shell_ver="0.5.10")
    state, msg = m.audit_host("dsh", "0.5.10", home=tmp_path)
    assert "降级" in msg, f"降级形态必须在报文里写清；实际 {state}: {msg}"


def test_s150_probe_rejects_entry_pointing_at_old_payload(tmp_path, monkeypatch):
    """巡检假绿地基（S150）：entry 指向旧载荷 → 必须 DRIFT。

    实测根因：`_pin_roots()` 把 VOD_DEVKIT_SRC_ROOT/DIST_ROOT 钉在进程 env，
    `_probe` 又 os.environ.copy() 继承，于是载荷 server 的 provenance 去读**仓根**
    build-info.json —— 0.5.11 的载荷自述 0.5.14，8 个非 dsh 宿主全部假 PASS。
    本用例固定两条判据：① 子进程不继承仓根变量；② 载荷目录的 build-info 版本
    必须等于期望版本（文件自证，不受 env 影响）。
    """
    m = _load_matrix()
    monkeypatch.setenv("VOD_DEVKIT_DIST_ROOT", str(ROOT))       # 模拟被钉住的巡检进程
    monkeypatch.setenv("VOD_DEVKIT_SRC_ROOT", str(ROOT / "src"))
    old = tmp_path / "payloads" / "0.5.11"
    (old / "vod_mcp").mkdir(parents=True)
    (old / "build-info.json").write_text(json.dumps({"version": "0.5.11", "commitSha": "deadbeef"}),
                                         encoding="utf-8")
    server = old / "vod_mcp" / "server.py"
    server.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n", encoding="utf-8")
    ok, msg = m._probe({"command": sys.executable, "args": [str(server)], "env": {}}, "0.5.14")
    assert not ok, f"载荷 0.5.11 而期望 0.5.14 必须 DRIFT，实际 ok={ok}: {msg}"
    assert "载荷版本 0.5.11" in msg, msg


def test_s150_payload_version_helper_reads_payload_build_info(tmp_path):
    m = _load_matrix()
    p = tmp_path / "p" / "0.5.11" / "vod_mcp"
    p.mkdir(parents=True)
    (p / "server.py").write_text("", encoding="utf-8")
    (tmp_path / "p" / "0.5.11" / "build-info.json").write_text(
        json.dumps({"version": "0.5.11"}), encoding="utf-8")
    assert m._payload_version(["/usr/bin/python3", str(p / "server.py")]) == "0.5.11"
    assert m._payload_version(["/usr/bin/python3"]) is None