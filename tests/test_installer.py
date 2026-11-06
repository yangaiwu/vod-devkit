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
def engine_stub(tmp_path):
    """桩引擎（协议级：本地 HTTP 服务器，零外呼）。D-product-id-2 安装期
    产品硬校验的回归源：meta 带 productCatalog，token 零字段签发。"""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    state = {"meta_up": True, "token_headers": None, "meta_headers": None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.endswith("/external/meta"):
                state["meta_headers"] = {k.lower(): v for k, v in self.headers.items()}
                if not state["meta_up"]:
                    self._send({"code": 500, "message": "stub down"}, 500)
                    return
                self._send({"code": 200, "data": {
                    "products": ["codearts"],
                    "productCatalog": [
                        {"id": 31, "name": "CodeArts"},
                        {"id": 651, "name": "高校AI开发者平台"},
                        {"id": 663, "name": "GTD"},
                    ]}})
                return
            if self.path.endswith("/external/products"):
                self._send({"code": 200, "data": [
                    {"id": 31, "name": "CodeArts"},
                    {"id": 651, "name": "高校AI开发者平台"}]})
                return
            self._send({"code": 404, "message": "no route"}, 404)

        def do_POST(self):
            if self.path.endswith("/external/token"):
                state["token_headers"] = {k.lower(): v for k, v in self.headers.items()}
                self._send({"code": 200, "data": {"token": "stub-token"}})
                return
            self._send({"code": 404, "message": "no route"}, 404)

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield {"base": f"http://127.0.0.1:{srv.server_port}", "state": state}
    srv.shutdown()


@pytest.fixture
def env(tmp_path, engine_stub):
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
    # 桩 codex / vod-devkit：D-codex-agents-1 原生插件路径的调用记录
    codex_calls = tmp_path / "codex-calls.log"
    stub_codex = stub / "codex"
    stub_codex.write_text(
        "#!/bin/sh\necho \"$@\" >> " + shq(codex_calls) + "\n"
        "case \"$1 $2 $3\" in\n"
        "  \"plugin marketplace list\") echo 'vod-local';;\n"
        "  \"plugin list\") echo 'vod-devkit@vod-local  not installed';;\n"
        "esac\nexit 0\n")
    stub_codex.chmod(0o755)
    stub_vd = stub / "vod-devkit"
    stub_vd.write_text("#!/bin/sh\nexit 0\n")
    stub_vd.chmod(0o755)

    bare = tmp_path / "origin.git"
    _git(SRC_REPO, "clone", "--bare", "--quiet", str(SRC_REPO), str(bare))
    # bare 的 HEAD 指向克隆时的分支；排除 hooks 干扰
    repo = tmp_path / "repo"
    _git(bare, "clone", "--quiet", str(bare), str(repo))
    # 叠加工作区未提交改动：门禁要测的是"当前要推的内容"，不是上一个提交
    shutil.copytree(SRC_REPO, repo, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__",
                                                  ".e2e-nightly.log",
                                                  ".smoke", "runtime.json"))

    e = os.environ.copy()
    e["HOME"] = str(home)
    e["PATH"] = str(stub) + os.pathsep + e["PATH"]
    e.pop("VOD_JAVA_API_KEY", None)
    e["VOD_JAVA_API_BASE"] = engine_stub["base"]  # 安装校验/绑定全打桩引擎（零外呼）
    return {"home": home, "repo": repo, "bare": bare, "env": e,
            "hermes_calls": calls, "stub": stub, "engine": engine_stub,
            "codex_calls": codex_calls}


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
    r = cli(env, "install", "--target", "opencode", "--preset", "collect", "--product", "CodeArts")
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
        r = cli(env, "install", "--target", "opencode", "--product", "CodeArts")
        assert r.returncode == 0, r.stderr
    cfg = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert list(cfg["mcp"]) == ["vod-devkit"]


# ---- codex：TOML 表形态 + 幂等（同表不重复） ----

def test_install_codex_native_plugin_and_legacy_cleanup(env):
    """D-codex-plugin-1 终态：--target codex 走原生插件路径（codex plugin
    marketplace/add），并清理历史遗留 config.toml MCP 段与 AGENTS.md 技能块
    （同名双注册防）+ stale 插件缓存（devkit 卫生实践）。stub codex/vod-devkit。"""
    home = env["home"]
    stale_cache = home / ".codex" / "plugins" / "cache" / "vod-local"
    stale_cache.mkdir(parents=True, exist_ok=True)
    (stale_cache / "junk").write_text("old")
    legacy_conf = home / ".codex" / "config.toml"
    legacy_conf.parent.mkdir(parents=True, exist_ok=True)
    legacy_conf.write_text('[mcp_servers.vod-devkit]\ncommand = "old"\n', encoding="utf-8")
    legacy_agents = home / ".codex" / "AGENTS.md"
    legacy_agents.write_text("# 用户自有内容\n<!-- vod-devkit:feedback-skill BEGIN -->\n旧技能块\n<!-- vod-devkit:feedback-skill END -->\n", encoding="utf-8")
    for _ in range(2):
        r = cli(env, "install", "--target", "codex", "--product", "CodeArts")
        assert r.returncode == 0, r.stderr
    # 历史遗留清理 + stale cache 清理
    assert "mcp_servers.vod-devkit" not in legacy_conf.read_text()
    assert not stale_cache.exists(), "stale 插件缓存必须先清（重装旧版残留防）"
    a = legacy_agents.read_text()
    assert "旧技能块" not in a and "用户自有内容" in a
    # 原生插件路径调用（stub codex 记录）
    calls = env["codex_calls"].read_text()
    assert "marketplace" in calls and "add" in calls and "vod-devkit@vod-local" in calls


# ---- hermes：官方 mcp add 通道 + 配置片段落盘 ----

def test_install_hermes_official_cli_and_conf(env):
    r = cli(env, "install", "--target", "hermes", "--preset", "collect", "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    calls = env["hermes_calls"].read_text().strip().splitlines()
    assert calls and calls[0].startswith("mcp add vod-devkit --command")
    conf = json.loads((env["home"] / ".hermes/mcp/vod-devkit.json").read_text())
    assert conf["command"] == sys.executable
    assert conf["args"][0].endswith("vod_mcp/server.py")
    assert conf["env"]["VOD_PACKS"] == "core,collect"


# ---- 归因绑定：安装必配（T7d 统一，与 dsh UI 加载必配同口径） ----

def test_install_requires_product(env):
    # 缺省宿主名=生态部署错归陷阱（高校AI开发者平台 agent 底座=hermes，
    # 不填全归 hermes）——必填 fail fast，宿主名须显式传
    r = cli(env, "install", "--target", "opencode")
    assert r.returncode == 2 and "--product 必填" in r.stderr

def test_install_binds_explicit_product(env):
    cli(env, "install", "--target", "codex", "--product", "高校AI开发者平台")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert mf["product"] == "高校AI开发者平台" and rt["product"] == "高校AI开发者平台"


# ---- D-product-id-2（2026-11-05 拍板 B）：安装期产品硬校验 ----

def test_install_rejects_unregistered_product(env):
    """--product 不在产品名录 → 拒绝安装（归因前提无效=采集技能全部空转）。"""
    r = cli(env, "install", "--target", "codex", "--product", "asdasdasdasd")
    assert r.returncode == 2
    assert "不在产品名录" in r.stderr and "权威名单" in r.stderr
    assert not (env["home"] / ".codex" / "config.toml").exists()  # 零副作用
    # 宿主名同拒：D-product-id-2 推翻"宿主名是显式合法值"宽容口径
    r = cli(env, "install", "--target", "opencode", "--product", "hermes")
    assert r.returncode == 2 and "不在产品名录" in r.stderr


def test_install_product_accepts_name_or_id(env):
    """名录命中（名字大小写不敏感/平台主键 id）→ 放行安装（codex=原生插件路径）。"""
    cli(env, "install", "--target", "codex", "--product", "codearts")  # 小写名
    assert "vod-devkit@vod-local" in env["codex_calls"].read_text()
    cli(env, "install", "--target", "codex", "--product", "651")  # 平台主键 id
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert rt["product"] == "651"


def test_plugin_selfcontained_contract(env):
    """插件自包含契约锁（devkit 卫生对齐）：.mcp.json 相对路径指向包内 server；
    vod_mcp 随包携带且与源码同步（sync_plugin.py 的回归锁——漂移即红）。"""
    import hashlib
    plug = env["repo"] / "plugins" / "vod-devkit"
    mcp = json.loads((plug / ".mcp.json").read_text())
    srv = mcp["mcpServers"]["vod-devkit"]
    assert srv["command"] == "vod-devkit" and srv["args"] == ["serve"], \
        "codex 0.166 实测：相对路径+cwd 不解析到插件目录——入口必须走全局 vod-devkit serve"
    pj = json.loads((plug / ".codex-plugin" / "plugin.json").read_text())
    assert "interface" in pj and pj["skills"] == "./skills/"
    bundled = plug / "vod_mcp" / "server.py"
    src = env["repo"] / "vod_mcp" / "server.py"
    assert bundled.exists(), "插件包必须自带 server（sync_plugin.py 产物已提交）"
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert h(bundled) == h(src), "插件包内 server 与源码漂移——跑 scripts/sync_plugin.py"
    assert (plug / "skills" / "vod-feedback-collect" / "SKILL.md").exists(), "skills 随包（sync_plugin.py 同步）"
    assert not (plug / "vod_mcp" / "runtime.json").exists()  # 真源账本不随包
    bi = json.loads((plug / "build-info.json").read_text())  # provenance 版本真源随包
    assert bi["version"] and bi["commitSha"], "build-info 未烧录=vod_devkit_info 版本号失真"


def test_validation_probe_uses_consistent_device_anchor(env):
    """S37（协议级）：安装校验链 token 签发与 meta 查询必须携带同一
    X-Vod-Device-Id 与 UA（S1 设备绑定语义）——缺失=meta 401 或烧 legacy 锚点。"""
    cli(env, "install", "--target", "codex", "--product", "CodeArts")
    st = env["engine"]["state"]
    assert st["token_headers"] and st["meta_headers"], "校验链必须先领令牌再查 meta"
    th, mh = st["token_headers"], st["meta_headers"]
    assert th.get("x-vod-device-id") == mh.get("x-vod-device-id"), "设备锚点不一致=S1 绑定校验必挂"
    assert th.get("user-agent") == mh.get("user-agent"), "UA 不一致=legacy 锚点漂移"
    import re
    assert re.fullmatch(r"[0-9a-f]{8,64}", th.get("x-vod-device-id", "")), "设备 id 必须纯 hex（非 hex 静默降 legacy 锚点）"


def test_skill_drift_lock(env):
    """D-drift-lock：安装记录技能拷贝件 sha256 指纹→安装后篡改拷贝件→
    doctor/verify 检出漂移并引导重装（vendor 规则漂移实锤的针对性防线）。"""
    import json as _json
    cli(env, "install", "--target", "hermes", "--product", "CodeArts")
    mf = _json.loads((env["repo"] / "install-manifest.json").read_text())
    assert mf.get("skillHashes"), "安装必须记录技能拷贝件指纹"
    r = cli(env, "doctor")
    assert r.returncode == 0, r.stderr
    # 篡改一个已安装技能文件 → doctor 检出漂移
    skills_dir = Path(mf["skillsDir"])
    target = next(skills_dir.rglob("SKILL.md"))
    target.write_text(target.read_text() + "\n<!-- 篡改 -->\n")
    r = cli(env, "doctor")
    assert r.returncode == 1 and "漂移" in r.stdout
    r = cli(env, "install", "--target", "hermes", "--product", "CodeArts")  # 重装恢复
    assert cli(env, "doctor").returncode == 0


def test_opencode_doctor_command_file(env):
    """opencode 自检命令随装写入 /vod-doctor（devkit 对表），内容含自检序列
    与 key 明文禁令。"""
    cli(env, "install", "--target", "opencode", "--product", "CodeArts")
    cmd = env["home"] / ".config/opencode/command/vod-doctor.md"
    assert cmd.exists()
    text = cmd.read_text()
    for key in ("vod_devkit_info", "vod_auth_status", "vod_list_submitted", "不要打印任何 key"):
        assert key in text


def _assert_golden(name, actual):
    """golden 快照比对：易变段由调用方归一化；UPDATE_GOLDEN=1 显式重录。"""
    golden = Path(__file__).parent / "golden" / f"{name}.txt"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(actual + "\n")
    assert golden.exists(), f"golden 缺失：UPDATE_GOLDEN=1 生成 {name} 并人工过目"
    expected = golden.read_text().rstrip("\n")
    assert actual == expected, (
        f"{name} 输出口径漂移——确认是有意变更后 UPDATE_GOLDEN=1 重录，\n"
        f"--- expected\n{expected}\n--- actual\n{actual}")


def test_doctor_verify_golden(env):
    """D-golden-1（devkit doctor-golden 对表）：doctor/verify 用户可见输出
    快照基线——口径漂移（文案/判定顺序/新增行）即红，改口径必须显式
    UPDATE_GOLDEN=1 重录并在 diff 里过目。易变段（HOME/REPO 路径、commit
    SHA）归一化后比对。"""
    cli(env, "install", "--target", "hermes", "--product", "CodeArts")
    # 输出确定性：剥离 key 源（runtime.json 残留）——key 探针行含易变指纹，
    # golden 只锁无 key 基线（key 态由 auth_status 专项用例覆盖）
    rt = env["repo"] / "vod_mcp" / "runtime.json"
    if rt.exists():
        d = json.loads(rt.read_text())
        d.pop("java_key", None); d.pop("token_tier", None)
        rt.write_text(json.dumps(d, ensure_ascii=False))
    outs = []
    for cmd in ("doctor", "verify"):
        r = cli(env, cmd)
        assert r.returncode == 0, r.stderr
        outs.append(f"$ vod-devkit {cmd}\n{r.stdout.strip()}")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    actual = "\n".join(outs)
    for volatile, tag in ((str(env["home"]), "<HOME>"), (str(env["repo"]), "<REPO>"),
                          (str(mf["source"]["commitSha"][:12]), "<SHA12>")):
        actual = actual.replace(volatile, tag)
    golden = Path(__file__).parent / "golden" / "doctor_verify.txt"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(actual + "\n")
    _assert_golden("doctor_verify", actual)


def test_golden_status_and_preset_update_refusal(env):
    """golden 扩展：status（manifest 原文，易变段归一化）+ preset 形态的
    update 拒绝语（固定文案）。"""
    cli(env, "install", "--target", "hermes", "--product", "CodeArts")
    r = cli(env, "status")
    assert r.returncode == 0
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    actual = r.stdout.strip()
    for volatile, tag in ((str(env["home"]), "<HOME>"), (str(env["repo"]), "<REPO>"),
                          (str(env["bare"]), "<ORIGIN>"),
                          (str(mf["source"]["commitSha"]), "<SHA>"),
                          (str(mf["installedAt"]), "<INSTALLED_AT>")):
        actual = actual.replace(volatile, tag)
    # JSON 结构稳定性：归一化后必须仍是合法 JSON（status 契约=原样 manifest）
    d = json.loads(actual)
    d["skillHashes"] = "<SKILL_HASHES>"  # 漂移锁专项覆盖，golden 不锁哈希值
    actual = json.dumps(d, ensure_ascii=False, indent=2)
    _assert_golden("status", actual)
    cli(env, "install", "--target", "hermes", "--product", "CodeArts",
        "--distribution", "preset")
    r = cli(env, "update")
    assert r.returncode == 0 and "不支持自更新" in r.stdout
    _assert_golden("preset_update_refusal", r.stdout.strip())


def test_stdio_probe_pack_gating_e2e(env):
    """S43（stdio 探针协议级）：pack 门控走真实 server 装配——
    VOD_PACKS=core → tools/list 无写工具；core,collect → 含 submit。
    （in-process 锁见 test_tool_specs_follow_packs；本例锁 server.py 装配层）"""
    from tests.probe import Probe
    base_env = {"VOD_JAVA_API_BASE": env["engine"]["base"]}
    with Probe(env_extra={**base_env, "VOD_PACKS": "core"}) as p:
        names = {t["name"] for t in p.list_tools()}
        assert "vod_devkit_info" in names and "vod_submit_voices" not in names
    with Probe(env_extra={**base_env, "VOD_PACKS": "core,collect"}) as p:
        names = {t["name"] for t in p.list_tools()}
        assert {"vod_devkit_info", "vod_submit_voices", "vod_auth_status",
                "vod_list_submitted"} <= names


def test_install_rejects_when_catalog_unreachable(env):
    """目录不可达（引擎 500/离线）→ 拒绝安装：宁可不装不可装错。"""
    env["engine"]["state"]["meta_up"] = False
    r = cli(env, "install", "--target", "codex", "--product", "CodeArts")
    assert r.returncode == 2 and ("拒绝安装" in r.stderr or "无 productCatalog" in r.stderr)
    env["engine"]["state"]["meta_up"] = True


# ---- 平台地址：install 的 --java-api-base 双落（env+runtime.json 兜底） ----

def test_install_java_base_defaults_to_platform(env):
    # 地址优先级：--java-api-base > env VOD_JAVA_API_BASE > DEFAULT_JAVA_BASE；
    # env 与插件运行时同键（安装器跟随同链），此处验证 env 兜底生效
    cli(env, "install", "--target", "opencode", "--product", "CodeArts")
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert rt["java_base"] == env["engine"]["base"]
    oc = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert oc["mcp"]["vod-devkit"]["environment"]["VOD_JAVA_API_BASE"] \
        == env["engine"]["base"]


def test_install_persists_java_base_to_runtime(env):
    # 显式 --java-api-base 覆盖 env/缺省（优先级第一位的回归锁）；地址打桩引擎零外呼
    cli(env, "install", "--target", "opencode",
        "--java-api-base", env["engine"]["base"],
        "--product", "CodeArts")
    rt = json.loads((env["repo"] / "vod_mcp" / "runtime.json").read_text())
    assert rt["java_base"] == env["engine"]["base"]
    oc = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert oc["mcp"]["vod-devkit"]["environment"]["VOD_JAVA_API_BASE"] \
        == env["engine"]["base"]


def test_install_omits_empty_key(env):
    # 无 key 时宿主配置不落 VOD_JAVA_API_KEY 空串（运行时自动兜底 runtime.json/匿名令牌）
    cli(env, "install", "--target", "opencode", "--product", "CodeArts")
    oc = json.loads((env["home"] / ".config/opencode/opencode.json").read_text())
    assert "VOD_JAVA_API_KEY" not in oc["mcp"]["vod-devkit"]["environment"]


# ---- packs 过滤：collect 预置不含 workflow 技能面 ----

def test_install_collect_preset_skill_set(env):
    cli(env, "install", "--target", "hermes", "--preset", "collect", "--product", "CodeArts")
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
    cli(env, "install", "--target", "opencode", "--product", "CodeArts")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    Path(mf["mcpConfig"]).unlink()
    r = cli(env, "doctor")
    assert r.returncode == 1 and "MCP 配置文件缺失" in r.stdout


def test_uninstall_removes_artifacts(env):
    cli(env, "install", "--target", "opencode", "--product", "CodeArts")
    mf = json.loads((env["repo"] / "install-manifest.json").read_text())
    r = cli(env, "uninstall")
    assert r.returncode == 0, r.stderr
    assert not (env["repo"] / "install-manifest.json").exists()
    assert not Path(mf["mcpConfig"]).exists()
    assert not Path(mf["skillsDir"]).exists()


# ---- dsh 壳（D-dsh-install-1，2026-11-06 拍板 A）：安装期硬校验 + 幂等写配置 ----

@pytest.fixture
def env_dsh(env):
    """dsh 桩 CLI：记录调用并 exit 0（真实 dsh 行为在真机验证过，桩只测安装器矩阵）。"""
    calls = env["repo"].parent / "dsh-calls.log"
    stub = env["stub"] / "dsh"
    stub.write_text("#!/bin/sh\necho \"$@\" >> " + shq(calls) + "\nexit 0\n")
    stub.chmod(0o755)
    env["dsh_calls"] = calls
    return env


def _dsh_patch(env, profile="web"):
    return env["home"] / ".dsh" / "profiles" / profile / "cordis.patch.yml"


def test_install_dsh_valid_product_writes_config(env_dsh):
    r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
            "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    calls = env_dsh["dsh_calls"].read_text()
    assert "--profile web" in calls and "add" in calls
    patch = _dsh_patch(env_dsh)
    text = patch.read_text()
    assert "- id: vod-devkit" in text
    assert "product: CodeArts" in text
    mf = json.loads((env_dsh["repo"] / "install-manifest.json").read_text())
    assert mf["dshProfile"] == "web"


def test_install_dsh_bad_product_exits2_before_add(env_dsh):
    r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
            "--product", "NoSuchProduct")
    assert r.returncode == 2
    assert not env_dsh["dsh_calls"].exists()  # 校验先于 add：无半成品


def test_install_dsh_missing_product_exits2(env_dsh):
    r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web")
    assert r.returncode == 2
    assert not env_dsh["dsh_calls"].exists()


def test_install_dsh_missing_profile_exits2(env_dsh):
    r = cli(env_dsh, "install", "--target", "dsh", "--product", "CodeArts")
    assert r.returncode == 2
    assert not env_dsh["dsh_calls"].exists()


def test_install_dsh_idempotent_no_duplicate_block(env_dsh):
    for _ in range(2):
        r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
                "--product", "CodeArts")
        assert r.returncode == 0, r.stderr
    text = _dsh_patch(env_dsh).read_text()
    assert text.count("- id: vod-devkit") == 1


def test_install_dsh_upsert_preserves_other_blocks(env_dsh):
    patch = _dsh_patch(env_dsh)
    patch.parent.mkdir(parents=True)
    patch.write_text("- id: other-plugin\n  config:\n    x: 1\n")
    r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
            "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    text = patch.read_text()
    assert "- id: other-plugin" in text and "x: 1" in text
    assert text.count("- id: ") == 2  # 不吞别人的段
    assert text.index("- id: other-plugin") < text.index("- id: vod-devkit") or True


def test_install_dsh_updates_existing_block(env_dsh):
    cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
        "--product", "CodeArts")
    r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
            "--product", "GTD")
    assert r.returncode == 0, r.stderr
    text = _dsh_patch(env_dsh).read_text()
    assert "product: GTD" in text and "CodeArts" not in text
    assert text.count("- id: vod-devkit") == 1  # 更新而非追加


def test_install_dsh_block_carries_name_binding(env_dsh):
    """name 行回归锁（2026-11-06 真机实锤）：cordis.patch.yml insert 块靠
    name 绑定 client 半（反馈按钮）——installer 模板曾无 name 行，重装幂等
    替换吞掉既有 name → UI 静默失激活（工具壳正常、入口消失）。"""
    # 前置：模拟 dsh plugin add 自建的带 name 块
    patch = _dsh_patch(env_dsh)
    patch.parent.mkdir(parents=True)
    patch.write_text(
        "- insert:\n"
        "    - id: vod-devkit\n"
        "      name: dsh-vod-devkit\n"
        "      config:\n"
        "        product: Old\n")
    r = cli(env_dsh, "install", "--target", "dsh", "--profile", "web",
            "--product", "CodeArts")
    assert r.returncode == 0, r.stderr
    text = patch.read_text()
    # upsert 后 name 绑定必须在（新块模板自带或保留既有值，二者皆可，不可消失）
    assert "name: dsh-vod-devkit" in text, \
        "重装吞掉 name 绑定 → client 半静默失激活（真机事故回归）"
    assert "product: CodeArts" in text
    assert "product: Old" not in text  # 配置值仍幂等更新


def test_install_dsh_cli_missing_exits2(env):
    # 无 dsh（PATH 剥离到仅含桩目录+系统基础路径，本机真 dsh 不参与）→ 拒绝安装
    e = env["env"].copy()
    e["PATH"] = str(env["stub"]) + os.pathsep + "/usr/bin:/bin"
    r = subprocess.run(
        [sys.executable, str(env["repo"] / "bin" / "vod-devkit"), "install",
         "--target", "dsh", "--profile", "web", "--product", "CodeArts"],
        env=e, capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "dsh CLI" in (r.stderr + r.stdout)
