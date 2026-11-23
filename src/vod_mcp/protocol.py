"""JSON-RPC 2.0 协议面常量（ARCH-CALL-05）。

为什么单独成模块：协议版本与保留错误码此前散在三处（stdio 面裸造信封、安装器探活、
remote 面 SDK 默认），升版本时漏改一处不会有任何测试报警，表现却是"某类客户端握手失败"。
- `PROTOCOL_VERSION` 的唯一真值仍在 `server_face`（那里有单一来源门禁锁），这里只做引用；
- 错误码段：`-32700..-32600` 是 JSON-RPC 2.0 **保留段**，语义固定，不许被产品语义复用。
"""
from vod_mcp import server_face

PROTOCOL_VERSION = server_face.PROTOCOL_VERSION

# JSON-RPC 2.0 保留错误码（不可复用给产品语义；产品段在 -320xx）
PARSE_ERROR = -32700          # 收到非法 JSON
INVALID_REQUEST = -32600      # 结构不是合法 JSON-RPC 请求
UNKNOWN_METHOD = -32601       # 方法不存在
INVALID_PARAMS = -32602       # 参数非法
INTERNAL_ERROR = -32603       # 服务端内部错误（兜底码）

# 便于门禁用例与 explain 表共用的全集
RESERVED_CODES = {
    PARSE_ERROR: "解析错误",
    INVALID_REQUEST: "请求结构不合法",
    UNKNOWN_METHOD: "未知方法",
    INVALID_PARAMS: "参数非法",
    INTERNAL_ERROR: "内部错误",
}