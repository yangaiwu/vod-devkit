#!/usr/bin/env python3
"""发版终态断言：publish 之后的「真的上线了」核验（v0.4.2 漏发事故的根治）。

事故形态：release.sh 把 tag 推上去、把发布命令打印出来，人念完命令以为发了；
实际上 npm 上没有该版本（或 CDN 还停在旧版），用户 `npx vod-devkit@latest`
拿到的是旧包——tag 与 registry 之间没有任何自动对账。

本脚本做三件事，任何一项不过即 exit 1：
1. **版本对账**：轮询 `npm view <pkg> version` 直到等于目标版本（registry/CDN
   有传播延迟，只信轮询结果不信 publish 回执）。
2. **包内容对账**：从 registry 拉回该版本的 tarball，断言关键文件在包内存在
   且契约版本号已同步（0.4.1 实锤：files 白名单漏新模块，包内缺 pending.py）。
3. **两包同版**：主包与 dsh 壳必须同版本（壳游离散版曾是半个月的静默故障）。

用法（一般由 release.sh --publish 调用）：
  python3 scripts/publish_verify.py --version 0.4.5 \
      --pkg vod-devkit --pkg dsh-vod-devkit [--timeout 300] [--interval 5]
"""
import argparse
import io
import json
import subprocess
import sys
import tarfile
import time
import urllib.request

# 每个包的关键内容断言：tarball 内路径 → 期望包含的子串（None=只要求存在）
REQUIRED = {
    "vod-devkit": [
        ("package/vod_mcp/pending.py", None),
        ("package/vod_mcp/config_forms.py", None),
        ("package/vod_mcp/server.py", None),
        ("package/contract/tools.schema.json", None),
    ],
    "dsh-vod-devkit": [
        ("package/lib/index.js", None),
    ],
}


def _npm_view(pkg: str, field: str):
    r = subprocess.run(["npm", "view", f"{pkg}", field, "--json"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout.strip().strip('"')


def wait_for_version(pkg: str, version: str, timeout: float, interval: float) -> tuple:
    """轮询 registry 直到 latest/该包版本落到位。返回 (ok, 最后观察值)。"""
    deadline = time.time() + timeout
    last = None
    while True:
        last = _npm_view(pkg, "version")
        if str(last) == str(version):
            return True, last
        if time.time() >= deadline:
            return False, last
        time.sleep(interval)


def fetch_tarball(pkg: str, version: str) -> bytes:
    url = _npm_view(pkg, "dist.tarball")
    url_s = str(url or "").strip('"')
    # file:// 是回归测试用的本地位移（桩 npm 不打网络）；线上只有 http(s)
    if not url_s.startswith(("http://", "https://", "file://")):
        raise RuntimeError(f"拿不到 {pkg}@{version} 的 dist.tarball（view 返回 {url!r}）")
    with urllib.request.urlopen(url_s, timeout=120) as resp:
        return resp.read()


def check_tarball(pkg: str, blob: bytes, version: str) -> list:
    """返回问题清单（空=通过）。"""
    problems = []
    members = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile() and m.size < 2_000_000:  # 只读小文件，避免整包读进内存
                fh = tf.extractfile(m)
                if fh is not None:
                    members[m.name] = fh.read()
    for path, needle in REQUIRED.get(pkg, []):
        if path not in members:
            problems.append(f"{pkg} tarball 缺 {path}（files 白名单漏了吗？）")
            continue
        if needle and needle not in members[path].decode("utf-8", "replace"):
            problems.append(f"{pkg} tarball 的 {path} 不含 {needle!r}")
    schema = members.get("package/contract/tools.schema.json")
    if schema:
        ver = json.loads(schema).get("version")
        if str(ver) != str(version):
            problems.append(f"{pkg} tarball 契约版本 {ver} ≠ 目标 {version}"
                            "（发版版本落点漏同步）")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--pkg", action="append", required=True)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--interval", type=float, default=5)
    ap.add_argument("--skip-tarball", action="store_true",
                    help="只做版本对账（registry 不可拉包时的降级档，需显式指定）")
    a = ap.parse_args()

    failed = False
    for pkg in a.pkg:
        ok, seen = wait_for_version(pkg, a.version, a.timeout, a.interval)
        if not ok:
            print(f"FAIL: {pkg} registry 版本停在 {seen}，目标 {a.version} 未上线"
                  f"（publish 回执成功≠已上线；检查 staging 2FA/权限）",
                  file=sys.stderr)
            failed = True
            continue
        print(f"OK: {pkg}@{a.version} 已上线（轮询确认）")
        if a.skip_tarball:
            continue
        try:
            blob = fetch_tarball(pkg, a.version)
        except Exception as e:
            print(f"FAIL: {pkg} tarball 拉取失败：{e}", file=sys.stderr)
            failed = True
            continue
        problems = check_tarball(pkg, blob, a.version)
        if problems:
            failed = True
            for p in problems:
                print(f"FAIL: {p}", file=sys.stderr)
        else:
            print(f"OK: {pkg} tarball 内容与版本已核验（{len(blob)} bytes）")
    if failed:
        print("发版终态断言未过：不要宣告发版完成。", file=sys.stderr)
        sys.exit(1)
    print("发版终态断言通过：" + "、".join(f"{p}@{a.version}" for p in a.pkg))


if __name__ == "__main__":
    main()