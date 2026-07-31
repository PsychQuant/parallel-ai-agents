#!/usr/bin/env bats
# codex-call 的 SSE error 訊息提取邏輯（--selftest-error-extract）的 bats 測試。
#
# Regression 錨點（#25）：後端在 HTTP 200 stream 內回
#   {"type":"error","error":{"code":"server_is_overloaded","message":"..."}}
# 時，提取鏈曾漏掉 json["error"]["message"] 這條路徑，三條路徑無一命中 →
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
