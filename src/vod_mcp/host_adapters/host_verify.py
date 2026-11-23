"""宿主 MCP 注册「真的落盘了」的统一判据（D-host-verify-1，2026-11-17 评审）。

为什么必须一处：install 收尾与 doctor 自检曾各用一套判据——install 只看 CLI 的 rc，
doctor 不查 configPath，于是出现「install rc=0 + doctor OK，工具却连不上」
（实测：隔离 HOME + 无 hermes CLI，只写备片 + hooks，config.yaml 无 mcp_servers）。

问题码分档（文案不复用，用户才知道下一步做什么）：
  no-entry  有 CLI 且写入动作发生过，读回没有条目 → **重跑 install**（install 非零退出）
  missing   降级（无 CLI / 超时 / rc!=0）本就没写 → **手工并入备片**（install rc=0，doctor 红）
  disabled  条目在但 enabled: false → 宿主不会加载（改回 true 或重跑 install）
  mismatch  条目在但指向的 server.py 不存在（载荷被删/路径写错）

范围（S178 扩面）：
  - hermes：`hermes mcp add` 交互被跳过时 rc=0 却不落配置（0.5.29 修）。
  - opencode / atomcode / workbuddy / codeartswork / codeartsdoer：JSON 配置型宿主。
    共同盲区是「合并器写完就打印成功」，被别的进程覆盖/写坏时 install 与 doctor 都看不见。
  - codex 不在此（已由 doctor 的 `.mcp.json` 形态三分类 `plugin_mcp_form()` 判）；
    同一宿主两套判据必然长成「一侧 OK 一侧 DRIFT」，所以这里不重复报。
  - generic：配置路径由 `--mcp-config` 现给，没有稳定 spec，留待单独的「显式路径」判据。

依赖方向（ARCH-DEP-01，2026-11-19 走查）：**本模块不许反向 import 具体适配器**。
适配器在降级分支里要的是"我自己的核验结论"，走下面的注入点登记取值函数
（此前 `_hermes_problems` 函数内 import hermes，与 `hermes.py` 函数内 import
本模块互为依赖，环只被"函数内 import"撑着）。
"""
import json
from pathlib import Path

# 宿主 → 取值函数（由各适配器在 import 期调用 register_verifier 登记）
_VERIFIERS: dict = {}


def register_verifier(host: str, fn) -> None:
    """供适配器登记"怎么取我自己的安装态"。重复登记以最后一次为准（幂等重载）。"""
    _VERIFIERS[host] = fn

SUPPORTED = ("hermes", "opencode", "atomcode", "workbuddy", "codeartswork", "codeartsdoer")

# host → (配置里的段名, command 是否为数组)
_JSON_HOSTS = {
    "opencode": ("mcp", True),
    "codeartswork": ("mcp", True),
    "codeartsdoer": ("mcp", True),
    "atomcode": ("mcpServers", False),
    "workbuddy": ("mcpServers", False),
}


def problems(host: str, *, degraded: bool = False) -> list:
    """返回 [] 表示注册可用；否则 [{"code", "target", "message"}]。

    `degraded=True` 由调用方在「无 CLI / 命令超时 / CLI rc!=0」时传——此时没有写入
    动作发生过，码是 missing（引导手工并入），不是 no-entry（引导重装）。
    """
    if host == "hermes":
        return _hermes_problems(degraded=degraded)
    if host in _JSON_HOSTS:
        return _json_problems(host, degraded=degraded)
    return []


def _hermes_problems(*, degraded: bool) -> list:
    # ARCH-DEP-01：取值函数由 hermes 模块在 import 期登记（本模块不反向 import 它）。
    # getter 未登记 ≠ 不可用：doctor 冷启动时 hermes 还没被加载过。这里按需 import 一次
    # （经 `get()` 走惰性注册表，probe 语义与"读本身即为可达性检查"一致），
    # 真加载不到才如实报"判不了"，不静默返回 OK。
    getter = _VERIFIERS.get("hermes")
    if getter is None:
        try:
            from vod_mcp.host_adapters import get as _ha_get
            _ha_get("hermes")                       # 触发 import 期登记
        except Exception:      # noqa: BLE001  宿主适配器缺失（载荷裁剪）：如实报
            return [{"code": "unverifiable", "target": "hermes",
                     "message": "hermes 适配器不可用（无核验入口）——重跑 install --target hermes"}]
        getter = _VERIFIERS.get("hermes")
    if getter is None:
        return [{"code": "unverifiable", "target": "hermes",
                 "message": "hermes 适配器未登记核验入口——重跑 install --target hermes"}]
    st, cfg = getter()
    if not st["present"]:
        code = "missing" if degraded else "no-entry"
        tail = ("手工把 <vod-devkit 备片> 并入该配置的 mcp_servers（无 CLI 时安装器只写备片）"
                if degraded else
                "重跑 install（有 hermes CLI 时逐问回答 y）；没有 CLI 则手工把备片并入 mcp_servers")
        return [{"code": code, "target": "hermes",
                 "message": f"hermes config.yaml 缺 mcp_servers.vod-devkit（{cfg}）——{tail}"}]
    if st["enabled_false"]:
        return [{"code": "disabled", "target": "hermes",
                 "message": f"hermes 的 mcp_servers.vod-devkit 被 enabled: false 关掉（{cfg}）"
                            "——改回 true 或重跑 install"}]
    return []


def _is_npx_form(entry: dict) -> bool:
    """配置是否 npx 启动形态：command 为 npx，或 argv 里出现 vod-devkit-mcp。"""
    cmd = entry.get("command")
    first = cmd[0] if isinstance(cmd, list) and cmd else cmd
    argv = list(cmd[1:]) if isinstance(cmd, list) else list(entry.get("args") or [])
    if str(first or "").strip() in ("npx", "npx.cmd"):
        return True
    return any(str(a).strip() == "vod-devkit-mcp" for a in argv)


def _entry_server_path(entry: dict) -> str:
    """从条目里取出 server.py 的路径（两种形态：command 数组 / command+args）。"""
    cand: list = []
    cmd = entry.get("command")
    if isinstance(cmd, list):
        cand.extend(str(x) for x in cmd)
    elif cmd:
        cand.append(str(cmd))
    cand.extend(str(x) for x in (entry.get("args") or []))
    for c in cand:
        if c.endswith(".py"):
            return c
    return ""


def _json_problems(host: str, *, degraded: bool) -> list:
    from vod_mcp import hosts as host_specs
    from vod_mcp.host_adapters import get as _ha_get

    section, _ = _JSON_HOSTS[host]
    try:
        mod = _ha_get(host)              # ARCH-DEP-02：惰性注册表只存名字，取模块要过 get()
        # 落点必须与 install 同一来源（codeartswork 有新旧目录之分）
        cfg = (mod.config_path() if hasattr(mod, "config_path")
               else Path(host_specs.load(host)["configPath"]))
    except (KeyError, ValueError):      # 未知宿主/路径缺 profile：不归本模块管
        return []
    data = {}
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [{"code": "mismatch", "target": host,
                     "message": f"{host} 的配置不是合法 JSON（{cfg}）——拒绝改写，先人工修"}]
    block = data.get(section) if isinstance(data, dict) else None
    entry = block.get("vod-devkit") if isinstance(block, dict) else None
    if not isinstance(entry, dict):
        code = "missing" if degraded else "no-entry"
        return [{"code": code, "target": host,
                 "message": f"{host} 配置里没有 {section}.vod-devkit（{cfg}）——"
                            + ("手工按备片片段并入" if degraded else "重跑 install")}]
    if entry.get("enabled") is False:
        return [{"code": "disabled", "target": host,
                 "message": f"{host} 的 {section}.vod-devkit 是 enabled: false（{cfg}）"
                            "——改回 true 或重跑 install"}]
    if entry.get("url") or entry.get("type") == "remote":
        # 远程形态（streamable-http）：没有 server.py 参数，判据是 url 非空
        if str(entry.get("url") or "").strip():
            return []
        return [{"code": "mismatch", "target": host,
                 "message": f"{host} 的 {section}.vod-devkit 是远程形态但 url 为空（{cfg}）"
                            "——重跑 install"}]
    if _is_npx_form(entry):
        # npx 形态（D-interpreter-1）：没有 server.py 参数，判据是启动器可用
        import shutil as _sh

        missing = [b for b in ("npx", "node") if not _sh.which(b)]
        if missing:
            return [{"code": "mismatch", "target": host,
                     "message": f"{host} 是 npx 启动形态，但 PATH 上找不到 {'/'.join(missing)}"
                                "——装 node/npm，或重跑 install --mcp-launcher python"}]
        return []
    server = _entry_server_path(entry)
    if not server or not Path(server).exists():
        return [{"code": "mismatch", "target": host,
                 "message": f"{host} 的 {section}.vod-devkit 指向的 server 不存在"
                            f"（{server or '未找到 .py 参数'}）——重跑 install 重建载荷/条目"}]
    return []


def require_ok(host: str, *, degraded: bool = False) -> None:
    """安装收尾用：读回不通过就非零退出（绝不打印成功）。"""
    import sys

    bad = problems(host, degraded=degraded)
    for p in bad:
        print(f"[vod-devkit] {p['message']}", file=sys.stderr)
    if bad:
        sys.exit(1)