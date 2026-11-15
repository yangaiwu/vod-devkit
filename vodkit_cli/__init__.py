"""installer CLI 实现包（bin/vod-devkit 是入口薄壳）。

对外稳定面（入口与测试都依赖，改动视为破坏性）：
  main / PRESETS / detect_targets / build_info / write_build_info
"""
from vodkit_cli.cli import main
from vodkit_cli.common import PRESETS, build_info, write_build_info
from vodkit_cli.install import detect_targets

__all__ = ["main", "PRESETS", "detect_targets", "build_info", "write_build_info"]
