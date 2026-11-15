"""凭据单入口（auth）与技能读取教法的用例（S124-S125）。

背景：
- S124（D-auth-init-1）：换 key 此前只有"删 runtime.json 重装"一条路，运维不可解释。
  `auth init` 把它收成唯一写入入口：缺省只校验 + 显示指纹（绝不打印明文），
  `--apply` 才写，写后读回，引擎可达且判拒时当场拒绝。
- S125（D-skill-teaching-1）：技能读取采用"动作优先"——initialize 就给技能树路径，
  先直读 SKILL.md，被拒/失败才回落 vod_retrieve_skill，绝不反复请求；远程面按
  既有纪律不给服务器本机路径。
"""

import pytest

from vod_mcp import net, runtime_state, skills_registry
from vodkit_cli import auth_cmd


class _A:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ── S124 auth init / status ──────────────────────────────

def test_s124_status_without_key_reports_anonymous(capsys):
    auth_cmd.cmd_auth(_A(auth_action="status"))
    out = capsys.readouterr().out
    assert "未配置" in out and "匿名令牌" in out


def test_s124_init_is_dry_run_by_default(capsys, monkeypatch):
    monkeypatch.setattr(net, "probe_key", lambda k: {"ok": True, "fingerprint": "fp123"})
    key = "abcd1234efgh"
    auth_cmd.cmd_auth(_A(auth_action="init", key=key, apply=False))
    out = capsys.readouterr().out
    assert "未写盘" in out
    assert net._fingerprint(key) in out, "回显必须是本地算的指纹（单一来源）"
    assert key not in out, "明文 key 不许出现在输出里"
    assert not runtime_state._runtime_cfg().get("java_key"), "dry-run 不许写盘"


def test_s124_init_apply_writes_and_reads_back(capsys, monkeypatch):
    monkeypatch.setattr(net, "probe_key", lambda k: {"ok": True, "fingerprint": "fp123"})
    auth_cmd.cmd_auth(_A(auth_action="init", key="abcd1234efgh", apply=True))
    out = capsys.readouterr().out
    assert "已写入" in out
    assert runtime_state._runtime_cfg()["java_key"] == "abcd1234efgh"
    assert runtime_state._runtime_cfg()["token_tier"] == "key"
    assert "abcd1234efgh" not in out


def test_s124_init_refuses_rejected_key(capsys, monkeypatch):
    monkeypatch.setattr(net, "probe_key",
                        lambda k: {"ok": False, "reason": "rejected", "fingerprint": "fp9"})
    with pytest.raises(SystemExit) as e:
        auth_cmd.cmd_auth(_A(auth_action="init", key="abcd1234efgh", apply=True))
    assert e.value.code == 2
    assert "判该 key 无效" in capsys.readouterr().err
    assert not runtime_state._runtime_cfg().get("java_key"), "无效 key 绝不许落盘"


def test_s124_init_offline_warns_but_allows(capsys, monkeypatch):
    monkeypatch.setattr(net, "probe_key",
                        lambda k: {"ok": None, "reason": "unreachable", "fingerprint": "fp1"})
    auth_cmd.cmd_auth(_A(auth_action="init", key="abcd1234efgh", apply=True))
    err = capsys.readouterr().err
    assert "无法验证" in err
    assert runtime_state._runtime_cfg()["java_key"] == "abcd1234efgh"


def test_s124_init_rejects_suspicious_key(capsys):
    with pytest.raises(SystemExit):
        auth_cmd.cmd_auth(_A(auth_action="init", key="short", apply=True))
    assert "形态可疑" in capsys.readouterr().err


# ── S125 技能读取教法 ────────────────────────────────────

def test_s125_stdio_catalog_exposes_skill_root_and_paths():
    out = skills_registry.list_skills({})
    assert out["skillRoot"] == str(skills_registry.SKILLS_ROOT)
    assert "动作优先" in out["readHint"]
    assert all("path" in s for s in out["skills"]), "stdio 面每个技能都要给绝对路径"


def test_s125_remote_face_withholds_paths():
    tok = net._SERVER_FACE.set(True)
    try:
        out = skills_registry.list_skills({})
    finally:
        net._SERVER_FACE.reset(tok)
    assert "skillRoot" not in out and "readHint" not in out
    assert all("path" not in s for s in out["skills"])


def test_s125_initialize_instructions_teach_action_first():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    text = (root / "vod_mcp" / "server.py").read_text(encoding="utf-8")
    assert "技能树：" in text and "动作优先" in text and "绝不反复请求" in text
    # 远程面仍按既有纪律：不发布本机路径
    remote = (root / "vod_mcp" / "remote_app.py").read_text(encoding="utf-8")
    assert "不提供服务器本机路径" in remote


def test_s125_catalog_lists_reference_files_if_any():
    out = skills_registry.list_skills({})
    for s in out["skills"]:
        if "references" in s:
            assert s["references"], "references 字段存在就必须非空"
            assert all(isinstance(x, str) for x in s["references"])