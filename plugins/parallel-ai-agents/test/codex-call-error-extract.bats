#!/usr/bin/env bats
# codex-call 的 SSE error 訊息提取邏輯（--selftest-error-extract）的 bats 測試。
#
# Regression 錨點（#25）：後端在 HTTP 200 stream 內回
#   {"type":"error","error":{"code":"server_is_overloaded","message":"..."}}
# 時，提取鏈**只有兩條**路徑（top-level message、response.error.message），
# 漏掉 json["error"]["message"]，故兩條皆不命中 →
# 全部落到 fallback "Codex error"，導致 200-stream 內的失敗無法區分原因。
#
# 這裡測的是提取邏輯本身，不打真後端（CODEX_URL 是 hardcoded 常數、無法注入
# mock server；--selftest-error-extract 是為此加的最小可測性介面，不發 HTTP）。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  # codex-call 的 shebang 是 `#!/usr/bin/swift`（釘 Xcode CLT swift，見 plugin CLAUDE.md），
  # 所以這支測試是 macOS-only。CI 的 shellcheck-bats job 跑在 ubuntu-latest 且用
  # `bats test/` glob 整個目錄 —— 沒有這道 guard，本檔在 CI 上會以 exit 126
  # (bad interpreter) 失敗，且下方「無效 JSON → 非零 exit」那則會因為 126≠0 而
  # 以錯誤的理由通過（比紅燈更糟：永遠綠、什麼都沒驗到）。
  # 本 repo 既有的 7 支測試全部可攜，這是第一支平台相依的。
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] \
    || skip "needs macOS + Xcode CLT swift (codex-call is a #!/usr/bin/swift script)"
}

@test "#25 regression：頂層 error 物件內的 message 被正確提取（實測 payload）" {
  run "$BIN" --selftest-error-extract '{"type":"error","error":{"type":"service_unavailable_error","code":"server_is_overloaded","message":"Our servers are currently overloaded. Please try again later.","param":null},"sequence_number":2}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"Our servers are currently overloaded"* ]]
  [[ "$output" != *"Codex error"* ]]
}

@test "response.failed 形狀：既有 response.error.message 路徑行為不變" {
  run "$BIN" --selftest-error-extract '{"type":"response.failed","response":{"error":{"code":"server_is_overloaded","message":"Backend overloaded via response.failed"}}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"Backend overloaded via response.failed"* ]]
}

@test "頂層 message 優先：新增路徑未搶先於既有第一條" {
  run "$BIN" --selftest-error-extract '{"type":"error","message":"top-level msg","error":{"message":"nested msg"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"top-level msg"* ]]
  [[ "$output" != *"nested msg"* ]]
}

@test "所有路徑皆無 message → fallback 到 Codex error" {
  run "$BIN" --selftest-error-extract '{"type":"error","error":{"code":"some_code_without_message"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"Codex error"* ]]
}

@test "無效 JSON → 非零 exit，不靜默" {
  run "$BIN" --selftest-error-extract 'not-json-at-all'
  [ "$status" -ne 0 ]
}

# --- sanitizeBackendText（#25 R5 security HIGH）---
# 本 PR 把 error.message 這條路徑從「實務上是死的」變成「常態會活」，
# 因此後端可控文字的長度上限與控制字元剝除隨同一個變更一起交付，
# 而不是留給 #28。同檔另外兩處外部文字（HTTP 錯誤 body）本來就 .prefix(500)。

@test "cap：超長後端訊息被截斷並標記" {
  LONG=$(printf 'A%.0s' $(seq 1 600))
  run "$BIN" --selftest-error-extract "{\"error\":{\"message\":\"$LONG\"}}"
  [ "$status" -eq 0 ]
  [ "${#output}" -le 520 ]
  [[ "$output" == *"(truncated)"* ]]
}

@test "控制字元剝除：ESC/CSI 不得抵達 stderr（可見文字須保留）" {
  # 控制字元用 JSON 的 \u 逸出序列表達，不可寫 literal —— JSON 規範要求
  # U+0000..U+001F 必須逸出，literal 會讓 payload 本身就是非法 JSON，
  # 於是測到的是「解析失敗」而非「sanitize 生效」（本測試初版就踩到）。
  run "$BIN" --selftest-error-extract '{"error":{"message":"safe\u001b[2Jwiped\u0007"}}'
  [ "$status" -eq 0 ]
  ESC=$(printf '\033'); BEL=$(printf '\007')
  [[ "$output" != *"$ESC"* ]]
  [[ "$output" != *"$BEL"* ]]
  [[ "$output" == *"safe"* ]]
  [[ "$output" == *"wiped"* ]]
}

@test "newline / tab 保留（它們不帶終端控制能力）" {
  run "$BIN" --selftest-error-extract '{"error":{"message":"line1\nline2\tend"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"line1"* ]]
  [[ "$output" == *"line2"* ]]
  [[ "$output" == *"end"* ]]
}

@test "一般長度訊息不因 sanitize 而變形" {
  run "$BIN" --selftest-error-extract '{"error":{"message":"Our servers are currently overloaded. Please try again later."}}'
  [ "$status" -eq 0 ]
  [ "$output" = "Our servers are currently overloaded. Please try again later." ]
}
