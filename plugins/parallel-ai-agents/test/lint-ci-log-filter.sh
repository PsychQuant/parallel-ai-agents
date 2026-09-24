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
#                                                             **假設 shell 是 bash**、不要求 pipefail 與逐段 `2>&1`
#       test/lint-ci-log-filter.sh --selftest
#       檔名請給絕對路徑或相對於 plugin 目錄的路徑：本 lint 先 `cd` 到 plugin 目錄，找不到檔案回 rc=2（不是 pass）。
# **兩種模式的取捨（#33 verify R34 放行條件第 5 條的偏離，R36 第 25 列要求寫在這裡）**：非 bash 的 shell（`sh`、`pwsh`、
# 帶白名單外選項的樣板）、container job、Windows／運算式 runs-on 只在 `--strict` fail-closed。R35 第一版在預設模式也套用，
# 合成 A 語料 959 個 base-綠檔翻紅一大批（R35 寫 290；R36 requirements 按規則重量：shell 值那條 75 檔、container／Windows
# 沒寫 shell 那條 223 檔，聯集 268——多數來自第 5 條沒要求的後者）。預設模式服務的是詞法量測、不是 CI 的寫法規範，
# 所以 shell 規則只放在 `--strict`；而 CI 與 run.sh 對真 workflow 一律用 `--strict`，第 5 條要的保護在那裡。
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  # R22 裁決 3／5：selftest 現在驗**三件**，不只「有沒有紅」。
  #   (1) 每個 fixture 自己用 `# EXPECT:` 宣告它該是 pass／rule-red／parse-red，實測必須相符。
  #       為什麼要分辨兩種紅：22 個 bypass fixture 裡有 8 個**只靠 parse-reject 變紅**，而
  #       parse-reject 正是修誤擋必須放寬的機制——分不出來，就等於「修誤擋會靜默重開繞過」。
  #   (2) **正向 fixture**（`good-*`）：先前 22 個 fixture 全是負向，一個都沒有證明它放得過好輸入。
  #       誤擋 26 個合法 workflow 中的 20 個，正是這個不對稱的必然結果。
  #   (3) bypass fixture 加 `--require-run-steps`，保留原本的 vacuity 保護（正式執行時不再套用，
  #       因為純 `uses:` workflow 沒有 run step 是合法的）。
  shopt -s nullglob
  fail=0; n_pass=0; n_rule=0; n_parse=0
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
    case "${want}" in
      pass)      n_pass=$((n_pass+1)) ;;
      rule-red)  n_rule=$((n_rule+1)) ;;
      parse-red) n_parse=$((n_parse+1)) ;;
    esac
  done
  # R24 regression F9：門檻寫成 `>=` 而實際值更高時，那個差額**沒有網**——刪掉一個 fixture 仍然綠。
  # 三個門檻一律改成**等於實測值**：要加 fixture 就同步改這裡，讓「少了一個」立刻紅。
  if [ "${n_pass}" -ne 161 ]; then
    echo "lint-ci-log-filter selftest FAILED: 正向 fixture 是 ${n_pass} 個，預期恰好 161（改動 fixture 請同步改這個數字）" >&2
    fail=1
  fi
  if [ "${n_rule}" -ne 219 ]; then
    echo "lint-ci-log-filter selftest FAILED: rule-red 是 ${n_rule} 個，預期恰好 219" >&2
    fail=1
  fi
  if [ "${fail}" -ne 0 ]; then exit 1; fi
  if [ "${n_parse}" -ne 121 ]; then
    echo "lint-ci-log-filter selftest FAILED: parse-red 是 ${n_parse} 個，預期恰好 121（先前這一類完全沒有下限）" >&2
    exit 1
  fi
  echo "lint-ci-log-filter selftest ok: ${n_pass} 正向通過、${n_rule} 條規則紅、${n_parse} 條解析紅（來源逐一比對相符）"
  exit 0
fi

# R16 DA-4：守備目標不寫死單檔——`.github/workflows/` 底下每一份 workflow 都檢查（新增第二份 workflow 不會漏）。
# `--require-run-steps` 是給 selftest 用的旗標（正式執行時純 `uses:` workflow 沒有 run step 是
# 合法的）。要在「檔案存在」檢查**之前**把它剝掉，否則它會被當成一個不存在的檔名。
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
python3 - "${flags[@]+"${flags[@]}"}" "${files[@]}" <<'PY'
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
# 一般字元也不算（`neutralise.pyc` 是另一個檔）。後者沒有 fixture：神諭的環境裡那個檔不存在、python3 什麼都不印，
# 神諭會把 lint 的 RULE 判成誤擋——這一格神諭在原理上量不了。`(` 那張已經殺得到「拿掉詞尾判定」的突變。
PIPED_RE = re.compile(r"[^|\s;&(]\s*\|(?!\|)&?\s*python3\s+[^\s;&|()<>`]*neutralise\.py(?=[\s;&|)<>`]|$)")
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")
# **fd 流向、`--strict` 的 `2>&1`、pipefail、shell 樣板**這四條規則不在這裡用正規式寫——它們讀的是 run 區塊的**結構**
# （詞、重導向、管線的每一段、群組、`case`），見 `shell_scan()` 之後的「規則層的詞法」一節（#33 verify R36 第 3、4、8、9、22 列）。
# R35 在這裡的五條正規式（`FD_RE`、`STRICT_NEUT_RE`、`PIPEFAIL_RE`、`ANY_PIPE_RE`、`BASH_SHELL_RE`＋`XTRACE_OPT_RE`）是拼法清單，
# R36 在每一條上都找到作者沒點名的相鄰輸入，所以整組換掉。
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
# 這裡補的是落到逐字元 fallthrough 的裸 `(`）、`!`、`{`。`)`／`}` 收尾**不**在這裡——收尾一個 subshell／group
# 之後不是自動的命令位置，要等下一個分隔字元。
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
    `probe.rstrip() == delim` 永遠不成立（`          EOF` 不等於 `EOF`）——**那個分支在任何真實
    `run: |` 裡都不可達**，heredoc 之後的真管線與真的 `# LOG-FILTER:` 一起被吞掉。
    DA 用合成的 base-綠語料量到：含 heredoc 的合規檔 17 個裡 **16 個被打紅**。
    順帶修好 `#` 詞首判定裡 `i == 0` 的語意——縮排剝掉後，行首才真的是行首。
    """
    # **「空行」的判準只算空白，tab 是內容**（#33 verify R37／R36 logic 第 10 列）。前一版用不帶參數的
    # `.strip()` 篩「非空行」——Python 的 `.strip()` 連 tab 一起當空白，於是一行「9 個空格 + 1 個 tab」
    # 被誤判成空行、排出 `body`，min() 就少算了它。YAML 的規則是**第一個非空行**（空行＝只含空白，而
    # 這裡的「空白」只算 SPACE）決定整段的縮排；那一行雖然總字元數比其他內容行少，只要它是**第一個**
    # 排進 body 的非空行，min() 自然會取到它（後面的內容行縮排不可能比它更淺，否則 YAML 解析器會把
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
# （RULE 誤擋）。`\|&` 放在 `\|\|?` 之前之後都一樣（regex 回溯會試到），這裡照抄其餘三個運算子的順序放最後。
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
            # `acc` 非 None ⇒ 它指向一個非空內容行（見下：只在 `not more` 為真時設定、空行段後歸 None），
            # 所以「`out[acc]` 非 None 且非空」是恆真的——R33 opsweep 對那兩個運算元各報存活，實測依構造多餘，刪掉。
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
                # 這一族）差一個字元就是有沒有終止的差別。R37 DA 用突變體（把這裡的 `.strip()` 拿掉）證明：
                # 拿掉之後 selftest 數字不變、且會讓原本放行的探針正確翻紅，`.strip()` 才是那個 bug。
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
    `\x01`（與 `\x7f`）是 bash 內部的引號跳脫字元，會被重複；`\c` 與解出這兩個字元的一律不猜。

    #33 verify R36（logic HIGH-3／R35 回歸）：`\x`、八進位、`\u`、`\U` 解出的**任何 ≥0x80 的值**一律 fail-closed。
    bash 對 `\x`／八進位產生的是單一**原始位元組**，不做任何 Unicode 解碼；Python 的 `chr(0xe9)` 卻是碼位
    U+00E9（一個字元），兩者在 UTF-8 檔案裡永遠不是同一行——`\377`、`\xe9`、兩個 `\x` 湊出的 `\xc3\xa9`
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
PARAM_UNPARSED = ("`${…}` 在同一行沒收尾（含裡面的引號、命令替換），或裡面有本 lint 不解析的構造："
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
    `$((…))`。**這不是 bash 的命令替換剖析**（#33 verify R36 第 7 列：logic HIGH-4、codex 第 1 條）——下列五種
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
# 命令起點：本行到目前為止的 code 以分隔字元（或行首）結尾，後面至多接幾個「後面還是命令」的保留字。
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
    **已知不涵蓋，第二組（這一組是封閉列舉，只有三條，不得依性質相似類推第四條；R32 抓到它們不在檔內）**：
      1. **stderr（預設模式）**：預設模式的 `PIPED_RE` 只要求管線存在，不要求 `2>&1`／`|&`（已知類別 S-2，範例
         `known-stderr-cmd-error-missing-2to1`）。**`--strict` 要求它**——CI 與 run.sh 對真 workflow 用 `--strict`，
         所以這一條只剩 fixture／產生語料（它們量的是詞法）。另：把輸出轉到 stderr 或開 xtrace 的寫法（`>&2`、
         `set -x`…）在**兩種模式**都是規則（R35；R33 的 S-2 範例用的正是 `>&2`，它不屬於這一條）。
         **`--strict` 的逐段 `2>&1` 只涵蓋命令執行時寫出的 stderr**（R37 合併時協調者發現，bash 5.3 實測）：在該段
         `2>&1` 生效**之前**就寫出的，兩種模式都看不到——(a) 展開期錯誤：`echo "${!PR_TITLE}" |& …` 印出
         「<原值>：無效的變數名稱」、`echo $(( PR_TITLE )) 2>&1 | …` 印出算術錯誤；(b) 寫在 `2>&1` 左邊的重導向本身出錯：
         `echo x > "$PR_TITLE" 2>&1 | …` 印出 `<原值>: No such file…`（`2>&1` 放左邊就走進管線）。命令執行時才產生的
         錯誤（`[[ $PR_TITLE -eq 1 ]] 2>&1 | …`）會走管線、被過濾。群組 `{ …; } 2>&1 |`／子殼層 `( … ) 2>&1 |` 的重導向
         在內部展開之前生效，兩種都涵蓋。本 lint 不為 (a)(b) 逐拼法列規則（那正是 R36 批評的形狀）；追蹤 #S2ISSUE。
         R34 更正：R33 這裡寫「repo 自己的 17 條管線全部已帶 `2>&1`／`|&`」——`--strict` 第一次跑就在 pack anchor
         那一步抓到一條 `… | tee | python3 …` 的最後一段沒帶（`tee` 的 stderr 沒有 PR 文字，但宣稱是假的）。
      2. **顆粒度**：一個 run 區塊裡**任一條**邏輯行接了管線，整個區塊就算已過濾（Codex 第 4 條）。
         `echo "$PR_TITLE"` ⏎ `echo safe | python3 …` 因此放行。這是宣告過的語意，不是漏洞的偽裝；
         但它從來沒寫在這份清單裡，現在寫了。要關它得改「什麼算已過濾」，那是另一次 change——追蹤 #59。
         同一條也涵蓋「管線不可達」：外流的行先執行、接管線的行因語法錯誤／`exit`／沒走到的分支不執行
         （R35 已把「引號開到區塊結尾」改成 fail-closed；R37 補齊同一族其餘未收尾構造——管線後面接
         `$(`、反引號、`; ((`、`; [[ -n x`、`$[`、`; (` 六種，以及掃描結束時 `csub`／`bt`／`arith`／`brk`／
         `cond`／未配對的裸 `(` 任一不為零，都比照辦理；另外「管線左邊沒有命令」（`true ;|& python3 …`、
         `true &&` 換行 `|& python3 …`——`;`／`&&` 之後直接是管線、bash 語法錯誤）不算接到 neutralise 的管線，
         `PIPED_RE` 排除 `;`／`&`／`(` 當左邊界，見該正規式旁的說明）。
      3. **多行分隔字**：`cat <<"A` ⏎ `B" | python3 …` 在 bash 是引號跨行、heredoc 永不終止但**管線照建**；
         本 lint 的分隔字是單行字串、表示不了它，一律 `PARSE:`（Codex 第 7 條，誤擋方向；產生語料的
         `d-delimword-unterm-*` 四檔由神諭歸「不可比（fail-closed）」）。
    **已知不涵蓋，第三組——預設模式的假設（封閉列舉，只有五條，不得依性質相似類推第六條；R35 新增前三條，
    R37 新增第 4、5 條）**：
      1. **shell 是 bash**：預設模式不讀 `shell:`／`defaults.run.shell`／container／runs-on，照 bash 的詞法判。
         `--strict`（CI 與 run.sh 對真 workflow 用的模式）驗這個假設：shell 必須是 bash（可帶選項、不得開 xtrace），
         container 或 Windows／運算式 runs-on 的 job 必須明寫 bash。R35 第一版在預設模式也套用，三軸量到合成 A
         語料 959 個 base-綠檔 290 個翻紅，所以移進 `--strict`。
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
         神諭列為 `KNOWN_DISAGREE`）。`--strict` 由「看得到管線、規則層剖析不出它」那條擋下
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
        # 一律正確。仍在 heredoc 內文（上面 `continue` 掉）或仍在 `arith`／`brk`／`cond`／`csub` 裡的字元
        # 不看這個旗標（那些分支在到得了 `[[`／`((` 判定之前就 `continue` 掉了）。
        cmd_pos = True
        after_compound = False               # 換行本身就是分隔字元：之後的保留字照一般命令位置處理
        quote0, prev0 = quote, prev_sig      # 邏輯行起點的狀態：摺疊後要從頭重掃
        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, tuple(dq_ret), tuple(map(tuple, cases)), bt_at, arith_cmd)
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
                    e = _backtick_end(line, i) if ch == "`" else _cmdsub_end_case(line, i)   # 雙引號裡：認得 case（合併 r37b×r37c）
                    if e is not None:
                        code.append(" " * (e - i)); i = e; prev_sig = "x"; continue
                    if line.startswith("$((", i):
                        unparsed = ("雙引號裡的算術 `$((…))` 本 lint 不解析：同一行沒收尾、裡面有引號／反引號／反斜線，"
                                    "或其實是 `$((…) …)` 形式的命令替換")
                        break
                    if ch == "`" and bt:
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
                    quote = None
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
                    bt_at, arith_cmd = lex0[9], lex0[10]
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
            # **保留字**（R37，#33 verify R36 第 5(a) 列）：`then`／`do`／`else`／`elif`／`if`／`while`／`until`
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
            # **`$(…)` 裡的 `case`**（#33 verify R36 第 7 列，logic HIGH-4 p12）：模式括號是單邊 `)`，只數括號的 `csub` 會提早
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
                dq_ret.pop(); quote = '"'
                cmd_pos = False          # 回到雙引號＝回到同一個詞的中間，不是命令位置（合併 r37c×r37d）
                code.append(ch); i += 1; prev_sig = ch; continue
            if ch == "#" and (prev_sig is None or prev_sig in SHELL_WORD_BREAK):
                # **反引號裡的註解止於收尾反引號**（#33 verify R37 合併時協調者發現）：bash 先照字面找收尾反引號
                # （反斜線逃脫下一個字元）、再把中間當指令剖析，所以 `echo a `# x` b` 印 `a b`。前一版一律吃到行尾：
                # 收尾反引號之後的程式碼跟著消失、`bt` 留在 True——d 包的區塊結尾檢查因此把合法的 bash 判 PARSE
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
                        # ——fail-closed 走 PARSE，與「引號沒收尾」同一條出口（R33，opsweep 對前一版整段消費的
                        # 十個運算元報存活，而它們守的東西根本追不到 bash）。
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
    if quote is not None:              # `and not unparsed` 只決定訊息寫哪個原因、判定都是 PARSE（opsweep 報存活，刪掉）
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
# 前一版的 fd 流向、`--strict` 的 `2>&1`、pipefail 三條規則都是**對挖空後的程式碼搜正規式**：`FD_RE` 是一份拼法清單
# （`>&2`、`>/dev/stderr`、`set -x`…），`--strict` 的 `2>&1` 比 `PIPED_RE` 與 `STRICT_NEUT_RE` 的**總數**，pipefail 用
# `ANY_PIPE_RE` 找「第一個 `|`」、用 `BASH_SHELL_RE` 把「shell 是 bash」當成「有 pipefail」。R36 在每一條上都找到作者沒點名
# 的相鄰輸入：引號包住的目標 `>"/dev/stderr"`（挖空之後字面清單看不到）、`/dev/fd/2`、`>&02`、`>&"2"`、另存的 fd、
# `set -eo xtrace`、`shopt -so xtrace`、從 `env:` 帶進的 SHELLOPTS；前段管線的 stderr、子殼層湊數、黏在詞上的 `"$X"2>&1`；
# `bash -e {0}`／`bash -l {0}` 沒有 pipefail；`case … in a|b)` 的模式 `|` 被當成管線；規則還擋掉它自己推薦的群組寫法。
# 修法是改成**按結構與流向**判：把 `shell_scan()` 的程式碼半邊對回原文（`_aligned_sources`），切成詞與運算子（`_lex`），
# 剖析成管線／群組／簡單命令（`_Sh`）。三條規則讀同一份結構：
#   · fd 流向：fd 複製（`2>&1` 與 no-op 的 `>&1` 除外）、去引號後落在 `/dev`、`/proc` 底下的寫檔目標（`_SAFE_TARGETS` 除外）、
#     開 xtrace／verbose 的命令、run 裡設定 SHELLOPTS 等變數——都算外流，除非它位在「收尾後緊接 `2>&1 |`（或 `|&`）進
#     neutralise 的群組」裡：那個群組是管線的一段、在子殼層裡跑，fd 1 與 fd 2 都是管線。
#   · `--strict` 的 `2>&1`：每一條接 neutralise 的管線，neutralise 之前的**每一段**都要讓 fd 2 併進管線（那一段最後一個動到
#     fd 2 的重導向是 `2>&1`，或接下一段的運算子是 `|&`）。
#   · pipefail：照詞元順序模擬——起始值由 shell 樣板決定（`_bash_template`），頂層的 `set ±o pipefail`／`shopt -s|-uo pipefail`
#     改變它，每一個管線運算子出現時它必須是開的。
# **已知不涵蓋（這一節的，封閉列舉，只有四條，不得依性質相似類推第五條）**：
#   1. 重導向目標含參數展開或命令替換（`> "$GITHUB_OUTPUT"`、`> "$X"`）時不求值——`$GITHUB_OUTPUT` 這類是 Actions 的日常寫法；
#      只有目標的**字面部分**已經落在 `/dev`、`/proc` 底下（`>/dev/fd/$N`）才擋。
#   2. `eval`／`bash -c`／`trap` 的**字串**不剖析（同 `shell_scan` 第一組：本 lint 不求值）；`eval` 後面全是字面詞時例外——
#      那時 bash 執行的就是那幾個詞（`eval set -x`）。
#   3. `if`／`while`／`for` 不建結構、當成一般的詞，所以判定不看可達性：沒走到的分支裡的 `set -o pipefail` 也算數。
#   4. 未引號 heredoc 的**內文**裡的命令替換（bash 會展開、執行它）不剖析：掃描器把內文整行當資料、規則層收不到那些行。
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
_RUN_ENV_KEYS = ("SHELLOPTS", "BASHOPTS", "BASH_ENV", "BASH_XTRACEFD")
_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")
_LEAD_WORDS = frozenset(("!", "time", "if", "then", "else", "elif", "do", "while", "until", "builtin", "command"))


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
    """`${` 之後（k 指向內容開頭）配對的 `}` 之後的位置；只用來跳過挖空段，結果一律再經 `_clamp`。"""
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
    （#33 verify R36 第 6 列，工作包 c 修），程式碼給的引號位置可能落在命令替換中間。已經剖析過的區段不重做（`_COVERED`）。"""
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
    r"""從 p 讀一個詞 → {code, lit, skel, glob, subs, bad_sub, s, e}。lit＝去引號後的字面（含展開、或看不到原文，就是 None）；
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
            "skel": "".join(skel) if known else None, "glob": glob, "subs": subs, "bad_sub": bad_sub, "s": st, "e": p}


def _opaque(C, p, e, subs=(), bad_sub=False):
    return {"k": "W", "code": C[p:e], "lit": None, "skel": None, "glob": False, "subs": list(subs), "bad_sub": bad_sub,
            "s": p, "e": e}


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


def _touches_fd2(r):
    """這個重導向會不會改掉 fd 2 指向哪裡（`2>…`、`&>…`、`>&檔名`）。"""
    if r["pre"] == "2" or r["op"] in ("&>", "&>>"):
        return True
    if r["op"] == ">&" and r["pre"] == "":
        tl = r["t"]["lit"] if r["t"] is not None else None
        return tl is None or not (tl.isdigit() or tl == "-")
    return False


def _fd2_to_pipe(rs):
    """一段的重導向依序套用完，fd 2 是不是併進了管線：最後一個動到 fd 2 的重導向是 `2>&1`。"""
    ok = False
    for r in rs:
        if _is_2to1(r):
            ok = True
        elif _touches_fd2(r):
            ok = False
    return ok


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
    if t["lit"] is not None and (posixpath.normpath(t["lit"]) in _SAFE_TARGETS
                                 or re.match(r"/dev/(tcp|udp)/", posixpath.normpath(t["lit"]))):
        return None                                      # `/dev/tcp/host/port`：bash 的網路 socket，不是 log（野外語料 3 處）
    if {"dev", "proc"} & set(posixpath.normpath(sk).split("/")):
        return "`%s` 寫到 /dev 或 /proc 底下（去引號後是 `%s`）" % (
            shown, t["lit"] if t["lit"] is not None else sk.replace("\0", "$…"))
    return None


class _Sh:
    """把 `_lex` 的詞元剖析成管線／群組／簡單命令，收集三條規則要讀的東西。

    不是完整的 bash 剖析器：`if`／`while`／`for` 當成一般的詞（它們不改變 fd 與管線的結構）；有自己結構的只有
    群組 `{ …; }`／`( … )`、`case`（模式裡的 `|` 是「或」、不是管線——R36 第 22 列）、函式定義、命令替換與
    process substitution。收集到 `out`：groups（每個群組是否豁免）、hits（（說明, 所在群組的堆疊））、
    events（pipefail 的模擬序列）、pipelines（（各段, 段與段之間的運算子））。"""

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

    def hit(self, why, ctx):
        self.o["hits"].append((why, ctx["stack"]))

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
        ev0, segs, conns = len(self.o["events"]), [], []
        while self.word(self.tok(), "!", "time"):
            self.i += 1
        seg = self.parse_command(ctx, end)
        while seg is not None:
            segs.append(seg)
            if not self.op(self.tok(), "|", "|&"):
                break
            conns.append(self.tok()["op"])
            self.o["events"].append({"k": "pipe"})
            self.i += 1
            self.skip_nl()
            seg = self.parse_command(ctx, end)
        if len(segs) > 1:                        # 管線的每一段都在子殼層：裡面的 `set -o pipefail` 不作用在外面
            for ev in self.o["events"][ev0:]:
                ev["sub"] = True
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
            self.parse_list(dict(ctx, stack=ctx["stack"] + (gid,), sub=True), lambda x: self.op(x, ")"))
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
        if self.word(t, "function"):             # `function f { …; }`：本體要呼叫才執行——子脈絡
            self.i += 1
            if self.tok() is not None and self.tok()["k"] == "W":
                self.i += 1
            if self.op(self.tok(), "(") and self.op(self.tok(1), ")"):
                self.i += 2
            self.skip_nl()
            self.parse_command(dict(ctx, sub=True), end)
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
                self.i += 2                      # `f() …`：本體要呼叫才執行——子脈絡
                self.skip_nl()
                self.parse_command(dict(ctx, sub=True), end)
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
            self.hit(why, ctx)
        if r["t"] is not None:
            self.subs(r["t"], ctx)

    def subs(self, w, ctx):
        if w.get("bad_sub"):
            self.hit("引號或 `${…}` 裡的命令替換對不到收尾（或掃描器不解析它）——裡面的重導向看不到，不解析就不放行", ctx)
        for sub in w["subs"]:                    # 命令替換、process substitution：子殼層，fd 繼承自所在的位置
            _Sh(sub, self.o).parse_list(dict(ctx, sub=True), lambda x: False)

    def simple(self, words, ctx):
        k = 0
        while k < len(words):                    # 前綴：變數指派（`X=1 cmd`）與不改變命令名的保留字
            w = words[k]
            if _ASSIGN_RE.match(w["skel"] if w["skel"] is not None else w["code"]):
                self.env_word(w, ctx, bare=False)
            elif w["code"] not in _LEAD_WORDS:
                break
            k += 1
        if k >= len(words):
            return
        name = words[k]["lit"] if words[k]["lit"] is not None else words[k]["code"]
        args = words[k + 1:]
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

    def env_word(self, w, ctx, bare):
        text = w["skel"] if w["skel"] is not None else w["code"]
        for key in _RUN_ENV_KEYS:
            if text.startswith((key + "=", key + "+=")) or (bare and text == key):
                self.hit("run 裡設定 `%s`——bash（含子行程）啟動時會讀它、可以開 xtrace 或執行別的程式碼" % key, ctx)

    def pf_event(self, on, ctx):
        self.o["events"].append({"k": "pf", "on": on, "sub": ctx["sub"]})

    def set_cmd(self, args, ctx):
        i = 0
        while i < len(args):
            a = args[i]["lit"]
            if a is None:
                self.hit("`set` 的參數不是字面（`set -$X`…）——開了什麼看不出來", ctx)
                self.pf_event(False, ctx)
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
                        self.pf_event(False, ctx)
                    elif on and nm in _TRACE_OPTS:
                        self.hit("`set %s %s` 開了 %s" % (a, nm, nm), ctx)
                    elif nm == "pipefail":
                        self.pf_event(on, ctx)
                elif on and ch in "xv":
                    self.hit("`set %s` 開了 %s" % (a, "xtrace" if ch == "x" else "verbose"), ctx)

    def shopt_cmd(self, args, ctx):
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
        for w in args[i:]:
            nm = w["lit"]
            if nm is None:
                self.hit("`shopt -o` 的選項名不是字面——開了什麼看不出來", ctx)
            elif "s" in flags and nm in _TRACE_OPTS:
                self.hit("`shopt -%s %s` 開了 %s" % (flags, nm, nm), ctx)
            elif nm == "pipefail" and ("s" in flags or "u" in flags):
                self.pf_event("s" in flags, ctx)

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
                        self.hit("子 shell 的 `%so %s` 開了 trace" % (a, nm or "…"), ctx)
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
    """一個 step 的邏輯行（程式碼與對齊的原文）→ {fd: 外流說明, bad_segs: `--strict` 缺 `2>&1` 的段號,
    n_neut: 接 neutralise 的管線條數, events: pipefail 的模擬序列}。"""
    C = "\n".join(logical)
    S = "\n".join(s if s is not None else "\0" * len(c) for c, s in zip(logical, logical_src))
    _COVERED.clear()
    toks, _ = _lex(C, S)
    out = {"groups": [], "hits": [], "events": [], "pipelines": []}
    _Sh(toks, out).parse_list({"stack": (), "sub": False}, lambda t: False)
    bad_segs, n_neut = [], 0
    for segs, conns in out["pipelines"]:
        last = max((k for k, sg in enumerate(segs) if sg["neut"]), default=0)
        if not last:
            continue
        n_neut += 1
        for k in range(last):
            if conns[k] != "|&" and not _fd2_to_pipe(segs[k]["trail"]):
                bad_segs.append(k + 1)
            # 群組豁免（R36 第 9 列）：收尾後緊接 `2>&1 |`（或 `|&`）進 neutralise——群組裡的 fd 1、fd 2 都是管線
            if segs[k]["kind"] == "group" and (
                    (conns[k] == "|&" and not segs[k]["trail"])
                    or (conns[k] == "|" and len(segs[k]["trail"]) == 1 and _is_2to1(segs[k]["trail"][0]))):
                out["groups"][segs[k]["gid"]] = True
    fd = [why for why, stack in out["hits"] if not any(out["groups"][g] for g in stack)]
    return {"fd": fd, "bad_segs": bad_segs, "n_neut": n_neut, "events": out["events"]}


def _pipefail_holds(events, on):
    """照詞元順序模擬 pipefail：頂層（不在子殼層、命令替換、函式本體、管線的一段裡）的設定才改變它；
    每一個管線運算子出現時它都要是開的。非字面的 `set` 參數當成關掉（fail-closed）。"""
    for ev in events:
        if ev["k"] == "pf" and not ev.get("sub"):
            on = ev["on"]
        elif ev["k"] == "pipe" and not on:
            return False
    return True


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


REQUIRE_RUN_STEPS = "--require-run-steps" in sys.argv
# **`--strict`**（#33 verify R35；R37 按 R36 第 3、4、13 列改寫）：CI 與 run.sh 對**真的 workflow** 用這個模式。
# 比預設模式多四條（封閉列舉，只有這四條）：
#   (1) 有管線的 step 必須跑在 pipefail 之下：shell 是**關鍵字** `bash`、或樣板自帶 `-o pipefail`，或 run 裡在管線之前、
#       頂層地 `set -o pipefail`（之後不得再關掉）——R33 的形狀普查 step 缺它，閘門在 CI 上結構上紅不了（R34 security S-1／
#       regression H-3／requirements F1）；R36 第 4 列：`bash -e {0}`、`bash -l {0}` 這類樣板**沒有** pipefail。
#   (2) 接 neutralise 的管線，neutralise 之前的**每一段**都要把 stderr 併進管線（`2>&1` 收尾、`|&`，或整段包成
#       `{ …; } 2>&1 |`）——已知類別 S-2 在這個模式下是規則（R34 requirements F4；R36 第 3 列：前一版比總數）。
#   (3) shell 只能是 bash 樣板（不得開 xtrace／verbose）；container 或 Windows／運算式 runs-on 的 job 必須明寫 shell
#       （R35 從預設模式移過來：預設模式假設 shell 是 bash，見 `shell_scan` 已知不涵蓋第三組第 1 條）。
#   (4) workflow 根層級 `defaults.run` 寫成 flow 形式 ⇒ PARSE（R36 第 13 列：讀不到 shell）。
# 預設模式不要求這四條：fixture 與產生語料量的是**詞法**，不是 CI 的寫法規範；改寫兩百個 fixture 的管線只會讓
# 每一個詞法形狀多一個與它無關的變數。fd 流向與 env 那兩條（見規則層的詞法一節）兩種模式都套用。
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
        """去掉 YAML 行尾註解、**保留引號內容**。`yaml_split_comment()` 的程式碼半邊是引號挖空的，只能拿它的註解半邊找起點
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
        return [k_ for _l, _i, k_ in _kids(l0, _end(l0, ind0), ind0)]

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
            # 找到註解起點（yaml_split_comment 只回挖空後的文字，所以用註解長度切原文），再解碼
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
        # **邏輯行**：只有前一行以 `|`／`||`／`&&` 結尾時才接續下一行——那才是 bash 會把兩行當成同一條
        # 命令的情形。前一版把整個區塊用空白接成一串再比對（`run_joined`），於是 literal 區塊裡
        # `echo "$PR_TITLE"` ⏎ `| python3 …neutralise.py` 被接成一條假管線而放行，
        # 而 bash 對行首的 `|` 報的是**語法錯誤**（R30 H-6：兩條路各自獨立足以放行，
        # 所以只收緊 `PIPED_RE` 修不好——要改的是「什麼叫一條命令」）。
        logical = []
        for c in run_code:
            cs = c.strip()
            if logical and CONT_RE.search(logical[-1]):
                logical[-1] = logical[-1] + " " + cs
            elif cs:
                logical.append(cs)
        rl_code, rl_src = _rule_lines(run_code, scan_in)     # 規則層的邏輯行：程式碼＋對齊的原文（R37，見 `_rule_lines`）
        via_pipe = any(PIPED_RE.search(l) for l in logical)
        declared = any(LOGFILTER_RE.match(l) for l in decl_lines)
        ok = via_pipe or declared
        try:
            an = _analyse(rl_code, rl_src)
        except (IndexError, KeyError, ValueError, RecursionError) as e:   # 剖析器自己的錯：fail-closed，不讓 traceback 蓋掉其他檔
            reject(r, "規則層剖析這個 run 區塊時出錯（%s: %s）——不解析就不放行" % (type(e).__name__, e))
            continue
        # env 帶進的 shell 設定（R36 第 8 列）：workflow／job（含 container.env）／step 三層；`?` ＝值是運算式、鍵名看不到
        env_names = wf_env + (job["env"] if job else []) + (
            _env_names(s["keys"]["env"], s["kindent"]) if "env" in s["keys"] else [])
        env_hit = [k for k in env_names if k in ENV_TRACE_KEYS or k == "?"]
        where = "%s:%d: RULE: " % (path, s["start"] + 1)
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
            print(where + "step '%s' 靠管線過濾，而 env（workflow／job／step）帶了 %s——bash 啟動時就讀它們：可以開 xtrace、"
                  "或在 run 之前執行別的程式碼，那些輸出不經過管線" % (s["name"], "、".join(
                      "`%s`" % k if k != "?" else "看不到鍵名的運算式" for k in env_hit)), file=sys.stderr)
            rc = 1
        elif STRICT and not declared and not an["n_neut"]:
            print(where + "[--strict] step '%s' 看得到接 neutralise.py 的管線，本 lint 卻剖析不出它的結構——不解析就不放行"
                  % s["name"], file=sys.stderr)
            rc = 1
        elif STRICT and not declared and an["bad_segs"]:
            # **逐條管線、每一段**（R36 第 3 列）：前一版比 `PIPED_RE` 與 `STRICT_NEUT_RE` 的總數，於是前段的 stderr
            # （`cat "$PR_TITLE" | grep x 2>&1 | …`）、子殼層湊數、黏在詞上的 `"$X"2>&1` 都放行。
            print(where + "[--strict] step '%s' 接 neutralise.py 的管線，第 %s 段沒有把 stderr 併進管線（該段要以 `2>&1` 收尾、"
                  "或用 `|&` 接下一段，或把前面整段包成 `{ …; } 2>&1 |`）——PR 文字會從那一段的 stderr 繞過"
                  % (s["name"], "、".join(str(k) for k in an["bad_segs"])), file=sys.stderr)
            rc = 1
        if STRICT and not _pipefail_holds(an["events"], tmpl["pipefail"] if tmpl is not None else False):
            # R36 第 4、22 列：起始值由樣板決定（只有關鍵字 `bash` 或樣板自帶 `-o pipefail`），頂層的 `set ±o pipefail` 依序改變它；
            # 管線運算子是剖析出來的（`case … in a|b)` 的模式 `|` 不是管線）。
            print(where + "[--strict] step '%s' 有管線，卻沒有跑在 pipefail 之下（shell 不是關鍵字 `bash`、樣板也沒帶 `-o pipefail`，"
                  "run 裡也沒在管線之前、頂層地 `set -o pipefail`——或之後又關掉了）——GitHub 預設 `bash -e {0}`，"
                  "管線前段的失敗會被後段的 rc 蓋掉" % s["name"], file=sys.stderr)
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
