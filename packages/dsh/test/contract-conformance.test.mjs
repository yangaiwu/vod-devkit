// 契约一致性门禁：dsh 每个工具的**实际返回**必须满足 tools.schema.json 的 output.required。
//
// 为什么需要这条：S243 修 echo 时只补了成功路径，失败/空批回执仍缺（复查才发现）；
// vod_devkit_info 长期缺 commitSha、vod_list_submitted 返回的是 voices 而契约要
// submissions——三处都是「改一端忘另一端」的同一类病。靠人肉核对反复漏，改由
// 行为级审计兜住：真跑 execute，拿真实回执逐字段校验 required。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { apply, __clearCaches } from '../lib/index.js';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const REPO = dirname(dirname(ROOT));
const contract = JSON.parse(
  readFileSync(join(REPO, 'assets', 'contract', 'tools.schema.json'), 'utf8')
);

function stubFetch() {
  globalThis.fetch = async (url) => {
    const u = String(url);
    let t = '{}';
    if (u.includes('/external/meta')) {
      t = JSON.stringify({ code: 200, data: {
        products: ['CodeArts'],
        productCatalog: [{ id: '1', name: 'CodeArts' }],
        aliases: {}, nameAliases: {},
      } });
    } else if (u.includes('/external/voices')) {
      t = JSON.stringify({ code: 200, voiceIds: ['ext_c1'] });
    }
    return { ok: true, status: 200, json: async () => JSON.parse(t), text: async () => t };
  };
}

function registry(cfg = {}) {
  const reg = {};
  apply({ on() {}, tools: { register(t) { reg[t.name] = t; } } },
    { apiBase: 'https://vod-dev.topxtopx.com', apiKey: 'k'.repeat(40), ...cfg });
  return reg;
}
const P = (o) => o?.structuredContent ?? o;

test('契约门禁: 每个工具的真实回执都满足 output.required', async () => {
  __clearCaches();
  process.env.VOD_DSH_RUNTIME = `/tmp/contract-${Date.now()}.json`;
  stubFetch();
  const reg = registry({ product: 'CodeArts' });
  const args = {
    vod_submit_voices: { voices: [{ content: '导出报错契约校验' }] },
    vod_list_submitted: {},
    vod_devkit_info: {},
    vod_check_update: { skip: true },
    vod_list_skills: {},
    vod_retrieve_skill: { name: 'vod-feedback-collect' },
  };

  const failures = [];
  for (const [name, tool] of Object.entries(reg)) {
    const req = contract.tools[name]?.output?.required || [];
    if (!req.length) continue;
    const out = P(await tool.execute(args[name] ?? {}, {})) || {};
    const missing = req.filter((k) => !(k in out));
    if (missing.length) {
      failures.push(`${name}: 缺 [${missing}]，实际有 [${Object.keys(out)}]`);
    }
  }
  assert.deepEqual(failures, [], `契约 required 未满足：\n${failures.join('\n')}`);
});

test('契约门禁: vod_submit_voices 的 echo 在成功/失败/空批回执里都存在', async () => {
  // 单独锁一遍：这是 S243 复查发现的漏点，三种返回路径都必须带
  const cases = [
    ['成功', async () => { stubFetch(); }, { voices: [{ content: '导出报错' }] }],
    ['失败', async () => {
      globalThis.fetch = async () => {
        const t = JSON.stringify({ message: 'nf' });
        return { ok: false, status: 404, json: async () => JSON.parse(t), text: async () => t };
      };
    }, { voices: [{ content: '导出报错' }] }],
    ['空批', async () => { stubFetch(); }, { voices: [{ content: '' }] }],
  ];
  for (const [label, setup, args] of cases) {
    __clearCaches();
    process.env.VOD_DSH_RUNTIME = `/tmp/contract-echo-${label}-${Date.now()}-${Math.random()}.json`;
    await setup();
    const reg = registry({ product: 'CodeArts' });
    const out = P(await reg.vod_submit_voices.execute(args, {})) || {};
    assert.ok('echo' in out, `${label} 回执缺 echo`);
    assert.equal(typeof out.echo.requiresUserEcho, 'boolean', `${label}: requiresUserEcho 非布尔`);
    assert.ok(Array.isArray(out.echo.contents), `${label}: contents 非数组`);
  }
});
