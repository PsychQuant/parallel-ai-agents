# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> ⚠ This file was bootstrapped by `changelog-tools:changelog-init` from the
> `plugin.json` description field. Section categorization is best-effort —
> review and refine `Added` / `Changed` / `Fixed` etc. as needed.

## [Unreleased]

## [2.3.0] - 2026-05-07

### Added
- **`--auto-iterate` mode for `/ensemble-academic-review` (#34)**: round → fix → round 自治收斂迴圈,內部沿用 mix N 的 alternating independent/hybrid pattern,但加上每輪結束的:
  - **Verdict parsing**: Codex prompt 強制要求 `<verdict>PERMANENT_CONVERGENCE | CONVERGED | NEEDS_ITER_N</verdict>` 結構化 tag,skill 用 regex 解析,不靠語意判斷
  - **HIGH-only fix application**: 從 `review-round-{N}.md` 解 HIGH-severity findings 自動套到 working tree;ambiguous fix skip + log to `skipped_fixes.log`
  - **Auto-commit per round**: `iter-{N}: apply HIGH fixes from ensemble round {N}`,user 可隨時 `git revert iter-{N}`
  - **Rotate-focus heuristic**: 連續 K=3 同 focus CONVERGED 才 switch (focus pool: method-section / proofs / typography / cross-references / boundary-cases)
  - **Stop conditions**: 達 `--converge-on` (default `PERMANENT_CONVERGENCE`) 或 `--max-rounds` (default 12, max 30)
- **8 cumulative methodological lessons** in SKILL.md tail — 來自實戰 23-round campaign (`PsychQuantHsu/psychophysic_representations_manuscript/docs/rounds/INDEX.md`),作為 rare-audited section / hypothesis-inheritance / verdict-tier 等坑的 reference

### Notes
- Self-contained Bash while + state machine,**不**依賴 ralph-loop 的 Stop-hook 機制
- 與 ralph-loop 同時跑時 skill 偵測並警告(雙 Stop-hook 衝突風險)
- Spec-only PR — agent 讀 SKILL.md 後在 user 顯式傳 `--auto-iterate` 才觸發,既有 mode 行為不變

## [2.2.0] - 2026-05-03

### Added
- **`number-verifier` reviewer**: 5th ensemble reviewer that checks every
  number in a doc against ground-truth artifacts (`.rds`, `.npz`, `.csv`,
  R/Python scripts). Catches hallucinated numbers that other reviewers
  miss. Verified by ASSG3 review pipeline (Canadian GDP ARIMA + Australian
  yields VAR/VECM) where it caught wrong y_T, drift omission, Ljung-Box
  fitdf errors, and ARIMA(1,1,1) reference p-value mistakes across 4 rounds.
- `--no-numeric` flag to disable number-verifier (pure theoretical papers)
- `--no-references` flag to disable reference-verifier (technical notes)
- Auto-detect: number-verifier enables when `analysis/`, `*.rds`, `*.ipynb`,
  `*.Rmd`, or `data/*.csv` are present near the doc
- Hybrid mode: `prior_number_issues` watch list passed to number-verifier
  in subsequent rounds (analogous to `prior_ref_issues`)

### Changed
- Reviewer count: 4 → 5 Claude teammates + Codex
- Tool-call rule: "5 calls in one message" → "N+1 calls (N ∈ {3,4,5})"
- Ironclad rules: HIGH-priority bucket now includes hallucinated numbers
  alongside hallucinated references

## [2.1.1] - (date unknown — please fill in)

### Changed
- 平行派發任務給多個 AI agent（Claude + Codex），獨立執行後交叉比對結果
