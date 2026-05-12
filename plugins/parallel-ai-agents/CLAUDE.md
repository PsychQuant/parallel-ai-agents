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
- **Codex OAuth token**（`~/.codex/auth.json`）— 由 codex CLI 在首次登入時建立。本 plugin 自帶 wrapper `bin/codex-call` 直接讀這個檔案、走 OAuth refresh + HTTP 直連 `chatgpt.com/backend-api`，不再 spawn `codex exec` subprocess（避免 stdin/stdout pipe 互鎖造成的 hang）
- Swift toolchain（Xcode CLT 內建；用 `#!/usr/bin/env swift` shebang，第一次跑會 compile cache）

## bin/codex-call

Swift script wrapper，取代原本的 `codex exec --full-auto`。設計目的：

| 問題 | `codex exec` | `codex-call` (Swift) |
|------|-------------|---------------------|
| Subprocess hang | 偶發 | ✗ 純 URLSession，無 subprocess |
| Hard timeout | 不可靠 | ✓ URLSession + DispatchSemaphore wait timeout |
| OAuth refresh | CLI 自動 | 自帶 refresh + flock 防 race |
| 計費 | ChatGPT 訂閱 | ChatGPT 訂閱（同一條 OAuth）|
| service_tier=fast | CLI 接受（似乎降級為 default）| backend 拒絕，預設不送 |
| Cold start | ~50ms (subprocess) | ~1.5s（swift compile + cache）|
| 依賴 | `codex` CLI 安裝 | macOS 內建 swift（Xcode CLT）|

範例：

```bash
codex-call \
  --output result.md \
  --model gpt-5.5 \
  --effort xhigh \
  --max-time 600 \
  --instructions "你是嚴謹 reviewer。" \
  --prompt-file prompt.txt
```

或 stdin：

```bash
echo "..." | codex-call --output out.md --model gpt-5.5 --effort xhigh
```

Wrapper 在 plugin 安裝時自動加入 PATH（透過 `bin/`），所以直接呼叫名字即可，不需要絕對路徑。

### 為什麼 Swift script 不是 Python

Python 在 macOS 上版本飄移：`/usr/bin/python3` 是 stub（要 Xcode CLT 才有真 binary）；版本可能是 3.9 / 3.10 / 3.11 / 3.13，新語法（如 `dict | None`）需 3.10+ 不一定可用。Swift script 用 Xcode CLT 內建的 swift 5+，shebang 直接跑，無版本兼容問題。

不走 Swift binary（che-mcps notarize 模式）的理由：這 wrapper 不需 TCC 權限（只發 HTTPS），開新 repo + notarize 流程過度工程化。Swift script 的 1-2s cold start 對 ensemble 場景（5-15s LLM response 為主）是可接受的雜訊。

## Development

- 測試：`claude --plugin-dir ./plugins/parallel-ai-agents`
- 更新：`/plugin-tools:plugin-update parallel-ai-agents`
