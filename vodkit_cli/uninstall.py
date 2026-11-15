"""uninstall 子命令：按 manifest 名册逐宿主摘除（共享配置只摘条目）。"""
import json
import shutil
import subprocess
from pathlib import Path

from vod_mcp import hosts as host_specs
from vodkit_cli import common


_SHARED_CONFIG_NAMES = {"config.toml", "config.yaml", "config.yml",
                        "opencode.json", "opencode.jsonc"}


def _remove_managed_mcp_entry(target: str, path: Path) -> None:
    """从宿主共享配置里摘掉 vod-devkit 条目（保留其它键/其它 server）。"""
    section = {"opencode": "mcp", "codeartsdoer": "mcp", "codeartswork": "mcp",
               "generic": "mcpServers", "workbuddy": "mcpServers",
               "atomcode": "mcpServers"}.get(target)
    if section:
        if not path.exists():
            return
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            print(f"skip（{path} 不是合法 JSON，未改动）")
            return
        block = cfg.get(section) or {}
        if "vod-devkit" not in block:
            return
        block.pop("vod-devkit")
        if not block:
            cfg.pop(section, None)
        else:
            cfg[section] = block
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"removed {section}.vod-devkit: {path}")
        return
    cli: str | None = None
    args: list[str] = []
    if target == "hermes":
        # 先摘 config.yaml 的预采集 hook（shell hook 形态，D-hook-unify-1）
        from vod_mcp.host_adapters import hermes as _hermes
        cfg = Path(_hermes._profile_config())
        if cfg.exists():
            text = cfg.read_text(encoding="utf-8")
            new_text, removed = _hermes.remove_llm_hook(text)
            if removed:
                cfg.write_text(new_text, encoding="utf-8")
                print("removed vod-devkit pre_llm_call hook:", cfg)
        # 旧插件形态（老装机）一并摘
        legacy = _hermes.remove_legacy_plugin()
        if legacy:
            print("removed legacy plugin:", legacy)
        if shutil.which("hermes"):
            cli, args = "hermes", ["mcp", "remove", "vod-devkit"]
        else:
            cli, args = None, []
    elif target == "codex" and shutil.which("codex"):
        cli, args = "codex", ["mcp", "remove", "vod-devkit"]
    elif target == "codex" and shutil.which("codex"):
        cli, args = "codex", ["mcp", "remove", "vod-devkit"]
    if cli:
        r = subprocess.run([cli, *args], capture_output=True, text=True, timeout=120)
        print(f"{cli} mcp remove:", "OK" if r.returncode == 0
              else (r.stderr or r.stdout).strip()[-120:])


def _remove_managed_skills(mf: dict, path: Path, target: str) -> None:
    """技能摘除：hermes 目录是专属的（整目录删）；其它宿主技能目录是**共享**的
    （opencode ~/.config/opencode/skills 等），只摘本插件改名下的技能。
    2026-11-11 与 uninstall 共享配置收口同批修：整目录删会连带删掉用户的其它技能。"""
    if target == "hermes":
        if path.exists():
            shutil.rmtree(path)
            print("removed:", path)
        return
    names = {rel.split("/")[0] for rel in (mf.get("skillHashes") or {})}
    removed = []
    for n in sorted(names):
        d = path / n
        if d.is_dir():
            shutil.rmtree(d)
            removed.append(n)
    print(f"removed skills: {removed}（共享目录保留）：{path}") if removed \
        else print(f"skip（无需摘除的技能）：{path}")


def _cleanup_install_row(row: dict, skill_hashes: dict | None = None) -> None:
    """按一条安装记录清理：MCP 条目 / 技能落点 / 宿主专属产物。

    技能名清单来自 manifest 顶层 skillHashes（各安装行共用同一份技能集合）。
    """
    target = str(row.get("target") or "")   # 名册老条目可能缺 target：按空串走"未知宿主"分支
    # codex-desktop：mcpConfig 指向共享的 marketplace.json，绝不能走"整文件删"分支
    # （那会删掉用户/其它插件的市场登记）。交给适配器只摘自己那一条 + 删插件目录。
    if target == "codex-desktop":
        from vod_mcp.host_adapters import codex_desktop as _cd
        _cd.uninstall()
        return
    mf = dict(row)
    mf["skillHashes"] = skill_hashes or {}
    for key in ("mcpConfig", "skillsDir"):
        path_s = row.get(key)
        if not path_s:
            continue  # codex 等宿主 mcpConfig 可为 None（P0-3：无托管配置文件）
        if key == "skillsDir":
            _remove_managed_skills(mf, Path(path_s), target)
            continue
        path = Path(path_s)
        # 深审 P0-3（破坏性路径一票否决）：共享用户配置永不整文件删除
        #（config.toml/opencode.json/codearts_cli.json/.claude.json 里有用户自己的
        # provider、其它 server）。JSON 合并型宿主一律走"摘条目"，与文件名无关——
        # codearts_cli.json 第一版没进 _SHARED_CONFIG_NAMES，卸载把整份配置删了（实锤）。
        if target in ("opencode", "codeartsdoer", "codeartswork", "generic",
                      "workbuddy", "atomcode") or path.name in _SHARED_CONFIG_NAMES:
            print(f"skip（用户配置文件，uninstall 只摘托管条目）：{path}")
            _remove_managed_mcp_entry(target, path)
            continue
        if path.exists():
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            print("removed:", path)
    # codex 摘除：remote 形态摘 MCP 条目；stdio 形态摘原生插件（best-effort）
    if target == "codex":
        codex = shutil.which("codex")
        if codex and (row.get("transport") or "stdio") == "remote":
            _remove_managed_mcp_entry("codex", Path.home() / ".codex" / "config.toml")
        elif codex:
            r = subprocess.run([codex, "plugin", "remove", "vod-devkit@vod-local"],
                               capture_output=True, text=True, timeout=120)
            print("codex plugin remove:",
                  "OK" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-120:])
    # opencode 随装生成物（/vod-doctor 命令）
    if target == "opencode":
        for g in host_specs.load("opencode")["generated"]:
            gen = Path(g["dest"])
            if gen.exists():
                gen.unlink()
                print("removed:", gen)
    # dsh 壳（D-dsh-install-1）：摘插件 + 从 profile patch 移除 config 段
    if target == "dsh":
        dsh = shutil.which("dsh")
        prof = (row.get("dshProfile") or "").strip()
        if dsh and prof:
            subprocess.run([dsh, "plugin", "--profile", prof, "remove",
                            "dsh-vod-devkit"], capture_output=True, text=True)
        if prof:  # 无 profile 记录=没写过 patch，无需（也无法）摘除
            patch_path = Path(host_specs.load("dsh", prof)["configPath"])
            from vod_mcp.host_adapters import dsh as dsh_adapter
            if dsh_adapter.remove_patch_block(patch_path):
                print("removed vod-devkit config block:", patch_path)


def _clean_global(rows: list) -> None:
    """清外部残留（对齐 devkit `--clean-global`）：载荷残留 + npx 缓存里的旧副本。

    纪律：只删"认得的东西"，逐条打印；在用载荷、仓内源码、宿主配置一律不碰。
    """
    from vod_mcp import payload as _payload
    in_use = {r.get("payloadDir") for r in rows if r.get("payloadDir")}
    for res in _payload.residue():
        if str(res) in in_use:
            continue
        shutil.rmtree(res, ignore_errors=True)
        print("removed payload residue:", res)
    root = Path.home() / ".vod-devkit"
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()
        print("removed empty:", root)
    npx = Path.home() / ".npm" / "_npx"
    if npx.is_dir():
        for d in npx.iterdir():
            pkg = d / "node_modules" / "vod-devkit"
            if pkg.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                print("removed npx cache:", d)


def cmd_uninstall(args=None):
    target = (getattr(args, "target", "") or "") if args else ""
    clean_global = bool(getattr(args, "clean_global", False)) if args else False
    p = common.manifest_path()
    if not p.exists():
        print("未安装")
        return
    mf = json.loads(p.read_text(encoding="utf-8"))
    all_rows = mf.get("installs") or [mf]   # 老 manifest（无 installs[]）退化为单条
    rows = [r for r in all_rows if not target or r.get("target") == target]
    if not rows:
        print(f"没有该宿主的安装记录：{target}"
              f"（现有：{', '.join(r.get('target','?') for r in all_rows)}）")
        return
    for row in rows:
        _cleanup_install_row(row, mf.get("skillHashes"))
    # 载荷清理（D-payload-1）：逐目录去重后删——但别删还被保留行引用的载荷
    keep = {r.get("payloadDir") for r in all_rows if r not in rows and r.get("payloadDir")}
    seen = set()
    for row in rows:
        pd = row.get("payloadDir")
        if not pd or pd in seen or pd in keep:
            continue
        seen.add(pd)
        if Path(pd).is_dir():
            shutil.rmtree(pd, ignore_errors=True)
            print("removed payload:", pd)
    remaining = [r for r in all_rows if r not in rows]
    if remaining:
        mf["installs"] = remaining
        mf["target"] = remaining[-1].get("target")
        mf.pop("payloadDir", None)
        if not any(r.get("payloadDir") for r in remaining):
            from vod_mcp import payload as _payload
            try:
                _payload.marker_path().unlink(missing_ok=True)
            except Exception:
                pass
        p.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"removed install row(s): {', '.join(r.get('target','?') for r in rows)}"
              f"（保留 {', '.join(r.get('target','?') for r in remaining)}）")
    else:
        from vod_mcp import payload as _payload
        try:
            _payload.marker_path().unlink(missing_ok=True)
        except Exception:
            pass
        p.unlink()
        print("removed:", p)
    if clean_global:
        _clean_global(rows)
