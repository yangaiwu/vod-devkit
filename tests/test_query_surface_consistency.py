"""查询面一致性门禁（D1/D2，0.5.12）。

背景：同一台机器上 `version` / `packs status` 与 `host_matrix --audit` 曾给出**相反**结论：
- dsh 的 pack 明明写在 patch 托管块的 `env.VOD_PACKS`（可读 YAML），status 说
  `unsupported 不是 JSON 形态`；
- codex-desktop 明明已在 marketplace 登记（audit PASS、10 工具在跑），status 说
  `missing 配置里没有 vod-devkit 条目`。

门禁意思：**audit 认为装好的宿主，status 不得报 missing/unsupported**。这里用两种
非 MCP 落点的读法钉住它——形态判定错了，这几条会红。

覆盖边界（评审 a 项，2026-11-16 明确）：这是**单元级形态断言**，直接调
`packs_cmd._read_effective()` + 合成配置，挡得住"某种落点的读法退化"，
挡不住"audit 新增了宿主而 status 没跟上"这类两面分叉——那需要真跑一次
`status` 与 `audit` 并比对输出，属于集成门禁的范围，此处不覆盖。
"""
import json

from vodkit_cli import packs_cmd


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _patch(profile_dir, body: str):
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "cordis.patch.yml").write_text(body, encoding="utf-8")


MCP_PATCH = """
# vod-devkit DSH integration start
- insert:
    - id: vod-devkit-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: vod-devkit
        env:
          VOD_DEVKIT_HOME: /root/.vod-devkit/state
          VOD_PACKS: core,collect
    - id: vod-devkit
      config:
        registerTools: false
        product: CodeArts
# vod-devkit DSH integration end
"""

DEGRADED_PATCH = """
# vod-devkit DSH integration start
- insert:
    - id: vod-devkit
      name: dsh-vod-devkit
      config:
        product: CodeArts
# vod-devkit DSH integration end
"""


def test_d1_dsh_mcp_mode_packs_are_readable(tmp_path, monkeypatch):
    """MCP 模式：从 patch 托管块读 env.VOD_PACKS —— 不许报 unsupported（D1）。"""
    home = _home(tmp_path, monkeypatch)
    _patch(home / ".dsh" / "profiles" / "web", MCP_PATCH)
    state, eff, note = packs_cmd._read_effective({"target": "dsh", "dshProfile": "web"})
    assert state == "ok", f"MCP 形态必须可读，实际 {state}: {note}"
    assert set(eff) == {"core", "collect"}, eff
    assert "mcp-client" in note and "VOD_PACKS" in note, note


def test_d1_dsh_degraded_mode_is_na_not_unsupported(tmp_path, monkeypatch):
    """降级形态没有 env → n/a（壳固定 6 工具），仍不许说 unsupported。"""
    home = _home(tmp_path, monkeypatch)
    _patch(home / ".dsh" / "profiles" / "web", DEGRADED_PATCH)
    state, _eff, note = packs_cmd._read_effective({"target": "dsh", "dshProfile": "web"})
    assert state == "n/a", f"降级形态应是 n/a，实际 {state}: {note}"
    assert "降级" in note, note


def test_d1_dsh_unknown_pack_value_is_unparsable(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _patch(home / ".dsh" / "profiles" / "web", MCP_PATCH.replace("core,collect", "core,nosuchpack"))
    state, _eff, note = packs_cmd._read_effective({"target": "dsh", "dshProfile": "web"})
    assert state == "unparsable", f"未知 pack 必须报错而不是当 ok；实际 {state}: {note}"


def test_d2_codex_desktop_marketplace_registration_is_not_missing(tmp_path, monkeypatch):
    """marketplace 登记形态：登记了就 n/a，不许报 missing（D2）。
    audit 在同一台机器上报 PASS —— 两个面必须不矛盾。"""
    home = _home(tmp_path, monkeypatch)
    mp = home / ".agents" / "plugins" / "marketplace.json"
    mp.parent.mkdir(parents=True)
    mp.write_text(json.dumps({"name": "personal", "plugins": [
        {"name": "vod-devkit", "source": {"source": "local", "path": "./plugins/vod-devkit"}}]}),
        encoding="utf-8")
    state, _eff, note = packs_cmd._read_effective({"target": "codex-desktop"})
    assert state == "n/a", f"marketplace 登记必须 n/a，实际 {state}: {note}"
    assert "登记" in note and "missing" not in note, note


def test_d2_codex_desktop_unregistered_is_missing(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    mp = home / ".agents" / "plugins" / "marketplace.json"
    mp.parent.mkdir(parents=True)
    mp.write_text(json.dumps({"name": "personal", "plugins": [{"name": "other-plugin"}]}),
                  encoding="utf-8")
    state, _eff, note = packs_cmd._read_effective({"target": "codex-desktop"})
    assert state == "missing", f"真没登记才是 missing；实际 {state}: {note}"
    assert "未登记" in note, note


def test_query_surface_never_says_unsupported_for_installed_hosts(tmp_path, monkeypatch):
    """门禁总纲：两种非 JSON 形态的宿主，读法错误时会退化成 unsupported/missing，
    这条把"已经装好却查不到"的退化固定在用例里。"""
    home = _home(tmp_path, monkeypatch)
    _patch(home / ".dsh" / "profiles" / "headless", MCP_PATCH)
    mp = home / ".agents" / "plugins" / "marketplace.json"
    mp.parent.mkdir(parents=True)
    mp.write_text(json.dumps({"plugins": [{"name": "vod-devkit"}]}), encoding="utf-8")
    for row in ({"target": "dsh", "dshProfile": "headless"}, {"target": "codex-desktop"}):
        state, _eff, note = packs_cmd._read_effective(row)
        assert state in ("ok", "n/a"), f"{row['target']} 退化成了 {state}: {note}"