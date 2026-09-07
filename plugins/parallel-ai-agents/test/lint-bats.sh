#!/usr/bin/env bash
# 機械護欄：bats 檔內不得有裸 `!` 斷言。
#
# 為什麼：bats 只靠 errexit 判失敗，而 bash 對 `!` 前綴的 pipeline **不觸發 errexit**——
# `! grep -q X f` 在 bats 裡永遠不會讓測試失敗。round 3 verify 判它「同型第三度復發」，
# round 6 仍在（`R5-S3`／`R5-L8` 的核心斷言是 no-op：mutant 偵測率 0/10，改寫後 10/10）。
# 散文規則寫了四次都沒用，所以改成機器擋。規則零例外：寫 `run cmd; [ "$status" -ne 0 ]`。
#
# 用法：test/lint-bats.sh [file...]      預設 test/*.bats（不含 fixtures/）
#       test/lint-bats.sh --selftest     護欄自己的自測：對故意含 `!` 的 fixture 必須回非零
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  # 護欄本身要有一個會失敗的案例，否則它只是第五度復發的預備（round 6 DA Q8）。
  if bash test/lint-bats.sh test/fixtures/lint-bats-bad.bats >/dev/null 2>&1; then
    echo "lint-bats selftest FAILED: the fixture with a bare '!' was accepted" >&2
    exit 1
  fi
  echo "lint-bats selftest ok: fixture rejected"
  exit 0
fi

files=("$@")
if [ "${#files[@]}" -eq 0 ]; then files=(test/*.bats); fi
rc=0
for f in "${files[@]}"; do
  if hits="$(grep -nE '^[[:space:]]*!([[:space:]]|$)' "$f")"; then
    echo "$f: bare '!' assertion(s) — bats' errexit never fires on them; write: run cmd; [ \"\$status\" -ne 0 ]" >&2
    echo "$hits" >&2
    rc=1
  fi
done
exit "$rc"
