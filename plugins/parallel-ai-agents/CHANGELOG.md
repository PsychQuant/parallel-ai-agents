# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> ⚠ This file was bootstrapped by `changelog-tools:changelog-init` from the
> `plugin.json` description field. Section categorization is best-effort —
> review and refine `Added` / `Changed` / `Fixed` etc. as needed.

## [Unreleased]

## [2.13.1] - 2026-06-01

### Fixed
- **diff 模式第二輪硬化（`--diff` re-audit dogfood 抓到「修正引入的新 bug」）**：上一版的 4 個 HIGH 經 re-audit 確認修好，但其中 `--commits` 的越界 clamp 自己有 off-by-one：
  - **`--commits N` clamp off-by-one**：`N=$TOT` → `HEAD~TOT`（root 的 parent、不存在）→ `git diff` fatal → hard-abort。改成 `N≥TOT` 時對 **empty tree**（`git hash-object -t tree /dev/null`）取 diff，涵蓋含 root 的全部變更、不越界。
  - **`validate_int` 排除 0 / leading-zero**：`^[0-9]+$` → `^[1-9][0-9]*$`（合約是「正整數」，舊版 `--commits 0` 會給假綠燈）。
  - **untracked 加 64KB size cap**（對齊 codex-pro），超大新檔轉 path-only，避免單檔撐爆 prompt；改用 repo-relative path（diff header 一致）。
  - **MODE/REF/N 明確賦值**（Phase 0 判定 lower 成變數，不只留 prose）；`--pr` 加 `--color never`；DIFF_FILE cleanup 改「ensemble 跑完後刪」（**不**用 trap EXIT 提前刪）。

## [2.13.0] - 2026-06-01

### Added
- **`ensemble-code-review` 完整 diff 輸入模式**：除了既有的 `FILE_OR_DIR`，現在能審變更 —— `--diff`（uncommitted）、`--base <ref>`（分支相對 merge-base）、`--commits <N>`、`--since <ref>`、`--pr <N>`（gh pr diff）。對齊 idd-verify 的輸入彈性，但不綁 issue。
  - 純 skill 改動：skill 算出 diff 寫 temp 檔 → 傳 harness `code` profile 的 `diffFile`（早已支援），reviewer/Codex 用 file-read tool 讀 diff，避開 inline escape + prompt 膨脹。
  - path 與 diff flag 互斥；都沒給預設 `--diff`；空 diff 不空跑 ensemble。
  - Backend B（legacy）同步支援：diff 模式把 `{FILE_OR_DIR}` 換成 `$DIFF_FILE`。

## [2.12.0] - 2026-06-01

### Added
- **`general.security-review` 內建 lens**（使用者提供）：LLM 應用安全 —— prompt injection（不可信輸入/RAG/工具回傳能否覆寫 system 指令、越權呼叫工具、外洩 system prompt）、secret 洩漏、不可信內容邊界、工具授權範圍。補上 `code.security` 沒涵蓋的 LLM 專屬面。內建 lens 15 → 16（general 6）。

### Docs
- ensemble-compose SKILL 補明：**devil's-advocate 與 Codex 由 harness 自動加入每個 ensemble**（DA fail-closed、Codex 由 `--codex` 開），不可 `--include`、不在 lens 表/CSV —— 它們本來就在每次 run，不該被當成可挑 lens 放進清單。

## [2.11.0] - 2026-06-01

### Added
- **新內建 `general` profile — 5 個通用軟體品質 lens**（`perf` / `a11y` / `i18n` / `deps-and-portability` / `observability`）。現在 `--include general.perf` 等可跨任何 ensemble 取用，且出現在 `builtin-lenses.csv`（內建 lens 10 → 15）。`deps-and-portability` 是 codex-call dogfood 真用過、抓到 bug 的那個。
- `references/example-lenses.csv` 改為與內建**不重複**的專案型範本（`api-compat` / `migration-safety` / `flaky-tests`），保持「自訂 `--lens-file` 包」的乾淨示範。

### Notes
- 內建只放**廣用、低後悔**的通用 lens；專案/個人特定的 reviewer 角色建議留在你自己的 `--lens-file` 包（user-owned、零 code、零 version bump）。

## [2.10.2] - 2026-06-01

### Added
- **`references/builtin-lenses.csv` — 內建 lens 的 reference catalog**：10 個內建 reviewer lens（lecture 3 / code 3 / academic 4）攤成 `profile,key,focus,needsSrt` 的 CSV，方便一覽、或 copy 到自己的 `--lens-file` 包。
  - **唯讀 reference**：harness runtime 無 FS、讀不到此檔；內建 lens 的真源是 `PROFILES`（code）。編此 CSV 不會改 harness。
  - **`references/regen-builtin-lenses.sh`**：從 `PROFILES` 重生此 CSV（砍 Orchestration 段、`export {PROFILES}`、用 JS engine eval 而非 regex parse）。idempotent，改 PROFILES 後跑它同步。
  - ensemble-compose SKILL 內建 lens 表加指引指向此檔。

## [2.10.1] - 2026-06-01

### Fixed
- **`bin/codex-call` 4 個 MEDIUM bug（ensemble-compose dogfood 抓到的剩餘項）**：
  - **`jwtExp` `exp as? Int` → `(... as? NSNumber)?.intValue`**：`exp` 是 NumericDate，JSONSerialization 可能給 Double，`as? Int` 會失敗 → 有效 token 讀成 exp=0 → 每次呼叫被當過期強制 refresh。改 NSNumber 解析（parse 失敗仍回 0，保守地強制 refresh）。
  - **`saveAuthRaw` umask 窗**：chmod-after-write 留下 staging temp 為 umask-default（常 0644 group/other-readable）的窗。改寫前 `umask(0o077)`（defer 還原），含 `.atomic` staging 都 ≤0600。
  - **rotating refresh_token race + `now` TOCTOU**：lock 後 re-read 卻沿用 pre-lock 的 `refresh`／`now`。flock 久等後，pre-lock `now` 讓 freshness recheck 偏樂觀（漏該 refresh），pre-lock `refresh` 可能已被並行 process rotate（single-use → 失敗）。改 re-read 後重抓 `nowLocked` 與 `refreshNow`。
  - **`.urlQueryAllowed` → 自訂 unreserved CharacterSet**：form body 用 `.urlQueryAllowed` 不轉義 `+ & = /`，refresh_token 含這些字會被伺服器解錯（`+`→空格）或破壞欄位邊界（參數污染）。改只允許 RFC 3986 unreserved。
  - e2e：CLT swift 編譯 4 處 + 真跑（jwtExp NSNumber 每次跑、request 成功）。

## [2.10.0] - 2026-06-01

### Added
- **`/ensemble-compose --lens-file <csv>` — 可重用 lens 包**：把自訂 reviewer 角色維護成 CSV（`key,focus,needsSrt`），一個檔一包（`frontend-lenses.csv`、`security-audit.csv`…），skill 讀進來轉成 `customLenses`。
  - 純 skill 改動（harness 的 `customLenses` 已支援，無需動 JS）；**CSV 由 skill 讀（主 session 有 Read），不是 harness（runtime 無 FS）**。
  - skill 必用 **python3 `csv` 模組**解析（focus 含逗號/中文標點，naive split 會切爛）—— recipe 內建於 SKILL.md。
  - `references/example-lenses.csv` 範本（perf / a11y / i18n / deps-and-portability / observability）。
  - 定位：CSV 是**使用者擴充包**入口，不是把穩定的內建 lens 搬出去。

## [2.9.1] - 2026-06-01

### Fixed
- **`bin/codex-call` 兩個 HIGH bug（由 `/ensemble-compose` dogfood 審 codex-call 本身抓到）**：
  - **empty-output → exit 0**：Codex stream 以 200 完成但無 text delta（只有 reasoning、或首個 delta 前斷流）時，原會寫**空檔 + exit 0**，被 ensemble 誤讀成「Codex reviewer 跑完無發現 = PASS」（偽造贊成票）。現在空輸出 fail-closed：throw（exit 非 0 + 明確訊息），不寫空檔。
  - **`#!/usr/bin/env swift` → `#!/usr/bin/swift`**：env shebang 解到 PATH 第一個 swift（這台機器是 swiftly 6.2.4），與 CLAUDE.md 宣稱的「Xcode CLT 內建 swift」不符、破壞確定性。釘 `/usr/bin/swift`（CLT，本機 6.3.2）後文件與實際一致。CLAUDE.md 同步註明不用 env 的理由。

## [2.9.0] - 2026-06-01

### Added
- **`/ensemble-compose` — 自由組合 ensemble 審閱（#1 的「自由組合 agents」原始構想落地）**：跨 profile 挑既有 reviewer lens、或在呼叫時自訂全新 reviewer 角色，組成一次性 ensemble。
- **harness composition engine**：
  - **`includeLenses`**（跨 profile 拉 lens，如 `["code.security", "academic.methodology"]`）
  - **`customLenses`**（呼叫時自訂 `[{key, focus, needsSrt?}]` reviewer 角色）
  - **`profile: "custom"`**（無內建 lens，全靠 include/custom 組）
  - **`maxAgents`**（agent 上限可調，硬上限 30）+ `daFocus` / `codexInstructions` / `codexMaxTime` args override
  - 組裝順序 base → include → custom、**key 去重 first-wins**；**雙重成本封頂**（先砍 lens 數到 `maxAgents − codex − DA`，replicas 再依剩餘 budget clamp）—— 組合自由但成本始終有 ceiling。

## [2.8.0] - 2026-06-01

### Added
- **Workflow backend Phase 3 — `ensemble-academic-review`（完成三 skill 全轉，#1）**：harness 加 `academic` profile（methodology / writing / reference-verifier / number-verifier + devil's-advocate + Codex），`ensemble-academic-review` 改 dual-backend。**workflow = 「一輪 ensemble」inner primitive**；mix / hybrid / `--auto-iterate` 多輪迴圈、verdict parse、apply-HIGH-fix、git commit per round、prior-slicing **全留 skill 側**（每輪呼叫 Backend A 一次）。
  - **reference-verifier**：harness 內用 **ToolSearch 取 che-zotero-mcp 工具**逐筆查文獻、抓幻覺文獻（workflow agents 可達 session MCP）。
  - **number-verifier**：用 **Bash 跑 Rscript / python** 從 ground-truth artifact 重算、抓幻覺數字。
  - Codex `--max-time 900`（論文較長，較 code 的 600 長）。
- **per-lens `priors` map**（取代單一 `priorBlock`）：skill 用「放不放某 lens 進 map」控制 hybrid 資訊不對稱 —— DA 收 `priors.da`（全部前輪）、reference-verifier 收自己的 watch-list，methodology/writing/number-verifier/codex 收不到任何前輪。機制留 harness、策略留 skill。
- **`disableLenses` arg**：對應 academic 的 `--no-numeric`（`["number-verifier"]`）/ `--no-references`（`["reference-verifier"]`）；fail-safe：全關退回全集。
- **`profile.codexMaxTime`**：Codex max-time 改 per-profile（academic 900 / 其餘 600）。

## [2.7.0] - 2026-06-01

### Added
- **Workflow backend Phase 2 — `ensemble-code-review` (#1)**：harness 新增 `code` profile（architecture / correctness / security + devil's-advocate），`ensemble-code-review` 改 dual-backend（workflow 預設 + legacy TeamCreate+Codex fallback）。CLI 與 Phase 4 報表契約不變。
  - **Codex 作為 barrier 內成員**：`codexEnabled: true` 時，Codex（gpt-5.5）是 Phase-1 barrier 的第 4 個 agent，shell 出去呼 `bin/codex-call`（**絕不** `codex exec`），fail-soft（timeout/error 只回 1 個 INFO，不阻擋 Claude-lens verdict）。跨模型獨立性由 codexPrompt 保證（不提及 Claude reviewers）。

### Changed
- **`codexPrompt` 改用絕對路徑 `args.codexCallPath`**（skill 傳 `${CLAUDE_PLUGIN_ROOT}/bin/codex-call`）取代裸 `codex-call`：workflow agent 的 shell PATH 是 install-time version-pinned 注入、可能 stale/不存在，絕對路徑消除此脆弱性（bare `codex-call` 僅 fallback）。

### Fixed
- **harness self-review 硬化**（Phase 2 dogfood 用 `code` profile 自審 harness 時，由 correctness/security lens 抓到）：
  - **empty-lenses guard**：若 `PROFILES` 出現 lenses 為空的 profile，原 `budgetForLenses / profile.lenses.length` 會 divide-by-zero → `maxReplicas=Infinity`（繞過 `MAX_AGENTS`）、fan-out 0 reviewer、fail-closed 迴圈空轉 → **false PASS**。現在 unknown-profile guard 一併攔截 empty/malformed lenses，bail with HIGH integrity finding。
  - **`SENTINEL_RE` 標籤類別 `[A-Z_]` → `[^>]`**：digit/space 等 sentinel-shaped 變體一併中和，符合「中和每個已知 sentinel token」原意（原窄類別讓 forge-shaped 變體漏網；非可 forge 真 boundary，但屬 defense-in-depth gap）。

## [2.6.0] - 2026-06-01

### Added
- **Workflow-tool backend for ensemble review (#1)** — 新增共用 harness `workflows/ensemble-workflow.js`，把 ensemble 審閱改用 Claude Code `Workflow` tool（dynamic workflows）編排，鏡像 `issue-driven-development` 的 idd-verify dynamic-workflow backend。
  - **dual-backend（加法、不破壞）**：`Workflow` tool 可用時走 workflow path，否則 capability-gate fallback 到既有 TeamCreate fan-out。findings 形狀與 Phase 4 報表契約不變。
  - **「大量 agents」**：reviewer 數量改為 data-driven（profile `lenses` × `args.replicas` 旋鈕），自動封頂 `MAX_AGENTS=16`，跨 replica 由 `mergeDedup` 去重強化共識訊號。
  - **Phase 1 範圍**：先轉 `ensemble-lecture-review`（最低風險：無 Codex / 無 MCP / 單輪）。`ensemble-code-review`（Phase 2，加 Codex-via-`codex-call`）、`ensemble-academic-review`（Phase 3，僅單輪進 workflow）後續。
- `references/ensemble-findings-schema.json` — harness 內嵌 `FINDINGS_SCHEMA` literal 的 canonical mirror（runtime 無 FS，schema 必須內嵌，此檔為人類可讀來源、防 drift）。

### Changed
- **devil's-advocate 行為（僅 workflow backend）**：從 live `TeamCreate`+`SendMessage` 即時拷問改為 downstream node 讀同儕**完稿** findings。更穩（消滅 idle-teammate / SendMessage 不觸發的失敗模式），但 DA 看的是定稿而非即時對話。legacy backend 行為不變。

## [2.3.0] - 2026-05-07

### Added
- **`--auto-iterate` mode for `/ensemble-academic-review` (#34)**: round → fix → round 自治收斂迴圈,內部沿用 mix N 的 alternating independent/hybrid pattern,但加上每輪結束的:
  - **Verdict parsing**: Codex prompt 強制要求 `<verdict>PERMANENT_CONVERGENCE | CONVERGED | NEEDS_ITER_N</verdict>` 結構化 tag,skill 用 regex 解析,不靠語意判斷
  - **HIGH-only fix application**: 從 `review-round-{N}.md` 解 HIGH-severity findings 自動套到 working tree;ambiguous fix skip + log to `skipped_fixes.log`
  - **Auto-commit per round**: `iter-{N}: apply HIGH fixes from ensemble round {N}`,user 可隨時 `git revert iter-{N}`
  - **Rotate-focus heuristic**: 連續 K=3 同 focus CONVERGED 才 switch (focus pool: method-section / proofs / typography / cross-references / boundary-cases)
  - **Stop conditions**: 達 `--converge-on` (default `PERMANENT_CONVERGENCE`) 或 `--max-rounds` (default 12, max 30)
- **8 cumulative methodological lessons** in SKILL.md tail — 來自實戰 23-round campaign (`PsychQuantHsu/psychophysic_representations_manuscript/docs/rounds/INDEX.md`),作為 rare-audited section / hypothesis-inheritance / verdict-tier 等坑的 reference

### Notes
- Self-contained Bash while + state machine,**不**依賴 ralph-loop 的 Stop-hook 機制
- 與 ralph-loop 同時跑時 skill 偵測並警告(雙 Stop-hook 衝突風險)
- Spec-only PR — agent 讀 SKILL.md 後在 user 顯式傳 `--auto-iterate` 才觸發,既有 mode 行為不變

## [2.2.0] - 2026-05-03

### Added
- **`number-verifier` reviewer**: 5th ensemble reviewer that checks every
  number in a doc against ground-truth artifacts (`.rds`, `.npz`, `.csv`,
  R/Python scripts). Catches hallucinated numbers that other reviewers
  miss. Verified by ASSG3 review pipeline (Canadian GDP ARIMA + Australian
  yields VAR/VECM) where it caught wrong y_T, drift omission, Ljung-Box
  fitdf errors, and ARIMA(1,1,1) reference p-value mistakes across 4 rounds.
- `--no-numeric` flag to disable number-verifier (pure theoretical papers)
- `--no-references` flag to disable reference-verifier (technical notes)
- Auto-detect: number-verifier enables when `analysis/`, `*.rds`, `*.ipynb`,
  `*.Rmd`, or `data/*.csv` are present near the doc
- Hybrid mode: `prior_number_issues` watch list passed to number-verifier
  in subsequent rounds (analogous to `prior_ref_issues`)

### Changed
- Reviewer count: 4 → 5 Claude teammates + Codex
- Tool-call rule: "5 calls in one message" → "N+1 calls (N ∈ {3,4,5})"
- Ironclad rules: HIGH-priority bucket now includes hallucinated numbers
  alongside hallucinated references

## [2.1.1] - (date unknown — please fill in)

### Changed
- 平行派發任務給多個 AI agent（Claude + Codex），獨立執行後交叉比對結果
