"""宿主适配层：每个宿主的路径/探测/生成物集中在 integrations/<host>/host.json。

动机（devkit 对表结论之一）：新增宿主此前要在 1074 行的 bin 里改五处常量
与若干字面量路径，改漏一处就是"装了一半"。把**数据**（配置落点、技能目录、
平台差异、随装生成物）抽到 host.json，代码只保留每个宿主真正不同的安装
**逻辑**（hermes 走官方 CLI、opencode 走 JSON 合并、codex/dsh 走插件命令）。

纪律：
- host.json 里的路径一律相对 HOME 用 `~` 表示，由本模块解析；不许在代码里
  出现第二份路径字面量。
- 平台差异用键名 "default"/"windows" 区分（当前只有 opencode 分叉）。
- `{profile}` 是 dsh 的占位符，必须由调用方显式代入（缺省不猜）。
"""
import json
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEGRATIONS = ROOT / "integrations"


def hosts() -> list:
    if not INTEGRATIONS.is_dir():
        return []
    return sorted(p.name for p in INTEGRATIONS.iterdir()
                  if (p / "host.json").exists())


def _pick(value):
    """平台分叉取值：{"default": x, "windows": y} → 当前平台对应的字符串。"""
    if isinstance(value, dict):
        key = "windows" if platform.system() == "Windows" else "default"
        return value.get(key, value.get("default"))
    return value


def _resolve(path_str, profile: str | None = None) -> Path:
    if not isinstance(path_str, str) or not path_str:
        raise ValueError("host.json 的路径配置缺失")
    if "{profile}" in path_str:
        if not profile:
            raise ValueError(f"路径 {path_str} 需要 profile 名（dsh 按 profile 组织）")
        path_str = path_str.replace("{profile}", profile)
    if path_str.startswith("~"):
        return Path.home() / path_str[2:] if path_str.startswith("~/") else Path.home()
    return Path(path_str)


def raw(host: str) -> dict:
    """读原始 host.json（不解析路径、不代入 profile）——探测/展示用。

    动机（2026-11-11 实测）：detect_targets 走 load() 时，dsh 的 configPath
    含 {profile} 必填占位符 → ValueError，--target auto 在装了 dsh 集成后直接
    崩。探测只需要 detectCLI/detectPath，不该被路径解析拖累。
    """
    p = INTEGRATIONS / host / "host.json"
    if not p.exists():
        raise KeyError(f"未知宿主 {host}")
    data = json.loads(p.read_text(encoding="utf-8"))
    detect = data.get("detect") or {}
    # 只补探测所需的两键（与 load() 同名）；configPath 等仍留原始串，不解析
    # {profile}——探测不该依赖安装期才有的输入。
    data["detectCLI"] = detect.get("cli")
    data["detectPath"] = (_resolve(_pick(detect["path"]))
                          if detect.get("path") else None)
    return data


def load(host: str, profile: str | None = None) -> dict:
    """读一个宿主的适配数据并解析成绝对路径 → dict（键为契约的一部分）。

    返回键：id / cli / detectCLI / detectPath / configPath / skillsDir /
    generated[{template, dest}] / managedPaths / notes
    未知宿主抛 KeyError（调用方据此给"不支持目标"提示，不许静默降级）。
    """
    p = INTEGRATIONS / host / "host.json"
    if not p.exists():
        raise KeyError(f"未知宿主 {host}（可选：{'、'.join(hosts())}）")
    raw = json.loads(p.read_text(encoding="utf-8"))
    detect = raw.get("detect") or {}
    spec = {
        "id": raw.get("id") or host,
        "cli": raw.get("cli"),
        "detectCLI": detect.get("cli"),
        "detectPath": (_resolve(_pick(detect["path"]), profile)
                       if detect.get("path") else None),
        "configPath": (_resolve(_pick(raw["config"]), profile)
                       if raw.get("config") else None),
        "skillsDir": (_resolve(_pick(raw["skillsDir"]), profile)
                      if raw.get("skillsDir") else None),
        "generated": [
            {"template": INTEGRATIONS / host / g["template"],
             "dest": _resolve(_pick(g["dest"]), profile)}
            for g in raw.get("generated") or []
        ],
        "managedPaths": [_resolve(_pick(x), profile)
                         for x in raw.get("managedPaths") or []],
        "notes": raw.get("notes") or "",
    }
    return spec