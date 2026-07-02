#!/usr/bin/env node
// ensemble-workflow.js 的 regression 測試（純 node，無框架）。
//
// 跑法：node test/ensemble-workflow.test.mjs
//
// harness 是 Workflow script（top-level await/return），無法被標準 runner 直接 import。
// 解法：讀原始碼 → 把 body 包成一個可 export 的 async 函式（注入 mock 的
// agent/parallel/phase/log/args 當參數）→ 寫成 temp module 後 import → 實跑整個
// orchestration 並斷言。鎖死 fail-closed 不變式（含 null-skip fail-open 的修正）。
// 載入的是本 repo 自己的 source（被測碼本身），信任等級等同 import 任何模組。

import { readFileSync, writeFileSync, rmSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const harnessSrc = readFileSync(join(__dirname, '..', 'workflows', 'ensemble-workflow.js'), 'utf8')
  .replace(/^export const meta/m, 'const meta') // strip ESM export so the body is legal inside a function

// Wrap the workflow-script body as an exportable async fn whose destructured params ARE the workflow
// globals the harness references (agent/parallel/pipeline/phase/log/args). Write → import (no eval).
const wrapped = `export async function runEnsemble({ agent, parallel, pipeline, phase, log, args }) {\n${harnessSrc}\n}\n`
const tmpFile = join(tmpdir(), `pai-ensemble-harness-${process.pid}.mjs`)
writeFileSync(tmpFile, wrapped)
let rawRun
try {
  ;({ runEnsemble: rawRun } = await import(pathToFileURL(tmpFile).href))
} finally {
  rmSync(tmpFile, { force: true })
}

const parallel = async (thunks) => Promise.all(thunks.map((f) => f()))
const pipeline = async () => []
const noop = () => {}

// run one scenario: agentImpl(prompt, opts) decides per-label behavior (return obj / null=skip / throw).
function runEnsemble(args, agentImpl) {
  return rawRun({ agent: agentImpl, parallel, pipeline, phase: noop, log: noop, args })
}

// agent impls keyed by label
const allPass = async () => ({ findings: [] })
const skip = (label) => async (_p, o) => (o && o.label === label ? null : { findings: [] })
const boom = (label) => async (_p, o) => { if (o && o.label === label) throw new Error('boom'); return { findings: [] } }

const tests = []
const test = (name, fn) => tests.push({ name, fn })

test('dispatch model defaults to opus at EVERY agent() site (#20)', async () => {
  const models = []
  const capture = async (_p, o) => { models.push(o && o.model); return { findings: [] } }
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: true, codexCallPath: '/bin/cc' }, capture)
  assert.ok(models.length >= 4, `expected reviewers+codex+da dispatches, got ${models.length}`)
  assert.ok(models.every((m) => m === 'opus'), `non-opus dispatch found: ${JSON.stringify(models)}`)
  assert.equal(out.stats.dispatchModel, 'opus')
})

test('agentModel override is honored at every site (#20)', async () => {
  const models = []
  const capture = async (_p, o) => { models.push(o && o.model); return { findings: [] } }
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false, agentModel: 'sonnet' }, capture)
  assert.ok(models.every((m) => m === 'sonnet'), JSON.stringify(models))
  assert.equal(out.stats.dispatchModel, 'sonnet')
})

test('explicitly invalid agentModel throws BEFORE any dispatch (#20)', async () => {
  let dispatched = 0
  const counting = async () => { dispatched++; return { findings: [] } }
  await assert.rejects(
    () => runEnsemble({ profile: 'code', file: '/x', codexEnabled: false, agentModel: 'gpt-4' }, counting),
    /invalid agentModel 'gpt-4'/
  )
  assert.equal(dispatched, 0, 'no agent may be dispatched on an invalid model')
})

test('unknown profile → HIGH harness finding, agents=0', async () => {
  const out = await runEnsemble({ profile: 'nope', file: '/x' }, allPass)
  assert.equal(out.verdict, 'FINDINGS')
  assert.equal(out.stats.agents, 0)
  assert.match(out.findings[0].title, /unknown ensemble profile/)
})

test('custom profile, no lenses → HIGH "no active lenses"', async () => {
  const out = await runEnsemble({ profile: 'custom', file: '/x' }, allPass)
  assert.equal(out.verdict, 'FINDINGS')
  assert.ok(out.findings.some((f) => /no active lenses/.test(f.title) && f.severity === 'HIGH'))
})

test('code profile all-ok → PASS, no integrity', async () => {
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false }, allPass)
  assert.equal(out.verdict, 'PASS')
  assert.equal(out.stats.integrity, 0)
})

test('REGRESSION: skip a core lens (null) → fail-closed HIGH (not silent PASS)', async () => {
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false }, skip('review:security'))
  assert.equal(out.verdict, 'FINDINGS')
  assert.ok(out.findings.some((f) => f.lens === 'security' && f.severity === 'HIGH' && /did not complete/.test(f.title)))
})

test('error (throw) a core lens → fail-closed HIGH', async () => {
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false }, boom('review:correctness'))
  assert.equal(out.verdict, 'FINDINGS')
  assert.ok(out.findings.some((f) => f.lens === 'correctness' && f.severity === 'HIGH' && /did not complete/.test(f.title)))
})

test('skip devils-advocate → fail-closed HIGH', async () => {
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false }, skip('devils-advocate'))
  assert.equal(out.verdict, 'FINDINGS')
  assert.ok(out.findings.some((f) => f.lens === 'devils-advocate' && f.severity === 'HIGH'))
})

test('skip codex (codexEnabled) → INFO process gap, verdict stays PASS', async () => {
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: true, codexCallPath: '/bin/codex-call' }, skip('codex'))
  assert.equal(out.verdict, 'PASS') // codex gap is non-blocking
  assert.ok(out.findings.some((f) => f.lens === 'codex' && f.severity === 'INFO'))
})

test('mergeDedup robust to malformed severity (no crash, finding kept, FINDINGS)', async () => {
  const weird = async (_p, o) =>
    o && o.label === 'review:architecture'
      ? { findings: [{ severity: 'BOGUS', title: 'odd', body: 'b', file: null }] }
      : { findings: [] }
  const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false }, weird)
  assert.ok(out.findings.some((f) => f.title === 'odd')) // unknown severity ranked 0, not dropped/crashed
  assert.equal(out.verdict, 'FINDINGS') // 'BOGUS' !== 'INFO'
})

let pass = 0
let fail = 0
for (const t of tests) {
  try {
    await t.fn()
    console.log(`ok - ${t.name}`)
    pass++
  } catch (e) {
    console.log(`not ok - ${t.name}\n  ${e.message}`)
    fail++
  }
}
console.log(`\n${pass}/${tests.length} passed`)
process.exit(fail === 0 ? 0 : 1)
