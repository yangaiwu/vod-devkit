"""诊断分层（doctor 报告）与项目识别（detect）的回归锁。

背景：对表 huaweicloud-devkit 的 doctor-report / explain-error / detect-framework。
我们缺的是"报告的形状"和"只读识别"，不是能力本身。三件事必须锁住：

1. 归层是确定性的（关键词表），未知问题如实进「未分类」——不许语义瞎猜。
2. 每条失败都带动作（运维只记一句话："doctor 报错了"）。
3. detect 不做语义推论：只认扩展名统计与清单里的显式依赖，且跳过 vendor/node_modules。
"""
import json
import subprocess
import sys
from pathlib import Path

from vod_mcp import diagnose, detect_framework

ROOT = Path(__file__).resolve().parent.parent


def test_classify_maps_known_failures_to_layers():
    cases = {
        "载荷目录缺失：/x/payloads/0.5.3（MCP 入口指向它，宿主起不来）": "载荷",
        "MCP 配置文件缺失": "配置",
        "技能文件缺失（codeartsdoer）：vod-core/SKILL.md": "技能",
        "路由插件副本落后于仓内：/x/router.py": "插件",
        "远程 MCP 端点不可达：https://x": "网络",
        "key 无效（指纹 abc，引擎 401 拒绝）": "网络",
        "无 install-manifest.json（未 install？）": "环境",
        "今天太阳很大": "未分类",
    }
    for msg, layer in cases.items():
        assert diagnose.classify(msg)[0] == layer, msg


def test_render_groups_by_layer_and_prints_action():
    problems = ["技能文件缺失（x）：a/SKILL.md", "载荷被改动：vod_mcp/server.py", "莫名失败"]
    out = diagnose.render_problems(problems)
    lines = out.splitlines()
    assert lines[0].startswith("[载荷]"), out          # LAYERS 顺序：载荷在技能之前
    assert any(l.startswith("[技能]") for l in lines)
    assert any(l.startswith("[未分类]") for l in lines), out
    assert "莫名失败" in out
    assert "动作：" in out and "原因：" in out


def test_explain_known_code_and_unknown_text():
    info = diagnose.explain("-32010")
    assert info["known"] and info["layer"] == "配置" and "产品" in info["cause"]
    unk = diagnose.explain("一条谁也没见过的报错")
    assert unk["known"] is False


def test_detect_reads_languages_frameworks_and_markers(tmp_path):
    (tmp_path / "src").mkdir()
    for i in range(5):
        (tmp_path / "src" / f"m{i}.py").write_text("x=1\n")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "app.tsx").write_text("export {}\n")
    (tmp_path / "requirements.txt").write_text("fastapi==0.110\npytest>=8\n")
    (tmp_path / "package.json").write_text(json.dumps(
        {"dependencies": {"react": "^18"}, "devDependencies": {"vite": "^5"}}))
    info = detect_framework.detect(str(tmp_path))
    langs = {l["name"]: l["files"] for l in info["languages"]}
    assert langs["Python"] == 5 and langs["TypeScript"] == 1
    assert "FastAPI" in info["frameworks"] and "React" in info["frameworks"]
    assert {m["file"] for m in info["markers"]} >= {"requirements.txt", "package.json"}


def test_detect_skips_vendor_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("1")
    (tmp_path / "a.py").write_text("1")
    info = detect_framework.detect(str(tmp_path))
    assert info["scanned"] == 1, info
    assert [l["name"] for l in info["languages"]] == ["Python"]


def test_detect_truncates_huge_trees(tmp_path, monkeypatch):
    monkeypatch.setattr(detect_framework, "MAX_FILES", 3)
    for i in range(10):
        (tmp_path / f"f{i}.py").write_text("1")
    info = detect_framework.detect(str(tmp_path))
    assert info["truncated"] is True and info["scanned"] == 3


def test_cli_explain_and_detect_run(tmp_path):
    py = sys.executable
    r = subprocess.run([py, str(ROOT / "bin" / "vod-devkit"), "explain", "-32010"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "动作：" in r.stdout

    (tmp_path / "a.py").write_text("1")
    r2 = subprocess.run([py, str(ROOT / "bin" / "vod-devkit"), "detect", "--path",
                         str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert r2.returncode == 0 and "摘要：" in r2.stdout
    assert "Python" in r2.stdout


def test_doctor_renders_layered_report_when_broken(tmp_path):
    """空 HOME 跑 doctor：应出分层报告（带层标题与动作），而不是平铺 FAIL 列表。"""
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "VOD_PACKS": "core",
           "VOD_DEVKIT_MANIFEST": str(tmp_path / "no-such-manifest.json")}
    r = subprocess.run([sys.executable, str(ROOT / "bin" / "vod-devkit"), "doctor"],
                       capture_output=True, text=True, env=env, timeout=180)
    assert r.returncode == 1
    out = r.stdout + r.stderr
    assert "[环境]" in out and "动作：" in out