<!-- SPECTRA:START v1.0.2 -->

# Spectra Instructions

This project uses Spectra for Spec-Driven Development(SDD). Specs live in `openspec/specs/`, change proposals in `openspec/changes/`.

## Use `/spectra-*` skills when:

- A discussion needs structure before coding → `/spectra-discuss`
- User wants to plan, propose, or design a change → `/spectra-propose`
- Tasks are ready to implement → `/spectra-apply`
- There's an in-progress change to continue → `/spectra-ingest`
- User asks about specs or how something works → `/spectra-ask`
- Implementation is done → `/spectra-archive`
- Commit only files related to a specific change → `/spectra-commit`

## Workflow

discuss? → propose → apply ⇄ ingest → archive

- `discuss` is optional — skip if requirements are clear
- Requirements change mid-work? Plan mode → `ingest` → resume `apply`

## Parked Changes

Changes can be parked（暫存）— temporarily moved out of `openspec/changes/`. Parked changes won't appear in `spectra list` but can be found with `spectra list --parked`. To restore: `spectra unpark <name>`. The `/spectra-apply` and `/spectra-ingest` skills handle parked changes automatically.

<!-- SPECTRA:END -->

# parallel-ai-agents (marketplace root)

此 repo 是 Claude Code marketplace，散發 `parallel-ai-agents` plugin。

## 結構

- `.claude-plugin/marketplace.json` — marketplace manifest
- `plugins/parallel-ai-agents/` — 唯一的 plugin（含 skills、`bin/codex-call` wrapper 等所有實作）
- `README.md` — marketplace 對外介紹
- `LICENSE` — MIT

## 給未來 Claude 的 note

當使用者要求改 ensemble 審閱邏輯、調整 agent 派發、改 Codex wrapper 時：**所有實作都在 `plugins/parallel-ai-agents/` 底下**，root 只保留 marketplace metadata 與整體文件。plugin 內部開發指引見 `plugins/parallel-ai-agents/CLAUDE.md`。

## 重要區分

- 「marketplace」=本 repo 整體（散發容器）
- 「plugin」=`plugins/parallel-ai-agents/`（功能本體）

不要把兩者混在一起。

## 版本同步（CRITICAL）

bump 版本時兩處必須一致：

- `plugins/parallel-ai-agents/.claude-plugin/plugin.json` 的 `version`
- `.claude-plugin/marketplace.json` 對應 plugin entry 的 `version`

兩者不同步 → 使用者 `/plugin update` 會看到舊版或裝不到新功能。
