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
# 用法：test/lint-ci-log-filter.sh [workflow.yml…]   預設 ../../.github/workflows/*.yml *.yaml（全部 workflow）
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
  # R16 requirements F3 / security S-3 / regression F4 + R17 requirements F-1 / logic L-1 / security S-1 / DA-B：
  # 每一種先前靜默繞過 step 解析的寫法各有一個 fixture。**用 glob 不用寫死清單**——寫死的那份會跟目錄漂
  # （同 repo 已有兩份寫死 shellcheck 清單互相不是超集的前例，#33 verify R11）。新增 fixture 自動納入。
  # 每個 fixture 內都放了一個合規 step：單獨放會被 `seen == 0` 的 vacuity 守衛判紅，那是假紅（R17 DA-B）。
  shopt -s nullglob
  bypass=(test/fixtures/ci-log-filter-bypass-*.yml)
  if [ "${#bypass[@]}" -eq 0 ]; then
    echo "lint-ci-log-filter selftest FAILED: no bypass fixtures found — the selftest would be vacuous" >&2
    exit 1
  fi
  for f in "${bypass[@]}"; do
    if bash test/lint-ci-log-filter.sh "$f" >/dev/null 2>&1; then
      echo "lint-ci-log-filter selftest FAILED: $f must be rejected" >&2
      exit 1
    fi
  done
  echo "lint-ci-log-filter selftest ok: bad fixture rejected, good fixture accepted, ${#bypass[@]} bypass fixtures rejected"
  exit 0
fi

# R16 DA-4：守備目標不寫死單檔——`.github/workflows/` 底下每一份 workflow 都檢查（新增第二份 workflow 不會漏）。
if [ $# -gt 0 ]; then files=("$@"); else files=(../../.github/workflows/*.yml ../../.github/workflows/*.yaml); fi
# `*.yaml` 沒有檔案時 glob 會留字面——過濾掉不存在的（R17 logic L-7／security S-1：GitHub 也執行 .yaml）
existing=(); for f in "${files[@]}"; do [ -f "$f" ] && existing+=("$f"); done; files=("${existing[@]:-../../.github/workflows/test.yml}")
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
  # 一個 step = `steps:` 底下**任何**清單項——dash 後跟空白**或行尾**（R17 logic L-1：R16 要求「恰好一個空白」，於是
  # bare `-`（鍵在下一行）與 dash 後兩個空白的項被併進前一個 step 而繼承其豁免；R16 requirements F3 則是 `- run:` 起頭
  # 的 step 整個看不見），到下一個同縮排的 `- ` 或下一個 job（縮排更淺的 `xxx:`）。
  # 本 lint **不解析**的寫法一律直接拒絕（fail-loud，不是 silently pass）：flow mapping（`- {…}`）、merge key（`<<:`）、
  # anchor／alias 起頭的項（`&x`／`*x`）。key 可加引號（`"run":`／`'run':`，R17 requirements F-1）。
  step_re = re.compile(r"^(\s*)-(?:\s+(\S.*)|\s*)$")
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
          first = (m.group(2) or "").strip()
          if first.startswith(("{", "<<", "&", "*")):
              print(f"{path}:{i+1}: step 用本 lint 不解析的寫法（flow mapping／merge key／anchor／alias）：`{first[:30]}`——請改用 block 寫法", file=sys.stderr)
              rc_flow = 1
          kind, _, rest = first.partition(":")
          kind = kind.strip().strip("\"'")          # R17 requirements F-1：`- "run":`／`- 'run':` 與 `- run:` 同義
          cur = {"indent": len(m.group(1)), "kind": kind or "<bare>", "name": rest.strip() if kind == "name" else f"<{kind or 'bare'}>",
                 "start": i, "body": [re.sub(r"^(\s*)-\s+[\"']?run[\"']?:", r"\1  run:", ln)] if kind == "run" else []}
          continue
      # step body 裡出現 merge key／alias（`<<: *base`、`run: *x`）：本 lint 不解析 → 拒絕（R17 logic L-1 C）
      if cur is not None and re.match(r"^\s*(<<:|[A-Za-z_\"']+:\s*\*)", ln):
          print(f"{path}:{i+1}: step '{cur['name']}' 用 merge key／alias 帶入欄位——本 lint 不解析它，請改用 block 寫法", file=sys.stderr)
          rc_flow = 1
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
      if not re.search(r"^\s*[\"']?run[\"']?:", body, re.M):     # R17：key 可加引號
          continue                                  # uses: 之類沒有 run 的 step 不在規則內
      seen += 1
      # R16 security S-3 ②／R17 S-1 ③：`neutralise.py` 要是 **pipeline 的一段**（`… | python3 <path>neutralise.py`）才算
      # 過濾——寫在註解裡、字串裡、`env:` value 裡都不算。
      # `# LOG-FILTER: in-process` 是自我宣告——lint 不查證該程式真的自帶 LineSanitiser（已知限制，明寫；
      # 本 repo 唯一的 in-process 是 validate.py，其 LineSanitiser 由 test_validate.py 釘住）。
      # 範圍限縮到 **`run:` 區塊之內**（R17 DA-B ⑤）：前一版看的是 step body 的任一非註解行，於是
      # `env:` 的 value 裡寫一段長得像管線的字就算「已過濾」。`run:` 的 value = 該行 key 之後的部分，
      # 加上後續**縮排比 `run:` 更深**的行（block scalar `|`／`>`）；遇到縮排 <= run 的非空非註解行即結束。
      run_lines, r_indent = [], None
      for l in s["body"]:
          st = l.strip()
          if r_indent is None:
              m_run = re.match(r"^(\s*)[\"']?run[\"']?:(.*)$", l)
              if m_run:
                  r_indent = len(m_run.group(1)); run_lines.append(m_run.group(2))
              continue
          if st and not st.startswith("#") and (len(l) - len(l.lstrip())) <= r_indent:
              break                                 # 同層或更淺的下一個 key → run 區塊結束
          if not st.startswith("#"):
              run_lines.append(l)
      piped = re.compile(r"\|\s*python3\s+\S*neutralise\.py(\s|$)")
      ok = any(piped.search(l) for l in run_lines) or re.search(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)", body, re.M)
      if not ok:
          print(f"{path}:{s['start']+1}: step '{s['name']}' 的 run 區塊既沒有經 neutralise.py，也沒有 `# LOG-FILTER:` 註解說明為何不過濾", file=sys.stderr)
          rc = 1
  if seen == 0:
      print(f"no run steps found in {path} — the lint would be vacuous", file=sys.stderr); rc_all = 1
  rc_all = rc_all or rc or rc_flow
sys.exit(rc_all)
PY
