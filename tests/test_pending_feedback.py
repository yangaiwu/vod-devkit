# D-pending-1 pending 反馈队列 契约锁（pytest，全纯函数+tmp_path，零外呼）：
# ①幂等键语义：条目级（content+confirmAt+source），内容级去重归引擎（注释锁）
# ②原子重写：save_entries tmp+rename，失败保留 pending
# ③flush 计划：上限 100 最早优先、30 天 expired、坏行容忍
# ④echo 标记：echoShown 承载（概率性防线口径，skill 层解释）
import datetime
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pending", ROOT / "vod_mcp" / "pending.py")
pq = importlib.util.module_from_spec(_spec)
sys.modules["pending"] = pq
_spec.loader.exec_module(pq)


# ── ① 幂等键 ──

def test_entry_key_is_entry_level():
    """同一条（content+confirmAt+source 相同）键稳定；任一分量变=新条目。
    内容级去重不归本键——两条同 content 不同 confirmAt 是两条 pending。"""
    a = pq.entry_key("导出很慢", "2026-11-09T20:00:00", "opencode")
    b = pq.entry_key("导出很慢", "2026-11-09T20:00:00", "opencode")
    c = pq.entry_key("导出很慢", "2026-11-09T20:05:00", "opencode")
    assert a == b, "同一条目重放键必须稳定"
    assert a != c, "confirmAt 不同=用户再次表达，是新条目，不得误判重复"


def test_make_entry_fields():
    e = pq.make_entry("导出很慢", ["易用性"], "2026-11-09T20:00:00", "opencode", echo_shown=True)
    assert e["status"] == "pending"
    assert e["echoShown"] is True
    assert e["tags"] == ["易用性"]
    assert len(e["idempotencyKey"]) == 40


# ── ② 原子重写 ──

def test_append_and_save_atomic(tmp_path):
    p = tmp_path / "pending-feedback.jsonl"
    pq.append_entry(p, pq.make_entry("一", [], "2026-11-09T20:00:00", "opencode"))
    pq.append_entry(p, pq.make_entry("二", [], "2026-11-09T20:01:00", "opencode"))
    assert len(pq.load_entries(p)) == 2
    # 重写剔除 done 条目（flush 后文件里只有真正待提交项）
    entries = pq.load_entries(p)
    entries[0]["status"] = "done"
    kept = [e for e in entries if e["status"] == "pending"]
    pq.save_entries(p, kept)
    assert [e["content"] for e in pq.load_entries(p)] == ["二"]
    assert not p.with_suffix(p.suffix + ".tmp").exists(), "原子 rename 后 tmp 不得残留"


def test_load_tolerates_bad_lines(tmp_path):
    p = tmp_path / "pending-feedback.jsonl"
    good = pq.make_entry("好内容", [], "2026-11-09T20:00:00", "opencode")
    p.write_text(json.dumps(good, ensure_ascii=False) + "\n{broken json\n\n", encoding="utf-8")
    entries = pq.load_entries(p)
    assert len(entries) == 1 and entries[0]["content"] == "好内容"


# ── ③ flush 计划 ──

def _entry(days_ago, content, now):
    e = pq.make_entry(content, [], (now - datetime.timedelta(days=days_ago)).isoformat(timespec="seconds"), "opencode")
    e["createdAt"] = (now - datetime.timedelta(days=days_ago)).isoformat(timespec="seconds")
    return e


def test_plan_flush_expired_and_order_and_cap():
    now = datetime.datetime(2026, 11, 9, 20, 0, 0)
    entries = [
        _entry(40, "超期条目", now),            # >30 天 → expired
        _entry(2, "甲", now),                    # pending，较早
        _entry(1, "乙", now),                    # pending，较晚
        {"content": "无时间手工行", "status": "pending"},  # 无 createdAt 不误杀
    ]
    plan = pq.plan_flush(entries, now=now)
    assert [e["content"] for e in plan["to_flush"]] == ["甲", "乙", "无时间手工行"], "最早优先"
    assert [e["content"] for e in plan["expired"]] == ["超期条目"]
    assert all(e["content"] != "超期条目" for e in plan["kept"] + plan["to_flush"])


def test_plan_flush_cap_100():
    now = datetime.datetime(2026, 11, 9, 20, 0, 0)
    entries = [_entry(1, f"c{i:03d}", now) for i in range(150)]
    plan = pq.plan_flush(entries, now=now)
    assert len(plan["to_flush"]) == 100, "单次 flush 上限"
    assert plan["to_flush"][0]["content"] == "c000" and plan["to_flush"][-1]["content"] == "c099", "最早优先"
    assert len(plan["kept"]) == 50, "超额条目保留 pending"


def test_failed_entries_must_stay_pending():
    """flush 尝试过≠已处理：失败条目保留 status=pending（flush 实现的契约，
    这里锁的是口径常量与计划函数不做状态篡改）。"""
    now = datetime.datetime(2026, 11, 9, 20, 0, 0)
    e = _entry(1, "失败条目", now)
    plan = pq.plan_flush([e], now=now)
    assert plan["to_flush"][0]["status"] == "pending", "计划函数不得改写条目状态"


# ── ④ flush 接线（源码锁） ──

def test_submit_voices_wires_flush():
    src = (ROOT / "vod_mcp" / "tools.py").read_text(encoding="utf-8")
    assert 'result["pendingFlush"] = _flush_pending(product)' in src, "两条成功路径都要接 flush"
    assert src.count('result["pendingFlush"] = _flush_pending(product)') == 2, "囤积+legacy 回落两处"
    assert "绝不回滚主提交" in src or "绝不回滚" in (ROOT / "vod_mcp" / "pending.py").read_text(encoding="utf-8"), \
        "flush 失败不得影响主提交口径在位"
