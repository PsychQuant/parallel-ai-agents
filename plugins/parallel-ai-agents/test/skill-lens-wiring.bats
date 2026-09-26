#!/usr/bin/env bats
#
# 每一支專屬 review skill（`skills/ensemble-<profile>-review/`）都必須把三層 lens 疊加的
# 層 ②③ 接進它的派發（#40）。
#
# 為什麼要機器擋：`/ensemble-minutes-review`（v2.22.0 出貨）漏接 `bin/pai-collect-lens-layers`，
# 結果 `pai-lenses` 的 `lenses/minutes.csv` 與 `~/.claude/pai-lenses/minutes.csv` 在它的審閱裡
# **完全不生效，而且沒有任何警告**——CI 全綠、報表沒有 provenance 行，從輸出上看不出少了東西。
# `plugins/pai-lenses/scripts/validate.py` 的 `collector_wiring` 只在「該 profile 有 pack CSV」時
# 才看、只印 warning，且自承是啟發式；這裡是主 plugin 這一側的硬閘門：新增第五支
# `ensemble-*-review` 時自動涵蓋，漏接就紅。
#
# 判準刻意只看 SKILL.md 的文字（skill 就是一份給模型的指令；沒寫進去就不會被執行）：
#   1. 有一行**非註解**的 `pai-collect-lens-layers <profile>` 呼叫，profile 取自目錄名
#   2. 派發的 args 帶 `customLenses`（collector 的 lenses 要有地方進去）
#   3. `profile` 維持原值（`"profile": "<p>"` 或 `profile: "<p>"`），不是 `"custom"`
#   4. 報表階段提到 provenance 行（references/lens-layers.md §4：沒裝 pack 也要印）

setup() {
  SKILLS="${BATS_TEST_DIRNAME}/../skills"
}

# 列出所有專屬 review skill 的目錄名（ensemble-<profile>-review）
review_skills() {
  local d
  for d in "$SKILLS"/ensemble-*-review; do
    [ -f "$d/SKILL.md" ] && basename "$d"
  done
}

profile_of() { local n="${1#ensemble-}"; printf '%s\n' "${n%-review}"; }

@test "至少有四支專屬 review skill（防列舉為空的 vacuous 綠燈）" {
  run review_skills
  [ "$status" -eq 0 ]
  [ "$(printf '%s\n' "$output" | grep -c .)" -ge 4 ]
  # minutes 就是 #40 漏掉的那一支 —— 釘住它在列舉裡
  printf '%s\n' "$output" | grep -qx "ensemble-minutes-review"
}

@test "每一支 review skill 都以自己的 profile 呼叫 pai-collect-lens-layers（非註解行）" {
  local missing=() s p
  while IFS= read -r s; do
    p="$(profile_of "$s")"
    if ! grep -vE '^[[:space:]]*#' "$SKILLS/$s/SKILL.md" \
         | grep -qE "pai-collect-lens-layers\"?[[:space:]]+\"?${p}([^[:alnum:]_-]|$)"; then
      missing+=("$s（profile=$p）")
    fi
  done < <(review_skills)
  if [ "${#missing[@]}" -ne 0 ]; then
    printf '漏接 collector：%s\n' "${missing[@]}" >&2
    return 1
  fi
}

@test "每一支 review skill 的派發 args 都帶 customLenses" {
  local missing=() s
  while IFS= read -r s; do
    grep -q 'customLenses' "$SKILLS/$s/SKILL.md" || missing+=("$s")
  done < <(review_skills)
  if [ "${#missing[@]}" -ne 0 ]; then
    printf '派發 args 沒有 customLenses：%s\n' "${missing[@]}" >&2
    return 1
  fi
}

@test "每一支 review skill 的 profile 維持原值（不改成 custom）" {
  local missing=() s p
  while IFS= read -r s; do
    p="$(profile_of "$s")"
    grep -qE "\"?profile\"?[[:space:]]*:[[:space:]]*\"${p}\"" "$SKILLS/$s/SKILL.md" || missing+=("$s（profile=$p）")
  done < <(review_skills)
  if [ "${#missing[@]}" -ne 0 ]; then
    printf 'profile 不是原值：%s\n' "${missing[@]}" >&2
    return 1
  fi
}

@test "每一支 review skill 的報表都印 provenance 行" {
  local missing=() s
  while IFS= read -r s; do
    grep -qi 'provenance' "$SKILLS/$s/SKILL.md" || missing+=("$s")
  done < <(review_skills)
  if [ "${#missing[@]}" -ne 0 ]; then
    printf '報表沒有 provenance 行：%s\n' "${missing[@]}" >&2
    return 1
  fi
}
