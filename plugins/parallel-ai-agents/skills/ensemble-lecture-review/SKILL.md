---
name: ensemble-lecture-review
description: |
  教學講義 Ensemble 審閱：4 個 Claude teammates（教學審閱角色）各自獨立審閱講義品質。
  當用戶提到「review 講義」「審閱講義」「講義品質」「lecture review」時使用。
argument-hint: "[講義 HTML 路徑] [--srt 對應逐字稿路徑]"
---

# /ensemble-lecture-review — 教學講義 Ensemble 審閱

4 個 Claude teammates 各自獨立審閱講義，合成比較表找共識和盲點。

> **與 ensemble-academic-review 的差異**：角色從「學術論文審閱」改為「教學材料審閱」。不查文獻真偽，改查逐字稿覆蓋率。

## 審閱架構

```
/ensemble-lecture-review lecture.html [--srt transcript.srt]
│
├── Claude Team（4 teammates）
│   ├── content-accuracy — 內容正確性（統計、理論、公式）
│   ├── student-readability — 學生可讀性（白話程度、邏輯銜接）
│   ├── completeness — 完整性（對照逐字稿找遺漏）
│   └── devils-advocate — 反駁前三個的判斷
│
└── 比較表 + 修改建議
```

## 執行流程

### Phase 0: 解析輸入

```
Arguments:
  FILE — 講義 HTML 檔案路徑
  --srt — 對應的 SRT 逐字稿（可選，completeness reviewer 會用）

如果沒有 FILE，掃描 handout 目錄列出所有講義讓用戶選。
如果沒有 --srt，嘗試從 lectures/ 目錄自動匹配。
```

### Phase 1: 讀取文件 + 準備 context

1. 讀取講義 HTML 全文
2. 如果有 SRT，讀取逐字稿全文
3. 讀取 teaching.json（了解學生背景）
4. 準備 context 字串

### Phase 2: 平行啟動 4 個 Claude Teammates

**CRITICAL: 所有 4 個 Agent tool calls 必須在同一個 message 送出。**

**CRITICAL: Teammates 必須用 `subagent_type: "general-purpose"`。**

用 TeamCreate 建立 team，然後在同一個 message 啟動 4 個 Agent：

#### Agent 1: content-accuracy

```
你是 Content Accuracy Reviewer，專門檢查教學講義的知識正確性。
審閱講義：{FILE}
{context}

學生背景：{student_info}

你的任務：
1. **統計概念**：定義是否正確（p-value、power、effect size、confidence interval）
2. **公式**：數學符號有沒有寫錯（KaTeX 語法是否正確）
3. **理論解釋**：心理學理論的描述是否準確（Higgins, Regulatory Focus/Fit）
4. **因果推論**：有沒有把相關說成因果、或過度推論
5. **術語一致性**：同一個概念在不同地方是否用同一個名稱
6. **範例正確性**：舉的例子是否恰當地支持概念

用 Read 工具讀取講義確認。
逐點列出問題，每個標注嚴重性（HIGH/MEDIUM/LOW）。
引用具體的段落或句子。
```

#### Agent 2: student-readability

```
你是 Student Readability Reviewer，從學生的角度審閱講義的易懂程度。
審閱講義：{FILE}
{context}

學生背景：{student_info}（注意：學生零程式基礎，概念理解可能表面化）

你的任務：
1. **白話程度**：有沒有用了專業術語但沒解釋的地方
2. **邏輯銜接**：段落之間的跳躍是否太大（學生能不能跟上）
3. **具體例子**：抽象概念有沒有搭配具體例子
4. **視覺輔助**：表格、圖表是否幫助理解（還是增加混淆）
5. **篇幅平衡**：重要概念是否得到足夠篇幅（vs 次要內容佔太多）
6. **結構導航**：學生能不能快速找到想看的段落（標題是否清楚）
7. **前後呼應**：「重點整理」是否真的涵蓋了最重要的內容

用 Read 工具讀取講義。
站在學生的角度思考：「如果我是零基礎的學生，讀到這裡我會卡住嗎？」
逐點列出問題，每個標注嚴重性（HIGH/MEDIUM/LOW）。
```

#### Agent 3: completeness

```
你是 Completeness Reviewer，檢查講義是否完整覆蓋了上課教的內容。
審閱講義：{FILE}
{context}

{srt_instruction}

你的任務：
1. **逐字稿覆蓋率**：逐字稿裡有教但講義沒寫到的重點（最重要）
2. **結構完整性**：
   - 有沒有「重點整理」section
   - 有沒有「課後作業」section
   - h2/h3 層級是否正確（沒有孤立的 h3）
   - h2 之間有沒有 --- 分隔
3. **KaTeX/Mermaid**：有數學符號的地方有沒有加 KaTeX CDN？有路徑圖的地方有沒有用 Mermaid 或 ASCII art？
4. **連結有效性**：href 指向的檔案是否存在
5. **缺少的教學元素**：
   - 有沒有該有 blockquote 提醒但沒有的地方
   - 有沒有該用表格對比但只用文字描述的地方

如果有 SRT，分段讀（每次 200 行），逐段對照講義找遺漏。
沒有 SRT 就只做結構完整性檢查。
逐點列出問題，每個標注嚴重性（HIGH/MEDIUM/LOW）。
```

SRT instruction（有 SRT 時注入）：
```
逐字稿路徑：{SRT_PATH}
請用 Read 工具分段讀取逐字稿（每次 200 行），逐段對照講義。
如果逐字稿裡有教學重點但講義沒寫到，標記為 HIGH。
```

#### Agent 4: devils-advocate

```
你是 Devil's Advocate，教學講義審閱的對抗性驗證者。
審閱講義：{FILE}
{context}

你的任務：等其他 3 個 reviewer 完成後，用 SendMessage 詢問他們的結論，
然後試著反駁每一個「通過」或「LOW」的判斷。

步驟：
1. 先用 Read 工具讀取講義，形成自己的理解
2. 用 SendMessage 分別問 content-accuracy、student-readability、completeness 他們的 findings
3. 對每個「通過」的判斷，找理由說它其實有問題：
   - content-accuracy 說概念正確 → 找邊界情況或過度簡化
   - student-readability 說易懂 → 找可能讓特定背景學生困惑的地方
   - completeness 說完整 → 找隱含的教學目標是否達成
4. 特別挑戰：
   - 「重點整理」是否真的是重點，還是只是把小標題抄了一遍
   - 表格是否真的幫助理解，還是增加認知負擔
   - 課後作業是否可執行，學生知不知道具體要做什麼
5. 如果找不到反駁的理由，才承認確實通過

用中文輸出反駁結果。
```

### Phase 3: 收集結果

等待 4 個 teammates 完成（透過自動訊息通知）。

### Phase 4: 合併去重

由主 session 的 Claude 讀取所有結果，產出比較表：

```markdown
## Ensemble Lecture Review: {FILE}

### 比較表
| # | 問題 | 嚴重性 | 來源 | 位置 |
|---|------|--------|------|------|
| 1 | Power 的定義缺少直覺解釋 | HIGH | content-accuracy, student-readability | 統計概念 section |
| 2 | h3 「OpenClaw」沒有 h2 父層 | HIGH | completeness | AI 工具比較 section |
| 3 | ... | ... | ... | ... |

### 共識問題（多個 reviewer 都指出）
...

### Devil's Advocate 升級的問題
...

### 統計
- content-accuracy: N 個問題（H: x, M: y, L: z）
- student-readability: N 個問題
- completeness: N 個問題
- devils-advocate 升級: N 個
```

### Phase 5: 詢問下一步

```
審閱完成。要怎麼做？
1. 修正 HIGH 問題
2. 只看不改
3. 針對特定問題深入討論
4. 用 /teaching-toolkit:lecture-enrich 充實講義
```

## 鐵律

- **4 個 tool calls 在同一個 message 送出**。不可分步驟。
- **completeness reviewer 必須讀逐字稿**（如果有提供）。不可跳過。
- **共識問題 > 單方問題**：多個 reviewer 都指出的問題最需要修。
- **Devil's Advocate 是必要的**。防止群體盲點。
- **考慮學生背景**：所有 reviewer 都要知道學生的程度和目標。
