#!/usr/bin/env bats
# codex-call 的圖片輸入（--image，#87）的 bats 測試。
#
# 不打真後端：CODEX_URL 是 hardcoded 常數、無法注入 mock server。payload 的形狀用隱藏旗標
# `--_selftest-payload` 檢查——它跑完參數解析、prompt 讀取與圖片驗證，印出**將要送出**的
# request body（sortedKeys JSON）後 exit 0，不讀 auth、不發 HTTP（契約 §7）。
#
# **每一則都必須帶 `--_selftest-payload`（或在送出前就被拒絕）**：HOME 只隔離 run base，不隔離
# 憑證——AUTH_FILE 走 passwd db（detach.bats 的 round 4 R4-6 註記）。沒帶鉤子又通過驗證的呼叫會
# 讀到真的 auth.json、真的發 HTTPS。鉤子的位置就在圖片驗證之後、讀 auth 之前，所以「壞圖被拒時
# 沒有印出 payload」同時證明了驗證發生在送出之前。
#
# 測試圖在 setup() 用 sips 現場產生，repo 不收二進位 fixture。

bats_require_minimum_version 1.5.0   # run --separate-stderr：縮圖時 stderr 有一行 log，不能混進 JSON

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  # codex-call 是 `#!/usr/bin/swift` script，sips 是 macOS 內建——兩者都只在 macOS 上有。
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] && command -v sips >/dev/null \
    || skip "needs macOS + Xcode CLT swift + sips (codex-call is a #!/usr/bin/swift script)"
  T="$BATS_TEST_TMPDIR"
  # 1×1 PNG，再用 sips 放大／轉檔出其餘尺寸與格式
  base64 -D <<<'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==' >"$T/dot.png"
  sips -z 40 60 "$T/dot.png" --out "$T/small.png" >/dev/null
  sips -s format jpeg "$T/small.png" --out "$T/small.jpg" >/dev/null
  sips -s format gif "$T/small.png" --out "$T/small.gif" >/dev/null
  sips -z 1000 3000 "$T/dot.png" --out "$T/wide.png" >/dev/null       # 長邊 3000 > 2048 → 要縮
  sips -z 1024 2048 "$T/dot.png" --out "$T/edge.png" >/dev/null       # 長邊恰好 2048 → 不縮
  sips -z 3000 1200 -s format jpeg "$T/dot.png" --out "$T/tall.jpg" >/dev/null
  printf 'just text, not an image\n' >"$T/note.png"                    # 副檔名騙人：判準是檔頭
  printf 'RIFF\000\000\000\000WEBPVP8 ' >"$T/fake.webp"                # 檔頭像 WebP、內容解不開
  { printf '\211PNG\r\n\032\n'; head -c 21000000 /dev/zero; } >"$T/huge.png"   # > 20 MB
  mkdir -p "$T/emptyhome"
}

# payload（JSON）裡的欄位，用 python3 取——macOS 內建，不假設有 jq
pyjson() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }

payload() { "$BIN" --output "$T/out.md" --_selftest-payload "$@"; }

# ── 不帶 --image：payload 形狀不變 ─────────────────────────────────────────────

@test "no --image: input is exactly one user message with one input_text" {
  run payload "hello"
  [ "$status" -eq 0 ]
  run pyjson 'c=d["input"]; assert c==[{"role":"user","content":[{"type":"input_text","text":"hello"}]}], c; print("ok")' <<<"$output"
  [ "$status" -eq 0 ]
}

@test "no --image: top-level keys are the pre-#87 set and nothing else" {
  run payload "hello"
  [ "$status" -eq 0 ]
  run pyjson 'print(",".join(sorted(d)))' <<<"$output"
  [ "$output" = "include,input,instructions,model,parallel_tool_calls,reasoning,store,stream,text,tool_choice" ]
}

@test "no --image: payload hook prints nothing to stdout besides the JSON" {
  run payload "hello"
  [ "$status" -eq 0 ]
  run pyjson 'print(d["stream"], d["store"])' <<<"$output"
  [ "$output" = "True False" ]
}

# ── 帶 --image ────────────────────────────────────────────────────────────────

@test "one PNG: appended after input_text as an input_image data URL" {
  run payload --image "$T/small.png" "what shape"
  [ "$status" -eq 0 ]
  run pyjson 'c=d["input"][0]["content"]; print(len(c), c[0]["type"], c[0]["text"], c[1]["type"], c[1]["image_url"][:22])' <<<"$output"
  [ "$output" = "2 input_text what shape input_image data:image/png;base64," ]
}

@test "one small PNG: bytes are sent unchanged (no re-encoding below the size limit)" {
  run payload --image "$T/small.png" "p"
  [ "$status" -eq 0 ]
  printf '%s' "$output" | pyjson 'import base64; sys.stdout.buffer.write(base64.b64decode(d["input"][0]["content"][1]["image_url"].split(",",1)[1]))' >"$T/sent.png"
  cmp "$T/small.png" "$T/sent.png"
}

@test "several images keep command-line order and their own MIME types" {
  run payload --image "$T/small.png" --image "$T/small.jpg" --image "$T/small.gif" "p"
  [ "$status" -eq 0 ]
  run pyjson 'c=d["input"][0]["content"]; print(" ".join(x["image_url"].split(";")[0] for x in c[1:]))' <<<"$output"
  [ "$output" = "data:image/png data:image/jpeg data:image/gif" ]
}

@test "--image may come after the PROMPT" {
  run payload "p" --image "$T/small.png"
  [ "$status" -eq 0 ]
  run pyjson 'print(len(d["input"][0]["content"]))' <<<"$output"
  [ "$output" = "2" ]
}

@test "long side over 2048 px: downscaled so the long side is exactly 2048" {
  run --separate-stderr payload --image "$T/wide.png" "p"
  [ "$status" -eq 0 ]
  printf '%s' "$output" | pyjson 'import base64; sys.stdout.buffer.write(base64.b64decode(d["input"][0]["content"][1]["image_url"].split(",",1)[1]))' >"$T/sent.png"
  run sips -g pixelWidth -g pixelHeight "$T/sent.png"
  [[ "$output" == *"pixelWidth: 2048"* ]]
  [[ "$output" == *"pixelHeight: 68"[23]* ]]    # 3000×1000 → 2048×683（四捨五入可差 1）
}

@test "downscaling reports the old and new size on stderr" {
  run --separate-stderr payload --image "$T/wide.png" "p"
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"3000x1000"* ]]
  [[ "$stderr" == *"2048x"* ]]
}

@test "downscaled JPEG stays JPEG" {
  run --separate-stderr payload --image "$T/tall.jpg" "p"
  [ "$status" -eq 0 ]
  run pyjson 'print(d["input"][0]["content"][1]["image_url"][:23])' <<<"$output"
  [ "$output" = "data:image/jpeg;base64," ]
}

@test "long side exactly 2048 px: not re-encoded" {
  run payload --image "$T/edge.png" "p"
  [ "$status" -eq 0 ]
  printf '%s' "$output" | pyjson 'import base64; sys.stdout.buffer.write(base64.b64decode(d["input"][0]["content"][1]["image_url"].split(",",1)[1]))' >"$T/sent.png"
  cmp "$T/edge.png" "$T/sent.png"
}

# ── 驗證失敗：fail-fast、在 auth 之前 ────────────────────────────────────────

@test "file over 20 MB is refused and names the limit" {
  run payload --image "$T/huge.png" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"huge.png"* ]]
  [[ "$output" == *"20 MB"* ]]
  [[ "$output" != *"input_image"* ]]
}

@test "text file with an image extension is refused by its header" {
  run payload --image "$T/note.png" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"note.png"* ]]
  [[ "$output" == *"not a PNG, JPEG, WebP or GIF"* ]]
}

@test "missing file is refused" {
  run payload --image "$T/nope.png" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"nope.png"* ]]
  [[ "$output" == *"cannot read"* ]]
}

@test "directory is refused" {
  run payload --image "$T" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"cannot read"* ]]
}

@test "image header that does not decode is refused" {
  run payload --image "$T/fake.webp" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"fake.webp"* ]]
  [[ "$output" == *"cannot decode"* ]]
}

@test "one bad image among good ones refuses the whole call" {
  run payload --image "$T/small.png" --image "$T/note.png" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"note.png: not a PNG, JPEG, WebP or GIF"* ]]
  [[ "$output" != *"input_image"* ]]
}

@test "--image without a value is refused" {
  run "$BIN" --output "$T/out.md" --_selftest-payload "p" --image
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing value for --image"* ]]
}

# ── 與背景模式的關係 ──────────────────────────────────────────────────────────

@test "--image with --detach is refused before any run is created" {
  run env HOME="$T/emptyhome" "$BIN" --detach --_selftest-sleep 1 --output "$T/out.md" --image "$T/small.png" "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--image"* ]]
  [[ "$output" == *"--detach"* ]]
  [ ! -d "$T/emptyhome/.cache/codex-call/runs" ] || [ -z "$(ls -A "$T/emptyhome/.cache/codex-call/runs")" ]
}

@test "--_selftest-payload with --detach is refused" {
  run env HOME="$T/emptyhome" "$BIN" --detach --_selftest-sleep 1 --output "$T/out.md" --_selftest-payload "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--_selftest-payload"* ]]
}

# ── --help ───────────────────────────────────────────────────────────────────

@test "--help lists --image (downstream capability probe)" {
  run "$BIN" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"--image FILE"* ]]
}
