/**
 * D-drift-1 行为锁：跑题期留底。
 *
 * 真机反例（2026-11-18 对照 DSH 宿主实测对话）：
 *   用户：「产品体验不友好」
 *   → 追问「哪个功能不符合预期」→「界面/导航/设置」
 *   → 用户反问「你是什么技能啊」        ← 话题完全跑题
 *   → agent 顺着介绍 5 分钟能力
 *   → 那句抱怨永久丢失，全程零提交
 *
 * 本锁断言三件机制行为（不是文本包含断言）：
 *   ① 恰好一次拉回：跑题时第一次拉，第二次不再拉（不重复追问）
 *   ② 漂移期留底：跑题过程中出现的抱怨句进缓冲区，不丢
 *   ③ 回来不重说：用户回到话题时同样从缓冲区继续，无需重述
 */
import test from 'node:test';
import assert from 'node:assert/strict';

const { planDriftHandling } = await import('../lib/index.js');

// DSH 那段对话的逐轮原话（含跑题与跑题期的抱怨）
const TURNS = [
    '产品体验不友好',                       // 最初的抱怨
    '功能缺失或不符预期',                    // 追问1的回答
    '界面/导航/设置',                        // 追问2的回答
    '你是什么技能啊',                        // 跑题
    '顺便说一句，设置页保存经常卡住',          // 跑题期间又冒出的一句抱怨
];

test('① 恰好一次拉回：首次跑题拉，已拉过就不再拉', () => {
    const first = planDriftHandling({ userTurns: TURNS, pulledBack: false, offTopic: true });
    assert.equal(first.shouldPullBack, true, '首次跑题应拉回一次');
    assert.equal(first.reason, 'off-topic-first-pull');

    const second = planDriftHandling({ userTurns: TURNS, pulledBack: true, offTopic: true });
    assert.equal(second.shouldPullBack, false, '已拉过不得再拉（禁止重复追问）');
    assert.equal(second.reason, 'off-topic-already-pulled');
});

test('② 漂移期留底：跑题期间出现的抱怨照样进缓冲区', () => {
    const r = planDriftHandling({ userTurns: TURNS, pulledBack: false, offTopic: true });
    assert.ok(r.buffer.includes('产品体验不友好'), '最初的抱怨必须在缓冲区');
    assert.ok(r.buffer.includes('顺便说一句，设置页保存经常卡住'),
        `跑题期间冒出的抱怨也必须留底，实得 ${JSON.stringify(r.buffer)}`);
    assert.ok(!r.buffer.includes('你是什么技能啊'), '纯跑题句不该当反馈留底');
});

test('③ 回来不重说：用户回到话题时从缓冲区继续', () => {
    const r = planDriftHandling({ userTurns: TURNS, pulledBack: true, offTopic: false });
    assert.equal(r.resume, true, '回到话题应可直接续用缓冲区');
    assert.equal(r.reason, 'resumed-with-buffer');
    assert.ok(r.buffer.length >= 2, '缓冲区内容完整，无需用户重述');
    assert.equal(r.shouldPullBack, false, '不在跑题态时不该再拉');
});

test('④ 用户彻底不回：拉过一次后放弃，缓冲仍保留此前原话', () => {
    const r = planDriftHandling({ userTurns: TURNS, pulledBack: true, offTopic: true });
    assert.equal(r.shouldPullBack, false, '不重复拉');
    assert.ok(r.buffer.includes('产品体验不友好'), '即使放弃追问，已留底的原话仍在');
});

test('⑤ 正常流程（无跑题）不触发拉回，也不误判 resume', () => {
    const r = planDriftHandling({
        userTurns: ['导出太慢了', '点了导出等了两分钟'], pulledBack: false, offTopic: false,
    });
    assert.equal(r.shouldPullBack, false, '正常流程不该拉回');
    assert.equal(r.resume, false, '从未跑题不算「回来续用」');
    assert.equal(r.reason, 'normal');
    assert.deepEqual(r.buffer, ['导出太慢了', '点了导出等了两分钟'], '缓冲区照常收录原话');
});
