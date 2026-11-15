"""运行期状态：runtime.json 读写/锁、账本、草稿、会话记忆、install nonce、日志。

为什么要单独成模块（P2）：状态是"读改写 + 内存镜像"的单点，散在 tools.py 里时
两处吃亏——远程面并发覆盖（F3）与手工 `_RT[k]=v` 漏同步（F2，曾致首提必 401）。
本模块只依赖 paths 与 stdlib；需要身份（net._eff_key）时**函数内懒导入**，避免
net ↔ runtime_state 的循环。
"""
import json
import os
import stat
import threading
from pathlib import Path

from vod_mcp import attribution as _attrib
from vod_mcp import paths


_RT_LOCK = threading.RLock()


def _runtime_path() -> Path:
    return paths.RUNTIME_JSON


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
    """原子更新运行期状态：落盘 → 镜像（同锁内）。

    replace=False 时按单参调用 _save_runtime：测试桩普遍是 `lambda u: ...`
    （历史签名），多传一个默认值会把所有桩打红——签名兼容性属于接口契约。
    """
    with _RT_LOCK:
        if replace:
            _save_runtime(update, replace=True)
        else:
            _save_runtime(update)
        if replace:
            _RT.clear()
        _RT.update(update)


def _save_runtime(update: dict, replace: bool = False) -> None:
    """低层落盘（唯一写文件处）。整段读改写必须持 _RT_LOCK——锁可重入，
    上层 _runtime_update/_ledger_append/draft 复合操作嵌套调用安全。"""
    with _RT_LOCK:
        p = _runtime_path()
        cfg = {}
        if p.exists() and not replace:
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        cfg.update(update)
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    # S1 式写后验（借 huaweicloud-devkit ensurePrivateMode 模式）：写完 chmod 0600
    # 并 stat 回验——不假设 chmod 按文档工作（WSL/drvfs 会静默忽略 chmod），
    # 验的是效果不是动作；runtime.json 含 java_key 明文，权限失效必须告警
    try:
        os.chmod(p, 0o600)
        mode = stat.S_IMODE(os.stat(p).st_mode)
        if mode != 0o600:
            _warn(f"runtime.json 权限异常（{oct(mode)}，期望 0600）——"
                  "key 可能被同机其他用户读取，请检查文件系统（WSL 挂载盘建议移回 Linux 原生盘）")
    except OSError as e:
        _warn(f"runtime.json 权限校验失败：{e}")


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


_SESSION_MEM: dict = {}         # 进程=一次宿主会话：重启即清，跨会话不继承


def _session_key(client_info) -> str:
    """记忆作用域（Scope）：宿主 + 身份。

    进程内即一次 stdio 会话；远程面是多租户共享进程，所以身份也必须进 key，
    否则 A 用户的"不知道→CodeArts"会串到 B 用户。
    """
    ci = client_info or {}
    import hashlib
    from vod_mcp import net as _net   # 懒导入：net 依赖本模块，导入期成环
    ident = _net._eff_key() or ""
    ident_hash = hashlib.sha256(ident.encode()).hexdigest()[:8] if ident else _install_nonce()
    return f"{ci.get('name') or 'unknown'}|{ident_hash}"


def _memory_get(client_info) -> dict:
    import time as _t
    cur = _SESSION_MEM.get(_session_key(client_info)) or {}
    if cur and _t.time() - float(cur.get("at") or 0) > _SESSION_TTL:
        return {}
    return dict(cur)


def _memory_put(client_info, **fields) -> None:
    import time as _t
    with _RT_LOCK:      # get→update→set 持锁：远程面并发请求不互相丢字段
        key = _session_key(client_info)
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
    with _RT_LOCK:   # 读改写整段持锁：远程面并发提交不再互相覆盖账本
        fresh = _runtime_cfg()
        if fresh.get("local_ledger") is False:
            return
        ledger = (fresh.get(_LEDGER_KEY) or [])[-_LEDGER_CAP:]
        ledger.extend(entries)
        _save_runtime({_LEDGER_KEY: ledger[-_LEDGER_CAP:]})


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
