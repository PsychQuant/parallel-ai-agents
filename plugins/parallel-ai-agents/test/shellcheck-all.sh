#!/usr/bin/env bash
# 機械護欄（#30）：shellcheck 的受檢清單由**列舉**產生，不再手寫。
#
# 為什麼：先前 `.github/workflows/test.yml` 與 `test/run.sh` 各有一份寫死的 shellcheck 清單。
# 寫死清單的預設值是錯的——新增的 script 預設**不被檢查**，而且 CI 全綠、沒有任何訊號
# （#33 實作 `bin/pai-list-profiles` 時撞過一次；#33 verify R11 又抓到兩份清單互相都不是
# 對方的超集）。現在兩處都呼叫這一支，列舉只有一份實作。
#
# 列舉規則（repo 級，不是 plugin 級——`plugins/pai-lenses/` 將來加 shell script 也會被掃到）：
#   來源：`git ls-files`（repo 頂層；只看 tracked 檔，未 commit 的草稿不算）。
#         不在 git worktree 裡（例如只複製了 plugin 目錄）→ 退回 `find` 掃 plugin 目錄，並明說。
#   收入：副檔名 `*.sh` / `*.bash`（副檔名優先——`foo.sh` 若帶 python shebang，讓 shellcheck 報出來），
#         或第一行 shebang 的直譯器是 sh / bash / dash / ksh（直接寫或經 `env` / `env -S`）。
#   排除：
#     - `*.bats`：bats 語法不是純 bash，另有 `test/lint-bats.sh` 專責；把它們納入 shellcheck 是另一個
#       決定（目前會帶出一批既有警告），不在 #30 範圍。
#     - 路徑含 `fixtures/` 的檔案：fixture 是**故意寫壞**的輸入，檢查它們只會逼人加豁免。
#     - symlink：指向的檔案若 tracked 會以本名被檢查；不 tracked 的不歸這裡管。
#     - 其他 shebang（`#!/usr/bin/swift`、python3、node、bats）：不是 shell。
#   護欄：列舉結果**逐行印出**（「掃了幾支」必須可見）；列舉為空 → 非零（偵測壞了，不是「沒有 script」）；
#         本檔自己不在列舉裡 → 非零（它是 bash shebang + `.sh`，找不到它就是偵測器壞了）。
#
# 已知不涵蓋：workflow `run:` 區塊裡的 inline bash——要 actionlint 之類的工具，另一個決定（#30 診斷的 Residue）。
#
# 用法：test/shellcheck-all.sh              列舉並跑 shellcheck（預設嚴重度，與先前的寫死清單一致）
#       test/shellcheck-all.sh --list       只印列舉結果（repo 頂層相對路徑），不跑 shellcheck
#       test/shellcheck-all.sh --selftest   護欄自己的自測：分類規則、git 來源只看 tracked、
#                                           空列舉必紅、shellcheck 的非零必須傳出來
set -euo pipefail
cd "$(dirname "$0")/.."
PLUGIN_DIR="$(pwd -P)"
SELF_NAME="test/shellcheck-all.sh"

# $1 = 路徑（相對於目前目錄）。回 0 = 是要檢查的 shell script。
is_shell_script() {
  local f="$1" first interp i
  local -a w
  if [ ! -f "$f" ] || [ -L "$f" ]; then return 1; fi
  case "$f" in
    *.bats) return 1 ;;
    fixtures/* | */fixtures/*) return 1 ;;
    *.sh | *.bash) return 0 ;;
  esac
  first=""
  IFS= read -r first < "$f" || [ -n "$first" ] || return 1
  first="${first%$'\r'}"
  case "$first" in '#!'*) ;; *) return 1 ;; esac
  read -r -a w <<< "${first#\#!}" || true
  [ "${#w[@]}" -gt 0 ] || return 1
  interp="${w[0]##*/}"
  if [ "$interp" = env ]; then
    i=1
    while [ "$i" -lt "${#w[@]}" ] && [[ "${w[$i]}" == -* ]]; do i=$((i + 1)); done
    [ "$i" -lt "${#w[@]}" ] || return 1
    interp="${w[$i]##*/}"
  fi
  case "$interp" in sh | bash | dash | ksh) return 0 ;; esac
  return 1
}

# $1 = 掃描根目錄。在該目錄底下印出（NUL 分隔、根目錄相對）要檢查的檔案。
# 呼叫前後的目前目錄不變（在 subshell 裡 cd）。
enumerate() (
  cd "$1"
  local f
  if [ "$(git rev-parse --is-inside-work-tree 2>/dev/null || true)" = true ] \
     && [ "$(git rev-parse --show-toplevel)" = "$(pwd -P)" ]; then
    while IFS= read -r -d '' f; do
      if is_shell_script "$f"; then printf '%s\0' "$f"; fi
    done < <(git ls-files -z)
  else
    while IFS= read -r -d '' f; do
      f="${f#./}"
      if is_shell_script "$f"; then printf '%s\0' "$f"; fi
    done < <(find . -path ./.git -prune -o -type f -print0)
  fi
)

# 本檔相對於掃描根目錄的路徑（自我包含護欄用）。git 的 --show-prefix 是 plugin 目錄在 repo 裡的前綴；
# 不在 git 裡時掃描根就是 plugin 目錄，前綴為空。不用 `realpath --relative-to`（macOS 沒有）。
self_path() {
  local prefix
  prefix="$(git -C "$PLUGIN_DIR" rev-parse --show-prefix 2>/dev/null || true)"
  printf '%s%s\n' "$prefix" "$SELF_NAME"
}

# 掃描根目錄：git worktree 的頂層；不在 git 裡就是 plugin 目錄本身。
scan_root() {
  local top
  if top="$(git -C "$PLUGIN_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    printf '%s\n' "$top"
  else
    echo "shellcheck-all: 不在 git worktree 裡，退回 find 掃 plugin 目錄（${PLUGIN_DIR}）" >&2
    printf '%s\n' "$PLUGIN_DIR"
  fi
}

# $1 = 掃描根目錄；$2 = 必須出現在列舉裡的路徑（根目錄相對；空字串 = 不要求）；
# $3 = list（只印）或 check（印 + 跑 shellcheck）。
run_check() {
  local root="$1" must="$2" mode="$3" f found=0 rc=0
  local -a files=()
  while IFS= read -r -d '' f; do files+=("$f"); done < <(enumerate "$root")
  if [ "${#files[@]}" -eq 0 ]; then
    echo "shellcheck-all: 列舉出 0 支 shell script（根目錄 ${root}）——偵測壞了，不是「沒有 script」" >&2
    return 1
  fi
  if [ -n "$must" ]; then
    for f in "${files[@]}"; do [ "$f" = "$must" ] && found=1; done
    if [ "$found" -ne 1 ]; then
      echo "shellcheck-all: 列舉結果裡沒有 ${must} 自己——偵測器壞了（它是 bash shebang + .sh）" >&2
      return 1
    fi
  fi
  if [ "$mode" = list ]; then
    printf '%s\n' "${files[@]}"
    return 0
  fi
  echo "shellcheck-all: ${#files[@]} 支（根目錄 ${root}）："
  printf '  %s\n' "${files[@]}"
  (cd "$root" && shellcheck -- "${files[@]}") || rc=$?
  return "$rc"
}

selftest() {
  local tmp got want
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064  # 故意現在展開：trap 觸發時 local 已不在
  trap "rm -rf '$tmp'" EXIT

  # ── 1. 分類規則（find 來源：tmp 不是 git worktree）──
  mkdir -p "$tmp/a/bin" "$tmp/a/test/fixtures" "$tmp/a/deep/fixtures"
  printf '#!/usr/bin/env bash\necho ok\n'         > "$tmp/a/bin/env-bash"
  printf '#!/bin/bash\necho ok\n'                 > "$tmp/a/bin/bin-bash"
  printf '#!/bin/sh\necho ok\n'                   > "$tmp/a/bin/bin-sh"
  printf '#!/usr/bin/env -S bash -e\necho ok\n'   > "$tmp/a/bin/env-S-bash"
  printf '#! /bin/dash\necho ok\n'                > "$tmp/a/bin/spaced-dash"
  printf '#!/bin/bash\r\necho ok\r\n'             > "$tmp/a/bin/crlf-bash"
  printf 'echo no shebang but .sh\n'              > "$tmp/a/ext.sh"
  printf '#!/usr/bin/env bash\necho ok\n'         > "$tmp/a/ext.bash"
  printf '#!/usr/bin/env python3\nprint(1)\n'     > "$tmp/a/bin/py"
  printf '#!/usr/bin/swift\nprint(1)\n'           > "$tmp/a/bin/swift"
  printf '#!/usr/bin/env node\n1\n'               > "$tmp/a/bin/node"
  printf '#!/usr/bin/env bashful\n'               > "$tmp/a/bin/not-bash"
  printf '#!/usr/bin/env bats\n@test "x" { :; }\n' > "$tmp/a/test/t.bats"
  # shellcheck disable=SC2016  # 故意：寫進 fixture 的字面 $1
  printf '#!/usr/bin/env bash\necho $1\n'         > "$tmp/a/test/fixtures/bad.sh"
  # shellcheck disable=SC2016  # 故意：寫進 fixture 的字面 $1
  printf '#!/usr/bin/env bash\necho $1\n'         > "$tmp/a/deep/fixtures/bad"
  printf 'plain text\n'                           > "$tmp/a/README"
  : > "$tmp/a/empty"
  ln -s bin/env-bash "$tmp/a/link-to-bash"
  want="bin/bin-bash bin/bin-sh bin/crlf-bash bin/env-S-bash bin/env-bash bin/spaced-dash ext.bash ext.sh"
  got="$(enumerate "$tmp/a" | tr '\0' '\n' | LC_ALL=C sort | tr '\n' ' ')"
  got="${got% }"
  if [ "$got" != "$want" ]; then
    printf 'shellcheck-all selftest FAILED: 分類規則\n  want: %s\n  got:  %s\n' "$want" "$got" >&2
    return 1
  fi

  # ── 2. git 來源只看 tracked 檔 ──
  mkdir -p "$tmp/g"
  printf '#!/usr/bin/env bash\necho ok\n' > "$tmp/g/tracked.sh"
  printf '#!/usr/bin/env bash\necho ok\n' > "$tmp/g/untracked"
  git -C "$tmp/g" init -q
  git -C "$tmp/g" add tracked.sh
  got="$(enumerate "$tmp/g" | tr '\0' ' ')"
  if [ "$got" != "tracked.sh " ]; then
    printf 'shellcheck-all selftest FAILED: git 來源應只列 tracked.sh，實得：%s\n' "$got" >&2
    return 1
  fi

  # ── 3. 空列舉必紅（vacuity guard）──
  mkdir -p "$tmp/empty"
  printf '#!/usr/bin/env python3\n' > "$tmp/empty/only-python"
  if run_check "$tmp/empty" "" check >/dev/null 2>&1; then
    echo "shellcheck-all selftest FAILED: 列舉為空卻回 0（vacuous green）" >&2
    return 1
  fi

  # ── 4. 必要路徑缺席必紅（自我包含護欄）──
  if run_check "$tmp/g" "not-there.sh" list >/dev/null 2>&1; then
    echo "shellcheck-all selftest FAILED: 必要路徑不在列舉裡卻回 0" >&2
    return 1
  fi

  # ── 5. shellcheck 的判定要傳出來：乾淨 → 0，有警告 → 非零 ──
  mkdir -p "$tmp/clean" "$tmp/dirty"
  printf '#!/usr/bin/env bash\necho "ok"\n' > "$tmp/clean/ok.sh"
  # shellcheck disable=SC2016  # 故意：寫進 fixture 的字面 $1
  printf '#!/usr/bin/env bash\necho $1\n'   > "$tmp/dirty/warn.sh"   # SC2086
  if ! run_check "$tmp/clean" "" check >/dev/null 2>&1; then
    echo "shellcheck-all selftest FAILED: 乾淨的 script 被判紅（shellcheck 不在 PATH？）" >&2
    return 1
  fi
  if run_check "$tmp/dirty" "" check >/dev/null 2>&1; then
    echo "shellcheck-all selftest FAILED: 有 SC2086 的 script 被判綠——shellcheck 的非零沒有傳出來" >&2
    return 1
  fi

  echo "shellcheck-all selftest ok: 分類、tracked-only、空列舉、自我包含、shellcheck 非零傳遞"
}

case "${1:-}" in
  --selftest) selftest ;;
  --list) run_check "$(scan_root)" "$(self_path)" list ;;
  "") run_check "$(scan_root)" "$(self_path)" check ;;
  *) echo "用法：test/shellcheck-all.sh [--list | --selftest]" >&2; exit 2 ;;
esac
