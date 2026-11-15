"""P2 结构护栏：拆分后 patch 面必须跟着实现走（防假绿）。

背景：tools.py 拆成 net / runtime_state / packs 三层后，历史用例里
`monkeypatch.setattr(tools, "_http", fake)` 这类打桩会**静默失效**——shim 上写个
属性，实现模块读的是自己的名字，测试照样绿但根本没拦到出口。三条锁：

  1. shim 不 re-export 私有符号（写 shim 直接 AttributeError，不允许静默无效）；
  2. packs/*.py 禁止 `from vod_mcp.net import _http`（符号导入会把引用冻结在
     导入期，patch 同样失效）——一律模块属性访问（net._http / rt._save_runtime）；
  3. patch 有效性：打桩到实现模块后，真实调用链必须命中假实现（三条代表：
     HTTP 出口、显式 key 常量、状态落盘）。
"""
import ast
import re
from pathlib import Path

from vod_mcp import net, runtime_state, tools
from vod_mcp.packs import core

ROOT = Path(__file__).resolve().parent.parent

# 拆到实现模块的私有符号：shim 上出现任何一个都视为"又开了条静默无效的打桩口"
MOVED_PRIVATE = [
    "_http", "_load_meta", "_eff_key", "JAVA_KEY", "JAVA_BASE",
    "_save_runtime", "_runtime_cfg", "_runtime_path", "_RT", "_RT_LOCK",
    "_runtime_update", "_install_nonce", "_log", "_warn", "_distribution",
    "_ledger_append", "_drafts_load", "_memory_get", "_memory_put", "_session_key",
    "_flush_pending", "_attribute_product", "_filter_tags", "_allowed_tags",
    "_require_product_or_ask", "_echo_plan", "_hoard_voice", "_voice_id",
]


def test_shim_does_not_reexport_moved_privates():
    leaked = [n for n in MOVED_PRIVATE if hasattr(tools, n)]
    assert not leaked, (
        f"tools.py shim 又导出了已迁走的私有符号 {leaked}——"
        "monkeypatch.setattr(tools, ...) 会写到 shim 上静默无效，"
        "宁可直接 AttributeError")


def test_toolerror_is_one_class():
    """`except tools.ToolError` 与 net 抛出的必须是同一个类对象。"""
    assert tools.ToolError is net.ToolError


def test_packs_use_module_attribute_access_not_symbol_imports():
    """packs/*.py 里禁止 `from vod_mcp.net import X` / `from vod_mcp import runtime_state as ...`？ 
    ——后者是模块导入（合法）；禁止的是从 net/runtime_state **导入符号**。"""
    bad = []
    for path in sorted((ROOT / "vod_mcp" / "packs").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (
                    "vod_mcp.net", "vod_mcp.runtime_state", "vod_mcp.paths"):
                names = [a.name for a in node.names]
                # 允许导入模块本身以外的常量？——不允许：常量 patch 同样是静默失效源
                bad.append(f"{path.name}:{node.lineno} from {node.module} import {names}")
    assert not bad, ("packs 里出现符号导入（patch 会静默失效，改用模块属性访问）：\n  "
                     + "\n  ".join(bad))


def test_patch_on_net_http_intercepts_real_call_chain():
    """打桩 net._http → probe_key / auth_status 必须走假实现（而不是真发请求）。

    显式钉住 JAVA_KEY：auth_status 只有「有 key」时才走主动探针分支，而 key
    来自环境/runtime.json——CI（无 runtime.json、无 env）与开发机状态不同，
    旧写法在 CI 上直接 KeyError: 'keyCheck'（v0.5.8 实锤假红）。
    """
    seen = []

    def fake(method, path, body=None, **kw):
        seen.append((method, path))
        return {"data": {"products": ["CodeArts"], "productCatalog": [{"id": 7, "name": "CodeArts"}]}}

    orig_http, orig_key = net._http, net.JAVA_KEY
    net._http = fake
    net.JAVA_KEY = "k-test"
    try:
        out = net.probe_key("k-test")
        assert out["ok"] is True, out
        assert seen and seen[0][0] == "GET", seen
        seen.clear()
        res = core.auth_status({})
        assert res["keyCheck"]["ok"] is True, res
        assert seen, "auth_status 的探针没命中假 _http（patch 面失效）"
    finally:
        net._http = orig_http
        net.JAVA_KEY = orig_key


def test_patch_on_java_key_is_seen_by_eff_key():
    """常量类打桩：net.JAVA_KEY 改了，net._eff_key() 必须读到新值。"""
    orig = net.JAVA_KEY
    net.JAVA_KEY = "k-patched"
    try:
        assert net._eff_key() == "k-patched"
    finally:
        net.JAVA_KEY = orig


def test_patch_on_save_runtime_intercepts_state_writes(tmp_path, monkeypatch):
    """状态落盘打桩：runtime_state._save_runtime 被替换后，_runtime_update 不再写盘。"""
    saved = {}
    monkeypatch.setattr(runtime_state, "_save_runtime",
                        lambda update, replace=False: saved.update(update))
    monkeypatch.setattr(runtime_state, "_runtime_path", lambda: tmp_path / "runtime.json")
    runtime_state._runtime_update({"probe_key": 1})
    assert saved.get("probe_key") == 1
    assert not (tmp_path / "runtime.json").exists(), "被打桩后不应真的落盘"

# 拆分脚本的切实风险：正则把**字符串里的普通词**也加上模块前缀。
# 实锤（2026-11-15）：F8 拆分时 "origin/main" 被改成 "origin/cli.main"，
# cmd_update 于是 `git rev-parse origin/cli.main` 永远取不到值 → 更新功能静默失效
# （installer 用例当场红，但这类污染在别的字符串里可能不会立刻暴露）。
ALIAS_TOKENS = ("cli", "common", "remote", "install", "doctor", "update", "uninstall",
                "net", "rt", "core", "collect", "knowledge")


def test_no_module_alias_leaked_into_ref_like_strings():
    """只扫"像 git ref / 路径 / 命令"的字面量（含 '/'、无空格），避免误伤
    f-string 里的真实调用表达式（那些片段里出现 core.search_products 是正常的）。"""
    bad = []
    paths = list((ROOT / "vod_mcp").rglob("*.py")) + list((ROOT / "vodkit_cli").rglob("*.py"))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            s = node.value
            if " " in s or ("/" not in s and not s.startswith("-")):
                continue
            for alias in ALIAS_TOKENS:
                if re.search(rf"(?<![\w.]){alias}\.(?!py\b)\w+", s):
                    bad.append(f"{path.relative_to(ROOT)}: {s!r}")
                    break
    assert not bad, ("字符串字面量被模块别名污染（拆分正则误伤，命令/ref 会静默失效）：\n  "
                     + "\n  ".join(bad[:10]))


def test_update_uses_origin_main_ref():
    """语义锁：cmd_update 比较的必须是 origin/main（上一条的具名实例）。"""
    src = (ROOT / "vodkit_cli" / "update.py").read_text(encoding="utf-8")
    assert '"origin/main"' in src, "cmd_update 的远端 ref 不是 origin/main"
    assert "cli.main" not in src, "origin/main 被拆分正则污染成 cli.main"
