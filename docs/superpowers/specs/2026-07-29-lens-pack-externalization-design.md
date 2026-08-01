# Lens pack 外部化 — 設計 spec

- **日期**：2026-07-29
- **相關 issue**：[PsychQuant/parallel-ai-agents#24](https://github.com/PsychQuant/parallel-ai-agents/issues/24)（agents/lens 設定更新現況盤點）
- **狀態**：設計已確認；§10 的唯一未驗證前提已於 2026-08-01 驗證成立，待寫實作計畫

---

## 1. 問題

`references/builtin-lenses.csv` 自 2026-06-01 起沒有新增過 lens 或 profile。根因不是疏於維護，而是**新增或修正一條 lens 的成本過高**：built-in lens 的單一真相源是 `workflows/ensemble-workflow.js` 裡的 `PROFILES` 物件，所以任何 lens 異動都等於改程式碼 → bump plugin 版本 → 同步 marketplace。

第二個問題是**版本座標缺失**。ensemble 的 lens 本質上是量測儀器：`eval/fixtures/` 的偵測率斷言，若前後兩次用不同 lens 量，數字不可比。目前 lens 版本只能用 `parallel-ai-agents` 的 plugin 版本當代理，但那個版本號會因為改 `bin/codex-call`、改 skill 文案而變動，**對 lens 而言是雜訊而非座標**。

目標：讓 lens 定義與 plugin 版本解耦，且讓「這次 review 用了哪一版 lens」成為可稽核的事實。

---

## 2. 關鍵技術約束（設計前查證，非假設）

### 2.1 Workflow runtime 沒有檔案系統存取

`references/regen-builtin-lenses.sh` 檔頭與 `skills/ensemble-compose/SKILL.md` 都明載：

> CSV 由 skill（主 session，有 Read）讀，**不是** harness（runtime 無 FS）。

因此 lens 有兩條互不相通的路徑：

| 路徑 | 載體 | 誰讀 | 異動成本 |
|---|---|---|---|
| built-in | `PROFILES` 物件（JS） | harness runtime | 改程式碼 + bump 版本 |
| 外部 | CSV | skill 層，經 `args.customLenses` 注入 | 改資料檔 |

`references/builtin-lenses.csv` **不驅動任何行為**，它只是 `PROFILES` 的唯讀 catalog；編輯它不產生任何效果。

目前僅 `ensemble-compose` 走外部路徑（`--lens-file`）；`ensemble-code-review` / `ensemble-academic-review` / `ensemble-lecture-review` 三個 profile skill 都不吃 `--lens-file`。

### 2.2 git submodule 在 plugin 散發鏈上會斷掉

實測（2026-07-29，本機 cache）：Anthropic 官方 `data` plugin 使用 submodule，散發到使用者端後未初始化。

```
$ cat ~/.claude/plugins/cache/claude-plugins-official/data/0.1.0/.gitmodules
[submodule "vendor/dbt-agent-skills"]
	path = vendor/dbt-agent-skills
	url = https://github.com/dbt-labs/dbt-agent-skills.git

$ git -C ~/.claude/plugins/cache/claude-plugins-official/data/0.1.0 submodule status
-58c8f09b740370cb1e888b9ea7585ec89c6d2a82 vendor/dbt-agent-skills
```

開頭的 `-` 是 git 對「submodule 未初始化」的標記；該目錄實際為空。官方 plugin marketplace 文檔全篇未提及 `submodule`，亦即不在支援契約內。

**結論**：submodule 提供的解耦與版本記錄跨不過散發邊界，使用者端拿到的是空目錄。因此 lens 外部化不採用 submodule。

更根本的理由見 D7：即便只把 submodule 用於開發端，它在本設計中也**沒有任何 build 或 runtime 依賴**，屬於純成本。

### 2.3 marketplace 原生提供等價能力

`marketplace.json` 的 plugin source（`github` / `url` / `git-subdir`）均支援 `ref` 與 `sha`；文檔明載「When both `ref` and `sha` are set, the `sha` is the effective pin」。這在語義上等同 submodule 的「指向外部 repo 的確切 commit」，差別在於它跨得過散發邊界，且使用者端可獨立更新（`/plugin update`）。

---

## 3. 設計決定

| # | 決定 | 已排除的替代方案 |
|---|---|---|
| D1 | lens 抽成獨立 repo，經 marketplace 註冊為**第二個 plugin**（`pai-lenses`），以 `version` / `sha` 做版本記錄 | git submodule（見 2.2）；`git-subdir` 指向本 repo 子目錄（解耦不完整） |
| D2 | built-in `PROFILES` **保留為 baseline**，lens pack **疊加**其上 | 全外部化（PROFILES 清空）—— 會使 harness 失去 self-contained fallback |
| D3 | 撞名時走**顯式 `override` 欄位**：未標記則純新增（撞名跳過並警告），標記 `true` 才取代 built-in | last-wins（靜默換掉量尺）；維持 first-wins（改不動 built-in，痛點只解一半） |
| D4 | 報表輸出 **provenance 行**，記錄 lens pack 版本與被 override 的 lens | 不記錄（等於放棄本設計的主要價值之一） |
| D5 | 缺席與損壞**分開處理**：沒裝 → 靜默；裝了但壞 → 警告 | 一律靜默降級（製造「以為生效但沒生效」的無跡象失敗） |
| D6 | 三個 profile skill 都接上 lens pack，不只 `ensemble-compose` | 只擴 compose —— 日常主要路徑拿不到好處 |

| D7 | **不使用 git submodule**。lens pack 與本 repo 為**平行 repo**；開發端的並排需求由 VS Code multi-root workspace 滿足 | submodule 掛 `repos/lenses`（曾列入考慮，見下方 D7 補述） |
| D8 | 新增**第三層 user-level lens**（`~/.claude/pai-lenses/*.csv`），疊加於 lens pack 之上，三層共用同一套 `override` 語意 | 只做兩層 —— 使用者將無法擁有不被 `/plugin update` 覆蓋的自訂 lens |

### D8 補述：為何需要第三層

lens pack 安裝後位於 `~/.claude/plugins/cache/`，那是**受管理的靜態副本** —— 使用者在該處的修改會被下一次 `/plugin update` 覆寫。因此「使用者擁有自己的 lens」這個需求，**無法由 D1 的 repo 拆分滿足**，兩者正交：D1 解決發布節奏與版本座標，D8 解決使用者端的可寫性。

第三層另有一個結構上的好處：它的路徑是固定的 `~/.claude/pai-lenses/`，**不依賴跨 plugin 檔案定位**（§10 的未驗證前提）。因此若 §10 驗證失敗，lens pack 可退化為「使用者自行 clone 至 `~/.claude/pai-lenses/`」，與第三層共用同一套讀取與合併機制，設計不需重做。

### D7 補述：為何連開發端也不用 submodule

submodule 的正當判準只有一條：**parent repo 在 build 或 run 時是否需要讀該 repo 的檔案。**本設計中答案是「否」——依 D1／§4，skill **永遠**從 marketplace 安裝的 pai-lenses 讀取，plugin 目錄內不存在 lens 來源。

曾為 submodule 保留的三個開發端理由，逐一檢視後皆不成立：

| 理由 | 檢視結果 |
|---|---|
| 編輯方便 | 平行 repo 兩個目錄並排同樣方便，且零同步成本 |
| CI 整合測試 | 合併邏輯**應以 fixture CSV 測試**（受控輸入），不應吃真實 lens repo —— 真實資料會變動，測試將 flaky。此理由本身即為誤 |
| 版本錨點 | 被上一條取代：測試用的 fixture 位於本 repo 內、已受 git 追蹤，「此版 code 以何種 lens 輸入測試」已被記錄 |

成本面：submodule pointer 落後時 `git status` 即為 dirty，會在與程式無關的情況下卡住 release 流程，並養成「先 bump 再說」的習慣 —— 每個手動同步點都是一條會安靜損壞的縫。

**注意**：此判準是本設計專屬，非通則。`bestOCR` 的 `repos/measureOCR` 使用 submodule 是正確的 —— 那裡 parent 確實在跑量測時讀該 repo，且 pin 本身就是目的（pre-registration 凍結）。同一個工具，在有依賴時是資產，在無依賴時是純成本。

### D1 補述：獨立 repo 的兩個理由

**理由一：版本座標。** lens 是量測儀器，需要獨立於 plugin 版本的版本號（見 §1）。

**理由二：外部貢獻的出口成本。** 若 lens 留在 `parallel-ai-agents` 內，接受一條外部貢獻的 lens **等於要發一次 plugin release** —— 使用者得 `/plugin update parallel-ai-agents`，連帶吃下所有無關的 code 變更。這使維護者傾向不收 lens PR，等於 issue #24 的痛點換個入口再現。獨立 repo 讓「收一條 lens」只需 bump lens pack 版本。

次要但實際的效果：目前 repo 內有**三個看起來都像 lens 的地方** —— `PROFILES`（JS，唯一真正生效）、`references/builtin-lenses.csv`（改了無效的 catalog）、`references/example-lenses.csv`（範本）。外部貢獻者有相當機率改到無效的那個，通過 review 後卻毫無效果。獨立 repo 內不存在「假的 lens 檔案」，順帶消除此陷阱。

兩個理由指向同一件事：**lens 的發布不應綁在 plugin 的發布上。**

---

## 4. 架構

### 4.1 散發佈局

```
┌─ PsychQuant/pai-lenses（新 repo，平行於本 repo）┐
│  lenses/code.csv  academic.csv  lecture.csv    │  ← 上游 lens 集（資料）
│  .claude-plugin/plugin.json（version: 1.0.0）  │  ← 供 marketplace 註冊
└────────────────────────────────────────────────┘
                    ▲ 註冊 + version/sha pin
┌─ .claude-plugin/marketplace.json ──────────────┐
│  plugins: [ parallel-ai-agents, pai-lenses ]   │  ← 兩個獨立版本號
└────────────────────────────────────────────────┘
                    ▼ 各自安裝至 cache
┌─ parallel-ai-agents plugin ────────────────────┐
│  workflows/ensemble-workflow.js  ← 不修改      │
│  skills/{code,academic,lecture,compose}        │
│    Phase 0：三層疊加 → args.customLenses       │
└────────────────────────────────────────────────┘
```

### 4.2 三層 lens 解析（skill Phase 0，由下而上疊加）

```
 ①  built-in PROFILES        workflows/ensemble-workflow.js
     17 條 baseline lens；harness 自帶，永遠存在
                  ↓ 疊加（D3 override 語意）
 ②  lens pack               ~/.claude/plugins/cache/<mkt>/pai-lenses/<ver>/lenses/<profile>.csv
     上游發布；有獨立版本號；受 /plugin update 管理
                  ↓ 疊加（同一套 override 語意）
 ③  user-level              ~/.claude/pai-lenses/<profile>.csv
     使用者自有；固定路徑；不受 /plugin update 覆寫
                  ↓
     合併結果 → args.customLenses → harness（不修改）
```

三層皆為**可選**：② 未安裝、③ 不存在時各自靜默略過（§8），① 保證系統永遠有可用的 lens。

**harness 不修改**。`args.customLenses` 介面既有（`ensemble-compose` 已在使用），本設計是在既有接縫上外接，不新增 harness 端概念。

### 4.3 資料流（以 `ensemble-code-review` 為例）

1. skill Phase 0 取得 `PROFILES.code` 作為起始集合
2. 定位 lens pack 的 `lenses/code.csv`；存在則以既有的 `bin/pai-parse-lens-csv` 解析（**不新寫 parser**）並依 §6 疊加
3. 讀 `~/.claude/pai-lenses/code.csv`；存在則同樣解析並疊加
4. 產生 `customLenses` 與 provenance 資訊，傳入 harness；harness 端行為與現況完全相同

---

## 5. CSV schema

**一個 profile 一個檔**（`lenses/code.csv` 對應 `code` profile），profile 由檔名決定，檔內**不含** `profile` 欄。這讓既有的 `bin/pai-parse-lens-csv` 完全不需要改動 —— 它本來就只讀 `key` / `focus` / `needsSrt`，不認得 `profile` 欄。

在既有欄位之上新增一個可選欄 `override`：

```csv
key,focus,needsSrt,override
security,"新版攻擊者視角：…",false,true
api-compat,"檢查對外 API 破壞性變更…",false,
```

| 欄位 | 必填 | 語意 |
|---|---|---|
| `key` | 是 | lens 識別碼；空值該列跳過（既有行為） |
| `focus` | 是 | lens 的審閱指示；空值該列跳過（既有行為） |
| `needsSrt` | 否 | `1`/`true`/`yes`（不分大小寫）→ true（既有行為） |
| `override` | 否 | `1`/`true`/`yes` → 取代**較低層**同 key 的 lens；其餘值或空白 → 純新增 |

`override` 的值解析沿用 `needsSrt` 既有的 truthy 慣例，避免同一份 CSV 出現兩套布林寫法。

**user-level（層 ③）使用完全相同的 schema 與檔名慣例** —— `~/.claude/pai-lenses/code.csv` 的格式與 lens pack 的 `lenses/code.csv` 無異。使用者可直接複製一份 lens pack 的檔案來改，不需學第二套格式。

本設計假設**單一 lens pack**。多個 pack 並存的優先序不在本 spec 範圍。

---

## 6. 合併規則（D3 具體化）

合併是一個**逐層折疊**：以 built-in 為起始累積集合，依序將每個上層來源疊加上去。

- 起始集合 `A₀ = PROFILES[profile]`（層 ①）
- 來源序列 `S = [lens pack 列（層 ②）, user-level 列（層 ③）]`；缺席的來源直接略過

對 `S` 中每個來源的每一列 `p`，針對**當前累積集合** `A`：

| `p.override` | `p.key ∈ A` | 動作 |
|---|---|---|
| truthy | 是 | **取代** `A` 中該條；記入 `overridden`（標註來源層） |
| truthy | 否 | 當作純新增，並**發出警告**（幾乎必為 typo） |
| 非 truthy | 是 | **跳過**該列，並**發出警告**（撞名但未聲明 override） |
| 非 truthy | 否 | **新增**；記入 `added`（標註來源層） |

輸出：合併後 lens 集合 + `{added, overridden, warnings}`，每筆均帶來源層標記。

**關鍵語意**：判定對象是「**當前累積集合**」而非「built-in」。因此 user-level 要覆蓋 lens pack 的某條 lens，同樣必須寫 `override=true` —— 覆蓋任何已存在的 lens 都需要顯式聲明，不論它來自哪一層。規則一致，不因層級而分岐。

此折疊為純函數，是本次唯一的新語意，應獨立於 I/O 實作以便測試。其形式亦使未來增層（如專案級 lens，見 §11）只需延長來源序列 `S`，無須修改合併邏輯。

### `ensemble-compose` 的行為

compose 使用 `custom` profile，本身沒有 built-in lens，因此**不會**自動疊加任何 lens pack 檔案；它取得 lens pack 內容的路徑有兩條，兩者都維持既有語意：

- `--include <profile>.<key>`（如 `code.security`）解析的是該 profile **疊加後**的 lens 集合。亦即若 lens pack override 了 `code.security`，compose 拉到的是 override 後的版本 —— `code.security` 一律指「code profile 當前實際生效的 security lens」，不因呼叫端不同而分岐。
- `--lens-file <path>` 維持現況，供臨時、專案級的 lens，不經過 lens pack。

compose 既有的合併順序（base → include → custom，first-wins）與 `--lens` 語意皆不變。

---

## 7. Provenance 輸出（D4）

每次 ensemble 報表開頭輸出 lens 組成，三層皆列出：

```
lens: 22 active = built-in 17 + pack pai-lenses v1.2.0 (abc1234) + user
  added:       api-compat(pack), migration-safety(pack), team-style(user)
  overridden:  security(pack), writing(user)
```

三層皆缺席時：

```
lens: 17 active = built-in only (no lens pack, no user lenses)
```

**每筆 added / overridden 均標註來源層**。這對除錯是必要的：當某條 lens 的行為不如預期，第一個要回答的問題就是「這條是誰定義的」——沒有來源標記，三層疊加會變成無法回溯的黑箱。

`eval/` 的輸出同樣帶此區塊，使偵測率數字自帶量測條件。**user-level lens 會影響 eval 結果**，因此跑 eval 時這一行必須一併記錄，否則跨機器的偵測率數字不可比。

---

## 8. 失敗處理（D5）

| 情境 | 處置 | 理由 |
|---|---|---|
| lens pack 未安裝（層 ②） | **靜默**略過該層 | 預期內狀態，非錯誤 |
| `~/.claude/pai-lenses/` 不存在（層 ③） | **靜默**略過該層 | 多數使用者不會有自訂 lens |
| 某層存在但缺該 profile 的 CSV | **靜默**略過該層 | 各層皆可只覆蓋部分 profile |
| CSV 存在但解析失敗 | **警告** + 略過該層後繼續；provenance 標記 `<layer>: parse failed` | 使用者會誤以為新 lens 生效 |
| `override=true` 但 key 不在當前累積集合 | **警告** + 當純新增處理 | 幾乎必為 typo |
| 空 `key` 或 `focus` 的列 | 跳過（既有 parser 行為） | 與 harness 的 `customLenses` filter 對稱 |

判準：**使用者是否會因為沉默而形成錯誤信念**。會，就必須發出警告。

注意「靜默」與「警告」的分界不隨層級改變，只隨**該狀態是否為預期內**而定：層 ③ 不存在是預期內（靜默），層 ③ 存在但寫壞了不是（警告）。

---

## 9. 測試

| 對象 | 作法 |
|---|---|
| `bin/pai-parse-lens-csv` | 擴充既有 `test/pai-parse-lens-csv.bats`：`override` 欄位的 truthy／falsy／空值／非法值 |
| 折疊規則（§6） | 新增單元測試，覆蓋四種分支 × 警告產出；**含三層案例**：層 ③ override 層 ②、層 ③ 未聲明 override 而撞層 ② 的 key（應跳過並警告）。純函數，不觸及 I/O |
| 來源定位 | 層 ②：未安裝／已安裝／多版本並存；層 ③：目錄不存在／存在但無該 profile |
| provenance 區塊 | 斷言格式、計數、**來源層標記**正確（含三層全缺席的變體） |

**測試輸入一律使用 fixture CSV**，不讀取真實 lens pack 或使用者的 `~/.claude/pai-lenses/` —— 後者會讓測試結果依賴執行機器的個人設定而 flaky。此點亦為 D7 判定 submodule 無 CI 依賴的根據。

既有測試骨架（bats + node）沿用，不另起框架。

---

## 10. 跨 plugin 檔案定位（**已於 2026-08-01 驗證成立**）

原本列為「動工前必須先驗、驗不過就要改 D1 形狀」的前提。**已驗證：成立，不需退路。**

### 更正：原本說「結構不一致」是判斷錯誤

spec 初稿寫：

> 觀察到 cache 結構不一致：`claude-plugins-official/data/0.1.0/`（含版本層）vs `parallel-ai-agents/parallel-ai-agents/`（不含版本層）

**這個觀察是錯的。** 錯因是當時用 `find -maxdepth 3` 列舉，`parallel-ai-agents/parallel-ai-agents` 是 `<marketplace>/<plugin>` 這個**中間層**，版本目錄在它底下、超出 maxdepth。實際列舉：

```
~/.claude/plugins/cache/parallel-ai-agents/parallel-ai-agents/2.20.0
~/.claude/plugins/cache/codex-pro/codex-pro/0.7.0
~/.claude/plugins/cache/issue-driven-development/issue-driven-dev/2.102.2
```

結構是**一致的** `<marketplace>/<plugin>/<version>/`。

### 定位方法（已有 production 先例）

```bash
DIR=$(ls -d ~/.claude/plugins/cache/<marketplace>/<plugin>/*/ 2>/dev/null \
      | grep -E '/[0-9]+\.[0-9]+\.[0-9]+/$' | sort -V | tail -1)
```

這**不是**為本 spec 發明的方法 —— `issue-driven-dev` 的 `idd-verify` 已在 production 用它解析兩個依賴（pai ensemble engine 與 codex-pro governance defaults），且帶最低版本閘門。2026-08-01 實測三個不同 marketplace 全部解析成功。

### Precondition：lens pack 必須有 `version` 欄位

唯一的 edge case：**`plugin.json` 缺 `version` 欄位時，cache 目錄名是 `unknown` 而非 semver**，semver glob 會漏掉它。實例：`claude-plugins-official` 底下的 `mcp-server-dev` / `feature-dev` / `context7` 等（皆確認 `plugin.json` 無 `version`）。

對本設計無妨 —— D1 本來就要求 lens pack 有版本號（版本座標是它的主要價值之一）。但這使「有 `version` 欄位」從**慣例**升格為**功能性前提**，須寫進 lens pack 的 repo README 與 CI 檢查。

### 層 ③ 不受影響

層 ③（user-level）路徑固定為 `~/.claude/pai-lenses/`，不經任何 plugin 定位邏輯 —— 這一點在驗證前後都成立。

### 原退路（保留紀錄，現已不需要）

若定位不可行，原計畫是讓 lens pack 退回「使用者自行 clone 至 `~/.claude/pai-lenses/`」、與層 ③ 共用機制，代價是 D1 的 marketplace 版本 pin 失效。**驗證通過後不採用**，此段僅作決策紀錄保留。

---

## 11. 明確排除範圍

- **umbrella marketplace（`psychquant-claude-plugins`）的 vestigial `parallel-ai-agents` 副本清理** —— issue #24 的另一條 follow-up，屬獨立問題，不在本 spec。
- **`disable` 語意（停用某條 built-in lens）** —— harness 雖已有 `disableLenses` 參數，但目前無實際需求驅動；`override` 成無害 focus 已可覆蓋多數情境。有具體案例再議。
- **`references/builtin-lenses.csv` 的廢除** —— 保留為 `PROFILES` 的唯讀 catalog（`regen-builtin-lenses.sh` 產物），但檔頭須標明「可編輯的 lens 位於 lens pack，編輯本檔無效」。
- **專案級 lens（`.claude/pai-lenses/`，第四層）** —— §6 的折疊形式已使增層只需延長來源序列，但目前無需求驅動。待有「不同專案要不同 lens」的具體案例再議。
- **多個 lens pack 並存的優先序** —— 本設計假設單一 pack（§5）。
