"""S234：工具面探针收成一份（host_matrix.resolve_entry + 两种环境键）。

踩坑记录（2026-11-17）：手写一次性探针只读 `env`，而 opencode/codeartsdoer/codeartswork
的配置把环境变量写在 `environment` 里 → VOD_PACKS 没传进子进程 → 服务端退回全 pack →
把 10 工具报成 12。产品侧（host_matrix._probe）本来就兼容两种键，错的只有裸探针。
现在口径收成：
- 入口解析 = `host_matrix.resolve_entry()`（巡检与探针共用，不许各解析一份配置）；
- 环境变量 = `probe_tools.entry_env()`（`env` ∪ `environment`）；
- 探针只调只读工具，不提交、不落库。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import host_matrix as hm  # noqa: E402
import probe_tools as pt  # noqa: E402


def test_s234_entry_env_reads_both_keys():
    """S234：`env` 与 `environment` 两种写法都要读（三个宿主用的是后者）。"""
    entry = {"command": "x", "env": {"A": "1"}, "environment": {"B": "2"}}
    assert pt.entry_env(entry) == {"A": "1", "B": "2"}
    assert pt.entry_env({"command": "x", "environment": {"VOD_PACKS": "core,collect"}}) == \
        {"VOD_PACKS": "core,collect"}
    assert pt.entry_env({}) == {}


def test_s234_entry_env_environment_wins_on_conflict():
    entry = {"env": {"VOD_PACKS": "old"}, "environment": {"VOD_PACKS": "core,collect"}}
    assert pt.entry_env(entry)["VOD_PACKS"] == "core,collect"


@pytest.mark.parametrize("host,rel_key", [
    ("opencode", "environment"), ("codeartsdoer", "environment"), ("codeartswork", "environment"),
])
def test_s234_resolve_entry_returns_host_configured_entry(tmp_path, host, rel_key):
    """S234：入口解析走宿主自己的配置，且保留 `environment` 原样（不许归一掉）。"""
    spec = hm.EXPECT[host]
    conf = tmp_path / spec["config"]
    conf.parent.mkdir(parents=True, exist_ok=True)
    entry = {"command": ["/bin/true"], "args": [],
             rel_key: {"VOD_PACKS": "core,collect", "VOD_DEVKIT_HOME": "/tmp/s"}}
    node = data = {}
    for part in spec["entry"]:
        node[part] = {}
        node = node[part]
    node.update(entry)
    conf.write_text(json.dumps(data), encoding="utf-8")
    got, why = hm.resolve_entry(host, home=tmp_path)
    assert got is not None, why
    assert pt.entry_env(got)["VOD_PACKS"] == "core,collect"


def test_s234_dsh_entry_parses_patch(tmp_path):
    """S234：dsh 的入口在 patch 托管块里，解析必须给出 command/args/env。"""
    patch = tmp_path / ".dsh" / "profiles" / "web" / "cordis.patch.yml"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(
        "# vod-devkit DSH integration start\n"
        "- insert:\n"
        "    - id: vod-devkit-mcp\n"
        "      name: '@deepseek-ai/dsh-mcp-client'\n"
        "      config:\n"
        "        command: /usr/bin/python3\n"
        "        args:\n"
        "          - /tmp/payload/vod_mcp/server.py\n"
        "        env:\n"
        "          VOD_PACKS: \"core,collect\"\n"
        "          VOD_DEVKIT_HOME: /tmp/state\n"
        "    - id: vod-devkit\n"
        "      name: dsh-vod-devkit\n"
        "# vod-devkit DSH integration end\n", encoding="utf-8")
    entry, why = hm.resolve_entry("dsh", home=tmp_path, profile="web")
    assert entry is not None, why
    assert entry["command"] == "/usr/bin/python3"
    assert entry["args"] == ["/tmp/payload/vod_mcp/server.py"]
    assert entry["env"]["VOD_PACKS"] == "core,collect"


def test_s234_probe_reuses_shared_resolver_and_is_not_shipped():
    """S234：探针不许自己再解析配置；且 scripts/ 不进 npm 包（部署验证工具不入交付面）。"""
    text = (ROOT / "scripts" / "probe_tools.py").read_text(encoding="utf-8")
    assert "hm.resolve_entry(" in text
    assert "resolve_entry" in text and "_dig(" not in text
    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert not any(str(f).startswith("scripts/") for f in pkg.get("files") or []), \
        "scripts/ 被加进 npm files 了——部署验证工具不该随包发出去"