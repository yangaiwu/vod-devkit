#!/usr/bin/env node
/**
 * vod-devkit npm 引导器（npx vod-devkit ... 的入口）。
 *
 * 职责：找到 python3（>=3.10）→ 把参数透传给仓内 bin/vod-devkit 安装器。
 * Node 层只是引导（devkit 的 npx 体验同款形态）；全部逻辑在 Python 侧。
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const installer = join(ROOT, 'bin', 'vod-devkit');

const candidates = [process.env.VOD_PYTHON, 'python3', 'python3.12', 'python3.11', 'python3.10', 'python']
  .filter(Boolean);

function findPython() {
  for (const cmd of candidates) {
    const probe = spawnSync(cmd, ['-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'], { stdio: 'ignore' });
    if (probe.status === 0) return cmd;
  }
  return null;
}

const py = findPython();
if (!py) {
  console.error('[vod-devkit] 未找到 Python >= 3.10（尝试过: ' + candidates.join(', ') + '）。');
  console.error('              请安装 Python 3.10+ 或设置 VOD_PYTHON 指向解释器路径。');
  process.exit(1);
}
if (!existsSync(installer)) {
  console.error('[vod-devkit] 安装器缺失: ' + installer);
  process.exit(1);
}

const result = spawnSync(py, [installer, ...process.argv.slice(2)], { stdio: 'inherit' });
process.exit(result.status ?? 1);
