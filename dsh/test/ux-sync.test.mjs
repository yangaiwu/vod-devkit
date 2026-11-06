// UX 定稿同步锁（2026-11-06 用户反馈：web widget 的 UX 定稿未同步 dsh 壳——各壳独立实现漂移实锤）：
// 1. 提示语固定单句：不得出现「会原样转达给产品团队」括号后缀与
//    「具体现象更容易被受理…」引导句（widget 定稿：引导暗示反馈范围=示例窄化）；
// 2. 不复述 maxlength：不得向用户展示 {content.length}/2000 计数器
//    （用户碰不到的边界=负面框架；maxLength 硬帽保留）；
// 3. 「我的反馈」入口暂撤（2026-11-05 拍板）：HistoryPanel 入口不渲染，
//    账本写入保留（saveHistory/E() 仍在，数据链不动）。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

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
