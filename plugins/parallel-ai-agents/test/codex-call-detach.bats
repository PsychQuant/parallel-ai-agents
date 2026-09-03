#!/usr/bin/env bats
# codex-call 背景模式（--detach / --poll / --abort）的行為測試（#37 換設計）。
#
# 這一層取代被退役的 test/pai-codex-review.bats。round 2 verify 證明 bash helper
# 累積的六個機制各自帶 race；現在 worker 是單一 Swift 程序、生存靠 fcntl record
# lock、身分靠 F_GETLK 的 l_pid、poll 只收 run id 不收路徑。
#
# CODEX_URL 寫死無法注入 mock server，所以用隱藏的 --_selftest-* 旗標：走**同一條**
# detach / lock / status / poll / abort 路徑，只把 streamCodex 換成 sleep + 寫檔。
#
# macOS-only（codex-call 是 #!/usr/bin/swift）——guard 沿用 codex-call-error-extract.bats。
# CI 的 macos-swift-bats job glob 是 test/codex-call-*.bats，本檔會被納入。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/codex-call"
  [ "$(uname)" = "Darwin" ] && [ -x /usr/bin/swift ] \
    || skip "needs macOS + Xcode CLT swift (codex-call is a #!/usr/bin/swift script)"
  TMP="$(mktemp -d)"
  export HOME_ORIG="$HOME"
  # 隔離 base：contract §3 說 base 在 $HOME 之下，測試用假 HOME 免得污染真的
  export HOME="$TMP/home"; mkdir -p "$HOME"
  BASE="$HOME/.cache/codex-call/runs"
}

teardown() {
  # 清掉本測試留下的 worker —— 走契約的 --abort，不用 pkill -f 盲殺
  # （`pkill -f _worker` 會殺到任何 argv 含 _worker 的無關程序）。
  for d in "$BASE"/*/; do
    [ -d "$d" ] || continue
    "$BIN" --abort "$(basename "$d")" >/dev/null 2>&1 || true
  done
  export HOME="$HOME_ORIG"
  rm -rf "$TMP"
}

wait_terminal() {  # $1=id → 設 POLL_OUT / POLL_RC
  for _ in $(seq 1 60); do
    # `X=$(cmd)` 會把 cmd 的 exit code 帶出來，bats 的 errexit 在 FAILED(2) 時會炸掉本函式。
    # 用 && / || 把 exit code 收進變數，不讓它逃逸。
    if POLL_OUT=$("$BIN" --poll "$1" 2>/dev/null); then POLL_RC=0; else POLL_RC=$?; fi
    [ "$POLL_OUT" = "RUNNING" ] || return 0
    sleep 0.25
  done
  return 1
}

@test "detach 立即返回並印出 32 字元 run id" {
  # worker sleep 30：若 detach 被阻塞到 worker 結束，elapsed ≥ 30；正常只有 swift cold
  # start（~1.5 s，機器忙時數秒）。門檻 15 與 30 之間留足夠空隙，不跟 CPU 競爭賭 timing。
  S=$(date +%s)
  run "$BIN" --detach --_selftest-sleep 30 --instructions i "prompt"
  E=$(date +%s)
  [ "$status" -eq 0 ]
  [[ "$output" =~ ^[A-Za-z0-9]{32}$ ]]
  [ $((E - S)) -lt 15 ]
  [ -d "$BASE/$output" ]
  "$BIN" --abort "$output" >/dev/null 2>&1 || true
}

@test "poll：RUNNING → DONE <path>，輸出在 <base>/<id>.out.md，run 目錄已清" {
  # sleep 5：第一次 poll 自己的 swift 啟動就要 ~1.5 s，worker 太短會在 poll 前結束
  run "$BIN" --detach --_selftest-sleep 5 --instructions i "prompt"
  id="$output"
  run "$BIN" --poll "$id"; [ "$status" -eq 0 ]; [ "$output" = "RUNNING" ]
  wait_terminal "$id"
  [ "$POLL_RC" -eq 0 ]
  [[ "$POLL_OUT" == DONE\ * ]]
  out="${POLL_OUT#DONE }"
  [ "$out" = "$BASE/$id.out.md" ]
  grep -q SELFTEST "$out"
  [ ! -d "$BASE/$id" ]
}

@test "--output 給定時 worker 直接寫該路徑，DONE 印出同一路徑" {
  run "$BIN" --detach --output "$TMP/mine.md" --_selftest-sleep 1 --instructions i "prompt"
  id="$output"
  wait_terminal "$id"
  [ "$POLL_OUT" = "DONE $TMP/mine.md" ]
  grep -q SELFTEST "$TMP/mine.md"
}

@test "abort 殺掉持鎖的 worker，run 目錄已清，程序不存在" {
  run "$BIN" --detach --_selftest-sleep 60 --instructions i "prompt"
  id="$output"
  sleep 1
  pgrep -f -- "--_worker $id" >/dev/null      # worker 存活
  run "$BIN" --abort "$id"
  [ "$status" -eq 0 ]; [ "$output" = "ABORTED" ]
  sleep 1
  ! pgrep -f -- "--_worker $id" >/dev/null    # 已死，無 orphan
  [ ! -d "$BASE/$id" ]
}

@test "worker 失敗 → FAILED <reason>、exit 2、run 已清" {
  run "$BIN" --detach --_selftest-sleep 1 --_selftest-fail --instructions i "prompt"
  id="$output"
  wait_terminal "$id"
  [ "$POLL_RC" -eq 2 ]
  [[ "$POLL_OUT" == FAILED* ]]
  [ ! -d "$BASE/$id" ]
}

@test "status 缺失 → FAILED（fail-closed），不得回 DONE" {
  run "$BIN" --detach --_selftest-sleep 1 --instructions i "prompt"
  id="$output"
  wait_terminal "$id" >/dev/null || true
  # 重建一個「worker 已結束、但 status 不存在」的 run：手動製造
  mkdir -p "$BASE/$id"
  printf '{"output":"%s","max_time":30,"started_at":%s}\n' "$BASE/$id.out.md" "$(date +%s)" > "$BASE/$id/meta.json"
  printf 'x\n' > "$BASE/$id.out.md"
  run "$BIN" --poll "$id"
  [ "$status" -eq 2 ]
  [[ "$output" == FAILED* ]]
}

@test "poll 端兜底：持鎖超過 max-time + grace → TIMEOUT exit 3，持鎖者被殺" {
  run "$BIN" --detach --max-time 1 --_selftest-grace 1 --_selftest-sleep 60 --instructions i "prompt"
  id="$output"
  sleep 3
  run "$BIN" --poll "$id"
  [ "$status" -eq 3 ]; [ "$output" = "TIMEOUT" ]
  sleep 1
  ! pgrep -f -- "--_worker $id" >/dev/null
  [ ! -d "$BASE/$id" ]
}

@test "偽造 id：格式錯 / 不存在 / 路徑 → exit 1，且不對任何程序發訊號" {
  sleep 40 & victim=$!
  run "$BIN" --poll "abc";                                    [ "$status" -eq 1 ]
  run "$BIN" --poll "$(printf 'a%.0s' $(seq 1 32))";          [ "$status" -eq 1 ]   # 合法格式但不存在
  run "$BIN" --poll "../../../../tmp/x";                      [ "$status" -eq 1 ]
  run "$BIN" --abort "/tmp/x";                                [ "$status" -eq 1 ]
  kill -0 "$victim"                                           # 無關程序仍活
  kill -9 "$victim" 2>/dev/null || true
}

@test "偽造 run 目錄（無人持鎖）→ 讀不到 status → FAILED，不殺任何程序" {
  sleep 40 & victim=$!
  fid="$(printf 'b%.0s' $(seq 1 32))"
  mkdir -p "$BASE/$fid"
  printf '{"output":"/tmp/nope","max_time":30,"started_at":%s}\n' "$(date +%s)" > "$BASE/$fid/meta.json"
  printf '%s\n' "$victim" > "$BASE/$fid/pid"          # 舊設計會讀這個檔 —— 新設計不得
  run "$BIN" --abort "$fid"
  kill -0 "$victim"                                    # victim 必須還活著
  kill -9 "$victim" 2>/dev/null || true
}

@test "兩個 poll 併發於 DONE：恰好一個回 DONE（原子 claim）" {
  run "$BIN" --detach --_selftest-sleep 1 --instructions i "prompt"
  id="$output"
  sleep 3   # 讓 worker 結束但不 poll
  "$BIN" --poll "$id" > "$TMP/p1" 2>/dev/null &
  "$BIN" --poll "$id" > "$TMP/p2" 2>/dev/null &
  wait
  n=$(cat "$TMP/p1" "$TMP/p2" | grep -c '^DONE ')
  [ "$n" -eq 1 ]
}

@test "detach 的參數錯誤同步浮現：空 prompt → exit 非零、不建 run" {
  run "$BIN" --detach --instructions i ""
  [ "$status" -ne 0 ]
  [ -z "$(ls -A "$BASE" 2>/dev/null)" ]
}

@test "既有同步路徑不受影響（--selftest-error-extract 仍可用）" {
  run "$BIN" --selftest-error-extract '{"type":"error","error":{"message":"still works"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"still works"* ]]
}
