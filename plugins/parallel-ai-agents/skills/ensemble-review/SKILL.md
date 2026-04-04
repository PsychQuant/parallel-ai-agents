---
name: ensemble-review
description: |
  Claude + Codex 雙 AI 獨立審閱，交叉比對找共識和盲點。
  Claude Opus 審一遍，Codex GPT-5.4 xhigh 獨立審一遍，最後合成比較表。
  Use when: 重要文件（blog、設計文件、PR）發布前需要嚴格審閱。
argument-hint: "FILE [--focus 'review focus'] e.g. 'src/blog/post.md', 'docs/design.md --focus 技術準確性'"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

# /ensemble-review — 雙 AI 獨立審閱 + 交叉比對

兩個不同的 AI（Claude Opus + Codex GPT-5.4 xhigh）各自獨立審閱同一份文件，然後合成比較表找出共識和盲點。

> **原理同 Ensemble OCR**：不同模型的錯誤模式不重疊。Claude 擅長架構和邏輯，GPT-5.4 擅長 deep research 和事實查核。兩個都漏掉的問題才是真正沒問題的。

## 核心原則

1. **獨立性**：兩個 AI 看到的 context 相同，但各自獨立產出審稿意見，不互相參考
2. **平行**：Claude 審稿和 Codex 審稿同時進行，不等對方
3. **交叉比對**：最後由 Claude 合成兩份意見，標記共識、衝突、盲點

## 執行流程

### Phase 0: 解析輸入

```
Arguments:
  FILE — 要審閱的檔案路徑
  --focus — 審閱重點（可選，如「技術準確性」「寫作品質」「安全性」）

如果沒有 FILE，問使用者。
如果 FILE 是目錄，列出檔案讓使用者選。
```

### Phase 1: 讀取文件 + 判斷審閱類型

讀取目標文件，自動判斷類型：

| 檔案類型 | 審閱重點 |
|---------|---------|
| `.md` blog 文章 | 技術準確性、邏輯一致性、聲明可驗證性、寫作品質 |
| `.md` 設計文件 | 架構合理性、邊界情況、可行性、遺漏 |
| `.swift` / `.py` / `.ts` 程式碼 | bug、安全漏洞、效能、可讀性、edge case |
| PR diff | 變更合理性、向後相容、測試覆蓋 |

使用者可以用 `--focus` 覆蓋自動判斷。

### Phase 2: 平行審閱

**同時**啟動兩個審閱：

#### Claude 審閱（直接在當前 session 做）

以嚴格審稿人角度審閱文件。輸出格式：

```markdown
## Claude Review

### 問題清單
1. [嚴重性: HIGH/MEDIUM/LOW] 問題描述
   - 證據/位置
   - 建議修改

2. ...

### 整體評價
{一段話}
```

#### Codex 審閱（背景執行）

用 Codex task 模式派發：

```bash
# 確認 Codex CLI 可用
codex --version 2>/dev/null || { echo "需要安裝 Codex CLI"; exit 1; }

# 找到目標文件所在的 git repo
REPO_ROOT=$(git -C "$(dirname "$FILE")" rev-parse --show-toplevel 2>/dev/null)

# 在 repo 目錄下啟動 Codex task
cd "$REPO_ROOT"

# 組裝 prompt
CODEX_PROMPT="你是嚴格的技術審稿人。請讀取 $FILE_REL 並審閱。

審閱重點：
1. 技術準確性 — 數據、描述、結論是否站得住腳
2. 邏輯一致性 — 論述有沒有跳躍或矛盾
3. 聲明的可驗證性 — 哪些說法需要更多證據
4. 讀者的質疑 — 專業讀者會怎麼挑戰這份文件
5. 遺漏的 caveat — 重要限制條件是否有寫出

$FOCUS_INSTRUCTION

用中文逐點列出問題和建議。每個問題標注嚴重性（HIGH/MEDIUM/LOW）。"

# 啟動 Codex
node "$CODEX_COMPANION" task \
  --model gpt-5.4 --effort xhigh --background \
  "$CODEX_PROMPT"
```

**注意**：必須在目標文件的 git repo 目錄下執行，否則 Codex 無法讀取文件。

### Phase 3: 等待 Codex 完成

```bash
# 輪詢 Codex 狀態
node "$CODEX_COMPANION" status --all
# 等待直到 job 完成
node "$CODEX_COMPANION" result $JOB_ID
```

如果 Codex 失敗或超時（>10 分鐘），跳過 Codex 意見，只用 Claude 的。

### Phase 4: 交叉比對

Claude 讀取兩份審稿意見，產出比較表：

```markdown
## Ensemble Review: {filename}

### 審閱者
- **Claude Opus 4.6**: 直接審閱
- **GPT-5.4 xhigh**: 透過 Codex，含 deep research（GitHub、HuggingFace 等）

### 共識（兩者都指出）
| # | 問題 | 嚴重性 | Claude 說法 | GPT-5.4 說法 |
|---|------|--------|------------|-------------|
| 1 | ... | HIGH | ... | ... |

### 僅 Claude 指出
| # | 問題 | 嚴重性 | 說明 |
|---|------|--------|------|
| 1 | ... | ... | ... |

### 僅 GPT-5.4 指出
| # | 問題 | 嚴重性 | 說明 |
|---|------|--------|------|
| 1 | ... | ... | ... |

### 衝突（兩者意見矛盾）
| # | 議題 | Claude | GPT-5.4 | 我的判斷 |
|---|------|--------|---------|---------|
| 1 | ... | ... | ... | ... |

### Summary
- 共識問題: N 個（最需要修）
- 僅 Claude: M 個
- 僅 GPT-5.4: K 個
- 衝突: J 個

### 建議修改優先順序
1. {highest priority fix}
2. ...
```

### Phase 5: 詢問下一步

```
審閱完成。要怎麼做？
1. 根據共識問題修改文件
2. 只看不改（純審閱）
3. 針對特定問題深入討論
```

## Codex CLI 參考

```bash
# companion script 路徑
CODEX_COMPANION="/Users/che/.claude/plugins/marketplaces/openai-codex/plugins/codex/scripts/codex-companion.mjs"

# 啟動 task
node "$CODEX_COMPANION" task \
  --model gpt-5.4 --effort xhigh --background \
  "prompt"

# 查狀態
node "$CODEX_COMPANION" status --all

# 取結果
node "$CODEX_COMPANION" result $JOB_ID
```

## 鐵律

- **Codex 的審稿結果原封不動呈現**，不要修改或摘要
- **Claude 的審稿必須在 Codex 啟動前完成**（確保獨立性——Claude 不能看到 Codex 的意見後才寫自己的）
- **交叉比對由 Claude 做**，因為 Claude 有對話 context
- **共識問題 > 單方問題**：兩個 AI 都指出的問題最需要修
- **衝突不自動裁決**：呈現給使用者判斷
