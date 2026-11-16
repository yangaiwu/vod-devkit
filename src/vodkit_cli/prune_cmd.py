"""prune：显式清理旧载荷（D3，2026-11-16 负责人定案）。

为什么单独一个命令、而不是 install 顺手删：
  · 安装时删用户文件不可接受（无法回滚、误删风险高、用户没预期）；
  · 卸载才清理又太晚（很多机器只升级不卸载，旧载荷永远留着）。

约束（定案原文的落法）：
  · 只删清单内：`payload.prune_candidates()` 只认 `<payload_home>/payloads/<ver>/`
    且带 `payload.json`（stage() 落的）的目录，绝不 glob 盲删；
  · 保留当前版本 + 任何安装行 payloadDir 指向的版本 + dsh 各 profile patch 里 args 指向的
    版本（配置面也算在用）；`--keep N` 额外保留最新 N 份；
  · 默认 dry-run（只打印清单）；真删要 `--apply`；
  · 二次确认：交互式 y/N；非 tty 必须 `--yes`，否则拒绝；
  · 逐条打印 路径/版本/大小；
  · 只删载荷目录，不碰机器级 state；
  · 单条删除失败记录后继续，最后以非零退出码收尾。
"""
import sys

from vod_mcp import payload as _payload


def _fmt(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def _rows() -> list:
    from vodkit_cli import common
    import json
    p = common.manifest_path()
    if not p.exists():
        return []
    try:
        mf = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return mf.get("installs") or ([mf] if mf.get("target") else [])


def cmd_prune(args) -> int:
    if not getattr(args, "payloads", False):
        print("只支持 --payloads（当前唯一的清理对象）", file=sys.stderr)
        return 2
    rows = _rows()
    keep = int(getattr(args, "keep", 0) or 0)
    cands = _payload.prune_candidates(rows, keep=keep)
    if not cands:
        print("没有可清理的旧载荷（当前版本与安装行在用的都保留）")
        return 0
    total = sum(size for _p, _v, size in cands)
    print(f"可清理 {len(cands)} 份旧载荷，共 {_fmt(total)}"
          + (f"（额外保留最新 {keep} 份）" if keep else ""))
    for path, ver, size in cands:
        print(f"  - {ver:<10s} {_fmt(size):>9s}  {path}")
    print("  保留：当前版本 + 安装行在用的版本 + 机器级 state（不在本命令范围内）")

    if not getattr(args, "apply", False):
        print("（dry-run：未删除。确认后加 --apply 执行）")
        return 0
    if not getattr(args, "yes", False):
        if not sys.stdin.isatty():
            print("非交互环境需加 --yes 才执行删除（二次确认）", file=sys.stderr)
            return 2
        ans = input(f"确认删除上述 {len(cands)} 份载荷？[y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("已取消")
            return 0

    removed, failed = _payload.remove_payloads(cands)
    print(f"已删除 {len(removed)} 份"
          + (f"，失败 {len(failed)} 份（见上）" if failed else ""))
    return 1 if failed else 0