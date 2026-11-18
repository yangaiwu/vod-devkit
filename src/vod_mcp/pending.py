#!/usr/bin/env python3
"""D-pending-1 无通道场景 pending 反馈队列（2026-11-09，方案 A 四条执行细节定稿）。

背景：宿主 VOD 插件未安装时，vod-feedback-collect skill 兜底把「用户已确认
意愿的反馈」落盘为 pending，等插件/通道恢复后由 submit_voices 顺手 flush。
此前「暂存」只存在于会话输出（全盘 grep 零落盘实锤），会话结束=有记录的丢失。

四条定稿口径：
1. 幂等键 = sha1(content + confirmAt + source)：**条目级去重**（同一条 flush
   两次可识别）；**内容级去重由引擎 uk_voice_id 负责**（voiceId=f(source,
   content,nonce)，同内容重提=skipped）——两 层分工，禁止混用。
2. flush 清理 = 重写 + 原子 rename（tmp+os.replace）：文件里永远只有真正
   待提交的条目；失败的条目保留 status=pending，不因尝试过就标已处理。
   flush 同步执行但失败只记日志、不回滚主提交（文件个位数行，毫秒级；
   异步留作扩展点，当前规模不值得引入并发写竞态）。
3. echo 两场景（skill 层口径，本模块只承载 echoShown 标记）：能拿到用户
   输入原文 → 落盘前比对不一致以原文为准；拿不到 → echoShown=true，
   承认是概率性防线非确定性闸非安全边界。
4. 生命周期：createdAt 超过 EXPIRE_DAYS(30) 的条目 flush 时标记 expired
   并从文件剔除（不搞定时任务）；单次 flush 上限 CAP=100 条（按 createdAt
   最早优先），文件过大是已知扩展点。

双通道消息分离：用户侧只见「已暂存，恢复后自动补交」，路径/profile/
幂等键/flush 结果全部只进日志。
"""
import datetime
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any

PENDING_DIRNAME = ".vod-devkit"
PENDING_FILENAME = "pending-feedback.jsonl"
CAP = 100
EXPIRE_DAYS = 30
STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_EXPIRED = "expired"


def _warn(msg: str) -> None:
    """权限收紧失败等非致命告警：走 server 日志，同时 stderr 兜底一次。

    不能只写日志——日志出口自己可能正是坏的（ARCH-ERR-04 的第 1 条），
    而权限窗口打开是用户该当场知道的安全事件。
    """
    try:
        from vod_mcp import runtime_state as _rt
        _rt._log(f"warn pending: {msg}")
    except Exception:      # noqa: BLE001  日志出口失败不许影响主链
        pass
    print(f"[vod-devkit] warn: {msg}", file=sys.stderr)


def _ensure_private(p: Path) -> None:
    """把文件权限收紧到 0600（**只收紧、不放宽**），验效果不验动作。

    ARCH-CFG-01（2026-11-19 走查 P0）：本文件存的是**用户原话全文**，同目录的
    runtime.json（含 key）早已是 0600，而它此前按 umask 落到 0644 —— 同机其他用户可读。
    口径与 `runtime_state._verify_perms` 一致：chmod 后 stat 回验，WSL/drvfs 会静默
    忽略 chmod，那条路只告警不阻断（不许因为收紧不了就让采集失败）。
    """
    try:
        cur = stat.S_IMODE(os.stat(p).st_mode)
    except OSError:
        return
    if cur & 0o077 == 0:
        return                          # 已经是私有的（0600/0400…），不动
    try:
        os.chmod(p, 0o600)
    except OSError as e:
        _warn(f"pending 文件权限收紧失败（{e}）：{p} 可能被同机其他用户读取")
        return
    # 验效果不验动作：chmod 立即返回不代表内核/文件系统真改了（WSL/drvfs 会静默无效，
    # 部分网络盘是异步生效），回读要留一点余量。
    after = 0
    for _ in range(3):
        try:
            after = stat.S_IMODE(os.stat(p).st_mode)
        except OSError:
            return
        if after & 0o077 == 0:
            return
        time.sleep(0.01)
    _warn(f"pending 文件权限收紧未生效（{oct(after)}，期望 0600）：{p}"
          "——WSL/drvfs 会忽略 chmod，建议移回 Linux 原生盘；其中是用户原话")


def default_path() -> Path:
    return Path(os.path.expanduser("~")) / PENDING_DIRNAME / PENDING_FILENAME


def entry_key(content: str, confirm_at: str, source: str) -> str:
    """条目级幂等键（内容级去重由引擎 uk_voice_id 负责，见模块 docstring）。"""
    return hashlib.sha1(
        (str(content) + "\x00" + str(confirm_at) + "\x00" + str(source)).encode("utf-8")
    ).hexdigest()


def make_entry(content: str, tags: list | None, confirm_at: str, source: str,
               echo_shown: bool = False, original_lines: list | None = None) -> dict:
    now = datetime.datetime.now().isoformat(timespec="seconds")
    return {
        "idempotencyKey": entry_key(content, confirm_at, source),
        "content": str(content),
        "tags": list(tags or []),
        "confirmAt": str(confirm_at),
        "createdAt": now,
        "source": str(source),
        "echoShown": bool(echo_shown),
        "status": STATUS_PENDING,
        **({"originalLines": [str(x) for x in original_lines]}
           if original_lines else {}),
    }


def canonical_content(entry: dict) -> str:
    """权威 content：带 originalLines 的条目以分行原文 `\n` 拼接为真源
    （S73 判定例的技术锁——模型拼接时新增的标点/连接词在此被机械剥除，
    实锤：模型把两行无标点原话拼成「差劲。使用…不流畅。」）。无
    originalLines 的条目回落 entry 自身 content（行为不变）。"""
    lines = entry.get("originalLines")
    if isinstance(lines, list) and lines:
        return "\n".join(str(x) for x in lines)
    return str(entry.get("content", ""))


def load_entries(path: Path) -> list[dict]:
    """读全量（坏行容忍跳过——手工写入/中断不炸 flush）。"""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except (ValueError, TypeError):
            continue
    return out


def append_entry(path: Path, entry: dict) -> None:
    """追加一行（原子性由「单行一次 write+flush」保证；坏行由 load 容忍）。

    权限：ARCH-CFG-01 —— 新建时按 0600 创建（不是 0644 窗口后再 chmod），
    已有文件在追加后收紧（只收紧不放宽；历史 0644 文件在下次写入时被纠正）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    fd = os.open(path, flags, 0o600)          # mode 只在新建时生效，不覆盖已有权限
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    finally:
        _ensure_private(path)


def save_entries(path: Path, entries: list[dict]) -> None:
    """重写 + 原子 rename（D-pending-1 口径 2：tmp + os.replace）。

    权限与 fsync/软链/只读保护一律复用 `paths.atomic_write_text`（ARCH-CFG-03 单源）。
    """
    from vod_mcp import paths as _paths
    body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    try:
        _paths.atomic_write_text(path, body, mode=0o600)
    except PermissionError:
        raise                            # 用户 chmod 444 = 要保护，照旧拒绝（S180 语义）
    except OSError as e:
        # 软链指向的目标不可写等：降级为"直接写 + 收紧权限"，不许把 pending 队列写死
        _warn(f"pending 原子写失败（{e}），降级直写：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
    finally:
        _ensure_private(path)


def plan_flush(entries: list[dict], now: datetime.datetime | None = None,
               cap: int = CAP, expire_days: int = EXPIRE_DAYS) -> dict[str, Any]:
    """flush 计划（纯函数）：to_flush（pending、未过期、最早优先、上限 cap）、
    expired（超期条目，调用方剔除+告知）、kept（留在文件里的其余条目）。"""
    now = now or datetime.datetime.now()
    deadline = now - datetime.timedelta(days=expire_days)
    pending, expired = [], []
    for e in entries:
        created = str(e.get("createdAt", ""))[:19]
        try:
            created_dt = datetime.datetime.fromisoformat(created)
        except ValueError:
            created_dt = now  # 无 createdAt 的手工行不误杀
        if e.get("status") == STATUS_PENDING and created_dt < deadline:
            expired.append(e)
        elif e.get("status") == STATUS_PENDING:
            pending.append(e)
    pending.sort(key=lambda e: str(e.get("createdAt", "")) or "9999-12-31T23:59:59")
    return {"to_flush": pending[:cap], "expired": expired,
            "kept": [e for e in pending[cap:]]}
