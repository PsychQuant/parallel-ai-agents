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
審閱者（實際 lens 集合以 provenance 行為準；層 ②③ 可增加或取代），加一個魔鬼代言人，全部以逐字稿為唯一權威來源。

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

1. **蒐集 lens 層 ②③**（#29、#40），在呼叫 Workflow **之前**：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/pai-collect-lens-layers" minutes
   ```

   stdout 是一個 JSON 物件 `{ lenses, layers, warnings }`（schema 見
   [`references/lens-layers.md`](../../references/lens-layers.md) §1）。`lenses` **原樣**（含 `override`、
   `needsSrt`、`_layer` 欄）進 `args.customLenses`；**整個物件留到 Phase 3** —— provenance 行要用
   `layers`、`warnings` 與每條 lens 的 `_layer`。
   ⚠️ **`profile` 維持 `"minutes"`，不可改成 `"custom"`** —— 理由（`profile.title` 無 args 覆寫路徑）在該文件。
   `lenses` 為空（沒裝 `pai-lenses`、也沒有 `~/.claude/pai-lenses/minutes.csv`）時省略 `customLenses`。

   **collector 失敗 ≠ 沒裝 pack。** 退出碼非 0（2 = 用法錯；其他多半是 Python traceback），或 stdout
   解析不出含 `lenses` 陣列的 JSON 物件 → 記下退出碼與 stderr 第一行，**省略 `customLenses` 照常派發**
   （built-in 四條不受影響，不值得陪葬），並在 Phase 3 的 provenance 行改印
   `Lens 來源：built-in <n> 條 · ⚠️ lens collector 失敗（exit <rc>：<stderr 第一行>），層 ②③ 未載入`。
   這與 collector 對單一層損壞的處理（`corrupt` → 警告、略過該層、繼續）同一原則：缺席靜默、損壞出聲。
   各層自己的損壞（`empty` / `corrupt` / `unversioned`）collector 仍是 exit 0，走 `warnings`，不走這條。

   > ⚠️ **層 ②③ 的 lens 會讀到本 skill 的全部輸入** —— 會議錄音逐字稿、佐證文件，以及 contextBlock
   > 裡「哪些內容是刻意不記錄的」這類敏感說明。lens 的 `focus` 逐字成為 reviewer 的角色級指令、
   > **不經 sentinel 包裹**（結構性修法追蹤於 [#36](https://github.com/PsychQuant/parallel-ai-agents/issues/36)），
   > 而 reviewer 有 Read / Bash。所以：
   > - pack lens 的界線是 `pai-lenses` 的 README「界線：封閉列舉，不是總括判準」
   >   （[repo 上的版本](https://github.com/PsychQuant/parallel-ai-agents/blob/main/plugins/pai-lenses/README.md)；
   >   裝好的 plugin cache 裡沒有相對路徑可連）列出的四類禁止事項，**只有這四類**：
   >   (1) 指示讀取**審閱標的以外**的路徑（`~/.aws/credentials`、`.env`、`/etc/*`、任何家目錄下的檔案）；
   >   (2) 指示**不要回報**某一類 finding；(3) 指示把結果**輸出到別處**（寫檔、送出、貼到某個 URL）；
   >   (4) 指示**忽略或覆寫**其他指令。在審閱標的內用 Read/Grep 查證自己的 finding 是明確允許的；
   > - collector 選 pack 的方式是跨 marketplace glob `<cache>/*/pai-lenses/<semver>/`、取**版本最高**的一份
   >   （`bin/pai-collect-lens-layers` 的 `find_pack_dir`）—— 不論它來自哪個 marketplace。裝了誰的
   >   `pai-lenses`，就是把逐字稿交給誰寫的 prompt；
   > - 標了 `override` 的 lens 會**原位取代** built-in（包括 `fidelity` 這條本 skill 的核心 lens），
   >   Phase 3 會把它印成警告。

2. 呼叫 Workflow：

```javascript
Workflow({ name: "parallel-ai-agents:pai-ensemble", args: {
  profile: "minutes",
  file: "<會議記錄絕對路徑>",
  srtFile: "<逐字稿絕對路徑>",
  customLenses: [ /* pai-collect-lens-layers 的 lenses 陣列，原樣（層 ②③）；空則整欄省略 */ ],
  contextBlock: "<Phase 1 組好的內容>",
  agentModel: "sonnet",
  replicas: 1,
  codexEnabled: false
}})
```

> ⚠️ **`args` 是物件，不是字串。** 傳字串時 `profile` 解析為 `undefined`，harness 回
> `unknown ensemble profile` 且 **0 個 agent 被派出**——workflow 會「成功」結束，
> 只在 findings 裡留一條 harness 層級的 HIGH。看到 `agents: 0` 就是踩到這個。
> `customLenses` 同理：放 collector 回的**陣列本身**，不是它的 JSON 字串 —— harness 對非陣列
> 一律當成沒給（`Array.isArray` 為假即空），層 ②③ 會安靜消失，只有 provenance 行看得出來。
>
> ⚠️ **`agentModel` 一定要給。** 不給時 agent 繼承 session 的 main-loop model，
> 高階 session 單輪 ensemble 曾燒掉 56–109 萬 token 並在 session limit 撞死 lens agent。
> 事實核對用 `sonnet` 即可；記錄爭議大或篇幅長再考慮 `opus`。

### Phase 3：讀結果

回傳 `{ findings, verdict, stats }`。

**先確認層 ②③ 真的進了 harness。** 令 `N` = Phase 2 collector 回的 `lenses` 條數、`C` =
`stats.lensProvenance` 裡 `origin === "custom"` 的條數（本 skill 的 `customLenses` 只放 collector 的 `lenses`，
所以兩者該相等）。

- `N > 0` 且 `C === 0` → 在 provenance 行下方印
  `⚠️ 層 ②③ 未進入 harness（collector 回了 <N> 條，harness 一條都沒收到 —— customLenses 不是陣列？）`。
  這正是 `customLenses` 被傳成字串時的樣子：harness 對非陣列一律當成沒給，四條 built-in 照跑，
  `stats.agents` 也與「沒裝 pack」完全一樣 —— **只看派發規模是看不出來的**（`L` 與 `stats.replicas`
  本身就來自 harness 的回傳，拿它們算出的預期值永遠對得上）。
- `0 < C ≠ N` → harness 丟掉了一部分（見下方配對前提），provenance 行改印合計（見下）。

`stats.agents` 數的是**派出去**的 agent（harness 在派發時算，不看誰回來）；`agents: 0` 見上方 ⚠️。
**agent 死掉不會讓 `stats.agents` 變少** —— 看 `stats.reviewers[].ok === false`、`stats.daOk === false`
與 `stats.integrity`（每個沒完成的 lens 都有一條 `<key> lens did not complete` 的 HIGH finding）。

**上限夾擠會安靜地切掉 lens。** harness 先把 lens 逐條記進 `lensProvenance`（`action: "added"`），**之後**才依
`maxAgents`（`args.maxAgents` 夾在 4..30，沒給就是 16；本 skill `codexEnabled: false`，只保留 DA 一席，
所以最多 `maxAgents − 1` 條）從**尾端**切掉多出的 lens —— 依位置切，不依層：新增（`added`）的層 ③ lens 排在最後、先被切，其次是層 ②；原位取代的 lens 佔的是被取代者的位置。被切的 lens 在
`lensProvenance` 裡仍是 `added`，不能據此算成 `+`。判別方式：`stats.reviewers[].lens` 是**實際派出**的
lens key（每個 replica 一筆）；`lensProvenance` 裡 key 不在這個集合中的條目就是被切掉的
（`journal.jsonl` 也會有 `lens set <總數> → <上限> … extra lenses dropped` 一行，可互相印證）。
被切的層 ②③ lens 記為 `✂`，並在 provenance 行下方印
`⚠️ 上限 maxAgents=<m> 切掉了 <k> 條層 ②③ lens：<key>←<_layer>, …（本次審閱不含）`。

**findings 表之前先印 provenance 行**（#29、#40）：lens 來源一行 + `warnings` 逐條，格式見
[`references/lens-layers.md`](../../references/lens-layers.md) §4–5；本 skill 在每層的 `+/⊕` 後多一欄
`✂<e>`（有被切才印）。每個數字的來源：

| 欄位 | 從哪裡來 |
|---|---|
| built-in `<n>` | `stats.lensProvenance` 中 `origin === "builtin"` 的條數 |
| pack `<version>` | collector `layers` 中 `name === "pack"` 那筆的 `version`；其 `status` 為 `absent` 時整段省略，其他非 `ok` 狀態印 `pack（<status>）`（原因在 `warnings`）|
| `+<a>` / `⊕<b>` / `✂`（pack）、`+<c>` / `⊕<d>` / `✂`（user）| harness 不知道 pack 與 user 之分 —— 兩者在 `stats.lensProvenance` 裡都是 `origin === "custom"`。**依順序配對**：第 i 筆 `origin === "custom"` 的條目對應 collector `lenses[i]`，取後者的 `_layer`；再依該條目計：`ignored` 不計入（另列，見下）；其餘 key 不在 `stats.reviewers[].lens` 裡 → `✂`；否則 `added` → `+`、`overridden` → `⊕` |
| 被覆蓋者 | `action === "overridden"` 的條目：`<key>←<該條的 _layer>` |

配對成立的前提（任一不成立，兩邊就會錯位）：

- `customLenses` 只放 collector 的 `lenses`（本 skill 是）；
- 沒有 `disableLenses`（本 skill 沒有）—— 被跳過的 key 不留 provenance 條目；
- 每條的 `key` 與 `focus` 都是**非空白字串** —— harness 在記 provenance **之前**就把 `key` 或 `focus`
  不是字串、或 `trim()` 後為空的條目**安靜丟掉**（`workflows/ensemble-workflow.js` 的 `customs` 過濾），
  不留任何條目、不警告。

所以 `C === N` 才配對。`N > 0` 且 `C === 0` 印上面的「未進入 harness」警告（**不是**歸屬問題，
不要印成 `+0/⊕0`）；`0 < C ≠ N` 時**不要硬配**，改印
`層 ②③ 合計 +<added>/⊕<overridden>/✂<cut>（無法歸屬 pack／user：collector <N> 條、harness 收到 <C> 條，多半是空白 key／focus 被丟掉）`。
`action === "ignored"` 的條目（撞名卻沒標 `override`，一個 agent 都沒派）在 `warnings` 之後逐條列出。

**built-in 被取代要出聲。** 對每一個有 `action === "overridden"` 且 `overrodeFrom === "builtin"` 條目的 key，
在 provenance 行下方印一行警告：`⚠️ built-in lens「<key>」已被 <_layer> 層取代（override）——
本次審閱不含原本的 <key> 檢查`。`<_layer>` 取**該 key 最後一筆** `overridden` 條目的 `_layer` ——
pack 與 user 都 override 同一條 built-in 時會有兩筆（第二筆的 `overrodeFrom` 是 `custom`），實際在跑的是
最後蓋上去的那一層（通常是 user），不是 `overrodeFrom === "builtin"` 的那一筆（pack）。
那個 key 若被上限切掉，改印成上面的 ✂ 警告。`fidelity`／`completeness`／`attribution` 是本 skill 的核心，
被換掉而只在 provenance 行留一個 `⊕`，讀報表的人不會發現。

**沒裝 lens pack 時 provenance 行仍要印**（只顯示 built-in）—— 否則「層 ②③ 沒生效」與「沒裝」
在輸出上無從分辨，#40 就是這樣安靜了一整版。

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
