// S241：旧单条提交链（/external/voice/submit）已从 dsh 壳彻底移除——
// 囤积端点 POST /external/voices 是唯一提交路径（引擎已上线，无需 404 回落）。
// 锁口径：代码行不得出现旧链路径/常量，也不得保留 404 回落分支。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const src = readFileSync(join(ROOT, 'lib', 'index.js'), 'utf8');
// 注释允许解释「已移除」，判定只看代码行
const codeLines = src.split('\n').filter((ln) => {
  const t = ln.trim();
  return t && !t.startsWith('//') && !t.startsWith('*') && !t.startsWith('/*');
});

test('S241: 旧单条链常量 SUBMIT_PATH 已删除', () => {
  assert.ok(!src.includes('SUBMIT_PATH'), '源码仍含 SUBMIT_PATH');
});

test('S241: 代码行不再引用 /external/voice/submit', () => {
  const hits = codeLines.filter((ln) => ln.includes('voice/submit'));
  assert.deepEqual(hits, [], `仍有代码行走旧单条链：\n${hits.join('\n')}`);
});

test('S241: 不保留 404 回落判定（status !== 404）', () => {
  const hits = codeLines.filter((ln) => ln.includes('status !== 404'));
  assert.deepEqual(hits, [], `仍有 404 回落分支：\n${hits.join('\n')}`);
});

test('S241: 提交只打囤积端点（主调用 + 401 重试两处）', () => {
  const calls = codeLines.filter((ln) => ln.includes("http('POST'") || ln.includes('http("POST"'));
  const hoard = calls.filter((ln) => ln.includes('HOARD_PATH'));
  const other = calls.filter((ln) => !ln.includes('HOARD_PATH') && !ln.includes('TOKEN_PATH'));
  assert.equal(hoard.length, 2, `囤积端点调用应为 2 处（主+401重试），实得 ${hoard.length}`);
  assert.deepEqual(other, [], `存在非囤积端点的 POST 调用：\n${other.join('\n')}`);
});
