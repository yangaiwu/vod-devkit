#!/usr/bin/env python3
"""pre-push 门禁第三检查：凭据泄漏 + 高危运行模式静态扫描。

对标 huawei-cloud-skill-audit 的三检查流水线（gitleaks + runtime_security 思路），
零依赖纯 Python 实现（不引 gitleaks 二进制，保持仓内自包含）：
  1. secret 模式：PAT/token/私钥/AK-SK/SMTP 授权码等，命中即红
  2. 高危运行模式：eval/exec/pickle.loads/shell=True 等动态执行面，命中列明细人工判
扫描对象 = git 追踪文件（工作树当前内容），排除本文件的模式定义自身。
退出码：0=干净，1=secret 命中（禁推）；高危模式仅告警不拦（白名单兜底）。
"""
from __future__ import annotations

import re
import subprocess
import sys

SECRET_PATTERNS = [
    (r"(?i)oauth2:[A-Za-z0-9_\-]{16,}@(?:gitcode|github|gitee)\.", "URL 内嵌 token"),
    (r"(?i)(gitcode|github|gitee)\.[a-z.]+/[^\s]*[?&](?:access_)?token=[A-Za-z0-9_\-]{16,}", "URL query token"),
    (r"(?i)(access_token|pat|api[_-]?key|apikey|secret|passwd|password|授权码)\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/]{16,}", "键值对疑似凭据"),
    (r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "私钥块"),
    (r"(?i)\b[A-Za-z0-9._%+-]+@(?:huawei|gitcode)\.(?:com|local)\s*[:/]\S{8,}", "账号口令对"),
    (r"(?i)(AK|SK|SECRET)_?[A-Z0-9]{6,}\s*[:=]\s*['\"][A-Za-z0-9+/]{20,}['\"]", "云 AK/SK"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI 型 key"),
    (r"(?i)Bearer\s+[A-Za-z0-9_\-\.]{32,}", "Bearer 长令牌"),
]
HIGH_RISK_PATTERNS = [
    (r"\beval\(", "eval 动态执行"),
    (r"\bexec\(", "exec 动态执行"),
    (r"\bpickle\.loads?\(", "pickle 反序列化"),
    (r"shell\s*=\s*True", "subprocess shell=True"),
    (r"(?i)os\.system\(", "os.system"),
]
SELF = "scripts/secret_scan.py"


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return [f for f in out.stdout.splitlines() if f and f != SELF]


def main() -> int:
    secret_hits: list[str] = []
    risk_hits: list[str] = []
    for path in tracked_files():
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
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
    if risk_hits:
        print("[secret-scan] 高危模式（人工确认，不拦推）:")
        for h in risk_hits:
            print("  ?", h)
    if secret_hits:
        print("[secret-scan] FAIL: 疑似凭据泄漏，禁止推送:")
        for h in secret_hits:
            print("  !", h)
        return 1
    print("[secret-scan] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
