// S243：dsh 壳与 vod_mcp 语义收敛的三处补齐。
//
// 背景：S241 删老链后，dsh 侧与 Python 侧仍有语义分叉——
//   ① 契约 tools.schema.json 里 vod_submit_voices.output.required 含 echo，dsh 回执没有
//   ② 契约参数有 tags（采集层三分类），dsh 工具面不存在，分类信息全丢
//   ③ 缺产品时 Python 会先问一次（D-product-ask-1），dsh 直接裸提交进 UNKNOWN 池
// 本文件锁住三项补齐，且锁住「歧义不追问」「有绑定不追问」两条边界。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { apply, __clearCaches } from '../lib/index.js';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const REPO = dirname(dirname(ROOT));
const src = readFileSync(join(ROOT, 'lib', 'index.js'), 'utf8');
const contract = JSON.parse(
  readFileSync(join(REPO, 'assets', 'contract', 'tools.schema.json'), 'utf8')
);

const META_WIRE = {
  code: 200,
  data: {
    products: ['CodeArts', 'MaaS', 'OBS'],
    productCatalog: [
      { id: '1', name: 'CodeArts' },
      { id: '2', name: 'MaaS' },
      { id: '3', name: 'OBS' },
    ],
    aliases: {},
    nameAliases: {},
  },
};

function stubFetch({ voiceIds = ['ext_t1'], problemTypes = ['产品缺陷', '功能需求', '体验改进'] } = {}) {
  const captured = [];
  globalThis.fetch = async (url, opts = {}) => {
    const u = String(url);
    const body = opts.body ? JSON.parse(opts.body) : null;
    if (u.includes('/external/meta')) {
      captured.push({ meta: true, url: u });
      const pid = new URL(u).searchParams.get('productId');
      const data = pid ? { ...META_WIRE.data, problemTypes } : META_WIRE.data;
      const t = JSON.stringify({ code: 200, data });
      return { ok: true, status: 200, json: async () => JSON.parse(t), text: async () => t };
    }
    if (u.includes('/external/voices')) {
      captured.push({ body });
      const t = JSON.stringify({ code: 200, voiceIds });
      return { ok: true, status: 200, json: async () => JSON.parse(t), text: async () => t };
    }
    const t = '{}';
    return { ok: true, status: 200, json: async () => ({}), text: async () => t };
  };
  return captured;
}

function submitTool(cfg = {}) {
  let reg = null;
  apply({ on() {}, tools: { register(t) { if (t.name === 'vod_submit_voices') reg = t; } } },
    { apiBase: 'https://vod-dev.topxtopx.com', apiKey: 'k'.repeat(40), ...cfg });
  return reg;
}

const payloadOf = (o) => o?.structuredContent ?? o;
const lastPost = (cap) => cap.filter((c) => c.body && Array.isArray(c.body.voices)).pop();

test('S243-①: 回执带契约必填的 echo（原话回显，禁改写）', async () => {
  // 契约层：echo 仍是 output.required
  const out = contract.tools.vod_submit_voices.output;
  assert.ok(out.required.includes('echo'), '契约层不再要求 echo，本测试前提失效');

  __clearCaches();
  process.env.VOD_DSH_RUNTIME = `/tmp/s243-echo-${Date.now()}.json`;
  stubFetch();
  const tool = submitTool({ product: 'CodeArts' });
  const r = payloadOf(await tool.execute({ voices: [{ content: '导出按钮点不动，报错了' }] }, {}));

  assert.ok(r.echo, '回执缺 echo');
  assert.equal(r.echo.requiresUserEcho, true);
  assert.equal(r.echo.contents.length, 1);
  assert.equal(r.echo.contents[0].content, '导出按钮点不动，报错了', 'echo 必须是原话逐字');
  assert.equal(r.echo.contents[0].voiceId, 'ext_t1');
  assert.ok(/禁止改写/.test(r.echo.instruction), 'instruction 必须禁改写');
});

test('S243-②: tags 按产品白名单过滤，脏值丢弃并报 invalidTags', async () => {
  __clearCaches();
  process.env.VOD_DSH_RUNTIME = `/tmp/s243-tags-${Date.now()}.json`;
  const cap = stubFetch({ problemTypes: ['产品缺陷', '功能需求'] });
  const tool = submitTool({ product: 'CodeArts' });
  const r = payloadOf(await tool.execute({
    voices: [{
      content: '列表加载特别慢',
      tags: ['problem_type:产品缺陷', 'problem_type:不存在的分类', 'custom:原样保留'],
    }],
  }, {}));

  // 白名单必须按 productId 取（引擎契约：problemTypes 按产品下发）
  assert.ok(cap.some((c) => c.meta && /productId=1/.test(c.url)), '未按 productId 拉 problemTypes');

  const tags = lastPost(cap).body.voices[0].tags;
  assert.deepEqual(tags, ['problem_type:产品缺陷', 'custom:原样保留'], '白名单外值应丢弃、非分类 tag 应原样保留');
  assert.deepEqual(r.invalidTags, [{ index: 0, tags: ['problem_type:不存在的分类'] }]);
});

test('S243-②b: tags 白名单取不到时不误杀（不过滤）', async () => {
  __clearCaches();
  process.env.VOD_DSH_RUNTIME = `/tmp/s243-tags2-${Date.now()}.json`;
  const cap = stubFetch({ problemTypes: [] });   // 该产品无分类 → 空集
  const tool = submitTool({ product: 'CodeArts' });
  await tool.execute({ voices: [{ content: '导入失败', tags: ['problem_type:任意值'] }] }, {});
  assert.deepEqual(lastPost(cap).body.voices[0].tags, ['problem_type:任意值'], '白名单为空时不得误杀');
});

test('S243-③: 缺产品先问一次（不裸提交），超 2 次终止', async () => {
  __clearCaches();
  process.env.VOD_DSH_RUNTIME = `/tmp/s243-ask-${Date.now()}.json`;
  const cap = stubFetch();
  const tool = submitTool({ product: '' });   // 无 config 绑定
  const args = { voices: [{ content: '这个功能不太好用' }] };

  const r1 = payloadOf(await tool.execute(args, {}));
  assert.equal(r1.needsProductAsk, true, '缺产品应返回 needsProductAsk');
  assert.equal(r1.code, -32010);
  assert.equal(cap.filter((c) => c.body).length, 0, '追问时不得提交');
  assert.ok(/CodeArts（1）/.test(r1.error), '错误里应带候选供模型问用户');

  const r2 = payloadOf(await tool.execute(args, {}));
  assert.equal(r2.askFailures, 2);
  const r3 = payloadOf(await tool.execute(args, {}));
  assert.ok(/别再问了/.test(r3.error), '第 3 次应明确终止');
});

test('S243-③b: 有 config 绑定 / 多产品歧义时不追问', async () => {
  __clearCaches();
  process.env.VOD_DSH_RUNTIME = `/tmp/s243-ask2-${Date.now()}.json`;

  let cap = stubFetch();
  let tool = submitTool({ product: 'CodeArts' });
  let r = payloadOf(await tool.execute({ voices: [{ content: '这个功能不太好用' }] }, {}));
  assert.ok(!r.needsProductAsk, '有绑定不该追问');
  assert.equal(lastPost(cap).body.product, '1');

  __clearCaches();
  cap = stubFetch();
  tool = submitTool({ product: 'CodeArts' });
  r = payloadOf(await tool.execute({ voices: [{ content: '从 CodeArts 导出到 MaaS 之后打不开' }] }, {}));
  assert.ok(!r.needsProductAsk, '歧义不该追问（引擎 UNKNOWN 池接得住）');
  assert.ok(!('product' in lastPost(cap).body), '歧义时不带 product');
});

test('S243: 工具描述不再教「已暂存」且声明 needsProductAsk 处理方式', () => {
  assert.ok(!/e\.g\. 已暂存/.test(src), '工具描述仍在教失败时说已暂存');
  assert.ok(src.includes('NEVER say 已暂存'), '工具描述未禁止谎报暂存');
  assert.ok(src.includes('needsProductAsk'), '工具描述未说明追问回执怎么处理');
  assert.ok(!src.includes('NEVER ask or invent a product'), '旧的「永不追问产品」约束应已更新');
});

test('S243-①b: 契约必填 echo 在所有「非追问」回执里都在（成功/失败/空批）', async () => {
  // 回归锁：echo 是 output.required，只补成功路径不够——失败与空批回执同样要带，
  // 否则宿主按 schema 校验会拿到不合法回执（2026-11-18 复查发现的遗漏）。
  const cases = [
    { name: '成功', stub: () => stubFetch(), cfg: { product: 'CodeArts' }, args: { voices: [{ content: '导出报错' }] } },
    { name: '失败(404)', stub: () => {
        globalThis.fetch = async () => {
          const t = JSON.stringify({ message: 'nf' });
          return { ok: false, status: 404, json: async () => JSON.parse(t), text: async () => t };
        };
        return [];
      }, cfg: { product: 'CodeArts' }, args: { voices: [{ content: '导出报错' }] } },
    { name: '空批(全部被拒)', stub: () => stubFetch(), cfg: { product: 'CodeArts' },
      args: { voices: [{ content: '' }, { content: '   ' }] } },
  ];
  for (const cs of cases) {
    __clearCaches();
    process.env.VOD_DSH_RUNTIME = `/tmp/s243-echo-${cs.name}-${Date.now()}-${Math.random()}.json`;
    cs.stub();
    const tool = submitTool(cs.cfg);
    const r = payloadOf(await tool.execute(cs.args, {}));
    assert.ok(r.echo, `${cs.name} 回执缺 echo`);
    assert.equal(typeof r.echo.requiresUserEcho, 'boolean', `${cs.name}: requiresUserEcho 必须是布尔`);
    assert.ok(Array.isArray(r.echo.contents), `${cs.name}: contents 必须是数组`);
    if (cs.name !== '成功') {
      assert.equal(r.echo.requiresUserEcho, false, `${cs.name}: 未收录时不得要求回显`);
    }
  }
});
