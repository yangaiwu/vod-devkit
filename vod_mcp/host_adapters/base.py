"""宿主适配公共件：MCP server 入口、环境与 JSON 配置合并（各宿主共用）。"""
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# 载荷目录（bin 在 install 前用 payload.stage() 落好并 set_payload_dir 指过来）
_PAYLOAD_DIR = None


def set_payload_dir(path) -> None:
    global _PAYLOAD_DIR
    _PAYLOAD_DIR = Path(path) if path else None


def payload_dir():
    return _PAYLOAD_DIR


def server_entry() -> str:
    """MCP server 绝对路径：优先载荷副本（npx 缓存被清也不会掉线），否则仓内。"""
    base = _PAYLOAD_DIR or ROOT
    return str(Path(base) / "vod_mcp" / "server.py")


def server_env(args, packs: str) -> dict:
    # 无 key 不写空串（空串会让探针/严格解析器误当字面值；运行时空=未设置，
    # 自动兜底 runtime.json java_key 或首提申请匿名令牌）
    env = {"VOD_PACKS": packs,
           "VOD_JAVA_API_BASE": args.java_api_base}
    key = os.environ.get("VOD_JAVA_API_KEY", "")
    if key:
        env["VOD_JAVA_API_KEY"] = key
    return env


def merge_json_mcp(path: Path, entry: dict, section: str = "mcp",
                   name: str = "vod-devkit", backup: bool = True) -> str:
    """读写共享 JSON 配置里的 <section>.<name> 条目（保留其它键/其它 server）。

    返回 created / updated / unchanged；文件不是合法 JSON 时抛 RuntimeError
    （调用方拒绝安装，字节不动）。共享配置文件首改落 .bak。
    """
    cfg = {}
    existed = path.exists()
    if existed:
        raw = path.read_text(encoding="utf-8")
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"{path} 不是合法 JSON（{e.msg}），拒绝改动") from e
            if not isinstance(parsed, dict):
                raise RuntimeError(f"{path} 顶层不是对象，拒绝改动")
            cfg = parsed
    block = cfg.get(section)
    if block is None:
        block = {}
    elif not isinstance(block, dict):
        raise RuntimeError(f"{path} 的 {section} 不是对象，拒绝改动")
    if block.get(name) == entry:
        return "unchanged"
    action = "updated" if block.get(name) else "created"
    if existed and backup:
        shutil.copyfile(path, str(path) + ".bak")
    block[name] = entry
    cfg[section] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return action
