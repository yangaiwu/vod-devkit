"""nightly E2E：官方 MCP 客户端对测试环境跑提交→账本查询回环（本机单宿主版 nightly）。

日志：/root/vod-devkit/.e2e-nightly.log（cron 每日 03:30 写入）。
数据：测试环境，voiceId 前缀 ext_mcp_、title 带 [nightly] 标记，可定期清理。
"""
import asyncio
import glob
import json
import sys
import time

sys.path.insert(0, "/root/vod-devkit")
SERVER_PY = glob.glob("/root/.hermes/tools/python-3.14.7*/bin/python3")[0]


async def main() -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    params = StdioServerParameters(
        command=SERVER_PY, args=["/root/vod-devkit/vod_mcp/server.py"],
        env={"VOD_JAVA_API_BASE": "https://vod-dev.topxtopx.com",
             "VOD_JAVA_API_KEY": "vod-external-api-key-2026",
             "VOD_PACKS": "core,collect",
             "PATH": "/usr/bin:/bin", "HOME": "/root"})
    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                names = [t.name for t in tools.tools]
                content = f"[nightly {stamp}] E2E 反馈，链路健康检查"
                res = await s.call_tool("vod_submit_voices", {
                    "voices": [{"content": content, "scene": "nightly-E2E"}],
                    "product": "codearts", "confirmed": True})
                payload = json.loads(res.content[0].text)
                lst = await s.call_tool("vod_list_submitted", {"limit": 1})
                ledger = json.loads(lst.content[0].text)
                line = (f"[{stamp}] OK tools={len(names)} accepted={payload['accepted']} "
                        f"taskIds={payload.get('taskIds')} ledger_total={ledger['total']}")
        print(line)
        return 0
    except Exception as e:
        print(f"[{stamp}] FAIL {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
