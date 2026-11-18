"""ARCH-DEP-01：`src/vod_mcp` 内不许有循环依赖（2026-11-19 走查，含台账漏记的一条）。

现状两条环，且都靠「函数内 import」维持：

    net.py:14  from vod_mcp import runtime_state as rt        （顶层）
    runtime_state.py:438  from vod_mcp import net as _net     （函数内）
    ↓
    hermes.py:409  from vod_mcp.host_adapters import host_verify   （函数内）
    host_verify.py:50  from vod_mcp.host_adapters import hermes    （函数内）

⚠️ 台账附录 10.2 的脚本**查不出这两条环**：它用 `str(p)[4:-3].replace('/', '.')` 从相对
路径 `src/vod_mcp/x.py` 生成模块名 `od_mcp.x`，而 `ImportFrom.module` 是 `vod_mcp.x`，
任何 FromImport 边都匹配不上，产出「21 edges / 无环」。本文件按**真实文件路径**建图
（相对 import 也解析），所以能抓到；先在现状上确认它红（红=两条环都在），再去破环。

纪律：函数内 import 也算边 —— 破环靠的就是那一行，把它提层就 ImportError，这就是缺陷。
"""
import ast
import collections
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"


def _resolve(base: str, name: str, nodes: set) -> list:
    """`from <base> import <name>` → 候选文件（`<base>.py` 与 `<base>/<name>.py`）。"""
    b = base.replace(".", "/")
    cands = [f"src/{b}.py", f"src/{b}/{name}.py"] if base else [f"src/{name}.py"]
    return [c for c in cands if c in nodes]


def _import_edges() -> dict:
    """{文件: {被导入的文件}}；含函数内 import。"""
    paths = list(SRC.rglob("*.py"))
    nodes = {str(p.relative_to(SRC.parent)) for p in paths}      # src/vod_mcp/x.py
    edges = collections.defaultdict(set)
    for p in paths:
        me = str(p.relative_to(SRC.parent))
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                for a in n.names:
                    edges[me].update(_resolve(n.module, a.name, nodes))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    cand = f"src/{a.name.replace('.', '/')}.py"
                    if cand in nodes:
                        edges[me].add(cand)
    return {k: v for k, v in edges.items() if v}


def _scc(edges: dict) -> list:
    """Tarjan：返回所有强连通分量（size>1 即环）。"""
    index, low, on_stack, stack, out = {}, {}, set(), [], []
    counter = [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in edges.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))

    for v in list(edges):
        if v not in index:
            strong(v)
    return out


def test_import_graph_is_built():
    """建图本身要成立（防止用例在"零边"上假绿）。"""
    edges = _import_edges()
    assert sum(len(v) for v in edges.values()) > 100, "依赖图边数异常，建图逻辑坏了"


def test_no_cycle_in_vod_mcp():
    """`src/` 内不许有环。现状期望红（net↔runtime_state、hermes↔host_verify）。"""
    cycles = _scc(_import_edges())
    pretty = [" ↔ ".join(c) for c in cycles]
    assert not cycles, (
        "检测到循环依赖（函数内 import 也算边）：\n  " + "\n  ".join(pretty)
        + "\n破环正道：把被依赖的能力换成「由传输层注入的标志/窄接口」，不要靠函数内 import 撑着。"
    )