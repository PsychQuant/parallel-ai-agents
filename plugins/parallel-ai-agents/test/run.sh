#!/usr/bin/env bash
# 本地一鍵跑 lint + 測試。
# 前置：brew install bats-core shellcheck
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── shellcheck (bash scripts) ──"
shellcheck bin/pai-build-diff bin/pai-parse-verdict bin/pai-iter-commit test/lint-bats.sh

echo "── py_compile (python scripts) ──"
python3 -m py_compile bin/pai-parse-lens-csv

echo "── lint-bats (bare ! assertions are no-ops under bats errexit — round 6 RC11) ──"
bash test/lint-bats.sh --selftest
bash test/lint-bats.sh

echo "── bats test/ ──"
bats test/

echo "── node tests ──"
for t in test/*.test.mjs; do echo "  $t"; node "$t"; done

echo "✓ 全部通過"
