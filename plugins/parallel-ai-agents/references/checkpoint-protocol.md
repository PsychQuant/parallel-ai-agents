# Checkpoint protocol（#103）

pai-ensemble 的每個席次（每個 lens reviewer、codex、devil's-advocate）邊做邊把進度寫進檔案。session 在 run 跑到一半時中斷，接回之後沒跑完的席次會從檔案接著做，不用從頭再來。

為什麼需要它：Workflow 快取的單位是一次 `agent()`，跑到一半的席次在中斷後什麼都留不下來；harness 也只在 run 完成時才存 `args`。workflow script 本身不能讀寫檔案，所以檔案全部由 agent 執行 engine 組好的命令寫入（`workflows/ensemble-workflow.js` 的 `READER_PY`、`RECORD_CMD`、`MARK_CMD`、`INIT_PY`）。

## 目錄

| 情況 | 目錄 |
|---|---|
| 沒給 `checkpointDir` | `$HOME/.cache/pai-ensemble/<argsDigest>/` |
| 給了 `checkpointDir`（絕對路徑） | 那個目錄本身 |
| `checkpoint: false` | 不存檔 |

`argsDigest` 是 args 去掉 `checkpointDir`／`checkpoint` 兩鍵、key 遞迴排序成 canonical JSON 之後的 FNV-1a 64（UTF-8 位元組，16 碼 hex）。它只用來辨認「是不是同一組輸入」，不防偽造。

目錄裡有：

- `args.json`：這個 run 的完整 args（canonical JSON）。由 `checkpoint-init` 席次寫入，寫完用 python 重算雜湊比對；比對不過時不寫，run 的結果多一則 INFO `checkpoint: args.json not saved`，verdict 不受影響。args 以 base64 交給這個席次：`contextBlock` 可能含不受信任的內容，照抄命令的席次不應讀到其中可讀的文字。
- `<席次>-<8 碼雜湊>.partial.jsonl`：每個席次一個檔。席次名稱裡檔名不安全的字元轉成 `_`，8 碼雜湊避免兩個 key 轉換後撞名。
- `<上面的檔名>.prev-N`：被留存的舊檔（見下）。

## 紀錄格式（一行一筆 JSON）

| `kind` | 誰寫 | 內容 |
|---|---|---|
| `header` | 讀檔器，檔案第一行 | `argsDigest`、`artifactSha`（`diffFile` 或 `file` 是一般檔案時的 sha256，否則 `null`）、`label`、`v` |
| `finding` | reviewer／DA | schema 的 finding 欄位 |
| `checked` | reviewer／DA | `item`：查過、沒有問題的項目 |
| `codex-run` | codex 席次 | `id`：`codex-call --detach` 印出的 32 碼 run id |
| `done` | 每個席次，回傳前 | 無 |

## 接回與重跑

每個席次的第一步是讀檔器，它依檔案狀態決定：

| 檔案狀態 | 結果 |
|---|---|
| 不存在 | `FRESH`：寫檔頭，從頭做 |
| 檔頭的 `argsDigest` 與 `artifactSha` 都相同、沒有 `done` | `RESUME`：印出先前的紀錄（最多 200 筆、60 KB，超過印 `TRUNCATED`）；壞掉的行跳過並計數 |
| 沒有檔頭、args 變了、artifact 變了、或有 `done` | 舊檔改名為 `.prev-N`（N 取第一個沒用過的），`FRESH` |
| 讀檔器自己出錯（例如沒有 python3、目錄建不起來） | `DISABLED`：席次照常審閱、不存檔 |

**為什麼看到 `done` 就從頭做**：接回時，已完成的席次直接由 journal 快取回答，根本不會再跑；會看到 `done` 的只有「同一組輸入的新的一輪」。新的一輪不沿用上一輪的結論，舊檔留存為 `.prev-N`。

**codex 席次**：接回時先 `--poll` 檔案裡的 run id，worker 還在跑或已經完成就不再開一個新的；`FAILED`／`TIMEOUT`／`unknown run id`／非零退出才重新 `--detach`。終態已經回報過的 run，poll 不會再報一次，這時會重新 detach（多花一次額度，結果仍然正確）。

## 呼叫端契約

- 部分結果**可以讀、可以在 terminal 顯示**，例如 workflow 中途失敗時讓使用者看到已經做了什麼。
- 部分結果**不是報告**：不得當成 verify 結果貼出去，也不得據此推進任何狀態。
- 要接回中斷的 run：`Workflow({scriptPath, resumeFromRunId, args})`。args 從呼叫端自己的紀錄取，或從 `args.json` 取。用 `ls -t ~/.cache/pai-ensemble/*/args.json` 依時間列出，由 args 裡的 `diffFile` 等欄位辨認是哪一輪。

## 已知限制

- **同一組 args 同時跑兩個 run 會共用目錄**，兩邊的席次可能讀到彼此的部分結果。需要各自獨立的呼叫端（例如 `ensemble-eval` 的 K 次 run）請各給一個 `checkpointDir`。
- `file` 是目錄時 `artifactSha` 是 `null`，目錄內容改變偵測不到。
- 協定是 prompt 層的要求：席次沒照做，接回時能省的就少；最終回傳仍以席次的 schema 輸出為準，正確性不受影響。
- 給同一個 `checkpointDir` 跑不同的 args 時，`args.json` 是最後一次的；各席次的檔案以檔頭的 `argsDigest` 分辨，不會沿用到別組輸入。

## 隱私與清理

- 檔案只在本機。finding 的內容可能引用被審的內容，所以和被審的東西同等看待。
- **永久保留，不自動刪除**（使用者 2026-10-20 裁決）。要清就手動刪：`rm -rf ~/.cache/pai-ensemble/<digest>`，或整個 `~/.cache/pai-ensemble/`。
