# parallel-ai-agents — CLAUDE.md

## Purpose

平行派發任務給多個 AI agent，獨立執行後交叉比對結果。使用 Claude orchestrated teams + Codex 實現跨模型、跨角色的盲驗。

## Skills

| Skill | 用途 |
|-------|------|
| `/parallel-ai-agents:ensemble-code-review` | 審程式碼/技術文件/diff（最完整：`--diff`/`--base`/`--since`/`--commits`/`--pr` 等 diff 模式，建構走 `bin/pai-build-diff`）|
| `/parallel-ai-agents:ensemble-academic-review` | 審學術論文（methodology/writing + 文獻真偽 + 數字重算；支援多輪 mix/hybrid/auto-iterate）|
| `/parallel-ai-agents:ensemble-lecture-review` | 審教學講義（內容正確性/可讀性/逐字稿覆蓋率）|
| `/parallel-ai-agents:ensemble-compose` | 自由組合：跨 profile 挑 lens + 自訂 reviewer（`--include`/`--lens`/`--lens-file` CSV）|
| `/parallel-ai-agents:ensemble-eval` | **dev 工具**：對 `eval/fixtures/` 埋好缺陷的論文跑 K 次真 ensemble，容差斷言偵測率（+`--apply-fix` 驗修稿）。手動跑、不進 CI |

審閱 skill 共用同一個 harness `workflows/ensemble-workflow.js`（`PROFILES` 內建各角色 lens；確定性 surface 的 regression 測試見 `test/`，模型判斷品質見 `eval/`）。

## 審閱架構（雙 backend，findings 形狀一致）

預設 **Backend A — Workflow harness**（`workflows/ensemble-workflow.js`）：distinct-lens reviewers（× `replicas`）+ devil's-advocate（讀同儕**完稿**反駁）+ 可選 Codex 跨模型盲驗 → pure-JS mergeDedup + **fail-closed**（core lens／DA 缺席 = HIGH integrity，不可假 PASS）。reviewer 數是資料（lens 陣列 × replicas），可大量 fan-out（硬上限 `MAX_AGENTS`）。

```
ensemble（以 code profile 為例）
├── reviewers（× replicas，平行 barrier）
│   ├── architecture — 設計、API、依賴
│   ├── correctness — 邏輯、bug、edge case
│   └── security — 攻擊者視角
├── devil's-advocate — 讀上面完稿、反駁「通過/LOW」（downstream node，非 live SendMessage）
└── Codex（gpt-5.x — model 由 codex-pro 治理契約解析（references/codex-governance.md，#23）；跨模型盲驗，--codex 開）
```

`Workflow` tool 不存在的舊版 Claude Code → fallback **Backend B — legacy TeamCreate fan-out**（同一 message 啟動 N 個 general-purpose Agent + Codex Bash）。兩 backend 報表一致。

## 依賴

- Claude Code orchestrated teams（TeamCreate、SendMessage）
- **Codex OAuth token**（`~/.codex/auth.json`）— 由 codex CLI 在首次登入時建立。本 plugin 自帶 wrapper `bin/codex-call` 直接讀這個檔案、走 OAuth refresh + HTTP 直連 `chatgpt.com/backend-api`，不再 spawn `codex exec` subprocess（避免 stdin/stdout pipe 互鎖造成的 hang）
- Swift toolchain（Xcode CLT 內建；用 `#!/usr/bin/swift` shebang **釘 CLT swift**，第一次跑會 compile cache）。⚠️ 不用 `#!/usr/bin/env swift` —— env 會解到 PATH 上第一個 swift（如 swiftly / Homebrew 安裝的版本），破壞「就用內建 CLT swift」的確定性假設。

## bin/codex-call

Swift script wrapper，取代原本的 `codex exec --full-auto`。設計目的：

| 問題 | `codex exec` | `codex-call` (Swift) |
|------|-------------|---------------------|
| Subprocess hang | 偶發 | ✗ 純 URLSession，無 subprocess |
| Hard timeout | 不可靠 | ✓ URLSession + DispatchSemaphore wait timeout |
| OAuth refresh | CLI 自動 | 自帶 refresh + flock 防 race |
| 計費 | ChatGPT 訂閱 | ChatGPT 訂閱（同一條 OAuth）|
| service_tier=fast | CLI 接受（內部翻譯成 priority）| **接受 `fast`/`priority`/`flex`**，內部翻譯與 codex CLI 一致 |
| Cold start | ~50ms (subprocess) | ~1.5s（swift compile + cache）|
| 依賴 | `codex` CLI 安裝 | macOS 內建 swift（Xcode CLT）|

範例：

```bash
codex-call \
  --output result.md \
  --model "$CODEX_MODEL" \   # 依 references/codex-governance.md 解析（#23）
  --effort xhigh \
  --max-time 600 \
  --instructions "你是嚴謹 reviewer。" \
  --prompt-file prompt.txt
```

或 stdin：

```bash
echo "..." | codex-call --output out.md --model "$CODEX_MODEL" --effort "$CODEX_EFFORT"   # 治理解析見 references/codex-governance.md
```

Wrapper 在 plugin 安裝時自動加入 PATH（透過 `bin/`），所以直接呼叫名字即可，不需要絕對路徑。

### 為什麼 Swift script 不是 Python

Python 在 macOS 上版本飄移：`/usr/bin/python3` 是 stub（要 Xcode CLT 才有真 binary）；版本可能是 3.9 / 3.10 / 3.11 / 3.13，新語法（如 `dict | None`）需 3.10+ 不一定可用。Swift script 用 Xcode CLT 內建的 swift 5+，shebang 直接跑，無版本兼容問題。

不走 Swift binary（che-mcps notarize 模式）的理由：這 wrapper 不需 TCC 權限（只發 HTTPS），開新 repo + notarize 流程過度工程化。Swift script 的 1-2s cold start 對 ensemble 場景（5-15s LLM response 為主）是可接受的雜訊。

## Development

- 測試：`claude --plugin-dir ./plugins/parallel-ai-agents`
- 更新：`/plugin-tools:plugin-update parallel-ai-agents`
