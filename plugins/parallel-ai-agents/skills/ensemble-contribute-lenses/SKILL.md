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
| **層 ②** lens pack | 為**既有** profile 加 lens | `plugins/pai-lenses/lenses/<profile>.csv` + bump **兩處** version（`plugin.json` **與** `marketplace.json` 對應 entry）|
| **層 ①** built-in | 需要**新 profile**，或需要 profile 級語意 | `plugins/parallel-ai-agents/workflows/ensemble-workflow.js` 的 `PROFILES` + 跑 `references/regen-builtin-lenses.sh` + bump 兩處 version |

> **「bump」永遠是兩處**：只改 `plugin.json` 而漏 `marketplace.json`，PR merge 後使用者
> `/plugin update` 收不到新版 —— 而且沒有任何錯誤訊息。見 root `CLAUDE.md` 的「版本同步（CRITICAL）」。

**判準是「能不能只用一條 lens 表達」**：

- lens pack 的 CSV 只能描述 lens 本身（`key` / `focus` / `needsSrt` / `override`）。
- profile 級的東西——`title`、`daFocus`、`codexDefault`——**只存在於 `PROFILES`**。CSV 表達不了。
- 更關鍵：harness 的 `PROFILES` 沒有某個 profile key 時，用該 profile 呼叫會回
  `unknown ensemble profile` 且 **0 個 agent 被派出**，workflow 卻仍「成功」結束。
  把新 profile 誤送層 ② 的後果是這個安靜失敗，所以**判錯必須 fail-loud，不可猜**。

## 執行

**整條流程是一支腳本，不是一串 bash 區塊。** 直接呼叫：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/pai-contribute-lenses" [--profile NAME] [--dry-run] [--include-override]
```

它做完所有**機械**的部分：定位可修改的 repo 工作樹（在 repo 內就用它；有 push 權 `gh repo clone`；
外部貢獻者 `gh repo fork --clone`）→ 走訪 `~/.claude/pai-lenses/*.csv`（檔名即 profile）→ 用
`bin/pai-parse-lens-csv` 解析並與層 ①② 比對 → 用 `bin/pai-list-profiles` 查真源判定目標層 →
附加到 pack CSV → bump **兩處** version → **驗證（真正的閘門）** → branch / commit / push /
`gh pr create`。

> **為什麼是腳本**（#33 verify R1 + R2）：前兩版把流程寫成本文件裡的 fenced bash blocks，
> 兩輪 6-AI verify 都判 FAIL。R2 明確指出形式本身不可行 —— AI 逐個 block 呼叫 Bash 時**每次
> 都是新 shell**，`REPO_ROOT` / `USER_DIR` 到下一個 block 全是空字串；`profile` 從未被賦值；
> 沒有 `set -e`，所以「驗證」失敗後仍會照常 commit / push / 開 PR。補指令不會讓它變成可執行，
> 這是形式問題不是內容問題。一個 process 內完成就沒有這些問題，而且可以被 bats 測。

### 你（skill）要做的：回答腳本問不出來的事

腳本**不代填任何設計決定**。遇到需要判斷的地方它 **exit 3** 並印出缺什麼，你負責問使用者、
然後帶著答案重跑：

| exit 3 的原因 | 你要做的 |
|---|---|
| 本機 CSV 的 profile 不在 `PROFILES` | 這是**新 profile**，只能進層 ①。用 `AskUserQuestion` 取得 `title` / `daFocus` / `codexDefault`，**手動**改 `workflows/ensemble-workflow.js` 的 `PROFILES`、跑 `references/regen-builtin-lenses.sh`、bump 主 plugin 的兩處 version。腳本不碰層 ① —— 改 JS 物件不是機械操作 |
| 某條 lens 要取代同 key 的既有 lens | 用 `AskUserQuestion` 確認，**問題中列出被取代那條的 `focus` 全文**，取得一句取代理由，再帶 `--include-override --override-reason KEY=理由` 重跑 |

其餘退出碼：`0` 完成（或 `--dry-run` 印完計畫）、`1` 錯誤（含驗證未過 —— 此時**保證尚未做任何
git 寫入或遠端操作**）、`2` 用法錯。

### `override` 為什麼預設不送

標了 `override` 的 lens 語意是「**取代**某條既有 lens」，不是「新增」。貢獻到公共層等於
**替所有使用者移除一條調校過的 lens**，而且傷害是靜默的 —— 被取代的 lens 消失後沒有人會收到通知。
所以預設不列入候選，要送必須顯式 `--include-override` 且逐條給理由（理由會寫進 PR body）。

### 讀腳本印出的分類

```
SKIP       已回流（層 ② 內容相同）／已在層 ①（built-in 內容相同）→ 提示使用者本機該條可刪
CANDIDATE  兩層都沒有 → 純新增，直接送
MODIFY     同 key 但 focus 不同 → 需要 override 決定
```


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
