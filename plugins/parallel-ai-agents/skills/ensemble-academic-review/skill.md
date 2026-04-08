---
name: ensemble-academic-review
description: |
  學術論文 ensemble 審閱：methodology、writing、reference verification、devils-advocate。
  用 che-zotero-mcp 驗證文獻真實性（抓幻覺文獻），用 perspective-writer 審查寫作風格。
  三種模式：independent（獨立單輪）、hybrid（DA 看前輪的單輪）、mix N（交替 N 輪）。
  Use when: 碩博論文、期刊投稿、學術報告需要嚴格審閱。
argument-hint: "FILE [--mode independent|hybrid|mix] [--rounds N] [--prior summary.md] [--focus 'topic']"
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
  - Skill
  - mcp__plugin_che-zotero-mcp_zotero__zotero_search
  - mcp__plugin_che-zotero-mcp_zotero__zotero_search_by_doi
  - mcp__plugin_che-zotero-mcp_zotero__academic_search
  - mcp__plugin_che-zotero-mcp_zotero__academic_lookup_doi
  - mcp__plugin_che-zotero-mcp_zotero__academic_get_references
  - mcp__plugin_che-zotero-mcp_zotero__academic_get_citations
---

# /ensemble-academic-review — 學術論文 Ensemble 審閱

4 個 Claude teammates（學術審閱角色）+ 1 個 Codex（gpt-5.4）各自獨立審閱，合成比較表找共識和盲點。

> **原理同 Ensemble OCR**：不同角色的錯誤模式不重疊。4 個 Claude 以不同學術審閱角度審閱且互相挑戰，Codex 提供跨模型盲驗。

## 三種模式

| 模式 | 說明 | 適用情境 |
|------|------|---------|
| **independent**（預設） | 所有審閱者從零開始，不知道前輪結果 | 第一輪審閱、或想要完全獨立的第二意見 |
| **hybrid** | 3 reviewer + Codex 獨立審閱，**只有 devil's advocate 看得到前輪結果** | 在前一輪基礎上挖更深，同時避免 anchoring bias |
| **mix N** | 自動交替 independent → hybrid → independent → hybrid... 共 N 輪 | 最完整的審閱，每輪都是完整 ensemble，用 tasks 追蹤進度 |

### mix N 的運作邏輯

```
mix 4 thesis.md
│
├── Round 1: independent — 全新獨立審閱
│   → 產出 review-round-1.md
│
├── Round 2: hybrid — DA 看到 Round 1 結果，找盲點
│   → 產出 review-round-2.md（標記 🆕 新發現）
│
├── Round 3: independent — 再一次全新獨立（不看 Round 1-2）
│   → 產出 review-round-3.md
│
├── Round 4: hybrid — DA 看到 Round 1-3 所有結果，找盲點
│   → 產出 review-round-4.md（標記 🆕 新發現）
│
└── Final: 合併所有輪次 → review-summary.md
    - 跨輪共識（多輪都指出）
    - 每輪獨有的新發現
    - 收斂趨勢（第 N 輪新發現數量遞減 = 審閱飽和）
```

**為什麼交替？**
- independent 輪：不受前輪汙染，能從完全不同的角度發現新問題，也能驗證/修正前輪結論
- hybrid 輪：devil's advocate 帶著所有前輪知識，專門挖前面所有輪次都沒發現的盲點
- 交替進行：每一輪都有獨立發現的機會，也有針對性深挖的機會

### hybrid 模式的資訊分配

| 角色 | 看到什麼 | 為什麼 |
|------|---------|--------|
| methodology | 什麼都不看 | 避免 anchoring，獨立發現新問題 |
| writing | 什麼都不看 | 同上 |
| Codex | 什麼都不看 | 跨模型盲驗必須獨立 |
| reference-verifier | 前輪的可疑文獻 watch list | 重點檢查 + 獨立全面查核 |
| **devil's advocate** | **所有前輪的完整結果** | 專攻盲點、升/降級前輪判斷 |

## 審閱架構

```
/ensemble-academic-review FILE [--mode independent|hybrid|mix] [--rounds N]
│
├── Claude Team（4 teammates）
│   ├── methodology — 研究設計、統計方法（永遠獨立）
│   ├── writing — 論述結構、學術語氣、APA（永遠獨立）
│   ├── reference-verifier — 逐一查文獻（hybrid 時收到 watch list）
│   └── devils-advocate — 反駁（hybrid 時看得到所有前輪結果）
│
└── Codex（gpt-5.4，永遠獨立）

→ 每輪產出獨立的 review-round-{N}.md
→ mix 模式最後合併所有輪次 → review-summary.md
```

## 執行流程

### Phase 0: 解析輸入

```
Arguments:
  FILE — 要審閱的學術論文檔案（.md, .tex, .docx, .pdf）
  --mode — independent（預設）、hybrid、mix
  --rounds — mix 模式的輪數（預設 2，即 independent + hybrid 各一輪）
  --prior — hybrid 模式的前輪摘要檔案（mix 模式自動管理，不需手動指定）
  --focus — 審閱重點（可選）

如果沒有 FILE，問使用者。
如果 --mode hybrid 但沒有 --prior，自動搜尋同目錄下的 review-round-*.md 或 review-summary.md。
如果是 .docx，用 che-word-mcp 的 get_document_text 讀取。
如果是 .pdf，用 macdoc convert --to md 轉換後讀取。
```

### Phase 0.5: Mix 模式的 Task 建立（僅 mix 模式）

用 TaskCreate 建立所有輪次的 tasks，作為進度追蹤：

```
TaskCreate: "Round 1/N: independent review"
TaskCreate: "Round 2/N: hybrid review"
TaskCreate: "Round 3/N: independent review"
...
TaskCreate: "Final: merge all rounds"
```

每完成一輪就 TaskUpdate 為 completed，然後開始下一輪。
**每一輪都是完整的 Phase 1-4 流程，不可偷工減料。**

### Phase 1: 讀取文件 + 準備 context

1. 讀取論文全文
2. 提取所有引用文獻（References / Bibliography 區塊）
3. 準備 context 字串，包含：檔案路徑、全文內容、文獻列表、focus 指示
4. （hybrid 模式）讀取前輪結果，提取：
   - `prior_ref_issues` — 可疑/幻覺文獻清單（給 reference-verifier）
   - `prior_full_report` — 所有前輪的完整結果（只給 devil's advocate）

### Phase 2: 平行啟動 Claude Team + Codex

**CRITICAL: 所有 tool calls（TeamCreate + Codex Bash）必須在同一個 message 送出。不可分步驟。**

**CRITICAL: Teammates 必須用 `subagent_type: "general-purpose"`。不可用 `Explore`。**

#### 2a. Claude Team（4 reviewers）

用 TeamCreate 建立 team，然後在**同一個 message** 啟動 4 個 Agent + 1 個 Codex Bash（共 5 個 tool calls）：

```
TeamCreate:
  name: "academic-review-{timestamp}-round{N}"
  description: "Academic review round {N} for {FILE}"
```

**Agent 1: methodology**
```
Agent:
  name: "methodology"
  subagent_type: "general-purpose"
  team_name: "academic-review-{timestamp}-round{N}"
  prompt: |
    你是 Methodology Reviewer，專門審閱學術研究方法。
    審閱論文：{FILE}
    {context}

    你的任務：
    1. 研究設計是否合理（實驗設計、對照組、隨機化）
    2. 統計方法是否正確（假設檢定、效果量、信賴區間）
    3. 樣本量是否足夠（power analysis）
    4. 推論邏輯是否成立（因果 vs 相關、過度推論）
    5. 研究限制是否充分討論
    6. 分析流程是否可重現

    {focus_instruction}

    用 Read 工具讀取論文相關段落確認。
    用中文逐點列出問題和建議。每個問題標注嚴重性（HIGH/MEDIUM/LOW）。
    最後給整體評價（一段話）。
```

**Agent 2: writing**
```
Agent:
  name: "writing"
  subagent_type: "general-purpose"
  team_name: "academic-review-{timestamp}-round{N}"
  prompt: |
    你是 Writing Quality Reviewer，專門審閱學術寫作品質。
    審閱論文：{FILE}
    {context}

    你的任務：
    1. 論述邏輯 — 各章節之間的銜接是否流暢
    2. 段落結構 — 每段是否有明確的 topic sentence 和 supporting evidence
    3. 學術語氣 — 是否適當使用 hedging language，避免過度武斷
    4. APA 格式 — 引用格式、標題層級、圖表標註是否符合規範
    5. 文法與用詞 — 英文文法錯誤、用詞精確度、一致性
    6. Abstract 品質 — 是否完整涵蓋 background、method、results、conclusion

    你可以使用 Skill tool 呼叫 perspective-writer 來分析特定段落的寫作風格。

    {focus_instruction}

    用中文逐點列出問題和建議。每個問題標注嚴重性（HIGH/MEDIUM/LOW）。
    引用具體段落或句子作為例證。
    最後給整體評價（一段話）。
```

**Agent 3: reference-verifier**
```
Agent:
  name: "reference-verifier"
  subagent_type: "general-purpose"
  team_name: "academic-review-{timestamp}-round{N}"
  prompt: |
    你是 Reference Verifier，專門驗證學術文獻的真實性。
    審閱論文：{FILE}
    {context}

    你的核心任務：**偵測幻覺文獻**（hallucinated references）。

    {hybrid_mode_ref_verifier_instruction}

    步驟：
    1. 從論文中提取所有引用文獻（作者、年份、標題、期刊）
    2. 對每一筆文獻，使用 che-zotero-mcp 工具驗證：
       - 用 `academic_search` 搜尋標題或作者+年份
       - 如果有 DOI，用 `academic_lookup_doi` 驗證
       - 用 `zotero_search` 檢查是否已在 Zotero 資料庫中
    3. 分類每筆文獻：
       - ✅ 已驗證（找到匹配的真實文獻）
       - ⚠️ 存疑（部分匹配，可能是資訊不完整）
       - ❌ 疑似幻覺（完全找不到，或作者/標題/年份不匹配）
    4. 檢查 in-text citation 與 reference list 是否一致（有沒有引了但沒列、或列了但沒引）

    輸出格式：
    ```
    ## 文獻驗證結果

    ### 已驗證 ✅
    1. Author (Year). Title. — DOI: xxx ✅

    ### 存疑 ⚠️
    1. Author (Year). Title. — 原因：找到類似文獻但年份不同

    ### 疑似幻覺 ❌
    1. Author (Year). Title. — 原因：完全查無此文獻

    ### 引用一致性
    - 引了但沒列在 references：...
    - 列在 references 但文中未引用：...
    ```

    每筆文獻都要查。不可跳過。
    用中文輸出結果。
```

**Agent 4: devils-advocate**
```
Agent:
  name: "devils-advocate"
  subagent_type: "general-purpose"
  team_name: "academic-review-{timestamp}-round{N}"
  prompt: |
    你是 Devil's Advocate，學術審閱的對抗性驗證者。
    審閱論文：{FILE}
    {context}

    你的任務：等其他 3 個 reviewer（methodology、writing、reference-verifier）完成後，
    用 SendMessage 詢問他們的結論，然後**試著反駁每一個「通過」或「LOW」的判斷**。

    {hybrid_mode_devils_advocate_instruction}

    步驟：
    1. 先用 Read 工具讀取論文，形成自己的理解
    2. 用 SendMessage 分別問 methodology、writing、reference-verifier 他們的 findings
    3. 對每個「通過」的判斷，找理由說它其實有問題
    4. 對每個「LOW」的判斷，論證為什麼應該是 MEDIUM 或 HIGH
    5. 特別挑戰：
       - methodology 說統計方法 OK → 找 alternative interpretation
       - writing 說邏輯清晰 → 找隱含的邏輯跳躍
       - reference-verifier 說文獻 OK → 質疑文獻的相關性和時效性
    6. 如果你找不到反駁的理由，才承認確實通過

    這是對抗性驗證 — 你的存在是為了防止群體盲點。
    用中文輸出你的反駁結果。
```

#### Mode-specific prompt injections

以下變數在 independent 輪為空字串，在 hybrid 輪注入內容：

**`{hybrid_mode_ref_verifier_instruction}`** — 給 reference-verifier：
```
（hybrid 輪時注入）
前幾輪審閱標記了以下可疑文獻，請特別留意：
{prior_ref_issues}
但你的核心任務仍然是逐一查核所有文獻，不要只看這份清單。
前輪的判斷可能有誤，你需要獨立驗證。
```

**`{hybrid_mode_devils_advocate_instruction}`** — 給 devil's advocate：
```
（hybrid 輪時注入）
## 所有前輪審閱結果

以下是前面所有輪次的 ensemble 審閱結果：
{prior_full_report}

你的額外任務（除了反駁本輪 reviewer 的判斷之外）：
1. **挑戰前輪「通過」的判斷** — 前輪認為 OK 或只給 LOW 的項目，是否有被低估的問題？
2. **找出所有前輪的盲點** — 有什麼問題是前面所有輪次都沒想到的？
3. **驗證前輪的結論** — 前輪的 HIGH 判斷是否真的那麼嚴重？有沒有過度反應的？
4. **不要重複已知問題** — 前輪已經充分討論的問題不需要重新論述，除非你有新的反駁角度

在輸出中，明確區分：
- 「前輪已知 + 本輪確認」的問題
- 「前輪已知但需要升級/降級」的問題
- 「前輪完全未發現」的新問題 🆕
```

#### 2b. Codex（背景執行）

```bash
CODEX_SCRIPT="$HOME/.claude/plugins/marketplaces/openai-codex/plugins/codex/scripts/codex-companion.mjs"

if [ ! -f "$CODEX_SCRIPT" ]; then
  CODEX_SCRIPT="$HOME/.claude/plugins/cache/openai-codex/codex/1.0.1/scripts/codex-companion.mjs"
fi

node "$CODEX_SCRIPT" task \
  --effort high \
  "{codex_prompt}"
```

Codex prompt 應包含：
- 論文全文（或摘要 + 關鍵段落，視長度而定）
- 要求從 methodology、writing、reference 三個角度審閱
- 用中文回答
- **不提及 Claude team 的存在**（確保獨立性）

### Phase 3: 收集結果

1. 等待 4 個 Claude teammates 完成（透過自動訊息通知）
2. 等待 Codex 完成（輪詢 status）
3. 如果 Codex 失敗或超時（>10 分鐘），跳過，標注「Codex 不可用」

### Phase 4: 合併去重 + 寫入本輪結果

由主 session 的 Claude 讀取所有結果，產出本輪比較表：

1. **去重**：相同問題 → 合併，標註來源
2. **severity 以最高為準**
3. **Devil's Advocate 的反駁如果成立** → 升級 severity
4. **幻覺文獻特別標示** — reference-verifier 的 ❌ 結果優先級最高

#### hybrid 輪額外步驟

5. **與前輪交叉比對**：將本輪發現分為三類：
   - **前輪已知 + 本輪確認**：增加可信度
   - **前輪已知但本輪修正**：前輪判斷不夠精確
   - **本輪新發現 🆕**：前輪所有審閱者都未發現的問題

#### 寫入本輪結果

將本輪結果寫入 `review-round-{N}.md`（與論文同目錄），然後：
- independent / hybrid 單輪模式：這就是最終輸出
- mix 模式：TaskUpdate 標記本輪完成，繼續下一輪

### Phase 5: Mix 模式的輪次循環

```
for round in 1..N:
    if round is odd:
        run Phase 1-4 as independent
    else:
        run Phase 1-4 as hybrid (prior = all previous rounds)
    
    TaskUpdate: "Round {round}/{N}" → completed
    Write review-round-{round}.md

TaskUpdate: "Final: merge all rounds" → in_progress
```

### Phase 6: 最終合併（mix 模式）

讀取所有 `review-round-*.md`，產出最終的 `review-summary.md`：

```markdown
## Ensemble Academic Review: {FILE}
## Mode: mix {N} rounds

### 審閱歷程
| 輪次 | 模式 | 新發現數 | 累計問題數 |
|------|------|---------|-----------|
| Round 1 | independent | 15 | 15 |
| Round 2 | hybrid | 8 🆕 | 23 |
| Round 3 | independent | 4 | 27 |
| Round 4 | hybrid | 1 🆕 | 28 |

### 收斂判斷
新發現數逐輪遞減（15 → 8 → 4 → 1），審閱已趨近飽和。

### 跨輪共識（多輪都獨立指出）
| # | 問題 | 出現輪次 | 嚴重性 |
|---|------|---------|--------|
| 1 | ... | R1, R2, R3 | HIGH |

### 僅單輪發現
| # | 問題 | 首次出現 | 嚴重性 | 後續輪次確認？ |
|---|------|---------|--------|--------------|
| 1 | ... | R2 🆕 | HIGH | R3 確認 |
| 2 | ... | R4 🆕 | MEDIUM | 未再驗證 |

### 文獻驗證（取最完整的一輪）
...

### 建議修改優先順序
...
```

### Phase 7: 詢問下一步

```
審閱完成（{mode}, {N} 輪）。
新發現趨勢：{round1_new} → {round2_new} → ... → {roundN_new}
{收斂判斷}

要怎麼做？
1. 修正幻覺文獻和 HIGH 問題
2. 只看不改（純審閱）
3. 針對特定問題深入討論
4. 用 /perspective-writer 改寫特定段落
5. 再跑一輪（如果新發現數未收斂）
```

## 鐵律

### 所有模式共用

- **5 個 tool calls 在同一個 message 送出**（4 Agent + 1 Bash codex）。不可分步驟。
- **Codex 看不到 Claude Team 的討論**。完全獨立的盲驗。
- **Codex 的審稿結果原封不動呈現**，不要修改或摘要。
- **reference-verifier 必須逐一查每筆文獻**。不可跳過或抽樣。
- **幻覺文獻是最高優先級**。任何 ❌ 結果都是 HIGH severity。
- **共識問題 > 單方問題**：多個來源都指出的問題最需要修。
- **衝突不自動裁決**：呈現給使用者判斷。
- **Devil's Advocate 是必要的**。防止群體盲點。

### hybrid 輪專屬

- **methodology、writing、Codex 絕對不看前輪結果**。防止 anchoring bias。
- **只有 devil's advocate 拿到所有前輪完整結果**。
- **reference-verifier 只拿到 watch list**，不是完整判斷。仍須獨立全面查核。
- **合併時必須標記 🆕 新發現**。

### mix 模式專屬

- **每一輪都是完整的 Phase 1-4**。不可偷工減料、跳過 Codex、或減少 reviewer。
- **用 TaskCreate/TaskUpdate 追蹤每輪進度**。讓使用者看到即時狀態。
- **每輪結果獨立寫入 `review-round-{N}.md`**。不可覆蓋前輪。
- **最終合併必須包含「收斂判斷」**：新發現數是否遞減。如果最後一輪仍有大量新發現，建議使用者再跑一輪。
- **前輪結論可以被後輪推翻**。independent 輪的獨立審閱者如果得出不同結論，標記衝突供使用者判斷。
