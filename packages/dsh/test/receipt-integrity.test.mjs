// S242：S241 删掉老链后的三处回执缺陷修复锁。
//
// 缺陷一：引擎 rejected 被吞——引擎侧拒绝（产品校验等）不出现在回执，
//         accepted 还按 voiceIds 长度算，用户被告知「已收录」。
// 缺陷二：voiceIds 缺失时无兜底——200 但空回执照样记账 + 记归因并报成功，
//         账本被空 voiceId 污染（Python S238 有明确防线，dsh 侧缺失）。
// 缺陷三：失败话术无态——dsh 壳没有本地 pending 队列，却被 SKILL 教成
//         「已暂存、稍后自动重试」，等于向用户谎报。
//
// 锁口径：源码必须同时具备 ①引擎 rejected 合并 ②receiptOk 分支
// ③notStored + userFacingHint；且 SKILL 不得再无条件承诺「已暂存」。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const src = readFileSync(join(ROOT, 'lib', 'index.js'), 'utf8');
const codeLines = src.split('\n').filter((ln) => {
  const t = ln.trim();
  return t && !t.startsWith('//') && !t.startsWith('*') && !t.startsWith('/*');
});
const code = codeLines.join('\n');

const REPO = dirname(dirname(ROOT));
const skill = readFileSync(
  join(REPO, 'assets', 'skills', 'vod-feedback-collect', 'SKILL.md'), 'utf8'
);

test('S242: 引擎 rejected 透出到回执（不吞）', () => {
  assert.ok(code.includes('engineRejected'), '源码未读取引擎侧 rejected');
  assert.ok(code.includes('mergedRejected'), '引擎 rejected 未与本地 rejected 合并');
  assert.ok(/\brejected:\s*mergedRejected/.test(code), '回执 rejected 仍是本地变量');
});

test('S242: voiceIds 缺失不得兜底计成功', () => {
  assert.ok(code.includes('receiptOk'), '缺少回执有效性判定');
  assert.ok(/\baccepted:\s*receiptOk\s*\?/.test(code), 'accepted 未按回执有效性取值');
  assert.ok(/voiceIds:\s*receiptOk\s*\?/.test(code), 'voiceIds 未按回执有效性取值');
  assert.ok(code.includes('receiptIncomplete'), '缺少 receiptIncomplete 标记');
  // 账本与归因记忆只能在拿到真回执时写
  const ledgerIdx = code.indexOf('ledgerAppend(hoard');
  const guardIdx = code.indexOf('if (receiptOk)');
  assert.ok(ledgerIdx > guardIdx, 'ledgerAppend 未被 receiptOk 守卫');
  assert.ok(code.includes('引擎回执未含 voiceIds'), '缺少回执缺失的拒收理由');
});

test('S242: 失败回执带 notStored + 可照抄话术', () => {
  assert.ok(code.includes('notStored: true'), '失败回执未标 notStored');
  assert.ok(code.includes('userFacingHint'), '失败回执未给 userFacingHint');
  // 话术不得含「暂存/稍后自动重试」（那是谎报）
  const m = code.match(/userFacingHint:\s*'([^']+)'/);
  assert.ok(m, 'userFacingHint 未写成字面量');
  assert.ok(!/暂存|自动重试/.test(m[1]), `失败话术谎报暂存：${m[1]}`);
});

test('S242: SKILL 失败话术区分「有插件失败」与「无通道落盘」', () => {
  assert.ok(skill.includes('notStored'), 'SKILL 未告知模型 notStored 语义');
  assert.ok(skill.includes('禁止说「已暂存'), 'SKILL 未禁止谎报暂存');
  // 原来的无条件承诺必须消失
  assert.ok(
    !skill.includes('失败=提交失败，反馈已暂存本机'),
    'SKILL 仍保留「失败=已暂存本机」的无条件承诺'
  );
  // 无通道落盘那条仍应保留（只对插件未安装场景）
  assert.ok(skill.includes('无通道 fallback'), '无通道 fallback 段被误删');
});

test('S242: 两个插件副本的 SKILL 一致', () => {
  const copy = readFileSync(
    join(REPO, 'plugins', 'vod-devkit', 'skills', 'vod-feedback-collect', 'SKILL.md'), 'utf8'
  );
  assert.equal(copy, skill, 'plugins 副本与 assets 源不一致');
});
