#!/usr/bin/env bash
# 本地一鍵跑 lint + 測試。
# 前置：brew install bats-core shellcheck
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── shellcheck (bash scripts) ──"
# 這份清單與 .github/workflows/test.yml 的 shellcheck step 是兩份寫死的規格（#30 追蹤自動列舉）；
# #33 verify R11 抓到兩邊互相都不是對方的超集 —— 改其中一邊時請一併改另一邊。
shellcheck bin/pai-build-diff bin/pai-parse-verdict bin/pai-iter-commit bin/pai-list-profiles test/lint-bats.sh test/lint-changelog-counts.sh test/lint-contract-enumerations.sh

echo "── py_compile (python scripts) ──"
python3 -m py_compile bin/pai-parse-lens-csv bin/pai-collect-lens-layers

echo "── lint-bats (bare ! assertions are no-ops under bats errexit — round 6 RC11) ──"
bash test/lint-bats.sh --selftest
bash test/lint-bats.sh

echo "── lint-changelog-counts (CHANGELOG case counts must equal grep -c — RC13, fifth recurrence) ──"
bash test/lint-changelog-counts.sh --selftest
bash test/lint-changelog-counts.sh

echo "── lint-contract-enumerations (contract closed lists vs bin/codex-call — round 11 R11-1) ──"
bash test/lint-contract-enumerations.sh --selftest
bash test/lint-contract-enumerations.sh

echo "── bats test/ ──"
bats test/

echo "── node tests ──"
for t in test/*.test.mjs; do echo "  $t"; node "$t"; done

# #33 verify R11：pack（plugins/pai-lenses）的 python 測試先前沒有任何本機入口，只有 CI 的
# manifests-and-lens-pack job 會跑；test/README.md 卻寫「CI 跑同一組」。這裡對齊那個 job
# （完整 mutation 量測仍是手動：python3 scripts/mutation_check.py，約十分鐘）。
echo "── pai-lenses pack (validate.py 的測試、靶清單、validator 本體) ──"
( cd ../pai-lenses && python3 -m py_compile scripts/*.py \
  && python3 scripts/test_validate.py \
  && python3 scripts/mutation_check.py --check-targets \
  && python3 scripts/validate.py --base "$(git merge-base origin/main HEAD 2>/dev/null || echo HEAD)" --event pull_request )

echo "✓ 全部通過"
