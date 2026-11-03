#!/usr/bin/env node
// bin/pai-artifact-fingerprint 的測試（純 node，無框架）：在拋棄式的目錄與 git repo 上真的執行它。
//
// 跑法：node test/pai-artifact-fingerprint.test.mjs

import { appendFileSync, chmodSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync, rmSync, statSync, symlinkSync, unlinkSync, utimesSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')
const TOOL = join(ROOT, 'bin', 'pai-artifact-fingerprint')
const HEX = /^[0-9a-f]{64}\n$/
const isRoot = process.getuid && process.getuid() === 0

const tests = []
const test = (name, fn) => tests.push({ name, fn })

const scratch = () => mkdtempSync(join(tmpdir(), 'pai-fp-'))
const run = (args, opts = {}) => {
  const r = spawnSync(TOOL, args, { encoding: 'utf8', timeout: 60000, ...opts })
  if (r.error) throw r.error
  return r
}
const fp = (...args) => {
  const r = run(args)
  assert.equal(r.status, 0, `exit ${r.status}: ${r.stderr}`)
  assert.match(r.stdout, HEX)
  assert.equal(r.stderr, '')
  return r.stdout.trim()
}
const refuses = (args, opts = {}) => {
  const r = run(args, opts)
  assert.notEqual(r.status, 0, `應該失敗卻 exit 0：${JSON.stringify(args)} → ${r.stdout}`)
  assert.equal(r.stdout, '', `失敗時 stdout 要是空的：${JSON.stringify(args)} → ${r.stdout}`)
  assert.notEqual(r.stderr, '', `失敗時要說原因：${JSON.stringify(args)}`)
  return r
}
const git = (cwd, ...args) => {
  const r = spawnSync('git', args, { cwd, encoding: 'utf8' })
  assert.equal(r.status, 0, `git ${args.join(' ')}: ${r.stderr}`)
  return r.stdout
}
const repo = () => {
  const d = scratch()
  git(d, 'init', '-q')
  git(d, 'config', 'user.email', 'a@example.invalid')
  git(d, 'config', 'user.name', 'a')
  writeFileSync(join(d, 'a.txt'), 'a\n')
  mkdirSync(join(d, 'config'))
  chmodSync(join(d, 'config'), 0o755)
  writeFileSync(join(d, 'config', 'app.conf'), 'k=v\n')
  writeFileSync(join(d, '.gitignore'), 'ignored.log\nignored-dir/\n')
  writeFileSync(join(d, 'ignored.log'), 'x\n')
  git(d, 'add', 'a.txt', 'config/app.conf', '.gitignore')
  git(d, 'commit', '-qm', 'init')
  return d
}
const plainDir = () => {
  const d = scratch()
  writeFileSync(join(d, 'a.txt'), 'a\n')
  mkdirSync(join(d, 'sub'))
  chmodSync(join(d, 'sub'), 0o755)
  writeFileSync(join(d, 'sub', 'b.txt'), 'b\n')
  return d
}
// 每個變動之後指紋都要變，而且與之前任何一個都不同。
const changesEachStep = (d, steps) => {
  const seen = new Map([[fp(d), 'start']])
  for (const [label, act] of steps) {
    act()
    const h = fp(d)
    assert.ok(!seen.has(h), `「${label}」之後的指紋與「${seen.get(h)}」相同`)
    seen.set(h, label)
  }
}

test('git 目錄：內容與檔名的每一種變動都讓指紋改變', () => {
  const d = repo()
  changesEachStep(d, [
    ['暫存的修改', () => { writeFileSync(join(d, 'a.txt'), 'a2\n'); git(d, 'add', 'a.txt') }],
    ['暫存之後再改再暫存', () => { writeFileSync(join(d, 'a.txt'), 'a3\n'); git(d, 'add', 'a.txt') }],
    ['新增未追蹤的檔', () => writeFileSync(join(d, 'u.txt'), 'u\n')],
    ['改未追蹤檔的內容', () => writeFileSync(join(d, 'u.txt'), 'u2\n')],
    ['git mv', () => git(d, 'mv', 'a.txt', 'b.txt')],
    ['一般的 mv', () => renameSync(join(d, 'b.txt'), join(d, 'c.txt'))],
    ['刪掉追蹤中的檔（沒有暫存）', () => unlinkSync(join(d, 'config', 'app.conf'))],
  ])
  rmSync(d, { recursive: true, force: true })
})

test('git 目錄：追蹤中的檔被刪只記成不存在，不會失敗；暫存刪除之後指紋也變', () => {
  const d = repo()
  unlinkSync(join(d, 'a.txt'))
  const gone = fp(d)
  git(d, 'rm', '-q', '--cached', 'a.txt')
  assert.notEqual(fp(d), gone)
  rmSync(d, { recursive: true, force: true })
})

test('git 目錄與一般目錄：檔案權限、上層目錄權限、symlink 改指都讓指紋改變', () => {
  for (const make of [repo, plainDir]) {
    const d = make()
    const parent = make === repo ? 'config' : 'sub'
    symlinkSync('a.txt', join(d, 'lnk'))
    changesEachStep(d, [
      ['檔案權限', () => chmodSync(join(d, 'a.txt'), 0o755)],
      ['上層目錄權限（0755 → 0777）', () => chmodSync(join(d, parent), 0o777)],
      ['symlink 改指', () => { unlinkSync(join(d, 'lnk')); symlinkSync(join(parent, 'nowhere'), join(d, 'lnk')) }],
    ])
    rmSync(d, { recursive: true, force: true })
  }
})

test('目錄本身的權限也算（與讀檔器相同）', () => {
  const d = plainDir()
  chmodSync(d, 0o755)
  const before = fp(d)
  chmodSync(d, 0o775)
  assert.notEqual(fp(d), before)
  rmSync(d, { recursive: true, force: true })
})

test('只改修改時間不變；只改被忽略的檔不變；repo 裡其他目錄的改動不影響子目錄的指紋', () => {
  const d = repo()
  const whole = fp(d)
  const sub = fp(join(d, 'config'))
  const old = new Date(Date.now() - 86400000)
  utimesSync(join(d, 'a.txt'), old, old)
  utimesSync(join(d, 'config'), old, old)
  assert.equal(fp(d), whole, '只改修改時間，指紋變了')
  writeFileSync(join(d, 'ignored.log'), 'changed\n')
  assert.equal(fp(d), whole, '只改被忽略的檔，指紋變了')
  writeFileSync(join(d, 'a.txt'), 'outside the subdirectory\n')
  assert.equal(fp(join(d, 'config')), sub, '子目錄外的改動影響了子目錄的指紋')
  assert.notEqual(fp(d), whole)
  rmSync(d, { recursive: true, force: true })
})

test('--exclude：拿掉那個路徑與底下的一切，路徑還不存在也一樣（git 與一般目錄）', () => {
  for (const make of [repo, plainDir]) {
    const d = make()
    const ck = join(d, 'ck')
    const before = fp('--exclude', ck, d)
    mkdirSync(join(ck, 'run-1'), { recursive: true })
    writeFileSync(join(ck, 'args.json'), '{}\n')
    writeFileSync(join(ck, 'run-1', 'x.partial.jsonl'), 'y\n')
    assert.equal(fp('--exclude', ck, d), before, 'checkpoint 目錄裡的檔改變了指紋')
    assert.notEqual(fp(d), before, '沒有 --exclude 時它們應該算進去（這個測試的前提）')
    writeFileSync(join(d, 'a.txt'), 'other\n')
    assert.notEqual(fp('--exclude', ck, d), before, '--exclude 把其他內容也拿掉了')
    rmSync(d, { recursive: true, force: true })
  }
})

test('--exclude 可以放在 INPUT 之後；相對路徑以工作目錄解析；拿掉全部就是失敗', () => {
  const d = plainDir()
  const ck = join(d, 'sub')
  assert.equal(fp(d, '--exclude', ck), fp('--exclude', ck, d))
  const r = run(['--exclude', 'sub', d], { cwd: d })
  assert.equal(r.stdout.trim(), fp('--exclude', ck, d))
  refuses(['--exclude', d, d])
  const f = join(d, 'a.txt')
  refuses(['--exclude', f, f])
  rmSync(d, { recursive: true, force: true })
})

test('失敗一律是 stdout 空、exit 非零、stderr 說原因；沒有「什麼都沒算到」的常數', () => {
  const d = scratch()
  const emptyDir = join(d, 'empty'); mkdirSync(emptyDir)
  const emptyTree = join(d, 'tree'); mkdirSync(join(emptyTree, 'a', 'b'), { recursive: true })
  const emptyRepo = join(d, 'repo'); mkdirSync(emptyRepo); git(emptyRepo, 'init', '-q')
  const good = join(d, 'good'); writeFileSync(good, 'g\n')
  const fifo = join(d, 'fifo'); assert.equal(spawnSync('mkfifo', [fifo]).status, 0)
  const cases = [
    [],
    [''],
    ['--exclude'],
    ['--exclude', '', good],
    ['--exclude', good],
    [join(d, 'no-such-path')],
    ['--exlude', good, good], // 打錯的旗標是一個不存在的路徑，不是被忽略
    [emptyDir],
    [emptyTree],
    [emptyRepo],
    [fifo],
    [good, join(d, 'no-such-path')], // 多個輸入裡有一個壞的，整個失敗
    [join(d, 'no-such-path'), good],
    [good, emptyDir],
    [good, ''],
  ]
  for (const args of cases) refuses(args)
  rmSync(d, { recursive: true, force: true })
})

test('0 byte 的檔照常雜湊：單獨給或在多個輸入裡都算，權限與內容一變指紋就變', () => {
  const d = scratch()
  const zero = join(d, 'zero'); writeFileSync(zero, ''); chmodSync(zero, 0o644)
  const good = join(d, 'good'); writeFileSync(good, 'g\n')
  const alone = fp(zero)
  assert.notEqual(fp(good, zero), fp(good), '多輸入裡的空檔沒有算進去')
  assert.notEqual(fp(good, zero), fp(zero, good))
  chmodSync(zero, 0o600)
  assert.notEqual(fp(zero), alone, '空檔的權限沒有算進去')
  chmodSync(zero, 0o644)
  writeFileSync(zero, 'x')
  assert.notEqual(fp(zero), alone)
  rmSync(d, { recursive: true, force: true })
})

test('直接給的檔：權限位元算進去，路徑不算（重建到別的路徑、權限相同的 diff 指紋相同）', () => {
  const d = scratch()
  const f = join(d, 'f'); writeFileSync(f, 'x\n'); chmodSync(f, 0o644)
  const g = join(d, 'g'); writeFileSync(g, 'y\n'); chmodSync(g, 0o644)
  const h = fp(f)
  const both = fp(f, g)
  chmodSync(f, 0o755)
  assert.notEqual(fp(f), h, 'chmod 644 → 755，指紋沒變')
  chmodSync(f, 0o644)
  assert.equal(fp(f), h)
  chmodSync(g, 0o600)
  assert.notEqual(fp(f, g), both, '多輸入裡第二個檔的權限沒有算進去')
  const rebuilt = join(d, 'rebuilt-elsewhere'); writeFileSync(rebuilt, 'x\n'); chmodSync(rebuilt, 0o644)
  assert.equal(fp(rebuilt), h, '換了路徑，內容與權限相同，指紋卻變了')
  rmSync(d, { recursive: true, force: true })
})

test('走訪模式：每個沒被排除的目錄都算，含空目錄；git 列出的範圍不含空目錄', () => {
  const d = plainDir()
  changesEachStep(d, [
    ['新增空目錄', () => { mkdirSync(join(d, 'empty')); chmodSync(join(d, 'empty'), 0o755) }],
    ['空目錄的權限', () => chmodSync(join(d, 'empty'), 0o777)],
    ['空目錄底下再一層', () => { mkdirSync(join(d, 'empty', 'inner')); chmodSync(join(d, 'empty', 'inner'), 0o755) }],
    ['內層空目錄的權限', () => chmodSync(join(d, 'empty', 'inner'), 0o700)],
  ])
  const h = fp(d)
  rmSync(join(d, 'empty'), { recursive: true, force: true })
  assert.notEqual(fp(d), h, '刪掉空目錄，指紋沒變')
  const noEmpty = fp(d)
  const ck = join(d, 'ck')
  const kept = fp('--exclude', ck, d)
  mkdirSync(ck)
  assert.equal(fp('--exclude', ck, d), kept, '被排除的空目錄算進去了')
  rmSync(ck, { recursive: true, force: true })
  mkdirSync(join(d, 'node_modules'))
  assert.equal(fp(d), noEmpty, '略過名單裡的空目錄算進去了')
  rmSync(d, { recursive: true, force: true })
  const r = repo()
  const inGit = fp(r)
  mkdirSync(join(r, 'empty-in-git'))
  assert.equal(fp(r), inGit, 'git 不列空目錄：這是協定寫的限制')
  rmSync(r, { recursive: true, force: true })
})

test('讀不了的檔（單獨給或在目錄裡）是失敗，不是少算一個', () => {
  if (isRoot) return
  const d = plainDir()
  const f = join(d, 'sub', 'b.txt')
  chmodSync(f, 0o000)
  refuses([f])
  refuses([d])
  const sub = join(d, 'sub')
  chmodSync(f, 0o644)
  chmodSync(sub, 0o000)
  refuses([d])
  chmodSync(sub, 0o755)
  rmSync(d, { recursive: true, force: true })
})

test('多個輸入合成一個雜湊：順序算數；輸入自己的路徑不算（重建到新暫存檔的 diff 內容相同就相同）', () => {
  const d = scratch()
  const a = join(d, 'a'); writeFileSync(a, 'A\n')
  const b = join(d, 'b'); writeFileSync(b, 'B\n')
  const copy = join(d, 'copy-of-a'); writeFileSync(copy, 'A\n')
  assert.equal(fp(a), fp(copy))
  assert.notEqual(fp(a), fp(b))
  assert.notEqual(fp(a, b), fp(b, a))
  assert.notEqual(fp(a, b), fp(a))
  assert.equal(fp(copy, b), fp(a, b))
  const dir = plainDir()
  assert.notEqual(fp(a, dir), fp(dir, a))
  writeFileSync(join(dir, 'a.txt'), 'changed\n')
  const after = fp(a, dir)
  writeFileSync(join(dir, 'a.txt'), 'a\n')
  assert.notEqual(after, fp(a, dir), '多輸入裡目錄的內容改動沒有反映')
  rmSync(d, { recursive: true, force: true })
  rmSync(dir, { recursive: true, force: true })
})

test('不受工作目錄、呼叫的 shell、絕對或相對寫法影響；python 版本不影響', () => {
  const d = repo()
  const h = fp(d)
  const other = scratch()
  const script = `"$T" "$D"`
  const env = { ...process.env, T: TOOL, D: d }
  for (const shell of ['bash', 'zsh', 'sh']) {
    const r = spawnSync(shell, ['-c', script], { env, cwd: other, encoding: 'utf8' })
    if (r.error && r.error.code === 'ENOENT') continue
    assert.equal(r.stdout.trim(), h, `${shell} 得到不同的指紋`)
  }
  assert.equal(run(['.'], { cwd: d }).stdout.trim(), h)
  assert.equal(run(['../' + d.split('/').pop()], { cwd: d }).stdout.trim(), h)
  const dir = plainDir()
  const fileHash = fp(join(dir, 'a.txt'))
  const dirHash = fp(dir)
  let tried = 0
  for (const v of ['3.8', '3.9', '3.10', '3.11', '3.12', '3.13', '3.14', '3.15']) {
    const py = `python${v}`
    if (spawnSync(py, ['--version']).status !== 0) continue
    tried++
    for (const [input, want] of [[d, h], [dir, dirHash], [join(dir, 'a.txt'), fileHash]]) {
      const r = spawnSync(py, ['-I', TOOL, input], { encoding: 'utf8' })
      assert.equal(r.stdout.trim(), want, `${py} on ${input}: ${r.stderr}`)
    }
  }
  console.log(`  (${tried} 個帶版本號的 python 得到相同的指紋)`)
  for (const x of [d, other, dir]) rmSync(x, { recursive: true, force: true })
})

test('整個被忽略的目錄：列表是空的，退回走訪，內容改了指紋就變', () => {
  const d = repo()
  const ign = join(d, 'ignored-dir')
  mkdirSync(ign)
  writeFileSync(join(ign, 'build.txt'), 'v1\n')
  assert.equal(git(ign, 'ls-files', '--cached', '--others', '--exclude-standard'), '', '前提：git 列不出任何東西')
  const h = fp(ign)
  const old = new Date(Date.now() - 86400000)
  utimesSync(join(ign, 'build.txt'), old, old)
  assert.equal(fp(ign), h, '退回走訪時只改修改時間，指紋變了')
  writeFileSync(join(ign, 'build.txt'), 'v2\n')
  assert.notEqual(fp(ign), h, '被忽略的目錄內容改了，指紋沒變（這是空常數的形狀）')
  rmSync(d, { recursive: true, force: true })
})

test('空 repo 裡的檔：還沒 commit 的未追蹤檔照算；全部被忽略時也退回走訪', () => {
  const d = scratch()
  git(d, 'init', '-q')
  writeFileSync(join(d, 'f.txt'), 'x\n')
  const h = fp(d)
  writeFileSync(join(d, 'f.txt'), 'y\n')
  assert.notEqual(fp(d), h)
  writeFileSync(join(d, '.gitignore'), '*\n')
  const ignoredAll = fp(d)
  writeFileSync(join(d, 'f.txt'), 'z\n')
  assert.notEqual(fp(d), ignoredAll)
  rmSync(d, { recursive: true, force: true })
})

test('略過名單與 engine 讀檔器相同，而且真的略過', () => {
  const list = (src) => {
    const m = src.match(/SKIP = \{([^}]*)\}/)
    assert.ok(m, '找不到 SKIP')
    return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort()
  }
  const engine = list(readFileSync(join(ROOT, 'workflows', 'ensemble-workflow.js'), 'utf8'))
  const tool = list(readFileSync(TOOL, 'utf8'))
  assert.deepEqual(tool, engine)
  assert.ok(engine.length >= 2)
  const d = plainDir()
  const h = fp(d)
  for (const name of engine) {
    for (const parent of ['', 'sub']) {
      const x = join(d, parent, name)
      mkdirSync(x)
      writeFileSync(join(x, 'f'), 'skipped\n')
      assert.equal(fp(d), h, `${join(parent, name)} 沒有被略過`)
    }
  }
  rmSync(d, { recursive: true, force: true })
})

test('不可信的目錄：core.fsmonitor 不會被執行（同一個 repo 直接跑 git 會被執行，證明設置是真的）', () => {
  const d = repo()
  const marker = join(d, '..', `marker-${process.pid}-fsmonitor`)
  const hook = join(d, 'hook.sh')
  writeFileSync(hook, `#!/bin/sh\ntouch '${marker}'\n`)
  chmodSync(hook, 0o755)
  git(d, 'config', 'core.fsmonitor', hook)
  fp(d)
  assert.ok(!existsSync(marker), 'pai-artifact-fingerprint 執行了 repo 設定的 core.fsmonitor')
  spawnSync('git', ['ls-files'], { cwd: d })
  assert.ok(existsSync(marker), '前提不成立：直接跑 git ls-files 沒有觸發 hook')
  rmSync(marker, { force: true })
  rmSync(d, { recursive: true, force: true })
})

test('不可信的目錄：diff 與 filter 類的設定也不會被執行', () => {
  const d = repo()
  const marker = join(d, '..', `marker-${process.pid}-exec`)
  const hook = join(d, 'hook.sh')
  writeFileSync(hook, `#!/bin/sh\ntouch '${marker}'\n`)
  chmodSync(hook, 0o755)
  writeFileSync(join(d, '.gitattributes'), '* filter=x diff=d\n')
  for (const [k, v] of [['filter.x.clean', hook], ['filter.x.smudge', hook], ['diff.external', hook], ['diff.d.command', hook], ['diff.d.textconv', hook]]) git(d, 'config', k, v)
  writeFileSync(join(d, 'a.txt'), 'dirty\n')
  fp(d)
  assert.ok(!existsSync(marker), 'pai-artifact-fingerprint 執行了 repo 設定的程式')
  rmSync(marker, { force: true })
  rmSync(d, { recursive: true, force: true })
})

test('不可信的目錄：工作目錄與被審目錄裡的 hashlib.py 不會被載入；環境裡的 GIT_* 不影響範圍', () => {
  const d = repo()
  const marker = join(d, '..', `marker-${process.pid}-py`)
  writeFileSync(join(d, 'hashlib.py'), `open(${JSON.stringify(marker)}, 'w').close()\n`)
  const h = fp(d)
  assert.equal(run([d], { cwd: d }).stdout.trim(), h)
  assert.equal(run([d], { cwd: d, env: { ...process.env, PYTHONPATH: d } }).stdout.trim(), h)
  assert.ok(!existsSync(marker), '載入了被審目錄裡的 hashlib.py')
  const other = repo()
  writeFileSync(join(other, 'elsewhere.txt'), 'e\n')
  for (const env of [{ GIT_DIR: join(other, '.git') }, { GIT_WORK_TREE: other }, { GIT_INDEX_FILE: join(other, '.git', 'index') }, { GIT_CEILING_DIRECTORIES: dirname(d) }]) {
    assert.equal(run([d], { env: { ...process.env, ...env } }).stdout.trim(), h, `環境 ${Object.keys(env)} 改變了指紋`)
  }
  for (const x of [d, other]) rmSync(x, { recursive: true, force: true })
})

test('路徑含空白、引號、換行、開頭的減號都能用；上層被換成 symlink 不會跟著走出目錄', () => {
  const d = scratch()
  for (const name of ['with space', `q'uote"s`, 'new\nline', '-leading-dash', '--exclude']) {
    const dir = join(d, name)
    mkdirSync(dir)
    writeFileSync(join(dir, 'f.txt'), name + '\n')
    assert.match(run(['--', dir]).stdout, HEX, name)
    const inner = join(dir, `in ${name.replace('--exclude', 'x')}`)
    writeFileSync(inner, 'x\n')
    assert.match(run([inner]).stdout, HEX, name)
  }
  assert.match(run(['-leading-dash'], { cwd: d }).stdout, HEX, '開頭是減號的相對路徑')
  assert.match(run(['--', '--exclude'], { cwd: d }).stdout, HEX, '-- 之後的 --exclude 是路徑')
  // 追蹤中的 dir/secret，dir 被換成指向目錄外的 symlink：外面的內容不算
  const r = repo()
  const out = scratch()
  writeFileSync(join(out, 'app.conf'), 'outside v1\n')
  rmSync(join(r, 'config'), { recursive: true, force: true })
  symlinkSync(out, join(r, 'config'))
  const h = fp(r)
  writeFileSync(join(out, 'app.conf'), 'outside v2\n')
  assert.equal(fp(r), h, '跟著 symlink 讀到了目錄外的檔')
  for (const x of [d, r, out]) rmSync(x, { recursive: true, force: true })
})

test('非 UTF-8 的路徑參數：檔案系統收得下就能用；收不下時（APFS）不存在的路徑仍乾淨失敗', () => {
  const d = scratch()
  const env = { ...process.env, T: TOOL, D: d }
  const make = spawnSync('bash', ['-c', `mkdir "$D"/$'bad\\xff' && printf x > "$D"/$'bad\\xff'/f`], { env, encoding: 'utf8' })
  const script = `"$T" "$D"/$'bad\\xff'`
  const r = spawnSync('bash', ['-c', script], { env, encoding: 'utf8' })
  if (make.status === 0) {
    assert.equal(r.status, 0, r.stderr)
    assert.match(r.stdout, HEX)
    const both = spawnSync('bash', ['-c', `"$T" "$D"`], { env, encoding: 'utf8' })
    assert.match(both.stdout, HEX, both.stderr)
  } else {
    assert.notEqual(r.status, 0)
    assert.equal(r.stdout, '')
    assert.ok(!/Traceback/.test(r.stderr), r.stderr)
  }
  rmSync(d, { recursive: true, force: true })
})

test('大檔分塊讀取，不會整個讀進記憶體', () => {
  const d = scratch()
  const big = join(d, 'big')
  const size = 400 * 1024 * 1024
  writeFileSync(big, '')
  spawnSync('python3', ['-c', 'import os,sys; f=open(sys.argv[1],"r+b"); f.truncate(int(sys.argv[2]))', big, String(size)])
  assert.equal(statSync(big).size, size)
  const code = [
    'import resource, subprocess, sys',
    'r = subprocess.run([sys.argv[1], sys.argv[2]], stdout=subprocess.PIPE)',
    'rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss',
    'print(r.returncode, rss if sys.platform == "darwin" else rss * 1024)',
  ].join('\n')
  const r = spawnSync('python3', ['-c', code, TOOL, big], { encoding: 'utf8', timeout: 120000 })
  const [rc, rss] = r.stdout.trim().split(' ').map(Number)
  assert.equal(rc, 0, r.stderr)
  assert.ok(rss < size / 2, `最大 RSS ${rss} bytes，檔案 ${size} bytes：看起來是整個讀進記憶體`)
  rmSync(d, { recursive: true, force: true })
})

test('目錄裡的 FIFO 不會卡住，也不算內容；未追蹤的巢狀 repo 與 submodule 只算路徑與權限', () => {
  const d = plainDir()
  assert.equal(spawnSync('mkfifo', [join(d, 'pipe')]).status, 0)
  assert.match(run([d]).stdout, HEX)
  rmSync(d, { recursive: true, force: true })
  const r = repo()
  const nested = join(r, 'nested')
  mkdirSync(nested)
  git(nested, 'init', '-q')
  git(nested, 'config', 'user.email', 'a@example.invalid')
  git(nested, 'config', 'user.name', 'a')
  writeFileSync(join(nested, 'n.txt'), 'n\n')
  git(nested, 'add', 'n.txt')
  git(nested, 'commit', '-qm', 'n')
  chmodSync(nested, 0o755)
  const h = fp(r)
  writeFileSync(join(nested, 'n.txt'), 'changed\n')
  assert.equal(fp(r), h, '巢狀 repo 的內容算進去了（協定寫的是不在範圍內）')
  chmodSync(nested, 0o775)
  assert.notEqual(fp(r), h, '巢狀 repo 目錄的權限沒有算進去')
  const direct = fp(nested)
  writeFileSync(join(nested, 'n.txt'), 'again\n')
  assert.notEqual(fp(nested), direct, '把巢狀 repo 另外列成輸入時，內容要算進去')
  rmSync(r, { recursive: true, force: true })
})

test('文件：舊的配方已經不在，五個審閱 skill 以引號呼叫工具，第一行寫出 inputs', () => {
  const docs = [
    'references/checkpoint-protocol.md',
    'CHANGELOG.md',
    'CLAUDE.md',
    ...readdirSync(join(ROOT, 'skills')).map((s) => `skills/${s}/SKILL.md`),
  ]
  const old = ['ls-files -z --cached', 'shasum -a 256', 'find . -name .git', 'hashlib.sha256(open(', "cut -d' ' -f1"]
  const entry = /^## \[2\.26\.0\][\s\S]*?(?=^## \[)/m
  for (const f of docs) {
    let text = readFileSync(join(ROOT, f), 'utf8')
    if (f === 'CHANGELOG.md') text = text.match(entry)[0] // 較舊的版本條目是歷史，不動
    for (const needle of old) assert.ok(!text.includes(needle), `${f} 還有舊配方：${needle}`)
  }
  for (const s of ['academic-review', 'code-review', 'compose', 'lecture-review', 'minutes-review']) {
    const text = readFileSync(join(ROOT, 'skills', `ensemble-${s}`, 'SKILL.md'), 'utf8')
    assert.ok(text.includes('"${CLAUDE_PLUGIN_ROOT}/bin/pai-artifact-fingerprint"'), `${s} 沒有以引號呼叫工具`)
    // 註記與 args 範本都要寫出 inputs：出現的每一處都檢查，只找一處會被另一處蓋過
    const lines = text.match(/artifact sha256: [^\n]*/g)
    assert.ok(lines && lines.length >= 2, `${s} 的註記或 args 範本沒有 artifact sha256 那一行`)
    for (const l of lines) assert.match(l, /^artifact sha256: <[^>]+> inputs: <[^>]+>/, `${s}：${l.slice(0, 60)}`)
  }
  const protocol = readFileSync(join(ROOT, 'references', 'checkpoint-protocol.md'), 'utf8')
  assert.match(protocol, /artifact sha256: <[^>]+> inputs: <[^>]+>/)
  assert.ok(protocol.includes('bin/pai-artifact-fingerprint'))
})

test('文件：五個審閱 skill 的指紋命令照抄就能跑，選填的輸入沒有時不傳（bash 與 zsh）', () => {
  const d = scratch()
  const [a, b, c] = ['main', 'with space', 'third'].map((n) => { const p = join(d, n); writeFileSync(p, n + '\n'); return p })
  // 每個情形：殼層變數、預期等於直接給哪些檔
  const none = { FILE: a, FILE_OR_DIR: a, SRT_FILE: '', GROUND_TRUTH: [], DOCS: [] }
  // 變數根本沒設定也要能跑：zsh 對沒設定的變數，"${X[@]}" 會給一個空字串參數
  const table = {
    'academic-review': [[{ ...none }, [a]], [{ FILE: a }, [a]], [{ ...none, GROUND_TRUTH: [b, c] }, [a, b, c]]],
    'code-review': [[{ ...none }, [a]]],
    compose: [[{ ...none }, [a]]],
    'lecture-review': [[{ ...none }, [a]], [{ FILE: a }, [a]], [{ ...none, SRT_FILE: b }, [a, b]]],
    'minutes-review': [[{ ...none, SRT_FILE: b }, [a, b]], [{ FILE: a, SRT_FILE: b }, [a, b]], [{ ...none, SRT_FILE: b, DOCS: [c] }, [a, b, c]]],
  }
  const q = (s) => `'${s.replace(/'/g, `'\\''`)}'`
  for (const [skill, cases] of Object.entries(table)) {
    const text = readFileSync(join(ROOT, 'skills', `ensemble-${skill}`, 'SKILL.md'), 'utf8')
    const m = text.match(/`("\$\{CLAUDE_PLUGIN_ROOT\}\/bin\/pai-artifact-fingerprint"[^`]*)`/)
    assert.ok(m, `${skill} 找不到指紋命令`)
    for (const [vars, files] of cases) {
      const setup = Object.entries(vars).map(([k, v]) => (Array.isArray(v) ? `${k}=(${v.map(q).join(' ')})` : `${k}=${q(v)}`)).join('; ')
      for (const shell of ['bash', 'zsh']) {
        const r = spawnSync(shell, ['-c', `${setup}; ${m[1]}`], { env: { ...process.env, CLAUDE_PLUGIN_ROOT: ROOT }, encoding: 'utf8' })
        if (r.error && r.error.code === 'ENOENT') continue
        assert.equal(r.status, 0, `${skill}（${shell}）照抄失敗：${r.stderr}`)
        assert.equal(r.stdout.trim(), fp(...files), `${skill}（${shell}）算到的不是這些檔：${m[1]}`)
      }
    }
  }
  rmSync(d, { recursive: true, force: true })
})

test('文件：工具失敗不擋審閱，一律改用 checkpoint: false；checkpoint: false 時沒有這一行', () => {
  const stop = ['工具失敗就停下來', '停下來告訴使用者']
  for (const s of ['academic-review', 'code-review', 'compose', 'lecture-review', 'minutes-review']) {
    const text = readFileSync(join(ROOT, 'skills', `ensemble-${s}`, 'SKILL.md'), 'utf8')
    const line = text.split('\n').find((l) => l.includes('**artifact 指紋**'))
    assert.ok(line, `${s} 找不到 artifact 指紋那一段`)
    for (const needle of stop) assert.ok(!line.includes(needle), `${s} 還要呼叫端停下來：${needle}`)
    assert.match(line, /工具失敗[^。]*審閱照跑[^。]*"checkpoint": false[^。]*接回保護/, `${s} 沒有寫工具失敗時怎麼做`)
    assert.match(line, /`checkpoint: false` 時沒有這一行/, `${s} 沒有寫 checkpoint: false 時不需要這一行`)
  }
  const protocol = readFileSync(join(ROOT, 'references', 'checkpoint-protocol.md'), 'utf8')
  for (const needle of stop) assert.ok(!protocol.includes(needle), `協定還要呼叫端停下來：${needle}`)
  assert.match(protocol, /工具失敗[^。]*審閱照跑[^。]*`checkpoint: false`[^。]*接回保護/)
  const claude = readFileSync(join(ROOT, 'CLAUDE.md'), 'utf8')
  assert.ok(!claude.includes('指紋工具失敗（'), 'CLAUDE.md 的句子沒有謂語')
  assert.match(claude, /指紋工具失敗[^。]*`checkpoint: false`/)
})

test('文件：協定與 CHANGELOG 不再說裁決待確認；inputs: 是資料，不是拿來重跑的文字', () => {
  const protocol = readFileSync(join(ROOT, 'references', 'checkpoint-protocol.md'), 'utf8')
  assert.ok(!/待使用者確認|待確認/.test(protocol), '協定還有待確認的說法')
  const changelog = readFileSync(join(ROOT, 'CHANGELOG.md'), 'utf8').match(/^## \[2\.26\.0\][\s\S]*?(?=^## \[)/m)[0]
  assert.ok(!/待使用者確認|待確認/.test(changelog), 'CHANGELOG 還有待確認的說法')
  assert.match(protocol, /`inputs:` 是資料[^。]*不經 shell 執行[^。]*自己有紀錄就取自己的/)
  for (const [name, text] of [['協定', protocol], ['CHANGELOG', changelog], ['code-review', readFileSync(join(ROOT, 'skills', 'ensemble-code-review', 'SKILL.md'), 'utf8')]]) {
    assert.ok(!/照 `inputs:` 重算|照這一行把 diff/.test(text), `${name} 還叫人重跑那段文字`)
  }
  assert.ok(!/academic 的分析檔/.test(protocol), '已知限制把有給指紋工具的檔說成不在雜湊裡')
  const skill = readFileSync(join(ROOT, 'skills', 'ensemble-code-review', 'SKILL.md'), 'utf8')
  assert.ok(!/\d+ 個 bats 測試/.test(skill), 'code-review 還寫死 bats 的個數')
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
console.log(`\n${pass}/${tests.length} passed${isRoot ? '（以 root 執行，權限相關的斷言不可靠）' : ''}`)
process.exit(fail === 0 ? 0 : 1)
