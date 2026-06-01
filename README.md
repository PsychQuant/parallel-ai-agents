# parallel-ai-agents

Claude Code marketplace，散發 **平行多 AI agent 審閱** plugin。

目前只裝一個 plugin：`parallel-ai-agents`。把任務平行派發給多個 AI agent（Claude teammates + Codex GPT-5.5），各自**獨立執行**後交叉比對，找出共識與盲點。

## 安裝

```bash
/plugin marketplace add PsychQuant/parallel-ai-agents
/plugin install parallel-ai-agents@parallel-ai-agents
```

安裝後即可使用三個 skill：

| Skill | 用途 |
|-------|------|
| `/ensemble-code-review` | 程式碼／技術文件審閱：4 個 Claude teammates（architecture、correctness、security、devils-advocate）+ Codex 獨立審一遍，最後合成比較表 |
| `/ensemble-academic-review` | 學術論文審閱：methodology、writing、reference verification（che-zotero-mcp 抓幻覺文獻）、number-verification（R/Python 重跑 ground-truth 抓幻覺數字）、devils-advocate。支援 independent／hybrid／mix N 三種模式 |
| `/ensemble-lecture-review` | 教學講義審閱：4 個 Claude teammates 各自獨立審閱講義品質（可帶對應逐字稿 `--srt`） |

## 為什麼

單一 AI 審閱有盲點且會自我說服。讓**兩個模型家族**（Claude + Codex）互相看不到對方結果地獨立審一遍，再交叉比對，共識的部分可信度高、分歧的部分正是該人工複查的地方。Codex 走 `bin/codex-call`（Swift script，直接 HTTP）而非 `codex exec` subprocess，解決 hang 問題並避開 Python 版本飄移。

## Repo 結構

```
.
├── .claude-plugin/
│   └── marketplace.json        # marketplace manifest
├── plugins/
│   └── parallel-ai-agents/     # 唯一的 plugin
│       ├── .claude-plugin/
│       │   └── plugin.json
│       ├── bin/
│       │   └── codex-call      # Swift script：直接 HTTP 呼叫 Codex
│       ├── skills/             # 三個 ensemble-review skill
│       ├── CHANGELOG.md
│       └── CLAUDE.md           # plugin internal guide
├── README.md                   # 本檔案：marketplace 說明
├── LICENSE                     # MIT
└── .gitignore
```

## 從 monorepo 抽出

此 repo 由 `psychquant-claude-plugins/plugins/parallel-ai-agents/` 透過 `git filter-repo --path` 抽出，保留完整 commit 歷史。抽出後主 marketplace 移除該 entry、改為獨立 self-marketplace 散發 —— 與 `che-axiom-systems`、`che-transport-mcp` 的作法一致。
