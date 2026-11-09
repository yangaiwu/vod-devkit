// D-rguard-1 ReceiptGuard 契约锁（node --test 运行）：
// ①纯函数行为：规范化/相似度/单条判定/会话原文采集/回执汇总
// ②提交链接线：cfg 档位白名单（非法值回落 report）、enforce 拒收理由串、
//   回执 receiptGuard 字段、默认 report（零危害只标注）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const indexSrc = readFileSync(join(ROOT, 'lib', 'index.js'), 'utf8');
const {
  normalizeForGuard, bigramSimilarity, evaluateVoiceGuard,
  collectUserTurns, rgGuardSummary, RG_MODES,
} = await import(join(ROOT, 'lib', 'index.js'));

// ── 纯函数 ──

test('normalizeForGuard: 空白折叠+小写化', () => {
  assert.equal(normalizeForGuard('  Hello  World \n'), 'helloworld');
  assert.equal(normalizeForGuard(null), '');
});

test('bigramSimilarity: 相同为1、无重叠为0、部分重叠居中', () => {
  assert.equal(bigramSimilarity('abc', 'abc'), 1);
  assert.equal(bigramSimilarity('abcd', 'wxyz'), 0);
  const s = bigramSimilarity('用户说界面很卡', '用户反馈界面很卡顿');
  assert.ok(s > 0.3 && s < 1, `部分重叠应居中，实得 ${s}`);
  assert.equal(bigramSimilarity('', 'abc'), 0);
});

test('evaluateVoiceGuard: 整串命中=verified（含跨轮纯子集聚合）', () => {
  const turns = ['这个导出按钮点不动', '补充：是 Excel 导出'];
  assert.equal(evaluateVoiceGuard(turns, '这个导出按钮点不动'), 'verified');
  assert.equal(evaluateVoiceGuard(turns, '导出按钮点不动'), 'verified'); // 去空白子串
});

test('evaluateVoiceGuard: 跨轮聚合中模型自加连接词=改写（判 mismatch）', () => {
  // '。补充' 是模型加的胶水词，不是用户原话——内容超集≠忠实转写
  assert.equal(evaluateVoiceGuard(['A问题'], 'A问题。补充B'), 'mismatch');
});

test('evaluateVoiceGuard: 编造内容=mismatch（dsh headless echo 改字同型）', () => {
  const turns = ['搜索结果排序不对'];
  assert.equal(evaluateVoiceGuard(turns, '用户对性能体验非常不满意'), 'mismatch');
});

test('evaluateVoiceGuard: 轻量顺滑转写=fuzzy；原文不可得=unavailable；空 content=mismatch', () => {
  const turns = ['这个导入功能太慢了，等半天都没反应，体验特别差'];
  const s = evaluateVoiceGuard(turns, '导入功能太慢，等半天没反应，体验特别差');
  assert.ok(s === 'fuzzy' || s === 'verified', `顺滑转写不应判 mismatch，实得 ${s}`);
  assert.equal(evaluateVoiceGuard(null, '任意'), 'unavailable');
  assert.equal(evaluateVoiceGuard(['原文'], '   '), 'mismatch');
});

test('collectUserTurns: 只取 user 轮 text 块（tool_result 同 role 按块型过滤）；无会话=null', () => {
  const session = {
    deriveMessages: () => ([
      { role: 'user', content: [{ type: 'text', text: '第一条原话' }] },
      { role: 'assistant', content: [{ type: 'text', text: '模型回复不算原文' }] },
      { role: 'user', content: [{ type: 'tool_result', text: '工具结果不是用户原话' }] },
      { role: 'user', content: [{ type: 'text', text: '第二条原话' }] },
    ]),
  };
  assert.deepEqual(collectUserTurns(session), ['第一条原话', '第二条原话']);
  assert.equal(collectUserTurns(undefined), null);
  assert.equal(collectUserTurns({}), null);
});

test('rgGuardSummary: 顺序位补全 unavailable + 计数', () => {
  const m = new Map([[0, 'verified'], [2, 'mismatch']]);
  const s = rgGuardSummary(m, 3);
  assert.deepEqual(s.verdicts, ['verified', 'unavailable', 'mismatch']);
  assert.equal(s.mismatch, 1);
  assert.equal(s.unavailable, 1);
});

// ── 提交链接线（源码锁，与 d-anon-ui.test 同款口径）──

test('接线: 配置档位白名单+默认 report', () => {
  assert.ok(indexSrc.includes("receiptGuard: z.string().default('report')"), 'Config 默认 report');
  assert.ok(indexSrc.includes("? readCfg(config?.receiptGuard, 'report') : 'report'"), '非法档位回落 report');
  assert.deepEqual(RG_MODES, ['off', 'report', 'enforce']);
});

test('接线: enforce 拒收理由串+回执字段在位', () => {
  assert.ok(indexSrc.includes('ReceiptGuard: content 与会话用户原文不一致'));
  assert.ok(indexSrc.includes('ReceiptGuard: 会话原文不可得，无法校验'));
  assert.ok(/rgMode !== 'off' \? \{ receiptGuard: rgGuardSummary/.test(indexSrc), '回执带 receiptGuard 汇总');
  assert.ok(indexSrc.includes('collectUserTurns(exec?.agent?.session)'), '原文通道=会话日志 user 轮');
});

test('接线: 提交载荷不带 guard 字段（引擎契约零变更，guard 只在插件回执层）', () => {
  assert.ok(!/hv\.receiptGuard|hoard\[\d\]\.receiptGuard|\{\.\.\.hv, receiptGuard/.test(indexSrc),
    '不得把 guard 字段混入引擎载荷——契约变更须走双仓评审');
});

test('client.jsx 声明 inject: [slots]（dsh runner 声明守卫，2026-11-10 真机实锤）', () => {
  const src = readFileSync(new URL('../src/client.jsx', import.meta.url), 'utf8');
  assert.ok(/export const inject = \['slots'\]/.test(src),
    '缺 slots 服务声明——rejectGuard 会静默中止 apply，反馈按钮不渲染');
  const lib = readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8');
  // lib 级码点转义断言：esbuild 会把键名压缩，但导出表必须含 slots 声明
  assert.ok(lib.includes('slots') || lib.includes('inject'),
    'lib/client.js 构建后须保留 slots 声明痕迹');
});

test('按钮定位无宽度自锁（右缘锚定，2026-11-10 竞态实锤）', () => {
  const src = readFileSync(new URL('../src/client.jsx', import.meta.url), 'utf8');
  // 病灶禁入锁：style.width 赋值=宽度自测量回归（0 测 24 自锁，只剩文字症状）
  assert.ok(!/\.style\.width\s*=/.test(src), 'client.jsx 不得写 style.width（自锁病灶）');
  // 0 宽守卫 + 右缘锚定在位
  assert.ok(/offsetWidth === 0\) return/.test(src), '需 offsetWidth===0 守卫');
  assert.ok(/style\.right\s*=/.test(src), '需右缘锚定（style.right）');
  assert.ok(/style\.left\s*=\s*'auto'/.test(src), 'left 须清 auto（防 left+right 拉伸）');
  const lib = readFileSync(new URL('../lib/client.js', import.meta.url), 'utf8');
  assert.ok(!/\.style\.width=/.test(lib), 'lib 构建后同样不得含 style.width 赋值');
});
