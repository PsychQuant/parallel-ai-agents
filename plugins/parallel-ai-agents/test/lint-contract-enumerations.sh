#!/usr/bin/env bash
# 機械護欄（round 11，R11-1）：`references/codex-call-contract.md` 自稱「封閉列舉」的地方，
# 必須與 `bin/codex-call` 實際印出的東西、以及與它自己同一節的另一句話一致。
#
# 為什麼：round 10 的契約在**同一個 commit** 裡，同型的手打枚舉缺陷復發四次——force-reap 的
# stdout 少列一種 token、exit-1 列舉少一個答案、§6 lead-in 寫「五項」句尾寫「六項」、abort 表
# 自稱十一列實有十二列。RC13（CHANGELOG 的 case 數）已證明散文規則對數字無效，round 10 把它機械化
# 了卻只覆蓋 CHANGELOG；本檔把同一個教訓推到它真正的適用範圍——契約。
#
# 五項檢查（封閉列舉，加新檢查要附 fixture）：
#   A  stdout token，依函式分節：doPoll / doAbort / doForceReap 裡每個 print("…") 的字面前綴，
#      必須出現在契約對應的 `### \`--poll\`` / `### \`--abort\`` / `### \`--force-reap\`` 小節內
#      （全域出現不算——round 10 的漏項正是「abort 表有、force-reap 節沒有」）。
#   B  exit-1 答案，雙向：§2「exit `1` 的答案」那一段裡每個反引號片語（`…` 當萬用）要對得到
#      code 裡某個 die/log 字串；反過來，doPoll / doAbort / doForceReap / resolveRun /
#      refuseIfUntrusted 裡每個 die("…") 的訊息，要有一段 ≥ 6 個連續英文字逐字出現在 §2。
#   C  `--abort` 表的資料列數 = 「上表封閉（N 列）」的中文數字。
#   D  §6「寫得到 base 者可以」那一個 bullet：(n) 項數 = lead-in 的「封閉列舉 N 項」= 句尾「以上 N 項」。
#   E  R10-B5s 依賴的三個 grep pattern 在 bin/codex-call 各恰好一次（否則 head -1 靜默選錯）。
#
# 用法：test/lint-contract-enumerations.sh [contract.md] [codex-call]   預設 references/… 與 bin/…
#       test/lint-contract-enumerations.sh --selftest   對 test/fixtures/contract-enum-bad/ 必須回非零
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  # 每一項檢查各有一個故意做壞的 fixture；任何一個被接受就是護欄無牙。
  rc=0
  for f in test/fixtures/contract-enum-bad/*.md; do            # broken CONTRACT, real code
    if bash test/lint-contract-enumerations.sh "$f" bin/codex-call >/dev/null 2>&1; then
      echo "lint-contract-enumerations selftest FAILED: $f was accepted" >&2; rc=1
    fi
  done
  for f in test/fixtures/contract-enum-bad/*.swift; do         # real contract, broken CODE (check E)
    if bash test/lint-contract-enumerations.sh references/codex-call-contract.md "$f" >/dev/null 2>&1; then
      echo "lint-contract-enumerations selftest FAILED: $f was accepted" >&2; rc=1
    fi
  done
  # 對照組：現行契約 + 現行 code 必須通過（否則 selftest 本身是空的）。
  if ! bash test/lint-contract-enumerations.sh >/dev/null 2>&1; then
    echo "lint-contract-enumerations selftest FAILED: the real contract does not pass" >&2; rc=1
  fi
  [ "$rc" -eq 0 ] && echo "lint-contract-enumerations selftest ok: every bad fixture rejected, real contract accepted"
  exit "$rc"
fi

CONTRACT="${1:-references/codex-call-contract.md}"
CODE="${2:-bin/codex-call}"

python3 - "$CONTRACT" "$CODE" <<'PY'
import re, sys
contract_path, code_path = sys.argv[1], sys.argv[2]
C = open(contract_path, encoding="utf-8").read()
S = open(code_path, encoding="utf-8").read()
errors = []
def err(tag, msg): errors.append(f"[{tag}] {msg}")

# ---------- helpers ----------
def section(heading_re):
    """Text of the contract from a heading matching heading_re up to the next heading of the same or higher level."""
    m = re.search(heading_re, C, re.M)
    if not m: return None
    level = len(re.match(r'#+', C[m.start():]).group(0))
    rest = C[m.end():]
    n = re.search(r'^#{1,%d} ' % level, rest, re.M)
    return rest[:n.start()] if n else rest

def func_body(name):
    """Body of `func <name>(` in the Swift script, up to the next top-level `func `/`// MARK`/`struct`/`enum` line."""
    m = re.search(r'^func %s\(' % re.escape(name), S, re.M)
    if not m: return ""
    rest = S[m.end():]
    n = re.search(r'^(func |// MARK|struct |enum |let |var )', rest, re.M)
    return rest[:n.start()] if n else rest

def print_tokens(body):
    """Literal stdout prefixes: every string literal inside a print(...) call — including the
    branches of `print(cond ? "A" : "B")` (round 11's force-reap token is exactly that shape; a
    regex anchored on `print("` silently extracted nothing and passed) — trimmed to the text
    before the first \\( interpolation."""
    out = set()
    for m in re.finditer(r'^[^\n]*\bprint\((.*)\)[^\n]*$', body, re.M):
        for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)):
            pre = re.split(r'\\\(', lit)[0].strip()
            if pre: out.add(pre)
    return out

def die_messages(body):
    """die("…") literals with interpolations collapsed to …"""
    out = []
    for m in re.finditer(r'die\("((?:[^"\\]|\\.)*)"', body):
        lit = re.sub(r'\\\([^)]*\)', '…', m.group(1))
        out.append(lit)
    return out

# ---------- A: stdout tokens per function → per section ----------
sec_map = {
    "doPoll":      r'^### `--poll <id>`',
    "doAbort":     r'^### `--abort <id>`',
    "doForceReap": r'^### `--force-reap <id>`',
}
for fn, hre in sec_map.items():
    sec = section(hre)
    if sec is None: err("A", f"contract has no section matching {hre}"); continue
    for tok in sorted(print_tokens(func_body(fn))):
        if f"`{tok}" not in sec:   # `TOKEN` or `TOKEN <path>` / `TOKEN …`
            err("A", f"{fn} prints stdout token `{tok}` but the contract section for it does not list it")

# ---------- B: exit-1 answers, both directions ----------
s2 = section(r'^## 2\. ')
if s2 is None:
    err("B", "contract has no `## 2.` section")
else:
    m = re.search(r'exit `1` 的答案不在上表.*?封閉列舉[：:](.*?)本列舉封閉', s2, re.S)
    if not m:
        err("B", "cannot locate the §2 exit-1 closed list (`exit \\`1\\` 的答案不在上表 … 封閉列舉：… 本列舉封閉`)")
    else:
        code_text = S
        for phrase in re.findall(r'`([^`]+)`', m.group(1)):
            if phrase.startswith('--'): continue          # flag names, not answers
            parts = [re.escape(p.strip()) for p in phrase.split('…') if p.strip()]
            if not parts: continue
            pat = r'.*?'.join(parts)
            if not re.search(pat, code_text, re.S):
                err("B", f"§2 exit-1 list names `{phrase}` but no die/log string in {code_path} matches it")
    # code → contract: every die in the background-mode entry points must match at least one
    # backticked answer the contract enumerates (the §2 exit-1 list, the `--abort` table, or the
    # `--force-reap` section). `…` inside a contract phrase is a wildcard. Symmetric with the
    # direction above: the contract names every answer, and every answer is named.
    pool = m.group(1) if m else ""
    for hre in (r'^### `--abort <id>`', r'^### `--force-reap <id>`'):
        pool += "\n" + (section(hre) or "")
    phrases = []
    for ph in re.findall(r'`([^`]+)`', pool):
        if ph.startswith('--') or ph.startswith('<') or len(re.findall(r'[A-Za-z]+', ph)) < 2: continue
        ph = re.sub(r'<[^>]+>', '…', ph)                  # `<path>` / `<dir>` placeholders are wildcards too
        parts = [re.escape(p.strip()) for p in ph.split('…') if p.strip()]
        if parts: phrases.append((ph, re.compile(r'.*?'.join(parts), re.S)))
    for fn in ("doPoll", "doAbort", "doForceReap", "resolveRun", "refuseIfUntrusted"):
        for msg in die_messages(func_body(fn)):
            if not any(rx.search(msg) for _, rx in phrases):
                err("B", f"{fn} can exit 1 with «{msg[:90]}» — no backticked answer in §2 / `--abort` / `--force-reap` matches it (undocumented)")

# ---------- C: abort table rows vs 「上表封閉（N 列）」 ----------
CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
def cn2int(s):
    if s.isdigit(): return int(s)
    if s == '十': return 10
    if s.startswith('十'): return 10 + CN[s[1]]
    if s.endswith('十'): return CN[s[0]] * 10
    if '十' in s:
        a, b = s.split('十'); return CN[a]*10 + CN[b]
    return CN[s]
ab = section(r'^### `--abort <id>`')
if ab is None: err("C", "no `--abort` section")
else:
    rows = [l for l in ab.splitlines() if l.startswith('| ') and not l.startswith('| 情況')]
    m = re.search(r'上表封閉（([一二三四五六七八九十\d]+)列）', ab)
    if not m: err("C", "`--abort` table has no 「上表封閉（N 列）」 sentence")
    elif cn2int(m.group(1)) != len(rows):
        err("C", f"`--abort` table has {len(rows)} data rows but the text says 「{m.group(1)}列」")

# ---------- D: §6 harm enumeration cardinality ----------
s6 = section(r'^## 6\. ')
if s6 is None: err("D", "no `## 6.` section")
else:
    bl = next((l for l in s6.splitlines() if '寫得到 base 者可以' in l), None)
    if bl is None: err("D", "§6 has no 「寫得到 base 者可以」 bullet")
    else:
        items = sorted({int(x) for x in re.findall(r'\((\d)\) ', bl)})
        lead = re.search(r'封閉列舉([一二三四五六七八九十\d]+)項', bl)
        tail = re.search(r'以上([一二三四五六七八九十\d]+)項為封閉列舉', bl)
        n = len(items)
        if items != list(range(1, n+1)): err("D", f"§6 items are not 1..n: {items}")
        if not lead: err("D", "§6 bullet has no lead-in 「封閉列舉 N 項」")
        elif cn2int(lead.group(1)) != n: err("D", f"§6 lead-in says {lead.group(1)} items, bullet lists {n}")
        if not tail: err("D", "§6 bullet has no closing 「以上 N 項為封閉列舉」")
        elif cn2int(tail.group(1)) != n: err("D", f"§6 closing says {tail.group(1)} items, bullet lists {n}")

# ---------- E: R10-B5s grep patterns unique in code ----------
for pat, label in ((r'O_RDWR \| O_CREAT \| O_EXCL \| O_NOFOLLOW', 'create'),
                   (r'try p\.run\(\)', 'spawn'),
                   (r'^    print\(id\); exit\(0\)', 'printid')):
    n = len(re.findall(pat, S, re.M))
    if n != 1: err("E", f"R10-B5s pattern for {label} matches {n} lines in {code_path} (must be exactly 1, or head -1 silently picks the wrong one)")

if errors:
    print(f"{contract_path}: {len(errors)} enumeration drift(s) vs {code_path}", file=sys.stderr)
    for e in errors: print("  " + e, file=sys.stderr)
    sys.exit(1)
print(f"lint-contract-enumerations ok: {contract_path} agrees with {code_path} (A stdout tokens, B exit-1 answers, C abort rows, D §6 cardinality, E B5s uniqueness)")
PY
