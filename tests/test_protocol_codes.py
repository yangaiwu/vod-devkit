"""ARCH-CALL-05：协议面错误码必须来自常量表，不许再裸造（2026-11-19 走查 P2）。

背景：`server.py` 手工拼 JSON-RPC 信封时把 `-32601/-32603/-32700` 写成字面量，
而 `-3260x` 是 JSON-RPC 2.0 **保留段**——写错一位就变成另一语义，且没有任何测试报警。
"""
import ast
import pathlib

from vod_mcp import protocol

SERVER = pathlib.Path(__file__).resolve().parent.parent / "src" / "vod_mcp" / "server.py"


def test_server_uses_protocol_constants_only():
    """server.py 内不得出现裸 `-32xxx` 字面量（只允许经 protocol.* 常量）。"""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
                and isinstance(node.operand, ast.Constant) \
                and isinstance(node.operand.value, int) and -32999 <= -node.operand.value <= -32000:
            bad.append((node.lineno, -node.operand.value))
    assert not bad, f"server.py 仍有裸协议码字面量：{bad}"


def test_reserved_codes_are_the_jsonrpc_ones():
    """保留段码值固定（协议契约，不可被产品语义复用）。"""
    assert protocol.PARSE_ERROR == -32700
    assert protocol.INVALID_REQUEST == -32600
    assert protocol.UNKNOWN_METHOD == -32601
    assert protocol.INVALID_PARAMS == -32602
    assert protocol.INTERNAL_ERROR == -32603


def test_protocol_version_single_source():
    """PROTOCOL_VERSION 只能有一处字面量（server_face），protocol 只做引用。"""
    assert protocol.PROTOCOL_VERSION == "2025-06-18"
    assert protocol.PROTOCOL_VERSION is not None
