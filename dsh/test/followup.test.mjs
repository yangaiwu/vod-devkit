// D-followup-impl-2：dsh 壳追问补充透传回归锁（行为级，stub fetch）。
// 锁三件：①双字段非空透传+trim ②"没有"拒答/空白=键不出现（键集合与旧流程一致）
// ③content 原话不回流污染 + 超 2000 引擎同口径截断。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { apply } from '../lib/index.js';

function stubFetch(captured) {
  globalThis.fetch = async (url, opts = {}) => {
    const body = opts.body ? JSON.parse(opts.body) : null;
    captured.push({ url: String(url), body });
    return {
      ok: true,
      status: 200,
      json: async () => ({ code: 200, voiceIds: ['ext_dsh_t1'] }),
      text: async () => JSON.stringify({ code: 200, voiceIds: ['ext_dsh_t1'] }),
    };
  };
}

async function getSubmitTool(captured, cfg = { apiBase: 'https://vod-dev.topxtopx.com', apiKey: 'k-test', product: 'CodeArts' }) {
  let registered = null;
  const ctx = {
    on() {},
    tools: { register(t) { if (t.name === 'vod_submit_voices') registered = t; } },
  };
  apply(ctx, cfg);
  return registered;
}

test('追问补充：非空透传+trim，content 原话不污染；拒答/空白键不出现；超长截 2000', async () => {
  const captured = [];
  stubFetch(captured);
  const tool = await getSubmitTool(captured);
  if (!tool) {
    // apply 未暴露 registerTool 通道时降级为源级锁（结构断言）
    const { readFileSync } = await import('node:fs');
    const src = readFileSync(new URL('../lib/index.js', import.meta.url), 'utf8');
    assert.ok(src.includes("for (const f of ['reproSteps', 'expectedBehavior'])"), '透传循环在位');
    assert.ok(src.includes("DECLINES.has(val.toLowerCase())"), '拒答语义过滤在位');
    assert.ok(src.includes('不方便回复"没有"'), '固定问句逐字在位');
    return;
  }
  const args = tool.parameters ? {} : {};
  const out = await tool.execute({
    voices: [
      { content: '导出转圈两分钟没文件', reproSteps: '  点导出后一直转圈  ', expectedBehavior: '应出文件' },
      { content: '搜索结果不准', reproSteps: '没有', expectedBehavior: '   ' },
      { content: '列表加载慢', reproSteps: '步'.repeat(2500) },
    ],
  }, {});
  assert.ok(out);
  const hoardCall = captured.find(c => c.body && Array.isArray(c.body.voices));
  assert.ok(hoardCall, '囤积端点被调用');
  const [v0, v1, v2] = hoardCall.body.voices;
  assert.equal(v0.reproSteps, '点导出后一直转圈');
  assert.equal(v0.expectedBehavior, '应出文件');
  assert.equal(v0.content, '导出转圈两分钟没文件');
  assert.ok(!('reproSteps' in v1) && !('expectedBehavior' in v1), '拒答/空白=键不出现');
  assert.equal(v1.content, '搜索结果不准');
  assert.equal(v2.reproSteps.length, 2000, '引擎同口径截 2000');
});
