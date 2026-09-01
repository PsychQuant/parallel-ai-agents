#!/usr/bin/env bats
# bin/pai-codex-review 的行為測試（#37 follow-up）。
#
# 這一層測的是 ensemble-workflow.test.mjs 測不到的東西：實際的檔案組裝順序、
# 前置驗證、總期限、以及 timeout 時有沒有留下 orphan。2.22.1 的六個 findings
# 裡有四個（變數不存在／orphan／無期限／不驗證）只有在這一層才抓得到 ——
# prompt 字串斷言永遠看不見它們。
#
# 用假的 wrapper 取代 codex-call，全程不發網路。

setup() {
  SCRIPT="${BATS_TEST_DIRNAME}/../bin/pai-codex-review"
  TMP="$(mktemp -d)"

  # 假 wrapper：把 --prompt-file 的內容原樣抄到 --output，可用 FAKE_SLEEP 拖時間
  FAKE="$TMP/fake-codex-call"
  cat > "$FAKE" <<'EOS'
#!/usr/bin/env bash
out=""; pf=""
while [ $# -gt 0 ]; do
  case "$1" in
    --output) out="$2"; shift 2 ;;
    --prompt-file) pf="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "${FAKE_SLEEP:-}" ] && sleep "$FAKE_SLEEP"
[ "${FAKE_FAIL:-}" = "1" ] && exit 9
cat "$pf" > "$out"
EOS
  chmod +x "$FAKE"

  ART="$TMP/artifact.txt"
  printf 'ARTIFACT_BODY_MARKER\n' > "$ART"
}

teardown() { rm -rf "$TMP"; }

@test "-h 印出用法" {
  run "$SCRIPT" -h
  [ "$status" -eq 0 ]
  [[ "$output" == *"pai-codex-review"* ]]
}

@test "第一個參數不是 start/poll/abort → 退出 1" {
  run "$SCRIPT" bogus
  [ "$status" -eq 1 ]
}

@test "finding #6：--artifact 是目錄 → 拒絕" {
  run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 30 \
      --instructions i --artifact "$TMP"
  [ "$status" -eq 1 ]
  [[ "$output" == *"不是一般檔案"* ]]
}

@test "finding #6：--artifact 是 symlink → 拒絕（防 follow-symlink 洩漏）" {
  ln -s "$ART" "$TMP/link.txt"
  run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 30 \
      --instructions i --artifact "$TMP/link.txt"
  [ "$status" -eq 1 ]
  [[ "$output" == *"symlink"* ]]
}

@test "--max-time 非正整數 → 拒絕" {
  run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time abc --instructions i
  [ "$status" -eq 1 ]
}

@test "--wrapper 不可執行 → 拒絕" {
  run "$SCRIPT" start --wrapper "$TMP/nope" --model m --effort e --max-time 30 --instructions i
  [ "$status" -eq 1 ]
}

@test "instructions 在 artifact 之前，且 artifact 內容有進 prompt" {
  run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 30 \
      --instructions "INSTRUCTIONS_MARKER" --artifact "$ART"
  [ "$status" -eq 0 ]
  rundir="$output"

  # 等背景假 wrapper 收工
  for _ in $(seq 1 40); do
    run "$SCRIPT" poll "$rundir"
    [[ "$output" == RUNNING ]] || break
    sleep 0.1
  done
  [[ "$output" == DONE\ * ]]
  result="${output#DONE }"
  [ -f "$result" ]

  grep -q INSTRUCTIONS_MARKER "$result"
  grep -q ARTIFACT_BODY_MARKER "$result"
  # 順序：instructions 必須在 artifact 之前
  ins_line=$(grep -n INSTRUCTIONS_MARKER "$result" | head -1 | cut -d: -f1)
  art_line=$(grep -n ARTIFACT_BODY_MARKER "$result" | head -1 | cut -d: -f1)
  [ "$ins_line" -lt "$art_line" ]
  rm -f "$result" "${result}.log"
}

@test "無 --artifact 時只送 instructions，不因缺檔而失敗" {
  run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 30 \
      --instructions "ONLY_INSTRUCTIONS"
  [ "$status" -eq 0 ]
  rundir="$output"
  for _ in $(seq 1 40); do
    run "$SCRIPT" poll "$rundir"
    [[ "$output" == RUNNING ]] || break
    sleep 0.1
  done
  [[ "$output" == DONE\ * ]]
  result="${output#DONE }"
  grep -q ONLY_INSTRUCTIONS "$result"
  rm -f "$result" "${result}.log"
}

@test "wrapper 失敗（無輸出）→ poll 回 FAILED、退出 2" {
  FAKE_FAIL=1 run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 30 \
      --instructions i --artifact "$ART"
  rundir="$output"
  for _ in $(seq 1 40); do
    run "$SCRIPT" poll "$rundir"
    [[ "$output" == RUNNING ]] || break
    sleep 0.1
  done
  [ "$status" -eq 2 ]
  [[ "$output" == FAILED ]]
}

@test "finding #5 + #4：超過總期限 → TIMEOUT、退出 3，且子程序被 kill（無 orphan）" {
  # max-time 1 → deadline = now + 1 + 30。把 deadline 直接改成過去以免等 31 秒。
  FAKE_SLEEP=60 run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 1 \
      --instructions i --artifact "$ART"
  [ "$status" -eq 0 ]
  rundir="$output"
  pid="$(cat "$rundir/pid")"
  kill -0 "$pid"                     # 起初活著

  printf '0\n' > "$rundir/deadline"  # 強制已逾期
  run "$SCRIPT" poll "$rundir"
  [ "$status" -eq 3 ]
  [[ "$output" == TIMEOUT ]]

  sleep 0.5
  ! kill -0 "$pid" 2>/dev/null       # 子程序已被收掉 —— 無 orphan
  [ ! -d "$rundir" ]                 # RUNDIR 已清
}

@test "abort 會 kill 子程序並清掉 RUNDIR" {
  FAKE_SLEEP=60 run "$SCRIPT" start --wrapper "$FAKE" --model m --effort e --max-time 30 \
      --instructions i --artifact "$ART"
  rundir="$output"
  pid="$(cat "$rundir/pid")"
  run "$SCRIPT" abort "$rundir"
  [ "$status" -eq 0 ]
  [[ "$output" == ABORTED ]]
  sleep 0.5
  ! kill -0 "$pid" 2>/dev/null
  [ ! -d "$rundir" ]
}

@test "poll 一個不存在的 RUNDIR → 退出 1" {
  run "$SCRIPT" poll "$TMP/not-a-rundir"
  [ "$status" -eq 1 ]
}

@test "poll 一個不是本腳本建立的目錄（缺 pid）→ 退出 1" {
  mkdir -p "$TMP/fake-rundir"
  run "$SCRIPT" poll "$TMP/fake-rundir"
  [ "$status" -eq 1 ]
  [[ "$output" == *"缺 pid"* ]]
}
