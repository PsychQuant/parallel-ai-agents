# test/

`ensemble-code-review` diff 模式的自動化測試。把過去人工 re-audit（3 輪 self-dogfood）抓到的 bug 全部固化成 regression，取代「每次改 diff 邏輯都要重新人工審」。

## 測什麼

| 檔案 | 對象 |
|------|------|
| `pai-build-diff.bats` | `../bin/pai-build-diff`（diff 模式建構器，3 輪硬化的單一真相源）|
| `ensemble-workflow.test.mjs` | `../workflows/ensemble-workflow.js`（共用 harness，4 個 skill 的底層）|

`pai-build-diff.bats` 涵蓋：5 種模式（`--diff`/`--base`/`--since`/`--commits`/`--pr`）、退出碼契約（0 有 diff／3 無變更／1 錯誤）、ref/N 驗證（injection、dashed-ref、0/leading-zero、位數溢位）、untracked 安全（symlink no-follow、FIFO no-hang、換行檔名 C-quote）、empty-tree base、未知 mode 的多位元組 regression。

`ensemble-workflow.test.mjs` 涵蓋 harness 的 **fail-closed 不變式**：unknown profile、空 lens 組合、core lens 被 skip（null）/ error（throw）/ devil's-advocate 缺席 → 一律 HIGH integrity（不可假 PASS）、codex 缺席 → INFO 非阻塞、mergeDedup 對 malformed severity 穩健。把「null-skip fail-open」的修正鎖死成 regression。（純 node，無框架；把 workflow script body 包成可 import 的 async 函式、注入 mock globals 實跑。）

## 跑法

```bash
# 前置（一次性）
brew install bats-core shellcheck

# 一鍵：shellcheck + bats
./test/run.sh

# 或分開
shellcheck bin/pai-build-diff
bats test/
```

CI（`.github/workflows/test.yml`）在每次 push / PR 自動跑同一組。

## 加測試的原則

改 `bin/pai-build-diff` 的行為 → **先在 `pai-build-diff.bats` 加一個會 fail 的 case（RED），再改 script 讓它 pass（GREEN）**。不要在 `SKILL.md` inline 重寫 diff 邏輯 —— script 是單一真相源，SKILL.md 只呼叫它。
