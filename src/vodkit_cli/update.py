"""update 子命令：git fetch/ff 拉取 + build-info 重烧 + 版本跳过状态。"""
import subprocess
import sys

from vodkit_cli import common


def cmd_update(args=None):
    """更新：git fetch 比较 origin/main，落后则 ff 拉取并重烧 build-info。

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
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=common.ROOT,
                           capture_output=True, text=True).stdout.strip()
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=common.ROOT,
                            capture_output=True, text=True).stdout.strip()
    if local == remote:
        print(f"已是最新（{local[:12]}）")
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
    print("  并重启 agent 会话")
