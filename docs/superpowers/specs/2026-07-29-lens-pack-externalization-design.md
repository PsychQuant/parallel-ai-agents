# Lens pack 外部化 — 設計 spec

- **日期**：2026-07-29
- **相關 issue**：[PsychQuant/parallel-ai-agents#24](https://github.com/PsychQuant/parallel-ai-agents/issues/24)（agents/lens 設定更新現況盤點）
- **狀態**：設計已確認，待寫實作計畫

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

**結論**：submodule 能在開發端提供解耦與版本記錄，但這個價值跨不過散發邊界，使用者端拿到的是空目錄。因此 lens 外部化不採用 submodule。

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

---

## 4. 架構

```
┌─ PsychQuant/pai-lenses（新 repo）───────────────┐
│  lenses/code.csv  academic.csv  lecture.csv    │  ← lens 單一真相源（資料）
│  .claude-plugin/plugin.json（version: 1.0.0）  │  ← 供 marketplace 註冊
└────────────────────────────────────────────────┘
                    ▲ 註冊 + version/sha pin
┌─ .claude-plugin/marketplace.json ──────────────┐
│  plugins: [ parallel-ai-agents, pai-lenses ]   │  ← 兩個獨立版本號
└────────────────────────────────────────────────┘
                    ▼ 各自安裝至 cache
┌─ parallel-ai-agents plugin ────────────────────┐
│  workflows/ensemble-workflow.js  ← 不修改      │
│    PROFILES：17 條 built-in lens（baseline）    │
│  skills/{code,academic,lecture,compose}        │
│    Phase 0 新增：定位 lens pack → 解析 CSV →    │
│    合併 → args.customLenses                    │
└────────────────────────────────────────────────┘
```

**harness 不修改**。`args.customLenses` 介面既有（`ensemble-compose` 已在使用），本設計是在既有接縫上外接，不新增 harness 端概念。

### 資料流（以 `ensemble-code-review` 為例）

1. skill Phase 0 定位 lens pack 的 `lenses/code.csv`
2. 以既有的 `bin/pai-parse-lens-csv` 解析（**不新寫 parser**）
3. 依 D3 規則與 built-in 合併，產生 `customLenses` 與 provenance 資訊
4. 傳入 harness；harness 端行為與現況完全相同

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
| `override` | 否 | `1`/`true`/`yes` → 取代同 key 的 built-in lens；其餘值或空白 → 純新增 |

`override` 的值解析沿用 `needsSrt` 既有的 truthy 慣例，避免同一份 CSV 出現兩套布林寫法。

本設計假設**單一 lens pack**。多個 pack 並存的優先序不在本 spec 範圍。

---

## 6. 合併規則（D3 具體化）

輸入：built-in lens 集合 `B`（來自 `PROFILES[profile]`）、lens pack 列 `P`。

1. 對 `P` 中每一列 `p`：
   - `p.override` 為 truthy 且 `p.key ∈ B` → **取代** `B` 中該條，記入 `overridden` 清單
   - `p.override` 為 truthy 且 `p.key ∉ B` → 當作純新增，並**發出警告**（幾乎必為 typo）
   - `p.override` 非 truthy 且 `p.key ∈ B` → **跳過**該列，並**發出警告**（撞名但未聲明 override）
   - `p.override` 非 truthy 且 `p.key ∉ B` → **新增**，記入 `added` 清單
2. 輸出合併後 lens 集合 + `{added, overridden, warnings}`

此合併為純函數，是本次唯一的新語意，應獨立於 I/O 實作以便測試。

### `ensemble-compose` 的行為

compose 使用 `custom` profile，本身沒有 built-in lens，因此**不會**自動疊加任何 lens pack 檔案；它取得 lens pack 內容的路徑有兩條，兩者都維持既有語意：

- `--include <profile>.<key>`（如 `code.security`）解析的是該 profile **疊加後**的 lens 集合。亦即若 lens pack override 了 `code.security`，compose 拉到的是 override 後的版本 —— `code.security` 一律指「code profile 當前實際生效的 security lens」，不因呼叫端不同而分岐。
- `--lens-file <path>` 維持現況，供臨時、專案級的 lens，不經過 lens pack。

compose 既有的合併順序（base → include → custom，first-wins）與 `--lens` 語意皆不變。

---

## 7. Provenance 輸出（D4）

每次 ensemble 報表開頭輸出一行：

```
lens: built-in 17 + pack pai-lenses v1.2.0 (sha abc1234) → +4 added, 2 overridden (security, methodology)
```

未安裝 lens pack 時：

```
lens: built-in 17 (no lens pack installed)
```

`eval/` 的輸出同樣帶此行，使偵測率數字自帶量測條件。

---

## 8. 失敗處理（D5）

| 情境 | 處置 | 理由 |
|---|---|---|
| lens pack 未安裝 | 靜默使用 built-in | 預期內狀態，非錯誤 |
| 已安裝但無該 profile 的 CSV | 靜默使用 built-in | lens pack 可只覆蓋部分 profile |
| CSV 存在但解析失敗 | **警告** + 使用 built-in 繼續；provenance 標記 `pack: parse failed` | 使用者會誤以為新 lens 生效 |
| `override=true` 但 key 不在 built-in | **警告** + 當純新增處理 | 幾乎必為 typo |
| 空 `key` 或 `focus` 的列 | 跳過（既有 parser 行為） | 與 harness 的 `customLenses` filter 對稱 |

判準：**使用者是否會因為沉默而形成錯誤信念**。會，就必須發出警告。

---

## 9. 測試

| 對象 | 作法 |
|---|---|
| `bin/pai-parse-lens-csv` | 擴充既有 `test/pai-parse-lens-csv.bats`：`override` 欄位的 truthy／falsy／空值／非法值 |
| 合併規則（§6） | 新增單元測試，覆蓋四種分支 + 警告產出；純函數，不觸及 I/O |
| lens pack 定位 | 新增測試：未安裝／已安裝／多版本並存 |
| provenance 行 | 斷言格式與計數正確（含未安裝時的變體） |

既有測試骨架（bats + node）沿用，不另起框架。

---

## 10. 未驗證前提（必須排在實作第一步）

**跨 plugin 檔案定位尚未驗證。** `${CLAUDE_PLUGIN_ROOT}` 只指向 plugin 自身，要讀 `pai-lenses` 的檔案需定位其 cache 路徑，而觀察到 cache 結構不一致：

```
~/.claude/plugins/cache/claude-plugins-official/data/0.1.0/   ← 含版本層
~/.claude/plugins/cache/parallel-ai-agents/parallel-ai-agents/ ← 不含版本層
```

實作計畫的第一個 task 必須是驗證「能否穩定定位另一個已安裝 plugin 的檔案」。

**若驗證失敗**，退回替代形狀：lens pack 改為使用者自行 clone 至約定路徑（如 `~/.claude/pai-lenses/`），skill 讀固定路徑。此時 D1 的 marketplace 版本 pin 失效，版本記錄改以 lens pack repo 內的 `VERSION` 檔 + git SHA 表達，D2–D6 不受影響。

---

## 11. 明確排除範圍

- **umbrella marketplace（`psychquant-claude-plugins`）的 vestigial `parallel-ai-agents` 副本清理** —— issue #24 的另一條 follow-up，屬獨立問題，不在本 spec。
- **`disable` 語意（停用某條 built-in lens）** —— harness 雖已有 `disableLenses` 參數，但目前無實際需求驅動；`override` 成無害 focus 已可覆蓋多數情境。有具體案例再議。
- **`references/builtin-lenses.csv` 的廢除** —— 保留為 `PROFILES` 的唯讀 catalog（`regen-builtin-lenses.sh` 產物），但檔頭須標明「可編輯的 lens 位於 lens pack，編輯本檔無效」。
