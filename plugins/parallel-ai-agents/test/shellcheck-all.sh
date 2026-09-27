#!/usr/bin/env bash
# 機械護欄（#30）：shellcheck 與 py_compile 的受檢清單由**列舉**產生，不再手寫。
#
# 為什麼：先前 `.github/workflows/test.yml` 與 `test/run.sh` 各有一份寫死的 shellcheck 清單與一份寫死的
# py_compile 清單。寫死清單的預設值是錯的——新增的 script 預設**不被檢查**，而且 CI 全綠、沒有任何訊號
# （#33 實作 `bin/pai-list-profiles` 時撞過一次；#33 verify R11 又抓到兩份 shellcheck 清單互相都不是對方的
# 超集；py_compile 清單 #34 延後到這裡）。現在兩處都呼叫這一支，列舉只有一份實作（`enumerate`），
# 兩種語言共用同一條分類路徑（`classify`）。
#
# 來源（`plan`）：
#   - 本檔被**它所在的 git repo 追蹤**（monorepo 的正常情況）→ 該 repo 頂層的 `git ls-files`
#     （repo 級：`plugins/pai-lenses/` 將來的 script 也涵蓋；只看 tracked 檔，未 `git add` 的草稿不算）。
#   - 不在任何 git worktree 裡（例如只複製了 plugin 目錄）→ `find` 掃 plugin 目錄，並明說。
#     判準是 `git rev-parse` 的**探索失敗訊息**（`not a git repository (or any …`，以 LC_ALL=C 取）；
#     其他失敗（`GIT_DIR` 指錯、dubious ownership…）→ 紅，不退回（#30 verify R2 row 3）。
#   - 在某個 git worktree 裡、但本檔**不被它追蹤**（plugin 目錄被 vendor 進另一個 repo）→ 同上退回
#     `find` 掃 plugin 目錄，並明說。先前這種情況會去掃外層 repo，再以「偵測器壞了」這個誤導訊息紅掉。
#     判準是 `git ls-files --error-unmatch` 的 **rc=1**（沒追蹤）；其他非零（index 損壞…）→ 紅，不退回。
#   - 來源指令（`git ls-files`／`find`）的輸出先落檔、**檢查它的退出碼**；非零 → 紅，不拿部分清單繼續。
#
# 分類（`classify`，每個候選檔一個 kind；`--list` 與正式輸出都逐行印 kind）：
#   sh:ext       副檔名 `*.sh`／`*.bash`（副檔名優先——`foo.sh` 若帶 python shebang，讓 shellcheck 報出來）
#   sh:shebang   第一行 shebang 的直譯器是 sh／bash／dash／ksh
#   py:ext       副檔名 `*.py`
#   py:shebang   直譯器是 python／python3／python3.N
#   直譯器的判定：`#!/path/interp …` 取 interp 的 basename；`#!/usr/bin/env …` 則跳過 env 的選項與
#   `NAME=VALUE` 指派：`-i`／`-0`／`-v`／`-`、`-u NAME`／`--unset NAME`／`--unset=NAME`、`-C DIR`／`--chdir DIR`、
#   `-a ARG`／`--argv0 ARG`、BSD 的 `-P PATH`、`-S`／`--split-string`（含黏寫的 `-Sbash`、`-iS`、`-uNAME`）、`--`。
#   BSD 的 `-L`／`-U USER[/CLASS]` 也吃參數。第一個不是選項也不是指派的字才是直譯器。
#   **判定不了 → 紅，不是 skip**（`error:shebang`，逐檔列出；#30 verify R2 row 4）：這裡只按空白切字，
#   不做 `env -S` 的引號／跳脫／`${VAR}` 展開。所以直譯器（含它之前被當成選項參數跳過的字）只要含
#   `"`、`'`、`\`、`$`，或 env 帶了上面以外的短選項，就沒辦法確定它是什麼——先前會被分成
#   `skip:shebang=<雜訊>`（例如 `-S "bash"` → `"bash"`），等於靜默不檢查。請把 shebang 改寫成不需要引號的形式。
#
# 排除（每一條都**逐行印出並附理由**，`skip:<理由>`——被排除的檔案不再隱形）：
#   skip:bats      `*.bats`：bats 語法不是純 bash，另有 `test/lint-bats.sh` 專責；把它們納入 shellcheck 是另一個
#                  決定（目前會帶出一批既有警告），不在 #30 範圍。副檔名優先於 shebang。
#   skip:fixture   **只有**「直接位於 `test/`、`tests/` 或 `eval/` 底下的 `fixtures/` 目錄」（任意深度，例如
#                  `plugins/<p>/test/fixtures/`、`plugins/<p>/eval/fixtures/`）裡、本來會被收入的檔。那是本 repo 放
#                  **故意寫壞**的輸入的慣例位置；檢查它們只會逼人加豁免。其他叫 `fixtures` 的目錄照常檢查——
#                  先前的「路徑含 `fixtures/` 就跳過」讓任何地方的 script 放進一個 fixtures 目錄就逃過檢查。
#   skip:symlink   symlink（git 追蹤的或 find 看到的）：指向的檔案若 tracked 會以本名被檢查；否則不歸這裡管。
#   skip:missing   git 追蹤、但工作樹裡不存在（被刪了還沒 commit）。
#   skip:unreadable 讀不到第一行。
#   skip:shebang=X 其他直譯器（swift、node、bats、zsh…）：兩種模式都不檢查，列出來讓「沒被任何人檢查」可見。
#   （`error:shebang` 若位於上述 fixtures 目錄裡同樣是 skip:fixture——故意寫壞的輸入。）
#   沒有 shebang、也沒有上述副檔名的檔（文件、資料）不列。
#
# 護欄（`run_check`，任一不成立 → 非零）：
#   1. 該語言列舉為空 → 紅（偵測壞了，不是「沒有 script」）。
#   2. 副檔名規則與 shebang 規則**各自**至少命中一支 → 否則紅。本 repo 兩種都有；一條規則零命中與
#      「那條規則壞了」分不開（#30 自己的故障形狀：來源若只列 `*.sh`，extensionless 的 `bin/` script 全數消失）。
#   3. （shell）本檔自己必須以 sh:* 出現在列舉裡；自我路徑為空也算紅（護欄沒接上）。
#   0. 任何 `error:shebang` → 紅（兩種語言都是；先於上面三條）。
#
# 已知不涵蓋：workflow `run:` 區塊裡的 inline bash——要 actionlint 之類的工具，另一個決定（#30 診斷的 Residue）。
#
# 用法：test/shellcheck-all.sh                   列舉並跑 shellcheck（預設嚴重度，與先前的寫死清單一致）
#       test/shellcheck-all.sh --list            只印列舉結果（`<kind>\t<根目錄相對路徑>`，含 skip），不跑 shellcheck
#       test/shellcheck-all.sh --python          列舉 python 並逐支編譯（`python3 -I -X pycache_prefix=… -m py_compile`：
#                                                `-I` 讓根目錄不進 sys.path——受檢 repo 裡的 `py_compile.py` 不得遮蔽
#                                                標準庫；`-I` 也忽略 PYTHON* 環境變數，所以 bytecode 目錄用 `-X`（3.8+）
#                                                而非 PYTHONPYCACHEPREFIX；不在工作樹留 __pycache__。#30 verify R2 row 7）
#       test/shellcheck-all.sh --python --list   只印 python 的列舉結果
#       test/shellcheck-all.sh --selftest        護欄自己的自測（涵蓋範圍見 selftest() 結尾的成功訊息，逐條對應；
#                                                鑑別力由 ../pai-lenses/scripts/mutation_check.py 的 `shellcheck-all` 守備單位量）
#       （`--_selftest-git`、`--_run` 是 selftest 內部用的子行程入口，不是公開介面。）
#
# **必須能在 bash 3.2 跑**（macOS 的 /bin/bash 是 3.2.57；`test/run.sh` 第一步就跑 `--selftest`）。
# 不用 bash 4+ 才有的東西：陣列讀檔 builtin、關聯陣列、`${v,,}`／`${v^^}`、`&>>`、`|&`、coproc、負索引；
# `set -u` 下展開**空陣列**在 3.2 是 unbound variable（先判 `${#a[@]}`）。#30 verify R2 row 1 在 3.2 上以
# rc=127 紅過一次；selftest 的 case 0 對本檔做最小的靜態掃描擋住回歸（CI 是 ubuntu/bash 5，跑不出 3.2）。
# 子行程一律用 `"$BASH"`（同一支直譯器），不是 PATH 上的 bash——否則在 3.2 下跑 selftest 其實有一半跑在 5。
set -euo pipefail
cd "$(dirname "$0")/.."
PLUGIN_DIR="$(pwd -P)"
SELF_NAME="test/shellcheck-all.sh"
SELF_ABS="${PLUGIN_DIR}/${SELF_NAME}"

# ── 分類 ────────────────────────────────────────────────────────────────────────────────────────

# $1 = shebang 行去掉 `#!` 之後的內容。把直譯器的 basename 放進全域 INTERP（沒有則為空）；
# 判定不了（見檔頭）→ INTERP 為空、全域 INTERP_ERR=1。
# 不用 command substitution：每個檔 fork 一次太慢，而且 subshell 會吃掉錯誤。
shebang_interp() {
  local -a w
  local i=1 opts=1 t j c k take=0 rest
  INTERP=""; INTERP_ERR=0
  read -r -a w <<< "$1" || true
  [ "${#w[@]}" -gt 0 ] || return 0
  if [ "${w[0]##*/}" != env ]; then i=0; opts=0; fi
  while [ "$i" -lt "${#w[@]}" ]; do
    t="${w[$i]}"
    if [ "$opts" -eq 1 ]; then
      case "$t" in
        --) opts=0; i=$((i + 1)); continue ;;
        --unset | --chdir | --argv0) i=$((i + 2)); continue ;;
        --split-string) i=$((i + 1)); continue ;;                  # 後面的字就是被切開的那個字串，照常解析
        --split-string=*) w[i]="${t#--split-string=}"; continue ;; # `=` 後面是字串的第一個字：原地重新解析
        --*) i=$((i + 1)); continue ;;                             # 其餘長選項不吃下一個字（可選參數只能用 `=`）
        -) i=$((i + 1)); continue ;;                               # 等同 -i
        -*)
          # 短選項群：逐字元。u／C／a／P 吃參數（群內剩下的字元，或下一個字）；S 的參數是要切開的字串。
          j=1; take=0; rest=""
          while [ "$j" -lt "${#t}" ]; do
            c="${t:j:1}"
            case "$c" in
              u | C | a | P | L | U) [ $((j + 1)) -lt "${#t}" ] || take=1; break ;;
              S) rest="${t:j+1}"; break ;;
              i | 0 | v) j=$((j + 1)) ;;
              *) INTERP_ERR=1; return 0 ;;      # 不認得的選項：不知道它吃不吃參數
            esac
          done
          if [ -n "$rest" ]; then w[i]="$rest"; continue; fi
          i=$((i + 1 + take)); continue ;;
      esac
    fi
    case "$t" in
      *=*) if [ "$i" -gt 0 ]; then opts=0; i=$((i + 1)); continue; fi ;;   # NAME=VALUE：env 把任何含 `=` 的字當指派
    esac
    # 直譯器與它之前的每個字（含被當成選項參數跳過的）都不得含引號／跳脫／`$`——那需要 env -S 的語法才解得開。
    k=0
    while [ "$k" -le "$i" ]; do
      case "${w[$k]}" in *[\"\'\\\$]*) INTERP_ERR=1; return 0 ;; esac
      k=$((k + 1))
    done
    INTERP="${t##*/}"
    return 0
  done
}

# 「直接位於 test/、tests/、eval/ 底下的 fixtures/ 目錄」——任意深度。$1 = 根目錄相對路徑。
in_fixture_dir() {
  case "/$1" in
    */test/fixtures/* | */tests/fixtures/* | */eval/fixtures/*) return 0 ;;
  esac
  return 1
}

# $1 = 根目錄相對路徑（目前目錄 = 根目錄）。把 kind 放進全域 KIND；空 = 不是候選（不列）。
classify() {
  local f="$1" first=""
  KIND=""
  if [ -L "$f" ]; then KIND=skip:symlink
  elif [ ! -e "$f" ]; then KIND=skip:missing
  elif [ ! -f "$f" ]; then return 0      # 目錄（submodule 的 gitlink）等
  else
    case "$f" in
      *.bats) KIND=skip:bats ;;
      *.sh | *.bash) KIND=sh:ext ;;
      *.py) KIND=py:ext ;;
      *)
        if [ ! -r "$f" ]; then
          KIND=skip:unreadable
        else
          IFS= read -r first < "$f" || true    # 最後一行沒有換行時 read 回非零，但內容已讀到
          first="${first%$'\r'}"
          case "$first" in '#!'*) ;; *) return 0 ;; esac
          shebang_interp "${first#\#!}"
          if [ "$INTERP_ERR" -eq 1 ]; then KIND=error:shebang; fi
          case "$KIND$INTERP" in
            error:*) ;;
            sh | bash | dash | ksh) KIND=sh:shebang ;;
            python | python[0-9] | python[0-9].[0-9]*) KIND=py:shebang ;;
            "") return 0 ;;
            *) KIND="skip:shebang=${INTERP}" ;;
          esac
        fi ;;
    esac
  fi
  case "$KIND" in sh:* | py:* | error:*) if in_fixture_dir "$f"; then KIND=skip:fixture; fi ;; esac
  return 0
}

# ── 列舉 ────────────────────────────────────────────────────────────────────────────────────────

# $1 = 根目錄；$2 = 來源（git | find）；$3 = 輸出檔。寫入 NUL 分隔的 `<kind>\t<根目錄相對路徑>` 紀錄。
# 來源指令的輸出先落檔、檢查退出碼——process substitution 會把它吃掉（#30 verify R1 row 3）。
enumerate() {
  local root="$1" src="$2" out="$3" paths="$3.paths" rc=0 f
  case "$src" in
    git) (cd "$root" && git ls-files -z) > "$paths" || rc=$? ;;
    find) (cd "$root" && find . -path ./.git -prune -o \( -type f -o -type l \) -print0) > "$paths" || rc=$? ;;
    *) echo "shellcheck-all: 未知的列舉來源「${src}」" >&2; return 2 ;;
  esac
  if [ "$rc" -ne 0 ]; then
    echo "shellcheck-all: 列舉來源失敗（${src}，rc=${rc}，根目錄 ${root}）——部分輸出不可信，不繼續" >&2
    return 1
  fi
  (
    cd "$root"
    while IFS= read -r -d '' f; do
      f="${f#./}"
      classify "$f"
      if [ -n "$KIND" ]; then printf '%s\t%s\0' "$KIND" "$f"; fi
    done < "$paths"
  ) > "$out"
}

# $1 = plugin 目錄。決定掃描根目錄與來源，設全域 PLAN_ROOT／PLAN_SRC／PLAN_SELF（本檔相對於根目錄的路徑）。
# 判準是「本檔是否被外層 repo 追蹤」，不是「外層有沒有 repo」（#30 verify R1 row 7：vendored 副本）。
# 只有兩種「確定的否定」才退回 find（#30 verify R2 row 3）：rev-parse 的探索失敗訊息、ls-files --error-unmatch 的 rc=1。
# 其餘失敗都是「問不出答案」——退回 find 會以一句錯的理由（vendored／不在 worktree）換來 rc=0。
plan() {
  local dir="$1" top prefix err="${WORK}/plan.err" rc=0
  top="$(LC_ALL=C git -C "$dir" rev-parse --show-toplevel 2>"$err")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 128 ] && grep -q '^fatal: not a git repository (or any ' "$err"; then
      echo "shellcheck-all: 不在 git worktree 裡，退回 find 掃 plugin 目錄（${dir}）" >&2
      PLAN_ROOT="$dir"; PLAN_SRC="find"; PLAN_SELF="$SELF_NAME"
      return 0
    fi
    echo "shellcheck-all: 列舉來源失敗（git rev-parse --show-toplevel，rc=${rc}，${dir}）：$(head -1 "$err")——不退回 find" >&2
    return 1
  fi
  prefix="$(LC_ALL=C git -C "$dir" rev-parse --show-prefix 2>"$err")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "shellcheck-all: 列舉來源失敗（git rev-parse --show-prefix，rc=${rc}，${dir}）：$(head -1 "$err")" >&2
    return 1
  fi
  LC_ALL=C git -C "$top" ls-files --error-unmatch -- "${prefix}${SELF_NAME}" >/dev/null 2>"$err" || rc=$?
  case "$rc" in
    0) PLAN_ROOT="$top"; PLAN_SRC="git"; PLAN_SELF="${prefix}${SELF_NAME}"; return 0 ;;
    1) echo "shellcheck-all: ${SELF_NAME} 不被外層 git repo（${top}）追蹤——視為 vendored 副本，退回 find 掃 plugin 目錄（${dir}）" >&2
       PLAN_ROOT="$dir"; PLAN_SRC="find"; PLAN_SELF="$SELF_NAME"; return 0 ;;
    *) echo "shellcheck-all: 列舉來源失敗（git ls-files --error-unmatch，rc=${rc}，${top}）：$(head -1 "$err")——不退回 find" >&2
       return 1 ;;
  esac
}

# ── 檢查 ────────────────────────────────────────────────────────────────────────────────────────

# $1 = 根目錄；$2 = 來源；$3 = 語言（sh | py）；$4 = list（只印）或 check（印 + 跑工具）；
# $5 = 必須以 sh:* 出現在列舉裡的路徑（sh 必填，空字串也算紅；py 忽略）。
run_check() {
  local root="$1" src="$2" lang="$3" action="$4" must="$5"
  local rec r k p n_ext=0 n_sb=0 found=0 rc=0 label tool
  local -a files=() lines=() skipped=() errors=()
  case "$lang" in
    sh) label="shell script"; tool=shellcheck ;;
    py) label="python script"; tool="python3 -I -m py_compile" ;;
    *) echo "shellcheck-all: 未知的語言「${lang}」" >&2; return 2 ;;
  esac
  rec="$(mktemp "${WORK}/rec.XXXXXX")"
  enumerate "$root" "$src" "$rec" || return 1
  while IFS= read -r -d '' r; do
    k="${r%%$'\t'*}"; p="${r#*$'\t'}"
    case "$k" in
      "${lang}:ext") files+=("$p"); lines+=("$r"); n_ext=$((n_ext + 1)) ;;
      "${lang}:shebang") files+=("$p"); lines+=("$r"); n_sb=$((n_sb + 1)) ;;
      skip:*) skipped+=("$r") ;;
      error:*) errors+=("$r") ;;
    esac
  done < "$rec"
  if [ "${#errors[@]}" -gt 0 ]; then
    echo "shellcheck-all: ${#errors[@]} 支檔案的 shebang 無法判定直譯器（含引號／反斜線／\$，或不認得的 env 選項）——" \
      "不能確定該用哪個工具檢查，也不能默默略過；請改寫 shebang（根目錄 ${root}）：" >&2
    printf '  %s\n' "${errors[@]}" >&2
    return 1
  fi
  if [ "${#files[@]}" -eq 0 ]; then
    echo "shellcheck-all: 列舉出 0 支 ${label}（根目錄 ${root}）——偵測壞了，不是「沒有 script」" >&2
    return 1
  fi
  if [ "$n_ext" -eq 0 ] || [ "$n_sb" -eq 0 ]; then
    echo "shellcheck-all: ${label} 的副檔名規則命中 ${n_ext} 支、shebang 規則命中 ${n_sb} 支——有一條規則零命中，分不出是「沒有」還是「規則壞了」（根目錄 ${root}）" >&2
    return 1
  fi
  if [ "$lang" = sh ]; then
    if [ -z "$must" ]; then
      echo "shellcheck-all: 自我包含護欄沒有接上（必須出現的路徑是空字串）" >&2
      return 1
    fi
    for p in "${files[@]}"; do if [ "$p" = "$must" ]; then found=1; fi; done
    if [ "$found" -ne 1 ]; then
      echo "shellcheck-all: 列舉結果裡沒有 ${must} 自己——偵測器壞了（它是 bash shebang + .sh）" >&2
      return 1
    fi
  fi
  if [ "$action" = list ]; then
    printf '%s\n' "${lines[@]}"
    if [ "${#skipped[@]}" -gt 0 ]; then printf '%s\n' "${skipped[@]}"; fi
    return 0
  fi
  echo "shellcheck-all: ${label} ${#files[@]} 支（根目錄 ${root}，來源 ${src}；副檔名 ${n_ext}、shebang ${n_sb}）→ ${tool}："
  printf '  %s\n' "${lines[@]}"
  echo "shellcheck-all: 排除 ${#skipped[@]} 支（附理由；兩種語言共用）："
  if [ "${#skipped[@]}" -gt 0 ]; then printf '  %s\n' "${skipped[@]}"; fi
  if [ "$lang" = sh ]; then
    (cd "$root" && shellcheck -- "${files[@]/#/./}") || rc=$?
  else
    # -I：根目錄不進 sys.path（受檢 repo 的 py_compile.py 不得遮蔽標準庫）；-I 忽略 PYTHON*，所以 bytecode 目錄走 -X。
    (cd "$root" && python3 -I -X pycache_prefix="${WORK}/pycache" -m py_compile "${files[@]/#/./}") || rc=$?
  fi
  return "$rc"
}

# ── 自測 ────────────────────────────────────────────────────────────────────────────────────────

st_fail() { printf 'shellcheck-all selftest FAILED: %s\n' "$*" >&2; return 1; }
# $1 = 訊息；$2 = 細節（縮排印出）。一次呼叫印完：selftest 本體跑在 errexit 下，`{ st_fail …; printf …; }` 的
# printf 永遠跑不到——st_fail 的 return 1 就讓 shell 結束了（#30 verify R2 實作時撞到）。
st_fail_with() { printf 'shellcheck-all selftest FAILED: %s\n' "$1" >&2; printf '%s\n' "$2" | sed 's/^/    /' >&2; return 1; }

# 自測的 scratch git repo 不得繼承呼叫者的 GIT_*（例如 hook 裡的 GIT_INDEX_FILE）——否則 `git add`
# 會寫進呼叫者的 index（#30 verify R1 row 4）。清單取 git 自己的 `--local-env-vars`，再加兩個探索相關的。
# 逐行讀、不存陣列：bash 3.2 沒有陣列讀檔 builtin（#30 verify R2 row 1：先前在 macOS 上 rc=127）。
scrub_git_env() {
  local vars v
  vars="$(git rev-parse --local-env-vars)" || { st_fail "git rev-parse --local-env-vars 失敗"; return 1; }
  while IFS= read -r v; do
    [ -z "$v" ] || unset "$v"
  done <<< "$vars"
  unset GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM
  # 使用者／系統層的 git 設定也不得影響 fixture（#30 verify R2 row 5：例如全域 core.excludesFile 含 `bin/`
  # 會讓 `git add bin/tool` 失敗）。GIT_CONFIG_GLOBAL 需要 git 2.32+，更舊的 git 忽略它——fixture 另外一律 `git add -f`
  # （預設的 ~/.config/git/ignore 不受 GIT_CONFIG_GLOBAL 影響）。
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
}

# $1 = 根目錄；$2 = 來源。印出排序後的紀錄（`<kind>\t<path>`，換行分隔）。
records_of() {
  local rec
  rec="$(mktemp "${WORK}/rec.XXXXXX")"
  enumerate "$1" "$2" "$rec" || return 1
  tr '\0' '\n' < "$rec" | LC_ALL=C sort
}

# $1 = 標籤；$2 = 期望（換行分隔、未排序亦可）；$3 = 實得。完整集合必須**逐字相等**。
expect_set() {
  local want
  want="$(printf '%s\n' "$2" | LC_ALL=C sort)"
  if [ "$want" != "$3" ]; then
    st_fail "$1——列舉的完整集合不符"
    diff <(printf '%s\n' "$want") <(printf '%s\n' "$3") | sed 's/^/    /' >&2 || true
    return 1
  fi
}

# $1 = 標籤；$2 = 期望訊息片段；其後 = 指令。指令必須非零，且 stderr 含該片段（紅得對不對也要驗）。
expect_red() {
  local label="$1" needle="$2" out
  shift 2
  if out="$("$@" 2>&1)"; then st_fail "${label}——應該紅卻回 0"; return 1; fi
  case "$out" in
    *"$needle"*) return 0 ;;
    *) st_fail "${label}——紅了，但不是因為「${needle}」："; printf '%s\n' "$out" | head -3 | sed 's/^/    /' >&2; return 1 ;;
  esac
}

# git 來源的 fixture（row 1(a)、6）：只看 tracked；extensionless shebang、tracked symlink、bats、fixture、
# 已刪除的 tracked 檔各一；完整集合逐字比對。另外在 --_selftest-git 子行程裡被重跑一次（row 4）。
st_git_source() {
  local g="$1/g" got
  mkdir -p "$g/bin" "$g/test/fixtures"
  printf '#!/usr/bin/env bash\necho ok\n'    > "$g/tracked.sh"
  printf '#!/usr/bin/env bash\necho ok\n'    > "$g/bin/tool"
  printf '#!/usr/bin/env python3\nprint(1)\n' > "$g/bin/pytool"
  printf 'print(1)\n'                        > "$g/mod.py"
  printf '#!/usr/bin/env bash\n@test x { :; }\n' > "$g/test/t.bats"
  printf '#!/usr/bin/env bash\necho ok\n'    > "$g/test/fixtures/bad.sh"
  printf '#!/usr/bin/env bash\necho ok\n'    > "$g/deleted.sh"
  printf '#!/usr/bin/env bash\necho ok\n'    > "$g/untracked-tool"
  printf '#!/usr/bin/env bash\necho ok\n'    > "$g/untracked.sh"
  ln -s bin/tool "$g/link"
  git -C "$g" init -q || { st_fail "git init 失敗"; return 1; }
  git -C "$g" add -f -- tracked.sh bin/tool bin/pytool mod.py test/t.bats test/fixtures/bad.sh deleted.sh link \
    || { st_fail "git add 失敗"; return 1; }
  rm "$g/deleted.sh"
  got="$(records_of "$g" git)" || { st_fail "git 來源列舉失敗"; return 1; }
  expect_set "git 來源（只看 tracked；extensionless shebang 必須在）" "$(printf '%s\t%s\n' \
    sh:ext tracked.sh  sh:shebang bin/tool  py:ext mod.py  py:shebang bin/pytool \
    skip:bats test/t.bats  skip:fixture test/fixtures/bad.sh  skip:symlink link  skip:missing deleted.sh)" "$got"
}

selftest() {
  local t="${WORK}/st" a got idx cp_idx out d
  scrub_git_env || return 1
  mkdir -p "$t"
  command -v shellcheck >/dev/null || { st_fail "shellcheck 不在 PATH（case 7 需要它）"; return 1; }

  # ── 0. bash 3.2 相容的最小靜態掃描（row 1 回歸護欄；CI 是 bash 5，跑不出 3.2 的 command not found）──
  #       只掃本檔的非註解行；樣式刻意拆字，免得掃到這一行自己。
  local b4
  b4="$(grep -nE '(^|[^[:alnum:]_])(map''file|read''array|co''proc)([^[:alnum:]_]|$)|(declare|local|typeset)[[:space:]]+-[[:alpha:]]*A|[$][{][[:alnum:]_]+(,,?|\^\^?)[}]|[&]>>|[|][&]' "$SELF_ABS" \
    | grep -vE '^[0-9]+:[[:space:]]*#' || true)"
  [ -z "$b4" ] || { st_fail_with "本檔用了 bash 4+ 才有的語法（macOS /bin/bash 3.2 會紅）：" "$b4"; return 1; }

  # ── 1. 分類規則（find 來源）：直譯器判定、env 選項與指派、排除規則，完整集合逐字比對 ──
  a="$t/a"
  mkdir -p "$a/bin" "$a/test/fixtures" "$a/tests/fixtures" "$a/eval/fixtures" "$a/lib/fixtures"
  printf '#!/usr/bin/env bash\necho ok\n'              > "$a/bin/env-bash"
  printf '#!/bin/bash\necho ok\n'                      > "$a/bin/bin-bash"
  printf '#!/bin/sh\necho ok\n'                        > "$a/bin/bin-sh"
  printf '#!/bin/sh -e\necho ok\n'                     > "$a/bin/bin-sh-e"
  printf '#!/bin/ksh\necho ok\n'                       > "$a/bin/bin-ksh"
  printf '#!/usr/bin/env dash\necho ok\n'              > "$a/bin/env-dash"
  printf '#! /bin/dash\necho ok\n'                     > "$a/bin/spaced-dash"
  printf '#!/bin/bash\r\necho ok\r\n'                  > "$a/bin/crlf-bash"
  printf '#!/usr/bin/env -S bash -e\necho ok\n'        > "$a/bin/env-S-bash"
  printf '#!/usr/bin/env -S FOO=bar bash\necho ok\n'   > "$a/bin/env-S-assign"
  printf '#!/usr/bin/env -S -u FOO bash\necho ok\n'    > "$a/bin/env-S-u"
  printf '#!/usr/bin/env -S -uFOO bash\necho ok\n'     > "$a/bin/env-S-u-attached"
  printf '#!/usr/bin/env -S --unset FOO ksh\necho ok\n' > "$a/bin/env-S-unset"
  printf '#!/usr/bin/env -S --unset=FOO sh\necho ok\n' > "$a/bin/env-S-unset-eq"
  printf '#!/usr/bin/env -S -C /tmp bash\necho ok\n'   > "$a/bin/env-S-C"
  printf '#!/usr/bin/env -S --chdir /tmp dash\necho ok\n' > "$a/bin/env-S-chdir"
  printf '#!/usr/bin/env -i bash\necho ok\n'           > "$a/bin/env-i"
  printf '#!/usr/bin/env -iS bash\necho ok\n'          > "$a/bin/env-iS"
  printf '#!/usr/bin/env -Sbash -e\necho ok\n'         > "$a/bin/env-S-attached"
  printf '#!/usr/bin/env --split-string=bash -e\necho ok\n' > "$a/bin/env-split-eq"
  printf '#!/usr/bin/env -S -- bash\necho ok\n'        > "$a/bin/env-S-dashdash"
  printf '#!/usr/bin/env -S -u bash zsh\necho ok\n'    > "$a/bin/env-u-eats-bash"
  printf '#!/usr/bin/env -S -C bash zsh\necho ok\n'    > "$a/bin/env-C-eats-bash"
  printf '#!/usr/bin/env -S SHELL=bash zsh\necho ok\n' > "$a/bin/env-assign-bash"
  printf '#!/usr/bin/env\n'                            > "$a/bin/env-bare"
  printf '#!/usr/bin/env bashful\n'                    > "$a/bin/not-bash"
  printf '#!/usr/bin/env python3\nprint(1)\n'          > "$a/bin/py"
  printf '#!/usr/bin/python3.11\nprint(1)\n'           > "$a/bin/py311"
  printf '#!/usr/bin/env -S PYTHONUTF8=1 python3 -u\nprint(1)\n' > "$a/bin/py-S"
  printf '#!/usr/bin/swift\nprint(1)\n'                > "$a/bin/swift"
  printf '#!/usr/bin/env node\n1\n'                    > "$a/bin/node"
  # row 4：判定不了 → error:shebang（不是 skip:shebang=<雜訊>）
  printf '#!/usr/bin/env -S "bash"\necho ok\n'         > "$a/bin/env-S-dquote"
  printf "#!/usr/bin/env -S 'FOO=a b' bash\\necho ok\\n" > "$a/bin/env-S-squote"
  # shellcheck disable=SC2016  # 故意：寫進 fixture 的字面 ${X}
  printf '#!/usr/bin/env -S ${X} bash\necho ok\n'      > "$a/bin/env-S-var"
  printf '#!/usr/bin/env -S -u X\\ Y bash\necho ok\n' > "$a/bin/env-S-escape"
  printf '#!/usr/bin/env -L root bash\necho ok\n'      > "$a/bin/env-L"
  printf '#!/usr/bin/env -Uroot bash\necho ok\n'       > "$a/bin/env-U-attached"
  printf '#!/usr/bin/env -X bash\necho ok\n'           > "$a/bin/env-unknown-opt"
  printf '#!/usr/bin/env -S bash -c "echo x"\necho ok\n' > "$a/bin/env-quote-after-interp"
  printf '#!/usr/bin/env -S "bash"\necho ok\n'         > "$a/test/fixtures/bad-quote"
  printf 'echo no shebang but .sh\n'                   > "$a/ext.sh"
  printf '#!/usr/bin/env bash\necho ok\n'              > "$a/ext.bash"
  printf 'print(1)\n'                                  > "$a/mod.py"
  printf '#!/usr/bin/env bats\n@test "x" { :; }\n'     > "$a/test/t.bats"
  printf '#!/usr/bin/env bash\n@test "x" { :; }\n'     > "$a/test/bash-shebang.bats"
  printf '#!/usr/bin/env bash\necho ok\n'              > "$a/test/fixtures/bad.sh"
  printf '#!/usr/bin/env bash\necho ok\n'              > "$a/test/fixtures/bad-noext"
  printf '#!/usr/bin/env bash\necho ok\n'              > "$a/tests/fixtures/bad.sh"
  printf 'print(1)\n'                                  > "$a/eval/fixtures/bad.py"
  printf '#!/usr/bin/env bash\necho ok\n'              > "$a/lib/fixtures/real.sh"
  printf 'plain text\n'                                > "$a/README"
  : > "$a/empty"
  ln -s bin/env-bash "$a/link-to-bash"
  ln -s bin "$a/link-to-dir"
  got="$(records_of "$a" find)" || { st_fail "find 來源列舉失敗"; return 1; }
  expect_set "分類規則（find 來源）" "$(printf '%s\t%s\n' \
    sh:shebang bin/env-bash  sh:shebang bin/bin-bash  sh:shebang bin/bin-sh  sh:shebang bin/bin-sh-e \
    sh:shebang bin/bin-ksh  sh:shebang bin/env-dash  sh:shebang bin/spaced-dash  sh:shebang bin/crlf-bash \
    sh:shebang bin/env-S-bash  sh:shebang bin/env-S-assign  sh:shebang bin/env-S-u  sh:shebang bin/env-S-u-attached \
    sh:shebang bin/env-S-unset  sh:shebang bin/env-S-unset-eq  sh:shebang bin/env-S-C  sh:shebang bin/env-S-chdir \
    sh:shebang bin/env-i  sh:shebang bin/env-iS  sh:shebang bin/env-S-attached  sh:shebang bin/env-split-eq \
    sh:shebang bin/env-S-dashdash \
    skip:shebang=zsh bin/env-u-eats-bash  skip:shebang=zsh bin/env-C-eats-bash  skip:shebang=zsh bin/env-assign-bash \
    skip:shebang=bashful bin/not-bash  skip:shebang=swift bin/swift  skip:shebang=node bin/node \
    py:shebang bin/py  py:shebang bin/py311  py:shebang bin/py-S \
    sh:ext ext.sh  sh:ext ext.bash  py:ext mod.py  sh:ext lib/fixtures/real.sh \
    skip:bats test/t.bats  skip:bats test/bash-shebang.bats \
    skip:fixture test/fixtures/bad.sh  skip:fixture test/fixtures/bad-noext  skip:fixture tests/fixtures/bad.sh \
    skip:fixture eval/fixtures/bad.py  skip:fixture test/fixtures/bad-quote \
    error:shebang bin/env-S-dquote  error:shebang bin/env-S-squote  error:shebang bin/env-S-var \
    error:shebang bin/env-S-escape  error:shebang bin/env-unknown-opt \
    sh:shebang bin/env-L  sh:shebang bin/env-U-attached  sh:shebang bin/env-quote-after-interp \
    skip:symlink link-to-bash  skip:symlink link-to-dir)" "$got" || return 1

  # ── 2. git 來源：只看 tracked、完整集合逐字比對（row 1(a)、6）──
  st_git_source "$t" || return 1

  # ── 3. 呼叫者的 GIT_* 不外洩：子行程帶著指向一份真 index 的 GIT_INDEX_FILE 跑 git 案例，那份 index 不得被動到（row 4）──
  if ! { git -C "$t" init -q idxsrc && printf 'x\n' > "$t/idxsrc/x" && git -C "$t/idxsrc" add -f x; }; then
    st_fail "準備 index 失敗"; return 1
  fi
  idx="$t/foreign-index"; cp_idx="$t/foreign-index.orig"
  cp "$t/idxsrc/.git/index" "$idx"; cp "$idx" "$cp_idx"
  if ! out="$(GIT_INDEX_FILE="$idx" "$BASH" "$SELF_ABS" --_selftest-git 2>&1)"; then
    st_fail_with "GIT_INDEX_FILE 外洩時 git 案例紅了：" "$(printf '%s\n' "$out" | head -5)"; return 1
  fi
  cmp -s "$idx" "$cp_idx" || { st_fail "呼叫者的 GIT_INDEX_FILE（${idx}）被自測改寫了"; return 1; }

  # ── 4. 護欄：空列舉、單一規則零命中、自我包含（含空字串）——各自以自己的訊息紅（row 1(b)(c)）──
  mkdir -p "$t/only-py" "$t/only-sh" "$t/ext-only" "$t/sb-only" "$t/both/bin"
  printf 'print(1)\n' > "$t/only-py/x.py"; printf '#!/usr/bin/env python3\n' > "$t/only-py/y"
  printf 'echo ok\n' > "$t/only-sh/x.sh"; printf '#!/bin/sh\necho ok\n' > "$t/only-sh/y"
  printf 'echo ok\n' > "$t/ext-only/x.sh"
  printf '#!/bin/sh\necho ok\n' > "$t/sb-only/y"
  printf 'echo ok\n' > "$t/both/x.sh"; printf '#!/bin/sh\necho ok\n' > "$t/both/bin/y"
  expect_red "sh 空列舉" "列舉出 0 支 shell" run_check "$t/only-py" find sh list x.sh || return 1
  expect_red "py 空列舉" "列舉出 0 支 python" run_check "$t/only-sh" find py list "" || return 1
  expect_red "只有副檔名命中" "shebang 規則命中 0 支" run_check "$t/ext-only" find sh list x.sh || return 1
  expect_red "只有 shebang 命中" "副檔名規則命中 0 支" run_check "$t/sb-only" find sh list y || return 1
  expect_red "必要路徑缺席" "列舉結果裡沒有 not-there.sh" run_check "$t/both" find sh list not-there.sh || return 1
  expect_red "必要路徑為空" "自我包含護欄沒有接上" run_check "$t/both" find sh list "" || return 1
  run_check "$t/both" find sh list x.sh >/dev/null 2>&1 || { st_fail "兩條規則都命中、自己也在卻紅了"; return 1; }
  #     row 4：shebang 判定不了 → 兩種語言都紅、訊息列出該檔（不是 skip 掉）
  mkdir -p "$t/errsb/bin"
  printf 'echo ok\n' > "$t/errsb/x.sh"; printf '#!/bin/sh\necho ok\n' > "$t/errsb/bin/y"
  printf '#!/usr/bin/env -S "bash"\necho ok\n' > "$t/errsb/bin/q"
  expect_red "shebang 判定不了（sh）" "無法判定直譯器" run_check "$t/errsb" find sh list x.sh || return 1
  expect_red "shebang 判定不了（py）" "無法判定直譯器" run_check "$t/errsb" find py list "" || return 1
  expect_red "shebang 判定不了：列出檔名" "error:shebang	bin/q" run_check "$t/errsb" find sh check x.sh || return 1

  # ── 5. 正式接線：plan 對本 plugin 目錄給出非空的自我路徑，它以 sh:ext 出現在真實列舉裡；
  #       `--list`（正式的 dispatch）也印出它（row 1(c)）──
  plan "$PLUGIN_DIR" 2>/dev/null || { st_fail "plan 在本 checkout 上失敗"; return 1; }
  [ -n "$PLAN_SELF" ] || { st_fail "plan 給出空的自我路徑"; return 1; }
  got="$(records_of "$PLAN_ROOT" "$PLAN_SRC")" || { st_fail "真實列舉失敗"; return 1; }
  printf '%s\n' "$got" | grep -qxF "sh:ext	${PLAN_SELF}" \
    || { st_fail "真實列舉（${PLAN_SRC}，${PLAN_ROOT}）裡沒有 ${PLAN_SELF}"; return 1; }
  out="$("$BASH" "$SELF_ABS" --list 2>/dev/null)" || { st_fail "--list 在本 checkout 上紅了"; return 1; }
  printf '%s\n' "$out" | grep -qxF "sh:ext	${PLAN_SELF}" || { st_fail "--list 沒印出 ${PLAN_SELF}"; return 1; }
  #     `--python` 真的切到 python（#30 verify R2 row 2(a)：先前沒有任何東西以 --python 跑 main）——
  #     每一行都是 py:* 或 skip:*、兩條規則各至少一行、沒有任何 sh:。
  out="$("$BASH" "$SELF_ABS" --python --list 2>/dev/null)" || { st_fail "--python --list 在本 checkout 上紅了"; return 1; }
  d="$(printf '%s\n' "$out" | grep -vE '^(py:(ext|shebang)|skip:[^	]+)	' || true)"
  [ -z "$d" ] || { st_fail_with "--python --list 印出非 python 的受檢行：" "$(printf '%s\n' "$d" | head -3)"; return 1; }
  printf '%s\n' "$out" | grep -q '^py:ext	' || { st_fail "--python --list 沒有 py:ext"; return 1; }
  printf '%s\n' "$out" | grep -q '^py:shebang	' || { st_fail "--python --list 沒有 py:shebang"; return 1; }

  # ── 5b. 排除清單真的印出來（row 2(b)：先前沒有斷言看 run_check 的輸出，`skip:*` 那一支可以整個拿掉）──
  #       git fixture（case 2）：list 與 check 兩種輸出都要逐行帶著 skip:<理由>。
  local want_skip
  want_skip="$(printf '%s\t%s\n' skip:bats test/t.bats skip:fixture test/fixtures/bad.sh skip:symlink link skip:missing deleted.sh)"
  out="$(run_check "$t/g" git sh list tracked.sh 2>&1)" || { st_fail "git fixture 的 list 紅了"; return 1; }
  got="$(printf '%s\n' "$out" | { grep '^skip:' || true; } | LC_ALL=C sort)"
  expect_set "list 印出的排除清單" "$want_skip" "$got" || return 1
  out="$(run_check "$t/g" git sh check tracked.sh 2>&1)" || { st_fail "git fixture 的 check 紅了"; return 1; }
  got="$(printf '%s\n' "$out" | sed -n 's/^  \(skip:.*\)$/\1/p' | LC_ALL=C sort)"
  expect_set "check 印出的排除清單" "$want_skip" "$got" || return 1
  #       skip:unreadable：root 讀得到任何檔（CAP_DAC_OVERRIDE），只能在非 root 下構造——CI runner 與開發機都不是 root。
  if [ "$(id -u)" -ne 0 ]; then
    mkdir -p "$t/unr/bin"
    printf '#!/usr/bin/env bash\necho ok\n' > "$t/unr/ok.sh"; printf '#!/bin/sh\necho ok\n' > "$t/unr/bin/ok"
    printf '#!/bin/sh\necho ok\n' > "$t/unr/bin/secret"; chmod 000 "$t/unr/bin/secret"
    out="$(run_check "$t/unr" find sh list ok.sh 2>&1)"; chmod 644 "$t/unr/bin/secret"
    printf '%s\n' "$out" | grep -qxF "skip:unreadable	bin/secret" || { st_fail "讀不到的檔沒有以 skip:unreadable 列出"; return 1; }
  else
    echo "shellcheck-all selftest: 以 root 執行——略過 skip:unreadable 子案例（root 構造不出讀不到的檔）" >&2
  fi

  # ── 6. 來源指令失敗必紅：假的 find／git 印出部分結果後 exit 1（row 3）──
  mkdir -p "$t/stub"
  printf '#!/bin/sh\nprintf "./x.sh\\000./bin/y\\000"\nexit 1\n' > "$t/stub/find"
  printf '#!/bin/sh\nprintf "x.sh\\000bin/y\\000"\nexit 1\n' > "$t/stub/git"
  chmod +x "$t/stub/find" "$t/stub/git"
  expect_red "find 失敗" "列舉來源失敗（find" env PATH="$t/stub:$PATH" "$BASH" "$SELF_ABS" --_run "$t/both" find sh list x.sh || return 1
  expect_red "git ls-files 失敗" "列舉來源失敗（git" env PATH="$t/stub:$PATH" "$BASH" "$SELF_ABS" --_run "$t/both" git sh list x.sh || return 1

  # ── 7. 工具的判定要傳出來：乾淨 → 0，有警告／語法錯 → 非零；python 不在工作樹留 __pycache__ ──
  mkdir -p "$t/clean/bin" "$t/dirty/bin" "$t/pyok/bin" "$t/pybad/bin"
  printf '#!/usr/bin/env bash\necho "ok"\n' > "$t/clean/ok.sh"; printf '#!/bin/sh\necho "ok"\n' > "$t/clean/bin/ok"
  # shellcheck disable=SC2016  # 故意：寫進 fixture 的字面 $1
  printf '#!/usr/bin/env bash\necho $1\n'   > "$t/dirty/warn.sh"   # SC2086
  printf '#!/bin/sh\necho "ok"\n' > "$t/dirty/bin/ok"
  printf 'x = 1\n' > "$t/pyok/ok.py"; printf '#!/usr/bin/env python3\ny = 2\n' > "$t/pyok/bin/ok"
  printf 'def (:\n' > "$t/pybad/bad.py"; printf '#!/usr/bin/env python3\ny = 2\n' > "$t/pybad/bin/ok"
  # row 7：受檢 repo 根目錄的 py_compile.py 不得遮蔽標準庫（它若被 import：留下記號並 exit 0 → 語法錯被判綠）
  printf 'import pathlib\npathlib.Path("SHADOWED").write_text("x")\nraise SystemExit(0)\n' > "$t/pybad/py_compile.py"
  run_check "$t/clean" find sh check ok.sh >/dev/null 2>&1 || { st_fail "乾淨的 script 被 shellcheck 判紅"; return 1; }
  if run_check "$t/dirty" find sh check warn.sh >/dev/null 2>&1; then
    st_fail "有 SC2086 的 script 被判綠——shellcheck 的非零沒有傳出來"; return 1
  fi
  run_check "$t/pyok" find py check "" >/dev/null 2>&1 || { st_fail "能編譯的 python 被判紅"; return 1; }
  if run_check "$t/pybad" find py check "" >/dev/null 2>&1; then
    st_fail "語法錯的 python 被判綠——py_compile 的非零沒有傳出來"; return 1
  fi
  [ ! -e "$t/pybad/SHADOWED" ] || { st_fail "受檢 repo 裡的 py_compile.py 遮蔽了標準庫（cwd 進了 sys.path）"; return 1; }
  d="$(find "$t/pyok" "$t/pybad" -name __pycache__ -print)"
  [ -z "$d" ] || { st_fail "py_compile 在受檢目錄留下 __pycache__：${d}"; return 1; }

  # ── 8. vendored：plugin 目錄在外層 repo 裡但本檔不被追蹤 → find 掃 plugin 目錄、不碰外層；
  #       被追蹤 → git 來源、根目錄是外層 repo。沒有任何 repo → find（row 7）──
  local o="$t/outer" v="$t/outer/vendor/plug" plain="$t/plain/plug"
  mkdir -p "$v/test" "$v/bin" "$plain/test" "$plain/bin"
  git -C "$t" init -q outer || { st_fail "git init outer 失敗"; return 1; }
  printf '#!/usr/bin/env bash\necho ok\n' > "$o/outer.sh"
  cp "$SELF_ABS" "$v/test/shellcheck-all.sh"; printf '#!/bin/sh\necho ok\n' > "$v/bin/tool"
  cp "$SELF_ABS" "$plain/test/shellcheck-all.sh"; printf '#!/bin/sh\necho ok\n' > "$plain/bin/tool"
  git -C "$o" add -f outer.sh || { st_fail "git add outer 失敗"; return 1; }
  out="$("$BASH" "$v/test/shellcheck-all.sh" --list 2>&1)" || { st_fail_with "vendored 副本紅了：" "$(printf '%s\n' "$out" | head -3)"; return 1; }
  case "$out" in *"視為 vendored 副本"*) ;; *) st_fail "vendored 副本沒有明說退回 find"; return 1 ;; esac
  got="$(printf '%s\n' "$out" | grep -E '^(sh|py|skip):' | LC_ALL=C sort)"
  expect_set "vendored 副本（只掃 plugin 目錄）" "$(printf '%s\t%s\n' sh:ext test/shellcheck-all.sh sh:shebang bin/tool)" "$got" || return 1
  git -C "$o" add -f vendor || { st_fail "git add vendor 失敗"; return 1; }
  out="$("$BASH" "$v/test/shellcheck-all.sh" --list 2>&1)" || { st_fail "被外層追蹤的副本紅了"; return 1; }
  got="$(printf '%s\n' "$out" | grep -E '^(sh|py|skip):' | LC_ALL=C sort)"
  expect_set "被外層追蹤（git 來源，外層頂層）" "$(printf '%s\t%s\n' sh:ext outer.sh sh:ext vendor/plug/test/shellcheck-all.sh sh:shebang vendor/plug/bin/tool)" "$got" || return 1
  #     row 3：index 損壞不是「沒追蹤」——必須紅，不得以 vendored 為由退回 find 拿 rc=0。
  cp "$o/.git/index" "$t/outer-index.bak"; printf 'garbage' > "$o/.git/index"
  expect_red "外層 index 損壞" "列舉來源失敗（git ls-files --error-unmatch" "$BASH" "$v/test/shellcheck-all.sh" --list || return 1
  cp "$t/outer-index.bak" "$o/.git/index"
  #     row 3：GIT_DIR 指錯也不是「不在 worktree」。
  expect_red "GIT_DIR 指錯" "列舉來源失敗（git rev-parse" env GIT_DIR="$t/no-such-git-dir" "$BASH" "$v/test/shellcheck-all.sh" --list || return 1
  #     無 repo：暫存目錄本身可能在某個 git worktree 裡（TMPDIR 指進 repo，row 6）——用 ceiling 把探索擋在 plugin 目錄。
  printf '#!/usr/bin/env bash\n@test x { :; }\n' > "$plain/test/t.bats"; ln -s bin/tool "$plain/link"
  out="$(GIT_CEILING_DIRECTORIES="$t/plain" "$BASH" "$plain/test/shellcheck-all.sh" --list 2>&1)" || { st_fail "無 repo 的副本紅了"; return 1; }
  case "$out" in *"不在 git worktree 裡"*) ;; *) st_fail "無 repo 的副本沒有明說退回 find"; return 1 ;; esac
  #     row 2(b)：正式 dispatch 的完整執行（不只 --list）也逐行印出排除清單。
  out="$(GIT_CEILING_DIRECTORIES="$t/plain" "$BASH" "$plain/test/shellcheck-all.sh" 2>&1)" || { st_fail_with "無 repo 副本的完整執行紅了：" "$(printf '%s\n' "$out" | tail -5)"; return 1; }
  got="$(printf '%s\n' "$out" | sed -n 's/^  \(skip:.*\)$/\1/p' | LC_ALL=C sort)"
  expect_set "完整執行印出的排除清單" "$(printf '%s\t%s\n' skip:bats test/t.bats skip:symlink link)" "$got" || return 1

  echo "shellcheck-all selftest ok: 本檔無 bash 4+ 語法（靜態掃描）、" \
    "分類（sh/bash/dash/ksh/python 直譯器、env 的選項與指派（含 BSD -L/-U）、bats/fixture/symlink 排除，完整集合逐字比對）、" \
    "shebang 判定不了（引號／跳脫／\$／未知 env 選項）→ error:shebang 且 run_check 紅、" \
    "git 來源只看 tracked（含 extensionless 與 tracked symlink）、呼叫者 GIT_INDEX_FILE 不被改寫、" \
    "空列舉／單一規則零命中／自我路徑缺席或為空各自以自己的訊息紅、本 checkout 的 plan 與 --list 含本檔、" \
    "--python --list 只有 py:*（兩條規則都有）、排除清單在 list／check／完整執行裡逐行印出（非 root 另驗 unreadable）、" \
    "find／git 來源失敗必紅、shellcheck 與 py_compile 的非零傳出、不留 __pycache__、repo 裡的 py_compile.py 不遮蔽標準庫、" \
    "vendored／無 repo（ceiling 隔離）退回 find、index 損壞與 GIT_DIR 指錯則紅而不退回"
}

# ── dispatch ────────────────────────────────────────────────────────────────────────────────────

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

main() {
  local lang=sh action=check
  case "${1:-}" in
    --selftest) selftest; return ;;
    --_selftest-git) scrub_git_env && mkdir -p "$WORK/st" && st_git_source "$WORK/st"; return ;;
    --_run) shift; run_check "$@"; return ;;   # 自測用：對指定根目錄／來源直接跑 run_check（row 3 的 PATH stub）
  esac
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --python) lang=py ;;
      --list) action=list ;;
      *) echo "用法：test/shellcheck-all.sh [--python] [--list] | --selftest" >&2; return 2 ;;
    esac
    shift
  done
  plan "$PLUGIN_DIR" || return 1
  run_check "$PLAN_ROOT" "$PLAN_SRC" "$lang" "$action" "$PLAN_SELF"
}

main "$@"
