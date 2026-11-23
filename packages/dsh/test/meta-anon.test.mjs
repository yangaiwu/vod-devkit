/**
 * D-meta-anon-1 回归锁：未配 key（默认形态）时，meta 必须先领匿名令牌再重试。
 *
 * 真机实锤（2026-11-18 端到端验证，v0.5.43 dev）：
 *   loadMeta 发生在「提交遇 401 才领令牌」之前 → auth=false → 平台 401
 *   → catch 吞掉 → 名录恒空 → 归因必失败 → needsProductAsk 死循环：
 *   领令牌要提交成功，提交成功要归因成功，归因成功要 meta，meta 要令牌。
 *   后果：默认形态（日志 key=none 是常态）下一条声音都提交不了。
 *
 * 修法与提交侧 i0Anon 重试对称：401 → fetchAnonToken → 带 key 重试一次。
 * 本文件锁住该行为，防回退。
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = 'https://vod.example.test';
const API = '/rest/developer/manager/hdvodmngservice/v1';

// 每个用例独立 runtime，避免账本/记忆串味
process.env.VOD_DSH_RUNTIME = '/tmp/meta-anon-runtime.json';

/** 平台桩：令牌与设备绑定 → 无有效 auth 一律 401。（内联实现，勿改函数封装） */
const platformLog = [];
const validTokens = new Set();
let tokenSeq = 0;

globalThis.fetch = async (url, opts = {}) => {
    const path = String(url).replace(BASE, '');
    const raw = opts.headers?.authorization ?? opts.headers?.Authorization ?? '';
    const authed = !!raw && validTokens.has(String(raw).replace(/^Bearer /, ''));
    platformLog.push({ path, auth: authed, sent: !!raw });
    const reply = (status, body) => ({
        ok: status >= 200 && status < 300,
        status,
        text: async () => JSON.stringify(body),
        json: async () => body,
    });
    if (path.includes('/external/token')) {
        const tk = `anon-${++tokenSeq}`;
        validTokens.add(tk);
        return reply(200, { code: 200, data: { token: tk, tier: 'anonymous' } });
    }
    if (path.includes('/external/meta')) {
        if (!authed) return reply(401, { code: 401, message: '令牌与请求设备不匹配' });
        if (path.includes('productId=')) {
            return reply(200, { code: 200, data: { problemTypes: ['产品缺陷', '功能需求', '体验改进'] } });
        }
        return reply(200, { code: 200, data: {
            products: ['CodeArts', 'OfficeAce'],
            productCatalog: [{ id: 1, name: 'CodeArts' }, { id: 3, name: 'OfficeAce' }],
        } });
    }
    if (path.includes('/external/voices')) {
        return reply(201, { code: 201, data: { voiceIds: ['V1'], statuses: ['new'] } });
    }
    return reply(404, { code: 404 });
};

// ⚠ 必须先装平台桩再 import 模块：模块在 import 期即捕获 globalThis.fetch。
// 相对路径：任何机器 clone 后都能跑（曾写死作者机绝对路径 → 他机 ERR_MODULE_NOT_FOUND）
const { apply, __clearCaches } = await import('../lib/index.js');

function boot(cfg = {}) {
    __clearCaches();
    const reg = new Map();
    apply(
        { tools: { register: (t) => reg.set(t.name, t) }, on: () => {}, provide: () => {},
          effect: () => {}, logger: { log() {}, warn() {}, error() {} }, get: () => undefined, set: () => {} },
        { apiBase: BASE, ...cfg },
    );
    return reg;
}

const submit = (reg, content, extra = {}) =>
    reg.get('vod_submit_voices').execute({ voices: [{ content, ...extra }], confirmed: true });

test('① meta 401 → 领匿名令牌 → 带 auth 重试 → 名录可用 → 归因成功并提交', async () => {
    platformLog.length = 0;
    const reg = boot();
    const out = await submit(reg, 'CodeArts：这块体验不流畅');

    const meta = platformLog.filter((c) => c.path.includes('/external/meta'));
    assert.ok(meta.length >= 2, `meta 应 ≥2 次（401+重试），实得 ${meta.length}`);
    assert.equal(meta[0].sent, false, '首次 meta 不带 auth（复现真机 401）');
    assert.ok(meta.some((c) => c.auth), '重试那次必须带有效 token');
    assert.ok(platformLog.some((c) => c.path.includes('/external/token')), '应领取匿名令牌');
    assert.ok(Array.isArray(out.voiceIds) && out.voiceIds.length,
        `应提交成功，实得 ${JSON.stringify(out).slice(0, 180)}`);
    assert.equal(out.productSource, 'user_input', '名录可用后归因应来自用户原话');
});

test('② ?productId= 401 同样领令牌重试（tags 白名单不失效）', async () => {
    platformLog.length = 0;
    const reg = boot();
    const out = await submit(reg, 'CodeArts：导出按钮点了没反应', { tags: ['problem_type:功能需求'] });

    const pid = platformLog.filter((c) => c.path.includes('productId='));
    assert.ok(pid.length >= 2, `productId 应 ≥2 次（401+重试），实得 ${pid.length}`);
    assert.ok(pid.some((c) => c.auth), '重试必须带有效 token');
    assert.equal((out.invalidTags || []).length, 0, `合法 tags 不应被丢：${JSON.stringify(out.invalidTags)}`);
});

test('③ 已配 apiKey 时 meta 首次请求即带 auth（不白吃一次 401）', async () => {
    platformLog.length = 0;
    const reg = boot({ apiKey: 'preset-key' });
    // preset-key 不在平台 valid 集里 → 允许 401 后重领，但首次必须已带 auth
    await submit(reg, 'CodeArts：已配 key 场景').catch(() => {});

    const first = platformLog.find((c) => c.path.includes('/external/meta'));
    assert.ok(first, '应发出 meta 请求');
    assert.equal(first.sent, true, '已配 key 时首次 meta 就应带 auth');
});
