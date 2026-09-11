#!/usr/bin/env bash
# 機械護欄（#33 verify R15 logic L-2 / security S-3 / requirements F2 / regression F5）：
# `.github/workflows/test.yml` 裡**每一個** `run:` step 都必須明示它的 step log 怎麼處理 PR 可控文字——
#   (a) run 區塊裡有 `neutralise.py`（經 validate.py 的 LineSanitiser 那一份中和實作），或
#   (b) step 名稱那一行**之後、run: 之前**（或 run 區塊內）有一行 `# LOG-FILTER: <理由>` 註解，明示不過濾與為什麼
#       （封閉的兩種理由：`in-process` = 該程式自帶 LineSanitiser；`none — …` = 執行 PR 自己的程式碼／只印工具版本，
#       stdout 本來就由 PR 決定或不含 PR 文字）。
# 為什麼：R14 把「哪些 step 會 echo fork 可控文字」寫成散文列舉，R15 四個 lens 各自找到列舉外的 step
# （shellcheck、lint-*、整個 macOS job）——散文列舉在第一輪就不封閉。與 lint-bats / lint-changelog-counts 同形：
# 規則寫成機器擋，且 `--selftest` 先證明它抓得到。
#
# 用法：test/lint-ci-log-filter.sh [workflow.yml]   預設 ../../.github/workflows/test.yml
#       test/lint-ci-log-filter.sh --selftest
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--selftest" ]; then
  if bash test/lint-ci-log-filter.sh test/fixtures/ci-log-filter-bad.yml >/dev/null 2>&1; then
    echo "lint-ci-log-filter selftest FAILED: a run step with neither neutralise.py nor LOG-FILTER was accepted" >&2
    exit 1
  fi
  if ! bash test/lint-ci-log-filter.sh test/fixtures/ci-log-filter-good.yml >/dev/null 2>&1; then
    echo "lint-ci-log-filter selftest FAILED: the compliant fixture was rejected" >&2
    exit 1
  fi
  echo "lint-ci-log-filter selftest ok: bad fixture rejected, good fixture accepted"
  exit 0
fi

file="${1:-../../.github/workflows/test.yml}"
python3 - "$file" <<'PY'
import re, sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
# 一個 step = 從 `- name:`（或 `- uses:`）到下一個同縮排的 `- ` 或下一個 job（縮排更淺的 `xxx:`）。
step_re = re.compile(r"^(\s*)- (name|uses):\s*(.*)$")
steps, cur = [], None
for i, ln in enumerate(lines):
    m = step_re.match(ln)
    if m:
        if cur: steps.append(cur)
        cur = {"indent": len(m.group(1)), "kind": m.group(2), "name": m.group(3).strip(), "start": i, "body": []}
        continue
    if cur is not None:
        stripped = ln.strip()
        # job 邊界：縮排比 step 淺、非註解、非空
        if stripped and not stripped.startswith("#") and (len(ln) - len(ln.lstrip())) < cur["indent"]:
            steps.append(cur); cur = None; continue
        cur["body"].append(ln)
if cur: steps.append(cur)
rc, seen = 0, 0
for s in steps:
    body = "\n".join(s["body"])
    if not re.search(r"^\s*run:", body, re.M):
        continue                                  # uses: 之類沒有 run 的 step 不在規則內
    seen += 1
    ok = ("neutralise.py" in body) or re.search(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)", body, re.M)
    if not ok:
        print(f"{path}:{s['start']+1}: step '{s['name']}' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾", file=sys.stderr)
        rc = 1
if seen == 0:
    print(f"no run steps found in {path} — the lint would be vacuous", file=sys.stderr); sys.exit(1)
sys.exit(rc)
PY
