"""registry ↔ 仓内 发版状态对账（devkit registry:diff 的裁剪版）。

和 publish_verify.py 分工（别重复造）：
- publish_verify：**发版当时**的终态断言（publish 后轮询上没上线、包内关键文件在不在）
- 本脚本：**任何时刻**的状态快照（registry 上是什么版本、仓内是什么版本、tag 打没打、
  两包是否同版、契约版本是否跟包版本同步）——回答「现在有没有未发布的改动」。

判据（退出码）：
  OK        registry == 仓内，且两包同版、契约同版、tag 在
  AHEAD     仓内领先 registry（有未发布提交）——开发期正常，默认 0；--strict 时 1
  DRIFT     registry 领先仓内 / 两包不同版 / 契约版本失步 —— 一律 1
  UNKNOWN   取不到 registry（离线）—— 明确 UNKNOWN，不当成绿
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PKGS = ("vod-devkit", "dsh-vod-devkit")


def npm_view(pkg: str, field: str, runner=subprocess.run) -> object:
    """查 registry 字段；失败返回 None（离线/包不存在都算取不到，不猜）。"""
    try:
        r = runner(["npm", "view", pkg, field, "--json"],
                   capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout.strip().strip('"')


def _contract_path(root: Path) -> Path:
    """契约文件位置：仓内 src/contract（S2 起），载荷/旧布局=根下 contract。"""
    for rel in ("assets/contract/tools.schema.json", "contract/tools.schema.json"):
        p = root / rel
        if p.exists():
            return p
    return root / "assets" / "contract" / "tools.schema.json"


def local_versions(root: Path = ROOT) -> dict:
    def _v(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("version")
        except Exception:
            return None
    return {
        "vod-devkit": _v(root / "package.json"),
        "dsh-vod-devkit": _v(root / "dsh" / "package.json"),
        "contract": _v(_contract_path(root)),
    }


def tag_exists(tag: str, root: Path = ROOT) -> bool:
    try:
        r = subprocess.run(["git", "tag", "--list", tag], cwd=root,
                           capture_output=True, text=True, timeout=30)
        return bool(r.stdout.strip())
    except Exception:
        return False


def reconcile(local: dict, registry: dict, tags: dict | None = None,
              shallow: bool = False) -> dict:
    """纯计算：返回 {"status": ok|ahead|drift|unknown, "findings":[...]}。"""
    findings = []
    v_main, v_dsh = local.get("vod-devkit"), local.get("dsh-vod-devkit")
    if not v_main or not v_dsh:
        return {"status": "drift", "findings": ["package.json / dsh/package.json 读不到版本"]}
    if v_main != v_dsh:
        findings.append(f"两包版本不一致：vod-devkit={v_main} / dsh-vod-devkit={v_dsh}"
                        "（壳游离散版曾造成半个月静默故障）")
    if local.get("contract") and str(local["contract"]) != str(v_main):
        findings.append(f"契约版本失步：contract={local['contract']} / package={v_main}")
    if findings:
        return {"status": "drift", "findings": findings}

    got = {p: (registry or {}).get(p) for p in DEFAULT_PKGS}
    if not all(got.values()):
        return {"status": "unknown",
                "findings": [f"registry 取不到版本（{got}）——离线时不算绿，也不算红"]}

    for pkg, rv in got.items():
        if str(rv) == str(v_main):
            findings.append(f"{pkg}: registry={rv} == 仓内（已发布）")
        elif _cmp(str(rv), str(v_main)) < 0:
            findings.append(f"{pkg}: registry={rv} < 仓内={v_main}（有未发布改动）")
        else:
            findings.append(f"{pkg}: registry={rv} > 仓内={v_main}（registry 领先=本地落后/他人发版）")
    status = "ok"
    if any("registry" in f and ">" in f for f in findings):
        status = "drift"
    elif any("<" in f for f in findings):
        status = "ahead"
    tag = f"v{v_main}"
    if tags is not None and not tags.get(tag):
        if shallow:
            # 浅克隆（actions/checkout 默认 fetch-depth=1）看不到 tag——
            # 「看不到」≠「没打」，判红=CI 假红（v0.5.8 实锤：已发布且 tag 已推，
            # CI 仍报缺 tag）。tag 对账交给本地/fetch-depth 0 的流水线。
            findings.append(f"tag {tag} 不可见（浅克隆未取 tags）——tag 对账跳过，不判红")
        else:
            findings.append(f"缺 tag {tag}（{v_main} 未打 tag 或未推送）")
            if status == "ok":
                status = "drift"  # 已发布却没有 tag=对账链断了；开发中（ahead）只提示
    return {"status": status, "findings": findings}


def _cmp(a: str, b: str) -> int:
    def t(v):
        out = []
        for part in str(v).split("-")[0].split("+")[0].split(".")[:3]:
            try:
                out.append(int(part))
            except ValueError:
                out.append(0)
        return tuple(out + [0] * (3 - len(out)))
    return (t(a) > t(b)) - (t(a) < t(b))


def is_shallow(root: Path = ROOT) -> bool:
    """仓库是否为浅克隆（浅克隆里 tag 不可见，不能当「没打 tag」）。"""
    try:
        r = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root,
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip() == "true"
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="仓内领先 registry 也判失败（发版检查用）")
    ap.add_argument("--no-tag-check", action="store_true")
    args = ap.parse_args(argv)
    local = local_versions()
    registry = {p: npm_view(p, "version") for p in DEFAULT_PKGS}
    tags = None if args.no_tag_check else {f"v{local.get('vod-devkit')}":
                                           tag_exists(f"v{local.get('vod-devkit')}")}
    rep = reconcile(local, registry, tags, shallow=is_shallow())
    print(f"状态: {rep['status'].upper()}")
    for f in rep["findings"]:
        print(f"  - {f}")
    if rep["status"] == "drift":
        return 1
    if rep["status"] == "ahead":
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())