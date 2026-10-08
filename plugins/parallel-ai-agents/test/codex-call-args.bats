#!/usr/bin/env bats
# codex-call 的參數解析（#80）：不認得的旗標必須報錯，不得被當成 PROMPT 吞掉。
#
# 修之前，`default:` 分支把任何不認得的字串（包括 `--something`）當成位置參數 PROMPT。
# 最危險的一種是「不認得的旗標 + stdin prompt」：旗標字串**取代**整份 stdin prompt、rc=0，
# 模型根本沒看到 caller 送的內容，在 verify ensemble 裡讀起來像一次乾淨的通過。
#
# **每一則都帶 `--_selftest-payload`**：HOME 不隔離憑證（AUTH_FILE 走 passwd db，detach.bats R4-6），
# 解析若錯誤放行，沒有鉤子的呼叫會真的發 HTTPS。有鉤子時錯放行只會印出 payload、exit 0，斷言照樣抓得到。
# 背景模式那則另帶 `--_selftest-sleep`，錯放行時 worker 只 sleep＋寫檔。HOME 仍指向空目錄，隔離 run base。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] \
    || skip "needs macOS + Xcode CLT swift (codex-call is a #!/usr/bin/swift script)"
  T="$BATS_TEST_TMPDIR"
  mkdir -p "$T/emptyhome"
  printf 'PROMPT-FROM-FILE\n' >"$T/p.md"
}

cc() { env HOME="$T/emptyhome" "$BIN" "$@"; }

# ── issue #80 的表格，一列一則 ────────────────────────────────────────────────

@test "#80 row 1: unknown flag with a value names the flag, not the value" {
  run bash -c 'echo "real prompt" | env HOME="$1" "$2" --output "$3/out.md" --_selftest-payload --foo bar' _ "$T/emptyhome" "$BIN" "$T"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown option: --foo"* ]]
  [[ "$output" != *"unexpected positional argument"* ]]
}

@test "#80 row 2: unknown flag next to --prompt-file is refused" {
  run cc --output "$T/out.md" --_selftest-payload --quiet --prompt-file "$T/p.md"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown option: --quiet"* ]]
}

@test "#80 row 3: unknown flag no longer replaces a stdin prompt" {
  run bash -c 'echo "Reply only STDIN-OK" | env HOME="$1" "$2" --output "$3/out.md" --_selftest-payload --quiet' _ "$T/emptyhome" "$BIN" "$T"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown option: --quiet"* ]]
  [[ "$output" != *"input_text"* ]]
}

@test "unknown single-dash flag is refused" {
  run cc --output "$T/out.md" --_selftest-payload -x "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown option: -x"* ]]
}

@test "unknown flag is refused before a background run is created" {
  run cc --detach --_selftest-sleep 1 --output "$T/out.md" --cwd /tmp "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown option: --cwd"* ]]
  [ ! -d "$T/emptyhome/.cache/codex-call/runs" ] || [ -z "$(ls -A "$T/emptyhome/.cache/codex-call/runs")" ]
}

# ── 合法的寫法仍然通 ─────────────────────────────────────────────────────────

@test "a PROMPT that starts with '-' is accepted after --" {
  run cc --output "$T/out.md" --_selftest-payload -- "- first item"
  [ "$status" -eq 0 ]
  run python3 -c 'import json,sys; print(json.load(sys.stdin)["input"][0]["content"][0]["text"])' <<<"$output"
  [ "$output" = "- first item" ]
}

@test "every documented flag still parses" {
  run cc --output "$T/out.md" --model m --effort low --service-tier fast --max-time 30 \
         --instructions "be brief" --_selftest-payload "p"
  [ "$status" -eq 0 ]
  run python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["model"], d["reasoning"]["effort"], d["service_tier"], d["instructions"])' <<<"$output"
  [ "$output" = "m low priority be brief" ]
}

@test "-o is still the short form of --output" {
  run cc -o "$T/out.md" --_selftest-payload "p"
  [ "$status" -eq 0 ]
}

# ── PROMPT 只能給一次 ────────────────────────────────────────────────────────

@test "a PROMPT argument together with --prompt-file is refused" {
  run cc --output "$T/out.md" --_selftest-payload --prompt-file "$T/p.md" "also a prompt"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--prompt-file"* ]]
  [[ "$output" == *"PROMPT"* ]]
}

@test "two PROMPT arguments are still refused" {
  run cc --output "$T/out.md" --_selftest-payload "one" "two"
  [ "$status" -ne 0 ]
  [[ "$output" == *"unexpected positional argument: two"* ]]
}
