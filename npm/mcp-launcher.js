#!/usr/bin/env node
/**
 * vod-devkit-mcp —— 宿主配置里的 MCP 启动入口（npx 形态）。
 *
 * 为什么要有它（D-interpreter-1）：
 *   历史配置写的是绝对解释器路径（sys.executable）+ 载荷里的 server.py。
 *   解释器一旦落在缓存/临时目录（0.5.45 事故：scratch venv 被 prune），
 *   11 个宿主同时起不来，而 doctor 看起来全绿。
 *   本启动器让配置只写 `npx -y -p vod-devkit@<ver> vod-devkit-mcp`：
 *   解释器与载荷在**每次启动时**解析，缺了能重新解析，而不是写死一份。
 *
 * 解析顺序（都可覆盖）：
 *   python  VOD_PYTHON → python3 → python3.13/3.12/3.11/3.10 → python（≥3.10 才接受）
 *   载荷    VOD_DEVKIT_PAYLOAD → ~/.vod-devkit/payloads/<本包版本>/vod_mcp/server.py
 *           → 该版本缺失时退到 payloads/ 下最新版本
 */
import { spawn } from 'node:child_process';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import os from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG_VERSION = (() => {
  try {
    return JSON.parse(readFileSync(join(HERE, '..', 'package.json'), 'utf8')).version;
  } catch {
    return null;
  }
})();

const PY_CANDIDATES = ['python3', 'python3.13', 'python3.12', 'python3.11', 'python3.10', 'python'];
const MIN_MINOR = 10;

function fail(msg, code = 78) {
  process.stderr.write(`[vod-devkit-mcp] ${msg}\n`);
  process.exit(code); // 78 = EX_CONFIG：环境/配置问题，不是崩溃
}

function payloadRoot() {
  const envHome = process.env.VOD_DEVKIT_STATE_HOME;
  const base = envHome || join(os.homedir(), '.vod-devkit');
  return join(base, 'payloads');
}

function resolvePayload() {
  if (process.env.VOD_DEVKIT_PAYLOAD) {
    if (existsSync(process.env.VOD_DEVKIT_PAYLOAD)) return process.env.VOD_DEVKIT_PAYLOAD;
    fail(`VOD_DEVKIT_PAYLOAD 指向的文件不存在：${process.env.VOD_DEVKIT_PAYLOAD}`);
  }
  const root = payloadRoot();
  const serverOf = (ver) => join(root, ver, 'vod_mcp', 'server.py');
  if (PKG_VERSION && existsSync(serverOf(PKG_VERSION))) return serverOf(PKG_VERSION);
  let versions = [];
  try {
    versions = readdirSync(root).filter((d) => /^\d+\.\d+\.\d+/.test(d));
  } catch {
    versions = [];
  }
  versions.sort((a, b) => {
    const pa = a.split('.').map(Number);
    const pb = b.split('.').map(Number);
    for (let i = 0; i < 3; i += 1) if (pa[i] !== pb[i]) return pb[i] - pa[i];
    return 0;
  });
  for (const v of versions) if (existsSync(serverOf(v))) return serverOf(v);
  fail(
    `找不到载荷（已找 ${PKG_VERSION || '<未知版本>'} 及 ${root} 下的其他版本）。` +
      '请重跑 install，或用 VOD_DEVKIT_PAYLOAD=/abs/path/vod_mcp/server.py 指定。',
  );
}

function probePython(name) {
  return new Promise((resolve) => {
    const p = spawn(name, ['-c', "import sys;print('%d.%d'%sys.version_info[:2])"], {
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    let out = '';
    p.stdout.on('data', (d) => {
      out += d;
    });
    p.on('error', () => resolve(null));
    p.on('close', (code) => {
      const m = out.trim().match(/^(\d+)\.(\d+)$/);
      if (code !== 0 || !m) return resolve(null);
      const [maj, min] = [Number(m[1]), Number(m[2])];
      if (maj < 3 || (maj === 3 && min < MIN_MINOR)) return resolve(null);
      return resolve({ name, version: out.trim() });
    });
  });
}

async function main() {
  const payload = resolvePayload();
  const candidates = [process.env.VOD_PYTHON, ...PY_CANDIDATES].filter(Boolean);
  let picked = null;
  for (const c of candidates) {
    if (!picked) picked = await probePython(c);
  }
  if (!picked) {
    fail(
      `找不到 Python ≥ 3.${MIN_MINOR}（试过：${candidates.join(', ')}）。` +
        '装一个，或用 VOD_PYTHON=/abs/path/python3 指定。',
    );
  }
  if (process.env.VOD_DEVKIT_LAUNCHER_DEBUG === '1') {
    process.stderr.write(`[vod-devkit-mcp] launcher: ${picked.name} (${picked.version}) → ${payload}\n`);
  }
  const child = spawn(picked.name, [payload], { stdio: 'inherit', env: process.env });
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
    process.on(sig, () => {
      try {
        child.kill(sig);
      } catch {
        /* 子进程已退出 */
      }
    });
  }
  child.on('error', (e) => fail(`无法启动 ${picked.name}：${e.message}`));
  child.on('exit', (code, sig) => process.exit(sig ? 1 : code ?? 0));
}

main().catch((e) => fail(`启动失败：${e && e.message ? e.message : e}`, 1));