"""运行期状态：runtime.json 读写/锁、账本、草稿、会话记忆、install nonce、日志。

为什么要单独成模块（P2）：状态是"读改写 + 内存镜像"的单点，散在 tools.py 里时
两处吃亏——远程面并发覆盖（F3）与手工 `_RT[k]=v` 漏同步（F2，曾致首提必 401）。
本模块只依赖 paths 与 stdlib；需要身份（net._eff_key）时**函数内懒导入**，避免
net ↔ runtime_state 的循环。
"""
import datetime
import json
import os
import re
import shutil
import stat
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from vod_mcp import attribution as _attrib
from vod_mcp import paths


_RT_LOCK = threading.RLock()


def _runtime_path() -> Path:
    # D-token-machine-1：机器级 state（跨版本/跨宿主一份）；每次现读，
    # 长驻进程不冻结（D-state-read-1 的同一条纪律：常量会把"换了 key/搬了目录"冻住）
    return paths.runtime_json_path()


def _runtime_cfg() -> dict:
    # 路径单源：一律走 _runtime_path()（曾与 _save_runtime 双写路径，
    # 注入/重定位场景读写分叉——测试实锤的真缺陷）
    p = _runtime_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


_RT = _runtime_cfg()


def _runtime_update(update: dict, replace: bool = False) -> None:
    """更新运行期状态：落盘（事务内）→ 内存镜像。

    落盘的锁由 `_runtime_atomic` 持（嵌套持锁会让 flock 在同一文件上二次加锁而
    死锁——同一进程两个 fd 互斥）；镜像只服务本进程，用 _RT_LOCK 单独保护。
    replace=False 时按单参调用 _save_runtime：测试桩普遍是 `lambda u: ...`
    （历史签名），多传一个默认值会把所有桩打红——签名兼容性属于接口契约。
    """
    if replace:
        _save_runtime(update, replace=True)
    else:
        _save_runtime(update)
    with _RT_LOCK:
        if replace:
            _RT.clear()
        _RT.update(update)


def _lock_path() -> Path:
    """跨进程锁文件（与 runtime.json 同目录、同名前缀，便于 --clean-global 认出来）。"""
    p = _runtime_path()
    return p.with_name(p.name + ".lock")


@contextmanager
def _file_lock():
    """跨进程互斥：同一份载荷 runtime.json 被同一台机器上多个宿主的 server 进程共用。

    `_RT_LOCK` 只保护**进程内**；多进程同时"读→改→写"会互相覆盖（实测：4 进程各写
    25 次，落盘只剩 36 条；`pending.py` 那条低价值补交队列反而是原子的）。
    POSIX 用 `fcntl.flock`；没有 fcntl 的平台退化为空上下文——那里没有对等的成熟机制，
    硬造一个只会引入新故障，README 按"仅 POSIX 覆盖"标注。
    """
    try:
        import fcntl
    except ImportError:            # pragma: no cover - Windows
        yield
        return
    p = _lock_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        f = open(p, "a+", encoding="utf-8")
    except OSError:                # 锁不可用不该让写入失败（宁可有竞态也不要写不进）
        yield
        return
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def _quarantine_bad_runtime(p: Path, err: Exception) -> Path | None:
    """坏文件**先备份再继续**，绝不静默丢弃。

    为什么不选"拒绝覆盖"：那会让插件在坏文件之后完全不能提交/记账（用户看到的是
    "插件坏了"），而备份已经保住可恢复性。备份名带时间戳，告警里给绝对路径。
    """
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = p.with_name(f"{p.name}.corrupt-{ts}")
    try:
        shutil.copy2(p, dst)
    except OSError as e:
        msg = f"runtime.json 解析失败（{err}）且备份失败（{e}）——本次以空状态继续"
        _warn(msg)
        print(f"[vod-devkit] warn: {msg}", file=sys.stderr)
        return None
    msg = (f"runtime.json 解析失败（{err}）：原文件已备份到 {dst}，"
           "本次以空状态继续（可人工核对/恢复）")
    _warn(msg)
    # 这份文件里有 key 与账本：宿主必须当场看到（stdio 面的 stderr 会透给用户），
    # 只写 /tmp 日志等于没有告警。
    print(f"[vod-devkit] warn: {msg}", file=sys.stderr)
    return dst


def _read_cfg_unlocked(p: Path) -> dict:
    """锁内读（调用方已持 _RT_LOCK + 文件锁）。坏文件先备份再继续。"""
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:      # noqa: BLE001  坏文件：备份后继续
        _quarantine_bad_runtime(p, e)
        return {}


def _write_cfg_unlocked(p: Path, cfg: dict) -> None:
    """锁内原子写：tmp → chmod 0600 → os.replace。"""
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)        # 先给权限再替换，不留 0644 窗口
    except OSError:
        pass
    os.replace(tmp, p)


def _verify_perms(p: Path) -> None:
    """S1 式写后验（借 huaweicloud-devkit ensurePrivateMode 模式）：chmod 0600 并 stat
    回验——不假设 chmod 按文档工作（WSL/drvfs 会静默忽略），验的是效果不是动作；
    runtime.json 含 java_key 明文，权限失效必须告警。"""
    try:
        os.chmod(p, 0o600)
        mode = stat.S_IMODE(os.stat(p).st_mode)
        if mode != 0o600:
            _warn(f"runtime.json 权限异常（{oct(mode)}，期望 0600）——"
                  "key 可能被同机其他用户读取，请检查文件系统（WSL 挂载盘建议移回 Linux 原生盘）")
    except OSError as e:
        _warn(f"runtime.json 权限校验失败：{e}")


def _runtime_atomic(mutate) -> dict:
    """**事务式读改写**：进程内 RLock + 跨进程 flock 一起持，读 → mutate → 原子写。

    为什么必须是事务（2026-11-16 第二轮评审实测）：只给"写"上锁不够。调用方若在锁外
    `_runtime_cfg()` 读到整份 submissions、再在锁内整键覆盖，后写者会盖掉先写者——
    4 进程各 25 条账本只剩 40-53 条。凡是"读整键→改→写整键"的路径都必须走这里。

    mutate(cfg) 返回 False 表示"不改、不用落盘"（例如账本被 local_ledger=false 关闭）。
    返回最终落盘的 cfg 快照（调用方可据此更新内存镜像）。
    """
    p = _runtime_path()
    with _RT_LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _file_lock():
            cfg = _read_cfg_unlocked(p)
            if mutate(cfg) is not False:
                _write_cfg_unlocked(p, cfg)
                _verify_perms(p)
            return cfg


def _save_runtime(update: dict, replace: bool = False) -> None:
    """原子差分更新（公共 API）：把 update 合并进现有 cfg。

    内部整段持锁（进程内 + 跨进程），所以"不同顶层键"的并发更新不会互相覆盖。
    需要"读整键→改→写整键"的调用方**不要**用它（那会丢失并发新增），改走
    `_runtime_atomic(mutate)`。
    """
    def _mutate(cfg: dict) -> None:
        if replace:
            cfg.clear()
        cfg.update(update)
    _runtime_atomic(_mutate)


def _log(line: str, path: str = "/tmp/vod_mcp_server.log") -> None:
    """统一日志出口，1MB 截断轮转
    （D-key-guard-3⑤：客户机长期运行防无限增长；截断保留尾部近期日志）。"""
    try:
        p = path
        if os.path.exists(p) and os.path.getsize(p) > 1024 * 1024:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                tail = f.read()[-200 * 1024:]
            os.replace(p, p + ".old")
            with open(p, "w", encoding="utf-8") as f:
                f.write("== truncated ==\n" + tail)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
    except Exception:
        pass


def _warn(msg: str) -> None:
    """告警出口：server 日志（排障真源），失败静默——不阻断业务主链。"""
    _log(f"warn {msg}")


def _distribution() -> str:
    """分发形态位（D-key-guard-3）：install --distribution preset 写入 manifest。
    devkit=自装自管；preset=产品随 agent 分发（客户机首启重生成运行时状态）。"""
    p = paths.INSTALL_MANIFEST
    if not p.exists():
        return "devkit"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("distribution", "devkit")
    except Exception:
        return "devkit"


_RUNTIME_STATE_KEYS = ("java_key", "token_tier", "install_nonce", "submissions",
                       "meta_cache")


def _ensure_first_boot(rt_path: Path | None = None) -> dict:
    """首启标记 + 构建机残留清理（D-key-guard-3①，preset 形态兜底）。

    主防线是打包排除（分发产物不含 runtime.json）；本函数兜底打包者漏排：
    preset 形态 + runtime.json 存在但无 firstBootAt + 携带运行时状态
    （key/nonce/账本/缓存）→ 判构建机残留 → 自动清空这些状态（保留
    product/java_base 等装机配置）+ 重新生成 per-install nonce + 告警。
    处置用自动重生成而非拒绝启动：残留状态全是本机可再生数据，
    自动清零伤害半径为零，拒启会把误判放大成全功能瘫痪。
    firstBootAt 首启写入，此后不再触发（防误伤正常运行中的安装）。"""
    p = rt_path or _runtime_path()
    if rt_path is None:
        # D-token-machine-1 首启迁移：state 无 runtime 而旧版本目录有 → 复制一次
        # （保留 install_nonce/key/账本，改造当天不重领令牌、不换设备锚点）
        mig = paths.migrate_state_once()
        if mig.get("migrated"):
            _log(f"state migrated: {mig['from']} -> {_runtime_path()}")
            p = _runtime_path()
    if not p.exists():
        return {"action": "none"}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"action": "none"}
    if cfg.get("firstBootAt"):
        _warn_if_cloned(cfg, p)
        return {"action": "none"}
    residual = [k for k in _RUNTIME_STATE_KEYS if cfg.get(k)]
    import time as _t
    if _distribution() == "preset" and residual:
        # 残留清理=整体重建（合并删不掉旧键），但保留装机配置（product/java_base 等）
        _save_runtime({**{k: v for k, v in cfg.items() if k not in _RUNTIME_STATE_KEYS},
                       "firstBootAt": _t.strftime("%Y-%m-%dT%H:%M:%S")},
                      replace=True)
        _warn(f"检测到构建机残留状态（{','.join(residual)}）已自动清空重生成——"
              "分发产物应只含代码与配置，不含安装结果（D-key-guard-3①）")
        return {"action": "cleaned", "removed": residual}
    _save_runtime({"firstBootAt": _t.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"action": "stamped"}


def _uptime_seconds() -> float:
    """本机 uptime（秒）。独立函数：测试可 monkeypatch，消除对宿主机器的依赖
    （实锤：test_clone_image_detection_warns 曾硬编码 boot_age=7 天与真机
    /proc/uptime 实值比较，uptime>7 天的机器必红——环境相关测试缺陷）。"""
    return float(open("/proc/uptime").read().split()[0])


def _warn_if_cloned(cfg: dict, p: Path) -> None:
    """preset 克隆镜像检测（D-key-guard-3①延伸，仅告警不阻断）：
    firstBootAt 距今显著超过本机 uptime（>1h 容差）→ 本机状态大概率来自
    母机镜像克隆——所有克隆机共享同一 device 锚点/账本，声量与配额会收敛。
    判据：firstBootAt 的"年龄" > uptime+容差 ⇒ 首启发生在"这台机器"存在之前。"""
    import time as _t
    if _distribution() != "preset":
        return
    try:
        boot = _t.mktime(_t.strptime(cfg["firstBootAt"], "%Y-%m-%dT%H:%M:%S"))
        uptime_s = _uptime_seconds()
    except (KeyError, ValueError, OSError) as ex:
        # 收窄捕获（原 except Exception: pass 吞掉真实异常，告警失效不可见）：
        # 只吞解析类异常（缺字段/格式坏/读不到 /proc），其余如实上抛
        _log(f"clone 检测跳过（无法解析 firstBootAt/uptime）：{ex}")
        return
    if _t.time() - boot > uptime_s + 3600:
        _warn("疑似镜像克隆机：firstBootAt 早于本机 uptime——克隆分发未清 "
              "runtime.json，所有克隆机共享同一设备锚点/账本。请在镜像冻结前 "
              "uninstall 或删除 runtime.json（装机 checklist ②）")


def _install_nonce() -> str:
    """per-install 8 位 hex：runtime.json 首次生成常驻——legacy 共用 key 场景下
    source 命名空间 per-machine 化，杜绝不同用户提交同款内容被确定性
    voiceId 合并成一条（跨用户吞声量，切换补丁前置修复）。"""
    n = _RT.get("install_nonce")
    if not n:
        import uuid
        n = uuid.uuid4().hex[:8]
        # 首装 nonce 必须同步回写内存态 _RT（D-dev-nonce-sync，2026-11-09 真机实锤）：
        # _RT 仅模块导入时加载一次，_save_runtime 只落盘——不同步则同进程内每次调用
        # 生成新 nonce：领令牌（设备 A）与提交（设备 B）设备绑定校验失败，重试仍
        # 新 nonce（设备 C）再 401——全新安装首次提交必失败冒给用户（存量安装
        # runtime.json 已有 nonce 不受影响）。同步后领令牌/提交同设备，401→领令牌
        # →重试全程进程内无感。
        try:
            _runtime_update({"install_nonce": n})
        except Exception:
            _RT["install_nonce"] = n   # 落盘失败也要在进程内保持一致
    return str(n)


_SESSION_TTL = 30 * 60          # 会话内滑动记忆（D-product-ask-1）
# 作用域 TTL 单一来源：远程传输的 session_idle_timeout 必须取这个值，
# 两个独立时钟会产生「记忆还在但会话已回收」（悬挂桶泄漏）或「窗口内会话过期
# 导致同一用户被当新客」。测试锁住两者相等。
SCOPE_TTL_SEC = _SESSION_TTL


_SESSION_MEM: dict = {}         # 进程=一次宿主会话：重启即清，跨会话不继承


def _resolve_scope(client_info) -> dict:
    """统一作用域解析（D-scope-1）：单一入口，业务侧只消费 key/product/flags。

    背景：远程面 client_info.name 曾写死 "http-remote"，_session_key 因此恒等，
    导致多 agent 共用一个 server 时记忆/计数/nonce 全串味（A 说过的产品被 B 命中、
    A 追问 2 次后 B 直接被"别再问了"挡掉、相同内容 voiceId 撞车）。

    返回：
      key             隔离键；None = 读写皆禁用（降级）
      grain           'process' | 'request' | None  —— 作用域粒度
      id_source       'proc' | 'proc_home' | 'sess' | 'agent' | None —— 身份来源
      product         请求级产品（priority 高于安装绑定）
      product_prior   安装先验是否可用（共用远程进程时必须禁用，否则错归）
      degraded        是否降级
      degraded_reason 'no_session_id' | 'no_proc_id' | None —— 供诊断打点

    两条纪律（都是踩过的坑）：
      ① 区分维度必须进 key，不能只写在注释里 —— "http-remote" 与机器级 nonce
         都因为"以为能区分、其实区分不了"出过事。
      ② 不用自我声明的 name 作 key 首选：name 可重复、可被写死。进程身份由内核
         保证，不需要任何人配合。
    """
    ci = client_info or {}
    agent = str(ci.get("agent_id") or "").strip()
    prod = str(ci.get("product") or "").strip()
    remote = _is_remote_face()

    # ⓪ 兜底用的"哨兵会话"（审查 ⑤）：它是**共享**会话，不是调用方自己的会话。
    #    若照常分桶，所有裸客户端会共用一个记忆桶（从"一人一桶"退化成"大家一桶"）。
    #    这里强制降级成 key=None —— 读写皆禁，业务行为与旧实现（每请求新会话、
    #    每次 key=None）完全一致，但会话池占用从 O(请求数) 降到 O(1)。
    if ci.get("sideless"):
        return _degraded_scope("no_session_id", prod)

    # ① 请求级身份（多 agent 共用远程进程）：显式 agent 头优先于会话。
    #    2026-11-19（审查 ⑥）：头必须过格式约束——它是"分桶提示"不是身份凭证，
    #    非法值（换行/空格/中文/超长）**忽略并降级**到会话，不报错、不中断采集。
    if agent and not agent.startswith("session:") and agent_id_accepted(agent):
        return {"key": f"agent:{agent}", "grain": "request", "id_source": "agent",
                "product": prod, "product_prior": False,
                "degraded": False, "degraded_reason": None}
    # ② 会话级（标准 stateful：initialize 下发的 mcp-session-id）
    if agent.startswith("session:"):
        sid = agent[len("session:"):].strip()
        if sid:
            return {"key": f"sess:{sid}", "grain": "request", "id_source": "sess",
                    "product": prod, "product_prior": False,
                    "degraded": False, "degraded_reason": None}

    if not remote:
        # ③ 非远程面（stdio）：以**进程身份**为主，name 仅当同一进程内需要区分
        #    多个逻辑宿主时作二级后缀（既有契约里有此形态，见 test_s145_draft_*）。
        #    进程身份由内核保证，不会像 name 那样被写死成常量。
        #    注意：这里刻意**不调用** _install_nonce()（它有写盘副作用，会在
        #    "显式 key 被拒"等路径上污染 runtime.json）；直接读进程内已有值。
        home = str(os.environ.get("VOD_DEVKIT_HOME") or "").strip()
        name = str(ci.get("name") or "").strip()
        suffix = f"|{name}" if name and name != "http-remote" else ""
        try:
            pid = os.getpid()
        except Exception:                  # 理论上不会：留作兜底自检
            return _degraded_scope("no_proc_id", prod)
        base = (f"proc:@{home}" if home else f"proc:{pid}")
        return {"key": base + suffix, "grain": "process",
                "id_source": "proc_home" if home else "proc",
                "product": prod, "product_prior": True,
                "degraded": False, "degraded_reason": None}

    # ④ 远程面：
    #    ④-a 单租户（模式②：一 agent 一远程，独立进程 + 独立 VOD_DEVKIT_HOME）
    #         —— 进程私有、只有一个 agent，安装先验不会错归，可用。
    #         🔴 三个条件必须同时满足，缺一个就退回 ④-b 的禁用：
    #            ① 显式开关 VOD_SINGLE_TENANT（默认关：不明说就不放开，避免误判）；
    #            ② 有 VOD_DEVKIT_HOME —— 它是"进程/目录私有"的唯一可证证据；
    #            ③ 拿不到调用方会话标识（能拿到 sess:/agent: 说明可能多 agent 共用，
    #               那正是模式③，绝不能用安装先验）。
    #         审查 P1-1（2026-11-19）：此前 `if not remote:` 把远程面一刀切禁用，
    #         模式②因此丢掉安装先验（design.md:763 承诺"可用"），是功能回归。
    #    ④-b 多租户/未声明：读写皆禁用 + 先验禁用（多租户下必错归）
    home = str(os.environ.get("VOD_DEVKIT_HOME") or "").strip()
    single_tenant = str(os.environ.get("VOD_SINGLE_TENANT") or "").strip().lower() in ("1", "true", "yes", "on")
    if single_tenant and home and not agent:
        return {"key": f"proc:@{home}", "grain": "process", "id_source": "proc_home",
                "product": prod, "product_prior": True,
                "degraded": False, "degraded_reason": None}
    return {"key": None, "grain": None, "id_source": None,
            "product": prod, "product_prior": False,
            "degraded": True, "degraded_reason": "no_session_id"}


def _degraded_scope(reason: str, product: str = "") -> dict:
    """统一的降级作用域（读写皆禁用）。reason 区分两种情况，供诊断打点：
      no_session_id —— 远程面拿不到 mcp-session-id（标准客户端应能拿到）
      no_proc_id    —— stdio 面竟拿不到进程身份（理论上不应发生，留作兜底自检）
    """
    return {"key": None, "grain": None, "id_source": None,
            "product": product, "product_prior": False,
            "degraded": True, "degraded_reason": reason}


def _is_remote_face() -> bool:
    """当前是否远程（HTTP）面。contextvar 由传输层设置，默认 False=stdio。"""
    from vod_mcp import net as _net
    return bool(_net._SERVER_FACE.get())


def _session_key(client_info):
    """记忆作用域（Scope）：见 _resolve_scope。

    返回 None = 未知调用方（远程面无标识）→ 调用方不读也不写记忆。
    返回 str  = 隔离键（记忆/追问计数共用）。
    """
    return _resolve_scope(client_info)["key"]


# agent 头格式约束（审查 ⑥）：只接受 URL/header 安全的短标识。
# 允许字母数字与 . _ : -（≤64）；其它（换行、空格、中文、超长）一律**忽略并降级**，
# 不报错——它本来就只是"分桶提示"，不是身份凭证，为它中断一次采集不值得。
_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def agent_id_accepted(agent: str) -> bool:
    """agent 头是否可用作分桶身份。空值/非法值 → False（调用方降级到会话）。"""
    a = str(agent or "").strip()
    if not a or a.startswith("session:"):
        return False
    return bool(_AGENT_ID_RE.match(a))


def _draft_owner(client_info) -> str | None:
    """草稿归属指纹（审查 ④）：**只认会话/进程边界，永不认 `X-Vod-Agent-Id`**。

    为什么不能复用 `_session_key`：agent 头在 _resolve_scope 里**优先于**会话，
    于是带着同一个 `X-Vod-Agent-Id` 的另一条连接（另一台机器、另一个 agent）
    会得到同一个 key → 能提交别人的草稿（2026-11-19 实测 DID NOT RAISE）。
    草稿是"这一次对话里刚跟用户确认过的内容"，归属就该跟对话（会话）走，
    而不是跟一个自我声明的头走。

    两类原因由此可分（话术见 collect.commit_voices）：
      会话漂移（重连/进程重启）      → 前后 owner 都是 sess: 前缀且都无 agent 摘要 = 自己
      跨 agent 冒用（agent 头不一致）→ agent 摘要不同 / 一方 sess: 一方 proc: / 旧草稿 sess: 而对方是 agent: = 可疑
    """
    ci = client_info or {}
    sid = str(ci.get("session_id") or "").strip()
    if not sid:
        aid = str(ci.get("agent_id") or "")
        if aid.startswith("session:"):
            sid = aid[len("session:"):].strip()
    if sid:
        owner = f"sess:{sid}"
        # agent 头（通过格式约束时）是"另一个维度的声明"。带上时把摘要并进指纹：
        #   · 同会话 + 同头       → 正常（同一个对话）
        #   · 同会话 + 不同头     → 不同 agent 抢同一会话，不认
        #   · 不同会话 + 同头     → 跨连接复用头，**不得**因此变回"同类"（否则
        #     话术分档会把冒用说成"你自己重连了"，等于给出错误的排查方向）
        # 摘要进指纹还顺带保证：即便 _resolve_scope 因格式放行，草稿归属也不看它。
        aid = str(ci.get("agent_id") or "")
        if aid and not aid.startswith("session:") and agent_id_accepted(aid):
            owner += f"|agent:{aid}"
        return owner
    if _is_remote_face():
        return None                      # 远程面拿不到会话：不设 owner（与 key=None 同源降级）
    # stdio 面：进程身份 + 可选 name 后缀（与 _resolve_scope 的 ③ 分支同口径）。
    # 为什么保留 name：同一进程内编排多个逻辑宿主（test_s145_draft_* 既有契约）时，
    # name 是唯一能区分"谁暂存的草稿"的维度；但 name 是自我声明、不跨进程可靠，
    # 所以**只在 stdio 面**采用，远程面永不采信（那正是 ④ 冒用的入口）。
    home = str(os.environ.get("VOD_DEVKIT_HOME") or "").strip()
    try:
        pid = os.getpid()
    except Exception:                    # pragma: no cover - 理论不可达
        return None
    base = f"proc:@{home}" if home else f"proc:{pid}"
    name = str(ci.get("name") or "").strip()
    if name and name != "http-remote":
        base += f"|{name}"
    return base


def _memory_get(client_info) -> dict:
    import time as _t
    key = _session_key(client_info)
    if not key:
        return {}                       # 未知调用方：不读共享桶（D-scope-1 降级）
    cur = _SESSION_MEM.get(key) or {}
    if cur and _t.time() - float(cur.get("at") or 0) > _SESSION_TTL:
        return {}
    return dict(cur)


def _memory_put(client_info, **fields) -> None:
    import time as _t
    with _RT_LOCK:      # get→update→set 持锁：远程面并发请求不互相丢字段
        key = _session_key(client_info)
        if not key:
            return                      # 未知调用方：不写，避免污染他人桶（D-scope-1）
        cur = _memory_get(client_info)
        cur.update(fields)
        cur["at"] = int(_t.time())      # 滑动过期
        _SESSION_MEM[key] = cur


_ATTR_HISTORY_CAP = 10


def _remember_attribution(result: dict, client_info: dict | None = None) -> None:
    """写记忆：只接受「字面证据唯一命中」，歧义/无证据/记忆本身不写（S100）。

    覆盖时留快照（D-attrib-B 追加，评审意见采纳项）：旧条目进
    attribution_history（cap 10，带 replacedAt），事后能回答「当时为什么归
    到 A 而不是 B」——单条记忆被覆盖后判据不可追是排障黑洞。
    """
    # 会话记忆（D-product-ask-1）：只记「有证据/用户明确回答/用户说不知道」三种
    src = result.get("source")
    if result.get("product"):
        _memory_put(client_info, ask_failures=0)
    if src in ("user_input", "user_answer"):
        _memory_put(client_info, product=result.get("product"),
                    productName=result.get("productName"),
                    alias=(result.get("evidence") or [{}])[0].get("alias"))
    elif src == "host_default":
        _memory_put(client_info, not_specified=True,
                    product=result.get("product"), productName=result.get("productName"))
    mem = _attrib.remember_if_evidenced(result)
    if not mem:
        return
    with _RT_LOCK:
        prev = _RT.get("attribution_memory") or {}
        if prev and prev.get("product"):
            hist = list(_RT.get("attribution_history") or [])
            hist.append({**prev, "replacedAt": mem["at"]})
            hist = hist[-_ATTR_HISTORY_CAP:]
            _runtime_update({"attribution_history": hist})
        _runtime_update({"attribution_memory": mem})


_LEDGER_KEY = "submissions"


_LEDGER_CAP = 200


def _ledger_append(entries: list) -> None:
    """本地提交账本（层级①）：本机提交记录，供 vod_list_submitted 对账。
    cap 200 条（环形截断，防 runtime.json 膨胀）。
    实现纪律：每次从文件读改写、只动 submissions 键——不从内存 _RT
    合并（陈旧配置会整体回写，覆盖其他键，且把无关配置泄入调用方）。
    D-key-guard-3④：local_ledger=false（企业数据驻留要求）→ 账本关闭，
    vod_list_submitted 随之不可用——留痕是可选项不是义务。"""
    if not entries:
        return

    def _mutate(cfg: dict):
        if cfg.get("local_ledger") is False:
            return False          # 企业数据驻留：账本关闭，不写也不改
        ledger = (cfg.get(_LEDGER_KEY) or [])[-_LEDGER_CAP:]
        ledger.extend(entries)
        cfg[_LEDGER_KEY] = ledger[-_LEDGER_CAP:]

    _runtime_atomic(_mutate)   # 读整键 → 改 → 写整键 必须整段在锁内


_DRAFT_KEY = "drafts"


_DRAFT_CAP = 10


_DRAFT_TTL = 600  # 秒；过期 commit 拒收，草稿自动作废


def _drafts_purge(store: dict) -> dict:
    """过期草稿清除（读时惰性，无后台任务）。"""
    import time as _time
    now = _time.time()
    return {k: v for k, v in store.items()
            if v.get("expiresAt", 0) > now}


def _drafts_load() -> dict:
    """草稿库现读 + 过期惰性清除（draft/commit 单源共用，禁双边漂移）。"""
    return _drafts_purge(_runtime_cfg().get(_DRAFT_KEY) or {})


def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()
