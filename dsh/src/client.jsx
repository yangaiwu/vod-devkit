/**
 * dsh-vod-devkit 浏览器半（client half）：
 *   输入框 dock 槽（conversation.composer.dock）注册 😊 反馈按钮 →
 *   弹窗表单 → POST {VOD}/external/voices 囤积入库（不触发分析）。
 *
 * 形态纪律（对齐 docs/dsh-ui-collect.md）：
 * - 纯浏览器组件，凭据不出 node 半以外的任何面：UI 通道用零字段
 *   匿名令牌（localStorage），无 key 概念，无凭据托管
 * - 知情同意：附昵称默认勾选、可取消，不静默外传
 * - 确定性本地对账键 f(deviceId, content)：同机重试幂等、跨机不吞声量
 * - 引擎侧 body.voiceId 被忽略（V9 自算确定性键），本地键仅供账本
 * - 回执说人话（F2）：不展示 voiceId/编号；匿名档「已收录，审核后跟进」
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
// 分类 chips（参考官方 message-feedback 七分类，对齐 agent 产品反馈维度）
const CATEGORIES = [
  { id: 'task-result', label: '任务结果' },
  { id: 'instruction-following', label: '指令理解与遵循' },
  { id: 'product-interaction', label: '产品功能与交互' },
  { id: 'service-stability', label: '稳定性和速度' },
  { id: 'resource-cost', label: '资源使用与费用' },
  { id: 'security-privacy', label: '安全隐私与权限' },
  { id: 'other', label: '其他' },
];

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
  const buf = await crypto.subtle.digest('SHA-1',
    new TextEncoder().encode(s));
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function localVoiceKey(content) {
  // 本地对账键（引擎有独立确定性键，此键仅账本）
  return `ext_dshui_${(await sha1Hex(getDeviceId())).slice(0, 8)}_${(await sha1Hex(content)).slice(0, 12)}`;
}

function ledgerAppend(row) {
  const rows = JSON.parse(localStorage.getItem(LS_LEDGER) || '[]');
  rows.unshift(row);
  localStorage.setItem(LS_LEDGER,
    JSON.stringify(rows.slice(0, LEDGER_CAP)));
}

async function ensureToken(setHint) {
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

/* ---------- 表单弹窗 ---------- */

const S = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 9999,
    background: 'rgba(0,0,0,.35)', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  },
  card: {
    width: 420, maxWidth: '92vw', background: 'var(--dsw-alias-bg-card, #fff)',
    color: 'var(--dsw-alias-label-primary, #111)', borderRadius: 12,
    padding: 20, boxShadow: '0 8px 40px rgba(0,0,0,.2)',
    fontFamily: 'inherit',
  },
  textarea: {
    width: '100%', boxSizing: 'border-box', minHeight: 96, borderRadius: 8,
    border: '1px solid var(--dsw-alias-border-l2, #ccc)',
    padding: 8, fontSize: 13, resize: 'vertical',
    background: 'transparent', color: 'inherit',
  },
  input: {
    width: '100%', boxSizing: 'border-box', borderRadius: 8,
    border: '1px solid var(--dsw-alias-border-l2, #ccc)',
    padding: '6px 8px', fontSize: 13,
    background: 'transparent', color: 'inherit',
  },
  btn: {
    borderRadius: 8, padding: '7px 14px', fontSize: 13,
    cursor: 'pointer', border: 'none',
  },
};

function FeedbackModal({ onClose }) {
  const [content, setContent] = useState('');
  const [scene, setScene] = useState('');
  const [category, setCategory] = useState('other');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // {ok, msg}
  const dialogRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function submit() {
    const text = content.trim();
    if (!text) { setDone({ ok: false, msg: '请先填写反馈内容' }); return; }
    if (text.length > 2000) {
      setDone({ ok: false, msg: `内容超长（${text.length}/2000），请精简` });
      return;
    }
    setBusy(true); setDone(null);
    try {
      const key = await localVoiceKey(text);
      const row = {
        voiceKey: key, title: text.slice(0, 60), scene: scene.trim(), category,
        at: new Date().toISOString(),
      };
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
              description: `dsh UI 采集｜分类：${
                (CATEGORIES.find((c) => c.id === category) || {}).label || category
              }${scene.trim() ? '｜场景：' + scene.trim() : ''}`,
              content: text,
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
        row.status = 'failed';
        row.error = String(e && e.message || e);
        ledgerAppend(row);
        setDone({ ok: false, msg: `提交失败（${row.error}）；反馈已暂存本机，稍后重试。` });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={S.overlay} onMouseDown={(e) =>
      (e.target === e.currentTarget || e.target === dialogRef.current) && onClose()}>
      <div ref={dialogRef} style={S.card} role="dialog" aria-label="VOD 开发者反馈">
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
          😊 反馈一句
        </div>
        <div style={{ fontSize: 12, opacity: 0.65, marginBottom: 12 }}>
          你的反馈将进入 VOD 开发者声音分析平台，帮助 dsh 变得更好。
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {CATEGORIES.map((c) => (
            <button key={c.id} style={{
              ...S.btn, fontSize: 12, padding: '4px 10px',
              borderRadius: 999,
              background: category === c.id
                ? 'var(--dsw-alias-state-business-primary, #2563eb)' : 'transparent',
              color: category === c.id ? '#fff' : 'inherit',
              border: '1px solid var(--dsw-alias-border-l2, #ccc)',
            }} onClick={() => setCategory(c.id)}>{c.label}</button>
          ))}
        </div>
        <textarea style={S.textarea} value={content} maxLength={2000}
          placeholder="比如：补全太慢，希望优化速度" autoFocus
          onChange={(e) => setContent(e.target.value)} />
        <div style={{ fontSize: 11, opacity: 0.5, textAlign: 'right',
          margin: '4px 0 10px' }}>{content.length}/2000</div>
        <div style={{ fontSize: 12, marginBottom: 10 }}>
          <input style={S.input} value={scene} placeholder="使用场景（选填），如：代码补全"
            onChange={(e) => setScene(e.target.value)} />
        </div>
        {done && (
          <div style={{
            fontSize: 12, marginBottom: 12, padding: 8, borderRadius: 8,
            background: done.ok ? 'rgba(46,160,67,.12)'
              : 'rgba(238,102,17,.12)',
          }}>{done.msg}</div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button style={{ ...S.btn, background: 'transparent',
            color: 'inherit' }} onClick={onClose}>关闭</button>
          <button style={{ ...S.btn,
            background: 'var(--dsw-alias-brand-primary, #2563eb)',
            color: '#fff' }} disabled={busy || !content.trim()}
            onClick={submit}>{busy ? '提交中…' : '提交反馈'}</button>
        </div>
      </div>
    </div>
  );
}

/* ---------- dock 按钮（注册进 conversation.composer.dock） ---------- */

function SmileyButton() {
  const [open, setOpen] = useState(false);
  return (
    <React.Fragment>
      <button title="反馈开发者声音" aria-label="反馈开发者声音"
        style={{
          border: 'none', background: 'transparent', fontSize: 16,
          cursor: 'pointer', padding: '2px 6px', borderRadius: 6,
          color: 'inherit',
        }}
        onClick={() => setOpen(true)}>😊</button>
      {open && <FeedbackModal onClose={() => setOpen(false)} />}
    </React.Fragment>
  );
}

/* ---------- 插件入口（slot 注册，官方 activity pill 同款模式） ---------- */

export function apply(ctx) {
  ctx.slots.inject('conversation.composer.dock', function* () {
    yield ctx.slots.register(
      { name: 'conversation.composer.dock', id: 'vod-feedback', order: 20 },
      SmileyButton,
    );
  });
}

export const name = 'vod-devkit-ui';
