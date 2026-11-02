# Checkpoint protocol（#103）

pai-ensemble 的每個席次（每個 lens reviewer、codex、devil's-advocate）邊做邊把進度寫進檔案。session 在 run 跑到一半時中斷，接回之後沒跑完的席次會從檔案接著做，不用從頭再來。

為什麼需要它：Workflow 快取的單位是一次 `agent()`，跑到一半的席次在中斷後什麼都留不下來；harness 也只在 run 完成時才存 `args`。workflow script 本身不能讀寫檔案，所以檔案全部由 agent 執行 engine 組好的命令寫入（`workflows/ensemble-workflow.js` 的 `READER_PY`、`RECORD_CMD`、`MARK_CMD`、`INIT_PY`）。每個命令都以 `python3 -I` 執行：席次的工作目錄是被審的 repo，那裡的 `json.py` 之類的檔不會被當成模組載入。

## 目錄

| 情況 | 目錄 |
|---|---|
| 沒給 `checkpointDir` | `$HOME/.cache/pai-ensemble/<dirKey>/` |
| 給了 `checkpointDir`（絕對路徑） | 那個目錄本身 |
| 再給 `checkpointRun` | 上面的目錄底下多一層 `run-<標籤>-<8 碼雜湊>/` |
| `checkpoint: false` | 不存檔（只收布林值） |

`dirKey` 是 `profile`、`file`、`diffFile`、`srtFile`、`contextBlock` 這五個所有席次共用的輸入，以 canonical JSON 計算的 FNV-1a 64（16 碼 hex）。其他參數不換目錄：只影響部分席次的（`daFocus`、`codexModel`、某個 lens 的 `priors`），以及影響所有席次但只改它們的鍵、不改它們讀的東西的 `agentModel`。它只用來辨認「是不是同一份東西」，不防偽造。

`checkpointRun` 給「同一組輸入、刻意獨立的多輪」用：`ensemble-academic-review` 的 mix 第 1 輪與第 3 輪 args 完全相同。不分開的話，第 1 輪中斷在一半的席次會把部分結果交給第 3 輪。標籤也要分開「不同次的審閱」：對同一份論文重新開一次獨立審閱時，若沿用 `round-1`，上一次中斷在一半的席次會被接續。所以 academic-review 的標籤帶一個審閱開始時決定、接回時沿用的識別碼。`ensemble-eval` 的 K 次 run 則各給一個 `checkpointDir`，效果相同。

目錄與檔案都是私有的：目錄 0700，檔案 0600。呼叫端先建好、但權限較寬的目錄會被收緊；給了 `checkpointRun` 時，呼叫端的 `checkpointDir` 本身也會被收緊。目錄本身必須是本人擁有的絕對路徑真目錄，不能是 symlink。通往它的路徑照 kernel 的方式逐層解析：遇到 symlink 就從它的目標路徑重新走起（從 `/` 開始，`..` 照解析後的位置算）。每一個做查找的目錄都必須由 root 或本人擁有，且不能讓他人寫入，除非它有 sticky 位元（例如 `/tmp`），或只是本人專屬群組可寫；每一個查到的項目（目錄或 symlink）都必須由 root 或本人擁有。所以 symlink 目標的上層目錄也會被檢查，不是只看最後一層。這些條件任一不符，或 `HOME` 沒設、設成相對路徑，讀檔器都回 `DISABLED`，init 回 `PAI_ARGS ERROR`。路徑檢查的理由：他人能寫入的目錄裡，路徑的某一層可以在檢查之後被換掉，之後的紀錄就寫到別的地方。root 擁有的 symlink（macOS 的 `/tmp`、`/var`）可以通過。目錄建好之後再走一次整條路徑：第一次檢查時還不存在的元件，以及接在它後面的 `..`，建好之後同樣受檢。被拒時，剛建的空目錄留在原地，不刪，因為無法確定那是不是自己建的。

checkpoint 目錄最好放在被審的 repo 之外。放在裡面時要把它加進 `.gitignore`：檔案裡有引用被審程式碼的 finding，`args.json` 裡有整份 `contextBlock`，`git add -A` 會把它們一起提交。

目錄裡有：

- `args.json` 與 `args-<argsDigest>.json`：這個 run 的完整 args（canonical JSON），內容相同。`args.json` 是這個目錄最近一次寫的那一份，`args-<argsDigest>.json` 讓同一個目錄跑過的不同 args 各自留著。`argsDigest` 是 args 去掉 `checkpointDir`、`checkpoint`、`checkpointRun` 之後的雜湊，也記在 `stats.checkpoint.argsDigest`。這個檔由 `checkpoint-init` 席次寫入：args 以 base64 交給它，它解碼後對解碼出的位元組重算雜湊，與 engine 算的比對，不符就不寫，run 的結果多一則 INFO `checkpoint: args.json not saved`，verdict 不受影響。以 base64 交付是因為 `contextBlock` 可能含不受信任的內容，照抄命令的席次不應讀到其中可讀的文字。
- `<席次>-<8 碼雜湊>.partial.jsonl`：每個席次一個檔。席次名稱裡檔名不安全的字元轉成 `_`，可讀的部分最多取 64 字元，8 碼雜湊（對整個名稱計算）避免兩個 key 轉換或截短後撞名。`checkpointRun` 的子目錄名同樣處理，所以名稱再長也不會超過檔名長度上限。
- `<上面的檔名>.prev-N`：被留存的舊檔（見下）。

## 紀錄格式（一行一筆 JSON）

| `kind` | 誰寫 | 內容 |
|---|---|---|
| `header` | 讀檔器，檔案第一行 | `v`（2）、`seatDigest`、`artifactSha`、`label` |
| `finding` | reviewer／DA | schema 的 finding 欄位；`title` 與 `body` 必須是非空字串 |
| `checked` | reviewer／DA | `item`：查過、沒有問題的項目，必須是非空字串 |
| `codex-run` | codex 席次 | `id`：`codex-call --detach` 印出的 32 碼 run id |
| `done` | 每個席次，回傳前 | 無 |

`seatDigest` 是這個席次自己的輸入：它在 checkpoint 關閉時會收到的 prompt，加上 dispatch model，算出的雜湊。所以：

- 改了某個參數，只有它實際影響到的席次換 key，其他席次的 prompt 與部分結果不受影響。journal 快取則只保留到派發順序中第一個沒有快取的呼叫（改過的，或上一次被打斷或出錯的）之前（見下方「journal 快取怎麼對應」）。
- devil's-advocate 的 prompt 含各 reviewer 的結果摘要，所以 reviewer 結論不同的新一輪，不會沿用上一輪 DA 針對舊結論做的反駁。
- engine 升級改了內建 lens 或 DA 的指示文字，key 也跟著變。

`artifactSha` 涵蓋席次讀的檔：`diffFile`、`file`（lens 與 DA 兩個都給時兩個都算；codex 席次只算它交給 codex-call 的那一個，有 `diffFile` 就是 `diffFile`），需要逐字稿的 lens 再加 `srtFile`。路徑先解析成實際的絕對路徑，連同內容一起雜湊：席次的工作目錄不算（先 `cd` 再跑讀檔器也接得回），相對路徑在另一個目錄解析成別的檔就不接回，symlink 改指也不接回。沒有 artifact 檔、只給 `contextBlock` 時，鍵只有 prompt（見已知限制）。artifact 是目錄時，雜湊每個項目的相對路徑與型態權限；檔案與 symlink 另加大小、修改時間與 symlink 目標。一般目錄（含根目錄）只算路徑與權限，不算修改時間：略過的目錄裡有變動時，上層目錄的修改時間會跟著變，算進去就讓略過失效。這是 metadata，不是內容：大小、修改時間或權限沒變的內容改動偵測不到。不算進去的有：checkpoint 目錄本身（放在被審目錄裡也不會讓自己的紀錄失效），以及固定一組依賴與快取目錄（`.git`、`node_modules`、`.build`、`.venv`、`venv`、`__pycache__`、`.tox`、`.mypy_cache`、`.pytest_cache`、`.gradle`、`DerivedData`）。略過是依目錄名稱，任何深度都算，同名的 symlink 也略過；呼叫端沒有辦法關掉或縮小這份清單。其餘項目（目錄、檔案、symlink）超過 20,000 個或讀不了時，讀檔器回 `DISABLED`：這個席次這一輪不存檔，先前的檔不動，席次自報的 `DISABLED` 讓它列在 `stats.checkpoint.disabledSeats`。

這個雜湊只有跑讀檔器的席次用得到。由 journal 回答的席次不跑讀檔器，它們靠的是呼叫端寫在 `contextBlock` 第一行的 artifact 指紋（見「artifact 指紋」）。

紀錄以 ASCII 寫入，非 ASCII 字元以 `\uXXXX` 跳脫：孤立的代理字元不會讓寫入失敗，從 artifact 引來的 C1 控制字元、DEL 與雙向覆寫字元也不會原樣留在檔案裡。接回時一般文字（含中文）原樣印出，依 Unicode 類別跳脫的只有控制、格式（含雙向）、代理、私用、未指派的字元與行、段落分隔符，這些不會原樣印到 terminal。讀檔器只以 `\n` 切行，手改或外部工具寫入的行若原樣含 U+2028／U+2029／U+0085，不會被拆成兩半。

## 接回與重跑

每個席次的第一步是讀檔器，它依檔案狀態決定：

| 檔案狀態 | 結果 |
|---|---|
| 不存在 | `FRESH`：寫檔頭，從頭做 |
| 檔頭的 `seatDigest` 與 `artifactSha` 都相同、沒有 `done`、至少一筆紀錄 | `RESUME`：印出先前的紀錄；壞掉的行跳過並計數 |
| 同上，但一筆紀錄都沒有（上一輪的席次在第一筆紀錄之前就中斷） | `FRESH`：沿用這個檔，不改名 |
| 沒有檔頭、輸入變了、artifact 變了、或有 `done` | 舊檔改名為 `.prev-N`（N 取第一個沒用過的），`FRESH` |
| 讀檔器自己出錯（目錄建不起來、路徑不安全、沒有 `HOME`、檔案位置不是一般檔案、檔案建不起來），或 artifact 無法雜湊（目錄超過 20,000 個項目或讀不了） | `DISABLED`：席次照常審閱、不存檔，已有的檔不動。`FRESH` 只在檔案建好之後才印，所以不會同時看到兩者 |
| 命令沒有印出任何 `PAI_CHECKPOINT` 行（例如沒有 python3） | prompt 交代視同 `DISABLED` |

紀錄命令的 heredoc 分隔符取自席次的鍵（`PAI_EOF_<12 碼>`）：紀錄內容常引用被審的 artifact，固定的分隔符可能被內容裡的同一行提早結束，後面的文字就會被當成 shell 執行。這個鍵是可以算出來的雜湊，不是秘密：要事先算出它，得知道席次完整的 prompt（含呼叫端的 `contextBlock`），artifact 的作者通常不知道。紀錄命令回 `REJECTED` 表示這一行不對，修好再寫：不是 JSON、不是 UTF-8、空的、巢狀深到無法解析、形狀不對、有多餘的鍵，都印 `REJECTED`、exit 0，不寫入。finding 的形狀與 schema 的 finding 相同：`severity` 是 CRITICAL、HIGH、MEDIUM、LOW、INFO 之一，`title` 與 `body` 是非空字串，`file` 是字串或 null，`line` 是整數或 null，可另給 `lens`（字串或 null），此外只有 `kind`；checked 只有 `kind` 與非空字串的 `item`。多餘的鍵拒收，不丟掉：接回時 finding 的欄位（`kind` 以外）經 schema 帶回，schema 不收多餘的鍵；丟掉則席次寫下的東西無聲消失。json 模組接受、嚴格 JSON 不接受的 NaN 與 Infinity 寫不進檔案，因為允許的值只有字串、整數與 null。其他失敗（沒有 python3、權限錯誤）表示存檔壞了，prompt 交代席次停止之後所有的存檔步驟、照常審閱。codex 席次 step 0 回 `DISABLED` 時，step 1 的 run id 紀錄與 step 3 的 done 也一併略過；run id 紀錄或 done 命令失敗時，detach 的結果不受影響，略過其餘存檔步驟、照常 poll。紀錄命令寫入前，如果檔尾沒有換行（上一筆寫到一半被打斷），會先補一個換行，所以被截斷的那一行不會吃掉下一筆。

席次被交代不要把秘密的值（token、密碼、金鑰）寫進紀錄，只寫出它在哪裡，因為檔案會一直留在磁碟上。這一條也是 prompt 層的要求。

`RESUME` 的輸出先印最新的 `codex-run`，再印 finding，最後印其餘紀錄。總量以 20,000 字元為上限（Bash 工具的輸出在 30,000 字元附近會被截斷），單筆超過 8,000 字元的不印，但不擋住後面的紀錄；字元數量的是印出來的樣子，中文一個字算一個。有沒印出來的就印 `PAI_CHECKPOINT TRUNCATED`，prompt 要席次自己從 `PAI_CHECKPOINT FILE` 那一行指出的檔案讀其餘紀錄，並把檔案裡的 `\uXXXX` 解碼之後再回傳。

**為什麼看到 `done` 就從頭做**：會看到 `done` 的情形有三種。(1) 同一組輸入的新的一輪：新的一輪不沿用上一輪的結論，舊檔留存為 `.prev-N`。(2) 接回時排在第一個沒有快取的呼叫之後、已經做完的席次（見下一段）：它被重新派發，看到自己的 `done`，就從頭做。(3) 寫完 `done`、結果還沒進 journal 就中斷的席次（見已知限制）。讀檔器分不出這三種，只能一律當成新的一輪，否則 (1) 會沿用上一輪的結論；(2) 與 (3) 是代價，那一輪的工作白做。

**journal 快取怎麼對應**：journal 是前綴快取。Workflow primitive 的文件寫明，派發順序中最長一段沒有改變的 `agent()` 呼叫直接回傳快取的結果；第一個改變的或新的呼叫，以及它之後的所有呼叫，都實際再跑。上一次被打斷或出錯、沒有結果的呼叫，在接回時就是那個「第一個」：排在它之後的呼叫全部再跑，args 沒變、prompt 沒變、上一次已經有結果的也一樣。再跑的席次若上一次已經做完，看到自己的 `done` 就從頭做；沒做完的席次從檔案接回。

實測三次。2026-10-20 以兩個探針 workflow 改過 args 再接回：第一個 prompt 改變的呼叫之後，所有呼叫都再跑。2026-10-21 一次驗證 run 的四個 lens 席次出錯後接回：排在它們之後、已經做完的 codex 重新派發，第二次的結果少了第一次報的一則 HIGH。2026-11-02 讀另一次驗證 run 的 journal：第一次執行時四個 lens 席次都以失敗結束（排在最前面的那一個已經寫了 `done`），codex 與 `checkpoint-init` 有結果；接回時 codex 與 init 以相同的快取鍵重新派發，codex 開了一個新的 codex-call（另一個 run id），三個沒做完的 lens 從檔案接回（列在 `stats.checkpoint.resumedSeats`），排在最前面的那個 lens 看到 `done` 從頭做。

派發順序是各 lens、codex、`checkpoint-init`、devil's-advocate。init 的 prompt 帶著整份 args，所以排在 barrier 的最後；也因此任何 args 的改動都會讓 devil's-advocate 在接回時重跑。codex 排在 lens 之後，只改 codex 的參數時，lens 的快取照樣有效。這兩個安排只在「其餘呼叫上一次都有結果」時有用：任何一個 lens 上一次沒有結果，排在它之後的 codex 與 init 都會再跑。`checkpoint: false` 時沒有 init，派發順序維持 #103 之前的 codex 在前。派發順序只影響誰先開始：回傳結果一律排回 codex 在前，`stats.reviewers` 的順序與並列重複的 finding 的歸屬，與存檔開關無關。

**由 journal 回答的席次不會重新檢查 artifact**：有快取的呼叫不跑讀檔器。中斷之後改了 artifact、再以存下的 args 接回時，這些席次保留舊版本的結論，再跑的席次看到 `artifact-changed` 改審新版本，合併的報告混了兩個版本，沒有任何訊號。engine 讀不到檔案，自己發現不了，所以由呼叫端處理：接回之前從目前的 artifact 重算指紋，和存下的 args 比對，不同就不接回（見呼叫端契約與「artifact 指紋」）。

**codex 席次**：讀檔器只印最新的一筆合法 `codex-run`。codex 席次沒做完（檔案裡沒有 `done`）時，接回先 `--poll` 那個 run id，worker 還在跑或已經完成就不再開一個新的；`FAILED`／`TIMEOUT`／`unknown run id`／非零退出才重新 `--detach`。終態已經回報過的 run，poll 不會再報一次，這時會重新 detach（多花一次額度，結果仍然正確）。已經做完的 codex 席次若排在第一個沒有快取的呼叫之後而再跑，看到 `done` 就從頭做：開一個新的 codex-call，額度再付一次，結果也可能不同（見已知限制）。

## 呼叫端契約

- 部分結果**可以讀、可以在 terminal 顯示**，例如 workflow 中途失敗時讓使用者看到已經做了什麼。
- 部分結果**不是報告**：不得當成 verify 結果貼出去，也不得據此推進任何狀態。
- 要接回中斷的 run：`Workflow({scriptPath, resumeFromRunId, args})`。只給 `resumeFromRunId` 不夠，Workflow 仍要 args；`args.json` 是讓呼叫端有一份可以讀回的副本，沒有讓接回省掉 args（issue #103 的 Expected 3 只做到這一步）。args 從呼叫端自己的紀錄取，或從 checkpoint 目錄的 `args.json` 取。目錄最可靠的出處是 run 開頭的 log 行 `pai-ensemble: checkpoint → <目錄>`：`args.json` 由 init 寫，init 排在最後，run 在它之前中斷時還沒有這個檔。`args.json` 與席次寫的檔在同一個目錄，被 artifact 誘導的席次可以改寫它；重用前核對 `codexCallPath`、`diffFile`、`file`，或用呼叫端自己的副本。檔名裡的雜湊不防竄改。預設位置用 `find ~/.cache/pai-ensemble -name args.json -exec ls -t {} +` 依時間列出（涵蓋 `run-*/` 子目錄），由 args 裡的 `diffFile` 等欄位辨認是哪一輪；給了 `checkpointDir` 的就看那個目錄（與它底下的 `run-*/`）。
- 同一組輸入要跑成彼此獨立的多輪時，各輪給不同的 `checkpointRun`（或不同的 `checkpointDir`）。
- **接回之前重算 artifact 指紋**（理由見上方「由 journal 回答的席次不會重新檢查 artifact」，做法見「artifact 指紋」）。本 plugin 的五個審閱 skill（academic、code、compose、lecture、minutes）都寫這一行並照做。`ensemble-eval` 不寫：被審的 fixture 是 plugin 裡固定的檔，每次 run 又給自己的 `checkpointDir`，中斷到接回之間 artifact 不會變。
- 出現過 `RESUME` 的 run，結論有一部分建立在前一次中斷的紀錄上，不等於全新一輪的結論。哪些席次接回了，列在 `stats.checkpoint.resumedSeats`：接回時讀到至少一筆紀錄的席次（只有檔頭的檔印 `FRESH`，不算）。回 `DISABLED` 的席次列在 `stats.checkpoint.disabledSeats`，它們這一輪沒有存檔，中斷了也接不回。兩份清單都來自席次在回傳裡自報的 `checkpointState`，沒報的不計；`stats` 只有 run 跑完才有，中斷的 run 沒有這個訊號。本 plugin 的五個審閱 skill 在報告裡寫出這兩份清單非空的情形，以及 `argsSaved` 為 false 的情形。要全新一輪，就換 `checkpointRun` 或 `checkpointDir`。
- `checkpoint` 只收 `true`／`false`；`"false"`、`0`、`null` 這類值在派發前 throw，不會被當成開啟。
- 開啟 checkpoint 時，run 會多派一個 `checkpoint-init` 席次，不算在 `maxAgents` 與 `stats.agents` 裡，以 `stats.checkpoint.initDispatched` 表示。

## artifact 指紋（呼叫端寫在 `contextBlock` 第一行）

```
artifact sha256: <hash> inputs: <給工具的參數>
```

`<hash>` 是 `bin/pai-artifact-fingerprint` 的輸出（雜湊什麼寫在它的檔頭），`inputs:` 照 shell 的引號寫下給它的參數，含 `--exclude`（checkpoint 目錄放在被審目錄裡時要排除它）。code-review 的 diff 模式寫建出 diff 的 `pai-build-diff` 參數。工具失敗時 stdout 是空的、exit 非零：停下來告訴使用者，不要用別的方法寫這一行。被 git 忽略的檔與 submodule、巢狀 repo 的內容不在目錄的範圍內，審的內容住在那裡時，把它們另外列成輸入。

接回之前，照 `inputs:` 重算，和存下的 args（自己的紀錄或 `args.json`）裡這一行比對：相同才接回；不同就不接回，用重算的那一行組 args，開新的 run（另給新的 `checkpointRun` 或 `checkpointDir`）。hash 不得從 `args.json` 抄：抄來的永遠相同。`args.json` 席次寫得到，比對不會認證它的 `inputs:` 與其他欄位，從它讀回時先核對（見呼叫端契約）。

engine 核對不到呼叫端有沒有寫這一行、有沒有重算；直接拿存下的 args 接回的呼叫端，會沿用舊版本的結論。

## 已知限制

- **接回只看席次的 prompt 與 artifact 的內容**。席次另外讀的東西不在雜湊裡：diff 模式下自己去讀的周邊程式碼、`contextBlock` 點名的參考檔（ensemble-eval 的 results.csv、academic 的分析檔）。這些東西在 prompt 與 artifact 都不變時改了，接回的席次會沿用舊的紀錄。被審內容可能這樣變的呼叫端，要把參考檔也給指紋工具，或把 commit id、tree id 寫進 `contextBlock`，這樣它一變，所有席次的 key 就跟著變。
- **args 很大時 init 的成本也大**：init 席次要逐字抄出 base64 的 args，它的 prompt 約是 args 位元組數的 1.35 倍再加 4.1 KB。contextBlock 為 4 KB 時約 9.7 千字元，30 KB 約 4.5 萬，100 KB 約 13.9 萬（2026-10-20 實測）。
- **每個席次的 prompt 變長**，大多是內嵌的讀檔器與紀錄命令（2026-11-02 實測，沒有 contextBlock：reviewer 879 → 13,621 字元，devil's-advocate 943 → 13,669，codex 3,643 → 13,988）。席次每記一筆就要輸出一次紀錄命令（1,680 字元，另加紀錄本身）。init 抄錯只會出 INFO，但輸出 token 已經付了。
- **寫下 `done` 到結果進 journal 之間有一段空窗**：席次寫完 `done` 之後才回傳結果。session 若剛好在這中間中斷，接回時這個席次沒有快取可用，會重新派發；它看到自己的 `done`，就從頭做。結果仍然正確，但那一輪的工作白做。這段空窗是席次寫下 `done` 之後產生最終回傳（全部 finding）的時間，長度沒有量過，在高 effort 下可能是數十秒。2026-10-22 實際發生過一次：一個 lens 席次寫完 `done` 之後，最後一次模型請求失敗，這個呼叫在 journal 裡記為失敗。
- **接回時，快取只保留到派發順序中第一個沒有快取的呼叫之前**（見上方「journal 快取怎麼對應」）。第一個沒有快取的呼叫可以是改過 args 的那一個，也可以是上一次被打斷或出錯的那一個。排在它之後、上一次已經做完的席次全部從頭做：看到自己的 `done`，把檔改名為 `.prev-N`，重新審閱。只有沒做完的席次從檔案接回。這是最常見的中斷形狀：派發順序中排第三的 lens 沒做完，排在它之後的 lens 與 codex 即使已經做完，也整份重做。
- **做完的 codex 席次在這種位置會再付一次額度**：它從頭做時開一個新的 codex-call，額度再付一次，結論也可能與第一次不同（2026-10-21 的實例少了一則 HIGH）。開啟存檔時 codex 排在所有 lens 之後，所以任何一個 lens 上一次沒有結果，就會發生這件事；`checkpoint: false` 時 codex 排在最前面，沒有這個代價，也沒有存檔。
- **同一組輸入同時跑兩個 run 會共用目錄**，兩邊的席次可能讀到彼此的部分結果，或互相把對方的檔改名為 `.prev-N`。需要各自獨立的呼叫端請給不同的 `checkpointRun` 或 `checkpointDir`。
- **目錄雜湊的略過清單會藏住同名的被審內容**：略過依名稱、任何深度、含同名 symlink。被審的東西若剛好叫 `venv`（例如 CPython 的 `Lib/venv`）、`.build`、`DerivedData`，或審的是 vendored 的 `node_modules/<套件>`，它改了之後接回的席次偵測不到，沿用舊的 `checked`。反過來，清單外的建置輸出目錄（`target`、`dist`、`build`、`vendor`、`.next`、`coverage`）照樣算，裡面很大時讀檔器回 `DISABLED`，這一輪不存檔。沒有逐次呼叫的覆寫；需要時用 `checkpoint: false`，或改審 `diffFile`。
- **開啟存檔時 codex 排在所有 lens 之後**：席次數超過並行上限時，codex（通常是最慢的一席）要等 lens 釋放名額才開始，總時間約是 lens 加 codex，而不是兩者取大。額度的代價見上方「做完的 codex 席次在這種位置會再付一次額度」。
- **席次自己在被審目錄裡寫的東西會讓接回失效**：跑測試產生的檔、coverage、改權限之類，只要不在上面那組略過的目錄裡，都會改變目錄雜湊，接回時從頭做；沒被 git 忽略的也會改變呼叫端的指紋，比對不同就要開新的 run。
- **接回的席次把紀錄當成已確立**：紀錄裡的 finding 原樣帶回，checked 的項目不再重查。紀錄若記錯，或記錄時被 artifact 的內容誤導，接回之後不會被重驗；記下的 finding 也沒有撤回的方法。
- **協定是 prompt 層的要求，engine 核對不到兩件事**：(1) 接回的席次有沒有把紀錄裡的 finding 帶回最終回傳——沒照做時，中斷前記下的 finding 會從結果消失；(2) 席次有沒有寫 `done`——沒寫就結束時，呼叫端以同一組輸入開的新 run（不是接回）會沿用那份部分結果。要獨立的新一輪，就給不同的 `checkpointRun`。
- **init 排在 barrier 最後的代價**：席次數超過並行上限（`min(16, CPU 數 − 2)`）時，init 要等前面某個席次做完才開始，`args.json` 會晚寫；在那之前中斷，接回要靠呼叫端自己的 args。
- **鍵不含工作目錄**：兩個 repo 用同樣的共用輸入（例如同一個 `contextBlock`、同一個 artifact 路徑）會落在同一個目錄。相對路徑解析成不同的檔時不沿用彼此的紀錄，但會互相把對方的檔改名為 `.prev-N`。同一個絕對路徑的 artifact，以及只有 `contextBlock`、沒有 artifact 檔的席次，會沿用：審閱範圍取決於席次所在目錄的呼叫端（`contextBlock` 寫「審目前的 repo」），要把路徑寫進 `contextBlock` 或給不同的 `checkpointRun`。
- 目錄擁有者的檢查（別人擁有的目錄或路徑項目回 `DISABLED`）沒有自動化測試，因為要另一個使用者才建得出那種目錄；他人可寫入的路徑那一條有測試。
- **init 沒有成功時的 INFO**：init 的命令先檢查目錄、再比對 base64，所以目錄不能用時回 `PAI_ARGS ERROR`，不會被抄錯蓋掉。只有引擎認得的情形（init 席次被略過、出錯、沒回傳，或命令回 `PAI_ARGS MISMATCH`，含 base64 抄錯）說「各席次的部分結果仍存著」；這是「init 的失敗與席次無關」的意思，席次自己的存檔是否正常，看它們的 `PAI_CHECKPOINT` 行。其餘情形（`PAI_ARGS ERROR`、沒有 python3、traceback、席次轉述的文字）說「可能是同一個原因讓每個席次都沒存檔，先看席次的 `PAI_CHECKPOINT` 行」。
- **接回的鍵與目錄名，與使用者裁決的字面不同（待使用者確認）**：2026-10-19 的裁決寫「args 雜湊與 artifact 雜湊都相同才沿用」，也就是 args 有任何不同就什麼都不沿用、全部重跑；2026-10-20 寫預設目錄以 args 雜湊命名。實作改成每個席次以自己的輸入為鍵，目錄以共用輸入的 `dirKey` 命名。以「沿用了多少」來比：只改到某些席次的參數時，派發順序中排在第一個改變的呼叫之前的席次由 journal 沿用，還沒做完、自己的輸入沒變的席次沿用檔案裡的紀錄，所以**實作沿用得比裁決多**（裁決是一律不沿用）；排在它之後、已經做完的席次從頭做，與裁決相同；目錄型 artifact 超過項目上限時不接回、只改修改時間也從頭做，**實作沿用得比裁決少**。同樣待確認的還有兩點：接回不看 prompt 與 artifact 位元組以外、席次自己讀的程式碼（第一條已知限制）；args 很大時 init 的成本（第二條已知限制）。

## 隱私與清理

- 檔案只在本機，權限是本人可讀寫。finding 的內容可能引用被審的內容，所以和被審的東西同等看待。`args.json` 與 `args-<digest>.json` 永久保存逐字的 `contextBlock`（issue 本文、PR 說明之類）。
- `ensemble-code-review` 每次把 diff 寫到新的暫存路徑，所以每個 run 都落在新的目錄、不會被之後的 run 重用，目錄會一直累積。那個 skill 在 run 結束後刪掉 diff（可能含秘密），但 finding 引用的片段仍留在 checkpoint 檔裡。審含秘密的內容時，可以傳 `"checkpoint": false`。
- **永久保留，不自動刪除**（使用者 2026-10-20 裁決）。要清就手動刪：`rm -rf ~/.cache/pai-ensemble/<key>`，或整個 `~/.cache/pai-ensemble/`。
