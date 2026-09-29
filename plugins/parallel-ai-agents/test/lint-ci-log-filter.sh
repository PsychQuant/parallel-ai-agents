#!/usr/bin/env bash
# 機械護欄（#33 verify R15 logic L-2 / security S-3 / requirements F2 / regression F5）：
# `.github/workflows/test.yml` 裡**每一個** `run:` step 都必須明示它的 step log 怎麼處理 PR 可控文字——
#   (a) run 區塊裡有 `neutralise.py`（經 validate.py 的 LineSanitiser 那一份中和實作），或
#   (b) step 名稱那一行**之後、run: 之前**（或 run 區塊內）有一行 `# LOG-FILTER: <理由>` 註解，明示不過濾與為什麼
#       （封閉的兩種理由：`in-process` = 該程式自帶 LineSanitiser；`none — …` = 執行 PR 自己的程式碼／只印工具版本，
#       stdout 本來就由 PR 決定或不含 PR 文字）。
# 為什麼：R14 把「哪些 step 會 echo fork 可控文字」寫成散文列舉，R15 四個 lens 各自找到列舉外的 step
# （shellcheck、lint-*、整個 macOS job）——散文列舉在第一輪就不封閉。與 lint-bats / lint-changelog-counts 同形：
# 規則寫成機器擋，且 `--selftest` 先證明它抓得到。
#
# **守備範圍（明寫，R20 security S-3）**：只看 `.github/workflows/` 底下的 workflow。composite action
# （`.github/actions/*/action.yml`）的 `run:` step 會在同一個 job log 裡執行、對本 lint 隱形。今日 latent
# （本 repo 沒有 `.github/actions/`）。**刻意不擴大 glob**：composite action 的 step 語意與 workflow 不同
# （沒有 job、`shell:` 必填），硬套同一套白名單會產生假紅；真的開始用 composite action 時，該做的是為
# 它寫一份自己的規則，不是把這一支的守備範圍偷偷放大。
#
# 用法：test/lint-ci-log-filter.sh --strict [workflow.yml…]   **檢查真的 workflow 用這個**（CI 與 run.sh 都是）；
#                                                             預設 ../../.github/workflows/*.yml *.yaml（全部 workflow）
#       test/lint-ci-log-filter.sh [workflow.yml…]            預設模式：fixture 與產生語料用，量的是 lint 與 bash 的詞法對帳，
#                                                             **假設 shell 是 bash**、不要求 pipefail 與群組形式
#       test/lint-ci-log-filter.sh --selftest
#       test/lint-ci-log-filter.sh --check-compgen            PATH 上的 bash 的 `compgen -b`／`-k` 必須 ⊆ FL_BUILTINS ∪ FL_KEYWORDS
#       檔名請給絕對路徑或相對於 plugin 目錄的路徑：本 lint 先 `cd` 到 plugin 目錄，找不到檔案回 rc=2（不是 pass）。
# **兩種模式從 R42 起是兩套判準**（#33 verify R41）：兩者共用 YAML 的白名單解析與 `shell_scan`（先跑、看不懂就 PARSE）。之後——
#   · `--strict`：整條規則鏈是 `flat_step_rules`。靠管線過濾的 step 用**正面文法**：只收點名的形狀，文法的補集一律 RULE
#     （產生式與已知限制見「`--strict` 的正面文法」一節）；宣告了 `# LOG-FILTER:` 的 step 只在觸發時（寫出來的管線、提到
#     `$GITHUB_ENV`／`$GITHUB_PATH`）套用同一套產生式。
#   · 預設模式：R1（過濾或宣告）、fd 流向（`_analyse`）、啟動時讀的 env 鍵、非字面的 runner 運算式。**不檢查** `$GITHUB_ENV`／
#     `$GITHUB_PATH` 的寫入（R40 的 `github_env_write` 兩種模式共用，R42 隨 pipefail 模擬一起刪除），也不模擬 pipefail。
# 神諭（test/oracle.py）只在它自己用的 bash 落在下面這個集合時才對帳——詞法模型（bash 5.3 的 `${ cmd; }`、`FL_BUILTINS`／`FL_KEYWORDS`）
# 是對這些版本寫的（R42，#33 verify R41 第 13 列）。CI 的 ubuntu 是 5.2、macOS 與本機是 5.3。
# ORACLE-BASH-SUPPORTED: 5.2 5.3
# **兩種模式的取捨（#33 verify R34 放行條件第 5 條的偏離，R36 第 25 列要求寫在這裡）**：非 bash 的 shell（`sh`、`pwsh`、
# 帶白名單外選項的樣板）、container job、Windows／運算式 runs-on 只在 `--strict` fail-closed。R35 第一版在預設模式也套用，
# 合成 A 語料 959 個 base-綠檔翻紅一大批（R35 寫 290；R36 requirements 按規則重量：shell 值那條 75 檔、container／Windows
# 沒寫 shell 那條 223 檔，聯集 268——多數來自第 5 條沒要求的後者）。預設模式服務的是詞法量測、不是 CI 的寫法規範，
# 所以 shell 規則只放在 `--strict`；而 CI 與 run.sh 對真 workflow 一律用 `--strict`，第 5 條要的保護在那裡。
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  # R22 裁決 3／5：selftest 現在驗**四件**（第四件是 R42 加的），不只「有沒有紅」。
  #   (1) 每個 fixture 自己用 `# EXPECT:` 宣告它該是 pass／rule-red／parse-red，實測必須相符。
  #       為什麼要分辨兩種紅：22 個 bypass fixture 裡有 8 個**只靠 parse-reject 變紅**，而
  #       parse-reject 正是修誤擋必須放寬的機制——分不出來，就等於「修誤擋會靜默重開繞過」。
  #   (2) **正向 fixture**（`good-*`）：先前 22 個 fixture 全是負向，一個都沒有證明它放得過好輸入。
  #       誤擋 26 個合法 workflow 中的 20 個，正是這個不對稱的必然結果。
  #   (3) bypass fixture 加 `--require-run-steps`，保留原本的 vacuity 保護（正式執行時不再套用，
  #       因為純 `uses:` workflow 沒有 run step 是合法的）。
  #   (4) R42（#33）：`--strict` 的正面文法把 FL_BUILTINS ∪ FL_KEYWORDS 裡的名字當成 bash 的 builtin／保留字、不在 FL_INERT 就拒絕；
  #       那兩份集合抄自 bash 5.3 的 `compgen -b`／`compgen -k`。PATH 上的 bash（CI 上是 ubuntu 那一支）若多列出一個名字，
  #       那個名字會被當成外部命令收下——所以每次 selftest 都拿 PATH 上的 bash 重比一次（`--check-compgen`，只查
  #       「bash 列出的 ⊆ 集合」這個方向：集合多一個名字只會多一個誤擋）。
  shopt -s nullglob
  fail=0; n_pass=0; n_rule=0; n_parse=0; n_msg=0; n_each=0
  if ! cg=$(bash test/lint-ci-log-filter.sh --check-compgen 2>&1); then
    printf 'lint-ci-log-filter selftest FAILED: %s\n' "${cg}" >&2
    fail=1
  fi
  # R42（opsweep）：`--check-compgen` 的診斷（bash 版本、bash 自己跑不起來時的 stderr）用**假 bash**釘住——真的 bash 只會走到「一切正常」
  # 那條路，版本字串與 rc≠0 的訊息從來沒有東西看過。假 bash 只放在 `--check-compgen` 這一個子行程的 PATH 最前面；跑 lint 的仍是真的 bash。
  realbash=$(command -v bash)
  fakebin=$(mktemp -d)
  # 三種假 bash：(1) 印出版本與一個不在集合裡的名字、(2) 版本行是空的、(3) 以 rc=3 結束且 stderr 前後帶空白
  for spec in "9.9.9-fake|printf '9.9.9-fake\\nzzz-not-a-builtin\\n'|bash 9.9.9-fake 列出的 \`zzz-not-a-builtin\`" \
              "empty-version|printf '\\nzzz-not-a-builtin\\n'|bash ? 列出的 \`zzz-not-a-builtin\`" \
              "rc3|printf '  boom  \\n' >&2; exit 3|rc=3：boom"; do
    IFS='|' read -r _label body want <<< "${spec}"
    printf '#!/bin/sh\n%s\n' "${body}" > "${fakebin}/bash"
    chmod +x "${fakebin}/bash"
    got=$(PATH="${fakebin}:${PATH}" "${realbash}" test/lint-ci-log-filter.sh --check-compgen 2>&1 || true)
    case "${got}" in
      *"${want}"*) ;;
      *) echo "lint-ci-log-filter selftest FAILED: 假 bash（${_label}）的 --check-compgen 輸出沒有「${want}」" >&2
         printf '%s\n' "${got}" | head -2 >&2; fail=1 ;;
    esac
  done
  rm -rf "${fakebin}"
  for f in test/fixtures/ci-log-filter-*.yml; do
    want=$(sed -n 's/^# EXPECT: //p' "$f" | head -1)
    if [ -z "${want}" ]; then
      echo "lint-ci-log-filter selftest FAILED: ${f} 沒有 EXPECT 宣告（pass / rule-red / parse-red）" >&2
      fail=1
      continue
    fi
    # `A && B || C` 是 SC2015，而且 R15 就是這樣讓 CI 紅的——一律用 if/then。
    # `# LINT-ARGS:` 讓 fixture 指定模式（R35：`--strict` 是 CI 對真 workflow 用的模式，規則比預設多兩條）
    read -r -a extra <<< "$(sed -n 's/^# LINT-ARGS: //p' "$f" | head -1)"
    if [ "${want}" = "pass" ]; then
      if out=$(bash test/lint-ci-log-filter.sh "${extra[@]+"${extra[@]}"}" "$f" 2>&1); then got=pass; else got="rc=$?"; fi
    else
      if out=$(bash test/lint-ci-log-filter.sh --require-run-steps "${extra[@]+"${extra[@]}"}" "$f" 2>&1); then
        got=pass
      else
        case "$out" in
          *": RULE: "*)  got=rule-red ;;
          *VACUOUS*)     got=vacuity ;;
          *": PARSE: "*) got=parse-red ;;
          *)             got=unknown-red ;;
        esac
      fi
    fi
    if [ "${got}" != "${want}" ]; then
      echo "lint-ci-log-filter selftest FAILED: ${f} 宣告 ${want}，實測 ${got}" >&2
      printf '%s\n' "$out" | head -2 >&2; fail=1; continue
    fi
    # R37：`# EXPECT-MSG:`（可多行）斷言**訊息內容**——每一行都必須以子字串出現在輸出裡。
    # 為什麼：類別對了不代表訊息對。`--verify-expected` 比對整段 stderr，推翻了「只改訊息文字 ⇒ 等價」
    # 這類理由（`set -x` 印成「開了 verbose」也照樣 rule-red）；而子 shell `-o xtrace` 的訊息實際印成
    # `-oo xtrace`，正是因為沒有任何一張 fixture 看訊息。
    msg_bad=""
    while IFS= read -r m; do
      case "$out" in *"$m"*) ;; *) msg_bad="$m"; break ;; esac
    done < <(sed -n 's/^# EXPECT-MSG: //p' "$f")
    if [ -n "${msg_bad}" ]; then
      echo "lint-ci-log-filter selftest FAILED: ${f} 的輸出沒有 EXPECT-MSG「${msg_bad}」" >&2
      printf '%s\n' "$out" | head -2 >&2; fail=1; continue
    fi
    if grep -q '^# EXPECT-MSG: ' "$f"; then n_msg=$((n_msg+1)); fi
    # R42（opsweep `--since 45dee04`）：多 step 的 fixture 只判「整張紅」時，某個守衛被拿掉、放行了其中幾步，只要還有一步被別的
    # 規則擋下，selftest 照樣綠——`bypass-r42-ghenv`（42 步）與 `bypass-r42-pf-outside-grammar`（36 步）上的 `_fl_command`
    # 存活都是這個形狀。檔頭寫 `# EXPECT-EACH-STEP: rule-red` 的 fixture，每一個 `- name:` 那一行都要有自己的 `:行號: RULE:`
    # （lint 把 step 的 RULE 印在 step 的起始行）。
    if grep -q '^# EXPECT-EACH-STEP: rule-red$' "$f"; then
      n_each=$((n_each+1))
      while IFS=: read -r ln _; do
        case "$out" in *":${ln}: RULE: "*) ;; *) msg_bad="第 ${ln} 行"; break ;; esac
      done < <(grep -n '^ *- name:' "$f")
      if [ -n "${msg_bad}" ]; then
        echo "lint-ci-log-filter selftest FAILED: ${f} 宣告 EXPECT-EACH-STEP，${msg_bad}的 step 沒有自己的 RULE 行" >&2
        fail=1; continue
      fi
    fi
    case "${want}" in
      pass)      n_pass=$((n_pass+1)) ;;
      rule-red)  n_rule=$((n_rule+1)) ;;
      parse-red) n_parse=$((n_parse+1)) ;;
    esac
  done
  # R24 regression F9：門檻寫成 `>=` 而實際值更高時，那個差額**沒有網**——刪掉一個 fixture 仍然綠。
  # 三個門檻一律改成**等於實測值**：要加 fixture 就同步改這裡，讓「少了一個」立刻紅。
  if [ "${n_pass}" -ne 268 ]; then
    echo "lint-ci-log-filter selftest FAILED: 正向 fixture 是 ${n_pass} 個，預期恰好 268（改動 fixture 請同步改這個數字）" >&2
    fail=1
  fi
  if [ "${n_rule}" -ne 454 ]; then
    echo "lint-ci-log-filter selftest FAILED: rule-red 是 ${n_rule} 個，預期恰好 454" >&2
    fail=1
  fi
  if [ "${fail}" -ne 0 ]; then exit 1; fi
  if [ "${n_parse}" -ne 153 ]; then
    echo "lint-ci-log-filter selftest FAILED: parse-red 是 ${n_parse} 個，預期恰好 153（先前這一類完全沒有下限）" >&2
    exit 1
  fi
  if [ "${n_msg}" -ne 65 ]; then
    echo "lint-ci-log-filter selftest FAILED: 帶 EXPECT-MSG 的 fixture 是 ${n_msg} 張，預期恰好 65" >&2
    exit 1
  fi
  if [ "${n_each}" -ne 11 ]; then
    echo "lint-ci-log-filter selftest FAILED: 帶 EXPECT-EACH-STEP 的 fixture 是 ${n_each} 張，預期恰好 11" >&2
    exit 1
  fi
  echo "lint-ci-log-filter selftest ok: ${n_pass} 正向通過、${n_rule} 條規則紅、${n_parse} 條解析紅、${n_msg} 張訊息斷言（來源逐一比對相符）、${n_each} 張逐步斷言；${cg}"
  exit 0
fi

# R16 DA-4：守備目標不寫死單檔——`.github/workflows/` 底下每一份 workflow 都檢查（新增第二份 workflow 不會漏）。
# `--require-run-steps` 是給 selftest 用的旗標（正式執行時純 `uses:` workflow 沒有 run step 是
# 合法的）。要在「檔案存在」檢查**之前**把它剝掉，否則它會被當成一個不存在的檔名。
# R42（#33）：單獨一個 `--check-compgen` 是 selftest 的一項（見 Python 端 `_fl_compgen_problems`）：只比對 PATH 上的 bash 列出的
# builtin／保留字與文法的兩份集合，不讀任何 workflow——所以不走下面的檔案解析，沒有 .github/ 的 plugin cache 副本也跑得了。
# 跟其他參數一起給就不是這個模式：它會被當成檔名、照「指定的檔案不存在」回 rc=2。
if [ $# -eq 1 ] && [ "$1" = "--check-compgen" ]; then
  flags=(--check-compgen); files=()
else
  flags=(); args=()
  for a in "$@"; do
    case "$a" in --require-run-steps|--strict) flags+=("$a") ;; *) args+=("$a") ;; esac
  done
  set -- "${args[@]+"${args[@]}"}"
  if [ $# -gt 0 ]; then files=("$@"); else files=(../../.github/workflows/*.yml ../../.github/workflows/*.yaml); fi
  # `*.yaml` 沒有檔案時 glob 會留字面——過濾掉不存在的（R17 logic L-7／security S-1：GitHub 也執行 .yaml）
  # 明確給定的檔案**不得**靜默換掉：傳一個不存在的路徑先前會落回預設的 test.yml，於是
  # 「我驗過那個 fixture 了」其實驗的是別的檔（R19 自查；同 repo 已有數個同形前例）。
  if [ $# -gt 0 ]; then
    missing=(); for f in "${files[@]}"; do [ -f "$f" ] || missing+=("$f"); done
    if [ ${#missing[@]} -gt 0 ]; then
      echo "lint-ci-log-filter: 指定的檔案不存在：${missing[*]}（cwd=${PWD}）—— 不會改去檢查別的檔" >&2
      exit 2
    fi
  else
    existing=(); for f in "${files[@]}"; do [ -f "$f" ] && existing+=("$f"); done; files=("${existing[@]}")
  fi
  # R16 logic L-2：非 monorepo 佈局（plugin cache 副本）沒有 .github/ —— 先前裸 traceback 並讓 run.sh 整支中止。
  if [ ! -f "${files[0]}" ]; then
    echo "lint-ci-log-filter: 找不到 ${files[0]}（非 monorepo 佈局？）—— 這條 lint 本次無法跑" >&2
    exit 2
  fi
fi
python3 - "${flags[@]+"${flags[@]}"}" "${files[@]+"${files[@]}"}" <<'PY'
# ── 白名單解析器（R18：四個 lens + DA 去重後仍有 7 個互不相同的根因）──────────────────────
# R15–R17 三輪都在加「拒絕這種寫法」的特例，而每一輪的下一輪都找得到新的寫法。R18 四份 findings
# 與 DA 的共同結論：**這是黑名單，而合法 YAML 比任何手寫黑名單大。** 所以改成相反的方向：
#   只認明確列出的結構，**其餘一律 fail-loud**（印行號與原因、rc=1，絕不靜默放行）。
#
# 七個根因裡有四個源自同一件事：**沒有正確消化 block scalar**。`env: |` 的內容裡寫一行
# `run: … | python3 neutralise.py`、或任何較早的 key 的 scalar 裡寫一行 `- `，前一版都會把那些
# 內容當成 key 或清單項。這一版把 block scalar 的內容當成**不透明文字**，結構上不可能再被誤讀。
# 另外三個是 key 的形式（`run :` 冒號前空白、`"\x72un":` 雙引號跳脫、`? run` 顯式 key）——
# 一個只認 plain key 的正規式把它們一起擋掉，它們不再是各自要處理的特例。
#
# 已知限制（明寫，不要靠讀者推論）：
#   · `# LOG-FILTER:` 寫在 `run:` 的 block scalar 內是**合法的**（本檔 header 明文允許；repo 裡
#     有兩個真實指令就是這樣寫的）。它是自我宣告，lint 不查證該程式真的自帶 LineSanitiser。
#   · 本 lint 不是 YAML 解析器，它解析的是這個 repo 實際用到的子集；子集之外一律拒絕而不是猜。
import re, sys

STEP_KEYS = {"id", "if", "name", "uses", "run", "shell", "env", "with",
             "working-directory", "continue-on-error", "timeout-minutes"}
KEY_RE = re.compile(r"^(\s*)([A-Za-z][A-Za-z0-9_-]*):(?:\s(.*))?$")   # plain key；冒號前不得有空白
SEQ_RE = re.compile(r"^(\s*)-(?:\s(.*))?$")
# R22 regression R-1 / requirements F-1：YAML 的 block scalar header 允許**兩種指示子順序**
# （`|2-` 與 `|-2` 都合法）。前一版只認 chomping 在前，於是 `name: |2-` 讓那段 scalar 不被視為
# 不透明內容、裡面的 `# LOG-FILTER:` 就放行了整個 step。`ff0f215` 也有這個洞——它是這一族未關閉
# 的成員，不是 R21 的回歸。
# 指示子 1-9；`|0`／`|10` 是 YAML 錯誤。**兩個 group 就是縮排指示子**（`|2-` 與 `|-2` 兩種順序都合法），
# 呼叫端用它們取值——**不得對整個標頭搜數字**：`BLOCK_SCALAR_RE` 自己允許行尾註解，而註解裡的數字
# （`run: | # see issue 9`）會被搜成指示子，於是一個合法又合規的 workflow 由綠翻紅、
# 訊息還捏造一個不存在的 PyYAML ParserError（R30 MB-1，四條 leg 各自獨立提出）。
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:([1-9])[+-]?|[+-]([1-9])?)?\s*(#.*)?$")
# R24 DA-3 R3：`||` 是**邏輯或**不是管線——`echo x || python3 …neutralise.py` 在 `echo` 成功時
# 後者**從未執行**，而前一版把它算成「已過濾」。反向，`|&`（bash 的 stderr 管線）是**真的**
# 管線卻被誤擋。兩個方向各一個 fixture（`bypass-or-operator` / `good-pipe-stderr`）。
# R30 H-6：管線的左邊**必須有東西**。邏輯行開頭的 `|` 在 bash 是語法錯誤（前一個命令已經印出去了、
# 這一行根本沒跑），而前一版的 `(?<!\|)\|` 在字串開頭同樣成立 → 把一個會洩漏的 step 算成「已過濾」。
# `[^|\s]` 同時擋掉 `||`（左邊是 `|`）與行首（左邊沒有字元）。
# R37 修法（#33 verify R36 第 15 列）：`[^|\s]` 太寬——`;`、`&`、`(` 都不是「命令的一部分」，是**分隔字元／
# 開括號**，它們前面沒有命令。`true ;|& python3 …`（`;` 後面直接接管線）、`true &&` 換行 `|& python3 …`
# （`&&` 續行後直接接管線）在 bash 都是語法錯誤——管線左邊是空的，根本沒有命令可以接。前一版仍判「已過濾」
# 是誤判：`;`／`&`／`(` 本身也滿足 `[^|\s]`。收窄成 `[^|\s;&(]`：合法的管線左邊（命令名、引號收尾、
# `)`／`}` 收尾一個 subshell／group 的輸出、數字、`2>&1` 的 `1`……）都不在這個排除集合裡，不受影響。
# **右半邊照 bash 的「一個詞」**（#33 verify R37 合併時協調者發現）：前一版路徑寫 `\S*`、結尾寫 `(\s|$)`，兩端都不是
# bash 的詞界。(1) `\S*` 跨過命令分隔字元：`| python3 -mquopri;scripts/neutralise.py` 在 bash 是「管線接到
# `python3 -m quopri`，再另跑一個命令」，quopri 把 PR 文字幾乎原樣印出——前一版判「已過濾」（繞過，
# `bypass-r37m-neutralise-path-spans-*` 三張，一個分隔字元一張）。(2) 結尾只認空白：`neutralise.py;`、`&&`、`||`、`)`、
# `|`、`>`、反引號、`&` 緊接在後都是 bash 的詞尾，前一版判「沒有經 neutralise.py」（誤擋，`good-r37m-neutralise-glued-follower`
# 與 `-unobservable` 兩張；後者是神諭量不到的四種寫法）。
# 兩端現在都用 bash 的 metacharacter 當詞界；`(` 不算詞尾（`neutralise.py(` 是語法錯誤，`bypass-r37m-neutralise-glued-paren`），
# 一般字元也不算（`neutralise.pyc` 是另一個檔）。後者沒有 fixture：神諭的環境裡那個檔不存在、python3 對 stdout 什麼都不印（stderr 仍會印出 can't open file 的錯誤），
# 神諭會把 lint 的 RULE 判成誤擋——這一格神諭在原理上量不了。`(` 那張已經殺得到「拿掉詞尾判定」的突變。
PIPED_RE = re.compile(r"[^|\s;&(]\s*\|(?!\|)&?\s*python3\s+[^\s;&|()<>`]*neutralise\.py(?=[\s;&|)<>`]|$)")
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")
# **fd 流向、`--strict` 的 `2>&1`、pipefail、shell 樣板**這四條規則不在這裡用正規式寫——它們讀的是 run 區塊的**結構**
# （詞、重導向、管線的每一段、群組、`case`），見 `shell_scan()` 之後的「規則層的詞法」一節（#33 verify R36 第 3、4、8、9、22 列）。
# R35 在這裡的六條正規式（`FD_RE`、`STRICT_NEUT_RE`、`PIPEFAIL_RE`、`ANY_PIPE_RE`、`BASH_SHELL_RE`＋`XTRACE_OPT_RE`）是拼法清單，
# R36 在其中五條（`XTRACE_OPT_RE` 除外）上都找到作者沒點名的相鄰輸入，所以整組換掉。
# **extglob 改變 bash 的詞法**（#33 verify R36 第 17 列；`shell_scan()` 已知不涵蓋第三組第 4 條，見下）：
# `shopt -s extglob` 之後 `@(`、`!(`、`+(`、`?(`、`*(pattern-list)` 都是合法語法，`(` 不再只是 subshell／
# 命令替換的開括號。本掃描器完全沒有模擬這套額外詞法，continuing 會把 `@(x 2>&1| python3 …)` 的 `(` 讀成
# 普通字元、內容照樣被掃成 code——`shell_scan()` 偵測到 `shopt -s extglob`（或多個 shopt 選項一起下、
# extglob 排在其他選項後面，如 `shopt -s nullglob extglob`）就整個 run 區塊 fail-closed PARSE，不猜語法。
EXTGLOB_RE = re.compile(r"\bshopt\s+-[A-Za-z]*s[A-Za-z]*\s+(?:\S+\s+)*extglob\b")


def yaml_split_comment(line):
    r"""把**一行 YAML** 切成（引號挖空後的程式碼半邊, YAML 註解半邊）。

    **這支只懂 YAML 的規則，不懂 shell 的**（R24 DA-3／Codex 第 2 條）。YAML 的 quoting 是資料
    表示層、shell 的是解碼後命令的語法層，兩者不可混用：前一版把同一支拿去切 `run:` 區塊，於是
    (a) 跨行引號與 heredoc 切錯、(b) `\"` 逃脫沒處理、(c) `;#` 這種 shell 註解看不見。
    `run:` 區塊現在改由 `shell_scan()` 處理，那支跨行、懂反斜線、懂 heredoc、用 shell 的註解規則。

    R22 的 meta 根因（requirements F-1/F-2、logic、Codex #1 獨立收斂）：`ok = (PIPED_RE …)` 與
    `(LOGFILTER_RE …)` 是**兩個判斷**，R21 只把右邊白名單化。左邊對原始行文字搜尋，於是
    「提到管線」與「真的經過管線」分不開——YAML 行尾註解、shell 註解、字串裡寫一句話，
    三者都算「已過濾」。而 `COMMENT` 的分類又排在白名單之上，只看 `strip()` 是否以 `#` 開頭，
    所以 `# name: |2-` 繞過的不是白名單本身、是它前面那道分類（requirements 的控制組：拿掉那個
    `#` 就變 rc=1 並印「本 lint 不解析這一行」——**白名單本來抓得到**）。

    修法是**一個抽取函式、兩個述詞各讀自己那一半**：管線判定只看會被執行的部分，`# LOG-FILTER:`
    判定只看不會被執行的部分。兩者不可能再對同一段文字得出相反的結論。

    規則（**只對 YAML 這一層成立，不得拿去切 shell**——那句全稱宣稱是 R24 DA-3 點名為假的那一句，
    本輪刪除）：引號外、位於行首或前面是空白的 `#` 起到行尾是 YAML 註解。引號內的內容**整段挖空**
    （保留引號與長度）。`run:` 區塊的 shell 由 `shell_scan()` 處理，那支的規則與這支**不同**。
    """
    code, comment, i, quote = [], "", 0, None
    while i < len(line):
        ch = line[i]
        if quote:
            if quote == '"' and ch == "\\":
                code.append("  "); i += 2; continue    # R28 D8b：`\"` 是逃脫不是收尾（`["a\"b:c"]`）；行尾的 `\` 讓 i 越界只是結束迴圈
            code.append(" " if ch != quote else ch)      # 引號內容挖空，引號本身保留
            if ch == quote:
                quote = None
            i += 1; continue
        if ch in ("'", '"'):
            quote = ch; code.append(ch); i += 1; continue
        prev = line[i - 1] if i else " "            # 行首視同前面是空白（R29 opsweep：寫成 `i == 0 or …` 的兩個運算元都證不了）
        if ch == "#" and prev.isspace():
            comment = line[i:]; break
        code.append(ch); i += 1
    return "".join(code), comment


# `#` 只在**詞首**起註解：行首、或前一個字元是空白／shell metacharacter。
# R30 H-4：反引號**開啟一個新的命令上下文**，所以它後面是詞首——bash 對 `` `#…` `` 起註解而前一版不起，
# 於是註解裡的 `| python3 …neutralise.py` 被當成真管線放行。反引號不是 POSIX metacharacter，
# 但在「下一個字元是不是詞首」這個問題上它的作用與 `(` 相同，所以列進來。
SHELL_WORD_BREAK = " \t;&|()<>`"
# **分隔字詞的詞尾判定不能用上面那個集合**（#33 verify R32：logic L-1／DA-3）。
# `SHELL_WORD_BREAK` 是為了回答「`#` 在不在詞首」而定義的，R30 還刻意為那個問題把反引號加進去；
# 拿它來切 heredoc 的分隔字詞就錯了——bash 在 `` ` `` 與 `$(`／`)` 上**不**斷詞，那些是詞的一部分。
# 用 bash 自己的 EOF 警告讀出它要的終止字（實測 bash 5.3）：
#   `cat <<EOF`x``     → 需要「EOF`x`」      （前一版讀成 `EOF`）
#   `cat <<EOF$(x)`    → 需要「EOF$(x)」     （前一版讀成 `EOF$`）
#   `cat <<`x`EOF`     → 需要「`x`EOF」      （前一版 delim 為空 ⇒ 根本不登記 heredoc）
# 終止字比 bash 短 ⇒ heredoc 提早結束 ⇒ 資料變 code ⇒ 假管線放行＝繞過。
# **但 `(` `)` 要留在集合裡**（#33 verify R34：logic F2／regression H-1／DA G-A）。R33 第一版把它們跟反引號一起
# 拿掉，理由只涵蓋反引號與 `$(`——而 `$(` 在分隔字裡已改走 fail-closed PARSE，那條理由不存在了；單獨的 `(`、`)`
# 是 bash 的 metacharacter、會斷詞：`(cat <<EOF)` 的終止字是 `EOF`（實測 bash 5.3），不是 `EOF)`。
# 終止字比 bash **長**同樣是繞過：bash 已經當 code 的那一段可以開自己的 heredoc，把 lint 認得的終止行收成資料
#（`bypass-heredoc-delim-close-paren`）；誤擋方向是 `good-heredoc-delim-subshell-paren`。
# 所以方向論證「比 bash 長只會誤擋」不成立——兩個方向都要精確。
DELIM_WORD_BREAK = " \t;&|()<>"
# **命令位置的觸發字元**（R37，`shell_scan()` 的 `cmd_pos` 用它維護；不含關鍵字，關鍵字另外整段消費）：
# `;`、`&`（含 `&&` 裡的每一個 `&`）、`|`（含 `||`／`|&` 裡的每一個 `|`）、`(`（含 `((`／`$(` 開啟時已各自處理，
# 這裡補的是落到逐字元 fallthrough 的裸 `(`）**無條件**把 `cmd_pos` 設成 True；`!`、`{` 不對稱——只在
# `cmd_pos` 已是 True 時依詞尾條件決定要不要保留（`cmd_pos = cmd_pos and 詞尾落在空白／行尾`），本身
# 從不會把 False 變成 True。`)`／`}` 收尾**不**在這裡——收尾一個 subshell／group 之後不是自動的命令
# 位置，要等下一個分隔字元。
CMD_POS_CHARS = ";&|(!{"


def yaml_decode_scalar(v):
    r"""把 YAML 的引號純量解碼成 runner 實際拿到的字串；不是引號純量就原樣回傳。

    R24 Codex 第 2 條：`run: "echo hi | python3 …neutralise.py"` 是合法寫法，runner 執行的命令
    **真的有管線**，但前一版把**含 YAML 外層引號的原始文字**丟給抽取器，整段被當成引號內容挖空
    → 誤擋，而且訊息是假診斷（說它沒過濾）。YAML 的引號要先解碼，再交給 shell 掃描。
    """
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        # **未實作的逃脫一律回報無法解碼**（R26 M4／Codex 第 1 條）。前一版對 `\\` 只是**把反斜線刪掉**，
        # 於是 `"echo \\x22hi | python3 …"` 被解成 `echo x22hi | python3 …` —— 憑空生出一條管線，
        # 而 runner 拿到的其實是 `echo "hi | python3 … "`（一個字串、沒有管線）。
        # **lint 與 runner 跑不同的字串**，那不是「不判可達性」，是上一層就給錯了。
        DECODE = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "r": "\r", "/": "/", " ": " "}
        out, i, body = [], 0, v[1:-1]
        while i < len(body):
            if body[i] == "\\":
                nxt = body[i + 1] if i + 1 < len(body) else ""
                if nxt not in DECODE:
                    return None                  # 交給呼叫端 PARSE: 拒絕，不得猜
                out.append(DECODE[nxt]); i += 2; continue
            out.append(body[i]); i += 1
        return "".join(out)
    return v


def dedent_block(lines, explicit_pad=None):
    r"""剝掉 block scalar 的共同縮排 —— **`shell_scan()` 之前必須做**（R26 M2）。

    R28 D5（Codex 第 4 條，無 Claude lens 提出）：`run: |2` 這種**顯式縮排指示子**規定內文縮排是
    「父節點縮排 + N」，比它深的空白是**內容的一部分**、runner 會保留。前一版用最小縮排剝，把那些
    空白剝光，於是 runner 眼中「不是終止字」的 `  EOF` 被 lint 當成終止字——heredoc 提早結束、後面的
    假管線變成 code → rc=0，而 runner 把展開後的 `$PR_TITLE` 當 heredoc 資料印出。
    有指示子時 `explicit_pad` 由呼叫端算好傳進來（父縮排 + N），沒有才用最小縮排。
    前一版把帶 YAML 縮排的原始行直接丟進掃描器，於是 heredoc 的終止判定
    （歷史寫法）`probe.rstrip() == delim` 永遠不成立（`          EOF` 不等於 `EOF`）——**那個分支在任何真實
    `run: |` 裡都不可達**，heredoc 之後的真管線與真的 `# LOG-FILTER:` 一起被吞掉。
    DA 用合成的 base-綠語料量到：含 heredoc 的合規檔 17 個裡 **16 個被打紅**。
    （原句稱「順帶修好 `#` 詞首判定裡 `i == 0` 的語意」是錯的：`shell_scan()` 的 `#` 詞首判定靠 `prev_sig`——
    追蹤前一個有意義字元，不是字元索引 `i == 0`，這裡的縮排剝除跟它無關。）
    """
    # **「空行」的判準只算空白，tab 是內容**（#33 verify R37／R36 logic 第 10 列）。前一版用不帶參數的
    # `.strip()` 篩「非空行」——Python 的 `.strip()` 連 tab 一起當空白，於是一行「9 個空格 + 1 個 tab」
    # 被誤判成空行、排出 `body`，min() 就少算了它。YAML 的規則是**第一個非空行**（空行＝只含空白，而
    # 這裡的「空白」只算 SPACE）決定整段的縮排；那一行雖然總字元數比其他內容行少，只要它是**第一個**
    # 排進 body 的非空行，min() 就會取到它（min() 對順序不敏感，取到它是因為它的 pad 值本來就是 body
    # 集合裡的最小值——由 YAML 良構性保證：後面的內容行縮排不可能比它更淺，否則 YAML 解析器會把
    # 那一行讀成區塊外——已成立的 YAML 保證這件事）。PyYAML 對帳：`run: |` ⏎ `<9sp><tab>` ⏎
    # `<10sp>echo "$PR_TITLE"; cat <<EOF` ⏎ `<10sp>EOF` 剝出的縮排是 9（不是 10），第一行變成單一個
    # `\t`，其餘行留一個 leading space——前一版把那個 tab 行排出去，min 改算其餘行的 10，把 `\t` 也
    # 剝空成整行消失，heredoc 分隔字 `EOF` 因此少算一次縮排、被 lint 誤判成已經 flush（終止字提早
    # 出現一行），真正的過濾管線被吞。
    body = [l for l in lines[1:] if l.strip(" ")]
    if not body:
        return list(lines)
    # **YAML 的縮排只算空白，tab 是內容**（#33 verify R34 logic F4）。前一版用 `lstrip()` 連 tab 一起剝：
    # runner 眼中的 `\tEOF` 在 lint 眼中是 `EOF`＝終止字（heredoc 提早結束、假管線變 code），
    # 折疊區塊裡以 tab 開頭的 more-indented 行被剝成 flush 行而折進前一行。
    pad = explicit_pad if explicit_pad is not None else min(len(l) - len(l.lstrip(" ")) for l in body)
    # **純空白行也要剝**（R30 MB-11／Codex 第 4 條）。前一版原封保留它們，理由寫的是「依構造等價：
    # 純空白行沒有 token」——那是假的：引號 heredoc 的分隔字**可以是空白**（`cat <<' '`），於是一行
    # 十一個空白在 runner 眼中是「十個縮排 ＋ 一個空白」＝終止字，在前一版眼中是十一個空白＝不終止，
    # heredoc 吞掉後面的真管線 → 合法檔被打紅。YAML 對每一行剝同樣的縮排，不分空白行。
    return [lines[0]] + [l[pad:] for l in lines[1:]]


# R37 修法（#33 verify R36 第 21 列 LOW）：`|&`（bash 的 stderr 管線，等同 `2>&1 |`）先前不在這裡——
# `echo "$PR_TITLE" |&` 換行接 `python3 …neutralise.py` 沒被接成同一個邏輯行，真管線因此被誤判成「未過濾」
# （RULE 誤擋）。`\|&` 放在 `\|\|?` 之前之後都一樣（regex 回溯會試到），這裡插在 `\|\|?` 之後、`&&` 之前——三個 alternative 中的第二個，不是放在最後（regex 回溯讓順序不影響行為）。
CONT_RE = re.compile(r"(\|\|?|\|&|&&)\s*$")     # 邏輯行的續行運算子：`|`／`||`／`|&`／`&&`


def _fold_blank(l):
    """`fold_block` 的「空行」定義：剝掉區塊縮排後的**空字串**（不是 `strip()` 後為空——見 fold_block 的註解）。

    #33 verify R34 logic F8：前一版在兩處各寫一次（內容行分支的 `if l:` 與空行段掃描的 `if lines[j]:`）。
    只改其中一處時，空行段掃描一格都不前進（`j == i`）⇒ selftest 卡死、CI 看到的是逾時，不是可歸因的紅燈。
    兩處共用這一個定義，就不可能只改一半。"""
    return l == ""


def fold_block(lines, folded):
    r"""folded block scalar（`run: >`）的換行在 runner 眼中是**空白**——先折起來再交給 shell 掃描。

    R30 H-1(族B)：前一版把 `|` 與 `>` 一視同仁、逐**實體行**掃，而 YAML 把 folded 的相鄰內容行接成
    **一條** shell 行。於是 `echo "$PR_TITLE" # note` ⏎ `| python3 …neutralise.py` 在 lint 眼中是
    「一行註解 ＋ 一行管線」＝放行，在 runner 眼中是「一行：註解從 `#` 吃到底」＝**真的洩漏**，
    而 lint、CI、job 三個訊號全綠。`shell_scan()` 收不到「我在掃 `|` 還是 `>`」是結構性的缺口，
    所以資訊由呼叫端給，折疊在進掃描器**之前**做。

    折疊規則（YAML 1.2 §8.1.3 的子集，本 lint 只需要這三條）：相鄰的兩個**內容行**（剝掉區塊縮排後
    不再有前導空白）之間的換行折成一個空白；**more-indented**（剝完仍有前導空白）的行前後不折；
    空行不折。行數保持不變（折走的那一行留一個空字串佔位）。
    """
    if not folded:
        return list(lines)
    # **折疊是遞移的，不是兩兩一組**（R32 DA-2／logic L-0／Codex 第 1 條）。
    # 前一版折完把佔位的空字串留在 `out[-1]`，下一輪的 `out[-1].strip()` 守衛看到它就把鏈斷掉：
    #   ['a','b','c','d'] → ['a b','','c d','']，而 PyYAML 給的是 'a b c d'。
    # 於是 R30 H-1(族B) 的繞過用**三行**內容就復發——runner 把三行看成一行、`#` 註解吃到底、
    # PR 文字裸印，而 lint 把第三行當成獨立的一行、看到那條管線就放行（實測 rc=0）。
    # **釘那個缺陷的 fixture 用的是兩行**，正好是兩兩折唯一正確的情形——網守住的是它守得住的那一點。
    # 修法：用 `acc` 記住「目前正在累積的那一行在 out 裡的位置」，不要從 `out[-1]` 推——
    # `out[-1]` 在折疊之後必然是佔位空字串，用它當狀態就等於每折一次就重設一次。
    # 逐段處理：**內容行**照折疊規則接，**空行段**另外判。前瞻是必要的——空行只有在它**兩邊都是
    # flush 內容行**時才是「分隔符」；下一行若是 more-indented，那個空行就是真的空行（PyYAML 實測）。
    out, acc, prev_more, i, n = [], None, False, 0, len(lines)
    while i < n:
        l = lines[i]
        # **「空行」是剝掉區塊縮排後的空字串，不是 `strip()` 後為空**（R33 opsweep：`if l:` 那個突變體存活，
        # 而它才是對的）。PyYAML 對 `['a','   ','b']` 給 `'a\n   \nb'`——只含空白、比縮排深的行是 **more-indented
        # 的一行**，原樣保留，前後都不折；它也**不是**空分隔字 heredoc 的終止行（bash 要的是空字串）。
        # 前一版把它當空行 ⇒ 當成分隔符丟掉 ⇒ 空分隔字的 heredoc 被一個 runner 沒有的終止提早收掉 ⇒ 假放行。
        if not _fold_blank(l):
            more = l[:1] in (" ", "\t")
            # `acc` 非 None ⇒ 在被讀取合併的那一刻，它指向一個非空內容行（`acc` 的賦值本身不限定 `not more`——
            # `more` 為 True 時一樣會賦值，讀取安全靠的是 `prev_more` 迫使下一輪立刻重新賦值），所以
            # 「`out[acc]` 非 None 且非空」在讀取當下恆真——R31／R32 opsweep 對那兩個運算元各報存活，實測依構造多餘，刪掉。
            if acc is not None and not more and not prev_more:
                # **接上去的 `l` 不 strip**（#33 verify R37／R36 logic 第 11 列）。折疊只在兩個內容行之間插入
                # 一個空白，不動任一行本身的內容——`l` 在這個分支已保證沒有前導空白（`not more`），差別只在
                # **行尾**空白，而那正是 heredoc 終止字比對（`probe.rstrip() == delim` 之外，分隔字本身若含
                # 行尾空白）與詞界判定要看到的東西。PyYAML 實測：`['a','   ','b']` 這種 more-indented 不會走
                # 到這支（上面已排除），但 `['a a ', 'a a ']`（兩個內容行、第二行帶行尾空白）folded 成
                # `'a a  a a '`——**第二行的行尾空白原樣保留**，不是折疊時新插入的那個空白。前一版的
                # `EXPECTED_SURVIVE`（`strip→id|fold_block|…`）論證「折進去的只差行尾空白，下游消費者都吃得
                # 下」是假的：heredoc 分隔字比對用的正是**沒被折走的整行**，`l.strip()` 悄悄把該行的行尾空白
                # 吃掉，讓 lint 算出的分隔字比 bash（＝PyYAML）短一個字元——分隔字恰好是空白時（`cat <<' '`
                # 這一族）差一個字元就是有沒有終止的差別。R36 verify（agents:logic）點名、R37 用突變體
                # （把這裡的 `.strip()` 拿掉）驗殺：拿掉之後會讓原本放行的探針正確翻紅（t8 隔離測試量到正向與
                # rule-red 計數各差 1，並非「數字不變」），`.strip()` 才是那個 bug。
                out[acc] = out[acc] + " " + l
                out.append(None)                # 佔位：行數不變，但 runner 眼中沒有這一行
            else:
                out.append(l); acc = len(out) - 1
            prev_more = more
            i += 1
            continue
        # ── 空行段 ──
        j = i
        while j < n:                            # 同上：空行＝空字串；寫成 break 不留布林運算元（opsweep 報存活）
            if not _fold_blank(lines[j]):
                break
            j += 1
        nxt_more = lines[j][:1] in (" ", "\t") if j < n else False   # 條件式，不留死的布林運算元
        prev_flush_content = acc is not None and not prev_more     # 同上：acc 非 None ⇒ 非空內容行
        # 段尾的空行被 clip chomping 吃掉（`['a','b','']` 的值是 `'a b\n'`）——全部是佔位。
        # 否則第一個空行換來那個換行、自己不留下；第二個以後才是真的空行
        #（`['a','','b']` → `'a\nb'`；`['a','','','b']` → `'a\n\nb'`）。
        # `j < n` 在這裡是死的：j ≥ n 時下面一律填 None，drop_first 的值不會被讀到（opsweep 報存活，刪掉）
        drop_first = prev_flush_content and not nxt_more
        for k in range(i, j):
            out.append(None if (j >= n or (k == i and drop_first)) else lines[k])
        acc, prev_more, i = None, False, j
    return out


def _next_phys(lines, k):
    """續行要接的是**下一個實體行**；折疊的佔位（`None`）不是行，跳過它。

    回傳 `(那一行, 吃掉的格數)`——格數＝跳過的佔位＋那一行本身。#33 verify R34（regression H-2）：前一版
    只回傳那一行，三個呼叫點一律 `spans += 1`；中間有佔位時被接上來的行沒有被算進 spans，於是它**再被
    當成獨立的一行掃一次**，而且帶著第一次掃完的引號狀態——一個不平衡引號就把假管線翻成 code。
    """
    start = k
    while k < len(lines) and lines[k] is None:
        k += 1
    if k < len(lines):
        return lines[k], k - start + 1
    return "", k - start


ANSIC = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r",
         "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


def _ansic_decode(s):
    r"""把 `$'…'` 的內容照 bash 的 ANSI-C 規則解碼；解不出確定值就回 `None`（呼叫端 fail-closed）。

    bash 5.3 實測（heredoc 終止字，讀 EOF 警告）：`E\x41`→`EA`、`E\'F`→`E'F`、`\101B`→`AB`、`E\\F`→`E\F`、
    `E\"F`→`E"F`、`E\qF`→`E\qF`（認不得的逃脫保留反斜線）、`E\x4`→`E\x04`。`E\cAF` 得到 `E\x01\x01F`——
    `\x01` 是 bash 內部的引號跳脫字元（CTLESC），出現時會自我重複；`\x7f`（CTLNUL）不是同一種逃脫字元，
    出現時是被加上一個 `\x01` 前綴，不是被複製成兩個 `\x7f`；`\c` 與解出這兩個字元的一律不猜。

    #33 verify R36（logic HIGH-3／R35 回歸）：`\x`、八進位、`\u`、`\U` 解出的**任何 ≥0x80 的值**一律 fail-closed。
    bash 對 `\x`／八進位產生的是單一**原始位元組**，不做任何 Unicode 解碼；Python 的 `chr(0xe9)` 卻是碼位
    U+00E9（一個字元），兩者（僅指 ≥0x80 的值；<0x80 的 ASCII 逃脫兩邊本來就是同一個位元組）在 UTF-8
    檔案裡永遠不是同一行——`\377`、`\xe9`、兩個 `\x` 湊出的 `\xc3\xa9`
    都曾讓 heredoc 提早（或延後）收尾、真管線被吞。`\u`／`\U` 雖然語意上是碼位不是位元組，這裡不區分、
    一律用同一條門檻擋下：解不出確定的 ASCII 值就不猜。同一條門檻也**先擋掉 NUL**（bash 在 NUL 截斷
    字串，本 lint 解出的卻是含 `\x00` 的完整字串——兩邊的終止字不同，前一版因此讓 heredoc 永不終止、
    後面的行全被當成資料誤擋；fail-closed 把它變成明確的 PARSE，不是意外的吞併）；**並且先於 `chr()`
    判斷範圍**——`\U7fffffff` 這種超出 Unicode 範圍（>0x10FFFF）的值本來會讓 `chr()` 丟 `ValueError`、
    lint 直接 traceback（rc=1 但不是走 fail-closed 那條路，後面的檔案也不再檢查），現在在呼叫 `chr()`
    之前就已經因為 ≥0x80 回了 `None`。
    """
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c != "\\":                 # 收集端把 `\\` 與下一格一起收，字串不會以單獨的 `\\` 結尾（opsweep 報 `i + 1 >= n` 存活，死碼刪掉）
            out.append(c); i += 1; continue
        d = s[i + 1]
        if d in ANSIC:
            out.append(ANSIC[d]); i += 2; continue
        if d in "01234567":
            m = re.match(r"[0-7]{1,3}", s[i + 1:]).group()
            v = int(m, 8) & 0xFF
            if v == 0 or v >= 0x80:
                return None
            out.append(chr(v)); i += 1 + len(m); continue
        if d in "xuU":
            m = re.match(r"[0-9A-Fa-f]{1,%d}" % {"x": 2, "u": 4, "U": 8}[d], s[i + 2:])
            if m:
                v = int(m.group(), 16)
                if v == 0 or v >= 0x80:
                    return None
                out.append(chr(v)); i += 2 + len(m.group()); continue
        if d == "c":
            return None
        out.append("\\" + d); i += 2
    r = "".join(out)
    return None if ("\x01" in r or "\x7f" in r) else r


# `_param_end()` 回 None 時呼叫端印的原因（兩處共用）。R36 第 24 列：前一版兩處都寫「命令替換／舊式算術」不解析——
# 命令替換自 R35 起是配對的，那句話不再成立。現在的 None 只有這些來源（見 `_param_end`、`_cmdsub_end`）。
PARAM_UNPARSED = ("`${…}` 在同一行沒收尾（含裡面的引號、命令替換），或是 bash 5.3 的 `${ cmd; }`／`${| cmd; }`，或裡面有本 lint 不解析的構造："
                  "舊式算術 `$[…]`；命令替換裡的詞首 `#`、heredoc、`$'…'`、`$[…]`、`case`；"
                  "算術 `$((…))` 裡的引號、反斜線，或 `$((…) …)` 形式")


def _backtick_end(line, j):
    """`` `…` `` 從開頭的反引號到收尾反引號之後的位置；同一行沒收尾回 None。反斜線逃脫下一個字元。"""
    k, n = j + 1, len(line)
    while k < n:
        if line[k] == "\\":
            k += 2; continue
        if line[k] == "`":
            return k + 1
        k += 1
    return None


def _arith_end(line, j):
    """`$((…))` 的配對：從 `$((` 到收尾 `))` 之後的位置；本 lint 不解析的構造回 None（呼叫端 fail-closed）。

    #33 verify R37（R36 第 16 列）：算術展開裡的 `<<` 是左移、`(`／`)` 是分組，不是 heredoc 也不是命令替換。
    括號計深度；深度 0 的 `))` 收尾。**深度 0 卻只有單一個 `)`** 代表 bash 會改讀成「命令替換裡的子殼層」
    （`$((cd x; ls) )`）——不猜，回 None。引號、反引號、反斜線出現在算術裡也回 None（bash 對它們的處理與
    剖析、展開兩個階段相依，本 lint 不追）；`${…}`／`$(…)` 走各自的配對。"""
    k, n, depth = j + 3, len(line), 0
    while k < n:
        c = line[k]
        if c in "\\'\"`":
            return None
        if line.startswith("${", k) or line.startswith("$(", k):
            e = _param_end(line, k) if line[k + 1] == "{" else _cmdsub_end(line, k)
            if e is None:
                return None
            k = e; continue
        if c == "(":
            depth += 1
        elif c == ")":
            if depth:
                depth -= 1
            elif line.startswith("))", k):
                return k + 2
            else:
                return None
        k += 1
    return None


def _dq_end(line, k):
    """雙引號字串（在 `${…}`／`$(…)` 裡）：從開頭的 `"` 到收尾 `"` 之後的位置；同一行沒收尾或含不解析的構造回 None。

    反斜線逃脫下一個字元；`$(…)`、反引號、`${…}` 走各自的配對（它們裡面的 `"` 不是這個字串的收尾）；
    舊式算術 `$[…]` 回 None（見 `_param_end`）。R37 以前 `_param_end` 與 `_cmdsub_end` 各寫一份，
    `_cmdsub_end` 那份不認巢狀的命令替換——三份引號邏輯互不一致正是 R36 codex 第 1 條的建議修法對象。"""
    k, n = k + 1, len(line)
    while k < n and line[k] != '"':
        if line[k] == "\\":
            k += 2; continue
        if line.startswith("$[", k):
            return None
        if line.startswith("$(", k) or line[k] == "`":
            e = _cmdsub_end(line, k) if line[k] == "$" else _backtick_end(line, k)
            if e is None:
                return None
            k = e; continue
        if line.startswith("${", k):
            e = _param_end(line, k)
            if e is None:
                return None
            k = e; continue
        k += 1
    return k + 1 if k < n else None


def _cmdsub_end(line, j):
    """`$(…)` 的配對：從 `$(` 到收尾 `)` 之後的位置；同一行沒收尾、或裡面有本 lint 不解析的構造，回 None。

    `$((` 是算術，交給 `_arith_end`。其餘括號計深度，略過逃脫、單雙引號（`_dq_end`）、巢狀的 `${…}`／反引號／
    `$((…))`。**這不是 bash 的命令替換剖析**（#33 verify R36 第 7 列：agents:logic, codex 第 1 條）——下列五種
    構造讓括號計數與 bash 分岔，**遇到一律回 None**（封閉列舉，只有這五種；其餘構造照上面的規則配對）：
      1. 詞首的 `#`：註解到行尾，註解裡的 `)` 不收尾（`$(echo a #)` 在 bash 要到下一行才收）。
      2. `<<`（`<<<` 除外）：heredoc 的內文在下一行起，同一行收尾的 `$(cat <<EOF)` 讓 bash 從下一行讀內文。
      3. `$'…'`：`\\'` 是逃脫不是收尾，普通單引號的規則會提早收掉字串。
      4. `$[…]`：bash 把它當巢狀結構讀，裡面的 `)` 不收命令替換。
      5. 詞首的 `case`：模式括號是單邊 `)`，深度提早歸零。
    R35 在這裡寫「`case` 的後果是 fail-closed 的方向」——錯的：深度提早歸零 ⇒ `${…}` 提早收尾 ⇒ 後面的假管線
    變 code ⇒ 放行（`bypass-r37c-case-in-param-cmdsub`）。呼叫端在頂層雙引號裡拿到 None 時不直接 PARSE，
    改把內容當 code 掃（見 `shell_scan` 的雙引號分支；`$((` 除外，那是算術、fail-closed）；在 `${…}` 裡拿到 None
    則 fail-closed。"""
    if line.startswith("$((", j):
        return _arith_end(line, j)
    k, n, depth = j + 2, len(line), 1
    prev = "("                                          # 詞首判定用：`$(` 之後就是詞首
    while k < n:
        c = line[k]
        at_word = prev in SHELL_WORD_BREAK
        if c == "\\":
            k += 2; prev = "x"; continue
        if (c == "#" and at_word) or line.startswith("$'", k) or line.startswith("$[", k):
            return None
        if line.startswith("<<<", k):
            k += 3; prev = "<"; continue
        if line.startswith("<<", k):
            return None
        if at_word and line.startswith("case", k) and line[k + 4:k + 5] in ("", " ", "\t"):
            return None
        if c == "'":
            e = line.find("'", k + 1)
            if e < 0:
                return None
            k = e + 1; prev = "x"; continue
        if c == '"' or c == "`" or line.startswith("${", k) or line.startswith("$((", k):
            e = (_dq_end(line, k) if c == '"' else _backtick_end(line, k) if c == "`"
                 else _param_end(line, k) if line[k + 1] == "{" else _arith_end(line, k))
            if e is None:
                return None
            k = e; prev = "x"; continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if not depth:
                return k + 1
        prev = c; k += 1
    return None


# `$(…)` 裡的 case 追蹤（見 `shell_scan` 的 `cases`）用的工具。R37，R36 第 7 列。
CASE_KW_RE = re.compile(r"(case|esac)(?=[\s;&|()<>]|$)")
# 命令起點：本行到目前為止的 code 以分隔字元（或行首）結尾，後面接零或多個（無上限）「後面還是命令」的保留字。
# 保留字本身也要在命令起點——`echo do case` 的 `do` 是參數，所以要求它前面緊接分隔字元，不接受任意空白後的 `do`。
AT_CMD_RE = re.compile(r"(?:^|[;&|(`])(?:\s*(?:do|then|else|elif|if|while|until|time|!|\{))*\s*$")


def _at_command(code, cases, lvl):
    """`code`（本邏輯行目前為止的 code 桶內容）之後的詞是不是在命令起點。case 子句的模式 `)` 之後也是。"""
    s = code.rstrip()
    if s.endswith(")") and cases and cases[-1][0] == lvl and cases[-1][1] == "cmd":
        return True
    return bool(AT_CMD_RE.search(s))


def _case_head(line, i):
    """從 `case` 起：後面是不是「一個 shell 詞 + `in`」。詞裡的引號、`$(…)`、`${…}`、反引號照各自的配對；配不起來回 False。"""
    j, n = i + 4, len(line)
    while j < n and line[j] in " \t":
        j += 1
    k = j
    while k < n and line[k] not in " \t;&|()<>":
        c = line[k]
        if c == "\\":
            k += 2; continue
        if c == "'":
            e = line.find("'", k + 1)
            e = e + 1 if e >= 0 else None
        elif c == '"':
            e = _dq_end(line, k)
        elif c == "`":
            e = _backtick_end(line, k)
        elif line.startswith("${", k) or line.startswith("$(", k):
            e = _param_end(line, k) if line[k + 1] == "{" else _cmdsub_end(line, k)
        else:
            k += 1; continue
        if e is None:
            return False
        k = e
    w_end = k
    while k < n and line[k] in " \t":
        k += 1
    return w_end > j and k > w_end and line.startswith("in", k) and line[k + 2:k + 3] in ("", " ", "\t", ";")


def _cmdsub_end_case(line, j):
    """`_cmdsub_end` 加上 case 模式括號的追蹤（R37 合併 r37b×r37c 時加）：只給**雙引號**裡的命令替換用。

    `_cmdsub_end` 對詞首的 `case` 一律回 None——那是 r37c 在 `${…}` 裡刻意的 fail-closed（第 7 列）。但雙引號裡同一行
    收尾的 `"$(case … esac)"` 是常見寫法，r37c 的掃描器對它改走 code 模式，而 r37b 的規則層（`_hidden_subs`、`_word`）
    假設雙引號內容是挖空的——兩包各自在 380e4a4 上都對，合在一起 `good-r37c-dq-cmdsub-case-sameline` 與
    `…-multiline-case` 被誤擋。這一支照主掃描器 `cases` 的規則追蹤 case（模式 `)` 不減深度、`;;`／`;&` 回到等模式、
    `esac` 在命令起點或等模式時收尾），其餘照 `_cmdsub_end`：詞首 `#`、`<<`、`$'`、`$[` 一律回 None。
    輸入可以跨行（規則層傳的是接起來的原文）：換行在命令起點判定裡當 `;`。"""
    if line.startswith("$((", j):
        return _arith_end(line, j)
    k, n, depth = j + 2, len(line), 1
    code, cases, prev = ["("], [], "("
    while k < n:
        c = line[k]
        at_word = prev in SHELL_WORD_BREAK or prev == "\n"
        if c == "\\":
            code.append("xx"); k += 2; prev = "x"; continue
        if c == "\n":
            code.append(";"); k += 1; prev = "\n"; continue
        if (c == "#" and at_word) or line.startswith("$'", k) or line.startswith("$[", k):
            return None
        if line.startswith("<<<", k):
            code.append("<<<"); k += 3; prev = "<"; continue
        if line.startswith("<<", k):
            return None
        if at_word:
            kw = CASE_KW_RE.match(line, k)
            if kw:
                at_cmd = _at_command("".join(code), cases, depth)
                if kw.group(1) == "case":
                    if not (at_cmd and _case_head(line, k)):
                        return None
                    cases.append([depth, "pat"])
                elif cases and cases[-1][0] == depth and (cases[-1][1] == "pat" or at_cmd):
                    cases.pop()
                code.append(kw.group(1)); k = kw.end(); prev = "x"; continue
        if cases and cases[-1][0] == depth and cases[-1][1] == "cmd" and line.startswith((";;", ";&"), k):
            cases[-1][1] = "pat"
        if c == "'":
            e = line.find("'", k + 1)
            if e < 0:
                return None
            code.append("x" * (e + 1 - k)); k = e + 1; prev = "x"; continue
        if c == '"' or c == "`" or line.startswith("${", k) or line.startswith("$(", k):
            e = (_dq_end(line, k) if c == '"' else _backtick_end(line, k) if c == "`"
                 else _param_end(line, k) if line[k + 1] == "{" else _cmdsub_end_case(line, k))
            if e is None:
                return None
            code.append("x" * (e - k)); k = e; prev = "x"; continue
        if c == "(":
            if not (cases and cases[-1][0] == depth and cases[-1][1] == "pat"):
                depth += 1                              # 等模式時的 `(` 是模式的前導括號，不計深度
        elif c == ")":
            if cases and cases[-1][0] == depth:
                if cases[-1][1] == "cmd":
                    return None                         # 子句命令之後同一層的單獨 `)`：bash 語法錯誤
                cases[-1][1] = "cmd"                    # 模式括號：不減深度
            else:
                depth -= 1
                if not depth:
                    return None if cases else k + 1
        code.append(c); prev = c; k += 1
    return None


def _param_end(line, i):
    r"""`${…}` 的配對剖析：回傳展開結束之後的位置；本 lint 不解析的構造回 `None`（呼叫端 fail-closed）。

    #33 verify R34 logic F1：前一版只認 `${`、`}`、逃脫與單雙引號，於是五種構造讓它在 bash 還沒結束展開的地方
    就宣告結束：反引號（`` `}` ``）、`$(…)`（`$(: })`）、`$'…'`（`\'` 是逃脫不是收尾）、雙引號裡的 `${`
    （雙引號分支根本不進來）、跨行。現在照 bash 的配對規則做：引號、`$'…'`、巢狀 `${`、`$(…)`（`_cmdsub_end`）、
    反引號（`_backtick_end`）——雙引號裡的也一樣（`_dq_end`）。**同一行沒收尾一律回 `None`**（跨行的 `${…}` 是
    已知不涵蓋第三組第 2 條）。R35 第一版對 `${…}` 裡的命令替換與 `$[` 也一律回 `None`；三軸量到常見寫法
    `${X:-$(cmd)}` 因此翻紅，命令替換改成配對（`_cmdsub_end` 自己對五種構造回 None，見該函式）。
    **舊式算術 `$[…]` 一律回 `None`**（#33 verify R36 第 5 列 (c)）：R35 以「`$[…]` 裡不可能出現 `}`，當普通字元
    處理與特判等價」為由把兩個 `$[` 分支當死碼刪掉——前提是錯的。bash 5.3 把 `${…}` 裡的 `$[ … ]` 當巢狀結構讀，
    `}` 放在裡面照樣過 `bash -n`：`echo ${PR_TITLE:-$[ } 2>&1 | python3 …neutralise.py ]}` 整串是一個詞、管線沒建立，
    刪掉之後 lint 在 `$[ }` 就收掉展開、放行（`bypass-r37c-param-legacy-arith-brace`）。opsweep 報「存活」只代表
    當時沒有 fixture 走到它，不代表它沒有行為。雙引號裡的 `$[` 同此（`_dq_end`）。
    """
    if i + 2 >= len(line) or line[i + 2] in " \t|":
        # bash 5.3 的 `${ cmd; }`／`${| cmd; }` 在**目前的 shell** 執行 cmd（R40，#33 verify R39 第 10 列）：`echo ${ set -x; }` 開了
        # xtrace。5.3 以前這些都是 bad substitution，沒有合法用途——一律不解析。
        return None
    j, depth, n = i + 2, 1, len(line)
    while j < n:
        c = line[j]
        if c == "\\":
            if j + 1 >= n:
                return None                         # 行尾反斜線：續行接進 `${…}`，不解析
            j += 2; continue
        # 命令替換照 bash 配對（R35 三軸：`${GITHUB_REF:-$(git …)}` 是常見寫法，一律 fail-closed 讓合法檔翻紅）
        if line.startswith("$(", j) or c == "`":
            e = _cmdsub_end(line, j) if c == "$" else _backtick_end(line, j)
            if e is None:
                return None
            j = e; continue
        if line.startswith("$[", j):                # 舊式算術：fail-closed（見 docstring，R36 第 5 列 (c)）
            return None
        if line.startswith("$'", j):                # ANSI-C：`\'` 是逃脫
            k = j + 2
            while k < n and line[k] != "'":
                k += 2 if line[k] == "\\" else 1
            if k >= n:
                return None
            j = k + 1; continue
        if c == "'":
            k = line.find("'", j + 1)
            if k < 0:
                return None
            j = k + 1; continue
        if c == '"':
            e = _dq_end(line, j)
            if e is None:
                return None
            j = e; continue
        if line.startswith("${", j):
            # 巢狀的 `${` 與最外層同一條（#33 verify R41 requirements F1）：先前只查最外層，`${X:-${ set -x; }}` 被讀成
            # 一般的參數展開，bash 5.3 卻在目前的 shell 開了 xtrace（`parse-r42-default-nested-funsub`）。
            if j + 2 >= n or line[j + 2] in " \t|":
                return None
            depth += 1; j += 2; continue
        j += 1
        if c == "}":
            depth -= 1
            if not depth:
                return j
    return None


def shell_scan(lines):
    r"""把一個 `run:` 區塊掃成（每行會被執行的部分, 不會被執行的宣告文字）。
    **狀態跨行**：引號、反斜線、續行摺疊、heredoc（含佇列）、算術展開深度。
    三個桶：code（會執行）／decls（shell 註解）／**丟棄**（heredoc 內文與引號內容是**資料**）。
    R26 修掉的五件（M2／M3／M5）：
      * 呼叫端先 `dedent_block()`，heredoc 終止判定才可達。
      * `<<<` 是 here-string 不是 heredoc —— 前一版守衛只看第一個 `<`，掃描器前進一格後在第二個
        `<` 上又命中，於是 `cat <<< "$X"` 的 delim 被 latch 成 `"$X"`。現在一次消費三格。
      * `$(( 1 << 4 ))` 的左移不是 heredoc —— 追蹤算術展開深度，深度 > 0 不判 heredoc。
      * 一行多個 heredoc：前一版只存 `pending[0]`，註解裡卻宣稱後面的會自己接上，**那是假的**
        （第二個 heredoc 的內文會落回 code 桶）。現在是 FIFO，前一個結束就接下一個。
      * 行尾 `\` 是**續行**：前一版把它丟掉、下一行重新當成新行，於是 `cat <\` ⏎ `<EOF` 這種寫法
        讓 heredoc 開頭被拆開、內文整批進了 code 桶，一句假管線就能讓整個 step 過關。
        現在維護 `prev_sig`（前一個有意義字元），續行時不重設，`#` 的詞首判定才正確。
    R28 修掉的六件（D1–D6；每件一個 mutation 靶、一個會翻色的 fixture）：
      * 終止字要**完全**相等：`EOF ` 對 bash 不是終止字，前一版 `rstrip()` 後相等就當終止。
      * 未引號分隔字含反斜線（`<<E\OF`）視同引號化：內文不展開、行尾反斜線不續行。
      * 未引號 heredoc 的內文行尾反斜線是續行——下一行是同一個邏輯行的一部分，不可能是終止字。
      * `((`／`))` 整個 token 消費：前一版 `$((` 在兩個位置各命中一次而 `))` 只減一次，深度卡住。
      * `run: |N` 的顯式縮排指示子由呼叫端算成 `explicit_pad` 交給 `dedent_block()`（見該函式）。
      * 續行重掃前還原 `pending` 快照：前一版只還原 quote／prev_sig，同一個 heredoc 被排兩次。
    **已知不涵蓋，第二組（這一組是封閉列舉，只有五條，不得依性質相似類推第六條；R32 抓到前三條不在檔內，第 4 條 R39、第 5 條 R40 加）**：
      1. **stderr（預設模式）**：預設模式的 `PIPED_RE` 只要求管線存在，不要求 `2>&1`／`|&`（已知類別 S-2，範例
         `known-stderr-cmd-error-missing-2to1`）。**`--strict` 擋它**（R37–R41 是群組規則，R42 起是正面文法的 `run_F`）——CI 與 run.sh 對真 workflow 用 `--strict`，
         所以這一條只剩 fixture／產生語料（它們量的是詞法）。另：把輸出轉到 stderr 或開 xtrace 的寫法（`>&2`、
         `set -x`…）在預設模式是 fd 流向規則；`--strict` 的群組裡 `>&2` 進管線、收下，`set -x` 不在文法裡（R35；R33 的 S-2 範例
         用的正是 `>&2`，它不屬於這一條）。
         **逐段的 `2>&1` 只涵蓋命令執行時寫出的 stderr**（R37 合併時協調者以 bash 5.3 覆核；#60 第 2 類）：在該段
         `2>&1` 生效**之前**就寫出的，預設模式看不到（範例 `known-expansion-error-before-2to1`）——(a) 展開期錯誤：`echo "${!PR_TITLE}" |& …` 印出
         「<原值>：無效的變數名稱」、`echo $(( PR_TITLE )) 2>&1 | …` 印出算術錯誤；(b) 寫在 `2>&1` 左邊的重導向本身出錯：
         `echo x > "$PR_TITLE" 2>&1 | …` 印出 `<原值>: No such file…`（`2>&1` 移到那個重導向的左邊——`echo x 2>&1 > "$PR_TITLE" | …`——錯誤就走進管線）。命令執行時才產生的
         錯誤（`[[ $PR_TITLE -eq 1 ]] 2>&1 | …`）會走管線、被過濾。群組 `{ …; } 2>&1 |` 的重導向在內部展開之前生效，
         (a)(b) 一起關掉——`--strict` 要求整個區塊就是那個群組（R37 自 PR #61 移植，R42 起是 `run_F`；R36 的逐段 `2>&1` 規則看不到它們）。
         本 lint 不為 (a)(b) 逐拼法列規則（那正是 R36 批評的形狀）。
         R35 更正：R33 這裡寫「repo 自己的 17 條管線全部已帶 `2>&1`／`|&`」——`--strict` 第一次跑就在 pack anchor
         那一步抓到一條 `… | tee | python3 …` 的最後一段沒帶（`tee` 的 stderr 沒有 PR 文字，但宣稱是假的）。
      2. **顆粒度（預設模式）**：一個 run 區塊裡**任一條**邏輯行接了管線，整個區塊就算已過濾（#33 verify R34 requirements F4、logic F6、DA；追蹤 #59）。
         `echo "$PR_TITLE"` ⏎ `echo safe | python3 …` 因此放行（已知類別 G）。這是宣告過的語意，不是漏洞的偽裝。
         **`--strict` 改了「什麼算已過濾」**（#59，R37 自 PR #61 移植）：整個區塊必須是一個 `{ …; } 2>&1 | python3 …`
         群組（R42 起是正面文法的 `run_F`，見「`--strict` 的正面文法」一節），另一條命令不可能在群組外。
         同一條也涵蓋「管線不可達」：外流的行先執行、接管線的行因語法錯誤／`exit`／沒走到的分支不執行
         （R35 已把「引號開到區塊結尾」改成 fail-closed；R37 補齊同一族其餘未收尾構造——管線後面接
         `$(`、反引號、`; ((`、`; [[ -n x`、`$[`、`; (` 六種，以及掃描結束時 `csub`／`bt`／`arith`／`brk`／
         `cond`／未配對的裸 `(` 任一不為零，都比照辦理；另外「管線左邊沒有命令」（`true ;|& python3 …`、
         `true &&` 換行 `|& python3 …`——`;`／`&&` 之後直接是管線、bash 語法錯誤）不算接到 neutralise 的管線，
         `PIPED_RE` 排除 `;`／`&`／`(` 當左邊界，見該正規式旁的說明）。
      3. **多行分隔字**：`cat <<"A` ⏎ `B" | python3 …` 在 bash 是引號跨行、heredoc 永不終止但**管線照建**；
         本 lint 的分隔字是單行字串、表示不了它，一律 `PARSE:`（誤擋方向，源頭在 R33、該回合無 Codex leg；產生語料的
         `d-delimword-unterm-*` 四檔由神諭歸「不可比（fail-closed）」）。
      4. **過濾器的身分**（#33 verify R38 第 21 列）：`NEUT_PATH_RE` 只比對「以 `neutralise.py` 結尾、不加引號、不帶變數的路徑」。
         本 lint 檢查的是 **shell 接線**——PR 文字有沒有經過那個過濾器——不驗證那個檔案的內容：前一個 step 寫出一個同名的
         `cat`，或 PR 直接改掉過濾器本身，lint 都看不到。test.yml 的威脅模型寫明每個 job 本來就執行 PR 的程式碼；這條 lint
         防的是維護者的無心之失（接線漏掉），不是對抗性的替換。過濾器自己的啟動環境（`PYTHON*` 的值是運算式）另有規則（R39）。
      5. **不經 shell 重導向的寫入**（#33 verify R39 第 2、9 列）：fd 規則看的是**重導向的目標**。以命令參數給的路徑
         （`tee /proc/$$/fd/1`、`dd of=/proc/$$/fd/1`、`cp f /proc/$$/fd/1`）、群組裡自己建的 symlink（`ln -s /proc/$$/fd/1 o; … > o`）
         都不在模型裡——參數分不出是讀還是寫（`cat /dev/null` 很常見），一律擋會誤擋太多；Linux 上它們寫到外層 shell 的 fd，
         是真的外流（本機沒有 /proc，未實跑）。`--strict` 對 `$$` 本身不收（文法的參數只收 `$NAME`、`${NAME}`、`${NAME:-字面}`、`$?`），
         但命令參數的路徑同樣不模擬（正面文法一節的 L1）。跨 step 的通道（`$GITHUB_ENV`／`$GITHUB_PATH`）：R40 的 `github_env_write`
         兩種模式共用，R42 刪除；現在只有 `--strict` 管（靠管線過濾的 step 與觸發了的宣告 step 只收字面寫入與唯讀，正面文法一節的
         P1、L3），預設模式不檢查。神諭把五個通道指到暫存檔、看得到一個 step 寫進去的 PR 文字（一次仍只跑一個 step）。
    **已知不涵蓋，第三組——預設模式的假設（封閉列舉，只有五條，不得依性質相似類推第六條；R35 新增前三條，
    R37 新增第 4、5 條）**：
      1. **shell 是 bash**：預設模式不讀 `shell:`／`defaults.run.shell`／container／runs-on，照 bash 的詞法判。
         `--strict`（CI 與 run.sh 對真 workflow 用的模式）驗這個假設：shell 必須是 bash（可帶選項、不得開 xtrace），
         container 或 Windows／運算式 runs-on 的 job 必須明寫 bash。R35 第一版在預設模式也套用，三軸量到合成 A
         語料 959 個 base-綠檔 290 個翻紅（R36 重算為聯集 268 檔：shell 值規則 75 檔、container／Windows 規則
         223 檔，多數來自後者），所以移進 `--strict`。
      2. **跨行的 `${…}`**（含雙引號裡的）：本 lint 的 `${…}` 配對不跨行 ⇒ fail-closed `PARSE:`（誤擋方向；
         合成 A 語料 1 檔：`"${X:+$X` ⏎ `…}"`）。
      3. **`$(…)` 裡的 `case`**：命令替換用括號計深度配對，`case … in a)` 的單邊模式括號會讓深度提早歸零。
         **R35 這一條寫「後果是 fail-closed 的方向」，那是錯的**（R36 第 7 列）：深度提早歸零 ⇒ `${…}` 提早收尾 ⇒
         後面的假管線變 code ⇒ 放行（`bypass-r37c-case-in-param-cmdsub`，bash 5.3 實測裸印 PR 文字）；主掃描器的
         `csub` 同一個根因，還繞過了「命令替換裡的 heredoc 以前綴收尾 ⇒ fail-closed」（`bypass-r37c-case-cmdsub-heredoc-prefix-term`）。
         R37 之後的實際行為：`_cmdsub_end`（`${…}` 裡、以及雙引號裡同一行收尾的那一段）遇到 `case` 一律回 None ⇒
         在 `${…}` 裡是 fail-closed `PARSE:`（誤擋方向）；主掃描器（含雙引號裡改當 code 掃的命令替換）**追蹤** case 的
         模式括號，追蹤表示不了的形狀 fail-closed（見主迴圈 `cases` 的註解）。
      4. **`shopt -s extglob`／`-O extglob`**：extglob 開啟後 `@(`、`!(`、`+(`… 是合法語法，本掃描器不模擬這套
         詞法，偵測到就整個 run 區塊 fail-closed `PARSE:`（見 `EXTGLOB_RE`；R36 第 17 列）。
      5. **頂層 `case` 的模式文字當成 code**（R37 完整性審查，缺陷 d）：`case x in a|python3\ scripts/neutralise.py ) ;; esac`
         的 `|` 是「或」、不建管線，預設模式的 `PIPED_RE` 卻算它接了 neutralise——放行（`known-r37t8-default-case-pattern-pipe`，
         神諭列為 `KNOWN_DISAGREE`）。`--strict` 由群組規則擋下（區塊不是 `{ …; } 2>&1 | python3 …` 群組；R37 移植 #61 之前是「看得到管線、規則層剖析不出它」那條）
         （`bypass-r37t8-strict-case-pattern-looks-piped`），CI 對真 workflow 用的是 `--strict`。修它要把第 3 條的 case 追蹤延伸到頂層、
         並把模式文字挖空；頂層 case 在 workflow 裡很常見，而那套追蹤對表示不了的形狀一律 fail-closed——延伸過去的誤擋代價沒量過，本輪不做。

    **命令位置（R37 新增，#33 verify R36 第 5(a) 列，R35 回歸的更正）**：`[[` 只在**命令位置**（邏輯行首，或
    `;`、`&`、`|`、`(`、`!`、`{`、`&&`、`||` 與 `then`／`do`／`else`／`elif`／`if`／`while`／`until` 之後）才當條件式
    關鍵字；`((` 同樣只在命令位置當算術**命令**（`$((…))` 算術**展開**不受限，看 `prev_sig == "$"` 直接放行，
    與位置無關——這是兩種不同構造）。R35 只檢查「前一個字元是不是空白／metacharacter」（`prev_sig in
    SHELL_WORD_BREAK`），但 `SHELL_WORD_BREAK` 本身含空白，於是「前面有空白」被誤當「在命令位置」——
    `echo "$PR_TITLE" [[ # ]] 2>&1 | python3 …` 這種**引數位置**的 `[[` 因此被誤判成條件式，內容被當成
    「不是 code」而blank 掉，真正的 `#` 詞首註解（bash 對它的解讀）反而被蓋住。用 `cmd_pos` 這個跨字元
    持續追蹤的旗標取代那個字元類檢查：`cmd_pos` 在掃到上述任一運算子／關鍵字之後變 `True`，掃到其餘任何
    非空白字元後變 `False`；每個新的邏輯行（`lines[]` 的新一筆）開頭視為命令位置（換行本身就是分隔字元）；
    `$(`／backtick 開啟時同樣視為命令位置（裡面的第一個詞就是新命令）。另外，`((cmd) )`
    這種**巢狀 subshell**（不是算術，因為 `)` 中間夾了空白、不構成 `))`）現在會被辨識為算術區塊裡**未配對
    的單獨 `)`**，一律 fail-closed `PARSE:`（不再靜默吞掉、繼續掃到檔尾）。
    **已知不涵蓋，第一組（這描述的是一個性質，不是一份封閉列舉）**：本掃描器是**詞法**的，
    **不判定可達性**。`false && …`、`if`／`case` 沒走到的分支、`exit 0` 之後的死碼、`eval` 的字串、
    `$(...)` 內的巢狀命令替換——詞法上看得到的管線，執行上不一定跑得到。
    R26 指出前一版把它寫成「五種」的封閉列舉而實際列了六項、且還有第七種（`exit 0` 之後），
    所以這裡改回**陳述性質**：凡是需要知道「這行會不會被執行到」的，本掃描器一律看不出來。
    要關掉這一類必須真的求值 shell，不在本 lint 的範圍內。
    """
    code_lines, decls = [], []
    # **分隔字裡的引號在同一行沒收尾 → 這個 run 區塊本 lint 不解析**（R31 opsweep：那個守衛沒有網，
    # 而唯一寫得出來的「會翻色」fixture 會把一個**錯的**判定釘住——前一版假裝引號在行尾收掉、
    # 算出一個終止字，然後對整個 step 回**綠**）。bash 5.3 實測**兩種引號各不相同、但都不是綠**：
    #   `cat <<"AB`（引號到檔尾都沒收）→ 「尋找符合的 `"` 時遇到了未預期的檔案結束符」＝語法錯誤；
    #   `cat <<"XY` ⏎ `data"`（收在下一行）→ 分隔字是**含換行的** `XY⏎data`，heredoc 永不終止，
    #   bash 只警告並把後面全部當內文（實測 `echo` 沒有執行）；單引號同此。
    # 兩種本 lint 都表示不了（它的分隔字是單行字串），所以 fail-closed：交給呼叫端印 `PARSE:`，
    # 且**不再印 `RULE:`**（R24 DA-8(b)：沒被解析出來的區塊沒有適用對象）。
    unparsed = None         # 本 lint 不解析的構造：填原因字串，呼叫端印 `PARSE:`（不再印 `RULE:`）
    # **跨行保留的詞法狀態**（#33 verify R34 logic F3／DA n5、n5b）：算術 `((`（含裡面的單括號）、舊式算術 `$[`、
    # 條件式 `[[`、命令替換 `$(` 與反引號、雙引號裡收不掉而改當 code 掃的命令替換（`dq_ret`，見雙引號分支）。
    # 前一版的算術深度每一行歸零，於是跨行的 `$((1` ⏎ `<<2 ))` 第二行的左移被當成 heredoc。
    arith = arith_par = brk = csub = cpar = 0
    cond = bt = False
    # `bt_at`：反引號開啟那一刻、**反引號以外**所有巢狀狀態的淨值（`nest()`）。註解分支拿它判斷最內層是不是反引號
    # （#33 verify R37 合併時協調者發現，見註解分支）。
    bt_at = None
    # `dq_ret`：從雙引號進入、同一行收不掉的命令替換（堆疊）。元素是進入後的 `csub + cpar`（`$(…)`：括號總深度
    # 跌破它＝這個命令替換收尾）或 0（反引號：`bt` 回到 False＝收尾）；收尾時回到雙引號（R37，R36 第 6 列）。
    dq_ret = []
    # `dq_back`：目前這個雙引號字串是從 `dq_ret` 回來的（前面有過跨行的命令替換）。這種字串裡再出現 `$(`／反引號一律
    # 不解析（R42 plan D8，#33 verify R41 logic F6）：同一行收得掉的會被 `_cmdsub_end_case` 整段挖空，而那段內容沒有別的
    # 分析看得到（單行寫法由整句剖析看見，跨行之後就沒有了），`$(echo "::error::…" >&2)` 因此放行。雙引號收尾時清除。
    dq_back = False
    # `cases`：命令替換裡開著的 case（堆疊），元素是 [所在的括號深度 `csub + cpar`, 階段 "pat"／"cmd"]（R37，見主迴圈）。
    cases = []
    # **裸括號（不屬於 `$(`／`((` 任何一邊）的未配對深度**（R37，#33 verify R36 第 15 列）：`( cmd` 沒有對應的
    # `)` 就掃到 run 區塊結尾，是語法錯誤（跟引號沒收尾同等級），不能靜默放行。只算「沒被 `$(`／`((`／
    # 巢狀 `cpar`／`csub` 認領」的裸 `(`／`)`——判定見下方迴圈裡的 `paren_claimed`。
    bare_par = 0
    # **命令位置**（R37，#33 verify R36 第 5(a) 列）：`[[` 與獨立的 `((` 只在這裡是 True 時才當關鍵字／算術
    # 命令；`$((` 算術展開不看這個旗標（直接看 `prev_sig == "$"`）。新的邏輯行開頭（換行本身就是分隔字元）、
    # `$(`／反引號剛開啟時，都視為命令位置。
    cmd_pos = True
    # **複合命令收尾之後**（#33 verify R37 完整性審查，缺陷 b）：`]]` 或算術**命令** `))` 收尾之後、下一個非空白字元之前是 True。
    # 那個位置的保留字（`if [[ … ]] then`，不寫分號）bash 接不接受取決於外層的 if／while——`if` 裡合法、單獨一行是語法錯誤——
    # 而本 lint 不追蹤複合命令的巢狀，所以遇到就 fail-closed（見主迴圈）。`arith_cmd`：目前這個 `((` 是算術命令、不是 `$((` 展開。
    after_compound = False
    arith_cmd = False
    quote = None            # None / "'" / '"'
    heredoc = None          # (delimiter, strip_tabs, quoted, 開在命令替換裡)
    body_continued = False  # 未引號 heredoc 內文的前一行以奇數個反斜線結尾（R28 D3）
    pending = []            # 這一行結束後依序要讀的 heredoc（FIFO）
    prev_sig = None         # 前一個「有意義」字元（跨行保留，供 `#` 詞首判定）

    def nest():
        # 反引號以外的巢狀狀態（淨值）。反引號開啟時記在 `bt_at`，註解時比對：相同＝反引號開啟之後沒有淨開任何構造。
        return (arith, arith_par, brk, csub, cpar, cond, bare_par, len(cases), len(dq_ret))

    li = 0
    while li < len(lines):
        line = lines[li]
        if line is None:                        # 折疊的佔位：runner 眼中沒有這一行
            code_lines.append(""); li += 1; continue
        spans = 1           # 這個**邏輯行**吃掉幾個實體行（續行摺疊）
        if heredoc is not None:
            delim, strip_tabs, quoted, in_sub = heredoc
            probe = line.lstrip("\t") if strip_tabs else line
            # R28 D2（security S1／Codex #5／requirements F-2）：bash 要求終止字**逐字元相同**，前一版用
            # `rstrip()` 讓 `EOF␠`／`EOF\t` 也算終止 → heredoc 提早結束、資料變 code → rc=0。改精確比對。
            # R28 D3（requirements F-2／regression M-R28-1b）：**未引號** heredoc 的內文行尾反斜線是續行，
            # bash 會把下一行併上來——「前一內文行以奇數個反斜線結尾」時，本行不可能是終止字。
            if probe == delim and not body_continued:      # body_continued 只在未引號 heredoc 才會是 True
                heredoc = pending.pop(0) if pending else None
                body_continued = False
            elif in_sub and delim and probe.startswith(delim) and not body_continued:
                # **開在 `$(…)`／反引號裡的 heredoc**：bash 5.3 以「以終止字開頭」的行結束它（`EOF)`、`EOF )`、
                # `EOFx)` 都算，並警告 delimited by end-of-file；行首多空白不算；一般 `( … )` subshell 不算）。
                # 這是版本相依的舊式相容行為，本 lint 不猜 ⇒ fail-closed（#33 verify R34 logic F3 r1）。
                unparsed = "命令替換裡的 heredoc 以「以終止字開頭、但不等於它」的行收尾——bash 的行為版本相依，本 lint 不解析"
                heredoc = pending.pop(0) if pending else None
                body_continued = False
            else:
                body_continued = (not quoted) and (len(line) - len(line.rstrip('\\'))) % 2 == 1
            code_lines.append("")
            li += 1
            continue
        code, i, n = [], 0, len(line)
        # **新的實體行＝新的命令位置**（R37）：換行本身就是命令分隔字元（等同 `;`），不管上一行是怎麼結束的
        # ——即使上一行以 `&&`／`|` 收尾（該接續到這一行），接續點本來就是命令位置，所以無條件重設為 True
        # 一律正確。仍在 heredoc 內文（上面 `continue` 掉）或仍在 `arith`／`brk`／`cond` 裡的字元不看這個旗標
        # （那些分支在到得了 `[[`／`((` 判定之前就 `continue` 掉了）；`csub`（`$(…)` 內容）不算例外——`$(`
        # 開啟時明確把 `cmd_pos` 設成 True（見下），csub 內容照一般規則用到這個旗標，`case` 追蹤等 csub
        # 專屬邏輯排在 `[[`／`((` 判定之後，不是判定之前就 continue 掉。
        cmd_pos = True
        after_compound = False               # 換行本身就是分隔字元：之後的保留字照一般命令位置處理
        quote0, prev0 = quote, prev_sig      # 邏輯行起點的狀態：摺疊後要從頭重掃
        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, tuple(dq_ret), tuple(map(tuple, cases)), bt_at, arith_cmd,
                dq_back)
        bare_par0 = bare_par                 # 裸括號深度也要快照——續行重掃前這一行已經記的深度要還原
        pending0 = list(pending)             # R28 D6（Codex #2）：快照漏了 pending，重掃會把同一個 heredoc 排兩次
        while i < n:
            ch = line[i]
            if quote == "'":
                # 引號**字元本身**要留著：`PIPED_RE` 的 `\S*` 讀得到它（`python3 ""scripts/neutralise.py`
                # 在 bash 眼中就是那個路徑）。R29 把它一起挖空並宣稱「依構造等價」，R30 MB-12 證偽。
                code.append("'" if ch == "'" else " ")
                if ch == "'":
                    quote = None
                i += 1; prev_sig = ch; continue
            if quote == '"':
                if ch == "\\":
                    code.append("  "); i += 2; prev_sig = "x"; continue   # 行尾 `\` 越界只是結束迴圈
                # **雙引號裡的 `${…}` 走同一個配對剖析**（#33 verify R34 logic F1 p3）：前一版這個分支不進 `${`，
                # `"${X#"…"}"` 的內層引號被當成收尾 ⇒ 每遇到一個 `"` 就切換狀態、假管線變 code。
                if line.startswith("${", i):
                    e = _param_end(line, i)
                    if e is None:
                        unparsed = PARAM_UNPARSED
                        break
                    code.append(" " * (e - i)); i = e; prev_sig = "x"; continue
                if line.startswith("$[", i):
                    # 舊式算術：bash 把 `$[ … ]` 當巢狀結構讀，裡面的 `"` 不收外層（實測 `: "$[ " | … " ]"` 是一個引數、
                    # 沒有管線）——與 `${…}` 裡的 `$[` 同一條（R36 第 5 列 (c) 的相鄰輸入 `bypass-r37c-dq-legacy-arith-inner-quote`）。
                    # 這裡 break 之後 quote 仍是 `"`，run 區塊結尾的一般性檢查（見 `if quote is not None:` 分支）一律會
                    # 覆寫這句成「引號到 run 區塊結尾都沒收」——判定仍是 PARSE-red，但使用者實際看到的不是這句
                    # （已實測：本 fixture 與最小重現 `: "$[ "` 皆印出覆寫後的訊息）。
                    unparsed = "雙引號裡的舊式算術 `$[…]`——bash 把它當巢狀結構讀，本 lint 不解析"
                    break
                if ch == "`" or line.startswith("$(", i):
                    # **雙引號裡的 `$(…)`／反引號是新的引號脈絡**（#33 verify R36 第 6 列）：裡面的 `"` 開的是命令替換
                    # 自己的字串，不是外層的收尾。380e4a4 在這裡只設一個旗標、照樣按雙引號掃，於是
                    # `"$(echo " | python3 …")"` 的假管線變 code（繞過），`"$(tr -d '"')"` 讓引號錯到區塊結尾（PARSE 誤擋）；
                    # 旗標又不在命令替換收尾時清除，同一個雙引號後面的字面 `<<` 也被當 heredoc（R36 第 16 列）。
                    # 現在：(1) 同一行收得掉 ⇒ 整段當不透明內容吃掉（`$((…))` 是算術，由 `_cmdsub_end` 轉給 `_arith_end`）；
                    # (2) 收不掉（跨行、heredoc、註解、`$'…'`、`case`…）⇒ 照 bash 把內容當 **code** 掃：離開雙引號、
                    # 記下進入點（`dq_ret`），這個命令替換收尾時回到雙引號。heredoc 因此由一般的 `<<` 分支登記（R35 的
                    # 「暫時離開雙引號、登記完就回來」只修到登記那一點：heredoc 之後命令替換裡的 `"…"` 仍被當外層的收尾與開頭，
                    # `bypass-r37c-dq-cmdsub-heredoc-then-quoted-code`）。
                    if dq_back:
                        # 見 `dq_back` 的宣告處（R42 plan D8）。break 之後 quote 仍是 `"`，訊息多半會被結尾的一般性檢查覆寫成
                        # 「引號到 run 區塊結尾都沒收」——判定仍是 PARSE-red（`bypass-r42-default-dq-second-cmdsub`）。
                        unparsed = "雙引號裡跨行的命令替換之後，同一個字串又開了命令替換——本 lint 不解析"
                        break
                    e = _backtick_end(line, i) if ch == "`" else _cmdsub_end_case(line, i)   # 雙引號裡：認得 case（合併 r37b×r37c）
                    if e is not None:
                        code.append(" " * (e - i)); i = e; prev_sig = "x"; continue
                    if line.startswith("$((", i):
                        # 這句訊息會不會被使用者看到要看運氣：只有當同一個 run 區塊裡稍後的內容剛好把外層雙引號
                        # 收掉，才不會被結尾的一般性檢查（`if quote is not None:`）覆寫；沒有後續收尾內容時
                        # 一樣會被換成「引號到 run 區塊結尾都沒收」（已用 fixture 與最小重現各實測一次）。
                        unparsed = ("雙引號裡的算術 `$((…))` 本 lint 不解析：同一行沒收尾、裡面有引號／反引號／反斜線，"
                                    "或其實是 `$((…) …)` 形式的命令替換")
                        break
                    if ch == "`" and bt:
                        # 同上：break 後 quote 仍是 `"`，多半會被結尾的一般性檢查覆寫成「引號到 run 區塊結尾都沒收」
                        # （已實測：fixture 與最小重現 `` `echo "a` `` 皆印出覆寫後的訊息）——判定仍是 PARSE-red，
                        # 但這句訊息文字通常不是使用者實際看到的那句。
                        unparsed = "反引號裡的雙引號又開了一個跨行的反引號——巢狀反引號本 lint 不解析"
                        break
                    if ch == "`":
                        bt = True; dq_ret.append(0); bt_at = nest()
                    else:
                        csub += 1; dq_ret.append(csub + cpar)
                    w = 1 if ch == "`" else 2
                    quote = None; code.append(line[i:i + w]); i += w; prev_sig = "`" if w == 1 else "("
                    cmd_pos = True           # 命令替換裡的第一個詞是新命令（合併 r37c×r37d：c 的雙引號分支原本不知道 cmd_pos）
                    continue
                code.append('"' if ch == '"' else " ")
                if ch == '"':
                    quote = None; dq_back = False
                i += 1; prev_sig = ch; continue
            if ch == "\\":
                if i + 1 < n:
                    code.append("  "); i += 2
                    prev_sig = "x"          # 被逃脫的字元一律當成「非空白」——`a\ #` 的 `#` 不起註解
                    cmd_pos = False          # 被逃脫的字元是詞的一部分：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）
                    continue
                # **行尾反斜線＝續行：把下一個實體行接上來，繼續掃同一個邏輯行。**
                # 前一版只是丟掉它、下一行重新當成新行——於是 `cat <\` ⏎ `<EOF` 的 heredoc
                # 開頭被拆成兩半，兩半都不成立，內文整批落回 code 桶（R26 M5／requirements R-1）。
                if li + spans < len(lines):
                    # 摺完之後**從邏輯行開頭重掃**：續行的接縫可能落在一個 token 中間
                    # （`cat <\` ⏎ `<EOF` 的 `<<` 就跨在接縫上），從斷點續掃會看不到它。
                    nxt, used = _next_phys(lines, li + spans)
                    line = line[:i] + nxt
                    n = len(line); spans += used
                    code, i = [], 0
                    quote, prev_sig = quote0, prev0
                    arith, arith_par, brk, csub, cpar, cond, bt = lex0[:7]
                    dq_ret, cases = list(lex0[7]), [list(c) for c in lex0[8]]
                    bt_at, arith_cmd, dq_back = lex0[9], lex0[10], lex0[11]
                    bare_par = bare_par0
                    cmd_pos = True           # 邏輯行起點永遠是命令位置，重掃回到起點也一樣
                    after_compound = False
                    pending = list(pending0)
                    continue
                break                       # 最後一行的行尾反斜線：沒有下一行可接
            # R30 H-2：`$'…'` 是 ANSI-C 引號，裡面的 `\'` 是**逃脫**不是收尾；前一版把它當成普通單引號，
            # 於是引號提早收掉、字串裡的 `| python3 …` 變成 code。
            # **`$"…"` 沒有自己的分支**：它的引號規則與雙引號完全相同，所以 `$` 走通用字元路徑、
            # 下一格的 `"` 走一般引號分支，結果一模一樣。R30 為它寫了一個分支，R31 的 opsweep 對那個
            # `startswith` 報存活——寫不出會翻色的 fixture，因為它本來就不改變任何輸出。**刪掉，
            # 不列預期存活**（同 `fold_block` 那兩個運算元的處置：多餘的程式碼沒有網是因為它沒有行為）。
            if line.startswith("$'", i):
                j = i + 2
                while j < n and line[j] != "'":
                    j += 2 if line[j] == "\\" else 1
                if j >= n:
                    # 跨行的 ANSI-C 字串（#33 verify R34 logic F3 r2）：前一版到行尾就重置，下一行字串內容裡的
                    # 假管線變 code。本 lint 的引號狀態不表示 `$'…'` 的跨行 ⇒ fail-closed。
                    unparsed = "`$'…'` 在同一行沒有收尾——跨行的 ANSI-C 字串本 lint 不解析"
                    break
                code.append(" " * (j + 1 - i)); i = j + 1; prev_sig = "x"; cmd_pos = False; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）
            # R30 H-3：`${VAR#pattern}` 裡的 `#` 不起註解、`|` 不是管線——整個 `${…}` 是**一個詞的一部分**。
            # 前一版逐字元掃，於是 `echo ${PR_TITLE#| python3 …neutralise.py }` 一行就放行。
            # 與 `((` 一樣**整段消費**：找到配對的 `}`（計深度），中間一律不解讀。
            if line.startswith("${", i):
                # **只有巢狀的 `${` 會加一層**——單獨的 `{` 不會（R31 自查）；**只有未引號、未逃脫的 `}` 才結束展開**
                # （R32 security S-1／Codex 第 2 條／DA-1）；**反引號、`$(`、`$'…'`、跨行**（R34 logic F1）——
                # 配對規則全部在 `_param_end()`，不解析的構造 fail-closed。
                e = _param_end(line, i)
                if e is None:
                    unparsed = PARAM_UNPARSED
                    break
                code.append(" " * (e - i)); i = e; prev_sig = "x"; cmd_pos = False; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）
            if arith or brk or cond:
                # **算術 `((…))`、舊式算術 `$[…]`、條件式 `[[…]]` 裡的內容不是 code**（#33 verify R34 DA n5、n5b）：
                # 那裡的 `|` 是位元 OR／正規式的「或」，不是管線；`<<` 是左移／字串比較，不是 heredoc。
                # 前一版把 `$(( 1 | python3 …neutralise.py ))` 與 `[[ x =~ (a| python3 … ) ]]` 讀成真管線 ⇒ 放行。
                # 這些狀態**跨行保留**（R34 logic F3 t2）。
                if ch in ("'", '"'):
                    quote = ch; code.append(" "); i += 1; prev_sig = ch; continue
                if arith:
                    if ch == "(":
                        arith_par += 1
                    elif ch == ")" and arith_par:
                        arith_par -= 1
                    elif line.startswith("))", i):
                        arith -= 1; code.append("))"); i += 2; prev_sig = ")"; cmd_pos = False
                        after_compound = arith_cmd and not arith; continue
                    elif ch == ")":
                        # **未配對的單獨 `)`**（R37，#33 verify R36 第 5(a) 列）：`((cmd) )` 不是算術——bash 把它讀成
                        # 巢狀 subshell（外層 `(` 加內層 `(cmd)`），`((` 進入算術模式的判定本來就是啟發式的猜測，
                        # 猜錯的訊號正是這裡出現一個 `arith_par` 沒認領、也不構成 `))` 的孤兒 `)`。前一版把它靜默
                        # blank 掉（落到下面的 `code.append(" ")`），於是永遠等不到收尾、把整行剩下的真管線一起吞掉
                        # 卻不出聲；探針 `((echo "$PR_TITLE") ) #))2>&1| python3 …` bash 實測是巢狀 subshell 執行、
                        # PR 文字裸印。不再猜，直接 fail-closed。
                        unparsed = "`((…))` 裡出現未配對的單獨 `)`——可能是巢狀 subshell `((cmd) )` 不是算術，本 lint 不猜"
                        break
                    # （算術裡的 `((` 只是兩個括號，由上面的單括號計數處理。R35 第一版另寫了一個巢狀 `((` 分支，
                    # 排在 `ch == "("` 之後、永遠走不到——opsweep 報存活，刪掉；`good-arith-double-paren` 守住。）
                elif brk:
                    if ch == "[":
                        brk += 1
                    elif ch == "]":
                        brk -= 1
                elif line.startswith("]]", i) and line[i - 1:i] in (" ", "\t"):
                    cond = False; code.append("]]"); i += 2; prev_sig = "]"; cmd_pos = False; after_compound = True; continue
                code.append(" "); i += 1; prev_sig = "x"; continue
            if after_compound and not ch.isspace():
                after_compound = False
                m = re.match(r"[A-Za-z]+", line[i:])
                w = m.group() if m else ""
                if w in ("then", "do", "else", "elif", "if", "while", "until") \
                        and line[i + len(w):i + len(w) + 1] in (" ", "\t", ";", ""):
                    unparsed = ("`]]`／算術命令 `))` 之後直接接保留字 `%s`（沒有分號或換行）——bash 接不接受取決於外層的 "
                                "if／while，本 lint 不追蹤複合命令的巢狀，不解析" % w)
                    break
            if ch in ("'", '"'):
                quote = ch; code.append(ch); i += 1; prev_sig = ch; cmd_pos = False; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）
            # **保留字**（R37，延伸自 #33 verify R36 第 5(a) 列的位置敏感性原則——原列只點名 `[[`／`((`，不是這幾個保留字）：
            # `then`／`do`／`else`／`elif`／`if`／`while`／`until`
            # 本身就是命令位置才成立的保留字，且它們後面**接著也是**命令位置（`if <cmd>`、`then <cmd>`…）。
            # 只在目前已經是命令位置、且這裡是一個詞的開頭（`prev_sig` 落在詞界）時才整段消費並保持
            # `cmd_pos = True`；不是保留字就不消費，落到下面逐字元處理（第一個字元就會把 `cmd_pos` 收回 False，
            # 見迴圈最底端）。
            if (cmd_pos and ch.isalpha() and (prev_sig is None or prev_sig in SHELL_WORD_BREAK)):
                m = re.match(r"[A-Za-z]+", line[i:])
                w = m.group() if m else ""
                if w in ("then", "do", "else", "elif", "if", "while", "until") \
                        and line[i + len(w):i + len(w) + 1] in (" ", "\t", ";", ""):
                    code.append(w); i += len(w); prev_sig = w[-1]; continue
            if line.startswith("$[", i):
                brk = 1; code.append("  "); i += 2; prev_sig = "x"; continue
            # **`[[` 只在命令位置才是條件式關鍵字**（R37 修正 R35 回歸，#33 verify R36 第 5(a) 列）：R35 只查
            # 「前一個字元是不是 metacharacter」（`SHELL_WORD_BREAK` 本身含空白），於是「前面有空白」被誤當
            # 「在命令位置」——`echo "$PR_TITLE" [[ # ]] …` 這種**引數位置**的 `[[` 因此被誤判成條件式。
            # 改查 `cmd_pos`（見上方定義與迴圈最底端如何維護）。
            if (line.startswith("[[", i) and line[i + 2:i + 3] in (" ", "\t", "")
                    and cmd_pos):
                cond = True; code.append("[["); i += 2; prev_sig = "["; cmd_pos = False; continue
            if line.startswith("$(", i) and not line.startswith("$((", i):
                # `$(`／反引號開啟時，裡面第一個詞就是一條新命令的開頭——視為命令位置
                # （`good-cmdsubst-arith-then-heredoc` 的 `x=$( ((1)) )` 需要這個才能把 `((` 認成算術）。
                csub += 1; code.append("$("); i += 2; prev_sig = "("; cmd_pos = True; continue
            # **`((` 只在命令位置才是算術命令**（R37 修正 R35 回歸，同上；`$((` 算術**展開**不受限——
            # 那是完全不同的構造，看 `prev_sig == "$"` 直接判定，與位置無關）。不成立就不消費，
            # 落到下面逐字元處理，兩個 `(` 各自當成裸括號（見 `paren_claimed`／`bare_par`）。
            paren_claimed = False
            if line.startswith("((", i) and (prev_sig == "$" or cmd_pos):
                arith_cmd = prev_sig != "$"          # `$((` 是算術展開：後面的詞是引數，不是保留字的位置
                arith += 1; code.append("(("); i += 2; prev_sig = "("; paren_claimed = True; continue
            # **`$(…)` 裡的 `case`**（#33 verify R36 第 7 列）：模式括號是單邊 `)`，只數括號的 `csub` 會提早
            # 歸零，之後開的 heredoc 被當成不在命令替換裡——R35 的「命令替換裡的 heredoc 以前綴收尾 ⇒ fail-closed」因此被繞過
            # （`bypass-r37c-case-cmdsub-heredoc-prefix-term`）；從雙引號進來的命令替換（`dq_ret`）也會提早回到雙引號。
            # R37 第一版照工作包一律 fail-closed，語料對照量到野外合法寫法（`bad="$(` ⏎ `… case "$p" in a|b) ;; esac` ⏎ `)"`，
            # openclaw 兩檔、`bash -n` rc=0）因此新增 PARSE，改成**追蹤**：`cases` 記每個開著的 case 所在的括號深度與階段
            # （"pat"：等模式、"cmd"：模式之後的命令），在它那一層 `)` 是模式括號、不減深度。凡是追蹤表示不了的形狀一律
            # fail-closed（封閉列舉，只有這兩種）：(1) `case` 不在命令起點（`_at_command`）或後面不是 `WORD in`（`_case_head`）；
            # (2) 子句命令裡出現同一層的單獨 `)`（bash 語法錯誤）。不在命令起點、也不在模式位置的 `esac` 是一般參數，
            # 照 bash 不理它（`bypass-r37c-dq-case-esac-argument`）。命令替換外的 case 不追蹤：那一層的 `)` 本來就不動深度。
            if csub and (prev_sig is None or prev_sig in SHELL_WORD_BREAK):
                kw = CASE_KW_RE.match(line, i)
                if kw:
                    at_cmd = _at_command("".join(code), cases, csub + cpar)
                    if kw.group(1) == "case":
                        if not (at_cmd and _case_head(line, i)):
                            unparsed = ("命令替換 `$(…)` 裡的 `case` 不在命令起點、或後面不是 `WORD in`——"
                                        "模式括號是單邊 `)`，本 lint 表示不了這個形狀，不解析")
                            break
                        cases.append([csub + cpar, "pat"])
                    elif cases and cases[-1][0] == csub + cpar and (cases[-1][1] == "pat" or at_cmd):
                        cases.pop()
            if cases and cases[-1][0] == csub + cpar and cases[-1][1] == "cmd" and line.startswith((";;", ";&"), i):
                cases[-1][1] = "pat"                        # `;;`／`;&`／`;;&`：回到等模式
            if ch == "(" and csub and not line.startswith("((", i):   # `((` 是算術，下面另外處理
                if not (cases and cases[-1][0] == csub + cpar and cases[-1][1] == "pat"):
                    cpar += 1                               # 等模式時的 `(` 是模式的前導括號（`(a) cmd;;`），不計深度
                paren_claimed = True                        # 在命令替換裡：由 cpar／case 追蹤負責，不是裸括號（合併 r37c×r37d）
            elif ch == ")" and cases and cases[-1][0] == csub + cpar:
                if cases[-1][1] == "cmd":
                    unparsed = "命令替換裡 case 子句的命令之後有同一層的單獨 `)`——bash 語法錯誤，本 lint 不解析"
                    break
                cases[-1][1] = "cmd"                        # case 的模式括號：不減深度
                paren_claimed = True                        # 模式括號不是裸括號（合併 r37c×r37d）
            elif ch == ")" and cpar:
                cpar -= 1; paren_claimed = True
            elif ch == ")" and csub:
                csub -= 1; paren_claimed = True
            elif ch == "`":
                cmd_pos = not bt    # 開啟（bt False→True）：裡面第一個詞是新命令；關閉：回到外層的引數位置
                bt = not bt
                if bt:
                    bt_at = nest()
            if dq_ret and ((ch == "`" and not bt) if dq_ret[-1] == 0 else (ch == ")" and csub + cpar < dq_ret[-1])):
                # 從雙引號進來的命令替換在這裡收尾（見雙引號分支）：回到雙引號。
                dq_ret.pop(); quote = '"'; dq_back = True
                cmd_pos = False          # 回到雙引號＝回到同一個詞的中間，不是命令位置（合併 r37c×r37d）
                code.append(ch); i += 1; prev_sig = ch; continue
            if ch == "#" and (prev_sig is None or prev_sig in SHELL_WORD_BREAK):
                # **反引號裡的註解止於收尾反引號**（#33 verify R37 合併時協調者發現）：bash 先照字面找收尾反引號
                # （反斜線逃脫下一個字元）、再把中間當指令剖析，所以 `echo a `# x` b` 印 `a b`。前一版一律吃到行尾：
                # 收尾反引號之後的程式碼跟著消失、`bt` 留在 True——R37 新增的區塊結尾檢查因此把合法的 bash 判 PARSE
                # （生成語料 gen-c-backtick-* 八個檔）。只在**最內層就是反引號**時成立：反引號裡又開了 `$(`／`(`，
                # 註解吞掉的是那一層的收尾（bash 報語法錯誤），照舊吃到行尾、由區塊結尾的檢查 fail-closed。
                # 同一行沒有收尾反引號＝跨行的反引號，註解止於行尾，也照舊。
                if bt and nest() == bt_at:
                    e = _backtick_end(line, i)
                    if e is not None:
                        decls.append(line[i:e - 1]); code.append(" " * (e - 1 - i)); i = e - 1; prev_sig = " "; continue
                decls.append(line[i:]); break
            # R28 D1（logic／requirements／Codex 第 3 條）：前一版 `$((` 在 `$` 處與第一個 `(` 處各命中一次、
            # `))` 只減一次，每個 `$(( … ))` 之後 arith 卡在 1，同一行後面的真 heredoc 過不了守衛。
            # **不能只刪 `$((`**（DA 實測 `$(((1+2)*3))` 仍卡）——要**整段消費**：命中就把 token 整個吃掉。
            # `$((` 不另開分支：`$` 在這支掃描器裡沒有特殊意義，`$((` 就是 `$` 接 `((`，由上面新的 `((` 判定處理
            # （`prev_sig == "$"` 那個分支）——**這裡不再重覆一次無條件版本**（R37：舊的無條件 `if
            # line.startswith("((", i): arith += 1 …` 排在這個位置會讓上面剛加的命令位置判定形同虛設——
            # 判定失敗落到這裡又整段吃掉，跟沒判一樣。R29 mutation 那句「依構造等價」的舊結論到這裡不再成立，
            # 因為現在兩個分支的判斷條件不同了）。
            if line.startswith("<<<", i):
                code.append("<<<"); i += 3; prev_sig = "<"; continue   # here-string，不是 heredoc
            if line.startswith("<<", i):
                j = i + 2
                strip_tabs = False
                if line[j:j + 1] == "-":            # 切片越界回空字串，不另寫 `j < n` 守衛
                    strip_tabs = True; j += 1
                while line[j:j + 1] in (" ", "\t"):
                    j += 1
                # R30 H-1：**bash 讀的是一個「詞」，然後對整個詞做 quote removal**——引號可以出現在詞的
                # 任何位置、出現幾次都行。前一版只認「詞的開頭是引號」，引號之後的字元整段丟掉，於是
                # `<<"EO"F`（delim 該是 `EOF`）被讀成 `EO`、`<<""EOF` 被讀成**空字串**（空的不登記 heredoc，
                # 整段內文直接變 code）、`<<'EOF'x` 被讀成 `EOF`。四個形狀一個根因：**沒有做 quote removal**。
                # 這裡照 bash 的性質做：讀到詞界為止，引號內的字元原樣進 delim；
                # **詞裡出現引號、或出現當成逃脫用的反斜線，整個 heredoc 就是 quoted**（內文不展開）。
                # 「行尾反斜線」是**例外**：那是續行、不是逃脫，不使 heredoc 變成 quoted——
                # R30 的註解把這一條寫成全稱（「行尾 `\` 不續行」），bash 5.3 實測證偽：
                #   `cat <<AB\` ⏎ `CD` 的終止字是 `ABCD`，而且內文**照樣展開**（`$X` → 值）；
                #   `cat <<"AB\` ⏎ `CD"` 的終止字也是 `ABCD`，內文不展開（因為有引號，不是因為反斜線）；
                #   `cat <<'AB\` ⏎ `CD'` **不**續行——單引號裡反斜線與換行都是字面，delim 跨兩行、
                #   bash 直接警告 EOF。三條規則不同，所以下面分三處寫。
                # R31：前一版這裡完全沒有續行，於是 `<<AB\` 的 delim 被讀成 `AB\` 並且被判成 quoted——
                # 終止字永遠對不上 → heredoc 吃到檔尾 → 真管線被吞掉＝**誤擋**，方向與 R30 的繞過相反
                # 但同樣是「lint 與 bash 對同一段文字的詞法不一致」。opsweep 對這兩個 `j + 1 < n`
                # 各報存活，指的就是這裡沒有網。
                # `saw_word`：**有沒有讀到分隔字詞**，與「詞 quote removal 之後是不是空字串」分開。
                # bash 實測：`cat <<''` 的終止字是**空字串**，一行空行就終止它（警告訊息寫「需要「」」）。
                # 前一版用 `if delim:` 把兩者混為一談 ⇒ 不登記 heredoc ⇒ 下一行的假管線被當成 code
                # ＝繞過（R32 Codex 第 3 條靜態預測、DA-5 執行確認）。
                delim, quoted, saw_word = "", False, False
                while j < n and line[j] not in DELIM_WORD_BREAK:
                    c = line[j]
                    # `$(…)` 與 `` `…` `` 在分隔字詞裡是**詞的一部分**，原樣進 delim（bash 不在此展開，
                    # 也不在此斷詞）。整段消費，中間不解讀。
                    if line.startswith("$(", j):
                        # bash 對分隔字裡的 `$(…)` **重新序列化**再當終止字：`cat <<EOF$(a;b)` 的 EOF 警告寫
                        # 「需要 EOF$(a; b)」（多了一個空格）。詞法上抄不出 bash 的序列化，所以本 lint 不解析它
                        # ——fail-closed 走 PARSE，與「引號沒收尾」同一條出口（R33 開發迭代內部：opsweep 對一版
                        # 整段消費 `$(…)` 的運算元報存活而刪掉；這裡的「前一版」指 R33 過程中的過渡草稿，不是
                        # 已提交的 d8340a6——d8340a6 這段迴圈用 SHELL_WORD_BREAK 斷詞，遇到 `(` 就提早斷開，
                        # 從未整段消費過 `$(…)`。它們守的東西——bash 對分隔字 `$(…)` 的重新序列化——本來就
                        # 追不到，故 fail-closed）。
                        unparsed = "heredoc 分隔字裡有 `$(…)`——bash 會重新序列化它，本 lint 不解析"; j = n; saw_word = True; break
                    if line.startswith("${", j) or line.startswith("$[", j):
                        # **`${…}`／`$[…]` 在分隔字詞裡也是詞的一部分**（R37，#33 verify R36 第 14 列）：bash 的
                        # 分詞器對 `${…}` 整段當一個 token 讀，裡面即使有空白也不斷詞——`cat <<\x${X:-a b}` 的
                        # 終止字是 `x${X:-a b}`（實測 bash 5.3），不是掃到第一個未跳脫空白就停。前一版沒有這條
                        # 分支，`$`／`{` 各自當成普通字元收進 delim，遇到內部空白（在 `DELIM_WORD_BREAK` 裡）就
                        # 提早斷詞——lint 認得的終止字比 bash 短，heredoc 提早結束、假管線變成 code。
                        # 與 `$(…)` 同一個道理：bash 是否對它重新序列化、有無展開，詞法上都抄不出來，fail-closed。
                        unparsed = "heredoc 分隔字裡有 `${…}`／`$[…]`——bash 把整段讀成一個詞（可能含空白），本 lint 不解析"
                        j = n; saw_word = True; break
                    if c == "`":
                        # 反引號在分隔字裡**逐字保留**（實測 `cat <<EOF`a;b`` 需要「EOF`a;b`」，不重排）：
                        # 讀到配對的反引號為止，中間的 `;`／空白都不是詞界。
                        k = line.find("`", j + 1)
                        k = n if k < 0 else k + 1
                        delim += line[j:k]; j = k; saw_word = True; continue
                    if line.startswith("$'", j):
                        # **`$'…'` 做 quote removal 並解 ANSI-C 逃脫**（#33 verify R34 logic F3 q2、DA n1）：`cat <<$'EOF'`
                        # 的終止字是 `EOF`。前一版把 `$` 收進 delim ⇒ 終止字比 bash 長 ⇒ 兩個方向都錯（繞過與誤擋）。
                        k, raw = j + 2, []
                        while k < n and line[k] != "'":
                            step = 2 if line[k] == "\\" else 1      # 行尾的 `\\` 越界也無妨：迴圈以 k ≥ n 結束、下面回 None（opsweep 報 `k + 1 < n` 存活，死碼刪掉）
                            raw.append(line[k:k + step]); k += step
                        dec = _ansic_decode("".join(raw)) if k < n else None
                        if dec is None:
                            unparsed = "heredoc 分隔字用 `$'…'`，而它沒收尾或含本 lint 不解碼的逃脫（`\\c`、控制字元）"
                            j = n; saw_word = True; break
                        delim += dec; quoted = True; saw_word = True; j = k + 1; continue
                    if line.startswith('$"', j):
                        j += 1; continue                 # `$"…"` 的引號規則與雙引號相同（logic F3 q3）
                    if c in ("'", '"'):
                        saw_word = True
                        quoted = True; q = c; j += 1
                        while j < n and line[j] != q:
                            # **雙引號裡的反斜線只在特定後繼字元前才是逃脫**（bash：`$`、`` ` ``、`"`、`\`、換行）。
                            # 其餘位置它是**字面**：`<<"E\OF"` 的終止字是 `E\OF`，不是 `EOF`（實測 bash 5.3）。
                            # R31 自查：第一版無條件吃掉反斜線，於是 lint 的 delim 比 bash 短——
                            # 一行 `EOF` 在 lint 眼中終止 heredoc、在 bash 眼中還是資料，
                            # 後面的假管線因此變成 code 而放行，真正的 `echo "$PR_TITLE"` 照樣執行＝繞過。
                            if q == '"' and line[j] == "\\" and j + 1 == n:   # 越界由 _next_phys 回 "" 處理
                                nxt, used = _next_phys(lines, li + spans)   # 續行：`\` 與換行一起消失
                                line = line[:j] + nxt
                                n = len(line); spans += used; continue
                            # `j + 1 < n` 在這裡是死的：`\` 在行尾的情形已被上面的續行分支接走（opsweep 報存活，刪掉）
                            if (q == '"' and line[j] == "\\"
                                    and line[j + 1] in ('$', '`', '"', '\\')):
                                delim += line[j + 1]; j += 2; continue
                            delim += line[j]; j += 1
                        if j >= n:                   # 迴圈是因為讀到行尾才停的：收尾引號不存在（`and not unparsed` 只決定訊息寫哪個原因、判定都是 PARSE——opsweep 報存活，刪掉）
                            unparsed = "heredoc 分隔字裡的引號在同一行沒有收尾——分隔字會含換行，本 lint 不解析它"
                        j += 1                       # 收尾引號
                        continue
                    if c == "\\" and j + 1 == n:                          # 越界由 _next_phys 回 "" 處理
                        nxt, used = _next_phys(lines, li + spans)                 # 續行：**不**設 quoted（實測會展開）
                        line = line[:j] + nxt
                        n = len(line); spans += used; continue
                    if c == "\\":                                     # 行尾的 `\` 已被上面的續行分支接走
                        quoted = True; delim += line[j + 1]; j += 2; continue
                    delim += c; j += 1; saw_word = True
                if saw_word:
                    pending.append((delim, strip_tabs, quoted, bool(csub or bt)))   # 從雙引號進來的命令替換也計入 csub／bt（見雙引號分支）
                code.append("<<"); i = j; prev_sig = "<"; continue
            code.append(ch); i += 1
            # **裸括號深度**（R37，#33 verify R36 第 15 列）：走到這裡的 `(`／`)` 是沒被 `$(`／`((`／巢狀
            # `cpar`／`csub` 認領的（`paren_claimed` 由上面那段判定；本掃描器裡任何會 `continue` 掉的分支
            # 都不會落到這裡，所以這裡看到的 `paren_claimed` 一定是**這個字元自己**的判定結果）。
            if ch == "(" and not paren_claimed:
                bare_par += 1
            elif ch == ")" and not paren_claimed and bare_par:
                bare_par -= 1
            # **命令位置**（R37）：見 `CMD_POS_CHARS` 旁的說明。
            if ch in "!{":
                # `!`／`{` 只有**本身在命令位置、而且是獨立的詞**時才是保留字（其後是命令位置）；在引數位置它們只是
                # 普通字元——`echo ! [[ # ]] …` 的 `[[` 是參數、` #` 起註解（R37 合併時發現，見 bypass-r37m-*）。
                cmd_pos = cmd_pos and line[i:i + 1] in ("", " ", "\t")
            elif ch in CMD_POS_CHARS:
                cmd_pos = True
            elif ch == "`":
                pass    # 反引號分支已經設好（開啟 True：裡面第一個詞是新命令；關閉 False）。前一版在這裡覆寫成 False，
                        # 反引號裡的 `[[` 因此不被當條件式、正規式的 `(a| python3 …)` 被讀成管線（#33 verify R37 完整性審查，缺陷 a）
            elif not ch.isspace():
                cmd_pos = False
            if not ch.isspace():
                prev_sig = ch
            else:
                prev_sig = ch
        code_lines.append("".join(code))
        for _ in range(spans - 1):
            code_lines.append("")      # 被摺進來的實體行沒有自己的程式碼
        prev_sig = None                # 邏輯行結束
        if pending:                     # 走到這裡 heredoc 必為 None：內文行在迴圈頂端就被消化掉、不會掃到這
            heredoc = pending.pop(0)
        li += spans
    if quote is not None:              # `and not unparsed` 只決定訊息寫哪個原因、判定都是 PARSE（opsweep 報存活，刪掉）；
        # 注意：這一句無條件覆寫上面雙引號分支裡任何已設的 unparsed 訊息（例如 967／983／987 行附近的訊息），
        # 只要 break 當下 quote 仍非 None——訊息文字最終是否被使用者看到，取決於同一個 run 區塊後面有沒有
        # 內容意外把雙引號收掉（各訊息旁已補上個別實測結果）。
        # **引號開到 run 區塊結尾**（R35，E 組語料抓到）：那一行在 bash 是語法錯誤、不會執行，而它前面的行照樣先執行——
        # lint 若照讀引號之前的 `| python3 …` 就會看到一條永遠不會建立的管線。bash 語法錯誤的行本 lint 不解析 ⇒ fail-closed。
        unparsed = "引號到 run 區塊結尾都沒收——那一行在 bash 是語法錯誤、不會執行，本 lint 不解析"
    elif dq_ret:
        # **雙引號裡的命令替換開到 run 區塊結尾**（R37）：與上一條同一個理由。R37 以前這一種落在上一條（整段都按雙引號掃，
        # 引號狀態停在 `"`）；現在收不掉的命令替換照 code 掃、引號狀態是「沒有引號」，上一條碰不到它
        #（`bypass-r37c-dq-cmdsub-unclosed-at-block-end`）。
        unparsed = "雙引號裡的命令替換到 run 區塊結尾都沒收——那一行在 bash 是語法錯誤、不會執行，本 lint 不解析"
    elif arith or brk or cond or csub or bt or bare_par:
        # **掃描結束時任一構造沒收尾**（R37，#33 verify R36 第 15 列）：`((`／`$[`／`[[`／`$(`／反引號／裸
        # `(` 任一沒配對，那一段在 bash 都是語法錯誤（或至少是本 lint 表示不了的懸置狀態），比照「引號開到
        # 區塊結尾」一視同仁：不猜、fail-closed。前一版只查 `quote`，於是管線後面接 `$(`、反引號、`; ((`、
        # `; [[ -n x`、`$[`、`; (` 六種未收尾構造全部被靜默吞到檔尾、真管線一起消失卻不出聲（探針見
        # `test/fixtures/ci-log-filter-bypass-r37d-unterm-*.yml`）。
        unparsed = ("run 區塊結尾時 `((`／`$[`／`[[`／`$(`／反引號／裸 `(` 有未收尾的（arith=%d brk=%d cond=%s "
                    "csub=%d bt=%s bare_par=%d）——那一段在 bash 是語法錯誤或本 lint 表示不了的懸置狀態，"
                    "本 lint 不解析" % (arith, brk, cond, csub, bt, bare_par))
    elif any(EXTGLOB_RE.search(c) for c in code_lines if c):
        # **`shopt -s extglob`**（R37，#33 verify R36 第 17 列；已知不涵蓋第三組第 4 條）：見 `EXTGLOB_RE` 旁的說明。
        unparsed = "`shopt -s extglob` 改變 bash 的詞法（`@(`／`!(`／`+(`… 等擴展 glob）——本 lint 不解析，fail-closed"
    return code_lines, decls, unparsed


# ══ 規則層的詞法（#33 verify R36 第 3、4、8、9、22 列）══════════════════════════════════════════════════
# R35 的 fd 流向、`--strict` 的 `2>&1`、pipefail 三條規則都是**對挖空後的程式碼搜正規式**：`FD_RE` 是一份拼法清單
# （`>&2`、`>/dev/stderr`、`set -x`…），`--strict` 的 `2>&1` 比 `PIPED_RE` 與 `STRICT_NEUT_RE` 的**總數**，pipefail 用
# `ANY_PIPE_RE` 找「第一個 `|`」、用 `BASH_SHELL_RE` 把「shell 是 bash」當成「有 pipefail」。R36 在每一條上都找到作者沒點名
# 的相鄰輸入：引號包住的目標 `>"/dev/stderr"`（挖空之後字面清單看不到）、`/dev/fd/2`、`>&02`、`>&"2"`、另存的 fd、
# `set -eo xtrace`、`shopt -so xtrace`、從 `env:` 帶進的 SHELLOPTS；前段管線的 stderr、子殼層湊數、黏在詞上的 `"$X"2>&1`；
# `bash -e {0}`／`bash -l {0}` 沒有 pipefail；`case … in a|b)` 的模式 `|` 被當成管線；規則還擋掉它自己推薦的群組寫法。
# 修法是改成**按結構與流向**判：把 `shell_scan()` 的程式碼半邊對回原文（`_aligned_sources`），切成詞與運算子（`_lex`），
# 剖析成管線／群組／簡單命令（`_Sh`）。**R42 起這一節只有預設模式在用**，讀這份結構的規則只剩一條：
#   · fd 流向：fd 複製（`2>&1` 與 no-op 的 `>&1` 除外）、去引號後落在 `/dev`、`/proc` 底下的寫檔目標（`_SAFE_TARGETS` 除外）、
#     開 xtrace／verbose 的命令、run 裡設定 SHELLOPTS 等變數——都算外流，除非它位在「收尾後緊接 `2>&1 |`（或 `|&`）進
#     neutralise 的群組」裡：那個群組是管線的一段、在子殼層裡跑，fd 1 與 fd 2 都是管線。
# R36 另外兩條讀這份結構的規則已經不在：`--strict` 的 `2>&1`（R37 改成整個區塊一個群組，R42 再改成正面文法的 `run_F`），
# pipefail 的詞元順序模擬（R37–R40；R42 刪除，`--strict` 的 pipefail 改由樣板與 `set` 前綴決定，見 `flat_step_rules`）。
# **已知不涵蓋（這一節的，預設模式；封閉列舉，只有三條，不得依性質相似類推第四條）**：
#   1. 重導向目標含參數展開或命令替換（`> "$GITHUB_OUTPUT"`、`> "$X"`）時不求值——`$GITHUB_OUTPUT` 這類是 Actions 的日常寫法；
#      只有目標的**字面部分**已經落在 `/dev`、`/proc` 底下（`>/dev/fd/$N`）才擋。
#   2. `eval`／`bash -c`／`trap` 的**字串**不剖析（同 `shell_scan` 第一組：本 lint 不求值）；`eval` 後面全是字面詞時例外——
#      那時 bash 執行的就是那幾個詞（`eval set -x`）。
#   3. 未引號 heredoc 的**內文**裡的命令替換（bash 會展開、執行它）不剖析：掃描器把內文整行當資料、規則層收不到那些行。
#      雙引號與 `${…}` 裡的命令替換**有**剖析（`_hidden_subs`）。
import posixpath

_OPS = ("&>>", ";;&", "<<<", "&>", "&&", ">>", ">|", ">&", "<&", "<>", "<<", "||", "|&", ";;", ";&",
        "&", "|", ";", "(", ")", "<", ">")
_REDIR_OPS = frozenset(("&>>", "&>", ">>", ">|", ">&", "<&", "<>", "<<", "<<<", "<", ">"))
_WORD_END = " \t\n;&|<>()"
_TRACE_OPTS = frozenset(("xtrace", "verbose"))
_SHELL_NAMES = frozenset(("bash", "sh", "dash", "ksh", "zsh", "mksh", "ash", "posh"))
# 不會把 stdout 帶離管線的寫檔目標（normpath 之後比對；另外 `/dev/tcp/…`、`/dev/udp/…` 是 bash 的網路 socket，見 `_redir_hit`）；
# 其餘落在 /dev、/proc 底下的一律算外流（`/dev/stderr`、`/dev/fd/2`、`/proc/self/fd/2`、`/dev/tty`…）——白名單，不是拼法清單。
_SAFE_TARGETS = frozenset(("/dev/null", "/dev/stdout", "/dev/fd/1", "/proc/self/fd/1"))
# bash 啟動時讀、會開 xtrace 或執行別的程式碼的環境變數（`env:` 三層都查；ENV 只有 `env:` 層——run 裡 `ENV=prod make` 是常見寫法）。
ENV_TRACE_KEYS = ("SHELLOPTS", "BASHOPTS", "BASH_ENV", "ENV", "BASH_XTRACEFD")
ENV_EXPR_RE = re.compile(r"PYTHON\w*=\$\{\{ … \}\}")     # `_env_names` 對值是運算式的 `PYTHON*` 鍵的記法（R39，R38 第 9 列）
_RUN_ENV_KEYS = ("SHELLOPTS", "BASHOPTS", "BASH_ENV", "BASH_XTRACEFD")
_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")
_LEAD_WORDS = frozenset(("!", "time", "if", "then", "else", "elif", "do", "while", "until", "builtin", "command"))
# 其中 `command`、`builtin` 是 **builtin**：加引號或跳脫照樣執行（`\command -p set -x`、`'builtin' set +o pipefail`），所以用字面值 `lit`
# 判（R40，#33 verify R39 第 5、7 列）。其餘是**保留字**：加了引號就不是保留字（`'time' -p set -x` 執行外部 `time`、不開 xtrace），
# 照挖空後的 `code` 判。封閉列舉，只有這兩個。
_LEAD_BUILTINS = frozenset(("builtin", "command"))
# 前綴詞自己的選項（R39，#33 verify R38 第 4、8 列）：封閉列舉，只有這三個詞的這些選項。
_LEAD_OPTS = {"command": frozenset(("-p", "--", "-v", "-V")), "builtin": frozenset(("--",)), "time": frozenset(("-p", "--"))}
# `set` 的單字母選項（bash 5.3 `help set`）——`opaque_cmd` 判「參數像 `set -x`」用。
_SET_LETTERS = "abefhkmnptuvxBCEHPT"


def _skip_delim_word(s, j):
    """`<<` 後面（含 `-` 與空白）那個分隔字詞在**原文**裡的結尾——`shell_scan()` 讀了它卻不輸出到程式碼，對齊時要跳過。
    讀不出來（引號沒收尾）回 None，呼叫端把那一行當成對不齊。"""
    n = len(s)
    if s[j:j + 1] == "-":
        j += 1
    while s[j:j + 1] in (" ", "\t"):
        j += 1
    while j < n and s[j] not in DELIM_WORD_BREAK:
        if s[j] in ("'", '"', "`") or s.startswith("$'", j):
            ansic = s[j] == "$"
            q = "'" if ansic else s[j]
            k = j + (2 if ansic else 1)
            while k < n and s[k] != q:
                k += 2 if (s[k] == "\\" and (q != "'" or ansic)) else 1
            if k >= n:
                return None
            j = k + 1
            continue
        j += 2 if s[j] == "\\" else 1
    return j


def _aligned_sources(code_lines, src_lines):
    r"""每一個程式碼行在原文裡的對應文字——與程式碼**等長、逐位置對齊**；對不齊回 None。

    `shell_scan()` 的程式碼行與原文逐位置相同，只有四種差異：引號內容、`${…}`、`$'…'`、逃脫字元被挖成空白（等長）；
    `#` 註解被截掉（程式碼較短）；行尾 `\` 續行把下一個實體行接上來重掃；`<<` 之後的分隔字詞被讀掉、不輸出（原文較長）。
    這裡照這四條對上去，並**逐字驗證**：程式碼每一個非空白字元都要等於原文同一位置的字元。驗證不過就是 None——
    規則層把那一行的詞當成「看不到原文」，往 fail-closed 的方向判（`_redir_hit`、`set`／`shopt` 的非字面參數）。

    **行尾 `\` 要不要接下一行，看掃描器自己的答案**：它把接進來的每一個實體行記成空的程式碼行。所以「下一個實體行的程式碼
    是空字串」⟺ 掃描器接了它；不是空字串就是引號裡的字面反斜線（雙引號裡程式碼挖成兩格空白）。前一版試過用程式碼裡的引號
    字元自己追蹤引號狀態——雙引號裡的 `$(…)` 讓程式碼的引號配對與 bash 不同，追蹤一錯就連錯到後面每一行（野外語料 5 → 20 行）。"""
    out = []

    def joined(m):
        """實體行 m 之後的下一個實體行（跳過折疊佔位）；掃描器接過它就回它的 index，否則 None。"""
        m += 1
        while m < len(src_lines) and src_lines[m] is None:
            m += 1
        return m if m < len(src_lines) and not code_lines[m] else None

    for k, c in enumerate(code_lines):
        if not c:
            out.append("")
            continue
        s, tail, a, i, j, ok = src_lines[k] or "", k, [], 0, 0, True
        while i < len(c):
            if j >= len(s):
                ok = not c[i:].strip()          # 雙引號裡的行尾 `\`：程式碼是兩格空白、原文只有一格
                a.append(" " * (len(c) - i))
                break
            if s[j] == "\\" and j == len(s) - 1 and joined(tail) is not None:
                tail = joined(tail)
                s = s[:j] + src_lines[tail]
                continue
            # `<<` 在**第一個** `<` 就命中：here-string `<<<` 因此走到這裡時分隔字詞是空的（第三個 `<` 是詞界），照樣對齊——
            # 這一支必須排在逐字比對之前，否則第二個 `<` 會被當成 heredoc 開頭、吃掉 `<<< "$X"` 的 `"$X"`（`good-here-string`）。
            if c.startswith("<<", i) and s.startswith("<<", j):
                e = _skip_delim_word(s, j + 2)
                while (e is None or e > len(s)) and s.endswith("\\") and joined(tail) is not None:
                    # 分隔字詞本身跨行（`<<AB\` ⏎ `CD`、`<<"AB\` ⏎ `CD"`）：掃描器同樣把 `\` 與換行拿掉、接上下一行
                    tail = joined(tail)
                    s = s[:-1] + src_lines[tail]
                    e = _skip_delim_word(s, j + 2)
                if e is None or e > len(s):
                    ok = False
                    break
                a.append("<<")
                i, j = i + 2, e
                continue
            if c[i] != " " and c[i] != s[j]:
                ok = False
                break
            a.append(s[j])
            i, j = i + 1, j + 1
        out.append("".join(a) if ok else None)
    return out


def _clamp(C, p, e):
    """挖空的構造在程式碼裡全是空白：由原文算出的結尾 e 不可越過任何活的程式碼字元（否則原文剖析與掃描器一有分歧，
    一個真的 `>` 就會被吞進詞裡）。至少前進一格。"""
    q = p
    while q < min(e, len(C)) and C[q] == " ":
        q += 1
    return max(q, p + 1)


def _brace_end(S, k):
    """`${` 之後（k 指向內容開頭）配對的 `}` 之後的位置；只用來跳過挖空段；只有 `_word` 那次呼叫（第 1737 行）的結果會再經 `_clamp`（第 1755 行）——`_dq_parts` 呼叫它時（第 1525 行）沒有 `C` 陣列可用，回傳值直接當新游標，不經過 `_clamp`。"""
    d, n = 1, len(S)
    while k < n and d:
        c = S[k]
        if c == "\\":
            k += 2
            continue
        if c in ("'", '"'):
            e = S.find(c, k + 1)
            k = n if e < 0 else e + 1
            continue
        if S.startswith("${", k):
            d, k = d + 1, k + 2
            continue
        d -= c == "}"
        k += 1
    return k


_PARAM_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])")


def _dq_parts(body):
    """雙引號內容（原文）→（去引號後的字面，含展開就是 None；骨架）。骨架把展開換成 `\\0`，給目標的字面部分判定用。"""
    lit, sk, i, n, literal = [], [], 0, len(body), True
    while i < n:
        c = body[i]
        if c == "\\" and i + 1 < n and body[i + 1] in '$`"\\\n':
            lit.append(body[i + 1])
            sk.append(body[i + 1])
            i += 2
            continue
        if c == "`":
            e = body.find("`", i + 1)
            i, literal = (n if e < 0 else e + 1), False
            sk.append("\0")
            continue
        if body.startswith("${", i):
            i, literal = _brace_end(body, i + 2), False
            sk.append("\0")
            continue
        if body.startswith("$(", i):
            d, i, literal = 1, i + 2, False
            while i < n and d:
                d += (body[i] == "(") - (body[i] == ")")
                i += 1
            sk.append("\0")
            continue
        m = _PARAM_RE.match(body, i)
        if m:
            i, literal = m.end(), False
            sk.append("\0")
            continue
        lit.append(c)
        sk.append(c)
        i += 1
    return ("".join(lit) if literal else None), "".join(sk)


def _sub_tokens(text):
    """原文裡一段命令替換的**內容** → 詞元串：走同一套 `shell_scan` → `_aligned_sources` → `_lex`。掃描器不解析就回 None。"""
    lines = text.split("\n")
    code, _decls, unparsed = shell_scan(lines)
    if unparsed:
        return None
    al = _aligned_sources(code, lines)
    return _lex("\n".join(code), "\n".join(a if a is not None else "\0" * len(c) for c, a in zip(code, al)))[0]


_COVERED = {}      # 這一次 `_analyse` 裡已經剖析過的原文區段：{原文字串: [(起, 迄)…]}（見 `_hidden_subs`）


def _hidden_subs(S, lo, hi, dq):
    """原文 [lo, hi) 是掃描器挖空的一段（雙引號內容，或未引號的 `${…}`）——找出裡面**會執行**的命令替換，
    各自剖析成詞元串（R37：`"$(cmd >&2)"`、`${X:-$(cmd >&2)}` 裡的重導向與 xtrace 同樣會外流，而挖空後規則看不到）。
    對不到收尾或掃描器不解析的回 None（呼叫端 fail-closed）。dq＝外層是雙引號：那裡的單引號是字面、不是引號；
    而且雙引號的結尾**由原文自己找**（hi 只當下限參考）——掃描器對 `"$(… "…" …)"` 的引號配對與 bash 不同
    （掃描器層級的引號配對已由工作包 c 修，#33 verify R36 第 6 列；但這裡 `_hidden_subs` 自行重找雙引號結尾是工作包 b 的獨立防禦，依 report-b 自己的交界說明，不論 c 修好與否都成立），程式碼給的引號位置可能落在命令替換中間。已經剖析過的區段不重做（`_COVERED`）。"""
    if any(a <= lo < b for a, b in _COVERED.get(S, ())):
        return []
    out, k = [], lo
    if dq:
        hi = len(S)
    while k < hi:
        c = S[k]
        if dq and c == '"':
            break                                # 雙引號的真正結尾（命令替換整段跳過，裡面的引號不會停在這裡）
        if c == "\\":
            k += 2
            continue
        if c == "'" and not dq:
            e = S.find("'", k + 1)
            k = hi if e < 0 else e + 1
            continue
        if S.startswith("$((", k):
            k += 3
            continue
        if S.startswith("$(", k) or c == "`":
            e = (_cmdsub_end_case(S, k) if dq else _cmdsub_end(S, k)) if c == "$" else _backtick_end(S, k)   # 雙引號裡認得 case（合併 r37b×r37c）
            if e is None:
                return None
            sub = _sub_tokens(S[k + (2 if c == "$" else 1):e - 1])
            if sub is None:
                return None
            out.append(sub)
            k = e
            continue
        k += 1
    _COVERED.setdefault(S, []).append((lo, k))
    return out


def _interior_subs(S, lo, hi):
    """算術 `((…))`／`$((…))`／`$[…]` 與條件式 `[[…]]` 的內部 [lo, hi)——掃描器把它挖空（那裡的 `|` 是位元 OR／正規式的「或」、
    `<<` 是左移），但裡面的命令替換照樣執行，`$(cmd >&2)` 的重導向與 xtrace 同樣會外流。前一版規則層把這幾種整段當成沒有
    命令替換的不透明詞，fd 流向規則在兩種模式都看不到它們（#33 verify R37 完整性審查，缺陷 c）。
    照 bash 的引號規則走一遍原文：單引號段跳過；雙引號段交給 `_hidden_subs(dq=True)`（引號裡的單引號是字面——
    `_hidden_subs(dq=False)` 只認單引號，`"it's $(…)"` 會被它誤跳過）；引號外的 `$(`／反引號各自剖析；巢狀的 `$((` 只是
    同一段算術的一部分，往下走。對不到收尾回 None（呼叫端設 `bad_sub`、fail-closed）。"""
    out, k = [], lo
    while k < hi:
        c = S[k]
        if c == "\\":
            k += 2
            continue
        if c == "'":
            e = S.find("'", k + 1)
            if e < 0:
                return None
            k = e + 1
            continue
        if c == '"':
            e = _dq_end(S, k)
            if e is None:
                return None
            hs = _hidden_subs(S, k + 1, e - 1, dq=True)
            if hs is None:
                return None
            out.extend(hs)
            k = e
            continue
        if S.startswith("$((", k):
            k += 3
            continue
        if S.startswith("$(", k) or c == "`":
            e = _cmdsub_end(S, k) if c == "$" else _backtick_end(S, k)
            if e is None:
                return None
            sub = _sub_tokens(S[k + (2 if c == "$" else 1):e - 1])
            if sub is None:
                return None
            out.append(sub)
            k = e
            continue
        k += 1
    return out


def _word(C, S, p, stop):
    r"""從 p 讀一個詞 → {k, code, lit, skel, glob, subs, bad_sub, s, e}（k＝"W"，docstring 原本漏列）。lit＝去引號後的字面（含展開、或看不到原文，就是 None）；
    skel＝字面部分＋把展開換成 `\0` 的骨架（看不到原文是 None）；subs＝詞裡的命令替換，各自一串詞元——包括雙引號與
    `${…}` 裡、掃描器挖空的那些（`_hidden_subs`）；bad_sub＝有命令替換對不到收尾（規則層 fail-closed）。"""
    n, st = len(C), p
    lit, skel, subs, literal, known, glob, bad_sub = [], [], [], True, True, False, False
    while p < n:
        c, s = C[p], S[p]
        if s == "\0":
            known = False
        hollow = c == " " and s not in " \t\n\0"
        if (c in _WORD_END and not hollow) or (c == "`" and stop == "`"):
            break
        if c == "`":
            sub, p = _lex(C, S, p + 1, "`")
            subs.append(sub)
            literal = False
            skel.append("\0")
            continue
        if C.startswith("$((", p):
            e = C.find("))", p + 3)
            hs = None if e < 0 else _interior_subs(S, p + 3, e)       # 算術展開裡的命令替換（缺陷 c）
            if hs is None:
                bad_sub = True
            else:
                subs.extend(hs)
            p, literal = (n if e < 0 else e + 2), False
            skel.append("\0")
            continue
        if C.startswith("$(", p):
            sub, p = _lex(C, S, p + 2, ")")
            subs.append(sub)
            literal = False
            skel.append("\0")
            continue
        if c == "$" and C[p + 1:p + 2] == '"':
            # `$"…"`：locale 翻譯字串，沒有訊息目錄時就是雙引號字串（R39，#33 verify R38 第 4 列）——前一版把 `$` 當字面，
            # `set $"-x"` 讀成 `set '$-x'`、`>&$"2"` 讀成 `>&$2`，兩個都看不出來。跳過 `$`，交給下面的雙引號分支。
            p += 1
            continue
        m = _PARAM_RE.match(C, p) if c == "$" else None
        if m:
            p, literal = m.end(), False
            skel.append("\0")
            continue
        if c in ("'", '"'):
            e = C.find(c, p + 1)
            e = n if e < 0 else e
            if c == '"' and C[p + 1:e].strip():
                # **掃描器把這段雙引號切成了 code**（R37 合併 r37b×r37c）：r37c 讓雙引號裡收不掉的命令替換（跨行、
                # 或 `_cmdsub_end_case` 也配不起來的）改當 code 掃（`shell_scan` 的 `dq_ret`），C 裡是真的 code、不是挖空的
                # 內容——這裡若照挖空處理，會在單一實體行的原文上找命令替換的收尾、找不到就 fail-closed，把常見的
                # `X="$(` ⏎ … ⏎ `)"` 整批誤擋（`good-r37c-dq-cmdsub-multiline-case`）。照 code 讀下去：引號字元本身跳過。
                literal = False
                skel.append("\0")
                p += 1
                continue
            body = S[p + 1:e]
            if "\0" in body:
                known = False
            elif c == "'":
                lit.append(body)
                skel.append(body)
            else:
                d, sk = _dq_parts(body)
                skel.append(sk)
                if d is None:
                    literal = False
                    hs = _hidden_subs(S, p + 1, e, dq=True)
                    if hs is None:
                        bad_sub = True
                    else:
                        subs.extend(hs)
                else:
                    lit.append(d)
            p = e + 1
            continue
        if hollow:                              # 掃描器挖空的未引號構造：`\x`、`$'…'`、`${…}`、`$[…]`
            if s == "\\":
                ch = S[p + 1] if p + 1 < n else ""
                lit.append(ch)
                skel.append(ch)
                p += 2
                continue
            e = p + 1
            if S.startswith("$'", p):
                k = p + 2
                while k < n and S[k] != "'":
                    k += 2 if S[k] == "\\" else 1
                dec = _ansic_decode(S[p + 2:k]) if k < n else None
                if dec is not None:
                    lit.append(dec)
                    skel.append(dec)
                    p = _clamp(C, p, k + 1)
                    continue
                e = k + 1
            elif S.startswith("${", p):
                e = _brace_end(S, p + 2)
                hs = _hidden_subs(S, p + 2, min(e, n), dq=False)
                if hs is None:
                    bad_sub = True
                else:
                    subs.extend(hs)
            elif S.startswith("$[", p):
                e, d = p + 2, 1
                while e < n and d:
                    d += (S[e] == "[") - (S[e] == "]")
                    e += 1
                hs = _interior_subs(S, p + 2, e - 1) if not d else None   # 舊式算術裡的命令替換（缺陷 c 的相鄰形狀）
                if hs is None:
                    bad_sub = True
                else:
                    subs.extend(hs)
            literal = False
            skel.append("\0")
            p = _clamp(C, p, e)
            continue
        glob = glob or c in "*?["
        lit.append(s)
        skel.append(s)
        p += 1
    return {"k": "W", "code": C[st:p], "lit": "".join(lit) if literal and known else None,
            "skel": "".join(skel) if known else None, "glob": glob, "subs": subs, "bad_sub": bad_sub, "s": st, "e": p,
            "src": S[st:p]}


def _opaque(C, p, e, subs=(), bad_sub=False):
    return {"k": "W", "code": C[p:e], "lit": None, "skel": None, "glob": False, "subs": list(subs), "bad_sub": bad_sub,
            "s": p, "e": e, "src": None}


def _lex(C, S, p=0, stop=None):
    """程式碼（與對齊的原文）→ 詞元串：`W`（詞）、`R`（重導向：fd 前綴、運算子、目標詞）、`OP`（運算子）、`NL`。
    stop 是 `)`（命令替換、process substitution）或反引號時，讀到配對的收尾就回傳。"""
    toks, n, depth, cased = [], len(C), 0, 0
    while p < n:
        c = C[p]
        if stop == "`" and c == "`":
            return toks, p + 1
        if stop == ")" and c == ")" and not depth and not cased:
            return toks, p + 1
        if c in " \t" and S[p] in " \t\0":       # 真的空白；程式碼是空白而原文不是＝挖空的構造，是詞的開頭（`${X}…`、`\x…`）
            p += 1
            continue
        if c == "\n":
            toks.append({"k": "NL"})
            p += 1
            continue
        if C.startswith("((", p) or C.startswith("[[", p):
            # 算術命令／條件式：**掃描器真的把它當成這個構造時，內容已被挖成空白**——只有那樣才是一個不透明的詞
            # （#33 verify R37 完整性審查，缺陷 e）。前一版一看到 `[[`／`((` 開頭就當成不透明詞：引數位置的
            # `set -o pipefail [[ -n x ]]` 因此被判「set 的參數不是字面」；找不到收尾（`[[x` 是命令名）時把整行剩下的
            # 部分吞成一個詞，碰巧沒事。內容沒被挖空＝掃描器沒把它當成那個構造：照一般的詞讀。
            # 「挖空」包括引號字元本身：掃描器在構造裡遇到引號時，收尾的 `"`／`'` 仍留在 code 裡（見主迴圈的引號分支）。
            e = C.find("))" if c == "(" else "]]", p + 2)
            if e >= 0 and not C[p + 2:e].strip(" \t\n'\""):
                hs = _interior_subs(S, p + 2, e)                    # 但裡面的命令替換照樣執行（缺陷 c）
                toks.append(_opaque(C, p, e + 2, hs or (), bad_sub=hs is None))
                p = e + 2
                continue
        if C.startswith("<(", p) or C.startswith(">(", p):   # process substitution：一個詞，裡面是一串命令
            sub, e = _lex(C, S, p + 2, ")")
            toks.append(_opaque(C, p, e, [sub]))
            p = e
            continue
        op = next((o for o in _OPS if C.startswith(o, p)), None)
        if op is None:
            w = _word(C, S, p, stop)
            if w["e"] == p:                                  # 不前進（不該發生）：吃一格當成看不懂的詞，不讓迴圈卡死
                w = _opaque(C, p, p + 1)
            toks.append(w)
            p = w["e"]
            if stop == ")" and w["lit"] in ("case", "esac"):  # `$(case … a) …;; esac)` 的模式 `)` 不是收尾
                cased += 1 if w["lit"] == "case" else (-1 if cased else 0)
            continue
        p += len(op)
        if op in _REDIR_OPS:
            pre, prev = "", (toks[-1] if toks else None)
            # fd 前綴要是**緊貼運算子的一整個字面詞**（`2>&1`）；`"$X"2>&1` 的 `2` 黏在前一個詞上，bash 讀成 `>&1`
            if (prev is not None and prev["k"] == "W" and prev["e"] == p - len(op) and prev["lit"] is not None
                    and prev["lit"] == prev["code"] and re.fullmatch(r"[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*\}", prev["lit"])):
                pre = toks.pop()["lit"]
            tgt = None
            if op != "<<":                                   # `<<` 的分隔字詞掃描器已經讀掉了
                while p < n and C[p] in " \t" and S[p] in " \t\0":   # 同上：挖空的 `${…}` 是目標的開頭，不是空白
                    p += 1
                if C.startswith("<(", p) or C.startswith(">(", p):
                    sub, e = _lex(C, S, p + 2, ")")
                    tgt = dict(_opaque(C, p, e, [sub]), psub=True)
                    p = e
                elif p < n and (C[p] not in _WORD_END or (C[p] == " " and S[p] not in " \t\n\0")):
                    tgt = _word(C, S, p, stop)
                    p = tgt["e"]
            toks.append({"k": "R", "pre": pre, "op": op, "t": tgt})
            continue
        if op == "(":
            depth += 1
        elif op == ")" and depth:
            depth -= 1
        toks.append({"k": "OP", "op": op})
    return toks, p


def _is_2to1(r):
    return r["op"] == ">&" and r["pre"] == "2" and r["t"] is not None and r["t"]["lit"] == "1"


def _redir_hit(r):
    """這個重導向會不會把輸出帶離管線？會就回一句說明，不會回 None。"""
    op, pre, t = r["op"], r["pre"], r["t"]
    if op in ("<", "<<", "<<<"):
        return None
    # 訊息裡的目標用去引號後的字（程式碼半邊的引號內容是挖空的，印出來只剩空白）
    shown = "%s%s%s" % (pre, op, "" if t is None else t["lit"] if t["lit"] is not None else t["code"])
    if op in (">&", "<&"):
        tl = t["lit"] if t is not None else None
        if tl == "-":
            return None                                  # 關閉 fd：之後的寫入失敗，不會寫到任何地方
        if tl is not None and re.fullmatch(r"[0-9]+-", tl):
            tl = tl[:-1]                                 # `>&2-`：搬移 fd（複製後關掉來源）——對「寫到哪裡」與複製相同
        if tl is not None and tl.isdigit():
            if op == ">&" and tl == "1" and pre in ("", "1", "2"):
                return None                              # `2>&1`：fd 2 跟著 fd 1 走（管線）；`>&1`：no-op
            return "`%s` 複製 fd（stdout 可能被帶到 stderr 或另存的 fd）" % shown
        if op == "<&" or tl is None or t.get("psub"):
            return "`%s` 複製到看不出值的 fd" % shown
        # `>&word`（word 不是數字）＝stdout 與 stderr 一起寫進檔案 word，同 `&>word`——往下判目標
    if t is None or t.get("psub"):
        return None                                      # 缺目標是 bash 語法錯誤；process substitution 繼承當下的 fd 1
    sk = t["skel"]
    if sk is None:
        return "`%s` 的目標看不到原文（本 lint 對不齊這一行）——不解析就不放行" % shown
    if t["glob"]:
        return "`%s` 的目標含萬用字元——bash 會對它做路徑展開" % shown
    if t["lit"] is not None and ".." in t["lit"].split("/") and {"dev", "proc"} & set(t["lit"].split("/")):
        # `..` 經過 /dev 或 /proc（R39，#33 verify R38 第 20 列）：Linux 的 `/dev/fd` 是指向 `/proc/self/fd` 的 symlink，
        # `/dev/fd/../../self/fd/2` 字面 normpath 成 `/self/fd/2`、實際是 stderr。symlink 讓字面的 `..` 不可信 ⇒ fail-closed。
        return "`%s` 的目標含 `..` 又經過 /dev 或 /proc——那底下有 symlink，字面的 `..` 算不出實際寫到哪裡" % shown
    if t["lit"] is not None and (posixpath.normpath(t["lit"]) in _SAFE_TARGETS
                                 or re.match(r"/dev/(tcp|udp)/", posixpath.normpath(t["lit"]))):
        return None                                      # `/dev/tcp/host/port`：bash 的網路 socket，不是 log（野外語料 3 處）
    if {"dev", "proc"} & set(posixpath.normpath(sk).split("/")):
        return "`%s` 寫到 /dev 或 /proc 底下（去引號後是 `%s`）" % (
            shown, t["lit"] if t["lit"] is not None else sk.replace("\0", "$…"))
    return None


# 群組裡**可以**豁免的目標（R39，#33 verify R38 第 5 列）：群組的 fd 1、fd 2 是管線，所以寫到自己的 fd 1／2 是安全的。
# 封閉列舉，只有這些：數字 fd 的複製（`>&2`、`>&3`——群組裡的 fd 都是群組自己開的或繼承自管線）與下面六個路徑。
# `/proc/$$/fd/1`（`$$` 在子殼層裡仍是外層 shell 的 PID——Linux 上就是 step log）、`/proc/<別的>`、`/dev/tty`、`/dev/console`
# 都不在其中：前一版把群組內的所有 fd 命中一起豁免，五條 leg 都指出這一格。
_GROUP_SAFE_PATHS = frozenset(("/dev/stdout", "/dev/stderr", "/dev/fd/1", "/dev/fd/2", "/proc/self/fd/1", "/proc/self/fd/2"))


def _group_safe_target(r):
    t = r["t"]
    tl = t["lit"] if t is not None else None
    if tl is None:
        return False
    if r["op"] in (">&", "<&"):
        return re.fullmatch(r"[0-9]+-?", tl) is not None
    return ".." not in tl.split("/") and posixpath.normpath(tl) in _GROUP_SAFE_PATHS


class _Sh:
    """把 `_lex` 的詞元剖析成管線／群組／簡單命令，收集 fd 流向規則（`_analyse`）要讀的東西。

    不是完整的 bash 剖析器：`if`／`while`／`for` 當成一般的詞（它們不改變 fd 與管線的結構）；有自己結構的只有
    群組 `{ …; }`／`( … )`、`case`（模式裡的 `|` 是「或」、不是管線——R36 第 22 列）、函式定義、命令替換與
    process substitution。收集到 `out`：groups（每個群組是否豁免）、hits（（說明, 所在群組的堆疊））、
    pipelines（（各段, 段與段之間的運算子））。R42 起只有預設模式呼叫它（`--strict` 走 `flat_step_rules`）；R37 起的
    pipefail 模擬（R39 的範圍、R40 的條件／迴圈／trap／lastpipe 事件）與 R40 的 `$GITHUB_ENV` 寫入規則隨之刪除。"""

    def __init__(self, toks, out):
        self.t, self.i, self.o = toks, 0, out

    def tok(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else None

    @staticmethod
    def op(t, *ops):
        return t is not None and t["k"] == "OP" and t["op"] in ops

    @staticmethod
    def word(t, *codes):
        return t is not None and t["k"] == "W" and t["code"] in codes

    def skip_nl(self):
        while self.tok() is not None and self.tok()["k"] == "NL":
            self.i += 1

    def hit(self, why, ctx, group_safe=True):
        """`group_safe`：這個命中在「收尾後緊接 `2>&1 |` 進 neutralise 的群組」裡可以豁免——豁免的論證是群組裡 fd 1、fd 2
        都是管線，所以只涵蓋寫到 fd 1／2 的東西（見 `_group_safe_target`）。"""
        self.o["hits"].append((why, ctx["stack"], group_safe))

    def group(self):
        self.o["groups"].append(False)
        return len(self.o["groups"]) - 1

    def parse_list(self, ctx, end):
        while self.tok() is not None:
            t = self.tok()
            if t["k"] == "NL" or self.op(t, ";", "&"):
                self.i += 1
                continue
            if end(t):
                return
            i0 = self.i
            self.parse_andor(ctx, end)
            if self.i == i0:                     # 語法錯誤的殘渣（孤立的 `)`、`;;`…）：略過一個，不讓迴圈卡死
                self.i += 1

    def parse_andor(self, ctx, end):
        self.parse_pipeline(ctx, end)
        while self.op(self.tok(), "&&", "||"):
            self.i += 1
            self.skip_nl()
            if self.tok() is None or end(self.tok()):
                return
            self.parse_pipeline(ctx, end)

    def parse_pipeline(self, ctx, end):
        segs, conns = [], []
        while self.word(self.tok(), "!", "time"):
            self.i += 1
            while self.word(self.tok(-1), "time") and self.tok() is not None and self.tok().get("lit") in _LEAD_OPTS["time"]:
                self.i += 1                      # `time -p set -x`（R39，R38 第 4 列）
        seg = self.parse_command(ctx, end)
        while seg is not None:
            segs.append(seg)
            if not self.op(self.tok(), "|", "|&"):
                break
            conns.append(self.tok()["op"])
            self.i += 1
            self.skip_nl()
            seg = self.parse_command(ctx, end)
        if segs:
            self.o["pipelines"].append((segs, conns))

    def parse_command(self, ctx, end):
        t = self.tok()
        if t is None or t["k"] == "NL" or end(t):
            return None
        if t["k"] == "OP":
            if t["op"] != "(":
                return None
            gid = self.group()
            self.i += 1
            self.parse_list(dict(ctx, stack=ctx["stack"] + (gid,)), lambda x: self.op(x, ")"))
            if self.op(self.tok(), ")"):
                self.i += 1
            return {"kind": "group", "gid": gid, "trail": self.redirs(ctx), "neut": False}
        if self.word(t, "{"):
            gid = self.group()
            self.i += 1
            self.parse_list(dict(ctx, stack=ctx["stack"] + (gid,)), lambda x: self.word(x, "}"))
            if self.word(self.tok(), "}"):
                self.i += 1
            return {"kind": "group", "gid": gid, "trail": self.redirs(ctx), "neut": False}
        if self.word(t, "case"):
            return self.parse_case(ctx)
        if self.word(t, "function"):             # `function f { …; }`：本體照樣剖析，裡面的 fd 命中照算
            self.i += 1
            if self.tok() is not None and self.tok()["k"] == "W":
                self.i += 1
            if self.op(self.tok(), "(") and self.op(self.tok(1), ")"):
                self.i += 2
            self.skip_nl()
            self.parse_command(ctx, end)
            return {"kind": "func", "trail": [], "neut": False}
        words, rs = [], []
        while self.tok() is not None and self.tok()["k"] in ("W", "R"):
            x = self.tok()
            if x["k"] == "W":
                words.append(x)
                self.subs(x, ctx)
            else:
                rs.append(x)
                self.redir(x, ctx)
            self.i += 1
            if len(words) == 1 and not rs and self.op(self.tok(), "(") and self.op(self.tok(1), ")"):
                self.i += 2                      # `f() …`：本體照樣剖析，裡面的 fd 命中照算
                self.skip_nl()
                self.parse_command(ctx, end)
                return {"kind": "func", "trail": [], "neut": False}
        self.simple(words, ctx)
        neut = (len(words) >= 2 and words[0]["code"] == "python3"
                and re.fullmatch(r"\S*neutralise\.py", words[1]["code"]) is not None)
        return {"kind": "simple", "trail": rs, "neut": neut}

    def parse_case(self, ctx):
        self.i += 1                              # `case`
        if self.tok() is not None and self.tok()["k"] == "W":
            self.subs(self.tok(), ctx)
            self.i += 1                          # 主詞
        self.skip_nl()
        if self.word(self.tok(), "in"):
            self.i += 1
        while self.tok() is not None:
            i0 = self.i
            self.skip_nl()
            if self.tok() is None or self.word(self.tok(), "esac"):
                break
            if self.op(self.tok(), "("):
                self.i += 1
            while self.tok() is not None and self.tok()["k"] != "NL" and not self.op(self.tok(), ")"):
                if self.tok()["k"] == "W":       # 模式：`|` 是「或」、不是管線
                    self.subs(self.tok(), ctx)
                self.i += 1
            if self.op(self.tok(), ")"):
                self.i += 1
            self.parse_list(ctx, lambda x: self.op(x, ";;", ";&", ";;&") or self.word(x, "esac"))
            if self.op(self.tok(), ";;", ";&", ";;&"):
                self.i += 1
            if self.i == i0:
                self.i += 1
        if self.word(self.tok(), "esac"):
            self.i += 1
        return {"kind": "case", "trail": self.redirs(ctx), "neut": False}

    def redirs(self, ctx):
        rs = []
        while self.tok() is not None and self.tok()["k"] == "R":
            rs.append(self.tok())
            self.redir(self.tok(), ctx)
            self.i += 1
        return rs

    def redir(self, r, ctx):
        why = _redir_hit(r)
        if why:
            self.hit(why, ctx, group_safe=_group_safe_target(r))
        if r["t"] is not None:
            self.subs(r["t"], ctx)

    def subs(self, w, ctx):
        if w.get("bad_sub"):
            self.hit("引號或 `${…}` 裡的命令替換對不到收尾（或掃描器不解析它）——裡面的重導向看不到，不解析就不放行", ctx)
        for sub in w["subs"]:                    # 命令替換、process substitution：子殼層，fd 繼承自所在的位置
            _Sh(sub, self.o).parse_list(ctx, lambda x: False)

    def simple(self, words, ctx):
        k = 0
        while k < len(words):                    # 前綴：變數指派（`X=1 cmd`）與不改變命令名的保留字
            w = words[k]
            lead = w["lit"] if w["lit"] in _LEAD_BUILTINS else w["code"]
            if _ASSIGN_RE.match(w["skel"] if w["skel"] is not None else w["code"]):
                self.env_word(w, ctx, bare=False)
            elif lead not in _LEAD_WORDS:
                break
            k += 1
            # 前綴詞自己的選項（R39，#33 verify R38 第 4、8 列）：`command -p set -x`、`builtin -- set +o pipefail`、`time -p …`——
            # 前一版只剝裸詞，選項被當成命令名，後面的 `set` 就看不到了（380e4a4 的 `FD_RE` 擋這幾種，回歸）。
            # `command -v`／`-V` 只印命令的描述、不執行它。
            while k < len(words) and lead in _LEAD_OPTS and words[k]["lit"] in _LEAD_OPTS[lead]:
                if words[k]["lit"] in ("-v", "-V"):
                    return
                k += 1
        if k >= len(words):
            return
        name = words[k]["lit"] if words[k]["lit"] is not None else words[k]["code"]
        args = words[k + 1:]
        if name in ("fi", "done"):
            return                               # 複合命令的收尾詞（R40 起如此；R42 刪掉 `ctl` 時保留，判定不變）
        if words[k]["lit"] is None:
            self.opaque_cmd(args, ctx)
        if name == "eval" and args[:1] and args[0]["lit"] == "--":
            args = args[1:]                      # `eval -- set -x`（R38 第 4 列）
        if name == "eval" and args and all(a["lit"] is not None for a in args):
            # `eval` 後面全是字面詞：bash 執行的就是那幾個詞接起來（`eval set -x`）
            self.simple([dict(_opaque("", 0, 0), code=x, lit=x, skel=x) for x in " ".join(a["lit"] for a in args).split()], ctx)
            return
        if name == "set":
            self.set_cmd(args, ctx)
        elif name == "shopt":
            self.shopt_cmd(args, ctx)
        elif name in ("export", "declare", "typeset", "local", "readonly", "env"):
            for a in args:
                self.env_word(a, ctx, bare=True)
        for j, w in enumerate(words):            # 任何位置的 shell 呼叫（`bash -x …`、`sudo bash -x …`、`env X=1 sh -x …`）
            if w["lit"] is not None and w["lit"].rsplit("/", 1)[-1] in _SHELL_NAMES:
                self.shell_opts(words[j + 1:], ctx)

    def opaque_cmd(self, args, ctx):
        """命令名不是字面（`${X:-set} +o pipefail`、`"$CMD" -x`）：看不出是不是 `set`／`shopt`（R39，#33 verify R38 第 4、8 列）。
        只在參數**像** `set` 的選項時 fail-closed，否則 `$MAKE -j4`、`"$TAR" -xzf a` 這類常見寫法會被一起擋掉：
        字面參數裡有 `-o xtrace|verbose`，或一個只由 `set` 的單字母選項組成、含 `x`／`v` 的 `-…` ⇒ 當成開了 trace。
        封閉列舉，只有這一類，不得依「看起來像選項」類推。（R39 的第二類「字面參數裡有 `pipefail` ⇒ 當成關掉 pipefail」
        餵的是 pipefail 模擬，R42 隨模擬一起刪除；`--strict` 的 pipefail 改由正面文法決定。）"""
        lits = [a["lit"] for a in args]
        # 合寫的 `-euxo pipefail`（R40，#33 verify R39 第 7 列）：`o` 不在單字母表裡，前一版整串不匹配、裡面的 `x` 看不到。
        # 單獨的 `-` 也會 fullmatch，但它沒有字母、不以 `o` 結尾，下面兩個條件都不成立——前一版多寫的 `len(l) > 1` 是多餘的（R40 opsweep）。
        bundles = [l for l in lits if l is not None and re.fullmatch(r"-[%s]*o?" % _SET_LETTERS, l)]
        if (any(set(l[1:]) & set("xv") for l in bundles)
                or (any(l.endswith("o") for l in bundles) and any(l in _TRACE_OPTS for l in lits))):
            self.hit("命令名不是字面、參數像 `set -x`／`set -o xtrace`——看不出是不是開了 trace", ctx)

    def env_word(self, w, ctx, bare):
        text = w["skel"] if w["skel"] is not None else w["code"]
        m = re.match(r"(PYTHON\w*)\+?=", text)
        if m and w["lit"] is None:                # skel 裡有 `\0`（展開）時 lit 必為 None——前一版多寫的 `"\0" in text` 被它蘊含（R39 opsweep）
            # 過濾器 `python3` 啟動時讀 `PYTHON*`（R39，#33 verify R38 第 9 列）：值不是字面就可能是 PR 文字，`PYTHONWARNINGS` 的
            # 不合法值原樣印到管線右端的 stderr。
            self.hit("run 裡把 `%s` 設成不是字面的值——過濾器 python3 啟動時就讀它（`PYTHONWARNINGS` 的不合法值會原樣印到"
                     "管線右端的 stderr）" % m.group(1), ctx)
        for key in _RUN_ENV_KEYS:
            if text.startswith((key + "=", key + "+=")) or (bare and text == key):
                self.hit("run 裡設定 `%s`——bash（含子行程）啟動時會讀它，依鍵不同可能開 xtrace、執行別的程式碼，或把已開啟的 trace 輸出轉向到別的 fd（`BASH_XTRACEFD` 單獨設定不會自己打開 xtrace，需要 `-x`／verbose 已經開著）" % key, ctx)

    def set_cmd(self, args, ctx):
        i = 0
        while i < len(args):
            a = args[i]["lit"]
            if a is None:
                self.hit("`set` 的參數不是字面（`set -$X`…）——開了什麼看不出來", ctx)
                return
            m = re.fullmatch(r"([-+])([A-Za-z]+)", a)
            if not m:
                return                           # `--`、`-`、位置參數：之後都不是選項
            on, i = m.group(1) == "-", i + 1
            for ch in m.group(2):
                if ch == "o":
                    if i >= len(args):
                        return                   # 單獨的 `set -o`：印出選項
                    nm, i = args[i]["lit"], i + 1
                    if nm is None:
                        self.hit("`set %so` 的選項名不是字面——開了什麼看不出來" % m.group(1), ctx)
                    elif on and nm in _TRACE_OPTS:
                        self.hit("`set %s %s` 開了 %s" % (a, nm, nm), ctx)
                elif on and ch in "xv":
                    self.hit("`set %s` 開了 %s" % (a, "xtrace" if ch == "x" else "verbose"), ctx)

    def shopt_cmd(self, args, ctx):
        # 只看會開 trace 的形狀（`shopt -so xtrace|verbose`）與看不出值的參數。這裡原本另外記 pipefail 與 lastpipe 事件、餵 pipefail
        # 模擬（R37–R40）；R42 隨模擬一起刪除（`--strict` 的正面文法裡沒有 `shopt`）。
        flags, i = "", 0
        while i < len(args):
            a = args[i]["lit"]
            if a is None:
                self.hit("`shopt` 的參數不是字面——開了什麼看不出來", ctx)
                return
            if a == "--":
                i += 1
                break
            if not re.fullmatch(r"-[A-Za-z]+", a):
                break
            flags, i = flags + a[1:], i + 1
        if "o" not in flags:
            return
        for nm in [w["lit"] for w in args[i:]]:
            if nm is None:
                self.hit("`shopt -o` 的選項名不是字面——開了什麼看不出來", ctx)
            elif "s" in flags and nm in _TRACE_OPTS:
                self.hit("`shopt -%s %s` 開了 %s" % (flags, nm, nm), ctx)

    def shell_opts(self, args, ctx):
        i = 0
        while i < len(args):
            a = args[i]["lit"]
            if a is None or not a.startswith(("-", "+")) or a in ("-", "--"):
                return
            i += 1
            if a == "--verbose":
                self.hit("子 shell 的 `--verbose` 開了 verbose", ctx)
                continue
            if a.startswith("--"):
                continue
            on = a[0] == "-"
            for ch in a[1:]:
                if ch in "oO":
                    nm = args[i]["lit"] if i < len(args) else None
                    i += 1
                    if ch == "o" and on and (nm is None or nm in _TRACE_OPTS):
                        self.hit("子 shell 的 `%s %s` 開了 trace" % (a, nm or "…"), ctx)
                elif ch == "c":
                    return                       # 之後是命令字串（不剖析，見本節已知不涵蓋第 2 條）
                elif on and ch in "xv":
                    self.hit("子 shell 的 `%s` 開了 %s" % (a, "xtrace" if ch == "x" else "verbose"), ctx)


def _rule_lines(code_lines, src_lines):
    """規則層的邏輯行：（程式碼, 對齊的原文或 None）。接行規則與管線判定用的 `logical` 相同（前一行以 `CONT_RE` 結尾才接），
    但**不 strip、不丟掉整行挖空的行**——跨行字串與跨行 `"$(…)"` 的中間行在程式碼裡全是空白，丟掉就連原文一起丟了
    （R37 自查：野外語料 12 個「命令替換對不到收尾」的誤擋全是這個）。空字串的程式碼行（heredoc 內文、被接走的續行）不收。"""
    rl_code, rl_src = [], []
    for c, a in zip(code_lines, _aligned_sources(code_lines, src_lines)):
        if rl_code and CONT_RE.search(rl_code[-1]):
            rl_code[-1] = rl_code[-1] + " " + c
            rl_src[-1] = None if rl_src[-1] is None or a is None else rl_src[-1] + " " + a
        elif c:
            rl_code.append(c)
            rl_src.append(a)
    return rl_code, rl_src


def _analyse(logical, logical_src):
    """一個 step 的邏輯行（程式碼與對齊的原文）→ {fd: 外流說明}。R42 起只有預設模式呼叫（`--strict` 走 `flat_step_rules`）。"""
    C = "\n".join(logical)
    S = "\n".join(s if s is not None else "\0" * len(c) for c, s in zip(logical, logical_src))
    _COVERED.clear()
    toks, _ = _lex(C, S)
    out = {"groups": [], "hits": [], "pipelines": []}
    _Sh(toks, out).parse_list({"stack": ()}, lambda t: False)
    for segs, conns in out["pipelines"]:
        last = max((k for k, sg in enumerate(segs) if sg["neut"]), default=0)
        for k in range(last):
            # 群組豁免（R36 第 9 列）：收尾後緊接 `2>&1 |`（或 `|&`）進 neutralise——群組裡的 fd 1、fd 2 都是管線
            if segs[k]["kind"] == "group" and (
                    (conns[k] == "|&" and not segs[k]["trail"])
                    or (conns[k] == "|" and len(segs[k]["trail"]) == 1 and _is_2to1(segs[k]["trail"][0]))):
                out["groups"][segs[k]["gid"]] = True
    fd = [why for why, stack, safe in out["hits"] if not (safe and any(out["groups"][g] for g in stack))]
    # neutralise **之後**還接了管線的一段（R39，mutation 全輪的存活者追到）：那一段自己的輸出不經過濾——
    # `… | python3 …neutralise.py | printf '%s\n' "$PR_TITLE"`。`--strict` 的正面文法（群組尾巴）本來就要求 neutralise 是最後一段；
    # 預設模式前一版沒有對應的檢查。R42 起只在預設模式跑（`--strict` 不呼叫 `_analyse`）。**保守**：`| cat`、`| tee log` 這類只轉印 stdin 的段也擋——分不出來：
    # `printenv PR_TITLE`、`sh -c 'echo $PR_TITLE'` 的詞全是字面也照樣外流（`restrict-r39-segment-after-neutralise-cat`）。
    for segs, _conns in out["pipelines"]:
        neut = [k for k, sg in enumerate(segs) if sg["neut"]]
        if neut and neut[-1] < len(segs) - 1:
            fd.append("`python3 …neutralise.py` 之後還接了管線的一段——那一段自己的輸出不經過濾")
            break
    return {"fd": fd}


_BASH_PATHS = ("bash", "/bin/bash", "/usr/bin/bash")
_BASH_LONG = frozenset(("--noprofile", "--norc", "--login", "--noediting"))
_BASH_SHORT = frozenset("abefhlBCEPTu")
_BASH_O = frozenset(("allexport", "braceexpand", "errexit", "errtrace", "functrace", "hashall", "noclobber",
                     "noglob", "nounset", "notify", "physical", "pipefail", "xtrace", "verbose"))


def _bash_template(sh):
    """`shell:` 的值 → {pipefail, trace}；不是本 lint 認得的 bash 樣板就 None（`--strict` fail-closed）。

    **pipefail 只有兩個來源**（#33 verify R36 第 4 列）：值恰好是關鍵字 `bash`（GitHub 對它用
    `bash --noprofile --norc -eo pipefail {0}`），或樣板自己的選項開了 `-o pipefail`（`-eo pipefail`、`-euo pipefail` 這類捆綁也算、
    之後的 `+o pipefail` 會關掉它）。其餘樣板照字面跑——GitHub 文件：「You can take full control over shell parameters by
    providing a template string」。前一版把「是 bash」當成「有 pipefail」，`bash -e {0}`、`bash -l {0}`、conda 的 `bash -el {0}`
    都漏網，而 `good-strict-bash-templates` 還把 `bash -l {0}` 釘成 pass。`/bin/bash`、`/usr/bin/bash` 是 bash，但不是關鍵字。
    選項採**白名單**：xtrace／verbose（`-x`、`-v`、`-o xtrace`、`--verbose`，含捆綁）算 trace；白名單外的選項（`-i`、`-s`、`-c`、
    `-O extglob`、`-o posix`、`+o interactive-comments`、`--rcfile`…）會改變詞法或讀進別的程式碼，一律不認。"""
    if sh == "bash":
        return {"pipefail": True, "trace": False}
    toks = sh.split()
    if not toks or toks[0] not in _BASH_PATHS:
        return None
    rest = toks[1:-1] if len(toks) > 1 and toks[-1] == "{0}" else toks[1:]
    pf = trace = False
    i = 0
    while i < len(rest):
        t = rest[i]
        i += 1
        if t == "--verbose":
            trace = True
            continue
        if t in _BASH_LONG:
            continue
        m = re.fullmatch(r"([-+])([A-Za-z]+)", t)
        if not m:
            return None
        on = m.group(1) == "-"
        for ch in m.group(2):
            if ch == "o":
                if i >= len(rest) or rest[i] not in _BASH_O:
                    return None
                nm = rest[i]
                i += 1
                if nm == "pipefail":
                    pf = on
                elif nm in _TRACE_OPTS:
                    trace = trace or on
            elif ch in "xv":
                trace = trace or on
            elif ch not in _BASH_SHORT:
                return None
    return {"pipefail": pf, "trace": trace}


# **群組形式**（#59／#60；R37 自 PR #61 移植成「群組規則」，R42 由正面文法的 `run_F` 產生式接手）：靠管線過濾的 step，整個 run 區塊必須是
#     [若干行 `set` 前綴]
#     { …整個區塊… ; } 2>&1 | python3 <路徑>/neutralise.py        （或 `} |& python3 …`）
# R36 的 `--strict` 只要求「緊鄰 `python3 …neutralise.py` 的那一段把 stderr 併進管線」，關不掉兩類：
#   · #59（已知類別 G）：同一個區塊裡**另一條命令**印的 PR 文字不經任何管線；
#   · #60 第 2 類：bash 先展開詞、再由左到右套用重導向——`echo "${!PR_TITLE}" 2>&1 | …` 的展開期錯誤、
#     `echo x > "$PR_TITLE" 2>&1 | …` 的重導向錯誤，都在那一段的 `2>&1` 生效**之前**寫到當下的 stderr。
# 群組的重導向在群組內任何展開之前生效，而整個區塊都在群組裡——兩類一起關掉，不需要 taint、不列拼法清單。
# R37–R41 的群組規則用 `shell_scan` 的挖空結果數大括號（「恰好一個 `{`、一個 `}`」，因為 `case` 模式、陣列字面裡的大括號不是保留字，
# 計深度會與 bash 分岔）。R42 的正面文法用自己的斷詞器：群組裡根本不收 `case`、陣列、`(`、mktemp 以外的 `$(`，`{`／`}` 當命令名
# 是保留字、不在 FL_INERT，所以巢狀群組、兩個群組、群組後面的行都在文法外；當參數的 `echo { }` 是字面、收下（R41 第 10 列）。
# 群組前的行只收 `set` 前綴（`_set_prefix_line`）：`-e`／`-u`／`-E`／`-o pipefail|errexit|nounset|errtrace`（`-E`／errtrace：R39，只影響
# ERR trap 的繼承）。`set -v` 會把原始碼（含 runner 代入的 `${{ … }}`）印到群組外的 stderr，`-x` 同理；裸 `set` 把所有變數（含 PR 可控的
# env）印到群組外的 stdout。
# **代價**：R39–R41 在這裡維護一份「保守誤擋的類別」清單（七類 → 九類），每一輪都被找到清單外的一類（R41 第 10 列）。R42 起改成性質：
# 靠管線過濾的 step，文法的補集一律 RULE；fixture 裡每一個這樣被擋的 step 都在檔頭簽 `KNOWN-CLASS: 文法外`，神諭照它計數
# （oracle.py 的已知類別）。常見寫法的代價清單在 #60。
SET_OPT_NAMES = frozenset(("pipefail", "errexit", "nounset", "errtrace"))   # errtrace：R39，R38 第 11 列（`-E` 不印任何東西）


def _set_prefix_line(toks):
    """`set` 前綴行：只收 `-e`／`-u`／`-E`（可合寫）與 `-o NAME`（可與 `-euE` 合寫成 `-euo NAME`），NAME 限 SET_OPT_NAMES。"""
    if toks[-1:] == [";"]:
        toks = toks[:-1]                         # 行尾的 `;` 只是結束那條命令（R39，R38 第 11 列）
    if toks[:1] != ["set"] or len(toks) < 2:
        return False
    k = 1
    while k < len(toks):
        m = re.fullmatch(r"-(?=.)([euE]*)(o?)", toks[k])      # `(?=.)`：單獨一個 `-` 不是選項
        if not m:
            return False
        if m.group(2):
            if len(toks) <= k + 1 or toks[k + 1] not in SET_OPT_NAMES:
                return False
            k += 1
        k += 1
    return True


def runner_exprs(s):
    """`s` 裡每一個 runner 運算式 `${{ … }}` 的 (起點, 終點, 內容)。邊界照運算式語言本身找：單引號字串（`''` 是跳脫的單引號）
    裡的 `}}` 不收尾（前一版用正規式在第一個 `}}`／`}` 收尾，`format('{0}', …)` 因此切錯位置，#33 verify R39 第 1 列）。
    沒收尾的 `${{` 延伸到字串結尾，內容照常判：多半不是字面、被擋，但 `${{ 123` 的內容是數字字面（#33 verify R41 第 17 列——前一版
    這裡寫「一律當成非字面」）。這一格不必擋：runner 拒絕沒收尾的運算式，整個 workflow 不會執行。"""
    out, i = [], 0
    while True:
        a = s.find("${{", i)
        if a < 0:
            return out
        j, q = a + 3, False
        while j < len(s):
            if s[j] == "'":
                # 連續兩個單引號當成一個單位跳過：字串裡是跳脫的單引號，字串外是空字串 `''`——一連串 k 個單引號走完之後，
                # 「在不在字串裡」只由 k 的奇偶決定，與從哪一個開始配對無關（R40 opsweep：前一版只在字串裡配對，多寫的 `q` 是多餘的）。
                if s[j + 1:j + 2] == "'":
                    j += 2
                    continue
                q = not q
            elif not q and s.startswith("}}", j):
                break
            j += 1
        end = min(j + 2, len(s))
        out.append((a, end, s[a + 3:j]))
        i = end


# 純字面常數（引號字串、數字、true／false／null）：不帶任何 context，值是作者寫死的。它與下面的 GH_SAFE_EXPRS 是不受 R40 運算式規則管的**全部**；
# 其餘每一個運算式——`github.*`、`env.*`、`steps.*`、`inputs.*`、`matrix.*`、函式呼叫、索引——都當成可能帶 PR 文字。
GH_LITERAL_RE = re.compile(r"\s*(?:'(?:[^']|'')*'|-?\d+(?:\.\d+)?|true|false|null)\s*")


# GitHub 產生、PR 作者控制不了的純量欄位（R40，#33 verify R39 第 12 列）。**封閉列舉，只有這八個**，點號寫法、大小寫不分（Actions 的
# context 名稱不分大小寫）；索引寫法、函式呼叫、同一物件的其他欄位（`head.ref`、`title`…）不在裡面、照擋。神諭（oracle.py）另有一份，
# 載入時與這一份比對、不同步就具名退出（R42，#33 verify R41 第 17 列：前一版這裡寫「共用同一份」，實際是兩份、沒有同步檢查）。
GH_SAFE_EXPRS = frozenset((
    "github.event.pull_request.number", "github.event.number",
    "github.event.pull_request.base.sha", "github.event.pull_request.head.sha",
    "github.sha", "github.run_id", "github.run_number", "github.run_attempt",
))


def gh_literal(inner):
    """不受運算式規則管的運算式：純字面常數，或 GH_SAFE_EXPRS 裡的欄位。"""
    return GH_LITERAL_RE.fullmatch(inner) is not None or inner.strip().lower() in GH_SAFE_EXPRS


def _logical_lines(code_lines):
    """程式碼半邊 → 邏輯行：只有前一行以 `CONT_RE` 結尾（`|`、`||`、`|&`、`&&`）才接下一行；空白行丟掉。"""
    logical = []
    for c in code_lines:
        cs = c.strip()
        if logical and CONT_RE.search(logical[-1]):
            logical[-1] = logical[-1] + " " + cs
        elif cs:
            logical.append(cs)
    return logical


# ── `--strict` 的正面文法（#33 verify R41 → R42）──────────────────────────────────────────────────────────────────
# R40 的 pipefail 控制流程模擬與 `$GITHUB_ENV` 形狀清單都是否定清單：R41 在那六個函式上找到約 30 個作者沒點名的相鄰放行輸入。
# R42 反過來：`--strict` 對靠管線過濾的 step 只收下面點名的形狀，其餘一律 RULE（保守誤擋）；宣告了 `# LOG-FILTER:` 的 step，
# 只要 run 文字裡有寫出來的管線或提到 `$GITHUB_ENV`／`$GITHUB_PATH`（`flat_trigger`），也要落在同一套產生式裡。
# 斷詞器是自己的：逐字元吃掉 run 文字，每個字元都必須屬於點名的詞元之一，吃不掉就拒絕。**不讀** `shell_scan` 的挖空結果
# （R41 第 15 列的缺陷在挖空層）；`shell_scan` 仍先跑、仍 fail-closed（PARSE）。
#
#   run_F   ::= PREFIX* '{' LIST '}' TAIL          靠管線過濾的 step（`flat_filtered`）
#   run_D   ::= PREFIX* LIST                       宣告不過濾、觸發了的 step（`flat_declared`）；沒有 `{`／`}` 命令
#   PREFIX  ::= 'set' 選項，單獨一行；選項照 `_set_prefix_line` 的白名單，每個詞都是未加引號的字面
#   TAIL    ::= ( '2>&1' '|' | '|&' ) 'python3' <字面路徑>/neutralise.py [';']；換行只准在 `|`／`|&` 之後，之後只准註解與空行
#   LIST    ::= 命令，以 `;`、換行、`&&`、`||`、`|`、`|&` 相接（`&&`／`||`／`|`／`|&` 之後可換行）
#   命令    ::= NAME=WORD | NAME=$(mktemp 字面…) | trap 動作 EXIT|0 | echo／printf 字面… >> "$GITHUB_ENV" | 簡單命令
#   簡單命令 ::= 未加引號的字面命令名（bash 的 builtin／保留字只收 FL_INERT）後接 WORD 與重導向
#   WORD    ::= 未加引號字面（FL_PLAIN_RE）、單引號、雙引號（`$` 只准 FL_VAR_RE）、FL_VAR_RE 的參數，接成一個詞
#   重導向  ::= '2>&1' | '>&2' | ( '>' | '>>' | '<' | '2>' | '2>>' ) 目標；run_F 的目標只收 `/dev/null`、`/dev/stdout`、
#               `/dev/stderr`、不含 `..` 的相對路徑、`"$RUNNER_TEMP/…"`
# 其餘一律拒絕：未加引號的 `\`、反引號、`(`、`)`、單獨的 `&`、`!`、非 ASCII 字元、任何控制字元（引號裡也一樣）、`;;`、heredoc、
# here-string、process substitution、`>&N`／`<&N`、`&>`、`>|`、`<>`、mktemp 以外的 `$(`、`$((`、`${` 的其他寫法。
# 允許清單漏掉一種相鄰寫法只會多一個誤擋，不會多一個繞過。文法接受的輸入裡，繞過會藏在兩處：斷詞與 bash 不一致，以及產生式
# 本身的語意（R42 移植時就在後者修掉兩個：trap 動作的 mktemp 登記、`printf -v` 經 GITHUB_ENV 產生式指派信任變數——見
# `_fl_command`）。
#
# **`--strict` 宣稱的性質（只有這三條）**：
#   P1（靠管線過濾的 step）：run 文字是 run_F 的字串。所以每個命令都在那一個 fd 1、fd 2 都進 neutralise.py 的群組裡跑；
#      在 step 的 shell 裡執行的只有 FL_INERT 的八個 builtin、`NAME=值` 指派、`trap <動作> EXIT`（動作本身也在文法裡）；
#      shell 自己開的重導向只落在點名的目標；run 文字提到 `$GITHUB_ENV`／`$GITHUB_PATH` 只有字面寫入與唯讀兩種形狀。
#   P2（有寫出來的管線的 step）：run 文字裡寫出來的每一條管線都跑在 pipefail 之下。「寫出來的管線」＝文字裡有一個不屬於 `||`
#      的 `|`（`||` 前一個字元不是 `\`）。宣告了 `# LOG-FILTER:` 的 step 也適用（`flat_trigger`）。
#   P3（靠管線過濾的 step）：run 文字裡的 `${{ … }}` 只有字面常數與 GH_SAFE_EXPRS 的八個欄位；字面常數在剖析**之前**代換，
#      與 runner 同序。宣告的 step 不在此列（#33 的 R42 決策 (f)，#81）。
# **已知不涵蓋（照性質寫，不是拼法清單；#33 verify R41 → R42）**：
#   L1 step 呼叫的程式：腳本、直譯器與它們的 `-c`／`-e` 字串（`bash -c "…$X…"`、`python3 -c '…os.environ["GITHUB_"+"ENV"]…'`），
#      以及這些程式按名字打開的檔案——命令參數給的路徑不是 shell 的重導向，`tee /proc/$PPID/fd/1`、`dd of=/dev/tty`、
#      `tee "$RUNNER_TEMP"/_runner_file_commands/*` 都照收。本 lint 檢查的是 run 文字與 shell 自己開的重導向；PR 的程式碼在
#      每個 job 裡本來就有同樣的能力。
#   L2 step 之前就在的狀態：前一個 step 寫進 `$GITHUB_ENV`／`$GITHUB_PATH` 的值、export 的函式、文法信任的 runner 變數
#      （FL_TRUSTED_VARS）。lint 假設它們是 runner 給的值；文法禁止 run 文字與任何一層 `env:` 覆寫它們。
#   L3 沒有寫出來的管線、宣告了 `# LOG-FILTER:` 的 step：不進文法。執行時才組出來的管線（`eval "$X"`、`source`、alias）看不到；
#      宣告的 step 裡 `$GITHUB_ENV` 的檢查只看**字面的名字**，是抓無心之失的，不是封閉（`n=GITHUB_; … "${!n}"` 看不到）。
#   L4 工作目錄：相對路徑的重導向目標照字面判，不對 `working-directory:` 求值，也不追 PR 提交的 symlink。
#   L5 YAML：本 lint 的白名單解析器與 PyYAML 對帳，兩者都不是 GitHub 的解析器（差異的實測見 oracle.py 檔頭的「盲區」段）。
#   L6 pipefail 以外的退出碼：`|| true`、群組裡的 `exit 0` 是維護者明寫的選擇，不在宣稱內。（trap 動作裡的 `exit` 不收：
#      EXIT trap 的 `exit N` 會蓋掉整個 step 的退出碼。）
# 另外 FL_STARTUP_KEYS 仍是否定清單（bash 啟動時讀的 env 鍵；權威是 bash 的 INVOCATION 一節，神諭的 pipefail 探針在執行時看它的效果）。
FL_GRAMMAR_TAG = "不在 `--strict` 的正面文法裡"     # 每一則文法 RULE 都帶這句；restrict fixture 的 EXPECT-MSG 以它斷言擋下的原因
# bash 5.3 的 `compgen -b` 與 `compgen -k`：這兩份是 bash 自己的輸出，不是拼法清單。命令名落在裡面而不在 FL_INERT 就拒絕。
FL_BUILTINS = frozenset(". : [ alias bg bind break builtin caller cd command compgen complete compopt continue declare dirs "
                        "disown echo enable eval exec exit export false fc fg getopts hash help history jobs kill let local "
                        "logout mapfile popd printf pushd pwd read readarray readonly return set shift shopt source suspend "
                        "test times trap true type typeset ulimit umask unalias unset wait".split())
FL_KEYWORDS = frozenset("if then else elif fi case esac for select while until do done in function time { } ! [[ ]] coproc".split())
FL_INERT = frozenset(("echo", "printf", "test", "[", "true", "false", ":", "exit"))
FL_PLAIN_RE = re.compile(r"[A-Za-z0-9_./:=,+%@~^*?\[\]{}-]+")
FL_NAME_RE = re.compile(r"[A-Za-z0-9_./+][A-Za-z0-9_./+-]*|\[|:")          # 命令名：純字面、無 glob／大括號／引號
FL_VAR_RE = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)(?::-([A-Za-z0-9_./:@%+,=-]*))?\}|(\?))")
FL_ASSIGN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=")
FL_MKTEMP_RE = re.compile(r"\$\(mktemp((?:[ \t]+[A-Za-z0-9_./:%+-]+)*)[ \t]*\)")
FL_REDIR_AT_RE = re.compile(r"[0-9]*[<>]")
FL_REDIR_BAD_RE = re.compile(r"[0-9]*(?:<<|<\(|>\(|[<>]&(?!2|1)|[<>]&1(?<=2>&1)?(?![ \t\n;|&]|$)|&>|>\||<>)")
FL_REDIR_DUP_OK_RE = re.compile(r"2>&1(?=[ \t\n;|&]|$)|>&2(?=[ \t\n;|&]|$)")
FL_REDIR_RE = re.compile(r"2>&1|>&2|2>>|2>|>>|>|<")
FL_SIGNALS = frozenset(("EXIT", "0"))
# **文法信任其值的變數**（R42）：不另寫一份清單，由用到它們的產生式各自的集合聯集而成。run 裡不得指派它們；靠管線過濾的 step 與
# 觸發了的宣告 step，workflow／job／step 的 `env:` 也不得設定（`flat_step_rules`）。產生式的正規式裡寫出的變數名必須在該產生式
# 自己的集合裡（`_fl_trusted_var_problems`）。
FL_TARGET_VARS = frozenset(("RUNNER_TEMP",))                              # 重導向目標 `"$RUNNER_TEMP/…"`（FL_TEMP_TARGET_RE）
FL_GHVALUE_VARS = frozenset(("HOME", "RUNNER_TEMP", "GITHUB_WORKSPACE"))  # 寫進 `$GITHUB_ENV`／`$GITHUB_PATH` 的值裡准展開的變數
FL_MKTEMP_VARS = frozenset(("TMPDIR",))                                   # `NAME=$(mktemp …)`：mktemp 在這個目錄下建檔
FL_CHANNEL_VARS = frozenset(("GITHUB_ENV", "GITHUB_PATH"))                # 跨 step 通道本身（FL_GH_RE、FL_GH_TARGET_RE）
FL_TRUSTED_VARS = FL_TARGET_VARS | FL_GHVALUE_VARS | FL_MKTEMP_VARS | FL_CHANNEL_VARS
FL_GH_RE = re.compile(r"GITHUB_ENV|GITHUB_PATH")
FL_GH_TARGET_RE = re.compile(r'"?\$(?:\{GITHUB_ENV\}|\{GITHUB_PATH\}|GITHUB_ENV|GITHUB_PATH)"?')
FL_TEMP_TARGET_RE = re.compile(r'"(?:\$RUNNER_TEMP|\$\{RUNNER_TEMP(?::-/tmp)?\})/([A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*)"')
FL_REL_TARGET_RE = re.compile(r"[A-Za-z0-9_+-][A-Za-z0-9_.+-]*(?:/[A-Za-z0-9_.+-]+)*")
# bash 啟動時讀、可以在 run 之前關掉 pipefail 的 env 鍵（R3 的清單去掉只影響 xtrace 輸出位置的 BASH_XTRACEFD）。這一份仍是否定清單，
# 權威是 bash 的 INVOCATION 一節；神諭的 pipefail 探針在執行時觀察它的效果。
FL_STARTUP_KEYS = tuple(k for k in ENV_TRACE_KEYS if k != "BASH_XTRACEFD")
# R41 第 19 列：管線接到了 neutralise.py、只是過濾器前多了直譯器選項（`python3 -u`）或路徑不是字面——R1 原本的訊息說「沒有經
# neutralise.py」，誤導。只換訊息，判定不變。
FL_NEUT_NEAR_RE = re.compile(r"\|&?\s*python3\b[^|;&]*neutralise\.py")
_FL_NAME_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{3,}")


def _fl_trusted_var_problems():
    """R42 的斷言：產生式正規式裡寫出來的每一個變數名，都在該產生式自己的集合裡；每個集合都在 FL_TRUSTED_VARS 裡。
    模組載入時就檢查、不成立就不跑（selftest 對每張 fixture 各執行一次本 lint，所以這也是 selftest 的一條斷言）。"""
    probs = []
    for label, rx, own in (("FL_TEMP_TARGET_RE", FL_TEMP_TARGET_RE, FL_TARGET_VARS),
                           ("FL_GH_TARGET_RE", FL_GH_TARGET_RE, FL_CHANNEL_VARS), ("FL_GH_RE", FL_GH_RE, FL_CHANNEL_VARS)):
        probs += ["%s 寫了 `%s`，它不在該產生式的集合裡" % (label, nm) for nm in _FL_NAME_TOKEN_RE.findall(rx.pattern) if nm not in own]
    for label, own in (("FL_TARGET_VARS", FL_TARGET_VARS), ("FL_GHVALUE_VARS", FL_GHVALUE_VARS),
                       ("FL_MKTEMP_VARS", FL_MKTEMP_VARS), ("FL_CHANNEL_VARS", FL_CHANNEL_VARS)):
        probs += ["%s 的 `%s` 不在 FL_TRUSTED_VARS 裡" % (label, nm) for nm in sorted(own - FL_TRUSTED_VARS)]
    return probs


if _fl_trusted_var_problems():
    sys.exit("lint-ci-log-filter: 文法信任的變數與產生式對不上——" + "；".join(_fl_trusted_var_problems()))


def _fl_compgen_problems():
    """R42：PATH 上那支 bash 自己列出的 builtin 與保留字（`compgen -b`、`compgen -k`）必須都在 FL_BUILTINS ∪ FL_KEYWORDS 裡。
    文法靠這兩份集合認出「命令名是 bash 的 builtin／保留字」，不在 FL_INERT 就拒絕；bash 新增一個 builtin（例如會改選項的）而集合
    沒跟上，那個名字就會被當成外部命令收下。只查這個方向：集合多列一個 bash 沒有的名字，只會多一個誤擋。
    `--selftest` 經 `--check-compgen` 跑這一項，用的是 PATH 上的 `bash`——CI 上就是 GitHub 的 `shell: bash` 會用的那一支。
    回傳 (bash 版本, bash 列出的名字, 問題清單)。"""
    import subprocess
    try:
        r = subprocess.run(["bash", "-c", 'printf "%s\\n" "$BASH_VERSION"; compgen -b; compgen -k'],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return "?", [], ["跑不起來 PATH 上的 bash：%s" % e]
    out = r.stdout.split("\n")
    ver, names = out[0] or "?", [n for n in out[1:] if n]
    if r.returncode != 0:
        return ver, names, ["`compgen -b; compgen -k` 的 rc=%d：%s" % (r.returncode, r.stderr.strip()[:200])]
    if not names:
        return ver, names, ["`compgen -b`／`compgen -k` 什麼都沒印——比對會空轉"]
    return ver, names, ["bash %s 列出的 `%s` 不在 FL_BUILTINS ∪ FL_KEYWORDS 裡" % (ver, n)
                        for n in sorted(set(names) - FL_BUILTINS - FL_KEYWORDS)]


if "--check-compgen" in sys.argv:
    _cg_ver, _cg_names, _cg_probs = _fl_compgen_problems()
    if _cg_probs:
        sys.exit("lint-ci-log-filter: 文法的 builtin／保留字集合沒跟上 bash——" + "；".join(_cg_probs)
                 + "（在 FL_BUILTINS／FL_KEYWORDS 補上；要收它就另外判斷它會不會改選項或 pipefail）")
    print("compgen：bash %s 列出的 %d 個 builtin／保留字都在 FL_BUILTINS ∪ FL_KEYWORDS 裡" % (_cg_ver, len(set(_cg_names))))
    sys.exit(0)


class FlatReject(Exception):
    pass


def _fl_word(s, i):
    """一個詞：由 P（未加引號字面）、S（單引號）、D（雙引號）、V（參數）、M（`$(mktemp …)`）片段接成。回傳 (詞, 結尾)。"""
    pieces, st = [], i
    while i < len(s):
        c = s[i]
        if c in " \t\n;&|<>()":
            break
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise FlatReject("單引號沒收尾")
            pieces.append(("S", s[i + 1:j]))
            i = j + 1
        elif c == '"':
            parts, j = [], i + 1
            while True:
                if j >= len(s):
                    raise FlatReject("雙引號沒收尾")
                d = s[j]
                if d == '"':
                    break
                if d == "\\":
                    parts.append(("T", s[j:j + 2]))
                    j += 2
                    continue
                if d == "`":
                    raise FlatReject("雙引號裡的反引號（命令替換）")
                if d == "$":
                    m = FL_VAR_RE.match(s, j)
                    if not m:
                        raise FlatReject("雙引號裡的 `%s`——文法只收 `$NAME`、`${NAME}`、`${NAME:-字面}`、`$?`" % s[j:j + 3])
                    parts.append(("V", m.group(1) or m.group(2) or "?", m.group(3)))
                    j = m.end()
                    continue
                parts.append(("T", d))
                j += 1
            pieces.append(("D", parts))
            i = j + 1
        elif c == "$":
            m = FL_MKTEMP_RE.match(s, i)
            if m and len(pieces) == 1 and pieces[0][0] == "P" and FL_ASSIGN_RE.fullmatch(pieces[0][1]):
                pieces.append(("M", m.group(1).split()))
                i = m.end()
                continue
            m = FL_VAR_RE.match(s, i)
            if not m:
                raise FlatReject("`%s`——文法只收 `$NAME`、`${NAME}`、`${NAME:-字面}`、`$?`、`NAME=$(mktemp …)`" % s[i:i + 3])
            pieces.append(("V", m.group(1) or m.group(2) or "?", m.group(3)))
            i = m.end()
        else:
            m = FL_PLAIN_RE.match(s, i)
            if not m:
                raise FlatReject("字元 %r 不在文法裡（反斜線、反引號、`!`、非 ASCII 字元…）" % c)
            pieces.append(("P", m.group(0)))
            i = m.end()
    if not pieces:
        raise FlatReject("`%s` 不在文法裡" % s[i:i + 2])
    return {"pieces": pieces, "raw": s[st:i], "s": st}, i


def _fl_plain(w):
    """整個詞只有一段未加引號的字面時回傳它，否則 None。"""
    return w["pieces"][0][1] if len(w["pieces"]) == 1 and w["pieces"][0][0] == "P" else None


def fl_tokens(s):
    """run 文字 → 詞元串列：('NL',)、('OP', op)、('R', op, 目標詞或 None)、('W', 詞)。註解只收 `#` 在詞首（bash 同）。"""
    m = re.search(r"[\x00-\x08\x0b-\x1f\x7f]", s)
    if m:
        raise FlatReject("控制字元 %r（引號裡也不收）" % m.group(0))
    toks, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1
            continue
        if c == "\n":
            toks.append(("NL",))
            i += 1
            continue
        if c == "#":
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        for op in ("&&", "||", "|&", "|", ";"):
            if s.startswith(op, i):
                # `;;` 以 `;` 開頭，而 `&&`／`||`／`|&`／`|` 都不以 `;` 起頭，所以走到這裡 op 必為 `;`——不必再比 op（opsweep 存活的多餘運算元，
                # R42：拿掉；`;;` 的訊息由 restrict-r42-flat-case-terminator-msg 釘住）。
                if s.startswith(";;", i):
                    raise FlatReject("`;;`（case）不在文法裡")
                toks.append(("OP", op))
                i += len(op)
                break
        else:
            m = FL_REDIR_AT_RE.match(s, i)
            if m and FL_REDIR_BAD_RE.match(s, i) and not FL_REDIR_DUP_OK_RE.match(s, i):
                raise FlatReject("`%s` 不在文法裡（heredoc／here-string、process substitution、`>&N`／`<&N`、`&>`、`>|`、`<>`）"
                                 % s[i:i + 4].split()[0])
            if m:
                r = FL_REDIR_RE.match(s, i)
                if not r or (r.group(0) in ("2>&1", ">&2") and i + len(r.group(0)) < n
                             and s[i + len(r.group(0))] not in " \t\n;|&"):
                    raise FlatReject("重導向 `%s` 不在文法裡（只收 `2>&1`、`>&2`、`>`、`>>`、`<`、`2>`、`2>>`）" % s[i:i + 4].split()[0])
                op = r.group(0)
                i = r.end()
                if op in ("2>&1", ">&2"):
                    toks.append(("R", op, None))
                    continue
                while i < n and s[i] in " \t":
                    i += 1
                if i >= n or s[i] in "\n;&|<>()#":
                    raise FlatReject("重導向 `%s` 沒有目標" % op)
                w, i = _fl_word(s, i)
                toks.append(("R", op, w))
                continue
            if c in "()&`\\!":
                raise FlatReject({"(": "`(`（子殼層、函式、陣列）", ")": "`)`", "&": "`&`（背景執行、`&>`）", "`": "反引號",
                                  "\\": "未加引號的反斜線（逃脫、續行）", "!": "`!`"}[c] + " 不在文法裡")
            w, i = _fl_word(s, i)
            toks.append(("W", w))
    return toks


def _fl_lines(toks):
    """詞元 → 命令：[(前一個分隔符, [W/R 詞元…])…]。分隔符是 'NL' 或 OP（`&&`／`||`／`|`／`|&`／`;`）。
    `&&`／`||`／`|`／`|&` 之後的換行是續行（bash 同）；運算子前面一定要有命令。"""
    cmds, cur, sep, i = [], [], "NL", 0
    while i < len(toks):
        t = toks[i]
        if t[0] == "NL":
            if cur:
                cmds.append((sep, cur))
                cur = []
            sep = "NL"
            i += 1
            continue
        if t[0] == "OP":
            if not cur:
                raise FlatReject("運算子 `%s` 前面沒有命令" % t[1])
            cmds.append((sep, cur))
            cur, sep = [], t[1]
            i += 1
            if t[1] in ("&&", "||", "|", "|&"):
                while i < len(toks) and toks[i][0] == "NL":
                    i += 1
                if i >= len(toks):
                    raise FlatReject("運算子 `%s` 後面沒有命令" % t[1])
            continue
        cur.append(t)
        i += 1
    if cur:
        cmds.append((sep, cur))
    return cmds


def _fl_lit(w, allow_vars=()):
    """GITHUB_ENV 寫入的值：未加引號字面（不含 glob、大括號、`~`）、單引號、雙引號（只准 `allow_vars` 裡的變數）。"""
    for p in w["pieces"]:
        if p[0] == "P" and re.search(r"[*?\[\]{}~]", p[1]):
            return False
        if p[0] in ("V", "M"):
            return False
        if p[0] == "D" and any(q[0] == "V" and (q[1] not in allow_vars or q[2] is not None) for q in p[1]):
            return False
    return True


def _fl_target_ok(w):
    raw = w["raw"]
    if raw in ("/dev/null", "/dev/stdout", "/dev/stderr"):
        return True
    m = FL_TEMP_TARGET_RE.fullmatch(raw)
    if m:
        return ".." not in m.group(1).split("/")
    return FL_REL_TARGET_RE.fullmatch(raw) is not None and ".." not in raw.split("/")


def _fl_command(words, redirs, ctx, pos=("NL", "NL")):
    """一個命令：指派、trap … EXIT、GITHUB_ENV 的字面寫入、或簡單命令。`ctx`：mktemp（到這一行為止由 mktemp 指派、之後沒再改過的
    變數）、filtered（是不是靠管線過濾的群組）、trap（是不是在 trap 動作裡）。`pos`：(前一個分隔符, 後一個分隔符)。"""
    w0 = words[0] if words else None
    p0 = _fl_plain(w0) if w0 else None
    # 指派 `NAME=值`（沒有前綴指派 `X=1 cmd`、沒有陣列、`+=`）
    if w0 is not None and w0["pieces"][0][0] == "P" and FL_ASSIGN_RE.match(w0["pieces"][0][1]):
        if len(words) > 1 or redirs:
            raise FlatReject("指派後面還有東西（`X=1 cmd` 這類前綴指派、陣列）不在文法裡：`%s`" % w0["raw"][:40])
        name = FL_ASSIGN_RE.match(w0["pieces"][0][1]).group(1)
        if FL_GH_RE.search(w0["raw"]) or name in FL_TRUSTED_VARS:
            raise FlatReject("指派 `%s`：`$GITHUB_ENV`／`$GITHUB_PATH` 與文法信任的 runner 變數（%s）在 run 裡不得指派或當成值"
                             % (w0["raw"][:40], "、".join(sorted(FL_TRUSTED_VARS - FL_CHANNEL_VARS))))
        ctx["mktemp"].discard(name)
        if any(p[0] == "M" for p in w0["pieces"]):
            if len(w0["pieces"]) != 2 or w0["pieces"][0][1] != name + "=":
                raise FlatReject("`$(mktemp …)` 只能是整個指派的值")
            # 只有「一定在目前的 shell 執行」的指派才算數：前面是換行或 `;`（不在 `&&`／`||` 右邊），後面不接管線（不在子殼層）
            if pos[0] in ("NL", ";") and pos[1] not in ("|", "|&"):
                ctx["mktemp"].add(name)
        return
    if w0 is None:
        raise FlatReject("只有重導向、沒有命令")
    if p0 is None or not FL_NAME_RE.fullmatch(p0):
        raise FlatReject("命令名不是純字面：`%s`" % w0["raw"][:40])
    args = words[1:]
    # `printf -v NAME` 會指派變數：格式參數必須是字面、不以 `-` 開頭。這一條在 GITHUB_ENV 的產生式**之前**檢查——原型放在它之後，
    # `printf -v RUNNER_TEMP … >> "$GITHUB_ENV"` 的參數全是字面，於是繞過了信任變數不得指派的規則（`bypass-r42-flat-ghwrite-printf-v`）。
    if p0 == "printf" and (not args or not _fl_lit(args[0]) or args[0]["raw"].lstrip("'\"").startswith("-")):
        raise FlatReject("`printf` 的第一個參數（格式）必須是字面、不以 `-` 開頭（`printf -v NAME` 會指派變數）")
    # GITHUB_ENV／GITHUB_PATH：唯一允許的寫入形狀是 echo／printf 全字面參數 `>>` 寫進它本身
    gh_targets = [r for r in redirs if r[2] is not None and FL_GH_RE.search(r[2]["raw"])]
    if gh_targets and all(r[1] == "<" and FL_GH_TARGET_RE.fullmatch(r[2]["raw"]) for r in gh_targets) \
            and not any(FL_GH_RE.search(w["raw"]) for w in words):
        gh_targets = []                          # 唯讀：shell 以唯讀開檔接到 fd 0（`grep -q X < "$GITHUB_ENV"`）
        redirs = [r for r in redirs if not (r[2] is not None and FL_GH_RE.search(r[2]["raw"]))]
    if gh_targets:
        if not (p0 in ("echo", "printf") and len(redirs) == 1 and redirs[0][1] == ">>"
                and FL_GH_TARGET_RE.fullmatch(redirs[0][2]["raw"])
                and all(_fl_lit(a, FL_GHVALUE_VARS) and not FL_GH_RE.search(a["raw"]) for a in args)):
            raise FlatReject("提到 `$GITHUB_ENV`／`$GITHUB_PATH` 的地方只收一種形狀：`echo`／`printf` 的參數全是字面"
                             "（雙引號裡只准 %s），`>> \"$GITHUB_ENV\"`" % "、".join("`$%s`" % v for v in sorted(FL_GHVALUE_VARS)))
        return
    for w in words:
        if FL_GH_RE.search(w["raw"]):
            raise FlatReject("提到 `$GITHUB_ENV`／`$GITHUB_PATH` 的地方只收一種形狀：`echo`／`printf` 的參數全是字面，"
                             "`>> \"$GITHUB_ENV\"`；唯讀寫成 `< \"$GITHUB_ENV\"`（當參數傳給程式、複製、別名都不收）")
    for r in redirs:
        if r[2] is not None and FL_GH_RE.search(r[2]["raw"]):
            raise FlatReject("提到 `$GITHUB_ENV`／`$GITHUB_PATH`")
        if ctx["filtered"] and r[2] is not None and not _fl_target_ok(r[2]):
            raise FlatReject("重導向目標 `%s` 不在文法裡（群組裡只收 `/dev/null`、相對路徑、`\"$RUNNER_TEMP/…\"`）" % r[2]["raw"][:40])
    if p0 == "trap":
        if redirs or len(args) != 2 or _fl_plain(args[1]) not in FL_SIGNALS:
            raise FlatReject("`trap` 只收 `trap <動作> EXIT`（或 `0`）；DEBUG／ERR／RETURN、其他訊號、選項都不收")
        act = args[0]
        if len(act["pieces"]) != 1:
            raise FlatReject("trap 的動作要是單一個單引號字串、雙引號字串或命令名")
        kind, body = act["pieces"][0][0], act["pieces"][0][1]
        # 只收三種片段。前一版只寫了 P 與 D 的分支、其餘落到「把 body 當文法剖析」——未加引號的 `trap $X EXIT` 的 body 是**變數名**，
        # 被當成外部命令收下；bash 卻在離開時把 `$X` 的值當程式碼執行（`bypass-r42-trap-unquoted-var-action`）。
        if kind not in ("P", "S", "D"):
            raise FlatReject("trap 的動作是未加引號的參數——設 trap 時展開、離開時把值當程式碼執行")
        if kind == "P":
            if not FL_NAME_RE.fullmatch(body) or body in FL_BUILTINS or body in FL_KEYWORDS:
                raise FlatReject("trap 的動作 `%s` 不是外部命令名" % body)
            return
        if kind == "D":
            text = []
            for q in body:
                if q[0] == "V":
                    if q[1] not in ctx["mktemp"] or q[2] is not None:
                        raise FlatReject("雙引號 trap 動作裡的 `$%s`：設 trap 時就展開、執行時當成程式碼再剖析一次——"
                                         "只收這個 body 裡由 `NAME=$(mktemp …)` 指派的變數" % q[1])
                    text.append("/tmp/tmp.x")
                else:
                    t_ = q[1]
                    text.append(t_[1:] if t_.startswith("\\") and t_[1:] in ('"', "\\", "$", "`") else
                                ("" if t_ == "\\\n" else t_))
            body = "".join(text)
        # 動作是離開時才執行的程式碼：它裡面的指派（含 `NAME=$(mktemp …)`）不影響設 trap 之後這個 body 的登記——用自己的一份。
        # 原型與外層共用同一個集合，單引號動作裡的 `tmp=$(mktemp -d)` 因此讓下一個雙引號 trap 展開了 PR 文字
        # （`bypass-r42-trap-action-registers-mktemp`）。
        _fl_body(body, dict(ctx, trap=True, mktemp=set(ctx["mktemp"])))
        return
    if p0 == "exit" and ctx.get("trap"):
        raise FlatReject("trap 動作裡的 `exit`——EXIT trap 裡的 `exit N` 會蓋掉整個 step 的退出碼")
    if p0 in FL_BUILTINS or p0 in FL_KEYWORDS:
        if p0 not in FL_INERT:
            raise FlatReject("`%s` 是 bash 的 builtin／保留字——文法只收外部命令與 echo、printf、test、[、true、false、:、exit"
                             "（`set` 只能當群組前的前綴）" % p0)


def _fl_body(text, ctx):
    cmds = _fl_lines(fl_tokens(text))
    for n_, (sep, items) in enumerate(cmds):
        words = [t[1] for t in items if t[0] == "W"]
        redirs = [t for t in items if t[0] == "R"]
        _fl_command(words, redirs, ctx, (sep, cmds[n_ + 1][0] if n_ + 1 < len(cmds) else "NL"))


def _fl_split_prefix(cmds):
    """開頭的 `set` 前綴行（只收 `_set_prefix_line` 的白名單，每個詞都是純字面）。回傳 (前綴數, pipefail 有沒有開)。"""
    k, pf = 0, False
    while k < len(cmds):
        sep, items = cmds[k]
        if sep not in ("NL", ";") or not items or items[0][0] != "W" or _fl_plain(items[0][1]) != "set":
            break
        toks = [_fl_plain(t[1]) if t[0] == "W" else None for t in items]
        if None in toks or not _set_prefix_line(toks):
            raise FlatReject("`set` 前綴只收 `-e`／`-u`／`-E`／`-o pipefail|errexit|nounset|errtrace`（每個詞都是字面）")
        nxt = cmds[k + 1][0] if k + 1 < len(cmds) else "NL"
        if nxt not in ("NL", ";"):
            raise FlatReject("`set` 前綴後面接了 `%s`" % nxt)
        pf = pf or "pipefail" in toks
        k += 1
    return k, pf


def flat_filtered(text):
    """靠管線過濾的 step：`set` 前綴* `{` BODY `}` (`2>&1 |` | `|&`) `python3 <路徑>/neutralise.py` [`;`]。回傳 pipefail 前綴有沒有開。"""
    toks = fl_tokens(text)
    cmds = _fl_lines(toks)
    k, pf = _fl_split_prefix(cmds)
    if k >= len(cmds):
        raise FlatReject("run 區塊只有 `set` 前綴，沒有群組")
    first = cmds[k][1][0]
    if not (first[0] == "W" and _fl_plain(first[1]) == "{"):
        raise FlatReject("`set` 前綴之後的第一個詞必須是群組的 `{`，實際是 `%s`" % (first[1]["raw"] if first[0] == "W" else first[1]))
    # 在原始詞元串上從 `{` 往後走，按 bash 的規則找命令位置上（`;`／換行之後）的第一個 `}`
    idx = [i for i, t in enumerate(toks) if t[0] == "W" and t[1] is first[1]][0]
    body_toks, j, at_cmd, close = [], idx + 1, True, None
    while j < len(toks):
        t = toks[j]
        if t[0] == "W" and at_cmd and _fl_plain(t[1]) == "}" and (not body_toks or body_toks[-1][0] == "NL"
                                                                  or body_toks[-1] == ("OP", ";")):
            close = j
            break
        body_toks.append(t)
        at_cmd = t[0] == "NL" or t[0] == "OP"
        j += 1
    if close is None:
        raise FlatReject("群組沒有收尾（`}` 要在 `;` 或換行之後）")
    ctx = {"mktemp": set(), "filtered": True}
    cmds = _fl_lines(body_toks)
    if not cmds:
        raise FlatReject("群組是空的（bash 對 `{ }` 報語法錯誤）")
    for n_, (sep, items) in enumerate(cmds):
        words = [t[1] for t in items if t[0] == "W"]
        if words and _fl_plain(words[0]) in ("{", "}"):
            raise FlatReject("群組裡的 `%s`（巢狀群組）不在文法裡" % _fl_plain(words[0]))
        _fl_command(words, [t for t in items if t[0] == "R"], ctx, (sep, cmds[n_ + 1][0] if n_ + 1 < len(cmds) else "NL"))
    tail = toks[close + 1:]
    while tail and tail[-1][0] == "NL":
        tail = tail[:-1]
    if tail[-1:] == [("OP", ";")]:
        tail = tail[:-1]
    shape = [t for t in tail if t[0] != "NL"]
    ok = False
    if len(shape) == 4 and shape[0] == ("R", "2>&1", None) and shape[1] == ("OP", "|"):
        py, path = shape[2], shape[3]
        ok = True
    elif len(shape) == 3 and shape[0] == ("OP", "|&"):
        py, path = shape[1], shape[2]
        ok = True
    if ok:
        ok = (py[0] == "W" and _fl_plain(py[1]) == "python3" and path[0] == "W" and _fl_plain(path[1]) is not None
              and re.fullmatch(r"[A-Za-z0-9_./-]*neutralise\.py", _fl_plain(path[1])) is not None)
    # 換行只准出現在 `|`／`|&` 之後（_fl_lines 的續行規則）；`}` 與 `2>&1` 之間、python3 與路徑之間不得換行
    nl_pos = [i for i, t in enumerate(tail) if t[0] == "NL"]
    if ok and nl_pos:
        pipe_at = next(i for i, t in enumerate(tail) if t[0] == "OP")
        ok = all(p == pipe_at + 1 + q for q, p in enumerate(nl_pos))
    if not ok:
        raise FlatReject("群組的 `}` 之後必須恰好是 `2>&1 | python3 <路徑>/neutralise.py`（或 `|& python3 …`），之後只准 `;`、註解、空行")
    return pf


def flat_declared(text):
    """宣告了 `# LOG-FILTER:` 而觸發了的 step：`set` 前綴* BODY。回傳 (有管線, pipefail 前綴有沒有開)。"""
    toks = fl_tokens(text)
    cmds = _fl_lines(toks)
    k, pf = _fl_split_prefix(cmds)
    ctx = {"mktemp": set(), "filtered": False}
    piped = any(t == ("OP", "|") or t == ("OP", "|&") for t in toks)
    for n_ in range(k, len(cmds)):
        sep, items = cmds[n_]
        words = [t[1] for t in items if t[0] == "W"]
        if words and _fl_plain(words[0]) in ("{", "}"):
            raise FlatReject("群組 `{ …; }` 在宣告不過濾的 step 裡不在文法裡")
        _fl_command(words, [t for t in items if t[0] == "R"], ctx, (sep, cmds[n_ + 1][0] if n_ + 1 < len(cmds) else "NL"))
    return piped, pf


def flat_trigger(text):
    """宣告不過濾的 step 什麼時候要落在文法裡：run 文字（含註解、引號、heredoc）裡有 `|` 字元——前面不是 `\\` 的 `||` 除外——
    或提到 GITHUB_ENV／GITHUB_PATH。依構造成立：bash 寫出來的每一條管線都有一個 `|` 字元，而一對前面沒有反斜線的 `||`
    在 bash 的詞法裡恆為「或」（兩個字元之間夾不進引號）。誤觸發（引號、註解、heredoc 裡的 `|`）只會多擋，不會漏。
    這是**寫出來的**管線的觸發條件：執行時才組出來的管線（`eval`、別的程式）不在它的範圍裡。"""
    rest, i = [], 0
    while i < len(text):
        if text.startswith("||", i) and (i == 0 or text[i - 1] != "\\"):
            i += 2
            continue
        rest.append(text[i])
        i += 1
    return "|" in "".join(rest) or FL_GH_RE.search(text) is not None


def flat_substitute(text, drop_nonliteral=False):
    """runner 運算式先代換（runner 在 bash 之前代換，所以依構造與 runner 同序）：字面常數換成它的值、GH_SAFE 換成 `0`。
    非字面的運算式：預設拒絕（值看不到，文法無從判斷 bash 看到什麼）；`drop_nonliteral` 時刪掉——只給 `flat_trigger` 的第二種讀法用。"""
    out, k = [], 0
    for a, b, inner in runner_exprs(text):
        out.append(text[k:a])
        v = inner.strip()
        if v.lower() in GH_SAFE_EXPRS:
            out.append("0")
        elif GH_LITERAL_RE.fullmatch(inner):
            if v.startswith("'"):
                val = v[1:-1].replace("''", "'")
                if "\n" in val and not drop_nonliteral:
                    raise FlatReject("字面運算式的值含換行")
                out.append(val)
            elif v == "null":
                out.append("")
            else:
                out.append(v)
        elif not drop_nonliteral:
            raise FlatReject("非字面的 runner 運算式")
        k = b
    out.append(text[k:])
    return "".join(out)


def _fl_declared_trigger(text):
    """宣告不過濾的 step 的觸發。R4′（連宣告的 step 也擋非字面運算式）不在 R42 的範圍（#33 的 R42 決策紀錄 (f)），所以這裡可能有
    非字面的運算式：它們的值看不到，觸發改看兩種讀法，任一觸發就要進文法——原文（運算式的字面也算），以及字面代換、非字面刪掉的
    結果（代換後才相鄰的 `\\` 與 `||` 在 bash 裡是管線）。已知不涵蓋：非字面運算式的**值**本身帶 `|` 或結尾的 `\\`——宣告的 step
    由作者承諾，其餘規則都信任宣告。"""
    return flat_trigger(text) or flat_trigger(flat_substitute(text, drop_nonliteral=True))


def flat_step_rules(where, name, ok, declared, logical, env_names, env_hit, text, tmpl):
    """`--strict` 的整條規則鏈（R42）：R1 → R4 → R3 → 信任變數的 env → 觸發了的宣告 step 的啟動 env → 正面文法 → pipefail。
    第一條不過的印一行 RULE、回傳 1；全過回傳 0。"""
    if not ok:
        if any(FL_NEUT_NEAR_RE.search(l) for l in logical):
            print(where + "step '%s' 的 run 區塊接到了 neutralise.py，但過濾器不是恰好 `python3 <字面路徑>/neutralise.py`"
                  "（直譯器選項、引號、變數都不收），也沒有 `# LOG-FILTER:` 註解" % name, file=sys.stderr)
        else:
            print(where + "step '%s' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾" % name,
                  file=sys.stderr)
        return 1
    if not declared and any(not gh_literal(inner) for _a, _b, inner in runner_exprs(text)):
        print(where + "step '%s' 靠管線過濾，而 run 裡直接寫了 runner 運算式 `${{ … }}`（純字面常數與 GitHub 產生的編號／SHA 除外）——"
              "runner 在 bash 解析之前代換，值裡的 PR 文字可以收掉引號與群組；改經 step 的 `env:` 傳進來" % name, file=sys.stderr)
        return 1
    if not declared and env_hit:
        print(where + "step '%s' 靠管線過濾，而 env（workflow／job／step）帶了 %s——bash（或過濾器 python3）啟動時就讀它們："
              "可以開 xtrace、在 run 之前執行別的程式碼，或把值印在管線右端的 stderr，那些輸出不經過管線" % (name, "、".join(
                  "`%s`" % k if k != "?" else "看不到鍵名的運算式" for k in env_hit)), file=sys.stderr)
        return 1
    triggered = not declared or _fl_declared_trigger(text)
    trusted = sorted(set(env_names) & FL_TRUSTED_VARS)
    if trusted and triggered:
        print(where + "[--strict] step '%s' 的 env（workflow／job／step）設了 %s——文法信任這些變數是 runner 給的值"
              "（`$GITHUB_ENV` 寫入的值、重導向目標、mktemp 的目錄），不得由 workflow 覆寫" % (name, "、".join("`%s`" % k for k in trusted)),
              file=sys.stderr)
        return 1
    if not triggered:
        return 0
    if declared:
        startup = [k for k in env_names if k in FL_STARTUP_KEYS or k == "?"]
        if startup:
            print(where + "[--strict] step '%s' 有寫出來的管線或提到 `$GITHUB_ENV`／`$GITHUB_PATH`，而 env 帶了 %s——bash 啟動時就讀它們，"
                  "可以在 run 之前關掉 pipefail" % (name, "、".join("`%s`" % k if k != "?" else "看不到鍵名的運算式" for k in startup)),
                  file=sys.stderr)
            return 1
    try:
        sub = flat_substitute(text)
        if declared:
            piped, pf = flat_declared(sub)
        else:
            piped, pf = True, flat_filtered(sub)
    except FlatReject as e:
        if not declared:
            print(where + "[--strict] step '%s' 靠管線過濾，而 run 區塊%s：%s——文法只收 `set` 前綴＋一個群組 "
                  "`{ …; } 2>&1 | python3 <路徑>/neutralise.py`；群組裡只收外部命令、echo／printf／test／[／true／false／:／exit、"
                  "`NAME=值`、`trap <動作> EXIT` 與點名的重導向。其餘寫進腳本檔再呼叫" % (name, FL_GRAMMAR_TAG, e), file=sys.stderr)
        else:
            print(where + "[--strict] step '%s' 有寫出來的管線或提到 `$GITHUB_ENV`／`$GITHUB_PATH`，而 run 區塊%s：%s——"
                  "文法外的構造（控制流程、builtin、命令替換…）可能關掉 pipefail 或改寫 `$GITHUB_ENV`，本 lint 不模擬它們；"
                  "寫進腳本檔再呼叫，或拿掉管線" % (name, FL_GRAMMAR_TAG, e), file=sys.stderr)
        return 1
    if piped and not (pf or (tmpl is not None and tmpl["pipefail"])):
        # 訊息保留 oracle.py 的 PIPEFAIL_RULE_MSG（「卻沒有跑在 pipefail 之下」）：神諭以它認出只因退出碼遮蔽而紅的列。
        print(where + "[--strict] step '%s' 有管線，卻沒有跑在 pipefail 之下（shell 不是關鍵字 `bash`、樣板也沒帶 `-o pipefail`，"
              "run 開頭的 `set` 前綴也沒開）——GitHub 預設 `bash -e {0}`，管線前段的失敗會被後段的 rc 蓋掉" % name, file=sys.stderr)
        return 1
    return 0


REQUIRE_RUN_STEPS = "--require-run-steps" in sys.argv
# **`--strict`**（#33 verify R35；R37 按 R36 第 3、4、13 列改寫；R42 按 R41 改寫）：CI 與 run.sh 對**真的 workflow** 用這個模式。
# 與預設模式的差別（封閉列舉，只有這三條——對應下面 `STRICT` 的四處用法）：
#   (1) 每個 run step 的規則鏈換成 `flat_step_rules`：R1 → 非字面的 runner 運算式 → 啟動時讀的 env 鍵 → 文法信任的變數被 `env:` 設定
#       → 觸發了的宣告 step 的啟動 env → 正面文法 → pipefail。預設模式的 fd 流向（`_analyse`）不在這條鏈裡：群組形式讓群組裡的
#       fd 1、fd 2 都進管線，文法又只收點名的重導向目標。pipefail 只有兩個來源：shell 是**關鍵字** `bash`（或樣板自帶
#       `-o pipefail`），或 run 開頭的 `set` 前綴——R33 的形狀普查 step 缺它，閘門在 CI 上結構上紅不了（R34 security S-1／
#       regression H-3／requirements F1）；R36 第 4 列：`bash -e {0}`、`bash -l {0}` 這類樣板**沒有** pipefail。
#   (2) shell 只能是 bash 樣板（不得開 xtrace／verbose）；container 或 Windows／運算式 runs-on 的 job 必須明寫 shell
#       （R35 從預設模式移過來：預設模式假設 shell 是 bash，見 `shell_scan` 已知不涵蓋第三組第 1 條）。
#   (3) workflow 根層級 `defaults.run` 寫成 flow 形式 ⇒ PARSE（R36 第 13 列：讀不到 shell）。
# R37–R41 的「群組規則」（`strict_group_violation`）與 R37–R40 的 pipefail 模擬已刪除，由 (1) 的正面文法取代。
# 預設模式不套用這三條：fixture 與產生語料量的是**詞法**，不是 CI 的寫法規範；改寫數百個 fixture 的管線只會讓
# 每一個詞法形狀多一個與它無關的變數。
STRICT = "--strict" in sys.argv
FLAGS = ("--require-run-steps", "--strict")
rc_all = 0
for path in [a for a in sys.argv[1:] if a not in FLAGS]:
    text = open(path, encoding="utf-8").read()
    # R20 regression R-2：前一版只用 `\n` 切行，於是一個 U+2028 藏得住第二個 `run:`。
    # **R22 regression R-2 的更正**：R21 的修法是在這裡寫一份 `OTHER_BREAKS` 元組——那**逐位元
    # 就是** `validate.py` 的 `_LINE_BREAKS` 減掉 `{"\r\n","\n"}`、而且順序相同，也就是同一概念的
    # 第二份寫死副本，正是 R20 放行條件第 1 點禁止的東西。當時的 commit message、CHANGELOG、
    # 以及這段註解本身都寫著「刻意不複製一份」——**那三句話都是假的**。
    #
    # 現在不列舉了：用 **Python 自己的 `splitlines()`** 當定義。一行（已經以 `\n` 切開、因此不含
    # `\n`）如果還能被 `splitlines()` 切成多段，就代表它含別的行界字元。沒有清單、沒有副本、
    # 新的行界字元由 Python 自己認得。
    raw = text.split("\n")
    stray = [(n, ln) for n, ln in enumerate(raw) if len(ln.splitlines()) > 1]
    if stray:
        n, ln = stray[0]
        odd = next((ch for ch in ln if len(ch.splitlines()) > 1 or ch in "\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"), "?")
        print("%s:%d: PARSE: 這一行含 `\\n` 以外的行界字元 %r —— YAML／runner 可能把它當換行，"
              "本 lint 不解析這種檔案" % (path, n + 1, odd), file=sys.stderr)
        rc_all = 1
        continue
    bad = []
    def reject(i, why):
        bad.append((i + 1, why))

    # `- key: v` 正規化成 `  key: v`（縮排 +2），讓 key 判定只有一條路徑
    norm, seq_at = list(raw), [False] * len(raw)
    for i, ln in enumerate(raw):
        m = SEQ_RE.match(ln)
        if m:
            seq_at[i] = True
            rest = (m.group(2) or "")
            norm[i] = " " * (len(m.group(1)) + 2) + rest if rest else ln

    # R30 MB-7：`root_indent` 不能對**全檔每一行**取 min——一行與結構無關的文字（跨行雙引號 scalar 的
    # 續行寫在第 0 欄）就讓整族 flow 規則不觸發，觸發條件與它取代掉的黑名單同形。
    # 改成由**解析器實際分類成 KEY 的行**決定：那個集合依構造排除了 scalar 續行、註解與清單項。
    # 因此 flow 規則不能在分類的同一個迴圈裡判（那時 root_indent 還不知道），改成**收集候選、分類完
    # 之後再判**——這樣「哪一棵子樹」的答案與解析器自己的答案永遠一致。
    flow_candidates = []          # (行號, 值, key 縮排)
    key_lines = []                # (行號, key 縮排, key 名)
    kind = [None] * len(raw)
    owner = [None] * len(raw)
    i = 0
    while i < len(raw):
        ln, st = raw[i], raw[i].strip()
        if not st:
            kind[i] = "BLANK"; i += 1; continue
        if st.startswith("#"):
            kind[i] = "COMMENT"; i += 1; continue
        if st in ("---", "..."):
            kind[i] = "BLANK"; i += 1; continue         # YAML 文件標記，合法（R22 裁決 3）
        if "\t" in ln[: len(ln) - len(ln.lstrip())]:
            reject(i, "縮排含 tab —— YAML 不允許，本 lint 不猜它的意思"); kind[i] = "BAD"; i += 1; continue
        if seq_at[i]:
            rest = (SEQ_RE.match(ln).group(2) or "").strip()
            if rest.startswith(("{", "[", "&", "*", "<<")):
                # R24 DA-8(a)：這裡 `reject()` 之後**沒有 continue**，控制流掉到下面的 plain-key 檢查，
                # 於是同一行再吐一則「清單項的 key 不是 plain 形式」——而 flow mapping 裡的 key
                # **全都是 plain**，那是假診斷。563 檔語料上出現 6 次，全是 `matrix.include` 這種
                # Actions 極常見的寫法。本輪新立的紀律是「紅的來源機械可判」，同一行兩則互相矛盾的
                # 訊息是它在解析層的反例。誠實的那一則留下，假的那一則不該存在 —— 補 continue。
                reject(i, "清單項用本 lint 不解析的寫法（flow／anchor／alias／merge key）：`%s`" % rest[:30])
                kind[i] = "BAD"; i += 1; continue
        mk = KEY_RE.match(norm[i])
        if mk:
            kind[i] = "KEY"
            val = (mk.group(3) or "").strip()
            # **flow 值只在「單行且不含 mapping」時才容忍**（R26 M1(b)）。
            # 守恆不變式是**文字型樣**不是解析器——`{`／`[` 裡面可以用無限多種寫法藏一個 `run` key
            # （`[run: …]`、`[{? run : …}]`、`[{"\x72un": …}]`、跨行 flow…），再補幾個字元類永遠追不完。
            # 所以改成結構判定：本 lint 不解析 flow mapping，**不解析就不放行**。
            # 反向（誤擋）由「不含 mapping 的單行 flow 序列照常放行」守住：`branches: [main]`、
            # `os: [ubuntu-latest, macos-14]` 這些 Actions 最常見的寫法都不含冒號，不受影響。
            key_lines.append((i, len(mk.group(1)), mk.group(2)))
            if val[:1] in ("{", "["):
                flow_candidates.append((i, val, len(mk.group(1))))
            # R30 MB-8：tag（`jobs: !!map {…}`）讓值的第一個字元是 `!`，於是 flow 規則、`steps:` flow
            # 檢查、anchor／alias 檢查**三條全部跳過**，整個 job 隱形。觸發條件是字元類就會有下一個字元。
            # 本 lint 不解析 tag —— 不解析就不放行。
            if val.startswith(("&", "*", "<<", "!")):
                reject(i, "欄位用 anchor／alias／merge key／tag 帶入——本 lint 不解析：`%s`" % val[:30])
            if mk.group(2) == "steps" and val.startswith(("[", "{")):
                reject(i, "`steps:` 用 flow 寫法（`[…]`／`{…}`）——本 lint 不解析，請改用 block 清單")
            # 跨行的引號 scalar：值裡的引號沒收掉，續行就是這個 scalar 的內容，**不是註解**。
            # 前一版的 COMMENT 分類只看 `strip()` 是否以 `#` 開頭、且排在白名單之上，於是
            # `name: "first` / `  # LOG-FILTER: …"` 的第二行被當成註解而放行整個 step
            # （R22 requirements F-1）。這裡把它一併消化成不透明內容。
            if val[:1] in ("'", '"'):
                q = val[0]
                body = val[1:]
                closed = False
                while True:
                    esc = False
                    for ch in body:
                        if esc:
                            esc = False; continue
                        if ch == "\\" and q == '"':
                            esc = True; continue
                        if ch == q:
                            closed = True; break
                    if closed:
                        break
                    j = i + 1
                    if j >= len(raw):
                        break
                    kind[j] = "SCALAR"; owner[j] = i
                    body = raw[j]; i = j
                i += 1; continue
            if BLOCK_SCALAR_RE.match(val):
                k_indent = len(mk.group(1))
                j = i + 1
                while j < len(raw):
                    nxt = raw[j]
                    if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= k_indent:
                        break
                    kind[j] = "SCALAR"; owner[j] = i; j += 1
                i = j; continue
            i += 1; continue
        if seq_at[i] and not (SEQ_RE.match(ln).group(2) or "").strip():
            kind[i] = "SEQ"; i += 1; continue           # bare `-`，鍵在下一行
        if seq_at[i]:
            rest_raw = (SEQ_RE.match(ln).group(2) or "")
            # **純量清單項是合法的，而且是 Actions 最常見的寫法之一**（`on: push: branches:` 底下的
            # `- main`、`paths`、`tags`、`needs`、block 形式的 `strategy.matrix.<dim>`、`services.*.ports`…）。
            # R21 把「清單項一定是 mapping」當成不成文前提，於是 26 個合法 workflow 誤擋了 20 個，
            # 而且訊息是**假診斷**（說「key 不是 plain 形式」，但那行根本沒有 key）。真 `test.yml`
            # 只因剛好用 flow 形式 `[main]` 而逃過（R22 裁決 3）。
            #
            # 判別式用 **YAML 自己的**：rest 含 `": "` 或以 `":"` 結尾才是 mapping，否則是純量。
            # R22 的 DA 在隔離樹實作並測過三種候選——另外兩種（含 security 提的「不是 plain key」）
            # 會讓 dash 行上的 `- run : x`、`- 'run': x` **靜默放行**而 selftest 全綠；只有這一個
            # 清掉全部十種合法形狀且零重開繞過。`- "8080:8080"` 這種含冒號但不是 mapping 的也對。
            code_rest, _ = yaml_split_comment(rest_raw)
            code_rest = code_rest.rstrip()
            if ": " in code_rest or code_rest.endswith(":"):
                reject(i, "清單項的 key 不是 plain 形式（冒號前有空白／加引號／顯式 key）：`%s`"
                       % rest_raw[:30])
            else:
                kind[i] = "SEQ"; i += 1; continue       # 純量清單項（`- main`、`- "8080:8080"`…）
        else:
            reject(i, "本 lint 不解析這一行（不是 plain key、不是清單項、不是 block scalar 內容）：`%s`" % st[:40])
        kind[i] = "BAD"; i += 1

    # ── flow 值的 fail-closed（分類完成之後才判，見上方 `flow_candidates` 的理由）──
    # 頂層 = **解析器分類成 KEY 的行裡縮排最小的那一層**。GitHub 接受並執行整份縮排的 workflow
    # （R29 探針 run 34927069456），所以頂層不是「縮排 0」；而取 min 的母體必須是解析器自己認的 key 行，
    # 不是全檔每一行（R30 MB-7）。
    root_indent = min((ind for _i, ind, _k in key_lines), default=0)
    for i, val, kind_ind in flow_candidates:
        top_key = None
        for li_, ind_, name_ in key_lines:          # 這一行之前最近的一個頂層 key
            if li_ > i:
                break
            if ind_ == root_indent:
                top_key = name_
        code_val, _ = yaml_split_comment(val)       # 引號內容挖空，避免資料裡的冒號誤判
        balanced = (code_val.count("{") == code_val.count("}")
                    and code_val.count("[") == code_val.count("]"))
        # **只在 `jobs:` 子樹裡 fail-closed**。第一版對整份文件套用，於是
        # `on: pull_request: { branches: [ main ] }` 這種完全合法、而且**結構上不可能藏 run step**
        # 的寫法被打紅——563 檔語料上當場兩個第三方檔從綠翻紅。誤擋與繞過是兩個方向，這條規則
        # 只該作用在真的可能藏東西的那棵子樹。括號不平衡（看不到整個值）則不分子樹一律拒絕：
        # 那時連「它在哪棵樹」都不確定。
        # **受影響面，量到的（R29；R28 DA D8 要求寫出來）**：野外 1565 檔被本規則擋 58 檔／177 行
        # ——121 行是單行 `{ name: …, os: … }`（`matrix.include` 類），56 行是跨行 flow 序列的開頭 `[`。
        # 這是**刻意** fail-closed：單行 flow mapping 可以藏 `run`，本 lint 不解析它就不放行；
        # `bypass-matrix-include-flow-mapping` fixture 釘住這個選擇。1002 份 GitHub 語料的清單見
        # `test/corpus/gh-workflow-corpus.txt`，量法：對清單每檔跑本 lint，數 stderr 含
        # 「flow 形式的值含 mapping 或跨行」的行與檔。
        if (":" in code_val and top_key == "jobs") or not balanced:
            reject(i, "flow 形式的值含 mapping 或跨行——本 lint 不解析它，而不解析就不放行："
                      "`%s`" % val[:40])
            kind[i] = "BAD"

    # ── 守恆不變式：**文字裡的每一個 `run` key，解析器都必須帳上有數** ──
    # R24 DA-1／DA-2。前一版是兩個各自的特例（清單項判準只認 `": "`、flow 值不管），於是
    #   `- 'run':<TAB>echo …`   引號 key 讓 KEY_RE 失配 ∧ tab 讓「rest 含 `": "`」失配 → 整項被當純量丟掉
    #   `j: {runs-on: …, steps: [{run: …}]}`   flow 值整段沒人解析
    # 兩者都讓 step 完全隱形、rc=0。**修法不是再補兩條特例**：改成一條守恆式——
    # 把文字裡看得出是 `run` key 的位置數一遍，與解析器實際記到的 run key 對帳，多出來就 fail-closed。
    # 這樣未來任何「新的藏法」都會被同一條擋住，不必等它被發現。
    #
    # 兩條正規式分工（不能只用一條）：
    #   PLAIN 對**引號挖空後**的文字比對 —— 這樣 `name: "how to run: carefully"` 這種資料不會誤判；
    #   QUOTED 對**原始**文字比對，但要求引號**恰好包住 `run`** 且緊接冒號 —— 這才抓得到引號 key，
    #   同時不會把「值裡剛好提到 run」算進來。
    # **誤擋面：只寫量到的，不寫想像的**（R26 M8：前一版這裡寫「`name: "{run: x}"` 會被拒」——
    # 實測 rc=0 **根本不會被拒**（QUOTED 要求引號恰好包住 `run`、PLAIN 看的是挖空後的文字），
    # 而真正會被誤擋的 `-run:` 結尾 key 一個字都沒寫。**以想像的限制代替量測到的限制，比不寫更糟**。）
    # R27 量測（三軸：RULE／PARSE／逐檔 rc，並報告 base-綠檔數當靈敏度分母）：
    #   真實語料 563 檔（分母 129）：GREEN->RED = 0
    #   DA 合成 base-綠語料 324 檔（分母 93）：GREEN->RED = 0
    # 也就是說在這兩份語料上**本守恆式沒有量到任何誤擋**。這句話的效力止於這兩份語料；
    # 語料清單：`test/corpus/r25-workflow-corpus.txt`（內容 hash ＋ repo 相對路徑）；量測腳本：
    # `test/corpus/threeaxis.py`（R29 進 repo；R27 時它只在 verify 的暫存目錄，這行當時寫的位置是假的）。
    # 1002 份 GitHub 語料的清單在 `test/corpus/gh-workflow-corpus.txt`（R31 補；R29 寫「清單見 test/corpus/」
    # 時那 1002 檔只在維護者本機的快取裡——位置陳述為假比沒有陳述更糟，它讓讀者以為自己可以查證）。
    # 要宣稱更多，先跑更大的語料。
    # R26 M1：`[-{,]` 有兩個錯。① 漏了 `[` —— YAML flow 序列允許**無括號的單對 mapping**
    # （`[k: v]` ≡ `[{k: v}]`），於是 `steps: [run: …]` 整個看不見。② `-` 直接放在字元類裡會
    # 命中**識別字內部的連字號**，`dry-run:`／`operations-per-run:`（`actions/stale` 最常見的
    # 兩個輸入）被判成藏起來的 run key —— 我在 R25 引進的真誤擋，第三方語料當場 6 處。
    # 清單項的 dash 後面**必然有空白**，而識別字內的連字號不會，所以用 `-\s+` 加左邊界。
    PLAIN_RUN_KEY = re.compile(r"(?:^\s*|(?<![\w.-])-\s+|[{,\[]\s*)run\s*:")
    # R30 MB-9（R31 探針 run 34938201988 證實 GitHub **接受並執行**）：
    # `- "\x72un":<TAB>echo …` —— 引號 key 用 YAML 的 hex 逃脫寫成 `run`，分隔用 tab。
    # 前一版的 QUOTED_RUN_KEY 要求引號**逐字**包住 `run`，於是逃脫寫法完全看不見；
    # 而清單項的 mapping 判準只認 `": "`（空白），tab 也看不見——**兩個各自的字面比對同時失手**。
    # 修法對準性質：引號 key 先用 YAML 的規則**解碼**再比對，比的是「解出來是不是 `run`」。
    QUOTED_KEY = re.compile(r"(?:^\s*|(?<![\w.-])-\s+|[{,\[]\s*)((['\"]).*?\2)\s*:")
    for i, ln in enumerate(raw):
        if kind[i] in ("COMMENT", "SCALAR"):
            continue                      # 註解與 block scalar 內容不是結構
        hollow, _ = yaml_split_comment(ln)
        found = len(PLAIN_RUN_KEY.findall(hollow))
        for m in QUOTED_KEY.finditer(ln):
            dec = yaml_decode_scalar(m.group(1))
            # `None` ＝ 這支未實作的逃脫（`\x72`、`\u0072`…）。**解不出來就當它可能是 `run`**：
            # 本 lint 的一貫立場是「不解析就不放行」，而這裡正是那個立場的入口——探針證明
            # GitHub 會把 `"\x72un"` 當成 `run` 執行（run 34938201988）。
            if dec == "run" or dec is None:
                found += 1
        accounted = 1 if (kind[i] == "KEY" and KEY_RE.match(norm[i]).group(2) == "run") else 0
        if found > accounted:
            reject(i, "這一行有 %d 個看得出是 `run` 的 key，但解析器只認到 %d 個——"
                      "本 lint 不解析它（引號 key、非空白分隔、flow 形式…），"
                      "而不解析就不放行：`%s`" % (found, accounted, ln.strip()[:40]))
            kind[i] = "BAD"

    # ── 第二階段：step 的邊界（R20：四份各自報的多條問題是**同一個根因** —— R19 把這一階段
    # 留成啟發式）。前一版用 `if ind <= s_indent: break` 當結束條件，暗含一個沒寫出來的前提：
    # 「清單項一定比 `steps:` 更深」。**那不是 YAML 的規則**：block sequence 可以與它的 key 同縮排
    # （`yaml.safe_load` 證明語意相同），於是整個 job 對 lint 隱形、rc=0 零輸出。
    #
    # 改法與第一階段同一個方向：**結構也白名單**。dash 的縮排由「`steps:` 之後第一個清單項」決定，
    # 之後只認**恰好那個縮排**的清單項；區塊結束於第一個縮排更淺的非空非註解行，或與 `steps:` 同層
    # 的下一個 key。找不到任何清單項 → **per-`steps:` fail-loud**（不解析就不放行）。
    steps = []
    for i in range(len(raw)):
        if kind[i] != "KEY":
            continue
        mk = KEY_RE.match(norm[i])
        if mk.group(2) != "steps":
            continue
        s_indent = len(mk.group(1))
        # dash 的縮排 = 第一個清單項的縮排（可以等於 s_indent —— flush 寫法）
        dash_indent, j = None, i + 1
        while j < len(raw):
            if kind[j] in ("BLANK", "COMMENT", "SCALAR"):
                j += 1; continue
            ind = len(raw[j]) - len(raw[j].lstrip())
            if seq_at[j] and ind >= s_indent:
                dash_indent = ind
            break
        if dash_indent is None:
            reject(i, "`steps:` 底下找不到任何清單項——本 lint 不解析這種寫法（flow 寫法？空 steps？）")
            continue
        starts = []
        j = i + 1
        while j < len(raw):
            if kind[j] in ("BLANK", "COMMENT", "SCALAR"):
                j += 1; continue
            ind = len(raw[j]) - len(raw[j].lstrip())
            if seq_at[j] and ind == dash_indent:
                starts.append(j); j += 1; continue
            if ind < dash_indent or (kind[j] == "KEY" and ind <= s_indent):
                break                                  # 離開 steps:（更淺，或 steps: 的兄弟 key）
            j += 1
        block_end = j - 1
        for n, st in enumerate(starts):
            # step 的行範圍 = [start, 下一個 start - 1]，尾端的空白／註解行**不屬於這個 step**
            en = (starts[n + 1] - 1) if n + 1 < len(starts) else block_end
            while en > st and (not raw[en].strip() or kind[en] == "COMMENT"):
                en -= 1
            cur = {"start": st, "end": en, "indent": dash_indent, "kindent": None,
                   "keys": {}, "name": "<未命名>"}
            for k_line in range(st, en + 1):
                if kind[k_line] != "KEY":
                    continue
                # **只看 step 自己那一層的 key**：`with:` / `env:` 底下的巢狀鍵是那個 mapping 的內容。
                k_ind = len(KEY_RE.match(norm[k_line]).group(1))
                if cur["kindent"] is None:
                    cur["kindent"] = k_ind
                if k_ind != cur["kindent"]:
                    continue
                k = KEY_RE.match(norm[k_line]).group(2)
                if k in cur["keys"]:
                    reject(k_line, "step 裡 `%s:` 出現兩次——YAML 取後者、lint 讀前者，本 lint 拒絕" % k)
                cur["keys"][k] = k_line
                if k == "name":
                    cur["name"] = (KEY_RE.match(norm[k_line]).group(3) or "").strip() or "<未命名>"
                elif k not in STEP_KEYS:
                    reject(k_line, "step 用了白名單外的欄位 `%s:`——本 lint 只認 %s" % (k, sorted(STEP_KEYS)))
            steps.append(cur)

    # ── 每個 step 實際用哪個 shell（#33 verify R34 security S-3、DA n4／n4b）──
    # runner 的 shell 由 step `shell:` → job `defaults.run.shell` → workflow `defaults.run.shell` 決定；都沒寫時，
    # container job 用 sh、Windows runner 用 pwsh。本 lint 的詞法是 bash 的，所以這兩種都得先查出來。
    def _kids(lo, hi, pind):
        # `hi` 由 `_end` 算：下一個縮排 ≤ pind 的 key 之前——範圍內的 key 縮排必然 > pind（opsweep 報 `ind_ > pind` 存活，死碼刪掉）
        ks = [(l_, ind_, k_) for l_, ind_, k_ in key_lines if lo < l_ <= hi]
        if not ks:
            return []
        m_ = min(ind_ for _l, ind_, _k in ks)
        return [(l_, ind_, k_) for l_, ind_, k_ in ks if ind_ == m_]

    def _end(l0, ind0):
        nx = [l_ for l_, ind_, _k in key_lines if l_ > l0 and ind_ <= ind0]
        return (min(nx) - 1) if nx else len(raw) - 1

    def _uncomment(t):
        """去掉 YAML 行尾註解、**保留引號內容**。`yaml_split_comment()` 的程式碼半邊雖然引號內容被挖空，但挖空是逐字元替換、長度不變（`len(code)` 恆等於註解起點位置），所以程式碼半邊的長度同樣可以拿來找起點；目前的實作選擇拿註解半邊的長度用
        （#33 verify R36 第 12、22 列：`_scalar` 與 `ro_text` 各自踩過一次——一個把 `"bash"` 讀成一串空白，一個把
        `# windows runners …` 這句註解讀成 Windows runner）。"""
        _code, cmt = yaml_split_comment(t)
        return t[:len(t) - len(cmt)] if cmt else t

    def _scalar(l0):
        body = _uncomment(KEY_RE.match(norm[l0]).group(3) or "")
        # 解碼對**原文**做（R36 第 12 列：前一版先挖空再解碼，`shell: "bash"` 成了 `'    '`、`--strict` 判 PARSE；放回 strip
        # 則 `shell: 'pwsh'` 變成空字串＝「沒寫 shell」而放行——兩個方向都錯）。解不出來就回原文，`--strict` 會當成不是 bash。
        d = yaml_decode_scalar(body)
        return d if d is not None else body.strip()

    def _flow_value(l0):
        """這個 key 的值寫成 flow 形式（`{…}`／`[…]`）。"""
        return _uncomment(KEY_RE.match(norm[l0]).group(3) or "").strip()[:1] in ("{", "[")

    def _env_names(l0, ind0):
        """`env:` 底下的鍵名。值寫在同一行、又不是 flow（`env: ${{ fromJSON(…) }}`）⇒ 鍵名看不到，回 `["?"]`（fail-closed）；
        flow 形式含 mapping 的，解析層已經 PARSE（jobs 子樹的 flow 規則、根層級見下），這裡不重複判。"""
        inline = _uncomment(KEY_RE.match(norm[l0]).group(3) or "").strip()
        if inline:
            return [] if inline[:1] in ("{", "[") else ["?"]
        # `PYTHON*` 的值是 runner 運算式（R39，#33 verify R38 第 9 列）：過濾器 `python3` 啟動時就讀它——`PYTHONWARNINGS` 的值不合法時
        # 原樣印到**管線右端**的 stderr，不經左端的 `2>&1`。記成 `KEY=${{ … }}`，由 `ENV_EXPR_RE` 認出來；字面值（`PYTHONPATH: src`）
        # 不可能帶 PR 文字，照常放行。
        return [k_ + "=${{ … }}" if k_.startswith("PYTHON") and "${{" in " ".join(raw[_l:_end(_l, _i) + 1]) else k_
                for _l, _i, k_ in _kids(l0, _end(l0, ind0), ind0)]

    def _defaults_shell(l0, ind0):
        for l1, i1, k1 in _kids(l0, _end(l0, ind0), ind0):
            if k1 == "defaults":
                for l2, i2, k2 in _kids(l1, _end(l1, i1), i1):
                    if k2 == "run":
                        for l3, _i3, k3 in _kids(l2, _end(l2, i2), i2):
                            if k3 == "shell":
                                return _scalar(l3)
        return None

    roots = [(l_, ind_, k_) for l_, ind_, k_ in key_lines if ind_ == root_indent]
    wf_shell, wf_env = None, []
    for l_, ind_, k_ in roots:
        if k_ == "defaults":
            for l2, i2, k2 in _kids(l_, _end(l_, ind_), ind_):
                if k2 == "run":
                    # **根層級 `defaults.run` 的 flow 形式**（R36 第 13 列）：`run: {shell: sh}` 讀不到 shell，前一版 `--strict` rc=0。
                    # jobs 子樹裡的同一寫法由 flow 規則擋；`defaults: {run: …}` 整個 flow 由 run key 守恆式擋（`{run:` 算一個 run key）。
                    if STRICT and _flow_value(l2):
                        reject(l2, "[--strict] workflow 的 `defaults.run` 用 flow 形式——本 lint 讀不到 shell，不解析就不放行")
                    for l3, _i3, k3 in _kids(l2, _end(l2, i2), i2):
                        if k3 == "shell":
                            wf_shell = _scalar(l3)
        elif k_ == "env":
            # 根層級 flow 形式的 env（`env: {SHELLOPTS: xtrace}`）讀不到鍵名（兩種模式；jobs 子樹的由 flow 規則擋）
            if _flow_value(l_) and ":" in yaml_split_comment(KEY_RE.match(norm[l_]).group(3) or "")[0]:
                reject(l_, "workflow 根層級的 `env` 用 flow 形式——本 lint 讀不到鍵名（SHELLOPTS、BASH_ENV… 在 bash 啟動時就生效），"
                           "不解析就不放行")
            else:
                wf_env = _env_names(l_, ind_)
    jobs_info = []
    for l_, ind_, k_ in roots:
        if k_ != "jobs":
            continue
        for lj, ij, _name in _kids(l_, _end(l_, ind_), ind_):
            hi = _end(lj, ij)
            kids = _kids(lj, hi, ij)
            names = {k2 for _l, _i, k2 in kids}
            ro_text, job_env = "", []
            for l2, i2, k2 in kids:
                if k2 == "runs-on":
                    # 行尾註解不算（R36 第 22 列：`runs-on: ubuntu-latest  # windows runners are not supported` 被判成 Windows）；
                    # 引號內容要留著（`runs-on: "windows-latest"` 仍是 Windows——`bypass-r37b-strict-runs-on-quoted-windows`）
                    ro_text = " ".join(_uncomment(l) for l in raw[l2:_end(l2, i2) + 1])
                elif k2 == "env":
                    job_env += _env_names(l2, i2)
                elif k2 == "container":
                    # 容器 job 的 step 用 docker exec 跑在容器裡，繼承 `container.env`
                    job_env += [n_ for l3, i3, k3 in _kids(l2, _end(l2, i2), i2) if k3 == "env" for n_ in _env_names(l3, i3)]
            jobs_info.append({"lo": lj, "hi": hi, "container": "container" in names,
                              "windows": "windows" in ro_text.lower() or "${{" in ro_text,
                              "ro": ro_text.split("runs-on:", 1)[-1][:40],      # 只進訊息（opsweep 報 strip 存活，刪掉）
                              "shell": _defaults_shell(lj, ij), "env": job_env})

    rc, seen = 0, 0
    for s in steps:
        if "run" not in s["keys"]:
            continue
        seen += 1
        r = s["keys"]["run"]
        job = next((j for j in jobs_info if j["lo"] <= s["start"] <= j["hi"]), None)
        eff_shell = (_scalar(s["keys"]["shell"]) if "shell" in s["keys"] else None) \
            or (job["shell"] if job else None) or wf_shell
        # **shell 是 `--strict` 的規則，不是預設模式的**（R35 三軸：預設模式一律套用時，合成 A 語料 959 個 base-綠檔
        # 有 290 個翻紅——`shell: bash -euo pipefail {0}`、`runs-on: ${{ matrix.os }}`、container job 都是常見寫法）。
        # 預設模式量的是「lint 與 bash 的詞法對帳」，它**假設** shell 是 bash（已知不涵蓋第三組第 1 條）；
        # CI 與 run.sh 對真 workflow 用 `--strict`，在那裡驗這個假設。
        tmpl = _bash_template(eff_shell) if eff_shell is not None else None
        if STRICT and eff_shell is not None and (tmpl is None or tmpl["trace"]):
            reject(s["keys"].get("shell", r), "[--strict] step 的 shell 是 %r——本 lint 的詞法是 bash 的，只接受 bash 樣板"
                                                 "（`bash`／`/bin/bash`／`/usr/bin/bash` 帶白名單內的選項；不得開 xtrace 或 verbose："
                                                 "`-x`、`-v`、`-o xtrace`、`--verbose` 會把 PR 文字印到 stderr）" % eff_shell)
            continue
        if STRICT and eff_shell is None and job and (job["container"] or job["windows"]):
            reject(r, "[--strict] 沒寫 shell，而這個 job %s——runner 不一定用 bash；請明寫 `shell: bash`"
                      % ("跑在 container 裡（預設 sh）" if job["container"] else "的 runs-on 是 %r（Windows 預設 pwsh，運算式無法靜態判定）" % job["ro"]))
            continue
        inline = (KEY_RE.match(norm[r]).group(3) or "").strip()   # plain scalar 前後空白不是值；一次 strip、之後不再各自 strip
        yaml_trailing_cmts = []
        # `run: |` 的 `|` 是 **block scalar 的指示子**，不是要執行的程式碼。前一版把它當成 run 的
        # 第一段文字丟進 run_joined，於是 `run: |` + 下一行的 `python3 …neutralise.py` 被接成
        # `| python3 …neutralise.py` ——**憑空造出一條管線**（R22 logic / Codex #1 的那個 fixture
        # 就是這樣過的）。這是 R21 為修折疊管線誤擋而加的合併帶進來的，第二次。
        explicit_pad, block_folded = None, False
        if BLOCK_SCALAR_RE.match(inline):
            # R28 D5（Codex 第 4 條）：`|2` 的數字是**顯式縮排指示子**——內文縮排 = 父節點縮排 + N，
            # 比它深的空白是內容、runner 會保留（PyYAML：`run: |2` 下 12 格的 `EOF` 讀成 `  EOF`）。
            # 這裡算好交給 dedent_block；淺於 N 的內文行是 YAML 錯誤，下面拒絕、不猜。
            block_folded = inline.startswith(">")
            m_hdr = BLOCK_SCALAR_RE.match(inline)
            ind = m_hdr.group(1) or m_hdr.group(2)      # 只取標頭本身的指示子，不碰行尾註解
            if ind:
                explicit_pad = len(KEY_RE.match(norm[r]).group(1)) + int(ind)
            inline = ""
        elif inline[:1] in ("|", ">"):
            # 標頭以 `|`／`>` 開頭卻不合 BLOCK_SCALAR_RE（`|0`、`|10`）：YAML 錯誤。規則對一個沒被
            # 解析出來的 run 區塊沒有適用對象（R24 DA-8(b)）——只印 `PARSE:`，不落到 else 去當 shell 掃。
            reject(r, "block scalar 標頭不合法（縮排指示子須為 1-9）：`%s`" % inline[:20])
            continue
        elif not inline:
            # R24 DA-8(b)：`run:` 的值寫在**下一行**（合法的 plain multi-line scalar）時，前一版
            # 既印 `PARSE:`（不解析那一行）**又**印 `RULE:`（說它沒過濾）——而該 step 真的過濾了。
            # 規則對一個沒被解析出來的 run 區塊**沒有適用對象**：只印 `PARSE:`，不得再印 `RULE:`。
            reject(r, "`run:` 的值不在同一行、也不是 block scalar（plain multi-line scalar）——本 lint 不解析")
            continue
        else:
            # **跨實體行的引號純量**（R37，#33 verify R36 第 21 列 LOW；探針 `test/fixtures/
            # ci-log-filter-bypass-r37d-multiline-*-run.yml`）：`run: "echo hi` 換行接 `| python3 …"`——
            # 這是**真正跨 YAML 實體行**的雙／單引號純量（不同於下面 `\n` 逃脫字面出現在單一實體行內的情形，
            # 那個由 `yaml_decode_scalar` 正常處理）。第一階段分類器已經把續行標成 `kind=="SCALAR"`／
            # `owner==r`（見上面 KEY 分類那段），所以這裡直接查那個既有結果，不必重新判斷引號有沒有收尾。
            # 前一版對這種輸入：`yaml_decode_scalar` 因為引號沒在同一行收尾而回傳**未解碼的原始文字**（不是
            # `None`），續行的原始 YAML 文字又被接進 `run_lines`——結果是 `shell_scan()` 把 YAML 的引號字元
            # 當成 shell 引號字元掃，兩層語意混在一起：本來會被過濾的 `echo hi | python3 …neutralise.py`
            # 因此被誤判成 RULE（未過濾）。跨行引號純量的重新序列化規則本 lint 沒有實作，fail-closed PARSE，
            # 不要往下走去猜。
            if inline[:1] in ("'", '"') and any(
                    kind[k] == "SCALAR" and owner[k] == r for k in range(r + 1, s["end"] + 1)):
                reject(r, "`run:` 的值是跨行的引號純量——本 lint 只解析單一實體行內收尾的引號純量，"
                          "跨行的重新序列化規則不猜")
                continue
            # R28 D7：`run: "…" # note` 的行尾註解是 YAML 層的，不在引號純量裡。先用 YAML 規則
            # 找到註解起點（yaml_split_comment 回傳的兩半，只有程式碼半邊被挖空，註解半邊 `comment = line[i:]` 是未挖空的原始文字；這裡捨棄挖空的那半，只借用原始註解的長度切原文），再解碼
            # 程式碼半邊；註解半邊歸宣告來源 (3)。前一版整行送去解碼→不是引號純量→原樣當 shell
            # 掃，於是引號裡的真管線被挖空、rc=1，而 runner 眼中那條管線存在。
            _, yaml_cmt = yaml_split_comment(inline)
            decoded = yaml_decode_scalar(inline[:len(inline) - len(yaml_cmt)] if yaml_cmt else inline)
            if decoded is None:
                reject(r, "`run:` 的值用了本 lint 未實作的 YAML 逃脫——"
                          "解錯字串會讓管線判定憑空成立或憑空消失，所以不猜：`%s`" % inline[:40])
                continue
            inline = decoded
            # **解碼後的換行是換行**（R35 三軸順帶找到、6cf6864 就有的繞過）：`run: "echo x\n#| python3 …"` 解碼後
            # 前一版把整串當成一行交給 `shell_scan`——換行後的 `#` 不在詞首、不起註解，`#| python3 …` 被讀成一條管線。
            # 按 `\n` 切行；切出來的行**不 dedent**（引號純量的行首空白是內容，heredoc 的終止行要逐字比）。
            if "\n" in inline:
                explicit_pad = 0
            if yaml_cmt:
                yaml_trailing_cmts.append(yaml_cmt)
        run_lines = inline.split("\n") + [raw[k] for k in range(r + 1, s["end"] + 1)
                                if kind[k] == "SCALAR" and owner[k] == r]
        if explicit_pad is not None and any(
                l.strip() and (len(l) - len(l.lstrip(" "))) < explicit_pad for l in run_lines[1:]):
            reject(r, "`run: |N` 的內文有一行比顯式縮排指示子淺——YAML 錯誤（PyYAML ParserError），本 lint 不猜")
            continue
        # **宣告層也白名單**（R20 security S-1/S-2）：R19 讓 block scalar 的內容對「結構」判定不透明，
        # 卻沒對「宣告」判定不透明——於是 `name: |` 的 scalar 裡寫一行 `# LOG-FILTER:` 就放行整個 step，
        # 而那一行是 step 的**顯示名稱**不是註解（`yaml.safe_load` 可證）。註解歸屬也會跨 step 邊界。
        # 現在只認**三種**來源，其餘一律不算（R26 M8／logic LOW-9：前一版寫「兩種」，而 R25 換成
        # `shell_scan()` 之後 `run:` 行尾的 YAML 註解實際上也算數——base rc=1 → head rc=0，行為放寬了
        # 卻沒揭露。它是合理的來源（那段文字 runner 不會執行、又緊貼著 run 本身），所以**保留並明寫**，
        # 另補 `good-run-trailing-comment.yml` 當正向 fixture 把它釘住）：
        #   (1) 真的是**註解行**（kind == COMMENT）且落在這個 step 自己的行範圍、縮排比 dash 深；
        #   (2) `run:` **自己**那個 block scalar 內容裡的 shell 註解（`shell_scan()` 的 decls 桶）；
        #   (3) `run:` 那一行本身、值之後的行尾註解（YAML 註解與 shell 註解在這個位置語意相同：
        #       runner 都不會執行它）。
        # `# LOG-FILTER:` 只能來自**不會被執行的部分**。(2)(3) 都由 shell_scan 切出來，與管線判定
        # 共用同一個定義；(1) 由 YAML 分類決定。
        decl_lines = []
        for k in range(s["start"], s["end"] + 1):
            if kind[k] == "COMMENT" and (len(raw[k]) - len(raw[k].lstrip())) > s["indent"]:
                decl_lines.append(raw[k])
            # `run:` 區塊自己的 shell 註解由 shell_scan 一次掃出（跨行狀態），不再逐行用 YAML 規則切。
        # 管線可以跨行（折疊 scalar `>`，或 literal `|` 裡行尾留 `|` 續行）——R20 regression R-6：
        # 前一版只逐行比對，於是 `echo hi |` / `python3 …neutralise.py` 分兩行寫就被誤擋。
        # 兩種寫法下行尾的 `|` 本來就代表管線延續，所以把 run 區塊接成一串再比對是語意正確的。
        # 管線判定只看**會被執行的部分**（引號內容已挖空、註解已剝掉）。跨行管線（折疊 scalar，
        # 或行尾留 `|` 續行）仍要接成一串才判得到——但接的是 code 半邊，不再是原始文字。
        scan_in = fold_block(dedent_block(run_lines, explicit_pad), block_folded)
        run_code, shell_decls, run_unparsed = shell_scan(scan_in)
        if run_unparsed:
            reject(r, run_unparsed)
            continue
        decl_lines += shell_decls + yaml_trailing_cmts
        # **邏輯行**：只有前一行以 `|`／`||`／`|&`／`&&` 結尾時才接續下一行——那才是 bash 會把兩行當成同一條
        # 命令的情形。前一版把整個區塊用空白接成一串再比對（`run_joined`），於是 literal 區塊裡
        # `echo "$PR_TITLE"` ⏎ `| python3 …neutralise.py` 被接成一條假管線而放行，
        # 而 bash 對行首的 `|` 報的是**語法錯誤**（R30 H-6：兩條路各自獨立足以放行，
        # 所以只收緊 `PIPED_RE` 修不好——要改的是「什麼叫一條命令」）。
        logical = _logical_lines(run_code)
        rl_code, rl_src = _rule_lines(run_code, scan_in)     # 規則層的邏輯行：程式碼＋對齊的原文（R37，見 `_rule_lines`）
        via_pipe = any(PIPED_RE.search(l) for l in logical)
        declared = any(LOGFILTER_RE.match(l) for l in decl_lines)
        ok = via_pipe or declared
        # env 帶進的 shell 設定（R36 第 8 列）：workflow／job（含 container.env）／step 三層；`?` ＝值是運算式、鍵名看不到
        env_names = wf_env + (job["env"] if job else []) + (
            _env_names(s["keys"]["env"], s["kindent"]) if "env" in s["keys"] else [])
        env_hit = [k for k in env_names if k in ENV_TRACE_KEYS or k == "?" or ENV_EXPR_RE.fullmatch(k)]
        where = "%s:%d: RULE: " % (path, s["start"] + 1)
        if STRICT:
            # R42：`--strict` 的整條規則鏈是正面文法（`flat_step_rules`）。下面的 `_analyse`（fd 流向）與這一段之後的規則只在預設模式跑；
            # R37 的群組規則與 R37–R40 的 pipefail 模擬已刪除。
            if flat_step_rules(where, s["name"], ok, declared, logical, env_names, env_hit,
                               "\n".join(l for l in scan_in if l is not None), tmpl):
                rc = 1
            continue
        try:
            an = _analyse(rl_code, rl_src)
        except (IndexError, KeyError, ValueError, RecursionError) as e:   # 剖析器自己的錯：fail-closed，不讓 traceback 蓋掉其他檔
            reject(r, "規則層剖析這個 run 區塊時出錯（%s: %s）——不解析就不放行" % (type(e).__name__, e))
            continue
        if not ok:
            print(where + "step '%s' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾"
                  % s["name"], file=sys.stderr)
            rc = 1
        elif not declared and an["fd"]:
            # **fd 流向**（#33 verify R34 security S-2／logic F5／DA G-B；R36 第 8、9 列改成按流向判）：把 stdout 帶離管線
            # （複製到 fd 2 或另存的 fd、寫到 /dev 或 /proc 底下）或開 xtrace／verbose，PR 文字都繞過只接 stdout 的管線——
            # **帶了 `2>&1` 也一樣**：`>&2 2>&1 |` 的 `>&2` 先把 fd 1 指到原本的 stderr；xtrace 在命令自己的 `2>&1` 套用之前就印到
            # shell 的 fd 2。只對「靠管線過濾」的 step 適用；`# LOG-FILTER:` 明示不過濾的 step 不受限（它已經聲明不印 PR 文字）。
            print(where + "step '%s' 靠管線過濾，卻有 %s——那些文字不經過管線（帶了 `2>&1` 也一樣：重導向由左到右套用；"
                  "只有收尾後緊接 `2>&1 |`／`|&` 進 neutralise 的群組 `{ …; }`／`( … )` 裡面例外）" % (s["name"], an["fd"][0]),
                  file=sys.stderr)
            rc = 1
        elif not declared and env_hit:
            print(where + "step '%s' 靠管線過濾，而 env（workflow／job／step）帶了 %s——bash（或過濾器 python3）啟動時就讀它們："
                  "可以開 xtrace、在 run 之前執行別的程式碼，或把值印在管線右端的 stderr，那些輸出不經過管線" % (s["name"], "、".join(
                      "`%s`" % k if k != "?" else "看不到鍵名的運算式" for k in env_hit)), file=sys.stderr)
            rc = 1
        elif not declared and any(not gh_literal(inner) for _a, _b, inner in
                                  runner_exprs("\n".join(l for l in scan_in if l is not None))):
            # R40（#33 verify R39 第 1 列）：前一版只認點號的 `github.event.`／`github.head_ref`，檔內還寫成「封閉列舉，只有這兩種」——
            # 那是拼法清單：`toJSON(github.event)`、`format('{0}', …)`、`github['event']…`、`env.X`、`steps.*.outputs.*`、大寫的
            # `GITHUB.EVENT…` 同樣由 runner 在 bash 之前代換，全部放行。現在反過來：只有純字面常數不管，其餘一律擋。
            # 代價：`matrix.*`、`inputs.*`、`runner.*` 這類作者控制的值也擋（它們可以經 `fromJSON(needs.*.outputs…)` 帶進 PR 文字）——
            # 改經 step 的 `env:` 傳進來。本 repo 的 test.yml 在任何 run 裡都沒有 `${{`。
            print(where + "step '%s' 靠管線過濾，而 run 裡直接寫了 runner 運算式 `${{ … }}`（純字面常數與 GitHub 產生的編號／SHA 除外）——runner 在 bash 解析之前"
                  "代換，值裡的 PR 文字可以收掉引號與群組；改經 step 的 `env:` 傳進來" % s["name"], file=sys.stderr)
            rc = 1
    for lineno, why in bad:
        # `PARSE:` / `RULE:` 是**機器可判的紅色來源標記**（R22 裁決 3）：22 個 bypass fixture 裡有
        # 8 個只靠 parse-reject 變紅，而 parse-reject 正是修誤擋必須放寬的機制——selftest 分不出
        # 兩種紅，就等於「修誤擋會靜默重開繞過」。現在每個 fixture 自己宣告它該是哪一種。
        print("%s:%d: PARSE: %s" % (path, lineno, why), file=sys.stderr)
    # vacuity 只在**解析成功**時才有意義：已經有結構性拒絕時，「找不到 run step」是那個拒絕的
    # 後果，不是另一件事。前一版兩個訊息都印，於是「這個 fixture 是被規則擋的嗎」變得無法機械判定
    # （R18 regression LOW 就是踩在這上面）。
    if seen == 0 and not bad:
        # 訊息刻意與規則的訊息不同：selftest 斷言 bypass fixture 的紅**不是**這一條
        # （R18 regression LOW：前一版只看 rc，於是 vacuity 守衛的紅被當成規則的紅）。
        # R22 Codex #2：「每個 `run` 都要交代」不等於「每份 workflow 都要有 `run`」。解析成功而
        # 本來就沒有 run step（純 `uses:`、只呼叫 reusable workflow）是**合法**的，先前卻讓整支
        # lint 變紅。把「解析器漏掉 run」與「本來就沒有 run」分開：前者由白名單的 fail-loud 負責，
        # 後者印一則說明就好。selftest 仍需要 vacuity 保護——改由 `--require-run-steps` 提供。
        if REQUIRE_RUN_STEPS:
            print("VACUOUS: no run steps found in %s — the lint would be vacuous" % path, file=sys.stderr)
            rc_all = 1
        else:
            # R24 DA-2：前一版這行斷言了一件它**沒有驗證**的事（宣稱該檔只有 uses 形式的 step）。
            # 那句字面現在刻意不出現在本檔任何地方——放行條件是機械 grep，把被禁的字面寫進說明
            # 正是它第一個踩到的東西（本 repo 已有兩次前例）。
            # 解析器收集不到 step 有兩種可能——真的沒有 run，或它沒看懂——而這行把兩者講成同一件。
            # 現在只陳述觀察到的事實，不給原因。（真正把「沒看懂」擋下來的是上面的守恆不變式。）
            print("%s: 本次未偵測到 run step —— 本規則沒有適用對象" % path, file=sys.stderr)
    rc_all = rc_all or rc or (1 if bad else 0)
sys.exit(rc_all)
PY
