"""auth 子命令：凭据的唯一写入入口（对齐 devkit `auth init` 的"单一入口"设计）。

为什么需要（D-auth-init-1）：此前换 key 的唯一路径是"删 runtime.json 再重装"——
运维不可解释，也没人能回答"这台机器现在用的是哪把钥匙"。本命令把写 key 收成一个
入口，并把回显固定为**指纹**（绝不打印明文）。

优先级链（写进文档、也在这里实现）：
  环境变量 VOD_JAVA_API_KEY（平台/CI 注入，最高）
  > runtime 里的显式 key（本命令写入）
  > 匿名令牌自动领取（设备绑定，无 key 时首次提交或 vod_auth_ensure 时自动领）。
注意：真正的现读顺序在 net._live()（env 优先于 runtime，D-state-read-1），本命令
只负责"写入 runtime"这一条入口，不改变读取优先级。
"""
import sys

from vod_mcp import msgs
from vod_mcp import net, runtime_state


def _fingerprint(key: str) -> str | None:
    return net._fingerprint(key)


def _current() -> dict:
    return runtime_state._runtime_cfg()


def cmd_auth(args=None):
    action = (getattr(args, "auth_action", "") or "status").strip()
    if action == "status":
        cfg = _current()
        base = cfg.get("java_base") or paths_default_base()
        key = cfg.get("java_key") or ""
        tier = cfg.get("token_tier") or ("key" if key else "anonymous")
        print(f"引擎：{base}")
        if key and tier == "key":
            print(f"key：已配置（指纹 {_fingerprint(key)}）——显式凭据，最高优先级")
        elif key:
            print(f"匿名令牌：已缓存（指纹 {_fingerprint(key)}，档位 {tier}）"
                  "——设备绑定领取，不是显式 key；要换显式 key 用 auth init")
        else:
            print("key：未配置 —— 走匿名令牌自动领取（设备绑定；首次提交或 vod_auth_ensure 时领取）")
        return

    # init：把 key 写进 runtime.json（唯一入口）
    key = (getattr(args, "key", "") or "").strip()
    if not key:
        import os
        key = (os.environ.get("VOD_JAVA_API_KEY") or "").strip()
    if not key:
        print("用法：vod-devkit auth init --key <引擎签发的 key> [--apply]\n"
              "      （也可用环境变量 VOD_JAVA_API_KEY 传；缺省只做校验不写盘）",
              file=sys.stderr)
        sys.exit(2)
    if any(ch.isspace() for ch in key) or len(key) < 8:
        print("[vod-devkit] key 形态可疑（含空白或长度 < 8）——拒绝写入，请核对后重试",
              file=sys.stderr)
        sys.exit(2)
    chk = net.probe_key(key)
    if chk.get("ok") is False:
        # 引擎可达却判拒：写进去只会让后续提交全 401，当场拒
        print(f"[vod-devkit] 引擎判该 key 无效（{chk.get('reason')}，指纹 "
              f"{chk.get('fingerprint')}）——未写入。请核对/续期后重试。", file=sys.stderr)
        sys.exit(2)
    if chk.get("ok") is None:
        print(f"warn: 引擎不可达（{chk.get('reason')}），无法验证 key 有效性；"
              "仍可写入，后续提交会由引擎最终判定", file=sys.stderr)
    fp = _fingerprint(key)
    if not getattr(args, "apply", False):
        print(f"将写入 key（指纹 {fp}）到 {runtime_state._runtime_path()}；"
              f"未写盘——加 --apply 生效（{msgs.after('使用新 key')}）")
        return
    runtime_state._runtime_update({"java_key": key, "token_tier": "key"})
    back = _current().get("java_key")
    if back != key:
        raise SystemExit(f"[vod-devkit] 写入后读回不一致：{runtime_state._runtime_path()}")
    print(f"已写入 key（指纹 {fp}）：{runtime_state._runtime_path()}（0600；{msgs.effective()}）")


def paths_default_base() -> str:
    from vod_mcp import DEFAULT_JAVA_BASE
    return DEFAULT_JAVA_BASE
