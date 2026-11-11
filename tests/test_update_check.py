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

def test_skip_version_suppresses_only_that_version(monkeypatch):
    """skip-version（devkit update-skip 裁剪）：只压指定的那个版本，下个版本照常提醒。"""
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: "99.0.0")
    out = tools.dispatch("vod_check_update", {"skip": True})
    assert out["updateAvailable"] is False and "只压这一个版本" in out["note"]
    assert _rt()["update_check"]["skipVersion"] == "99.0.0"

    out2 = tools.dispatch("vod_check_update", {})
    assert out2["updateAvailable"] is False and out2.get("skippedVersion") == "99.0.0"

    # 更新的版本出现 → 照常提醒（不提供永久静音）
    # 先把 24h 缓存打到过期，模拟"过一阵子再检查"
    st = dict(tools._runtime_cfg().get("update_check") or {})
    st["checkedAt"] = "2000-01-01T00:00:00"
    tools._save_runtime({"update_check": st})
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: "99.1.0")
    out3 = tools.dispatch("vod_check_update", {})
    assert out3["updateAvailable"] is True and out3["latestVersion"] == "99.1.0"
    assert out3.get("skippedVersion") is None


def test_clear_skip_restores_nagging(monkeypatch):
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: "99.0.0")
    tools.dispatch("vod_check_update", {"skip": True})
    out = tools.dispatch("vod_check_update", {"clearSkip": True})
    assert "已清除版本跳过" in out["note"]
    assert "skipVersion" not in (_rt()["update_check"] or {})
    out2 = tools.dispatch("vod_check_update", {})
    assert out2["updateAvailable"] is True


def test_skip_when_registry_unreachable_is_honest(monkeypatch):
    # 隔离：清掉缓存里的 latestVersion（否则 skip 会直接拿缓存值，测不到不可达路径）
    tools._save_runtime({"update_check": {k: v for k, v in
                                          (tools._runtime_cfg().get("update_check") or {}).items()
                                          if k != "latestVersion"}})
    monkeypatch.setattr(uc, "_fetch_latest", lambda timeout=3: None)
    out = tools.dispatch("vod_check_update", {"skip": True})
    assert out["checked"] is False and "无法记录跳过版本" in out["note"]
    assert "skipVersion" not in (_rt().get("update_check") or {})
