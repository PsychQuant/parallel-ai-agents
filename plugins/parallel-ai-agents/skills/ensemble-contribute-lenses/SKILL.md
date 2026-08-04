---
name: ensemble-contribute-lenses
description: |
  把本機 user 層的 lens 送回公共層並開 PR。掃 ~/.claude/pai-lenses/*.csv，
  比對 built-in（PROFILES）與 lens pack（plugins/pai-lenses/lenses/），
  判定每條 lens 該進哪一層，產出變更後開 PR。
  Use when: 自己寫的 lens 想貢獻回 repo、或想知道本機有哪些 lens 還沒回流。
argument-hint: "[--profile <name>] [--dry-run] [--include-override]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - AskUserQuestion
---

# /ensemble-contribute-lenses — 把本機 lens 送回公共層

三層 lens 疊加（`references/lens-layers.md`）裡，層 ③（user）原本是單向終點：寫在
`~/.claude/pai-lenses/<profile>.csv` 的 lens 只有自己機器吃得到。這個 skill 是它的出口。

## 兩個目標層，判準不同

| 目標 | 何時 | 改什麼 |
|---|---|---|
| **層 ②** lens pack | 為**既有** profile 加 lens | `plugins/pai-lenses/lenses/<profile>.csv` + bump `plugin.json` version |
| **層 ①** built-in | 需要**新 profile**，或需要 profile 級語意 | `workflows/ensemble-workflow.js` 的 `PROFILES` + 跑 `references/regen-builtin-lenses.sh` |

**判準是「能不能只用一條 lens 表達」**：

- lens pack 的 CSV 只能描述 lens 本身（`key` / `focus` / `needsSrt` / `override`）。
- profile 級的東西——`title`、`daFocus`、`codexDefault`——**只存在於 `PROFILES`**。CSV 表達不了。
- 更關鍵：harness 的 `PROFILES` 沒有某個 profile key 時，用該 profile 呼叫會回
  `unknown ensemble profile` 且 **0 個 agent 被派出**，workflow 卻仍「成功」結束。
  把新 profile 誤送層 ② 的後果是這個安靜失敗，所以**判錯必須 fail-loud，不可猜**。

## 執行流程

### Phase 1：盤點本機 lens

```bash
USER_DIR="${PAI_USER_LENS_DIR:-$HOME/.claude/pai-lenses}"
[ -d "$USER_DIR" ] || { echo "本機無 $USER_DIR — 沒有可貢獻的 lens。"; exit 0; }
ls "$USER_DIR"/*.csv 2>/dev/null || { echo "$USER_DIR 下沒有 .csv。"; exit 0; }
```

每個檔名即 profile（一檔一 profile 是 user 層的既定格式，見 `lens-layers.md`）。
解析一律走 `bin/pai-parse-lens-csv`，**不可** naive split——`focus` 是含逗號與中文標點的長 prose。

### Phase 2：比對，找出本機獨有的 lens

對每個 `<profile>.csv` 的每條 lens：

```bash
# 層 ① 是否已有同 key？（真源是 PROFILES；builtin-lenses.csv 是它的唯讀投影，查詢用它即可）
grep -E "^${profile},${key}," plugins/parallel-ai-agents/references/builtin-lenses.csv

# 層 ② 是否已有同 key？
grep -E "^${key}," plugins/pai-lenses/lenses/${profile}.csv 2>/dev/null
```

三種結果：

| 比對結果 | 處置 |
|---|---|
| 兩層都沒有 | **候選**，進 Phase 3 |
| 層 ② 已有同 key 且 focus 相同 | 已回流，略過（並提示本機該條可刪） |
| 層 ①/② 已有同 key 但 focus 不同 | 這是**修改**不是新增，走 Phase 4 的 override 路徑 |

### Phase 3：判定目標層

對每個候選：

```
該 lens 的 profile 是否已存在於 PROFILES？
├── 是 → 目標 = 層 ②（改 lenses/<profile>.csv）
└── 否 → 目標 = 層 ①（新 profile，改 PROFILES）
         └── 但 CSV 只有 lens 資訊，profile 級欄位（title / daFocus / codexDefault）
             缺失 → 必須向使用者索取，不可代填
```

**新 profile 一律要問**。`daFocus` 決定 devil's advocate 盯什麼、`codexDefault` 決定要不要跑跨模型 leg，兩者都不是能從 lens 的 `focus` 推導出來的。代填等於替使用者做設計決定。

### Phase 4：`override` 的特別處理

標了 `override` 的 lens 語意是「**取代**某條 built-in lens」，不是「新增」。貢獻到公共層等於
**替所有使用者移除一條調校過的 lens**。

預設**不送**。要送必須：

1. 用 `AskUserQuestion` 確認，並在問題中列出被取代的那條 built-in lens 的 `focus` 全文
2. 取得取代理由（一句話），寫進 PR body
3. `--include-override` flag 才會把它列入候選

沒有理由就不送——這條規則存在是因為 override 的傷害是靜默的：被取代的 lens 消失後，
沒有人會收到通知。

### Phase 5：產出變更

**層 ②**（多數情形）：

```bash
# 附加到既有 CSV（保持 header 不動）
# 欄位順序：key,focus,needsSrt,override
# bump plugin.json 的 version（新增 lens 是 minor）
```

**層 ①**（新 profile）：

```bash
# 1. 在 workflows/ensemble-workflow.js 的 PROFILES 加 entry
# 2. 跑 references/regen-builtin-lenses.sh 重生唯讀 catalog
#    （順序不可反 —— CSV 是投影，改它不影響行為）
# 3. bump plugins/parallel-ai-agents 的 version
```

### Phase 6：驗證後開 PR

```bash
# lens pack 的自我檢查（semver version + 每個 CSV 至少一條 lens）
(cd plugins/pai-lenses && python3 scripts/validate.py)

# 層 ① 變更時另需確認 catalog 不 stale（CI 也會擋）
bash plugins/parallel-ai-agents/references/regen-builtin-lenses.sh
git diff --exit-code -- plugins/parallel-ai-agents/references/builtin-lenses.csv
```

PR body 須含：每條 lens 的來源（本機哪個 profile）、目標層與**理由**、override 的取代理由（若有）。

`--dry-run` 只印計畫不動檔案、不開 PR。

## 為什麼是單一 repo 的一個 PR

`pai-lenses` 曾是獨立 repo，貢獻要跨兩個 repo 判斷該去哪、開兩個 PR。#33 裁定它是本 repo 的
官方增補層並併入 `plugins/pai-lenses/` 後，兩層的變更落在同一個 PR，這個 skill 也因此不需要
處理跨 repo 的分支與版本對齊。

## 反模式

| 想做的 | 為什麼不行 |
|---|---|
| 直接編 `references/builtin-lenses.csv` | 那是 generated 的唯讀投影，改它不改變任何行為。真源是 `PROFILES` |
| 新 profile 送層 ② | harness 的 `PROFILES` 沒有該 key → `unknown ensemble profile`、0 agent 派出，且 workflow 仍「成功」結束 |
| 代填 `daFocus` / `codexDefault` | 那是設計決定不是格式轉換。缺就問 |
| 自動送出 `override` lens | 會替所有使用者移除一條調校過的 lens，且無人收到通知 |
| 送完就刪本機檔 | PR 未 merge 前刪掉會兩頭落空。提示使用者，由他決定何時清 |
