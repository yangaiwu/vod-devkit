"""版本提醒（vod_check_update）的回归锁。

边界必须实测的三条：不自升级（只给命令）、网络失败不打脸（静默降级）、
preset 形态零外呼。另外顺带钉死 semver 比较——字符串比较会把 0.4.10 判成
比 0.4.9 旧（真实陷阱）。
"""
import json

from vod_mcp import tools, update_check as uc


def _rt():
    return json.loads(tools._runtime_path().read_text(encoding="utf-8"))


def test_version_tuple_orders_numerically():
    assert uc._version_tuple("0.4.10") > uc._version_tuple("0.4.9")
    assert uc._version_tuple("0.5.0") > uc._version_tuple("0.4.99")
    assert uc._version_tuple("0.4.4-rc1") == uc._version_tuple("0.4.4")


def test_newer_version_reports_upgrade_command(monkeypatch):
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: "99.0.0")
    out = tools.dispatch("vod_check_update", {})
    assert out["updateAvailable"] is True
    assert out["latestVersion"] == "99.0.0"
    assert "upgradeCommand" in out and "update" in out["upgradeCommand"]
    assert _rt()["update_check"]["latestVersion"] == "99.0.0", "检查结果必须进缓存"


def test_same_version_is_not_an_update(monkeypatch):
    from vod_mcp import __version__
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: __version__)
    out = tools.dispatch("vod_check_update", {})
    assert out["updateAvailable"] is False
    assert "已是最新" in out["note"]


def test_cache_suppresses_second_network_call(monkeypatch):
    calls = {"n": 0}

    def fake(timeout=3):
        calls["n"] += 1
        return "99.0.0"
    monkeypatch.setattr(uc, "_fetch_latest", fake)
    tools.dispatch("vod_check_update", {})
    tools.dispatch("vod_check_update", {})
    assert calls["n"] == 1, "24h 缓存失效=每次会话都打 registry"


def test_dismiss_cools_down_for_three_days(monkeypatch):
    calls = {"n": 0}

    def fake(timeout=3):
        calls["n"] += 1
        return "99.0.0"
    monkeypatch.setattr(uc, "_fetch_latest", fake)
    out = tools.dispatch("vod_check_update", {"dismiss": True})
    assert "不再提醒" in out["note"]
    assert _rt()["update_check"]["dismissedUntil"]
    out2 = tools.dispatch("vod_check_update", {})
    assert out2["updateAvailable"] is False and "跳过" in out2["note"]
    assert calls["n"] == 0, "冷却期内不得再打 registry"


def test_network_failure_degrades_silently(monkeypatch):
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: None)
    out = tools.dispatch("vod_check_update", {})
    assert out["checked"] is False and out["updateAvailable"] is False
    assert "不影响采集" in out["note"], "离线环境必须明说无妨，不能让 agent 去修网络"


def test_preset_distribution_never_calls_network(monkeypatch):
    def boom(timeout=3):
        raise AssertionError("preset 形态不应发外呼")
    monkeypatch.setattr(uc, "_fetch_latest", boom)
    monkeypatch.setattr(tools, "_distribution", lambda: "preset")
    out = tools.dispatch("vod_check_update", {})
    assert out["checked"] is False
    assert "preset" in out["note"]


def test_registry_failures_never_raise(monkeypatch):
    """_fetch_latest 自身吞掉一切异常（超时/DNS/坏 JSON）。"""
    class Bad:
        def __init__(self, *a, **k):
            raise OSError("dns dead")
    monkeypatch.setattr(uc.urllib.request, "urlopen", Bad)
    assert uc._fetch_latest() is None