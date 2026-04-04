# parallel-ai-agents — CLAUDE.md

## Purpose

平行派發任務給多個 AI agent（Claude + Codex GPT-5.4 xhigh），獨立執行後交叉比對結果。原理同 Ensemble OCR：不同模型的錯誤模式不重疊，交叉比對找出共識和盲點。

## Skills

| Skill | 用途 |
|-------|------|
| `/parallel-ai-agents:ensemble-review` | 雙 AI 獨立審閱文件，交叉比對產出共識/盲點報告 |

## 依賴

- Codex CLI（`codex` 命令）
- Codex companion script（openai-codex plugin 提供）

## Development

- 測試：`claude --plugin-dir ./plugins/parallel-ai-agents`
- 更新：`/plugin-tools:plugin-update parallel-ai-agents`
