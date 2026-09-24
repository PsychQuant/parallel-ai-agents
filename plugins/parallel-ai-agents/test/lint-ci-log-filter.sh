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
# 用法：test/lint-ci-log-filter.sh [workflow.yml…]   預設 ../../.github/workflows/*.yml *.yaml（全部 workflow）
#       test/lint-ci-log-filter.sh --selftest
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
  if [ "${n_pass}" -ne 108 ]; then
    echo "lint-ci-log-filter selftest FAILED: 正向 fixture 是 ${n_pass} 個，預期恰好 108（改動 fixture 請同步改這個數字）" >&2
    fail=1
  fi
  if [ "${n_rule}" -ne 98 ]; then
    echo "lint-ci-log-filter selftest FAILED: rule-red 是 ${n_rule} 個，預期恰好 98" >&2
    fail=1
  fi
  if [ "${fail}" -ne 0 ]; then exit 1; fi
  if [ "${n_parse}" -ne 62 ]; then
    echo "lint-ci-log-filter selftest FAILED: parse-red 是 ${n_parse} 個，預期恰好 62（先前這一類完全沒有下限）" >&2
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
PIPED_RE = re.compile(r"[^|\s]\s*\|(?!\|)&?\s*python3\s+\S*neutralise\.py(\s|$)")
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")
# **fd 流向**（#33 verify R34 security S-2／logic F5／DA G-B）：把 stdout 轉到 stderr（`>&2`、`1>&2`、`>/dev/stderr`）
# 或開 xtrace（`set -x`、`set -o xtrace`、`bash -x`）都讓 PR 文字繞過只接 stdout 的管線——而且**帶了 `2>&1` 也一樣**：
# `>&2 2>&1 |` 的 `>&2` 先把 fd1 指到原本的 stderr；xtrace 在命令自己的 `2>&1` 套用之前就印到 shell 的 fd2。
# 只對「靠管線過濾」的 step 適用；`# LOG-FILTER:` 明示不過濾的 step 不受限（它已經聲明不印 PR 文字）。
FD_RE = re.compile(r">&\s*2\b|>\s*/dev/stderr|\bset\b[^;&|]*\s-[A-Za-z]*x|\bset\b[^;&|]*-o\s+xtrace\b|\bbash\s+-[A-Za-z]*x")
STRICT_NEUT_RE = re.compile(r"(2>&1\s*\||\|&)\s*python3\s+\S*neutralise\.py")
PIPEFAIL_RE = re.compile(r"\bset\b[^;&|]*-[A-Za-z]*o\s+pipefail\b")
ANY_PIPE_RE = re.compile(r"(?<!\|)\|(?!\|)")
# `--strict` 接受的 shell：`bash`，可帶 GitHub 模板的 `{0}` 與選項（`bash -euo pipefail {0}`、`bash --noprofile --norc -e {0}`）；
# 選項裡有 xtrace（`-x`、`-xeuo`、`-o xtrace`）另外拒絕。`bash -l {0}`（login shell）也是 bash。
BASH_SHELL_RE = re.compile(r"^bash(?:\s+(?:--[a-z-]+|[-+][A-Za-z]*o\s+[a-z]+|-[A-Za-z]+|\+[A-Za-z]+))*(?:\s+\{0\})?$")
XTRACE_OPT_RE = re.compile(r"(?:^|\s)-[A-Za-z]*x|-o\s+xtrace")


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
    body = [l for l in lines[1:] if l.strip()]
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


CONT_RE = re.compile(r"(\|\|?|&&)\s*$")     # 邏輯行的續行運算子：`|`／`||`／`&&`


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
            # `acc` 非 None ⇒ 它指向一個非空內容行（見下：只在 `l.strip()` 為真時設定、空行段後歸 None），
            # 所以「`out[acc]` 非 None 且非空」是恆真的——R33 opsweep 對那兩個運算元各報存活，實測依構造多餘，刪掉。
            if acc is not None and not more and not prev_more:
                out[acc] = out[acc] + " " + l.strip()
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
            out.append(chr(int(m, 8) & 0xFF)); i += 1 + len(m); continue
        if d in "xuU":
            m = re.match(r"[0-9A-Fa-f]{1,%d}" % {"x": 2, "u": 4, "U": 8}[d], s[i + 2:])
            if m:
                out.append(chr(int(m.group(), 16))); i += 2 + len(m.group()); continue
        if d == "c":
            return None
        out.append("\\" + d); i += 2
    r = "".join(out)
    return None if ("\x01" in r or "\x7f" in r) else r


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


def _cmdsub_end(line, j):
    """`$(…)` 的配對：從 `$(` 到收尾 `)` 之後的位置；同一行沒收尾回 None。

    括號計深度，略過引號、逃脫、巢狀的 `${…}`／反引號。已知不涵蓋：`case … in a)` 的模式括號（單邊 `)`）
    會讓深度提早歸零——那一種出現在 `${…}` 裡的命令替換中的機率是零，而它的後果是 fail-closed 的方向
    （展開提早「結束」、後面的 `}` 由 `_param_end` 繼續找）。"""
    k, n, depth = j + 2, len(line), 1
    while k < n:
        c = line[k]
        if c == "\\":
            k += 2; continue
        if c == "'":
            e = line.find("'", k + 1)
            if e < 0:
                return None
            k = e + 1; continue
        if c == '"':
            k += 1
            while k < n and line[k] != '"':
                k += 2 if line[k] == "\\" else 1
            if k >= n:
                return None
            k += 1; continue
        if c == "`":
            e = _backtick_end(line, k)
            if e is None:
                return None
            k = e; continue
        if line.startswith("${", k):
            e = _param_end(line, k)
            if e is None:
                return None
            k = e; continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if not depth:
                return k + 1
        k += 1
    return None


def _param_end(line, i):
    r"""`${…}` 的配對剖析：回傳展開結束之後的位置；本 lint 不解析的構造回 `None`（呼叫端 fail-closed）。

    #33 verify R34 logic F1：前一版只認 `${`、`}`、逃脫與單雙引號，於是五種構造讓它在 bash 還沒結束展開的地方
    就宣告結束：反引號（`` `}` ``）、`$(…)`（`$(: })`）、`$'…'`（`\'` 是逃脫不是收尾）、雙引號裡的 `${`
    （雙引號分支根本不進來）、跨行。現在照 bash 的配對規則做：引號、`$'…'`、巢狀 `${`、`$(…)`（`_cmdsub_end`）、
    反引號（`_backtick_end`）——雙引號裡的也一樣。**同一行沒收尾一律回 `None`**（跨行的 `${…}` 是已知不涵蓋
    第三組第 2 條）。R35 第一版對 `${…}` 裡的命令替換與 `$[` 也一律回 `None`；三軸量到常見寫法 `${X:-$(cmd)}`
    因此翻紅，改成配對；`$[…]` 裡不可能出現 `}`，當普通字元處理與特判等價，opsweep 報那兩個分支存活，刪掉。
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
            k = j + 1
            while k < n and line[k] != '"':
                if line[k] == "\\":
                    k += 2; continue
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
            if k >= n:
                return None
            j = k + 1; continue
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
         R34 更正：R33 這裡寫「repo 自己的 17 條管線全部已帶 `2>&1`／`|&`」——`--strict` 第一次跑就在 pack anchor
         那一步抓到一條 `… | tee | python3 …` 的最後一段沒帶（`tee` 的 stderr 沒有 PR 文字，但宣稱是假的）。
      2. **顆粒度**：一個 run 區塊裡**任一條**邏輯行接了管線，整個區塊就算已過濾（Codex 第 4 條）。
         `echo "$PR_TITLE"` ⏎ `echo safe | python3 …` 因此放行。這是宣告過的語意，不是漏洞的偽裝；
         但它從來沒寫在這份清單裡，現在寫了。要關它得改「什麼算已過濾」，那是另一次 change——追蹤 #59。
         同一條也涵蓋「管線不可達」：外流的行先執行、接管線的行因語法錯誤／`exit`／沒走到的分支不執行
         （R35 已把其中「引號開到區塊結尾」改成 fail-closed）。
      3. **多行分隔字**：`cat <<"A` ⏎ `B" | python3 …` 在 bash 是引號跨行、heredoc 永不終止但**管線照建**；
         本 lint 的分隔字是單行字串、表示不了它，一律 `PARSE:`（Codex 第 7 條，誤擋方向；產生語料的
         `d-delimword-unterm-*` 四檔由神諭歸「不可比（fail-closed）」）。
    **已知不涵蓋，第三組——預設模式的假設（封閉列舉，只有三條，不得依性質相似類推第四條；R35 新增）**：
      1. **shell 是 bash**：預設模式不讀 `shell:`／`defaults.run.shell`／container／runs-on，照 bash 的詞法判。
         `--strict`（CI 與 run.sh 對真 workflow 用的模式）驗這個假設：shell 必須是 bash（可帶選項、不得開 xtrace），
         container 或 Windows／運算式 runs-on 的 job 必須明寫 bash。R35 第一版在預設模式也套用，三軸量到合成 A
         語料 959 個 base-綠檔 290 個翻紅，所以移進 `--strict`。
      2. **跨行的 `${…}`**（含雙引號裡的）：本 lint 的 `${…}` 配對不跨行 ⇒ fail-closed `PARSE:`（誤擋方向；
         合成 A 語料 1 檔：`"${X:+$X` ⏎ `…}"`）。
      3. **`$(…)` 裡 `case … in a)` 的單邊 `)`**：`${…}` 裡的命令替換用括號計深度配對，模式括號會讓深度提早歸零。
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
    # 條件式 `[[`、命令替換 `$(` 與反引號、雙引號裡是否出現過命令替換。前一版的算術深度每一行歸零，
    # 於是跨行的 `$((1` ⏎ `<<2 ))` 第二行的左移被當成 heredoc。
    arith = arith_par = brk = csub = cpar = 0
    cond = bt = dq_sub = dq_resume = False
    quote = None            # None / "'" / '"'
    heredoc = None          # (delimiter, strip_tabs, quoted, 開在命令替換裡)
    body_continued = False  # 未引號 heredoc 內文的前一行以奇數個反斜線結尾（R28 D3）
    pending = []            # 這一行結束後依序要讀的 heredoc（FIFO）
    prev_sig = None         # 前一個「有意義」字元（跨行保留，供 `#` 詞首判定）
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
        quote0, prev0 = quote, prev_sig      # 邏輯行起點的狀態：摺疊後要從頭重掃
        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, dq_sub)
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
                        unparsed = "`${…}` 裡有本 lint 不解析的構造（命令替換／舊式算術），或同一行沒收尾"
                        break
                    code.append(" " * (e - i)); i = e; prev_sig = "x"; continue
                if ch == "`" or line.startswith("$(", i):
                    dq_sub = True
                if dq_sub and line.startswith("<<", i) and not line.startswith("<<<", i):
                    # **雙引號裡的命令替換開 heredoc**（`X="$(cat <<EOF` ⏎ … ⏎ `EOF` ⏎ `)"`）：bash 照樣讀 heredoc 內文，
                    # 讀完回到雙引號。前一版這個分支把整段挖空、不登記 heredoc，內文裡的 `"` 讓引號狀態與 bash 分岔
                    # （`bypass-heredoc-in-dq-cmdsubst`）；R35 第一版改成 fail-closed，三軸量到合成 A 語料 8 個合法檔翻紅。
                    # 現在照 bash 做：暫時離開雙引號、交給下面的 `<<` 分支登記 heredoc，登記完回到雙引號。
                    quote = None; dq_resume = True        # 不在這裡消費：落到下面的 `<<` 分支
                else:
                    code.append('"' if ch == '"' else " ")
                    if ch == '"':
                        quote = None; dq_sub = False
                    i += 1; prev_sig = ch; continue
            if ch == "\\":
                if i + 1 < n:
                    code.append("  "); i += 2
                    prev_sig = "x"          # 被逃脫的字元一律當成「非空白」——`a\ #` 的 `#` 不起註解
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
                    arith, arith_par, brk, csub, cpar, cond, bt, dq_sub = lex0
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
                code.append(" " * (j + 1 - i)); i = j + 1; prev_sig = "x"; continue
            # R30 H-3：`${VAR#pattern}` 裡的 `#` 不起註解、`|` 不是管線——整個 `${…}` 是**一個詞的一部分**。
            # 前一版逐字元掃，於是 `echo ${PR_TITLE#| python3 …neutralise.py }` 一行就放行。
            # 與 `((` 一樣**整段消費**：找到配對的 `}`（計深度），中間一律不解讀。
            if line.startswith("${", i):
                # **只有巢狀的 `${` 會加一層**——單獨的 `{` 不會（R31 自查）；**只有未引號、未逃脫的 `}` 才結束展開**
                # （R32 security S-1／Codex 第 2 條／DA-1）；**反引號、`$(`、`$'…'`、跨行**（R34 logic F1）——
                # 配對規則全部在 `_param_end()`，不解析的構造 fail-closed。
                e = _param_end(line, i)
                if e is None:
                    unparsed = "`${…}` 裡有本 lint 不解析的構造（命令替換／舊式算術），或同一行沒收尾"
                    break
                code.append(" " * (e - i)); i = e; prev_sig = "x"; continue
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
                        arith -= 1; code.append("))"); i += 2; prev_sig = ")"; continue
                    # （算術裡的 `((` 只是兩個括號，由上面的單括號計數處理。R35 第一版另寫了一個巢狀 `((` 分支，
                    # 排在 `ch == "("` 之後、永遠走不到——opsweep 報存活，刪掉；`good-arith-double-paren` 守住。）
                elif brk:
                    if ch == "[":
                        brk += 1
                    elif ch == "]":
                        brk -= 1
                elif line.startswith("]]", i) and line[i - 1:i] in (" ", "\t"):
                    cond = False; code.append("]]"); i += 2; prev_sig = "]"; continue
                code.append(" "); i += 1; prev_sig = "x"; continue
            if ch in ("'", '"'):
                quote = ch; code.append(ch); i += 1; prev_sig = ch; continue
            if line.startswith("$[", i):
                brk = 1; code.append("  "); i += 2; prev_sig = "x"; continue
            if (line.startswith("[[", i) and line[i + 2:i + 3] in (" ", "\t", "")
                    and (prev_sig is None or prev_sig in SHELL_WORD_BREAK)):
                cond = True; code.append("[["); i += 2; prev_sig = "["; continue
            if line.startswith("$(", i) and not line.startswith("$((", i):
                csub += 1; code.append("$("); i += 2; prev_sig = "("; continue
            if ch == "(" and csub and not line.startswith("((", i):   # `((` 是算術，下面另外處理
                cpar += 1
            elif ch == ")" and cpar:
                cpar -= 1
            elif ch == ")" and csub:
                csub -= 1
            elif ch == "`":
                bt = not bt
            if ch == "#" and (prev_sig is None or prev_sig in SHELL_WORD_BREAK):
                decls.append(line[i:]); break
            # R28 D1（logic／requirements／Codex 第 3 條）：前一版 `$((` 在 `$` 處與第一個 `(` 處各命中一次、
            # `))` 只減一次，每個 `$(( … ))` 之後 arith 卡在 1，同一行後面的真 heredoc 過不了守衛。
            # **不能只刪 `$((`**（DA 實測 `$(((1+2)*3))` 仍卡）——要**整段消費**：命中就把 token 整個吃掉。
            # `$((` 不另開分支：`$` 在這支掃描器裡沒有特殊意義，`$((` 就是 `$` 接 `((`，由下一行處理
            # （R29 mutation：獨立的 `$((` 分支關掉後 selftest 仍綠——依構造等價，所以刪掉而不是列入
            # EXPECTED_SURVIVE）。
            if line.startswith("((", i):
                arith += 1; code.append("(("); i += 2; prev_sig = "("; continue
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
                    pending.append((delim, strip_tabs, quoted, bool(csub or bt or dq_resume)))
                if dq_resume:
                    quote, dq_resume = '"', False       # 回到雙引號（見雙引號分支）
                code.append("<<"); i = j; prev_sig = "<"; continue
            code.append(ch); i += 1
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
    return code_lines, decls, unparsed


REQUIRE_RUN_STEPS = "--require-run-steps" in sys.argv
# **`--strict`**（#33 verify R35）：CI 與 run.sh 對**真的 workflow** 用這個模式。多兩條規則：
#   (1) 有管線的 step 必須跑在 pipefail 之下（`shell: bash`／defaults 是 bash／run 裡先 `set -o pipefail`）——
#       R33 的形狀普查 step 缺它，閘門在 CI 上結構上紅不了（R34 security S-1／regression H-3／requirements F1）；
#   (2) 接 neutralise 的管線必須帶 `2>&1` 或用 `|&`——已知類別 S-2 在這個模式下是規則（R34 requirements F4）。
# 預設模式不要求這兩條：fixture 與產生語料量的是**詞法**，不是 CI 的寫法規範；改寫兩百個 fixture 的管線只會讓
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

    def _scalar(l0):
        v = KEY_RE.match(norm[l0]).group(3) or ""      # 前後空白由下面兩次 strip 處理（opsweep 報這裡的 strip 存活，多餘、刪掉）
        code_v, _c = yaml_split_comment(v)
        # `yaml_decode_scalar` 自己先 strip；引號裡帶空白的值（`"bash "`）不再剝——`--strict` 會把它當成不是 bash、fail-closed
        #（opsweep 報這兩個 strip 存活：一個多餘、一個只影響那種值，都刪掉）
        d = yaml_decode_scalar(code_v)
        return d if d is not None else code_v

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
    wf_shell = None
    for l_, ind_, k_ in roots:
        if k_ == "defaults":
            for l2, i2, k2 in _kids(l_, _end(l_, ind_), ind_):
                if k2 == "run":
                    for l3, _i3, k3 in _kids(l2, _end(l2, i2), i2):
                        if k3 == "shell":
                            wf_shell = _scalar(l3)
    jobs_info = []
    for l_, ind_, k_ in roots:
        if k_ != "jobs":
            continue
        for lj, ij, _name in _kids(l_, _end(l_, ind_), ind_):
            hi = _end(lj, ij)
            kids = _kids(lj, hi, ij)
            names = {k2 for _l, _i, k2 in kids}
            ro_text = ""
            for l2, i2, k2 in kids:
                if k2 == "runs-on":
                    ro_text = " ".join(raw[l2:_end(l2, i2) + 1])      # 只做子字串檢查與訊息，空白無妨（opsweep 報 strip 存活，刪掉）
            jobs_info.append({"lo": lj, "hi": hi, "container": "container" in names,
                              "windows": "windows" in ro_text.lower() or "${{" in ro_text,
                              "ro": ro_text.split("runs-on:", 1)[-1][:40],      # 只進訊息（opsweep 報 strip 存活，刪掉）
                              "shell": _defaults_shell(lj, ij)})

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
        is_bash = eff_shell is not None and BASH_SHELL_RE.match(eff_shell) is not None
        if STRICT and eff_shell is not None and (not is_bash or XTRACE_OPT_RE.search(eff_shell)):
            reject(s["keys"].get("shell", r), "[--strict] step 的 shell 是 %r——本 lint 的詞法是 bash 的，只接受 bash"
                                                 "（可帶選項，但不得開 xtrace：`-x`／`-o xtrace` 會把 PR 文字印到 stderr）" % eff_shell)
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
        run_code, shell_decls, run_unparsed = shell_scan(fold_block(dedent_block(run_lines, explicit_pad), block_folded))
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
        via_pipe = any(PIPED_RE.search(l) for l in logical)
        declared = any(LOGFILTER_RE.match(l) for l in decl_lines)
        ok = via_pipe or declared
        if not ok:
            print("%s:%d: RULE: step '%s' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾"
                  % (path, s["start"] + 1, s["name"]), file=sys.stderr)
            rc = 1
        elif not declared and any(FD_RE.search(l) for l in logical):
            print("%s:%d: RULE: step '%s' 靠管線過濾，卻把輸出轉到 stderr（`>&2`／`/dev/stderr`）或開了 xtrace——"
                  "那些文字不經過管線（帶了 `2>&1` 也一樣：重導向由左到右套用）" % (path, s["start"] + 1, s["name"]), file=sys.stderr)
            rc = 1
        elif STRICT and not declared and (sum(len(PIPED_RE.findall(l)) for l in logical)
                                           > sum(len(STRICT_NEUT_RE.findall(l)) for l in logical)):
            print("%s:%d: RULE: [--strict] step '%s' 接 neutralise.py 的管線沒有帶 `2>&1`（或用 `|&`）——"
                  "PR 文字會從 stderr 繞過" % (path, s["start"] + 1, s["name"]), file=sys.stderr)
            rc = 1
        if STRICT and not is_bash:
            first_pipe = next((k for k, l in enumerate(logical) if ANY_PIPE_RE.search(l)), None)
            if first_pipe is not None and not any(PIPEFAIL_RE.search(l) for l in logical[:first_pipe + 1]):
                print("%s:%d: RULE: [--strict] step '%s' 有管線，卻沒有跑在 pipefail 之下（沒寫 `shell: bash`、defaults 不是 bash、"
                      "run 裡也沒先 `set -o pipefail`）——GitHub 預設 `bash -e {0}`，管線前段的失敗會被後段的 rc 蓋掉"
                      % (path, s["start"] + 1, s["name"]), file=sys.stderr)
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
