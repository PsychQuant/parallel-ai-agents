# parallel-ai-agents

Claude Code marketplace，散發 **平行多 AI agent 審閱** plugin。

散發**兩個** plugin。把任務平行派發給多個 AI agent（Claude teammates + Codex），各自**獨立執行**後交叉比對，找出共識與盲點。

| Plugin | 是什麼 |
|---|---|
| **`parallel-ai-agents`** | 主 plugin —— ensemble 審閱的 skill、harness、`bin/` 工具 |
| **`pai-lenses`** | 官方 **lens pack**（三層疊加的層 ②）：以 CSV 提供可疊加的 reviewer lens。純資料，無程式碼 |

## 安裝

```bash
/plugin marketplace add PsychQuant/parallel-ai-agents
/plugin install parallel-ai-agents@parallel-ai-agents
/plugin install pai-lenses@parallel-ai-agents        # 官方 lens pack（建議一併安裝）
```

> **`pai-lenses` 是選配但建議裝。** 沒裝時 ensemble 只會用 harness 內建的 lens ——
> 不會報錯、不會警告（缺席是靜默的，這是刻意設計），所以**「沒裝」與「裝了但沒生效」
> 從輸出上看不出差別**。報表的 provenance 行會列出實際載入了哪幾層，可據此確認。

安裝後可用的 skill：

| Skill | 用途 |
|-------|------|
| `/ensemble-code-review` | 程式碼／技術文件審閱：architecture、correctness、security + devils-advocate + Codex 獨立審一遍，最後合成比較表 |
| `/ensemble-academic-review` | 學術論文審閱：methodology、writing、reference verification（che-zotero-mcp 抓幻覺文獻）、number-verification（R/Python 重跑 ground-truth 抓幻覺數字）、devils-advocate。支援 independent／hybrid／mix N 三種模式 |
| `/ensemble-lecture-review` | 教學講義審閱：內容正確性／可讀性／逐字稿覆蓋率（可帶 `--srt`） |
| `/ensemble-compose` | 自由組合：跨 profile 挑 lens + 自訂 reviewer（`--include` / `--lens` / `--lens-file`）|
| `/ensemble-contribute-lenses` | 把本機 `~/.claude/pai-lenses/` 的 lens 送回公共層並開 PR |
| `/ensemble-eval` | **dev 工具**：對埋好缺陷的 fixture 跑 K 次真 ensemble，量偵測率 |

## 三層 lens 疊加

reviewer 的 lens 由三層疊出來，順序即優先序：

| 層 | 來源 | 誰能改 |
|---|---|---|
| ① built-in | 主 plugin 的 `PROFILES`（harness 內） | 改 code + 發版 |
| ② lens pack | `pai-lenses` 的 `lenses/<profile>.csv` | 改 CSV + bump 版本 |
| ③ user | `~/.claude/pai-lenses/<profile>.csv` | 直接編，立即生效、不必發布 |

撞名時預設 first-wins，CSV 標了 `override` 才取代。寫在層 ③ 的 lens 想回流上游，跑
`/ensemble-contribute-lenses`。完整契約見
[`references/lens-layers.md`](plugins/parallel-ai-agents/references/lens-layers.md)。

## 為什麼

單一 AI 審閱有盲點且會自我說服。讓**兩個模型家族**（Claude + Codex）互相看不到對方結果地獨立審一遍，再交叉比對，共識的部分可信度高、分歧的部分正是該人工複查的地方。Codex 走 `bin/codex-call`（Swift script，直接 HTTP）而非 `codex exec` subprocess，解決 hang 問題並避開 Python 版本飄移。

## Repo 結構

```
.
├── .claude-plugin/
│   └── marketplace.json        # marketplace manifest
├── plugins/
│   ├── parallel-ai-agents/     # 主 plugin
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json
│   │   ├── bin/
│   │   │   ├── codex-call      # Swift script：直接 HTTP 呼叫 Codex
│   │   │   ├── pai-list-profiles        # 查 PROFILES 真源
│   │   │   └── pai-contribute-lenses    # 層 ③ 的回流流程
│   │   ├── skills/             # 六個 skill
│   │   ├── workflows/          # ensemble harness
│   │   ├── references/         # lens-layers 契約、built-in lens catalog
│   │   ├── CHANGELOG.md
│   │   └── CLAUDE.md           # plugin internal guide
│   └── pai-lenses/             # 官方 lens pack（層 ②）
│       ├── .claude-plugin/
│       │   └── plugin.json
│       ├── lenses/             # <profile>.csv
│       └── scripts/validate.py # CI 閘門
├── README.md                   # 本檔案：marketplace 說明
├── LICENSE                     # MIT
└── .gitignore
```

## 從 monorepo 抽出

此 repo 由 `psychquant-claude-plugins/plugins/parallel-ai-agents/` 透過 `git filter-repo --path` 抽出，保留完整 commit 歷史。抽出後主 marketplace 移除該 entry、改為獨立 self-marketplace 散發 —— 與 `che-axiom-systems`、`che-transport-mcp` 的作法一致。
