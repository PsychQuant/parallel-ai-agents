#!/usr/bin/env bats
# codex-call 的 SSE 終端事件「勝出政策」測試（--selftest-process-events）。
#
# 為什麼需要這一支（#25 R2）：
#   `codex-call-error-extract.bats` 測的是純函式 extractErrorMessage —— 每個 case
#   只餵一個 payload，因此**在構造上看不見**多事件交錯的問題。R1 的修法（arrival-order
#   latch `if streamError == nil`）就是在那組測試全綠的情況下引入了一個回歸：把失敗
#   從「分 chunk, rich→bare」搬到「分 chunk, bare→rich」。
#
#   爭議所在的語意（哪個終端事件勝出）恰恰是零覆蓋的那一塊，而不具爭議的
#   extractErrorMessage 有 5 個 case。這支測試補的正是那一塊。
#
# 兩個被本輪修正的缺陷是**複合**的，必須一起測：
#   (1) 勝出政策：arrival-order → informativeness（bare 不得壓住後到的 rich）
#   (2) buffer drain：原本 while-loop 內的 early return 會在同一個 chunk 內丟掉
#       sibling 事件 —— 而終端錯誤正是 backend flush+close 的時刻，同 chunk 抵達
#       的機率不低於分開
#
# 輸入格式：--selftest-process-events 吃一個 JSON array of chunk strings，
# 每個元素代表一次 didReceive 收到的 chunk（可含 0..N 個完整 SSE 事件）。
# 這讓「chunk 邊界」成為可直接表達的測試輸入，不需要網路或 CODEX_URL 注入點。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  # 同 codex-call-error-extract.bats：codex-call 是 #!/usr/bin/swift script。
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] \
    || skip "needs macOS + Xcode CLT swift (codex-call is a #!/usr/bin/swift script)"
}

# 無 message 的終端事件（會落到 fallback）
BARE='data: {\"type\":\"error\",\"error\":{\"code\":\"some_code_without_message\"}}\n\n'
# 帶 message 的終端事件
RICH='data: {\"type\":\"response.failed\",\"response\":{\"error\":{\"message\":\"RICH_MESSAGE\"}}}\n\n'

@test "A 同 chunk, bare→rich：rich 勝出（需要 buffer drain）" {
  run "$BIN" --selftest-process-events "[\"${BARE}${RICH}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RICH_MESSAGE"* ]]
  [[ "$output" != *"Codex error"* ]]
}

@test "B 分 chunk, bare→rich：rich 勝出（需要 informativeness policy）" {
  run "$BIN" --selftest-process-events "[\"${BARE}\",\"${RICH}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RICH_MESSAGE"* ]]
  [[ "$output" != *"Codex error"* ]]
}

@test "C 同 chunk, rich→bare：rich 保留（bare 不得覆寫）" {
  run "$BIN" --selftest-process-events "[\"${RICH}${BARE}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RICH_MESSAGE"* ]]
}

@test "D 分 chunk, rich→bare：rich 保留（R1 原本要修的那個）" {
  run "$BIN" --selftest-process-events "[\"${RICH}\",\"${BARE}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RICH_MESSAGE"* ]]
}

@test "只有 bare：如實落到 fallback，不虛構訊息" {
  run "$BIN" --selftest-process-events "[\"${BARE}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Codex error"* ]]
}

@test "只有 rich：訊息完整取出" {
  run "$BIN" --selftest-process-events "[\"${RICH}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RICH_MESSAGE"* ]]
}

@test "兩個 rich：先到者保留，後到者不覆寫（policy 只提升資訊量、不追新）" {
  R2='data: {\"type\":\"error\",\"error\":{\"message\":\"SECOND_RICH\"}}\n\n'
  run "$BIN" --selftest-process-events "[\"${RICH}\",\"${R2}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"RICH_MESSAGE"* ]]
  [[ "$output" != *"SECOND_RICH"* ]]
}

@test "無終端事件：不虛構錯誤" {
  DELTA='data: {\"type\":\"response.output_text.delta\",\"delta\":\"hello\"}\n\n'
  run "$BIN" --selftest-process-events "[\"${DELTA}\"]"
  [ "$status" -eq 0 ]
  [[ "$output" == *"(no error)"* ]]
}

@test "非 JSON array 輸入 → 非零 exit" {
  run "$BIN" --selftest-process-events '{"not":"an array"}'
  [ "$status" -ne 0 ]
}
