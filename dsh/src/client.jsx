/**
 * dsh-vod-devkit 浏览器半（client half）：
 *   输入框右上角反馈图标 → 弹窗表单（官方 Modal/Button 原语+dsw 令牌）
 *   → POST {VOD}/external/voices 囵积入库（不触发分析）。
 *
 * 形态纪律（对齐 docs/dsh-ui-collect.md）：
 * - 纯浏览器组件，UI 通道用零字段匿名令牌（localStorage），无凭据托管
 * - 身份=登录态二值：未登录纯匿名（v1）；登录取账号快照（v1.1 待接）
 * - 分类=VOD 引擎 v2.2 六类口径 chips，默认不选（引擎 LLM 全量重判，
 *   错误预分类比留空更糟）；选中仅作 problem_type hint（desc 前缀+tags）
 * - scene 独立字段已移除（T7h）：VOD-Project 全仓无独立场景字段（库/契约/归一化均无），场景写进正文
 * - 本地对账键 f(deviceId, content)：同机重试幂等、跨机不吞声量；
 *   引擎有独立确定性键（V9），本键仅账本
 * - 回执说人话（F2）：voiceId 不展示给用户
 * - 样式：官方 message-feedback 同款（Modal/Button 原语 + --dsw-alias 令牌）
 */
import React, { useState, useRef, useEffect } from 'react';

const API_PREFIX = '/rest/developer/manager/hdvodmngservice/v1';
let BASE = (typeof globalThis !== 'undefined'
  && globalThis.__VOD_DSH_UI_BASE__) || ''; // '' = 同源（宿主代理 /rest/，公网/内网/本地同构）
const TOKEN_PATH = `${API_PREFIX}/external/token`;
const VOICES_PATH = `${API_PREFIX}/external/voices`;
const META_PATH = `${API_PREFIX}/external/meta`; // T7i：productCatalog 解析源
const LS_TOKEN = 'vod_dshui_token';
// 渠道=T7b 定稿：引擎囤积入库侧固定赋值 vod-agent（链路即渠道，客户端不自报）——
// 本端零字段取令牌（方案 C 原样），无任何渠道上报参数
const LS_DEVICE = 'vod_dshui_device';
const LS_LEDGER = 'vod_dshui_ledger';
const LS_DRAFT = 'vod_dshui_draft';
const LS_RECOVERED = 'vod_dshui_recovered'; // 后台重试成功的条数（下次打开弹窗补提示）
const LEDGER_CAP = 200;
// 企业数据驻留（--no-local-ledger）：server 半经 index-inject 注入禁用旗标，
// UI 停写账本 + 隐藏历史入口（显式不可用，不显示空列表——三主体边界拍板）
const LEDGER_DISABLED = (typeof globalThis !== 'undefined'
  && globalThis.__VOD_DSH_UI_LEDGER_DISABLED__ === true);
// 宿主/产品名：嵌入方可经 __VOD_DSH_UI_PRODUCT__ 注入（解耦：任何支持
// 本插件能力的 agent 装上后文案自动对，不注入=中性通用文案）
const UI_PRODUCT = (typeof globalThis !== 'undefined'
  && globalThis.__VOD_DSH_UI_PRODUCT__) || '';

// 分类 chips：云声表单三分类（VOD-Project 采集层标准——面向人的表单用平台
// 标准枚举：功能建议/用户体验/产品缺陷；与 suggestionType 1/2/3 逐字对齐）。
// 六类是分析层 n01 LLM 内部枚举，不泄漏给人看表单；3→6 的映射由 n01 重判
// 本身承担（云声链同款：选"功能建议"→标题【功能建议】→n01 判六类之一）。
// 默认不选=不预分类（引擎全量重判——错误预分类比留空更糟）；
// 选中=采集层渠道原生分类，以【类型名】标题前缀正式入库（T7c）。


/* 样式：对齐官方 message-feedback 的 dsw 设计令牌 */
const S = {
  textarea: {
    width: '100%', boxSizing: 'border-box', minHeight: 96,
    borderRadius: 'var(--dsw-radius-sm, 8px)',
    border: '1px solid var(--dsw-alias-border-l3, #ccc)',
    padding: '8px 10px', fontSize: 13, resize: 'none', // 禁拉伸（2026-11-06 用户反馈：弹窗内输入框不该有 resize 角，拉拽顶破布局）
    background: 'var(--dsw-alias-bg-layer-1, transparent)',
    color: 'var(--dsw-alias-label-primary, #111)',
    outline: 'none',
  },
  input: {
    width: '100%', boxSizing: 'border-box',
    borderRadius: 'var(--dsw-radius-sm, 8px)',
    border: '1px solid var(--dsw-alias-border-l3, #ccc)',
    padding: '7px 10px', fontSize: 13,
    background: 'var(--dsw-alias-bg-layer-1, transparent)',
    color: 'var(--dsw-alias-label-primary, #111)',
    outline: 'none',
  },
  hint: {
    fontSize: 12, color: 'var(--dsw-alias-label-caption, #999)',
    marginBottom: 12,
  },
  label: {
    fontSize: 12, color: 'var(--dsw-alias-label-secondary, #666)',
    margin: '10px 0 6px',
  },
  result: {
    fontSize: 12, marginBottom: 12, padding: '8px 10px',
    borderRadius: 'var(--dsw-radius-sm, 8px)',
    background: 'var(--dsw-alias-interactive-bg-hover, rgba(0,0,0,.05))',
    color: 'var(--dsw-alias-label-primary, #111)',
  },
};

/* ---------- 工具 ---------- */

function getDeviceId() {
  // 引擎设备锚点只认纯 hex（[0-9a-f]{8,64}）——uuid 连字符会静默降级
  // legacy ip|ua 锚点（NAT 收敛+签发 5 次/天易打满，本机实锤）
  let id = localStorage.getItem(LS_DEVICE);
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID()
      : Date.now().toString(16) + Math.random().toString(16).slice(2)
      + Math.random().toString(16).slice(2)).replace(/[^0-9a-f]/g, '').slice(0, 32);
    localStorage.setItem(LS_DEVICE, id);
  }
  return id;
}

async function sha1Hex(s) {
  // crypto.subtle 只在安全上下文存在（https/localhost）——公网 http
  // 访问时为 undefined（实测踩坑）。本键仅本地账本对账，无密码学要求，
  // 兜底走纯 JS FNV-1a 双种子拼 64bit。
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const buf = await crypto.subtle.digest('SHA-1',
      new TextEncoder().encode(s));
    return [...new Uint8Array(buf)]
      .map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  return fnv1a64(s);
}

function fnv1a64(s) {
  const h1 = 0x811c9dc5, h2 = 0x01000193;
  let a = h1 >>> 0, b = (h2 ^ 0xdeadbeef) >>> 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    a ^= c; a = Math.imul(a, 0x01000193) >>> 0;
    b ^= (c << 3) & 0xffff; b = Math.imul(b, 0x85ebca6b) >>> 0;
  }
  return a.toString(16).padStart(8, '0') + b.toString(16).padStart(8, '0');
}

async function localVoiceKey(content) {
  return `ext_dshui_${(await sha1Hex(getDeviceId())).slice(0, 8)}_${(await sha1Hex(content)).slice(0, 12)}`;
}

function ledgerAppend(row) {
  if (LEDGER_DISABLED) return; // 数据驻留模式：不落本地
  const rows = JSON.parse(localStorage.getItem(LS_LEDGER) || '[]');
  rows.unshift(row);
  localStorage.setItem(LS_LEDGER,
    JSON.stringify(rows.slice(0, LEDGER_CAP)));
}

async function ensureToken() {
  let t = localStorage.getItem(LS_TOKEN);
  if (t) return t;
  const r = await fetch(BASE + TOKEN_PATH, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'X-Vod-Device-Id': getDeviceId() },
    body: '{}',
  });
  if (r.status !== 200 && r.status !== 201) {
    throw new Error(`token ${r.status}`);
  }
  const body = await r.json().catch(() => ({}));
  t = typeof body === 'string' ? body
    : (body.token || body.data?.token || '');
  if (!t) throw new Error('token empty');
  localStorage.setItem(LS_TOKEN, t);
  return t;
}

/* ---------- 自研弹窗/按钮（解耦：零官方组件依赖，dsw 令牌做可选增强） ---------- */

/* 视觉参考官方 message-feedback：遮罩+卡片+标题+关闭+footer。
 * 主题对接走 CSS 变量（--dsw-alias-*）+硬编码兜底——变量在就跟随主题，
 * 不在（非 dsh 宿主或主题改版）就用自己的兜底值，永不裸奔。 */
function SelfModal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9000,
      background: 'rgba(0,0,0,.35)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-label={title} style={{
        width: 'min(488px, 92vw)',
        borderRadius: 'var(--dsw-radius-panel, 12px)',
        background: 'var(--dsw-alias-bg-layer-1, #fff)',
        color: 'var(--dsw-alias-label-primary, #111)',
        padding: '18px 20px', fontFamily: 'inherit',
        boxShadow: '0 8px 40px rgba(0,0,0,.2)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>{title}</div>
          <button onClick={onClose} aria-label="关闭" style={{
            border: 'none', background: 'transparent', cursor: 'pointer',
            fontSize: 16, lineHeight: 1, padding: 4, borderRadius: 6,
            color: 'var(--dsw-alias-label-tertiary, #888)',
          }}>✕</button>
        </div>
        {children}
        {footer && <div style={{ marginTop: 14 }}>{footer}</div>}
      </div>
    </div>
  );
}

function PrimaryBtn({ disabled, onClick, children }) {
  return (
    <button disabled={disabled} onClick={onClick} style={{
      width: '100%', height: 44, fontSize: 14, fontWeight: 500,
      border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
      borderRadius: 'var(--dsw-radius-lg, 10px)',
      background: disabled
        ? 'var(--dsw-alias-interactive-bg-hover, rgba(0,0,0,.06))'
        : 'var(--dsw-alias-button-primary-fill, #2563eb)',
      color: disabled
        ? 'var(--dsw-alias-label-tertiary, #999)'
        : 'var(--dsw-alias-label-primary-foreground, #fff)',
    }}>{children}</button>
  );
}

/* ---------- 暂存自动重试（U-S3：断线/未上线的反馈下次打开自动补提） ---------- */

let retrySweepDone = false;  // 每会话一次

async function retryStashedSubmissions() {
  if (retrySweepDone) return;
  retrySweepDone = true;
  let recovered = 0;
  const rows = JSON.parse(localStorage.getItem(LS_LEDGER) || '[]')
    .filter((r) => r.status === 'pending-endpoint' || r.status === 'failed');
  for (const row of rows.slice(0, 5)) {  // cap 5 防风暴
    try {
      const token = await ensureToken();
      const r = await fetch(BASE + VOICES_PATH, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'X-Vod-Device-Id': getDeviceId(), // 设备锚点随所有请求（令牌按设备签发，漏带=401）
          authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          voices: [{
            title: row.title,
            content: row.content,
          }],
          product: UI_PRODUCT,
        }),
      });
      if (r.status === 200 || r.status === 201) {
        row.status = 'accepted';
        try { localStorage.removeItem(LS_DRAFT); } catch (e) {} // 成功提交清草稿
        const body = await r.json().catch(() => ({}));
        row.serverVoiceId = (body.voiceIds || body.data?.voiceIds || [])[0] || '';
        row.retriedAt = new Date().toISOString();
        recovered++; // 2026-11-06 UX 修复：后台重试成功不再静默——计数落旗标，下次打开弹窗补提示
      } else if (r.status !== 404) {
        row.error = `retry ${r.status}`;
      }
    } catch (e) {
      row.error = String(e && e.message || e);
    }
  }
  const kept = rows.filter((r) => r.status !== 'accepted');
  if (recovered > 0) {
    // 后台重试成功补提示（2026-11-06 UX 修复）：失败提示不随静默重试更新的事故形态。
    // 回显明细走账本原话（方案 A 覆盖恢复场景）；voice-id 不出用户面（F2）；
    // 措辞「已自动重试成功」说清因果=完成用户此前点提交的指令，非绕过确认
    // （暂存仅发生在用户点提交后的技术失败分支，同意前提成立）
    const items = rows.filter((r) => r.status === 'accepted' && r.retriedAt)
      .map((r) => `“${(r.content || r.title || '').slice(0, 60)}”`)
      .join('、');
    try { localStorage.setItem(LS_RECOVERED, JSON.stringify({ n: recovered, items })); } catch (e) {}
  }
  if (kept.length !== rows.length || rows.length) {
    // 回写账本：成功的从暂存态转 accepted，其余原样保留
    const all = JSON.parse(localStorage.getItem(LS_LEDGER) || '[]');
    const byKey = new Map(rows.map((r) => [r.voiceKey, r]));
    const out = all.map((r) => byKey.get(r.voiceKey) || r);
    localStorage.setItem(LS_LEDGER, JSON.stringify(out.slice(0, LEDGER_CAP)));
  }
}

/* ---------- 表单弹窗 ---------- */

function FeedbackModal({ onClose }) {
  // 草稿自动保存（借鉴 DSH-Feedback-Bridge）：刷新/重启不丢半截反馈
  const draft = (() => { try { return JSON.parse(localStorage.getItem(LS_DRAFT) || 'null') || {}; } catch (e) { return {}; } })();
  const [content, setContent] = useState(draft.content || '');
  // 分类已撤（2026-11-05 用户拍板）：n01 引擎全量重判，UI 预分类仅 hint 且
  // 用户分不清边界——三层认知负担换不来信号质量。表单=单输入框
  useEffect(() => {
    try { localStorage.setItem(LS_DRAFT, JSON.stringify({ content })); } catch (e) {}
  }, [content]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // {ok, msg}
  // 后台重试成功补提示（2026-11-06 UX 修复）：打开弹窗时若暂存反馈已被静默重试
  // 成功，把账本状态翻译成人话告诉用户——失败提示不更新=用户以为还在失败
  useEffect(() => {
    let rec = null;
    try { rec = JSON.parse(localStorage.getItem(LS_RECOVERED) || 'null'); } catch (e) {}
    if (rec && rec.n > 0) {
      try { localStorage.removeItem(LS_RECOVERED); } catch (e) {}
      const echo = rec.items ? `，产品团队会看到：${rec.items}` : '' // items 空=残句防护，话术降级为纯状态告知
      setDone({ ok: true, msg: `你之前提交的 ${rec.n} 条反馈已自动重试成功（当时提交临时失败）${echo}` });
    }
  }, []);

  // T7i（方案 A，2026-11-05 拍板）：产品归因主键化——meta productCatalog 按名解析
  // 平台 id 后提交；纯数字=平台 id 透传；目录无此名/不可达 → 名字兼容通道（不静默丢）。
  // 进程内缓存一次，页内刷新即重取。
  let PRODUCT_CATALOG = null;
  async function resolveProductId(product, token) {
    if (/^\d+$/.test(product)) return product;
    try {
      if (!PRODUCT_CATALOG) {
        const r = await fetch(BASE + META_PATH, {
          headers: { authorization: `Bearer ${token}` },
        });
        if (r.ok) {
          const j = await r.json().catch(() => ({}));
          PRODUCT_CATALOG = ((j.data || j).productCatalog) || [];
        }
      }
      const hit = (PRODUCT_CATALOG || []).find(
        (x) => String(x?.name || '').toLowerCase() === product.toLowerCase());
      if (hit && hit.id != null) return String(hit.id);
    } catch (e) { /* 目录不可用 → 名字兼容通道 */ }
    return product;
  }

  async function submit() {
    const text = content.trim();
    if (!text) { setDone({ ok: false, msg: '请先填写反馈内容' }); return; }
    if (text.length > 2000) {
      setDone({ ok: false, msg: `内容超长（${text.length}/2000），请精简` });
      return;
    }
    setBusy(true); setDone(null);
    const row = {
      title: text.slice(0, 64), // voice_title=用户原文前 64 字（单输入框，不加标题摩擦）
      content: text,  // U-S3 重试重建提交体用（本机账本，cap 200）
      // 分类走 tags 正式通道（T7c），description 模板文案已移除
      at: new Date().toISOString(), status: 'failed', error: '',
    };
    try {
      row.voiceKey = await localVoiceKey(text);
      try {
        const token = await ensureToken();
        const r = await fetch(BASE + VOICES_PATH, {
          method: 'POST',
          headers: {
            'content-type': 'application/json', 'X-Vod-Device-Id': getDeviceId(),
            authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            voices: [{
              title: text.slice(0, 60),
              content: text,
              // 分类不预选（D-anon-ui 极简）：tags 不传，n01 引擎全量重判
              // （05ce5fb 撤 chips 时漏删本行引用，ReferenceError 实锤修复+回归锁）
            }],
            // 产品=加载必配（T7d）：入口仅在注入后激活，product 恒有值
            // T7i：注入名→meta 目录解析平台 id 后提交（主键化，名字漂移不进链路）
            product: await resolveProductId(UI_PRODUCT, token),
          }),
        });
        if (r.status === 404) {
          row.status = 'pending-endpoint';
          ledgerAppend(row);
          setDone({ ok: false, msg: '囤积端点尚未上线（引擎部署后自动可用）；反馈已暂存本机，稍后重试提交。' });
          return;
        }
        if (r.status === 401) { localStorage.removeItem(LS_TOKEN); }
        if (r.status !== 200 && r.status !== 201) {
          throw new Error(`submit ${r.status}`);
        }
        const body = await r.json().catch(() => ({}));
        row.status = 'accepted';
        row.serverVoiceId = body.voiceIds?.[0] || '';
        row.taskId = body.taskIds?.[0] || '';
        ledgerAppend(row);
        const reg = body.productRegistered === undefined ? true : body.productRegistered;
        // 话术=行为实况（S51，D-inbox-DIRECT 收口）：引擎直达主声音表、不建 issue，
        // 提交成功即终态提示——无「轮询回执补链接」后续（原 U-S2 轮询随
        // 引擎建单层退场一并拆除，2026-11-09 拍板）
        setDone(reg
          ? { ok: true, msg: '已收录，产品团队会看到这条反馈。' }
          : { ok: true, msg: '已收录。注意：产品名尚未在平台注册，这条反馈暂不进产品分析，请联系部署方核对。' });
      } catch (e) {
        row.error = String(e && e.message || e);
        ledgerAppend(row);
        setDone({ ok: false, msg: `提交失败（${row.error}）；反馈已暂存本机，稍后重试。` });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <SelfModal title="提交反馈" onClose={onClose}
      footer={(
        <PrimaryBtn disabled={busy || !content.trim()} onClick={submit}>
          {busy ? '提交中…' : '提交'}
        </PrimaryBtn>
      )}>
      <textarea id="vod-fb-content" style={S.textarea} value={content} maxLength={2000}
        placeholder="比如：对话响应慢、某个功能找不到入口" autoFocus
        onChange={(e) => setContent(e.target.value)} />
        {/* 场景输入已移除（T7h）：VOD-Project 全仓无独立 scene 字段（库无列/契约无键），
          场景由用户自然写进正文——云声表单同款引导 */}
      {done && <div style={S.result}>{done.msg}</div>}
    </SelfModal>
  );
}


/* ---------- 输入框右上角图标（自定位） ---------- */

function SmileyButton() {
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);

  // 自定位：图标落在输入框右上角（用户拍板）。无现成角位槽——仍挂官方
  // composer.dock 槽作挂载点，JS 计算输入框（contenteditable）矩形，
  // fixed 定位其右上角，ResizeObserver+窗口事件+轮询兜底跟随布局。
  useEffect(() => {
    // U-S3：会话内首挂载补提暂存行（断线/引擎未上线期的反馈）
    retryStashedSubmissions();
    const place = () => {
      const btn = btnRef.current;
      if (!btn) return;
      const input = document.querySelector(
        '[contenteditable=true][role=textbox], [contenteditable=true]');
      if (!input) return;
      const r = input.getBoundingClientRect();
      // 宽度自适应（图标+文字标签）：place 在 render 后跑，读实测 offsetWidth
      const w = btn.offsetWidth || 24, h = 24;
      btn.style.left = Math.round(r.right - w - 8) + 'px';
      btn.style.top = Math.round(r.top - h - 6) + 'px';  // 框外上方（用户实测纠偏：+5 仍在框内）
      btn.style.width = w + 'px';
      btn.style.height = h + 'px';
    };
    place();
    const ro = new ResizeObserver(place);
    ro.observe(document.documentElement);
    window.addEventListener('resize', place);
    const t = setInterval(place, 800);
    return () => { ro.disconnect(); window.removeEventListener('resize', place);
      clearInterval(t); };
  }, []);

  return (
    <React.Fragment>
      <button ref={btnRef} title="反馈" aria-label="反馈开发者声音"
        style={{
          position: 'fixed', zIndex: 300, border: 'none',
          background: 'transparent', cursor: 'pointer', padding: 0,
          display: 'inline-flex', alignItems: 'center', gap: 4,
          borderRadius: 'var(--dsw-radius-sm, 6px)',
          color: 'var(--dsw-alias-label-tertiary, #888)',
          fontFamily: 'inherit',
        }}
        onMouseEnter={(e) => e.currentTarget.style.color =
          'var(--dsw-alias-label-primary, #111)'}
        onMouseLeave={(e) => e.currentTarget.style.color =
          'var(--dsw-alias-label-tertiary, #888)'}
        onClick={() => setOpen(true)}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M21.5 2.5 2.9 10.2c-.8.3-.8 1.5.1 1.7l4.6 1.4 1.7 5.5c.3.9 1.4 1 1.9.3l2.5-3.3 4.6 3.4c.7.5 1.7.1 1.9-.8l3.2-14.4c.2-.9-.7-1.7-1.5-1.4z"/>
          <path d="M7.3 13.5 21.5 2.5l-9.5 12.3"/>
        </svg>
        <span style={{ fontSize: 12, lineHeight: 1, whiteSpace: 'nowrap' }}>反馈</span>
      </button>
      {open && <FeedbackModal onClose={() => setOpen(false)} />}
    </React.Fragment>
  );
}

/* ---------- 插件入口（官方 activity pill 同款注册模式） ---------- */

export function apply(ctx) {
  // 产品归因=加载必配（T7d）：嵌入方（产品部署方）装前必须注入
  // __VOD_DSH_UI_PRODUCT__。无注入=入口不激活+控制台报错（fail fast）——
  // 归因错误比没数据更糟：缺省宿主名在嵌入场景会静默错归（如 Skills 门户
  // 反馈落 dsh）；UNKNOWN 档是运行期兜底（agent 误用），不做配置缺失的常规出口
  if (!UI_PRODUCT) {
    console.error(
      '[vod-devkit] 嵌入方未注入 __VOD_DSH_UI_PRODUCT__，反馈入口未激活。' +
      '产品归因是必配项：嵌入方装前设置 window.__VOD_DSH_UI_PRODUCT__ = "<产品名>"' +
      '（取值=生态看板产品名：高校AI开发者平台/成长中心/AI云原生开发实践中心/鸿蒙开发实践中心/' +
      'AI办公实践中心/IaC 实践中心/AI 开发者空间/AI Agent 集成/AI 工具集成/AI 运行环境/开放能力/' +
      'Skills门户/GTD/VOD）');
    return;
  }
  ctx.slots.inject('conversation.composer.dock', function* () {
    yield ctx.slots.register(
      { name: 'conversation.composer.dock', id: 'vod-feedback', order: 20 },
      SmileyButton,
    );
  });
}

export const name = 'vod-devkit-ui';
