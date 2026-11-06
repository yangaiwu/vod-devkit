// UX 定稿同步锁（2026-11-06 用户反馈：web widget 的 UX 定稿未同步 dsh 壳——各壳独立实现漂移实锤）：
// 1. 提示语固定单句：不得出现「会原样转达给产品团队」括号后缀与
//    「具体现象更容易被受理…」引导句（widget 定稿：引导暗示反馈范围=示例窄化）；
// 2. 不复述 maxlength：不得向用户展示 {content.length}/2000 计数器
//    （用户碰不到的边界=负面框架；maxLength 硬帽保留）；
// 3. 「我的反馈」入口暂撤（2026-11-05 拍板）：HistoryPanel 入口不渲染，
//    账本写入保留（saveHistory/E() 仍在，数据链不动）。
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'client.jsx'), 'utf8');
const lib = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'lib', 'client.js'), 'utf8');

function assertAbsent(text, needle, where) {
  if (text.includes(needle)) throw new Error(`UX 回归：${where} 不应再含「${needle}」`);
}

// 1+2：src 源级锁
assertAbsent(src, '会原样转达给产品团队', 'src');
assertAbsent(src, '具体现象更容易被受理', 'src');
assertAbsent(src, '{content.length}/2000', 'src');
assertAbsent(src, '我的反馈（本机记录，', 'src');

// HistoryPanel 组件已整体删除（入口撤、账本写入保留）
assertAbsent(src, 'function HistoryPanel', 'src');
if (!src.includes('function ledgerAppend')) {
  throw new Error('UX 回归：账本写入函数被误删（入口撤≠写入撤）');
}

// 3：构建产物级锁（esbuild 会把 CJK 转义成 \uXXXX，用码点判定）
const esc = (s) => [...s].map(c => '\\u' + c.codePointAt(0).toString(16).padStart(4, '0')).join('');
for (const needle of ['会原样转达给产品团队', '具体现象更容易被受理', '我的反馈（本机记录']) {
  assertAbsent(lib, esc(needle), 'lib/client.js');
}
console.log('dsh UX 定稿同步锁 OK');

// 提交链 ReferenceError 回归锁（真机实锤 2026-11-06：05ce5fb 撤分类 chips
// 时漏删 submit 请求体里的 tags: category ? ... 引用，UI 提交必抛
// ReferenceError 走暂存分支）。锁：src 中不得再出现裸 category 引用。
const bareCategory = [...src.matchAll(/(?<![.\w])category(?![\w])/g)];
if (bareCategory.length > 0) {
  throw new Error(`提交链回归：src 仍引用已删除的 category 变量（${bareCategory.length} 处）`);
}
console.log('category 残留锁 OK');

// S55 resize 锁（2026-11-06 用户反馈：弹窗输入框不该有拉伸角）
if (!/resize:\s*'none'/.test(src)) throw new Error('S55 回归：textarea 未设 resize:none');
if (/resize:\s*'vertical'/.test(src)) throw new Error('S55 回归：resize:vertical 回流');

// S54 恢复提示要素锁：原话回显在、voice-id/产品名不出用户面、空 items 残句防护
if (!src.includes('已自动重试成功')) throw new Error('S54 回归：恢复补提示话术缺失');
if (!src.includes('（当时提交临时失败）')) throw new Error('S54 回归：因果措辞缺失');
if (!src.includes("rec.items ? `，产品团队会看到")) throw new Error('S54 回归：items 空值残句防护缺失');

// S56 legacy key 明文清退锁（用户面 md 不得出现共用 key 明文）
const userDocs = ['INSTALL.md', 'README.md', 'QUICKSTART.md']
  .map(f => join(ROOT, f)).filter(p => { try { return existsSync(p) } catch { return false } });
for (const p of userDocs) {
  if (readFileSync(p, 'utf8').includes('vod-external-api-key-2026')) {
    throw new Error(`S56 回归：${p} 泄漏 legacy 共用 key 明文`);
  }
}
console.log('S55/S54/S56 锁 OK');

// S51 话术=行为实况锁（2026-11-06 用户抓出）：匿名直建模式无人工审核闸，
// 回执禁止出现「审核后将以 issue 形式跟进」类空头承诺（issue 链接由
// pollForReceipt 在引擎真实建成后补出）
if (src.includes('审核后将以')) throw new Error('S51 回归：回执含不存在的审核跟进承诺');
if (src.includes('反馈经审核未采纳') && !src.includes("sync.status === 'REJECTED'")) {
  throw new Error('S51 回归：REJECTED 话术失去引擎状态承载');
}
console.log('S51 回执实况锁 OK');

// S63 追问前置锁（D-followup-design-1）：引擎无 supplement 承载，采集话术
// 不得出现"追问复现步骤"类承诺（先有承载再进话术）。立项落地（引擎
// supplement 字段+独立存储+来源标注）后应有意识地更新本锁。
if (src.includes('复现步骤') || src.includes('当时在做什么')) {
  throw new Error('S63 回归：采集话术出现追问承诺，但引擎无 supplement 承载（S51 空头支票）');
}
console.log('S63 追问前置锁 OK');
