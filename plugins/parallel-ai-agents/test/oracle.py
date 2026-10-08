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
S-2 的定義是「預設模式不要求 `2>&1`、`--strict` 要求」：管線自己只從 stderr 外流、`--strict` 真的擋下這個 step（R37–R41 是群組規則；
R42 起要求擋下它的 RULE 帶正面文法的標記 `GRAMMAR_RULE_TAG`），
**而且機制成立**（R39，R38 第 6 列；見 `s2_mechanism`）——每一段補上 `2>&1` 外流就消失，或外流行全是 bash 自己的錯誤訊息、
左邊包成群組就消失。前一版只看前兩條，而 `--strict` 擋下所有非群組管線，於是 fd 轉向、xtrace 這些 fd 規則該擋的外流在規則失效時
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
  lint RULE-red ∧ piped ∧ 無外流                → **不一致：誤擋**；RULE 全是文法標記或 pipefail 時歸已知類別「文法外」（R42，見下）
  lint pass     ∧ 非 piped ∧ 無宣告 ∧ 有外流    → **不一致：繞過**；無外流時是**量不到**
  lint PARSE    ∧ piped ∧ PyYAML 解析成功        → **不一致：誤擋（PARSE）**，除非該檔自己宣告 `# EXPECT: parse-red`
  timeout／stub 沒被呼叫到但腳本逾時             → **量不到**（不是繞過，也不算一致；逐項具名）；逾時之前已經外流：lint 放行判繞過、
                                                   lint 擋下判一致（R42，#33 verify R41 第 20 列）
  **`--strict` 的檔再疊一層**（R42；逾時的那次不疊）：
  lint RULE-red ∧（pipefail 探針看到關閉 ∨ 通道帶 PR 文字） → 一致（擋下是對的）
  lint pass     ∧ 通道帶 PR 文字                            → **不一致：繞過（跨 step 通道）**
  lint pass     ∧ pipefail 探針看到關閉                     → **不一致：繞過（pipefail）**
  pipefail 探針被換掉（腳本改了 DEBUG trap、主 shell 沒跑到 EXIT）→ **量不到**（已判繞過的不改：外流是事實）
  step 唯一的 RULE 是 pipefail ∧ 沒有任何多段管線跑完 ∧ 通道沒帶 → 不可比（量不到退出碼遮蔽）

## `--strict` 的兩個額外觀測（R42，#33 verify R41 第 1–7、11 列）
`--strict` 宣稱兩件預設模式不宣稱的事——寫出來的每條管線跑在 pipefail 之下、靠管線過濾的 step 不把 PR 文字寫進跨 step 的通道。
前一版兩件都量不到（pipefail 的 step 一律不可比；一次跑一個 step，看不到 `$GITHUB_ENV`），R39–R41 那兩類的繞過因此全在神諭的盲區裡。
  · **pipefail 探針**（`PRELUDE_PF`、`pf_observation`）：DEBUG trap 在每條多段管線跑完時記下管線**開始時**的 pipefail（bash 在那時決定
    退出碼怎麼算）與退出碼有沒有被遮蔽；每個子殼層第一次觸發時裝一個 EXIT 收尾。完整性檢查：DEBUG trap 被換掉、或主 shell 沒跑到
    EXIT，判「量不到」而不是「一致」。腳本自己的 `trap <動作> EXIT` 經 `trap` 函式與神諭的收尾組合——不組合的話，文法接受的每一個
    trap step 都會讀成量不到。探針自己的程式碼不產生 xtrace（`local -; set +xv`）。
  · **跨 step 通道**（`CHANNELS`）：`GITHUB_ENV`／`PATH`／`OUTPUT`／`STATE`／`STEP_SUMMARY` 指到暫存檔，跑完看有沒有 PR 文字。
    R44 起 lint 的產生式也涵蓋這五個通道（字面 `>>` 寫入放行、`tee -a` 等當成別的命令的參數一律 RULE），兩邊看同一組。一次仍只跑一個 step：之後的 step 怎麼讀它，
    神諭不模擬——看到 PR 文字寫進去就算外流。

## 已知類別「文法外」（R42）
`--strict` 對靠管線過濾的 step 用正面文法，文法的補集一律 RULE——多數是保守的誤擋。這一格只在誤擋、KNOWN_DISAGREE 之後判，
三個條件同時成立：step 的每一條 RULE 都帶 `GRAMMAR_RULE_TAG` 或是 pipefail 那一條；沒有外流；pipefail 探針與通道都沒看到東西
（看到的話上面的疊加已判一致）。與 G、S-2 同一道雙向閘門：由檔頭 `# KNOWN-CLASS: 文法外` 簽名、數量必須相等。平台變體
「文法外-without-proc」只在沒有 `/proc` 的平台計數（`/proc/$$/fd/…` 那一類在 Linux 會外流、判一致）；有 `/proc` 的平台不計它的宣告。

## KNOWN_DISAGREE 的格式（R42，#33 verify R41 第 14 列）
鍵是（檔名, step 名），值是 `{dir, hash, why}`：`dir` 是登記的方向（誤擋／繞過），`hash` 是運算式代換之前 run 區塊的
`kd_hash`（`--print-kd-hash FILE STEP` 印出）。方向與雜湊都相符才算已知；不符 ⇒ 照一般的不一致處理並具名（前一版只比鍵，
一條登記成誤擋的條目吞掉了同名 step 的繞過）。`KNOWN_DISAGREE_WITHOUT_PROC` 同格式，只在沒有 `/proc` 的平台生效。

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
`BASHOPTS`、`BASH_XTRACEFD` 因此量得到；含 `${{` 的值照 run 區塊的規則代換（R42：字面常數換成值、GH_SAFE 換成數字、其餘換成
PR 標記——前一版不設，`PR_BODY` 寫到哪裡都量不到）。PATH、HOME、`PR_TITLE` 永遠用神諭自己的值；`RUNNER_TEMP`、`GITHUB_WORKSPACE`
照 runner 的語意設成臨時目錄（R42：前一版不設，`> "$RUNNER_TEMP/e"` 變成寫 `/e`、失敗，那一步做了什麼就量不到）。
**盲區**：`env:` 對信任變數（`HOME`、`RUNNER_TEMP`、`GITHUB_WORKSPACE`）的覆寫神諭看不到——它們一律蓋成神諭自己的值（R46 起 primitive 稽核逐命令比對這幾個變數有沒有被 **run 文字**改寫，
但 `env:` 設定的值在稽核的快照之前就生效；`restrict-r44-env-sets-a-trusted-variable` 簽 `文法外`）；`BASH_ENV`／`ENV` 指向的檔案在臨時 cwd 裡不存在（神諭不把 repo 的檔案帶進去），那些檔案的內容量不到；
`/proc/self/fd/2` 在 macOS 上不存在，那一類 fd 轉向在本機量不到外流、在 Linux runner 上量得到（R39 起這幾張
fixture 的誤擋只在沒有 /proc 的平台列為已知，見 `KNOWN_DISAGREE_WITHOUT_PROC`）；`/bin/sh` 在 macOS 是 bash、在 ubuntu
是 dash——依賴 `sh` 的外流兩個平台不同（R38 第 1 列：CI 紅、本機綠）。**本機的神諭數字要註明平台，CI（Linux）為準。**
PR 文字固定是 `ORACLE-PR-TITLE-MARKER`：算術展開（`$(( PR_TITLE ))` 在這個值下是 0）與寫檔（神諭的 cwd 可寫）這兩種
#60 第 2 類形狀在神諭裡不出錯、量不到外流，會把群組規則正確的擋判成誤擋（R38 第 19 列；fixture 改用 `1 $PR_TITLE` 這類
一定出錯的寫法）。`python3` 是 shell stub，不讀 `PYTHON*`（R39 那三張 fixture 因此列在 `KNOWN_DISAGREE`）。
**差分的中性替換會改變 `$?`**（R38 codex 第 5 條）：換掉接 neutralise 的那一行，之後依賴 `$?` 的分支可能不再印，差分因此把
「管線外的命令外流」看成管線自己的外流。R39 起 S-2 另外要求機制差分成立（補 `2>&1` 後外流消失），這一類因此判繞過、
不再被收進已知類別——方向是 fail-closed，但歸類的**原因**仍可能寫錯。
**R40 起的三條（#33 verify R39 第 3、8、15 列、放行條件 12）**：
  · **差分的往上擴範圍是逐段貪婪的**：每一段都要求整份腳本語法完整才擴成功。同一個 run 區塊有兩段都需要擴時判量不到；擴進來的行
    若恰好是另一條外流的命令（`echo "::notice::$PR_TITLE"; {` ⏎ … ⏎ `} 2>&1 | …`），外流跟著消失、被歸成「管線自己印的」而不是 G。
    兩者都判繞過（rc=1），方向是吵、不是藏，但原因可能寫錯（`known-r39-g-two-continued-pipelines` 的檔頭有細節）。
  · **S-2 的機制差分禁止多出 baseline 沒有的外流行**（stdout 與 stderr 都禁）。R40 這裡寫「本機做不出會翻色的 fixture」——
    不對：R41 requirements 用背景子殼層看 `/dev/fd/1 -ef /dev/fd/2` 在 macOS 做出來了，R42 收成 must-fail 探針
    `oracle-r42-s2-flip`（拿掉這個條件，它就被收成 S-2、探針不再以宣告的理由失敗）。**R48 更正**：那個版本的「背景子殼層
    讀旗標、前面墊 `sleep 1`」在神諭裡是一場賽跑——神諭的 `sleep` 是空操作 stub（下方 `sleep 是空操作`），所以沒有排序可言；
    Linux 容器單檔跑三十次，R46 的樹輸 4 次、R48 的樹輸 14 次，R48 合併後的第一次 CI 因此紅。現在讀旗標在管線**結束之後**的
    主殼層，見該 fixture 檔頭。
  · **runner 運算式的代換是一組封閉的 payload**（`RUNNER_PAYLOADS`）：R42 起多了註解、算術、heredoc 內文三種脈絡（#33 verify
    R41 DA-4），每一組都跑、lint 放行時取最嚴重的一份（`select_most_severe`）。仍不在表上的脈絡（`$'…'`、case 模式…）神諭不保證
    逃得出去，判的是「沒看到外流」；每一組代換之後語法都壞掉時判量不到。bash 樣板照旗標跑（`bash_template_prefix`），封閉清單以外的樣板（`-x`、`-v`、`-l`…）仍不可比。

依賴：PyYAML（`python3 -m pip install pyyaml`）。缺就 fail-loud，不靜默跳過。
用法：test/oracle.py [FILE…]   不給檔案 → 全部 test/fixtures/ci-log-filter-*.yml
      test/oracle.py --print-kd-hash FILE STEP   印出 step 的 `kd_hash`（新增或更新 KNOWN_DISAGREE 條目時用）
      test/oracle.py --selftest-severity         `select_most_severe` 的單元測試
      test/oracle.py --selftest-aud              `aud_violations` 的單元測試（記錄編碼、init／fin、損毀記錄；R48）
      環境變數 `ORACLE_LINT=<path>` 換掉被對帳的 lint（只給突變測試用：量「神諭抓不抓得到某個 lint 突變」）。
退出碼：神諭用的 bash 不在 lint 檔頭 `# ORACLE-BASH-SUPPORTED:` 的集合裡 → 1（`bash_supported`，第 13 列）；神諭與 lint 的
`GH_SAFE_EXPRS` 不同步 → 載入時具名退出；有 `KNOWN_DISAGREE` 之外的不一致（含方向或雜湊不符的條目）→ 1；`KNOWN_DISAGREE` 裡的項目變成一致（理由不再成立）→ 1；
已知類別的歸類數與檔頭宣告數不相等（任一方向）→ 1；must-fail 探針沒有以宣告的理由失敗 → 1；不給檔案參數執行整個 fixture 集時，已知類別總數／must-fail 探針總數與寫死常數 `FIXTURE_CLASS_TOTALS`／`FIXTURE_MUSTFAIL_TOTAL` 不符 → 1；否則 0。
「量不到」不改變退出碼，但一定逐項印出來。
"""
import collections
import hashlib
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
    # ── R40（#33 verify R39 第 12 列）：R39 宣稱「沒揭露的誤擋是 0」之外的八種——不放寬，揭露（lint 的代價清單與 #60 同步）──
    ("ci-log-filter-restrict-r40-undisclosed-false-blocks.yml", "python3 -u"): {"dir": "誤擋", "hash": "sha256:090762cebe17c84ab8e2a685deec79f87029945fc9fc4b245da16e390e3bec11", "why": "群組尾巴只認 `python3 <路徑>/neutralise.py`，直譯器選項 `-u` 讓它看不出後面是不是過濾器。"},
    ("ci-log-filter-restrict-r40-undisclosed-false-blocks.yml", "python3 -I"): {"dir": "誤擋", "hash": "sha256:b67c1039ed3306bc8475eb3f3f34a045458d11bd06da36ea605719e1a2efcb47", "why": "同上：`-I`（R38 放行條件 9 建議的加固寫法）同樣被擋——放寬要先讓尾巴的比對認直譯器選項，R40 未做。"},
    ("ci-log-filter-restrict-r40-undisclosed-false-blocks.yml", "workspace path"): {"dir": "誤擋", "hash": "sha256:afc2206f8baf2d6c0e942fc026d055735201c6dc34a6d1470583a6f3c1d1f1c1", "why": "路徑 `\"$GITHUB_WORKSPACE/…\"` 不是字面，lint 看不出它指向的是不是 neutralise.py。"},
    ("ci-log-filter-restrict-r40-undisclosed-false-blocks.yml", "PYTHONPATH from github.workspace"):
        {"dir": "誤擋", "hash": "sha256:04dda1214c6c95363007ed6dc1445d4db866a9f26934507cfd79ffeaa71d5fc3", "why": "`PYTHON*` 的值是運算式就擋（R39 第 9 列）；`github.workspace` 是 runner 給的路徑、不是 PR 文字，lint 不分辨鍵與運算式。"},
    ("ci-log-filter-restrict-r40-default-export-pythonpath.yml", "export PYTHONPATH at top level"):
        {"dir": "誤擋", "hash": "sha256:64fc9029b985ff00db07c6c0ee750987da9eb517073407c7c0a3771f43e2a784", "why": "頂層 export 的 `PYTHON*` 值不是字面就擋；這一步的值是本地路徑，不外流。"},
    # ── R40：神諭照 bash 樣板的旗標跑（`bash_template_prefix`）之後才量得到的五條。它們前一版刻意用帶旗標的樣板讓神諭判不可比
    #    （檔頭寫著「神諭量不到這一條」）；現在量得到了，結果是「lint 擋、這一次執行不外流」。擋的是**機制**，不是這個輸入 ──
    ("ci-log-filter-bypass-r37b-env-policy-BASH_XTRACEFD.yml", "job env BASH_XTRACEFD"):
        {"dir": "誤擋", "hash": "sha256:aa2fa76f86d686a69925a4ee1ecd7ac2eb07cd1033b861b13ff1e57b1ae8efee", "why": "`BASH_XTRACEFD` 單獨設定不會打開 xtrace（lint 的訊息也這樣寫）；擋的是它與 xtrace 並存時把 trace 轉到別的 fd。"},
    ("ci-log-filter-bypass-r37b-fd-bash-xtracefd-assign.yml", "run assigns BASH_XTRACEFD"): {"dir": "誤擋", "hash": "sha256:9a750ad6cd65ee44131b5fe4eb4a53085d367ae1d61519a0cd1916ff91a9e988", "why": "同上：run 裡指派。"},
    ("ci-log-filter-bypass-r37b-env-policy-ENV.yml", "step env ENV"):
        {"dir": "誤擋", "hash": "sha256:aa2fa76f86d686a69925a4ee1ecd7ac2eb07cd1033b861b13ff1e57b1ae8efee", "why": "bash 只在互動**且** POSIX 模式的 shell 啟動時讀 `ENV`（5.3.15 用 pty 實測：`--posix -i`、以及標準輸入與標準錯誤都是終端機的單獨 `--posix`〔那也算互動；stderr 導到 /dev/null 就不讀〕都讀；`-c` 的非互動執行與單獨 `-i` 不讀；R47 DA 在 5.2.21 同結論）。runner 的 `shell:`（含 `sh -e {0}`）跑的是檔案、非互動，不會讀，所以 lint 擋的是機制、不是 runner 目前的行為。"},
    ("ci-log-filter-bypass-r37b-xtrace-verbose-set-o.yml", "verbose on a pipe-filtered step"):
        {"dir": "誤擋", "hash": "sha256:be52a2ebb9fe176759f98a26723285436ac273ddf27def8201c4933b9a07ad0d", "why": "`set -o verbose` 印的是原始碼；這一步的原始碼裡沒有 PR 文字——run 裡寫了 runner 運算式時（runner 先代換）才外流，"
        "那一類另由運算式規則擋。擋的是機制。"},
    ("ci-log-filter-bypass-r37p-parse-misc-parse-list-fallback-skip-amount.yml", "stray close-paren before an xtrace bash call"):
        {"dir": "誤擋", "hash": "sha256:133aa8bd74063fb393670ea743a3e64ae97805a3f3d9d4bd0e79f76a97b08915", "why": "第二行是語法錯誤，bash（`-e`）什麼也不外流；lint 擋的是剖析殘渣裡的 `bash -x`（fail-closed）。前一版照裸 bash 跑時"
        "判「一致」，靠的是 `called-unpiped` 這個狀態，不是外流。"},
    # **YAML tag 一律 fail-closed，而 `!!str` 的值 bash 照跑** ⇒ 誤擋。這是**刻意保留**的，
    # 理由與代價都寫在這裡（R33，由 642 檔產生語料的 `R31-5 tag 值` 那一列量出來）：
    #   · 那道守衛是 R30 MB-8 加的，堵的是 `jobs: !!map {…}` 讓 flow 規則、`steps:` flow 檢查、
    #     anchor／alias 檢查**三條全部跳過**、整個 job 隱形的洞。
    #   · 只放行 `!!str` 需要動 YAML 分類路徑本身；那條路徑守著一個真的洞，而 `!!str` 的
    #     野外出現率是 **0/1565**（`shapes.py` 的 `R31-5` 列，本機語料實測）。
    #   · 所以本輪**不動它**，改成記在這裡：數字誠實地印成「不一致 1（已知 1）」，
    #     而不是讓它在「量不到」或某個寬鬆的述詞後面消失。
    # 這一條若哪天變成「一致」（有人放行了 tag），神諭會 rc=1 要求重判——理由不再成立就要拿掉。
    # **已知類別（G、S-2、文法外）不在這裡逐檔列**：它們按類別處理——`classify_piped_leak` 用差分判定外流是誰印的、
    # S-2 另外要 `--strict` 真的擋下那個 step，歸了類的 step 由所在檔頭的 `# KNOWN-CLASS:` 逐條簽名（雙向閘門，R37）。
    # 逐檔列會讓產生語料上的幾十條各佔一行、沒人讀；類別讓規則改掉的那一天，整類一起翻並被逼重判。
    ("gen-d-yaml-tag-bang.yml", "tag-bang"):  # 這個檔名只在 shellgen.py 產生語料時動態產生（R31-5 tag 值 shape），repo 內沒有這個靜態 fixture 檔案
        {"dir": "誤擋", "hash": "sha256:95dc6aea18e5450ae2b019c68ddbf304ef3507e636bf4460bda96bca789a34d3", "why": "YAML tag 一律 fail-closed（R30 MB-8 堵 `jobs: !!map` 隱形 job）；`!!str` 因此被連帶擋下。"
        "野外 0/1565，不值得為它動那條守著真洞的路徑。"},
    # **`env:` 整張來自 runner 運算式** ⇒ 誤擋（R37 完整性審查補的 fixture）。lint 看不到鍵名，記成 `?` 並 fail-closed：
    # 那張 map 可以帶進 `SHELLOPTS: xtrace`，bash 啟動時就生效、trace 行帶著 PR 文字裸印（實測）。神諭（R42 起）會代換 `env:`
    # 裡各個鍵的運算式值，但整張 map 是一個運算式時沒有鍵可設，所以量不到那個外流、判誤擋。這是兩邊資訊量不同造成的設計差異，不是 lint 的缺陷。
    ("ci-log-filter-bypass-r37t8-step-env-inline-expression.yml", "s"):
        {"dir": "誤擋", "hash": "sha256:de75717165ba9dfcb60236e5bdb4b353bc9c16915bb4c1ab02004a7af9dbdd37", "why": "`env:` 整張來自 `${{ … }}`，lint 看不到鍵名而 fail-closed；神諭不設 runner 運算式的值，量不到它可能帶進的 SHELLOPTS。"},
    # **頂層 `case` 的模式 `|` 被預設模式讀成管線** ⇒ 繞過（R37 完整性審查缺陷 d，刻意保留的已知限制）：`--strict` 擋下它；
    # 預設模式要修得把 case 追蹤延伸到頂層，代價與理由見 lint 已知不涵蓋第三組第 5 條。修好之後這一列變一致，神諭 rc=1 逼人拿掉。
    # **根層級 `env:` 是純量**（R37 opsweep 補件 `bypass-r37o-module-misc-root-env-nonflow-colon-value`）：`env: FOO:bar` 讀不到
    # 鍵名，lint 記成 `?` 並 fail-closed（那張 map 可能帶進 SHELLOPTS）；神諭沒有鍵可設、量不到外流而判誤擋。與上面
    # `step-env-inline-expression` 同一種兩邊資訊量不同的設計差異。GitHub 本身也不接受非 mapping 的 `env`。
    ("ci-log-filter-bypass-r37o-module-misc-root-env-nonflow-colon-value.yml", "probe"):
        {"dir": "誤擋", "hash": "sha256:15de4b262daa1b9e9ab959aa68fe699378b0567e4685f3af5aa626e2b8393f11", "why": "根層級 `env:` 是純量、看不到鍵名，lint fail-closed；神諭沒有鍵可設，量不到它可能帶進的 SHELLOPTS。"},
    # **R37 最終 lint 的 opsweep 補件裡的限制型 fixture**（`restrict-r37p-*`）：突變體把保守的拒絕放寬，這些 fixture 釘住拒絕本身。
    # 輸入實際都不外流，神諭因此判誤擋——那是刻意的 fail-closed，不是 lint 的缺陷。
    ('ci-log-filter-restrict-r37p-fdflow-analyse-amp-trail-drop.yml', 'group has its own trailer plus |& connector'):
        {"dir": "誤擋", "hash": "sha256:6ebc8ae93b8e0c90138fc6fe6c23527faa8fac70e5984490d3ae370bd0020751", "why": '群組豁免只收收尾後恰好接 `2>&1 |` 或 `|&`（沒有別的 trailer）的群組；這個形狀實際不外流，但豁免不涵蓋它。'},
    ('ci-log-filter-restrict-r37p-fdflow-analyse-pipe-conn-drop.yml', 'exact 2>&1 trailer combined with |& connector'):
        {"dir": "誤擋", "hash": "sha256:3c9b94dda5e8773da4b6c823a856739afbde58a11d663e35084273610df1a124", "why": '群組豁免只收收尾後恰好接 `2>&1 |` 或 `|&`（沒有別的 trailer）的群組；這個形狀實際不外流，但豁免不涵蓋它。'},
    ('ci-log-filter-restrict-r37p-fdflow-is2to1-lit-drop.yml', 'group trailer closes fd2, does not dup to fd1'):
        {"dir": "誤擋", "hash": "sha256:2b125c420c2a549a471e3315a0e82385bae2450c09afc1858c62978149a51406", "why": '群組豁免要求收尾恰好是 `2>&1`（fd 2 複製到 fd 1）；`2>&-`、`2>1` 這類實際不外流，但不是豁免的形狀。'},
    ('ci-log-filter-restrict-r37p-fdflow-is2to1-op-drop.yml', 'group trailer redirects to a file literally named 1, not fd dup'):
        {"dir": "誤擋", "hash": "sha256:9d149f876a7a923bd4f31e87d77a8d427a918367df34702f6e0594e76be8e001", "why": '群組豁免要求收尾恰好是 `2>&1`（fd 2 複製到 fd 1）；`2>&-`、`2>1` 這類實際不外流，但不是豁免的形狀。'},
    ('ci-log-filter-restrict-r37p-fdflow-redirhit-1740-op-drop.yml', 'input-direction fd dup treated same as output-direction'):
        {"dir": "誤擋", "hash": "sha256:9e1da96bdbe09ef4a1cb0697e1bdd3d8b65af5bbc3d28ccf27ddce8013d14a29", "why": '輸入方向的 fd 複製（`<&`）一律當成 fd 流向命中（fail-closed）；這個形狀實際不外流。'},
    ('ci-log-filter-restrict-r37p-fdflow-redirhit-1743-op-drop.yml', 'input-direction fd dup to a literal non-digit word'):
        {"dir": "誤擋", "hash": "sha256:aaaa04d863ce5630d05abef969073288549b983fd34c2991e37828c0d06f9255", "why": '輸入方向的 fd 複製（`<&`）一律當成 fd 流向命中（fail-closed）；這個形狀實際不外流。'},
    ('ci-log-filter-restrict-r37p-parse-command-neut-wrong-filename.yml', 'group piped through python3 running the wrong script'):
        {"dir": "誤擋", "hash": "sha256:5d30953066faa495ba1cc1cccbeb88259ea34a49c727faab074142ee85f05161", "why": '管線的過濾端不是 `python3 <路徑>/neutralise.py`，照規則拒絕；實際執行會報錯、不把 stdin 印出來，神諭量不到外流。'},
    ('ci-log-filter-restrict-r37p-parse-command-neut-wrong-interpreter.yml', 'group piped through a same-named script under the wrong interpreter'):
        {"dir": "誤擋", "hash": "sha256:df24f36b345b5276d3025c0c190edb817afc7b3983b945a36ea6c04cf4f04f0e", "why": '管線的過濾端不是 `python3 <路徑>/neutralise.py`，照規則拒絕；實際執行會報錯、不把 stdin 印出來，神諭量不到外流。'},
    ("ci-log-filter-known-r37t8-default-case-pattern-pipe.yml", "s"):
        {"dir": "繞過", "hash": "sha256:386a13f6fdfe38ddae75a87bb794d95694df84c0faadd42c0894cebf568290d3", "why": "頂層 case 模式的 `|` 是「或」，預設模式的 `PIPED_RE` 算它接了 neutralise；`--strict` 由正面文法擋下（R42 以前是群組規則）。"},
    # **神諭的 python3 是 stub**：它不檢查路徑存不存在，所以真 python3 的「can't open file '<路徑>'」（路徑裡帶著展開後的
    # PR 文字、寫在 python3 自己的 stderr）在這裡不會出現。lint 擋下是對的，神諭量不到——這是儀器的盲區，不是 lint 的誤擋。
    ("ci-log-filter-bypass-strict-group-expansion-in-filter-path.yml", "expansion in the filter path"):
        {"dir": "誤擋", "hash": "sha256:732780584052d765f038290a1f00b8fd91a57c2e34d77a16475c020dbc715f56", "why": "stub python3 不報「can't open file」；真 python3 會把含 PR 文字的路徑印到群組外的 stderr。"},
    ("ci-log-filter-bypass-strict-group-variable-filter-path.yml", "variable in the filter path"):
        {"dir": "誤擋", "hash": "sha256:cabe4af65c222775ab172c47b9b073ee695fee9dbd2266b9a8893bccedca43b6", "why": "同上：路徑是 `$PR_TITLE/neutralise.py`，stub python3 不報「can't open file」。"},
    # **R42：`--strict` 的保守擋下改由檔頭簽名**。群組規則時代逐條登記在這裡的誤擋——巢狀群組、子殼層群組、群組前的 `cd`／
    # `export`／`set +e`／`shopt`、兩個群組、函式定義、`..` 經過 dev 的路徑，以及產生語料 `--strict` 組維度 1／5／6 的逐段 `2>&1`
    # 與子殼層包裹——在正面文法下都是「不在文法裡、沒有外流」：神諭把它們歸進已知類別**文法外**，由所在檔頭的
    # `# KNOWN-CLASS: 文法外` 簽名（產生語料由 shellgen 依構造寫出）。只有神諭**量不到**外流的（下面那一段）才留在這裡。
    # ── R39（#33 verify R38 第 5、9 列）：神諭結構上量不到的外流 ──
    ("ci-log-filter-bypass-r39-strict-group-proc-ppid-fd1.yml", "group writes to proc-ppid-fd1"):
        {"dir": "誤擋", "hash": "sha256:8e7c9c9cb222536cd93fd77b668f0145eebdd184919a7b44803511596062c0ca", "why": "`/proc/$PPID/fd/1` 在 runner 上是 runner 自己的 log；在神諭裡 `$PPID` 是神諭行程，它的 fd 1 不在神諭擷取的輸出裡。"},
    ("ci-log-filter-bypass-r39-strict-group-dev-tty.yml", "group writes to dev-tty"):
        {"dir": "誤擋", "hash": "sha256:89bcaba7f39dd27476ea4103c75938cd181305a2406e465bc60ac680ec7a04b3", "why": "`/dev/tty` 是控制終端；神諭與 GitHub runner 都沒有，寫入失敗、錯誤訊息在群組裡進管線。lint 擋下是保守的方向"
        "（控制終端存在的 runner——自架、互動式——寫進去的東西不經過濾）。"},
    # ── R44（#33 verify R43 第 9 列）：預設模式的雙胞胎／新形狀——神諭看不到的外流與它們的 strict 原件同一原因 ──
    ("ci-log-filter-bypass-r44-default-twin-group-dev-tty.yml", "group writes to dev-tty"):
        {"dir": "誤擋", "hash": "sha256:89bcaba7f39dd27476ea4103c75938cd181305a2406e465bc60ac680ec7a04b3", "why": "同 `bypass-r39-strict-group-dev-tty`：控制終端神諭與 runner 都沒有；這一份在預設模式跑（殺 `_group_safe_target` 的突變體）。"},
    ("ci-log-filter-bypass-r44-default-lex-cmdsub-then-tty.yml", "a tty write after a process substitution in a command substitution"):
        {"dir": "誤擋", "hash": "sha256:d4c14596860fd48e854c5b07e8934e8fea83ebc045834abebbea1a67325fa2e4", "why": "同上：`/dev/tty` 神諭寫不進去。這張的用途是殺 `parse_command` 的 `self.i += 1` 位移突變，不是量外流。"},
    ("ci-log-filter-bypass-r44-default-twin-group-dotdot-stderr.yml", "group writes through dotdot"):
        {"dir": "誤擋", "hash": "sha256:8b2cc0db68beab086a14845e9a1624a53c1543e2bcfc532056d35c6a1d69feba", "why": "`/dev/fd/../stderr`：bash 在兩個平台都寫不出去或寫到群組自己的 stderr（`bypass-r39` 原註解實測），沒有外流；lint 對 `..` 經過 /dev 的路徑 fail-closed。"},
    ("ci-log-filter-bypass-r39-env-pythonwarnings-expression.yml", "PYTHONWARNINGS from the PR title"):
        {"dir": "誤擋", "hash": "sha256:5421eda798594418bb957e112a59b815cccca3f788666a60821442614b90dfa5", "why": "神諭的 `python3` 是 shell stub，不解析 `PYTHONWARNINGS`；真的 CPython 會把不合法的值印到管線右端的 stderr（協調者實跑）。"},
    ("ci-log-filter-bypass-r39-env-pythonwarnings-expression-default.yml", "PYTHONWARNINGS from the PR title"): {"dir": "誤擋", "hash": "sha256:de75717165ba9dfcb60236e5bdb4b353bc9c16915bb4c1ab02004a7af9dbdd37", "why": "同上：stub。"},
    ("ci-log-filter-bypass-r39-run-export-pythonwarnings.yml", "export PYTHONWARNINGS in run"): {"dir": "誤擋", "hash": "sha256:99c2ded5fce312cafe5acb56e4ea737f2eb05d03dc41ccfdcd10cdfc44d6a7cd", "why": "同上：stub。"},
    # ── R39（R38 第 13 列）：殺 `_cmdsub_end_case` 四條存活突變的 fixture——原碼保守判 RULE（命令替換裡的 `shopt -s extglob`
    # 改變之後的詞法，本 lint 不追蹤就擋），bash 照常執行、不外流 ──
    ("ci-log-filter-restrict-r39-cmdsub-case-esac-at-cmd.yml", "cmdsub case esac at cmd"):
        {"dir": "誤擋", "hash": "sha256:f73b2f88fe063741fa3344fc990630b9f6411370273a119d92b42253be1c627f", "why": "命令替換裡 `shopt -s extglob`：保守擋（見 `restrict-r37p-*` 的同類理由）；這張的用途是殺 `_cmdsub_end_case` 的突變體。"},
    ("ci-log-filter-restrict-r39-cmdsub-case-hash-word-start.yml", "cmdsub case hash word start"): {"dir": "誤擋", "hash": "sha256:2f9fdfacbb13346ce31a5ba7dacc7c22e83f27bec3f2ba49055cf2963a4107f1", "why": "同上。"},
    ("ci-log-filter-restrict-r39-cmdsub-case-paren-branch.yml", "cmdsub case paren branch"): {"dir": "誤擋", "hash": "sha256:38ef1ddd006c9d0a223112b2b9634a909327459aa7c7f289f93490745b74799e", "why": "同上。"},
    ("ci-log-filter-restrict-r39-cmdsub-case-herestring.yml", "cmdsub case herestring"): {"dir": "誤擋", "hash": "sha256:07a4d18ba7906d4efae201035b3480b1cb8ee0f49a40c3a56b531407e8c65356", "why": "同上。"},
    # ── R42：神諭（WP5–WP7 之後）仍然量不到的外流，逐條寫出盲區 ──
    ("ci-log-filter-bypass-r42-default-k3.yml", "s"):
        {"dir": "誤擋", "hash": "sha256:bccc8e5de706da2d6392bf0230af19daf8d0c92fd6388efb94fbb792c3505e8f", "why": "fd 流向規則不看內容：`>&2` 那一行只印 `a hi x`，沒有 PR 文字。這張的用途是殺 `_word` 雙引號進 code 那一支的位移突變（R41 logic F7）。"},
    ("ci-log-filter-bypass-r42-ghenv.yml", "a13-python"):
        {"dir": "誤擋", "hash": "sha256:4e53dd39864e4550329bfa1042f315848a5548faeaf39c5092627566c4aff310", "why": "神諭的 `python3` 是 stub，`python3 -c` 不會真的寫 `$GITHUB_ENV`；真 CPython 會。"},
    ("ci-log-filter-bypass-r42-ghenv.yml", "ge-python"): {"dir": "誤擋", "hash": "sha256:13385b7d8a6a65a07897c0c8890aa8f8bc3ca3fa883216ec7f7dbd87890b129c", "why": "同上：stub。"},
    ("ci-log-filter-bypass-r42-ghenv.yml", "a25-git-log"):
        {"dir": "誤擋", "hash": "sha256:b2169564fabfb93bee6575ee56ee33a345844138f0b85d2e55bf185c91f6095b", "why": "神諭的工作目錄不是 git repo，`git log` 讀不到 commit 訊息；在 runner 上那是 PR 作者寫的文字。"},
    ("ci-log-filter-bypass-r42-flat-fd-dup-3.yml", "fd 3 dup"):
        {"dir": "誤擋", "hash": "sha256:190b3a43ed23e34e218e4e4dc2d10e1892a9cfe317ff80dfb6baff5707afbc68", "why": "`>&3` 寫到外層 shell 繼承的 fd 3：神諭跑的時候 fd 3 沒開、寫入失敗；runner 上開著時就是群組管線以外的輸出。不歸文法外——它不是安全的寫法，只是神諭量不到。"},
}
# **只在沒有 /proc 的平台上成立**的已知分歧（R39，#33 verify R38 第 1、5 列）：macOS 沒有 `/proc`，`/dev/fd` 也不是指向
# `/proc/self/fd` 的 symlink，這幾個外流在本機量不到、判誤擋。Linux（CI）上**不列入**——在那裡神諭必須看到外流、判一致，
# 否則就是 lint 擋錯了或 fixture 寫錯了。R38 的教訓：ground truth 在 CI 的平台上量，本機數字要註明平台。
KNOWN_DISAGREE_WITHOUT_PROC = {
    ("ci-log-filter-bypass-r39-fd-dotdot-dev-target.yml", "dotdot path under /dev"):
        {"dir": "誤擋", "hash": "sha256:5baf0b11467c08bc512e7069112a4b038899ef65c9fbf6c46ec4da92fb512a1d", "why": "`/dev/fd/../../self/fd/2`：Linux 的 `/dev/fd` 是指向 `/proc/self/fd` 的 symlink，實際是 stderr；本機沒有那個 symlink。"},
    ("ci-log-filter-bypass-r42-default-group-proc-pid-fd1.yml", "group writes to proc-pid-fd1"):
        {"dir": "誤擋", "hash": "sha256:923cbb058aab2662553bab6b9313fb820dd4083f9f45e75ebacfba500cc6732c", "why": "預設模式的雙胞胎（R42 WP5）：`/proc/$$/fd/1` 只在 Linux 寫到外層 shell 的 fd。擋它的是 fd 流向規則、不是正面文法，所以不歸文法外。"},
    # macOS 的 BSD `dd` 不認 `oflag=append`（不是 /proc 的差別，但同樣只在這個平台成立——Linux 的 GNU dd 照寫，神諭判一致）。
    ("ci-log-filter-bypass-r42-ghenv.yml", "a17-dd"):
        {"dir": "誤擋", "hash": "sha256:51795bdbe6da9584355a17610a6abfa3e92f02e63b13d2c041ce5d3b63cef19a", "why": "BSD `dd` 拒絕 `oflag=append`、什麼都沒寫；GNU dd 會把 PR 文字寫進 `$GITHUB_ENV`。"},
}
# 文法外類別的平台變體（`文法外-without-proc`）也看這個旗標，見 `check_file`。
HAS_PROC = os.path.isdir("/proc/self/fd")
if not HAS_PROC:
    KNOWN_DISAGREE.update(KNOWN_DISAGREE_WITHOUT_PROC)

# lint 自己的宣告正規式（與 `lint-ci-log-filter.sh` 的 `LOGFILTER_RE` 同形）。這裡只用它判**文字長相**；
# 「那段文字是不是真的不會被執行」由差分決定，不靠任何一支的詞法分析。
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")

TIMEOUT_S = 5
# `$PR_TITLE` 的值：**「有沒有洩漏」是繞過判定的第三個條件**。lint 放行 ∧ runner 沒接管線，
# 只說明「沒過濾」；要構成繞過還得真的把 fork 可控的文字印出去。少了這一條，任何「lint 以為有管線、
# 但那一行根本沒執行」的構造都會被誤報成繞過（R31 自查：產生語料上 60 筆假指控全屬此類）。
PR_MARKER = "ORACLE-PR-TITLE-MARKER"
# **注入探針**（R44，#33 verify R43 第 1–3 列）：PR_MARKER 是文字、不是程式碼——「PR 文字被當程式碼執行」（`[ -n $PR_TITLE ]` 的 `-v` 下標算術求值、
# `RANDOM="$X"`、`trap "$tmp" EXIT` 之前被 `printf -v` 改寫的變數）它結構上看不到。這一組 payload 是會留下哨兵的程式碼：下標算術裡的命令替換
# （`PWD[$(…)]`，用 `${IFS}` 代替空白，所以單一個詞就夠）、前面接 `-v`／`-n -o -v` 讓 `[`／`test` 把它當 `-v` 的運算元、以及一行純程式碼
# （trap 動作）。把 PR 相關的環境變數（PR_TITLE、PR_BODY 與 step `env:` 裡值是運算式的鍵）設成 payload 再跑一次：哨兵檔有東西 = 被當成程式碼執行了。
INJECT_MARKER = "ORACLE-INJECT-MARKER"
_INJECT_SUB = "$(echo${IFS}" + INJECT_MARKER + ">>$ORACLE_INJECT)"
INJECT_PAYLOADS = ("PWD[" + _INJECT_SUB + "]",
                   "-v PWD[" + _INJECT_SUB + "]",
                   "-n -o -v PWD[" + _INJECT_SUB + "]",
                   "echo " + INJECT_MARKER + ' >> "$ORACLE_INJECT"')


# ── runner 運算式的代換（R40，#33 verify R39 第 1 列、DA N3）─────────────────────────────────────────────────────────────
# 前一版不代換 `${{ … }}`：bash 看到的是錯誤的替換，量不到代換之後的注入——R39 的 `${{ }}` 規則只認兩種拼法，其餘寫法在
# `--strict` 放行而真的外流，神諭卻看不見（三條 KNOWN_DISAGREE 寫的就是「神諭不代換運算式」，R40 刪掉）。現在：純字面常數換成它的值；
# 其餘每一個運算式都當成 PR 可控，換成下面這組 payload 各跑一次、各判一次，選一份（見 `check_file` 與 `select_most_severe`）。
# payload 的集合是封閉的：純標記（值直接被印出來）＋三種引號脈絡（不加引號、雙引號、單引號）× 兩種位置（收掉群組、群組外的
# 同一行）＋ R42 的三種脈絡（註解、算術、heredoc 內文，#33 verify R41 DA-4）。不在這張表上的脈絡（例如 `$'…'`）神諭不保證
# 逃得出去——那時它判的是「沒看到外流」，方向是寬。**每一組都跑**，lint 放行時取最嚴重的一份（R42，logic F9，見 `check_file`）。
# 每一組都先 `|| :`：runner 用 `bash -e`（神諭也照樣板跑，見 `bash_template_prefix`），運算式前面那個命令失敗時腳本就停了，
# 標記印不出來——payload 不得依賴它前面的命令成功（R40 自查：`{ make ${{ matrix.target }}; }` 的 make 失敗，前一版的 payload 量不到）。
RUNNER_PAYLOADS = (
    PR_MARKER,
    "x || :; }; echo %s; { :" % PR_MARKER,
    'x" || :; }; echo %s; { : "' % PR_MARKER,
    "x' || :; }; echo %s; { : '" % PR_MARKER,
    "x || :; echo %s >&2; :" % PR_MARKER,
    'x" || :; echo %s >&2; : "' % PR_MARKER,
    "x' || :; echo %s >&2; : '" % PR_MARKER,
    # R42（#33 verify R41 DA-4）：前一版逃不出去的三種脈絡，各一組收掉群組、一組印到 stderr。
    "\nx || :; }; echo %s; { :; #" % PR_MARKER,       # 註解：先換行結束註解，結尾的 `#` 把同一行剩下的原文再變回註解
    "\nx || :; echo %s >&2; : #" % PR_MARKER,
    "0 )); }; echo %s; { : $(( 0" % PR_MARKER,         # 算術：收掉 `$((`，最後開一個新的接住原文的 `+ 1 ))`
    "0 )); echo %s >&2; : $(( 0" % PR_MARKER,
    "\n{D}\n}; echo %s; { cat <<{D}" % PR_MARKER,      # heredoc 內文：`{D}` 換成所在 heredoc 的終止字（`_heredoc_delim_at`）
    "\n{D}\necho %s >&2; cat <<{D}" % PR_MARKER,
)
# heredoc 的開頭：`<<WORD`、`<<-WORD`、`<<'WORD'`、`<<"WORD"`（不認 `<<<`）。只用來判斷 heredoc 那一組 payload 適不適用——
# 認錯只會多試或少試一組，不會讓神諭少看已經觀察到的外流。
HEREDOC_OPEN_RE = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _heredoc_delim_at(run, pos):
    """`pos` 落在某個 heredoc 的**內文**行裡時，回傳那個 heredoc 的終止字；否則 None。"""
    off, cur, pending = 0, None, []
    for line in run.split("\n"):
        start, end = off, off + len(line)
        if cur is not None:
            strip, d = cur
            if (line.lstrip("\t") if strip else line) == d:
                cur = pending.pop(0) if pending else None
            elif start <= pos <= end:
                return d
        else:
            pending += [(m.group(1) == "-", m.group(3)) for m in HEREDOC_OPEN_RE.finditer(line)]
            cur = pending.pop(0) if pending else None
        off = end + 1
    return None
GH_LITERAL_RE = re.compile(r"\s*(?:'(?:[^']|'')*'|-?\d+(?:\.\d+)?|true|false|null)\s*")


def runner_exprs(s):
    """`s` 裡每一個 `${{ … }}` 的 (起點, 終點, 內容)——與 lint 的 `runner_exprs` 同一套邊界：單引號字串（`''` 跳脫）裡的 `}}`
    不收尾；沒收尾的延伸到結尾。"""
    out, i = [], 0
    while True:
        a = s.find("${{", i)
        if a < 0:
            return out
        j, q = a + 3, False
        while j < len(s):
            if s[j] == "'":
                if q and s[j + 1:j + 2] == "'":
                    j += 2
                    continue
                q = not q
            elif not q and s.startswith("}}", j):
                break
            j += 1
        end = min(j + 2, len(s))
        out.append((a, end, s[a + 3:j]))
        i = end


# GitHub 產生、PR 作者控制不了的純量欄位（R40，#33 verify R39 第 12 列）。**封閉列舉，只有這八個**，點號寫法、大小寫不分（Actions 的
# context 名稱不分大小寫）；索引寫法、函式呼叫、同一物件的其他欄位（`head.ref`、`title`…）不在裡面、照擋。lint 與神諭各寫一份（神諭把它們換成數值，不換成 payload）；神諭載入時與 lint 那一份比對，不同步就具名退出（見下方「`GH_SAFE_EXPRS` 同步檢查」）。
GH_SAFE_EXPRS = frozenset((
    "github.event.pull_request.number", "github.event.number",
    "github.event.pull_request.base.sha", "github.event.pull_request.head.sha",
    "github.sha", "github.run_id", "github.run_number", "github.run_attempt",
))


def _literal_value(inner):
    v = inner.strip()
    return v[1:-1].replace("''", "'") if v.startswith("'") else ("" if v == "null" else v)


def substitute_runner_exprs(run, payload):
    """把 `run` 裡的運算式換成 runner 會代入的東西：字面常數換成值，其餘換成 `payload`（None ⇒ 只換字面、非字面原樣留著）。
    payload 帶 `{D}`（heredoc 那一組）時，每個非字面運算式都要落在 heredoc 內文裡、`{D}` 換成那個終止字；有一個不在 ⇒ 回傳 None
    （這一組不適用這個 step）。"""
    parts, last = [], 0
    for a, b, inner in runner_exprs(run):
        parts.append(run[last:a])
        if GH_LITERAL_RE.fullmatch(inner):
            parts.append(_literal_value(inner))
        elif inner.strip().lower() in GH_SAFE_EXPRS:
            parts.append("123")
        elif payload is not None and "{D}" in payload:
            d = _heredoc_delim_at(run, a)
            if d is None:
                return None
            parts.append(payload.replace("{D}", d))
        else:
            parts.append(run[a:b] if payload is None else payload)
        last = b
    parts.append(run[last:])
    return "".join(parts)


def has_nonliteral_expr(run):
    return any(not GH_LITERAL_RE.fullmatch(inner) and inner.strip().lower() not in GH_SAFE_EXPRS
               for _a, _b, inner in runner_exprs(run))
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
# 換成群組規則，這裡的第二個字面跟著換；R42 群組規則換成正面文法（#33 verify R41），第二個字面換成文法的標記——
# 文法拒絕的每一句訊息都帶它（lint 的 `flat_*`），神諭用它認出「這條 RULE 是文法擋的」（文法外類別、S-2 的查核）。
PIPEFAIL_RULE_MSG = "卻沒有跑在 pipefail 之下"
GRAMMAR_RULE_TAG = "不在 `--strict` 的正面文法裡"
RULE_LINE_RE = re.compile(r":(\d+): RULE: ([^\n]*)")
# **耦合檢查**（R37 合併時加）：上面兩個字面必須真的出現在 lint 裡。R37 合併 r37a 與 r37b 時，r37b 把 `2>&1` 那條的訊息
# 改寫了、這裡沒跟上——上一段說那是 fail-closed，但它只會讓某張 fixture 碰巧變紅、不會說出原因。直接查字面，對不上就
# 具名失敗。
_LINT_SRC = LINT.read_text(encoding="utf-8", errors="replace") if LINT.is_file() else ""
for _msg in (PIPEFAIL_RULE_MSG, GRAMMAR_RULE_TAG):
    if _msg not in _LINT_SRC:
        sys.exit("✗ oracle.py 用來認 RULE 的字面「%s」不在 %s 裡——lint 改了訊息，這裡要同步改" % (_msg, LINT))
# **`GH_SAFE_EXPRS` 同步檢查**（R42，#33 verify R41）：lint 放行這些運算式、神諭把它們換成數值——兩份清單各寫一次。
# 不同步時一邊當成作者寫死的值、另一邊當成 PR 可控，對帳量的就不是同一件事，而且沒有任何一張 fixture 會因此變紅。
# 直接讀 lint 原始碼裡那一份比對。假 lint（`oracle-probes/lint-*.sh`）不解析運算式、沒有這份清單，不比；repo 自己的
# lint 找不到清單則具名退出。
_GH_M = re.search(r"^GH_SAFE_EXPRS = frozenset\(\((.*?)\)\)", _LINT_SRC, re.M | re.S)
if _GH_M is not None:
    _GH_LINT = frozenset(re.findall(r'"([^"]+)"', _GH_M.group(1)))
    if _GH_LINT != GH_SAFE_EXPRS:
        sys.exit("✗ GH_SAFE_EXPRS 在神諭與 %s 裡不同步：只在神諭 %s、只在 lint %s"
                 % (LINT, sorted(GH_SAFE_EXPRS - _GH_LINT), sorted(_GH_LINT - GH_SAFE_EXPRS)))
elif LINT == (HERE / "lint-ci-log-filter.sh").resolve():
    sys.exit("✗ %s 裡找不到 GH_SAFE_EXPRS——神諭無法確認兩份同步" % LINT)
# **primitive 稽核的判讀常數**（R46，#33 verify R45 第 1–3 列）：文法對 `test`／`[` 與 `printf` 收的形狀。神諭自己寫一份；`FL_TEST_UNARY`／`FL_TEST_BINARY`／`FL_PRINTF_CONVERSIONS` 與 lint 的那份做同步檢查（同 `GH_SAFE_EXPRS`），格式正規式與三種形狀的判斷式不比對（目前人工核過逐字相同）——
# 稽核問的是「builtin 實際收到的 argv／格式在不在文法的形狀裡」，不是「lint 的詞模型怎麼說」，所以不從 lint 讀值，只比對。
AUD_TEST_UNARY = frozenset("-n -z -e -f -d -s -r -w -x -L -h -b -c -g -k -p -t -u -G -N -O -S".split())
AUD_TEST_BINARY = frozenset("= == -eq -ne -lt -le -gt -ge".split())
AUD_PRINTF_CONVERSIONS = "sdiuoxXeEfFgGcq"
AUD_PRINTF_FMT_RE = re.compile(r"(?:[^%\\]|\\[abefnrtv\\'\"?0-7xuU]|%%|%[-+ #0]*[0-9]*(?:\.[0-9]+)?[" + AUD_PRINTF_CONVERSIONS + r"])*")
for _name, _mine in (("FL_TEST_UNARY", AUD_TEST_UNARY), ("FL_TEST_BINARY", AUD_TEST_BINARY)):
    _m = re.search(r'^%s = frozenset\("([^"]+)"\.split\(\)\)' % _name, _LINT_SRC, re.M)
    if _m is not None and frozenset(_m.group(1).split()) != _mine:
        sys.exit("✗ %s 在神諭與 %s 裡不同步：神諭 %s、lint %s" % (_name, LINT, sorted(_mine), sorted(_m.group(1).split())))
    elif _m is None and LINT == (HERE / "lint-ci-log-filter.sh").resolve():
        sys.exit("✗ %s 裡找不到 %s——神諭無法確認兩份同步" % (LINT, _name))
_m = re.search(r'^FL_PRINTF_CONVERSIONS = "([^"]+)"', _LINT_SRC, re.M)
if _m is not None and _m.group(1) != AUD_PRINTF_CONVERSIONS:
    sys.exit("✗ FL_PRINTF_CONVERSIONS 在神諭與 %s 裡不同步：神諭 %r、lint %r" % (LINT, AUD_PRINTF_CONVERSIONS, _m.group(1)))
elif _m is None and LINT == (HERE / "lint-ci-log-filter.sh").resolve():
    sys.exit("✗ %s 裡找不到 FL_PRINTF_CONVERSIONS——神諭無法確認兩份同步" % LINT)


ORC_NAME_RE = re.compile(r"ORACLE_|__orc_")
AUD_INTEGRITY = "儀器："


def aud_violations(raw, complete=True):
    """稽核檔的內容（PRELUDE 的 `__orc_aud` 寫的位元組：每筆記錄是「名稱、欄位數、各欄位」，每個都以 NUL 結尾）→ 觀察（字串清單）。
    **文法性質的違規**：`test`／`[`：實際 argv 不是三種形狀（零或一個運算元、一元運算子加運算元、運算元加二元運算子加運算元）；`printf`：第一個參數是選項、或格式不在封閉的轉換列舉裡；
    `trusted`：信任變數的值變了（每個命令之前、任何行程都比對，含管線的子殼層；例：`{RUNNER_TEMP[0]}>`、`printf '%n' HOME`）。這是**文法性質**的稽核——不問 PR 文字有沒有出現在 log。
    **儀器完整性**（R48，#33 verify R47；以 `AUD_INTEGRITY` 開頭的條目，不是違規）：稽核檔沒有 `init` 開頭（被截斷或改寫）、記錄解析不出來（損毀或被截斷）、`complete`（這次執行跑完了，不是逾時）卻沒有任何 `fin`——
    這些都表示儀器不可信；呼叫端在（`--strict` 檔、lint 判 pass 或 RULE-red、step 在文法內、判定還不是「繞過」）時判「量不到」，不當成「沒有違規」。`raw` 是 bytes（也接受 str；目前沒有單元測試用到那個分支）。"""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    toks = raw.split(b"\0")
    out, recs, bad = [], [], None
    if toks and toks[-1] == b"":
        toks.pop()
    elif toks:
        bad = "最後一筆記錄沒有結尾"
    i = 0
    while i < len(toks) and bad is None:
        name = toks[i].decode("utf-8", "replace")
        if i + 1 >= len(toks):
            bad = "記錄 `%s` 缺欄位數" % name[:20]
            break
        try:
            n = int(toks[i + 1])
        except ValueError:
            bad = "記錄 `%s` 的欄位數不是整數" % name[:20]
            break
        if n < 0 or i + 2 + n > len(toks):
            bad = "記錄 `%s` 的欄位數 %d 超出檔案" % (name[:20], n)
            break
        recs.append((name, [t.decode("utf-8", "replace") for t in toks[i + 2:i + 2 + n]]))
        i += 2 + n
    if bad:
        out.append(AUD_INTEGRITY + "稽核檔解析不出來（%s）" % bad)
    if not recs or recs[0][0] != "init":
        out.append(AUD_INTEGRITY + "稽核檔沒有 init 開頭（被截斷或改寫）")
    if complete and not any(n == "fin" for n, _ in recs):
        out.append(AUD_INTEGRITY + "這次執行跑完了，稽核檔卻沒有 fin 記錄")
    for name, a in recs:
        if name == "trusted":
            out.append("信任變數 `%s` 在這個 step 裡的值變了" % (a[0] if a else "?"))
        elif name in ("test", "["):
            if name == "[" and a and a[-1] == "]":
                a = a[:-1]
            n = len(a)
            if not (n <= 1 or (n == 2 and a[0] in AUD_TEST_UNARY) or (n == 3 and a[1] in AUD_TEST_BINARY)):
                out.append("`%s` 實際收到文法三種形狀之外的 argv（%d 個運算元，開頭 %r）" % (name, n, a[:3]))
        elif name == "printf":
            fmt = a[0] if a else ""
            if fmt.startswith("-") or not AUD_PRINTF_FMT_RE.fullmatch(fmt):
                out.append("`printf` 實際收到的格式 %r 在封閉的轉換列舉之外（選項或會指派變數的轉換）" % fmt[:30])
    return out


# 已知類別在 repo 自己的 fixture 集（不給檔案參數）上的**確切**條數（R37，R36 第 2 列；同 selftest 門檻 R24 F9 的理由：
# 寫成 `>=` 而實際更高時，那個差額沒有網——刪掉一張 G 範例 fixture 仍然綠）。must-fail 探針不算在內。
# R46：301 → 264——51 個簽名消失（40 個改判「一致」：primitive 稽核看到 builtin 收到的 argv 超出 lint 的形狀——**不代表危險**：其中有無害的誤擋，如 `[ "$A" != b ]`（只有它在 301 之內；`printf '%ld'` 在 R44 的 lint 是放行的、從沒簽過），誤擋帳本不再記它們〔R47 第 5 列；R48 決定先揭露、不重簽 8 張 fixture 裡的 40 個 step〕；11 個是 `restrict-r44-test-shapes-corpus` 的第 016–026 個隨一元運算子清單補全移到 `good-r46-test-harmless-unary`、lint 改放行；見各 fixture 檔頭的 R46 註記），再加 R46 新 fixture 仍簽名的 14 個 step（大括號與具名 fd 各一、was-good 四、`$GITHUB_ENV` 鍵與特殊變數六、區域 opsweep 補的 trap 訊號與非字面 printf 格式各一）。
FIXTURE_CLASS_TOTALS = {"G": 8, "S-2": 3, "文法外": 264, "文法外-without-proc": 2}
# `文法外-without-proc` 只在沒有 /proc 的平台成立（見 `check_file` 的平台變體）；有 /proc 時預期是 0。
FIXTURE_CLASS_PLATFORM_ONLY = frozenset(("文法外-without-proc",))
# must-fail 探針的確切張數（同理：刪掉一張探針＝少一條負對照，必須立刻紅）。
FIXTURE_MUSTFAIL_TOTAL = 8   # R42：`bypass-r37a-mustfail-strict-pipefail-hides-2to1` 退役（見該檔頭）、新增 `oracle-r42-s2-flip`
KNOWN_CLASS_RE = re.compile(r"^# KNOWN-CLASS: (\S+)", re.M)
MUSTFAIL_RE = re.compile(r"^# ORACLE-MUST-FAIL: (.+?)\s*$", re.M)
# 差分用的中性命令：單獨一行是合法的空操作（rc=0），接在懸空的 `|`／`|&` 後面則是**語法錯誤**——`!` 只能出現在
# 管線開頭。所以「換掉的範圍少了管線的上游那一段」不會安靜地變成一條新管線，而是被 `bash -n` 當場抓到（R37 實測 bash 5.3）。
NEUTRAL_CMD = "! ! :"

STUB = '''#!/bin/sh
for a in "$@"; do case "$a" in *neutralise.py) echo "called $a" >> "$ORACLE_MARK";; esac; done
# R44（#33 verify R43 第 4 列）：真的 CPython 沒有腳本參數（也沒有 -c／-m）就把 stdin 當程式讀——`python3 -Xneutralise.py` 把 `-Xneutralise.py` 當
# 選項，SyntaxError 把第一行（含 PR 文字）印到 python3 自己的 stderr，那條 stderr 在管線最右端、不經任何過濾。前一版的 stub 一律吞掉 stdin，
# 於是這一類神諭量不到。只模擬這一件事：選項的值（`-W x`、`-X x`、`-Q x`）跳過，第一個位置參數是腳本。
mode=stdin
while [ $# -gt 0 ]; do
  case "$1" in
    -c|-m|-c?*|-m?*) mode=drain; break;;
    -W|-X|-Q) shift;;
    -W?*|-X?*|-Q?*) :;;
    -) break;;
    -*) :;;
    *) mode=drain; break;;
  esac
  shift
done
if [ "$mode" = stdin ]; then cat >&2; exit 1; fi
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
#
# **pipefail 探針**（R42，#33 verify R41 放行條件 5；原型 r42-design 的 pfprobe2）：同一個 DEBUG trap 另外記每一條跑完的
# 多段管線開始時 pipefail 開著沒有（`pf … start=`）、以及退出碼有沒有被遮蔽（`masked=1`：整條 rc=0 但有一段非 0）。
# 每個 shell 行程（子殼層也算）第一次觸發時記 `start`，結束時由 EXIT trap 的 `__orc_fin` 比對 DEBUG trap 還是不是神諭裝的
# ——腳本自己改了 DEBUG trap（`trap … DEBUG`）或換掉了 EXIT trap（`builtin trap … EXIT`），探針就量不到（`pf_observation`）。
# **EXIT 的組合**：腳本裡的 `trap <動作> EXIT`（或 `0`）——正面文法唯一收的 trap 形狀——經 `trap` 函式接到 `__orc_fin` 之後，
# `$?` 先存後還；其他任何寫法都交給內建 trap，由完整性檢查判量不到。管線判定（`piped`）與前一版逐字相同。
PRELUDE = r'''set -T
__orc_dbg() {
  local -; set +xv
  case " ${FUNCNAME[*]:1} " in *" __orc_"*|*" trap "*|" test "*|" [ "*|" printf "*) return 0;; esac
  local __s=$1 __new=0 __x __m=0 __cur=off
  shift
  # 信任變數的比對放在每個命令之前、任何行程都做（R46）：群組跑在管線的子殼層裡，`{RUNNER_TEMP[0]}>` 改寫的值到主 shell 結束時早就看不到了。
  __orc_chk
  if [[ $BASHPID != "$__orc_pid" ]]; then
    __orc_pid=$BASHPID; __new=1
    echo "start $BASHPID" >> "$ORACLE_PF"
    builtin trap '__orc_fin' EXIT
  fi
  if [[ $# -ge 2 ]]; then
    case "$__orc_prev" in *neutralise.py*) echo "piped" >> "$ORACLE_MARK";; esac
    if [[ $__new = 0 ]]; then
      if [[ $__s = 0 ]]; then for __x in "$@"; do if [[ $__x != 0 ]]; then __m=1; fi; done; fi
      if [[ -o pipefail ]]; then __cur=on; fi
      echo "pf $BASHPID start=$__orc_pf end=$__cur masked=$__m rc=$__s" >> "$ORACLE_PF"
    fi
  fi
  __orc_prev=$BASH_COMMAND
  __orc_pf=off; if [[ -o pipefail ]]; then __orc_pf=on; fi
  return 0
}
__orc_fin() {
  local -; set +xv
  local __t=""
  builtin trap -p DEBUG >| "$ORACLE_PF.t$BASHPID"
  IFS= read -r __t < "$ORACLE_PF.t$BASHPID" || :
  if [[ $__t = "$__orc_want" ]]; then echo "fin $BASHPID ok" >> "$ORACLE_PF"
  else echo "fin $BASHPID dbg-changed" >> "$ORACLE_PF"; fi
  __orc_chk
  __orc_aud fin
}
__orc_ret() { return "$1"; }
__orc_tail=$'\n:'
trap() {
  local -; set +xv
  if [[ $# -eq 2 && ( $2 = EXIT || $2 = 0 ) ]]; then
    __orc_uexit=$1
    # R44（#33 verify R43 第 5、6 列）：(1) `__orc_ret "$__orc_x"` 在 errexit 下回傳非零就中止整個 EXIT 動作串、使用者的動作沒跑到——失敗路徑
    # 因此完全盲，真外流還被歸成「文法外（沒有外流）」；接 `&& :` 讓它在條件脈絡裡、`$?` 照樣留給使用者的動作。(2) 動作裡最後一條管線之後沒有
    # 下一個命令，DEBUG 不會再觸發、`PIPESTATUS` 沒人讀——動作字串後面補一行 `:`（在同一個 eval 裡，所以讀到的是動作最後一條管線）。
    builtin trap '__orc_x=$?; __orc_fin; __orc_ret "$__orc_x" && :; eval -- "$__orc_uexit$__orc_tail"' EXIT
    return 0
  fi
  builtin trap "$@"
}
__orc_init() {
  local -; set +xv
  __orc_prev=""
  __orc_pid=$BASHPID
  __orc_pf=off; if [[ -o pipefail ]]; then __orc_pf=on; fi
  builtin trap '__orc_dbg "$?" "${PIPESTATUS[@]}"' DEBUG
  builtin trap -p DEBUG >| "$ORACLE_PF.want"
  IFS= read -r __orc_want < "$ORACLE_PF.want"
  echo "start $BASHPID main" >> "$ORACLE_PF"
  builtin trap '__orc_fin' EXIT
}
# **primitive 稽核**（R46，#33 verify R45 第 1–3 列；DA 的 D11 的簡化版：不比對 lint 的詞數，只查 argv 形狀與信任變數）：R45 驗的樹（R44）以前，神諭觀察 PR 標記在 stdout／stderr／通道、pipefail 開關與注入哨兵，沒有任何一項記錄「文法收的 builtin 實際收到什麼」——
# `test {-v,"$X"}` 與 `{a[…]}>` 的缺口都在 lint 的詞模型與 bash 實際 argv／指派之間，沒有任何輸入餵它。這裡把 `[`、`test`、`printf` 換成記錄實際 argv 的函式
# （函式優先於 builtin；`builtin` 前綴與 `command` 不在文法裡），在每個命令之前（任何行程，不只主 shell）與行程結束時比對信任變數有沒有被改寫；Python 端（`aud_violations`）判讀。
# 包裝函式內關掉 xtrace，DEBUG 的防護條件跳過來自它們的呼叫（`FUNCNAME[1]`；R46 第一版在函式裡 `set +T`，管線的子殼層因此把 DEBUG trap 弄丟、探針判「被換掉」）。PRELUDE 內部一律用 `[[ ]]`，不經過這些函式。
declare -A __orc_tv0
# 不含 SHELLOPTS／BASHOPTS：`set -o`／`shopt` 本來就會改它們（`set -o pipefail` 之後 SHELLOPTS 變了）。
__orc_tvn=(HOME RUNNER_TEMP GITHUB_WORKSPACE TMPDIR PATH IFS BASH_ENV ENV GITHUB_ENV GITHUB_PATH GITHUB_OUTPUT GITHUB_STATE GITHUB_STEP_SUMMARY)
__orc_chk() {
  local __n
  for __n in "${__orc_tvn[@]}"; do
    if [[ ${!__n-<unset>} != "${__orc_tv0[$__n]}" ]]; then __orc_aud trusted "$__n"; __orc_tv0[$__n]=${!__n-<unset>}; fi
  done
}
# R48（#33 verify R47 第 4 列〔security／Codex 第 1 條／DA〕；記錄編碼與原子寫入是 Codex 第 2 條）：記錄是「名稱、欄位數、各欄位」，每個都以 NUL 結尾——argv 不可能含 NUL，所以邊界無法偽造（前一版用 0x1f／0x1e 分隔，printf 的格式含這兩個
# 字元時可以把 `%n` 藏掉）；整筆記錄用**一次** printf 寫完（記錄約 1 KB 內是單次 write、不交錯；更長的記錄 bash 的 printf 會分多次 write，同時寫會交錯——宣稱查核在 macOS bash 5.3.15 實測 1000 位元組不交錯、1500 位元組交錯；Linux 未測）；路徑存成唯讀的 `__orc_audp`，步驟改 `ORACLE_AUD` 不影響記錄。
__orc_aud() {
  local __f='%s\0%d\0' __a
  for __a in "${@:2}"; do __f+='%s\0'; done
  builtin printf "$__f" "$1" "$(( $# - 1 ))" "${@:2}" >> "$__orc_audp"
}
test() { local -; set +xv; __orc_aud test "$@"; builtin test "$@"; }
[() { local -; set +xv; __orc_aud '[' "$@"; builtin '[' "$@"; }
printf() { local -; set +xv; __orc_aud printf "$@"; builtin printf "$@"; }
readonly __orc_audp=$ORACLE_AUD
__orc_aud init
for __n in "${__orc_tvn[@]}"; do __orc_tv0[$__n]=${!__n-<unset>}; done
__orc_init
'''


def pick_bash():
    for cand in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("找不到 bash")


# 跨 step 的通道（R42，#33 verify R41 放行條件 3 的神諭那一半）：runner 在 step 結束後讀這些檔。神諭把它們指到空的暫存檔，
# 跑完看裡面有沒有 PR 文字。GITHUB_ENV／GITHUB_PATH 決定之後每一個 step 的環境；GITHUB_OUTPUT／GITHUB_STATE 經運算式流到
# 之後的 step；GITHUB_STEP_SUMMARY 顯示在執行摘要。神諭五個都看；R44 起 lint 的通道產生式也是同一組五個，不再是「神諭比 lint 嚴」。
CHANNELS = ("GITHUB_ENV", "GITHUB_PATH", "GITHUB_OUTPUT", "GITHUB_STATE", "GITHUB_STEP_SUMMARY")


def pf_observation(recs):
    """pipefail 探針的判讀（`on`／`off`／`no-pipeline`／`unmeasured`）。`off`：有一條多段管線開始時 pipefail 是關的——看到了就是
    事實，優先於完整性檢查；`unmeasured`：某個行程的 DEBUG trap 被換掉、或某個行程沒有跑到 `__orc_fin`；`no-pipeline`：沒有任何
    多段管線跑完。"""
    main = {l.split()[1] for l in recs if l.startswith("start ") and l.endswith(" main")}
    fins = dict(l.split()[1:3] for l in recs if l.startswith("fin "))
    pipes = [l for l in recs if l.startswith("pf ")]
    if any(" start=off " in l for l in pipes):
        return "off"
    # 缺 `fin` 只看**主 shell**：子殼層最後一個命令是外部程式時 bash 直接 exec，EXIT trap 本來就不會跑（`$(mktemp -d)`、管線裡的
    # `git …`）——那不是竄改（R42 自查：`good-r42-trap-exit` 因此被判量不到）。子殼層換掉 DEBUG trap 仍由 `dbg-changed` 抓到；
    # 子殼層同時換掉 DEBUG 與 EXIT 的雙重竄改看不到——正面文法拒絕任何 `trap … DEBUG` 與非 `trap <動作> EXIT` 的寫法，
    # 這種 step 一定是 lint 擋下的，看不到只會讓「量不到」變成「一致」，不改退出碼。
    if any(v != "ok" for v in fins.values()) or not main or main - set(fins):
        return "unmeasured"
    return "on" if pipes else "no-pipeline"


def run_script(run, bash, stub_bin, yaml_env=None, extra=False, inject=None):
    """跑一次 run 區塊，回傳 (verdict, observable, leaked, marker_lines)。
    verdict: 'piped' / 'called-unpiped' / 'not-invoked' / 'timeout'
    observable: 差分用的可觀察結果（rc, stdout, stderr, mark 內容）——逾時的那次不拿來差分。
    leaked: (stdout 有 PR 文字, stderr 有 PR 文字)。
    marker_lines: (stdout, stderr) 各自「含 PR 文字的行」的多重集合（Counter），臨時目錄路徑換成 `<TMP>`——
      已知類別 G 的差分比的是它（`classify_piped_leak`）：兩次執行的臨時目錄不同，bash 的錯誤訊息又帶腳本路徑。
    yaml_env: 從 YAML `env:` 收來的變數（R37，R36 第 8 列）；神諭自己的 PATH／HOME／PR_TITLE／ORACLE_MARK 一律蓋過它。
    extra=True 時另外回傳第五項 dict：`pf`（`pf_observation`）與 `chan`（帶 PR 文字的通道名，見 `CHANNELS`）、`inject`（哨兵檔有沒有東西）、`aud`（`aud_violations` 的觀察）。
    inject：`INJECT_PAYLOADS` 的一組——PR 相關的環境變數設成它（不是 PR_MARKER），`$ORACLE_INJECT` 指到哨兵檔（R44，第 1–3 列）。"""
    # `ignore_cleanup_errors=True`（Python 3.10+；R48 量測鏈 v10，#33）：步驟留下的背景行程（`cmd >/dev/null 2>&1 &`，不握著 stdout／stderr，`subprocess.run` 不等它）
    # 在清理時還在寫儀器目錄——`rmtree` 剛刪掉通道檔，`>> "$GITHUB_ENV"` 又建回來，`rmdir` 報 `OSError: [Errno 66] Directory not empty`，整支神諭帶著 traceback 崩潰，
    # mutation 的前置檢查（未突變的基準驗證）因此隨機紅了一次。清理發生在所有觀測都讀完之後，清不乾淨只是留下一個暫存目錄，不改變任何判定，所以吞掉這一類錯誤；
    # 背景行程本身不殺（既有行為，也沒有東西要靠它被殺）。探針：`oracle-probes/straggler-writes-during-cleanup.yml`。
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        # R48（#33 verify R47 第 4 列；宣稱查核 E 組）：儀器檔（mark／pf／inject／aud）與跨 step 通道檔放在步驟 cwd **底下名稱帶隨機後綴、以 `.` 開頭的子目錄**——前一版放在 cwd 本身，`: > aud`、
        # `tee chan-GITHUB_E""NV < /dev/null`（相對路徑重導向或外部命令）能把它們截斷、讓稽核與通道觀察失明；第二版固定叫 `.orc/`，外部命令（`tee .orc/inject`）仍到得了。現在步驟拿不到名字
        # （`ls -a` 與 glob 仍看得到：**這不是 sandbox**，fixture 受信）；稽核檔另有 `init`／`fin`、解析、唯讀路徑的檢查（`aud_violations`），其餘檔案沒有完整性檢查。
        inst = tempfile.mkdtemp(prefix=".orc-", dir=d)
        mark = os.path.join(inst, "mark")
        open(mark, "w").close()
        pf = os.path.join(inst, "pf")
        open(pf, "w").close()
        chan = {c: os.path.join(inst, "chan-" + c) for c in CHANNELS}
        for c in chan.values():
            open(c, "w").close()
        script = os.path.join(d, "s.sh")
        with open(script, "w") as fh:
            # 收尾命令由 PRELUDE 的 EXIT trap（`__orc_fin`；使用者的 `trap <動作> EXIT` 經 `trap` 函式接在它後面）提供——**不要**在這裡再補文字，
            # 那正是 R32 DA-6 抓到的缺陷（heredoc 會吞掉它）。
            fh.write(PRELUDE); fh.write(run); fh.write("\n")
        env = dict(yaml_env or {})
        # runner 一定會設、lint 的正面文法也信任的兩個變數（R42：`FL_TARGET_VARS`／`FL_GHVALUE_VARS`）。前一版不設，
        # `> "$RUNNER_TEMP/e"` 在神諭裡變成寫 `/e`、失敗，那一步做了什麼就量不到（`bypass-r42-ghenv` 的 ge-alias-var、ge-cat-file）。
        runner_temp = os.path.join(d, "runner_temp")
        os.mkdir(runner_temp)
        env.update({"PATH": stub_bin + ":/usr/bin:/bin", "ORACLE_MARK": mark, "ORACLE_PF": pf,
                    "PR_TITLE": PR_MARKER, "HOME": d, "PS4": PS4_MARK,
                    "RUNNER_TEMP": runner_temp, "GITHUB_WORKSPACE": d})
        env.update(chan)
        inj_file = os.path.join(inst, "inject")
        open(inj_file, "w").close()
        env["ORACLE_INJECT"] = inj_file
        aud_file = os.path.join(inst, "aud")
        open(aud_file, "w").close()
        env["ORACLE_AUD"] = aud_file
        if inject is not None:
            for k in {"PR_TITLE", "PR_BODY"} | {k for k, v in (yaml_env or {}).items() if "${{" in str(v)}:
                env[k] = inject

        def more():
            recs = open(pf).read().split("\n")
            got_chan = [c for c, path in chan.items() if PR_MARKER in open(path, errors="replace").read()]
            return {"pf": pf_observation(recs), "chan": got_chan,
                    "inject": INJECT_MARKER in open(inj_file, errors="replace").read(),
                    "aud": aud_violations(open(aud_file, "rb").read())}
        try:
            # stdin **一定要**是 /dev/null：繼承呼叫端的 stdin 會讓任何讀 stdin 的指令卡住，
            # 於是「量不到」變成隨呼叫環境而定的東西（R31 自查：同一個 fixture 在終端機下逾時、
            # 在 pipe 下不逾時）。runner 的 step stdin 也不是終端機。
            r = subprocess.run([bash, script], env=env, cwd=d, capture_output=True,
                               stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as e:
            # 逾時之前的輸出要留著（R40，#33 verify R39 第 8 列）：前一版丟掉它、判「量不到」——一個已經外流、只是之後的命令比
            # TIMEOUT_S 慢的 step 就變成 rc=0。這一次不拿來差分（obs=None），只回報已經看到的外流。
            so, se = e.stdout or b"", e.stderr or b""
            leaked = (PR_MARKER.encode() in so, PR_MARKER.encode() in se)
            mlines = tuple(collections.Counter(l.replace(inst, "<INST>").replace(d, "<TMP>") for l in s.decode("utf-8", "replace").split("\n")
                                               if PR_MARKER in l) for s in (so, se))
            # R44（#33 verify R43 第 7 列）：通道檔裡已經寫進去的 PR 文字也是事實，不因為之後逾時而撤銷（stdout／stderr 同一個原則）。
            got_chan = [c for c, path in chan.items() if PR_MARKER in open(path, errors="replace").read()]
            return ("timeout", None, leaked, mlines) + (({"pf": "unmeasured", "chan": got_chan,
                                                           "inject": INJECT_MARKER in open(inj_file, errors="replace").read(),
                                                           "aud": aud_violations(open(aud_file, "rb").read(), complete=False)},) if extra else ())
        got = open(mark).read().split("\n")
        # 分開記 stdout 與 stderr：外流走哪一條流是歸類的輸入（S-2 只可能走 stderr；管線自己印到 stdout 一律是繞過）。
        leaked = (PR_MARKER.encode() in r.stdout, PR_MARKER.encode() in r.stderr)
        # 暫存目錄換成 `<TMP>`（R42 自查）：bash 的錯誤訊息帶腳本路徑，每次執行的暫存目錄不同——前一版的差分（`real_declaration`）
        # 因此在任何會印 bash 錯誤的宣告 step 上都判「不是宣告」（`gen-g-d-008`：`[ -n a{b,c} ]` 的錯誤訊息）。`mlines` 早就這樣做。
        # R48：儀器目錄（`.orc-` 加隨機後綴）先換成 `<INST>`——它在 `d` 底下，不先換的話每次執行的後綴不同，xtrace 之類會印出路徑的 step 在宣告差分裡每次都「不同」
        # （量測 v9 抓到：`good-r37o-module-misc-env-trace-declared-logfilter` 從一致變量不到）。
        tmpb, instb = d.encode(), inst.encode()
        obs = (r.returncode, r.stdout.replace(instb, b"<INST>").replace(tmpb, b"<TMP>"), r.stderr.replace(instb, b"<INST>").replace(tmpb, b"<TMP>"), sorted(got))
        mlines = tuple(collections.Counter(l.replace(inst, "<INST>").replace(d, "<TMP>") for l in s.decode("utf-8", "replace").split("\n")
                                           if PR_MARKER in l) for s in (r.stdout, r.stderr))
        o = "piped" if "piped" in got else ("called-unpiped" if any(l.startswith("called ") for l in got) else "not-invoked")
        return (o, obs, leaked, mlines) + ((more(),) if extra else ())


MARKER_RE = re.compile(r"#\s*LOG-FILTER:\s*(?:in-process|none — .+)")
_GH_TRIGGER_RE = re.compile(r"GITHUB_ENV|GITHUB_PATH")


def _without_or_lists(run):
    """剔除前面不是反斜線的 `||`（「或」不是管線）——與 lint 的 `flat_trigger` 同一套規則。"""
    out, i = [], 0
    while i < len(run):
        if run.startswith("||", i) and (i == 0 or run[i - 1] != "\\"):
            i += 2
            continue
        out.append(run[i])
        i += 1
    return "".join(out)


def in_grammar(run, yaml_declared=False):
    """`--strict` 的正面文法對這個 step 有宣稱嗎（R45 第 10 列〔logic〕）：宣告了 `# LOG-FILTER:` 而沒有觸發（剔除 `||` 之後的 run 文字沒有 `|`、沒提到 `GITHUB_ENV`／`GITHUB_PATH`）的
    step 不進文法（lint 檔頭 L3）——lint 對它放行是對的，神諭的 primitive 稽核與注入探針都不該把它報成「繞過」。
    **宣告有三個來源**（與 lint 的 `declared` 一致）：run 區塊內的註解（`MARKER_RE`）、step 範圍內的 YAML 註解行、`run:` 行尾註解（後兩者由 `yaml_declaration` 判，呼叫端算好傳 `yaml_declared`；
    test.yml 自己用的是 YAML 層那種）；R47 之前只認第一種，YAML 層宣告而沒有觸發的 step 被當成在文法內、稽核報成「繞過」。
    觸發條件複製 lint 的 `_fl_declared_trigger` 的**第一種讀法**（對原文跑 `flat_trigger`：先剔除前面不是反斜線的 `||`，再找 `|`）。R46 宣稱查核更正：前一版只看 `|` 字元、宣稱「同一把尺」，
    所以只含 `||` 的宣告 step 被神諭當成在文法內（`audit-declared-step-or-only-not-in-grammar`）。**第二種讀法**（對 `flat_substitute` 之後的文字再跑一次 `flat_trigger`；兩種讀法 or 起來）：
    R47 logic 的實例是 `echo x \\${{ '' }}||cat`——原文 `||` 前面是 `}`、被剔除當「或」，字面常數代換成空字串之後反斜線與 `||` 相鄰，第二種讀法觸發（lint `--strict` rc=1，對照沒有反斜線的 rc=0）。
    神諭三個呼叫點傳進來的都是**代換之後**的 run（`substitute_runner_exprs`）：運算式全是字面常數時它等於第二種讀法的文字；非字面運算式在神諭是換成 payload、在 lint 的第二種讀法是刪掉，兩者不同
    （例：`echo x \\${{ github.event.pull_request.title }}||cat` lint 觸發、神諭的 `in_grammar` 回 False）。兩個方向的差異都存在：原文才觸發、代換後不觸發的有 `fixtures/ci-log-filter-restrict-r42-declared-opsweep.yml`
    第三步（`a |${{ null }}| b` 代換成 `a || b`，神諭看不到、lint 判 RULE）；非字面運算式裡的 `|` 那一型沒有 fixture。這些是殘餘，不是已修（R48 更正：這個 docstring 前兩版都把方向寫錯）。"""
    declared = bool(yaml_declared) or bool(MARKER_RE.search(run))
    return not (declared and "|" not in _without_or_lists(run) and not _GH_TRIGGER_RE.search(run))


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
        # stderr 也不得多出 baseline 沒有的外流行（R40，#33 verify R39 第 3 列）：前一版只禁新增的 stdout，於是改寫後換成另一種
        # 內容的 stderr 外流，也被當成「補上 `2>&1` 就修好了」而歸 S-2。
        return (v != "timeout" and not (contrib & ml[1]) and not (ml[0] - base_ml[0])
                and not (ml[1] - base_ml[1]))

    # heredoc 的內文不是命令，`_pipe_to_pipeamp` 卻會改寫它、讓外流的**內容**變了（R39 verify 第 3 列）——這一類由上面「stderr 不得多出
    # baseline 沒有的外流行」接住，不另外擋 `<<`：R40 第一版見到 `<<` 就不做差分，產生語料裡 folded 成一行的 heredoc 形狀
    # （`cat <<EOF… echo "$PR_TITLE" | …` 全在同一行、沒有內文）60 條 S-2 全部掉成繞過——那些行根本沒有內文可改。
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
    """mapping 節點的 `env:`（純量值才收；鍵非空、鍵不含 `=`、鍵值合併不含 NUL byte）。R37，R36 第 8 列。
    **含 `${{` 的值照 run 區塊的規則代換**（R42，#33 verify R41）：字面常數換成值、`GH_SAFE_EXPRS` 換成數字、其餘當成 PR 可控，
    換成 `PR_MARKER`。前一版不設這些變數，`env: PR_BODY: ${{ github.event.pull_request.body }}` 的 step 把 `$PR_BODY` 寫到哪裡
    神諭都看不到（R42 自查：`bypass-r42-ghenv` 42 步只量到 13 步的通道外流）。env 的值是資料、不會被 shell 剖析，
    所以只用純標記、不用 `RUNNER_PAYLOADS` 的逃脫形式。"""
    if not isinstance(node, yaml.MappingNode):
        return {}
    e = {kk.value: vv for kk, vv in node.value if isinstance(kk, yaml.ScalarNode)}.get("env")
    if not isinstance(e, yaml.MappingNode):
        return {}
    return {k.value: substitute_runner_exprs(v.value, PR_MARKER) for k, v in e.value
            if isinstance(k, yaml.ScalarNode) and isinstance(v, yaml.ScalarNode)
            and k.value and "=" not in k.value and "\0" not in k.value + v.value}


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
                    prefix = ""
                    if eff is not None:
                        prefix = bash_template_prefix(eff)
                        note = None if prefix is not None else "shell 是 %r" % eff
                    elif "container" in jkv:
                        note = "job 跑在 container 裡、沒寫 shell（預設 sh）"
                    elif "windows" in ro_text.lower() or "${{" in ro_text:
                        note = "runs-on 是 %r、沒寫 shell（Windows 預設 pwsh；運算式無法靜態判定）" % ro_text
                    else:
                        note, prefix = None, "set -e; "          # 沒寫 shell、不在 container：GitHub 用 `bash -e {0}`
                    body = run.value
                    if note is None and prefix:
                        body = prefix + body                     # 同一行：行號不動（錯誤訊息的行號要對得上）
                    out.append((jk.value, name, body, (starts[idx], end), note, dict(job_env, **_env_of(st))))
    return out


# bash 樣板的旗標 → 神諭在 run 第一行前面加的 `set`（R40，#33 verify R39 放行條件 12、DA N3）。前一版只認關鍵字 `bash`、而且照裸的 `bash`
# 跑——runner 其實用 `bash --noprofile --norc -eo pipefail {0}`；`bash -e {0}`（GitHub 沒寫 shell 時的預設）等二十個樣板全判不可比。
# **封閉列舉**：旗標只收 `-e`、`-u`、`-o pipefail`（可合寫成 `-eo pipefail`、`-euo pipefail`、`-eu`）、`--noprofile`、`--norc`
# （後兩個對非互動的腳本沒有作用）；其餘旗標（`-x`、`-v`、`-l`、`-O …`…）照舊不可比。
_TEMPLATE_BASH = ("bash", "/bin/bash", "/usr/bin/bash")


def bash_template_prefix(sh):
    """`shell:` 的值 → 要加在 run 前面的 `set …; `；不是封閉列舉裡的樣板回 None（不可比）。"""
    sh = sh.strip()
    if sh == "bash":
        return "set -eo pipefail; "
    toks = sh.split()
    if len(toks) < 2 or toks[0] not in _TEMPLATE_BASH or toks[-1] != "{0}":
        return None
    opts, i = [], 1
    while i < len(toks) - 1:
        x = toks[i]
        if x in ("--noprofile", "--norc"):
            pass
        elif re.fullmatch(r"-[eu]+", x):
            opts += ["-" + c for c in x[1:]]
        elif re.fullmatch(r"-[eu]*o", x) and i + 1 < len(toks) - 1 and toks[i + 1] == "pipefail":
            opts += ["-" + c for c in x[1:-1]] + ["-o pipefail"]
            i += 1
        elif x == "-o" and i + 1 < len(toks) - 1 and toks[i + 1] == "pipefail":
            opts.append("-o pipefail")
            i += 1
        else:
            return None
        i += 1
    return ("set %s; " % " ".join(opts)) if opts else ""


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


def kd_hash(run):
    """KNOWN_DISAGREE 條目的內容雜湊（R42，#33 verify R41 DA-5）：`steps_with_lines` 給的 run 區塊——YAML 已經去掉縮排、
    照 block scalar 的規則接好行，**運算式代換之前**——換行一律 `\n`，UTF-8 位元組的 sha256。條目只擔保它被寫下時的那段
    文字：內容改了，理由就要重新判斷。算法改了這裡，所有條目的 `hash` 都要重算（`--print-kd-hash`）。"""
    return "sha256:" + hashlib.sha256(run.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _severity(verdict, classes):
    """`select_most_severe` 的等級：stdout 外流的繞過＝跨 step 通道的繞過 > 其他繞過 > 已知類別 > 量不到 > 其他。"""
    if verdict.startswith("不一致：繞過") and not classes:
        return 4 if ("印到 stdout" in verdict or "跨 step 通道" in verdict) else 3
    if classes:
        return 2
    return 1 if verdict.startswith("量不到") else 0


def select_most_severe(results):
    """`results`：[(verdict, classes), …]，依 payload 的順序。回傳最嚴重那一份的索引（同級取最前面）。R42（#33 verify R41
    logic F9）：前一版取「第一個外流的 payload」，一組只從 stderr 外流、被歸進 S-2 的 payload 因此蓋掉後面一組印到 stdout 的繞過。"""
    best = 0
    for i, (v, c) in enumerate(results):
        if _severity(v, c) > _severity(*results[best]):
            best = i
    return best


def selftest_severity():
    """`--selftest-severity`：`select_most_severe` 的單元測試（`oracle_selfcheck.py` 呼叫），合成的判定，不跑 bash。"""
    out = ("不一致：繞過（接 neutralise 的管線自己把 PR 文字印到 stdout——不是 G 也不是 S-2）", [])
    err = ("不一致：繞過（接 neutralise 的管線自己把 PR 文字印到 stderr，但每一段補上 `2>&1`…——不是 S-2）", [])
    s2 = ("不一致：繞過（已知類別 S-2：管線自己只從 stderr 外流——…）", ["S-2"])
    chan = ("不一致：繞過（跨 step 通道：GITHUB_ENV 帶 PR 文字——之後的 step 讀得到）", [])
    ok, unm = ("一致", []), ("量不到（逾時 5s）", [])
    cases = [([err, out], 1), ([out, err], 0), ([s2, err], 1), ([s2, out], 1), ([ok, s2], 1), ([ok, ok], 0),
             ([s2, chan], 1), ([ok, unm], 1), ([chan, out], 0)]
    for items, want in cases:
        got = select_most_severe(items)
        if got != want:
            print("✗ select_most_severe(%s) = %d，預期 %d" % ([v[:24] for v, _ in items], got, want))
            return 1
    print("select_most_severe ok（%d 組）" % len(cases))
    return 0


def selftest_aud():
    """`--selftest-aud`：`aud_violations` 的單元測試（R48，#33 verify R47 第 4 列〔Codex 第 2 條〕；`oracle_selfcheck.py` 呼叫），合成的稽核檔位元組，不跑 bash。
    覆蓋：合法的最小串流無違規；`%n` 格式、`-v` 運算元、信任變數被改寫各報一條；**偽造的記錄邊界字元（0x1e／0x1f）不再藏得住 `%n`**；沒有 init、沒有 fin（跑完的執行）、
    逾時（`complete=False`）不要求 fin、截斷、欄位數不是整數、欄位數超出檔案、最後一筆沒結尾各**至少**報一條儀器完整性（損毀與截斷類連帶報「沒有 fin」，最後一筆沒結尾連「沒有 init」也報）；逾時不要求 fin、不報。"""
    def rec(name, *fields):
        return b"".join(x.encode() + b"\0" for x in (name, str(len(fields)), *fields))
    init, fin = rec("init"), rec("fin")
    integ = lambda out: [x for x in out if x.startswith(AUD_INTEGRITY)]
    viol = lambda out: [x for x in out if not x.startswith(AUD_INTEGRITY)]
    cases = [
        ("合法的最小串流", aud_violations(init + rec("printf", "%s\n", "x") + rec("test", "-n", "a") + fin), lambda o: o == []),
        ("`%n` 格式", aud_violations(init + rec("printf", "%n", "Z") + fin), lambda o: len(viol(o)) == 1 and not integ(o)),
        ("`test -v` 運算元", aud_violations(init + rec("test", "-v", "X") + fin), lambda o: len(viol(o)) == 1 and not integ(o)),
        ("信任變數被改寫", aud_violations(init + rec("trusted", "HOME") + fin), lambda o: len(viol(o)) == 1 and "HOME" in o[0]),
        ("偽造記錄邊界字元藏不住 `%n`", aud_violations(init + rec("printf", "%s\x1eignored\x1f%n", "x", "Z") + fin), lambda o: len(viol(o)) == 1),
        ("沒有 init", aud_violations(rec("printf", "%n", "Z") + fin), lambda o: len(integ(o)) == 1 and len(viol(o)) == 1),
        ("跑完卻沒有 fin", aud_violations(init + rec("test", "-n", "a")), lambda o: len(integ(o)) == 1),
        ("逾時不要求 fin", aud_violations(init + rec("test", "-n", "a"), complete=False), lambda o: o == []),
        ("空檔（被截斷）", aud_violations(b""), lambda o: len(integ(o)) >= 1),
        ("最後一筆沒有結尾", aud_violations(init + b"printf\x001\x00%n"), lambda o: any("沒有結尾" in x for x in o)),
        ("欄位數不是整數", aud_violations(init + b"printf\x00x\x00"), lambda o: any("不是整數" in x for x in o)),
        ("欄位數超出檔案", aud_violations(init + b"printf\x005\x00a\x00"), lambda o: any("超出檔案" in x for x in o)),
    ]
    for what, got, ok in cases:
        if not ok(got):
            print("✗ aud_violations（%s）= %r" % (what, got))
            return 1
    print("aud_violations ok（%d 組）" % len(cases))
    return 0


def run_lint(largs, f):
    return subprocess.run(["bash", str(LINT)] + largs + [str(f)], capture_output=True, text=True)


def check_file(f, text, bash, stub_bin):
    """一個 workflow 檔的逐 step 對帳。回傳 dict：rows、disagree、stale、unmeasured、seen（歸類的 Counter）、
    failures（這個檔讓神諭 rc=1 的每一個理由，一句一條——must-fail 探針拿它比對宣告的理由）、
    cls_stale、cls_undeclared（已知類別檔頭宣告與神諭實際歸類的落差，見下方類別閘門）。"""
    res = {"rows": [], "disagree": [], "stale": [], "unmeasured": [], "seen": collections.Counter(), "failures": [],
           "uncomparable": [],
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
    declared = collections.Counter(KNOWN_CLASS_RE.findall(text))
    for _job, name, run, (a, b), shell_note, yenv in steps:
        key = (f.name, name, a + 1)     # **含行號**（#33 verify R34 DA n1）：同名 step 不得共用一個 key
        run0 = run                      # KD 的雜湊算在運算式代換之前（`kd_hash`）
        in_step = lambda ln: a + 1 <= ln <= b + 1
        step_rules = [m for ln, m in rules if in_step(ln)]
        # `[--strict]` 的 pipefail 規則管的是**退出碼被遮蔽**，不是 PR 文字外流。R35–R41 神諭量不到它，這種 step 一律判不可比；
        # R42 起有 pipefail 探針（PRELUDE），照常跑，再依探針判（見下方 strict 檔的疊加）。探針說「沒有管線跑完」時仍是不可比。
        pf_only = bool(step_rules) and all(PIPEFAIL_RULE_MSG in m for m in step_rules)
        if shell_note:
            rows.append((f.name, name, "-", "-", "不可比（%s——神諭只會用 bash 跑）" % shell_note))
            # R40（#33 verify R39 放行條件 12）：不可比的 step 前一版直接跳過——掛在它上面的 KNOWN_DISAGREE 條目因此永遠不會過期
            # （理由已經量不到，卻被靜默保留）；檔頭宣告 `ORACLE-COMPARABLE` 的檔，每個 step 都必須可比。
            if key[:2] in KNOWN_DISAGREE:
                res["stale"].append(key)
            if "# ORACLE-COMPARABLE" in text:
                res["uncomparable"].append(key)
                res["failures"].append("%s（第 %d 行）：宣告了 ORACLE-COMPARABLE，卻不可比（%s）" % (name, a + 1, shell_note))
            continue
        yaml_decl_step = yaml_declaration(text, a, b, bodies)   # R48：YAML 層的 `# LOG-FILTER:` 宣告（`in_grammar` 的第二個來源）
        def judge(run, o, obs, leaked, mlines, more):
            """一次執行的判定（R42 WP8 抽出來：每一組 payload 各判一次，再選一份）。回傳 (verdict, classes, 量不到?, lint)。"""
            unm = False
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
            if o == "timeout" and lint == "pass" and (leaked[0] or leaked[1]):
                verdict = ("不一致：繞過（逾時之前已經觀察到 PR 文字外流——量不到的只是之後的部分，不抵銷已觀察到的外流）")
            elif o == "timeout" and lint == "RULE-red" and (leaked[0] or leaked[1]):
                # lint 擋下、逾時之前已經觀察到外流（R42，#33 verify R41 第 20 列）：同「RULE ∧ 外流 → 一致」，擋下是對的。
                # 前一版落到下一格「量不到」，逐項印出卻不是事實——外流已經看到了。
                verdict = "一致"
            elif o == "timeout" and lint == "pass" and "--strict" in largs and more["chan"]:
                verdict = ("不一致：繞過（逾時之前跨 step 通道已經帶了 PR 文字：%s——量不到的只是之後的部分，不抵銷已寫進去的）"
                           % "、".join(more["chan"]))
            elif o == "timeout" and lint == "RULE-red" and "--strict" in largs and more["chan"]:
                verdict = "一致"
            elif o == "timeout":
                verdict = "量不到（逾時 %ds）" % TIMEOUT_S
                unm = True
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
                        elif any(in_step(ln) and GRAMMAR_RULE_TAG in m for ln, m in strict_out()[0]):
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
                            verdict = ("不一致：繞過（接 neutralise 的管線自己把 PR 文字印到 stderr，而 `--strict` 的正面文法"
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
                    unm = True
            elif o != "piped":
                verdict = "一致"
            elif leaked[0] or leaked[1]:
                # **有管線不等於沒有外流**（R35）：lint 擋下、bash 也確實建了接 neutralise 的管線，但 PR 文字
                # 仍然出去了（fd 轉向到 stderr、xtrace、管線以外的命令）——擋下是對的。前一版這一格一律判誤擋。
                verdict = "一致"
            else:
                verdict = "不一致：誤擋"
            # **strict 檔的疊加**（R42，#33 verify R41 放行條件 3、5）：lint 在 `--strict` 下額外宣稱兩件事——每條管線跑在 pipefail
            # 之下、過濾 step 不寫跨 step 的通道——神諭各有一個觀測（`pf_observation`、`CHANNELS`）。預設模式不宣稱這兩件事，不疊加。
            # 逾時的那次兩個觀測都不可信，也不疊加。判準：lint 擋下 ∧（pipefail 關了或通道帶 PR 文字）⇒ 擋下是對的，一致；
            # lint 放行 ∧ 其一成立 ⇒ 繞過；探針被換掉 ⇒ 量不到（已經看到外流的繞過不改：外流是事實）。
            if "--strict" in largs and o != "timeout" and lint in ("pass", "RULE-red"):
                pfo, chans = more["pf"], more["chan"]
                if pf_only and pfo == "no-pipeline" and not chans:
                    verdict = "不可比（`--strict` 的 pipefail 規則是這個 step 唯一的 RULE，而沒有任何多段管線跑完——量不到退出碼遮蔽）"
                elif lint == "RULE-red" and (pfo == "off" or chans) and not verdict.startswith("一致"):
                    verdict = "一致"
                elif lint == "pass" and chans and not verdict.startswith("不一致：繞過"):
                    verdict = "不一致：繞過（跨 step 通道：%s 帶 PR 文字——之後的 step 讀得到）" % "、".join(chans)
                elif lint == "pass" and pfo == "off" and not verdict.startswith("不一致：繞過"):
                    verdict = "不一致：繞過（pipefail：管線在 pipefail 關閉下完成，退出碼被遮蔽）"
                elif pfo == "unmeasured" and not verdict.startswith("不一致：繞過") and not verdict.startswith("不可比"):
                    verdict = "量不到（pipefail 探針被換掉：腳本改了 DEBUG trap 或繞過了 EXIT 的組合）"
                    unm = True
            # **primitive 稽核的疊加**（R46，#33 verify R45 第 1–3 列）：`--strict` 另外宣稱「文法收的 builtin 只會收到文法點名的形狀」——`test`／`[` 的 argv 在三種形狀裡、`printf` 的格式在封閉的轉換列舉裡、
            # 信任變數不被改寫。神諭看的是 builtin **實際**收到什麼（PRELUDE 的包裝函式），與 PR 文字有沒有出現在 log 無關，所以不需要任何 payload：lint 放行 ∧ 有違反 ⇒ 繞過；
            # lint 擋下 ∧ 有違反 ⇒ 擋下是對的，一致（取代「誤擋」；**「違反」是超出 lint 的形狀，不代表危險**——無害的誤擋如 `[ "$A" != b ]`、`printf '%ld'` 也在這裡被判一致，R47 第 5 列）。逾時之前已經記下的也算（同通道證據的原則）。宣告而沒有觸發的 step 不進文法（`in_grammar`）。
            # R48（#33 verify R47 security／Codex）：**儀器完整性**——步驟文字提到 `ORACLE_*`／`__orc_*`，或稽核檔沒有 init／fin、解析不出來，儀器就不可信：判「量不到」，不判一致
            # （已經看到外流的繞過不改：外流是事實）。這不是 sandbox：fixture 受信，這一層擋的是意外與兩個具體的失明法（改儀器變數、截斷儀器檔）。
            aud_all = more.get("aud") if isinstance(more, dict) else None
            aud = [x for x in (aud_all or []) if not x.startswith(AUD_INTEGRITY)]
            integ = [x for x in (aud_all or []) if x.startswith(AUD_INTEGRITY)]
            if "--strict" in largs and lint in ("pass", "RULE-red") and in_grammar(run, yaml_decl_step) \
                    and (integ or ORC_NAME_RE.search(run)) and not verdict.startswith("不一致：繞過"):
                verdict = "量不到（儀器不可信：%s）" % (integ[0][len(AUD_INTEGRITY):] if integ else "步驟文字提到神諭的儀器變數 `ORACLE_*`／`__orc_*`")
                classes, unm = [], True
            elif aud and "--strict" in largs and lint in ("pass", "RULE-red") and in_grammar(run, yaml_decl_step):
                if lint == "pass" and not verdict.startswith("不一致：繞過"):
                    verdict, classes, unm = "不一致：繞過（primitive 稽核：%s）" % aud[0], [], False
                elif lint == "RULE-red" and not verdict.startswith("一致"):
                    verdict, classes, unm = "一致", [], False
            return verdict, classes, unm, lint

        if has_nonliteral_expr(run):
            # **每一組 payload 都跑、都判定，再選一份**（R42，#33 verify R41 logic F9）：lint 放行時取最嚴重的（`select_most_severe`），
            # lint 擋下時取第一份判一致的（任何一組外流都證明擋下是對的）。前一版取第一個外流的 payload，stderr 的 S-2 蓋掉了 stdout 的繞過。
            # 不適用的 payload（heredoc 那一組，運算式不在 heredoc 內文裡）跳過；每一組都語法壞掉 ⇒ 量不到。
            cands = []
            for payload in RUNNER_PAYLOADS:
                cand = substitute_runner_exprs(run, payload)
                if cand is not None:
                    cands.append((cand,) + run_script(cand, bash, stub_bin, yenv, extra=True))
            judged = [(judge(*c), c) for c in cands]
            syn = [_bash_n(c[0], bash)[0] == 0 for c in cands]
            lint0 = judged[0][0][3]
            if lint0 == "pass":
                # 語法壞掉、又沒有任何外流的那一組不參與排序：bash 一行都沒跑，它的「量不到」只是代換的假象（R42 自查：
                # `good-r40-ghexpr-declared-step` 被雙引號與算術那幾組蓋成量不到）。語法壞掉但**有**外流的照算——bash 逐條命令讀、
                # 語法錯誤之前的命令已經跑了，那些外流是真的。
                ranked = [i for i, c in enumerate(cands) if syn[i] or c[3][0] or c[3][1] or c[5]["chan"]] or [0]
                pick = ranked[select_most_severe([(judged[i][0][0], judged[i][0][1]) for i in ranked])]
            else:
                pick = next((i for i, j in enumerate(judged) if j[0][0] == "一致"), 0)
            (verdict, classes, unm, lint), (run, o, obs, leaked, mlines, more) = judged[pick]
            if (lint == "pass" and not (leaked[0] or leaked[1]) and verdict.startswith("一致") and not any(syn)):
                verdict, unm = "量不到（每一組 payload 代換之後語法都壞掉——運算式所在的脈絡逃不出去）", True
        else:
            run = substitute_runner_exprs(run, None)
            o, obs, leaked, mlines, more = run_script(run, bash, stub_bin, yenv, extra=True)
            verdict, classes, unm, lint = judge(run, o, obs, leaked, mlines, more)
            # **注入探針**（R44，#33 verify R43 第 1–3 列；`INJECT_PAYLOADS` 的說明在檔頭常數處）：只在 `--strict` 的檔、而且神諭還沒有觀察到外流的
            # 兩格才跑——(1) lint 放行、PR 標記沒外流（判「一致」，這是**放行**的那一方向，探針要抓的就是這一格）；(2) lint 擋下、PR 標記沒外流
            # （判「誤擋」）。放行 ∧ 哨兵有東西 ⇒ 繞過；擋下 ∧ 哨兵有東西 ⇒ 一致（擋下是對的，不是「文法外」）。
            # （第一版的條件寫成「判定不是一致」，於是 lint 放行而標記沒外流的那一格——判定本來就是一致——根本沒跑到探針；
            # `oracle_selfcheck` 第 29 項用「永遠放行」的替身抓到。）
            # R46（#33 verify R45 logic 第 4、5 列）：(1) **逾時的那一格也跑**——前一版的條件含 `o != "timeout"`，於是「注入完成之後才被 `/bin/sleep` 拖逾時」的 step 判量不到（rc=0），
            # 與 R44 自己對通道證據的原則（「後續逾時不抵銷先前已發生的效果」）不一致；探針自己逾時也沒關係，哨兵在逾時之前寫進去就看得到。(2) **只在文法內的 step 跑**（`in_grammar`）：
            # 宣告了 `# LOG-FILTER:` 而沒有觸發的 step 本來就不進正面文法（L3），探針不該把它報成未知繞過。
            timed = o == "timeout" and unm
            if ("--strict" in largs and "$" in run0 and in_grammar(run, yaml_decl_step)
                    and ((lint == "pass" and (verdict.startswith("一致") or timed))
                         or (lint == "RULE-red" and (verdict.startswith("不一致：誤擋") or timed)))
                    and (not unm or timed)):
                hit = next((pl for pl in INJECT_PAYLOADS
                            if run_script(run, bash, stub_bin, yenv, extra=True, inject=pl)[4]["inject"]), None)
                if hit is not None:
                    unm = False
                    if lint == "pass":
                        verdict = "不一致：繞過（注入：PR 文字被當程式碼執行，哨兵檔有東西；payload `%s`）" % hit.split("PWD[")[0].strip()
                        classes = []
                    else:
                        verdict, classes = "一致", []
        if unm:
            res["unmeasured"].append(key)
        if not classes and verdict.startswith("不一致"):
            # **KD 條目要對上方向與內容**（R42，#33 verify R41 DA-5）：前一版只比 (檔名, step 名)，一條登記成誤擋的條目吞掉了
            # 同名 step 的繞過（`oracle-probes/kd-direction`）。現在方向與 `kd_hash` 都要相符，否則照一般的不一致處理。
            kd = KNOWN_DISAGREE.get(key[:2])
            kdir = "誤擋" if verdict.startswith("不一致：誤擋") else "繞過"
            if kd is None:
                # **文法外**（R42）：只在誤擋這一格、KD 之後判。三個條件同時成立：這個 step 的每一條 RULE 都是文法擋的
                # （帶 `GRAMMAR_RULE_TAG`）或 pipefail 那一條；沒有任何外流（走到這一格已經是「無外流」）；
                # 整個判定只在 `lint == "RULE-red"` 時成立（PARSE 的誤擋另一格）。由檔頭 `# KNOWN-CLASS: 文法外` 簽名。
                if (verdict == "不一致：誤擋" and step_rules
                        and all(GRAMMAR_RULE_TAG in m or PIPEFAIL_RULE_MSG in m for m in step_rules)):
                    cls = "文法外"
                    # 平台變體：只在沒有 /proc 的平台成立（`/proc/$$/fd/…` 那一類在 Linux 會外流、判一致）。
                    if not HAS_PROC and res["seen"]["文法外-without-proc"] < declared["文法外-without-proc"]:
                        cls = "文法外-without-proc"
                    classes = [cls]
                    verdict = ("不一致：誤擋（已知類別 %s：這個 step 不在 `--strict` 的正面文法裡、神諭沒有觀察到外流——檔頭簽名的保守擋下；"
                               "神諭觀察的是 stdout／stderr／通道的 PR 標記、pipefail 與注入哨兵，信任邊界類的缺口不在它的觀察範圍，"
                               "所以這個類別不是安全證明）" % cls)
            elif kd["dir"] != kdir:
                verdict += "——KNOWN_DISAGREE 方向不符（登記的是%s，實測是%s）" % (kd["dir"], kdir)
                res["disagree"].append(key)
                res["failures"].append("%s（第 %d 行）：%s" % (name, a + 1, verdict))
                kd = "mismatch"
            elif kd["hash"] != kd_hash(run0):
                verdict += "——KNOWN_DISAGREE 內容雜湊不符（條目擔保的是另一段文字，重新判斷後用 `--print-kd-hash` 更新）"
                res["disagree"].append(key)
                res["failures"].append("%s（第 %d 行）：%s" % (name, a + 1, verdict))
                kd = "mismatch"
            else:
                verdict += "（已知：%s）" % kd["why"]
                kd = "matched"
            if kd is None and not classes:
                res["disagree"].append(key)
                res["failures"].append("%s（第 %d 行）：%s" % (name, a + 1, verdict))
        if classes:
            res["seen"].update(classes)             # 已知**類別**：印出、計入「已知」、由檔頭宣告簽名（見下方的雙向閘門）
        elif verdict.startswith("不一致"):
            pass                                    # 已在上面處理（KD 相符、不符，或列入 disagree）
        elif key[:2] in KNOWN_DISAGREE:
            res["stale"].append(key)
            res["failures"].append("KNOWN_DISAGREE 過期：%s（第 %d 行）" % (name, a + 1))
        assert verdict.startswith(VERDICT_KINDS), verdict   # 判定表的種類是 VERDICT_KINDS（CHANGELOG 讀它）
        rows.append((f.name, name, lint, o, verdict))
    # **類別閘門是雙向的，數量釘死**（R37，#33 verify R36 第 2 列）。前一版只查「宣告了卻沒歸進去」（R34 security LOW-1），
    # 反方向不查、門檻又是「至少一條」——於是一張**沒有宣告**的正向 fixture 被歸進已知類別時 selftest 與神諭都綠
    # （DA 實測：`不一致 5（已知 5）`）。現在每個類別的歸類數必須**等於**檔頭 `# KNOWN-CLASS:` 的行數。
    if HAS_PROC:
        # 有 /proc 的平台上，那幾步會外流、判一致——平台變體的宣告不計（判不一致時由一般的不一致路徑攔下）。
        declared.pop("文法外-without-proc", None)
    for c in sorted(set(declared) | set(res["seen"])):
        d_, s_ = declared[c], res["seen"][c]
        if d_ > s_:
            res["cls_stale"].append((f.name, c, d_, s_))
            res["failures"].append("KNOWN-CLASS 過期：%s（宣告 %d、歸類 %d）" % (c, d_, s_))
        elif s_ > d_:
            res["cls_undeclared"].append((f.name, c, d_, s_))
            res["failures"].append("歸了類卻沒宣告：%s（宣告 %d、歸類 %d）" % (c, d_, s_))
    return res


def print_kd_hash(argv):
    """`--print-kd-hash FILE STEP`：印出那個 step 的 `kd_hash`（新增或更新 KNOWN_DISAGREE 條目時用）。同名的 step 逐一列出行號。"""
    if len(argv) != 2:
        print("用法：oracle.py --print-kd-hash FILE STEP", file=sys.stderr)
        return 2
    f, want = pathlib.Path(argv[0]), argv[1]
    hits = [(a + 1, run) for _j, name, run, (a, _b), _sh, _e in steps_with_lines(f.read_text(encoding="utf-8")) if name == want]
    if not hits:
        print("✗ %s 裡沒有叫 %r 的 step" % (f, want), file=sys.stderr)
        return 1
    for ln, run in hits:
        print("%s\t第 %d 行\t%s" % (want, ln, kd_hash(run)))
    return 0


def bash_supported(bash):
    """版本守衛（R42，#33 verify R41）：神諭用的 bash 必須在被對帳的 lint 檔頭 `# ORACLE-BASH-SUPPORTED:` 宣告的集合裡
    （`主版號.次版號`，空白分隔）。lint 的詞法模型是對特定版本寫的（bash 5.3 的 `${ cmd; }`、`compgen` 的兩份集合）；
    版本對不上時，對帳量的是另一個語言。回傳 None 表示通過，否則是具名的理由。"""
    sup = re.search(r"^# ORACLE-BASH-SUPPORTED:(.*)$", _LINT_SRC, re.M)
    mm = subprocess.run([bash, "-c", 'echo "${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"'],
                        capture_output=True, text=True).stdout.strip()
    if sup is None:
        return "%s 沒有 `# ORACLE-BASH-SUPPORTED:` 檔頭——神諭無法確認自己用的 bash（%s）是 lint 支援的版本" % (LINT, mm)
    if mm not in sup.group(1).split():
        return ("神諭用的 bash %s（%s）不在 %s 檔頭 `# ORACLE-BASH-SUPPORTED:%s` 宣告的集合裡——lint 的詞法模型沒有對這個版本寫"
                % (mm, bash, LINT.name, sup.group(1)))
    return None


def main(argv):
    if argv[:1] == ["--print-kd-hash"]:
        return print_kd_hash(argv[1:])
    if argv == ["--selftest-severity"]:
        return selftest_severity()
    if argv == ["--selftest-aud"]:
        return selftest_aud()
    # `--min-comparable N`（R44，#33 verify R43 第 22 列）：可比的 step（判一致或不一致，不含「不可比」「量不到」）少於 N 個就 rc=1。
    # 用在「這一組檔本來就該量得到東西」的地方——CI 的 macOS 子集：前一版那一步的 11 個 fixture step 全是 `lint=PARSE` 的「不可比」，
    # 只是一條絆線，rc=0 與「什麼都沒量」看不出差別。
    min_comp = None
    if argv[:1] == ["--min-comparable"]:
        if len(argv) < 2 or not argv[1].isdigit():
            print("✗ --min-comparable 後面要接一個整數")
            return 2
        min_comp, argv = int(argv[1]), argv[2:]
    # 給定的檔案一律轉成絕對路徑：lint 會先 cd 到 plugin 目錄，相對路徑會變成「檔案不存在」（rc=2）。
    files = [pathlib.Path(a).resolve() for a in argv] or sorted(FIXTURES.glob("ci-log-filter-*.yml"))
    bash = pick_bash()
    ver = subprocess.run([bash, "-c", 'echo "$BASH_VERSION"'], capture_output=True, text=True).stdout.strip()
    print("bash: %s (%s)  管線判定：DEBUG trap + PIPESTATUS（bash 自己的剖析）" % (bash, ver))
    why = bash_supported(bash)
    if why:
        print("✗ %s" % why)
        return 1
    if LINT != (HERE / "lint-ci-log-filter.sh").resolve():
        print("⚠ ORACLE_LINT：對帳的是 %s（不是 repo 自己的 lint）" % LINT)
    rows, disagree, stale, unmeasured, uncomparable = [], [], [], [], []
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
            uncomparable += res["uncomparable"]
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
    if min_comp is not None:
        comparable = sum(1 for r in rows if r[4] == "一致" or r[4].startswith("不一致"))
        if comparable < min_comp:
            rc = 1
            print("\n✗ 可比的 step 只有 %d 個，要求至少 %d（`--min-comparable`）——這一組檔沒有量到它該量的東西，rc=0 在這裡不是證據"
                  % (comparable, min_comp))
    if disagree:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 之外的不一致（lint 與 runner 對同一個 step 說不同的話）：")
        for fn, name, ln in disagree: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if uncomparable:
        rc = 1
        print("\n✗ 檔頭宣告了 ORACLE-COMPARABLE，這些 step 卻不可比（神諭對 bash 樣板的解析退化了，或樣板不在封閉清單裡）：")
        for k in uncomparable:
            print("  - %s :: %s（第 %d 行）" % k)
    if stale:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 裡的項目現在一致了、或已經量不到（理由不再成立，移除它）：")
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
            want = 0 if (c in FIXTURE_CLASS_PLATFORM_ONLY and HAS_PROC) else FIXTURE_CLASS_TOTALS.get(c, 0)
            if cls_count[c] != want:
                rc = 1
                print("\n✗ 已知類別 %s 在 fixture 集上是 %d 條，預期恰好 %d（改動已知類別的 fixture 請同步改 FIXTURE_CLASS_TOTALS）"
                      % (c, cls_count[c], want))
        if len(mf_report) != FIXTURE_MUSTFAIL_TOTAL:
            rc = 1
            print("\n✗ must-fail 探針是 %d 張，預期恰好 %d（改動探針請同步改 FIXTURE_MUSTFAIL_TOTAL）"
                  % (len(mf_report), FIXTURE_MUSTFAIL_TOTAL))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
