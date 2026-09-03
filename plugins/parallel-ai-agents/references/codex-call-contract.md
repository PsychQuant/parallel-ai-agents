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
- `--detach` / `--poll` / `--abort` **恰好一個**；同時給 → 同步錯誤 exit 1。
- **readiness handshake**：`--detach` 只在 worker **已持鎖、或已寫出 `status`** 之後才印出 id（上限 20 s；逾時 → **先 SIGTERM／SIGKILL worker 並等它退出、確認無人持鎖**，再清 run（清除失敗印 warning）；worker 殺不死 → run 原地保留、exit 1 並說明；worker 先退出且無 status → 同步 exit 1、不印 id、run 已清。stderr 一律附 `worker.log` 尾段——**真的是尾段**：從檔尾有界讀取最後 12 行，經 sanitizer；worker 的每一條提早退出都會先寫一行原因，所以尾段不會是空的（round 4 R4-3b、Codex #3／#14）。「還沒開始」與「已經跑完」是**兩個不同的答案**（round 3 的第一版 handshake 把它們壓成同一個，DA 實測 11/12 把瞬間完成的 run 判成沒啟動並刪掉結果）。
- 因此 caller 拿到 id 之後看得到的 run 狀態是**封閉列舉的兩種：持鎖中／已結束**。「正在啟動」對 caller 不可見。**不得依性質相似類推第三種**——round 3 的 L1（abort 在啟動視窗漏殺）正是從沒列出的那一種掉出去的。
- `--output` **選填**。省略時輸出寫到 `<base>/<id>.out.md`（見 §3），**該檔由本工具擁有**：任何非 `DONE` 的 terminal 狀態（FAILED / TIMEOUT / ABORTED）都會把它清掉。給定時 worker 直接寫該路徑，**不經任何中介或搬移**，且本工具**永不**刪除 caller 給的檔案（半截輸出留給 caller 處置）。**`DONE <path>` 印出之後，該檔（不論預設或 caller 給定）轉為 caller 所有**：本工具不再碰它，也沒有任何回收機制——caller 讀完必須自己刪（engine 的 prompt 明寫）。唯一例外是 §4 的 24 h GC：落在 base 且命名為 `<id>.out.md` 形狀的檔案（含 caller 刻意把 `--output` 指到那裡的情況）會被當最後防線回收——那不是 caller 可以依賴的回收（round 4 S8）。
- `--max-time` 在 `--detach` 下必須是**正整數**（垃圾值 / `0` / 負數 → exit 1、不建 run）。同步路徑維持歷史行為（§1 逐 byte 不變），不加驗證。
- worker 是**單一程序**（本 script 以 `--_worker <id>` 重新執行自己，路徑為 `argv[0]` 的 realpath，不依賴 cwd / PATH），並在啟動時 `setsid()` 自成 session，不隨 launcher 的 process group / 終端 SIGHUP 消失（`setsid` 失敗時記 log、不阻擋——盡力而為，不是絕對保證，Codex round 4 #11）；stdio 全部導向 run 目錄內的檔案，**不繼承** caller 的 pipe（否則 `$(codex-call --detach …)` 會阻塞到 run 結束）。

### `--poll <id>`

印一行狀態，立即返回：

| stdout | exit | 意義 |
|---|---|---|
| `RUNNING` | 0 | worker 仍持鎖 |
| `DONE <path>` | 0 | 成功；`<path>` 是輸出檔。run 目錄已清除 |
| `FAILED <reason>` | 2 | worker 回報失敗，或 status 缺失（fail-closed），或 **worker 拒絕終止**（見下）。run 目錄已清除（後者除外） |
| `TIMEOUT` | 3 | worker 自報逾時，或 poll 端兜底：已持鎖超過 `max-time + 60 s` ⇒ SIGTERM → 2 s → SIGKILL，**確認鎖已釋放**後才清除 |

- `--wait N`（1–120）：在 codex-call **內部**阻塞最多 N 秒等待狀態改變（每秒重查持鎖者與期限），仍 RUNNING 則印 `RUNNING`；終態提早返回。這是輪詢節奏的唯一正確形狀——**不要用 shell `sleep`**：Claude Code 的 Bash tool 擋前景 sleep，round 4 R4-1 實測 `sleep 30; …` 被工具層拒絕。
- 清除失敗（`removeItem` 錯誤）不會改變已印出的狀態行，但會在 stderr 印 warning。`<id>.done` 殘留的兩種處置（與 §5 一致）：仍含 `status` 的 → claim 超過 60 s 由下一次 poll／abort 接手完成；**不含 `status` 的是清理中斷留下的**（`removeItem` 遞迴且非原子）→ 清掉並回 exit 1「unknown run id」，**不會把已回報的 DONE 翻成 FAILED**（round 4 L3）。
- 兜底 kill 後鎖若仍未釋放（極罕見：不可中斷的系統呼叫），回 `FAILED worker did not terminate`、exit 2、**run 目錄保留**供診斷——不假報「已清除」。

- id 不合法（格式錯／不存在）→ stderr 訊息，exit `1`，**不對任何程序發訊號**。
- exit `1` 的四種答案不在上表——它們不是 run 的狀態，是「這次呼叫沒有答案」：id 不合法；`unknown run id`（含清理殘留已清）；`concurrent poll — retry`（另一個 poll 正在 claim，retry 有意義）；`cannot claim … retrying will not help`（`rename` 因 EPERM 等其他原因失敗，round 4 L2）。
- terminal 狀態的清除以 `rename(run, run.done)` 作原子 claim：兩個 poll 併發只有一個會回 terminal，另一個回 exit `1`（run 已不存在）。

### `--abort <id>`

- 持鎖中 → `SIGTERM` 持鎖者，等 2 s，仍持鎖 → `SIGKILL`。確認鎖釋放後清除 run 目錄（與預設輸出檔），印 `ABORTED`，exit `0`；鎖仍未釋放 → 再進一輪 SIGTERM→SIGKILL（持鎖者若在第一次探測**之後**才拿到鎖，也會被送到訊號，Codex round 4 #10）；兩輪後仍持鎖 → `FAILED worker did not terminate`、exit 2、run 保留。
- 未持鎖（已結束）→ 直接清除（含預設輸出檔），印 `ABORTED`，exit `0`。
- id 不合法 → exit `1`，不發訊號。

## 3. Run id 與狀態目錄

- id：`^[A-Za-z0-9]{32}$`，由 CSPRNG 產生。**`--poll` / `--abort` 只接受 id，不接受路徑。**
- base：`$HOME/.cache/codex-call/runs/`（`0700`）。run 目錄 `<base>/<id>/`（`0700`）含 `meta.json`、`prompt.txt`、`lock`、`status`、`worker.log`。
- **base 硬化**（每次 `--detach`）：`~/.cache/codex-call` 與 `runs` 兩層各自 `lstat`——必須是真目錄（拒 symlink）、owner 必須是當前 uid、權限修正為 `0700`（`createDirectory` 不會修正預先存在的 0755，實測），**`chmod` 失敗也是失敗**（round 4 S2：原本被吞掉，「強制」曾是 best-effort）。任一不符 → detach 同步失敗。硬化**先驗上層再建 `runs/`**，拒絕前不在不受信目標下建任何東西（S4）。硬化只涵蓋這兩層：`~/.cache` 本身（含它是 symlink 到另一顆磁碟這種合法配置）屬 §6 第二列「caller 環境完整性」，run 樹會落在其目標且不受本工具的權限承諾涵蓋（S3）。
- 為什麼不收路徑：round 2 verify（PR #47）證明「接受任意目錄 + 檔案存在性檢查」等於任意 PID kill / `rm -rf` 原語。id 只能解析到 HOME 之下的 0700 目錄，跨使用者偽造面消失。

## 4. 生存與身分（為什麼 PID 重用不會誤殺）

- worker 對 `<run>/lock` 持有 **`fcntl(F_SETLK)` POSIX record lock**，直到程序結束（含被 kill）。
- `--poll` / `--abort` 用 **`F_GETLK`** 判斷：`F_UNLCK` = 已結束；否則 `l_pid` 是**查詢當下**持鎖的程序。
- **run 目錄的回收**：`--detach` 每次啟動前掃 base，刪除 mtime 超過 24 h **且無人持鎖**的 `<id>`／`<id>.done`／`<id>.out.md`。`--abort` 是**盡力而為**的早停路徑（engine step 4 要求 agent 早停時先 abort），agent 被硬殺時不可用，所以 GC 仍是最後防線；被放棄的 run（含 `prompt.txt`，即 artifact 的完整副本）最多存活到下一次 detach。
  發訊號的對象永遠是 `F_GETLK` 回報的 pid，**不從任何檔案讀 pid**——這消滅了「讀到陳舊 pid 檔」這一類誤殺。
- **誠實邊界（PID 重用）**：`F_GETLK` 與 `kill()` 之間仍有微秒級 TOCTOU——持鎖者可能在查詢後、訊號前退出，且該 pid 理論上可被回收。本工具的緩解是**每次發訊號前都重新查詢持鎖者**（`killHolder`），把視窗縮到單一系統呼叫之間；macOS 沒有 pidfd 一類可把查詢與訊號原子綁定的原語，所以這不是「不可能」，是「機率極低且已縮到最小」。
- 實測（macOS 26）：`flock()` 鎖在 `F_GETLK` 下 `l_pid = -1`（BSD 行為），**不可用**；`fcntl` record lock 回報真實 pid。這是選 `fcntl` 的唯一理由。
- 誠實邊界：`fcntl` 鎖在程序關閉**任何**指向該檔的 fd 時釋放。worker 只開一次且不關閉；不得在 worker 內對 `lock` 另開 fd。
- **lock 檔完整性**：`<run>/lock` 以 `O_NOFOLLOW` 開啟，並 `fstat` 驗證它是一般檔案、`st_nlink == 1`、owner 是當前 uid。任一不符 → `--poll`／`--abort` **exit 1、不發訊號、run 原地保留**（不判為終止、不清除——round 4 S1 實測原本把它當「已結束」刪掉 run，把活的 worker 孤兒化，是 lifecycle 的 fail-open）；GC 也跳過它。這三個檢查**排除的是 symlink、hard link 與非一般檔案**，它們**不**建立「這是我們建立的 inode」：`rename()` 保留 inode，把 victim 正持鎖的檔案**搬**進 `<run>/lock` 可讓三個檢查全過，abort 會殺掉它（實測，bats 鎖住這個宣告的邊界）。在「寫得到 base」這個前提下沒有任何檢查能成立——`meta.json` 與 `lock` 同在一個可寫目錄；那需要同 uid 或 HOME 注入，皆在 §6 之外。這三個檢查買到的是消掉最便宜的兩種變體，與一行誠實。
- **worker 不可重放（已完成的 run）**：run 已有 `status` 時，第二個 `--_worker` 直接退出，不重跑 HTTP、不覆寫 status。未完成（無 status）且無人持鎖的 run **可以**被第二個 `--_worker` 接手——那是隱藏旗標，只有同 uid 能碰到（Codex round 4 #13）。

## 5. 期限與清理

- worker **自己**強制 `--max-time`（URLSession timeout + semaphore，既有機制），到期寫 status token **`TIMEOUT`**（其餘失敗寫 `<exit code> <message>`，成功寫 `0`）。逾時的判定依 **(domain, code)**：`codex-call/408`（semaphore 兜底，`max-time + 5 s`）與 `NSURLErrorDomain/-1001`（URLSession 自己的 timer，設在 `max-time`，**比兜底早 5 s、是主要路徑**）都寫 `TIMEOUT`。round 4 L1：只認 408 讓主要路徑寫成 `FAILED -1001`——與 round 3 L3 同型（拿 code 數字當分類鍵），換了一端。poll 比對的是**整個 token**，不是數字前綴——round 3 L3：`NSError code 3`（auth.json 缺 tokens）曾被誤判成可重試的逾時。
- poll 端另有兜底：持鎖超過 `max-time + 60 s` ⇒ `SIGKILL`。兩者都不依賴任何可被竄改的 deadline 檔——期限資訊寫在 `meta.json`，但 meta 損毀時 poll **fail-closed**（視為逾時，kill + TIMEOUT），不會退化成無限 RUNNING。
- `<id>.done` 是 poll 的 claim 中繼目錄（rename 原子 claim）。若某次 poll 在 claim 後崩潰，**claim 超過 60 s**（以 `.done` 的 **ctime** 計——`rename` 更新 ctime、不動 mtime；目錄 mtime 是 worker 最後寫 status 的時間，可能遠早於 claim，Codex round 4 #1）**且仍含 `status`** 的 `.done` 會被下一次 `--poll` / `--abort` 接手完成；不含 `status` 的是清理中斷的殘留，清掉並回「unknown run id」exit 1（與 §2 一致）；60 s 內的視為併發 claim 進行中（exit 1，訊息明說「concurrent」）。claim → 清理只需毫秒，60 s 的門檻不會誤傷活的 claim。
- `status` 由 worker 在**同一程序**寫入；寫失敗 ⇒ 無 status ⇒ poll 回 FAILED。沒有「半截輸出 + 非零退出被當成功」的路徑：DONE 要求 status 為 `0` **且**輸出檔非空。

## 6. 威脅模型

以下是**封閉列舉的三列**（同 uid／caller 環境完整性／跨 uid），**不得依性質相似類推第四列**。round 3 security 的 H1（hard-link lock）從「同 uid」與「跨 uid」之間的縫掉出去，因為第二列當時不存在。（下方的 prompt-injection 段落**不是**第四列，是對緩解措施的說明——round 4 R4-4 指出原本的排版讓讀者數成四列。）

- **同一 uid 的攻擊者在模型之外。** base 是 `0700`，同 uid 本來就能 kill 你的任何程序。
- **`$HOME` 與 base 的完整性是 caller 的責任**：本工具的 **run base** 讀環境變數 `HOME`；**憑證**（`~/.codex/auth.json` 與其 refresh lock）走 passwd db 的家目錄、**不受 `HOME` 影響**（同步路徑的既有行為，§1 不動）——所以「隔離 HOME」隔離的是 run 目錄不是憑證，測試不打線上 API 靠的只有 `--_selftest-*`（round 4 R4-6）；被注入的 HOME 等同同 uid 攻擊。硬化（§3）與 lock 完整性（§4）把「寫得到 base」能造成的傷害縮到「殺自己的 worker」，但不把 HOME 注入納入防禦承諾。**base 硬化的硬失敗是宣告的行為**：`~/.cache/codex-call/` 與 `runs/` 任一層若是 symlink、非目錄、或 owner 不是當前 uid（例如曾以 `sudo` 建立），`--detach` 同步 exit 1 並說明原因；不是 bug，也不會自動修復。
- 跨 uid：`/tmp` 不再涉入（base 在 HOME）；id 不可猜（CSPRNG 32 字元）；poll 不收路徑。

**prompt-injection 鏈（緩解說明，不屬於上面三列）**：artifact → Codex 輸出 → wrapper agent 讀取，是一條 **prompt-injection 鏈**。engine 的「strictly as DATA」與 `DATA_GUARD` 是對同一個 LLM 的自然語言指示，是**緩解、不是安全邊界**——本契約不宣稱已建立隔離。caller 端的硬性規則：poll 用的 id **只能**來自 `--detach` 的 tool output，不得來自任何檔案內容；agent 可執行的命令面由 caller 的 tool 權限決定，本工具不擴大它。round 4 起 engine 的 codex leg 要求 agent 在讀取 Codex 輸出檔**之後**執行一次 `rm -f '<path>'`，早停時執行 `--abort '<id>'`——這擴大的是 **engine 指示的動作面**，不是本工具的權限；兩者的唯一可變部分分別是 `DONE` 印出的路徑與 `--detach` 印出的 id，agent 不得從任何檔案內容取路徑或 id（S5／S9）。codex-call 印到 stderr 的一切（`FAILED` 原因、`worker.log` 尾段）同樣是 DATA（S7）。

## 7. 隱藏旗標（internal，不在穩定性承諾內）

- `--_worker <id>`：由 `--detach` 呼叫。id 不合法或 run 不存在 → exit 1。
- `--_selftest-sleep N` / `--_selftest-fail` / `--_selftest-grace N`：與 `--detach` 並用，worker 以 sleep + 寫檔取代 HTTP（測試 detach / lock / poll / abort 路徑，不發網路）。
- `--selftest-error-extract`（#25，既有）。

## 8. 穩定性承諾

- §1、§2 的旗標名、stdout 格式、exit code、§3 的 id 格式與 base 路徑：**STABLE**。變更需 major bump + migration note。
- §7 隱藏旗標：可在 minor 內變更。
- 消費者釘 SHA（codex-pro）時，本檔的版本欄與 `CHANGELOG.md` 是判斷「要不要 re-vendor」的依據。
