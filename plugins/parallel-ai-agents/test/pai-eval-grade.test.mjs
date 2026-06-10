#!/usr/bin/env node
// pai-eval-grade 的 regression 測試（純 node，無框架）。
// 跑法：node test/pai-eval-grade.test.mjs
// 用合成 findings / manifest / 修正稿（temp 檔），透過 subprocess 跑真正的 bin/pai-eval-grade。

import { execFileSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BIN = join(__dirname, '..', 'bin', 'pai-eval-grade')
const T = mkdtempSync(join(tmpdir(), 'pai-eval-grade-'))
process.on('exit', () => rmSync(T, { recursive: true, force: true }))

let fileSeq = 0
function tmpJSON(obj) {
  const p = join(T, `f${++fileSeq}.json`)
  writeFileSync(p, JSON.stringify(obj))
  return p
}
function tmpText(text) {
  const p = join(T, `f${++fileSeq}.md`)
  writeFileSync(p, text)
  return p
}

function run(args) {
  try {
    const out = execFileSync('node', [BIN, ...args], { encoding: 'utf8' })
    return { report: JSON.parse(out), status: 0 }
  } catch (e) {
    return { report: e.stdout ? JSON.parse(e.stdout || 'null') : null, status: e.status ?? 99 }
  }
}

const MANIFEST = tmpJSON({
  defects: [
    { id: 'ref', match_any: ['tanaka'] },
    { id: 'num', match_any: ['5.42', '4.42'] },
    { id: 'consist', match_all: ['120', '102'] },
  ],
  fix: [
    { id: 'ref', plantedAbsent: 'Tanaka' },
    { id: 'num', plantedAbsent: '5\\.42', correctedPresent: '4.42' },
  ],
})

const F = (title, body, lens = 'x') => ({ lens, severity: 'HIGH', title, body })

const tests = []
const test = (name, fn) => tests.push({ name, fn })

test('detect: match_any 命中 title 或 body（不分大小寫）', () => {
  const r1 = tmpJSON({ findings: [F('發現 TANAKA 引用可疑', '...')] })
  const r2 = tmpJSON({ findings: [F('數字問題', '其中 tanaka 2019 查無')] })
  const { report } = run(['detect', '--manifest', MANIFEST, '--min-hits', '2', r1, r2])
  assert.equal(report.defects.find((d) => d.id === 'ref').hits, 2)
})

test('detect: match_all 須在「同一個 finding」——拆在兩個 finding 不算', () => {
  const split = tmpJSON({ findings: [F('a', '說 120'), F('b', '說 102')] })
  const same = tmpJSON({ findings: [F('不一致', 'Abstract 120 vs Method 102')] })
  const { report } = run(['detect', '--manifest', MANIFEST, '--min-hits', '1', split, same])
  const d = report.defects.find((x) => x.id === 'consist')
  assert.deepEqual(d.runsHit, [2]) // 只有 same 那個 run 命中
})

test('detect: 容差聚合 — K=3 預設 minHits=2；2 hit pass、1 hit fail', () => {
  const hit = () => tmpJSON({ findings: [F('mean 錯', 'paper 5.42 vs truth')] })
  const miss = () => tmpJSON({ findings: [F('無關', 'nothing')] })
  const { report, status } = run(['detect', '--manifest', MANIFEST, hit(), hit(), miss()])
  assert.equal(report.minHits, 2)
  assert.equal(report.defects.find((d) => d.id === 'num').pass, true)
  assert.equal(report.defects.find((d) => d.id === 'ref').pass, false) // 0 hits
  assert.equal(status, 1) // 有 defect 未達標 → exit 1
})

test('detect: --min-hits 覆寫（1 → 單 run 命中即 pass）', () => {
  const r = tmpJSON({ findings: [F('TANAKA', ''), F('m', '4.42'), F('n', '120 vs 102')] })
  const { report, status } = run(['detect', '--manifest', MANIFEST, '--min-hits', '1', r])
  assert.equal(report.pass, true)
  assert.equal(status, 0)
})

test('detect: 裸 findings array 輸入也接受', () => {
  const r = tmpJSON([F('tanaka', ''), F('m', '5.42'), F('n', '120 與 102')])
  const { status } = run(['detect', '--manifest', MANIFEST, '--min-hits', '1', r])
  assert.equal(status, 0)
})

test('detect: integrity findings 不算命中、但列入 run 報表', () => {
  const r = tmpJSON({ findings: [F('tanaka lens did not complete', 'errored', 'tanaka')] })
  const { report } = run(['detect', '--manifest', MANIFEST, '--min-hits', '1', r])
  assert.equal(report.defects.find((d) => d.id === 'ref').hits, 0) // title 含 tanaka 但是 integrity → 排除
  assert.equal(report.runs[0].integrity, 1)
})

test('detect: caughtBy 回報命中的 lens', () => {
  const r = tmpJSON({ findings: [F('幻覺文獻', 'tanaka 查無', 'reference-verifier')] })
  const { report } = run(['detect', '--manifest', MANIFEST, '--min-hits', '1', r])
  assert.deepEqual(report.defects.find((d) => d.id === 'ref').caughtBy, ['reference-verifier'])
})

test('fix: planted 已消失 + corrected 出現 → pass', () => {
  const doc = tmpText('結果 M = 4.42（修正後），無可疑引用。')
  const { report, status } = run(['fix', '--manifest', MANIFEST, doc])
  assert.equal(report.pass, true)
  assert.equal(status, 0)
})

test('fix: planted 仍在 → fail', () => {
  const doc = tmpText('M = 5.42 還在，tanaka 也還在')
  const { report, status } = run(['fix', '--manifest', MANIFEST, doc])
  assert.equal(status, 1)
  assert.equal(report.checks.find((c) => c.id === 'ref').plantedGone, false)
  assert.equal(report.checks.find((c) => c.id === 'num').plantedGone, false)
})

test('fix: planted 消失但 corrected 沒出現 → 該 check fail', () => {
  const doc = tmpText('數字整段被刪掉了。')
  const { report, status } = run(['fix', '--manifest', MANIFEST, doc])
  assert.equal(status, 1)
  const num = report.checks.find((c) => c.id === 'num')
  assert.equal(num.plantedGone, true)
  assert.equal(num.correctedPresent, false)
})

test('用法錯誤：未知 mode / 缺 manifest / 非法 JSON → exit 2', () => {
  assert.equal(run(['bogus']).status, 2)
  assert.equal(run(['detect', tmpJSON({})]).status, 2) // 缺 --manifest
  const bad = join(T, 'bad.json')
  writeFileSync(bad, '{not json')
  assert.equal(run(['detect', '--manifest', bad, tmpJSON([])]).status, 2)
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
