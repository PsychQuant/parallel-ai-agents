# test/

ensemble-* skill 的自動化測試。把過去人工 re-audit（多輪 self-dogfood）抓到的 bug 全部固化成 regression，取代「每次改邏輯都要重新人工審」。

## 哲學：把「LLM 編排」拆成「確定性核心 + 模型 seam」

ensemble-* 的程式表面看似都是「LLM 驅動的編排」，不可測。但把每條流程拆開，**80% 是確定性膠水**（可窮舉測），只有真正呼叫模型那幾步是非確定的。本目錄的策略（Functional Core, Imperative Shell）：

1. **抽出 decider / parser 純函式** → 窮舉單元測。例：`pai-iterate-decide`（迴圈狀態機）、`pai-parse-verdict`（收斂判定）、`pai-build-diff`（diff 建構）。
2. **Mock 模型 seam** → 注入確定性 oracle，測「接線」而非模型。例：`ensemble-workflow.test.mjs` 把 `agent()` 換成 mock。
3. **Fixture 測 side-effect** → 拋棄式 git repo 斷言 commit graph。例：`pai-iter-commit`（空輪不留空 commit）。
4. **真正不可單元測的（模型判斷品質）** → 屬 eval 範疇，**不進 CI**：`/parallel-ai-agents:ensemble-eval` 對 `eval/fixtures/` 埋好缺陷的論文跑 K 次真 ensemble，`bin/pai-eval-grade` 容差斷言（每缺陷 ≥ minHits 次被抓到）+ `--apply-fix` 驗證修稿。eval 的**評分器本身是確定性的** → 它有單元測試（`pai-eval-grade.test.mjs`）；非確定的只有「跑 ensemble」那步。

`--auto-iterate` 主迴圈即範例：halt 判定、mode 奇偶交替、focus-rotation、max-rounds clamp、per-round commit 全部抽出測（`pai-iterate-decide` + `pai-iter-commit`），未測表面縮到只剩 `apply_fixes` 一步。

## 測什麼

| 檔案 | 對象 |
|------|------|
| `pai-build-diff.bats` | `../bin/pai-build-diff`（ensemble-code-review 的 diff 模式建構器）|
| `ensemble-workflow.test.mjs` | `../workflows/ensemble-workflow.js`（共用 harness，4 個 skill 的底層）|
| `pai-parse-lens-csv.bats` | `../bin/pai-parse-lens-csv`（ensemble-compose 的 `--lens-file` CSV 解析器）|
| `pai-list-profiles.bats` | `../bin/pai-list-profiles`（validate.py 的 profile 名稱真源：求值 harness PROFILES 印 key；`PAI_HARNESS` 只在測試裡指向 fixture，validate.py 呼叫時顯式傳入被 containment 過的路徑——#33 verify R14 E-2）|
| `pai-parse-verdict.bats` | `../bin/pai-parse-verdict`（ensemble-academic-review `--auto-iterate` 的 verdict tag 解析器）|
| `pai-iterate-decide.test.mjs` | `../bin/pai-iterate-decide`（`--auto-iterate` 主迴圈的純狀態機：halt / 套 fix / mode 交替 / focus-rotation）|
| `pai-iter-commit.bats` | `../bin/pai-iter-commit`（`--auto-iterate` 的 per-round checkpoint commit + 空輪防護）|
| `pai-eval-grade.test.mjs` | `../bin/pai-eval-grade`（eval 評分器：detect 容差聚合 / fix 修稿驗證 —— eval 裡唯一確定性、可單元測的部分）|
| `codex-call-error-extract.bats` | `../bin/codex-call` 的 SSE error 訊息提取（`--selftest-error-extract`）—— **macOS-only**（codex-call 是 `#!/usr/bin/swift` script），在非 macOS 環境自我 skip |
| `codex-profile.bats` | repo root `.codex-pro/profile.yaml`（#48 專案層 codex-pro profile pin）—— 用 `references/codex-governance.md` 同組正規式鎖住解析後字面、重複 key、git 追蹤；fixture 三層優先序（不依賴 codex-pro cache）；形狀驗證拒絕注入。與 governance 文件是連動點（codex-pro#18 / #19）|
| `codex-call-detach.bats` | `../bin/codex-call` 的背景模式（`--detach`／`--poll`／`--abort`／`--force-reap`；#37）—— **macOS-only**、95 case；絕大多數案例走同一條 detach／lock／claim／poll 路徑（另有 5 個不走：1 個同步路徑、2 個對原始碼／契約文件的靜態斷言、2 個 lint 呼叫），用 `--_selftest-sleep`（加上 -fail／-grace／-ignore-term／-prelock-sleep／-gc-age 這幾個修飾旗標）把 streamCodex 換成 sleep＋寫檔，另有 `--_selftest-classify` 與 `--selftest-error-extract` 兩個不經 worker 的鉤子（任何通過參數驗證、沒帶 `--_selftest-sleep` 的 detach，worker 都會真的發 HTTPS）。**不可與另一組 bats 在同一 checkout 並行**（`own_workers` 斷言是 checkout 級） |
| `lint-bats.sh` | 護欄：bats 檔內不得有裸 `!` 斷言（errexit 不觸發，斷言變 no-op；round 6 RC11）。`--selftest` 對 `fixtures/lint-bats-bad.bats` 必須拒絕 |
| `lint-changelog-counts.sh` | 護欄：CHANGELOG 每個「N 個 case（`grep -c "^@test" <file>`）」／「N 條（`grep -c …`）」／「N 個（`grep -c …`）」宣稱，加上第四種「N 量詞（`python3 -c "<expr>"`）」的資料結構長度宣稱（#33 verify R30/R31 加入，LEN_CLAIM）——共四種形式，封閉列舉，不得類推第五種，N 必須等於那條命令此刻的輸出（RC13 第五度復發後機械化，#37 round 10；#33 verify R13/R14 加後兩種）。指向 sibling plugin 的 `../` 路徑在非 monorepo 佈局缺席時跳過並註明。`--selftest` 對 `fixtures/changelog-count-bad.md` 拒絕、對再次餵入的 `fixtures/changelog-count-sibling-file-missing.md`（在 `../pai-lenses` 不存在的分支下）接受——沒有獨立的 `changelog-count-sibling-absent.md` 這個檔案、對 `changelog-count-sibling-file-missing.md`（sibling 目錄在、檔不在）拒絕（該斷言只在 monorepo 佈局跑）|
| `lint-ci-log-filter.sh` | 護欄：`.github/workflows/*.yml`／`*.yaml`（全部 workflow）每一個 `run:` step 都必須經 `../pai-lenses/scripts/neutralise.py`（**`run:` 區塊之內的 pipeline 位置**）或帶 `# LOG-FILTER:` 註解明示不過濾與理由。**R18 起是白名單解析器**：只認明確列出的結構（plain key、block 清單、block scalar），其餘一律 fail-loud——三輪的黑名單特例都被新的合法 YAML 寫法穿過（去重後 7 個根因）。`--selftest` 對 `fixtures/ci-log-filter-*.yml`（正向與負向全部）**逐一 glob**，數量寫死在門檻裡（正向、rule-red、parse-red、帶 `EXPECT-MSG`、帶 `EXPECT-EACH-STEP` 的張數都要恰好相等；改 fixture 要同步改門檻，R24 regression F9；R42 起另比對 PATH 上那支 bash 的 `compgen -b`／`-k` 是否都在正面文法的 builtin／保留字集合裡），每張 fixture 的檢查彼此獨立，所以平行跑（預設 min(核心數, 8) 個，`LINT_SELFTEST_JOBS=1` 就是原來的串行；輸出依序號彙整、訊息順序不變）；突變測試用的 `LINT_SELFTEST_FAILFAST=1`（第一張失敗就停）與 `LINT_SELFTEST_FIRST=<檔>`（一行一個 fixture 路徑，先跑；只改順序）不改任何判定，見 `opsweep.py` 的 `_selftest_env`，並依每個 fixture 的 `# EXPECT:` 斷言它是規則擋（rule-red）還是解析擋（parse-red）；帶 `# EXPECT-MSG:`（可多行）的 fixture 另斷言訊息內容——每行都要以子字串出現在輸出裡，帶它的張數同樣寫死（R37：類別對了不代表訊息對）——兩種都不是 `seen == 0` 的 vacuity 守衛擋的。**兩種模式**（#33 verify R36 第 25 列）：檢查真的 workflow 一律用 **`--strict`**（CI 與 `run.sh` 都是）——它另外要求 shell 是 bash 樣板、有管線的 step 跑在 pipefail 之下（關鍵字 `bash`、樣板自帶 `-o pipefail`，或 run 開頭的 `set` 前綴——R42 起只有這三個來源；自訂樣板如 `bash -e {0}` 沒有）、靠管線過濾的 step 只收一套**正面文法**（R42，#33 verify R41）：`set` 前綴＋一個群組 `{ …; } 2>&1 | python3 <路徑>/neutralise.py`，群組裡只收九類原語（lint 檔頭的 P1 在 R44 起逐個列舉隱藏效果與條件，不再說「惰性 builtin」：`[`／`test` 的 `-v` 與 `RANDOM`／`SRANDOM`／`OPTIND`／`HISTCMD` 的指派會對值做算術求值、`printf -v` 會指派變數、`trap` 動作是離開時才執行的程式碼——所以命令參數裡的參數展開要在雙引號裡、`test`／`[` 只收三種形狀且運算元不得有未加引號的 glob 字元、特殊變數與信任變數不收指派、`printf` 判 quote removal 之後的值），見 lint「`--strict` 宣稱的性質」一節的 P1——其餘一律擋（保守誤擋，fixture 檔頭以 `KNOWN-CLASS: 文法外` 簽名）；宣告了 `# LOG-FILTER:` 的 step 寫出管線或提到 `$GITHUB_ENV` 時也要落在同一套文法裡。要印 `::error::` 的檢查另開 `# LOG-FILTER: none` 的 step。五個 runner 通道（`$GITHUB_ENV`／`PATH`／`OUTPUT`／`STATE`／`STEP_SUMMARY`）的寫入只在 `--strict` 查；不帶旗標的預設模式是給 fixture 與產生語料的詞法量測，**假設 shell 是 bash**，非 bash 的 shell／container／Windows runner 只在 `--strict` fail-closed（R34 放行條件第 5 條的偏離，理由見 lint 檔頭）。檔名給絕對路徑：lint 先 `cd` 到 plugin 目錄，找不到檔案回 rc=2，那不是 pass。 |
| `oracle.py` | 神諭：對每個 fixture 的每個 `run:` step 用 bash 真的跑一次，**管線的判定由 bash 自己的剖析器給**（DEBUG trap ＋ `${#PIPESTATUS[@]}`；`[ -p /dev/stdin ]` 分不出 heredoc 與管線），宣告的判定用**差分**（把候選文字切掉再跑一次，可觀察結果相同才是註解），與 lint 的逐 step 判定對帳——lint pass 而 runner 沒 pipe（且無 `# LOG-FILTER:` 宣告）＝繞過；lint RULE-red 而 runner 有 pipe 且無外流＝誤擋（有外流時視為一致，擋下是對的，R35）。selftest 只證「lint 判定 = 作者宣告」，這支把第三方（runner）拉進來（#33 verify R28 DA）。R42 起另外量 `--strict` 宣稱的兩件事：pipefail 探針（每條多段管線開始時 pipefail 開著沒有、腳本換掉探針時判量不到）與跨 step 通道（`GITHUB_ENV` 等五個檔帶不帶 PR 文字）；已知類別多了「文法外」（正面文法保守擋下、**神諭沒有觀察到外流也沒有違規 argv——不是安全證明**）；R46 起有 primitive 稽核（PRELUDE 把 `[`／`test`／`printf` 換成記錄實際 argv 的函式、逐命令比對信任變數）——builtin 收到文法形狀之外的東西時判一致、不再只能說「沒有觀察到外流」；`KNOWN_DISAGREE` 的條目記方向與內容雜湊；lint 檔頭宣告支援的 bash 版本對不上就具名退出。**R44 起另外量**：注入探針（PR 標記是文字、不是程式碼——把 PR 相關的環境變數換成會留下哨兵的 payload 再跑一次：放行而哨兵有東西＝繞過、擋下而哨兵有東西＝一致）、EXIT trap 在 errexit 下仍執行使用者的動作（失敗路徑）、逾時之前已寫進通道的 PR 文字不撤銷；`--min-comparable N` 讓一組檔的可比 step 少於 N 個就 rc=1；「文法外」類別的措辭是「神諭沒有觀察到外流」，**不是安全證明**。需 PyYAML；YAML 層是它的盲區（PyYAML ≠ GitHub 的解析器，見 docstring） |
| `opsweep.py` | 作者無關的運算子突變掃描：對 lint 內嵌的 Python 以固定五種運算子（strip→id、±1、刪布林運算元、startswith→False、==↔!=）逐一突變，每個突變體跑一次 `--selftest`；`--since REF` 只掃自 REF 起被改動的區域（R44：頂層函式**與類別方法**各算一個單位——前一版 `_Sh` 的方法改了不進區域；`--since` 仍看不到「程式沒改、但路徑變了」的網失效，R43 第 9 列，所以發版前要跑一次不帶 `--since` 的全輪）。存活的要嘛補會翻色的 fixture，要嘛證明等價後列入 `EXPECTED_SURVIVE`（≤ 突變體數 10%）。第二道判準是 `corpus/shellgen.py` 的產生語料（形狀完整樣本）——selftest 沒抓到而產生語料抓到的會單獨列出，那就是 fixture 集缺的形狀。`--verify-expected` 把每一條 `EXPECTED_SURVIVE` 的等價論證在產生語料（R42：預設組 624＋`--strict` 組 88＝712 檔；R39 寫這句時是 709，R31 時是 468）上真的跑一次。手動跑（R44 提速後：每個突變體的 selftest 提早結束、殺過突變體的 fixture 按次數排最前面並存在 `~/.cache/idd-verify/opsweep-killers.txt` 跨輪沿用；39 個樣本與完整 selftest 的殺／存活逐個相同，冷啟動 `--jobs 9` 約 8 s／個，提速前完整 selftest 約 72–96 s、`--jobs 6` 牆鐘約 18 s／個；`OPSWEEP_FULL_SELFTEST=1` 退回完整 selftest）；不進 CI |
| `corpus/shellgen.py` | **詞法對帳產生器**：按封閉的構造維度（分隔字引號擺法 16（R33 由 12 加到 16）／引號種類 4／`#` 位置 6／block scalar 形式 8／管線位置 3／內文縮排 2）分組取笛卡兒積：預設模式 A–E 五組 624 個（R31 時三組 468 個），另有 `--strict` 組 88 個（`--strict` 旗標；十個封閉維度，R39 加了群組外的行、群組內容、群組尾巴三個，R40 加了「只靠某一條規則擋下的群組形式」），共 712 個 workflow 餵給 `oracle.py`；R42 加 `--grammar` 組 100 個（`--strict` 正面文法的產生式取樣，每個變數位置放 PR 文字：lint 必須全收、神諭必須判一致；R44 補失敗路徑——獨立的 `false`、`exit`、會失敗的 `test`／`[`——並把變數位置限定為加了引號的形式，文法外的形狀不在這一組）。**不列舉已知形狀，列舉維度**——R30 的第 14 類「網的投餵」要防的就是「判準與作者無關了，輸入集合還是作者挑的」。CI 會跑 |
| `oracle_selfcheck.py` | 神諭的反向探針：只有神諭**失敗**時才成立的檢查，封閉列舉 31 項（批次與編號寫在檔頭，docstring 的總數由 `main()` 與 `CHECKS` 機械比對：must-fail 理由比對、oracle↔lint 耦合、R39 的歸類探針、R40 的兩項、R42 的 KD 方向與雜湊、版本守衛、`GH_SAFE_EXPRS` 同步、文法外閘門、pipefail 探針、通道、payload 脈絡、payload 不依賴前一個命令成功、取最嚴重、S-2 機制差分，R44 的 EXIT 失敗路徑、逾時保留通道、注入探針、trap 動作裡的管線、`--min-comparable`——多數用 `oracle-probes/lint-*.sh` 假 lint 或暫存目錄裡的突變版讓神諭走到那個分支）。rc=0 表示每一項都照預期（多數是照預期失敗）。`mutation_check.py` 的 `oracle-inverted` 守備單位跑它。CI 會跑 |
| `corpus/foldcheck.py` | lint 的 `dedent_block`／`fold_block` 對 PyYAML 的窮舉對帳（R37）：短字母表上的所有組合逐一比對兩邊的結果，印出不符的組數與例子 |
| `corpus/regexcheck.py` | `FL_REDIR_BAD_RE` 與 `FL_REDIR_DUP_OK_RE` 互斥的窮舉檢查（R42）：兩遍窮舉（基本字母表長度 0 到 7、擴充字母表——加 `(`、tab、數字 3–9 的代表——長度 0 到 6），印出同時命中的個數，檔頭另寫結構性論證（R44 更正：前一版把字母表說成「這十個字元」不對）；opsweep 的一條 EXPECTED_SURVIVE 靠它 |
| `corpus/` | 語料工具：`r25-workflow-corpus.txt`（真實 workflow 清單，hash＋repo 相對路徑）、`threeaxis.py`（base vs head 逐檔 RULE／PARSE／rc 三軸 diff，報 base-綠檔數當靈敏度分母）、`synth.py`（合成 base-綠語料，A/B/C 三變體）、`shapes.py`（每個新機制一個可計數的觸發形狀，報它在各清單的檔數——分母裡沒有那個形狀，GREEN→RED=0 就不是證據） |
| `lint-contract-enumerations.sh` | 護欄：`references/codex-call-contract.md` 自稱封閉的列舉（各命令的 stdout token、exit-1 答案、abort 表列數、§6 項數、`R10-B5s` pattern 唯一性）必須與 `bin/codex-call` 一致（#37 round 11——同型手打枚舉缺陷在一輪契約裡復發四次）。`--selftest` 對 `fixtures/contract-enum-bad/` 五個 fixture 各自拒絕 |

`pai-parse-lens-csv.bats` 涵蓋：含逗號/引號/換行的 focus（csv 模組、不被切爛）、needsSrt 變體、空欄跳過、**BOM 不丟列（utf-8-sig regression）**、CRLF、缺檔/缺欄。
`codex-call-error-extract.bats` 的 SUT 是 macOS-only 的 Swift script，故在 ubuntu job 上會**自我 skip**；CI 另有 `macos-swift-bats` job 確保它真的被執行（只加 skip guard 而不加 job，錨點會變成永遠 skip 的 vacuous green —— #25 verify）。

`pai-parse-verdict.bats` 涵蓋：**last-match（防 echoed instruction 範例造成假收斂的 regression）**、`{N}` placeholder 不匹配、嚴格大寫、查無 tag → 非零、stdin/file。

`pai-build-diff.bats` 涵蓋：5 種模式（`--diff`/`--base`/`--since`/`--commits`/`--pr`）、退出碼契約（0 有 diff／3 無變更／1 錯誤）、ref/N 驗證（injection、dashed-ref、0/leading-zero、位數溢位）、untracked 安全（symlink no-follow、FIFO no-hang、換行檔名 C-quote）、empty-tree base、未知 mode 的多位元組 regression。

`ensemble-workflow.test.mjs` 涵蓋 harness 的 **fail-closed 不變式**：unknown profile、空 lens 組合、core lens 被 skip（null）/ error（throw）/ devil's-advocate 缺席 → 一律 HIGH integrity（不可假 PASS）、codex 缺席 → INFO 非阻塞、mergeDedup 對 malformed severity 穩健。把「null-skip fail-open」的修正鎖死成 regression。（純 node，無框架；把 workflow script body 包成可 import 的 async 函式、注入 mock globals 實跑。）

## 跑法

```bash
# 前置（一次性）
brew install bats-core shellcheck

# 一鍵：shellcheck + py_compile + 四支 lint（各含 selftest）+ oracle + bats + node
./test/run.sh

# 或分開
shellcheck bin/pai-build-diff
bats test/
```

CI（`.github/workflows/test.yml`）在每次 push / PR 自動跑：`shellcheck-bats` 與 `macos-swift-bats` 兩個 job 涵蓋上面這一組；另有 `manifests-and-lens-pack` job 跑 `plugins/pai-lenses/scripts/` 的 python 測試、靶清單檢查與 validator 本體 —— `run.sh` 末段也跑同一組，所以本機一鍵與 CI 對得上（完整 mutation 量測仍是手動：`python3 scripts/mutation_check.py`）。

## 加測試的原則

改 `bin/pai-build-diff` 的行為 → **先在 `pai-build-diff.bats` 加一個會 fail 的 case（RED），再改 script 讓它 pass（GREEN）**。不要在 `SKILL.md` inline 重寫 diff 邏輯 —— script 是單一真相源，SKILL.md 只呼叫它。
