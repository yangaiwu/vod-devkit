"""prune --payloads（D3，2026-11-16 负责人定案）。

锁六条定案约束：
1. 默认 dry-run，不加 --apply 不删任何东西；
2. 非交互环境无 --yes 必须拒绝（exit 2），交互式再问 y/N；
3. 只删清单内（带 payload.json 的安装器产物），无 payload.json 的手工目录不在此列；
4. 保留当前版本 + 安装行 payloadDir 指向的版本；
5. --keep N 额外保留最新 N 份；逐条打印 版本/大小/路径；
6. 只删载荷，机器级 state（令牌/账本）不动。
"""
import json
import sys

import pytest

from vod_mcp import __version__ as CUR
from vod_mcp import payload as P
from vodkit_cli import prune_cmd


def _mk_payload(home, ver, with_manifest=True):
    d = home / "payloads" / ver
    d.mkdir(parents=True, exist_ok=True)
    if with_manifest:
        (d / "payload.json").write_text(json.dumps({"version": ver}), encoding="utf-8")
    (d / "vod_mcp").mkdir(exist_ok=True)
    (d / "vod_mcp" / "server.py").write_text("# stub\n", encoding="utf-8")
    return d


@pytest.fixture()
def env(tmp_path, monkeypatch):
    home = tmp_path / "vk"
    home.mkdir()
    monkeypatch.setenv("VOD_PAYLOAD_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path))
    # manifest：一个宿主在用 0.5.12（= 旧版本，但仍是"在用"）
    mf = tmp_path / "install-manifest.json"
    mf.write_text(json.dumps({"installs": [
        {"target": "hermes", "payloadDir": str(home / "payloads" / "0.5.12")}]}),
        encoding="utf-8")
    monkeypatch.setattr(prune_cmd, "_rows", lambda: [
        {"target": "hermes", "payloadDir": str(home / "payloads" / "0.5.12")}])
    _mk_payload(home, "0.5.9")
    _mk_payload(home, "0.5.10")
    _mk_payload(home, "0.5.12")           # 安装行在用 → 必须保留
    _mk_payload(home, CUR)                # 当前版本 → 必须保留
    _mk_payload(home, "handmade", with_manifest=False)  # 无 payload.json → 不在此列
    return home


class _A:
    payloads = True
    keep = 0
    apply = False
    yes = False


def _args(**kw):
    a = _A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_dry_run_is_default_and_deletes_nothing(env, capsys):
    rc = prune_cmd.cmd_prune(_args())
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run" in out and "--apply" in out
    for v in ("0.5.9", "0.5.10", "0.5.12", CUR, "handmade"):
        assert (env / "payloads" / v).is_dir(), f"{v} 在 dry-run 下不得被删"


def test_non_interactive_apply_requires_yes(env, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    rc = prune_cmd.cmd_prune(_args(apply=True))
    assert rc == 2, "非 tty 且无 --yes 必须拒绝执行"
    assert "--yes" in capsys.readouterr().err
    assert (env / "payloads" / "0.5.9").is_dir()


def test_apply_deletes_only_old_and_keeps_current_and_in_use(env, capsys):
    rc = prune_cmd.cmd_prune(_args(apply=True, yes=True))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert not (env / "payloads" / "0.5.9").exists()
    assert not (env / "payloads" / "0.5.10").exists()
    assert (env / "payloads" / "0.5.12").is_dir(), "安装行在用的版本必须保留"
    assert (env / "payloads" / CUR).is_dir(), "当前版本必须保留"
    assert (env / "payloads" / "handmade").is_dir(), "无 payload.json 的手工目录不在此列"
    assert "已删除 2 份" in out, out


def test_keep_n_protects_the_newest_old_versions(env, capsys):
    rc = prune_cmd.cmd_prune(_args(apply=True, yes=True, keep=1))
    out = capsys.readouterr().out
    assert rc == 0, out
    assert not (env / "payloads" / "0.5.9").exists()
    assert (env / "payloads" / "0.5.10").is_dir(), "--keep 1 必须留下最新的那份旧载荷"


def test_nothing_to_do_when_only_live_versions(env, capsys):
    import shutil
    for v in ("0.5.9", "0.5.10"):
        shutil.rmtree(env / "payloads" / v)
    rc = prune_cmd.cmd_prune(_args())
    assert rc == 0
    assert "没有可清理" in capsys.readouterr().out


def test_state_is_untouched(env, capsys):
    state = env / "state"
    state.mkdir()
    (state / "runtime.json").write_text('{"install_nonce":"x"}', encoding="utf-8")
    prune_cmd.cmd_prune(_args(apply=True, yes=True))
    assert (state / "runtime.json").exists(), "prune 只删载荷，绝不碰机器级 state"


def test_candidates_never_include_used_or_current(env):
    cands = P.prune_candidates(_rows_fixture(env))
    names = {v for _p, v, _s in cands}
    assert names == {"0.5.9", "0.5.10"}, names


def _rows_fixture(env):
    return [{"target": "hermes", "payloadDir": str(env / "payloads" / "0.5.12")}]