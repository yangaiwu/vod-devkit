"""update 子命令：git fetch/ff 拉取 + build-info 重烧 + 版本跳过状态。"""
import subprocess
from vod_mcp import msgs
import sys

from vodkit_cli import common


def cmd_update(args=None):
    """更新：git fetch 比较**当前分支**的远端，落后则 ff 拉取并重烧 build-info。

    ARCH-BLD-02：此前硬钉 `origin/main`，而本仓开发主干是 `dev` ⇒ 在 dev 上执行
    `update` 会拿 HEAD 与落后许多个提交的 main 比较，永远判\"有更新\"并把分支
    ff 到 main（等于静默切换主干）。改法同 `release.sh`（`95217f1`）：
    **用 `git rev-parse --abbrev-ref HEAD` 解析当前分支，不硬编码分支名。**

    --skip / --clear-skip（D-devtoolchain-7，对齐 devkit update-skip 裁剪版）：
    只维护「跳过某个版本提醒」的运行时状态，不动代码——所以放在 git 拉取之前返回。
    """
    if getattr(args, "skip", False) or getattr(args, "clear_skip", False):
        from vod_mcp import update_check as uc
        out = uc.check({"clearSkip": True} if getattr(args, "clear_skip", False)
                       else {"skip": True})
        print(out.get("note") or "")
        if out.get("latestVersion"):
            print(f"latest = {out['latestVersion']}（clearSkip=true 可撤销）")
        return
    if common._distribution() == "preset":
        # D-key-guard-3②：产品分发形态插件版本随 agent 发版管理，客户机禁止自更新
        #（绕过产品版本管理=未测试代码进客户现场）
        print("产品分发形态（preset）不支持自更新：插件版本随 agent 发版管理。"
              "如需升级请联系产品提供方发布新版本。")
        return
    subprocess.run(["git", "fetch", "origin", "--tags"], cwd=common.ROOT, capture_output=True)
    # ARCH-BLD-02：分支不硬编码。detached HEAD / 拿不到分支名时拒绝执行，
    # 而不是猜一个 main 出来（错 ff 比不更新更糟）。
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=common.ROOT,
                            capture_output=True, text=True).stdout.strip()
    if not branch or branch == "HEAD":
        print("更新失败：当前处于 detached HEAD 或无法解析分支名，"
              "请先 `git checkout <分支>` 再重试。")
        sys.exit(1)
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=common.ROOT,
                           capture_output=True, text=True).stdout.strip()
    remote = subprocess.run(["git", "rev-parse", f"origin/{branch}"], cwd=common.ROOT,
                            capture_output=True, text=True).stdout.strip()
    if not remote:
        print(f"更新失败：远端没有对应分支 origin/{branch}。")
        sys.exit(1)
    if local == remote:
        print(f"已是最新（{branch} @ {local[:12]}）")
        return
    r = subprocess.run(["git", "pull", "--ff-only"], cwd=common.ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("更新失败（有本地改动阻挡 ff？）：", r.stderr.strip()[:200])
        sys.exit(1)
    print(f"已更新 {local[:12]} → {remote[:12]}")
    common.write_build_info(strict=False)
    print("build-info 已重烧；如需重新安装执行：")
    print(f"  {sys.argv[0]} install --target hermes --preset collect --product <产品名>")
    print(f"  并{msgs.restart_only('agent 会话')}")
