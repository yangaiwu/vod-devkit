"""S154：错误码解释表与 raise 点一致（2026-11-16 通读漏面实锤）。

背景：`explain` 面长期与代码分叉——`-32011` 被说成"产品不在名录里"（真实语义是草稿/审批
令牌不符），`-32012` / `-32014` / `-32015` 在代码里 raise 却"未收录"。上一轮把错误码清单
改成 -32010/11/12/14，这张表没跟上，于是文档与命令两套说法。

门禁口径：**代码里出现的 `code=-320XX` ⊆ explain 表**，且 explain 必须 known；
另外锁死 -32011 的语义（不许再被写成产品名录）。
"""
import re
from pathlib import Path

import pytest

from vod_mcp import diagnose

SRC = Path(__file__).resolve().parent.parent / "src" / "vod_mcp"


def _raised_codes() -> set:
    """代码里真实 raise / 抛出的错误码（`ToolError(..., code=-320XX)`）。"""
    codes = set()
    for f in SRC.rglob("*.py"):
        if f.name == "diagnose.py":
            continue                    # 解释表本身不是 raise 点
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"code\s*=\s*(-320\d\d)", text):
            codes.add(m.group(1))
    return codes


# ARCH-ERR-03（2026-11-19 走查 P1）：旧门禁只扫 `code=-320\d\d` 字面量，于是
# `code=e.code`（上游状态码透传）**永远不进扫描面**——这正是本条缺陷能在绿灯下活下来的原因。
# 新口径用 AST 而不是正则：只认 `ToolError(...)` 调用的 `code=` 关键字实参，
# 正则会把 `if code == 404:` / `exitcode=0` 这类无关文本全抓进来（实测 44 条噪音）。
_ERR_TYPE = {"ToolError", "PackRefused"}
_ALLOWED_CODE_EXPRS = (
    re.compile(r"^-32\d{2,3}$"),           # 字面量（-320xx 与 -326xx 段）
    re.compile(r"^_http_error_code\("),    # 上游状态码映射函数（net._http_error_code）
    re.compile(r"^_[A-Z_]+_CODE$"),        # 模块内具名常量（如 _UNRESOLVED_CODE）
)


def _bad_code_assignments() -> list[tuple[str, int, str]]:
    """所有「错误对象构造时 code=」的实参，若有既非字面量也非白名单的名字 → 视为违规。

    白名单里的 `e.code` 只对**同类错误转译**放行（`SkillError` → `ToolError`，两者码域
    都在 -32xxx）。上游 `HTTPError.code` 是 HTTP 状态码，**不在**放行之列——那正是本条缺陷。
    """
    import ast

    _TRANSLATED = {"SkillError", "PolicyRefused"}   # 码域同属 -32xxx，转译不改语义

    bad = []
    for f in SRC.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name not in _ERR_TYPE:
                continue
            for kw in node.keywords:
                if kw.arg != "code":
                    continue
                expr = ast.unparse(kw.value).strip()
                if any(p.search(expr) for p in _ALLOWED_CODE_EXPRS):
                    continue
                # `code=e.code` 转译：只有当 except 子句捕获的是同类错误才放行
                if expr == "e.code" and _caught_same_domain(tree, kw.value.lineno, _TRANSLATED):
                    continue
                bad.append((str(f.relative_to(SRC)), kw.value.lineno, expr))
    return bad


def _caught_same_domain(tree, lineno: int, allowed: set) -> bool:
    """该行所在 `except <T> as e:` 的 T 是否在 allowed 里（码域同属 -32xxx）。"""
    import ast

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.lineno > lineno:
            continue
        body_start = node.body[0].lineno if node.body else node.lineno
        body_end = max((n.lineno for n in ast.walk(node) if hasattr(n, "lineno")), default=body_start)
        if not (body_start <= lineno <= body_end):
            continue
        t = node.type
        name = getattr(t, "id", None) or getattr(t, "attr", None)
        if name in allowed:
            return True
    return False


def test_s154_every_raised_code_is_explained():
    codes = _raised_codes()
    assert codes, "扫描面失效（一个 raise 点都没扫到）"
    missing = []
    for c in sorted(codes):
        got = diagnose.explain(c)
        if not got["known"] or not got["cause"]:
            missing.append((c, got["cause"]))
    assert not missing, f"代码里 raise 了但 explain 未收录/无原因：{missing}"


def test_s154_known_codes_are_self_consistent():
    for c in ("-32010", "-32011", "-32012", "-32014", "-32015"):
        got = diagnose.explain(c)
        assert got["known"], f"{c} 未收录"
        assert got["layer"] and got["cause"] and got["action"], f"{c} 三要素不全：{got}"


def test_s154_32011_is_draft_token_mismatch_not_catalog():
    got = diagnose.explain("-32011")
    assert "草稿" in got["cause"] or "令牌" in got["cause"], got
    assert "名录" not in got["cause"], f"-32011 又被写成产品名录：{got}"

def test_s167_http_429_is_explained():
    """S167：引擎 `POST /external/voices` 的 429 要能解释成「重试」而不是「插件/配置坏了」。

    背景（引擎 dev 1d4fba8d，2026-11-17 核对）：voiceId 取号改序列表原子分配后，极端异常
    （序列行写不进去、并发删行）抛 VoiceIdExhaustedException → Controller 回 429
    「提交排队繁忙，请稍后再试」，明确不造假号。插件 `_http` 对非 401 透传
    `上游返回 429: <detail>`。
    """
    msg = "上游返回 429: 提交排队繁忙，请稍后再试"
    got = diagnose.explain(msg)
    assert got["known"], got
    assert "重试" in got["action"], got
    assert "VOD_JAVA" not in got["action"], "429 不许被说成本机配置问题（会把排查引向错误方向）"


# ── ARCH-ERR-03：上游状态码不许进 JSON-RPC code 域 ──────────────────────────
def test_all_error_codes_come_from_table():
    """源码内不许出现「变量原样透传」的 `code=`（除 -32xx 字面量与 _http_error_code）。"""
    bad = _bad_code_assignments()
    assert not bad, f"有 code= 赋值没溯源到常量表/映射函数：{bad}"


def test_http_status_never_leaks_into_code():
    """上游 4xx/5xx 必须映射进 -32xx 段，不许 429/500 直接当 code。"""
    from vod_mcp import net
    for status in (400, 403, 404, 429, 500, 502, 503):
        code = net._http_error_code(status)
        assert -32768 <= code <= -32000, f"HTTP {status} -> {code} 落在 JSON-RPC 合法码之外"
        assert code != status
        assert diagnose.explain(str(code))["known"], f"映射出的 {code}（HTTP {status}）未收录进 explain"


def test_http_error_carries_upstream_status_for_internal_branching():
    """code 归一到 -32xx，原始状态码走 upstream_status（collect 判 404 靠它）。"""
    import http.server
    import threading

    from vod_mcp import net

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D102
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"message":"busy"}')

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(net.ToolError) as ei:
            net._http("POST", "/x", {}, base=f"http://127.0.0.1:{srv.server_address[1]}", key="k")
    finally:
        srv.shutdown()
    err = ei.value
    assert err.code == -32018, err.code
    assert err.upstream_status == 429, err.upstream_status
    # 文案里仍保留原始状态码，便于人读排障
    assert "429" in str(err)


def test_layer_is_stable_per_code():
    """ARCH-ERR-06 验收：对每个已知码，文案换了（同义词/顺序颠倒）层不变。

    历史缺陷：`远程面|探活|不可达|401` 在 RULES 里排在 `-32010|产品` 之前，
    于是"产品未命中且探活失败 -32010"会被判成「网络」，只提产品时又判「配置」。
    """
    from vod_mcp import diagnose

    codes = {k: v for k, v in diagnose._EXPLAIN_EXTRA.items() if k.startswith("-32")}
    assert codes, "码表为空，用例失去意义"
    for code, (layer, _cause, _action) in codes.items():
        variants = [
            f"远程面探活失败，工具返回 {code}（网络看起来不可达）",
            f"{code}: 业务侧直接给出的错误码，没有其它关键词",
            f"上游 401 与产品无关，纯粹是 {code} 这个码",
        ]
        got = {diagnose.classify(v)[0] for v in variants}
        assert got == {layer}, f"{code} 归层随文案漂移：{got} ≠ {layer}"


def test_explain_and_classify_agree_on_code():
    """explain(text) 与 classify(text) 对同一码必须给同一层（消除双轨）。"""
    from vod_mcp import diagnose

    for code in [k for k in diagnose._EXPLAIN_EXTRA if k.startswith("-32")]:
        text = f"任意措辞 {code} 尾巴"
        assert diagnose.explain(text)["layer"] == diagnose.classify(text)[0]


def test_group_never_keyerrors_on_unknown_layers():
    """码表用到 LAYERS 之外的层（认证/传输/引擎/内部/上游）时，报告分组不得 KeyError。"""
    from vod_mcp import diagnose

    msgs = [f"某错误 {code}" for code in diagnose._EXPLAIN_EXTRA if code.startswith("-32")]
    grouped = diagnose.group(msgs)
    total = sum(len(v) for v in grouped.values())
    assert total == len(msgs)
    diagnose.render_problems(msgs)          # 渲染路径同样不许炸
