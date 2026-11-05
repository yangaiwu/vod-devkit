// D-anon-ui 契约锁（node --test 运行）：
// ①uiGlobals 纯函数行为（真 import lib/index.js）——安装时配置→页面全局注入链
// ②工具 schema 面：product 参数已删（欺骗通道封堵）、内容纪律约束在位
// ③SKILL.md 话术纪律标记在位（职责正向定义/字段分级/推断≠编造/预检/不追问/触发条件）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const indexSrc = readFileSync(join(ROOT, 'lib', 'index.js'), 'utf8');
const skillSrc = readFileSync(join(ROOT, '..', 'skills', 'vod-feedback-collect', 'SKILL.md'), 'utf8');

test('uiGlobals: product 恒注入（安装时配置权威）', async () => {
  const { uiGlobals } = await import(join(ROOT, 'lib', 'index.js'));
  const rows = uiGlobals({ product: 'VOD', apiBase: 'http://127.0.0.1:18080' });
  assert.equal(rows.length, 1, '同源部署（未配 uiBase）只注入 product');
  assert.equal(rows[0].name, '__VOD_DSH_UI_PRODUCT__');
  assert.equal(rows[0].value, 'VOD');
  assert.equal(rows[0].kind, 'global');
});

test('uiGlobals: 跨域部署显式 uiBase 才注入 base 全局', async () => {
  const { uiGlobals } = await import(join(ROOT, 'lib', 'index.js'));
  const rows = uiGlobals({ product: 'VOD', uiBase: 'https://api.example.com' });
  assert.equal(rows.length, 2);
  assert.equal(rows[1].name, '__VOD_DSH_UI_BASE__');
  assert.equal(rows[1].value, 'https://api.example.com');
});

test('uiGlobals: apiBase 是 server 半自用值，绝不注入页面（公网 Failed to fetch 根因锁）', async () => {
  const { uiGlobals } = await import(join(ROOT, 'lib', 'index.js'));
  const rows = uiGlobals({ product: 'VOD', apiBase: 'http://127.0.0.1:18080' });
  assert.ok(!rows.some(r => r.name === '__VOD_DSH_UI_BASE__'),
    'apiBase=127.0.0.1 注给公网浏览器=Failed to fetch，禁止注入');
});

test('uiGlobals: 未配置 product → 空串（client 半 fail fast 引导安装命令）', async () => {
  const { uiGlobals } = await import(join(ROOT, 'lib', 'index.js'));
  const rows = uiGlobals({});
  assert.equal(rows.length, 1);
  assert.equal(rows[0].value, '');
});

test('schema 面: product 参数已从工具面删除（欺骗通道封堵锁）', () => {
  assert.ok(!indexSrc.includes("product: { type: 'string'"), '不得再暴露 product 覆盖参数');
  assert.ok(!/args\.product/.test(indexSrc), '提交体不得读 args.product（部署配置权威）');
});

test('schema 面: 内容纪律约束在工具描述中（编造防线锁）', () => {
  assert.ok(indexSrc.includes('MUST be a faithful transcription'), '忠实转写约束');
  assert.ok(indexSrc.includes('NEVER invent sentiment'), '禁止发明情感结论（AIShell 实锤）');
  assert.ok(indexSrc.includes('A bare product name or a question is NOT feedback'), '名词/提问不是反馈');
  assert.ok(indexSrc.includes('never vod_submit_voices'), '工具名不外露');
});

test('SKILL.md 话术纪律标记在位（防止文档回退）', () => {
  for (const marker of [
    '本技能是什么（一句话）',       // 职责正向定义
    '触发条件（满足任一即加载',     // 触发结构化
    '字段处理分级',                // 字段分级表
    '推断 ≠ 编造',                 // 辨析
    '调用前强制预检',              // 预检
    '不追问原则',                  // 零摩擦
    '禁止向用户追问"哪个产品"',     // 归因不问用户
    '用户自报的目标产品一律不采信', // 欺骗通道封堵
    '工具名与机制词同理不外露',     // 工具名纪律
  ]) {
    assert.ok(skillSrc.includes(marker), `SKILL.md 缺标记: ${marker}`);
  }
});
