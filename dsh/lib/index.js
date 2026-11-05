/**
 * dsh-vod-devkit — VOD 用户声音采集插件（dsh 薄壳）。
 *
 * 形态纪律（与 vod-devkit MCP 侧一致）：
 * - 插件=引擎的客户端，只走 HTTPS，不 import 任何引擎模块
 * - 纯采集形态：submit / 本地账本查询 / 自述，共 3 工具
 * - 写操作默认走 dsh 审批通道（tools/pre-execute → kind:'ask'）
 * - voiceId = f(source, content, 调用级nonce)：同调用幂等、跨调用保声量
 * - key 缺失/401 → 自动 POST /external/token 零字段令牌 → 落本地 → 重试一次
 * - 本地账本（data/runtime.json，cap 200 环形）只动目标键，读改写
 */
import z from '@deepseek-ai/schemastery';
import { createHash, randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';

export const name = 'vod-devkit';
export const inject = ['tools'];

const PKG_DIR = dirname(dirname(fileURLToPath(import.meta.url)));
const DATA_DIR = join(PKG_DIR, 'data');
const RUNTIME = join(DATA_DIR, 'runtime.json');
const API_PREFIX = '/rest/developer/manager/hdvodmngservice/v1';
const SUBMIT_PATH = `${API_PREFIX}/external/voice/submit`; // TODO(引擎VOD-VOI上线)：切换为 `${API_PREFIX}/external/voices`（囤积入库、批量、不触发LLM分析、逐条结构化回执）——切换点仅此一行+body 字段核对，见 docs/decisions.md D-dsh-4
const TOKEN_PATH = `${API_PREFIX}/external/token`;
const LEDGER_CAP = 200;

export const Config = z.object({
    apiBase: z.string().default('https://vod-dev.topxtopx.com').volatile(),
    apiKey: z.string().default('').volatile().role('secret'),
    product: z.string().default('').volatile(),
    confirmWrites: z.boolean().default(true).volatile(),
    timeoutSec: z.number().default(30).volatile(),
});

function readCfg(v, fallback) {
    if (v === undefined || v === null) return fallback;
    if (typeof v === 'object' && typeof v.get === 'function') {
        const got = v.get();
        return got === undefined || got === null ? fallback : got;
    }
    return v;
}

// ── 本地账本：每次文件读改写，只动目标键（防内存合并回写陈旧配置） ──
function loadRuntime() {
    try { return JSON.parse(readFileSync(RUNTIME, 'utf8')); } catch { return {}; }
}
function saveRuntime(patch) {
    const rt = loadRuntime();
    const next = { ...rt, ...patch };
    if (Array.isArray(next.submissions) && next.submissions.length > LEDGER_CAP) {
        next.submissions = next.submissions.slice(-LEDGER_CAP);
    }
    mkdirSync(DATA_DIR, { recursive: true });
    writeFileSync(RUNTIME, JSON.stringify(next, null, 2));
}
function ledgerAppend(entries) {
    const rt = loadRuntime();
    const subs = Array.isArray(rt.submissions) ? rt.submissions : [];
    saveRuntime({ submissions: [...subs, ...entries].slice(-LEDGER_CAP) });
}

// ── HTTP ──
// ── 传输守卫（与 vod_mcp tools.py -32014 同构）：Bearer key/匿名令牌不得明文过公网 ──
function transportError(base) {
    if (!base) return null;
    let u; try { u = new URL(base); } catch { return { error: `apiBase 非法 URL: ${base}`, code: -32014 }; }
    const host = u.hostname;
    const loopback = host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
    if (u.protocol !== 'https:' && !loopback) {
        return {
            error: `上游 ${u.protocol}//${host} 非 https 且非本机回环——Bearer key 明文外发被拒` +
                '（插件配置 apiBase 改为 https:// 地址）',
            code: -32014,
        };
    }
    return null;
}

async function http(method, path, body, { base, key, timeoutSec, signal }) {
    const guard = transportError(base);
    if (guard) throw new Error(`[${guard.code}] ${guard.error}`); // backstop：守卫在工具入口已拦截，此处兜底
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), (timeoutSec || 30) * 1000);
    const onOuterAbort = () => ctrl.abort();
    signal?.addEventListener('abort', onOuterAbort);
    try {
        const res = await fetch(`${base}${path}`, {
            method,
            headers: {
                'content-type': 'application/json',
                ...(key ? { authorization: `Bearer ${key}` } : {}),
            },
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: ctrl.signal,
        });
        const text = await res.text();
        let data = null;
        try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
        return { status: res.status, ok: res.ok, data };
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onOuterAbort);
    }
}

async function fetchAnonToken(cfg) {
    const out = await http('POST', TOKEN_PATH, {}, cfg);
    if (out.ok && out.data && (out.data.token || out.data.data?.token)) {
        return out.data.token || out.data.data.token;
    }
    return null;
}

const PRODUCT_MAP = { // 引擎枚举归一（实测：小写 codearts → 400 空响应；Python 侧同款映射）
    // 已知差距（M2/M3 不适用于 dsh 形态）：本表硬编码，不拉 GET /external/meta——
    // 引擎 VodExternalProducts 变更时需同步此表（含 kb-query-auth 合入后的 AISHELL/nameAliases）。
    // 详见 docs/decisions.md D-dsh-3。
    agentarts: 'AgentArts', codearts: 'CodeArts', dataarts: 'DataArts',
    maas: 'MaaS', obs: 'OBS', officeclaw: 'OfficeClaw',
    modelarts: 'MaaS',
};

function voiceId(source, content, nonce) {
    const h = createHash('sha1').update(content + nonce).digest('hex').slice(0, 12);
    return `ext_${source}_${h}`;
}

function buildParameters(specs) {
    const properties = {};
    const required = [];
    for (const [k, spec] of Object.entries(specs)) {
        properties[k] = { type: spec.type, description: spec.description || k };
        if (spec.required) required.push(k);
    }
    const r = { type: 'object', properties, additionalProperties: false };
    if (required.length) r.required = required;
    return r;
}

const textResult = (obj) => obj; // execute 返回结构化对象；render 负责呈现
const renderText = (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }];

export function apply(ctx, config) {
    // D-anon-ui（安装时配置口径）：部署配置经官方 index-inject 通道下发页面全局，
    // client 半零改动即读到 product/apiBase（对齐 settings-account 的
    // __DSH_CONTACT_CONFIG__ 同款机制）。产品归因仍是安装必配（T7d）——
    // 未配置=client 半 fail fast 不激活，但不再是"散户死插件"：错误信息
    // 指向安装命令（npx vod-devkit install --target dsh --product <产品名>）
    ctx.on("webserver/index-inject", (table) => {
        table.push({ kind: "global", name: "__VOD_DSH_UI_PRODUCT__",
            value: readCfg(config?.product, '') || '' });
        table.push({ kind: "global", name: "__VOD_DSH_UI_BASE__",
            value: readCfg(config?.apiBase, 'https://vod-dev.topxtopx.com') || '' });
    });
    const cfg = () => ({
        base: (readCfg(config?.apiBase, 'https://vod-dev.topxtopx.com') || '').replace(/\/+$/, ''),
        key: readCfg(config?.apiKey, '') || '',
        product: readCfg(config?.product, '') || '',
        confirmWrites: readCfg(config?.confirmWrites, true) !== false,
        timeoutSec: readCfg(config?.timeoutSec, 30),
    });

    const tools = [
        {
            name: 'vod_submit_voices',
            description: '[VOD-unique] Submit agent-product user feedback voices to VOD (write). '
                + 'ON FAILURE: tell the user in plain words only (e.g. 已暂存，稍后自动重试). '
                + 'NEVER expose HTTP status codes, apiKeyFingerprint, tokenTier or stack traces to the user - '
                + 'they are internal diagnostics. Anonymous tier has NO credentials by design. ' +
                'Each voice = one user feedback (content ≤2000 chars). ' +
                'Product attribution ("host-is-product", no whitelist): explicit arg → config product → ' +
                'host identity (DSH). Host-reported products pass through as-is. ' +
                'Batch ≤50. Returns voiceIds (reconciliation key) + taskIds.',
            parameters: buildParameters({
                voices: {
                    type: 'array', required: true,
                    description: 'Array of 1-50 voices: {content (required, ≤2000), userType (optional 企业|个人|未知)}',
                },
            }),
            output: { schema: { type: 'object', additionalProperties: true }, render: renderText },
            async execute(args, exec) {
                const c = cfg();
                const guard = transportError(c.base); // 传输守卫：非 https 且非回环 → 拒绝（-32014，对齐 vod_mcp）
                if (guard) return textResult(guard);
                const voices = Array.isArray(args.voices) ? args.voices : [];
                if (!voices.length) return textResult({ error: 'voices 为空', code: -32001 });
                if (voices.length > 50) return textResult({ error: '单批上限 50 条', code: -32001 });
                // 归因（「宿主即产品」口径，2026-11-03 拍板·不设白名单）：显式传参 > 配置绑定
                // （安装时默认=宿主名）> 缺省 DSH（本插件就装在 dsh 里）；白名单废除，
                // 宿主自报产品原样上送（引擎宽松归一），不再 -32013 本地拦截
                let product = String(c.product || '').trim(); // 部署配置权威（安装时定），无 args 覆盖
                product = PRODUCT_MAP[product.toLowerCase()] || product;
                const source = 'dsh';
                const accepted = [], taskIds = [], rejected = [];
                let key = c.key;
                for (let i = 0; i < voices.length; i++) {
                    const v = voices[i] || {};
                    const content = String(v.content ?? '').trim();
                    if (!content) { rejected.push({ index: i, reason: 'content 为空' }); continue; }
                    if (content.length > 2000) { rejected.push({ index: i, reason: `content 超 2000 字（${content.length}）` }); continue; }
                    const scene = String(v.scene ?? '').slice(0, 128);
                    const nonce = randomUUID().replace(/-/g, '').slice(0, 8); // 调用级幂等、跨调用保声量
                    const vid = voiceId(source, content, nonce);
                    const desc = content.length >= 10 ? content : `${content} [vod-devkit]`;
                    const body = {
                        voiceId: vid,
                        title: content.slice(0, 128), // R3：title=用户原文（分析消费），模板只允许出现在 description
                        description: desc,
                        product,
                        source,
                        ...(v.userType ? { customer: v.userType } : {}),
                        ...(scene ? { scene } : {}),
                    };
                    const call = () => http('POST', SUBMIT_PATH, body, { ...c, key, signal: exec?.signal });
                    let out = await call();
                    if (out.status === 401 && i === 0) {
                        // 零字段匿名令牌：401 → 自动取令牌 → 落本地 → 重试一次
                        const token = await fetchAnonToken({ ...c, key: '', signal: exec?.signal });
                        if (token) {
                            key = token;
                            saveRuntime({ java_key: token, token_tier: 'anonymous' });
                            out = await call();
                        } else {
                            return textResult({
                                error: '未配置接入 key 且匿名令牌端点不可用。引导：1) 首次提交时插件自动申请零字段匿名令牌；' +
                                    '2) 量到上限后联系 VOD 运营升级正式 key；3) 宿主平台整体对接可获宿主 key',
                                code: -32012,
                            });
                        }
                    }
                    if (out.ok) {
                        accepted.push(vid);
                        taskIds.push(out.data?.data?.taskId ?? null);
                    } else {
                        const msg = JSON.stringify(out.data || {}).slice(0, 160);
                        if (msg.includes('Duplicate entry')) { accepted.push(vid); taskIds.push(null); }
                        else rejected.push({ index: i, reason: msg && msg !== '{}' ? msg : `HTTP ${out.status}` });
                    }
                }
                const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
                ledgerAppend(accepted.map((vid, i) => ({
                    voiceId: vid, taskId: taskIds[i],
                    title: String((voices[i] || {}).content ?? '').slice(0, 40),
                    product, at: now,
                })));
                return textResult({ accepted: accepted.length, voiceIds: accepted, taskIds, rejected });
            },
        },
        {
            name: 'vod_list_submitted',
            description: '[VOD-unique] Read-only: list voices submitted from THIS machine (local ledger, cap 200, newest first). ' +
                'Scope: local machine only — authoritative cross-machine query arrives with the engine-side endpoint (VOD-VOI layer 2).',
            parameters: buildParameters({
                limit: { type: 'number', description: '1-100, default 20, newest first' },
            }),
            output: { schema: { type: 'object', additionalProperties: true }, render: renderText },
            async execute(args) {
                const rt = loadRuntime();
                const subs = Array.isArray(rt.submissions) ? rt.submissions : [];
                const limit = Math.max(1, Math.min(100, Number(args.limit) || 20));
                return textResult({
                    scope: 'local-machine',
                    total: subs.length,
                    voices: subs.slice(-limit).reverse(),
                });
            },
        },
        {
            name: 'vod_devkit_info',
            description: '[VOD-unique] Read-only plugin self-description: version, api endpoint (fingerprinted), auth state (fingerprinted, never plaintext), local ledger size.',
            parameters: buildParameters({}),
            output: { schema: { type: 'object', additionalProperties: true }, render: renderText },
            async execute() {
                const c = cfg();
                const rt = loadRuntime();
                const fp = (s) => (s ? createHash('sha1').update(s).digest('hex').slice(0, 8) : null);
                // D-anon-ui：匿名档=散户默认正常态。无 key 不是"未配置"故障，
                // 显式标注防模型误诊（实锤：模型曾把 null 读成"凭据没配置"端给用户）
                const authMode = c.key ? 'key-configured' : (rt.token_tier ? 'anonymous-token' : 'anonymous (auto on first submit)');
                return textResult({
                    version: '0.1.0',
                    host: 'dsh',
                    apiBase: c.base,
                    apiKeyFingerprint: fp(c.key),
                    tokenTier: rt.token_tier || null,
                    authMode,
                    authNote: c.key ? null : 'No key configured - this is the DEFAULT anonymous tier (normal), auto token on first submit. NOT a misconfiguration.',
                    ledgerEntries: Array.isArray(rt.submissions) ? rt.submissions.length : 0,
                });
            },
        },
    ];

    for (const t of tools) ctx.tools.register(t);

    // 写操作确认：dsh 审批通道（web 端弹确认框），拒绝则不执行
    if (typeof ctx.on === 'function') {
        try {
            ctx.on('tools/pre-execute', (exec, next) => {
                if (exec.name !== 'vod_submit_voices') return next();
                if (!cfg().confirmWrites) return next();
                return {
                    kind: 'ask',
                    reason: `vod-write:${exec.name}`,
                    displayReason: {
                        en: 'Submit user feedback voices to VOD?',
                        zh: '向 VOD 提交用户反馈声音（入库即触发分析）？',
                    },
                };
            });
        } catch (err) {
            console.warn(`[dsh-vod-devkit] pre-execute registration failed: ${String(err)}`);
        }
    }

    console.log(`[dsh-vod-devkit] Registered ${tools.length} tools, apiBase=${cfg().base}` +
        (cfg().key ? ', key=set' : ', key=none (auto anonymous-token on first submit)') +
        (cfg().product ? `, product=${cfg().product}` : ', product=unset (must be set or passed per call)'));
}
