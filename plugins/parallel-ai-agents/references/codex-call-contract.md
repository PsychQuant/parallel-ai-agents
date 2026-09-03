# `bin/codex-call` — EXTERNAL-CONSUMER CONTRACT（v1，#35 / #37）

`bin/codex-call` 是實際對 `chatgpt.com/backend-api` 發 HTTPS 的程式，持有 OAuth 憑證與呼叫 payload。
它被 `codex-pro` 以 byte-for-byte 快照 vendored（SHA-256 釘死，見該 repo 的 `codex-call-provenance.json`），
也被本 repo 的 ensemble engine 與 `issue-driven-dev` 的 verify codex leg 直接呼叫。

**在 #35 之前它沒有任何介面穩定性承諾**——codex-pro 的契約明文排除它、pai #20 凍結的是 engine。
本檔補上這一層。比照 pai #20 對 engine 的做法：**breaking change 需 major bump + CHANGELOG migration note。**

## 1. 同步模式（既有，逐 byte 不變）

```
codex-call --output FILE [--model M] [--effort E] [--service-tier T] [--max-time S]
           [--instructions TEXT] [--prompt-file FILE | PROMPT]
```

- 阻塞直到回應完成或 `--max-time` 到期。stdout 無輸出；stderr 有 `[codex-call] …` 診斷。
- exit `0` 且 `FILE` 非空 = 成功。**空輸出視為失敗**（exit 非零，不寫檔）——空檔會被 ensemble 誤讀成「通過」。
- 這條路徑是 codex-pro producer skills 走的；本契約保證它**逐 byte 不變**。

## 2. 背景模式（v2.23.0+，#37）

單一呼叫最長 `--max-time` 秒（預設 600）會超過 Workflow runtime 的 no-progress 門檻（180 s）。
背景模式把「等待」拆成多次短呼叫，每次呼叫本身就是 progress 事件。

### `--detach`

```
codex-call --detach [--output FILE] [同步模式的其餘旗標] [--prompt-file FILE | PROMPT]
```

- 同步驗證參數並讀取 prompt（錯誤**同步**浮現，不進背景才發現），然後啟動 worker，**立即返回**。
- stdout 印**一行** run id；exit `0`。
- `--output` **選填**。省略時輸出寫到 `<base>/<id>.out.md`（見 §3）。給定時 worker 直接寫該路徑，**不經任何中介或搬移**。
- worker 是**單一程序**（本 script 以 `--_worker <id>` 重新執行自己），無 subprocess；其 stdio 全部導向 run 目錄內的檔案，**不繼承** caller 的 pipe（否則 `$(codex-call --detach …)` 會阻塞到 run 結束）。

### `--poll <id>`

印一行狀態，立即返回：

| stdout | exit | 意義 |
|---|---|---|
| `RUNNING` | 0 | worker 仍持鎖 |
| `DONE <path>` | 0 | 成功；`<path>` 是輸出檔。run 目錄已清除 |
| `FAILED <reason>` | 2 | worker 回報失敗，或 status 缺失（fail-closed）。run 目錄已清除 |
| `TIMEOUT` | 3 | worker 自報逾時，或 poll 端兜底：已持鎖超過 `max-time + 60 s` ⇒ `SIGKILL` 持鎖者。run 目錄已清除 |

- id 不合法（格式錯／不存在）→ stderr 訊息，exit `1`，**不對任何程序發訊號**。
- terminal 狀態的清除以 `rename(run, run.done)` 作原子 claim：兩個 poll 併發只有一個會回 terminal，另一個回 exit `1`（run 已不存在）。

### `--abort <id>`

- 持鎖中 → `SIGTERM` 持鎖者，等 2 s，仍持鎖 → `SIGKILL`。清除 run 目錄，印 `ABORTED`，exit `0`。
- 未持鎖（已結束）→ 直接清除，印 `ABORTED`，exit `0`。
- id 不合法 → exit `1`，不發訊號。

## 3. Run id 與狀態目錄

- id：`^[A-Za-z0-9]{32}$`，由 CSPRNG 產生。**`--poll` / `--abort` 只接受 id，不接受路徑。**
- base：`$HOME/.cache/codex-call/runs/`（`0700`）。run 目錄 `<base>/<id>/`（`0700`）含 `meta.json`、`prompt.txt`、`lock`、`status`、`worker.log`。
- 為什麼不收路徑：round 2 verify（PR #47）證明「接受任意目錄 + 檔案存在性檢查」等於任意 PID kill / `rm -rf` 原語。id 只能解析到 HOME 之下的 0700 目錄，跨使用者偽造面消失。

## 4. 生存與身分（為什麼 PID 重用不會誤殺）

- worker 對 `<run>/lock` 持有 **`fcntl(F_SETLK)` POSIX record lock**，直到程序結束（含被 kill）。
- `--poll` / `--abort` 用 **`F_GETLK`** 判斷：`F_UNLCK` = 已結束；否則 `l_pid` **就是此刻持鎖的程序**。
  發訊號的對象永遠是 `F_GETLK` 回報的 pid，**不從任何檔案讀 pid**——回收後的無關程序不可能持有這把鎖。
- 實測（macOS 26）：`flock()` 鎖在 `F_GETLK` 下 `l_pid = -1`（BSD 行為），**不可用**；`fcntl` record lock 回報真實 pid。這是選 `fcntl` 的唯一理由。
- 誠實邊界：`fcntl` 鎖在程序關閉**任何**指向該檔的 fd 時釋放。worker 只開一次且不關閉；不得在 worker 內對 `lock` 另開 fd。

## 5. 期限與清理

- worker **自己**強制 `--max-time`（URLSession timeout + semaphore，既有機制），到期寫 status code `3`。
- poll 端另有兜底：持鎖超過 `max-time + 60 s` ⇒ `SIGKILL`。兩者都不依賴任何可被竄改的 deadline 檔——期限資訊寫在 `meta.json`，但 meta 損毀時 poll **fail-closed**（視為逾時，kill + TIMEOUT），不會退化成無限 RUNNING。
- `status` 由 worker 在**同一程序**寫入；寫失敗 ⇒ 無 status ⇒ poll 回 FAILED。沒有「半截輸出 + 非零退出被當成功」的路徑：DONE 要求 status 為 `0` **且**輸出檔非空。

## 6. 威脅模型

- **同一 uid 的攻擊者在模型之外。** base 是 `0700`，同 uid 本來就能 kill 你的任何程序。
- 跨 uid：`/tmp` 不再涉入（base 在 HOME）；id 不可猜（CSPRNG 32 字元）；poll 不收路徑。
- prompt injection：Codex 的輸出檔內容來自不受信任的 artifact，caller（ensemble engine）**必須**把它當 DATA 讀，並且 poll 用的 id 必須來自 `--detach` 的 stdout，不得來自任何檔案內容。這是 caller 的責任，本契約在 engine 的 prompt 中明寫。

## 7. 隱藏旗標（internal，不在穩定性承諾內）

- `--_worker <id>`：由 `--detach` 呼叫。id 不合法或 run 不存在 → exit 1。
- `--_selftest-sleep N` / `--_selftest-fail` / `--_selftest-grace N`：與 `--detach` 並用，worker 以 sleep + 寫檔取代 HTTP（測試 detach / lock / poll / abort 路徑，不發網路）。
- `--selftest-error-extract`（#25，既有）。

## 8. 穩定性承諾

- §1、§2 的旗標名、stdout 格式、exit code、§3 的 id 格式與 base 路徑：**STABLE**。變更需 major bump + migration note。
- §7 隱藏旗標：可在 minor 內變更。
- 消費者釘 SHA（codex-pro）時，本檔的版本欄與 `CHANGELOG.md` 是判斷「要不要 re-vendor」的依據。
