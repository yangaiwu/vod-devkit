// Python ↔ dsh(JS) 归因对账（F1）：与 tests/test_attribution_parity.py 共用一份 fixture。
//
// 2026-11-15 实测漂移两处（本文件就是防它们复发）：
//  · 「maas」小写：Python 从登记名派生大小写变体命中，JS 未派生 → UNKNOWN
//  · 「码道」：Python 有 BRAND_ALIASES 品牌俗称表，JS 缺 → UNKNOWN
// 依赖：dsh/node_modules（@deepseek-ai/schemastery 等），缺失时本用例无法装载主模块。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

process.env.VOD_DSH_RUNTIME = join(mkdtempSync(join(tmpdir(), 'dsh-parity-')), 'runtime.json');

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(HERE, '..', '..', 'tests', 'fixtures', 'attribution_parity.json');

const { attributeProduct } = await import('../lib/index.js');
const fx = JSON.parse(readFileSync(FIXTURE, 'utf8'));

test('fixture 覆盖实测漂移过的两种写法（大小写变体 / 品牌俗称）', () => {
  const texts = fx.cases.map((c) => c.text);
  assert.ok(texts.some((t) => t.toLowerCase().includes('maas') && t.trim() !== 'MaaS'),
    '缺「小写 maas」用例');
  assert.ok(texts.some((t) => t.includes('码道')), '缺「码道」用例');
});

for (const c of fx.cases) {
  test(`JS 侧归因与 fixture 一致：${c.text.slice(0, 24)}`, () => {
    const got = attributeProduct(c.text, fx.meta);
    assert.deepEqual(
      { product: got.product ?? null, productName: got.productName ?? null, source: got.source },
      { product: c.expect.product ?? null, productName: c.expect.productName ?? null, source: c.expect.source },
    );
  });
}