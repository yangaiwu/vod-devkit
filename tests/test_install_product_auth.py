"""产品校验的引擎鉴权异常处置（0.5.12，真机实锤 P3）。

现场：引擎多实例时「签发令牌的实例」与「校验令牌的实例」不同步 →
POST /external/token 刚签出匿名令牌，紧随其后的 GET /external/meta 就 401
「API Key 无效或已失效」。旧实现把这归成"产品校验不可达"，排错会往网络上跑。

锁三件：
1. 401 一次 → 换设备锚点重领令牌重试，成功则放行（偶发的一半能自愈）；
2. 401 两次 → exit 2，文案必须说"鉴权异常/集群不同步"，不许说"不可达"；
3. 真网络异常（非 401）→ 仍是"不可达"文案，且同样重试过一次。
"""
import json
import urllib.error

import pytest

from vodkit_cli import remote


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """每个用例都隔离 HOME/state：否则会读到真机 <state> 里的匿名令牌，
    让"是否新签令牌"的断言失去意义（也避免打到真引擎）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VOD_DEVKIT_HOME", str(tmp_path / "state"))


class _Resp:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _handler(meta_behaviour, calls):
    """meta_behaviour: 可调用 list（第 n 次调用的行为）→ 返回 _Resp 或 raise。"""
    def fn(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        if "/external/token" in url:
            calls["mint"] += 1
            return _Resp({"data": {"token": f"tok{calls['mint']}"}})
        calls["meta"] += 1
        act = meta_behaviour[calls["meta"] - 1]
        if isinstance(act, Exception):
            raise act
        return act
    return fn


def test_401_once_then_retry_succeeds(monkeypatch):
    """偶发 401（签发/校验不同步）→ 重试一次即过，不该阻断安装。"""
    ok = _Resp({"data": {"productCatalog": [{"id": "1", "name": "CodeArts"}]}})
    calls = {"meta": 0, "mint": 0}
    beh = [urllib.error.HTTPError("u", 401, "Unauthorized", None, None), ok]
    monkeypatch.setattr("urllib.request.urlopen", _handler(beh, calls))
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert calls["meta"] == 2, "401 后必须重试"
    assert calls["mint"] == 2, "重试要换设备锚点重新领令牌（同锚点重领会被引擎当成同一设备）"


def test_401_twice_reports_auth_anomaly_not_network(monkeypatch, capsys):
    calls = {"meta": 0, "mint": 0}
    err = urllib.error.HTTPError("u", 401, "Unauthorized", None, None)
    monkeypatch.setattr("urllib.request.urlopen", _handler([err, err], calls))
    with pytest.raises(SystemExit) as e:
        remote._validate_product_or_exit("CodeArts", "https://engine")
    assert e.value.code == 2
    err_out = capsys.readouterr().err
    assert "鉴权异常" in err_out and "401" in err_out, err_out
    assert "不同步" in err_out, "文案要说清可能是集群令牌不同步，而不是网络"
    assert "不可达" not in err_out, "鉴权问题不许说成网络不可达（会误导排错方向）"


def test_network_error_retried_then_reported_as_unreachable(monkeypatch, capsys):
    calls = {"meta": 0, "mint": 0}
    boom = urllib.error.URLError("conn refused")
    monkeypatch.setattr("urllib.request.urlopen", _handler([boom, boom], calls))
    with pytest.raises(SystemExit) as e:
        remote._validate_product_or_exit("CodeArts", "https://engine")
    assert e.value.code == 2
    err_out = capsys.readouterr().err
    assert "不可达" in err_out, err_out
    assert calls["meta"] == 2, "网络抖动也应重试一次"


def test_empty_catalog_is_its_own_message(monkeypatch, capsys):
    """引擎在但目录空（老引擎/部署不完整）→ 第 3 种文案，别和鉴权/网络混。"""
    calls = {"meta": 0, "mint": 0}
    empty = _Resp({"data": {"productCatalog": []}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([empty, empty], calls))
    with pytest.raises(SystemExit) as e:
        remote._validate_product_or_exit("CodeArts", "https://engine")
    assert e.value.code == 2
    err_out = capsys.readouterr().err
    assert "productCatalog" in err_out and "T7i" in err_out, err_out


def test_reuses_state_anonymous_token_instead_of_minting(monkeypatch):
    """state 里已有匿名令牌 → 复用它（device=install_nonce），不再新签。

    真机实锤：安装器每次校验都新签一枚，密集重装把"同网络当日 100 次"打满 → 429，
    整批装机被挡。复用既省配额，又保证令牌与设备锚点配对（S1 设备绑定）。
    """
    from vod_mcp import runtime_state as rt
    rt._runtime_update({"java_key": "statetok", "token_tier": "anonymous"})
    dev = rt._install_nonce()
    seen = {}

    def handler(req, timeout=None):
        url = getattr(req, "full_url", "")
        if "/external/token" in url:
            seen["minted"] = True
            return _Resp({"data": {"token": "newly-minted"}})
        seen["headers"] = dict(getattr(req, "headers", {}) or {})
        return _Resp({"data": {"productCatalog": [{"id": "1", "name": "CodeArts"}]}})

    monkeypatch.setattr("urllib.request.urlopen", handler)
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert not seen.get("minted"), "state 已有匿名令牌时不得新签（会烧日配额）"
    hdrs = {k.lower(): v for k, v in seen["headers"].items()}
    assert hdrs.get("authorization") == "Bearer statetok", hdrs
    assert hdrs.get("x-vod-device-id") == dev, "复用时 device 必须是 state 的 install_nonce"


def test_429_reports_rate_limit_and_stops_retrying(monkeypatch, capsys):
    """限流（429）不是网络故障：文案要说清日配额，且不再重试（重试只会更糟）。"""
    calls = {"meta": 0, "mint": 0}
    err = urllib.error.HTTPError("u", 429, "Too Many Requests", None, None)  # type: ignore[arg-type]

    def handler(req, timeout=None):
        url = getattr(req, "full_url", "")
        if "/external/token" in url:
            calls["mint"] += 1
            raise err
        calls["meta"] += 1
        return _Resp({})

    monkeypatch.setattr("urllib.request.urlopen", handler)
    with pytest.raises(SystemExit) as e:
        remote._validate_product_or_exit("CodeArts", "https://engine")
    assert e.value.code == 2
    err_out = capsys.readouterr().err
    assert "429" in err_out and "限流" in err_out, err_out
    assert calls["mint"] == 1, f"429 后不得继续重试签发；实际尝试 {calls['mint']} 次"


# ── S149：产品名录缓存（把"每次校验都要一枚令牌"降到"7 天一枚"）──────

def _seed_cache(base, catalog, age_secs=0.0):
    import time
    p = remote._catalog_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"base": base, "at": time.time() - age_secs, "catalog": catalog}),
                 encoding="utf-8")


def test_s149_cache_hit_skips_engine(monkeypatch, capsys):
    _seed_cache("https://engine", [{"id": "1", "name": "CodeArts"}])
    called = []

    def handler(req, timeout=None):
        called.append(getattr(req, "full_url", ""))
        return _Resp({})

    monkeypatch.setattr("urllib.request.urlopen", handler)
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert not called, "缓存命中不得请求引擎（每请求一次就烧一枚匿名令牌）"
    assert "命中本地缓存" in capsys.readouterr().out


def test_s149_cache_expired_refetches_and_rewrites(monkeypatch):
    _seed_cache("https://engine", [{"id": "1", "name": "Stale"}], age_secs=8 * 86400)
    calls = {"meta": 0, "mint": 0}
    ok = _Resp({"data": {"productCatalog": [{"id": "1", "name": "CodeArts"}]}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([ok], calls))
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert calls["meta"] == 1, "TTL 过期必须重拉"
    fresh = json.loads(remote._catalog_cache_path().read_text(encoding="utf-8"))
    assert fresh["catalog"][0]["name"] == "CodeArts", "重拉后必须刷新缓存"


def test_s149_cache_keyed_by_engine_base(monkeypatch):
    _seed_cache("https://other-engine", [{"id": "1", "name": "CodeArts"}])
    calls = {"meta": 0, "mint": 0}
    ok = _Resp({"data": {"productCatalog": [{"id": "1", "name": "CodeArts"}]}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([ok], calls))
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert calls["meta"] == 1, "换了引擎地址，旧缓存必须作废"


def test_s149_refresh_flag_ignores_cache(monkeypatch):
    _seed_cache("https://engine", [{"id": "1", "name": "CodeArts"}])
    calls = {"meta": 0, "mint": 0}
    ok = _Resp({"data": {"productCatalog": [{"id": "1", "name": "CodeArts"}]}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([ok], calls))
    assert remote._validate_product_or_exit("CodeArts", "https://engine", refresh=True) is True
    assert calls["meta"] == 1, "--refresh-product-catalog 必须绕过缓存"


def test_s149_ttl_env_disables_cache(monkeypatch):
    _seed_cache("https://engine", [{"id": "1", "name": "CodeArts"}])
    monkeypatch.setenv("VOD_PRODUCT_CATALOG_TTL", "0")
    calls = {"meta": 0, "mint": 0}
    ok = _Resp({"data": {"productCatalog": [{"id": "1", "name": "CodeArts"}]}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([ok], calls))
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert calls["meta"] == 1, "TTL=0 等于禁用缓存"


def test_s149_skip_product_check_env(monkeypatch, capsys):
    """巡检路径：VOD_MATRIX=1 + VOD_SKIP_PRODUCT_CHECK=1 才直接放行，零外呼。"""
    monkeypatch.setenv("VOD_SKIP_PRODUCT_CHECK", "1")
    monkeypatch.setenv("VOD_MATRIX", "1")
    called = []
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: called.append(1) or _Resp({}))
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert not called
    assert "跳过产品校验" in capsys.readouterr().err


def test_s149_skip_env_alone_does_not_bypass_hard_gate(monkeypatch):
    """只抄 VOD_SKIP_PRODUCT_CHECK=1（不带 VOD_MATRIX）不得绕过产品硬校验 ——
    否则审计日志里那行 env 被单用，就等于装出一台产品归属未验证的机器。"""
    monkeypatch.setenv("VOD_SKIP_PRODUCT_CHECK", "1")
    calls = {"meta": 0, "mint": 0}
    empty = _Resp({"data": {"productCatalog": []}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([empty, empty], calls))
    with pytest.raises(SystemExit) as e:
        remote._validate_product_or_exit("CodeArts", "https://engine")
    assert e.value.code == 2, "单用 skip 环境变量必须仍然走校验并拒绝"
    assert calls["meta"] >= 1


def test_s149_bad_ttl_warns_and_falls_back(monkeypatch, capsys):
    """坏 TTL（如 7d）不许把安装打断：按默认 7 天并告警（真机实锤曾抛 ValueError）。"""
    monkeypatch.setenv("VOD_PRODUCT_CATALOG_TTL", "7d")
    _seed_cache("https://engine", [{"id": "1", "name": "CodeArts"}])
    called = []
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: called.append(1) or _Resp({}))
    assert remote._validate_product_or_exit("CodeArts", "https://engine") is True
    assert not called, "TTL 配错应按 7 天默认 → 缓存仍命中"
    assert "不是秒数" in capsys.readouterr().err


def test_s149_unknown_product_points_at_refresh_flag(monkeypatch, capsys):
    """名录里没有该产品时，文案必须给 --refresh-product-catalog 出路（7 天旧缓存会挡住新上线的产品）。"""
    calls = {"meta": 0, "mint": 0}
    ok = _Resp({"data": {"productCatalog": [{"id": "1", "name": "Other"}]}})
    monkeypatch.setattr("urllib.request.urlopen", _handler([ok], calls))
    with pytest.raises(SystemExit) as e:
        remote._validate_product_or_exit("CodeArts", "https://engine")
    assert e.value.code == 2
    err_out = capsys.readouterr().err
    assert "--refresh-product-catalog" in err_out, err_out