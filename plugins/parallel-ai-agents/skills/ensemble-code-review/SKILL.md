---
name: ensemble-code-review
description: |
  Claude + Codex 雙 AI 獨立審閱程式碼，交叉比對找共識和盲點。
  4 Claude teammates（architecture, correctness, security, devils-advocate）+ Codex GPT-5.4 獨立審一遍，最後合成比較表。
  Use when: 程式碼、技術文件、設計文件發布前需要嚴格審閱。
argument-hint: "FILE_OR_DIR [--focus 'review focus'] e.g. 'src/auth/', 'packages/ocr-swift/ --focus API正確性'"
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

4 個 Claude teammates（orchestrated team）+ 1 個 Codex（gpt-5.4）各自獨立審閱，合成比較表找出共識和盲點。

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
└── Codex（gpt-5.4，完全獨立 process，跨模型盲驗）

→ 5 份 findings 合併去重 → 比較表
```

**為什麼 5 個？**
- 4 個 Claude teammates 在同一個 team 裡**互相挑戰**（不是各自獨立報告）
- Devil's Advocate 的工作是**試著證明其他 3 個的通過判斷是錯的**
- Codex 是完全不同的模型家族（gpt-5.4），提供**跨模型盲驗**

## 執行流程

### Phase 0: 解析輸入

```
Arguments:
  FILE_OR_DIR — 要審閱的檔案或目錄路徑
  --focus — 審閱重點（可選，如「API正確性」「技術準確性」「安全性」）

如果沒有 FILE_OR_DIR，問使用者。
如果 FILE_OR_DIR 是目錄，讀取所有原始碼檔案作為審閱範圍。
```

### Phase 1: 讀取文件 + 準備 context

1. 讀取目標文件（如果是目錄，列出所有檔案路徑和內容摘要）
2. 自動判斷審閱類型：

| 檔案類型 | 審閱重點 |
|---------|---------|
| `.md` blog/文章 | 技術準確性、邏輯一致性、聲明可驗證性 |
| `.md` 設計文件 | 架構合理性、邊界情況、可行性、遺漏 |
| `.swift` / `.py` / `.ts` 程式碼 | bug、安全漏洞、效能、API 用法、edge case |
| 目錄（整個 package） | 架構、死碼、API 一致性、依賴管理 |

3. 準備 context 字串，包含：檔案路徑、內容、focus 指示

### Phase 2: 平行啟動 Claude Team + Codex

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

#### 2b. Codex（背景執行）

```bash
CODEX_SCRIPT="$HOME/.claude/plugins/marketplaces/openai-codex/plugins/codex/scripts/codex-companion.mjs"

# 也可以用 cache 路徑作為 fallback
if [ ! -f "$CODEX_SCRIPT" ]; then
  CODEX_SCRIPT="$HOME/.claude/plugins/cache/openai-codex/codex/1.0.1/scripts/codex-companion.mjs"
fi

node "$CODEX_SCRIPT" task \
  --effort high \
  "{codex_prompt}"
```

Codex prompt 應包含：
- 審閱範圍和 focus
- 要求逐點分析，標注嚴重性
- 用中文回答
- **不提及 Claude team 的存在**（確保獨立性）

### Phase 3: 收集結果

1. 等待 4 個 Claude teammates 完成（透過自動訊息通知）
2. 等待 Codex 完成（輪詢 status）
3. 如果 Codex 失敗或超時（>10 分鐘），跳過，標注「Codex 不可用」

```bash
node "$CODEX_SCRIPT" status --all
node "$CODEX_SCRIPT" result $JOB_ID
```

### Phase 4: 合併去重 + 交叉比對

由主 session 的 Claude 讀取所有結果，產出比較表：

1. **去重**：相同檔案 + 相似描述 → 合併，標註來源 `[team:architecture+codex]`
2. **severity 以最高為準**：如果 correctness 說 MEDIUM 但 codex 說 HIGH → HIGH
3. **Devil's Advocate 的反駁如果成立** → 升級 severity

輸出格式：

```markdown
## Ensemble Review: {FILE_OR_DIR}

### 審閱者
- **Claude Team**: architecture, correctness, security, devils-advocate（orchestrated）
- **Codex GPT-5.4**: 獨立盲驗

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

## 鐵律

- **5 個 tool calls 在同一個 message 送出**（4 Agent + 1 Bash codex）。不可分步驟。
- **Codex 看不到 Claude Team 的討論**。它是完全獨立的盲驗。
- **Codex 的審稿結果原封不動呈現**，不要修改或摘要。
- **交叉比對由主 session 的 Claude 做**，因為主 session 有完整 context。
- **共識問題 > 單方問題**：多個來源都指出的問題最需要修。
- **衝突不自動裁決**：呈現給使用者判斷。
- **Devil's Advocate 是必要的**。防止 3 個 reviewer 的群體盲點。
