"""远程面（Streamable HTTP）的服务实例：与 devkit 同构，工具面从契约派生。

三处与 devkit 对齐、一处按我们自己的边界收紧：

对齐：
- 官方 SDK 的 Streamable HTTP 传输（StreamableHTTPSessionManager，stateless +
  json_response），一个进程服务多个 agent；
- 工具面由 remoteSurface 语义门控：摘掉"写本机状态"的工具（草稿/本地账本），
  保留调引擎 API 的 submit；
- initialize 的 instructions 换一版，明说远程面不给服务器本机路径（skillRoot
  等价物），规则文本请走 vod_retrieve_skill。

收紧（2026-11-16 D-token-machine-1 修订）：
- **身份优先取请求头**（Authorization: Bearer ***，逐请求、不进 env、不落盘）。
- 没有 Bearer 时与本地同链：领/复用**机器级匿名令牌**（同机独立部署的默认形态）。
  多租户若需按调用方隔离，各调用方自带 Bearer；匿名档就是"整机一份"的低信任档。

插件不写库：本进程对 VOD 的全部动作仍然是调用引擎 HTTP API。
"""
import asyncio
import json

from mcp import types
from mcp.server.lowlevel import Server

from vod_mcp import guardrails, instructions, packs, skills_registry, tools
from vod_mcp import runtime_state as rt

# ARCH-CALL-02：采集纪律的唯一真值在 instructions.COLLECT_DISCIPLINE，
# 本面只拼接远程形态尾句。曾经这里与 server.py 各写一份近乎逐字重复的文本。
REMOTE_INSTRUCTIONS = instructions.remote_instructions()


MCP_SESSION_HEADER = "mcp-session-id"
# 内部标记头：兜底补的"哨兵会话"专属。客户端不会发它（服务端内部自己加），
# 作用是让业务侧知道"这个 session 不是你的，别拿它分桶"（审查 ⑤）。
SIDELESS_MARK_HEADER = "x-vod-sideless"


def _req_scope(ctx, remote: bool = True) -> dict:
    """从当前请求取作用域信息（D-scope-1）。

    MCP 标准 stateful 传输下，服务端在 initialize 响应头下发 mcp-session-id，
    客户端后续请求自动回传（SDK: streamable_http.py:154）。据此把同一会话的
    记忆/追问计数/nonce 收拢到一个作用域，不同会话互不影响。

    降级：拿不到 session（极端客户端不回传 / stdio 面）→ agent_id 为空，
    runtime_state._resolve_scope 会给出 key=None，即"不写记忆、不持久计数"。
    宁可多问用户一次，也不把 A 的归因写进 B 的桶。

    可选增强：客户端若显式声明 X-Vod-Agent-Id / X-Vod-Product（同一 agent
    跨会话共享记忆时用），优先采用 —— 但这不是接入前提。
    """
    h = {}
    req = getattr(ctx, "request", None)
    if req is not None:
        raw = getattr(req, "headers", None) or {}
        try:
            h = {str(k).lower(): str(v) for k, v in dict(raw).items()}
        except Exception:      # 头部实现对非映射类型应宽松：取不到就降级
            h = {}
    sid = h.get(MCP_SESSION_HEADER, "").strip()
    aid = h.get("x-vod-agent-id", "").strip()
    prod = h.get("x-vod-product", "").strip()
    # 审查 ⑥：非法 agent 头忽略并降级（与 runtime_state._resolve_scope 同一判据）。
    # 头只是分桶提示：换行/空格/超长/中文都会污染 key（日志伪造、桶名失控），
    # 且它不是认证凭证，没必要为一个格式错误中断整次采集。
    if aid and not rt.agent_id_accepted(aid):
        aid = ""
    # 审查 ⑤：兜底补的哨兵会话是**共享**会话，不是调用方自己的会话。
    # 若不标记，_resolve_scope 会给出 sess:<哨兵> → 所有裸客户端共用一个记忆桶
    # （从"一人一桶"退化成"大家一桶"，比现状更坏）。标记后强制 key=None。
    sideless = bool(h.get(SIDELESS_MARK_HEADER, "").strip())
    if sideless:
        sid = ""
    return {
        "name": "http-remote",
        "version": "1",
        "transport": "http" if remote else "stdio",
        # 作用域键：显式 agent 标识优先，其次会话 id，都没有则为空（降级）
        "agent_id": aid or (f"session:{sid}" if sid else ""),
        "product": prod,
        "session_id": sid,
        "sideless": sideless,
    }


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


def verify_servable_skills() -> None:
    """远程面构造期自校验（对齐 devkit 的 verifySkillTree）。

    动机：list_skills 是注册表驱动的——如果技能文件缺失/被删，工具仍会宣传一堆
    retrieve_skill 取不到的名字，调用方只能反复失败。远程面是无鉴权的长驻服务，
    这种"宣传了但给不出"的状态必须在构造期就拒绝，而不是每个用户踩一次。
    """
    from vod_mcp import skills_registry as sr
    if not sr.SKILLS_ROOT.is_dir():
        raise RuntimeError(
            f"远程面拒绝启动/构造：技能树不存在 {sr.SKILLS_ROOT}"
            "——list_skills/retrieve_skill 会整体失效（重跑 install 重建载荷）")
    dirs = sr._skill_dirs()
    if not dirs:
        raise RuntimeError(
            f"远程面拒绝启动/构造：{sr.SKILLS_ROOT} 下没有任何目录型技能（缺 SKILL.md）"
            "——远程面不许在没有规则文本的情况下对外服务")
    broken = [d.name for d in dirs if not (d / "SKILL.md").is_file()]
    if broken:
        raise RuntimeError("远程面拒绝启动/构造：技能文件缺失 "
                           + "、".join(sorted(broken)) + "（重跑 install 重建载荷）")


def build_server(remote: bool = True) -> Server:
    if remote:
        verify_servable_skills()
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
        # D-scope-1：从标准会话头取作用域键。
        # MCP 标准 stateful 传输由服务端在 initialize 下发 mcp-session-id，客户端
        # 后续请求自动回传（SDK streamable_http.py:154）。拿不到时降级为无作用域
        # （不写记忆、不持久计数），绝不共用同一个桶 —— "错归比不归更糟"。
        client_info = _req_scope(ctx, remote=remote)
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