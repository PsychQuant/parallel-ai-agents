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
| `codex-profile.bats` | repo root `.codex-pro/profile.yaml`（#48 專案層 codex-pro profile pin）—— 用 `references/codex-governance.md` 同組正規式鎖住解析後字面、重複 key、git 追蹤；fixture 三層優先序（不依賴 codex-pro cache）；形狀驗證拒絕注入。與 governance 文件是連動點（codex-pro#18 / #19）|
| `codex-call-detach.bats` | `../bin/codex-call` 的背景模式（`--detach`／`--poll`／`--abort`／`--force-reap`；#37）—— **macOS-only**、95 case；全部走同一條 detach／lock／claim／poll 路徑，只用 `--_selftest-*` 旗標把 HTTP 換成 sleep＋寫檔（任何沒帶 selftest 旗標的 detach 都會真的發 HTTPS）。**不可與另一組 bats 在同一 checkout 並行**（`own_workers` 斷言是 checkout 級） |
| `lint-bats.sh` | 護欄：bats 檔內不得有裸 `!` 斷言（errexit 不觸發，斷言變 no-op；round 6 RC11）。`--selftest` 對 `fixtures/lint-bats-bad.bats` 必須拒絕 |
| `lint-changelog-counts.sh` | 護欄：CHANGELOG 每個「N 個 case（`grep -c "^@test" <file>`）」宣稱，N 必須等於那條命令此刻的輸出（RC13 第五度復發後機械化，#37 round 10）。`--selftest` 對 `fixtures/changelog-count-bad.md` 拒絕 |
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

# 一鍵：shellcheck + py_compile + 三支 lint（各含 selftest）+ bats + node
./test/run.sh

# 或分開
shellcheck bin/pai-build-diff
bats test/
```

CI（`.github/workflows/test.yml`）在每次 push / PR 自動跑：`shellcheck-bats` 與 `macos-swift-bats` 兩個 job 涵蓋上面這一組；另有 `manifests-and-lens-pack` job 跑 `plugins/pai-lenses/scripts/` 的 python 測試、靶清單檢查與 validator 本體 —— `run.sh` 末段也跑同一組，所以本機一鍵與 CI 對得上（完整 mutation 量測仍是手動：`python3 scripts/mutation_check.py`）。

## 加測試的原則

改 `bin/pai-build-diff` 的行為 → **先在 `pai-build-diff.bats` 加一個會 fail 的 case（RED），再改 script 讓它 pass（GREEN）**。不要在 `SKILL.md` inline 重寫 diff 邏輯 —— script 是單一真相源，SKILL.md 只呼叫它。
