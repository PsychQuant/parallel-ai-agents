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

test('agentModel null / empty string ≡ absent → default opus, no throw (#20)', async () => {
  for (const v of [null, '']) {
    const models = []
    const capture = async (_p, o) => { models.push(o && o.model); return { findings: [] } }
    const out = await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false, agentModel: v }, capture)
    assert.ok(models.every((m) => m === 'opus'), `agentModel=${JSON.stringify(v)} → ${JSON.stringify(models)}`)
    assert.equal(out.stats.dispatchModel, 'opus')
  }
})

test('early-return guards carry dispatchModel in stats (#20 verify fix)', async () => {
  const out = await runEnsemble({ profile: 'nope', file: '/x', agentModel: 'sonnet' }, allPass)
  assert.equal(out.stats.dispatchModel, 'sonnet')
})

test('explicitly invalid agentModel throws BEFORE any dispatch (#20)', async () => {
  let dispatched = 0
  const counting = async () => { dispatched++; return { findings: [] } }
  await assert.rejects(
    () => runEnsemble({ profile: 'code', file: '/x', codexEnabled: false, agentModel: 'gpt-4' }, counting),
    /invalid agentModel "gpt-4"/
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

// ── #29 lens-layer override semantics ───────────────────────────────────────
// 三層 lens 疊加（built-in → lens pack → user）在 harness 內折疊，所以「撞名時誰勝出」
// 是 harness 的不變式，不是 skill 側的膠水。lens pack 的 CSV 用 override 欄宣告取代意圖。

// 捕捉每個 reviewer 的 prompt —— 這是唯一能分辨「哪一份 focus 真的出貨」的觀測點。
const captureLenses = () => {
  const seen = []
  const impl = async (prompt, o) => {
    if (o && typeof o.label === 'string' && o.label.startsWith('review:')) {
      seen.push({ key: o.label.slice('review:'.length), prompt: String(prompt) })
    }
    return { findings: [] }
  }
  return { seen, impl }
}

test('#29 向後相容鎖：未標記的撞名仍是 first-wins（built-in 勝）', async () => {
  const { seen, impl } = captureLenses()
  await runEnsemble(
    { profile: 'code', file: '/x', codexEnabled: false,
      customLenses: [{ key: 'security', focus: 'CUSTOM_SECURITY_FOCUS' }] },
    impl
  )
  const sec = seen.filter((s) => s.key === 'security')
  assert.equal(sec.length, 1, 'security 被複製成兩個 reviewer')
  assert.ok(!sec[0].prompt.includes('CUSTOM_SECURITY_FOCUS'),
    '未標記的 custom lens 蓋掉了 built-in —— first-wins 被改壞了')
})

test('#29 override:true 取代同 key 的 built-in lens', async () => {
  const { seen, impl } = captureLenses()
  await runEnsemble(
    { profile: 'code', file: '/x', codexEnabled: false,
      customLenses: [{ key: 'security', focus: 'CUSTOM_SECURITY_FOCUS', override: true }] },
    impl
  )
  const sec = seen.filter((s) => s.key === 'security')
  assert.equal(sec.length, 1, 'override 必須是取代，不是追加')
  assert.ok(sec[0].prompt.includes('CUSTOM_SECURITY_FOCUS'),
    'override:true 沒生效 —— 出貨的仍是 built-in 的 focus')
})

test('#29 override 是原位取代（lens 順序不變）', async () => {
  const base = captureLenses()
  await runEnsemble({ profile: 'code', file: '/x', codexEnabled: false }, base.impl)
  const baseOrder = base.seen.map((s) => s.key)
  assert.ok(baseOrder.length >= 2, 'code profile 應有多個 lens')

  const over = captureLenses()
  await runEnsemble(
    { profile: 'code', file: '/x', codexEnabled: false,
      customLenses: [{ key: baseOrder[0], focus: 'OVERRIDDEN', override: true }] },
    over.impl
  )
  assert.deepEqual(over.seen.map((s) => s.key), baseOrder,
    'override 把 lens 移位了 —— devil\'s-advocate 依序讀 reviewer 完稿，位置是契約的一部分')
})

test('#29 stats.lensProvenance 記錄 added / overridden / ignored', async () => {
  const out = await runEnsemble(
    { profile: 'code', file: '/x', codexEnabled: false,
      customLenses: [
        { key: 'security', focus: 'REPLACED', override: true },
        { key: 'correctness', focus: 'SHOULD_BE_IGNORED' },
        { key: 'perf', focus: '全新的 lens' },
      ] },
    allPass
  )
  const prov = out.stats.lensProvenance
  assert.ok(Array.isArray(prov), 'stats.lensProvenance 缺席')
  // 每個「進來的」lens 一筆（含 built-in），後來者覆寫同 key 的紀錄 → 取最後一筆為最終處置
  const byKey = Object.fromEntries(prov.map((p) => [p.key, p]))
  assert.equal(byKey.security.action, 'overridden', JSON.stringify(prov))
  assert.equal(byKey.security.overrodeFrom, 'builtin', JSON.stringify(prov))
  assert.equal(byKey.correctness.action, 'ignored', JSON.stringify(prov))
  assert.equal(byKey.perf.action, 'added', JSON.stringify(prov))
})

// ── #37 codex leg：artifact 不得經過 wrapper agent 的 context ────────────────
// #37 的成因：codexPrompt 要 agent 先「讀」 artifact、再把它「寫」回暫存檔，
// 同一份 bytes 兩次過 context（實測 ~976k token）。tool call 之間的模型延遲
// 因此超過 runtime 的 180s no-progress 門檻，leg 被判 stall、從零重試五次。
// 另一半：codex-call 是最長 600s 的阻塞呼叫，600 > 180 ⇒ 結構上保證觸發。

const captureCodex = () => {
  const seen = []
  const impl = async (prompt, o) => {
    if (o && o.label === 'codex') seen.push(String(prompt))
    return { findings: [] }
  }
  return { seen, impl }
}

const codexPromptFor = async (args) => {
  const { seen, impl } = captureCodex()
  await runEnsemble({ codexEnabled: true, codexCallPath: '/bin/codex-call', ...args }, impl)
  assert.equal(seen.length, 1, 'codex leg 沒有被派發')
  return seen[0]
}

test('#37 T1 codex leg 不再被指示把 artifact 讀進自己的 context', async () => {
  const p = await codexPromptFor({ profile: 'code', diffFile: '/tmp/d.diff' })
  for (const phrase of [
    'to get the content under review',
    'read it fully with your file-read tool',
    'read it from this file with your file-read tool',
  ]) {
    assert.ok(!p.includes(phrase),
      `codex prompt 仍要求讀 artifact 進 context（命中 "${phrase}"）—— 這正是 #37 的成因`)
  }
})

test('#37 T2 codex leg 用只傳 path 的串接組 prompt，且 instructions 在 artifact 之前', async () => {
  const p = await codexPromptFor({ profile: 'code', diffFile: '/tmp/d.diff' })
  assert.match(p, /cat\s+"\$INSTR_FILE"\s+"\$ARTIFACT_FILE"\s*>\s*"\$PROMPT_FILE"/,
    'path-only 串接缺席或順序錯（instructions 必須在 artifact 之前）')
  assert.ok(p.includes('--prompt-file "$PROMPT_FILE"'), 'wrapper 沒有吃組好的 prompt 檔')
})

test('#37 T3 byte-interpolation 的注入禁令仍在（安全回歸護欄）', async () => {
  const p = await codexPromptFor({ profile: 'code', diffFile: '/tmp/d.diff' })
  assert.ok(p.includes('echo/printf/heredoc'),
    '禁令消失了 —— 放寬措辭時把硬化規則一起拆了')
  assert.ok(p.includes('command-injection'),
    '禁令沒說明為什麼，未來會被當成可有可無的規則刪掉')
})

test('#37 T4 Claude lens 仍被要求讀 artifact（過度編輯的回歸護欄）', async () => {
  const { seen, impl } = captureLenses()
  await runEnsemble({ profile: 'code', diffFile: '/tmp/d.diff', codexEnabled: false }, impl)
  assert.ok(seen.length > 0, 'reviewer lens 沒有被派發')
  assert.ok(seen.every((s) => s.prompt.includes('file-read tool')),
    'Claude lens 的讀取指示被誤刪 —— 它們必須讀 artifact 才能審（那一半見 #44）')
})

test('#37 T5 無 artifact 時不組空的 cat，直接用 instructions 檔', async () => {
  const p = await codexPromptFor({ profile: 'code' })
  assert.ok(!p.includes('cat "$INSTR_FILE"'),
    '沒有 artifact 卻仍組 cat —— 會串接一個不存在的路徑')
  assert.ok(p.includes('--prompt-file "$INSTR_FILE"'),
    '無 artifact 時應直接把 instructions 當 prompt 檔')
})

test('#37 T6 codex-call 以背景執行 + 輪詢，不阻塞單一命令', async () => {
  const p = await codexPromptFor({ profile: 'code', diffFile: '/tmp/d.diff' })
  assert.ok(/BACKGROUND/i.test(p),
    '沒有背景執行指示 —— 阻塞呼叫最長 600s > 180s 門檻，結構上必被判 stall')
  assert.ok(p.includes('kill -0'),
    '沒有輪詢存活的方式，agent 無從得知何時完成')
  assert.ok(/separate tool call/i.test(p),
    '沒有交代輪詢必須是分開的 tool call（那才是 progress 事件）')
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
