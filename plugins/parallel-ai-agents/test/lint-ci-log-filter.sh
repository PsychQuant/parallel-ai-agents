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
# 用法：test/lint-ci-log-filter.sh [workflow.yml…]   預設 ../../.github/workflows/*.yml *.yaml（全部 workflow）
#       test/lint-ci-log-filter.sh --selftest
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  if bash test/lint-ci-log-filter.sh test/fixtures/ci-log-filter-bad.yml >/dev/null 2>&1; then
    echo "lint-ci-log-filter selftest FAILED: a run step with neither neutralise.py nor LOG-FILTER was accepted" >&2
    exit 1
  fi
  if ! bash test/lint-ci-log-filter.sh test/fixtures/ci-log-filter-good.yml >/dev/null 2>&1; then
    echo "lint-ci-log-filter selftest FAILED: the compliant fixture was rejected" >&2
    exit 1
  fi
  # R16 requirements F3 / security S-3 / regression F4 + R17 requirements F-1 / logic L-1 / security S-1 / DA-B：
  # 每一種先前靜默繞過 step 解析的寫法各有一個 fixture。**用 glob 不用寫死清單**——寫死的那份會跟目錄漂
  # （同 repo 已有兩份寫死 shellcheck 清單互相不是超集的前例，#33 verify R11）。新增 fixture 自動納入。
  # 每個 fixture 內都放了一個合規 step：單獨放會被 `seen == 0` 的 vacuity 守衛判紅，那是假紅（R17 DA-B）。
  shopt -s nullglob
  bypass=(test/fixtures/ci-log-filter-bypass-*.yml)
  if [ "${#bypass[@]}" -eq 0 ]; then
    echo "lint-ci-log-filter selftest FAILED: no bypass fixtures found — the selftest would be vacuous" >&2
    exit 1
  fi
  for f in "${bypass[@]}"; do
    out=$(bash test/lint-ci-log-filter.sh "$f" 2>&1) && {
      echo "lint-ci-log-filter selftest FAILED: $f must be rejected" >&2
      exit 1
    }
    # **紅得對不對也要驗**（R18 regression LOW）：`seen == 0` 的 vacuity 守衛同樣回 rc=1，
    # 所以只看 rc 的 selftest 會把「這個 fixture 根本沒有 run step」誤讀成「規則抓到了」。
    # 種一個沒有 run step 的檔進 fixtures/ 就能讓前一版的 selftest 報「全部 rejected」。
    case "$out" in
      *VACUOUS*)
        echo "lint-ci-log-filter selftest FAILED: $f 是被 vacuity 守衛擋的，不是被規則擋的 —— 這個 fixture 需要一個合規的 run step 當對照" >&2
        exit 1 ;;
    esac
  done
  echo "lint-ci-log-filter selftest ok: bad fixture rejected, good fixture accepted, ${#bypass[@]} bypass fixtures rejected"
  exit 0
fi

# R16 DA-4：守備目標不寫死單檔——`.github/workflows/` 底下每一份 workflow 都檢查（新增第二份 workflow 不會漏）。
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
python3 - "${files[@]}" <<'PY'
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
BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?\d*\s*(#.*)?$")
PIPED_RE = re.compile(r"\|\s*python3\s+\S*neutralise\.py(\s|$)")
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")

rc_all = 0
for path in sys.argv[1:]:
    raw = open(path, encoding="utf-8").read().split("\n")
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
            reject(i, "清單項的 key 不是 plain 形式（冒號前有空白／加引號／顯式 key）：`%s`"
                   % (SEQ_RE.match(ln).group(2) or "")[:30])
        else:
            reject(i, "本 lint 不解析這一行（不是 plain key、不是清單項、不是 block scalar 內容）：`%s`" % st[:40])
        kind[i] = "BAD"; i += 1

    # steps: 底下的每個 step
    steps = []
    for i in range(len(raw)):
        if kind[i] != "KEY":
            continue
        mk = KEY_RE.match(norm[i])
        if mk.group(2) != "steps":
            continue
        s_indent = len(mk.group(1))
        j, cur = i + 1, None
        while j < len(raw):
            if kind[j] in ("BLANK", "COMMENT", "SCALAR"):
                if cur is not None:
                    cur["end"] = j
                j += 1; continue
            ind = len(raw[j]) - len(raw[j].lstrip())
            if ind <= s_indent:
                break
            if seq_at[j]:
                if cur: steps.append(cur)
                cur = {"start": j, "end": j, "indent": ind, "kindent": None, "keys": {}, "name": "<未命名>"}
            if cur is None:
                j += 1; continue
            cur["end"] = j
            # **只看 step 自己那一層的 key**。`with:` / `env:` 底下的巢狀鍵是那個 mapping 的內容，
            # 不是 step 的欄位——第一版把它們也拿去比白名單，於是真 test.yml 的 `fetch-depth:`
            # 與三個 `env:` 變數被誤擋。白名單的作用域和它的內容一樣重要。
            if kind[j] == "KEY":
                k_ind = len(KEY_RE.match(norm[j]).group(1))
                if cur["kindent"] is None:
                    cur["kindent"] = k_ind
                if k_ind != cur["kindent"]:
                    j += 1; continue
                k = KEY_RE.match(norm[j]).group(2)
                if k in cur["keys"]:
                    reject(j, "step 裡 `%s:` 出現兩次——YAML 取後者、lint 讀前者，本 lint 拒絕" % k)
                cur["keys"][k] = j
                if k == "name":
                    cur["name"] = (KEY_RE.match(norm[j]).group(3) or "").strip() or "<未命名>"
                elif k not in STEP_KEYS:
                    reject(j, "step 用了白名單外的欄位 `%s:`——本 lint 只認 %s" % (k, sorted(STEP_KEYS)))
            j += 1
        if cur: steps.append(cur)

    rc, seen = 0, 0
    for s in steps:
        if "run" not in s["keys"]:
            continue
        seen += 1
        r = s["keys"]["run"]
        inline = KEY_RE.match(norm[r]).group(3) or ""
        run_lines = [inline] + [raw[k] for k in range(r + 1, s["end"] + 1)
                                if kind[k] == "SCALAR" and owner[k] == r]
        # 註解只有在 step **之內**（縮排比清單項的 dash 更深）才算數。前一版把 step 範圍內的
        # 所有行都拿去比對，於是寫在第 0 欄、落在 job 之間或檔尾的 `# LOG-FILTER:` 也能放行。
        body_lines = [raw[k] for k in range(s["start"], s["end"] + 1)
                      if raw[k].strip() and (len(raw[k]) - len(raw[k].lstrip())) > s["indent"]]
        ok = any(PIPED_RE.search(l) for l in run_lines) or any(LOGFILTER_RE.match(l) for l in body_lines)
        if not ok:
            print("%s:%d: step '%s' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾"
                  % (path, s["start"] + 1, s["name"]), file=sys.stderr)
            rc = 1
    for lineno, why in bad:
        print("%s:%d: %s" % (path, lineno, why), file=sys.stderr)
    # vacuity 只在**解析成功**時才有意義：已經有結構性拒絕時，「找不到 run step」是那個拒絕的
    # 後果，不是另一件事。前一版兩個訊息都印，於是「這個 fixture 是被規則擋的嗎」變得無法機械判定
    # （R18 regression LOW 就是踩在這上面）。
    if seen == 0 and not bad:
        # 訊息刻意與規則的訊息不同：selftest 斷言 bypass fixture 的紅**不是**這一條
        # （R18 regression LOW：前一版只看 rc，於是 vacuity 守衛的紅被當成規則的紅）。
        print("VACUOUS: no run steps found in %s — the lint would be vacuous" % path, file=sys.stderr)
        rc_all = 1
    rc_all = rc_all or rc or (1 if bad else 0)
sys.exit(rc_all)
PY
