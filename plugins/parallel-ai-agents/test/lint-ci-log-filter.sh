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
  # R16 requirements F3 / security S-3 / regression F4：四種寫法先前靜默繞過 step 解析
  for f in ci-log-filter-bypass-run-first ci-log-filter-bypass-flow ci-log-filter-bypass-comment ci-log-filter-bypass-leading; do
    if bash test/lint-ci-log-filter.sh "test/fixtures/$f.yml" >/dev/null 2>&1; then
      echo "lint-ci-log-filter selftest FAILED: $f.yml must be rejected" >&2
      exit 1
    fi
  done
  echo "lint-ci-log-filter selftest ok: bad fixture rejected, good fixture accepted"
  exit 0
fi

# R16 DA-4：守備目標不寫死單檔——`.github/workflows/` 底下每一份 workflow 都檢查（新增第二份 workflow 不會漏）。
if [ $# -gt 0 ]; then files=("$@"); else files=(../../.github/workflows/*.yml); fi
# R16 logic L-2：非 monorepo 佈局（plugin cache 副本）沒有 .github/ —— 先前裸 traceback 並讓 run.sh 整支中止。
if [ ! -f "${files[0]}" ]; then
  echo "lint-ci-log-filter: 找不到 ${files[0]}（非 monorepo 佈局？）—— 這條 lint 本次無法跑" >&2
  exit 2
fi
python3 - "${files[@]}" <<'PY'
import re, sys
rc_all = 0
for path in sys.argv[1:]:
  lines = open(path, encoding="utf-8").read().split("\n")
  # 一個 step = `steps:` 底下**任何**以 `- ` 開頭的清單項（不只 `- name:`／`- uses:`——R16 requirements F3：
  # `- run:` 起頭的 step 先前整個看不見），到下一個同縮排的 `- ` 或下一個 job（縮排更淺的 `xxx:`）。
  # flow mapping（`- {name: x, run: y}`）本 lint 不解析 → 直接拒絕，請改用 block 寫法（fail-loud，不是 silently pass）。
  step_re = re.compile(r"^(\s*)- (\S.*)$")
  steps, cur = [], None
  rc_flow = 0
  for i, ln in enumerate(lines):
      m = step_re.match(ln)
      if m:
          if cur:
              # R16 security S-3 ④／regression F4：緊接在下一個 `- ` 之前的純註解行屬於下一個 step 的前導，不是前一個
              # step 的 body——否則寫在 `- name:` 上方的 `# LOG-FILTER:` 會替前一個 step 放行。剝掉尾端註解行。
              while cur["body"] and (cur["body"][-1].strip().startswith("#") or not cur["body"][-1].strip()):
                  cur["body"].pop()
              steps.append(cur)
          first = m.group(2).strip()
          if first.startswith("{"):
              print(f"{path}:{i+1}: step 用 flow mapping 寫法（`- {{…}}`）——本 lint 不解析它，請改用 block 寫法", file=sys.stderr)
              rc_flow = 1
          kind, _, rest = first.partition(":")
          cur = {"indent": len(m.group(1)), "kind": kind.strip(), "name": rest.strip() if kind.strip() == "name" else f"<{kind.strip()}>",
                 "start": i, "body": [ln.replace("- run:", "  run:", 1)] if kind.strip() == "run" else []}
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
      # R16 security S-3 ②：`neutralise.py` 只算**非註解行**上的（寫在註解裡不算過濾）。
      # `# LOG-FILTER: in-process` 是自我宣告——lint 不查證該程式真的自帶 LineSanitiser（已知限制，明寫；
      # 本 repo 唯一的 in-process 是 validate.py，其 LineSanitiser 由 test_validate.py 釘住）。
      code_lines = [l for l in s["body"] if not l.strip().startswith("#")]
      ok = any("neutralise.py" in l for l in code_lines) or re.search(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)", body, re.M)
      if not ok:
          print(f"{path}:{s['start']+1}: step '{s['name']}' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾", file=sys.stderr)
          rc = 1
  if seen == 0:
      print(f"no run steps found in {path} — the lint would be vacuous", file=sys.stderr); rc_all = 1
  rc_all = rc_all or rc or rc_flow
sys.exit(rc_all)
PY
