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
    if [ "${want}" = "pass" ]; then
      if out=$(bash test/lint-ci-log-filter.sh "$f" 2>&1); then got=pass; else got="rc=$?"; fi
    else
      if out=$(bash test/lint-ci-log-filter.sh --require-run-steps "$f" 2>&1); then
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
  if [ "${n_pass}" -ne 19 ]; then
    echo "lint-ci-log-filter selftest FAILED: 正向 fixture 是 ${n_pass} 個，預期恰好 19（改動 fixture 請同步改這個數字）" >&2
    fail=1
  fi
  if [ "${n_rule}" -ne 32 ]; then
    echo "lint-ci-log-filter selftest FAILED: rule-red 是 ${n_rule} 個，預期恰好 32" >&2
    fail=1
  fi
  if [ "${fail}" -ne 0 ]; then exit 1; fi
  if [ "${n_parse}" -ne 19 ]; then
    echo "lint-ci-log-filter selftest FAILED: parse-red 是 ${n_parse} 個，預期恰好 19（先前這一類完全沒有下限）" >&2
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
  if [ "$a" = "--require-run-steps" ]; then flags+=("$a"); else args+=("$a"); fi
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
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]\d*|\d+[+-]?)?\s*(#.*)?$")
# R24 DA-3 R3：`||` 是**邏輯或**不是管線——`echo x || python3 …neutralise.py` 在 `echo` 成功時
# 後者**從未執行**，而前一版把它算成「已過濾」。反向，`|&`（bash 的 stderr 管線）是**真的**
# 管線卻被誤擋。兩個方向各一個 fixture（`bypass-or-operator` / `good-pipe-stderr`）。
PIPED_RE = re.compile(r"(?<!\|)\|(?!\|)&?\s*python3\s+\S*neutralise\.py(\s|$)")
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")


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
            code.append(" " if ch != quote else ch)      # 引號內容挖空，引號本身保留
            if ch == quote:
                quote = None
            i += 1; continue
        if ch in ("'", '"'):
            quote = ch; code.append(ch); i += 1; continue
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            comment = line[i:]; break
        code.append(ch); i += 1
    return "".join(code), comment


SHELL_WORD_BREAK = " \t;&|()<>"      # `#` 只在**詞首**起註解：行首、或前一個字元是空白／shell metacharacter


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


def dedent_block(lines):
    r"""剝掉 block scalar 的共同縮排 —— **`shell_scan()` 之前必須做**（R26 M2）。
    前一版把帶 YAML 縮排的原始行直接丟進掃描器，於是 heredoc 的終止判定
    `probe.rstrip() == delim` 永遠不成立（`          EOF` 不等於 `EOF`）——**那個分支在任何真實
    `run: |` 裡都不可達**，heredoc 之後的真管線與真的 `# LOG-FILTER:` 一起被吞掉。
    DA 用合成的 base-綠語料量到：含 heredoc 的合規檔 17 個裡 **16 個被打紅**。
    順帶修好 `#` 詞首判定裡 `i == 0` 的語意——縮排剝掉後，行首才真的是行首。
    """
    body = [l for l in lines[1:] if l.strip()]
    if not body:
        return list(lines)
    pad = min(len(l) - len(l.lstrip()) for l in body)
    return [lines[0]] + [(l[pad:] if l.strip() else l) for l in lines[1:]]
def shell_scan(lines):
    r"""把一個 `run:` 區塊掃成（每行會被執行的部分, 不會被執行的宣告文字）。
    **狀態跨行**：引號、反斜線、續行摺疊、heredoc（含佇列）、算術展開深度。
    三個桶：code（會執行）／decls（shell 註解）／**丟棄**（heredoc 內文與引號內容是**資料**）。
    R26 修掉的四件（M2／M3／M5）：
      * 呼叫端先 `dedent_block()`，heredoc 終止判定才可達。
      * `<<<` 是 here-string 不是 heredoc —— 前一版守衛只看第一個 `<`，掃描器前進一格後在第二個
        `<` 上又命中，於是 `cat <<< "$X"` 的 delim 被 latch 成 `"$X"`。現在一次消費三格。
      * `$(( 1 << 4 ))` 的左移不是 heredoc —— 追蹤算術展開深度，深度 > 0 不判 heredoc。
      * 一行多個 heredoc：前一版只存 `pending[0]` 並在註解裡宣稱「其餘由分隔行順推」，**那是假的**
        （第二個 heredoc 的內文會落回 code 桶）。現在是 FIFO，前一個結束就接下一個。
      * 行尾 `\` 是**續行**：前一版把它丟掉、下一行重新當成新行，於是 `cat <\` ⏎ `<EOF` 這種寫法
        讓 heredoc 開頭被拆開、內文整批進了 code 桶，一句假管線就能讓整個 step 過關。
        現在維護 `prev_sig`（前一個有意義字元），續行時不重設，`#` 的詞首判定才正確。
    **已知不涵蓋（這描述的是一個性質，不是一份封閉列舉）**：本掃描器是**詞法**的，
    **不判定可達性**。`false && …`、`if`／`case` 沒走到的分支、`exit 0` 之後的死碼、`eval` 的字串、
    `$(...)` 內的巢狀命令替換——詞法上看得到的管線，執行上不一定跑得到。
    R26 指出前一版把它寫成「五種」的封閉列舉而實際列了六項、且還有第七種（`exit 0` 之後），
    所以這裡改回**陳述性質**：凡是需要知道「這行會不會被執行到」的，本掃描器一律看不出來。
    要關掉這一類必須真的求值 shell，不在本 lint 的範圍內。
    """
    code_lines, decls = [], []
    quote = None            # None / "'" / '"'
    heredoc = None          # (delimiter, strip_tabs)
    pending = []            # 這一行結束後依序要讀的 heredoc（FIFO）
    prev_sig = None         # 前一個「有意義」字元（跨行保留，供 `#` 詞首判定）
    li = 0
    while li < len(lines):
        line = lines[li]
        spans = 1           # 這個**邏輯行**吃掉幾個實體行（續行摺疊）
        if heredoc is not None:
            delim, strip_tabs = heredoc
            probe = line.lstrip("\t") if strip_tabs else line
            if probe.rstrip() == delim:
                heredoc = pending.pop(0) if pending else None
            code_lines.append("")
            li += 1
            continue
        code, i, n = [], 0, len(line)
        arith = 0
        quote0, prev0 = quote, prev_sig      # 邏輯行起點的狀態：摺疊後要從頭重掃
        while i < n:
            ch = line[i]
            if quote == "'":
                code.append("'" if ch == "'" else " ")
                if ch == "'":
                    quote = None
                i += 1; prev_sig = ch; continue
            if quote == '"':
                if ch == "\\" and i + 1 < n:
                    code.append("  "); i += 2; prev_sig = "x"; continue
                code.append('"' if ch == '"' else " ")
                if ch == '"':
                    quote = None
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
                    line = line[:i] + lines[li + spans]
                    n = len(line); spans += 1
                    code, i, arith = [], 0, 0
                    quote, prev_sig = quote0, prev0
                    continue
                i += 1; break
            if ch in ("'", '"'):
                quote = ch; code.append(ch); i += 1; prev_sig = ch; continue
            if ch == "#" and (prev_sig is None or prev_sig in SHELL_WORD_BREAK):
                decls.append(line[i:]); break
            if line.startswith("((", i) or line.startswith("$((", i):
                arith += 1
            elif line.startswith("))", i) and arith:
                arith -= 1
            if line.startswith("<<<", i):
                code.append("<<<"); i += 3; prev_sig = "<"; continue   # here-string，不是 heredoc
            if line.startswith("<<", i) and not arith:
                j = i + 2
                strip_tabs = False
                if j < n and line[j] == "-":
                    strip_tabs = True; j += 1
                while j < n and line[j] in " \t":
                    j += 1
                if j < n and line[j] in ("'", '"'):
                    q = line[j]; j += 1; st = j
                    while j < n and line[j] != q:
                        j += 1
                    delim = line[st:j]; j += 1
                else:
                    st = j
                    while j < n and line[j] not in SHELL_WORD_BREAK:
                        j += 1
                    delim = line[st:j]
                delim = delim.replace("\\", "")        # `<<\EOF`：反斜線只是把分隔字引號化
                if delim:
                    pending.append((delim, strip_tabs))
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
        if heredoc is None and pending:
            heredoc = pending.pop(0)
        li += spans
    return code_lines, decls
REQUIRE_RUN_STEPS = "--require-run-steps" in sys.argv
rc_all = 0
for path in [a for a in sys.argv[1:] if a != "--require-run-steps"]:
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

    top_key = None
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
            if len(mk.group(1)) == 0:
                top_key = mk.group(2)                      # 最近一個頂層 key，決定我們在哪棵子樹裡
            if val[:1] in ("{", "["):
                code_val, _ = yaml_split_comment(val)      # 引號內容挖空，避免資料裡的冒號誤判
                balanced = (code_val.count("{") == code_val.count("}")
                            and code_val.count("[") == code_val.count("]"))
                # **只在 `jobs:` 子樹裡 fail-closed**。第一版對整份文件套用，於是
                # `on: pull_request: { branches: [ main ] }` 這種完全合法、而且**結構上不可能藏
                # run step** 的寫法被打紅——563 檔語料上當場兩個第三方檔從綠翻紅。
                # 誤擋與繞過是兩個方向，這條規則只該作用在真的可能藏東西的那棵子樹。
                # 括號不平衡（看不到整個值）則不分子樹一律拒絕：那時連「它在哪棵樹」都不確定。
                if (":" in code_val and top_key == "jobs") or not balanced:
                    reject(i, "flow 形式的值含 mapping 或跨行——本 lint 不解析它，而不解析就不放行："
                              "`%s`" % val[:40])
                    kind[i] = "BAD"; i += 1; continue
            if val.startswith(("&", "*", "<<")):
                reject(i, "欄位用 anchor／alias／merge key 帶入——本 lint 不解析：`%s`" % val[:30])
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
    # 語料清單在 verify 產物目錄，量測腳本是 threeaxis.py。要宣稱更多，先跑更大的語料。
    # R26 M1：`[-{,]` 有兩個錯。① 漏了 `[` —— YAML flow 序列允許**無括號的單對 mapping**
    # （`[k: v]` ≡ `[{k: v}]`），於是 `steps: [run: …]` 整個看不見。② `-` 直接放在字元類裡會
    # 命中**識別字內部的連字號**，`dry-run:`／`operations-per-run:`（`actions/stale` 最常見的
    # 兩個輸入）被判成藏起來的 run key —— 我在 R25 引進的真誤擋，第三方語料當場 6 處。
    # 清單項的 dash 後面**必然有空白**，而識別字內的連字號不會，所以用 `-\s+` 加左邊界。
    PLAIN_RUN_KEY = re.compile(r"(?:^\s*|(?<![\w.-])-\s+|[{,\[]\s*)run\s*:")
    QUOTED_RUN_KEY = re.compile(r"(?:^\s*|(?<![\w.-])-\s+|[{,\[]\s*)(['\"])run\1\s*:")
    for i, ln in enumerate(raw):
        if kind[i] in ("COMMENT", "SCALAR"):
            continue                      # 註解與 block scalar 內容不是結構
        hollow, _ = yaml_split_comment(ln)
        found = len(PLAIN_RUN_KEY.findall(hollow)) + len(QUOTED_RUN_KEY.findall(ln))
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

    rc, seen = 0, 0
    for s in steps:
        if "run" not in s["keys"]:
            continue
        seen += 1
        r = s["keys"]["run"]
        inline = KEY_RE.match(norm[r]).group(3) or ""
        # `run: |` 的 `|` 是 **block scalar 的指示子**，不是要執行的程式碼。前一版把它當成 run 的
        # 第一段文字丟進 run_joined，於是 `run: |` + 下一行的 `python3 …neutralise.py` 被接成
        # `| python3 …neutralise.py` ——**憑空造出一條管線**（R22 logic / Codex #1 的那個 fixture
        # 就是這樣過的）。這是 R21 為修折疊管線誤擋而加的合併帶進來的，第二次。
        if BLOCK_SCALAR_RE.match(inline.strip()):
            inline = ""
        elif not inline.strip():
            # R24 DA-8(b)：`run:` 的值寫在**下一行**（合法的 plain multi-line scalar）時，前一版
            # 既印 `PARSE:`（不解析那一行）**又**印 `RULE:`（說它沒過濾）——而該 step 真的過濾了。
            # 規則對一個沒被解析出來的 run 區塊**沒有適用對象**：只印 `PARSE:`，不得再印 `RULE:`。
            reject(r, "`run:` 的值不在同一行、也不是 block scalar（plain multi-line scalar）——本 lint 不解析")
            continue
        else:
            decoded = yaml_decode_scalar(inline)
            if decoded is None:
                reject(r, "`run:` 的值用了本 lint 未實作的 YAML 逃脫——"
                          "解錯字串會讓管線判定憑空成立或憑空消失，所以不猜：`%s`" % inline.strip()[:40])
                continue
            inline = decoded
        run_lines = [inline] + [raw[k] for k in range(r + 1, s["end"] + 1)
                                if kind[k] == "SCALAR" and owner[k] == r]
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
        run_code, shell_decls = shell_scan(dedent_block(run_lines))
        decl_lines += shell_decls
        run_joined = " ".join(c.strip() for c in run_code)
        ok = (any(PIPED_RE.search(c) for c in run_code) or PIPED_RE.search(run_joined)
              or any(LOGFILTER_RE.match(l) for l in decl_lines))
        if not ok:
            print("%s:%d: RULE: step '%s' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾"
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
