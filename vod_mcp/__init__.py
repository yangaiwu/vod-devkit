"""vod-devkit：VOD 分析能力的 MCP 插件薄壳。

铁律（见 docs/design.md）：
1. 只允许经 HTTP 调 workflow/api.py，禁止 import 引擎内部模块
2. 外部无 DB 直连路径（护栏 deny 兜底）
3. 任务 ID 是唯一对账主键，写类工具返回一律携带
"""
__version__ = "0.1.0"
