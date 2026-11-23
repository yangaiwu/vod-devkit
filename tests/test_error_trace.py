"""ARCH-ERR-04 主链三点 + ARCH-ERR-05 日志出口：失败必须留痕（2026-11-19 走查 P1）。

台账 ERR-04 列了 26 处 `except: pass`，其中三个让「排障真源」本身失效：
1. `runtime_state._log:211` —— 日志出口自己写失败时 `pass`（唯一真源坏了没人知道）；
2. `runtime_state._runtime_cfg:39` —— runtime.json 解析失败读成空 dict（看起来像"没配 key"）；
3. `net.py` 领匿名令牌失败 —— 静默 `return None`（调用方只看到"端点不可用"）。

真实事故链（已被跑出来过）：runtime.json 被写坏 → 读成空 → 重领匿名令牌 → 设备锚点漂移
→ 服务端判"设备绑定校验失败"，**而插件侧没有一行日志指向"文件被写坏"**。
"""
import pytest

from vod_mcp import runtime_state as rt


@pytest.fixture(autouse=True)
def _reset_rt(monkeypatch, tmp_path):
    """隔离账本 + 内存镜像（模块级 _RT 是导入期快照，不重置会串味）。"""
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(rt, "_RT", {}, raising=False)
    yield


def test_log_failure_falls_back_to_stderr(capfd):
    """日志文件写不进去（父目录是文件而不是目录）⇒ 必须往 stderr 兜底一行，不许静默消失。"""
    bad = "/dev/null/not-a-dir/server.log"      # 必然 OSError（ENOTDIR）
    rt._log("hello", path=bad)
    err = capfd.readouterr().err
    assert "hello" in err, f"日志出口失败后必须 stderr 兜底，实际 stderr={err!r}"


def test_corrupt_runtime_json_leaves_a_log_line(monkeypatch, tmp_path):
    """runtime.json 半截 JSON ⇒ 读成空是既有行为，但必须留一行带文件名的痕迹。"""
    logs = []
    monkeypatch.setattr(rt, "_log", lambda line, **kw: logs.append(line))
    p = rt._runtime_path()                                    # 路径随 VOD_DEVKIT_HOME 走
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"java_key": "abc"', encoding="utf-8")      # 半截
    cfg = rt._runtime_cfg()
    assert cfg == {}, cfg                                     # 既有行为不变
    joined = " ".join(logs)
    assert "runtime.json" in joined, f"坏 runtime.json 必须留痕，日志里没有：{logs}"


def test_anon_token_failure_is_logged(monkeypatch):
    """领匿名令牌失败要进日志（调用方仍只看 -32012，语义不变）。"""
    from vod_mcp import net
    logs = []
    monkeypatch.setattr(rt, "_log", lambda line, **kw: logs.append(line), raising=False)

    def _raise(*a, **kw):
        raise net.ToolError("匿名令牌端点不可用（HTTP 503）", code=-32012)
    monkeypatch.setattr(net, "_http", _raise)
    assert net._fetch_anon_token() is None                    # 接口语义不变
    joined = " ".join(logs)
    assert "匿名令牌" in joined or "token" in joined.lower(), f"领令牌失败未留痕：{logs}"