"""S187：行为回归套件对引擎 5xx 的容错（D-engine-502-1 配套）。

实测事故（2026-11-17）：真机 `e2e_behavior.py --host codex --suite` 跑到第一条用例的
引擎对账环节就 `urllib.error.HTTPError: HTTP Error 502` 抛栈退出——整轮 10 分钟遥测
全丢，日志里只剩 traceback，看起来像产品回归。同一调用手工连打 5 次全 200：网关抖动，
不是代码问题。

三条边界：
- 5xx 先重试（退避），抖动恢复即继续，不丢轮次；
- 持续 5xx → EngineUnavailable（脚本给「不可判（环境故障）」并 exit 2），不是裸 traceback；
- 4xx 不重试不吞：401/403 是判定依据（鉴权档/设备绑定），要原样抛给上层当数据用。
"""
import importlib.util
import io
import sys
import urllib.error
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_SPEC = importlib.util.spec_from_file_location("e2e_behavior", _SCRIPTS / "e2e_behavior.py")
assert _SPEC is not None and _SPEC.loader is not None, "scripts/e2e_behavior.py 缺失"
e2e = importlib.util.module_from_spec(_SPEC)
sys.modules["e2e_behavior"] = e2e
_SPEC.loader.exec_module(e2e)


class _Resp:
    """最小 urlopen 回执替身：read() 出 JSON 体，支持 with（不继承 BytesIO，免覆写语义）。"""

    def __init__(self, payload: bytes, status: int = 200):
        self._buf = io.BytesIO(payload)
        self.status = status

    def read(self, *a):
        return self._buf.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def _row(**kw) -> bytes:
    import json as _json
    return _json.dumps({"code": 200, "data": {"voices": [kw]}}).encode()


def test_s187_retries_transient_5xx_then_returns_rows(monkeypatch):
    calls = []
    payload = _row(id="VDPL1", title="原话", at="2999-01-01 00:00:00")

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", None, io.BytesIO(b""))
        return _Resp(payload)

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(e2e.time, "sleep", lambda *_: None)
    rows = e2e.engine_rows_since("2000-01-01 00:00:00")
    assert len(rows) == 1 and rows[0]["id"] == "VDPL1"
    assert len(calls) == 3, "5xx 应重试而不是立刻放弃"


def test_s187_persistent_5xx_raises_engine_unavailable(monkeypatch):
    def fake_urlopen(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", None, io.BytesIO(b""))

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(e2e.time, "sleep", lambda *_: None)
    try:
        e2e.engine_rows_since("2000-01-01 00:00:00")
    except e2e.EngineUnavailable as e:
        assert "502" in str(e), e
    else:
        raise AssertionError("持续 5xx 必须抛 EngineUnavailable（不能裸 traceback 丢整轮）")


def test_s187_4xx_is_judgement_data_not_retried(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, io.BytesIO(b""))

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("k", "https://e", "dev"))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(e2e.time, "sleep", lambda *_: None)
    try:
        e2e.engine_rows_since("2000-01-01 00:00:00")
    except urllib.error.HTTPError as e:
        assert e.code == 401
    else:
        raise AssertionError("401 必须原样抛出（鉴权/设备判定依据）")
    assert len(calls) == 1, "4xx 不得重试（重试只会放大鉴权压力）"


def test_s187_no_key_returns_empty_without_calling_engine(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("无 key 不应发请求")

    monkeypatch.setattr(e2e, "_install_runtime", lambda: ("", "https://e", ""))
    monkeypatch.setattr(e2e.urllib.request, "urlopen", boom)
    assert e2e.engine_rows_since("2000-01-01 00:00:00") == []