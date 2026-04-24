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
- Codex CLI（`codex` 命令）
- Codex companion script（openai-codex plugin 提供）

## Development

- 測試：`claude --plugin-dir ./plugins/parallel-ai-agents`
- 更新：`/plugin-tools:plugin-update parallel-ai-agents`
