"""安装载荷（payload）：把 server 与技能拷到宿主 / 用户自己的稳定目录。

动机（对标 huaweicloud-devkit 的 copyServerPayload，D-payload-1）：
本仓所有 MCP 入口此前指向 `<repo>/vod_mcp/server.py`。用 npx 安装时 repo 在
`~/.npm/_npx/<hash>/`，npm 一旦清缓存/换版本，入口指向已删除的路径 —— 宿主
启动即 MCP 掉线，而用户看不到任何报错。

载荷模型就是它那套：
  ① 落一份稳定副本（默认 ~/.vod-devkit/payloads/<version>/）
  ② 入口指向副本，不指向 npx 缓存
  ③ 每次 install 覆盖 + prune 掉源里已不存在的旧条目（只删我们自己前缀的）
  ④ 落 `.installed` 标记 = "载荷已换，重启即生效"；server 启动时自己删掉
  ⑤ payload.json 记录版本/commitSha/逐文件 sha256（doctor 与 verify 的依据）

与 devkit 的差别：零第三方依赖 → 不需要它的 installRuntimeDeps（npm install
undici 那一段）；我们只校验 Python 版本与文件指纹。
"""
import hashlib
import json
import os
import shutil
import datetime
from pathlib import Path

from vod_mcp import paths

ROOT = paths.ROOT

def payload_home() -> Path:
    """载荷根（用户级，多宿主共享；版本目录隔离）。

    每次读 env：测试用 VOD_PAYLOAD_HOME 重定向，进程内可随时改——
    常量在 import 期求值会把测试写进真实 ~/.vod-devkit（第一版实锤）。
    """
    return Path(os.environ.get("VOD_PAYLOAD_HOME") or (Path.home() / ".vod-devkit"))

# 我们拥有的顶层条目（prune 只在这个集合内动手，绝不碰用户文件）
OWNED = ("vod_mcp", "contract", "safety", "skills", "hooks",
         "build-info.json", "payload.json", "package.json")

SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {"runtime.json", "install-manifest.json", "payload.json"}
SKIP_SUFFIX = (".pyc", ".pyo", ".log")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(src: Path):
    for p in sorted(src.rglob("*")):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_FILES or p.name.endswith(SKIP_SUFFIX):
            continue
        yield p


def payload_dir(version: str | None = None) -> Path:
    from vod_mcp import __version__
    return payload_home() / "payloads" / (version or __version__)


def marker_path() -> Path:
    return payload_home() / ".installed"


def file_hashes(base: Path) -> dict:
    out = {}
    for p in _iter_files(base):
        out[str(p.relative_to(base)).replace(os.sep, "/")] = _sha256(p)
    return out


def prune_stale(dest: Path, src_names: set) -> list:
    """删掉 dest 里我们拥有、但源里已不存在的顶层条目（升级不留残骸）。"""
    removed = []
    if not dest.exists():
        return removed
    for entry in sorted(dest.iterdir()):
        if entry.name not in OWNED or entry.name in src_names:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed.append(entry.name)
    return removed


def stage(version: str | None = None, quiet: bool = False) -> Path:
    """把载荷拷进稳定目录（存在则原地刷新），返回载荷目录。"""
    from vod_mcp import __version__
    version = version or __version__
    dest = payload_dir(version)
    dest.mkdir(parents=True, exist_ok=True)

    from vod_mcp import paths as _paths
    # 运行期源码取自 SRC_ROOT（仓内=src/，载荷/插件副本=根），资产取自 ASSETS，
    # hook 脚本取自它的真实位置（仓内在 integrations/hermes/hooks/）。
    sources = {"vod_mcp": _paths.SRC_ROOT / "vod_mcp",
               "contract": _paths.ASSETS / "contract",
               "safety": _paths.ASSETS / "safety",
               "skills": _paths.ASSETS / "skills",
               "hooks": _paths.hook_script().parent}
    for name, src in sources.items():
        if not src.is_dir():
            continue  # hooks 可缺（历史版本载荷）
        target = dest / name
        target.mkdir(parents=True, exist_ok=True)
        for f in _iter_files(src):
            rel = f.relative_to(src)
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, out)

    # 顶层单体文件
    for name in ("build-info.json", "package.json"):
        src = ROOT / name
        if src.exists():
            shutil.copyfile(src, dest / name)

    removed = prune_stale(dest, set(sources) | {"build-info.json", "package.json",
                                                "payload.json"})

    info = json.loads((ROOT / "build-info.json").read_text(encoding="utf-8")) \
        if (ROOT / "build-info.json").exists() else {}
    manifest = {
        "version": version,
        "commitSha": info.get("commitSha"),
        "stagedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": file_hashes(dest),
    }
    (dest / "payload.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    marker_path().parent.mkdir(parents=True, exist_ok=True)
    marker_path().write_text(datetime.datetime.now().isoformat(timespec="seconds"),
                             encoding="utf-8")
    if not quiet:
        print(f"载荷已就位：{dest}（{len(manifest['files'])} 个文件"
              + (f"；清理旧条目 {removed}" if removed else "") + "）")
    return dest


def consume_marker() -> None:
    """server 启动时调用：标记只表示"换过载荷，该重启"，被运行中的进程消费掉。"""
    try:
        marker_path().unlink(missing_ok=True)
    except Exception:
        pass


def verify(payload: Path) -> list:
    """比对 payload.json 的逐文件 sha256，返回问题清单（空=OK）。"""
    problems = []
    pj = payload / "payload.json"
    if not pj.exists():
        return [f"载荷缺 payload.json：{payload}"]
    data = json.loads(pj.read_text(encoding="utf-8"))
    for rel, sha in (data.get("files") or {}).items():
        f = payload / rel
        if not f.exists():
            problems.append(f"载荷文件缺失：{rel}")
        elif _sha256(f) != sha:
            problems.append(f"载荷文件被改：{rel}")
    return problems


def residue() -> list:
    """没有 payload.json 的载荷目录 = 残留（旧版本/手工拷贝），doctor 报出来。"""
    base = payload_home() / "payloads"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.iterdir())
            if p.is_dir() and not (p / "payload.json").exists()]


def _vkey(name: str) -> tuple:
    """版本目录名排序键（0.5.9 < 0.5.10 < 0.5.11；非数字段落当 0，不抛异常）。"""
    out = []
    for part in str(name).replace("-", ".").split("."):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


def _tree_size(p: Path) -> int:
    try:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _patch_referenced_payloads() -> set:
    """dsh profile patch 里 args 指向的载荷根（S153）。

    账本的 payloadDir 只记"最近一次安装"的那一行；dsh 有多个 profile（web/headless），
    各自 patch 可能指向不同版本。只按账本算"在用"，会把另一个 profile 仍在用的载荷
    当孤儿删掉——宿主下次启动即白屏（工具面全失）。所以"在用"集合必须同时扫配置面。
    """
    import re
    used: set = set()
    root = Path(os.path.expanduser("~")) / ".dsh" / "profiles"
    if not root.is_dir():
        return used
    pat = re.compile(r"(/\S+?/payloads/[^/\s]+)/vod_mcp/server\.py")
    for f in root.glob("*/cordis.patch.yml"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in pat.finditer(text):
            try:
                used.add(str(Path(m.group(1)).resolve()))
            except OSError:
                used.add(m.group(1))
    return used


def prune_candidates(rows=None, keep: int = 0) -> list:
    """可清理的旧载荷清单 —— 只认安装器自己落过的，且没有宿主在跑（D3，0.5.13）。

    约束（负责人 2026-11-16 定案）：
      · 只删清单内：必须是 `<payload_home>/payloads/<ver>/` 且带 `payload.json`
        （= stage() 落的），绝不按 glob 删目录；
      · 保留当前版本，以及任何安装行 payloadDir 指向的版本（在用的不碰）；
      · keep>0 时额外保留最新的 keep 份；
      · 只读 payloads/ 目录，不碰机器级 state（令牌/账本）。
    返回 [(path, version, size_bytes)]，按版本升序（最旧的在前）。
    """
    from vod_mcp import __version__
    base = payload_home() / "payloads"
    if not base.is_dir():
        return []
    used = set()
    for r in (rows or []):
        d = str(r.get("payloadDir") or "").strip()
        if d:
            try:
                used.add(str(Path(d).resolve()))
            except OSError:
                used.add(d)
    # S153：配置面同样算"在用"（dsh 多 profile 各指一份版本）
    used |= _patch_referenced_payloads()
    cand = []
    for d in sorted(base.iterdir(), key=lambda p: _vkey(p.name)):
        if not d.is_dir() or not (d / "payload.json").exists():
            continue
        try:
            if str(d.resolve()) in used:
                continue
        except OSError:
            continue
        if d.name == __version__:
            continue
        cand.append(d)
    if keep > 0:
        cand = cand[:-keep] if len(cand) > keep else []
    return [(d, d.name, _tree_size(d)) for d in cand]


def remove_payloads(cands, quiet: bool = False) -> tuple:
    """按清单删除载荷目录：单条失败记录后继续，返回 (removed, failed)。"""
    removed, failed = [], []
    for path, ver, _size in cands:
        try:
            shutil.rmtree(path)
            removed.append(str(path))
            if not quiet:
                print(f"removed old payload {ver}: {path}")
        except OSError as e:  # noqa: BLE001  单条失败不中断整体
            failed.append((str(path), str(e)))
            if not quiet:
                print(f"[warn] 删除失败 {path}: {e}")
    return removed, failed