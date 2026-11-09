// D-inbox-DIRECT 收口锁（2026-11-09 拍板）：引擎直达主声音表、不建 issue——
// dsh UI 的 issue_sync 回执轮询随引擎建单层退场一并拆除：
// 1. src 不得再有 pollIssueSync/pollForReceipt（轮询入口净删）；
// 2. src/lib 均不得再消费 issue_sync 节与「已建成 issue」话术；
// 3. 提交链本体（POST /external/voices + 自动重试）必须保留——拆除仅限轮询。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'client.jsx'), 'utf8');
const lib = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'lib', 'client.js'), 'utf8');

function assertAbsent(text, needle, where) {
  if (text.includes(needle)) throw new Error(`D-inbox-DIRECT 回归：${where} 不应再含「${needle}」`);
}

// 1+2：src 源级锁
assertAbsent(src, 'pollIssueSync', 'src');
assertAbsent(src, 'pollForReceipt', 'src');
assertAbsent(src, 'issue_sync', 'src');
assertAbsent(src, '已建成 issue', 'src');

// 2：构建产物级锁（esbuild 会把 CJK 转义成 \uXXXX，用码点判定）
const esc = (s) => [...s].map(c => '\\u' + c.codePointAt(0).toString(16).padStart(4, '0')).join('');
assertAbsent(lib, esc('issue_sync'), 'lib/client.js');
assertAbsent(lib, esc('已建成 issue'), 'lib/client.js');

// 3：提交链本体保留锁（拆轮询≠拆提交）
for (const needle of ['VOICES_PATH', 'retryStashedSubmissions', 'serverVoiceId']) {
  if (!src.includes(needle)) throw new Error(`D-inbox-DIRECT 回归：提交链被误伤（缺 ${needle}）`);
}
console.log('dsh issue_sync 轮询拆除锁 OK');
