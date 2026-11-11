"""版本更新检查（devkit update-check/upgrade 的裁剪版：只提醒，不自升级）。

为什么只提醒：本插件有两种分发形态，preset 形态**禁止自更新**（插件版本随
agent 发版管理，D-key-guard-3②）。所以升级动作永远是 install/update，工具
只负责回答"我这台是不是旧了"，绝不下载、不解包、不改盘。

三个约束：
- 一次会话只打扰一次 + 拒绝后冷却 3 天（devkit 同款）；状态落 runtime.json。
- 网络失败静默降级（离线/内网环境必须可用），不阻塞任何采集链。
- preset 形态完全不发外呼。
"""
import datetime
import json
import urllib.request

REGISTRY = "https://registry.npmjs.org/vod-devkit/latest"
CACHE_TTL_HOURS = 24
DISMISS_DAYS = 3


def _now():
    return datetime.datetime.now()


def _fetch_latest(timeout=3) -> str | None:
    """查 npm registry 的 latest 版本；任何失败返回 None（永不抛出）。"""
    try:
        req = urllib.request.Request(REGISTRY, headers={"accept": "application/json",
                                                        "user-agent": "vod-devkit"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        v = data.get("version")
        return str(v) if v else None
    except Exception:
        return None


def _version_tuple(v: str) -> tuple:
    """宽松 semver：只比数字段，预发布后缀按 0 处理（0.4.4-rc1 视作 0.4.4）。"""
    core = str(v or "").split("-")[0].split("+")[0]
    out = []
    for part in core.split(".")[:3]:
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def check(params: dict | None = None) -> dict:
    from vod_mcp import __version__, tools
    params = params or {}
    dismiss = bool(params.get("dismiss"))
    cfg = tools._runtime_cfg()
    state = cfg.get("update_check") or {}
    now = _now()

    if tools._distribution() == "preset":
        return {"currentVersion": __version__, "latestVersion": None,
                "updateAvailable": False, "checked": False,
                "note": "本装机为产品分发形态（preset），版本随 agent 发版管理，"
                        "不做外呼检查。升级请联系产品提供方。"}

    dismissed_until = state.get("dismissedUntil")
    if dismiss:
        until = (now + datetime.timedelta(days=DISMISS_DAYS)).date().isoformat()
        tools._save_runtime({"update_check": {**state, "dismissedUntil": until}})
        return {"currentVersion": __version__, "latestVersion": state.get("latestVersion"),
                "updateAvailable": False, "checked": False,
                "note": f"已记录：{DISMISS_DAYS} 天内不再提醒（至 {until}）。"}

    if dismissed_until and now.date().isoformat() < dismissed_until:
        return {"currentVersion": __version__,
                "latestVersion": state.get("latestVersion"),
                "updateAvailable": False, "checked": False,
                "note": f"用户此前已选择跳过（至 {dismissed_until}），本期不再提醒。"}

    cached_at = state.get("checkedAt")
    fresh = False
    if cached_at:
        try:
            age = (now - datetime.datetime.fromisoformat(cached_at)).total_seconds()
            fresh = age < CACHE_TTL_HOURS * 3600
        except ValueError:
            fresh = False
    latest = state.get("latestVersion") if fresh else _fetch_latest()
    if latest is None:
        return {"currentVersion": __version__, "latestVersion": None,
                "updateAvailable": False, "checked": False,
                "note": "版本检查不可达（离线/内网正常现象），不影响采集；稍后重试即可。"}

    if not fresh:
        tools._save_runtime({"update_check": {**state, "checkedAt": now.isoformat(
            timespec="seconds"), "latestVersion": latest}})
    newer = _version_tuple(latest) > _version_tuple(__version__)
    out = {"currentVersion": __version__, "latestVersion": latest,
           "updateAvailable": newer, "checked": True,
           "note": ("有新版本可用：重跑 install（幂等原位更新）或 vod-devkit update。"
                    "用户不想被打扰时用 dismiss=true 跳过 3 天。") if newer else
                   "已是最新版本。"}
    if newer:
        out["upgradeCommand"] = "vod-devkit update   # 或重跑 install（同一行装命令）"
    return out