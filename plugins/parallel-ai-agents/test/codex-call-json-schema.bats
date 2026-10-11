#!/usr/bin/env bats
# codex-call 的結構化輸出（--json-schema，#92）的 bats 測試。
#
# 不打真後端：CODEX_URL 是 hardcoded 常數、無法注入 mock server。請求這一端用 `--_selftest-payload`
# （#87）檢查將要送出的 body；回覆這一端用 `--_selftest-stream FILE`（#92）：把一份 SSE 事件檔餵進
# 與真實串流相同的 `feed()` 與 `finalizeOutput()`，不讀 auth、不發 HTTP（契約 §7）。
#
# **每一則都必須帶 selftest 鉤子（`--_selftest-payload`／`--_selftest-stream`／`--_selftest-sleep`），
# 或在送出前就被拒絕**：HOME 只隔離 run base，不隔離憑證——AUTH_FILE 走 passwd db（detach.bats 的
# round 4 R4-6 註記）。沒帶鉤子又通過驗證的呼叫會讀到真的 auth.json、真的發 HTTPS。
# 實作前跑這份檔是安全的：新旗標不存在時一律是 `unknown option`（#80），在讀 auth 之前就 exit 1。

bats_require_minimum_version 1.5.0

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  # codex-call 是 `#!/usr/bin/swift` script，只在 macOS 上有。
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] \
    || skip "needs macOS + Xcode CLT swift (codex-call is a #!/usr/bin/swift script)"
  T="$BATS_TEST_TMPDIR"
  export HOME_ORIG="$HOME"
  export HOME="$T/home"; mkdir -p "$HOME"     # 隔離 run base（不隔離憑證，見檔頭）
  BASE="$HOME/.cache/codex-call/runs"
  printf '%s\n' '{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}' >"$T/schema.json"
  printf '[1, 2]\n' >"$T/array.json"
  printf '5\n' >"$T/scalar.json"
  # property 順序刻意不是字母序：結構化輸出依 schema 順序生成欄位，順序必須原樣送出
  printf '%s\n' '{"type":"object","properties":{"zeta":{"type":"string"},"alpha":{"type":"integer"}},"required":["zeta","alpha"],"additionalProperties":false}' >"$T/ordered.json"
  printf '{"type": \n' >"$T/broken.json"
  : >"$T/empty.json"
  mkdir -p "$T/adir"
  # 1×1 PNG（與 codex-call-image.bats 同一張），測 --json-schema 與 --image 並用
  base64 -D <<<'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==' >"$T/dot.png"
}

teardown() {
  export HOME="$HOME_ORIG"
}

# payload（JSON）裡的欄位，用 python3 取——macOS 內建，不假設有 jq
pyjson() { local code="$1"; shift; python3 -c "import json,sys; d=json.load(sys.stdin); $code" "$@"; }   # 其餘參數 → sys.argv
payload() { "$BIN" --output "$T/out.md" --_selftest-payload "$@"; }

# 把每個參數當成一個 SSE 事件的 data 寫進 $1
sse() {
  local f="$1"; shift
  : >"$f"
  local e
  for e in "$@"; do printf 'event: x\ndata: %s\n\n' "$e" >>"$f"; done
}
stream() { "$BIN" --output "$T/out.md" --_selftest-stream "$@"; }

DELTA_OPEN='{"type":"response.output_text.delta","delta":"{\"answer\":"}'
DELTA_CLOSE='{"type":"response.output_text.delta","delta":"\"five\"}"}'
DELTA_CUT='{"type":"response.output_text.delta","delta":"\"fi"}'
COMPLETED='{"type":"response.completed","response":{"status":"completed","incomplete_details":null}}'
INCOMPLETE='{"type":"response.incomplete","response":{"status":"incomplete","incomplete_details":{"reason":"max_output_tokens"}}}'
REFUSAL='{"type":"response.refusal.delta","delta":"I cannot help with that request."}'

# ── 請求端：不帶旗標時不變 ─────────────────────────────────────────────────────

@test "no --json-schema: text is exactly {verbosity: medium}" {
  run --separate-stderr payload "hello"
  [ "$status" -eq 0 ]
  run pyjson 'assert d["text"]=={"verbosity":"medium"}, d["text"]; print("ok")' <<<"$output"
  [ "$status" -eq 0 ]
}

@test "no --json-schema: top-level keys are the pre-#92 set and nothing else" {
  run --separate-stderr payload "hello"
  [ "$status" -eq 0 ]
  run pyjson 'print(",".join(sorted(d)))' <<<"$output"
  [ "$output" = "include,input,instructions,model,parallel_tool_calls,reasoning,store,stream,text,tool_choice" ]
}

# ── 請求端：帶旗標 ─────────────────────────────────────────────────────────────

@test "--json-schema: text.format carries the schema unmodified, strict, with the fixed name" {
  run --separate-stderr payload --json-schema "$T/schema.json" "hello"
  [ "$status" -eq 0 ]
  run pyjson '
s=json.load(open(sys.argv[1]))
f=d["text"]["format"]
assert f=={"type":"json_schema","name":"codex_call_output","schema":s,"strict":True}, f
assert d["text"]["verbosity"]=="medium", d["text"]
print("ok")' "$T/schema.json" <<<"$output"
  [ "$status" -eq 0 ]
}

@test "--json-schema: nothing outside text changes" {
  run --separate-stderr payload --json-schema "$T/schema.json" "hello"
  [ "$status" -eq 0 ]
  run pyjson 'print(",".join(sorted(d)))' <<<"$output"
  [ "$output" = "include,input,instructions,model,parallel_tool_calls,reasoning,store,stream,text,tool_choice" ]
}

@test "--json-schema with --image: both the image and the format are sent" {
  run --separate-stderr payload --json-schema "$T/schema.json" --image "$T/dot.png" "describe"
  [ "$status" -eq 0 ]
  run pyjson '
c=d["input"][0]["content"]
assert [x["type"] for x in c]==["input_text","input_image"], c
assert d["text"]["format"]["type"]=="json_schema", d["text"]
print("ok")' <<<"$output"
  [ "$status" -eq 0 ]
}

@test "--json-schema: the schema text is sent unchanged, property order included" {
  run --separate-stderr payload --json-schema "$T/ordered.json" "hello"
  [ "$status" -eq 0 ]
  raw="$(tr -d '\n' <"$T/ordered.json")"
  [[ "$output" == *"$raw"* ]]
}

@test "--json-schema with --prompt-file and --instructions (synchronous)" {
  printf 'score this clip\n' >"$T/prompt.txt"
  run --separate-stderr payload --json-schema "$T/schema.json" --instructions "be terse" --prompt-file "$T/prompt.txt"
  [ "$status" -eq 0 ]
  run pyjson '
assert d["instructions"]=="be terse", d["instructions"]
assert d["input"][0]["content"][0]["text"]=="score this clip\n", d["input"]
assert d["text"]["format"]["type"]=="json_schema", d["text"]
print("ok")' <<<"$output"
  [ "$status" -eq 0 ]
}

# ── 請求端：送出前的驗證（沒印出 payload ＝ 驗證先於送出）────────────────────────

@test "--json-schema: a missing file is refused before anything is sent" {
  run --separate-stderr payload --json-schema "$T/nope.json" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"--json-schema"*"cannot read"* ]]
}

@test "--json-schema: a directory is refused before anything is sent" {
  run --separate-stderr payload --json-schema "$T/adir" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"--json-schema"*"cannot read"* ]]
}

@test "--json-schema: invalid JSON is refused before anything is sent" {
  run --separate-stderr payload --json-schema "$T/broken.json" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"not valid JSON"* ]]
}

@test "--json-schema: an empty file is refused before anything is sent" {
  run --separate-stderr payload --json-schema "$T/empty.json" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"not valid JSON"* ]]
}

@test "--json-schema: a top-level array is refused before anything is sent" {
  run --separate-stderr payload --json-schema "$T/array.json" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"must be a JSON object"* ]]
}

@test "--json-schema: a scalar is refused as not an object, not as invalid JSON" {
  run --separate-stderr payload --json-schema "$T/scalar.json" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"must be a JSON object"* ]]
}

@test "--json-schema given twice is refused instead of silently keeping one" {
  run --separate-stderr payload --json-schema "$T/schema.json" --json-schema "$T/schema.json" "hello"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"--json-schema"*"once"* ]]
}

@test "--json-schema with --poll is refused" {
  run --separate-stderr "$BIN" --poll abcdefghijklmnopqrstuvwxyzabcdef --json-schema "$T/schema.json"
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"--json-schema is only supported for a new request"* ]]
}

@test "--json-schema with --abort is refused" {
  run --separate-stderr "$BIN" --abort abcdefghijklmnopqrstuvwxyzabcdef --json-schema "$T/schema.json"
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"--json-schema is only supported for a new request"* ]]
}

# ── 背景模式：schema 經 meta.json 交給 worker ──────────────────────────────────

@test "--detach writes the schema text, unchanged, into meta.json" {
  run --separate-stderr "$BIN" --detach --_selftest-sleep 1 --json-schema "$T/schema.json" --instructions i "prompt"
  [ "$status" -eq 0 ]
  id="$output"
  run pyjson '
s=open(sys.argv[1]).read().strip()
assert d["json_schema"]==s, d.get("json_schema")
print("ok")' "$T/schema.json" <"$BASE/$id/meta.json"
  [ "$status" -eq 0 ]
  run "$BIN" --poll "$id" --wait 20
  [[ "$output" == DONE* ]]
}

@test "--detach without --json-schema writes no json_schema key" {
  run --separate-stderr "$BIN" --detach --_selftest-sleep 1 --instructions i "prompt"
  [ "$status" -eq 0 ]
  id="$output"
  run pyjson 'assert "json_schema" not in d, d; print("ok")' <"$BASE/$id/meta.json"
  [ "$status" -eq 0 ]
  run "$BIN" --poll "$id" --wait 20
  [[ "$output" == DONE* ]]
}

@test "--detach with a broken schema fails before a run is created" {
  run --separate-stderr "$BIN" --detach --_selftest-sleep 1 --json-schema "$T/broken.json" --instructions i "prompt"
  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *"not valid JSON"* ]]
  # run base 可能根本還不存在；存在的話裡面不得有 run 目錄
  [ ! -d "$BASE" ] || [ -z "$(find "$BASE" -mindepth 1 -maxdepth 1 -type d)" ]
}

@test "worker refuses a meta.json whose json_schema is not a JSON object (no silent schema-less request)" {
  # prelock 視窗內把 json_schema 換成字串（同 detach.bats R5-F2d 的手法）
  ( for _ in $(seq 1 60); do
      for d in "$BASE"/*/; do
        [ -f "$d/meta.json" ] && python3 -c '
import json,sys
import os
p=sys.argv[1]; m=json.load(open(p)); m["json_schema"]="oops"
open(p+".tmp","w").write(json.dumps(m)); os.replace(p+".tmp",p)' "$d/meta.json" 2>/dev/null
      done
      sleep 0.1
    done ) &
  run "$BIN" --detach --_selftest-sleep 1 --_selftest-prelock-sleep 2 --json-schema "$T/schema.json" --instructions i "p"
  wait
  if [ "$status" -eq 0 ]; then id="$output"; run "$BIN" --poll "$id" --wait 20; fi
  [[ "$output" == *"json_schema"* ]]
}

# ── 回覆端（--_selftest-stream）──────────────────────────────────────────────

@test "with --json-schema: valid JSON output is written and exits 0" {
  sse "$T/ok.sse" "$DELTA_OPEN" "$DELTA_CLOSE" "$COMPLETED"
  run --separate-stderr stream "$T/ok.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = '{"answer":"five"}' ]
}

@test "with --json-schema: output that is not valid JSON is refused and no file is written" {
  sse "$T/cut.sse" "$DELTA_OPEN" "$DELTA_CUT" "$COMPLETED"
  run --separate-stderr stream "$T/cut.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"not valid JSON"* ]]
  [ ! -e "$T/out.md" ]
}

@test "with --json-schema: a refusal is reported with its text and no file is written" {
  sse "$T/refusal.sse" "$REFUSAL" "$COMPLETED"
  run --separate-stderr stream "$T/refusal.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"refused"*"I cannot help with that request."* ]]
  [ ! -e "$T/out.md" ]
}

@test "with --json-schema: an incomplete response is refused even when the partial text parses" {
  sse "$T/incomplete.sse" "$DELTA_OPEN" "$DELTA_CLOSE" "$INCOMPLETE"
  run --separate-stderr stream "$T/incomplete.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"incomplete"*"max_output_tokens"* ]]
  [ ! -e "$T/out.md" ]
}

@test "with --json-schema: valid JSON without a completion event is refused and no file is written" {
  sse "$T/nocomplete.sse" "$DELTA_OPEN" "$DELTA_CLOSE"
  run --separate-stderr stream "$T/nocomplete.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"completion"* ]]
  [ ! -e "$T/out.md" ]
}

@test "with --json-schema: a terminal status other than completed is refused" {
  sse "$T/cancelled.sse" "$DELTA_OPEN" "$DELTA_CLOSE" '{"type":"response.completed","response":{"status":"cancelled","incomplete_details":null}}'
  run --separate-stderr stream "$T/cancelled.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"cancelled"* ]]
  [ ! -e "$T/out.md" ]
}

@test "with --json-schema: valid JSON that is not an object is refused" {
  sse "$T/array.sse" '{"type":"response.output_text.delta","delta":"[1, 2]"}' "$COMPLETED"
  run --separate-stderr stream "$T/array.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"not a JSON object"* ]]
  [ ! -e "$T/out.md" ]
}

@test "with --json-schema: control sequences in a refusal never reach stderr raw" {
  sse "$T/esc.sse" '{"type":"response.refusal.delta","delta":"No.\u001b]0;PWNED\u0007\u001b[2J done"}' "$COMPLETED"
  run --separate-stderr stream "$T/esc.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"refused"* ]]
  [[ "$stderr" != *$'\e'* ]]
  [[ "$stderr" != *$'\a'* ]]
}

@test "without --json-schema: non-JSON text is written exactly as before" {
  sse "$T/plain.sse" '{"type":"response.output_text.delta","delta":"plain review text"}' "$COMPLETED"
  run --separate-stderr stream "$T/plain.sse" "p"
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "plain review text" ]
}

@test "without --json-schema: a refusal still fails as empty output (unchanged here; tracked in #93)" {
  sse "$T/refusal.sse" "$REFUSAL" "$COMPLETED"
  run --separate-stderr stream "$T/refusal.sse" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"no text output"* ]]
  [ ! -e "$T/out.md" ]
}

@test "an error event in the stream is still reported (feed() keeps the existing path)" {
  sse "$T/err.sse" '{"type":"error","error":{"code":"server_is_overloaded","message":"Backend overloaded for the test"}}'
  run --separate-stderr stream "$T/err.sse" --json-schema "$T/schema.json" "p"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"Backend overloaded for the test"* ]]
  [ ! -e "$T/out.md" ]
}

@test "--_selftest-stream is refused together with --detach" {
  sse "$T/ok.sse" "$DELTA_OPEN" "$DELTA_CLOSE" "$COMPLETED"
  run --separate-stderr "$BIN" --detach --_selftest-sleep 1 --_selftest-stream "$T/ok.sse" "p"
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"--_selftest-stream is only supported in synchronous mode"* ]]
}

# ── 下游偵測 ───────────────────────────────────────────────────────────────────

@test "--help lists --json-schema FILE" {
  run "$BIN" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"--json-schema FILE"* ]]
}
