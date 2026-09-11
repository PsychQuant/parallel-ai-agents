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
  if [ "${n_pass}" -lt 8 ]; then
    echo "lint-ci-log-filter selftest FAILED: 正向 fixture 只有 ${n_pass} 個——負向再多也證明不了它放得過好輸入" >&2
    fail=1
  fi
  if [ "${n_rule}" -lt 20 ]; then
    echo "lint-ci-log-filter selftest FAILED: rule-red 只有 ${n_rule} 個" >&2
    fail=1
  fi
  if [ "${fail}" -ne 0 ]; then exit 1; fi
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
PIPED_RE = re.compile(r"\|\s*python3\s+\S*neutralise\.py(\s|$)")
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")


def split_code_and_comment(line):
    """把一行切成（**會被執行的部分**, **不會被執行的部分**）。

    R22 的 meta 根因（requirements F-1/F-2、logic、Codex #1 獨立收斂）：`ok = (PIPED_RE …)` 與
    `(LOGFILTER_RE …)` 是**兩個判斷**，R21 只把右邊白名單化。左邊對原始行文字搜尋，於是
    「提到管線」與「真的經過管線」分不開——YAML 行尾註解、shell 註解、字串裡寫一句話，
    三者都算「已過濾」。而 `COMMENT` 的分類又排在白名單之上，只看 `strip()` 是否以 `#` 開頭，
    所以 `# name: |2-` 繞過的不是白名單本身、是它前面那道分類（requirements 的控制組：拿掉那個
    `#` 就變 rc=1 並印「本 lint 不解析這一行」——**白名單本來抓得到**）。

    修法是**一個抽取函式、兩個述詞各讀自己那一半**：管線判定只看會被執行的部分，`# LOG-FILTER:`
    判定只看不會被執行的部分。兩者不可能再對同一段文字得出相反的結論。

    規則（對 YAML plain scalar 與 block scalar 內的 shell 都成立）：引號外、位於行首或前面是空白
    的 `#` 起，到行尾都不會被執行。引號內的內容**整段挖空**（保留引號與長度），這樣寫在字串裡的
    `| python3 …neutralise.py` 不會被誤認成管線。
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
                reject(i, "清單項用本 lint 不解析的寫法（flow／anchor／alias／merge key）：`%s`" % rest[:30])
        mk = KEY_RE.match(norm[i])
        if mk:
            kind[i] = "KEY"
            val = (mk.group(3) or "").strip()
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
            code_rest, _ = split_code_and_comment(rest_raw)
            code_rest = code_rest.rstrip()
            if ": " in code_rest or code_rest.endswith(":"):
                reject(i, "清單項的 key 不是 plain 形式（冒號前有空白／加引號／顯式 key）：`%s`"
                       % rest_raw[:30])
            else:
                kind[i] = "SEQ"; i += 1; continue       # 純量清單項（`- main`、`- "8080:8080"`…）
        else:
            reject(i, "本 lint 不解析這一行（不是 plain key、不是清單項、不是 block scalar 內容）：`%s`" % st[:40])
        kind[i] = "BAD"; i += 1

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
        run_lines = [inline] + [raw[k] for k in range(r + 1, s["end"] + 1)
                                if kind[k] == "SCALAR" and owner[k] == r]
        # **宣告層也白名單**（R20 security S-1/S-2）：R19 讓 block scalar 的內容對「結構」判定不透明，
        # 卻沒對「宣告」判定不透明——於是 `name: |` 的 scalar 裡寫一行 `# LOG-FILTER:` 就放行整個 step，
        # 而那一行是 step 的**顯示名稱**不是註解（`yaml.safe_load` 可證）。註解歸屬也會跨 step 邊界。
        # 現在只認兩種來源，其餘一律不算：
        #   (1) 真的是**註解行**（kind == COMMENT）且落在這個 step 自己的行範圍、縮排比 dash 深；
        #   (2) `run:` **自己**那個 block scalar 的內容（header 明文允許，repo 裡有兩個真實指令這樣寫）。
        # `# LOG-FILTER:` 只能來自**不會被執行的部分**：step 自己的 YAML 註解行，或 `run:` 區塊
        # 內的 shell 註解。兩者都由 split_code_and_comment 切出來，與管線判定共用同一個定義。
        decl_lines = []
        for k in range(s["start"], s["end"] + 1):
            if kind[k] == "COMMENT" and (len(raw[k]) - len(raw[k].lstrip())) > s["indent"]:
                decl_lines.append(raw[k])
            elif kind[k] == "SCALAR" and owner[k] == r:
                _, cmt = split_code_and_comment(raw[k])
                if cmt:
                    decl_lines.append(cmt)
        # 管線可以跨行（折疊 scalar `>`，或 literal `|` 裡行尾留 `|` 續行）——R20 regression R-6：
        # 前一版只逐行比對，於是 `echo hi |` / `python3 …neutralise.py` 分兩行寫就被誤擋。
        # 兩種寫法下行尾的 `|` 本來就代表管線延續，所以把 run 區塊接成一串再比對是語意正確的。
        # 管線判定只看**會被執行的部分**（引號內容已挖空、註解已剝掉）。跨行管線（折疊 scalar，
        # 或行尾留 `|` 續行）仍要接成一串才判得到——但接的是 code 半邊，不再是原始文字。
        run_code = [split_code_and_comment(l)[0] for l in run_lines]
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
            print("%s: 沒有 run step（純 uses:／reusable workflow）—— 本規則沒有適用對象" % path, file=sys.stderr)
    rc_all = rc_all or rc or (1 if bad else 0)
sys.exit(rc_all)
PY
