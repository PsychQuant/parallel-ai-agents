# parallel-ai-agents — CLAUDE.md

## Purpose

平行派發任務給多個 AI agent，獨立執行後交叉比對結果。使用 Claude orchestrated teams + Codex 實現跨模型、跨角色的盲驗。

## Skills

| Skill | 用途 | 架構 |
|-------|------|------|
| `/parallel-ai-agents:ensemble-review` | 審閱文件/程式碼，交叉比對產出共識/盲點報告 | 4 Claude teammates (team) + 1 Codex |

## 審閱架構

```
ensemble-review
├── Claude Team（4 teammates，orchestrated）
│   ├── architecture — 設計、API、依賴
│   ├── correctness — 邏輯、bug、edge case
│   ├── security — 攻擊者視角
│   └── devils-advocate — 反駁前 3 人
└── Codex（gpt-5.5，跨模型盲驗）
```

## 依賴

- Claude Code orchestrated teams（TeamCreate、SendMessage）
- **Codex OAuth token**（`~/.codex/auth.json`）— 由 codex CLI 在首次登入時建立。本 plugin 自帶 wrapper `bin/codex-call.py` 直接讀這個檔案、走 OAuth refresh + HTTP 直連 `chatgpt.com/backend-api`，不再 spawn `codex exec` subprocess（避免 stdin/stdout pipe 互鎖造成的 hang）
- Python 3（macOS 12+ 內建）

## bin/codex-call.py

直接 HTTP wrapper，取代原本的 `codex exec --full-auto`。設計目的：

| 問題 | `codex exec` | `codex-call.py` |
|------|-------------|-----------------|
| Subprocess hang | 偶發 | ✗ 純 HTTP，無 subprocess |
| Hard timeout | 不可靠 | ✓ `--max-time` socket-level abort |
| OAuth refresh | CLI 自動 | 自帶 refresh + file lock |
| 計費 | ChatGPT 訂閱 | ChatGPT 訂閱（同一條 OAuth）|
| service_tier=fast | CLI 接受（似乎降級為 default）| backend 拒絕，預設不送 |

範例：

```bash
codex-call.py \
  --output result.md \
  --model gpt-5.5 \
  --effort xhigh \
  --max-time 600 \
  --instructions "你是嚴謹 reviewer。" \
  --prompt-file prompt.txt
```

或 stdin：

```bash
echo "..." | codex-call.py --output out.md --model gpt-5.5 --effort xhigh
```

Wrapper 在 plugin 安裝時自動加入 PATH（透過 `bin/`），所以直接呼叫名字即可，不需要絕對路徑。

## Development

- 測試：`claude --plugin-dir ./plugins/parallel-ai-agents`
- 更新：`/plugin-tools:plugin-update parallel-ai-agents`
