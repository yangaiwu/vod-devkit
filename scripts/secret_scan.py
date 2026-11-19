#!/usr/bin/env python3
"""pre-push 门禁第三检查：凭据泄漏 + 高危运行模式静态扫描。

对标 huawei-cloud-skill-audit 的三检查流水线（gitleaks + runtime_security 思路），
零依赖纯 Python 实现（不引 gitleaks 二进制，保持仓内自包含）：
  1. secret 模式：PAT/token/私钥/AK-SK/SMTP 授权码等，命中即红
  2. 高危运行模式：eval/exec/pickle.loads/shell=True 等动态执行面，命中列明细人工判

ARCH-CFG-04（2026-11-19）修三处覆盖边界：
  · 扫描面从「只用 git ls-files」扩到「tracked + 生成副本（plugins/、assets/）」——
    副本零提交正是为了不进 git，于是它天然落在 tracked 之外，明文 key 藏在里面不会被发现。
    没有 git（tarball 解包/打包机）时退化为全树遍历，不再崩、也不再静默扫零个文件。
  · `git ls-files` 加 timeout；调用失败/超时一律降级并**明确告警**，不许静默通过。
  · 模式表补 `.env` 形态、通用长十六进制串，并认本仓实际字段名 `java_key`。

退出码：0=干净，1=secret 命中（禁推）/扫描面不可用（fail-closed）。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SECRET_PATTERNS = [
    (r"(?i)oauth2:[A-Za-z0-9_\-]{16,}@(?:gitcode|github|gitee)\.", "URL 内嵌 token"),
    (r"(?i)(gitcode|github|gitee)\.[a-z.]+/[^\s]*[?&](?:access_)?token=[A-Za-z0-9_\-]{16,}", "URL query token"),
    (r"(?i)(access_token|pat|api[_-]?key|apikey|secret|passwd|password|授权码)\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/]{16,}", "键值对疑似凭据"),
    # 本仓实际落盘字段（ARCH-CFG-04：src/vod_mcp/runtime_state.py 用的就是它）
    (r"(?i)\bjava_key\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/]{16,}", "本仓 java_key 落盘"),
    (r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "私钥块"),
    (r"(?i)\b[A-Za-z0-9._%+-]+@(?:huawei|gitcode)\.(?:com|local)\s*[:/]\S{8,}", "账号口令对"),
    (r"(?i)(AK|SK|SECRET)_?[A-Z0-9]{6,}\s*[:=]\s*['\"][A-Za-z0-9+/]{20,}['\"]", "云 AK/SK"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI 型 key"),
    (r"(?i)Bearer\s+[A-Za-z0-9_\-\.]{32,}", "Bearer 长令牌"),
    # ARCH-CFG-04 补：.env 形态（大写键名 + 长值）。实测零误报。
    (r"^[A-Z][A-Z0-9_]{2,40}\s*=\s*[A-Za-z0-9_\-/+=]{24,}$", ".env 形态长值"),
    # 不设「通用长令牌串」模式：实测它把 git SHA、sha256 指纹、npm integrity 全抓进来
    # （build-info/rules-provenance/package-lock 上百条误报），真凭据一个没多抓。
    # 长随机串若无键名上下文，与哈希不可区分——这类只靠上面的「键值对」模式带键名兜。
]
HIGH_RISK_PATTERNS = [
    (r"\beval\(", "eval 动态执行"),
    (r"\bexec\(", "exec 动态执行"),
    (r"\bpickle\.loads?\(", "pickle 反序列化"),
    (r"shell\s*=\s*True", "subprocess shell=True"),
    (r"(?i)os\.system\(", "os.system"),
]
SELF = "scripts/secret_scan.py"

# 生成副本：零提交，天然在 tracked 之外，但会随发布物一起发出去。
EXTRA_ROOTS = ("plugins", "assets")
# 二进制/大文件跳过：按扩展名 + 大小双判。
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
               ".tar", ".whl", ".so", ".pyc", ".woff", ".woff2", ".ttf", ".jar"}
MAX_BYTES = 2 * 1024 * 1024
SKIP_DIR = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist"}


def tracked_files(root: Path) -> tuple[list[str], str]:
    """返回 (相对路径列表, 降级说明)。git 不可用/超时/失败一律降级，不抛异常。

    降级说明非空 = 扫描面不完整，主流程据此告警（fail-closed 由 main 决定）。
    """
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                             cwd=root, timeout=30)
    except subprocess.TimeoutExpired:
        return [], "git ls-files 超时（30s）"
    except (OSError, FileNotFoundError):
        return [], "git 不可用"
    if out.returncode != 0:
        return [], f"git ls-files 失败（exit={out.returncode}）"
    files = [f for f in (out.stdout or "").splitlines() if f and f != SELF]
    if not files:
        return [], "git 仓库没有任何 tracked 文件"
    return files, ""


def walk_extra(root: Path) -> list[str]:
    """遍历生成副本目录（plugins/、assets/），跳过二进制与超大文件。"""
    found = []
    for base in EXTRA_ROOTS:
        d = root / base
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIR for part in p.parts):
                continue
            if p.suffix.lower() in SKIP_SUFFIX:
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            found.append(str(p.relative_to(root)))
    return found


def scan_paths(root: Path, paths: list[str]) -> tuple[list[str], list[str]]:
    secret_hits: list[str] = []
    risk_hits: list[str] = []
    for path in paths:
        try:
            text = open(root / path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "secret-scan:allow" in line:
                continue  # 行内豁免（测试夹具等假阳性，标注留痕）
            for pat, label in SECRET_PATTERNS:
                if re.search(pat, line):
                    secret_hits.append(f"{path}:{i} [{label}] {line.strip()[:100]}")
            for pat, label in HIGH_RISK_PATTERNS:
                if re.search(pat, line) and not line.strip().startswith("#"):
                    risk_hits.append(f"{path}:{i} [{label}] {line.strip()[:100]}")
    return secret_hits, risk_hits


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    tracked, degraded = tracked_files(root)
    if degraded:
        # ARCH-CFG-04：旧实现此处会静默扫零个文件 → 门禁绿着什么都没查。
        print(f"[secret-scan] WARN: 扫描面降级（{degraded}），改走全树遍历", file=sys.stderr)
    extra = walk_extra(root)
    paths = list(dict.fromkeys(tracked + extra))

    if not paths:
        print("[secret-scan] FAIL: 扫描面为空——无法确认无凭据泄漏（fail-closed）",
              file=sys.stderr)
        return 1

    secret_hits, risk_hits = scan_paths(root, paths)
    if risk_hits:
        print("[secret-scan] 高危模式（人工确认，不拦推）:")
        for h in risk_hits:
            print("  ?", h)
    if secret_hits:
        print("[secret-scan] FAIL: 疑似凭据泄漏，禁止推送:")
        for h in secret_hits:
            print("  !", h)
        return 1
    print(f"[secret-scan] OK（扫描 {len(paths)} 个文件"
          f"{'，含生成副本 ' + str(len(extra)) + ' 个' if extra else ''}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())