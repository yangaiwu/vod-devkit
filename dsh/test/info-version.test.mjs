// 回归：vod_devkit_info 的 version 必须来自 package.json（PKG_VERSION），
// 不能写死。2026-11-12 真机实锤：写死 '0.1.0' 导致会话里回执永远报旧版本。
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert';

const here = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(join(here, '..', 'package.json'), 'utf8'));
const src = readFileSync(join(here, '..', 'lib', 'index.js'), 'utf8');

assert.ok(/version:\s*PKG_VERSION/.test(src), "info 工具必须用 PKG_VERSION 报版本");
assert.ok(!/version:\s*'0\.1\.0'/.test(src), "不许写死版本号");
assert.match(pkg.version, /^\d+\.\d+\.\d+$/, "包版本格式异常");
console.log('ok:', pkg.version);
