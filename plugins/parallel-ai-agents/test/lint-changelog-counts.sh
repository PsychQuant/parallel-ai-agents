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
  # R15：sibling 目錄在、檔案不在 → 必須拒絕（不然 `../pai-lenses/no-such.py` 就是永久豁免）
  # R16 logic L-3：這條斷言只在 sibling 目錄真的存在（monorepo 佈局）時成立——非 monorepo 下第二條斷言的前提
  # 就是「沒有 sibling」，兩條不能同時要求；缺 sibling 時明說略過。
  # R17 logic L-5：這兩條**與佈局無關**（一個必拒、一個必收），所以放在 sibling 判斷之外。
  if bash test/lint-changelog-counts.sh test/fixtures/changelog-count-parent-file-missing.md >/dev/null 2>&1; then
    echo "lint-changelog-counts selftest FAILED: ../<missing file> 只差一層，錨點是永遠存在的 ..，必須拒絕" >&2
    exit 1
  fi
  if ! bash test/lint-changelog-counts.sh test/fixtures/changelog-count-anchor-dir-missing.md >/dev/null 2>&1; then
    echo "lint-changelog-counts selftest FAILED: 錨點目錄缺席的宣稱必須跳過（rc=0），現在被判失敗" >&2
    exit 1
  fi
  if [ -d ../pai-lenses ]; then
    for f in changelog-count-sibling-file-missing changelog-count-sibling-subdir-missing; do
      if bash test/lint-changelog-counts.sh "test/fixtures/$f.md" >/dev/null 2>&1; then
        echo "lint-changelog-counts selftest FAILED: $f.md (present ../sibling, missing file/subdir) must be rejected" >&2
        exit 1
      fi
    done
  else
    echo "lint-changelog-counts selftest: ../pai-lenses 不在（非 monorepo 佈局），sibling-file-missing 那條斷言略過" >&2
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
            # 封閉規則：只有 `../<sibling>/…` 的路徑、且 **sibling 目錄本身不存在**（非 monorepo 佈局）時才跳過——
            # R14 版只看「檔案不存在」，一條指向 `../pai-lenses/沒有的檔` 的宣稱在 monorepo 裡也會被跳過、永遠不被驗
            # （R14 S5 / R15 security LOW：`99999` rc=0 的自我豁免後門）。sibling 目錄在、檔案不在 → 照常算失敗。
            if path.startswith('../') and not os.path.exists(path):
                # R17 logic L-5：R16 的 dirname 判準讓「多寫一層不存在的子目錄」重新拿到永久豁免。封閉規則：只看**第一個
                # 非 `..` 的路徑段**所指的目錄（`../pai-lenses`、`../../.github`）——那是佈局的錨點；錨點不在 → 佈局缺席 →
                # 跳過（訊息只說錨點不在，不斷言佈局）；錨點在而檔案不在 → 照常算失敗。
                parts = path.split('/')
                k = next((i for i, seg in enumerate(parts) if seg != '..'), None)
                # 錨點必須是一個**目錄段**：`../pai-lenses/scripts/x.py` → `../pai-lenses`。若第一個非 `..` 段
                # 就是路徑最後一段（`../nothing.md`），那條路徑的容身處只有 `..`，在任何佈局都存在 → **不得跳過**，
                # 否則「往上一層指一個不存在的檔」又是一個永久豁免（這正是本規則要關的形狀，第一版自己漏了）。
                anchor = '/'.join(parts[:k + 1]) if (k is not None and k + 1 < len(parts)) else None
                if anchor is not None and not os.path.isdir(anchor):
                    print(f"{f}:{n}: note: {anchor} 不在這個 checkout —— 這條宣稱本次無法驗證，跳過", file=sys.stderr)
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
