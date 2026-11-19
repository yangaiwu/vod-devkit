"""JSON-RPC 保留段错误码必须可解释（fix-list 附 3 / 台账 ARCH-ERR-06）。

**缺陷**：`diagnose.explain()` 只覆盖 `-320xx` 业务段，`-32600/-32601/-32602/-32603`
与 `-32700` 五条 JSON-RPC 保留码全部 `known=False`。这五条**全都会真实抛出**：

| 码 | 含义 | 真实 raise 点 |
|---|---|---|
| -32600 | Invalid Request | transport_remote.py 请求体不合法 |
| -32601 | Method not found | tools.py:77 未知工具 / server.py:98 未知方法 |
| -32602 | Invalid params | collect.py 参数校验 4 处 / core.py:112,121 / skills_registry.py:119,123 |
| -32603 | Internal error | **主循环兜底码**（server.py:193）——用户最可能拿它来问 |
| -32700 | Parse error | server.py:175 / transport_remote.py:571,578 |

最糟的是 `-32603`：它是内部错误兜底，用户最可能来问"这什么意思"，
偏偏答不出 ⇒ 只能拿到 `layer=未分类`。仓库既有 `-32013` 废除法码必须保持
`known=False`（它是策略被推翻的结果，不是空位），本用例同时锁住这条反向约束。
"""
import pytest

from vod_mcp import diagnose

RESERVED_CODES = {
    "-32600": "配置",   # 请求体结构不合法 → 客户端拼包/配置面
    "-32601": "配置",   # 未知方法/工具名 → 配置或工具面
    "-32602": "配置",   # 参数非法 → 配置面
    "-32603": "内部",   # 插件自身异常（主循环兜底）
    "-32700": "配置",   # JSON 解析失败 → 客户端拼包
}


@pytest.mark.parametrize("code,layer", sorted(RESERVED_CODES.items()))
def test_reserved_codes_are_explained(code, layer):
    got = diagnose.explain(code)
    assert got["known"], (
        f"{code}（JSON-RPC 保留码）未收录 explain —— 它会真实抛出，"
        "用户拿它来问只会得到「未分类」")
    assert got["cause"] and got["action"], got
    assert got["layer"] == layer, f"{code} 归层应为 {layer}，实际 {got['layer']}"


def test_internal_error_code_is_actionable():
    """-32603 是主循环兜底码：必须给出「看日志/重试」这类可执行动作。"""
    got = diagnose.explain("-32603")
    text = got["cause"] + got["action"]
    assert "日志" in text or "log" in text.lower(), (
        f"-32603 的解释必须指向日志（否则用户无从下手）：{text}")


def test_abolished_32013_stays_unknown():
    """-32013 是**已废除的归因拦截码**：必须保持 known=False，不得被误收录。

    它"零 raise 点"不是空位，是策略被推翻后的结果（decisions.md:87、design.md:140、
    safety-model.md:33、proposal.md:135/168 四处记载）。收录它等于复活一个废义。
    """
    got = diagnose.explain("-32013")
    assert not got["known"], f"-32013 是废除法码，不许被 explain 当作已知码：{got}"