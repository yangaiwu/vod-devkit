"""远程面（Streamable HTTP）的服务实例：与 devkit 同构，工具面从契约派生。

三处与 devkit 对齐、一处按我们自己的边界收紧：

对齐：
- 官方 SDK 的 Streamable HTTP 传输（StreamableHTTPSessionManager，stateless +
  json_response），一个进程服务多个 agent；
- 工具面由 remoteSurface 语义门控：摘掉"写本机状态"的工具（草稿/本地账本），
  保留调引擎 API 的 submit；
- initialize 的 instructions 换一版，明说远程面不给服务器本机路径（skillRoot
  等价物），规则文本请走 vod_retrieve_skill。

收紧：
- **身份只从请求头来**。插件不代签、不落盘；缺 Authorization 时 submit 直接
  结构化拒绝（匿名令牌按设备锚点签发，服务面一进程一锚点会把配额/声量/归因
  搅在一起）。这是与 devkit 的实质差异：它的远程面不管身份，我们的写面必须管。

插件不写库：本进程对 VOD 的全部动作仍然是调用引擎 HTTP API。
"""
import asyncio
import json

from mcp import types
from mcp.server.lowlevel import Server

from vod_mcp import guardrails, packs, skills_registry, tools

REMOTE_INSTRUCTIONS = (
    "vod-devkit 采集资产与纪律（远程面）：技能 vod-feedback-collect 处理用户对"
    "本产品的不满/建议/期望（触发词：慢/报错/体验差/希望支持/提单等）。"
    "提交前必须征得用户明确同意（用户抱怨本身不构成同意）；提交回执 "
    "echo.contents 必须逐条原样转述给用户（「已收录原话：<content>」），"
    "禁止改写、概括、增删字词。product 归因由部署绑定决定，禁止询问用户。"
    "本面不提供服务器本机路径（skillRoot），规则文本用 vod_retrieve_skill 取；"
    "写本机状态的工具（草稿/本地账本）不在本面提供。"
)


def _text_result(payload: dict, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text",
                                   text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload,
        is_error=is_error)


class _RemoteServer(Server):
    """把 capabilities 对齐 devkit：{tools:{listChanged:true}}。

    Python SDK 的默认 NotificationOptions 给 listChanged=false；devkit 的
    remote test 明确断言 {tools: {listChanged: true}}。工具面由 pack 门控且
    本面 stateless，listChanged 只是信息性声明，但既然参照物声明了 true，就照它。
    """

    def create_initialization_options(self, *args, **kwargs):  # noqa: D401
        from mcp.server.lowlevel.server import NotificationOptions
        kwargs.setdefault("notification_options", NotificationOptions(tools_changed=True))
        return super().create_initialization_options(*args, **kwargs)


def build_server(remote: bool = True) -> Server:
    version = tools.load_contract()["version"]

    async def on_list_tools(ctx, params):
        specs = tools.tool_specs(packs.enabled_tools(remote=remote))
        return types.ListToolsResult(tools=[
            types.Tool(name=s["name"], description=s["description"],
                       input_schema=s["inputSchema"]) for s in specs])

    async def on_call_tool(ctx, params):
        name = params.name
        args = params.arguments or {}
        if remote and name in packs.REMOTE_WITHHELD:
            return _text_result({
                "error": f"[remote] {name} 不在服务面提供",
                "reason": ("该工具写本机状态（草稿/本地账本），远程面没有「本机」概念。"
                           "跨机对账请走引擎端点；两段式请改用 stdio 形态。"),
            }, is_error=True)
        verdict, msg, code = guardrails.check(name, args)
        if verdict != "allow":
            return _text_result({"error": msg, "code": code}, is_error=True)
        client_info = {"name": "http-remote", "version": "1", "transport": "http"}
        try:
            out = await asyncio.to_thread(tools.dispatch, name, args, client_info)
        except tools.ToolError as e:
            return _text_result({"error": str(e), "code": e.code}, is_error=True)
        if remote and name == "vod_list_skills":
            out.pop("skillsDir", None)  # 服务面不发布本机目录
        return _text_result(out)

    return _RemoteServer(
        name="vod-devkit",
        version=version,
        instructions=REMOTE_INSTRUCTIONS if remote else None,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


__all__ = ["build_server", "REMOTE_INSTRUCTIONS", "skills_registry"]