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
 * - scene 按引擎契约独立字段（≤128，引擎侧落 voice_desc 前缀）
 * - 本地对账键 f(deviceId, content)：同机重试幂等、跨机不吞声量；
 *   引擎有独立确定性键（V9），本键仅账本
 * - 回执说人话（F2）：voiceId 不展示给用户
 * - 样式：官方 message-feedback 同款（Modal/Button 原语 + --dsw-alias 令牌）
 */
import React, { useState, useRef, useEffect } from 'react';

const API_PREFIX = '/rest/developer/manager/hdvodmngservice/v1';
const BASE = (typeof globalThis !== 'undefined'
  && globalThis.__VOD_DSH_UI_BASE__) || 'https://vod-dev.topxtopx.com';
const TOKEN_PATH = `${API_PREFIX}/external/token`;
const VOICES_PATH = `${API_PREFIX}/external/voices`;
const LS_TOKEN = 'vod_dshui_token';
const LS_DEVICE = 'vod_dshui_device';
const LS_LEDGER = 'vod_dshui_ledger';
const LEDGER_CAP = 200;

// 分类 chips：VOD 引擎 v2.2 六类口径（n01_classify 真源）。无效问题
// 不给用户选项；默认不选=不预分类（引擎 LLM 全量重判——错误预分类
// 比留空更糟，技能纪律）；选中仅作 problem_type hint。
const CATEGORIES = [
  { id: '产品缺陷', label: '产品缺陷', hint: 'Bug/报错/功能不可用' },
  { id: '技术业务咨询', label: '技术业务咨询' },
  { id: '体验改进', label: '体验改进', hint: '可用但体验差' },
  { id: '功能需求', label: '功能需求', hint: '希望新增能力' },
  { id: '主观评价', label: '主观评价', hint: '纯感受/评分/对比' },
];

/* 样式：对齐官方 message-feedback 的 dsw 设计令牌 */
const S = {
  textarea: {
    width: '100%', boxSizing: 'border-box', minHeight: 96,
    borderRadius: 'var(--dsw-radius-sm, 8px)',
    border: '1px solid var(--dsw-alias-border-l3, #ccc)',
    padding: '8px 10px', fontSize: 13, resize: 'vertical',
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
  let id = localStorage.getItem(LS_DEVICE);
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : 'dev-' + Date.now()
      + '-' + Math.random().toString(36).slice(2));
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
    headers: { 'content-type': 'application/json' },
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

/* ---------- 表单弹窗 ---------- */

function FeedbackModal({ onClose }) {
  const [content, setContent] = useState('');
  const [scene, setScene] = useState('');
  const [category, setCategory] = useState(''); // '' = 不预分类，引擎重判
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // {ok, msg}

  async function submit() {
    const text = content.trim();
    if (!text) { setDone({ ok: false, msg: '请先填写反馈内容' }); return; }
    if (text.length > 2000) {
      setDone({ ok: false, msg: `内容超长（${text.length}/2000），请精简` });
      return;
    }
    setBusy(true); setDone(null);
    const row = {
      title: text.slice(0, 60), scene: scene.trim(), category,
      at: new Date().toISOString(), status: 'failed', error: '',
    };
    try {
      row.voiceKey = await localVoiceKey(text);
      try {
        const token = await ensureToken();
        const r = await fetch(BASE + VOICES_PATH, {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            voices: [{
              title: text.slice(0, 60),
              description: `dsh UI 采集${
                category ? '｜预分类：' + category + '（待引擎重判）' : ''}`,
              content: text,
              scene: scene.trim() ? scene.trim().slice(0, 128) : undefined,
              tags: category ? ['problem_type:' + category] : [],
            }],
            product: 'DSH',
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
        setDone({ ok: true, msg: '已收录，产品团队会看到这条反馈；审核后将以 issue 形式跟进。' });
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
    <SelfModal title="反馈一句" onClose={onClose}
      footer={(
        <PrimaryBtn disabled={busy || !content.trim()} onClick={submit}>
          {busy ? '提交中…' : '提交反馈'}
        </PrimaryBtn>
      )}>
      <div style={S.hint}>
        你的反馈将进入 VOD 开发者声音分析平台，帮助 dsh 变得更好。
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {CATEGORIES.map((c) => (
          <button key={c.id} title={c.hint || ''} style={{
            fontSize: 12, padding: '4px 10px', cursor: 'pointer',
            borderRadius: 'var(--dsw-radius-sm, 999px)',
            background: category === c.id
              ? 'var(--dsw-alias-state-business-primary, #2563eb)' : 'transparent',
            color: category === c.id
              ? 'var(--dsw-alias-label-primary-foreground, #fff)'
              : 'var(--dsw-alias-label-secondary, #666)',
            border: '1px solid var(--dsw-alias-border-l3, #ccc)',
          }}
            onClick={() => setCategory(category === c.id ? '' : c.id)}>
            {c.label}{c.hint ? '·' + c.hint : ''}
          </button>
        ))}
      </div>
      <textarea style={S.textarea} value={content} maxLength={2000}
        placeholder="比如：补全太慢，希望优化速度" autoFocus
        onChange={(e) => setContent(e.target.value)} />
      <div style={{ fontSize: 11, textAlign: 'right', margin: '4px 0 0',
        color: 'var(--dsw-alias-label-tertiary, #999)' }}>
        {content.length}/2000
      </div>
      <div style={S.label}>使用场景（选填）</div>
      <div style={{ fontSize: 12, marginBottom: 6 }}>
        <input style={S.input} value={scene} maxLength={128}
          placeholder="如：代码补全、生成 PR 描述"
          onChange={(e) => setScene(e.target.value)} />
      </div>
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
    const place = () => {
      const btn = btnRef.current;
      if (!btn) return;
      const input = document.querySelector(
        '[contenteditable=true][role=textbox], [contenteditable=true]');
      if (!input) return;
      const r = input.getBoundingClientRect();
      const w = 24, h = 24;
      btn.style.left = Math.round(r.right - w - 8) + 'px';
      btn.style.top = Math.round(r.top + 5) + 'px';
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
          borderRadius: 'var(--dsw-radius-sm, 6px)',
          color: 'var(--dsw-alias-label-tertiary, #888)',
        }}
        onMouseEnter={(e) => e.currentTarget.style.color =
          'var(--dsw-alias-label-primary, #111)'}
        onMouseLeave={(e) => e.currentTarget.style.color =
          'var(--dsw-alias-label-tertiary, #888)'}
        onClick={() => setOpen(true)}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.3 8.9 8.9 0 0 1-3.8-.8L3 21l1.9-4.4a8 8 0 0 1-1-3.9A8.4 8.4 0 0 1 12.4 3.2 8.4 8.4 0 0 1 21 11.5z"/>
          <path d="M8.5 10.5h7M8.5 13.5h4"/>
        </svg>
      </button>
      {open && <FeedbackModal onClose={() => setOpen(false)} />}
    </React.Fragment>
  );
}

/* ---------- 插件入口（官方 activity pill 同款注册模式） ---------- */

export function apply(ctx) {
  ctx.slots.inject('conversation.composer.dock', function* () {
    yield ctx.slots.register(
      { name: 'conversation.composer.dock', id: 'vod-feedback', order: 20 },
      SmileyButton,
    );
  });
}

export const name = 'vod-devkit-ui';
