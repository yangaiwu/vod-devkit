/**
 * dsh-vod-devkit — VOD 用户声音采集插件（dsh 薄壳）。
 *
 * 形态纪律（与 vod-devkit MCP 侧一致）：
 * - 插件=引擎的客户端，只走 HTTPS，不 import 任何引擎模块
 * - 纯采集形态：submit / 本地账本查询 / 自述 / 技能披露×2 / 版本检查，共 6 工具
 * - 写操作默认走 dsh 审批通道（tools/pre-execute → kind:'ask'）
 * - 提交唯一路径 = POST /external/voices（囤积端点，S241 起不再有旧单条回落）
 * - key 缺失/401 → 自动 POST /external/token 零字段令牌 → 落本地 → 重试一次
 * - 本地账本（data/runtime.json，cap 200 环形）只动目标键，读改写
 */
import z from '@deepseek-ai/schemastery';
import { createHash, randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';

export const name = 'vod-devkit';
export const inject = ['tools'];

const PKG_DIR = dirname(dirname(fileURLToPath(import.meta.url)));
const DATA_DIR = join(PKG_DIR, 'data');
// 运行时状态路径可用 VOD_DSH_RUNTIME 覆盖（测试隔离/企业数据驻留用；
// 2026-11-11 实锤：dsh/test 直写仓内 dsh/data/runtime.json，本地账本被测试
// 灌到 128 条——测试必须能指到 tmp，不能再共用真实账本）
// 运行时状态默认写在包目录 data/ 下（历史形态，存量账本不迁移）。
// 但包目录在只读安装形态（全局共享 node_modules / pnpm store / 容器只读挂载）下
// 不可写——落盘失败=本地账本与归因记忆全丢，且只有提交时才会发现。
// 修法：写入失败一次性回退到 <dsh home>/data/ 并告警；VOD_DSH_RUNTIME 仍最高优先。
const RUNTIME = process.env.VOD_DSH_RUNTIME || join(DATA_DIR, 'runtime.json');
const FALLBACK_RUNTIME = join(homedir(), '.dsh', 'data', 'vod-devkit-runtime.json');
let runtimePath = RUNTIME;   // 运行期可变：写入失败后切到 fallback
const API_PREFIX = '/rest/developer/manager/hdvodmngservice/v1';
const HOARD_PATH = `${API_PREFIX}/external/voices`; // 囤积端点：唯一提交路径（S241 起旧单条链已删除）
const TOKEN_PATH = `${API_PREFIX}/external/token`;
const LEDGER_CAP = 200;
const PKG_VERSION = JSON.parse(readFileSync(join(PKG_DIR, 'package.json'), 'utf8')).version;

// build-info.json（构建烧录）：与 vod_mcp provenance.read_build_info 同源口径。
// dsh 是独立 npm 包（packages/dsh/），仓内形态在上一层；发布物形态可能在包内或缺失
// → 缺失即 null，不阻断（契约 required 只要求字段存在，不要求非空）。
function readBuildInfo() {
    for (const p of [join(PKG_DIR, 'build-info.json'), join(PKG_DIR, '..', '..', 'build-info.json')]) {
        try {
            if (existsSync(p)) return JSON.parse(readFileSync(p, 'utf8'));
        } catch (e) { /* 坏文件按缺失处理 */ }
    }
    return {};
}

export const Config = z.object({
    apiBase: z.string().default('https://vod-dev.topxtopx.com').volatile(),
    apiKey: z.string().default('').volatile().role('secret'),
    product: z.string().default('').volatile(),
    confirmWrites: z.boolean().default(true).volatile(),
    // D-dsh-mcp-b-1：B 模式（MCP client 承载工具面）时壳只留 UI 半。
    // 默认 true 保向后兼容（旧 config 无此键 = 仍注册 6 个工具 = 降级形态）；
    // 安装器在 MCP 模式（dsh 本体带 @deepseek-ai/dsh-mcp-client）下显式写 false。
    registerTools: z.boolean().default(true).volatile(),
    timeoutSec: z.number().default(30).volatile(),
    receiptGuard: z.string().default('report').volatile(), // D-rguard-1：off|report|enforce，默认 report（零危害只标注）
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
    try { return JSON.parse(readFileSync(runtimePath, 'utf8')); } catch { return {}; }
}
function _writeRuntime(target, next) {
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, JSON.stringify(next, null, 2));
}
function saveRuntime(patch) {
    const rt = loadRuntime();
    const next = { ...rt, ...patch };
    if (Array.isArray(next.submissions) && next.submissions.length > LEDGER_CAP) {
        next.submissions = next.submissions.slice(-LEDGER_CAP);
    }
    try {
        _writeRuntime(runtimePath, next);
    } catch (err) {
        if (runtimePath === FALLBACK_RUNTIME) throw err;   // 两处都不可写=真故障，不静默
        console.warn(`[dsh-vod-devkit] 包目录不可写（${runtimePath}：${String(err).slice(0, 80)}）`
            + `——运行时状态改落 ${FALLBACK_RUNTIME}（本地账本换位置，跨版本不互通）`);
        _writeRuntime(FALLBACK_RUNTIME, next);
        runtimePath = FALLBACK_RUNTIME;
    }
}
function ledgerAppend(entries) {
    const rt = loadRuntime();
    const subs = Array.isArray(rt.submissions) ? rt.submissions : [];
    saveRuntime({ submissions: [...subs, ...entries].slice(-LEDGER_CAP) });
}

// 回显段（方案 A，与 vod_mcp _echo_plan 逐字段同构）：提交回执强制携带原话回显。
// 检测型防线——宿主模型改写用户原话（实锤："体验不好"→"不友好"）在回执处当场可见，
// agent 必须原样转述，改写露馅。voiceId 为空（未拿到回执）的条目不进回显。
function echoPlan(hoard, vids) {
    const ok = [];
    for (let i = 0; i < vids.length && i < hoard.length; i += 1) {
        const vid = vids[i];
        if (vid) ok.push({ voiceId: String(vid), content: String(hoard[i]?.content ?? '') });
    }
    return {
        requiresUserEcho: ok.length > 0,
        instruction: '请向用户原样转述已收录内容：每条以「已收录原话：」开头，'
            + '后接 content 全文。禁止改写、概括、增删字词。',
        contents: ok,
    };
}

// ── tags 分类白名单（与 vod_mcp _allowed_tags/_filter_tags 逐条同构）──
// 引擎约定：分类标注写 problem_type:<值>，值域=meta.problemTypes。其它语义的 tag
// 不参与分类校验、原样保留；只有 problem_type 的值会被白名单过滤——脏值丢弃
// 不拒收声音（对标 vod-skill 的 check_classification）。
// 引擎契约变更（2026-11-12）：problemTypes 不再随无参 meta 下发，改为
// GET /external/meta?productId=<id> 按产品下发（真源 t_vod_problem_category 按
// product_id 分组，不同产品分类集不同）。
const PROBLEM_TYPE_PREFIX = 'problem_type:';
const PTYPE_TTL_MS = 24 * 3600 * 1000;
let _ptypeCache = null;   // {at, by: {productId: [types]}}

// 取不到（无 productId / 老引擎 / 该产品无分类 / 网络异常）→ 空集=不知道值域
// → 不过滤：宁可放行也不误杀采集。
async function allowedTags(productId, cfg, signal) {
    const pid = String(productId || '').trim();
    if (!pid || !/^\d+$/.test(pid)) return new Set();
    const cache = _ptypeCache || { at: 0, by: {} };
    const by = { ...(cache.by || {}) };
    if (Date.now() - Number(cache.at || 0) < PTYPE_TTL_MS && Array.isArray(by[pid])) {
        return new Set(by[pid]);
    }
    try {
        const out = await http('GET', `${META_PATH}?productId=${encodeURIComponent(pid)}`,
            undefined, { ...cfg, signal, timeoutSec: 10 });
        const data = out?.data?.data || out?.data || {};
        const types = (Array.isArray(data.problemTypes) ? data.problemTypes : [])
            .map((t) => String(t).trim()).filter(Boolean);
        by[pid] = types;
        _ptypeCache = { at: Date.now(), by };
        return new Set(types);
    } catch (e) {
        // 任何取不到 = 不知道值域 → 不过滤，绝不阻断提交
        return new Set(Array.isArray(by[pid]) ? by[pid] : []);
    }
}

function filterTags(tags, allowed) {
    const kept = [], dropped = [];
    for (const t of Array.isArray(tags) ? tags : []) {
        let s = String(t ?? '').trim();
        if (!s) continue;
        if (allowed.size && s.startsWith(PROBLEM_TYPE_PREFIX)) {
            const val = s.slice(PROBLEM_TYPE_PREFIX.length).trim();
            if (!allowed.has(val)) { dropped.push(s); continue; }
            s = PROBLEM_TYPE_PREFIX + val;   // 归一（去多余空白）
        }
        if (!kept.includes(s)) kept.push(s);
    }
    return { kept, dropped };
}

// ── 产品候选检索（与 vod_mcp/packs/core.py search_products 同算法）──
// 给模型 3-5 个候选去问用户，而不是从名录里瞎猜。名录=引擎 meta 的 productCatalog。
const UNRESOLVED_CODE = -32010;   // 「需要先问用户是哪个产品」的可执行错误码

function searchProducts(query, meta, limit = 5) {
    const catalog = Array.isArray(meta?.catalog) ? meta.catalog : [];
    const lim = Math.max(1, Math.min(20, Number(limit) || 5));
    if (!catalog.length) {
        return { candidates: [], total: 0, reason: 'catalog_unavailable',
            hint: '产品名录不可达（引擎或令牌不可用）：直接问用户产品名或 ID，不要编造候选' };
    }
    const q = String(query || '').trim();
    if (!q) {
        return { candidates: [], total: catalog.length, reason: 'empty_query',
            hint: '入参名是 query（其它名字会被当成空查询）；本次没有按任何关键词匹配' };
    }
    const idx = buildAliasIndex(meta);
    const hits = matchProducts(q, idx);
    const seen = new Set(), cands = [];
    for (const h of hits) {
        const pid = String(h?.id ?? '');
        if (!pid || seen.has(pid)) continue;
        seen.add(pid);
        cands.push({ id: pid, name: h.product,
            score: Math.round(Math.min(1, String(h.alias || '').length / Math.max(q.length, 1)) * 100) / 100,
            matchReason: `alias:${h.alias}` });
    }
    if (!cands.length) {   // 别名没命中：退回名字子串（用户可能打错/只说一半）
        const low = q.toLowerCase();
        for (const item of catalog) {
            const name = String(item?.name ?? '');
            if (low && (name.toLowerCase().includes(low) || low.includes(name.toLowerCase()))) {
                cands.push({ id: String(item?.id), name, score: 0.5, matchReason: 'name-substring' });
            }
        }
    }
    if (!cands.length) {   // 完全无关联词：给名录前 N 个当「可选项」（问用户用）
        for (const item of catalog.slice(0, lim)) {
            cands.push({ id: String(item?.id), name: String(item?.name ?? ''),
                score: 0, matchReason: 'catalog-default' });
        }
    }
    cands.sort((a, b) => (b.score - a.score) || (b.name.length - a.name.length));
    return { candidates: cands.slice(0, lim), total: catalog.length };
}

// 候选串的唯一拼写点（S233 同口径）：`名字（主键）` 顿号分隔。
function formatCandidates(cands, empty = '（名录为空）') {
    const items = (Array.isArray(cands) ? cands : []).filter((c) => c && typeof c === 'object');
    return items.map((c) => `${c.name}（${c.id}）`).join('、') || empty;
}

// 缺产品时先问一次（D-product-ask-1，对齐 Python _require_product_or_ask 的可执行错误
// 形态）。dsh 壳没有 product/productNotSpecified 入参（工具面故意不暴露 product——
// 防模型自报，见 ux-sync 锁），因此只走「按原话检索候选 → 请模型问一次」这一条路径。
// 追问轮次上限 2 次，之后明确终止——避免用户连续给两个都查不到的名字时无限重问。
function askProductOrFail(attr, hoard, runtime, meta) {
    if (attr.product) return null;
    // 歧义（多产品命中）不追问：引擎 UNKNOWN 池接得住，且追问会让用户被迫二选一
    // （对齐 Python：ambiguous 不带 product 直接提交，只有 no-evidence 才问）。
    if (attr.source === 'unknown' && (attr.evidence || []).some((e) => e && e.reason === 'ambiguous')) {
        return null;
    }
    // 计数封顶 3（2 次追问 + 1 次终止）：不封顶的话 state 里会一直累加，
    // 跨会话永远进不了「重新开始」的状态。提交成功时归零（见下方 saveRuntime）。
    const fails = Math.min(Number(runtime.productAskFailures || 0) + 1, 3);
    const stop = fails > 2;
    const tail = '（已追问 2 次仍未确认：别再问了，直接告诉用户这条反馈因为没有产品归属而不提交）';
    const text = hoard.map((h) => h.content).join('\n');
    const hint = formatCandidates(searchProducts(text, meta).candidates,
        '（名录未命中，可问用户直接说产品名）');
    return {
        error: '这条反馈还没确定是哪个产品：请先问用户一次『这条是哪个产品的反馈？』，'
            + '让他说产品名或 ID，然后原样重提这条反馈（不要自己填产品）。'
            + `候选：${hint}` + (stop ? tail : ''),
        code: UNRESOLVED_CODE,
        needsProductAsk: true,
        askFailures: fails,
    };
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

// ── 归因（D-attrib-B，2026-11-11 负责人拍板 A/A/A/A）：与 vod_mcp/attribution.py
// 同一口径——用户原话字面证据 > 记忆（TTL 30 分钟）> 部署 config 先验 > 未知。
// 唯一命中才采信；多产品命中=歧义 → 不上送 product（引擎 UNKNOWN 池）；
// 模型自报参数不存在（本壳工具面无 product 入参）。
const META_PATH = `${API_PREFIX}/external/meta`;
const META_TTL_MS = 24 * 3600 * 1000;
const ATTR_MEM_TTL = 30 * 60;          // 秒（与 Python 侧 MEM_TTL 对齐）
const ATTR_SHORT_ALIAS = 5;            // <5 字符短别名只认大小写精确（obs/maas）
const ATTR_BOUNDARY = /[A-Za-z0-9_-]/;
const ATTR_HISTORY_CAP = 10;
let _metaCache = null;                 // {at, data}

// 测试用：清进程内 meta/分类白名单缓存。产品运行时不需要调用（TTL 自然过期），
// 但测试里同一进程连着跑多个场景时，缓存会把前一个场景的 meta 带进后一个，
// 造成「本该发请求却没发」的假失败。
export function __clearCaches() {
    _metaCache = null;
    _ptypeCache = null;
}

function emptyMeta() {
    return { products: [], catalog: [], aliases: {}, nameAliases: {} };
}

async function loadMeta(cfg, signal) {
    if (_metaCache && Date.now() - _metaCache.at < META_TTL_MS) return _metaCache.data;
    try {
        const out = await http('GET', META_PATH, undefined, { ...cfg, signal });
        const d = out?.data?.data || out?.data || {};
        const meta = {
            products: Array.isArray(d.products) ? d.products : [],
            catalog: Array.isArray(d.productCatalog) ? d.productCatalog : [],
            aliases: d.aliases && typeof d.aliases === 'object' ? d.aliases : {},
            nameAliases: d.nameAliases && typeof d.nameAliases === 'object' ? d.nameAliases : {},
        };
        if (meta.products.length) {
            _metaCache = { at: Date.now(), data: meta };
            return meta;
        }
    } catch (e) { /* 名录不可用 → 快照空：短码都拿不到，宁可 UNKNOWN 不猜 */ }
    return _metaCache?.data || emptyMeta();
}

// 品牌俗称表（与 vod_mcp/attribution.py BRAND_ALIASES 同一份口径）：
// 只放**无法从登记名规则派生**且用户口语高频的品牌名（码道=CodeArts 中文品牌）。
const BRAND_ALIASES = {
    CodeArts: ['码道', '华为云码道'],
};

const LATIN_RUN = /[A-Za-z][A-Za-z0-9 ._-]*[A-Za-z0-9]|[A-Za-z]/g;
const isAscii = (s) => [...String(s)].every((c) => c.charCodeAt(0) < 128);

// 从单个登记名派生可用写法（与 Python _derive_aliases 逐条同源）：
// 原名 / 去空格 / 拉丁核心段（≥3）/ 非全大写混写名的 lower·capitalize 变体。
// 全大写缩写（OBS/CCE）不生成小写变体——否则 obs://bucket、/obs/bin 会被误命中（S93 铁律）。
function deriveAliases(name) {
    const raw = String(name || '').trim();
    if (!raw) return [];
    const out = [raw];
    const compact = raw.replace(/\s+/g, '');
    if (compact && compact !== raw) out.push(compact);
    const runs = (raw.match(LATIN_RUN) || []).map((r) => r.trim()).filter((r) => r.length >= 3);
    if (runs.length) {
        out.push(...runs);
        if (raw.includes(' ')) {
            const head = (runs[0].split(/\s+/)[0] || runs[0]);
            if (head.length >= 3) out.push(head);
        }
    }
    for (const run of runs) {
        if (run.length <= 8 && isAscii(run) && run !== run.toUpperCase()) {
            for (const v of [run.toLowerCase(), run.charAt(0).toUpperCase() + run.slice(1).toLowerCase()]) {
                if (v !== run) out.push(v);
            }
        }
    }
    return [...new Set(out.filter(Boolean))];
}

export function buildAliasIndex(meta = {}) {
    const products = (meta.products || []).map(String).filter(Boolean);
    const catalog = meta.catalog || [];
    const idByLower = new Map();
    for (const it of catalog) {
        const name = String(it?.name || '').trim();
        if (name) idByLower.set(name.toLowerCase(), it.id != null ? String(it.id) : null);
    }
    const canon = new Map(); // lower(name) -> {label,id,aliases:Set,brand,derived:Set}
    const slot = (nm, brand) => {
        const key = String(nm).trim().toLowerCase();
        let cur = canon.get(key);
        if (!cur) {
            cur = { label: String(nm).trim(), id: null, aliases: new Set(),
                    brand: !!brand, derived: new Set() };
            canon.set(key, cur);
        } else if (brand && !cur.brand) {
            cur.label = String(nm).trim();
            cur.brand = true;
        }
        cur.aliases.add(String(nm).trim());
        return cur;
    };
    products.forEach((p) => slot(p, true));          // 展示名优先成标签
    catalog.forEach((it) => { if (it?.name) slot(it.name, false); });
    // 规则派生（对齐 Python：每条登记名派生多种写法，派生的允许大小写不敏感）
    for (const s of canon.values()) {
        for (const d of deriveAliases(s.label)) {
            s.aliases.add(d);
            if (d !== s.label) s.derived.add(d);
        }
    }
    // 品牌俗称：目标产品不在本次名录（引擎换库）就不落地，宁可丢俗称也不错归
    for (const [target, words] of Object.entries(BRAND_ALIASES)) {
        const s = canon.get(target.toLowerCase());
        if (!s) continue;
        for (const w of words) if (w) s.aliases.add(String(w).trim());
    }
    for (const [key, list] of Object.entries(meta.nameAliases || {})) {
        const aliases = (list || []).map(String).filter(Boolean);
        let target = canon.get(String(key).toLowerCase());
        if (!target) {
            for (const a of aliases) {
                const s = canon.get(a.toLowerCase());
                if (s) { target = s; break; }
            }
        }
        if (!target) target = slot(key, true);
        aliases.forEach((a) => target.aliases.add(a));
        target.aliases.add(String(key));
    }
    for (const [key, targetName] of Object.entries(meta.aliases || {})) {
        let s = canon.get(String(targetName).toLowerCase());
        if (!s) s = slot(targetName, false);   // 目标不在名录也不丢别名
        s.aliases.add(String(key));
    }
    for (const s of canon.values()) {          // 名字/别名任一命中 catalog → 拿 id
        for (const a of [s.label, ...s.aliases]) {
            if (idByLower.has(a.toLowerCase())) {
                const id = idByLower.get(a.toLowerCase());
                if (id != null) { s.id = id; break; }
            }
        }
    }
    const merged = [];
    const byId = new Map();                    // 同 id 合并（展示名那条为准）
    for (const s of canon.values()) {
        if (s.id != null && byId.has(s.id)) {
            const keep = byId.get(s.id);
            s.aliases.forEach((a) => keep.aliases.add(a));
            continue;
        }
        if (s.id != null) byId.set(s.id, s);
        merged.push(s);
    }
    const entries = [];
    const seen = new Set();
    for (const s of merged) {
        for (const alias of s.aliases) {
            const key = `${s.label.toLowerCase()}\u0000${alias}`; // 大小写敏感：留住 MaaS/Maas
            if (!alias || seen.has(key)) continue;
            seen.add(key);
            // caseless：派生写法才允许大小写不敏感；全大写缩写永不（对齐 Python）
            const caseless = s.derived.has(alias) && alias !== alias.toUpperCase();
            entries.push({ product: s.label, id: s.id, alias, caseless });
        }
    }
    entries.sort((a, b) => b.alias.length - a.alias.length);
    return entries;
}

function snippetOf(text, start, end) {
    const lo = Math.max(0, start - 20);
    const hi = Math.min(text.length, end + 20);
    return text.slice(lo, hi).replace(/\s+/g, ' ').slice(0, 80);
}

export function matchProducts(text, index) {
    const t = String(text || '');
    if (!t || !Array.isArray(index) || !index.length) return [];
    const taken = [];
    const hits = [];
    const isAscii = (s) => [...s].every((c) => c.charCodeAt(0) < 128);
    for (const e of index) {
        const alias = String(e.alias || '');
        if (!alias) continue;
        const spans = [];
        if (!isAscii(alias)) {
            let i = 0;
            while ((i = t.indexOf(alias, i)) >= 0) { spans.push([i, i + alias.length]); i += 1; }
        } else {
            const exact = !e.caseless && alias.length < ATTR_SHORT_ALIAS;
            const hay = exact ? t : t.toLowerCase();
            const needle = exact ? alias : alias.toLowerCase();
            let i = 0;
            while ((i = hay.indexOf(needle, i)) >= 0) {
                const j = i + needle.length;
                const beforeOk = i === 0 || !ATTR_BOUNDARY.test(hay[i - 1]);
                let afterOk = true;
                if (j < hay.length) {
                    const n = hay[j];
                    if (ATTR_BOUNDARY.test(n)) afterOk = false;
                    else if (n === '.' && j + 1 < hay.length && /[A-Za-z0-9]/.test(hay[j + 1])) afterOk = false;
                }
                if (beforeOk && afterOk) {
                    // URL/路径上下文不是产品提及：obs://bucket、/obs/bin、a@obs（对齐 Python）
                    const prev = i > 0 ? hay[i - 1] : '';
                    const nxt = j < hay.length ? hay[j] : '';
                    const prevBad = ['/', '\\', '.', '@'].includes(prev);
                    const nxtBad = [':', '/', '\\'].includes(nxt);
                    if (!prevBad && !nxtBad) spans.push([i, j]);
                }
                i += 1;
            }
        }
        for (const [s, en] of spans) {
            if (taken.some(([ts, te]) => !(en <= ts || s >= te))) continue; // 长别名优先
            taken.push([s, en]);
            hits.push({ product: e.product, id: e.id, alias, start: s, end: en, snippet: snippetOf(t, s, en) });
        }
    }
    hits.sort((a, b) => a.start - b.start);
    return hits;
}

function resolveSubmitValue(product, meta) {
    const p = String(product || '').trim();
    if (!p) return '';
    if (/^\d+$/.test(p)) return p;
    const idx = buildAliasIndex(meta || {});
    const low = p.toLowerCase();
    for (const e of idx) {
        if (String(e.product).toLowerCase() === low && e.id != null) return String(e.id);
    }
    for (const e of idx) {
        if (String(e.alias).toLowerCase() === low && e.id != null) return String(e.id);
    }
    return p;
}

export function attributeProduct(text, meta, opts = {}) {
    const nowSec = opts.now ?? Math.floor(Date.now() / 1000);
    const ttl = opts.ttl ?? ATTR_MEM_TTL;
    const hits = matchProducts(text, buildAliasIndex(meta || {}));
    const groups = new Map();
    for (const h of hits) {
        const k = String(h.product).toLowerCase();
        const cur = groups.get(k);
        if (!cur || h.alias.length > cur.alias.length) groups.set(k, h);
    }
    if (groups.size === 1) {
        const h = [...groups.values()][0];
        return { product: h.id != null ? String(h.id) : h.product, productName: h.product,
            source: 'user_input',
            evidence: [{ product: h.product, alias: h.alias, snippet: h.snippet }] };
    }
    if (groups.size > 1) {
        return { product: null, productName: null, source: 'unknown',
            evidence: hits.map((h) => ({ product: h.product, alias: h.alias,
                snippet: h.snippet, reason: 'ambiguous' })) };
    }
    const mem = opts.memory || {};
    if (mem.product && nowSec - Number(mem.at || 0) <= ttl) {
        return { product: String(mem.product), productName: mem.productName || null,
            source: 'memory',
            evidence: [{ product: mem.productName || String(mem.product), alias: mem.alias,
                snippet: mem.snippet, at: mem.at, reason: 'memory' }] };
    }
    const binding = String(opts.binding || '').trim();
    if (binding) {
        return { product: resolveSubmitValue(binding, meta), productName: binding,
            source: 'install_binding', evidence: [] };
    }
    return { product: null, productName: null, source: 'unknown',
        evidence: [{ reason: 'no-evidence' }] };
}

// 记忆：只记「字面证据唯一命中」；覆盖时旧条目进 attribution_history（cap 10）
function rememberAttribution(attr) {
    if (attr?.source !== 'user_input') return;
    const ev = (attr.evidence || [])[0] || {};
    const mem = { product: attr.product, productName: ev.product || attr.productName || null,
        alias: ev.alias, snippet: ev.snippet, at: Math.floor(Date.now() / 1000) };
    const rt = loadRuntime();
    const prev = rt.attribution_memory || {};
    if (prev.product) {
        const hist = (Array.isArray(rt.attribution_history) ? rt.attribution_history : [])
            .concat([{ ...prev, replacedAt: mem.at }]).slice(-ATTR_HISTORY_CAP);
        saveRuntime({ attribution_history: hist });
    }
    saveRuntime({ attribution_memory: mem });
}

async function fetchAnonToken(cfg) {
    const out = await http('POST', TOKEN_PATH, {}, cfg);
    if (out.ok && out.data && (out.data.token || out.data.data?.token)) {
        return out.data.token || out.data.data.token;
    }
    return null;
}

// ── D-rguard-1 ReceiptGuard（提交侧原文比对，2026-11-09 验证立项）──
// 通道实测（dsh-tools 0.2.0 类型源）：exec.agent.session.deriveMessages() 的
// user 轮消息 = 用户逐字原文（append-only 会话日志投影，不经模型）——模型改写
// 只发生在 args 侧，比对 args.content 与日志原文即可抓改写（dsh headless echo
// 改字两次实锤均在 args 侧，正是本闸覆盖面）。模型无往日志写用户轮的通道
// （ToolRunContext.deferContext 是插件自铸上下文，不产生用户轮）。
// 三档：off=不校验；report（默认）=只标注零危害；enforce=mismatch/unavailable 拒收。
export function normalizeForGuard(s) {
    return String(s ?? '').replace(/\s+/g, '').toLowerCase();
}

export function bigramSimilarity(a, b) {
    if (!a || !b) return 0;
    if (a === b) return 1;
    const grams = (s) => {
        const m = new Map();
        for (let i = 0; i < s.length - 1; i++) {
            const g = s.slice(i, i + 2);
            m.set(g, (m.get(g) || 0) + 1);
        }
        return m;
    };
    const ga = grams(a), gb = grams(b);
    let inter = 0, total = 0;
    for (const v of ga.values()) total += v;
    for (const [g, v] of gb) {
        total += v;
        if (ga.has(g)) inter += Math.min(v, ga.get(g));
    }
    return total ? (2 * inter) / total : 0;
}

/** 从会话日志取全部用户轮逐字文本（text 块；tool_result 也是 user role，按块型过滤）；不可得=null */
export function collectUserTurns(session) {
    if (!session || typeof session.deriveMessages !== 'function') return null;
    const msgs = session.deriveMessages();
    const turns = [];
    for (const m of Array.isArray(msgs) ? msgs : []) {
        if (!m || m.role !== 'user' || !Array.isArray(m.content)) continue;
        const text = m.content.filter((b) => b && b.type === 'text').map((b) => b.text).join('\n');
        if (text) turns.push(text);
    }
    return turns.length ? turns : null;
}

/** 单条 content 判定：规范化整串命中任一用户轮=verified；跨轮忠实聚合按拼接语料命中；
 *  字符二元组相似度 ≥0.5 且规范化长度 ≥10=fuzzy（短内容必须逐字，防止相似度阈值吞掉短改写）；
 *  否则 mismatch；原文不可得=unavailable。 */
export function evaluateVoiceGuard(userTurns, content) {
    if (!Array.isArray(userTurns)) return 'unavailable';
    const c = normalizeForGuard(content);
    if (!c) return 'mismatch';
    const corpus = normalizeForGuard(userTurns.join('\n'));
    if (corpus.includes(c)) return 'verified';
    if (c.length < 10) return 'mismatch'; // 短内容不享受相似度豁免（'A问题。补充B' 型胶水词改写）
    let best = 0;
    for (const t of userTurns) best = Math.max(best, bigramSimilarity(c, normalizeForGuard(t)));
    return best >= 0.5 ? 'fuzzy' : 'mismatch';
}

export const RG_MODES = ['off', 'report', 'enforce'];

/** 回执汇总：mode + 逐条判定（对账主键=voiceId 顺序位；纯函数可单测） */
export function rgGuardSummary(verdictMap, total) {
    const verdicts = [];
    for (let i = 0; i < total; i++) verdicts.push(verdictMap.get(i) ?? 'unavailable');
    return {
        verdicts,
        mismatch: verdicts.filter((v) => v === 'mismatch').length,
        unavailable: verdicts.filter((v) => v === 'unavailable').length,
    };
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
        // D-dsh-mcp-b-1：工具面开关。缺省 true（老 config / 降级形态照旧自注册）；
        // MCP 模式下安装器写 false，壳只留 UI 半（否则两个 submit 并存）。
        registerTools: readCfg(config?.registerTools, true) !== false,
        timeoutSec: readCfg(config?.timeoutSec, 30),
        receiptGuard: RG_MODES.includes(readCfg(config?.receiptGuard, 'report'))
            ? readCfg(config?.receiptGuard, 'report') : 'report',
    });

    // ── 技能披露 + 版本提醒（与 Python 侧同口径的只读面）──────────────────
    // 为什么 dsh 必须有这两个：dsh 是本插件唯一没有 MCP 的宿主，规则/话术
    // 全靠落盘技能；而 2026-11-11 前安装器根本没给 dsh 落技能（已修）。
    // 披露让"技能文本=server data"，改规则不必碰宿主拷贝。
    const SKILLS_DIR = process.env.VOD_SKILLS_DIR || join(homedir(), '.dsh', 'skills');
    const SKILL_RE = /^[a-z0-9][a-z0-9-]{2,63}$/;
    const SKILL_CAP = 12000;
    const UPDATE_TTL_MS = 24 * 3600 * 1000;
    const DISMISS_DAYS = 3;

    function skillDirs() {
        try {
            return readdirSync(SKILLS_DIR, { withFileTypes: true })
                .filter((e) => e.isDirectory())
                .map((e) => e.name)
                .filter((n) => existsSync(join(SKILLS_DIR, n, 'SKILL.md')))
                .sort();
        } catch {
            return [];
        }
    }

    function skillDescription(text) {
        const m = /^description:\s*(.+)$/m.exec(text || '');
        return m ? m[1].trim().replace(/^['"]|['"]$/g, '') : '';
    }

    function versionTuple(v) {
        const core = String(v || '').split('-')[0].split('+')[0];
        return core.split('.').slice(0, 3).map((x) => Number.parseInt(x, 10) || 0)
            .concat([0, 0]).slice(0, 3);
    }

    function cmpVersion(a, b) {
        const x = versionTuple(a), y = versionTuple(b);
        for (let i = 0; i < 3; i += 1) {
            if (x[i] !== y[i]) return x[i] > y[i] ? 1 : -1;
        }
        return 0;
    }

    const tools = [
        {
            name: 'vod_submit_voices',
            description: '[VOD-unique] Submit user feedback voices to VOD (write). '
                // 500 字窗口纪律（dsh 硬截断）：同意闸 + 缺产品追问 + 失败话术 + 禁编造
                // 必须在最前面，其余机制纪律放窗口外（模型仍可读到全文的宿主不受影响）。
                + 'PRECONDITION: obtain the user\'s explicit consent to submit THIS feedback before calling; '
                + 'a complaint alone is NOT consent; never pass confirmed=true without it. '
                + 'NO PRODUCT FOUND → the tool returns needsProductAsk: ask the user once which product this is about (use the candidates in the error), then resubmit the same feedback verbatim; NEVER invent a product for them. '
                + 'ON FAILURE: say in plain words only (e.g. 这次没有提交成功，需要的话我再提一次). '
                + 'NEVER say 已暂存/稍后自动重试 — no local queue exists; that would be a false claim. '
                + 'content MUST be a faithful transcription of the user\'s own words (≤2000 chars); '
                + 'NEVER invent sentiment or fabricate content the user did not say. A bare product name or a question is NOT feedback -- ask what they want to report. '
                + 'Each voice = one user feedback. '
                + 'NEVER expose HTTP status codes, fingerprints, tokenTier, stack traces, tool names '
                + '(say 提交反馈, never vod_submit_voices) or mechanism words (调用/被拒/护栏/参数/配额) — internal diagnostics. '
                + 'Attribution comes from the user\'s own words; config product is only a fallback. '
                + 'Anonymous tier has NO credentials by design. '
                + 'OUTPUT: to the user, cover only 收录状态与后续跟进; never explain 声音来源/渠道字段、计数规则、归因. '
                + 'Fixed one-time follow-up at confirmation, verbatim: 「方便的话，补充一下遇到这个问题时的操作步骤或期望的表现吗？不方便回复"没有"，我直接提交。」'
                + 'Answer → reproSteps/expectedBehavior verbatim excerpt, never into content; "没有/跳过"=omit both. '
                + 'Batch ≤50. Returns voiceIds (reconciliation key) + taskIds.',
            parameters: buildParameters({
                voices: {
                    type: 'array', required: true,
                    description: 'Array of 1-50 voices: {content (required, ≤2000), userType (optional 企业|个人|未知), tags (optional 采集层分类标注，写 problem_type:<六类之一>，白名单外值由插件丢弃并在回执 invalidTags 报出，不拒收声音), reproSteps/expectedBehavior (optional 用户追问补充, only when the fixed one-time follow-up got an answer; never merge into content)}',
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
                // 归因（D-attrib-B，对齐 vod_mcp/attribution.py）：从用户原话解析，
                // 部署 config.product 只是「无字面证据且无记忆」时的先验
                const meta = await loadMeta(c, exec?.signal);
                const attrText = voices.map((v) => String(v?.content ?? '')).join('\n');
                const attr = attributeProduct(attrText, meta, {
                    memory: loadRuntime().attribution_memory,
                    binding: String(c.product || ''),
                });
                const product = attr.product || '';
                const source = 'dsh';
                // D-rguard-1：原文比对（whitelist 通道=会话日志 user 轮）。enforce 档
                // mismatch/unavailable 拒收；report（默认）只标注；off 全跳过。
                const rgMode = c.receiptGuard;
                const userTurns = rgMode === 'off' ? null : collectUserTurns(exec?.agent?.session);
                const rgVerdict = new Map(); // index → verified|fuzzy|mismatch|unavailable
                const accepted = [], taskIds = [], rejected = [];
                const invalidTags = [];
                let key = c.key;
                // 分类白名单按产品取（引擎 ?productId= 下发）；product 非数字 id 时取不到→不过滤
                const allowed = await allowedTags(product, c, exec?.signal);
                // V16 切换（囤积端点）：批量一次 POST，title=原文截取、content=用户原话
                // （新端点无 10 字下限，不做模板补齐——P1 数据完整性）。404=引擎未部署 → 回落旧单条
                const hoard = [];
                for (let i = 0; i < voices.length; i++) {
                    const v = voices[i] || {};
                    const content = String(v.content ?? '').trim();
                    if (!content) { rejected.push({ index: i, reason: 'content 为空' }); continue; }
                    if (content.length > 2000) { rejected.push({ index: i, reason: `content 超 2000 字（${content.length}）` }); continue; }
                    if (rgMode !== 'off') {
                        const st = evaluateVoiceGuard(userTurns, content);
                        rgVerdict.set(i, st);
                        if (rgMode === 'enforce' && st !== 'verified' && st !== 'fuzzy') {
                            rejected.push({ index: i, reason: st === 'mismatch'
                                ? 'ReceiptGuard: content 与会话用户原文不一致'
                                : 'ReceiptGuard: 会话原文不可得，无法校验' });
                            continue;
                        }
                    }
                    const hv = { title: content.slice(0, 128), content }; // R3：title=用户原文
                    // tags（采集层三分类 problem_type:值）→ 按产品白名单过滤后正式入库；
                    // 白名单外的 problem_type 值丢弃不拒收，回执 invalidTags 报出（对齐 vod_mcp）
                    if (Array.isArray(v.tags) && v.tags.length) {
                        const { kept, dropped } = filterTags(v.tags, allowed);
                        if (kept.length) hv.tags = kept;
                        if (dropped.length) invalidTags.push({ index: i, tags: dropped });
                    }
                    if (v.userType) hv.userType = String(v.userType);
                    // D-followup-impl-2 追问补充透传：仅 trim 非空才含键（未追问/答"没有"=键集合与旧流程一致）；引擎同口径截 2000
                    // followupStatus（评审八点 #3）：三态白名单归一透传，白名单外省键（desc 无预算不宣讲，行为对齐 vod_mcp 单源）
                    const DECLINES = new Set(['没有', '无', '没有。', '没了', '跳过', '不方便', '不用了', '不用', '不补充', '算了', '没有了', '没有了。', '不方便说', 'no', 'none', 'skip', 'n/a']);
                    for (const f of ['reproSteps', 'expectedBehavior']) {
                        const val = String(v[f] ?? '').trim();
                        if (val && !DECLINES.has(val.toLowerCase())) hv[f] = val.slice(0, 2000);
                    }
                    const st = String(v.followupStatus ?? '').trim().toLowerCase();
                    if (['not_asked', 'declined', 'answered'].includes(st)) hv.followupStatus = st;
                    hoard.push(hv);
                }
                // 缺产品先问一次（D-product-ask-1）：与其裸提交进引擎 UNKNOWN 池，
                // 不如让模型问用户一句。追问计数落 runtime，超 2 次明确终止。
                if (hoard.length) {
                    const ask = askProductOrFail(attr, hoard, loadRuntime(), meta);
                    if (ask) {
                        saveRuntime({ productAskFailures: ask.askFailures });
                        return textResult(ask);
                    }
                }
                if (hoard.length) {
                    const hoardBody = { voices: hoard, ...(product ? { product } : {}) };
                    let out = await http('POST', HOARD_PATH, hoardBody,
                        { ...c, key, signal: exec?.signal });
                    if (out.status === 401 && i0Anon(c)) {
                        const token = await fetchAnonToken({ ...c, key: '', signal: exec?.signal });
                        if (token) {
                            key = token;
                            saveRuntime({ java_key: token, token_tier: 'anonymous' });
                            out = await http('POST', HOARD_PATH, hoardBody,
                                { ...c, key, signal: exec?.signal });
                        } else {
                            return textResult({
                                error: '未配置接入 key 且匿名令牌端点不可用。引导：1) 首次提交时插件自动申请零字段匿名令牌；' +
                                    '2) 量到上限后联系 VOD 运营升级正式 key；3) 宿主平台整体对接可获宿主 key',
                                code: -32012,
                            });
                        }
                    }
                    if (out.ok) {
                        const d = out.data?.data || out.data || {};
                        const ids = Array.isArray(d.voiceIds) ? d.voiceIds : [];
                        // 引擎侧 rejected（产品校验拒绝等）透出，不吞（对齐 Python S238 口径）
                        const engineRejected = Array.isArray(d.rejected) ? d.rejected
                            : (Array.isArray(out.data?.rejected) ? out.data.rejected : []);
                        const mergedRejected = rejected.concat(engineRejected);
                        // 回执缺失 voiceIds（200 但空回执/整批被拒）→ 不得兜底计成功。
                        // 实锤缺陷：空 voiceId 记成功且宿主模型据此谎报「已提交」。
                        const receiptOk = ids.length > 0;
                        if (receiptOk) {
                            for (let i = 0; i < hoard.length; i++) accepted.push(ids[i] || '');
                        }
                        for (let i = 0; i < hoard.length; i++) taskIds.push(null); // 囤积语义：无即时任务
                        const now = new Date().toISOString().replace('T', ' ').slice(0, 19);
                        if (receiptOk) {
                            // 只有真拿到回执才记账 + 记归因记忆，否则账本被空 voiceId 污染
                            rememberAttribution(attr); // 只记有字面证据的唯一命中
                            // 提交成功 → 追问计数归零（下一轮反馈重新从第 1 次问起）
                            if (loadRuntime().productAskFailures) saveRuntime({ productAskFailures: 0 });
                            ledgerAppend(hoard.map((h, i) => ({
                                voiceId: ids[i] || '', taskId: null,
                                title: h.title.slice(0, 40), product,
                                productSource: attr.source, productEvidence: attr.evidence,
                                at: now, status: 'accepted',
                            })));
                        }
                        if (!receiptOk && !engineRejected.length) {
                            mergedRejected.push({ reason: '引擎回执未含 voiceIds（提交结果未知），请勿视为已收录' });
                        }
                        return textResult({
                            accepted: receiptOk ? accepted.length : 0,
                            voiceIds: receiptOk ? accepted : [],
                            taskIds, rejected: mergedRejected, path: 'hoarding',
                            analysis: 'deferred',
                            // 回显段（方案 A，与 vod_mcp _echo_plan 同构）：检测型防线——
                            // 宿主模型改写用户原话在回执处当场可见，agent 必须原样转述。
                            echo: echoPlan(hoard, receiptOk ? ids : []),
                            ...(receiptOk ? {} : { receiptIncomplete: true }),
                            productSource: attr.source,
                            ...(attr.evidence && attr.evidence.length ? { productEvidence: attr.evidence } : {}),
                            ...(invalidTags.length ? { invalidTags } : {}),
                            ...(rgMode !== 'off' ? { receiptGuard: rgGuardSummary(rgVerdict, hoard.length) } : {}),
                            ...(d.productRegistered !== undefined ? { productRegistered: d.productRegistered } : {}),
                        });
                    }
                    // S241：囤积端点是唯一提交路径，失败不再回落旧单条 /external/voice/submit
                    // 失败话术纪律：dsh 壳没有本地 pending 队列（仅 vod_mcp 侧有），
                    // 因此不得让模型说「已暂存/稍后自动重试」——那是谎报。回执里显式给
                    // userFacingHint 供模型照抄，并标 notStored 供内部判断。
                    const detail = JSON.stringify(out.data || {}).slice(0, 160);
                    const is404 = out.status === 404;
                    return textResult({
                        error: is404
                            ? '囤积端点未上线（POST /external/voices 返回 404）：本条未提交。引擎部署该端点后自动可用；不要改用老链。'
                            : `囤积端点返回 HTTP ${out.status}，未提交（旧单条端点已移除）`,
                        code: is404 ? -32016 : -32002,
                        httpStatus: out.status,
                        notStored: true,
                        userFacingHint: '这条反馈没有提交成功，我这边也没法先存下来——需要的话稍后再让我提交一次。',
                        ...(detail && detail !== '{}' ? { detail } : {}),
                        rejected,
                        accepted: 0,
                        path: 'hoarding',
                        echo: echoPlan(hoard, []),   // 契约必填：未拿到回执=无 voiceId，回显为空
                    });
                }
                // hoard 为空（所有条目在前置校验被拒）→ 无提交调用，只回执拒收原因
                return textResult({ accepted: 0, voiceIds: [], taskIds: [], rejected,
                    echo: echoPlan([], []),   // 契约必填：无提交也就无回显
                    productSource: attr.source,
                    ...(attr.evidence && attr.evidence.length ? { productEvidence: attr.evidence } : {}),
                    ...(invalidTags.length ? { invalidTags } : {}),
                    ...(rgMode !== 'off' ? { receiptGuard: rgGuardSummary(rgVerdict, voices.length) } : {}) });
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
                    submissions: subs.slice(-limit).reverse(),   // 契约 required 名
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
                    // 版本必须跟随包（PKG_VERSION）：写死 '0.1.0' 会让壳永远自称旧版，
                    // 真机实测就吃过这个亏（会话里工具回执报 0.1.0，误判成"装的是老壳"）。
                    version: PKG_VERSION,
                    commitSha: readBuildInfo().commitSha ?? null,   // 契约 required
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
        {
            name: 'vod_list_skills',
            description: '[VOD-unique] Read-only: list skills available on this machine (name/pack/description). '
                + 'Use before routing a rules question (分类/评分/话术) or before vod_retrieve_skill.',
            parameters: buildParameters({}),
            output: { schema: { type: 'object', additionalProperties: true }, render: renderText },
            async execute() {
                const skills = skillDirs().map((n) => {
                    let text = '';
                    try { text = readFileSync(join(SKILLS_DIR, n, 'SKILL.md'), 'utf8'); } catch { /* 忽略 */ }
                    const pack = ['vod-core', 'vod-feedback-collect'].includes(n) ? 'core' : 'knowledge';
                    return { name: n, pack, native: true, description: skillDescription(text) };
                });
                return textResult({ skills, skillsDir: SKILLS_DIR });
            },
        },
        {
            name: 'vod_retrieve_skill',
            description: '[VOD-unique] Read-only: read one skill verbatim (SKILL.md). '
                + 'Use when this machine\'s copy is missing or you need the rules text without a native skill loader. '
                + 'Unknown names return the available list.',
            parameters: buildParameters({
                name: { type: 'string', description: 'skill name from vod_list_skills' },
            }),
            output: { schema: { type: 'object', additionalProperties: true }, render: renderText },
            async execute(args) {
                const nm = String(args.name || '').trim();
                if (!SKILL_RE.test(nm)) {
                    return textResult({ error: 'bad-name', available: skillDirs() });
                }
                try {
                    let content = readFileSync(join(SKILLS_DIR, nm, 'SKILL.md'), 'utf8');
                    const truncated = content.length > SKILL_CAP;
                    if (truncated) content = content.slice(0, SKILL_CAP);
                    return textResult({ name: nm, chars: content.length, truncated, content });
                } catch {
                    return textResult({ error: 'not-found', name: nm, available: skillDirs() });
                }
            },
        },
        {
            name: 'vod_check_update',
            description: '[VOD-unique] Read-only: is this plugin behind npm latest? 24h cache, silent on failure. '
                + 'Reports only - never self-upgrades (upgrade = rerun the install command). '
                + 'Pass dismiss=true after the user asks to stop the reminders (3-day cooldown).',
            parameters: buildParameters({
                dismiss: { type: 'boolean', description: 'user asked to stop reminders (3-day cooldown)' },
            }),
            output: { schema: { type: 'object', additionalProperties: true }, render: renderText },
            async execute(args) {
                const state = loadRuntime().update_check || {};
                const now = Date.now();
                const today = new Date(now).toISOString().slice(0, 10);
                if (args.dismiss === true) {
                    const until = new Date(now + DISMISS_DAYS * 86400e3).toISOString().slice(0, 10);
                    saveRuntime({ update_check: { ...state, dismissedUntil: until } });
                    return textResult({ dismissedUntil: until, updateAvailable: false });
                }
                if (state.dismissedUntil && today < state.dismissedUntil) {
                    return textResult({ updateAvailable: false, dismissedUntil: state.dismissedUntil });
                }
                const fresh = state.checkedAt && (now - Date.parse(state.checkedAt)) < UPDATE_TTL_MS;
                let latest = fresh ? state.latestVersion : null;
                if (!latest) {
                    try {
                        const ctl = new AbortController();
                        const timer = setTimeout(() => ctl.abort(), 3000);
                        const res = await fetch('https://registry.npmjs.org/dsh-vod-devkit/latest',
                            { signal: ctl.signal });
                        clearTimeout(timer);
                        const body = await res.json();
                        latest = body?.version ? String(body.version) : null;
                    } catch { latest = null; }
                    if (latest) {
                        saveRuntime({ update_check: { ...state, checkedAt: new Date(now).toISOString(),
                            latestVersion: latest } });
                    }
                }
                if (!latest) {
                    return textResult({ currentVersion: PKG_VERSION, latestVersion: null,
                        updateAvailable: false, checked: false,
                        note: '版本检查不可达（离线/内网正常），不影响采集。' });
                }
                const newer = cmpVersion(latest, PKG_VERSION) > 0;
                return textResult({ currentVersion: PKG_VERSION, latestVersion: latest,
                    updateAvailable: newer, checked: true,
                    ...(newer ? { upgradeCommand: '重跑 install（同一行装命令）' } : {}) });
            },
        },
    ];

    // D-dsh-mcp-b-1：工具面两条路——① MCP client 挂 python server（工具面随 packs：默认
    // core,collect=10，含 knowledge=12；机器级 state、
    // 两段式/ensure 全在）；② 壳自注册（6 工具，mcp-client 缺失或显式关闭时的降级形态）。
    // registerTools=false 时壳只提供 UI 半（浏览器按钮），不再注册任何工具。
    const registerShellTools = cfg().registerTools !== false;
    if (registerShellTools) for (const t of tools) ctx.tools.register(t);

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

    if (registerShellTools) {
        console.log(`[dsh-vod-devkit] Registered ${tools.length} tools, apiBase=${cfg().base}` +
            (cfg().key ? ', key=set' : ', key=none (auto anonymous-token on first submit)') +
            (cfg().product ? `, product=${cfg().product}` : ', product=unset (must be set or passed per call)'));
    } else {
        console.log(`[dsh-vod-devkit] UI only（registerTools=false）：工具面由 MCP client 提供`
            + `（serverName=vod-devkit，工具名 mcp__vod-devkit__vod_*），apiBase=${cfg().base}`);
    }
}
