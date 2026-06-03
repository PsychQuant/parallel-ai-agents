#!/usr/bin/env bash
# 本地一鍵跑 lint + 測試。
# 前置：brew install bats-core shellcheck
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── shellcheck bin/pai-build-diff ──"
shellcheck bin/pai-build-diff

echo "── bats test/ ──"
bats test/

echo "── harness regression (node) ──"
node test/ensemble-workflow.test.mjs

echo "✓ 全部通過"
