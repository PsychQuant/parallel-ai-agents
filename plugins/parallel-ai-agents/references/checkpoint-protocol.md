# Checkpoint protocol（#103）

pai-ensemble 的每個席次（每個 lens reviewer、codex、devil's-advocate）邊做邊把進度寫進檔案。session 在 run 跑到一半時中斷，接回之後沒跑完的席次會從檔案接著做，不用從頭再來。

為什麼需要它：Workflow 快取的單位是一次 `agent()`，跑到一半的席次在中斷後什麼都留不下來；harness 也只在 run 完成時才存 `args`。workflow script 本身不能讀寫檔案，所以檔案全部由 agent 執行 engine 組好的命令寫入（`workflows/ensemble-workflow.js` 的 `READER_PY`、`RECORD_CMD`、`MARK_CMD`、`INIT_PY`）。每個命令都以 `python3 -I` 執行：席次的工作目錄是被審的 repo，那裡的 `json.py` 之類的檔不會被當成模組載入。

## 目錄

| 情況 | 目錄 |
|---|---|
| 沒給 `checkpointDir` | `$HOME/.cache/pai-ensemble/<dirKey>/` |
| 給了 `checkpointDir`（絕對路徑） | 那個目錄本身 |
| 再給 `checkpointRun` | 上面的目錄底下多一層 `run-<標籤>-<8 碼雜湊>/` |
| `checkpoint: false` | 不存檔 |

`dirKey` 是 `profile`、`file`、`diffFile`、`srtFile`、`contextBlock` 這五個所有席次共用的輸入，以 canonical JSON 計算的 FNV-1a 64（16 碼 hex）。只影響部分席次的參數（`daFocus`、`codexModel`、某個 lens 的 `priors`、`agentModel`）不換目錄。它只用來辨認「是不是同一份東西」，不防偽造。

`checkpointRun` 給「同一組輸入、刻意獨立的多輪」用：`ensemble-academic-review` 的 mix 第 1 輪與第 3 輪 args 完全相同。不分開的話，第 1 輪中斷在一半的席次會把部分結果交給第 3 輪。`ensemble-eval` 的 K 次 run 則各給一個 `checkpointDir`，效果相同。

目錄與檔案都是私有的：目錄 0700（呼叫端先建好、但權限較寬的目錄會收緊），檔案 0600。目錄必須是本人擁有的絕對路徑真目錄，symlink、別人擁有的目錄，或 `HOME` 沒設、設成相對路徑，都會讓讀檔器回 `DISABLED`。

目錄裡有：

- `args.json` 與 `args-<argsDigest>.json`：這個 run 的完整 args（canonical JSON），內容相同。`args.json` 是這個目錄最近一次寫的那一份，`args-<argsDigest>.json` 讓同一個目錄跑過的不同 args 各自留著。`argsDigest` 是 args 去掉 `checkpointDir`、`checkpoint`、`checkpointRun` 之後的雜湊，也記在 `stats.checkpoint.argsDigest`。這個檔由 `checkpoint-init` 席次寫入：args 以 base64 交給它，它解碼後對解碼出的位元組重算雜湊，與 engine 算的比對，不符就不寫，run 的結果多一則 INFO `checkpoint: args.json not saved`，verdict 不受影響。以 base64 交付是因為 `contextBlock` 可能含不受信任的內容，照抄命令的席次不應讀到其中可讀的文字。
- `<席次>-<8 碼雜湊>.partial.jsonl`：每個席次一個檔。席次名稱裡檔名不安全的字元轉成 `_`，8 碼雜湊避免兩個 key 轉換後撞名。
- `<上面的檔名>.prev-N`：被留存的舊檔（見下）。

## 紀錄格式（一行一筆 JSON）

| `kind` | 誰寫 | 內容 |
|---|---|---|
| `header` | 讀檔器，檔案第一行 | `v`（2）、`seatDigest`、`artifactSha`、`label` |
| `finding` | reviewer／DA | schema 的 finding 欄位 |
| `checked` | reviewer／DA | `item`：查過、沒有問題的項目 |
| `codex-run` | codex 席次 | `id`：`codex-call --detach` 印出的 32 碼 run id |
| `done` | 每個席次，回傳前 | 無 |

`seatDigest` 是這個席次自己的輸入：它在 checkpoint 關閉時會收到的 prompt，加上 dispatch model，算出的雜湊。所以：

- 改了某個參數，只有它實際影響到的席次換 key，其他席次的 prompt 與部分結果不受影響。journal 快取則只保留到派發順序中第一個改變的呼叫之前（見下方「journal 快取怎麼對應」）。
- devil's-advocate 的 prompt 含各 reviewer 的結果摘要，所以 reviewer 結論不同的新一輪，不會沿用上一輪 DA 針對舊結論做的反駁。
- engine 升級改了內建 lens 或 DA 的指示文字，key 也跟著變。

`artifactSha` 涵蓋席次讀的檔與席次所在的工作目錄：`diffFile`、`file`（兩個都給時兩個都算），需要逐字稿的 lens 再加 `srtFile`。路徑先解析成絕對路徑，工作目錄也算進去，所以同一份 diff 在另一個 repo 裡審時不會沿用紀錄。artifact 是目錄的話只記「是目錄」，目錄內容改變偵測不到。

紀錄以 `\n` 切行。`json.dumps` 會原樣寫出 U+2028／U+2029／U+0085，以這些字元切行會把一筆紀錄拆成兩半。

## 接回與重跑

每個席次的第一步是讀檔器，它依檔案狀態決定：

| 檔案狀態 | 結果 |
|---|---|
| 不存在 | `FRESH`：寫檔頭，從頭做 |
| 檔頭的 `seatDigest` 與 `artifactSha` 都相同、沒有 `done` | `RESUME`：印出先前的紀錄；壞掉的行跳過並計數 |
| 沒有檔頭、輸入變了、artifact 變了、或有 `done` | 舊檔改名為 `.prev-N`（N 取第一個沒用過的），`FRESH` |
| 讀檔器自己出錯（目錄建不起來、沒有 `HOME`、檔案位置不是一般檔案） | `DISABLED`：席次照常審閱、不存檔 |
| 命令沒有印出任何 `PAI_CHECKPOINT` 行（例如沒有 python3） | prompt 交代視同 `DISABLED` |

紀錄命令的 heredoc 分隔符取自席次的鍵（`PAI_EOF_<12 碼>`）：紀錄內容常引用被審的 artifact，固定的分隔符可能被內容裡的同一行提早結束，後面的文字就會被當成 shell 執行。這個鍵是可以算出來的雜湊，不是秘密：要事先算出它，得知道席次完整的 prompt（含呼叫端的 `contextBlock`），artifact 的作者通常不知道。紀錄命令寫入前，如果檔尾沒有換行（上一筆寫到一半被打斷），會先補一個換行，所以被截斷的那一行不會吃掉下一筆。

`RESUME` 的輸出先印最新的 `codex-run`，再印 finding，最後印其餘紀錄。總量以 20,000 字元為上限（Bash 工具的輸出在 30,000 字元附近會被截斷），單筆超過 8,000 字元的不印，但不擋住後面的紀錄。有沒印出來的就印 `PAI_CHECKPOINT TRUNCATED`，prompt 要席次自己從 `PAI_CHECKPOINT FILE` 那一行指出的檔案讀其餘紀錄。

**為什麼看到 `done` 就從頭做**：args 不變的接回，已完成的席次直接由 journal 快取回答，不會再跑。會看到 `done` 的主要是「同一組輸入的新的一輪」，新的一輪不沿用上一輪的結論，舊檔留存為 `.prev-N`。另有兩種情形也會看到，代價是那一輪的工作重做：改過 args 再接回時，排在第一個改變的呼叫之後、已經做完的席次；以及寫完 `done`、結果還沒進 journal 就中斷的席次（見已知限制）。

**journal 快取怎麼對應**（2026-10-20 以兩個探針 workflow 實測）：快取鍵依派發順序串接。args 不變的接回時，所有已完成的呼叫都由快取回答，排在被打斷的呼叫之後的也一樣，只有被打斷的那些重跑。改過 args 再接回時，派發順序中第一個 prompt 改變的呼叫之後，所有呼叫都重跑，prompt 沒變的也一樣。這些重跑的席次看到自己的 `done`，就從頭做。派發順序是各 lens、codex、`checkpoint-init`、devil's-advocate。init 的 prompt 帶著整份 args，所以排在 barrier 的最後；也因此任何 args 的改動都會讓 devil's-advocate 在接回時重跑。codex 排在 lens 之後，只改 codex 的參數時，lens 的快取照樣有效。`checkpoint: false` 時沒有 init，派發順序維持 #103 之前的 codex 在前。

**codex 席次**：讀檔器只印最新的一筆合法 `codex-run`。接回時先 `--poll` 那個 run id，worker 還在跑或已經完成就不再開一個新的；`FAILED`／`TIMEOUT`／`unknown run id`／非零退出才重新 `--detach`。終態已經回報過的 run，poll 不會再報一次，這時會重新 detach（多花一次額度，結果仍然正確）。

## 呼叫端契約

- 部分結果**可以讀、可以在 terminal 顯示**，例如 workflow 中途失敗時讓使用者看到已經做了什麼。
- 部分結果**不是報告**：不得當成 verify 結果貼出去，也不得據此推進任何狀態。
- 要接回中斷的 run：`Workflow({scriptPath, resumeFromRunId, args})`。args 從呼叫端自己的紀錄取，或從 checkpoint 目錄的 `args.json` 取。預設位置用 `find ~/.cache/pai-ensemble -name args.json -exec ls -t {} +` 依時間列出（涵蓋 `run-*/` 子目錄），由 args 裡的 `diffFile` 等欄位辨認是哪一輪；給了 `checkpointDir` 的就看那個目錄（與它底下的 `run-*/`）。
- 同一組輸入要跑成彼此獨立的多輪時，各輪給不同的 `checkpointRun`（或不同的 `checkpointDir`）。
- 開啟 checkpoint 時，run 會多派一個 `checkpoint-init` 席次，不算在 `maxAgents` 與 `stats.agents` 裡，以 `stats.checkpoint.initDispatched` 表示。

## 已知限制

- **接回只看席次的 prompt 與 artifact 的位元組**。被審的程式若在兩者都不變的情況下改了（例如審的是工作樹，而 diff 檔沒有重產），接回的席次會沿用舊的紀錄。被審內容可能這樣變的呼叫端，要把 commit id 或 tree id 寫進 `contextBlock`，這樣它一變，所有席次的 key 就跟著變。
- **args 很大時 init 的成本也大**：init 席次要逐字抄出 base64 的 args，它的 prompt 約是 args 位元組數的 1.37 倍再加 2.5 KB。contextBlock 為 4 KB 時約 8 千字元，30 KB 約 4.4 萬，100 KB 約 14.1 萬（2026-10-20 實測）。中文的 contextBlock 每個字 3 位元組，同樣位元組數下，init 的 prompt 是 reviewer prompt 的 3.3 倍。抄錯只會出 INFO，但輸出 token 已經付了。
- **寫下 `done` 到結果進 journal 之間有一段空窗**：席次寫完 `done` 之後才回傳結果。session 若剛好在這中間中斷，接回時這個席次沒有快取可用，會重新派發；它看到自己的 `done`，就從頭做。結果仍然正確，但那一輪的工作白做。這段空窗是席次寫下 `done` 之後產生最終回傳（全部 finding）的時間，沒有量過，在高 effort 下可能是數十秒。
- **改過 args 再接回時，快取只保留到第一個改變的呼叫之前**（見上方「journal 快取怎麼對應」）。之後的席次即使自己的 prompt 沒變也會重跑，而且因為看到 `done` 而從頭做。
- **同一組輸入同時跑兩個 run 會共用目錄**，兩邊的席次可能讀到彼此的部分結果，或互相把對方的檔改名為 `.prev-N`。需要各自獨立的呼叫端請給不同的 `checkpointRun` 或 `checkpointDir`。
- **協定是 prompt 層的要求，engine 核對不到兩件事**：(1) 接回的席次有沒有把紀錄裡的 finding 帶回最終回傳——沒照做時，中斷前記下的 finding 會從結果消失（不會多出錯的 finding，但會漏）；(2) 席次有沒有寫 `done`——沒寫就結束時，呼叫端以同一組輸入開的新 run（不是接回）會沿用那份部分結果。要獨立的新一輪，就給不同的 `checkpointRun`。
- **init 排在 barrier 最後的代價**：席次數超過並行上限（`min(16, CPU 數 − 2)`）時，init 要等前面某個席次做完才開始，`args.json` 會晚寫；在那之前中斷，接回要靠呼叫端自己的 args。
- **預設目錄的鍵不含工作目錄**：兩個 repo 用同樣的共用輸入（例如同一個 `contextBlock`、同一個 artifact 路徑）會落在同一個目錄。artifact 雜湊含工作目錄，所以不會沿用彼此的紀錄，但會互相把對方的檔改名為 `.prev-N`。
- 目錄擁有者的檢查（別人擁有的目錄回 `DISABLED`）沒有自動化測試，因為要另一個使用者才建得出那種目錄。
- **接回的鍵與目錄名，與使用者裁決的字面不同**：2026-10-19 的裁決寫「args 雜湊與 artifact 雜湊都相同才沿用」，2026-10-20 寫預設目錄以 args 雜湊命名。實作改成每個席次自己的輸入（verify R1 的 HIGH），目錄以共用輸入的 `dirKey` 命名。差別：只改到某些席次的參數時，派發順序中排在第一個改變的呼叫之前、或還沒做完的席次會沿用紀錄（比裁決窄）；排在它之後、已經做完的席次照樣從頭做，與裁決相同；同一份 diff 換了工作目錄時會失效（比裁決寬）。仍待使用者確認。

## 隱私與清理

- 檔案只在本機，權限是本人可讀寫。finding 的內容可能引用被審的內容，所以和被審的東西同等看待。`args.json` 與 `args-<digest>.json` 永久保存逐字的 `contextBlock`（issue 本文、PR 說明之類）。
- `ensemble-code-review` 每次把 diff 寫到新的暫存路徑，所以每個 run 都落在新的目錄、不會被之後的 run 重用，目錄會一直累積。那個 skill 在 run 結束後刪掉 diff（可能含秘密），但 finding 引用的片段仍留在 checkpoint 檔裡。審含秘密的內容時，可以傳 `"checkpoint": false`。
- **永久保留，不自動刪除**（使用者 2026-10-20 裁決）。要清就手動刪：`rm -rf ~/.cache/pai-ensemble/<key>`，或整個 `~/.cache/pai-ensemble/`。
