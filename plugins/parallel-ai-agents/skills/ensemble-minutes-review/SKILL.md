---
name: ensemble-minutes-review
description: |
  會議記錄 ensemble 審閱：fidelity（忠實性）、completeness（完整性）、attribution（歸屬）、
  cross-document（佐證文件對照）、devils-advocate。以會議錄音逐字稿為唯一權威來源，
  逐條檢查記錄的每一項陳述是否站得住，並比對來函、開會通知、前次記錄等佐證文件。
  Use when: 會議記錄定稿前的事實核對、對外行文前的查核、記錄與逐字稿的一致性驗證。
argument-hint: "MINUTES_FILE --srt TRANSCRIPT [--docs 'path1,path2'] [--replicas N] [--model sonnet|opus]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
  - Agent
  - TaskCreate
  - TaskUpdate
  - TaskList
  - AskUserQuestion
  - Workflow
---

# /ensemble-minutes-review — 會議記錄 Ensemble 審閱

會議記錄的品質關卡不是文筆，是**每一條陳述是否站得住**。這份 skill 派出四個角度互不重疊的
審閱者，加一個魔鬼代言人，全部以逐字稿為唯一權威來源。

## 為什麼不用 academic 或 lecture profile

| profile | 用在會議記錄的問題 |
|---|---|
| `academic` | `methodology` 不適用（記錄沒有研究設計）；`reference-verifier` 會去查 Zotero 空轉；`number-verifier` 設計成跑 R/Python 重算，但記錄沒有計算 artifact。四個 lens 有三個空轉或方向錯誤 |
| `lecture` | `completeness` 的「逐字稿覆蓋率」確實對得上，但 `student-readability` 不適用，`content-accuracy` 問的是知識正確性而非「是否忠於逐字稿」 |

會議記錄要問的是**忠實性**（有沒有寫出逐字稿沒有的東西）與**完整性**（有沒有漏掉逐字稿有的
東西），這兩者互為反面，缺一不可。`minutes` profile 為此而設。

## 審閱架構

| Lens | 需要逐字稿 | 問的問題 |
|---|:---:|---|
| `fidelity` | ✓ | 記錄寫的，逐字稿有嗎？推論有沒有被寫成會中決定？ |
| `completeness` | ✓ | 逐字稿有的，記錄漏了嗎？不利內容有沒有消失？ |
| `attribution` | ✓ | 誰說的、誰要辦，依據何在？未確認者有無被具名？ |
| `cross-document` | | 來函、開會通知、前次記錄，對得上嗎？交叉參照指對地方了嗎？ |
| `devils-advocate` | ✓ | 上面四位判定「沒問題」的地方，真的沒問題嗎？ |

DA 專門盯三種安靜的偏移：把個別發言寫成全體共識、把條件句寫成確定句、把會後才知道的事寫得
像會中已知。這三種在文本上都讀起來很正常。

## 執行流程

### Phase 0：解析輸入

- `MINUTES_FILE`：會議記錄（`.tex` / `.md` / `.docx`）
- `--srt`：**必要**。逐字稿路徑。沒有逐字稿就沒有權威來源，此時應拒絕執行而非降級——
  無來源的「審閱」只會產生看起來合理的臆測
- `--docs`：佐證文件路徑，逗號分隔（來函、開會通知、議程、前次會議的記錄或溯源檔）

### Phase 1：組 contextBlock

把下列資訊寫進 `contextBlock` 交給 agent：

1. **任務定性**：這是行政文件的事實查核，不是論文審查；重點不在文筆，在每條陳述是否站得住
2. **佐證文件清單**：逐一列出絕對路徑並說明各是什麼，agent 才知道要 Read 什麼
3. **已知限制**（避免回饋都在講這些）：逐字稿字錯率、語者分離是否可靠、哪些專名已知為誤聽、
   哪些內容是刻意不記錄的（如製作說明移入註解、敏感內容依指示略去）
4. **已知曾犯的錯**（如果有）：給具體實例比給抽象原則有效。例如「曾把『本案屬 top-down 推動』
   誤寫為『另備 top-down 計畫書』，把性質誤讀成文件」，agent 會據此找同類錯誤

### Phase 2：派發

```javascript
Workflow({ name: "parallel-ai-agents:pai-ensemble", args: {
  profile: "minutes",
  file: "<會議記錄絕對路徑>",
  srtFile: "<逐字稿絕對路徑>",
  contextBlock: "<Phase 1 組好的內容>",
  agentModel: "sonnet",
  replicas: 1,
  codexEnabled: false
}})
```

> ⚠️ **`args` 是物件，不是字串。** 傳字串時 `profile` 解析為 `undefined`，harness 回
> `unknown ensemble profile` 且 **0 個 agent 被派出**——workflow 會「成功」結束，
> 只在 findings 裡留一條 harness 層級的 HIGH。看到 `agents: 0` 就是踩到這個。
>
> ⚠️ **`agentModel` 一定要給。** 不給時 agent 繼承 session 的 main-loop model，
> 高階 session 單輪 ensemble 曾燒掉 56–109 萬 token 並在 session limit 撞死 lens agent。
> 事實核對用 `sonnet` 即可；記錄爭議大或篇幅長再考慮 `opus`。

### Phase 3：讀結果

回傳 `{ findings, verdict, stats }`。`stats.agents` 應等於 lens 數 × replicas + DA；
**明顯偏少就是有 agent 死掉或 profile 沒吃到**，先查 `journal.jsonl` 再解讀 findings。

### Phase 4：處置

findings 逐條回原文核對後才改。**不要照單全收**——審閱者同樣可能誤讀逐字稿，
特別是逐字稿本身字錯率高的時候。改與不改都要能說出理由。

## 與 `sinica-admin:meeting-minutes` 的分工

| | 管什麼 |
|---|---|
| `meeting-minutes` | 產出記錄；`compile.sh` 的機械 gate（破折號、markdown 殘留、寡行、缺字、檔名） |
| 本 skill | 內容是否忠於會議；機械檢查看不出來的東西 |

兩者互補，順序是先產出、機械 gate 過關，再跑 ensemble 查事實。**不要用本 skill 檢查標點或
排版**——那些有確定性的機械檢查，派 LLM 去做既慢又不可靠。

## 反模式

| 想做的 | 為什麼不行 |
|---|---|
| 沒有逐字稿也跑 | 沒有權威來源，審閱者只能憑常識猜「這樣寫合不合理」，產出的是臆測 |
| 用本 skill 抓錯字、標點 | 那是 `compile.sh` 的工作，機械檢查更快更準 |
| findings 直接照改 | 審閱者也會誤讀。每條回原文核對 |
| 把已知限制留給 agent 自己發現 | 會得到一堆「語者未確認」「字錯率高」的重複回饋，淹掉真正的問題 |
