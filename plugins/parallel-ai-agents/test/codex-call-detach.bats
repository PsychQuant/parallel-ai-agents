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
  # R3-C1 readiness：detach 返回時 worker 必須已持鎖（lock 檔存在），否則此刻的 poll
  # 會把合法 run 判成 terminal 並清除（實測視窗 0.6–1.0 s）
  [ -f "$BASE/$output/lock" ]
  run "$BIN" --poll "$output"; [ "$status" -eq 0 ]; [ "$output" = "RUNNING" ]
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
  run pgrep -f -- "--_worker $id"; [ "$status" -ne 0 ]   # 已死，無 orphan（`! cmd` 在中段被 errexit 豁免，round 3 regression §5）
  [ ! -d "$BASE/$id" ]
  [ ! -e "$BASE/$id.out.md" ]                 # R3-H8：預設輸出檔一併清除，不留孤兒
}

@test "R3-H8 abort 不動 caller 給的 --output（所有權在 caller）" {
  printf 'CALLER_OWNED\n' > "$TMP/mine.md"
  run "$BIN" --detach --output "$TMP/mine.md" --_selftest-sleep 60 --instructions i "prompt"
  id="$output"
  run "$BIN" --abort "$id"; [ "$status" -eq 0 ]
  [ -f "$TMP/mine.md" ]; grep -q CALLER_OWNED "$TMP/mine.md"
}

@test "R3-H8 FAILED 也清除預設輸出檔" {
  run "$BIN" --detach --_selftest-sleep 1 --_selftest-fail --instructions i "prompt"
  id="$output"
  wait_terminal "$id"; [ "$POLL_RC" -eq 2 ]
  [ ! -e "$BASE/$id.out.md" ]
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
  run pgrep -f -- "--_worker $id"; [ "$status" -ne 0 ]   # 持鎖者真的被殺（round 3 regression §5）
  [ ! -d "$BASE/$id" ]
}

@test "偽造 id：格式錯 / 不存在 / 路徑 → exit 1，且不對任何程序發訊號" {
  sleep 40 & victim=$!
  run "$BIN" --poll "abc";                                    [ "$status" -eq 1 ]
  run "$BIN" --poll "$(printf 'a%.0s' $(seq 1 32))";          [ "$status" -eq 1 ]   # 合法格式但不存在
  run "$BIN" --poll "../../../../tmp/x";                      [ "$status" -eq 1 ]
  run "$BIN" --abort "/tmp/x";                                [ "$status" -eq 1 ]
  # round 3 regression §4：穿越目標必須真的存在，否則 fileExists 就擋下、validRunId 零覆蓋
  mkdir -p "$TMP/outside"; printf 'precious\n' > "$TMP/outside/precious.txt"
  printf '{"output":"/tmp/nope","max_time":30,"started_at":%s}\n' "$(date +%s)" > "$TMP/outside/meta.json"
  run "$BIN" --abort "../../../../outside";                   [ "$status" -eq 1 ]
  [ -f "$TMP/outside/precious.txt" ]                          # 目錄與內容都還在
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
  [ "$status" -eq 0 ]; [ "$output" = "ABORTED" ]     # R3：abort 對無人持鎖的 run 是 no-signal 清除
  [ ! -d "$BASE/$fid" ]
  kill -0 "$victim"                                    # victim 必須還活著
  kill -9 "$victim" 2>/dev/null || true
}

@test "兩個 poll 併發於 DONE：恰好一個回 DONE（原子 claim）" {
  # round 3 regression §6：單輪偵測力約 35%，跑三輪把「原子 claim 被拿掉」的漏檢率壓到 ~4%
  for round in 1 2 3; do
    run "$BIN" --detach --_selftest-sleep 1 --instructions i "prompt"
    id="$output"
    sleep 3   # 讓 worker 結束但不 poll
    "$BIN" --poll "$id" > "$TMP/p1" 2>/dev/null &
    "$BIN" --poll "$id" > "$TMP/p2" 2>/dev/null &
    wait
    n=$(cat "$TMP/p1" "$TMP/p2" | grep -c '^DONE ')
    [ "$n" -eq 1 ]
  done
}

@test "detach 的參數錯誤同步浮現：空 prompt → exit 非零、不建 run" {
  run "$BIN" --detach --instructions i ""
  [ "$status" -ne 0 ]
  [ -z "$(ls -A "$BASE" 2>/dev/null)" ]
}
@test "R3-H5 同步路徑順序不變：缺 --output 時先報 --output is required（不先讀 prompt）" {
  run "$BIN" --model m --effort e "some prompt"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--output is required"* ]]
  # 缺 --output 且 prompt-file 不存在 → 仍是 --output 先報（原順序）
  run "$BIN" --prompt-file "$TMP/does-not-exist"
  [[ "$output" == *"--output is required"* ]]
}

@test "R3-M3 模式互斥：--detach 與 --poll 同時給 → exit 1，不靜默擇一" {
  run "$BIN" --detach --poll "$(printf 'c%.0s' $(seq 1 32))" --instructions i "p"
  [ "$status" -eq 1 ]
  [ -z "$(ls -A "$BASE" 2>/dev/null)" ]
}

@test "R3-M1 worker 啟動失敗 → detach 同步失敗、不印 id、不留 run" {
  # 讓 worker 一定拿不到鎖：預先在 run 目錄放一個被別人持有的 lock？無法預知 id。
  # 改用可控的失敗：把 HOME 指到不可寫的目錄 → hardenBase / ensureDir 同步失敗。
  export HOME="$TMP/ro"; mkdir -p "$HOME"; chmod 500 "$HOME"
  run "$BIN" --detach --_selftest-sleep 1 --instructions i "p"
  chmod 700 "$HOME"
  [ "$status" -ne 0 ]
  [[ ! "$output" =~ ^[A-Za-z0-9]{32}$ ]]
}

@test "R3-H6 base 中間層是 symlink → detach 拒絕" {
  mkdir -p "$TMP/elsewhere"; mkdir -p "$HOME/.cache"
  ln -s "$TMP/elsewhere" "$HOME/.cache/codex-call"
  run "$BIN" --detach --_selftest-sleep 1 --instructions i "p"
  [ "$status" -ne 0 ]
  [[ "$output" == *"symlink"* ]] || [[ "$output" == *"refusing"* ]]
}

@test "R3-Sec-H1 lock 檔被換成指向 victim 持鎖檔的 hard link → abort 拒絕、victim 存活" {
  # victim：一個持有 fcntl 鎖的程序（用 codex-call 自己的 worker 當 victim 最省事）
  run "$BIN" --detach --_selftest-sleep 60 --instructions i "victim"
  vid="$output"; vpid=$(pgrep -f -- "--_worker $vid" | head -1)
  # 攻擊者的 run：偽造目錄，lock 硬連結到 victim 的 lock
  aid="$(printf 'd%.0s' $(seq 1 32))"; mkdir -p "$BASE/$aid"
  printf '{"output":"/tmp/x","max_time":30,"started_at":%s}
' "$(date +%s)" > "$BASE/$aid/meta.json"
  ln "$BASE/$vid/lock" "$BASE/$aid/lock"
  run "$BIN" --abort "$aid"
  kill -0 "$vpid"                                     # victim 必須還活著（st_nlink==2 → 拒絕）
  rm -f "$BASE/$aid/lock"                             # 拆掉硬連結，victim 的 lock 回到 nlink==1
  "$BIN" --abort "$vid" >/dev/null 2>&1 || true
}

@test "R3-Sec-M2 已完成但未 claim 的 run，第二個 --_worker 不得重跑" {
  run "$BIN" --detach --_selftest-sleep 1 --instructions i "p"
  id="$output"; sleep 3                               # 讓 worker 結束、status 已寫、尚未 poll
  before=$(stat -f %m "$BASE/$id/status")
  run "$BIN" --_worker "$id"; [ "$status" -ne 0 ]     # 拒絕
  after=$(stat -f %m "$BASE/$id/status")
  [ "$before" = "$after" ]                            # status 沒被覆寫
  "$BIN" --poll "$id" >/dev/null 2>&1 || true
}

@test "R3-L3 status token：3-auth-error 不得判 TIMEOUT，只有 TIMEOUT token 才是" {
  for s in "3 auth.json missing tokens.access_token/refresh_token" "TIMEOUT Hard timeout after 600s"; do
    xid="$(printf 'g%.0s' $(seq 1 32))"; mkdir -p "$BASE/$xid"
    printf '{"output":"/tmp/nope","max_time":30,"started_at":%s}\n' "$(date +%s)" > "$BASE/$xid/meta.json"
    printf '%s\n' "$s" > "$BASE/$xid/status"
    run "$BIN" --poll "$xid"
    case "$s" in
      TIMEOUT*) [ "$status" -eq 3 ]; [ "$output" = "TIMEOUT" ] ;;
      *)        [ "$status" -eq 2 ]; [[ "$output" == "FAILED 3 auth"* ]] ;;
    esac
  done
}

@test "R3-L4 status 0 但輸出缺失 → FAILED output missing or empty（不是 FAILED 0）" {
  xid="$(printf 'h%.0s' $(seq 1 32))"; mkdir -p "$BASE/$xid"
  printf '{"output":"%s","max_time":30,"started_at":%s}\n' "$TMP/absent.md" "$(date +%s)" > "$BASE/$xid/meta.json"
  printf '0\n' > "$BASE/$xid/status"
  run "$BIN" --poll "$xid"
  [ "$status" -eq 2 ]; [ "$output" = "FAILED output missing or empty" ]
}

@test "R3-Reg7 status 非零但 caller 的輸出檔非空 → FAILED，不得 DONE，檔案不動" {
  xid="$(printf 'i%.0s' $(seq 1 32))"; mkdir -p "$BASE/$xid"
  printf 'old but non-empty\n' > "$TMP/prev.md"
  printf '{"output":"%s","max_time":30,"started_at":%s}\n' "$TMP/prev.md" "$(date +%s)" > "$BASE/$xid/meta.json"
  printf '9 boom\n' > "$BASE/$xid/status"
  run "$BIN" --poll "$xid"
  [ "$status" -eq 2 ]; [[ "$output" == "FAILED 9 boom"* ]]
  [ -f "$TMP/prev.md" ]
}

@test "R3-Reg8 持鎖中 meta 損毀 → fail-closed：TIMEOUT exit 3、worker 被殺、run 已清" {
  run "$BIN" --detach --_selftest-sleep 60 --instructions i "p"
  id="$output"
  printf 'garbage\n' > "$BASE/$id/meta.json"
  run "$BIN" --poll "$id"
  [ "$status" -eq 3 ]; [ "$output" = "TIMEOUT" ]
  sleep 1
  run pgrep -f -- "--_worker $id"; [ "$status" -ne 0 ]
  [ ! -d "$BASE/$id" ]
}

@test "R3-L7 --detach 的 --max-time 必須是正整數：0 / abc / -5 → exit 非零、不建 run" {
  run "$BIN" --detach --max-time 0 --instructions i "p";    [ "$status" -ne 0 ]
  run "$BIN" --detach --max-time abc --instructions i "p";  [ "$status" -ne 0 ]
  run "$BIN" --detach --max-time -5 --instructions i "p";   [ "$status" -ne 0 ]
  [ -z "$(ls -A "$BASE" 2>/dev/null)" ]
}

@test "R3-L9 --_selftest-grace 沒有 --_selftest-sleep 時拒絕（不得改寫 production 兜底）" {
  run "$BIN" --detach --_selftest-grace 1 --instructions i "p"
  [ "$status" -ne 0 ]
  [ -z "$(ls -A "$BASE" 2>/dev/null)" ]
}

@test "R3-M5 abort 清不掉 run 目錄 → FAILED exit 2，不得印 ABORTED" {
  fid="$(printf 'e%.0s' $(seq 1 32))"; mkdir -p "$BASE/$fid"
  printf '{"output":"/tmp/nope","max_time":30,"started_at":%s}\n' "$(date +%s)" > "$BASE/$fid/meta.json"
  chmod 500 "$BASE"
  run "$BIN" --abort "$fid"
  chmod 700 "$BASE"
  # bats 的 run 把 stderr 併進 $output：stderr 的 warning 行在前、stdout 的 FAILED 在後 → 比子字串
  [ "$status" -eq 2 ]; [[ "$output" == *"FAILED could not remove run dir"* ]]; [[ "$output" != *ABORTED* ]]
  [ -d "$BASE/$fid" ]
}

@test "R3-L10 stale .done（>60 s）被接手完成；新鮮的 .done 視為併發 claim → exit 1" {
  sid="$(printf 'f%.0s' $(seq 1 32))"; mkdir -p "$BASE/$sid.done"
  printf 'x\n' > "$TMP/stale.out"
  printf '{"output":"%s","max_time":30,"started_at":%s}\n' "$TMP/stale.out" "$(date +%s)" > "$BASE/$sid.done/meta.json"
  printf '0\n' > "$BASE/$sid.done/status"
  touch -t 202001010000 "$BASE/$sid.done"
  run "$BIN" --poll "$sid"
  [ "$status" -eq 0 ]; [ "$output" = "DONE $TMP/stale.out" ]
  [ ! -d "$BASE/$sid.done" ]
  mkdir -p "$BASE/$sid.done"
  run "$BIN" --poll "$sid"
  [ "$status" -eq 1 ]; [[ "$output" == *concurrent* ]]
}

@test "R4-B1 瞬間完成的 worker（--_selftest-sleep 0）：detach 必須成功、poll 回 DONE（DA 鏡射 race，六連跑）" {
  for i in 1 2 3 4 5 6; do
    run "$BIN" --detach --_selftest-sleep 0 --instructions i "p"
    [ "$status" -eq 0 ]; [[ "$output" =~ ^[A-Za-z0-9]{32}$ ]]
    id="$output"
    wait_terminal "$id"
    [ "$POLL_RC" -eq 0 ]; [[ "$POLL_OUT" == DONE\ * ]]
  done
}

@test "R4-X2 FAILED 時 stderr 附 worker.log 尾段（診斷不隨 run 一起消失）" {
  run "$BIN" --detach --_selftest-sleep 1 --_selftest-fail --instructions i "p"
  id="$output"
  sleep 3
  run "$BIN" --poll "$id"
  [ "$status" -eq 2 ]
  [[ "$output" == *"worker.log tail"* ]]
  [[ "$output" == *"worker finished: 9"* ]]
}

@test "R4-GC detach 回收 >24h 且無人持鎖的 run／.done／.out.md，保留新鮮的與持鎖中的" {
  mkdir -p "$BASE"
  old="$(printf 'j%.0s' $(seq 1 32))"; new="$(printf 'k%.0s' $(seq 1 32))"
  mkdir -p "$BASE/$old" "$BASE/$old.done" "$BASE/$new"; printf 'x\n' > "$BASE/$old.out.md"; printf 'x\n' > "$BASE/$new.out.md"
  touch -t 202001010000 "$BASE/$old" "$BASE/$old.done" "$BASE/$old.out.md"
  mkdir -p "$BASE/not-a-run"; touch -t 202001010000 "$BASE/not-a-run"
  run "$BIN" --detach --_selftest-sleep 60 --instructions i "live"
  live="$output"
  touch -t 202001010000 "$BASE/$live"                 # 舊 mtime 但持鎖中 → 必須留下
  run "$BIN" --detach --_selftest-sleep 1 --instructions i "p"
  [ "$status" -eq 0 ]
  [ ! -e "$BASE/$old" ]; [ ! -e "$BASE/$old.done" ]; [ ! -e "$BASE/$old.out.md" ]
  [ -d "$BASE/$new" ]; [ -f "$BASE/$new.out.md" ]; [ -d "$BASE/not-a-run" ]; [ -d "$BASE/$live" ]
}

@test "既有同步路徑不受影響（--selftest-error-extract 仍可用）" {
  run "$BIN" --selftest-error-extract '{"type":"error","error":{"message":"still works"}}'
  [ "$status" -eq 0 ]
  [[ "$output" == *"still works"* ]]
}
