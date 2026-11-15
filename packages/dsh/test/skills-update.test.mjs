// dsh 壳的只读面回归锁：技能披露 + 版本提醒（2026-11-11 对齐 Python 侧）。
// 背景：dsh 是本插件唯一没有 MCP 的宿主，此前只有 3 个工具，规则/更新闻不到；
// 而安装器在 11-11 前根本没给 dsh 落技能（已修）。这里锁四条：
// ① list/retrieve 读的是宿主技能目录（VOD_SKILLS_DIR 可指）②坏名/缺名不抛
// ③ 版本提醒有 24h 缓存与失败静默 ④ dismiss 冷却 3 天。
// 运行时路径用 VOD_DSH_RUNTIME 指到 tmp——dsh/data/runtime.json 里有真实账本。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const skillsDir = mkdtempSync(join(tmpdir(), 'dsh-skills-'));
const runtimeDir = mkdtempSync(join(tmpdir(), 'dsh-rt-'));
process.env.VOD_SKILLS_DIR = skillsDir;
process.env.VOD_DSH_RUNTIME = join(runtimeDir, 'runtime.json');

for (const [name, desc] of [
  ['vod-core', '路由入口与纪律速查'],
  ['vod-feedback-collect', '采集话术与确认纪律'],
  ['vod-scoring-rules', '四项评分公式'],
]) {
  mkdirSync(join(skillsDir, name), { recursive: true });
  writeFileSync(join(skillsDir, name, 'SKILL.md'),
    `---\nname: ${name}\ndescription: '${desc}'\n---\n\n# ${name}\n正文\n`);
}

const { apply } = await import('../lib/index.js');

function loadTools(cfg = { apiBase: 'https://vod-dev.topxtopx.com', apiKey: 'k', product: 'CodeArts' }) {
  const map = new Map();
  apply({ on() {}, tools: { register(t) { map.set(t.name, t); } } }, cfg);
  return map;
}

test('list_skills 读宿主技能目录并标注 pack', async () => {
  const tools = loadTools();
  const out = await tools.get('vod_list_skills').execute({});
  const names = out.skills.map((s) => s.name).sort();
  assert.deepEqual(names, ['vod-core', 'vod-feedback-collect', 'vod-scoring-rules']);
  const by = Object.fromEntries(out.skills.map((s) => [s.name, s]));
  assert.equal(by['vod-core'].pack, 'core');
  assert.equal(by['vod-scoring-rules'].pack, 'knowledge');
  assert.ok(by['vod-scoring-rules'].description.includes('评分'));
});

test('retrieve_skill 返回原文；坏名/未知名给可用清单且不抛', async () => {
  const tools = loadTools();
  const t = tools.get('vod_retrieve_skill');
  const ok = await t.execute({ name: 'vod-scoring-rules' });
  assert.ok(ok.content.startsWith('---'), '必须返回 SKILL.md 原文');
  assert.equal(ok.truncated, false);
  const bad = await t.execute({ name: '../etc/passwd' });
  assert.equal(bad.error, 'bad-name');
  assert.ok(bad.available.includes('vod-core'));
  const missing = await t.execute({ name: 'vod-category-matching' });
  assert.equal(missing.error, 'not-found');
  assert.ok(missing.available.length >= 3);
});

test('check_update：有新版本给升级命令，24h 内不重复打 registry', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return { ok: true, json: async () => ({ version: '99.0.0' }) };
  };
  const t = loadTools().get('vod_check_update');
  const first = await t.execute({});
  assert.equal(first.updateAvailable, true);
  assert.equal(first.latestVersion, '99.0.0');
  assert.ok(first.upgradeCommand);
  const second = await t.execute({});
  assert.equal(second.checked, true);
  assert.equal(calls, 1, '24h 缓存失效=每次会话都打 registry');
});

test('check_update：registry 不可达静默降级', async () => {
  globalThis.fetch = async () => { throw new Error('offline'); };
  const t = loadTools().get('vod_check_update');
  // 清缓存态：直接删文件（测试自持 tmp）
  const { rmSync } = await import('node:fs');
  rmSync(process.env.VOD_DSH_RUNTIME, { force: true });
  const out = await t.execute({});
  assert.equal(out.checked, false);
  assert.equal(out.updateAvailable, false);
  assert.ok(out.note.includes('不影响采集'));
});

test('check_update：dismiss 后冷却期内不再外呼', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; return { ok: true, json: async () => ({ version: '99.1.0' }) }; };
  const t = loadTools().get('vod_check_update');
  const d = await t.execute({ dismiss: true });
  assert.ok(d.dismissedUntil);
  const after = await t.execute({});
  assert.equal(after.updateAvailable, false);
  assert.equal(calls, 0);
});