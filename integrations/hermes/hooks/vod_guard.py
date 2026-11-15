#!/usr/bin/env python3
"""vod_guard：Hermes `pre_tool_call` hook —— 只拦"把引擎 key 读进对话"的动作。

为什么要这条机制：runtime.json 里是引擎 key（仓内那份是设备绑定的），而排障时
最容易发生的就是 `cat ~/.vod-devkit/payloads/*/vod_mcp/runtime.json`、`grep -r
key`、`env | grep VOD` —— 一旦打印，key 就进了会话、日志和模型上下文。技能里
写"排障只引指纹"靠模型自觉，这条 hook 把它变成机制。

判定窄而明确（只做"读取该文件/导出该变量"这一件事）：
1) 命令里出现 `runtime.json` 且出现读取类动词 → block；
2) 命令是 `env`/`printenv`/`set` 且同时点名 key 变量 → block（给只看变量名的替代写法）。
其它一切（包括解析失败、字段缺失、异常）→ **放行**。

失败姿态必须是 fail-open：`pre_tool_call` 是 Hermes 的**阻塞事件**，脚本一坏就是
"所有工具调用都被拦"，伤害远大于漏拦一次。关闭开关：env `VOD_HOOK_READ_GUARD=0`
（或 `hermes hooks revoke <cmd>`）。

线协议：stdin 收 JSON 载荷（顶层 tool_name / args），stdout 回
`{"decision": "block", "reason": "..."}`；不拦时零输出。
"""
import json
import os
import re
import sys

# shell 类：命令字符串里判判读动词
SHELL_TOOLS = {"terminal", "shell", "bash", "run_command", "computer_use", "process"}
# 文件/代码类：模型读 runtime.json 的常规路径恰好是这几个（不是 shell）
FILE_TOOLS = {"read_file", "read_files"}
SEARCH_TOOLS = {"search_files", "search"}
CODE_TOOLS = {"execute_code"}

_READ_VERBS = re.compile(
    r"(?:^|[\s|;&(`])(cat|head|tail|less|more|strings|xxd|base64|od|hexdump|"
    r"grep|rg|awk|sed|jq|sqlite3|python3?|perl|ruby|open|read_text|read_bytes|"
    r"json\.load|json\.loads)\b")
_READ_FILE = re.compile(r"runtime\.json")
_ENV_DUMP = re.compile(r"(?:^|[\s|;&(`])(env|printenv|set)\b")
_KEY_NAMES = re.compile(r"(VOD_JAVA_API_KEY|VOD_[A-Z_]*KEY|java_key|JAVA_API_KEY)")

_BLOCK_RUNTIME = (
    "读取 runtime.json 会把引擎 key 打进对话/日志（这个文件里是明文 key）。"
    "要看凭据只引指纹：`vod-devkit auth status`（输出 指纹 + 档位，不含明文）。"
    "确需人工核对请把文件拷到受控位置、由人处理，不要让模型 cat。"
    "（本拦截可用 VOD_HOOK_READ_GUARD=0 关闭；hermes hooks revoke 可摘除本条。）"
)
_BLOCK_ENV = (
    "导出 VOD 相关环境变量会带出 key 明文。只想确认变量是否存在/叫什么名，用："
    "`env | cut -d= -f1 | grep '^VOD_'`（只有名字，没有值）；"
    "要看档位用 `vod-devkit auth status`（指纹）。"
    "（可用 VOD_HOOK_READ_GUARD=0 关闭。）"
)


def _strings(node) -> list:
    """把载荷里的所有字符串摊平（命令可能在 command/cmd/code/script 等键下）。"""
    out = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            out.append(cur)
        elif isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
    return out


def verdict(payload: dict) -> str | None:
    """返回 block 文案；放行返回 None。纯函数，用例直接测它。

    覆盖三条真实读取路径（评审实测：只拦 shell 等于没拦）：
    - shell 类：命令里出现 runtime.json + 读动词；
    - read_file / search_files：参数里点名 runtime.json（或搜 key 名）；
    - execute_code：代码里点名 runtime.json（open/read_text/json.load 都算）。
    其余工具与命令一律放行（fail-open）。
    """
    if not isinstance(payload, dict):
        return None
    tool = str(payload.get("tool_name") or "").strip().lower()
    known = SHELL_TOOLS | FILE_TOOLS | SEARCH_TOOLS | CODE_TOOLS
    if tool and tool not in known:
        return None
    blobs = _strings(payload.get("args") if "args" in payload else payload)
    text = "\n".join(blobs)
    if not text.strip():
        return None
    if tool in FILE_TOOLS or tool in SEARCH_TOOLS:
        # read_file(path=…runtime.json) / search_files(pattern=java_key, path=…)
        if _READ_FILE.search(text):
            return _BLOCK_RUNTIME
        if tool in SEARCH_TOOLS and _KEY_NAMES.search(text):
            return _BLOCK_ENV
        return None
    if tool in CODE_TOOLS:
        # 代码里点名 runtime.json：读它没有别的正当用途（存在性判断也不是排障必需）
        if _READ_FILE.search(text):
            return _BLOCK_RUNTIME
        if _ENV_DUMP.search(text) and _KEY_NAMES.search(text):
            return _BLOCK_ENV
        return None
    if _READ_FILE.search(text) and _READ_VERBS.search(text):
        return _BLOCK_RUNTIME
    if _ENV_DUMP.search(text) and _KEY_NAMES.search(text):
        return _BLOCK_ENV
    return None


def main() -> int:
    if os.environ.get("VOD_HOOK_READ_GUARD", "1").strip() in ("0", "false", "off"):
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        msg = verdict(payload)
    except Exception:      # noqa: BLE001  fail-open：解析失败绝不拦
        return 0
    if msg:
        sys.stdout.write(json.dumps({"decision": "block", "reason": msg},
                                    ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())