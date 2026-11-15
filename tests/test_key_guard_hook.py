"""读 Key 拦截 hook（S135，D-key-guard-4）。

背景：runtime.json 里是引擎 key（明文），排障时最容易发生 `cat ~/.vod-devkit/
payloads/*/vod_mcp/runtime.json`、`env | grep VOD_JAVA_API_KEY` —— 一旦打印，key
就进了会话/日志/模型上下文。技能里写"只引指纹"靠模型自觉，这条 hook 是机制。

两条铁律（用例锁死）：
1. 判定窄而明确——只拦"读 runtime.json"与"导出点名 key 的 env"，其它放行；
2. **fail-open**——pre_tool_call 是阻塞事件，脚本一坏就是所有工具调用都挂，
   所以坏输入/异常一律零输出（放行）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from vod_mcp.host_adapters import hermes

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "integrations" / "hermes" / "hooks" / "vod_guard.py"


def _load_guard():
    """把 hook 当模块加载（它不在包路径里）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("vod_guard_under_test", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load_guard()


def _payload(tool, **args):
    return {"event": "pre_tool_call", "tool_name": tool, "args": args}


# ── S135 判定 ────────────────────────────────────────────

def test_s135_cat_runtime_json_is_blocked():
    msg = guard.verdict(_payload("terminal", command=(
        "cat ~/.vod-devkit/payloads/0.5.9/vod_mcp/runtime.json")))
    assert msg and "runtime.json" in msg
    assert "auth status" in msg, "拦截必须给可执行的替代（只引指纹）"
    assert "VOD_HOOK_READ_GUARD=0" in msg, "要告诉用户怎么关"


def test_s135_read_verbs_behind_pipes_are_blocked():
    for cmd in ("grep -o 'java_key' /root/.vod-devkit/vod_mcp/runtime.json",
                "python3 -c \"print(open('runtime.json').read())\"",
                "head -c 400 runtime.json && jq . submissions"):
        assert guard.verdict(_payload("terminal", command=cmd)), cmd


def test_s135_env_with_key_name_is_blocked():
    assert guard.verdict(_payload(
        "terminal", command="env | grep VOD_JAVA_API_KEY"))


def test_s135_naming_only_is_allowed():
    """只看变量名不泄值：这条替代写法必须放行（否则拦截把人逼进死胡同）。"""
    assert guard.verdict(_payload(
        "terminal", command="env | cut -d= -f1 | grep '^VOD_'")) is None


def test_s135_unrelated_commands_pass():
    assert guard.verdict(_payload("terminal", command="ls -la ~/.vod-devkit")) is None
    assert guard.verdict(_payload("terminal", command="rm -f foo.json")) is None


def test_s135_other_tools_are_never_blocked():
    """非读取类工具不拦：MCP 工具自己走 auth_status，不该被误伤。

    注意 read_file 现在**在**覆盖范围里（见 S135 文件/代码工具那条）——这里举
    写文件与插件自有工具，才是真正的"不相关工具"。
    """
    assert guard.verdict(_payload("write_file", path="/x/a.txt")) is None
    assert guard.verdict({"tool_name": "vod_auth_status", "args": {}}) is None


def test_s135_empty_or_broken_payload_passes():
    assert guard.verdict({}) is None
    assert guard.verdict({"tool_name": "terminal"}) is None


# ── S135 线协议与 fail-open ───────────────────────────────

def _run_stdin(payload, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    return subprocess.run([sys.executable, str(GUARD)],
                          input=payload, capture_output=True, text=True, timeout=30,
                          env=env)


def test_s135_stdout_is_hermes_wire_shape():
    r = _run_stdin(json.dumps(_payload("terminal", command="cat runtime.json")))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    assert out["decision"] == "block" and "runtime.json" in out["reason"]


def test_s135_broken_json_fails_open():
    """阻塞事件里崩掉等于拦掉所有工具调用——必须静默放行。"""
    r = _run_stdin("{not json")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_s135_empty_stdin_passes():
    r = _run_stdin("")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_s135_kill_switch():
    r = _run_stdin(json.dumps(_payload("terminal", command="cat runtime.json")),
                   env_extra={"VOD_HOOK_READ_GUARD": "0"})
    assert r.returncode == 0 and r.stdout.strip() == ""


# ── S135 config.yaml 注册（两条 hook 各摘各的） ─────────────

LLM_CMD = "/usr/bin/python3 /x/hooks/vod_router.py"
GUARD_CMD = "/usr/bin/python3 /x/hooks/vod_guard.py"


def test_s135_both_hooks_register_idempotently():
    text = ""
    text, s1 = hermes.upsert_llm_hook(text, LLM_CMD)
    text, s2 = hermes.upsert_guard_hook(text, GUARD_CMD)
    assert s1 == "created" and s2 in ("added", "created")
    assert "pre_llm_call:" in text and "pre_tool_call:" in text
    assert "vod_router.py" in text and "vod_guard.py" in text
    text2, s3 = hermes.upsert_llm_hook(text, LLM_CMD)
    text3, s4 = hermes.upsert_guard_hook(text2, GUARD_CMD)
    assert s3 == s4 == "unchanged" and text3 == text, "幂等：再跑一次不许改写"


def test_s135_removal_is_per_hook():
    text, _ = hermes.upsert_llm_hook("", LLM_CMD)
    text, _ = hermes.upsert_guard_hook(text, GUARD_CMD)
    only_guard, removed_llm = hermes.remove_llm_hook(text)
    assert removed_llm and "vod_router.py" not in only_guard
    assert "vod_guard.py" in only_guard, "摘一条不许连另一条一起摘"
    final, removed_guard = hermes.remove_guard_hook(only_guard)
    assert removed_guard and "vod_guard.py" not in final


def test_s135_other_peoples_hooks_are_untouched():
    text = "hooks:\n  pre_tool_call:\n    - command: \"/their/script.sh\"\n      timeout: 3\n"
    text, _ = hermes.upsert_guard_hook(text, GUARD_CMD)
    after, _ = hermes.remove_guard_hook(text)
    assert "/their/script.sh" in after and "vod_guard.py" not in after

def test_s135_file_and_code_tools_are_covered():
    """只拦 shell 等于没拦：模型读 runtime.json 的常规路径是 read_file / execute_code。

    评审实测（2026-11-16）：read_file(path=…/runtime.json)、execute_code(open(...).read())
    与 search_files(pattern=java_key) 当时全部放行——白名单外一律 allow。
    """
    assert guard.verdict(_payload("read_file", path="/x/payloads/0.5.9/vod_mcp/runtime.json"))
    assert guard.verdict(_payload("execute_code",
                                 code="print(open('/x/vod_mcp/runtime.json').read())"))
    assert guard.verdict(_payload("search_files", pattern="java_key", path="/x/.vod-devkit"))
    # 正常读取一律放行（fail-open 的边界）
    assert guard.verdict(_payload("read_file", path="/root/vod-devkit/README.md")) is None
    assert guard.verdict(_payload("execute_code", code="print(1 + 1)")) is None
    assert guard.verdict(_payload("search_files", pattern="def main", path="/x/src")) is None
