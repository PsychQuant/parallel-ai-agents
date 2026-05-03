# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> ⚠ This file was bootstrapped by `changelog-tools:changelog-init` from the
> `plugin.json` description field. Section categorization is best-effort —
> review and refine `Added` / `Changed` / `Fixed` etc. as needed.

## [Unreleased]

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
