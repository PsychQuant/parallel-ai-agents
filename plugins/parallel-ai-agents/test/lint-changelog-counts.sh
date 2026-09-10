#!/usr/bin/env bash
# 機械護欄（RC13，round 10）：CHANGELOG 裡任何「N 個 case（`grep -c "^@test" <file>`）」、「N 條（`grep -c …`）」、
# 「N 個（`grep -c …`）」的宣稱（三種形式見下方 CLAIM），N 必須等於那條命令**此刻**的輸出。
#
# 為什麼：這個數字手打錯了五次（round 7：69 vs 76；round 9：76 vs 79）——而 round 8 起那一句
# 自己就宣稱「由 grep -c 產生、不手打」。散文規則寫了四次都沒用，所以跟 lint-bats 一樣改成機器擋：
# 宣稱裡附的命令就是判準，lint 只是真的去跑它。
#
# 用法：test/lint-changelog-counts.sh [file...]   預設 CHANGELOG.md
#       test/lint-changelog-counts.sh --selftest   對故意寫錯數字的 fixture 必須回非零
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  if bash test/lint-changelog-counts.sh test/fixtures/changelog-count-bad.md >/dev/null 2>&1; then
    echo "lint-changelog-counts selftest FAILED: the fixture with a wrong count was accepted" >&2
    exit 1
  fi
  # #33 verify R13：宣稱可以指向 sibling plugin（`../pai-lenses/…`）。那個檔在 plugin cache 副本裡不存在，
  # 此時要「跳過並註明」而不是報「數字錯」—— 後者是 R12 #4 那種對錯誤佈局的肯定式假診斷。
  if ! bash test/lint-changelog-counts.sh test/fixtures/changelog-count-sibling-absent.md >/dev/null 2>&1; then
    echo "lint-changelog-counts selftest FAILED: a claim on an absent ../sibling file must be skipped, not rejected" >&2
    exit 1
  fi
  echo "lint-changelog-counts selftest ok: fixture rejected"
  exit 0
fi

files=("$@")
if [ "${#files[@]}" -eq 0 ]; then files=(CHANGELOG.md); fi

python3 - "${files[@]}" <<'PY'
import os, re, subprocess, sys
# 「N 個 case」之後、括號之前允許 markdown 裝飾（**），括號可全形或半形；命令逐字取自宣稱本身。
# 三種宣稱形式（封閉列舉，不得類推第四種；#33 verify R13 R13-1 加第二種、R14 L-10/E-5 加第三種——
# 靶數在測試數的同一句話裡照樣手打）：
#   N 個 case（`grep -c "^@test" <file>`）
#   N 條（`grep -c "<pattern>" <file>`）        ← pattern 逐字取自宣稱，lint 只是真的去跑它
#   N 個（`grep -c "<pattern>" <file>`）        ← 靶數：MUTATIONS 的每個 tuple 恰以 `    ("` 起頭
CLAIM = re.compile(r'(\d+)\s*(?:個\s*case|條|個)[^（(]*[（(]`grep -c "((?:[^"\\]|\\.)+)" ([^`]+)`[）)]')
rc, seen = 0, 0
for f in sys.argv[1:]:
    for n, line in enumerate(open(f, encoding='utf-8'), 1):
        for m in CLAIM.finditer(line):
            seen += 1
            claimed, pattern, path = int(m.group(1)), m.group(2), m.group(3)
            # 封閉規則：只有 `../` 開頭（sibling plugin）的路徑允許不存在——plugin cache 副本沒有 sibling，
            # 那不是「數字錯」。plugin 自己底下的檔案不在就照常算失敗。
            if path.startswith('../') and not os.path.exists(path):
                print(f"{f}:{n}: note: {path} 不在這個 checkout（非 monorepo 佈局）—— 這條宣稱本次無法驗證，跳過", file=sys.stderr)
                continue
            out = subprocess.run(['grep', '-c', pattern, path], capture_output=True, text=True)
            actual = out.stdout.strip()
            if not actual.isdigit() or int(actual) != claimed:
                print(f"{f}:{n}: claims {claimed} for {path}; `grep -c \"{pattern}\" {path}` says {actual or '(unreadable)'}", file=sys.stderr)
                rc = 1
if seen == 0:
    print(f"no case-count claims found in {' '.join(sys.argv[1:])} — the lint would be vacuous", file=sys.stderr)
    sys.exit(1)
sys.exit(rc)
PY
