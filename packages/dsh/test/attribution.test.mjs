// 归因链（D-attrib-B）：dsh 壳与 vod_mcp/attribution.py 同口径。
// 锁四件：①字面证据唯一命中 → 主键 id ②多产品歧义 → 不带 product（UNKNOWN）
// ③误命中反例（文件名/小写 obs/词内包含）④部署 config 只在无证据时兜底。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// 隔离运行时状态：行为级用例会写 attribution_memory，不能碰真实 dsh/data/runtime.json
process.env.VOD_DSH_RUNTIME = join(mkdtempSync(join(tmpdir(), 'dsh-attr-')), 'runtime.json');

const { buildAliasIndex, matchProducts, attributeProduct, apply } =
  await import('../lib/index.js');

// 线上 meta 真实形态：catalog 名（Maas / 对象存储服务 OBS）≠ 展示名
const META = {
  products: ['AgentArts', 'DataArts', 'MaaS', 'OfficeClaw', 'CodeArts', 'AIShell', 'OBS'],
  catalog: [{ id: 5, name: 'Maas' }, { id: 1, name: 'CodeArts' },
    { id: 261, name: '对象存储服务 OBS' }],
  nameAliases: {
    MAAS: ['MaaS', 'Maas', 'MAAS'],
    CODEARTS: ['码道', 'CodeArts', '软件开发生产线 CodeArts'],
    OBS: ['OBS', '对象存储服务 OBS'],
  },
  aliases: { modelarts: 'maas' },
};

test('字面证据唯一命中 → catalog 主键 id', () => {
  const out = attributeProduct('码道导出转圈两分钟没文件', META);
  assert.equal(out.product, '1');
  assert.equal(out.source, 'user_input');
  assert.equal(out.evidence[0].alias, '码道');
});

test('catalog 名≠展示名仍合并到同一主键（MaaS/OBS 两颗雷）', () => {
  const idx = buildAliasIndex(META);
  const maas = idx.filter((e) => e.product === 'MaaS').map((e) => `${e.alias}=${e.id}`);
  assert.ok(maas.includes('MaaS=5') && maas.includes('Maas=5'), maas.join(','));
  const obs = idx.filter((e) => e.product === 'OBS').map((e) => `${e.alias}=${e.id}`);
  assert.ok(obs.includes('OBS=261') && obs.includes('对象存储服务 OBS=261'), obs.join(','));
  assert.equal(attributeProduct('OBS 上传失败', META).product, '261');
  assert.equal(attributeProduct('modelarts 部署失败', META).product, '5');
});

test('多产品命中 → 歧义，不带 product 且保留全部证据', () => {
  const out = attributeProduct('从 CodeArts 导出到 MaaS 之后打不开', META);
  assert.equal(out.product, null);
  assert.equal(out.source, 'unknown');
  assert.deepEqual([...new Set(out.evidence.map((e) => e.product))].sort(), ['CodeArts', 'MaaS']);
  assert.ok(out.evidence.every((e) => e.reason === 'ambiguous'));
});

test('误命中反例：文件名/词内/小写短名/URL 均不命中', () => {
  for (const text of ['codearts.yaml 配置错了', 'mycodearts 报错',
    '依赖 obs://bucket 路径', 'obs 一直转圈', 'codearts_config 写坏了']) {
    assert.deepEqual(matchProducts(text, buildAliasIndex(META)), [], text);
  }
  // 强形态仍命中
  assert.equal(attributeProduct('对象存储服务 OBS 上传失败', META).product, '261');
});

test('记忆 TTL 与部署先验的回退顺序', () => {
  const mem = { product: '1', productName: 'CodeArts', alias: '码道', snippet: '码道导出慢', at: 1000 };
  const fresh = attributeProduct('导出还是慢', META, { memory: mem, now: 1060 });
  assert.equal(fresh.source, 'memory');
  assert.equal(fresh.product, '1');
  assert.equal(fresh.evidence[0].at, 1000); // 证据可回指历史命中
  const expired = attributeProduct('导出还是慢', META,
    { memory: mem, now: 1000 + 30 * 60 + 1, binding: 'CodeArts' });
  assert.equal(expired.source, 'install_binding');
  assert.equal(expired.product, '1');
  const none = attributeProduct('导出还是慢', META, { memory: mem, now: 1000 + 30 * 60 + 1 });
  assert.equal(none.source, 'unknown');
  assert.equal(none.product, null);
});

function stubFetch(metaBody) {
  const captured = [];
  globalThis.fetch = async (url, opts = {}) => {
    const isMeta = String(url).includes('/external/meta');
    const body = opts.body ? JSON.parse(opts.body) : null;
    captured.push({ url: String(url), body, meta: isMeta });
    const payload = isMeta ? metaBody
      : { code: 200, data: { voiceIds: ['ext_dsh_a1'], statuses: ['new'] } };
    return {
      ok: true, status: 200,
      json: async () => payload,
      text: async () => JSON.stringify(payload),
    };
  };
  return captured;
}

async function submitTool(cfg) {
  let registered = null;
  const ctx = { on() {}, tools: { register(t) { if (t.name === 'vod_submit_voices') registered = t; } } };
  apply(ctx, { apiBase: 'https://vod-dev.topxtopx.com', apiKey: '', ...cfg });
  return registered;
}

test('行为级：提交时按用户原话带主键；歧义/无证据时不带 product', async () => {
  // wire 形态：meta 端点是 productCatalog，不是内部索引用的 catalog
  const captured = stubFetch({ code: 200, data: { ...META, productCatalog: META.catalog } });
  const tool = await submitTool({ product: 'CodeArts' });
  assert.ok(tool, 'vod_submit_voices 已注册');

  // ① 无字面证据 → 部署先验（主键化）
  let out = await tool.execute({ voices: [{ content: '导出转圈两分钟' }] }, {});
  let post = captured.filter((c) => !c.meta && c.body && Array.isArray(c.body.voices)).pop();
  assert.equal(post.body.product, '1');
  assert.equal(out?.data?.productSource ?? out?.productSource, 'install_binding');

  // ② 中文别名命中 → 字面证据压过先验
  out = await tool.execute({ voices: [{ content: '码道导出转圈两分钟' }] }, {});
  post = captured.filter((c) => !c.meta && c.body && Array.isArray(c.body.voices)).pop();
  assert.equal(post.body.product, '1');

  // ③ 双产品歧义 → 不带 product（引擎 UNKNOWN 池）
  out = await tool.execute({ voices: [{ content: '从 CodeArts 导出到 MaaS 之后打不开' }] }, {});
  post = captured.filter((c) => !c.meta && c.body && Array.isArray(c.body.voices)).pop();
  assert.ok(!('product' in post.body), 'UNKNOWN 不带 product 键');
});

test('工具面不存在 product 入参（模型无从自报）', async () => {
  const captured = stubFetch({ code: 200, data: { ...META, productCatalog: META.catalog } });
  const tool = await submitTool({ product: '' });
  const names = JSON.stringify(tool.parameters || {});
  assert.ok(!names.includes('"product"'), names.slice(0, 200));
  const desc = String(tool.description || '');
  assert.ok(desc.includes("user's own words"), '描述已改运行期解析口径');
  assert.ok(!desc.includes('bound at install/deploy time'), '旧口径句必须消失');
});