#!/usr/bin/env bats
# codex-call 的 SSE 分幀（#28）：`didReceive` 依 TCP 的可得量交付 Data，切點與 UTF-8 字元邊界、
# SSE 事件邊界都沒有關係。這份測試用 `--_selftest-cuts` 把一份 capture 依位元組位移切段，依序交給
# 與真實串流同一個入口（`StreamCollector.ingest`），重現「切在字中間」「切在事件中間」。
#
# 不打真後端、不讀 auth：每一則都帶 `--_selftest-stream`（契約 §7）。
#
# 突變紀錄（2026-10-12，在本檔 24 則上手動跑過；括號是轉紅的測試編號，日後增刪測試會對不上）：
#   1. ingest 改回「解不開的 chunk 整塊丟掉」（1 2 3 4 5 8 9 10 11 12 13 14）。
#   2. 拿掉 `complete()` 裡 `finishStream()` 的呼叫（7 12 13 14 15 19）。13 是逐位元組重播：它先斷言基準
#      成功，少了 flush 時 trailing capture 的基準失敗，由那道斷言抓到。
#   3. 拿掉 `complete()` 的 `error == nil`，有傳輸錯誤也 flush（18）。
#   4. 拿掉 `finishStream()` 開頭的 `streamError == nil`（16 17）。
#   5. `finishStream()` 改成嚴格解碼 `String(data:encoding:) ?? ""`（12）。
#   拿掉 `complete()` 的 `statusCode == 200`：沒有一則轉紅，這是預期的——非 200 時資料不進 buffer，那道條件是
#   縱深防禦。verify 第 1 輪時 `finishStream()` 另有一次 drain() 與第二道條件，那段多餘，已刪除。

bats_require_minimum_version 1.5.0

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] \
    || skip "needs macOS + Xcode CLT swift (codex-call is a #!/usr/bin/swift script)"
  T="$BATS_TEST_TMPDIR"
  export HOME_ORIG="$HOME"
  export HOME="$T/home"; mkdir -p "$HOME"
  printf '%s\n' '{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}' >"$T/schema.json"
}

teardown() {
  export HOME="$HOME_ORIG"
}

# 用 python3 組 capture（位元組層），並印出指定標記在檔內的位元組位移。
# 用法：capture <out> <kind>；kind 決定內容，stdout 是 JSON：{"name": offset, ...}
capture() {
  python3 - "$1" "$2" <<'PY'
import json, sys
out, kind = sys.argv[1], sys.argv[2]

def ev(obj, end=b"\n\n"):
    return b"event: x\ndata: " + json.dumps(obj, ensure_ascii=False).encode("utf-8") + end

def delta(s):
    return {"type": "response.output_text.delta", "delta": s}

def completed(text):
    return {"type": "response.completed",
            "response": {"status": "completed",
                         "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}}

A, B = "第一段：今天天氣很好，", "第二段：我們去公園散步。"
marks = {}
if kind == "plain":
    parts = [ev(delta(A)), ev(delta(B)), ev(completed(A + B))]
elif kind == "structured":
    D = ['{"answer":"', "今天天氣很好", "，我們去公園散步", '"}']
    parts = [ev(delta(d)) for d in D] + [ev(completed("".join(D)))]
elif kind == "trailing":
    D = ['{"answer":"', "最後一個事件沒有結尾的空行", '"}']
    parts = [ev(delta(d)) for d in D] + [ev(completed("".join(D)), end=b"")]
elif kind == "two-errors":
    parts = [ev({"type": "error", "error": {"message": "first error"}}),
             ev({"type": "error", "error": {"message": "second error"}}, end=b"")]
elif kind == "two-errors-closed":
    # 兩個都有結尾空行：drain() 處理完第一個就停，第二個是 buffer 裡完整的事件
    parts = [ev({"type": "error", "error": {"message": "first error"}}),
             ev({"type": "error", "error": {"message": "second error"}})]
elif kind == "trailing-error":
    # issue #28 第 2 點的情境：之前沒有錯誤，最後一個 error 事件沒有結尾空行
    parts = [ev(delta(A)), ev({"type": "error", "error": {"message": "backend error at the end"}}, end=b"")]
elif kind == "broken-byte":
    good = ev(delta("前面的字"))
    bad = b'event: x\ndata: {"type":"response.output_text.delta","delta":"\xff\xfe"}\n\n'
    parts = [good, bad, ev(delta("後面的字")), ev(completed("前面的字後面的字"))]
elif kind == "truncated-cjk":
    # 一個 3 位元組中文字只剩前 2 個位元組：是「一段」不合法序列，只換成 1 個 U+FFFD（不是 2 個）
    bad = b'event: x\ndata: {"type":"response.output_text.delta","delta":"\xe4\xb8"}\n\n'
    parts = [ev(delta("前面的字")), bad, ev(delta("後面的字"))]
elif kind == "stray-continuation":
    # 兩個沒有起始位元組的延續位元組：各自一段，換成兩個 U+FFFD（不會合併成一個）
    bad = b'event: x\ndata: {"type":"response.output_text.delta","delta":"\x80\x80"}\n\n'
    parts = [ev(delta("前面的字")), bad, ev(delta("後面的字"))]
elif kind == "trailing-broken":
    # 最後一個事件沒有結尾空行，而且含壞位元組：走 finishStream() 的 lossy 解碼
    bad = b'event: x\ndata: {"type":"response.output_text.delta","delta":"\xe5\xbe\x8c\xff\xe9\x9d\xa2"}'
    parts = [ev(delta("前面的字")), bad]
else:
    sys.exit("unknown kind")
data = b"".join(parts)
open(out, "wb").write(data)

starts, pos = [], 0
for p in parts:
    starts.append(pos)
    pos += len(p)

def mid_cjk(part_index):
    """該事件裡第一個中文字的第 2 個位元組：切在這裡就是切在字中間。"""
    p = parts[part_index]
    i = next(i for i, b in enumerate(p) if b >= 0xE0)
    return starts[part_index] + i + 1

marks["size"] = len(data)
if kind == "plain":
    marks["mid_ev2"] = mid_cjk(1)
    marks["mid_completed"] = mid_cjk(2)
elif kind == "structured":
    marks["end_ev1"] = starts[1]
    marks["mid_ev2"] = mid_cjk(1)
    marks["end_ev2"] = starts[2]
    marks["mid_completed"] = mid_cjk(4)
print(json.dumps(marks))
PY
}
mark() { python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2"; }

stream() { "$BIN" --output "$T/out.md" --_selftest-stream "$@"; }

@test "framing: a cut inside a CJK character keeps the whole text" {
  m=$(capture "$T/c.sse" plain)
  run stream "$T/c.sse" --_selftest-cuts "$(mark "$m" mid_ev2)" -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "第一段：今天天氣很好，第二段：我們去公園散步。" ]
}

@test "framing: a cut inside the CJK text of response.completed still completes a --json-schema call" {
  m=$(capture "$T/c.sse" structured)
  run stream "$T/c.sse" --json-schema "$T/schema.json" --_selftest-cuts "$(mark "$m" mid_completed)" -- hi
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["answer"])' "$T/out.md")" = "今天天氣很好，我們去公園散步" ]
}

@test "framing: a structured answer is not silently truncated when a delta is cut mid-character" {
  # 切在事件邊界、字中間、事件邊界：舊的分幀會整塊丟掉第二個 delta，剩下的仍是合法 JSON 而被接受
  m=$(capture "$T/c.sse" structured)
  run stream "$T/c.sse" --json-schema "$T/schema.json" \
    --_selftest-cuts "$(mark "$m" end_ev1),$(mark "$m" mid_ev2),$(mark "$m" end_ev2)" -- hi
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["answer"])' "$T/out.md")" = "今天天氣很好，我們去公園散步" ]
}

@test "framing: every single cut position gives the same result as no cut (in-process sweep)" {
  capture "$T/c.sse" plain >/dev/null
  run stream "$T/c.sse" --_selftest-cuts all -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "第一段：今天天氣很好，第二段：我們去公園散步。" ]
}

@test "framing: the structured capture survives every single cut position too" {
  capture "$T/c.sse" structured >/dev/null
  run stream "$T/c.sse" --json-schema "$T/schema.json" --_selftest-cuts all -- hi
  [ "$status" -eq 0 ]
}

@test "framing: several events delivered in one chunk are all processed" {
  capture "$T/c.sse" plain >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "第一段：今天天氣很好，第二段：我們去公園散步。" ]
}

@test "framing: the last event without a trailing blank line is still processed" {
  capture "$T/c.sse" trailing >/dev/null
  run stream "$T/c.sse" --json-schema "$T/schema.json" -- hi
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["answer"])' "$T/out.md")" = "最後一個事件沒有結尾的空行" ]
}

@test "framing: two independently invalid bytes become two U+FFFD; the rest of the chunk survives" {
  # \xff、\xfe 各自就是一段不合法序列 → 兩個 U+FFFD。斷言確切輸出：glob 的 * 會讓「整個事件被丟掉」也過關
  capture "$T/c.sse" broken-byte >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "$(printf '前面的字\xef\xbf\xbd\xef\xbf\xbd後面的字')" ]
}

@test "framing: the broken-byte capture survives every single cut position" {
  capture "$T/c.sse" broken-byte >/dev/null
  run stream "$T/c.sse" --_selftest-cuts all -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "$(printf '前面的字\xef\xbf\xbd\xef\xbf\xbd後面的字')" ]
}

@test "framing: a truncated CJK character becomes ONE U+FFFD (a truncated prefix counts once)" {
  # 繁中輸出最常見的壞資料：一個字被截斷。兩個位元組只換成一個 U+FFFD
  capture "$T/c.sse" truncated-cjk >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "$(printf '前面的字\xef\xbf\xbd後面的字')" ]
}

@test "framing: stray continuation bytes are NOT merged — two bytes, two U+FFFD" {
  # 只有「合法起始位元組後被截斷的前綴」合成一個；其餘每個不合法的位元組各一個
  capture "$T/c.sse" stray-continuation >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "$(printf '前面的字\xef\xbf\xbd\xef\xbf\xbd後面的字')" ]
}

@test "framing: a broken byte in the unterminated last event is decoded lossily too, not dropped" {
  # finishStream() 那條解碼路徑：改成嚴格解碼（解不開就整段丟）時，這則會轉紅
  capture "$T/c.sse" trailing-broken >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -eq 0 ]
  [ "$(cat "$T/out.md")" = "$(printf '前面的字後\xef\xbf\xbd面')" ]
}

@test "framing: replaying byte by byte (a cut at every offset at once) gives the uncut result" {
  # 窮舉單一切點只切成兩段；這一則把每個位元組都切開，六份 capture 各比一次。
  # two-errors-closed 不在這裡：逐位元組送達時勝出的錯誤會變（#100 的 early bail），那不是分幀的問題
  # 這一則是相對比對（切與不切的結果相同），所以先斷言基準本身成功、有輸出，才不會兩邊一起失敗而空過。
  for spec in "plain:" "trailing:--json-schema" "broken-byte:" "truncated-cjk:" "stray-continuation:" "trailing-broken:"; do
    kind=${spec%%:*}; extra=${spec#*:}
    m=$(capture "$T/c.sse" "$kind")
    every=$(python3 -c 'import sys; print(",".join(str(i) for i in range(1, int(sys.argv[1]))))' "$(mark "$m" size)")
    run stream "$T/c.sse" ${extra:+$extra "$T/schema.json"} -- hi
    [ "$status" -eq 0 ]
    [ -s "$T/out.md" ]
    base_status=$status; base_out=$(cat "$T/out.md"); rm -f "$T/out.md"
    run stream "$T/c.sse" ${extra:+$extra "$T/schema.json"} --_selftest-cuts "$every" -- hi
    [ "$status" -eq "$base_status" ]
    [ -s "$T/out.md" ]
    [ "$(cat "$T/out.md")" = "$base_out" ]
    rm -f "$T/out.md"
  done
}

@test "framing: the unterminated-last-event capture survives every single cut position" {
  # 走 finishStream() flush 的那份 capture 也要窮舉：切點落在沒有結尾的最後一個事件裡
  capture "$T/c.sse" trailing >/dev/null
  run stream "$T/c.sse" --json-schema "$T/schema.json" --_selftest-cuts all -- hi
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["answer"])' "$T/out.md")" = "最後一個事件沒有結尾的空行" ]
}

@test "framing: a lone error event without a trailing blank line fails the call with its message" {
  # issue #28 第 2 點本身的情境：以前少一段、exit 0；現在要回報後端的訊息並失敗
  capture "$T/c.sse" trailing-error >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"backend error at the end"* ]]
}

@test "finishStream guard: with an error already recorded, an unterminated trailing error is not processed" {
  # 釘的是 finishStream() 的「還沒有錯誤」條件：已有錯誤時，不處理沒有結尾的殘留事件。
  # 不規定多個終端事件誰勝出（#100）；第二個 error 沒有結尾空行，所以不論怎麼切都不會在收尾前完整。
  capture "$T/c.sse" two-errors >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"first error"* ]]
  [[ "$output" != *"second error"* ]]
}

@test "single-chunk delivery: finishStream does not process a complete error the bail left in the buffer" {
  # 兩個 error 都有結尾空行、同一個 chunk：drain() 停在第一個，第二個留在 buffer。
  # finishStream() 開頭那道「還沒有錯誤」的條件擋住它；拿掉那道條件，回報的會變成第二個。
  #
  # 這一則只釘那道條件，**不**規定多個終端事件誰勝出。同一份 capture 逐位元組送達時，
  # 第二個 error 會落在另一次 callback、照樣被處理而勝出——bail 只停在一次 callback 之內（#100）。
  # 所以這裡的「first error」只在「同一個 chunk 送達」的前提下成立。#100 定下政策時要重新定基準。
  capture "$T/c.sse" two-errors-closed >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"first error"* ]]
  [[ "$output" != *"second error"* ]]
}

@test "--_selftest-end timeout: a residual error event does not replace the timeout" {
  # 有傳輸錯誤時不 flush：殘留的 error 事件若先被處理，會蓋掉逾時的分類
  capture "$T/c.sse" trailing-error >/dev/null
  run stream "$T/c.sse" --_selftest-end timeout -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"timed out"* ]]
  [[ "$output" != *"backend error at the end"* ]]
}

@test "--_selftest-end clean: same as no flag" {
  capture "$T/c.sse" trailing-error >/dev/null
  run stream "$T/c.sse" -- hi
  base_status=$status; base_output=$output
  run stream "$T/c.sse" --_selftest-end clean -- hi
  [ "$status" -eq "$base_status" ]
  [ "$output" = "$base_output" ]
  [[ "$output" == *"backend error at the end"* ]]
}

@test "--_selftest-end: requires --_selftest-stream" {
  run "$BIN" --output "$T/out.md" --_selftest-end timeout -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"--_selftest-end requires --_selftest-stream"* ]]
}

@test "--_selftest-end: unknown values are refused" {
  capture "$T/c.sse" plain >/dev/null
  for bad in "" "Timeout" "error" "timeout,clean"; do
    run stream "$T/c.sse" --_selftest-end "$bad" -- hi
    [ "$status" -ne 0 ]
    [[ "$output" == *"--_selftest-end"* ]]
  done
}

@test "--_selftest-cuts: requires --_selftest-stream" {
  run "$BIN" --output "$T/out.md" --_selftest-cuts 3 -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"--_selftest-cuts requires --_selftest-stream"* ]]
}

@test "--_selftest-cuts: malformed lists are refused, never clamped" {
  capture "$T/c.sse" plain >/dev/null
  for bad in "abc" "5,,7" "7,5" "5,5" "0" "-1" "999999"; do
    run stream "$T/c.sse" --_selftest-cuts "$bad" -- hi
    [ "$status" -ne 0 ]
    [[ "$output" == *"--_selftest-cuts"* ]]
  done
}

@test "--_selftest-cuts / --_selftest-end: not listed in --help" {
  run "$BIN" --help
  [[ "$output" != *"_selftest-cuts"* ]]
  [[ "$output" != *"_selftest-end"* ]]
}
