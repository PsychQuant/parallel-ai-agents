# parallel-ai-agents (marketplace root)

此 repo 是 Claude Code marketplace，散發 `parallel-ai-agents` plugin。

## 結構

- `.claude-plugin/marketplace.json` — marketplace manifest
- `plugins/parallel-ai-agents/` — 主 plugin（含 skills、`bin/codex-call` wrapper 等所有實作）
- `plugins/pai-lenses/` — **第二個 plugin**：官方 lens pack（三層疊加的層 ②，見 `plugins/parallel-ai-agents/references/lens-layers.md`）。只有 CSV 與 validator，無程式碼
- `README.md` — marketplace 對外介紹
- `LICENSE` — MIT

## 給未來 Claude 的 note

當使用者要求改 ensemble 審閱邏輯、調整 agent 派發、改 Codex wrapper 時：**實作都在 `plugins/parallel-ai-agents/` 底下**，root 只保留 marketplace metadata 與整體文件。plugin 內部開發指引見 `plugins/parallel-ai-agents/CLAUDE.md`。

要**新增或修改一條 lens** 則看目標層：既有 profile 加 lens → `plugins/pai-lenses/lenses/<profile>.csv`；需要新 profile → `plugins/parallel-ai-agents/workflows/ensemble-workflow.js` 的 `PROFILES`。判準見 `plugins/parallel-ai-agents/references/lens-layers.md`。**自動回流工具（層 ③ → 公共層）尚未就緒**，見 #39 —— 目前請照該文件的決策表手動做。**`references/builtin-lenses.csv` 是 generated 的唯讀投影，編它不改變任何行為。**

## 重要區分

- 「marketplace」=本 repo 整體（散發容器），對應 `.claude-plugin/marketplace.json`
- 「plugin」=`plugins/` 底下的**一個**目錄。現在有兩個：`parallel-ai-agents`（功能本體）
  與 `pai-lenses`（官方 lens pack，純資料）

不要把 marketplace 與 plugin 混在一起，也不要假設「plugin」單指主 plugin。

## 版本同步（CRITICAL）

bump 版本時兩處必須一致。**這條對每一個 plugin 各自成立**，現在有兩個：

| plugin | plugin.json | marketplace.json entry |
|---|---|---|
| `parallel-ai-agents` | `plugins/parallel-ai-agents/.claude-plugin/plugin.json` | `name: "parallel-ai-agents"` |
| `pai-lenses` | `plugins/pai-lenses/.claude-plugin/plugin.json` | `name: "pai-lenses"` |

兩者不同步 → 使用者 `/plugin update` 會看到舊版或裝不到新功能，**而且沒有任何錯誤訊息**。

**兩個 plugin 都有機械閘門守這條**：`plugins/pai-lenses/scripts/validate.py` 的 `check_marketplace_sync` 會逐一比對 marketplace.json 裡**每一個在本 repo 內的** plugin（不只 pai-lenses），CI job `manifests-and-lens-pack` 會跑。新增第三個 plugin 時自動涵蓋。
