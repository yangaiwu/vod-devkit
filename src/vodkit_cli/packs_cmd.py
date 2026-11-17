"""全局命令：version（各宿主已装版本一眼视图）/ packs（能力包启用面查看与持久改写）。

为什么要有（对齐 huaweicloud-devkit 的三条全局命令）：
多宿主分发必然产生版本碎片与能力面漂移——同一个包在 codex 缓存、hermes 配置、
dsh profile 里可能是三个版本/三套 VOD_PACKS。单宿主命令回答"这个宿主好不好"，
全局命令回答"整台机器现在是什么状态"。没有它，排查就是各查一遍配置文件。

数据源唯一：install-manifest.json 的 installs[]（D-installs-1：一个 manifest
记全部宿主安装）。本模块只**读**宿主真实配置来回答"实际生效的是哪一套"，
写只在 `packs enable/disable/all --apply` 时发生，并且只改受管条目的 env。
"""
import json
import shutil
import sys
from pathlib import Path

from vod_mcp import msgs
from vod_mcp import packs as packs_mod
from vod_mcp import paths
from vodkit_cli import common
from vod_mcp.host_adapters import codex as _codex

_ENV_KEYS = ("env", "environment")


def _rows() -> list:
    p = common.manifest_path()
    if not p.exists():
        return []
    mf = json.loads(p.read_text(encoding="utf-8"))
    return common.install_rows(mf)


def _filter(rows: list, target: str) -> list:
    if not target:
        return rows
    return [r for r in rows if r.get("target") == target]


def _current_version() -> str:
    from vod_mcp import __version__
    return __version__


# ── dsh：不进 installs[] 的宿主（只读探测） ─────────────────
#
# dsh 由 `dsh-vod-devkit` 的 profile 依赖承载（install --target dsh 只装壳包，
# 不写 install-manifest 行——D-installs-1 的账本只登记 MCP 宿主）。结果是
# `version` / `packs status` 里连一行都没有、也没有 [missing] 提示，读起来像
# "这台机器没装 dsh"。补法是只读探测 profile，**不是**把 dsh 塞进 installs[]
# （塞进去会改写安装/卸载语义：uninstall 会按行去删壳依赖）。

def _dsh_rows() -> list:
    """读 ~/.dsh/profiles/*/package.json，返回声明了 dsh-vod-devkit 的 profile。

    只读：不写 profile、不碰 node_modules。版本取**实际装下来的那份**
    （node_modules/dsh-vod-devkit/package.json）；取不到才回落声明的 spec
    ——spec 是意图（可能是 `file:…tgz` 或范围号），实际跑的是装下来的版本。
    """
    base = paths.host_home("DSH_HOME", ".dsh") / "profiles"
    if not base.is_dir():
        return []
    out = []
    for pj in sorted(base.glob("*/package.json")):
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dep = (data.get("dependencies") or {}).get("dsh-vod-devkit")
        bundles = ((data.get("dsh") or {}).get("profile") or {}).get("bundles") or []
        if not dep and "dsh-vod-devkit" not in bundles:
            continue
        inst = None
        try:
            inst = json.loads((pj.parent / "node_modules" / "dsh-vod-devkit"
                               / "package.json").read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError):
            pass
        out.append({"profile": pj.parent.name, "declared": dep or "(bundles 引用)",
                    "installed": inst, "config": str(pj)})
    return out


def _dsh_name(row: dict) -> str:
    return f"dsh({row['profile']})"


def _dsh_version_line(row: dict, cur: str) -> None:
    name = _dsh_name(row)
    inst = row["installed"] or row["declared"]
    if row["installed"] is None:
        verdict = "已装版本未知（node_modules 无该包，先 dsh plugin add dsh-vod-devkit）"
    elif inst == cur:
        verdict = "同版"
    else:
        verdict = (f"≠ CLI（{inst} → {cur}，重跑 install --target dsh "
                   f"--profile {row['profile']}）")
    print(f"  {name:14s} 已装 {inst:8s} {verdict}")
    _st, _eff, _note = _dsh_effective(row)
    print(f"  {'':14s} 生效 packs: {','.join(_eff) if _eff else '—'}   [{_st}] {_note}")


def _dsh_effective(row: dict) -> tuple:
    """dsh 的 packs 来源，按形态分两种（B 模式 D-dsh-mcp-b-1，0.5.10 起）：

    · MCP 模式：patch 托管块里 `- id: vod-devkit-mcp` 子项的 `env.VOD_PACKS`
      就是生效值（agent 工具面的 server 由它拉起）→ 与其它宿主一样可读；
    · 降级形态（无 mcp-client）：能力面由壳包固定（6 工具）→ 只能重装改。
    旧实现见 .yml 就报 `unsupported 不是 JSON 形态`，把可读的 YAML 说成读不了（D1）。
    """
    prof = str(row.get("profile") or row.get("dshProfile") or "")
    patch = paths.host_home("DSH_HOME", ".dsh") / "profiles" / prof / "cordis.patch.yml"
    if not prof or not patch.exists():
        return ("missing", None, f"dsh profile patch 不存在：{patch}")
    try:
        text = patch.read_text(encoding="utf-8", errors="replace")
    except OSError as e:  # noqa: BLE001
        return ("unparsable", None, f"patch 读不出（{e}）")
    if "- id: vod-devkit-mcp" not in text:
        return ("n/a", None,
                f"{patch}（降级形态：壳自注册 6 工具，能力面由包内固定，改 packs 需重装）")
    raw, in_mcp = None, False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("- id:"):
            in_mcp = (s == "- id: vod-devkit-mcp")
            continue
        if in_mcp and s.startswith("VOD_PACKS:"):
            raw = s.split(":", 1)[1].strip().strip("'\"")
            break
    if not raw:
        return ("n/a", None, f"{patch}（mcp-client 未设 VOD_PACKS，server 用内置默认）")
    try:
        eff = packs_mod.parse_packs(raw)
    except packs_mod.UnknownPack as e:
        return ("unparsable", None, str(e))
    return ("ok", eff, f"{patch}（mcp-client env.VOD_PACKS）")


def _codex_desktop_effective(row: dict) -> tuple:
    """codex-desktop 是 marketplace 登记形态（{name, source}），没有 env：
    packs 由插件包里的 .mcp.json 决定。旧实现按 mcpServers/env 找条目必然报
    missing，而 host_matrix 同时报 PASS —— 同一台机器两个门禁互相打架（D2）。
    判据：marketplace.plugins[] 里有登记就不是 missing。"""
    mp = Path.home() / ".agents" / "plugins" / "marketplace.json"
    if not mp.exists():
        return ("missing", None, f"marketplace 不存在：{mp}")
    try:
        cfg = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:  # noqa: BLE001
        return ("unparsable", None, f"marketplace 读不出（{e}）")
    plugins = cfg.get("plugins") or []
    hit = any((p.get("name") if isinstance(p, dict) else p) == "vod-devkit" for p in plugins)
    if not hit:
        return ("missing", None, f"marketplace 未登记 vod-devkit：{mp}")
    return ("n/a", None,
            f"{mp}（marketplace 登记形态：packs 由插件包内 .mcp.json 决定，装包时写入）")


def _dsh_packs_note(row: dict) -> str:
    """改 packs 的出路：MCP 形态能直接改 env，降级形态只能重装换形态。"""
    state, _eff, note = _dsh_effective(row)
    prof = row.get("profile") or row.get("dshProfile") or ""
    if state == "ok":
        return (f"dsh 的 packs 在 MCP 托管块的 env.VOD_PACKS（{note}）：改它，"
                f"或重跑 install --target dsh --profile {prof}")
    return (f"当前形态不支持改 packs（{note}）；换形态："
            f"install --target dsh --profile {prof}")


def _dsh_filter(rows: list, target: str) -> list:
    """--target 只有 dsh（整族）有意义；给具体 dsh(web) 也接受，便于复制输出。"""
    if not target or target == "dsh":
        return rows
    return [r for r in rows if target == _dsh_name(r)]


# ── 宿主配置定位与受管条目 ────────────────────────────────

def _config_path(row: dict) -> Path | None:
    """该安装行的 MCP 配置文件。codex 走插件缓存（manifest 里无 mcpConfig）。"""
    target = row.get("target")
    if target == "codex":
        from vod_mcp.host_adapters import codex
        ver = row.get("version")
        if ver:
            # 优先读"与 manifest 记录同版本"的缓存目录：多版本残留时按 mtime 取最新
            # 会把 0.5.5 的配置当成 0.5.9 的（实测本机就是这样）
            p = _codex.codex_home() / "plugins" / "cache" / "vod-local" / "vod-devkit" / ver / ".mcp.json"
            if p.exists():
                return p
        return codex.locate_plugin_mcp(None)
    cfg = row.get("mcpConfig")
    return Path(cfg) if cfg else None


def _locate_entry(cfg):
    """在任意宿主 JSON 里找到 vod-devkit 条目 → (entry_dict, env_key) 或 None。

    形态差异（实测）：hermes 的独立 mcp json 顶层就是条目本身；opencode 在
    `mcp.vod-devkit.environment`；其余在 `mcpServers.vod-devkit.env`；
    codex 插件缓存同 mcpServers。用递归定位而不是写死九张表——写死就会在
    下一个宿主形态上再漏一次。
    """
    if isinstance(cfg, dict) and cfg.get("name") == "vod-devkit" and "command" in cfg:
        return cfg, ("env" if "env" in cfg else "environment")
    stack = [cfg]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == "vod-devkit" and isinstance(v, dict) and (
                        "command" in v or "args" in v):
                    env_key = next((e for e in _ENV_KEYS if e in v), "env")
                    return v, env_key
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(x for x in cur if isinstance(x, (dict, list)))
    return None


def _read_effective(row: dict) -> tuple:
    """(形态, 实际生效 packs, 说明)。形态: ok / missing / unparsable / unsupported / n/a

    D1/D2（0.5.12）：两种非 MCP 落点必须先分派掉，否则会被当成"JSON 里找不到条目"
    —— dsh 读 patch YAML 托管块、codex-desktop 读 marketplace 登记。这两处曾与
    host_matrix 的结论直接矛盾（同一台机器一个 PASS 一个 missing）。
    """
    target = str(row.get("target") or "")
    if target == "dsh":
        return _dsh_effective(row)
    if target == "codex-desktop":
        return _codex_desktop_effective(row)
    path = _config_path(row)
    if path is None:
        return ("unsupported", None, "该宿主的 MCP 配置不在可写 JSON 里（dsh 等需重跑 install）")
    if path.suffix not in (".json", ".jsonc"):
        return ("unsupported", None, f"不是 JSON 形态（{path.name}），该宿主改 packs 需重跑 install")
    if not path.exists():
        return ("missing", None, f"配置不存在：{path}")
    stale = ""
    if row.get("target") == "codex" and row.get("version"):
        # manifest 记的版本与缓存目录不一致时说出来：实际跑的是哪个版本，别让人自己猜
        want = (_codex.codex_home() / "plugins" / "cache" / "vod-local" / "vod-devkit"
                / str(row["version"]) / ".mcp.json")
        if not want.exists():
            stale = f"（manifest 记 {row['version']}，cache 无该版本目录，读到的是残留副本）"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return ("unparsable", None, f"配置读不出（{e}）")
    hit = _locate_entry(cfg)
    if hit is None:
        return ("missing", None, f"配置里没有 vod-devkit 条目：{path}")
    entry, env_key = hit
    raw = (entry.get(env_key) or {}).get("VOD_PACKS")
    try:
        eff = packs_mod.parse_packs(raw or "")
    except packs_mod.UnknownPack as e:
        return ("unparsable", None, str(e))
    return ("ok", eff, f"{path}（{'.'.join([env_key, 'VOD_PACKS'])}）{stale}")


# ── version ───────────────────────────────────────────

def cmd_version(_args):
    """CLI 版本 + 每个宿主已装版本 + 实际生效的能力包（一眼诊断碎片）。"""
    cur = _current_version()
    print(f"vod-devkit CLI: {cur}")
    rows = _rows()
    if not rows:
        print("未安装（无 install-manifest；先 install --target <agent>）")
        return
    # S153 起账本也记 dsh 行（(target, dshProfile) 各一行）；这里统一交给下面的
    # profile 探测面显示，否则同一 profile 会打两遍（真机 4 行 dsh）。
    rows = [r for r in rows if r.get("target") != "dsh"]
    for row in rows:
        target = row.get("target", "?")
        inst = row.get("version") or row.get("source", {}).get("version") or "?"
        if inst == cur:
            verdict = "同版"
        else:
            verdict = f"≠ CLI（{inst} → {cur}，重跑 install 刷新）"
        state, eff, note = _read_effective(row)
        eff_s = ",".join(eff) if eff else "—"
        print(f"  {target:14s} 已装 {inst:8s} {verdict}")
        print(f"  {'':14s} 生效 packs: {eff_s}   [{state}] {note}")
    # dsh 的显示面统一走 profile 探测（账本行由它覆盖，避免同一 profile 显示两遍）
    for drow in _dsh_rows():
        _dsh_version_line(drow, cur)


# ── packs ────────────────────────────────────────────

def _write_packs(row: dict, new_packs: tuple, apply: bool) -> tuple:
    """把受管条目的 VOD_PACKS 改成 new_packs。返回 (changed?, 说明)。

    只改 env 里这一个键：其它 env（VOD_JAVA_API_BASE 等）与宿主其它 server、
    用户自有键原样保留；首改落 .bak。apply=False 时只报"将改什么"。
    """
    path = _config_path(row)
    if path is None or not path.exists():
        return (False, "配置不在可写 JSON 里（该宿主需重跑 install 改 packs）")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return (False, f"配置读不出（{e}），拒绝改动")
    hit = _locate_entry(cfg)
    if hit is None:
        return (False, "配置里没有 vod-devkit 条目，拒绝改动")
    entry, env_key = hit
    env = dict(entry.get(env_key) or {})
    want = ",".join(new_packs)
    if env.get("VOD_PACKS") == want:
        return (False, "已是目标值")
    if not apply:
        return (True, f"将把 {env_key}.VOD_PACKS: {env.get('VOD_PACKS') or '(缺省=全包)'} → {want}"
                      "（未写盘；加 --apply 生效）")
    shutil.copyfile(path, str(path) + ".bak")
    env["VOD_PACKS"] = want
    entry[env_key] = env
    common.atomic_write_text(path, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    # 写后读回：写成功 ≠ 落盘就是我们要的（并发改写/宿主升级会改回去）
    back = json.loads(path.read_text(encoding="utf-8"))
    hit2 = _locate_entry(back)
    if not hit2 or (hit2[0].get(hit2[1]) or {}).get("VOD_PACKS") != want:
        raise RuntimeError(f"写入后读回不一致：{path}")
    return (True, f"已写入 {path}（{msgs.effective()}；旧值备份 .bak）")


def cmd_packs(args):
    action = getattr(args, "packs_action", "status")
    target = getattr(args, "target", "") or ""
    rows = [r for r in _filter(_rows(), target) if r.get("target") != "dsh"]
    dsh = _dsh_filter(_dsh_rows(), target)
    if not rows and not dsh:
        print("未安装（无 install-manifest）" if not _rows() else f"没有该宿主的安装记录：{target}")
        return
    if action == "status":
        for row in rows:
            state, eff, note = _read_effective(row)
            eff_s = ",".join(eff) if eff else "—"
            print(f"{row.get('target'):14s} 生效 packs: {eff_s}   [{state}] {note}")
        for drow in dsh:
            _st, _eff, _note = _dsh_effective(drow)
            print(f"{_dsh_name(drow):14s} 生效 packs: "
                  f"{','.join(_eff) if _eff else '—'}   [{_st}] {_note}")
        return
    # enable/disable/all：dsh 的 packs 在 patch YAML 托管块里，本命令只改 JSON 形态，
    # 不代写 YAML（写坏托管块=插件掉出组合树/UI 消失）→ 跳过并说出路，不打印"已改"
    for drow in dsh:
        print(f"{_dsh_name(drow):14s} 跳过：{_dsh_packs_note(drow)}")
    if not rows:
        return
    # enable/disable/all
    if action == "all":
        want = packs_mod.ALL_PACKS
    else:
        ids = [p.strip() for p in (getattr(args, "ids", "") or "").split(",") if p.strip()]
        if not ids:
            print("用法：packs enable|disable core,collect [--target <agent>] [--apply]",
                  file=__import__("sys").stderr)
            return
        for row in rows:
            state, eff, note = _read_effective(row)
            if eff is None:
                print(f"{row.get('target'):14s} 跳过：{note}")
                continue
            base = list(eff)
            if action == "enable":
                base += [p for p in ids if p not in base]
            else:
                base = [p for p in base if p not in ids]
            want = tuple(dict.fromkeys(["core"] + base))   # core 强制包含
            try:
                changed, note = _write_packs(row, want, getattr(args, "apply", False))
            except RuntimeError as e:
                print(f"{row.get('target'):14s} 失败：{e}")
                continue
            print(f"{row.get('target'):14s} → {','.join(want)}  {note}")
            if changed and getattr(args, "apply", False):
                _update_row_packs(row.get("target"), ",".join(want))
        return
    for row in rows:
        state, eff, note = _read_effective(row)
        if eff is None:
            print(f"{row.get('target'):14s} 跳过：{note}")
            continue
        try:
            changed, note = _write_packs(row, want, getattr(args, "apply", False))
        except RuntimeError as e:
            print(f"{row.get('target'):14s} 失败：{e}")
            continue
        print(f"{row.get('target'):14s} → {','.join(want)}  {note}")
        if changed and getattr(args, "apply", False):
            _update_row_packs(row.get("target"), ",".join(want))


def _update_row_packs(target: str, packs: str) -> None:
    """manifest 行同步（幂等；读改写整份文件，只动目标行的 packs）。"""
    p = common.manifest_path()
    if not p.exists():
        return
    try:
        mf = common._read_manifest(strict=True)
    except common.ManifestCorrupt as e:
        print(f"[vod-devkit] {e}", file=sys.stderr)
        sys.exit(2)
    rows = mf.get("installs") or []
    for r in rows:
        if r.get("target") == target:
            r["packs"] = packs
    if rows:
        mf["installs"] = rows
        mf["packs"] = packs
    common.atomic_write_text(p, json.dumps(mf, ensure_ascii=False, indent=2))