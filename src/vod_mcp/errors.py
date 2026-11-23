"""领域错误基类单一真源（ARCH-DEP-03）。

为什么从 `net` 里搬出来：`ToolError` 曾被定义在网络出口层，于是"知识披露 pack"为了
转译一个错误码不得不 `import net` —— 知识包声称"零上游调用、零依赖"，实际却依赖出口层，
既不能离线单测，也让"改 net 的异常面"影响全部 pack。现在 `net` 只做别名导出（兼容既有
`net.ToolError` 调用），真值在这里，任何模块都可以零依赖地引用。
"""


class ToolError(Exception):
    """工具层错误。`code` 必须是 JSON-RPC 合法错误码（`-32xxx` 段）。

    ARCH-ERR-03：**上游 HTTP 状态码不许进 `code`**——`429`/`500` 落在协议保留段之外，
    宿主无法按 JSON-RPC 分类；也不该让 `explain 500` 落到"未分类"。
    上游真实状态码放 `upstream_status`，供内部按码分流（如 collect 判 404）。
    """

    def __init__(self, message: str, code: int = -32000, *,
                 upstream_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.upstream_status = upstream_status
