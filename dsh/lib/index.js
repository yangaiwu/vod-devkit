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
const HOARD_PATH = `${API_PREFIX}/external/voices`; // V16 囤积端点（批量/不触发 LLM/结构化回执）
const SUBMIT_PATH = `${API_PREFIX}/external/voice/submit`; // 旧单条端点：仅 404 回落使用 // V16 已切换：主路径 HOARD_PATH（囤积），本路径仅 404 回落（见 docs/decisions.md D-dsh-4）
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

// VOD-DEVICE：设备锚点（纯 hex 32 位，引擎 [0-9a-f]{8,64} 校验；
// 含非 hex 字符会静默降 legacy 锚点——UI 半实锤的同类坑）
function i0Anon() { return true; } // 401 → 匿名令牌重试一次（保持原行为锚点）

function deviceNonce() {
    let n = loadRuntime().device_nonce;
    if (!n) {
        n = (randomUUID() + randomUUID()).replace(/[^0-9a-f]/g, '').slice(0, 32);
        saveRuntime({ device_nonce: n });
    }
    return n;
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
                'X-Vod-Device-Id': deviceNonce(),
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

// T7i（方案 A，2026-11-05 拍板）：产品归因主键化——meta productCatalog
// （[{id,name}]，t_vod_product 运营预置）按名解析平台 id 后提交；
// ①纯数字=平台 id 透传 ②目录无此名/不可达（含老引擎 404）→ 规范名兼容通道
// （引擎 name 命中同样补落 product_id）——不静默丢提交。进程内缓存一次。
const META_PATH = `${API_PREFIX}/external/meta`;
let _productCatalog = null;
async function resolveProductId(product, cfg, signal) {
    if (/^\d+$/.test(product)) return product;
    try {
        if (!_productCatalog) {
            const out = await http('GET', META_PATH, undefined, { ...cfg, signal });
            _productCatalog = (out.ok && out.data && out.data.data?.productCatalog)
                || out.data?.productCatalog || [];
        }
        const hit = _productCatalog.find(
            (x) => String(x?.name || '').toLowerCase() === product.toLowerCase());
        if (hit && hit.id != null) return String(hit.id);
    } catch (e) { /* 目录不可用 → 名字兼容通道 */ }
    return product;
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

/**
 * D-anon-ui（安装时配置口径）：从部署配置计算要注入页面的全局变量。
 * 纯函数（可单测）：product 恒注入；__VOD_DSH_UI_BASE__ 仅跨域部署显式配
 * uiBase 才注入（apiBase 是 server 半自用的绝对地址，浏览器同源策略下
 * 不能直接给页面；UI base 默认同源相对路径，宿主代理 /rest/）。
 */
export function uiGlobals(config) {
    const globals = [{
        kind: "global", name: "__VOD_DSH_UI_PRODUCT__",
        value: readCfg(config?.product, '') || '',
    }];
    const uiBase = readCfg(config?.uiBase, '');
    if (uiBase) {
        globals.push({ kind: "global", name: "__VOD_DSH_UI_BASE__", value: uiBase });
    }
    // 企业数据驻留（--no-local-ledger）：通知 client 半停写账本+隐藏历史入口
    if (readCfg(config?.noLocalLedger, false)) {
        globals.push({ kind: "global", name: "__VOD_DSH_UI_LEDGER_DISABLED__", value: true });
    }
    return globals;
}

export function apply(ctx, config) {
    // D-anon-ui：部署配置经官方 index-inject 通道下发页面全局（对齐
    // settings-account 的 __DSH_CONTACT_CONFIG__ 同款机制）。产品归因仍是
    // 安装必配（T7d）——未配置=client 半 fail fast 不激活，但不再是
    // "散户死插件"：错误信息指向安装命令（npx vod-devkit install
    // --target dsh --product <产品名>）
    ctx.on("webserver/index-inject", (table) => {
        for (const row of uiGlobals(config)) table.push(row);
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
                + 'PRECONDITION (overrides everything below): obtain the user\'s explicit consent to submit THIS feedback before calling; '
                + 'the user merely stating a complaint is NOT consent; never pass confirmed=true without it. '
                + 'ON FAILURE: tell the user in plain words only (e.g. 已暂存，稍后自动重试). '
                + 'NEVER expose HTTP status codes, apiKeyFingerprint, tokenTier, stack traces, '
                + 'tool names (say 提交反馈, never vod_submit_voices) or mechanism words '
                + '(调用/被拒/护栏/参数) to the user - they are internal diagnostics. '
                + 'The agent submits on the user\'s behalf; system behavior is described as 系统/稍后自动. '
                + 'OUTPUT CONTRACT: when explaining results to the user, only cover 收录状态与后续跟进. '
                + 'NEVER explain internal mechanics to users: 声音来源/渠道字段、计数规则（入库/净新增）、配额、归因——这些是系统内部概念。 '
                + 'Anonymous tier has NO credentials by design. ' +
                'Each voice = one user feedback (content ≤2000 chars). '
                + 'content MUST be a faithful transcription of the user\'s own words - '
                + 'NEVER invent sentiment (e.g. 体验不好) or fabricate content the user did not say. '
                +                'A bare product name or a question is NOT feedback - ask what the user wants to report. ' +
                'Product attribution is bound at install/deploy time (config product; no runtime product argument exists). ' +
                'Fixed one-time follow-up at confirmation, verbatim: 「方便的话，补充一下遇到这个问题时的操作步骤或期望的表现吗？不方便回复"没有"，我直接提交。」' +
                'Answer → reproSteps/expectedBehavior verbatim excerpt, never into content; "没有/跳过"=omit both. ' +
                'Batch ≤50. Returns voiceIds (reconciliation key) + taskIds.',
            parameters: buildParameters({
                voices: {
                    type: 'array', required: true,
                    description: 'Array of 1-50 voices: {content (required, ≤2000), userType (optional 企业|个人|未知), reproSteps/expectedBehavior (optional 用户追问补充, only when the fixed one-time follow-up got an answer; never merge into content)}',
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
                // 归因（D-attrib-A，2026-11-06 拍板，方案 A）：归因只由部署配置绑定
                // 决定（安装时定），不读 args——宿主/模型传参自报不采信（对齐 vod_mcp
                // effectiveBotPat 同款收紧；Python 侧实锤宽容口径被模型滥用后统一）
                let product = String(c.product || '').trim(); // 部署配置权威（安装时定），无 args 覆盖
                product = PRODUCT_MAP[product.toLowerCase()] || product;
                product = await resolveProductId(product, c, exec?.signal); // T7i：主键化提交
                const source = 'dsh';
                const accepted = [], taskIds = [], rejected = [];
                let key = c.key;
                // V16 切换（囤积端点）：批量一次 POST，title=原文截取、content=用户原话
                // （新端点无 10 字下限，不做模板补齐——P1 数据完整性）。404=引擎未部署 → 回落旧单条
                const hoard = [];
                for (let i = 0; i < voices.length; i++) {
                    const v = voices[i] || {};
                    const content = String(v.content ?? '').trim();
                    if (!content) { rejected.push({ index: i, reason: 'content 为空' }); continue; }
                    if (content.length > 2000) { rejected.push({ index: i, reason: `content 超 2000 字（${content.length}）` }); continue; }
                    const hv = { title: content.slice(0, 128), content }; // R3：title=用户原文
                    // D-followup-impl-2 追问补充透传：仅 trim 非空才含键（未追问/答"没有"=键集合与旧流程一致）；引擎同口径截 2000
                    const DECLINES = new Set(['没有', '无', '没有。', '没了', '跳过', '不方便', '不用了', '不用', '不补充', '算了', '没有了', '没有了。', '不方便说', 'no', 'none', 'skip', 'n/a']);
                    for (const f of ['reproSteps', 'expectedBehavior']) {
                        const val = String(v[f] ?? '').trim();
                        if (val && !DECLINES.has(val.toLowerCase())) hv[f] = val.slice(0, 2000);
                    }
                    hoard.push(hv);
                }
                if (hoard.length) {
                    let out = await http('POST', HOARD_PATH, { voices: hoard, product },
                        { ...c, key, signal: exec?.signal });
                    if (out.status === 401 && i0Anon(c)) {
                        const token = await fetchAnonToken({ ...c, key: '', signal: exec?.signal });
                        if (token) {
                            key = token;
                            saveRuntime({ java_key: token, token_tier: 'anonymous' });
                            out = await http('POST', HOARD_PATH, { voices: hoard, product },
                                { ...c, key, signal: exec?.signal });
                        } else {
                            return textResult({
                                error: '未配置接入 key 且匿名令牌端点不可用。引导：1) 首次提交时插件自动申请零字段匿名令牌；' +
                                    '2) 量到上限后联系 VOD 运营升级正式 key；3) 宿主平台整体对接可获宿主 key',
                                code: -32012,
                            });
                        }
                    }
                    if (out.status !== 404) {
                        if (out.ok) {
                            const d = out.data?.data || out.data || {};
                            const ids = d.voiceIds || [];
                            const sts = d.statuses || [];
                            for (let i = 0; i < hoard.length; i++) {
                                const vid = ids[i] || '';
                                if (vid && sts[i] !== 'skipped') accepted.push(vid);
                                else if (vid) { accepted.push(vid); } // skipped=幂等，也回执
                                taskIds.push(null); // 囤积语义：无即时任务
                            }
                            const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
                            ledgerAppend(hoard.map((h, i) => ({
                                voiceId: ids[i] || '', taskId: null,
                                title: h.title.slice(0, 40), product,
                                at: now, status: sts[i] === 'skipped' ? 'accepted' : 'accepted',
                            })));
                            return textResult({
                                accepted: accepted.length, voiceIds: accepted,
                                taskIds, rejected, path: 'hoarding',
                                ...(d.productRegistered !== undefined ? { productRegistered: d.productRegistered } : {}),
                            });
                        }
                        // 非 404 非 2xx → 回落旧单条（如 401 已处理；此处为兼容异常响应）
                    }
                }
                for (let i = 0; i < voices.length; i++) {
                    const v = voices[i] || {};
                    const content = String(v.content ?? '').trim();
                    if (!content) { rejected.push({ index: i, reason: 'content 为空' }); continue; }
                    if (content.length > 2000) { rejected.push({ index: i, reason: `content 超 2000 字（${content.length}）` }); continue; }
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
                        en: 'Submit this user feedback voice to VOD?',
                        zh: '向 VOD 提交这条用户反馈声音？',
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
