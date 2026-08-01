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
| `pai-parse-verdict.bats` | `../bin/pai-parse-verdict`（ensemble-academic-review `--auto-iterate` 的 verdict tag 解析器）|
| `pai-iterate-decide.test.mjs` | `../bin/pai-iterate-decide`（`--auto-iterate` 主迴圈的純狀態機：halt / 套 fix / mode 交替 / focus-rotation）|
| `pai-iter-commit.bats` | `../bin/pai-iter-commit`（`--auto-iterate` 的 per-round checkpoint commit + 空輪防護）|
| `pai-eval-grade.test.mjs` | `../bin/pai-eval-grade`（eval 評分器：detect 容差聚合 / fix 修稿驗證 —— eval 裡唯一確定性、可單元測的部分）|
| `codex-call-error-extract.bats` | `../bin/codex-call` 的 SSE error 訊息提取（`--selftest-error-extract`）—— **macOS-only**（codex-call 是 `#!/usr/bin/swift` script），在非 macOS 環境自我 skip |

`pai-parse-lens-csv.bats` 涵蓋：含逗號/引號/換行的 focus（csv 模組、不被切爛）、needsSrt 變體、空欄跳過、**BOM 不丟列（utf-8-sig regression）**、CRLF、缺檔/缺欄。
`codex-call-error-extract.bats` 的 SUT 是 macOS-only 的 Swift script，故在 ubuntu job 上會**自我 skip**；CI 另有 `macos-swift-bats` job 確保它真的被執行（只加 skip guard 而不加 job，錨點會變成永遠 skip 的 vacuous green —— #25 verify）。

`pai-parse-verdict.bats` 涵蓋：**last-match（防 echoed instruction 範例造成假收斂的 regression）**、`{N}` placeholder 不匹配、嚴格大寫、查無 tag → 非零、stdin/file。

`pai-build-diff.bats` 涵蓋：5 種模式（`--diff`/`--base`/`--since`/`--commits`/`--pr`）、退出碼契約（0 有 diff／3 無變更／1 錯誤）、ref/N 驗證（injection、dashed-ref、0/leading-zero、位數溢位）、untracked 安全（symlink no-follow、FIFO no-hang、換行檔名 C-quote）、empty-tree base、未知 mode 的多位元組 regression。

`ensemble-workflow.test.mjs` 涵蓋 harness 的 **fail-closed 不變式**：unknown profile、空 lens 組合、core lens 被 skip（null）/ error（throw）/ devil's-advocate 缺席 → 一律 HIGH integrity（不可假 PASS）、codex 缺席 → INFO 非阻塞、mergeDedup 對 malformed severity 穩健。把「null-skip fail-open」的修正鎖死成 regression。（純 node，無框架；把 workflow script body 包成可 import 的 async 函式、注入 mock globals 實跑。）

## 跑法

```bash
# 前置（一次性）
brew install bats-core shellcheck

# 一鍵：shellcheck + bats
./test/run.sh

# 或分開
shellcheck bin/pai-build-diff
bats test/
```

CI（`.github/workflows/test.yml`）在每次 push / PR 自動跑同一組。

## 加測試的原則

改 `bin/pai-build-diff` 的行為 → **先在 `pai-build-diff.bats` 加一個會 fail 的 case（RED），再改 script 讓它 pass（GREEN）**。不要在 `SKILL.md` inline 重寫 diff 邏輯 —— script 是單一真相源，SKILL.md 只呼叫它。
