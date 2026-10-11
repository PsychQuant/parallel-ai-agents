#!/usr/bin/env bats
# codex-call 的 SSE 分幀（#28）：`didReceive` 依 TCP 的可得量交付 Data，切點與 UTF-8 字元邊界、
# SSE 事件邊界都沒有關係。這份測試用 `--_selftest-cuts` 把一份 capture 依位元組位移切段，依序交給
# 與真實串流同一個入口（`StreamCollector.ingest`），重現「切在字中間」「切在事件中間」。
#
# 不打真後端、不讀 auth：每一則都帶 `--_selftest-stream`（契約 §7）。
#
# 突變紀錄（2026-10-12，實作時手動跑過；改回去之後這幾則轉紅）：
#   1. ingest 改回逐 chunk `String(data:encoding:)` 解碼 → 字中間切一刀、completed 裡切一刀、
#      結構化路徑的靜默截斷、窮舉切點，這四則轉紅。
#   2. 拿掉 `finishStream()` 的呼叫 → 「最後一個事件沒有結尾的空行」轉紅。
#   3. 拿掉 finishStream 裡 `streamError == nil` 的條件 → 「已有錯誤時不處理殘留的錯誤事件」轉紅。

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
elif kind == "broken-byte":
    good = ev(delta("前面的字"))
    bad = b'event: x\ndata: {"type":"response.output_text.delta","delta":"\xff\xfe"}\n\n'
    parts = [good, bad, ev(delta("後面的字")), ev(completed("前面的字後面的字"))]
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

@test "framing: a broken byte costs one character, not the whole chunk" {
  capture "$T/c.sse" broken-byte >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -eq 0 ]
  [[ "$(cat "$T/out.md")" == 前面的字*後面的字 ]]
}

@test "policy unchanged: with an error already recorded, a trailing error event is not processed" {
  # 終端事件政策（誰勝出）不在 #28 的範圍：flush 只在還沒有錯誤時做，回報的仍是第一個錯誤
  capture "$T/c.sse" two-errors >/dev/null
  run stream "$T/c.sse" -- hi
  [ "$status" -ne 0 ]
  [[ "$output" == *"first error"* ]]
  [[ "$output" != *"second error"* ]]
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

@test "--_selftest-cuts: is not listed in --help" {
  run "$BIN" --help
  [[ "$output" != *"_selftest-cuts"* ]]
}
