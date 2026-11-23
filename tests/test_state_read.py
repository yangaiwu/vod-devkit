"""身份类值的读取口径（S140，D-state-read-1）。

背景：`net.JAVA_KEY` / `net.JAVA_BASE` 曾是 import 期常量——长驻的 MCP server 会在
启动那一刻把 env + runtime.json 的值冻结进模块全局。于是 `auth init --apply` 换了 key、
安装器改了 apiBase、自动领取了匿名令牌，**运行中的进程仍用旧值**（表现：用户"明明配了"
却 401，或提交打到旧环境）。

现在的契约：
1. 调用期现读：env（平台注入）> runtime.json > 默认；
2. 显式 set 过的模块属性优先（保留 ``monkeypatch.setattr(net, "JAVA_KEY", …)`` 的 patch 面）；
3. 本进程刚写的值通过 ``_RT`` 镜像回落可见（文件优先，镜像只兜文件缺失）。
"""
import json

from vod_mcp import net, runtime_state as rt


def _write_runtime(tmp_path, **kv):
    p = tmp_path / "runtime.json"
    p.write_text(json.dumps(kv), encoding="utf-8")


def test_s140_key_change_in_runtime_is_visible_without_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    _write_runtime(tmp_path, java_key="first-key")
    assert net.JAVA_KEY == "first-key"
    # 模拟 `auth init --apply`：外部进程改了文件，进程不重启
    _write_runtime(tmp_path, java_key="second-key")
    assert net.JAVA_KEY == "second-key", "换了 key 必须立刻生效（此前会一直用启动时的旧值)"


def test_s140_base_change_is_visible_without_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("VOD_JAVA_API_BASE", raising=False)
    monkeypatch.setattr(rt, "_RT", {})
    _write_runtime(tmp_path, java_base="http://engine-a:1")
    assert net.JAVA_BASE == "http://engine-a:1"
    _write_runtime(tmp_path, java_base="http://engine-b:2")
    assert net.JAVA_BASE == "http://engine-b:2"


def test_s140_env_beats_runtime(tmp_path, monkeypatch):
    _write_runtime(tmp_path, java_key="from-runtime")
    monkeypatch.setenv("VOD_JAVA_API_KEY", "from-env")
    assert net.JAVA_KEY == "from-env", "平台/CI 注入的 env 优先级最高"


def test_s140_explicit_patch_still_wins(tmp_path, monkeypatch):
    """保留模块属性 patch 面：显式 set 过的值优先于现读（既有测试全靠它）。"""
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    _write_runtime(tmp_path, java_key="from-runtime")
    monkeypatch.setattr(net, "JAVA_KEY", "patched-key")
    assert net.JAVA_KEY == "patched-key"
    assert net._eff_key() == "patched-key", "出口必须看到同一个值"


def test_s140_anonymous_tier_is_reflected(tmp_path, monkeypatch):
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setattr(net, "JAVA_KEY", "")
    _write_runtime(tmp_path, java_key="anon-tok", token_tier="anonymous")
    assert net._explicit_key() is False, "匿名令牌不是正式 key（换档后不重启也要判对）"
    _write_runtime(tmp_path, java_key="real-key", token_tier="key")
    assert net._explicit_key() is True


def test_s140_missing_runtime_falls_back_to_mirror(tmp_path, monkeypatch):
    """文件缺失/坏掉时用本进程镜像，不把出口打断。"""
    monkeypatch.delenv("VOD_JAVA_API_KEY", raising=False)
    monkeypatch.setattr(rt, "_RT", {"java_key": "mirrored"})
    assert net.JAVA_KEY == "mirrored"

def test_provenance_paths_are_live(tmp_path, monkeypatch):
    """ARCH-DEP-06 验收：换根后 build-info/manifest 路径必须现读，不重启、不重新 import。"""
    import json
    from pathlib import Path

    from vod_mcp import paths as paths_mod
    from vod_mcp import payload as payload_mod
    from vod_mcp import provenance

    root_a = tmp_path / "rootA"
    root_b = tmp_path / "rootB"
    for root, ver in ((root_a, "9.9.9"), (root_b, "8.8.8")):
        root.mkdir()
        (root / "build-info.json").write_text(json.dumps({"version": ver}), encoding="utf-8")

    monkeypatch.setattr(paths_mod, "ROOT", root_a)
    assert provenance.read_build_info()["version"] == "9.9.9"
    assert payload_mod._root() == Path(root_a)

    monkeypatch.setattr(paths_mod, "ROOT", root_b)          # 同一进程内换根
    assert provenance.read_build_info()["version"] == "8.8.8", "换根后仍读到旧根 = 路径被 import 期冻结"
    assert payload_mod._root() == Path(root_b)
