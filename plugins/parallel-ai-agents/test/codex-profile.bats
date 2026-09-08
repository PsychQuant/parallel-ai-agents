#!/usr/bin/env bats
# codex-profile.bats — #48：repo 層級的 codex-pro profile pin（repo root `.codex-pro/profile.yaml`）。
#
# 為什麼要測一個設定檔：pai 的 codex leg 不在樹內 pin model/effort（#23），值由 codex-pro 契約
# 三層解析（defaults.json → ~/.codex-pro/profile.yaml → ./.codex-pro/profile.yaml），解析器是
# references/codex-governance.md 那組 grep/sed 正規式。它「取 `^model:` 之後的整段」——
# 引號、尾隨註解、尾隨空白都會原樣進 wire，backend 直接回 400 或靜默 fallback。這裡用
# **同一組正規式**斷言解析出來的字面恰好是 wire 要的值，把格式漂移擋在 CI。
#
# 第四案跑完整三層解析（真 codex-pro cache + 隔離 $HOME），斷言 project 層勝出；cache 缺席
# （ubuntu CI）自我 skip —— 那是環境限制不是 vacuous green，前三案在任何環境都會執行。

setup() {
  REPO_ROOT="$(git -C "$BATS_TEST_DIRNAME" rev-parse --show-toplevel)"
  PROFILE="$REPO_ROOT/.codex-pro/profile.yaml"
}

# 與 references/codex-governance.md 的 overlay 解析逐字相同（改這裡 = 改那裡）。
resolve_field() {
  grep -E "^$1:" "$2" | head -1 | sed "s/^$1:[[:space:]]*//"
}

@test "#48 repo root 有 .codex-pro/profile.yaml（專案層 pin）" {
  [ -f "$PROFILE" ]
}

@test "#48 profile 的 model 解析後恰為 gpt-6-astra（無引號、無尾隨字元）" {
  run resolve_field model "$PROFILE"
  [ "$status" -eq 0 ]
  [ "$output" = "gpt-6-astra" ]
}

@test "#48 profile 的 effort 解析後恰為 medium" {
  run resolve_field effort "$PROFILE"
  [ "$status" -eq 0 ]
  [ "$output" = "medium" ]
}

@test "#48 三層解析：project profile 蓋過 codex-pro defaults（無 codex-pro cache 則 skip）" {
  CP_DIR="$(ls -d "$HOME"/.claude/plugins/cache/codex-pro/codex-pro/*/ 2>/dev/null \
            | grep -E '/[0-9]+\.[0-9]+\.[0-9]+/$' | sort -V | tail -1)"
  if [ -z "$CP_DIR" ] || [ ! -f "${CP_DIR}references/defaults.json" ]; then
    skip "codex-pro plugin cache 缺席（ubuntu CI）—— 三層解析無 baseline 可疊"
  fi
  CP_DEFAULTS="${CP_DIR}references/defaults.json"

  # 隔離 $HOME：本機若有 ~/.codex-pro/profile.yaml（#48 選項 a）不可混進來，
  # 否則測到的是「global 層」而非本檔要鎖的「project 層」。
  export HOME="$BATS_TEST_TMPDIR/home"
  mkdir -p "$HOME"
  cd "$REPO_ROOT"

  # 以下即 references/codex-governance.md 的解析片段（逐字）。
  CODEX_MODEL=$(python3 -c "import json;print(json.load(open('$CP_DEFAULTS'))['model'])")
  CODEX_EFFORT=$(python3 -c "import json;print(json.load(open('$CP_DEFAULTS'))['effort'])")
  for PF in "$HOME/.codex-pro/profile.yaml" "./.codex-pro/profile.yaml"; do
    [ -f "$PF" ] || continue
    M=$(grep -E '^model:' "$PF" | head -1 | sed 's/^model:[[:space:]]*//'); [ -n "$M" ] && CODEX_MODEL="$M"
    E=$(grep -E '^effort:' "$PF" | head -1 | sed 's/^effort:[[:space:]]*//'); [ -n "$E" ] && CODEX_EFFORT="$E"
  done

  [ "$CODEX_MODEL" = "gpt-6-astra" ]
  [ "$CODEX_EFFORT" = "medium" ]
}
