"""CLI 装配：argparse 子命令表 + serve 直通 + 分派。"""
import argparse
import os
import sys

from vodkit_cli import (auth_cmd, common, doctor, install, packs_cmd, prune_cmd,
                        uninstall, update)


def main():
    # `serve` 后的参数整体透传给 MCP server（argparse 的 REMAINDER 会把
    # --transport 当成未知参数拦下，devkit 的二进制本身就是 server，同形处理）
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        # 显式声明这份副本的根（paths.py 读 VOD_DEVKIT_ROOT）：插件/载荷根
        # 不总是"CLI 所在包根"，隐式相对深度正是此前副本装载失败的原因。
        from vod_mcp import paths as _paths
        os.execve(sys.executable,
                  [sys.executable, str(_paths.SRC_ROOT / "vod_mcp" / "server.py"), *sys.argv[2:]],
                  {**os.environ,
                   "VOD_DEVKIT_SRC_ROOT": str(_paths.SRC_ROOT),
                   "VOD_DEVKIT_DIST_ROOT": str(_paths.DIST_ROOT),
                   "VOD_DEVKIT_ROOT": str(_paths.DIST_ROOT)})
    ap = argparse.ArgumentParser(prog="vod-devkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("install")
    sp.add_argument("--target", default="auto",
                    help="hermes|opencode|codeartsdoer|codeartswork|codex|codex-desktop|dsh|workbuddy|atomcode|openclaw|officeace|generic|all|auto"
                         "（all=所有探测到的宿主，缺 CLI 的跳过；默认探测）")
    sp.add_argument("--preset", default="collect", choices=list(common.PRESETS),
                    help="collect=对外默认（采集者）；full=内部全量")
    sp.add_argument("--api-base", default="http://127.0.0.1:8000")
    sp.add_argument("--java-api-base", default=None,
                    help="VOD 平台地址（缺省=https://vod-dev.topxtopx.com，勿用回环默认）")
    sp.add_argument("--packs", default="", help="显式覆盖 preset（逗号分隔）")
    sp.add_argument("--mcp-launcher", default="npx", choices=["npx", "python", "auto"],
                    help="MCP 启动形态：npx=配置写 `npx -y -p vod-devkit@<ver> vod-devkit-mcp`"
                         "（启动时解析解释器/载荷，默认）；python=绝对解释器+载荷脚本（旧形态）；"
                         "auto=有 node 用 npx，否则 python。dsh/officeace/codex 本轮仍用 python")
    sp.add_argument("--ack-suspension", action="store_true",
                     help="确认解除 codex 采集熔断（恢复门禁逃生口，D-codex-circuit-breaker-1）")
    sp.add_argument("--product", default="",
                    help="归因绑定：本 agent 服务的产品（codearts/aishell 等；采集反馈默认归属）")
    sp.add_argument("--distribution", default="devkit", choices=["devkit", "preset"],
                    help="devkit=开发/运维自装（默认）；preset=产品随 agent 分发（禁 key 随包/"
                         "禁自更新/客户机首启重生成状态）")
    sp.add_argument("--profile", dest="dsh_profile", default="",
                    help="dsh 专用：profile 名（--target dsh 时必填）")
    sp.add_argument("--mcp-url", default="",
                    help="远程 attach 模式：宿主 MCP 配置指向该 Streamable HTTP 端点"
                         "（hermes/opencode/codex 支持；dsh 本轮只支持本地形态：工具面走 MCP stdio，远程 attach 待开）")
    sp.add_argument("--mcp-token", default="",
                    help="远程 attach 的身份（也可用 env VOD_MCP_TOKEN）：默认可选——"
                         "给了就用请求头 Bearer，不给则走远程 server 侧机器级匿名令牌")
    sp.add_argument("--mcp-config", default="",
                    help="通用宿主（--target generic）的 MCP 配置文件路径；不给则只打印可粘贴片段")
    sp.add_argument("--skills-only", action="store_true",
                    help="只装技能，不动宿主 MCP 配置（MCP 已由别处/手工注册时用）")
    sp.add_argument("--no-local-ledger", action="store_true",
                    help="关闭本地提交账本（企业数据驻留要求；vod_list_submitted 将不可用）")
    sp.add_argument("--refresh-product-catalog", action="store_true",
                    help="强制向引擎重拉产品名录（默认命中 state 里 7 天内的缓存，省令牌配额）")
    sp.set_defaults(fn=install.cmd_install)
    for name, fn in (("status", doctor.cmd_status), ("doctor", doctor.cmd_doctor),
                     ("verify", doctor.cmd_verify), ("update", update.cmd_update),
                     ("uninstall", uninstall.cmd_uninstall),
                     ("explain", doctor.cmd_explain),
                     ("detect", doctor.cmd_detect),
                     ("version", packs_cmd.cmd_version)):
        s = sub.add_parser(name)
        if name == "explain":
            s.add_argument("text", nargs="+", help="错误文案或错误码（-32010 等）")
        if name == "detect":
            s.add_argument("--path", default="", help="要识别的项目目录（默认当前目录）")
        if name in ("status", "doctor", "uninstall"):
            # 多宿主账本（installs[]）里挑一个宿主看/摘；缺省=全部行
            s.add_argument("--target", default="",
                           help="只看该宿主的安装行（缺省=全部）")
        if name == "uninstall":
            s.add_argument("--clean-global", action="store_true",
                           dest="clean_global",
                           help="一并清载荷残留与 npx 缓存里的旧副本（逐条打印，只删认得的）")
        if name == "update":
            s.add_argument("--skip", action="store_true",
                           help="跳过当前 registry latest 的提醒（只压这一个版本，"
                                "下个版本仍提醒；不提供永久静音）")
            s.add_argument("--clear-skip", action="store_true",
                           help="撤销版本跳过设置，恢复正常提醒")
        s.set_defaults(fn=fn)
    sp_packs = sub.add_parser("packs", help="能力包启用面：status | enable | disable | all")
    sp_packs.add_argument("packs_action", nargs="?", default="status",
                          choices=["status", "enable", "disable", "all"])
    sp_packs.add_argument("ids", nargs="?", default="",
                          help="enable/disable 的包 id（逗号分隔，如 core,collect）")
    sp_packs.add_argument("--target", default="", help="只作用于该宿主（缺省=全部）")
    sp_packs.add_argument("--apply", action="store_true",
                          help="真正写盘（缺省只报告将改什么；core 强制包含）")
    sp_packs.set_defaults(fn=packs_cmd.cmd_packs)
    sp_auth = sub.add_parser("auth", help="凭据：status | init（写 runtime.json 的唯一入口）")
    sp_auth.add_argument("auth_action", nargs="?", default="status",
                         choices=["status", "init"])
    sp_auth.add_argument("--key", default="", help="引擎签发的 key（也可用 env VOD_JAVA_API_KEY）")
    sp_auth.add_argument("--apply", action="store_true",
                         help="真正写盘（缺省只校验并显示指纹）")
    sp_auth.set_defaults(fn=auth_cmd.cmd_auth)
    def _prune(a):
        """cmd_prune 返回退出码（0=干净/no-op，1=有删除失败，2=参数/确认问题）。"""
        sys.exit(prune_cmd.cmd_prune(a))

    sp_prune = sub.add_parser("prune", help="显式清理旧载荷（默认 dry-run；二次确认）")
    sp_prune.add_argument("--payloads", action="store_true",
                          help="清理旧载荷版本（当前唯一的清理对象）")
    sp_prune.add_argument("--keep", type=int, default=0,
                          help="额外保留最新的 N 份旧载荷（默认 0）")
    sp_prune.add_argument("--apply", action="store_true",
                          help="真正删除（缺省只打印清单，dry-run 优先）")
    sp_prune.add_argument("--yes", action="store_true",
                          help="非交互环境确认删除（交互式会再问一次 y/N）")
    sp_prune.set_defaults(fn=_prune)
    sub.add_parser("build-info").set_defaults(fn=lambda a: common.write_build_info(strict=False))

    def _serve(a):
        """MCP server 入口（codex 插件 .mcp.json 与远程面共用）。

        透传参数：`vod-devkit serve --transport remote --port 9528` 即起 HTTP 面
        （与 huaweicloud-devkit 的 `--transport remote` 同形）。

        DEP-04：**必须与 main() 的 serve 前置分支同源**——server.py 是代码，在
        SRC_ROOT 下；common.ROOT 是分发根（仓根/载荷根），拿它拼 `vod_mcp/server.py`
        在仓内形态就指到不存在的路径（实测 /home/.../vod-devkit/vod_mcp/server.py）。
        两条分支的 env 也统一成同一组，避免只有一条路径声明了根。
        """
        from vod_mcp import paths as _paths
        extra = list(getattr(a, "server_args", []) or [])
        os.execve(sys.executable,
                 [sys.executable, str(_paths.SRC_ROOT / "vod_mcp" / "server.py"), *extra],
                  {**os.environ,
                   "VOD_DEVKIT_SRC_ROOT": str(_paths.SRC_ROOT),
                   "VOD_DEVKIT_DIST_ROOT": str(_paths.DIST_ROOT)})
    sp_serve = sub.add_parser("serve", help="启动 MCP server（默认 stdio；"
                                            "--transport remote 起 Streamable HTTP）")
    sp_serve.add_argument("server_args", nargs=argparse.REMAINDER,
                          help="透传给 vod_mcp.server（如 --transport remote --port 9528）")
    sp_serve.set_defaults(fn=_serve)
    args = ap.parse_args()
    args.fn(args)
