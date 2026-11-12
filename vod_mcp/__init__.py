"""vod-devkit：VOD 分析能力的 MCP 插件薄壳。

铁律（见 docs/design.md）：
1. 只允许经 HTTP 调 workflow/api.py，禁止 import 引擎内部模块
2. 外部无 DB 直连路径（护栏 deny 兜底）
3. 任务 ID 是唯一对账主键，写类工具返回一律携带
"""
__version__ = "0.5.2"
# 默认上游：VOD 测试环境。外部用户本机无 VOD，回环默认值=装完即坏；
# 生产地址定型后只改这一处（tools.py 与 bin/vod-devkit 共用本常量）。
DEFAULT_JAVA_BASE = "https://vod-dev.topxtopx.com"
