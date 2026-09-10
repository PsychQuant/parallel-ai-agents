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

- 同步驗證參數並讀取 prompt（錯誤**同步**浮現，不進背景才發現），啟動 worker，**等到 worker 已持鎖、或已寫出 `status`** 才返回（readiness handshake，細節見下一條；worker 啟動失敗＝detach 同步失敗，stderr 附 `worker.log` 尾段）。實測 worker 從啟動到持鎖需 0.6–1.0 s；沒有這個 handshake，這段視窗內的 poll 會把合法 run 判成 terminal 並清除。
- stdout 印**一行** run id；exit `0`。
- `--detach` / `--poll` / `--abort` / `--force-reap` **恰好一個**；同時給 → 同步錯誤 exit 1。
- **readiness handshake**：`--detach` 只在 worker **已持鎖、或已寫出 `status`** 之後才印出 id（上限 20 s；逾時 → **先 SIGTERM／SIGKILL worker 並等它退出、確認無人持鎖**，再清 run（清除失敗印 warning）；worker 殺不死 → run 原地保留、exit 1 並說明；worker 先退出且無 status → 同步 exit 1、不印 id、run 已清。stderr 一律附 `worker.log` 尾段——**真的是尾段**：從檔尾有界讀取最後 12 行（`O_NOFOLLOW`＋一般檔案檢查＋`O_NONBLOCK`，FIFO／symlink 到裝置不會讓 poll 阻塞或無界成長，round 5 S5），經 sanitizer 並剝除 bidi／Tags／BOM（S10）；worker 的每一條提早退出都會先寫一行原因，所以尾段不會是空的（round 4 R4-3b、Codex #3／#14）。「還沒開始」與「已經跑完」是**兩個不同的答案**（round 3 的第一版 handshake 把它們壓成同一個，DA 實測 11/12 把瞬間完成的 run 判成沒啟動並刪掉結果）。
- 因此 caller 拿到 id 之後看得到的 run 狀態是**封閉列舉的兩種：持鎖中／已結束**。「正在啟動」對 caller 不可見。**不得依性質相似類推第三種**——round 3 的 L1（abort 在啟動視窗漏殺）正是從沒列出的那一種掉出去的。
- `--output` **選填**。省略時輸出寫到 `<base>/<id>.out.md`（見 §3），**該檔由本工具擁有**：任何非 `DONE` 的 terminal 狀態（FAILED / TIMEOUT / ABORTED）都會把它清掉。給定時 worker 直接寫該路徑，**不經任何中介或搬移**，且本工具**永不**刪除 caller 給的檔案（半截輸出留給 caller 處置）。**`DONE <path>` 印出之後，該檔（不論預設或 caller 給定）轉為 caller 所有**：本工具不再碰它，也沒有任何回收機制——caller 讀完必須自己刪（engine 的 prompt 明寫）。唯一例外是 §4 的 24 h GC：落在 base 且命名為 `<id>.out.md` 形狀的檔案（含 caller 刻意把 `--output` 指到那裡的情況）會被當最後防線回收——那不是 caller 可以依賴的回收（round 4 S8）。
- `--max-time` 在 `--detach` 下必須是**正整數**（垃圾值 / `0` / 負數 → exit 1、不建 run）。同步路徑維持歷史行為（§1 逐 byte 不變），不加驗證。
- worker 是**單一程序**（本 script 以 `--_worker <id>` 重新執行自己，路徑為 `argv[0]` 的 realpath，不依賴 cwd / PATH），Foundation 的 `Process` 讓 worker 成為**自己的 process-group leader**，終端 SIGHUP 只送前景 process group，所以 launcher 的終端斷線不會殺到 worker；**不做 `setsid()`**——對 group leader 呼叫 `setsid(2)` 依定義必失敗 EPERM（round 5 L8 實測 100%），「自成 session」從未成立也不承諾；stdio 全部導向 run 目錄內的檔案，**不繼承** caller 的 pipe（否則 `$(codex-call --detach …)` 會阻塞到 run 結束）。

### `--poll <id>`

印一行狀態，立即返回：

| stdout | exit | 意義 |
|---|---|---|
| `RUNNING` | 0 | worker 仍持鎖 |
| `DONE <path>` | 0 | 成功；`<path>` 是輸出檔。run 目錄已清除 |
| `FAILED <reason>` | 2 | worker 回報失敗，或 status 缺失（fail-closed），或 **worker 拒絕終止**（見下）。run 目錄已清除（後者除外） |
| `TIMEOUT` | 3 | worker 自報逾時，或 poll 端兜底：已持鎖超過 `max-time + 60 s` ⇒ **先 claim**（與 `--abort` 對稱，round 6 RC1a）⇒ SIGTERM → 2 s → SIGKILL，**確認鎖已釋放**後——若 worker 在這一瞬間已寫好 `status`，以 status 為準（DONE／FAILED），只有**沒有 status** 的 run 才是 TIMEOUT（round 6 RC1c）——`reported` 落地後才清除 |

- `--wait N`（1–120，**只配 `--poll`**，與 `--detach` 併用或 `N` 不在範圍內（含 `0`）→ exit 1；round 5 L1：`--wait 0` 曾因「用值當旗標存在性」溜過所有檢查，讓同步路徑真的發 HTTPS）：在 codex-call **內部**阻塞**最多** N 秒（不超過，round 5 L9）等待狀態改變（每秒重查持鎖者與期限）——「不超過 N」指的是**這個等待迴圈**；迴圈結束後的收尾另計：逾時兜底的 SIGTERM→SIGKILL 最多再數秒，claim 檔不在時的 2 s 有界重查（§9 R9-REG-A）再 2 s（round 10 實測 `--wait 1` 總長 +2.15 s；round 11 把這句寫清楚，不改行為）；仍 RUNNING 則印 `RUNNING`，終態提早返回，**lock 檔不可信／無法檢查時與無 `--wait` 的路徑同一個答案**（exit 1、run 保留，round 5 L3）。這是輪詢節奏的唯一正確形狀——**不要用 shell `sleep`**：Claude Code 的 Bash tool 擋前景 sleep，round 4 R4-1 實測 `sleep 30; …` 被工具層拒絕。
- 清除失敗（`removeItem` 錯誤）不會改變已印出的狀態行，但會在 stderr 印 warning——而且**印出之前終態已落地**（`reported`，見下），所以殘留是良定義的三形態（封閉列舉）：`<id>` 內含 `reported` 者＝「已回報、清理中斷」→ 下一個 poll 只清掉它、exit 1、**stdout 空**、訊息指向 `reported` 檔（不是 `unknown run id`，round 6 R6-9）；下一個 **abort** 同樣只清掉它但 **exit 0**（後置條件成立，見 `--abort` 表第 5 列——round 10 這一句曾把兩者都寫成 exit 1，Codex 實測 abort 為 0）；含 `status` 而無 `reported` 者＝「跑完了、還沒有人來報」（可能是從未被 poll，也可能是 claimer 在 `reported` 落地前死了——round 9 Stage B 之後兩者分不出來，也不需要分）→ 下一個 poll／abort 回報**一次**；兩者皆無者＝「worker 沒留下 status」→ finalizer 以 `FAILED status missing` fail-closed。本列舉封閉，**不得依性質相似類推第四形態**。round 4 L3 的「不含 status 即清理中斷、直接清掉」在 round 6 被推翻（RC2：abort 先 claim 但 kill 未收斂也留下無 status 的 run，而 worker 還活著——那種 run 現在由 worker 鎖判定：持鎖 → `RUNNING` 或逾時兜底，不是殘留）。
- 兜底 kill 後鎖若仍未釋放（極罕見：不可中斷的系統呼叫），回 `FAILED worker did not terminate`、exit 2、**run 目錄保留**供診斷——不假報「已清除」。這是唯一**不落地 `reported`** 的 FAILED：run 沒有終結，下一次 `--poll`／`--abort` 會再 claim、再 kill，並回報那**一次**（見 §9）。

- id 不合法（格式錯／不存在）→ stderr 訊息，exit `1`，**不對任何程序發訊號**。
- exit `1` 的答案不在上表——它們不是 run 的狀態，是「這次呼叫沒有答案」，**沒有一種值得 retry**（round 5 L5：ENOENT 曾被說成「另一個 poll，retry 有意義」，而 retry 只會得到 unknown）。封閉列舉：`invalid run id`（id 不合法）；`unknown run id`（id 從未存在，或已完全清除——兩者無法區分）；`being finalized by a concurrent poll or abort — its terminal state goes to that caller`（`claim` 鎖被別人持有）；`gone — removed, or being torn down by the caller that reported it`；`cannot claim …`（claim 檔因 EPERM、EACCES、ENOSPC、完整性檢查失敗——round 6 RC3b：這些曾被摺成「別人拿走了、不要 retry」，訊息附 `retrying will not help`；**claim 檔不在而 run 目錄還在**是另一個答案：先做 2 s 的有界重查——目錄在這段時間內消失就是上一項的 `gone`（那是本工具**自己**的併發拆除：`removeRun` 遞迴 unlink 先刪 claim、最後才 rmdir，round 9 實測 **8.7 %**、無攻擊者），仍在才回 `cannot claim … still on disk`，訊息指向 §9 與 `--force-reap`——round 10 R9-REG-A：舊訊息的三句話「不是本工具刪的／沒有別的 poll／retry 沒用」對最常見的入口全部為假）；`worker did not terminate … another caller holds the claim`（`--abort` 兩輪 kill 未收斂**且** claim 被別人持有——round 10 L9-1：worker 還活著，後置條件沒成立，不得 exit 0，也不印 `FAILED` token——那個 token 只在持有 claim 時印）；`cannot be trusted or inspected`（lock 檔完整性或 I/O 問題，run 原地保留）；`could not confirm the worker stopped … another caller holds the claim`／`could not confirm the worker stopped … run directory is gone`／`could not confirm the worker stopped … could not be claimed`（`--abort` 兩輪訊號後無法確認 worker 已停止——持鎖中或 lock 不可判定，兩者分不出來——且 claim 分別被別人持有／run 已消失／claim 不可得；三格皆 exit 1、不印 token，round 10 L9-1 與 round 11 補齊）；`already reported to another caller (recorded in …/reported)`（清理中斷的殘留，已清）；`cannot finalize … no terminal state printed`（`reported` 落地失敗，run 保留）；`--_selftest-claim-age was removed`。本列舉封閉，**不得依性質相似類推**——新的 exit-1 答案必須加進這裡並附測試。
- 「恰好回報一次」是**三個分開的性質、三個分開的機制**，不是一個函式（round 6 DA-1：五方都把「唯一 claim」當充分條件，它只是必要條件；契約這一句曾寫成「由單一函式保證」）：

  **(1) at-most-one claimer**——`<id>/claim` 上的 `fcntl(F_SETLK)` 寫鎖，持到程序結束。**這個檔案由 `--detach` 建立一次**，在 spawn worker 之前、印出 id 之前；**任何 caller 都不建立它**（`open` 不帶 `O_CREAT`）。所以「輸掉」是 `EAGAIN`，不是第二個 inode；「檔案不在」是「run 正在被清除」（`removeRun` 是唯一的刪除者），不是「輪到我建」。claim 檔不可信或其他 errno ＝ `.failed`（**不是**「別人拿走了」，round 7 RC3b）；claim 檔不在但 run 目錄還在 ＝ `.failed`（**不是** `gone`，round 8 R8-A：一個帶著已付費結果、還躺在磁碟上的 run 曾被說成「gone — 不要 retry」）。

  **(2) 至多印一次**——印任何終態**之前**先讓 `<id>/reported` 落地（有 `status` 則 `rename(status, reported)`，一個原子系統呼叫；沒有則 `O_EXCL` 建立），落地失敗就不印（exit 1、run 保留）；下一個 caller 遇到已有 `reported` 的 run 永不重報（round 6 RC4：DONE 後清理失敗曾在 65 s 後被改報 FAILED）。

  **(3) 沒有 claim 就不刪、不印**——`--poll`、`--wait` 迴圈、poll 端逾時兜底、`--abort`、detach 的 readiness 逾時清理，全部先取得 claim 鎖（round 6 RC1a：逾時兜底曾在 claim 之外 kill＋刪＋印，兩個 poll 打同一個逾時 run 10/10 雙終態）。**例外恰好兩個**：§4 的 24 h GC（且 GC 不碰 claim 鎖被持有**或不可判定**的 run），與人明確下達的 `--force-reap`（§2 下方——它是設計上的繞過，不是協定的一部分，engine 不得自動使用；round 10 新增時本句仍寫「唯一例外」，Codex 抓到）。

  **發訊號不在性質 (3) 之內（round 9 A1，改自 round 6–8 的「不發訊號」）**：claim 決定的是**誰可以回報終態、誰可以刪除 run**；「可不可以讓一個 worker 停止燒錢」由 **worker 鎖單獨回答**——`F_GETLK` 指出此刻的持鎖者（§4），不需要 claim。round 8 把兩者綁在一起的後果是實測到的：一個 claim 不可得的 run，`--abort` 回 **exit 0**（契約說那代表「不會再跑、不會再花錢」），**而 worker 仍在跑，且此後沒有任何命令能終止它**。`--abort` 是唯一目的就是停止付費的命令，**不得**被一個可能不可用的協定擋住。回報與清理仍在 claim 之後——RC1a 的發現是「在 claim 之外**印與刪**」，不是「在 claim 之外發訊號」。

  **為什麼不是前三種設計**（rounds 5–8 各付過一次代價，不要重新推導；程式碼裡 `ClaimResult` 上方有同一段）：`<id>.claim.<pid>` 第三種目錄名讓 `resolveRun` 與 GC 對它盲目、成功結果永久遺失（round 5）；`<id>.done/.claimed` 以 `O_EXCL` ＋ 60 s mtime lease，lease 是時鐘所以 `touch` 偽造得了、慢而非死的接手者會被搶、`lstat→unlink→O_EXCL` 是 ABA（round 6）；改成 fcntl 鎖但由 `rename` 的贏家建立，`removeRun` 的遞迴 unlink 會先放掉標記名、第二個接手者於是建出新 inode 並取得鎖（round 7，實測 7/150 雙終態），而擋掉接手者建立之後，「rename 成功、標記沒建成」變成黑洞（round 8）。三者的共同結構特徵是**「一個名字加上一個事後才建立的檔案」是兩個不可組合的系統呼叫**——把 claim 檔與 run 一起建立（在任何人能叫出它的名字之前）刪掉的是那個特徵本身。

  本列舉封閉，**不得依性質相似類推第四個性質或第三個例外**。

### 狀態叉積（規格，不是紀錄）

維度：**caller 配對** × **run 狀態**。每格填 `(stdout token, exit code)`；**沒有空格**——不可達的格子要寫「不可達」與理由。round 8 的兩條 blocking（R8-A／L-R8-1）正好落在 round 7 那張表沒有的格子裡，所以這張表放在契約裡，讓每一輪的 requirements lens 逐格驗證時會撞上空白。

run 狀態（**封閉列舉，五種**，round 9 Stage B 之後只有一個目錄名）：`live`（worker 持鎖）、`live-expired`（持鎖且超過 `max_time + grace`）、`done`（無人持鎖、有 `status`）、`stale`（無人持鎖、無 `status`）、`reported`（有 `reported`；claim 後崩潰或清理中斷）。

| run 狀態 ＼ | 單一 `--poll` | 單一 `--abort` | poll × poll | poll × abort | abort × abort | claim 被第三方持有 |
|---|---|---|---|---|---|---|
| `live` | `RUNNING`, 0 | `ABORTED`, 0（先殺後 claim） | 皆 `RUNNING`, 0（無副作用，不需 claim） | poll `RUNNING`／abort `ABORTED`（順序無關） | 恰好一個 `ABORTED`, 0；輸家空, 0 | poll `RUNNING`, 0；abort 空, 0 |
| `live-expired` | `TIMEOUT`, 3（claim → kill → 重讀 status；有 status 則以它為準） | `ABORTED`, 0 | 恰好一個終態；輸家空, 1 | 恰好一個終態；輸家空, 1（poll）／0（abort） | 恰好一個 `ABORTED`；輸家空, 0 | poll 空, 1 `concurrent`；abort 空, 0（別人正在 finalize，後置條件成立——round 10 R9-REG-B：本欄曾對 abort 寫 exit 1，實測 0）——**例外**：abort 兩輪訊號後無法確認 worker 已停止 → 空, **1**（`could not confirm`，L9-1） |
| `done` | `DONE <path>`, 0 | `ABORTED`, 0（結果被放棄） | 恰好一個 `DONE`；輸家空, 1 | 恰好一個終態 | 恰好一個 `ABORTED` | poll 空, 1 `concurrent`；abort 空, 0（別人正在 finalize，後置條件成立——round 10 R9-REG-B：本欄曾對 abort 寫 exit 1，實測 0） |
| `stale` | `FAILED status missing`, 2 | `ABORTED`, 0 | 恰好一個 `FAILED`；輸家空, 1 | 恰好一個終態 | 恰好一個 `ABORTED` | poll 空, 1 `concurrent`；abort 空, 0（別人正在 finalize，後置條件成立——round 10 R9-REG-B：本欄曾對 abort 寫 exit 1，實測 0） |
| `reported` | 空, 1（`already reported`，殘留清掉） | 空, 0（`nothing to abort`，殘留清掉） | 恰好一個清掉；另一個空, 1 | 同左 | 同左 | poll 空, 1 `concurrent`；abort 空, 0（別人正在 finalize，後置條件成立——round 10 R9-REG-B：本欄曾對 abort 寫 exit 1，實測 0） |

**`--force-reap` 不在本表**：它繞過 claim，對五種 run 狀態的結果一律是 `REAPED [<path>]`, 0（或操作性失敗 exit 2，見其小節）；與它併發的 poll／abort 在它之後得到 `unknown run id`。

**不可達的格子**：detach 的 readiness 逾時清理 × 任何併發 caller——id 尚未印出，沒有第二個 caller 能叫出這個 run。**表外的異常狀態**（claim 檔被 `rm`、claim 完整性失敗、lock 不可信）不在本表，它們一律 exit 1、run 原地保留，見 §9。

**不保證的格子（round 10 揭露；round 8 DA 收斂判準：不做第三次換設計，改為接受並揭露）**：`<run>/lock` 被同 uid `rm`、換成一個全新的一般檔、或換成 FIFO 之後，本表**沒有任何一格成立**——前兩者讓四項完整性檢查全過（那確實是一個乾淨的、自己 uid 的一般檔），`--poll` 對一個**活著的** worker 印 `FAILED status missing` exit 2 並刪掉 run，`--abort` 印 `ABORTED` exit 0 而 worker 續跑成永久孤兒（S9-1，round 8／9 實測；根因是 `lockState` 的 ENOENT ⇒ `.unlocked` 既有語意，round 9 Stage A／B 都沒有引入它）；FIFO 讓 `--abort` 在殺 worker **之前**被 `refuseIfUntrusted` 擋下，止血能力永久喪失——**stdout 無任何 token**，stderr 只有一行 `cannot be trusted or inspected`，沒有一個字說 worker 還活著（S9-2；round 10 這裡曾寫「stderr 無任何行」，三方實測 222 bytes）。這些格子標「不保證」而不是修，理由在 §9；唯一誠實的出路是 `--force-reap <id>`（下一節）。

### `--abort <id>`

- **先止血，後 claim（round 9 A1）**：`--abort` 先看 worker 鎖——持鎖中就送訊號（不需要 claim，理由見上方性質 (3) 的段落）；鎖釋放後才走與 `--poll` 完全相同的 `claimRun`（`<id>/claim` 的 fcntl 寫鎖），回報與清理都在 claim 之後（round 5 S3：abort 曾不參與 claim，與 poll 併發時 7/12 對成功的 run 偽造 FAILED）。**兩輪訊號後仍持鎖**（`FAILED worker did not terminate`）這個 stdout token 也在 claim 之後才印——round 10 L9-1：A1 把止血搬到 claim 之前時順帶把它搬了出去，兩個併發 abort 會各印一次；現在 claim 被別人持有 → stdout 空、exit 1（worker 還活著，後置條件沒成立，不得 exit 0）。
- `--abort` 的**後置條件**是「這個 run 不會再跑、不會再花錢」。它在「本次呼叫終止了它」、「別人正在 finalize 它」、「它已經消失」三種情況下都成立；後置條件成立時 exit 是 `0`（前三列）或 `1`（已完全清除 → `unknown run id`，與從未存在無法區分），見下表。stdout 的 `ABORTED` **專指「本次呼叫執行了終止」**：engine 讀 stdout token 記票，輸家印 `ABORTED` 就是同一個 run 的第二個終態 token（round 6 RC6，DA Q4）。**`--abort` 的 stdout 只有三種：`ABORTED`（本次終止）、空（所有非終止情況）、`FAILED …`（表末兩列的操作性失敗，不是 run 的終態）。**

| 情況 | stdout | exit | stderr |
|---|---|---|---|
| 本次 claim 到並終結了它 | `ABORTED` | 0 | — |
| claim 輸給併發的 poll／abort（`claim` 鎖被持有；worker 已由本次或對方終止） | 空 | 0 | `already being finalized by a concurrent poll — nothing to abort` |
| run 在 resolve 與 claim 之間**真的**消失（磁碟上已無 `<id>`），且 worker 已確認停止 | 空 | 0 | `already gone (removed, or torn down by the caller that reported it) — nothing to abort` |
| run 真的消失，但兩輪訊號後**無法確認** worker 已停止（持鎖中或 lock 不可判定） | 空 | **1** | `could not confirm the worker stopped, yet its run directory is gone (another caller reported it)`——若 worker 還活著它已是孤兒，`--force-reap` 靠 argv 仍找得到（round 11 補列；靜態可達、未實測——窗口是「kill 之後、claim 之前目錄消失」） |
| **claim 不可得但 run 仍在磁碟上**（標記從未建成／被 `rm`），但**無法確認** worker 已停止 | 空 | **1** | `could not confirm the worker stopped after SIGTERM/SIGKILL AND the run could not be claimed`（round 10 實測可達：`chmod 000 claim` ＋ kill 途中 lock 變 hard link） |
| **claim 不可得但 run 仍在磁碟上**（標記從未建成／被 `rm`）；worker 已由本次呼叫終止 | 空 | **1** | `the worker was terminated (nothing more will be spent) but the run could not be claimed for cleanup … left at <path>`——**後置條件只成立一半，不得用 exit 0 宣稱全部成立**（round 9 A1；round 8 L-R8-1 實測 exit 0 而 worker 續跑） |
| run 已含 `reported`（已回報、清理中斷） | 空 | 0 | `already finalized (recorded in …/reported) — nothing to abort; the leftover was removed` |
| id 格式錯／從未存在／已完全清除 | 空 | 1 | `invalid run id` ／ `unknown run id` |
| lock 不可信／無法檢查 | 空 | 1 | 既有訊息，run 原地保留 |
| `cannot claim`（EPERM、EACCES、ENOSPC、標記完整性…） | 空 | 1 | `retrying will not help` |
| `reported` 落地失敗 | 空 | 1 | `cannot finalize … run left in place` |
| SIGTERM→SIGKILL 兩輪未收斂，且本次拿到 claim | `FAILED worker did not terminate` | 2 | run 保留；不是終態（無 `reported`），claim 隨本程序結束釋放，下一次 poll／abort 再試（§9） |
| SIGTERM→SIGKILL 兩輪後無法確認 worker 已停止，且 claim 被別人持有 | 空 | **1** | `could not confirm the worker stopped … another caller holds the claim and will report it`——後置條件沒被建立；token 歸持 claim 者（round 10 L9-1；round 11 L-R10-2：「無法確認」不是「還活著」——lock 不可判定時 worker 可能早已停止，訊息不再宣稱它還在燒錢） |
| 已 `reported`、清不掉 run 目錄 | `FAILED could not remove run dir …` | 2 | 終態已落地為 `ABORTED`；殘留由下一次 poll／abort 只清不報 |

上表封閉（十四列），**不得依性質相似類推第十五列**；`--abort` 的任何新結果都必須加進表並附測試。列數由 `test/lint-contract-enumerations.sh` 機器核對（round 10 這一句寫「十一列」而表有十二列、round 9 寫「十列」而表有十一列——手打的數字連兩輪都錯，散文規則對數字無效）。

- **順序（round 9 A1；round 10 L9-1）**：先 `lockState`——持鎖中就 `SIGTERM` → 2 s → `SIGKILL`，第二輪同樣（持鎖者若在第一次探測**之後**才拿到鎖也會被送到訊號，Codex round 4 #10），**這一步不需要 claim**。接著 `claimRun`；兩輪後仍持鎖 → 持有 claim 者印 `FAILED worker did not terminate`、exit 2、run 保留，輸掉 claim 者 exit 1 不印。確認鎖釋放且拿到 claim 後 `reported` 落地（內容 `ABORTED`）→ 清除預設輸出檔 → 清除 run 目錄 → 印 `ABORTED`。
- 未持鎖（已結束、尚未被 poll）→ 同樣先 claim、`reported` 落地，清除（含預設輸出檔），印 `ABORTED`，exit `0`——結果被放棄是 abort 的語意。
- id 不合法 → exit `1`，不發訊號。

### `--force-reap <id>`（v2.23.0+，round 10；round 8 DA 預先授權的逃生命令）

語意是一句話：**「我知道我在繞過 claim 協定。」** 它存在的理由是 §9 的 S9-2——lock 檔不可信時 `--abort` 被擋在殺 worker 之前，此後**沒有任何命令**能讓那個 worker 停止燒錢；以及 S9-1——工具對活的 worker 印出終態並刪掉 run 之後，worker 成為永久孤兒。這兩格在叉積表標「不保證」（round 8 DA 收斂判準：接受並揭露，不做第三次換設計），`--force-reap` 是唯一誠實的出路。

- **一定能終止 worker**：**完全不信任** `<run>/lock`——以 `ps -o args=` 印出的**文字**（argv 以空白接起來，quoting 已遺失）找出**同 uid** 且該文字含相鄰的 `--_worker <id>` 的程序，SIGTERM → 2 s → SIGKILL。**這不是 argv 邊界檢查**：一個**單一**、內含空白的 argv 元素只要寫著這兩個字也會匹配（本 repo 自己的 `pgrep -f`／`pkill -f` pattern 就是這個形狀；round 10 四方實測）。同 uid 在模型外（§6 第一列），id 是 32 字元 CSPRNG，非蓄意碰撞可忽略；**跨 uid** 植不進 victim 的 argv。不改成讀真 argv（`sysctl KERN_PROCARGS2`）：那是換設計、買不到安全（同 uid 本來就能殺你任何程序）、且會打掉下一條的孤兒回收（round 10 DA 裁決）。唯一的例外是 `ps` 本身失敗——`cannot enumerate processes (ps failed)`，exit 1、不動手（fail-closed；「一定能終止」帶這一個揭露的例外）。**永不**對 `F_GETLK` 回報的 pid 送訊號：victim 持鎖的檔案 `rename` 進 `<run>/lock` 會通過 §4 的全部檢查（實測），逃生口不得變成殺 victim 的原語。SIGKILL 都殺不掉 → `FAILED worker did not terminate`、exit 2、run 保留。**孤兒也在範圍內**：S9-1 之後 run 目錄已被刪，worker 只靠 argv 找——「沒有目錄**且**沒有程序」才是 `unknown run id`。
- **一定能取回輸出**：`<base>/<id>.out.md`（§3 的預設輸出）存在且非空 → stdout 印 `REAPED <path>`，**該檔保留、轉為 caller 所有**（與 `DONE` 相同）；不存在或空 → 印 `REAPED`，stderr 說明沒有輸出可取（caller 自己給的 `--output` 從不被本工具讀取或刪除，caller 知道它在哪）。**清理失敗也取得回**：run 目錄刪不掉時印 `FAILED could not remove run dir <dir>; output kept at <path>`（exit 2；無輸出時省略分號之後）——路徑在 token 裡，caller 不必再猜（round 10 這一格印了列舉外的第三種 token 且不帶路徑，三方實測）。
- **繞過 claim**：不取 claim、不看 claim 被誰持有、不落地 `reported`，直接清掉 run 目錄（含不可信的 lock／claim 檔）。這正是它與 `--abort` 的差別，也是它必須由人明確下達、engine 的 prompt **不得**自動使用它的理由——併發的 poll／abort 在它之後會得到 `unknown run id`。
- **`REAPED` 是後置條件，不是動作報告**：它的意思是「此刻 `ps` 文字裡沒有任何程序帶著這個 id、且沒有 run 目錄殘留」——不是「我剛剛殺了一個 worker」。無目錄時它的唯一依據就是上面那個 `ps` 文字比對，所以一個「無目錄、無真 worker、但有別的同 uid 程序 argv 裡寫著這個 id」的情況會被 reap 並印 `REAPED`（round 10 實測；同 uid 在模型外，揭露不防禦）。
- exit 1（不發訊號、不刪東西）：`invalid run id`（格式錯）；`unknown run id`（**沒有目錄且** `ps` 文字裡沒有程序帶此 id——S9-1 的孤兒只靠後者找到，所以「有程序沒目錄」不是 unknown）；`cannot enumerate processes (ps failed)`（無身分來源，見上）。與 `--detach`／`--poll`／`--abort` 互斥（同時給 → exit 1）。
- stdout 只有兩種成功 token：`REAPED <path>`、`REAPED`；操作性失敗（exit 2）兩種：`FAILED worker did not terminate`、`FAILED could not remove run dir <dir>; output kept at <path>`（無輸出時無分號後段）。**封閉列舉，不得依性質相似類推**；由 `test/lint-contract-enumerations.sh` 對 `bin/codex-call` 的 `print` 字面逐節核對。

## 3. Run id 與狀態目錄

- id：`^[A-Za-z0-9]{32}$`，由 CSPRNG 產生。**`--poll` / `--abort` / `--force-reap` 只接受 id，不接受路徑。**
- base：`$HOME/.cache/codex-call/runs/`（`0700`）。run 目錄 `<base>/<id>/`（`0700`）含 `meta.json`、`prompt.txt`、`lock`、`claim`、`worker.log`（皆由 `--detach` 在 spawn worker 之前建立），`status`（worker 在同一程序寫入），以及 `reported`（finalizer 在印出終態**之前**落地，§2 性質 (2)）。round 9 Stage B 之後**只有這一個目錄名**——沒有 `.done`、沒有 `.claimed`（兩者已移除，失敗史見 §2「為什麼不是前三種設計」）。預設輸出檔在 base 下與 run 目錄並列：`<base>/<id>.out.md`。
- **base 硬化**（每次 `--detach`）：`~/.cache/codex-call` 與 `runs` 兩層各自 `lstat`——必須是真目錄（拒 symlink）、owner 必須是當前 uid、權限修正為 `0700`（`createDirectory` 不會修正預先存在的 0755，實測），**`chmod` 失敗也是失敗**（round 4 S2：原本被吞掉，「強制」曾是 best-effort）。任一不符 → detach 同步失敗。硬化**先驗上層再建 `runs/`**，拒絕前不在不受信目標下建任何東西（S4）。硬化只涵蓋這兩層：`~/.cache` 本身（含它是 symlink 到另一顆磁碟這種合法配置）屬 §6 第二列「caller 環境完整性」，run 樹會落在其目標且不受本工具的權限承諾涵蓋（S3）。
- 為什麼不收路徑：round 2 verify（PR #47）證明「接受任意目錄 + 檔案存在性檢查」等於任意 PID kill / `rm -rf` 原語。id 只能解析到 HOME 之下的 0700 目錄，跨使用者偽造面消失。

## 4. 生存與身分（為什麼 PID 重用不會誤殺）

- worker 對 `<run>/lock` 持有 **`fcntl(F_SETLK)` POSIX record lock**，直到程序結束（含被 kill）。
- `--poll` / `--abort` 用 **`F_GETLK`** 判斷：`F_UNLCK` = 已結束；否則 `l_pid` 是**查詢當下**持鎖的程序。
- **run 目錄的回收**：`--detach` 每次啟動前掃 base，刪除超過 24 h **且無人持鎖、lock 檔可信、claim 鎖無人持有且可判定**的 `<id>`／`<id>.out.md`（依 mtime＝最後寫入；round 9 Stage B 取消 rename 之後只有一個目錄名、一個時鐘——round 5 L6 的 max(mtime, ctime) 是 rename 只更新 ctime 逼出來的，已隨 rename 一起移除）。`--abort` 是**盡力而為**的早停路徑（engine step 4 要求 agent 早停時先 abort），agent 被硬殺時不可用，所以 GC 仍是最後防線；被放棄的 run（含 `prompt.txt`，即 artifact 的完整副本）最多存活到下一次 detach。 GC **不碰**任何 `claim` 鎖被持有的 run（有人正在 finalize），並且是**唯一**在 claim 之外刪除 run 的路徑（§2 性質 (3) 的例外；`--force-reap` 是人明確下達的第二個，見 §2）；隱藏旗標 `--_selftest-gc-age` 生效時**只掃 meta 含 `selftest_sleep` 的 run**（round 6 RC5：它曾掃掉同 base 的正式 run 與已交付的輸出）。掃到含 `status` 而無 `reported` 的 run 會在 stderr 記一行「finished but never reported」——round 10 S9-3：那可能是「跑完了沒人來 poll」也可能是「claimer 在 `reported` 落地前死了」，Stage B 之後兩者分不出來，訊息不再宣稱後者（round 9 的「its claimer died first」對前者是捏造）。

- **標記狀態也有三個答案（round 9 A2）**：`held`（`F_GETLK` 明確回報持鎖者）／`unheld`（ENOENT）／`untrusted`（完整性四檢查任一不符，或 `F_GETLK` 本身失敗）。GC 只在 `unheld` 時掃除；**`untrusted` 不刪、記錄一行**——與本節對 lock 檔 `.untrusted` 的處置同一紀律（R4-S1：「沒有鎖檔」「不信任鎖檔」「持鎖中」是三個答案，把第二個摺進第一個會讓完整性失敗看起來像已結束的 run）。round 8 曾把它摺成兩答案且方向正好相反：同 uid 對標記 `ln` 一個 hard link（nlink 2）就讓 GC 印出「claimer died first」並**掃掉一個 claimer 全程存活的 `.done`**（round 8 DA §3 實測）；**非對抗入口**是 `F_GETLK` 在 NFS／SMB 掛載的 `$HOME` 上回 `ENOLCK`／`EIO`，不需要任何攻擊者。靜默刪掉一個活的 claim 會讓已付費的結果永久消失，比留下一個看得見的殘留嚴重——所以這裡選擇留下，並在 §9 列出人工清理。
  發訊號的對象永遠是 `F_GETLK` 回報的 pid，**不從任何檔案讀 pid**——這消滅了「讀到陳舊 pid 檔」這一類誤殺。
- **誠實邊界（PID 重用）**：`F_GETLK` 與 `kill()` 之間仍有微秒級 TOCTOU——持鎖者可能在查詢後、訊號前退出，且該 pid 理論上可被回收。本工具的緩解是**每次發訊號前都重新查詢持鎖者**（`killHolder`），把視窗縮到單一系統呼叫之間；macOS 沒有 pidfd 一類可把查詢與訊號原子綁定的原語，所以這不是「不可能」，是「機率極低且已縮到最小」。
- 實測（macOS 26）：`flock()` 鎖在 `F_GETLK` 下 `l_pid = -1`（BSD 行為），**不可用**；`fcntl` record lock 回報真實 pid。這是選 `fcntl` 的唯一理由。
- 誠實邊界：`fcntl` 鎖在程序關閉**任何**指向該檔的 fd 時釋放。worker 只開一次且不關閉；不得在 worker 內對 `lock` 另開 fd。
- **lock 檔完整性**：`<run>/lock` 以 `O_NOFOLLOW` 開啟，並 `fstat` 驗證它是一般檔案、`st_nlink == 1`、owner 是當前 uid。任一不符、**或根本無法檢查**（`lstat`／`open`／`F_GETLK` 因 EACCES、ELOOP、EIO 等失敗——round 5 L4：這是「無法判斷」，不是「沒有 lock 檔」，只有 ENOENT 才算沒有）→ `--poll`／`--abort`／`--poll --wait` **exit 1、不發訊號、run 原地保留**，訊息附原因（不判為終止、不清除——round 4 S1 實測原本把它當「已結束」刪掉 run，把活的 worker 孤兒化，是 lifecycle 的 fail-open）；GC 也跳過它。這三個檢查**排除的是 symlink、hard link 與非一般檔案**，它們**不**建立「這是我們建立的 inode」：`rename()` 保留 inode，把 victim 正持鎖的檔案**搬**進 `<run>/lock` 可讓三個檢查全過，abort 會殺掉它（實測，bats 鎖住這個宣告的邊界）。在「寫得到 base」這個前提下沒有任何檢查能成立——`meta.json` 與 `lock` 同在一個可寫目錄；那需要同 uid 或 HOME 注入，皆在 §6 之外。這三個檢查買到的是消掉最便宜的兩種變體，與一行誠實。
- **worker 不可重放（已完成的 run）**：run 已有 `status` 時，第二個 `--_worker` 直接退出，不重跑 HTTP、不覆寫 status。未完成（無 status）且無人持鎖的 run **可以**被第二個 `--_worker` 接手——那是隱藏旗標，只有同 uid 能碰到（Codex round 4 #13）。

## 5. 期限與清理

- worker **自己**強制 `--max-time`（URLSession timeout + semaphore，既有機制），到期寫 status token **`TIMEOUT`**（其餘失敗寫 `<exit code> <message>`，成功寫 `0`）。逾時的判定依 **(domain, code)**：`codex-call/408`（semaphore 兜底，`max-time + 5 s`）與 `NSURLErrorDomain/-1001`（URLSession 自己的 timer，設在 `max-time`，**比兜底早 5 s、是主要路徑**）都寫 `TIMEOUT`。round 4 L1：只認 408 讓主要路徑寫成 `FAILED -1001`——與 round 3 L3 同型（拿 code 數字當分類鍵），換了一端。poll 比對的是**整個 token**，不是數字前綴——round 3 L3：`NSError code 3`（auth.json 缺 tokens）曾被誤判成可重試的逾時。
- poll 端另有兜底：持鎖超過 `max-time + 60 s` ⇒ `SIGKILL`。兩者都不依賴任何可被竄改的 deadline 檔——期限資訊寫在 `meta.json`，但 meta 損毀時 poll **fail-closed**（視為逾時，kill + TIMEOUT），不會退化成無限 RUNNING。
- **finalize 的所有權不看年齡**：下一次 `--poll`／`--abort` 能拿到 `<id>/claim` 的 fcntl 寫鎖就是 finalizer，拿不到就是有人正在 finalize（`--poll` exit 1、`--abort` exit 0——後者的後置條件由對方成立，見 §2 的 `--abort` 表；訊息明說「concurrent」。round 10 這裡對兩者都寫 exit 1，Codex 抓到）。沒有接手分支、沒有第二個目錄名、沒有第二個時鐘（round 9 Stage B）。round 5 的「claim 超過 60 s（ctime）才可接手」與「claim → 清理只需毫秒、門檻不會誤傷活的 claim」在 round 6 被推翻：abort 先 claim 但 kill 未收斂會留下 worker 仍活的 run（RC2），而慢但活著的 finalizer 會被 60 s 後的第三者搶走（R6-3）；round 6–8 的 `.done` 中繼目錄與 `.claimed` 標記已於 round 9 取消（失敗史見 §2「為什麼不是前三種設計」）。run 內 worker 仍持鎖 → poll 回 `RUNNING`（未逾時）或走逾時兜底（先 claim 再 kill）——它不是殘留。
- `status` 由 worker 在**同一程序**寫入；寫失敗 ⇒ 無 status ⇒ poll 回 FAILED。沒有「半截輸出 + 非零退出被當成功」的路徑：DONE 要求 status 為 `0` **且**輸出檔非空。

## 6. 威脅模型

以下是**封閉列舉的三列**（同 uid／caller 環境完整性／跨 uid），**不得依性質相似類推第四列**。round 3 security 的 H1（hard-link lock）從「同 uid」與「跨 uid」之間的縫掉出去，因為第二列當時不存在。（下方的 prompt-injection 段落**不是**第四列，是對緩解措施的說明——round 4 R4-4 指出原本的排版讓讀者數成四列。）

- **同一 uid 的攻擊者在模型之外。** base 是 `0700`，同 uid 本來就能 kill 你的任何程序。
- 硬化（§3）與 lock 完整性（§4）**不建立**針對「寫得到 base」的安全邊界。它們買到的是消掉最便宜的兩種 lock 檔變體與一行誠實。**寫得到 base 者可以，封閉列舉六項：** (1) 殺掉本工具的 worker（直接 kill——同 uid 本來就能）；注意把 victim 持鎖的檔案 `rename` 進 `<run>/lock` 的效果是**相反**的：`--abort` 對 `F_GETLK` 回報的 pid 送訊號，殺的是 **victim**、worker 反而活成孤兒、run 被刪、印 `ABORTED` exit 0（round 10 實測）——那落在第 (6) 項，不是這裡（round 10 把它寫在 (1) 底下，歸因反了）；(2) 刪掉 base 下的任何 run 與預設輸出；(3) `touch <run>/reported`——讓一個已付費的成功結果被下一個 caller 只清不報，caller 得到 exit 1（round 7 Q3）；(4) 把 `<run>/claim` 換成 symlink／FIFO／目錄／hard link 或直接 `rm`——讓 claim `.failed`（run 原地保留、需人工清理），**或**讓 GC 誤判（round 9 A2 之後 GC 對不可判定一律不刪，所以這一項的傷害從「掃掉正在被 finalize 的 run」降為「留下需人工清理的殘留」）；(5) 改寫 `meta.json` 的**任何欄位**或 `prompt.txt`——`output` 讓 `--poll` 印出 `DONE <攻擊者選定路徑>`，caller 會去讀那個檔（round 8 DA §4.1 實測）；`instructions`／`model`／`effort`／`service_tier` 與 `prompt.txt` 讓 worker **用受害者的 OAuth 送出攻擊者寫的 prompt 與 system instructions**（配額竊取＋任意生成），並把攻擊者自撰的文字當成「Codex 的審閱」交給 wrapper agent（round 10 S10-4，#54）；**這一項直接餵進本節末的 prompt-injection 鏈**，是「刪除面」（round 5 S2 已修）之外的「回報面」與「送出面」，同一句上界曾因此兩次為假；(6) **讓工具對一個活著的 worker 印出終態並刪掉 run，或讓 `--abort` 永久無法止血**——`rm <run>/lock`、換成全新一般檔、或把 victim 持鎖的檔案 `rename` 進來（前兩者四項完整性檢查全過，第三者三檢查全過）→ `--poll` 印 `FAILED status missing` 並刪 run、`--abort` 印 `ABORTED` exit 0，worker 續跑成永久孤兒（S9-1）；`mkfifo <run>/lock` → `--abort` 在殺 worker 之前被拒：**stdout 無 token、stderr 一行 `cannot be trusted or inspected`**（S9-2；round 10 曾寫「無任何 stderr 行」，為假）。round 9 security 指出這既不是第 1 項（殺自己的 worker）也不是第 2 項（刪自己的 run），是第六類傷害；逃生命令 `--force-reap <id>`（§2）。**以上六項為封閉列舉，不得依性質相似類推第七項。** 本工具**不宣稱防禦**其中任何一項；列出它們是為了讓 caller 知道「同 uid 在模型外」這句話具體換來的是什麼。
- 跨 uid：`/tmp` 不再涉入（base 在 HOME）；id 不可猜（CSPRNG 32 字元）；poll 不收路徑。

**prompt-injection 鏈（緩解說明，不屬於上面三列）**：artifact → Codex 輸出 → wrapper agent 讀取，是一條 **prompt-injection 鏈**。engine 的「strictly as DATA」與 `DATA_GUARD` 是對同一個 LLM 的自然語言指示，是**緩解、不是安全邊界**——本契約不宣稱已建立隔離。caller 端的硬性規則：poll 用的 id **只能**來自 `--detach` 的 tool output，不得來自任何檔案內容；agent 可執行的命令面由 caller 的 tool 權限決定，本工具不擴大它。round 4 起 engine 的 codex leg 要求 agent 在讀取 Codex 輸出檔**之後**執行一次 `rm -f '<path>'`，早停時執行 `--abort '<id>'`——這擴大的是 **engine 指示的動作面**，不是本工具的權限；兩者的唯一可變部分分別是 `DONE` 印出的路徑與 `--detach` 印出的 id，agent 不得從任何檔案內容取路徑或 id（S5／S9）。codex-call 印到 stderr 的一切（`FAILED` 原因、`worker.log` 尾段）同樣是 DATA（S7）。

## 7. 隱藏旗標（internal，不在穩定性承諾內）

- `--_worker <id>`：由 `--detach` 呼叫。id 不合法或 run 不存在 → exit 1。
- `--_selftest-sleep N` / `--_selftest-fail` / `--_selftest-grace N` / `--_selftest-prelock-sleep N`：與 `--detach` 並用，worker 以 sleep + 寫檔取代 HTTP（測試 detach / lock / poll / abort 路徑，不發網路）；`prelock-sleep` 讓 worker 在拿鎖**之前**卡住（測 readiness 逾時路徑）。
- `--_selftest-claim-age N`：**已於 round 7 移除**（接手不再有時間門檻，沒有東西可覆寫）；給了就 exit 1、零副作用。
- `--_selftest-ignore-term`：與 `--_selftest-sleep` 並用，selftest worker **活過** SIGTERM：安裝 handler，收到訊號時 touch `<run>/term-seen`（測試錨點，round 10）並把被中斷的 `sleep()` 睡回剩餘秒數直到期限（round 11）。這個前提由 `R11-HOOK` 斷言——round 10 換掉 `SIG_IGN` 時 `sleep()` 被 EINTR 提早返回、worker 0 秒內結束，4/91 個 case 綠的理由靜默變了而沒有任何測試發現。用途：測「kill 等待中 lock 變不可信不得視為已釋放」、「逾時瞬間 status 已落地」與 SIGKILL 升級輪。
- `--_selftest-gc-age N`：與 `--_selftest-sleep` 並用，覆寫 24 h 的 GC 門檻——**只對 meta 含 `selftest_sleep` 的 run 生效**（round 6 RC5），正式 run 不受影響。
- `--_selftest-classify DOMAIN CODE`：印出該 NSError 會寫成的 status token，無副作用（測 catch 分支的 (domain, code) 分類）。
- **隱藏旗標同 uid 皆可達**：它們是測試鉤子不是安全邊界，契約 §6 第一列已把同 uid 排除。
- `--selftest-error-extract`（#25，既有）。

## 8. 穩定性承諾

- §1、§2 的旗標名（含 round 10 新增的 `--force-reap`）、stdout 格式、exit code、§3 的 id 格式與 base 路徑：**STABLE**。變更需 major bump + migration note。新增旗標與新增 stdout token（`REAPED`）不是 breaking change——既有 caller 不會收到它們。
- §7 隱藏旗標：可在 minor 內變更。
- 消費者釘 SHA（codex-pro）時，本檔的版本欄與 `CHANGELOG.md` 是判斷「要不要 re-vendor」的依據。

## 9. Known limitations（round 7 明確排除——寫在這裡，不是默默不做）

- ~~**worker 用路徑字串寫 status**~~ —— **round 9 Stage B 已關閉**：取消 `rename` 之後 run 目錄的名字終生不變，worker 手上的路徑字串永遠有效，「rename 之後才收尾的 run 被誤報 TIMEOUT」在結構上不再發生（round 8 DA §1.6 指出這是取消 rename 的附帶收益；`R9-B7` 守它）。**不需要** dirfd／`openat` 重構。
- **`--wait` 上限 120 s 與 Claude Code Bash tool 的前景 timeout 衝突**：`--wait 120` 實測 121 s、被工具層移到背景（round 6 regression）。engine 用 `--wait 30`；上限未降。
- **lock 檔不可信的 run 沒有回收路徑**（round 6 L-R6-4）：poll／abort／GC 三方皆拒，需人工清理。
- **探測用 `O_RDWR` 開 lock**（round 6 S5-R6）：`chmod 400 lock` 讓三方皆拒、run 永久不可回收；`F_GETLK` 用 `O_RDONLY` 即可，未改。
- **同 uid `rm <id>/claim`**：run 從此不可 claim——`--poll` 回 exit 1「claim 檔不見了、run 還在磁碟上」（**不是** `gone`），`--abort` 仍會終止 worker 並說「已止血、清理沒做成」，run 原地保留待人工、24 h GC 或 `--force-reap`。**這一項在替代設計上沒有消失**（round 8 DA 攻擊 4 預言、round 9 實測確認）；把它寫在這裡，就是不把「結構上不存在」講成一句假話。
- **同一個狀態有一個非對抗入口（round 10 R9-REG-A）**：本工具自己的併發拆除——`removeRun` 是遞迴 unlink，claim 先於目錄消失；round 9 實測 150 輪 **13 次（8.7 %）** 第二個 poll 落在這個視窗，無攻擊者、無故障。`claimRun` 對「claim 不在、目錄還在」現在先做 **2 s 有界重查**：目錄消失就是 `gone`；仍在才回 `cannot claim … still on disk`。誠實邊界：**2 s 內分不出「正在拆除」與「被 `rm`」**——拆除慢過 2 s 的 run（幾乎不可能，目錄只有六個小檔）會被說成 `rm`；而被 `rm` 的 run 這 2 s 是白等的。
- **`<run>/lock` 被 `rm`、換成全新一般檔（S9-1）**：`lockState` 的 ENOENT ⇒ `.unlocked` 是既有語意，四項完整性檢查也擋不住一個乾淨的、自己 uid 的一般檔——`--poll` 對活的 worker 印 `FAILED status missing` exit 2 並刪 run，`--abort` 印 `ABORTED` exit 0 並刪 run，worker 續跑成永久孤兒，此後任何呼叫得到 `unknown run id`。**不修**（收斂判準）：在「寫得到 base」的前提下沒有任何檢查能區分「我們建的 lock」與「別人放的一般檔」（§4 早已寫明）。叉積表對這種狀態標「不保證」；逃生：`--force-reap <id>`（它不信任 lock，改以 argv 找 worker）。
- **`<run>/lock` 換成 FIFO（S9-2）**：`--abort` 被 `refuseIfUntrusted` 擋在**殺 worker 之前**，止血能力永久喪失——stdout 無 token、stderr 一行 `cannot be trusted or inspected`（沒有一個字說 worker 還活著；round 10 曾寫「stderr 無任何行」，為假）——**直接違反 A1 自己寫的原則**（`--abort` 不得被一個可能不可用的協定擋住）。**不修** abort 本身：A1 的「不需要 claim」是對的，但「不需要可信的 lock」不成立——沒有可信的 lock 就沒有可信的持鎖者 pid，對 F_GETLK 回報的 pid 送訊號會殺到 victim（R3-Sec-H1 實測）。出路是 `--force-reap`，它用另一個身分來源（同 uid ＋ argv 含 CSPRNG id）。
- **`claim` 完整性失敗**（目錄／symlink／hard link／FIFO／`chmod 000`／`F_GETLK` 失敗）：poll／abort exit 1（`cannot claim`）、run 原地保留；**GC 也不掃**（round 9 A2：不可判定時刪除會靜默丟掉一個活 claim 的已付費結果），只記錄一行——因此**這種 run 需要人工清理**（或 `--force-reap`），與上一列的 lock 檔同型。round 7 L-R7-2 的原始問題是「沒有任何回收路徑」，round 8 用「不可判定就刪」去修它是錯的方向；正確的代價分配是「留下、但說出來」。
- **`reported` 落地與 `print` 之間被 SIGKILL**：終態永久遺失（下一個 caller 得到 `already reported`）。這是 at-most-once 的方向，round 6 DA Q5 選擇了它而不是重報。
- **`FAILED worker did not terminate` 之後的第二個 token**：worker 後來自然死亡 → 下一次 poll 走 `.unlocked` 路徑，得到 `FAILED status missing`；仍持鎖且再逾時 → `TIMEOUT`。兩者都是第二個 stdout token（上一條所述的例外）。
- **`reported` 與 `claim` 的偽造面（同 uid）**：在活的 `<id>` 內預放一個 `reported` 檔，claimer 會把它讀成「已回報」而只清不報——**一個 `touch` 就讓已付費的成功結果被清掉**；把 `claim` 換成 symlink 會讓 claim `.failed`、run 永久保留（人工、GC 24 h 或 `--force-reap`）。兩者都在 §6 第一列（同 uid）之外，但比 round 6 的 `meta.output` 遞迴刪更容易觸發；本工具不宣稱防禦，只在此揭露。
- **`FAILED worker did not terminate` 之後 run 保留、不落地 `reported`**：到這一格有**兩條路**——SIGKILL 都殺不掉的 worker（kernel 層異常），或 lock 在 kill 等待中變得**不可判定**（`lockReleasedForSure` 的三態：不可判定永遠不是「已釋放」）——後者 worker 可能**從未被送過任何訊號**（`killHolder` 只對 `.held` 發訊號；`R7-M05` 正是這一格，round 10 這裡寫「只有 kernel 層異常才會到這裡」，Logic 抓到）。此時下一次 poll 的 TIMEOUT 是同一 run 的第二個 stdout token——§2 性質 (2) 在這一格有明寫的例外。
- **claim 檔不在時的 2 s 有界重查把任何 `lstat` 錯誤摺成 `gone`**（不只 ENOENT；EACCES／EIO 也是），且最後一次觀測在 1.95 s、之後的 50 ms 沒看——與 round 9 的單次 lstat 同一語意，只是觀測窗放大 40 倍。誠實邊界：訊息說「waited 2 s — it is not being torn down」證明的只是「2 s 內目錄仍可見」（round 10 Logic L-R10-8／Codex）。
- **`.done` 這個名字與接手（adoption）分支已於 round 9 Stage B 移除**；它們的失敗史保存在 `bin/codex-call` 的 `ClaimResult` doc-comment 與 §2 的「為什麼不是前三種設計」，不是隨程式碼一起消失（round 8 DA 的遷移完整性要求：被刪機制的失敗史不得淨損失）。

上列各項（逐條以 `-` 起首、可數）為封閉列舉，**不得依性質相似類推**——新的排除項必須寫進這裡並附理由，不得默默不做。**這句是本節的最後一句**：round 9 與 round 10 都曾在它之後再長出一個 `-` 起首的項目（Logic L-R10-12），round 11 把它搬回列舉內。
