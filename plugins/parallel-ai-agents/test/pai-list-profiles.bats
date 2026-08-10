#!/usr/bin/env bats
#
# `bin/pai-list-profiles` 是 PROFILES 的**唯一真源查詢入口**，卻在 #33 出貨時零測試覆蓋
# （#33 verify R6 MEDIUM）。它有兩個脆弱點值得錨住：
#
#   1. 它靠 harness 裡一行**註解分隔線**（`// ── Orchestration ──`）切出 PROFILES 那段。
#      那行是註解 —— 沒有任何東西阻止未來有人改寫或移除它，而它一壞，抽取就壞。
#   2. `plugins/pai-lenses/scripts/validate.py` 的 profile 名稱閘門現在**依賴它**：
#      工具不見或輸出為空都會讓那道閘門報錯（R6 之前是靜默蒸發）。
#
# 所以這裡錨的不只是「它會動」，而是「它答得對」——特別是 `custom`：
# `references/builtin-lenses.csv` 是**由 lens 產生**的投影，`lenses: []` 的 profile
# 在裡面一列都沒有，拿投影問存在性對 `custom` 必定答錯。這正是這支工具存在的理由。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-list-profiles"
  HARNESS="${BATS_TEST_DIRNAME}/../workflows/ensemble-workflow.js"
}

@test "印出 PROFILES 的 key，一行一個" {
  run bash "$BIN"
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  # 每一行都必須是合法的 identifier（抽取壞掉時常見的症狀是吐出整段 JS）
  while IFS= read -r line; do
    [[ "$line" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]
  done <<< "$output"
}

@test "涵蓋 custom —— 那是 builtin-lenses.csv 投影答不出來的那一個" {
  run bash "$BIN"
  [ "$status" -eq 0 ]
  # **整行**精確比對，不是子字串。先前寫 `[[ "$output" == *"custom"* ]]`，
  # 把真源的 key 改成 `customXX` 一樣通過 —— 那是套套邏輯的覆蓋，等於沒測。
  printf '%s\n' "$output" | grep -qx "custom"
}

@test "與 harness 的 PROFILES key 集合逐一相符（不是子集、也不是超集）" {
  run bash "$BIN"
  [ "$status" -eq 0 ]
  from_tool=$(printf '%s\n' "$output" | sort)
  # 直接數 harness 裡 PROFILES 的頂層 key，作為獨立的第二來源
  from_src=$(awk '
    /^const PROFILES = \{/ {inp=1; next}
    inp && /^\}/ {exit}
    inp && /^  [a-zA-Z_][a-zA-Z0-9_]*: \{/ { gsub(/[ :{]/,""); print }
  ' "$HARNESS" | sort)
  [ -n "$from_src" ]
  [ "$from_tool" = "$from_src" ]
}

@test "PAI_HARNESS 指向不存在的檔案時 fail-loud，不回空清單" {
  # 這條同時證明下一條測試的注入點是有效的（否則那條會套套邏輯地通過）。
  PAI_HARNESS="$BATS_TEST_TMPDIR/does-not-exist.js" run bash "$BIN"
  [ "$status" -ne 0 ]
}

@test "分隔線被改掉時要壞得看得見，而不是安靜地少幾個 profile" {
  tmp="$BATS_TEST_TMPDIR/harness.js"
  # 移除 Orchestration 分隔線 —— 抽取靠它切段（那是一行**註解**，沒有東西阻止它被改掉）
  grep -v '── Orchestration ──' "$HARNESS" > "$tmp"
  run diff -q "$HARNESS" "$tmp"
  [ "$status" -ne 0 ]        # 確認 mutation 真的改到了東西

  PAI_HARNESS="$tmp" run bash "$BIN"
  # 可接受的結果只有兩種：報錯，或輸出仍與真源完全相符。
  # **不可接受**的是「rc=0 且輸出一個看起來正常但少了東西的清單」——
  # validate.py 對 rc != 0 與空輸出都會報錯（R6），唯獨那一種會安靜地放行。
  if [ "$status" -eq 0 ]; then
    from_tool=$(printf '%s\n' "$output" | sort)
    from_src=$(awk '
      /^const PROFILES = \{/ {inp=1; next}
      inp && /^\}/ {exit}
      inp && /^  [a-zA-Z_][a-zA-Z0-9_]*: \{/ { gsub(/[ :{]/,""); print }
    ' "$HARNESS" | sort)
    [ "$from_tool" = "$from_src" ]
  fi
}
