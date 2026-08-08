#!/usr/bin/env bats
# pai-contribute-lenses（層 ③ 回流流程）的 bats 測試。
#
# 這支腳本存在的理由就是「可測」：#33 的前兩版把流程寫成 SKILL.md 裡的 bash 區塊，
# 兩輪 6-AI verify 都判 FAIL——跨 Bash 呼叫的 shell 變數不存活、`profile` 從未被賦值、
# 沒有 set -e 所以「閘門」不是閘門。文件測不了，腳本測得了。
#
# 鐵律：全部用 BATS_TEST_TMPDIR 內自建的 user lens 目錄，絕不讀開發機真實的
# ~/.claude/pai-lenses/。repo 用真實的 checkout（唯讀操作 + --dry-run）。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-contribute-lenses"
  ROOT="$(cd "${BATS_TEST_DIRNAME}/../../.." && pwd)"
  USERDIR="${BATS_TEST_TMPDIR}/userlens"
  mkdir -p "$USERDIR"
  export PAI_USER_LENS_DIR="$USERDIR"
}

# 取一條真實的 built-in lens（key 與 focus），供「逐字相同」與「同 key 不同 focus」用
builtin_row() {
  python3 -c "
import csv,sys
rows=[r for r in csv.DictReader(open(sys.argv[1],encoding='utf-8-sig'))
      if r.get('profile')=='code' and (r.get('key') or '').strip()]
r=rows[0]; print(r['key']); print(r['focus'])
" "${ROOT}/plugins/parallel-ai-agents/references/builtin-lenses.csv"
}

@test "本機無 user lens 目錄 → 靜默 exit 0" {
  export PAI_USER_LENS_DIR="${BATS_TEST_TMPDIR}/nope"
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"沒有可貢獻的 lens"* ]]
}

@test "全新 lens → CANDIDATE，dry-run 印計畫且不寫入任何檔案" {
  printf 'key,focus\nzz-brand-new,"檢查 hot path 的複雜度, 以及重算"\n' > "${USERDIR}/code.csv"
  before=$(cd "$ROOT" && git status --porcelain | wc -l)
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CANDIDATE"* ]]
  [[ "$output" == *"zz-brand-new"* ]]
  [[ "$output" == *"dry-run"* ]]
  after=$(cd "$ROOT" && git status --porcelain | wc -l)
  [ "$before" -eq "$after" ]
}

@test "與 built-in 逐字相同 → SKIP（不是 MODIFY，也不進 override 路徑）" {
  # #33 verify R2 H13：先前 builtin 的 focus 讀進來卻從未比較（dead code），
  # 導致「上游已經有一模一樣的東西」被判成 MODIFY 並要求 override 理由。
  mapfile -t row < <(builtin_row)
  python3 -c "
import csv,sys
w=csv.writer(open(sys.argv[1],'w',newline=''))
w.writerow(['key','focus']); w.writerow([sys.argv[2], sys.argv[3]])
" "${USERDIR}/code.csv" "${row[0]}" "${row[1]}"
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"SKIP"* ]]
  [[ "$output" != *"MODIFY"* ]]
}

@test "同 key 但 focus 不同 → MODIFY；未給理由時 exit 3 而非擅自送出" {
  mapfile -t row < <(builtin_row)
  python3 -c "
import csv,sys
w=csv.writer(open(sys.argv[1],'w',newline=''))
w.writerow(['key','focus']); w.writerow([sys.argv[2],'完全不同的 focus 內容'])
" "${USERDIR}/code.csv" "${row[0]}"
  run python3 "$BIN" --dry-run --repo-root "$ROOT" --include-override
  [ "$status" -eq 3 ]
  [[ "$output" == *"MODIFY"* ]] || [[ "$output" == *"取代理由"* ]]
}

@test "override 給了理由 → 可進行" {
  mapfile -t row < <(builtin_row)
  python3 -c "
import csv,sys
w=csv.writer(open(sys.argv[1],'w',newline=''))
w.writerow(['key','focus']); w.writerow([sys.argv[2],'完全不同的 focus 內容'])
" "${USERDIR}/code.csv" "${row[0]}"
  run python3 "$BIN" --dry-run --repo-root "$ROOT" --include-override \
      --override-reason "${row[0]}=內建那條漏了 X"
  [ "$status" -eq 0 ]
  [[ "$output" == *"dry-run"* ]]
}

@test "未標 --include-override 時，MODIFY 不會被送出（預設不送）" {
  mapfile -t row < <(builtin_row)
  python3 -c "
import csv,sys
w=csv.writer(open(sys.argv[1],'w',newline=''))
w.writerow(['key','focus']); w.writerow([sys.argv[2],'完全不同的 focus 內容'])
" "${USERDIR}/code.csv" "${row[0]}"
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"沒有需要送出的 lens"* ]]
}

@test "新 profile → exit 3 並說明缺哪些 profile 級欄位（不代填）" {
  # CSV 描述不了 title / daFocus / codexDefault；代填等於替使用者做設計決定。
  printf 'key,focus\nfoo,某個檢查\n' > "${USERDIR}/zz-not-a-profile.csv"
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 3 ]
  [[ "$output" == *"不在 PROFILES"* ]]
  [[ "$output" == *"daFocus"* ]]
}

@test "--profile 真的會篩選（只處理指定的那一個檔）" {
  printf 'key,focus\naaa,檢查 A\n' > "${USERDIR}/code.csv"
  printf 'key,focus\nbbb,檢查 B\n' > "${USERDIR}/academic.csv"
  run python3 "$BIN" --dry-run --repo-root "$ROOT" --profile code
  [ "$status" -eq 0 ]
  [[ "$output" == *"aaa"* ]]
  [[ "$output" != *"bbb"* ]]
}

@test "bump 計畫一定同時涵蓋 plugin.json 與 marketplace.json" {
  # 只 bump 一處時使用者 /plugin update 收不到新版，且無任何錯誤訊息。
  printf 'key,focus\nzz-brand-new,某個檢查\n' > "${USERDIR}/code.csv"
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"plugin.json + marketplace.json"* ]]
}

@test "focus 含逗號與引號不會被切爛（走 parser 不是 naive split）" {
  printf 'key,focus\nzz-comma,"檢查 a, b, 以及 ""c"" 的情況"\n' > "${USERDIR}/code.csv"
  run python3 "$BIN" --dry-run --repo-root "$ROOT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"CANDIDATE"* ]]
  [[ "$output" == *"zz-comma"* ]]
}
