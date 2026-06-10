#!/usr/bin/env node
// pai-iterate-decide 的 regression 測試（純 node，無框架）。
// 跑法：node test/pai-iterate-decide.test.mjs
// 透過 subprocess 跑真正的 bin/pai-iterate-decide（JSON stdin → JSON stdout），測 CLI 契約。

import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BIN = join(__dirname, '..', 'bin', 'pai-iterate-decide')

// 跑 decider，回 {action, status}；非 0 退出時 action=null
function run(state) {
  try {
    const out = execFileSync('node', [BIN], { input: JSON.stringify(state), encoding: 'utf8' })
    return { action: JSON.parse(out), status: 0 }
  } catch (e) {
    return { action: null, status: e.status ?? 1 }
  }
}

const base = { round: 1, maxRounds: 12, verdict: 'NEEDS_ITER_1', currentFocus: 'method-section', focusHistory: [] }

const tests = []
const test = (name, fn) => tests.push({ name, fn })

test('PERMANENT_CONVERGENCE（預設 convergeOn）→ halt converged、不套 fix', () => {
  const { action } = run({ ...base, round: 3, verdict: 'PERMANENT_CONVERGENCE' })
  assert.equal(action.halt, true)
  assert.equal(action.reason, 'converged')
  assert.equal(action.applyFixes, false)
})

test('CONVERGED（預設 convergeOn=PERMANENT）→ 不 halt、繼續迭代', () => {
  const { action } = run({ ...base, round: 3, verdict: 'CONVERGED' })
  assert.equal(action.halt, false)
  assert.equal(action.applyFixes, true)
})

test('自訂 --converge-on CONVERGED → CONVERGED 即 halt', () => {
  const { action } = run({ ...base, round: 3, verdict: 'CONVERGED', convergeOn: 'CONVERGED' })
  assert.equal(action.halt, true)
  assert.equal(action.reason, 'converged')
})

test('NEEDS_ITER 中段 → continue、applyFixes、前進一輪', () => {
  const { action } = run({ ...base, round: 1, verdict: 'NEEDS_ITER_1' })
  assert.equal(action.halt, false)
  assert.equal(action.applyFixes, true)
  assert.equal(action.nextRound, 2)
})

test('最後一輪 NEEDS_ITER → 本輪仍套 fix，但 halt max-rounds', () => {
  const { action } = run({ ...base, round: 12, maxRounds: 12, verdict: 'NEEDS_ITER_12' })
  assert.equal(action.applyFixes, true) // break 只在 converge，max-rounds 輪 fix 照套
  assert.equal(action.halt, true)
  assert.equal(action.reason, 'max-rounds')
})

test('maxRounds clamp 下界：0 → 1（round 1 即達上限 → halt）', () => {
  const { action } = run({ ...base, round: 1, maxRounds: 0, verdict: 'NEEDS_ITER_1' })
  assert.equal(action.halt, true)
  assert.equal(action.reason, 'max-rounds')
})

test('maxRounds clamp 上界：1000 → 30（round 30 → nextRound 31 > 30 → halt）', () => {
  const { action } = run({ ...base, round: 30, maxRounds: 1000, verdict: 'NEEDS_ITER_30' })
  assert.equal(action.halt, true)
  assert.equal(action.reason, 'max-rounds')
})

test('mode 奇偶：round 1 → nextMode hybrid(2)；round 2 → independent(3)', () => {
  assert.equal(run({ ...base, round: 1 }).action.nextMode, 'hybrid')
  assert.equal(run({ ...base, round: 2 }).action.nextMode, 'independent')
})

test('focus 輪替：末 3 筆同 focus 皆 CONVERGED → rotated、focus 進下一個', () => {
  const { action } = run({
    ...base, round: 4, verdict: 'CONVERGED', currentFocus: 'method-section',
    focusHistory: [{ focus: 'method-section', verdict: 'CONVERGED' }, { focus: 'method-section', verdict: 'CONVERGED' }],
  })
  assert.equal(action.rotated, true)
  assert.equal(action.nextFocus, 'proofs') // method-section 的下一個
})

test('focus 不輪替：只有 2 筆（含本輪）→ 不足 3', () => {
  const { action } = run({
    ...base, round: 2, verdict: 'CONVERGED', currentFocus: 'method-section',
    focusHistory: [{ focus: 'method-section', verdict: 'CONVERGED' }],
  })
  assert.equal(action.rotated, false)
  assert.equal(action.nextFocus, 'method-section')
})

test('focus 不輪替：3 筆 CONVERGED 但 focus 不一致', () => {
  const { action } = run({
    ...base, round: 4, verdict: 'CONVERGED', currentFocus: 'proofs',
    focusHistory: [{ focus: 'method-section', verdict: 'CONVERGED' }, { focus: 'proofs', verdict: 'CONVERGED' }],
  })
  assert.equal(action.rotated, false)
})

test('focus 不輪替：末 3 筆 focus 同但 verdict 含 NEEDS_ITER', () => {
  const { action } = run({
    ...base, round: 4, verdict: 'CONVERGED', currentFocus: 'proofs',
    focusHistory: [{ focus: 'proofs', verdict: 'NEEDS_ITER_2' }, { focus: 'proofs', verdict: 'CONVERGED' }],
  })
  assert.equal(action.rotated, false)
})

test('pool 繞回：boundary-cases 輪替 → 回到 method-section', () => {
  const { action } = run({
    ...base, round: 4, verdict: 'CONVERGED', currentFocus: 'boundary-cases',
    focusHistory: [{ focus: 'boundary-cases', verdict: 'CONVERGED' }, { focus: 'boundary-cases', verdict: 'CONVERGED' }],
  })
  assert.equal(action.rotated, true)
  assert.equal(action.nextFocus, 'method-section')
})

test('focus 不在 pool（自訂）+ 輪替 → 落到 pool[0]', () => {
  const { action } = run({
    ...base, round: 4, verdict: 'CONVERGED', currentFocus: 'custom-area',
    focusHistory: [{ focus: 'custom-area', verdict: 'CONVERGED' }, { focus: 'custom-area', verdict: 'CONVERGED' }],
  })
  assert.equal(action.rotated, true)
  assert.equal(action.nextFocus, 'method-section')
})

test('自訂 focusPool 被採用', () => {
  const { action } = run({
    ...base, round: 4, verdict: 'CONVERGED', currentFocus: 'a', focusPool: ['a', 'b'],
    focusHistory: [{ focus: 'a', verdict: 'CONVERGED' }, { focus: 'a', verdict: 'CONVERGED' }],
  })
  assert.equal(action.nextFocus, 'b')
})

test('round 非法（0）→ exit 2', () => {
  assert.equal(run({ ...base, round: 0 }).status, 2)
})

test('非法 JSON → exit 2', () => {
  let status
  try {
    execFileSync('node', [BIN], { input: '{not json', encoding: 'utf8' })
    status = 0
  } catch (e) {
    status = e.status
  }
  assert.equal(status, 2)
})

let pass = 0
let fail = 0
for (const t of tests) {
  try {
    t.fn()
    console.log(`ok - ${t.name}`)
    pass++
  } catch (e) {
    console.log(`not ok - ${t.name}\n  ${e.message}`)
    fail++
  }
}
console.log(`\n${pass}/${tests.length} passed`)
process.exit(fail === 0 ? 0 : 1)
