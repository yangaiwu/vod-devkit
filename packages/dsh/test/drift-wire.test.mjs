/**
 * 审查 P1-2：D-drift-1 接线真实性（行为级，不是源码 grep）
 *
 * 修复前三个实锤缺陷：
 *   ① offTopic 没进 parameters，而 buildParameters 产 additionalProperties:false
 *      ⇒ 宿主过滤掉 ⇒ args.offTopic 恒 undefined ⇒ 拉回分支永不触发；
 *   ② drift.buffer 只取 .length 当诊断字段，注释说的"并入 content"从未实现；
 *   ③ drift.test.mjs 第⑥条是源码正则，抓不到上面两条。
 */
import { test } from 'node:test';
import assert from 'node:assert';
import { writeFileSync } from 'node:fs';

const rt = `/tmp/drift-wire-${Date.now()}.json`;
process.env.VOD_DSH_RUNTIME = rt;
const { apply, planDriftHandling } = await import('../lib/index.js');

/** 直接写 runtime 文件（saveRuntime 未导出，不为此改产品代码） */
function setRuntime(obj) {
    writeFileSync(rt, JSON.stringify(obj), 'utf8');
}

/** 伪造引擎：meta 必须先成功（否则归因失败 -32010 早退，根本到不了提交） */
function stubFetch(onVoices) {
    globalThis.fetch = async (url, opts) => {
        const u = String(url);
        let body = {};
        try { body = JSON.parse(opts?.body || '{}'); } catch { body = {}; }
        if (u.includes('/meta')) {
            // 🔴 结构必须照真实响应来：loadMeta 取 `out.data.data || out.data`，
            // 且只有 `products` 非空才缓存/返回（否则退回 emptyMeta）。
            // 只给 productCatalog 不给 products 会静默变空名录 —— 探针坑，不是产品缺陷。
            const payload = {
                products: [
                    { id: 1, name: 'CodeArts' },
                    { id: 2, name: 'VOD' },
                ],
                productCatalog: [
                    { id: 1, name: 'CodeArts' },
                    { id: 2, name: 'VOD' },
                ],
            };
            return {
                ok: true, status: 200,
                // 🔴 http() 用的是 res.text() + JSON.parse，不是 res.json()
                // （见 lib/index.js:311-313）。只给 json() 会让 meta 解析成空 ——
                // 这是本仓第四次踩的"探针桩形状不对"，不是产品缺陷。
                json: async () => ({ data: payload }),
                text: async () => JSON.stringify({ data: payload }),
            };
        }
        if (u.includes('/voices')) return onVoices(body);
        return { ok: true, status: 200, json: async () => ({}), text: async () => '{}' };
    };
}

const reg = new Map();
apply(
    {
        tools: { register: (t) => reg.set(t.name, t) },
        on: () => {}, provide: () => {}, effect: () => {},
        logger: { log() {}, warn() {}, error() {} },
        get: () => undefined, set: () => {},
    },
    { apiBase: 'https://placeholder.invalid' },
);
const submit = reg.get('vod_submit_voices');

/** 取提交批里实际发出去的原话 */
function batchTexts(body) {
    const arr = body?.voices || body?.items || [];
    return arr.map((v) => String(v?.content ?? v?.title ?? ''));
}

/** 会话桩：user 轮原话（🔴 原话必须含产品名——归因只从原话/记忆/绑定取，
 *  不读 args.product；不含产品名会 -32010 早退，测试就到不了提交链路） */
function sessionOf(turns) {
    return {
        agent: {
            session: {
                deriveMessages: () => turns.map((t) => ({
                    role: 'user',
                    content: [{ type: 'text', text: t }],
                })),
            },
        },
    };
}

test('P1-2①：offTopic 已进契约参数（宿主不会把它过滤掉）', () => {
    const p = submit.parameters;
    assert.ok(p.properties.offTopic, 'offTopic 必须在 properties 里，否则宿主过滤后恒 undefined');
    assert.strictEqual(p.properties.offTopic.type, 'boolean');
    assert.deepStrictEqual(p.required, ['voices'], 'voices 仍必须是 required（不许被改动波及）');
});

test('P1-2②：planDriftHandling 能识别跑题与复位', () => {
    const turns = ['你们这个导出太慢了', '今天天气不错'];
    const before = planDriftHandling({ userTurns: turns, pulledBack: false, offTopic: true });
    assert.strictEqual(before.shouldPullBack, true, '首次跑题应拉回');
    assert.strictEqual(before.reason, 'off-topic-first-pull');

    const again = planDriftHandling({ userTurns: turns, pulledBack: true, offTopic: true });
    assert.strictEqual(again.shouldPullBack, false, '已拉回过就不再追问（只拉一次）');
    assert.strictEqual(again.reason, 'off-topic-already-pulled');

    const back = planDriftHandling({ userTurns: turns, pulledBack: true, offTopic: false });
    assert.strictEqual(back.resume, true, '曾跑题且现在不跑题 = 回到话题，应续用缓冲');
    assert.ok(back.buffer.includes(turns[0]), '缓冲里必须含跑题期间那条像反馈的原话');
});

test('P1-2③：buffer 只收像反馈的原话，不吞整个跑题内容', () => {
    const r = planDriftHandling({
        userTurns: ['今天天气不错', '帮我订个外卖', '这个页面加载要等半分钟'],
        pulledBack: false, offTopic: true,
    });
    assert.ok(r.buffer.includes('这个页面加载要等半分钟'), '含量级描述的反馈必须留底');
    assert.ok(!r.buffer.includes('今天天气不错'), '纯跑题不该进缓冲（否则污染语料）');
    assert.ok(!r.buffer.includes('帮我订个外卖'), '非反馈意图不该进缓冲');
});

test('P1-2④：resume 时 buffer 真的并入提交批（不是只报个数）', async () => {
    let sent = null;
    stubFetch((body) => {
        sent = body;
        const n = (body?.voices || body?.items || []).length;
        const resp = { voiceIds: Array.from({ length: n }, (_, i) => `VD${i}`) };
        return {
            ok: true, status: 200,
            json: async () => resp,
            text: async () => JSON.stringify(resp),
        };
    });

    // 曾跑题已拉回 + 本批只提交一条新反馈 → 跑题期那条应被补进来
    setRuntime({ drift_pulled_back: true });

    const out = await submit.execute(
        { voices: [{ content: 'CodeArts 提交按钮点了没反应' }], confirmed: true, offTopic: false },
        sessionOf(['CodeArts 这个导出太慢了吧', 'CodeArts 提交按钮点了没反应']),
    );

    const texts = batchTexts(sent);
    assert.ok(
        texts.some((t) => t.includes('导出太慢')),
        `跑题期原话必须并入提交批，实际提交=${JSON.stringify(texts)}`,
    );
    assert.strictEqual(
        texts.filter((t) => t.includes('提交按钮点了没反应')).length, 1,
        '本批已有的原话不得重复补入（防重复入库）',
    );
    assert.ok(!out.error, `提交不应报错，实际=${JSON.stringify(out).slice(0, 200)}`);
});

test('P1-2⑤：shouldPullBack 那一轮不擅自并入（还没确认，不替用户决定）', async () => {
    let sent = null;
    stubFetch((body) => {
        sent = body;
        const resp = { voiceIds: ['VX'] };
        return { ok: true, status: 200, json: async () => resp, text: async () => JSON.stringify(resp) };
    });
    setRuntime({ drift_pulled_back: false });   // 尚未拉回过

    await submit.execute(
        { voices: [{ content: 'CodeArts 这个报错老是出现' }], confirmed: true, offTopic: true },
        sessionOf(['算了先不聊这个，说个别的', 'CodeArts 这个报错老是出现']),
    );

    const texts = batchTexts(sent);
    assert.ok(texts.length > 0, '本轮应正常提交（跑题判定不应拦截提交本身）');
    assert.ok(!texts.some((t) => t.includes('算了先不聊这个')), '跑题原话在此轮不得被自动提交');
});