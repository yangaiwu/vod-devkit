"""runtime.json 的原子性与跨进程一致性（S137，P0 修复的回归锁）。

三个真实故障形态（修复前全部复现）：
1. **跨进程丢更新**：一份载荷 runtime.json 被同机多个宿主的 server 进程共用，
   `threading.RLock` 管不到别的进程 → 4 进程各写 25 条，落盘只剩 36 条（期望 100）。
2. **非原子写**：整文件 `write_text`，读者会读到半截 JSON（实测并发读里出现
   JSONDecodeError）→ 下一次"读到 {}"的更新把 key/账本冲成空。
3. **坏文件静默归零**：解析失败 `except: return {}`，不留备份、不告警。

修复=跨进程文件锁 + tmp/os.replace + 坏文件备份后继续。这三条都锁在这里。
"""
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _child_env(tmp_path):
    env = dict(os.environ)
    env["VOD_DEVKIT_DIST_ROOT"] = str(tmp_path)
    env["VOD_DEVKIT_SRC_ROOT"] = str(SRC)
    env["PYTHONPATH"] = str(SRC)
    env.pop("VOD_DEVKIT_MANIFEST", None)
    return env


def _write_child(tmp_path, worker: int, count: int) -> str:
    return (
        "import os\n"
        f"os.environ['VOD_DEVKIT_DIST_ROOT'] = {str(tmp_path)!r}\n"
        f"os.environ['VOD_DEVKIT_SRC_ROOT'] = {str(SRC)!r}\n"
        "from vod_mcp import runtime_state as rs\n"
        f"for i in range({count}):\n"
        f"    rs._runtime_update({{'k{worker}_' + str(i): i}})\n"
    )


def _runtime_file(tmp_path) -> Path:
    return tmp_path / "vod_mcp" / "runtime.json"


# ── S137 跨进程不丢更新 ──────────────────────────────────

def test_s137_concurrent_writers_do_not_lose_updates(tmp_path):
    procs = [subprocess.Popen([sys.executable, "-c", _write_child(tmp_path, n, 25)],
                              env=_child_env(tmp_path),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for n in range(4)]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err.decode()[-500:]
    data = json.loads(_runtime_file(tmp_path).read_text(encoding="utf-8"))
    keys = [k for k in data if k.startswith("k") and "_" in k]
    assert len(keys) == 100, f"跨进程丢了更新：{len(keys)}/100（修复前实测 36）"


def test_s137_lock_file_is_created(tmp_path):
    code = _write_child(tmp_path, 0, 1)
    subprocess.run([sys.executable, "-c", code], env=_child_env(tmp_path),
                   check=True, timeout=60)
    assert (_runtime_file(tmp_path).with_name("runtime.json.lock")).exists()


# ── S137 原子替换：读者永远看不到半截 JSON ──────────────────

def test_s137_readers_never_see_partial_json(tmp_path):
    writer = subprocess.Popen(
        [sys.executable, "-c",
         "import os\n"
         f"os.environ['VOD_DEVKIT_DIST_ROOT'] = {str(tmp_path)!r}\n"
         f"os.environ['VOD_DEVKIT_SRC_ROOT'] = {str(SRC)!r}\n"
         "from vod_mcp import runtime_state as rs\n"
         "for i in range(300):\n"
         "    rs._runtime_update({'n' + str(i): 'x' * 2000})\n"],
        env=_child_env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    bad, reads = 0, 0
    f = _runtime_file(tmp_path)
    while writer.poll() is None or reads < 50:
        if f.exists():
            try:
                json.loads(f.read_text(encoding="utf-8"))
                reads += 1
            except json.JSONDecodeError:
                bad += 1
            except OSError:
                pass
        if bad or reads >= 2000:
            break
    writer.communicate(timeout=120)
    assert bad == 0, f"读到 {bad} 次半截 JSON（原子写失效）"
    assert reads > 0, "没读到任何一次（用例本身无效）"


# ── S137 坏文件：备份 + 告警 + 继续 ────────────────────────

def test_s137_corrupt_file_is_quarantined_not_silently_dropped(tmp_path):
    code = (
        "import os\n"
        f"os.environ['VOD_DEVKIT_DIST_ROOT'] = {str(tmp_path)!r}\n"
        f"os.environ['VOD_DEVKIT_SRC_ROOT'] = {str(SRC)!r}\n"
        "from vod_mcp import runtime_state as rs\n"
        "rs._runtime_update({'after': 1})\n"
        "print(rs._runtime_cfg().get('after'))\n"
    )
    f = _runtime_file(tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('{"java_key": "SECRET-THAT-MUST-NOT-DISAPPEAR"', encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", code], env=_child_env(tmp_path),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
    backups = list(f.parent.glob("runtime.json.corrupt-*"))
    assert backups, "坏文件必须留备份（否则 key/账本永久丢失）"
    assert "SECRET-THAT-MUST-NOT-DISAPPEAR" in backups[0].read_text(encoding="utf-8")
    assert "备份" in r.stderr, "必须告警（静默归零就是本次修的那个缺陷）"
    assert json.loads(f.read_text(encoding="utf-8")) == {"after": 1}


def test_s137_good_file_is_not_quarantined(tmp_path):
    code = (
        "import os\n"
        f"os.environ['VOD_DEVKIT_DIST_ROOT'] = {str(tmp_path)!r}\n"
        f"os.environ['VOD_DEVKIT_SRC_ROOT'] = {str(SRC)!r}\n"
        "from vod_mcp import runtime_state as rs\n"
        "rs._runtime_update({'a': 1})\n"
        "rs._runtime_update({'b': 2})\n"
    )
    subprocess.run([sys.executable, "-c", code], env=_child_env(tmp_path),
                   check=True, timeout=60)
    f = _runtime_file(tmp_path)
    assert not list(f.parent.glob("runtime.json.corrupt-*")), "正常文件不许产生备份"
    assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1, "b": 2}

# ── S139 账本条目在并发下不丢（真实入口） ───────────────────
#
# S137 子进程写的是**不同的顶层键**（`{'k3_1': 1}`），合并在锁内发生，天然不丢。
# 真实路径是 `_ledger_append`：锁外 `_runtime_cfg()` 读整份 submissions 列表 →
# 锁内 `_save_runtime({submissions: 整份})` 覆盖，后写者盖掉先写者。实测 4 进程
# 各 25 条只剩 41 条。用例必须走真实入口，否则锁的是假安全。

def _ledger_child(tmp_path, worker: int, count: int = 25) -> str:
    return "\n".join([
        "import os",
        f"os.environ['VOD_DEVKIT_DIST_ROOT'] = {str(tmp_path)!r}",
        f"os.environ['VOD_DEVKIT_SRC_ROOT'] = {str(SRC)!r}",
        "from vod_mcp import runtime_state as rs",
        f"for i in range({count}):",
        f"    rs._ledger_append([dict(voiceId='V{worker}-' + str(i),"
        " content='x', stage='committed')])",
    ]) + "\n"


def test_s139_concurrent_ledger_appends_keep_every_entry(tmp_path):
    procs = [subprocess.Popen([sys.executable, "-c", _ledger_child(tmp_path, n)],
                              env=_child_env(tmp_path),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for n in range(4)]
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err.decode()[-500:]
    data = json.loads(_runtime_file(tmp_path).read_text(encoding="utf-8"))
    ledger = data.get("submissions") or []
    assert len(ledger) == 100, f"并发写账本丢了条目：{len(ledger)}/100（修前实测 40-53）"
