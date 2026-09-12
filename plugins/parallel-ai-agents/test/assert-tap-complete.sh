#!/usr/bin/env bash
# 對一份 bats TAP 輸出斷言：沒有失敗、沒有 skip、plan == executed。
# #33 verify R16 DA-6：這條守衛先前有**三份**手抄實作（macOS job、ubuntu pack 錨點 step、run.sh），R15 手抄第三份時
# 改寫成 `A && B || C`（SC2015）讓 CI 紅——同一檢查多份實作的第 N 次。現在只有這一份，三處呼叫。
# 用法：test/assert-tap-complete.sh <tap-file> <label>   退出碼：0 全部成立；1 任一不成立（訊息用 ::error:: 形式）
set -euo pipefail

# R18 requirements F-7：這支是 repo 裡**唯一**沒有 selftest、不在 mutation 範圍、也沒有任何測試的
# 守衛——而它守的正是「假綠」。守門的東西自己沒有網，是這個 PR 一路在修的形狀的最後一處。
if [ "${1:-}" = "--selftest" ]; then
  t=$(mktemp -d); rc_all=0
  chk() {  # chk <期望rc> <說明> <TAP內容>
    printf '%s\n' "$3" > "$t/tap"
    set +e; out=$(bash "$0" "$t/tap" selftest 2>&1); rc=$?; set -e
    if [ "$rc" -ne "$1" ]; then
      echo "assert-tap-complete selftest FAILED: $2 —— 期望 rc=$1，實得 rc=$rc（$out）" >&2; rc_all=1
    fi
  }
  chk 0 "全綠且 plan 相符"            '1..2
ok 1 a
ok 2 b'
  chk 1 "有 not ok"                   '1..2
ok 1 a
not ok 2 b'
  chk 1 "有 skip（錨點空轉）"          '1..2
ok 1 a
ok 2 b # skip no reason'
  chk 1 "plan 多於實際執行"            '1..3
ok 1 a
ok 2 b'
  chk 1 "沒有 plan 行"                'ok 1 a
ok 2 b'
  chk 1 "完全沒有測試（空 glob）"      '1..0'
  rm -rf "$t"
  [ "$rc_all" -eq 0 ] && echo "assert-tap-complete selftest ok: 六種 TAP 輸入各自判對"
  exit "$rc_all"
fi

tap="${1:?tap file}"; label="${2:-bats}"
# `-a`：bats 把含路徑的 CJK skip reason 截在 codepoint 中間時，某些 grep 會把檔案判成 binary 而回報無命中（R15/R16）。
if grep -aq '^not ok' "$tap"; then echo "::error::${label}: a test failed"; exit 1; fi
if grep -aqi '# skip' "$tap"; then echo "::error::${label}: a case was skipped — the anchor is vacuous"; exit 1; fi
grep -aq '^ok' "$tap" || { echo "::error::${label}: no tests ran (empty glob or bats bail-out)"; exit 1; }
# errexit 下 grep 無命中會讓 `$( )` 先死，守衛才到得了——`|| true`（R16 logic LOW）
plan="$(grep -a -m1 -oE '^1\.\.[0-9]+' "$tap" | sed 's/^1\.\.//' || true)"
ran="$(grep -acE '^(ok|not ok) ' "$tap" || true)"
if [ -z "$plan" ] || [ "$ran" -ne "$plan" ]; then
  echo "::error::${label}: TAP plan announces ${plan:-?} tests but ${ran} executed — cases were skipped or unknown to bats"; exit 1
fi
echo "${label}: TAP plan $plan == executed $ran"
