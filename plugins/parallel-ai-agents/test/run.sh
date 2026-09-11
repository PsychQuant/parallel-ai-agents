#!/usr/bin/env bash
# 本地一鍵跑 lint + 測試。
# 前置：brew install bats-core shellcheck
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── shellcheck (bash scripts) ──"
# 這份清單與 .github/workflows/test.yml 的 shellcheck step 是兩份寫死的規格（#30 追蹤自動列舉）；
# #33 verify R11 抓到兩邊互相都不是對方的超集 —— 改其中一邊時請一併改另一邊。
shellcheck bin/pai-build-diff bin/pai-parse-verdict bin/pai-iter-commit bin/pai-list-profiles references/regen-builtin-lenses.sh test/run.sh test/assert-tap-complete.sh test/lint-bats.sh test/lint-changelog-counts.sh test/lint-contract-enumerations.sh test/lint-ci-log-filter.sh

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

echo "── lint-ci-log-filter (every CI run step must say how its log is filtered — #33 verify R15) ──"
bash test/lint-ci-log-filter.sh --selftest
# R16 logic L-2：非 monorepo 佈局沒有 .github/ —— 明說略過，不是 traceback。
if [ -f ../../.github/workflows/test.yml ]; then bash test/lint-ci-log-filter.sh; else echo "（非 monorepo 佈局，略過 workflow 檢查）"; fi

echo "── bats test/ ──"
bats test/

# #33 verify R15（regression LOW）：CI 的 pack 錨點 no-skip 守衛（R14 新增）run.sh 沒跟上——R12 才關掉的分岔又開。
# R16：非 monorepo 佈局（plugin cache 副本）沒有 sibling pack，錨點依設計 skip——那不是 vacuous，是不適用；只在 monorepo 跑守衛。
echo "── bats (pack anchor) — fail on skip ──"
if [ ! -d ../pai-lenses ]; then
  echo "（非 monorepo 佈局，pack 錨點不適用，略過 no-skip 守衛）"
else
TAP="$(mktemp)"
bats --formatter tap test/pai-collect-lens-layers.bats > "$TAP" || { cat "$TAP"; exit 1; }
bash test/assert-tap-complete.sh "$TAP" "pai-collect-lens-layers.bats" || { cat "$TAP"; exit 1; }
rm -f "$TAP"
fi

echo "── node tests ──"
for t in test/*.test.mjs; do echo "  $t"; node "$t"; done

# #33 verify R11：pack（plugins/pai-lenses）的 python 測試先前沒有任何本機入口，只有 CI 的
# manifests-and-lens-pack job 會跑；test/README.md 卻寫「CI 跑同一組」。這裡對齊那個 job
# （完整 mutation 量測仍是手動：python3 scripts/mutation_check.py，約 30–50 分鐘）。
# #33 verify R12：CI 的 builtin-lenses.csv drift step 也搬過來 —— 它是 run.sh 與 CI 之間最後一處分岔。
echo "── builtin-lenses.csv drift (regenerate → expect no diff) ──"
# R13 logic N4：非 git checkout（plugin cache 副本）下 `git diff` rc=129，不能拿它當「過期」。
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # R14 regression E-1：regen 腳本的 node 例外會印 harness 原始碼——與 CI 同一份過濾器（monorepo 才有）。
  # 注意這一步會**改寫工作樹**（catalog 過期時留下重生後的檔）——R13 reg R13-4，明示不改：那正是「請 commit」的用意。
  if [ -f ../pai-lenses/scripts/neutralise.py ]; then
    ( set -o pipefail; bash references/regen-builtin-lenses.sh 2>&1 | python3 ../pai-lenses/scripts/neutralise.py )
  else
    bash references/regen-builtin-lenses.sh
  fi
  # R13 requirements R13-5：不印 diff 內容 —— catalog 的 focus 是 fork 可控文字，`##[…]`/`::` 會原樣進 step log。
  git diff --quiet -- references/builtin-lenses.csv || { echo "references/builtin-lenses.csv 過期 —— 上面已重生，請 commit（內容不印：見 git diff）"; exit 1; }
else
  echo "（非 git checkout，略過 drift 檢查）"
fi

echo "── pai-lenses pack (validate.py 的測試、靶清單、validator 本體) ──"
# 這段只在 monorepo 佈局下成立（plugin cache 裡的副本沒有 sibling pack）。
if [ ! -d ../pai-lenses ]; then
  echo "（非 monorepo 佈局，略過 pack 測試）"
else
  ( cd ../pai-lenses && python3 -m py_compile scripts/*.py \
    && python3 scripts/test_validate.py \
    && python3 scripts/mutation_check.py --check-targets )
  # #33 verify R12：拿不到 origin/main 時**不要**拿 HEAD 當替身 —— `--base HEAD` 恆印「無需 bump ✓」，
  # 正是本 PR 一路在消滅的肯定式假綠燈。validate.py 對「本機且無 base」自己會說「bump 檢查未跑」。
  if BASE="$(git merge-base origin/main HEAD 2>/dev/null)" && [ -n "$BASE" ] && [ "$BASE" != "$(git rev-parse HEAD)" ]; then
    ( cd ../pai-lenses && python3 scripts/validate.py --base "$BASE" --event pull_request )
  else
    echo "（找不到 origin/main，或 HEAD 就在 main 上：bump 檢查本次未跑，只跑其餘閘門）"
    ( cd ../pai-lenses && python3 scripts/validate.py )
  fi
fi

echo "✓ 全部通過"
