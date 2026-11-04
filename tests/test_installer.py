# 安装器矩阵测试：fake-home + 桩 hermes + 隔离 git 仓（origin=本地 bare）。
# 铁律：不触真实 /root/vod-devkit 的 runtime.json / install-manifest.json /
# 真实 ~/.hermes、~/.config/opencode、~/.codex——一切副作用圈在 tmp_path。
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC_REPO = Path(__file__).resolve().parent.parent
GIT_ID = ["-c", "user.name=tester", "-c", "user.email=t@t.local"]


def _git(cwd, *args):
    return subprocess.run(["git", *GIT_ID, *args], cwd=cwd,
                          capture_output=True, text=True)


@pytest.fixture
def env(tmp_path):
    """隔离环境：fake home + 桩 hermes + 仓库克隆（origin=本地 bare，可离线演进）。"""
    home = tmp_path / "home"
    home.mkdir()
    stub = tmp_path / "bin"
    stub.mkdir()
    calls = tmp_path / "hermes-calls.log"
    stub_hermes = stub / "hermes"
    stub_hermes.write_text(
        "#!/bin/sh\necho \"$@\" >> " + shq(calls) + "\nexit 0\n")
    stub_hermes.chmod(0o755)

    bare = tmp_path / "origin.git"
    _git(SRC_REPO, "clone", "--bare", "--quiet", str(SRC_REPO), str(bare))
    # bare 的 HEAD 指向克隆时的分支；排除 hooks 干扰
    repo = tmp_path / "repo"
    _git(bare, "clone", "--quiet", str(bare), str(repo))
    # 叠加工作区未提交改动：门禁要测的是"当前要推的内容"，不是上一个提交
    shutil.copytree(SRC_REPO, repo, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                  ".e2e-nightly.log",
                                                  ".smoke", "vod_mcp/runtime.json"))

    e = os.environ.copy()
    e["HOME"] = str(home)
    e["PATH"] = str(stub) + os.pathsep + e["PATH"]
    e.pop("VOD_JAVA_API_KEY", None)
    return {"home": home, "repo": repo, "bare": bare, "env": e,
            "hermes_calls": calls, "stub": stub}


def shq(p):
    return "'" + str(p).replace("'", "'\\''") + "'"


def cli(env, *args):
    return subprocess.run(
        [sys.executable, str(env["repo"] / "bin" / "vod-devkit"), *args],
        env=env["env"], capture_output=True, text=True, timeout=120)


def commit_on_origin(env, marker, touch=None):
    """在 bare 上制造领先提交（第三个临时克隆推送，绝不碰真实仓）。"""
    pusher = env["bare"].parent / "pusher"
    _git(env["bare"], "clone", "--quiet", str(env["bare"]), str(pusher))
    (pusher / marker).write_text("x")
    if touch:
        t = pusher / touch
        t.write_text("upstream change\n")
    _git(pusher, "add", "-A")
    _git(pusher, "commit", "-q", "-m", "test: " + marker)
    _git(pusher, "push", "-q", "origin", "HEAD:" + _head_branch(env))
    return _git(pusher, "rev-parse", "HEAD").stdout.strip()


def _head_branch(env):
    return _git(env["repo"], "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"


# ---- opencode：schema 形态 + 既有配置无损合并 ----

def test_install_opencode_schema_and_merge(env):
    oc = env["home"] / ".config" / "opencode" / "opencode.json"
    oc.parent.mkdir(parents=True)
    oc.write_text(json.dumps({"provider": "keep-me", "theme": "dark"}))
    r = cli(env, "install", "--target", "opencode", "--preset", "collect")
    assert r.returncode == 0, r.stderr
    cfg = json.loads(oc.read_text())
    # 既有内容无损（读改写只动 mcp.vod-devkit 键）
    assert cfg["provider"] == "keep-me" and cfg["theme"] == "dark"
    entry = cfg["mcp"]["vod-devkit"]
    assert entry["command"][0] == sys.executable          # command=数组
    assert entry["command"][1].endswith("vod_mcp/server.py")
    assert entry["enabled"] is True                       # enabled 必填
    assert entry["environment"]["VOD_PACKS"] == "core,collect"  # 键名 environment


def test_install_opencode_idempotent(env):
    for _ in range(2):
        r = cli(env, "install", "--target", "opencode")
        assert r.returncode == 0, r.stderr
    cfg = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert list(cfg["mcp"]) == ["vod-devkit"]


# ---- codex：TOML 表形态 + 幂等（同表不重复） ----

def test_install_codex_toml_and_idempotent(env):
    for _ in range(2):
        r = cli(env, "install", "--target", "codex")
        assert r.returncode == 0, r.stderr
    text = (env["home"] / ".codex" / "config.toml").read_text()
    assert text.count("[mcp_servers.vod-devkit]") == 1
    assert text.count("[mcp_servers.vod-devkit.env]") == 1
    assert f'command = "{sys.executable}"' in text
    assert 'VOD_PACKS = "core,collect"' in text


# ---- hermes：官方 mcp add 通道 + 配置片段落盘 ----

def test_install_hermes_official_cli_and_conf(env):
    r = cli(env, "install", "--target", "hermes", "--preset", "collect")
    assert r.returncode == 0, r.stderr
    calls = env["hermes_calls"].read_text().strip().splitlines()
    assert calls and calls[0].startswith("mcp add vod-devkit --command")
    conf = json.loads((env["home"] / ".hermes/mcp/vod-devkit.json").read_text())
    assert conf["command"] == sys.executable
    assert conf["args"][0].endswith("vod_mcp/server.py")
    assert conf["env"]["VOD_PACKS"] == "core,collect"


# ---- 归因绑定：缺省=宿主名（「宿主即产品」口径） ----

def test_install_binds_product_to_host_by_default(env):
    cli(env, "install", "--target", "opencode")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert mf["product"] == "opencode" and rt["product"] == "opencode"
    cli(env, "install", "--target", "codex", "--product", "CodeArts")
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert rt["product"] == "CodeArts"                    # 显式传参优先


# ---- 平台地址：install 的 --java-api-base 双落（env+runtime.json 兜底） ----

def test_install_java_base_defaults_to_platform(env):
    # 不传地址不强制用户：缺省=平台真实地址（回环默认会装完即坏）
    cli(env, "install", "--target", "opencode")
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert rt["java_base"] == "https://vod-dev.topxtopx.com"
    oc = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert oc["mcp"]["vod-devkit"]["environment"]["VOD_JAVA_API_BASE"] \
        == "https://vod-dev.topxtopx.com"


def test_install_persists_java_base_to_runtime(env):
    cli(env, "install", "--target", "opencode",
        "--java-api-base", "https://vod-dev.topxtopx.com")
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert rt["java_base"] == "https://vod-dev.topxtopx.com"
    oc = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert oc["mcp"]["vod-devkit"]["environment"]["VOD_JAVA_API_BASE"] \
        == "https://vod-dev.topxtopx.com"


# ---- packs 过滤：collect 预置不含 workflow 技能面 ----

def test_install_collect_preset_skill_set(env):
    cli(env, "install", "--target", "hermes", "--preset", "collect")
    skills = env["home"] / ".hermes/skills/devops/vod-devkit"
    names = {p.name for p in skills.iterdir()}
    assert "vod-core" in names and "vod-feedback-collect" in names


# ---- update：ff 拉取 + build-info 重烧；本地脏改动挡 ff 必须失败 ----

def test_update_ff_pull_and_reburn(env):
    new_sha = commit_on_origin(env, "ahead.marker")
    r = cli(env, "update")
    assert r.returncode == 0, r.stderr
    bi = json.loads((env["repo"] / "build-info.json").read_text())
    assert bi["commitSha"] == new_sha
    assert (env["repo"] / "ahead.marker").exists()


def test_update_refuses_when_tracked_conflict(env):
    # untracked 文件不挡 ff（git 语义，非 bug）；真挡点是 tracked 冲突：
    # 本地与上游同时改同一 tracked 文件 → ff-only 拉取失败退出 1
    commit_on_origin(env, "ahead2.marker", touch="README.md")
    (env["repo"] / "README.md").write_text("local change\n")
    r = cli(env, "update")
    assert r.returncode == 1
    assert "更新失败" in (r.stdout + r.stderr)


# ---- doctor / uninstall ----

def test_doctor_flags_missing_mcp_config(env):
    cli(env, "install", "--target", "opencode")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    Path(mf["mcpConfig"]).unlink()
    r = cli(env, "doctor")
    assert r.returncode == 1 and "MCP 配置文件缺失" in r.stdout


def test_uninstall_removes_artifacts(env):
    cli(env, "install", "--target", "opencode")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    r = cli(env, "uninstall")
    assert r.returncode == 0, r.stderr
    assert not (env["repo"] / "install-manifest.json").exists()
    assert not Path(mf["mcpConfig"]).exists()
    assert not Path(mf["skillsDir"]).exists()
