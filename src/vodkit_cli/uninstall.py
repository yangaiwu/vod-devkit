"""uninstall 子命令：按 manifest 名册逐宿主摘除（共享配置只摘条目）。"""
import json
import os
import shutil
import subprocess
import sys
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
            new_text2, removed2 = _hermes.remove_guard_hook(new_text)
            if removed or removed2:
                cfg.write_text(new_text2, encoding="utf-8")
                print("removed vod-devkit hooks:", cfg,
                      "(pre_llm_call)" if removed else "",
                      "(pre_tool_call)" if removed2 else "")
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
    if cli:
        r = subprocess.run([cli, *args], capture_output=True, text=True, timeout=120)
        print(f"{cli} mcp remove:", "OK" if r.returncode == 0
              else (r.stderr or r.stdout).strip()[-120:])


def _outside_home(p: Path) -> bool:
    """落点是否在当前 HOME 之外——**卸载是破坏性动作，守卫必须在这里**。

    实锤（2026-11-16）：`common.HERMES_SKILLS_DIR` 是 import 期常量，同进程里
    monkeypatch HOME 后它仍指真实家目录，隔离用例于是删掉了真机的 vod-core。
    判据用 resolve() 后前缀比较（符号链接/相对路径都归一）。
    """
    try:
        home = Path.home().resolve()
        return not str(Path(p).resolve()).startswith(str(home) + os.sep)
    except OSError:
        return True


def _remove_managed_skills(mf: dict, path: Path, target: str | None = None) -> None:
    """技能摘除：**只摘本插件装进去的子目录**，目录本身与别人的技能一律不动。

    为什么不再"hermes 目录整删"（2026-11-16 并行评审 P2）：该目录
    `~/.hermes/skills/devops/vod-devkit` 是所有安装共用的副本池（`install._install_skills`
    对每个宿主都会往这里拷一份），用户/其它插件也可能在这里放技能——整删会连带删掉
    不属于我们的东西。留下的空目录无害，`uninstall` 也不是清理工具。
    """
    names = {rel.split("/")[0] for rel in (mf.get("skillHashes") or {})}
    removed = []
    for n in sorted(names):
        d = path / n
        if d.is_dir():
            shutil.rmtree(d)
            removed.append(n)
    if removed:
        print(f"removed skills: {removed}（目录与其它技能保留）：{path}")
    else:
        print(f"skip（无需摘除的技能）：{path}")


def _cleanup_install_row(row: dict, skill_hashes: dict | None = None,
                        skill_installs: list | None = None,
                        remaining_targets: set | None = None) -> None:
    """按一条安装记录清理：技能落点 / MCP 条目 / 宿主专属产物。

    技能名清单来自 manifest 顶层 skillHashes（各安装行共用同一份技能集合）。
    技能**落点**来自顶层 skillInstalls（按 host 匹配）——不能只用 row["skillsDir"]：
    历史 manifest 把每一行的 skillsDir 都写成 hermes 目录（common.py 单值形态），
    于是 `uninstall --target opencode` 会去删 hermes 的技能目录、而 opencode 自己的
    `~/.config/opencode/skills` 永远漏删（并行评审 P2 实测）。
    """
    target = str(row.get("target") or "")   # 名册老条目可能缺 target：按空串走"未知宿主"分支
    # codex-desktop：mcpConfig 指向共享的 marketplace.json，绝不能走"整文件删"分支
    # （那会删掉用户/其它插件的市场登记）。交给适配器只摘自己那一条 + 删插件目录。
    if target == "codex-desktop":
        from vod_mcp.host_adapters import codex_desktop as _cd
        _cd.uninstall()
        return
    # openclaw：注册表在 JSON5 配置里（可能带注释），只许经它自己的 CLI 摘条目；
    # officeace：条目在宿主 sqlite（schema 不是我们的），只许删自己那几行。
    if target in ("openclaw", "officeace"):
        from vod_mcp.host_adapters import get as _get
        _get(target).uninstall()
        return
    mf = dict(row)
    mf["skillHashes"] = skill_hashes or {}
    # ① 技能：落点真源是 skillInstalls（按 host 匹配），且**共享落点不许摘**——
    #    历史 manifest 把每行 skillsDir 都写成 hermes 目录（单值形态），若照此行删，
    #    卸 opencode 会删掉 hermes 正在用的副本（卸 A 删 B），而 opencode 自己的
    #    ~/.config/opencode/skills 永远漏删。老 manifest 无该键时 skillsDir 只有
    #    hermes 行可信，其它行宁可漏删也不猜。
    installs = list(skill_installs or [])
    mine = [si for si in installs if si.get("host") == target and si.get("dir")]
    # hermes 目录是**所有安装共用**的副本池（install._install_skills 对每个宿主都往里拷，
    # _skill_installs 也恒含 hermes 条目）。所以它不是"别人的落点"，而是"我们冗余的一份"：
    # 本次卸载后若不再有 hermes 安装行，这一份也该摘。用自己的落点之外判据 = 剩余行。
    if target != "hermes" and "hermes" not in (remaining_targets or set()):
        # 路径**调用期**解析：common.HERMES_SKILLS_DIR 是 import 期常量，同进程里
        # monkeypatch HOME 之后它会指到真实家目录（隔离测试会去删真机技能，实锤）。
        try:
            pool = str(host_specs.load("hermes")["skillsDir"])
        except KeyError:
            pool = ""
        if pool:
            mine.append({"host": "hermes", "dir": pool})
    if not mine:
        legacy = row.get("skillsDir")
        if legacy and target == "hermes":
            mine = [{"host": target, "dir": legacy}]
    for si in mine:
        d = Path(si["dir"])
        if _outside_home(d):
            print(f"skip（落点不在当前 HOME 之下，拒绝删除）：{d}")
            continue
        _remove_managed_skills(mf, d, si.get("host"))
    # ② MCP 配置
    path_s = row.get("mcpConfig")
    if path_s and _outside_home(Path(path_s)):
        print(f"skip（配置不在当前 HOME 之下，拒绝改动）：{path_s}")
        path_s = None
    if path_s:  # codex 等宿主 mcpConfig 可为 None（P0-3：无托管配置文件）
        path = Path(path_s)
        # dsh 的 profile cordis.patch.yml 是**共享文件**（用户与其它插件也往里写 insert
        # 块）——整文件删会把别人的内容一起删掉（本轮 B 模式用例实锤：卸载后文件消失）。
        # 托管块的摘除由下方 dsh 段（remove_patch_block）完成，这里只打印不改字节。
        if target == "dsh":
            print(f"skip（dsh profile patch 是共享文件，只摘托管块）：{path}")
        # 深审 P0-3（破坏性路径一票否决）：共享用户配置永不整文件删除
        #（config.toml/opencode.json/codearts_cli.json/.claude.json 里有用户自己的
        # provider、其它 server）。JSON 合并型宿主一律走"摘条目"，与文件名无关——
        # codearts_cli.json 第一版没进 _SHARED_CONFIG_NAMES，卸载把整份配置删了（实锤）。
        elif target in ("opencode", "codeartsdoer", "codeartswork", "generic",
                        "workbuddy", "atomcode") or path.name in _SHARED_CONFIG_NAMES:
            print(f"skip（用户配置文件，uninstall 只摘托管条目）：{path}")
            _remove_managed_mcp_entry(target, path)
        elif path.exists():
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


def _clean_global(rows: list, remaining: list | None = None) -> None:
    """清外部残留（对齐 devkit `--clean-global`）：载荷残留 + npx 缓存里的旧副本。

    纪律：只删"认得的东西"，逐条打印；在用载荷、仓内源码、宿主配置一律不碰。
    `remaining` = 卸载后仍装着的其它宿主行：非空时**机器级 state 必须保留**
    （它是同机共享的设备锚点/令牌，删了会让剩余宿主下次首启换新 nonce = 新设备，
    历史提交查不到、匿名额度重计）。这条与载荷的 `in_use` 同形，不是特例。
    """
    from vod_mcp import payload as _payload
    from vod_mcp import paths as _paths
    in_use = _payload.in_use_payloads(rows)   # 账本 ∪ dsh 各 profile patch（P2 单一入口）
    for res in _payload.residue():
        try:
            key = str(Path(res).resolve())
        except OSError:
            key = str(res)
        if key in in_use:
            continue
        shutil.rmtree(res, ignore_errors=True)
        print("removed payload residue:", res)
    # 旧载荷（带 payload.json 的安装器产物）：与 `prune --payloads` 同一实现
    #（D3 定案：显式、只删清单内、保留 remaining 宿主仍在引用的版本）。
    old = _payload.prune_candidates(remaining or [])
    if old:
        _removed, _failed = _payload.remove_payloads(old)
        if _failed:
            print(f"[warn] 旧载荷删除失败 {len(_failed)} 份（见上）")
    # D-token-machine-1：机器级 state（跨版本/跨宿主共享的那一份）。
    state = _paths.machine_state_home()
    if remaining:
        users = ", ".join(r.get("target", "?") for r in remaining)
        print(f"保留 state：{state}（仍有宿主在用：{users}）——同机共享设备锚点/令牌")
    else:
        for name in ("runtime.json", "runtime.json.lock", ".migrated"):
            f = state / name
            if f.is_file():
                f.unlink()
                print("removed state:", f)
        if state.is_dir() and not any(state.iterdir()):
            state.rmdir()
            print("removed empty:", state)
    root = Path.home() / ".vod-devkit"
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()
        print("removed empty:", root)
    npx = Path.home() / ".npm" / "_npx"
    if npx.is_dir():
        for d in npx.iterdir():
            pkg = d / "node_modules" / "vod-devkit"
            if not pkg.is_dir():
                continue
            # 只删我们那一份：一个 npx hash 目录里可能同时缓存了别的包
            #（整目录 rmtree 会连带删掉用户其它 npx 缓存，评审 P2 实测）。
            shutil.rmtree(pkg, ignore_errors=True)
            try:
                leftovers = [x for x in (d / "node_modules").iterdir()]
            except OSError:
                leftovers = []
            if not leftovers:
                shutil.rmtree(d, ignore_errors=True)
                print("removed npx cache:", d)
            else:
                print(f"removed npx copy of vod-devkit（保留同目录其它包）：{pkg}")


def cmd_uninstall(args=None):
    target = (getattr(args, "target", "") or "") if args else ""
    clean_global = bool(getattr(args, "clean_global", False)) if args else False
    p = common.manifest_path()
    if not p.exists():
        print("未安装")
        return
    try:
        mf = common._read_manifest(strict=True)
    except common.ManifestCorrupt as e:
        print(f"[vod-devkit] {e}", file=sys.stderr)
        sys.exit(2)
    all_rows = mf.get("installs") or [mf]   # 老 manifest（无 installs[]）退化为单条
    rows = [r for r in all_rows if not target or r.get("target") == target]
    if not rows:
        print(f"没有该宿主的安装记录：{target}"
              f"（现有：{', '.join(r.get('target','?') for r in all_rows)}）")
        return
    for row in rows:
        still_installed = {r.get("target") for r in all_rows if r not in rows}
        _cleanup_install_row(row, mf.get("skillHashes"), mf.get("skillInstalls"),
                             still_installed)
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
        common.atomic_write_text(p, json.dumps(mf, ensure_ascii=False, indent=2))
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
        _clean_global(rows, remaining)
