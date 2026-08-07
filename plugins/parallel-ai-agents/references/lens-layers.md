# 三層 lens 疊加（#29）

所有 ensemble skill 的 lens 集合由**三層**疊出來。這份文件是四個 skill 共用的契約 ——
**要改行為就改這裡**，不要在個別 SKILL.md 裡各寫一份（三份文案會漂移，那正是 #29
診斷時記下的風險）。同 `codex-governance.md` 的引用模式。

| 層 | 來源 | 誰讀它 |
|---|---|---|
| ① built-in | `workflows/ensemble-workflow.js` 的 `PROFILES` | **harness 自己**（workflow runtime 無檔案系統，讀不到任何 CSV） |
| ② lens pack | `pai-lenses` plugin 的 `lenses/<profile>.csv` | skill（Phase 2） |
| ③ user | `~/.claude/pai-lenses/<profile>.csv` | skill（Phase 2） |

層 ① 由 harness 供給，層 ②③ 由 skill 蒐集後經 `args.customLenses` 送進去。**陣列順序即優先序**。

## 我想加一條 lens，該去哪？

| 你的情況 | 去哪 | 怎麼做 |
|---|---|---|
| 只想自己用 | 層 ③ user | 編 `~/.claude/pai-lenses/<profile>.csv`，立即生效，不必發布 |
| 想貢獻，且是**既有** profile 的 lens | 層 ② lens pack | 編 `plugins/pai-lenses/lenses/<profile>.csv` + bump **兩處** version（`plugin.json` 與 `marketplace.json` 對應 entry）|
| 想貢獻，且需要**新 profile** | 層 ① built-in | 改 `workflows/ensemble-workflow.js` 的 `PROFILES` → 跑 `references/regen-builtin-lenses.sh` → bump 兩處 version |

> ⚠️ **「profile 是否存在」要查真源，不要查 `builtin-lenses.csv`**：該投影由 lens 產生，
> `lenses: []` 的 profile（如 `custom`）在裡面一列都沒有。用 `bin/pai-list-profiles`。
| 本機已經寫好，想一次送上去 | — | `/ensemble-contribute-lenses`（掃 user 層、判定目標層、開 PR） |

> ⚠️ **`references/builtin-lenses.csv` 是 generated 的唯讀投影** —— 編它不改變任何行為。
> 真源是 `PROFILES`。這個檔存在只為了讓人「看得到目前有哪些 lens」。

> ⚠️ **新 profile 不能只靠 lens pack**：CSV 描述得了 lens，描述不了 profile 級的
> `title` / `daFocus` / `codexDefault`。harness 的 `PROFILES` 沒有該 key 時，用它呼叫會回
> `unknown ensemble profile` 且 **0 個 agent 被派出**，workflow 卻仍「成功」結束。

## Skill 該做的事

### 1. 蒐集（Phase 2，呼叫 Workflow 之前）

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/pai-collect-lens-layers" <profile>
```

`<profile>` = 該 skill 的 profile 名（`code` / `academic` / `lecture`；`ensemble-compose`
用 `--base` 的值，預設不帶則跳過本步）。

輸出：

```json
{
  "lenses":   [{"key":"…","focus":"…","needsSrt":true?,"override":true?,"_layer":"pack"|"user"}],
  "layers":   [{"name":"pack"|"user","path":…,"version":…,"status":"…"}],
  "warnings": ["…"]
}
```

把 `lenses` **原樣** append 進 `args.customLenses`（`override` 欄必須保留 —— 它就是取代語意的載體；
`_layer` 留著無妨，harness 只讀 `key`/`focus`/`needsSrt`/`override`）。若 skill 另有自己的
custom lens（`--lens` / `--lens-file`），那些排在**後面**（使用者當下打的指令優先序最高）。

### 2. `profile` 維持原值 —— 不要改成 `"custom"`

```json
{ "profile": "code", "customLenses": [ …層 ②③… ] }
```

**這一點是刻意的，不是疏漏。** 把 profile 換成 `"custom"` 會讓 built-in lens 不再是 baseline，
連帶換掉 `profile.title` —— 而 title 被寫進 reviewer、devil's-advocate、Codex 三種 prompt 的
四個位置，且**沒有 `args` 覆寫路徑**。改了之後每次審閱都會對所有 agent 自稱「自訂 ensemble」，
是安靜的 prompt 品質退化。

### 3. 撞名判定全在 harness，skill 不去重

- 預設 **first-wins**：同 key 時先到的勝（built-in → include → 層 ② → 層 ③）
- CSV 標了 `override`（`1`/`true`/`yes`）的才**原位取代**先前同 key 的 lens
- 因此層 ③ 要蓋層 ② 同樣需要 `override` —— 判定對象是**當前累積集合**，不是 built-in

單一去重點才不會兩邊語意漂移。skill 只搬運。

### 4. 報表印 provenance 行

合併/報表階段（各 skill 的 Phase 4，`ensemble-compose` 為 Phase 3）在 findings 表**之前**印一行：

```
Lens 來源：built-in <n> 條 · pack <version> +<a>/⊕<b> · user +<c>/⊕<d>
（⊕ = 覆蓋，被覆蓋者：security←pack）
```

資料來自兩處：`pai-collect-lens-layers` 的 `layers`（哪幾層在、版本多少）與 harness 回傳的
`stats.lensProvenance`（每個 lens 的處置：`added` / `overridden` / `ignored`，`overrodeFrom` 指出被誰蓋）。

**沒裝 lens pack 時這行仍要印**（只會顯示 built-in），這樣「今天的報表跟昨天不同」永遠有據可查 ——
量測儀器換了刻度卻不說，是 eval 數字不可比的根源。

### 5. 警告照實印

`warnings` 非空 → 在 provenance 行下方逐條列出。**缺席是靜默的，損壞不是**（spec D5）：

| status | 意思 | 印警告？ |
|---|---|---|
| `absent` | 沒裝 / 沒這個檔 | ❌ 靜默 |
| `ok` | 正常 | ❌ |
| `empty` | 檔案在、卻解析出 0 條（多半 header 打錯） | ✅ |
| `corrupt` | 解析器非零退出 | ✅ |
| `unversioned` | 裝了 `pai-lenses` 但無 semver 目錄（`plugin.json` 缺 `version`） | ✅ |

`empty` 與 `unversioned` 是刻意加的防安靜失敗：前者會讓一個存在的檔案什麼都不貢獻，
後者會讓「裝了但定位不到」看起來像「沒裝」。

## Lens pack 的 CSV 格式

```csv
key,focus,needsSrt,override
perf,"檢查每個 hot path 的時間複雜度與不必要的重算",,
security,"（取代內建的 security lens）……",,true
```

- `key` / `focus` 必填，其餘可選
- `needsSrt` / `override` 用同一套 truthy 判準：`1` / `true` / `yes`（不分大小寫）
- **一個 profile 一個檔**，profile 由檔名決定（`lenses/code.csv`）
- 解析一律走 `bin/pai-parse-lens-csv`（BOM-safe、csv 模組、bats 覆蓋），**不可** naive split ——
  focus 是含逗號與中文標點的長 prose

`override` 的語意是「**我要取代那一條**」，不是「我比較重要」。不標記 = 純新增。標記需要理由，
因為它會讓一條經過調校的 built-in lens消失。

## 相關

- `references/builtin-lenses.csv` — 層 ① 的唯讀 catalog（**編它不改變任何行為**；真源是 `PROFILES`）
- `bin/pai-collect-lens-layers` — 層 ②③ 的蒐集器
- `bin/pai-parse-lens-csv` — CSV 解析的單一真相源
- 設計 spec：`docs/superpowers/specs/2026-07-29-lens-pack-externalization-design.md`（D1–D8）
