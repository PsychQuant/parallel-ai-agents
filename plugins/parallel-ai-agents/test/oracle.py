#!/usr/bin/env python3
"""bash 神諭：runner 到底有沒有把 `neutralise.py` 接在管線的接收端——與 lint 的判定對帳。

為什麼（#33 verify R28 DA）：lint 對一個 fixture 的判定與 fixture 上 `# EXPECT:` 的宣告，**兩者都是作者寫的**。
selftest 只證明「lint 的判定 = 作者的宣告」，證不了「作者的宣告 = runner 的行為」。神諭把第三個東西（runner）
拉進來對帳。R30 的 DA 把同一支工具指向 base 的 lint，一條指令重現出 R28 的十條——網有牙。

## 管線判定改由 **bash 自己的剖析器**回答（R30 MB-4）
前一版在 stub 裡問 `[ -p /dev/stdin ]`。那量的是「stdin 是不是 pipe fd」，而 bash 5.x 的 heredoc **也用 pipe**
——於是 `python3 …neutralise.py <<EOF` 被算成「有管線」，神諭對 lint 發出**假指控**。
現在用 DEBUG trap ＋ `${#PIPESTATUS[@]}`：trap 在**下一個**命令之前觸發，此時 `PIPESTATUS` 是剛結束那個
pipeline 的每段狀態，長度 ≥2 就代表它真的是 pipeline。這是 bash 自己的答案，
對 `<<"EO"F`、`$'…'`、`${VAR#…}`、反引號註解這些詞法花招**一律免疫**——剖析是它做的，不是我們做的。
（`( … )` 之類的子殼層不影響：PIPESTATUS 的長度只由 pipeline 的段數決定。）

## 宣告的判定改用**差分**（R30 MB-2）
前一版是對 step 行範圍做裸子字串 `"LOG-FILTER:" in l`，於是寫在 **heredoc 內文**裡的假宣告被當成真宣告，
把一個真繞過認證成「一致」。宣告的定義是「runner 不會執行、也不會當資料吃掉的文字」，所以現在**直接問 bash**：
把那一行刪掉再跑一次，`(rc, stdout, stderr, 被記錄的呼叫)` 完全相同 ⟹ 它既不被執行也不被消費 ⟹ 它是註解。
（YAML 層的註解——真正的註解行、`run:` 行尾註解——不在 run 區塊的文字裡，另行辨識，不需要差分。）

## 已知類別用**差分**判定（R37，#33 verify R36 第 1、2 列）
「lint 放行 ∧ bash 建了接 neutralise 的管線 ∧ PR 文字仍然外流」時，要回答的是**外流是誰印的**。前一版用兩條正規式
（幾乎就是 lint 規則的副本）回答：「正規式沒認出 fd 轉向／xtrace、且管線本身已經帶 `2>&1`（`NEUT_WITH_STDERR_RE` 命中）⟹ 已知類別 G；正規式認得 fd 轉向時反而不歸 G，改判一般的不一致：繞過」——凡是正規式
以外的 fd 轉向（`>&02`、`>/dev/fd/2`、`exec 3>&1` 後 `>&3`、`shopt -so xtrace`…），lint 放行、神諭也把它收進已知 G、rc=0。
現在**直接問 bash**：把含 `neutralise.py` 的那幾條邏輯行換成一個中性命令再跑一次，逐條比對外流的行（stdout／stderr 分開、
計重數）。外流原封不動 ⟹ 另一條命令印的 ⟹ G（還要 `--strict` 真的擋下這個 step，否則是繞過，見下）；有一部分跟著消失
⟹ **那條管線自己外流**，不是 G。
換掉之後語法壞掉時先把範圍往上擴到語法完整（多行群組 `{` ⏎ … ⏎ `} 2>&1 | …`，R39）；仍然壞掉、neutralise 仍被呼叫、或出現
原本沒有的外流 ⟹ 差分不可比 ⟹ **分類**失敗，絕不歸 G。**外流是 baseline 已觀察到的事實，分類失敗不抵銷它**：判不一致：繞過
（R39，#33 verify R38 第 3 列；前一版判「量不到」而量不到不改 rc，lint 與神諭兩張網因此同時看不到多行群組裡的外流）。
外流行是 xtrace 的輸出（神諭把 PS4 設成自己的標記）⟹ 繞過，不歸任何已知類別（R39，R38 第 4、6 列）。
S-2 的定義是「預設模式不要求 `2>&1`、`--strict` 要求」：管線自己只從 stderr 外流、`--strict` 的群組規則真的擋下這個 step，
**而且機制成立**（R39，R38 第 6 列；見 `s2_mechanism`）——每一段補上 `2>&1` 外流就消失，或外流行全是 bash 自己的錯誤訊息、
左邊包成群組就消失。前一版只看前兩條，而群組規則擋下所有非群組管線，於是 fd 轉向、xtrace 這些 fd 規則該擋的外流在規則失效時
被收進 S-2。G 同理（#59／#60，R37 自 PR #61 移植）：`--strict` 對那個 step 印 pipefail 以外的 RULE 或 PARSE 才算已知 G，
否則判 `STRICT_MISS`（繞過）。**兩個類別都另外要求原因檢查**（R39，R38 第 7 列）：刪掉與外流無關的行之後 `--strict` 仍擋，
否則判 `CAUSE_MISS`（繞過）。這些判準都不含任何 lint 規則的正規式副本。
**類別閘門是雙向的**：被歸進類別 X 的 step 數必須**等於**檔頭 `# KNOWN-CLASS: X` 的行數——多了是「歸了類卻沒宣告」，
少了是「KNOWN-CLASS 過期」，兩者都 rc=1。已知類別因此不再是免檢區：每一條都有人在檔頭簽名。
**must-fail 探針**（`# ORACLE-MUST-FAIL: <理由子字串>`）：只在神諭**失敗**時才過的 fixture——上面那些分支只在 lint 有缺陷或
宣告寫錯時才會走到，一個全綠的 fixture 集結構上測不到它們。探針自己的失敗不計入總 rc；探針**沒有**以宣告的理由失敗才 rc=1。

## 判定表（含第三格「量不到」；判定的**種類**是 `VERDICT_KINDS` 那五種）
  lint pass     ∧ piped ∧ 無外流                → 一致
  lint pass     ∧ piped ∧ 外流                  → 差分歸類：已知類別 G／S-2，否則**不一致：繞過**（含分類失敗，見上）
  lint pass     ∧ 非 piped ∧ 有**真**宣告        → 一致（宣告的豁免）
  lint RULE-red ∧ 非 piped                      → 一致
  lint RULE-red ∧ piped ∧ 外流                  → 一致（擋下是對的，R35）
  lint RULE-red ∧ piped ∧ 無外流                → **不一致：誤擋**
  step 唯一的 RULE 是 `[--strict]` pipefail      → 不可比（量的是退出碼遮蔽；同 step 另有 RULE 時照常對帳，R37）
  lint pass     ∧ 非 piped ∧ 無宣告 ∧ 有外流    → **不一致：繞過**；無外流時是**量不到**
  lint PARSE    ∧ piped ∧ PyYAML 解析成功        → **不一致：誤擋（PARSE）**，除非該檔自己宣告 `# EXPECT: parse-red`
  timeout／stub 沒被呼叫到但腳本逾時             → **量不到**（不是繞過，也不算一致；逐項具名）

**適用邊界**：lint 依設計不判可達性（`if false; then … | python3 …; fi` 它算「有管線」），神諭是真的跑——
這類差異多數落在「量不到」，根本不會走到「不一致」（用不到 `KNOWN_DISAGREE`）；只有真的判成「不一致」的設計性分歧，才會列在 `KNOWN_DISAGREE` 並寫理由（可達性本身目前沒有對應條目）。神諭不用 `-e`：runner 用 `bash -e`，但這裡要問的是
「管線有沒有被建立」，前面的指令失敗屬於可達性、不屬於本題。

**盲區（明寫）**：YAML 層用 PyYAML 解析，而 GitHub 的解析器**不同**——R25 探針實測（R26 verify 獨立覆核為真）tab 分隔的引號 key
PyYAML 拒絕、GitHub 照樣執行；R29 探針實測整份縮排的文件 PyYAML 接受、GitHub 也執行。所以 `YAML-FAIL`
那一格是神諭**看不到**的地方，不是「runner 也不會跑」的保證。神諭對帳的是 shell 層，YAML 層的真值要靠探針。

**它會真的執行 fixture 裡的 shell**（R30 M-16）：PATH 只有 stub 與 `/usr/bin:/bin`、cwd 與 HOME 都是臨時目錄、
stdin `/dev/null`、逾時 5 秒。但那不是沙箱——fixture 寫絕對路徑就寫得出去、背景程序活得過逾時。
**加 fixture 等於加一段會被執行的 shell**，review 時請當成程式碼看。
**`env:` 會帶進去**（R37，R36 第 8 列）：workflow／job／step 三層的純量值依序覆蓋（step 最後），`SHELLOPTS: xtrace`、
`BASHOPTS`、`BASH_XTRACEFD` 因此量得到；含 `${{` 的值 runner 才知道，不設。PATH、HOME、`PR_TITLE` 永遠用神諭自己的值。
**盲區**：`BASH_ENV`／`ENV` 指向的檔案在臨時 cwd 裡不存在（神諭不把 repo 的檔案帶進去），那些檔案的內容量不到；
`/proc/self/fd/2` 在 macOS 上不存在，那一類 fd 轉向在本機量不到外流、在 Linux runner 上量得到（R39 起這幾張
fixture 的誤擋只在沒有 /proc 的平台列為已知，見 `KNOWN_DISAGREE_WITHOUT_PROC`）；`/bin/sh` 在 macOS 是 bash、在 ubuntu
是 dash——依賴 `sh` 的外流兩個平台不同（R38 第 1 列：CI 紅、本機綠）。**本機的神諭數字要註明平台，CI（Linux）為準。**
PR 文字固定是 `ORACLE-PR-TITLE-MARKER`：算術展開（`$(( PR_TITLE ))` 在這個值下是 0）與寫檔（神諭的 cwd 可寫）這兩種
#60 第 2 類形狀在神諭裡不出錯、量不到外流，會把群組規則正確的擋判成誤擋（R38 第 19 列；fixture 改用 `1 $PR_TITLE` 這類
一定出錯的寫法）。`python3` 是 shell stub，不讀 `PYTHON*`（R39 那三張 fixture 因此列在 `KNOWN_DISAGREE`）。
**差分的中性替換會改變 `$?`**（R38 codex 第 5 條）：換掉接 neutralise 的那一行，之後依賴 `$?` 的分支可能不再印，差分因此把
「管線外的命令外流」看成管線自己的外流。R39 起 S-2 另外要求機制差分成立（補 `2>&1` 後外流消失），這一類因此判繞過、
不再被收進已知類別——方向是 fail-closed，但歸類的**原因**仍可能寫錯。

依賴：PyYAML（`python3 -m pip install pyyaml`）。缺就 fail-loud，不靜默跳過。
用法：test/oracle.py [FILE…]   不給檔案 → 全部 test/fixtures/ci-log-filter-*.yml
      環境變數 `ORACLE_LINT=<path>` 換掉被對帳的 lint（只給突變測試用：量「神諭抓不抓得到某個 lint 突變」）。
退出碼：有 `KNOWN_DISAGREE` 之外的不一致 → 1；`KNOWN_DISAGREE` 裡的項目變成一致（理由不再成立）→ 1；
已知類別的歸類數與檔頭宣告數不相等（任一方向）→ 1；must-fail 探針沒有以宣告的理由失敗 → 1；不給檔案參數執行整個 fixture 集時，已知類別總數／must-fail 探針總數與寫死常數 `FIXTURE_CLASS_TOTALS`／`FIXTURE_MUSTFAIL_TOTAL` 不符 → 1；否則 0。
「量不到」不改變退出碼，但一定逐項印出來。
"""
import collections
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
# `ORACLE_LINT` 只給突變測試用（見 docstring 的用法）：正常執行一律對帳 repo 自己的 lint。
LINT = pathlib.Path(os.environ.get("ORACLE_LINT") or (HERE / "lint-ci-log-filter.sh")).resolve()
FIXTURES = HERE / "fixtures"

try:
    import yaml
except ImportError:                       # 依賴缺席不是「沒有不一致」——那是沒量到
    print("✗ oracle.py 需要 PyYAML：python3 -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# (fixture 檔名, step 名) → 理由。每一條都要能說出「runner 與 lint 為什麼依設計會不同」；說不出來的就是缺陷。
KNOWN_DISAGREE = {
    # **YAML tag 一律 fail-closed，而 `!!str` 的值 bash 照跑** ⇒ 誤擋。這是**刻意保留**的，
    # 理由與代價都寫在這裡（R33，由 642 檔產生語料的 `R31-5 tag 值` 那一列量出來）：
    #   · 那道守衛是 R30 MB-8 加的，堵的是 `jobs: !!map {…}` 讓 flow 規則、`steps:` flow 檢查、
    #     anchor／alias 檢查**三條全部跳過**、整個 job 隱形的洞。
    #   · 只放行 `!!str` 需要動 YAML 分類路徑本身；那條路徑守著一個真的洞，而 `!!str` 的
    #     野外出現率是 **0/1565**（`shapes.py` 的 `R31-5` 列，本機語料實測）。
    #   · 所以本輪**不動它**，改成記在這裡：數字誠實地印成「不一致 1（已知 1）」，
    #     而不是讓它在「量不到」或某個寬鬆的述詞後面消失。
    # 這一條若哪天變成「一致」（有人放行了 tag），神諭會 rc=1 要求重判——理由不再成立就要拿掉。
    # **已知類別（G、S-2）不在這裡逐檔列**：它們按類別處理——`classify_piped_leak` 用差分判定外流是誰印的、
    # S-2 另外要 `--strict` 真的擋下那個 step，歸了類的 step 由所在檔頭的 `# KNOWN-CLASS:` 逐條簽名（雙向閘門，R37）。
    # 逐檔列會讓產生語料上的幾十條各佔一行、沒人讀；類別讓規則改掉的那一天，整類一起翻並被逼重判。
    ("gen-d-yaml-tag-bang.yml", "tag-bang"):  # 這個檔名只在 shellgen.py 產生語料時動態產生（R31-5 tag 值 shape），repo 內沒有這個靜態 fixture 檔案
        "YAML tag 一律 fail-closed（R30 MB-8 堵 `jobs: !!map` 隱形 job）；`!!str` 因此被連帶擋下。"
        "野外 0/1565，不值得為它動那條守著真洞的路徑。",
    # **`env:` 整張來自 runner 運算式** ⇒ 誤擋（R37 完整性審查補的 fixture）。lint 看不到鍵名，記成 `?` 並 fail-closed：
    # 那張 map 可以帶進 `SHELLOPTS: xtrace`，bash 啟動時就生效、trace 行帶著 PR 文字裸印（實測）。神諭依設計不設含
    # `${{` 的值（runner 才知道），所以量不到那個外流、判誤擋。這是兩邊資訊量不同造成的設計差異，不是 lint 的缺陷。
    ("ci-log-filter-bypass-r37t8-step-env-inline-expression.yml", "s"):
        "`env:` 整張來自 `${{ … }}`，lint 看不到鍵名而 fail-closed；神諭不設 runner 運算式的值，量不到它可能帶進的 SHELLOPTS。",
    # **頂層 `case` 的模式 `|` 被預設模式讀成管線** ⇒ 繞過（R37 完整性審查缺陷 d，刻意保留的已知限制）：`--strict` 擋下它；
    # 預設模式要修得把 case 追蹤延伸到頂層，代價與理由見 lint 已知不涵蓋第三組第 5 條。修好之後這一列變一致，神諭 rc=1 逼人拿掉。
    # **根層級 `env:` 是純量**（R37 opsweep 補件 `bypass-r37o-module-misc-root-env-nonflow-colon-value`）：`env: FOO:bar` 讀不到
    # 鍵名，lint 記成 `?` 並 fail-closed（那張 map 可能帶進 SHELLOPTS）；神諭沒有鍵可設、量不到外流而判誤擋。與上面
    # `step-env-inline-expression` 同一種兩邊資訊量不同的設計差異。GitHub 本身也不接受非 mapping 的 `env`。
    ("ci-log-filter-bypass-r37o-module-misc-root-env-nonflow-colon-value.yml", "probe"):
        "根層級 `env:` 是純量、看不到鍵名，lint fail-closed；神諭沒有鍵可設，量不到它可能帶進的 SHELLOPTS。",
    # **R37 最終 lint 的 opsweep 補件裡的限制型 fixture**（`restrict-r37p-*`）：突變體把保守的拒絕放寬，這些 fixture 釘住拒絕本身。
    # 輸入實際都不外流，神諭因此判誤擋——那是刻意的 fail-closed，不是 lint 的缺陷。
    ('ci-log-filter-restrict-r37p-fdflow-analyse-amp-trail-drop.yml', 'group has its own trailer plus |& connector'):
        '群組豁免只收收尾後恰好接 `2>&1 |` 或 `|&`（沒有別的 trailer）的群組；這個形狀實際不外流，但豁免不涵蓋它。',
    ('ci-log-filter-restrict-r37p-fdflow-analyse-pipe-conn-drop.yml', 'exact 2>&1 trailer combined with |& connector'):
        '群組豁免只收收尾後恰好接 `2>&1 |` 或 `|&`（沒有別的 trailer）的群組；這個形狀實際不外流，但豁免不涵蓋它。',
    ('ci-log-filter-restrict-r37p-fdflow-is2to1-lit-drop.yml', 'group trailer closes fd2, does not dup to fd1'):
        '群組豁免要求收尾恰好是 `2>&1`（fd 2 複製到 fd 1）；`2>&-`、`2>1` 這類實際不外流，但不是豁免的形狀。',
    ('ci-log-filter-restrict-r37p-fdflow-is2to1-op-drop.yml', 'group trailer redirects to a file literally named 1, not fd dup'):
        '群組豁免要求收尾恰好是 `2>&1`（fd 2 複製到 fd 1）；`2>&-`、`2>1` 這類實際不外流，但不是豁免的形狀。',
    ('ci-log-filter-restrict-r37p-fdflow-redirhit-1740-op-drop.yml', 'input-direction fd dup treated same as output-direction'):
        '輸入方向的 fd 複製（`<&`）一律當成 fd 流向命中（fail-closed）；這個形狀實際不外流。',
    ('ci-log-filter-restrict-r37p-fdflow-redirhit-1743-op-drop.yml', 'input-direction fd dup to a literal non-digit word'):
        '輸入方向的 fd 複製（`<&`）一律當成 fd 流向命中（fail-closed）；這個形狀實際不外流。',
    ('ci-log-filter-restrict-r37p-parse-command-neut-wrong-filename.yml', 'group piped through python3 running the wrong script'):
        '管線的過濾端不是 `python3 <路徑>/neutralise.py`，照規則拒絕；實際執行會報錯、不把 stdin 印出來，神諭量不到外流。',
    ('ci-log-filter-restrict-r37p-parse-command-neut-wrong-interpreter.yml', 'group piped through a same-named script under the wrong interpreter'):
        '管線的過濾端不是 `python3 <路徑>/neutralise.py`，照規則拒絕；實際執行會報錯、不把 stdin 印出來，神諭量不到外流。',
    ('ci-log-filter-restrict-r37p-strict-set-prefix-badname.yml', 'set -o with an unrecognised option name is not accepted as a group prefix line'):
        '群組規則的 `set` 前綴只收 `-e`／`-u`／`-o pipefail|errexit|nounset`；bash 對壞選項報錯，這一步實際不外流，被擋是限制。',
    ('ci-log-filter-restrict-r37p-strict-set-prefix-eu-skip.yml', 'set -e followed by a bad token is not accepted as a group prefix line'):
        '群組規則的 `set` 前綴只收 `-e`／`-u`／`-o pipefail|errexit|nounset`；bash 對壞選項報錯，這一步實際不外流，被擋是限制。',
    ('ci-log-filter-restrict-r37p-strict-set-prefix-o-skip.yml', 'set -o pipefail followed by a bad token is not accepted as a group prefix line'):
        '群組規則的 `set` 前綴只收 `-e`／`-u`／`-o pipefail|errexit|nounset`；bash 對壞選項報錯，這一步實際不外流，被擋是限制。',
    ("ci-log-filter-known-r37t8-default-case-pattern-pipe.yml", "s"):
        "頂層 case 模式的 `|` 是「或」，預設模式的 `PIPED_RE` 算它接了 neutralise；`--strict` 由群組規則擋下（區塊不是 `{ …; } 2>&1 | python3 …` 群組）。",
    # **`--strict` 群組規則只收恰好一對大括號**（#59／#60）⇒ 群組裡再包一個群組是誤擋。刻意保留：計深度要判斷每個
    # `{`／`}` 在 bash 眼中是不是保留字，而 `case` 模式的 `{)` 會讓計數器以為群組還開著（`bypass-strict-group-case-pattern-brace`
    # 實測外流）。代價只落在 `--strict`（真 workflow）：要短路改寫成 `if`，repo 自己的 workflow 沒有巢狀群組。
    ("ci-log-filter-restrict-strict-group-nested.yml", "nested group"):
        "群組規則只收恰好一對大括號（計深度會被 `case` 的 `{)` 騙過）；巢狀群組因此被連帶擋下，改寫成 `if` 即可。",
    # **神諭的 python3 是 stub**：它不檢查路徑存不存在，所以真 python3 的「can't open file '<路徑>'」（路徑裡帶著展開後的
    # PR 文字、寫在 python3 自己的 stderr）在這裡不會出現。lint 擋下是對的，神諭量不到——這是儀器的盲區，不是 lint 的誤擋。
    ("ci-log-filter-bypass-strict-group-expansion-in-filter-path.yml", "expansion in the filter path"):
        "stub python3 不報「can't open file」；真 python3 會把含 PR 文字的路徑印到群組外的 stderr。",
    ("ci-log-filter-bypass-strict-group-variable-filter-path.yml", "variable in the filter path"):
        "同上：路徑是 `$PR_TITLE/neutralise.py`，stub python3 不報「can't open file」。",
    # **子殼層群組 `( … ) 2>&1 |` 被擋**（R37 移植 #61 群組規則）：安全，但 `(`／`)` 也出現在 `$(`、`$((`、陣列、`case` 模式裡，
    # 「恰好一對」的論證對它不成立。改寫成 `{ …; }` 即可。
    ("ci-log-filter-restrict-r37-strict-subshell-group.yml", "subshell group"):
        "群組規則只收大括號群組；子殼層群組安全但被連帶擋下，改寫成 `{ …; }` 即可。",
    # **產生語料 `--strict` 組（shellgen 維度 1／5／6）上的同兩種代價**（R37 移植 #61 群組規則後重跑產生語料神諭才量到——
    # 移植當下只重跑了 fixture 神諭，而 CI 的產生語料 step 兩組都跑）。這一組是移植前按「逐段 `2>&1`」規則設計的，
    # 它的「該放行」基準在群組規則下變成保守擋下；lint 行為是設計，不是回歸：
    #   · 逐段 `2>&1`（5 檔）：群組規則刻意不收逐段形式——那一段的 `2>&1` 生效前的展開期／重導向錯誤不經過濾（#60 第 2 類）。
    #     這幾個形狀剛好沒有這種錯誤，但規則不分辨哪一段會出錯。改寫成 `{ …; } 2>&1 | …` 即可。
    #   · `( … )` 子殼層包裹（3 檔）：同上一條 `restrict-r37-strict-subshell-group`。`{ … }` 那三檔照樣放行、判一致。
    ("gen-f-shell-bash.yml", "shell value bash"):
        "群組規則不收逐段 `2>&1`（#60 第 2 類：那一段的 `2>&1` 生效前的錯誤不經過濾）；這個形狀剛好不出錯，規則不分辨。",
    ("gen-f-shell-bash-dq.yml", "shell value bash-dq"): "同 `gen-f-shell-bash`：逐段 `2>&1`，群組規則保守擋下。",
    ("gen-f-shell-bash-sq.yml", "shell value bash-sq"): "同 `gen-f-shell-bash`：逐段 `2>&1`，群組規則保守擋下。",
    ("gen-f-pipeseg-2-gap0.yml", "pipeline of 2 segments, gap=0"): "同 `gen-f-shell-bash`：每段都帶 `2>&1`，仍不是群組形式。",
    ("gen-f-pipeseg-3-gap0.yml", "pipeline of 3 segments, gap=0"): "同 `gen-f-shell-bash`：每段都帶 `2>&1`，仍不是群組形式。",
    ("gen-f-wrap-subshell-fd-redirect-wrapped.yml", "subshell wrapped fd-redirect"):
        "同 `restrict-r37-strict-subshell-group`：群組規則只收 `{ …; }`，子殼層包裹安全但被連帶擋下。",
    ("gen-f-wrap-subshell-saved-fd-wrapped.yml", "subshell wrapped saved-fd"): "同上：子殼層包裹。",
    ("gen-f-wrap-subshell-xtrace-wrapped.yml", "subshell wrapped xtrace"): "同上：子殼層包裹。",
    # ── R39（#33 verify R38 第 5、9 列）：神諭結構上量不到的外流 ──
    ("ci-log-filter-bypass-r39-strict-group-proc-ppid-fd1.yml", "group writes to proc-ppid-fd1"):
        "`/proc/$PPID/fd/1` 在 runner 上是 runner 自己的 log；在神諭裡 `$PPID` 是神諭行程，它的 fd 1 不在神諭擷取的輸出裡。",
    ("ci-log-filter-bypass-r39-strict-group-dev-tty.yml", "group writes to dev-tty"):
        "`/dev/tty` 是控制終端；神諭與 GitHub runner 都沒有，寫入失敗、錯誤訊息在群組裡進管線。lint 擋下是保守的方向"
        "（控制終端存在的 runner——自架、互動式——寫進去的東西不經過濾）。",
    ("ci-log-filter-bypass-r39-env-pythonwarnings-expression.yml", "PYTHONWARNINGS from the PR title"):
        "神諭的 `python3` 是 shell stub，不解析 `PYTHONWARNINGS`；真的 CPython 會把不合法的值印到管線右端的 stderr（協調者實跑）。",
    ("ci-log-filter-bypass-r39-env-pythonwarnings-expression-default.yml", "PYTHONWARNINGS from the PR title"): "同上：stub。",
    ("ci-log-filter-bypass-r39-run-export-pythonwarnings.yml", "export PYTHONWARNINGS in run"): "同上：stub。",
    ("ci-log-filter-bypass-r39-github-event-expression-in-run.yml", "event expression in the group"):
        "神諭不代換 runner 運算式（值只有 runner 知道）：`${{ … }}` 在 bash 眼中是錯誤的替換，量不到代換之後的注入（R38 第 14 列）。",
    ("ci-log-filter-bypass-r39-github-head-ref-in-run-default.yml", "head_ref expression in a piped line"): "同上：不代換運算式。",
    ("gen-d-yaml-ghexpr-plain.yml", "d-yaml-ghexpr-plain"):
        "同上：產生語料 d 組的 `echo \"${{ github.event.pull_request.title }}\" | …`——真的注入形狀，R39 起兩種模式都擋；神諭不代換運算式。",
    # ── R39（R38 第 11 列）：群組規則的保守誤擋，逐條揭露（放寬會動到「恰好一對大括號、前綴只收 `set`」的論證）──
    ("ci-log-filter-restrict-r39-strict-function-def.yml", "function def"):
        "群組內定義函式：多一對大括號。群組規則只收恰好一對（`case` 模式、陣列裡的大括號不是保留字，計深度要判斷那個）。",
    ("ci-log-filter-restrict-r39-strict-github-env-group.yml", "github env group"): "同上：巢狀的 `{ …; } >> \"$GITHUB_ENV\"`。",
    ("ci-log-filter-restrict-r39-strict-two-groups.yml", "two groups"): "同上：一個 step 兩個群組。",
    ("ci-log-filter-restrict-r39-strict-cd-before-group.yml", "cd before group"):
        "群組前只收 `set` 前綴：`cd`、`export` 放進群組或改用 `working-directory:`／`env:`。",
    ("ci-log-filter-restrict-r39-strict-export-before-group.yml", "export before group"): "同上。",
    # ── R39 opsweep 存活者的殺法 fixture ──
    ("ci-log-filter-bypass-r39-env-shellopts-expression.yml", "SHELLOPTS from an expression"):
        "神諭不設 runner 運算式的值（`SHELLOPTS: ${{ … }}` 在沙箱裡不存在），量不到它可能開的 xtrace；這張的用途是殺 `_env_names` 的突變體。",
    ("ci-log-filter-restrict-r39-strict-group-dotdot-stderr.yml", "group writes through dotdot"):
        "`/dev/fd/../stderr`：`..` 經過 /dev 就不給群組豁免（fail-closed）。bash 寫到群組自己的 stderr（macOS）或寫不出去（Linux），不外流。",
    # ── R39（R38 第 13 列）：殺 `_cmdsub_end_case` 四條存活突變的 fixture——原碼保守判 RULE（命令替換裡的 `shopt -s extglob`
    # 改變之後的詞法，本 lint 不追蹤就擋），bash 照常執行、不外流 ──
    ("ci-log-filter-restrict-r39-cmdsub-case-esac-at-cmd.yml", "cmdsub case esac at cmd"):
        "命令替換裡 `shopt -s extglob`：保守擋（見 `restrict-r37p-*` 的同類理由）；這張的用途是殺 `_cmdsub_end_case` 的突變體。",
    ("ci-log-filter-restrict-r39-cmdsub-case-hash-word-start.yml", "cmdsub case hash word start"): "同上。",
    ("ci-log-filter-restrict-r39-cmdsub-case-paren-branch.yml", "cmdsub case paren branch"): "同上。",
    ("ci-log-filter-restrict-r39-cmdsub-case-herestring.yml", "cmdsub case herestring"): "同上。",
}
# **只在沒有 /proc 的平台上成立**的已知分歧（R39，#33 verify R38 第 1、5 列）：macOS 沒有 `/proc`，`/dev/fd` 也不是指向
# `/proc/self/fd` 的 symlink，這幾個外流在本機量不到、判誤擋。Linux（CI）上**不列入**——在那裡神諭必須看到外流、判一致，
# 否則就是 lint 擋錯了或 fixture 寫錯了。R38 的教訓：ground truth 在 CI 的平台上量，本機數字要註明平台。
KNOWN_DISAGREE_WITHOUT_PROC = {
    ("ci-log-filter-bypass-r39-strict-group-proc-pid-fd1.yml", "group writes to proc-pid-fd1"):
        "`/proc/$$/fd/1`：本機沒有 /proc。Linux 上 `$$` 是外層 shell，那個 fd 就是 step log。",
    ("ci-log-filter-bypass-r39-strict-group-exec-proc-pid.yml", "group writes to exec-proc-pid"): "同上：`exec >/proc/$$/fd/2`。",
    ("ci-log-filter-bypass-r39-fd-dotdot-dev-target.yml", "dotdot path under /dev"):
        "`/dev/fd/../../self/fd/2`：Linux 的 `/dev/fd` 是指向 `/proc/self/fd` 的 symlink，實際是 stderr；本機沒有那個 symlink。",
}
if not os.path.isdir("/proc/self/fd"):
    KNOWN_DISAGREE.update(KNOWN_DISAGREE_WITHOUT_PROC)

# lint 自己的宣告正規式（與 `lint-ci-log-filter.sh` 的 `LOGFILTER_RE` 同形）。這裡只用它判**文字長相**；
# 「那段文字是不是真的不會被執行」由差分決定，不靠任何一支的詞法分析。
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")

TIMEOUT_S = 5
# `$PR_TITLE` 的值：**「有沒有洩漏」是繞過判定的第三個條件**。lint 放行 ∧ runner 沒接管線，
# 只說明「沒過濾」；要構成繞過還得真的把 fork 可控的文字印出去。少了這一條，任何「lint 以為有管線、
# 但那一行根本沒執行」的構造都會被誤報成繞過（R31 自查：產生語料上 60 筆假指控全屬此類）。
PR_MARKER = "ORACLE-PR-TITLE-MARKER"
# 判定表的**種類**（#33 verify R34 requirements F3）：每一列的判定都必須以其中之一開頭（`main()` 逐列 assert）。
# CHANGELOG 的「判定表有 N 種」由 `lint-changelog-counts.sh` 讀這個常數驗——前一版那一句量的是 CHANGELOG 自己打的字面清單，
# 永遠抓不到 CHANGELOG 與神諭分岔。「不一致」的兩種各自帶後綴（繞過／誤擋），所以這裡列的是完整前綴。
# 形狀像已知類別、`--strict` 卻放行 ⇒ 不是已知，是真繞過（計入不一致、rc=1）。
STRICT_MISS = "不一致：繞過（形狀像已知類別 %s，但 `--strict` 也放行——已知類別的定義是 CI 模式擋得下）"
# **擋下的原因必須是外流本身**（R39，#33 verify R38 第 7 列）：前一版只查「`--strict` 擋下這個 step」。DA 的反例是
# `set -Eeuo pipefail`（`-E` 是一個沒揭露的誤擋）＋ 群組外一行外流：`--strict` 擋它只因為 `-E`，改成 `set -euo` 就放行，
# 外流仍在——誰修掉那個誤擋，繞過就重新打開，而沒有任何一張網會紅。所以已知類別另外要求：刪掉與外流無關的行之後，
# `--strict` 仍然擋下（見 `reduce_leaking_run`、`strict_blocks_text`）。
CAUSE_MISS = ("不一致：繞過（形狀像已知類別 %s，但 `--strict` 擋下這個 step 的原因與外流無關——刪掉與外流無關的行之後 "
              "`--strict` 放行）")
# xtrace 的外流行以 PS4 開頭。神諭把 PS4 設成自己的標記（run 區塊自己改 PS4 時認不出來——那時照一般外流歸類）。
# bash 依巢狀層數重複 PS4 的**第一個字元**，所以開頭是一個以上的 `+`。
PS4_MARK = "+ORACLE-XT "
XTRACE_LINE_RE = re.compile(r"^\++ORACLE-XT ")
XTRACE_LEAK = ("不一致：繞過（外流行是 xtrace 的輸出——xtrace 規則兩種模式都要求，不是 G 也不是 S-2）")
# bash 自己的錯誤訊息（展開期、重導向錯誤）：`<腳本路徑>: line N: …`。`run_script` 把臨時目錄換成 `<TMP>`。
# 「line」會被在地化（macOS 上實測是「列 5」），所以不比那個字，只比「腳本路徑: 一個字 行號: 」的形狀。
BASH_DIAG_RE = re.compile(r"^<TMP>/s\.sh: [^:\s]+ \d+: ")
# 接 neutralise 的那個 `|`／`|&`（S-2 的「包成群組」差分從這裡切開）。
NEUT_TAIL_RE = re.compile(r"\|&?[ \t]*python3[ \t]+[^\n]*neutralise\.py")
VERDICT_KINDS = ("一致", "不一致：繞過", "不一致：誤擋", "不可比", "量不到")
# **已知類別的判定不含任何 lint 規則的正規式副本**（R37，#33 verify R36 第 1 列）。前一版在這裡放了
# `STDERR_ROUTE_RE`（≈ lint 的 `FD_RE`）與 `NEUT_WITH_STDERR_RE`（≈ `STRICT_NEUT_RE`），分類「外流是誰印的」
# 靠它們——於是正規式以外的 fd 轉向，lint 放行、神諭也收進已知 G。現在 G 由差分決定（`classify_piped_leak`），
# S-2 由「`--strict` 的群組規則真的擋下這個 step」決定（跑一次 lint 看它的 RULE）。
# **兩個類別都要 `--strict` 擋得下才算已知**（#59／#60，R37 自 PR #61 移植）：G 與 S-2 的定義是「預設模式（量詞法）放行、
# CI 用的 `--strict` 擋下」。前一版的 G 只看差分，於是「`--strict` 也放行的同形繞過」一樣被算成已知、不改 rc——
# 現在那種判 `STRICT_MISS`（真繞過，rc=1）。
#
# 下面兩個是 lint 的**訊息**字面，不是規則：神諭用它們認出「這條 RULE 是哪一條規則」。lint 改了訊息而這裡沒跟上時，
# pipefail 那條會被當成一般 RULE 對帳（→ 誤擋、rc=1），S-2 的「`--strict` 的群組規則擋下了」查核會失敗（→ 繞過＋
# KNOWN-CLASS 過期、rc=1）——兩個方向都是 fail-closed，不會靜默放行。R37 移植 #61 時，`--strict` 的 `2>&1` 規則
# 換成群組規則，這裡的第二個字面跟著換。
PIPEFAIL_RULE_MSG = "卻沒有跑在 pipefail 之下"
STRICT_GROUP_RULE_MSG = "不是整個包在一個群組裡"
RULE_LINE_RE = re.compile(r":(\d+): RULE: ([^\n]*)")
# **耦合檢查**（R37 合併時加）：上面兩個字面必須真的出現在 lint 裡。R37 合併 r37a 與 r37b 時，r37b 把 `2>&1` 那條的訊息
# 改寫了、這裡沒跟上——上一段說那是 fail-closed，但它只會讓某張 fixture 碰巧變紅、不會說出原因。直接查字面，對不上就
# 具名失敗。
_LINT_SRC = LINT.read_text(encoding="utf-8", errors="replace") if LINT.is_file() else ""
for _msg in (PIPEFAIL_RULE_MSG, STRICT_GROUP_RULE_MSG):
    if _msg not in _LINT_SRC:
        sys.exit("✗ oracle.py 用來認 RULE 的字面「%s」不在 %s 裡——lint 改了訊息，這裡要同步改" % (_msg, LINT))
# 已知類別在 repo 自己的 fixture 集（不給檔案參數）上的**確切**條數（R37，R36 第 2 列；同 selftest 門檻 R24 F9 的理由：
# 寫成 `>=` 而實際更高時，那個差額沒有網——刪掉一張 G 範例 fixture 仍然綠）。must-fail 探針不算在內。
FIXTURE_CLASS_TOTALS = {"G": 8, "S-2": 3}
# must-fail 探針的確切張數（同理：刪掉一張探針＝少一條負對照，必須立刻紅）。
FIXTURE_MUSTFAIL_TOTAL = 8
KNOWN_CLASS_RE = re.compile(r"^# KNOWN-CLASS: (\S+)", re.M)
MUSTFAIL_RE = re.compile(r"^# ORACLE-MUST-FAIL: (.+?)\s*$", re.M)
# 差分用的中性命令：單獨一行是合法的空操作（rc=0），接在懸空的 `|`／`|&` 後面則是**語法錯誤**——`!` 只能出現在
# 管線開頭。所以「換掉的範圍少了管線的上游那一段」不會安靜地變成一條新管線，而是被 `bash -n` 當場抓到（R37 實測 bash 5.3）。
NEUTRAL_CMD = "! ! :"

STUB = '''#!/bin/sh
for a in "$@"; do case "$a" in *neutralise.py) echo "called $a" >> "$ORACLE_MARK";; esac; done
cat >/dev/null 2>&1; exit 0
'''

# DEBUG trap：`PIPESTATUS` 在**下一個**命令之前才反映剛結束的 pipeline，所以記錄的是「上一個命令」。
# 最後一個 pipeline 需要「之後還有一個命令」才記得到——那個收尾命令用 **EXIT trap**，不是在腳本
# 尾端補一行文字。
#
# **R32 DA-6：這件事是本輪整份報告的前提，而前一版把它做成了文字。** 前一版在 run 區塊後面接
# `"\n:\n"`，於是**未終止的 heredoc 會把那個 `:` 一起吞掉**——最後一個 pipeline 因此沒有下一個
# 命令、PIPESTATUS 沒被讀到、神諭回報「量不到」。而「量不到」不改變 rc，所以 CI 全綠。
# 實測差別（468 檔產生語料）：文字哨兵 `一致 408、不一致 0、量不到 60`；EXIT trap
# `一致 413、不一致 55、量不到 0`。**那個被宣傳成「不一致 0」的數字，量到的是儀器答不出來。**
# EXIT trap 不是腳本正文的一部分，heredoc 的資料區吞不掉它——這是「非文字哨兵」的意思。
PRELUDE = '''set -T
__orc_prev=""
trap '[ ${#PIPESTATUS[@]} -ge 2 ] && case "$__orc_prev" in *neutralise.py*) echo "piped" >> "$ORACLE_MARK";; esac; __orc_prev=$BASH_COMMAND' DEBUG
trap ':' EXIT
'''


def pick_bash():
    for cand in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("找不到 bash")


def run_script(run, bash, stub_bin, yaml_env=None):
    """跑一次 run 區塊，回傳 (verdict, observable, leaked, marker_lines)。
    verdict: 'piped' / 'called-unpiped' / 'not-invoked' / 'timeout'
    observable: 差分用的可觀察結果（rc, stdout, stderr, mark 內容）——逾時的那次不拿來差分。
    leaked: (stdout 有 PR 文字, stderr 有 PR 文字)。
    marker_lines: (stdout, stderr) 各自「含 PR 文字的行」的多重集合（Counter），臨時目錄路徑換成 `<TMP>`——
      已知類別 G 的差分比的是它（`classify_piped_leak`）：兩次執行的臨時目錄不同，bash 的錯誤訊息又帶腳本路徑。
    yaml_env: 從 YAML `env:` 收來的變數（R37，R36 第 8 列）；神諭自己的 PATH／HOME／PR_TITLE／ORACLE_MARK 一律蓋過它。"""
    with tempfile.TemporaryDirectory() as d:
        mark = os.path.join(d, "mark")
        open(mark, "w").close()
        script = os.path.join(d, "s.sh")
        with open(script, "w") as fh:
            # 收尾命令由 PRELUDE 的 `trap ':' EXIT` 提供——**不要**在這裡再補文字，
            # 那正是 R32 DA-6 抓到的缺陷（heredoc 會吞掉它）。
            fh.write(PRELUDE); fh.write(run); fh.write("\n")
        env = dict(yaml_env or {})
        env.update({"PATH": stub_bin + ":/usr/bin:/bin", "ORACLE_MARK": mark,
                    "PR_TITLE": PR_MARKER, "HOME": d, "PS4": PS4_MARK})
        try:
            # stdin **一定要**是 /dev/null：繼承呼叫端的 stdin 會讓任何讀 stdin 的指令卡住，
            # 於是「量不到」變成隨呼叫環境而定的東西（R31 自查：同一個 fixture 在終端機下逾時、
            # 在 pipe 下不逾時）。runner 的 step stdin 也不是終端機。
            r = subprocess.run([bash, script], env=env, cwd=d, capture_output=True,
                               stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return "timeout", None, (False, False), None
        got = open(mark).read().split("\n")
        # 分開記 stdout 與 stderr：外流走哪一條流是歸類的輸入（S-2 只可能走 stderr；管線自己印到 stdout 一律是繞過）。
        leaked = (PR_MARKER.encode() in r.stdout, PR_MARKER.encode() in r.stderr)
        obs = (r.returncode, r.stdout, r.stderr, sorted(got))
        mlines = tuple(collections.Counter(l.replace(d, "<TMP>") for l in s.decode("utf-8", "replace").split("\n")
                                           if PR_MARKER in l) for s in (r.stdout, r.stderr))
        if "piped" in got:
            return "piped", obs, leaked, mlines
        if any(l.startswith("called ") for l in got):
            return "called-unpiped", obs, leaked, mlines
        return "not-invoked", obs, leaked, mlines


MARKER_RE = re.compile(r"#\s*LOG-FILTER:\s*(?:in-process|none — .+)")


def real_declaration(run, bash, stub_bin, baseline, yaml_env=None):
    """run 區塊裡有沒有**真的**宣告：把候選文字**從 `#` 切到行尾**再跑一次，可觀察結果完全相同
    ⟹ 那段文字既不被執行也不被當資料消費 ⟹ 它是註解。

    這是 R30 MB-2 的修法。前一版用裸子字串，於是 heredoc 內文裡的假宣告把一個真繞過認證成「一致」。
    差分法不依賴任何一支的詞法分析——判準是 bash 自己的行為。
    切到行尾（而不是刪整行）是因為宣告可以跟程式碼同行：`echo x;# LOG-FILTER:none — …`。
    """
    if baseline is None:
        return False                       # 量不到就不當成宣告（fail-closed）
    lines = run.split("\n")
    for i, l in enumerate(lines):
        m = MARKER_RE.search(l)
        if not m:
            continue
        probe = "\n".join(lines[:i] + [l[:m.start()]] + lines[i + 1:])
        v, obs, _leak, _ml = run_script(probe, bash, stub_bin, yaml_env)
        if v != "timeout" and obs == baseline:
            return True
    return False


def _bash_n(text, bash):
    """`bash -n` 的 (rc, 第一則訊息)，腳本路徑正規化——拿來比較「換掉之前／之後的語法狀態是否相同」。"""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.sh")
        with open(p, "w") as fh:
            fh.write(PRELUDE); fh.write(text); fh.write("\n")
        try:
            r = subprocess.run([bash, "-n", p], env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return 124, "bash -n 逾時"          # 當成語法狀態不明：呼叫端會判不完整／差分不可比（fail-closed）
        return r.returncode, r.stderr.replace(p, "<S>").split("\n")[0]


def _continues(line, bash):
    """這一行與下一行是不是**同一條邏輯行**。兩種情形：
      · 行尾奇數個反斜線（續行；`bash -n` 對它不報錯，所以另外用文字判）。
      · **由 bash 判**：這一行單獨不完整、但後面接一行 `:` 就完整了 ⟹ 它以 `|`、`|&`、`&&`、`||` 懸空（後面帶註解也一樣）。
        `if …; then`、`{`、未收的引號與 `$(` 接了 `:` 仍不完整 ⟹ 不算——那些是複合命令的開頭，不是同一條邏輯行。"""
    if re.search(r"(?<!\\)(?:\\\\)*\\$", line):
        return True
    if not line.strip():
        return False
    return (_bash_n(line, bash)[0] != 0 and _bash_n(line + "\n:", bash)[0] == 0
            and _dangling_op(line) != "andor")


def _dangling_op(line):
    """懸空的是 `|`／`|&`（同一條管線）還是 `&&`／`||`（and-or 串的下一條命令）——R39：前一版兩者都算同一條邏輯行，
    `a | python3 …neutralise.py &&` 換行 `echo "$PR_TITLE"` 的差分把下一行那條**別的命令**一起換掉，外流跟著消失、被錯判成
    「管線自己印的」（實為 G，`known-r39-g-andand-continuation`）。用 shlex 取最後一個標點詞元；取不出來回 None（照舊當成續行）。"""
    try:
        lx = shlex.shlex(line, posix=True, punctuation_chars=True)
        toks = list(lx)
    except ValueError:
        return None
    last = toks[-1] if toks else ""
    return "pipe" if last in ("|", "|&") else "andor" if last in ("&&", "||") else None


def neutralise_spans(run, bash):
    """含 `neutralise.py` 字樣的實體行，各自擴成它所在的邏輯行（`_continues` 往上、往下接），回傳合併後的 [(s, e)]（含端點、0-based）。
    `neutralise.py` 是**子字串**，不是 lint 的任何規則：它就是「接 neutralise」的定義本身（stub 也這樣認）。"""
    lines = run.split("\n")
    spans = []
    for i, l in enumerate(lines):
        if "neutralise.py" not in l:
            continue
        s = e = i
        while s > 0 and _continues(lines[s - 1], bash):
            s -= 1
        while e + 1 < len(lines) and _continues(lines[e], bash):
            e += 1
        if spans and s <= spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], max(spans[-1][1], e))
        else:
            spans.append((s, e))
    return spans


def classify_piped_leak(run, bash, stub_bin, yaml_env, base_mlines):
    """「lint 放行 ∧ bash 建了接 neutralise 的管線 ∧ PR 文字外流」：**外流是誰印的**（R37，#33 verify R36 第 1 列）。

    差分：把含 `neutralise.py` 的邏輯行換成 `NEUTRAL_CMD`（行數不變——錯誤訊息裡的行號才對得上）再跑一次，
    逐條比對含 PR 文字的行（stdout／stderr 分開、計重數）。回傳其中一種：
      ("G", None)                      外流原封不動 ⟹ 另一條命令印的（lint 限制第 2 條：一條管線＝整個區塊已過濾）
      ("pipeline", (streams, g_part))  有一部分跟著管線消失 ⟹ **管線自己外流**；streams ⊆ {"stdout","stderr"}，
                                       g_part = 換掉之後仍有外流（同一 step 裡另有別的命令也印了）
      ("unmeasured", 原因)             差分不可比——**絕不歸 G**（fail-closed 的方向），由呼叫端記成「量不到」
    判準只有 bash 的行為與 `neutralise.py` 這個子字串，**沒有**任何以 `>&2`、`/dev/stderr`、`xtrace` 為字面的正規式。

    第三個回傳值是差分用到的範圍與換掉之後的外流行（`(spans, ml)`；"unmeasured" 時是 None）——S-2 的機制差分與
    已知類別的原因檢查要用。"""
    spans = neutralise_spans(run, bash)
    if not spans:
        return "unmeasured", "找不到含 neutralise.py 的行可以換掉", None
    lines = run.split("\n")
    base_n = _bash_n(run, bash)
    # 換掉之後必須語法完整，或與原腳本**同一個**語法錯誤（那個錯誤不是換掉造成的）。只比 rc 為 0 的那一邊不看訊息：
    # 原腳本的 heredoc 沒有內文時 `bash -n` 會印「here-document delimited by end-of-file」警告而 rc=0，換掉之後警告消失——
    # 那是換掉的本意，不是語法被切斷（R37 在產生語料的 60 個折疊 heredoc 檔上實測到這一點）。
    if not _syntax_ok(_neutralised(lines, spans), base_n, bash):
        # **多行群組**（R39，#33 verify R38 第 3 列）：`{` ⏎ … ⏎ `} 2>&1 | python3 …` 的邏輯行只有 `}` 那一行，
        # 換掉它 `{` 就沒收——前一版因此判「量不到」，而「量不到」不改 rc：lint 與神諭兩張網同時看不到那個外流。
        # 把範圍往上擴到語法完整為止（取最短的那個）；擴進來的是那條管線的上游（群組本體），差分量的仍是「整條管線」。
        for j in range(len(spans)):
            s, e = spans[j]
            lo = spans[j - 1][1] + 1 if j else 0
            for s2 in range(s - 1, lo - 1, -1):
                trial = spans[:j] + [(s2, e)] + spans[j + 1:]
                if _syntax_ok(_neutralised(lines, trial), base_n, bash):
                    spans = trial
                    break
            if _syntax_ok(_neutralised(lines, spans), base_n, bash):
                break
        else:
            return "unmeasured", "換掉接 neutralise 的邏輯行後語法壞掉（heredoc、if/fi、引號被切斷）——差分不可比", None
    v, _obs, _leak, ml = run_script(_neutralised(lines, spans), bash, stub_bin, yaml_env)
    if v == "timeout":
        return "unmeasured", "換掉之後的腳本逾時 %ds" % TIMEOUT_S, None
    if v != "not-invoked":
        return "unmeasured", "換掉之後 neutralise 仍被呼叫（%s）——範圍沒涵蓋到那條管線，差分不可比" % v, None
    if any(ml[k] - base_mlines[k] for k in (0, 1)):
        return "unmeasured", "換掉之後出現原本沒有的外流行——控制流被改變，差分不可比", None
    contrib = [name for k, name in ((0, "stdout"), (1, "stderr")) if base_mlines[k] - ml[k]]
    if not contrib:
        return "G", None, (spans, ml)
    return "pipeline", (contrib, bool(ml[0] or ml[1])), (spans, ml)


def _neutralised(lines, spans):
    """把每個範圍換成 `NEUTRAL_CMD`（範圍內其餘行清空，行數不變）。"""
    out = list(lines)
    for s, e in spans:
        out[s] = NEUTRAL_CMD
        for k in range(s + 1, e + 1):
            out[k] = ""
    return "\n".join(out)


def _syntax_ok(probe, base_n, bash):
    pn = _bash_n(probe, bash)
    return pn[0] == 0 or pn == base_n


def _pipe_to_pipeamp(line):
    """引號外的單一 `|`（不是 `||`、`|&`、`>|`）換成 `|&`——等於在管線的每一段尾端補 `2>&1`。
    只做引號與逃脫的追蹤：換錯（`case` 模式、`$(…)` 裡）會讓 `bash -n` 報錯，呼叫端就不當成 S-2（fail-closed）。"""
    out, q, i = [], None, 0
    while i < len(line):
        c = line[i]
        if c == "\\" and q != "'":
            out.append(line[i:i + 2]); i += 2; continue
        if q:
            if c == q:
                q = None
        elif c in "'\"":
            q = c
        elif (c == "|" and line[i + 1:i + 2] not in ("|", "&") and (i == 0 or line[i - 1] not in "|>")):
            out.append("|&"); i += 1; continue
        out.append(c); i += 1
    return "".join(out)


def s2_mechanism(run, spans, bash, stub_bin, yaml_env, base_ml, neutral_ml):
    """S-2 的**機制**（R39，#33 verify R38 第 6 列）。前一版的 S-2 只看「管線自己只從 stderr 外流 ∧ `--strict` 的群組規則
    擋下」，而群組規則擋下所有非群組管線，後半幾乎恆真——`>/dev/fd/2 2>&1 |`、`>&02`、`set -eo xtrace` 這些 fd／xtrace 規則
    該擋的外流，只要那條規則失效，就被收進 S-2（R36 第 1 列的問題從 G 搬到了 S-2）。現在 S-2 是兩種機制之一
    （封閉列舉，只有這兩種，不得依症狀相似類推）：
      "missing-2to1"  管線每一段尾端補上 `2>&1`（`|` → `|&`）之後，管線貢獻的 stderr 外流行全部消失，stdout 沒有多出外流。
      "early-error"   管線貢獻的外流行**全部**是 bash 自己的錯誤訊息（`<腳本>: line N: …`：展開期或重導向錯誤），
                      把 `|` 左邊整段包成群組 `{ …; } 2>&1 |` 之後全部消失——`2>&1` 在那些錯誤**之後**才生效（#60 第 2 類）。
    都不成立回 None：那不是「缺 `2>&1`」，而是補上也擋不住的外流（fd 轉向、另存的 fd…），由呼叫端判繞過。"""
    contrib = base_ml[1] - neutral_ml[1]
    lines = run.split("\n")
    base_n = _bash_n(run, bash)

    def gone(probe):
        if not _syntax_ok(probe, base_n, bash):
            return False
        v, _o, _l, ml = run_script(probe, bash, stub_bin, yaml_env)
        return v != "timeout" and not (contrib & ml[1]) and not (ml[0] - base_ml[0])

    a = list(lines)
    for s, e in spans:
        for k in range(s, e + 1):
            a[k] = _pipe_to_pipeamp(a[k])
    if gone("\n".join(a)):
        return "missing-2to1"
    if not all(BASH_DIAG_RE.match(l) for l in contrib):
        return None
    b = list(lines)
    for s, e in spans:
        text = "\n".join(b[s:e + 1])
        tails = list(NEUT_TAIL_RE.finditer(text))
        if not tails:
            return None
        m = tails[-1]
        b[s] = "{ " + text[:m.start()] + "\n} 2>&1 " + text[m.start():]
        for k in range(s + 1, e + 1):
            b[k] = ""
    return "early-error" if gone("\n".join(b)) else None


def reduce_leaking_run(run, spans, bash, stub_bin, yaml_env):
    """刪掉與外流無關的行（R39，#33 verify R38 第 7 列）：由上而下逐行試著清空範圍外的每一行，語法仍完整（或同一個錯誤）、
    neutralise 仍在管線上、PR 文字仍然外流，就保留這個刪除。貪婪、一輪——結果不一定最小，但每一行被留下都有原因
    （刪掉它外流就消失，或語法壞掉）。"""
    lines = run.split("\n")
    base_n = _bash_n(run, bash)
    keep = {k for s, e in spans for k in range(s, e + 1)}
    cur = list(lines)
    for i in range(len(lines)):
        if i in keep or not cur[i].strip():
            continue
        trial = cur[:i] + [""] + cur[i + 1:]
        p = "\n".join(trial)
        if not _syntax_ok(p, base_n, bash):
            continue
        v, _o, leaked, _ml = run_script(p, bash, stub_bin, yaml_env)
        if v == "piped" and (leaked[0] or leaked[1]):
            cur = trial
    return "\n".join(cur)


SYNTH_WORKFLOW = """name: t
on: pull_request
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - name: reduced
        shell: bash
        run: |2
"""


def strict_blocks_text(run_text):
    """`--strict` 擋不擋這段 run 文字：包成最小的 workflow（`shell: bash`、沒有 env；`|2` 顯式縮排，內文開頭的空白
    才不會被當成縮排）跑 lint。回傳擋下的理由（第一則非 pipefail 的 RULE 訊息，或 "PARSE"），沒擋回 None；
    lint fail-loud（rc=2）當成沒擋（fail-closed：量不到擋下就不給已知類別）。"""
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "reduced.yml"
        p.write_text(SYNTH_WORKFLOW + "".join(("          " + l if l else "") + "\n" for l in run_text.split("\n")),
                     encoding="utf-8")
        rs = run_lint(["--strict"], p)
    if rs.returncode == 2:
        return None
    msgs = [m for _ln, m in RULE_LINE_RE.findall(rs.stderr) if PIPEFAIL_RULE_MSG not in m]
    if msgs:
        return msgs[0]
    return "PARSE" if ": PARSE: " in rs.stderr else None


def _env_of(node):
    """mapping 節點的 `env:`（純量值才收；鍵非空、鍵不含 `=`、鍵值合併不含 NUL byte；含 `${{` 的值只有 runner 知道，不設）。R37，R36 第 8 列。"""
    if not isinstance(node, yaml.MappingNode):
        return {}
    e = {kk.value: vv for kk, vv in node.value if isinstance(kk, yaml.ScalarNode)}.get("env")
    if not isinstance(e, yaml.MappingNode):
        return {}
    return {k.value: v.value for k, v in e.value
            if isinstance(k, yaml.ScalarNode) and isinstance(v, yaml.ScalarNode)
            and k.value and "=" not in k.value and "\0" not in k.value + v.value and "${{" not in v.value}


def steps_with_lines(text):
    """[(job, step-name, run, (start_line, end_line), shell_note, env)]，行號 0-based，用 yaml.compose 的 mark 取範圍。
    env 是 workflow → job → step 三層 `env:` 依序覆蓋的結果（R37，R36 第 8 列：`SHELLOPTS: xtrace` 之類從這裡進來）。"""
    root = yaml.compose(text)
    all_lines = text.split("\n")
    out = []
    if not isinstance(root, yaml.MappingNode):
        return out
    wf_env = _env_of(root)
    def _shell_of(node):
        """`defaults: run: shell:` 的值（沒有就 None）。"""
        if not isinstance(node, yaml.MappingNode):
            return None
        d = {kk.value: vv for kk, vv in node.value if isinstance(kk, yaml.ScalarNode)}.get("defaults")
        if not isinstance(d, yaml.MappingNode):
            return None
        r = {kk.value: vv for kk, vv in d.value if isinstance(kk, yaml.ScalarNode)}.get("run")
        if not isinstance(r, yaml.MappingNode):
            return None
        sh = {kk.value: vv for kk, vv in r.value if isinstance(kk, yaml.ScalarNode)}.get("shell")
        return sh.value if isinstance(sh, yaml.ScalarNode) else "<非純量>" if sh is not None else None
    wf_shell = _shell_of(root)
    for k, v in root.value:
        if k.value != "jobs" or not isinstance(v, yaml.MappingNode):
            continue
        for jk, jv in v.value:
            if not isinstance(jv, yaml.MappingNode):
                continue
            jkv = {kk.value: vv for kk, vv in jv.value if isinstance(kk, yaml.ScalarNode)}
            job_shell = _shell_of(jv)
            job_env = dict(wf_env, **_env_of(jv))
            ro = jkv.get("runs-on")
            ro_text = " ".join(x.value for x in ro.value if isinstance(x, yaml.ScalarNode)) if isinstance(ro, yaml.SequenceNode) \
                else (ro.value if isinstance(ro, yaml.ScalarNode) else "")
            for sk, sv in jv.value:
                if sk.value != "steps" or not isinstance(sv, yaml.SequenceNode):
                    continue
                # **step 的行範圍用「下一個 step 的起點 - 1」**，不用 `end_mark`：PyYAML 的 end_mark 指向
                # 下一個 token 的起點，也就是**下一個 step 的第一行**——用它會讓相鄰 step 的範圍重疊，
                # 而範圍一重疊，逐 step 的 RULE／PARSE 歸屬就整批錯位（R31 自查：每個檔的第一個 step
                # 都被算成 RULE-red）。
                sibs = [st for st in sv.value if isinstance(st, yaml.MappingNode)]
                # 先把每個 step 的**起點**都調整好（bare `-`：鍵寫在下一行時 PyYAML 的 mapping 起點在
                # **鍵**那一行，而 lint 報的是 **dash** 那一行），**再**用「下一個起點 - 1」算終點。
                # 兩步不能合成一步：先算終點就會讓 dash 那一行同時落在兩個 step 的範圍裡（R31 自查）。
                starts = []
                for st in sibs:
                    st0 = st.start_mark.line
                    while st0 > 0 and re.match(r"^\s*-\s*$", all_lines[st0 - 1]):
                        st0 -= 1
                    starts.append(st0)
                for idx, st in enumerate(sibs):
                    kv = {kk.value: vv for kk, vv in st.value if isinstance(kk, yaml.ScalarNode)}
                    run = kv.get("run")
                    if not isinstance(run, yaml.ScalarNode):
                        continue
                    name = kv["name"].value if isinstance(kv.get("name"), yaml.ScalarNode) else "<未命名>"
                    end = (starts[idx + 1] - 1) if idx + 1 < len(sibs) else sv.end_mark.line
                    # **神諭只會用 bash 跑**（#33 verify R34 security S-3、DA n4／n4b）：runner 實際用的 shell
                    # 由 step `shell:` → job `defaults.run.shell` → workflow `defaults.run.shell` 決定；都沒寫時，
                    # container 裡是 sh、Windows runner 是 pwsh。這些情況神諭的判定沒有意義 ⇒ 不可比，並寫出原因。
                    st_sh = kv.get("shell")
                    eff = (st_sh.value if isinstance(st_sh, yaml.ScalarNode) else None) or job_shell or wf_shell
                    if eff is not None:
                        note = None if eff.strip() == "bash" else "shell 是 %r" % eff
                    elif "container" in jkv:
                        note = "job 跑在 container 裡、沒寫 shell（預設 sh）"
                    elif "windows" in ro_text.lower() or "${{" in ro_text:
                        note = "runs-on 是 %r、沒寫 shell（Windows 預設 pwsh；運算式無法靜態判定）" % ro_text
                    else:
                        note = None
                    out.append((jk.value, name, run.value, (starts[idx], end), note, dict(job_env, **_env_of(st))))
    return out


def yaml_declaration(text, a, b, block_bodies):
    """YAML 層的宣告來源：step 行範圍內**不在 block scalar 內文裡**的註解行，或 `run:` 行尾註解。
    這兩種 runner 結構上看不到，不需要差分。`block_bodies` 是 block scalar 內文的行號集合。"""
    lines = text.split("\n")
    for i in range(a, min(b + 1, len(lines))):
        if i in block_bodies:
            continue
        l = lines[i]
        if LOGFILTER_RE.match(l):
            return True
        m = re.match(r"^\s*(?:- )?[\w-]+:\s*(?:\"[^\"]*\"|'[^']*'|[^#]*?)\s(#.*)$", l)
        if m and LOGFILTER_RE.match(" " + m.group(1)):
            return True
    return False


def block_scalar_body_lines(text):
    """block scalar 內文的行號集合（給 `yaml_declaration` 排除用）——內文不是 YAML 註解。"""
    lines = text.split("\n")
    hdr = re.compile(r"^(\s*)(?:- )?[\w-]+:\s*[|>][+-]?\d?[+-]?\s*(?:#.*)?$")
    out, deeper = set(), None
    for i, l in enumerate(lines):
        ind = len(l) - len(l.lstrip())
        if deeper is not None:
            if not l.strip() or ind > deeper:
                out.add(i); continue
            deeper = None
        m = hdr.match(l)
        if m:
            deeper = len(m.group(1)) + (2 if l.lstrip().startswith("- ") else 0)
    return out


def run_lint(largs, f):
    return subprocess.run(["bash", str(LINT)] + largs + [str(f)], capture_output=True, text=True)


def check_file(f, text, bash, stub_bin):
    """一個 workflow 檔的逐 step 對帳。回傳 dict：rows、disagree、stale、unmeasured、seen（歸類的 Counter）、
    failures（這個檔讓神諭 rc=1 的每一個理由，一句一條——must-fail 探針拿它比對宣告的理由）、
    cls_stale、cls_undeclared（已知類別檔頭宣告與神諭實際歸類的落差，見下方類別閘門）。"""
    res = {"rows": [], "disagree": [], "stale": [], "unmeasured": [], "seen": collections.Counter(), "failures": [],
           "cls_stale": [], "cls_undeclared": []}
    rows = res["rows"]
    expect = (re.search(r"^# EXPECT: (\S+)", text, re.M) or [None, ""])[1] if "# EXPECT:" in text else ""
    try:
        steps = steps_with_lines(text)
    except yaml.YAMLError:
        rows.append((f.name, "-", "YAML-FAIL", "-", "不可比（PyYAML 也拒絕）"))
        return res
    # **用 fixture 宣告的模式跑 lint**（`# LINT-ARGS:`，R35）：前一版一律用預設模式，於是 `--strict` 的 fixture
    # 被放到它沒宣告的模式下量——一個嚴格模式該擋的 step 被讀成「lint 放行」，還被算進已知類別 S-2。
    largs = (re.search(r"^# LINT-ARGS: (.+)$", text, re.M) or [None, ""])[1].split()
    r = run_lint(largs, f)
    # **逐 step 歸屬用行號，不用名稱**：lint 印的是它自己解析出來的 step 名，而 `name: |` 這種
    # block scalar 的名字在 lint 眼中是 `|`、在 PyYAML 眼中是內文——名稱比對必然失配，於是
    # 一個真的被 lint 擋下來的 step 會被神諭讀成 `lint=pass` 並反過來指控 lint 放行（R31 自查）。
    # RULE 逐條收（行號＋訊息），不收成行號集合：同一 step 的所有 RULE 都掛在 step 起始行，
    # 按行號扣掉 pipefail 那一行會把同一行的其他 RULE 一起扣掉（R37，#33 verify R36 第 18 列）。
    rules = [(int(ln), m) for ln, m in RULE_LINE_RE.findall(r.stderr)]
    parse_lines = {int(x) for x in re.findall(r":(\d+): PARSE: ", r.stderr)}
    # 已知類別的判準要看 `--strict` 的 RULE 與 PARSE（見 `classify_piped_leak` 的呼叫處）。檔案本身就是 `--strict` 時就是 `r`；
    # 否則要用時才跑一次（大多數檔永遠用不到）。rc=2 當成「沒擋」——量不到擋下就不給已知類別（fail-closed）。
    strict_cache = {}
    def strict_out():
        if "v" not in strict_cache:
            rs = r if "--strict" in largs else run_lint(["--strict"] + largs, f)
            strict_cache["v"] = (([], set()) if rs.returncode == 2 else
                                 ([(int(ln), m) for ln, m in RULE_LINE_RE.findall(rs.stderr)],
                                  {int(x) for x in re.findall(r":(\d+): PARSE: ", rs.stderr)}))
        return strict_cache["v"]
    def strict_blocks(in_step):
        """`--strict` 擋下這個 step：step 上有 pipefail 以外的 RULE（pipefail 管退出碼、不管外流），或 PARSE
        （step 內，或落在所有 step 範圍外的結構性 PARSE）。逐則訊息判斷，不用行號相減：同一個 step 可以同時吃
        pipefail 與群組兩條 RULE（行號相同）。"""
        srules, sparse = strict_out()
        return (any(in_step(ln) and PIPEFAIL_RULE_MSG not in m for ln, m in srules)
                or any(in_step(x) or not any(lo <= x <= hi for lo, hi in ranges) for x in sparse))
    bodies = block_scalar_body_lines(text)
    ranges = [(a + 1, b + 1) for _j, _n, _r, (a, b), _sh, _e in steps]
    # **一次算完**：落在任何一個 step 範圍外的 PARSE 才是結構性的（整檔不可信）。
    # 前一版在每個 step 內各算一次，於是別的 step 的 PARSE 讓這個 step 也變成 PARSE
    # （`bypass-duplicate-key` 的合規對照 step 被算成「PARSE ∧ piped」＝誤擋，R31 自查）。
    struct_parse = any(not any(lo <= x <= hi for lo, hi in ranges) for x in parse_lines)
    for _job, name, run, (a, b), shell_note, yenv in steps:
        key = (f.name, name, a + 1)     # **含行號**（#33 verify R34 DA n1）：同名 step 不得共用一個 key
        in_step = lambda ln: a + 1 <= ln <= b + 1
        step_rules = [m for ln, m in rules if in_step(ln)]
        # `[--strict]` 的 pipefail 規則管的是**退出碼被遮蔽**，不是 PR 文字外流——神諭量不到它（R35）。
        # **只在它是這個 step 唯一的 RULE 時**才判不可比（R37，R36 第 18 列）：前一版只要 step 起始行上有一條 pipefail
        # RULE 就整個 step `continue`，同一行的 fd 流向、`2>&1` 規則一起被藏起來、不做外流對帳。
        if step_rules and all(PIPEFAIL_RULE_MSG in m for m in step_rules):
            rows.append((f.name, name, "RULE-pipefail", "-", "不可比（`--strict` 的 pipefail 規則是這個 step 唯一的 RULE：量的是退出碼遮蔽，不是外流）"))
            continue
        if shell_note:
            rows.append((f.name, name, "-", "-", "不可比（%s——神諭只會用 bash 跑）" % shell_note))
            continue
        o, obs, leaked, mlines = run_script(run, bash, stub_bin, yenv)
        # step 範圍外的 PARSE 是**結構性**的（整檔不可信）→ 所有 step 都不可比；
        # 範圍內的 PARSE 只影響那一個 step。前一版對整檔一視同仁，於是
        # `bypass-duplicate-key` 的合規對照 step 被算成「PARSE ∧ piped」＝誤擋（R31 自查）。
        # **lint 自己 fail-loud（rc=2：檔案不存在／用法錯誤）不是 pass**（R32 DA-8）。
        # 前一版只看 stderr 裡的 RULE/PARSE 標記，rc=2 時兩者都沒有 ⇒ 落到 `pass` ⇒ 一個
        # 刻意的 fail-loud 被神諭讀成「lint 放行」。命名為 ERROR、歸不可比，不進一致也不進不一致。
        if r.returncode == 2:
            lint = "ERROR"
        else:
            lint = ("RULE-red" if step_rules
                    else ("PARSE" if (any(in_step(x) for x in parse_lines) or struct_parse) else "pass"))
        classes = []
        if o == "timeout":
            verdict = "量不到（逾時 %ds）" % TIMEOUT_S
            res["unmeasured"].append(key)
        elif lint == "ERROR":
            verdict = "不可比（lint rc=2：fail-loud，不是判定）"
        elif lint == "PARSE":
            if o == "piped" and expect != "parse-red":
                verdict = "不一致：誤擋（PARSE）"
            else:
                verdict = "不可比（fail-closed%s）" % ("，檔案自己宣告 parse-red" if expect == "parse-red" else "")
        elif lint == "pass" and o == "piped":
            # **「某處有管線」≠「沒有洩漏」**（R32 Codex 第 4 條／security S-3／requirements F4）：洩漏就要問是誰印的。
            # 前一版用兩條 lint 規則的正規式副本回答，R36 第 1 列證明那是按症狀收容（見 `classify_piped_leak`）。
            if not (leaked[0] or leaked[1]):
                verdict = "一致"
            else:
                kind, detail, ctx = classify_piped_leak(run, bash, stub_bin, yenv, mlines)
                if any(XTRACE_LINE_RE.match(l) for c in mlines for l in c):
                    # xtrace 的外流（R39，#33 verify R38 第 4、6 列）：前一版把 `command -p set -x` 之後的 `+ echo …` 收進 S-2，
                    # 訊息還說「缺 `2>&1`」——那條管線帶了 `2>&1`。xtrace 是 lint 兩種模式都要求的 fd 規則，漏了就是繞過。
                    verdict = XTRACE_LEAK
                elif kind == "unmeasured":
                    # **已觀察到外流、只是分類失敗 ⇒ 繞過，不是量不到**（R39，#33 verify R38 第 3 列）。前一版判「量不到」，
                    # 而量不到不改 rc：Codex 的多行群組輸入讓 lint 與神諭同時 rc=0。外流是 baseline 的事實，分類是額外的歸屬；
                    # 歸屬失敗不抵銷事實。
                    verdict = "不一致：繞過（PR 文字已經外流，來源分類量不到：%s——分類失敗不抵銷已觀察到的外流）" % detail
                elif kind == "G":
                    # 換掉接 neutralise 的邏輯行，外流原封不動 ⇒ 印它的是**另一條命令**——lint 明寫的「已知不涵蓋，第二組」第 2 條
                    # 「一條管線＝整個區塊已過濾」（Codex R32 第 4 條）。按類別記已知：整類在「什麼算已過濾」改掉的那一天一起翻。
                    if not strict_blocks(in_step):
                        verdict = STRICT_MISS % "G"
                    else:
                        why = strict_blocks_text(reduce_leaking_run(run, ctx[0], bash, stub_bin, yenv))
                        if why is None:
                            verdict = CAUSE_MISS % "G"
                        else:
                            verdict = ("不一致：繞過（已知類別 G：一條管線＝整個區塊已過濾——差分：換掉接 neutralise 的邏輯行後外流原封不動，"
                                       "限制第 2 條；刪掉與外流無關的行之後 `--strict` 仍擋：%s）" % why[:80])
                            classes = ["G"]
                else:
                    streams, g_part = detail
                    if "stdout" in streams:
                        verdict = "不一致：繞過（接 neutralise 的管線自己把 PR 文字印到 stdout——不是 G 也不是 S-2）"
                    elif any(in_step(ln) and STRICT_GROUP_RULE_MSG in m for ln, m in strict_out()[0]):
                        # 檔案本身是 `--strict` 時，這裡查的就是剛才放行它的同一次 lint ⇒ 結構上不可能成立——所以不需要另外的
                        # 「模式是不是 strict」判斷（那會是一條等價突變）。S-2 另外要求**機制**成立（`s2_mechanism`）與原因檢查。
                        mech = s2_mechanism(run, ctx[0], bash, stub_bin, yenv, mlines, ctx[1])
                        why = mech and strict_blocks_text(reduce_leaking_run(run, ctx[0], bash, stub_bin, yenv))
                        if not mech:
                            verdict = ("不一致：繞過（接 neutralise 的管線自己把 PR 文字印到 stderr，但每一段補上 `2>&1`、"
                                       "或（bash 自己的錯誤訊息時）左邊包成群組，外流都不消失——不是 S-2）")
                        elif why is None:
                            verdict = CAUSE_MISS % "S-2"
                        else:
                            verdict = ("不一致：繞過（已知類別 S-2%s：管線自己只從 stderr 外流——%s；預設模式不要求，"
                                       "刪掉與外流無關的行之後 `--strict` 仍擋：%s）"
                                       % ("＋G（同一 step 另有別的命令也印）" if g_part else "",
                                          "缺 `2>&1`（每一段補上就消失）" if mech == "missing-2to1"
                                          else "展開期／重導向錯誤早於 `2>&1` 生效（左邊包成群組就消失）", why[:80]))
                            classes = ["S-2"] + (["G"] if g_part else [])
                    else:
                        verdict = ("不一致：繞過（接 neutralise 的管線自己把 PR 文字印到 stderr，而 `--strict` 的群組規則"
                                   "沒有擋下這個 step——不是預設模式獨有的缺口，不是 S-2）")
        elif lint == "pass":
            decl = (yaml_declaration(text, a, b, bodies)
                    or real_declaration(run, bash, stub_bin, obs, yenv))
            if decl:
                verdict = "一致"
            elif leaked[0] or leaked[1]:
                verdict = "不一致：繞過"
            else:
                # lint 放行、runner 沒過濾，但這一次執行**沒有把 PR 文字印出去**——
                # 沒有洩漏就沒有繞過，可是也證不了「不會洩漏」。第三格，逐項具名。
                verdict = "量不到（沒有觀察到 PR 文字外流）"
                res["unmeasured"].append(key)
        elif o != "piped":
            verdict = "一致"
        elif leaked[0] or leaked[1]:
            # **有管線不等於沒有外流**（R35）：lint 擋下、bash 也確實建了接 neutralise 的管線，但 PR 文字
            # 仍然出去了（fd 轉向到 stderr、xtrace、管線以外的命令）——擋下是對的。前一版這一格一律判誤擋。
            verdict = "一致"
        else:
            verdict = "不一致：誤擋"
        if classes:
            res["seen"].update(classes)             # 已知**類別**：印出、計入「已知」、由檔頭宣告簽名（見下方的雙向閘門）
        elif verdict.startswith("不一致"):
            if key[:2] in KNOWN_DISAGREE:
                verdict += "（已知：%s）" % KNOWN_DISAGREE[key[:2]]
            else:
                res["disagree"].append(key)
                res["failures"].append("%s（第 %d 行）：%s" % (name, a + 1, verdict))
        elif key[:2] in KNOWN_DISAGREE:
            res["stale"].append(key)
            res["failures"].append("KNOWN_DISAGREE 過期：%s（第 %d 行）" % (name, a + 1))
        assert verdict.startswith(VERDICT_KINDS), verdict   # 判定表的種類是 VERDICT_KINDS（CHANGELOG 讀它）
        rows.append((f.name, name, lint, o, verdict))
    # **類別閘門是雙向的，數量釘死**（R37，#33 verify R36 第 2 列）。前一版只查「宣告了卻沒歸進去」（R34 security LOW-1），
    # 反方向不查、門檻又是「至少一條」——於是一張**沒有宣告**的正向 fixture 被歸進已知類別時 selftest 與神諭都綠
    # （DA 實測：`不一致 5（已知 5）`）。現在每個類別的歸類數必須**等於**檔頭 `# KNOWN-CLASS:` 的行數。
    declared = collections.Counter(KNOWN_CLASS_RE.findall(text))
    for c in sorted(set(declared) | set(res["seen"])):
        d_, s_ = declared[c], res["seen"][c]
        if d_ > s_:
            res["cls_stale"].append((f.name, c, d_, s_))
            res["failures"].append("KNOWN-CLASS 過期：%s（宣告 %d、歸類 %d）" % (c, d_, s_))
        elif s_ > d_:
            res["cls_undeclared"].append((f.name, c, d_, s_))
            res["failures"].append("歸了類卻沒宣告：%s（宣告 %d、歸類 %d）" % (c, d_, s_))
    return res


def main(argv):
    # 給定的檔案一律轉成絕對路徑：lint 會先 cd 到 plugin 目錄，相對路徑會變成「檔案不存在」（rc=2）。
    files = [pathlib.Path(a).resolve() for a in argv] or sorted(FIXTURES.glob("ci-log-filter-*.yml"))
    bash = pick_bash()
    ver = subprocess.run([bash, "-c", 'echo "$BASH_VERSION"'], capture_output=True, text=True).stdout.strip()
    print("bash: %s (%s)  管線判定：DEBUG trap + PIPESTATUS（bash 自己的剖析）" % (bash, ver))
    if LINT != (HERE / "lint-ci-log-filter.sh").resolve():
        print("⚠ ORACLE_LINT：對帳的是 %s（不是 repo 自己的 lint）" % LINT)
    rows, disagree, stale, unmeasured = [], [], [], []
    cls_stale, cls_undeclared, cls_count = [], [], collections.Counter()
    mf_rows, mf_report, mf_bad = [], [], []
    with tempfile.TemporaryDirectory(prefix="oracle-") as d:
        stub_bin = os.path.join(d, "bin"); os.mkdir(stub_bin)
        p = os.path.join(stub_bin, "python3"); open(p, "w").write(STUB); os.chmod(p, 0o755)
        # CI runner 的 sudo 是無密碼的；本機的會等密碼而讓整個 step 逾時（＝把量得到的變成量不到）。
        q = os.path.join(stub_bin, "sudo"); open(q, "w").write('#!/bin/sh\nexec "$@"\n'); os.chmod(q, 0o755)
        # **`sleep` 是空操作**（#33 verify R34 DA n6）：`sleep 6` 讓腳本超過 TIMEOUT_S，一個真繞過因此落進
        # 「量不到（逾時）」——逾時不改 rc。等待不改變 PR 文字有沒有外流，所以不讓它耗時。
        z = os.path.join(stub_bin, "sleep"); open(z, "w").write('#!/bin/sh\nexit 0\n'); os.chmod(z, 0o755)
        for f in files:
            text = f.read_text(encoding="utf-8")
            res = check_file(f, text, bash, stub_bin)
            mf = MUSTFAIL_RE.search(text)
            if mf:
                # **must-fail 探針**：這個檔的失敗是預期的，不計入總 rc；它**沒有**以宣告的理由失敗才算失敗。
                # 理由要比對，不只看「有沒有失敗」：以別的理由失敗的探針，量到的不是它宣稱要量的那個分支。
                # 理由可以出現在失敗訊息裡，也可以出現在同一檔某一列的判定裡（例：「量不到（…語法壞掉…）」讓宣告的 G 過期——
                # 失敗訊息只說「過期」，是哪一道守衛讓它量不到要看判定），但**一定要有失敗**。
                mf_rows += res["rows"]
                ok = bool(res["failures"]) and any(mf.group(1) in x for x in res["failures"] + [r[4] for r in res["rows"]])
                mf_report.append((f.name, mf.group(1), ok, res["failures"]))
                if not ok:
                    mf_bad.append(f.name)
                continue
            rows += res["rows"]
            disagree += res["disagree"]; stale += res["stale"]; unmeasured += res["unmeasured"]
            cls_stale += res["cls_stale"]; cls_undeclared += res["cls_undeclared"]
            cls_count.update(res["seen"])
    w = max(len(r[0]) for r in rows + mf_rows) if rows + mf_rows else 10
    for fn, name, lint, o, verdict in rows:
        print("%-*s  %-40s lint=%-9s oracle=%-14s %s" % (w, fn, name[:40], lint, o, verdict))
    n = len(rows)
    print("\n%d 個 step：一致 %d、不一致 %d（已知 %d）、不可比 %d、量不到 %d"
          % (n, sum(1 for r in rows if r[4] == "一致"),
             sum(1 for r in rows if r[4].startswith("不一致")), sum(1 for r in rows if "（已知" in r[4]),
             sum(1 for r in rows if r[4].startswith("不可比")), len(unmeasured)))
    if cls_count:
        print("已知類別：%s" % "、".join("%s %d" % (c, cls_count[c]) for c in sorted(cls_count)))
    rc = 0
    if disagree:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 之外的不一致（lint 與 runner 對同一個 step 說不同的話）：")
        for fn, name, ln in disagree: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if stale:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 裡的項目現在一致了（理由不再成立，移除它）：")
        for fn, name, ln in stale: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if unmeasured:
        # R32 requirements F1：前一版這一行的標題斷言「腳本逾時」，而列在下面的大多數是另一個原因
        # （「這一次執行沒有把 PR 文字印出去」）。標題不得斷言它沒量到的原因——兩個都寫，逐列自帶。
        print("\n⚠ 量不到（逾時、這一次執行沒有把 PR 文字印出去、或已知類別的差分不可比——各列自帶原因；"
              "不是繞過也不是一致，這一格存在本身就是揭露）：")
        for fn, name, ln in unmeasured: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if cls_stale:
        rc = 1
        print("\n✗ 檔頭宣告了已知類別、神諭卻沒把那麼多 step 歸進那一類（KNOWN-CLASS 過期——重判這個 fixture）：")
        for fn, c, d_, s_ in cls_stale: print("  - %s :: %s（宣告 %d、歸類 %d）" % (fn, c, d_, s_))
    if cls_undeclared:
        rc = 1
        print("\n✗ 神諭把 step 歸進了已知類別、檔頭卻沒有對應的 `# KNOWN-CLASS:`（歸了類卻沒宣告——"
              "已知類別不是免檢區，每一條都要有人在檔頭簽名）：")
        for fn, c, d_, s_ in cls_undeclared: print("  - %s :: %s（宣告 %d、歸類 %d）" % (fn, c, d_, s_))
    if mf_report:
        print("\nmust-fail 探針 %d 張（它們的失敗是預期的、不計入上面的數字；**沒有**以宣告的理由失敗才算失敗）：" % len(mf_report))
        for fn, name, lint, o, verdict in mf_rows:
            print("  %-*s  %-40s lint=%-9s oracle=%-14s %s" % (w, fn, name[:40], lint, o, verdict))
        for fn, reason, ok, fails in mf_report:
            print("  %s %s —— 宣告的理由「%s」%s" % ("✓" if ok else "✗", fn, reason, "出現" if ok else "沒有出現"))
            for x in fails:
                print("      · %s" % x)
    if mf_bad:
        rc = 1
        print("\n✗ must-fail 探針沒有以宣告的理由失敗（它要量的那個分支沒被走到，或神諭在那裡放行了）：")
        for fn in mf_bad: print("  - %s" % fn)
    # **類別與探針的數量釘死**（R37，R36 第 2 列；同 selftest 門檻 R24 F9）：已知類別依設計不改 rc，但只有「某類別所有宣告它的 fixture 都被刪除」在 rc 上看不出來（「類別路徑整個壞掉」只要還有 fixture 宣告該類別且被掃描到，就會被 `cls_stale`／`cls_undeclared` 逐檔攔下、使 rc=1）。只在跑 repo 自己的 fixture 集（沒有給檔案參數）時檢查。
    if not argv:
        for c in sorted(set(FIXTURE_CLASS_TOTALS) | set(cls_count)):
            if cls_count[c] != FIXTURE_CLASS_TOTALS.get(c, 0):
                rc = 1
                print("\n✗ 已知類別 %s 在 fixture 集上是 %d 條，預期恰好 %d（改動已知類別的 fixture 請同步改 FIXTURE_CLASS_TOTALS）"
                      % (c, cls_count[c], FIXTURE_CLASS_TOTALS.get(c, 0)))
        if len(mf_report) != FIXTURE_MUSTFAIL_TOTAL:
            rc = 1
            print("\n✗ must-fail 探針是 %d 張，預期恰好 %d（改動探針請同步改 FIXTURE_MUSTFAIL_TOTAL）"
                  % (len(mf_report), FIXTURE_MUSTFAIL_TOTAL))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
