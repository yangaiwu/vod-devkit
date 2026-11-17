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
        ("package/src/vod_mcp/pending.py", None),
        ("package/src/vod_mcp/config_forms.py", None),
        ("package/src/vod_mcp/server.py", None),
        ("package/assets/contract/tools.schema.json", None),
    ],
    "dsh-vod-devkit": [
        ("package/lib/index.js", None),
    ],
}


class RegistryQueryTimeout(RuntimeError):
    """registry 查询超时（网络/npm 工具层），与"包未发布"是两件事（S213）。"""


def _npm_view(pkg: str, field: str, attempts: int = 3, timeout: float = 90.0):
    """查询 registry 字段。超时重试，耗尽抛 RegistryQueryTimeout——**不许**把超时当"未发布"。

    实锤（0.5.33）：两颗包已 publish、tarball 200，但一次 `npm view … --json` 60s 超时，
    TimeoutExpired 直接冒泡成裸 traceback，发版脚本据此宣告"终态断言未过"并 exit 1——
    与 S187（引擎 502 打断整轮 e2e）同一类错：把不可判当失败。
    """
    last_err = None
    for i in range(max(1, attempts)):
        try:
            r = subprocess.run(["npm", "view", f"{pkg}", field, "--json"],
                               capture_output=True, text=True, timeout=timeout)
            if r.returncode != 0:
                return None
            try:
                return json.loads(r.stdout)
            except json.JSONDecodeError:
                return r.stdout.strip().strip('"')
        except subprocess.TimeoutExpired as e:
            last_err = e
            if i + 1 < attempts:
                time.sleep(min(5.0 * (i + 1), 15.0))
                continue
    raise RegistryQueryTimeout(f"{pkg} {field} 查询超时（{timeout:.0f}s × {attempts} 次）") from last_err


def wait_for_version(pkg: str, version: str, timeout: float, interval: float) -> tuple:
    """轮询 registry 直到目标版本**存在**。返回 (ok, latest, 该版本是否可见)。

    v0.5.3 实锤：只查 `npm view <pkg> version`（= dist-tag latest）会在传播窗口内
    误判——主包 0.5.3 已经 publish 成功、`<pkg>@0.5.3` 也查得到，但 latest 还指向
    0.5.2，脚本据此宣告发版失败。现在分两个信号：
      · 目标版本可查  → 包确实上线（发布成功）
      · latest 是否已切 → 只是 dist-tag/CDN 传播，晚几秒到几分钟
    任一信号到位都不该判失败；latest 落后只提示，不阻塞。
    """
    deadline = time.time() + timeout
    timeouts = 0
    last_latest, last_specific = None, None
    started = time.time()
    while True:
        try:
            last_latest = _npm_view(pkg, "version")
            last_specific = _npm_view(f"{pkg}@{version}", "version")
        except RegistryQueryTimeout as e:
            # 查询层故障 ≠ 包未发布（S213）：窗口内继续轮询，窗口用尽则交"不可判"
            timeouts += 1
            last_err = e
            last_specific = None
            if time.time() >= deadline:
                raise RegistryQueryTimeout(
                    f"{pkg} 在 {timeout:.0f}s 内始终查询超时（{timeouts} 次）：{e}") from last_err
            time.sleep(interval)
            continue
        specific_ok = str(last_specific) == str(version)
        latest_ok = str(last_latest) == str(version)
        if specific_ok or latest_ok:
            return True, last_latest, specific_ok
        now = time.time()
        if int(now - started) % 30 < interval + 1:
            print(f"  … 等待 {pkg}@{version}（latest={last_latest}，"
                  f"目标版本={'待传播' if not specific_ok else '已可见'}）",
                  file=sys.stderr)
        if now >= deadline:
            return False, last_latest, False
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
    schema = members.get("package/assets/contract/tools.schema.json")
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
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--interval", type=float, default=5)
    ap.add_argument("--skip-tarball", action="store_true",
                    help="只做版本对账（registry 不可拉包时的降级档，需显式指定）")
    a = ap.parse_args()

    failed = False
    indeterminate = False
    for pkg in a.pkg:
        try:
            ok, latest, specific_ok = wait_for_version(pkg, a.version, a.timeout, a.interval)
        except RegistryQueryTimeout as e:
            # 不可判（不是失败）：exit 3，调用方据此不清账、手工复核
            print(f"不可判：{pkg} registry 查询超时——**不是**未发布（{e}）；"
                  f"请稍后手工复核：npm view {pkg}@{a.version} version", file=sys.stderr)
            indeterminate = True
            continue
        if not ok:
            print(f"FAIL: {pkg} 在 {a.timeout:.0f}s 内查不到 {a.version}"
                  f"（latest 仍是 {latest}；publish 回执成功≠已上线，"
                  "检查 staging 2FA / 权限 / 是否被 npm 拒收）",
                  file=sys.stderr)
            failed = True
            continue
        if latest != a.version:
            print(f"OK: {pkg}@{a.version} 已上线（目标版本可查）；"
                  f"dist-tag latest 仍指向 {latest}——属 CDN 传播延迟，稍后自愈")
        else:
            print(f"OK: {pkg}@{a.version} 已上线（latest 已切，轮询确认）")
        if a.skip_tarball:
            continue
        try:
            blob = fetch_tarball(pkg, a.version)
        except RegistryQueryTimeout as e:
            print(f"不可判：{pkg} tarball 地址查询超时（不是内容不符）：{e}", file=sys.stderr)
            indeterminate = True
            continue
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
        return 1
    if indeterminate:
        print("发版终态断言：不可判（registry 查询超时，不是未发布）——"
              "请稍后手工复核，不要据此重发或改版本号。", file=sys.stderr)
        return 3
    print("发版终态断言通过：" + "、".join(f"{p}@{a.version}" for p in a.pkg))
    return 0


if __name__ == "__main__":
    sys.exit(main())