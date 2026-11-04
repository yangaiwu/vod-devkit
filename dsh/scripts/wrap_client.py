#!/usr/bin/env python3
"""把 esbuild CJS 输出包进 dsh 官方 client factory 模式。

要点（对照官方 dsh-client-ui-attachment 反编译形态）：
- require 延迟到 factory 内执行（react/react/jsx-runtime 由 shell 模块表提供，不 vendor）
- exports.inject = ["slots"]：浏览器半声明注入的客户端服务，缺它内核不激活（实测 web boot 报 entry did not activate）
"""
import os

body = open("/tmp/client-cjs.js").read().strip()
out = (
    'window.__ModuleLoader__.load({\n'
    '  id: "dsh-vod-devkit",\n'
    '  factory: (require) => {\n'
    '    var module = { exports: {} };\n'
    '    var exports = module.exports;\n'
    + body + '\n'
    '    module.exports.inject = ["slots"];\n'
    '    return module.exports;\n'
    '  }\n});\n'
)
d = os.path.join(os.path.dirname(__file__), "..", "lib")
open(os.path.join(d, "client.js"), "w").write(out)
print("client.js", len(out))
