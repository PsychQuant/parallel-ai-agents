---
name: ensemble-code-review
description: |
  Claude + Codex 雙 AI 獨立審閱程式碼，交叉比對找共識和盲點。
  4 Claude teammates（architecture, correctness, security, devils-advocate）+ Codex GPT-5.5 獨立審一遍，最後合成比較表。
  可審：檔案/目錄現狀、uncommitted diff（--diff）、分支比較（--base <ref>）、最近 N 個 commit（--commits N）、--since <ref>、PR（--pr N）。
  Use when: 程式碼、技術文件、設計文件發布前需要嚴格審閱；或 commit / PR 前審變更。
argument-hint: "[FILE_OR_DIR | --diff | --base <ref> | --commits <N> | --since <ref> | --pr <N>] [--focus '...'] [--replicas N] e.g. 'src/auth/', '--diff', '--base main', '--pr 123'"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - Agent
  - TeamCreate
  - SendMessage
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - AskUserQuestion
---

# /ensemble-review — Orchestrated Team + Codex 交叉審閱

4 個 Claude teammates（orchestrated team）+ 1 個 Codex（gpt-5.5）各自獨立審閱，合成比較表找出共識和盲點。

> **原理同 Ensemble OCR**：不同模型、不同角色的錯誤模式不重疊。4 個 Claude 以不同專業角度審閱且互相挑戰，Codex 提供跨模型盲驗。

## 審閱架構

```
/ensemble-review FILE_OR_DIR
│
├── Claude Team（4 teammates，互相挑戰）
│   ├── architecture — 設計模式、API 用法、依賴關係、全局合理性
│   ├── correctness — 邏輯正確性、bug、edge case、型別安全
│   ├── security — injection、secrets、權限、輸入驗證（攻擊者視角）
│   └── devils-advocate — 讀前 3 人結論，反駁「通過」判斷
│
└── Codex（gpt-5.5，完全獨立 process，跨模型盲驗）

→ 5 份 findings 合併去重 → 比較表
```

**為什麼 5 個？**
- 4 個 Claude teammates 在同一個 team 裡**互相挑戰**（不是各自獨立報告）
- Devil's Advocate 的工作是**試著證明其他 3 個的通過判斷是錯的**
- Codex 是完全不同的模型家族（gpt-5.5），提供**跨模型盲驗**

## 執行流程

### Phase 0: 解析輸入（target 擇一）

審閱 target 分兩類，**擇一**：

**A. 路徑**（審檔案/目錄現狀）
```
  FILE_OR_DIR — 檔案或目錄路徑（目錄 = 讀所有原始碼檔當審閱範圍）
```

**B. diff**（審變更）— 擇一 flag：
```
  --diff           審 uncommitted 變更        → git diff HEAD
  --base <ref>     審本分支相對 <ref> 的變更   → git diff <ref>...HEAD（merge-base diff）
  --commits <N>    審最近 N 個 commit          → git diff HEAD~N..HEAD
  --since <ref>    審 <ref> 之後的變更         → git diff <ref>..HEAD
  --pr <N>         審 PR                      → gh pr diff <N>
```

共用 flag：
```
  --focus '...'    審閱重點（可選）
  --replicas N     每個 lens 複製 N 份（可選，預設 1；harness 封頂 MAX_AGENTS=16）
```

**解析規則**：
- 給了 path → 路徑模式。給了 B 類任一 flag → diff 模式。**path 與 diff flag 互斥**（同時給則問使用者）。
- **都沒給**：在 git repo 內 → 預設 `--diff`（審 uncommitted）；**不在 git repo、或工作區乾淨無變更** → 問使用者要審哪個路徑或 ref（不要落入無 path 又無 diff 的死路）。
- **安全前提（鐵律，見下）**：使用者給的 `<ref>` 一律先 `git rev-parse --verify` 驗證、`<N>` 一律驗證為正整數，**絕不把未驗證的 token 內插進指令**；所有 git/gh 命令**檢查 exit code**，非 0 報 stderr 並停。

### Phase 1: 取得審閱內容 + 準備 context

**路徑模式**：讀取目標（目錄則列所有原始碼檔路徑 + 內容摘要）。

**diff 模式**：依 Phase 0 的來源取 diff，**寫到 temp 檔**（大 diff 不塞 inline args —— Workflow 會把 args JSON-stringify；reviewer 用 file-read tool 讀，避開 escape 地獄 + prompt 膨脹）：

```bash
# Phase 0 已把判定 lower 成變數（缺值→pai-build-diff 自己報錯）：
#   --diff               → MODE=--diff（無 ARG）
#   --base|--since <ref> → MODE=--base|--since、ARG=<ref>
#   --commits|--pr <N>   → MODE=--commits|--pr、ARG=<N>
ARG="${ARG:-}"
DIFF_FILE="$(mktemp -t pai-codereview-diff.XXXXXX)"   # ⚠ skill 自管：async reviewer 讀這個檔；Phase 4.5 才 rm（含 changed-line 祕密）

# diff 建構統一交給 version-pinned 的 bin/pai-build-diff —— 3 輪硬化 + bats 覆蓋的「單一真相源」。
# 絕對路徑不賭 PATH（同 codex-call 理由）。退出碼：0=有 diff／3=無變更（良性）／其它=錯誤。
bash "${CLAUDE_PLUGIN_ROOT}/bin/pai-build-diff" "$MODE" ${ARG:+"$ARG"} >"$DIFF_FILE"; rc=$?
case "$rc" in
  0) : ;;                                                      # 有變更 → 往下派 ensemble
  3) rm -f "$DIFF_FILE"; echo "無變更可審 → 停（不空跑 ensemble）"; exit 0 ;;
  *) rm -f "$DIFF_FILE"; echo "diff 建構失敗（見上方 stderr）→ 停"; exit 1 ;;
esac
```

> `pai-build-diff` 封裝了全部硬化：ref/N 驗證（防 command injection + dashed-ref）、untracked 新檔的 symlink/FIFO/換行檔名安全處理、`--commits N≥TOT` 用 empty-tree base、所有 git/gh exit-code 檢查、空判定。**要改 diff 邏輯就改 `bin/pai-build-diff` 並更新 `test/pai-build-diff.bats`，不要在這裡重寫 inline**（單一真相源）。契約細節見該 script 與其 25 個 bats 測試。

> **PR mode 的 context 陷阱**：`gh pr diff` 取的是**遠端 PR** 的 diff，但 reviewer 用 Read 讀到的「周邊原始碼」是**本地工作樹**（可能停在別的分支）。所以 `--pr` 模式下，contextBlock 要明示「周邊以 diff 內 hunk context 為準，本地 Read 未必對應 PR 的版本」；要精確就先 `gh pr checkout <N>`（會動工作樹，多數情況不值得）。

自動判斷審閱重點（兩模式共用）：

| 內容 | 審閱重點 |
|------|---------|
| `.md` blog/文章 | 技術準確性、邏輯一致性、聲明可驗證性 |
| `.md` 設計文件 | 架構合理性、邊界情況、可行性、遺漏 |
| 程式碼（`.swift`/`.py`/`.ts`…） | bug、安全漏洞、效能、API 用法、edge case |
| 目錄 / diff | 架構、死碼、API 一致性、依賴管理、**變更的影響面與回歸風險** |

準備 `contextBlock`：focus 指示 + 內容類型 emphasis +（diff 模式時）一句「以下是 diff；需要時用 Read 工具看周邊檔案補 context」。

### Phase 2: 派發審閱（雙 backend）

先選 backend：

- **`Workflow` tool 可用（預設、推薦）** → Backend A（workflow）。可大量 agent fan-out，Codex 是 barrier 內一個成員。
- **`Workflow` tool 不存在**（舊版 Claude Code）→ fallback 到 Backend B（legacy TeamCreate + Codex Bash，下方 2a/2b）。

兩個 backend 產出**相同的 findings 形狀**，Phase 4 報表完全一致。

#### Backend A — Workflow（預設）

1. 解析 harness 絕對路徑：`${CLAUDE_PLUGIN_ROOT}/workflows/ensemble-workflow.js`。
2. 解析 wrapper 絕對路徑：`${CLAUDE_PLUGIN_ROOT}/bin/codex-call`（**用絕對路徑**，不賭 workflow agent shell 的 PATH —— install-time PATH 注入是 version-pinned、可能 stale/不存在）。
3. 解析 dispatch model（#20）：`PAI_AGENT_MODEL` 未設 → `opus`；設了但不在 `sonnet|opus|haiku|fable` → **abort with usage error**（fail-loud，不靜默換模型；engine 對顯式非法值亦會於派發前 throw 作第二層）。解析值經 `args.agentModel` 傳入。接著呼叫 `Workflow` tool，傳 `scriptPath`（harness 絕對路徑）+ `args`：

   ```json
   {
     "profile": "code",
     "agentModel": "<PAI_AGENT_MODEL 解析值（預設 opus，#20）>",
     "file": "<路徑模式：FILE_OR_DIR 絕對路徑>",
     "diffFile": "<diff 模式：Phase 1 的 $DIFF_FILE 絕對路徑>",
     "contextBlock": "<focus + 內容類型 emphasis（見 Phase 1 表）>",
     "codexEnabled": true,
     "codexCallPath": "${CLAUDE_PLUGIN_ROOT}/bin/codex-call",
     "replicas": 1
   }
   ```

   - **path 模式傳 `file`、diff 模式傳 `diffFile`（擇一，不要兩個都傳）**。harness 的 `code` lens 與 Codex 都會用 file-read tool 讀 `diffFile` 並當 diff 審；`--replicas` 帶入時覆蓋預設 1。

   - `codexEnabled: true` → Codex（gpt-5.5）作為 barrier 內第 4 個 agent，shell 出去呼 `codexCallPath`（**絕不** `codex exec`），fail-soft：timeout/error 只回 1 個 INFO finding（不阻擋 Claude-lens verdict）。
   - `replicas` 預設 1（3 Claude lens + Codex + DA = 5，與 legacy 等價）。調高即大量 fan-out；harness 封頂 `MAX_AGENTS=16`（建議 Codex replica ≤2，fast = 2.5× credit）。
4. Workflow 回 `{ findings, verdict, stats }`，`findings` 已 merge+dedup（severity 高者勝、跨 lens 不誤併）。Codex 的 finding `lens="codex"`、DA 的 `lens="devils-advocate"`。直接進 Phase 4 render，**不要**自己再 dedup。

> 跨模型獨立性由 harness 保證：codexPrompt **不**提及 Claude reviewers、**不**餵 Codex 他們的 findings；DA 則**會**讀 Claude reviewers 的完稿 findings（兩者 prompt builder 分開）。DA 為 downstream node（讀完稿，非 live SendMessage）。

#### Backend B — Legacy TeamCreate + Codex Bash（fallback）

> 每個 spawn 的 Agent 都帶顯式 `model: $PAI_AGENT_MODEL`（預設 `opus`，#20——不繼承 session 主迴圈模型）。

> **diff 模式時**（不只換路徑字串）：① 把下方 prompt 的 `審閱範圍：{FILE_OR_DIR}` 換成 `審閱範圍（diff）：$DIFF_FILE`；② **在每個 reviewer prompt 開頭加一句框架引導**：「以下是一份 diff，只審變更行、評估**變更的影響面與回歸風險**；需要時自行 Read 周邊原始碼補 context」——否則 teammate 會用『審整棵原始碼樹』的 mental model 看 diff（如 architecture 的『檔案組織/死碼』對著一份 diff 語意走樣）；③ TeamCreate 的 `description` 不要塞 temp 檔路徑，用「diff review」之類描述。devil's-advocate 走 SendMessage 不受影響。

**CRITICAL: 所有 tool calls（TeamCreate + Codex Bash）必須在同一個 message 送出。不可分步驟。**

**CRITICAL: Teammates 必須用 `subagent_type: "general-purpose"`。不可用 `Explore`（Explore 不會主動 SendMessage 回報結果，會直接 idle）。**

#### 2a. Claude Team（4 reviewers）

用 TeamCreate 建立 team，然後用 Agent 啟動 4 個 teammates：

```
TeamCreate:
  name: "ensemble-review-{timestamp}"
  description: "Ensemble review for {FILE_OR_DIR}"
```

然後在**同一個 message** 啟動 4 個 Agent + 1 個 Codex Bash（共 5 個 tool calls）：

**Agent 1: architecture**
```
Agent:
  name: "architecture"
  subagent_type: "general-purpose"
  team_name: "ensemble-review-{timestamp}"
  subagent_type: "general-purpose"
  prompt: |
    你是 Architecture Reviewer。
    審閱範圍：{FILE_OR_DIR}
    {context}

    你的任務：
    1. 設計模式是否正確（protocol 使用、抽象層級）
    2. API 用法是否符合上游框架的推薦方式
    3. 依賴關係是否合理（有沒有多餘或缺少的）
    4. 檔案組織是否清晰
    5. 有沒有死碼或重複實作

    {focus_instruction}

    用 Read/Grep/Glob 工具實際去看相關檔案確認。
    用中文逐點列出問題和建議。每個問題標注嚴重性（HIGH/MEDIUM/LOW）。
    最後給整體評價（一段話）。
```

**Agent 2: correctness**
```
Agent:
  name: "correctness"
  subagent_type: "general-purpose"
  team_name: "ensemble-review-{timestamp}"
  subagent_type: "general-purpose"
  prompt: |
    你是 Correctness Reviewer。
    審閱範圍：{FILE_OR_DIR}
    {context}

    你的任務：
    1. 邏輯正確性 — 有沒有 bug
    2. Edge cases — null、empty、boundary values
    3. 型別安全 — 隱式轉換、optional handling
    4. 控制流程 — if/else 覆蓋、switch fall-through
    5. 錯誤處理 — 有沒有漏接的 error

    {focus_instruction}

    用 Read 工具查看完整函數上下文。
    用中文逐點列出問題和建議。每個問題標注嚴重性（HIGH/MEDIUM/LOW）。
    最後給整體評價（一段話）。
```

**Agent 3: security**
```
Agent:
  name: "security"
  subagent_type: "general-purpose"
  team_name: "ensemble-review-{timestamp}"
  subagent_type: "general-purpose"
  prompt: |
    你是 Security Reviewer，以攻擊者視角審閱。
    審閱範圍：{FILE_OR_DIR}
    {context}

    你的任務：
    1. Injection 風險（SQL、command、path traversal）
    2. Hardcoded secrets（API keys、passwords、tokens）
    3. 權限檢查（有沒有繞過的可能）
    4. 輸入驗證（external data 是否被信任）
    5. 敏感資訊洩漏（error message、log）

    {focus_instruction}

    用 Grep 搜尋可疑模式（hardcoded strings、eval、exec 等）。
    用中文逐點列出問題和建議。每個問題標注嚴重性（HIGH/MEDIUM/LOW）。
    最後給整體評價（一段話）。
```

**Agent 4: devils-advocate**
```
Agent:
  name: "devils-advocate"
  subagent_type: "general-purpose"
  team_name: "ensemble-review-{timestamp}"
  subagent_type: "general-purpose"
  prompt: |
    你是 Devil's Advocate。
    審閱範圍：{FILE_OR_DIR}
    {context}

    你的任務：等其他 3 個 reviewer（architecture、correctness、security）完成後，
    用 SendMessage 詢問他們的結論，然後**試著反駁每一個「通過」或「LOW」的判斷**。

    步驟：
    1. 用 SendMessage 分別問 architecture、correctness、security 他們的 findings
    2. 對每個「通過」的判斷，找理由說它其實有問題
    3. 對每個「LOW」的判斷，論證為什麼應該是 MEDIUM 或 HIGH
    4. 如果你找不到反駁的理由，才承認確實通過

    這是對抗性驗證 — 你的存在是為了防止群體盲點。
    用中文輸出你的反駁結果。
```

#### 2b. Codex（背景執行 — 直接 HTTP，繞過 codex CLI subprocess）

```bash
codex-call \
  --output "{output_file}" \
  --model gpt-5.5 \
  --effort xhigh \
  --service-tier fast \
  --max-time 600 \
  --instructions "你是嚴謹的程式碼審閱者，用中文輸出。" << 'EOF'
{codex_prompt}
EOF
```

> **為什麼不用 `codex exec`**：subprocess 偶爾會 hang（stdin/stdout pipe 互鎖、tty 問題），等 10 分鐘 timeout 才能繼續。`codex-call` 是 plugin 自帶 wrapper（`bin/codex-call`，Swift script，安裝時自動加入 PATH），直接 HTTP POST 到 `chatgpt.com/backend-api/codex/responses`，仍走你的 ChatGPT 訂閱 OAuth — 但 `--max-time` 是硬性保證，不會 hang。
>
> **Fast mode**：傳 `--service-tier fast`，wrapper 內部會翻譯成 backend 接受的 `priority`（codex CLI 內部也是這樣翻譯）。Fast = 1.5× 速度、2.5× credit（gpt-5.5）；ensemble 場景值得，因為 user 在等。
>
> **OAuth token**：wrapper 自動讀 `~/.codex/auth.json`（codex CLI 的同一份），到期前 5 分鐘自動 refresh，用 file lock 避免 ensemble 平行 race。

Codex prompt 應包含：
- 審閱範圍和 focus
- 要求逐點分析，標注嚴重性
- 用中文回答
- **不提及 Claude team 的存在**（確保獨立性）

### Phase 3: 收集結果

1. 等待 4 個 Claude teammates 完成（透過自動訊息通知）
2. 等待 Codex 完成（輪詢 status）
3. 如果 Codex 失敗或超時（>10 分鐘），跳過，標注「Codex 不可用」

`codex-call` 完成後輸出會寫入 `--output` 指定的檔案，直接用 Read 讀取即可。

### Phase 4: 合併去重 + 交叉比對

- **Backend A（workflow）**：`findings` 已由 harness merge+dedup（severity 高者勝）。主 session 依 `lens` 欄分組 render 下方各表（共識 = 同一問題多 lens／含 codex；僅 Codex = `lens="codex"`；DA = `lens="devils-advocate"`）。**不要**再跑一次 dedup。
- **Backend B（legacy）**：主 session Claude 讀取 4 teammate + Codex 結果，手動去重交叉比對。

產出比較表：

1. **去重**：相同檔案 + 相似描述 → 合併，標註來源 `[team:architecture+codex]`
2. **severity 以最高為準**：如果 correctness 說 MEDIUM 但 codex 說 HIGH → HIGH
3. **Devil's Advocate 的反駁如果成立** → 升級 severity

輸出格式：

```markdown
## Ensemble Review: {FILE_OR_DIR}

### 審閱者
- **Claude Team**: architecture, correctness, security, devils-advocate（orchestrated）
- **Codex GPT-5.5**: 獨立盲驗

### 共識（≥2 個來源都指出）
| # | 問題 | 嚴重性 | 來源 | 說明 |
|---|------|--------|------|------|
| 1 | ... | HIGH | team:arch+correct+codex | ... |

### 僅 Claude Team 指出
| # | 問題 | 嚴重性 | 來源 | 說明 |
|---|------|--------|------|------|
| 1 | ... | ... | team:security | ... |

### 僅 Codex 指出
| # | 問題 | 嚴重性 | 說明 |
|---|------|--------|------|
| 1 | ... | ... | ... |

### Devil's Advocate 反駁結果
| # | 原始判斷 | 反駁 | 成立？ |
|---|---------|------|--------|
| 1 | correctness: LOW | 「其實是 MEDIUM 因為...」 | ✅ 升級 |
| 2 | security: 通過 | 「未能反駁」 | ❌ 維持 |

### 衝突（來源間意見矛盾）
| # | 議題 | Claude Team | Codex | 建議 |
|---|------|------------|-------|------|
| 1 | ... | ... | ... | 交由使用者判斷 |

### Summary
- 共識問題: N 個（最需要修）
- 僅 Claude Team: M 個
- 僅 Codex: K 個
- Devil's Advocate 升級: L 個
- 衝突: J 個

### 建議修改優先順序
1. {highest priority fix}
2. ...
```

### Phase 4.5: 清理 temp 檔（diff 模式）

Phase 4 報表 render 完、確定所有 reviewer/Codex/DA 都已讀過 diff 之後，刪掉 temp 檔（含 changed-line 祕密，別累積在 `/tmp`）：

```bash
[ -n "${DIFF_FILE:-}" ] && rm -f "$DIFF_FILE"   # 路徑模式沒這個變數 → 條件自動跳過
```

> 為何不在 Phase 1 用 `trap … EXIT` 提前刪：workflow / teammate agent 是**非同步**讀 `$DIFF_FILE`，Phase 1 的 shell 一結束 trap 就觸發，會在 agent 還沒讀到前刪掉檔案。所以刪除排在「報表 render 完」這個確定下游都讀完的時點。

### Phase 5: 詢問下一步

```
審閱完成。要怎麼做？
1. 根據共識問題修改文件
2. 只看不改（純審閱）
3. 針對特定問題深入討論
```

## Codex CLI 參考

```bash
# companion script 路徑（優先 marketplace，fallback cache）
CODEX_SCRIPT="$HOME/.claude/plugins/marketplaces/openai-codex/plugins/codex/scripts/codex-companion.mjs"

# 啟動 task
node "$CODEX_SCRIPT" task --effort high "prompt"

# 查狀態
node "$CODEX_SCRIPT" status --all

# 取結果
node "$CODEX_SCRIPT" result $JOB_ID
```

## 範例

```bash
/ensemble-code-review src/auth/              # 路徑：審目錄現狀
/ensemble-code-review --diff                 # uncommitted 變更
/ensemble-code-review --base main            # 本分支相對 main 的變更
/ensemble-code-review --commits 3            # 最近 3 個 commit
/ensemble-code-review --pr 123 --focus 安全性 # 審 PR #123、聚焦安全
```

## 鐵律

- **target 擇一**：path 與 diff flag 互斥；都沒給預設 `--diff`（uncommitted），工作區乾淨則問使用者。
- **diff 一律寫 temp 檔傳 `diffFile`**，不 inline 進 args（大 diff 會撐爆 + escape 地獄）。diff 為空就停，不空跑 ensemble。
- **ref/N 一律先驗證再用**：`<ref>` 經 `git rev-parse --verify`、`<N>` 驗正整數；**絕不把未驗證的使用者 token 內插進 git/gh 指令**（防 command injection + dashed-ref 被當 option）。
- **所有 git/gh 命令檢查 exit code**：非 0（壞 ref / `HEAD~N` 越界 / pre-first-commit / 非 repo）報 stderr 並停 —— **不可把 git 報錯的空輸出當「無變更、乾淨通過」**（假綠燈）。
- **`--diff` 要含 untracked 新檔**（`git ls-files --others --exclude-standard`），別讓「還沒 git add 的新檔」被靜默漏審。
- **`git -C "$REPO"` 的 `$REPO` 先定義**（`git rev-parse --show-toplevel`），不可裸用未定義變數。
- **`--commits N` 的 `N≥commit 總數` 用 empty tree 當 base**（`git hash-object -t tree /dev/null`），**不可** clamp 成 `HEAD~TOT`（= root 的 parent、不存在 → fatal）。`N` 排除 0。
- **DIFF_FILE 在 ensemble 跑完後刪**（含 changed-line 祕密，別累積在 /tmp）。**不要**用 `trap ... EXIT` 提前刪 —— workflow agent 還沒讀就被刪掉。
- **（Backend B legacy）5 個 tool calls 在同一個 message 送出**（4 Agent + 1 Bash codex）。不可分步驟。（Backend A workflow 由 harness 處理平行 + Codex barrier，不適用此條。）
- **Codex 看不到 Claude Team 的討論**。它是完全獨立的盲驗。
- **Codex 的審稿結果原封不動呈現**，不要修改或摘要。
- **交叉比對由主 session 的 Claude 做**，因為主 session 有完整 context。
- **共識問題 > 單方問題**：多個來源都指出的問題最需要修。
- **衝突不自動裁決**：呈現給使用者判斷。
- **Devil's Advocate 是必要的**。防止 3 個 reviewer 的群體盲點。
