#!/usr/bin/env python3
"""bash 神諭：runner 到底有沒有把 `neutralise.py` 當成管線的接收端執行——與 lint 的判定對帳。

為什麼（#33 verify R28 DA）：lint 對一個 fixture 的判定與 fixture 上 `# EXPECT:` 的宣告，**兩者都是作者寫的**。
selftest 只證明「lint 的判定 = 作者的宣告」，證不了「作者的宣告 = runner 的行為」。R28 的 DA 用一個
stub `python3` 真的跑每個 run 區塊，第一次把第三個東西（runner）拉進來對帳。這一支把那個工具放進 repo。

做法：對每個 fixture 的每個 `run:` step，用 bash（優先 5.x，與 GitHub runner 一致）執行它，PATH 前面放一個
stub `python3`：被呼叫時若引數以 `neutralise.py` 結尾，就記下 stdin 是不是管線。然後與 lint 的逐 step 判定比：

  lint pass      ∧ oracle piped                    → 一致
  lint pass      ∧ oracle 非 piped ∧ step 有 LOG-FILTER 宣告 → 一致（宣告的豁免）
  lint RULE-red  ∧ oracle 非 piped                 → 一致
  lint RULE-red  ∧ oracle piped                    → **不一致：誤擋**（runner 真的過濾了，lint 說沒有）
  lint pass      ∧ oracle 非 piped ∧ 無宣告        → **不一致：繞過**（lint 放行，runner 沒過濾）
  lint PARSE                                       → 不可比（整檔 fail-closed，不落到 step 層）

**適用邊界（明寫）**：lint 依設計不判可達性（`if false; then … | python3 …neutralise.py; fi` 它算「有管線」），
神諭卻是真的跑——這類 fixture 的不一致是**設計上的**，列在 KNOWN_DISAGREE 並寫理由。神諭不用 `-e`：
runner 用 `bash -e`，但這裡要問的是「管線有沒有被建立」，前面的指令失敗屬於可達性、不屬於本題。

**盲區（明寫）**：YAML 層用 PyYAML 解析，而 GitHub 的 YAML 解析器與它**不同**——R28 探針實測 tab 分隔的引號 key
PyYAML 拒絕、GitHub 照樣執行。所以 `YAML-FAIL` 那一格是神諭**看不到**的地方，不是「runner 也不會跑」的保證；
反方向也成立：PyYAML 接受不代表 GitHub 接受。神諭對帳的是 shell 層（管線有沒有建立），YAML 層的真值仍要靠探針。
本輪它在 shell 層之外仍抓到一件事：`good-semicolon-logfilter` 前一版根本不是合法 YAML（plain scalar 裡有 `: `），
selftest 三輪都綠——「lint 判定 = 作者宣告」對一個 runner 不會跑的檔案照樣成立。

依賴：PyYAML（`python3 -m pip install pyyaml`；CI 的 ubuntu job 已裝）。缺就 fail-loud，不靜默跳過。
用法：test/oracle.py [FILE…]   不給檔案 → 全部 test/fixtures/ci-log-filter-*.yml
退出碼：有 KNOWN_DISAGREE 之外的不一致 → 1；KNOWN_DISAGREE 裡的項目變成一致（理由不再成立）→ 1；否則 0。
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
LINT = HERE / "lint-ci-log-filter.sh"
FIXTURES = HERE / "fixtures"

try:
    import yaml
except ImportError:                       # 依賴缺席不是「沒有不一致」——那是沒量到
    print("✗ oracle.py 需要 PyYAML：python3 -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# (fixture 檔名, step 名) → 理由。每一條都要能說出「runner 與 lint 為什麼依設計會不同」；說不出來的就是缺陷。
KNOWN_DISAGREE = {
}

STUB = '''#!/bin/sh
for a in "$@"; do case "$a" in *neutralise.py) if [ -p /dev/stdin ]; then echo piped >> "$ORACLE_MARK"; else echo unpiped >> "$ORACLE_MARK"; fi;; esac; done
cat >/dev/null 2>&1; exit 0
'''


def pick_bash():
    for cand in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("找不到 bash")


def oracle(run, bash, stub_bin):
    with tempfile.TemporaryDirectory() as d:
        mark = os.path.join(d, "mark")
        env = {"PATH": stub_bin + ":/usr/bin:/bin", "ORACLE_MARK": mark, "PR_TITLE": "X", "HOME": d}
        try:
            subprocess.run([bash, "-c", run], env=env, cwd=d, capture_output=True, timeout=5)
        except subprocess.TimeoutExpired:
            return "timeout"
        if not os.path.exists(mark):
            return "not-invoked"
        return "piped" if "piped" in open(mark).read().split() else "unpiped"


def steps_with_lines(text):
    """[(job, step-name, run, (start_line, end_line))]，行號 0-based，用 yaml.compose 的 mark 取範圍。"""
    root = yaml.compose(text)
    out = []
    if not isinstance(root, yaml.MappingNode):
        return out
    for k, v in root.value:
        if k.value != "jobs" or not isinstance(v, yaml.MappingNode):
            continue
        for jk, jv in v.value:
            if not isinstance(jv, yaml.MappingNode):
                continue
            for sk, sv in jv.value:
                if sk.value != "steps" or not isinstance(sv, yaml.SequenceNode):
                    continue
                for st in sv.value:
                    if not isinstance(st, yaml.MappingNode):
                        continue
                    kv = {kk.value: vv for kk, vv in st.value if isinstance(kk, yaml.ScalarNode)}
                    run = kv.get("run")
                    if not isinstance(run, yaml.ScalarNode):
                        continue
                    name = kv["name"].value if isinstance(kv.get("name"), yaml.ScalarNode) else "<未命名>"
                    out.append((jk.value, name, run.value, (st.start_mark.line, st.end_mark.line)))
    return out


def main(argv):
    files = [pathlib.Path(a) for a in argv] or sorted(FIXTURES.glob("ci-log-filter-*.yml"))
    bash = pick_bash()
    ver = subprocess.run([bash, "-c", 'echo "$BASH_VERSION"'], capture_output=True, text=True).stdout.strip()
    print("bash: %s (%s)" % (bash, ver))
    rows, disagree, stale = [], [], []
    with tempfile.TemporaryDirectory(prefix="oracle-") as d:
        stub_bin = os.path.join(d, "bin"); os.mkdir(stub_bin)
        p = os.path.join(stub_bin, "python3"); open(p, "w").write(STUB); os.chmod(p, 0o755)
        for f in files:
            text = f.read_text(encoding="utf-8")
            try:
                steps = steps_with_lines(text)
            except yaml.YAMLError:
                rows.append((f.name, "-", "YAML-FAIL", "-", "不可比（PyYAML 也拒絕）")); continue
            r = subprocess.run(["bash", str(LINT), str(f)], capture_output=True, text=True)
            red = set(re.findall(r"RULE: step '([^']*)'", r.stderr))
            parse = ": PARSE: " in r.stderr
            lines = text.split("\n")
            for _job, name, run, (a, b) in steps:
                o = oracle(run, bash, stub_bin)
                decl = any("LOG-FILTER:" in l for l in lines[a:b + 1])
                lint = "RULE-red" if name in red else ("PARSE" if parse else "pass")
                if lint == "PARSE":
                    verdict = "不可比（fail-closed）"
                elif lint == "pass" and (o == "piped" or decl):
                    verdict = "一致"
                elif lint == "RULE-red" and o != "piped":
                    verdict = "一致"
                elif lint == "RULE-red":
                    verdict = "不一致：誤擋"
                else:
                    verdict = "不一致：繞過"
                key = (f.name, name)
                if verdict.startswith("不一致"):
                    if key in KNOWN_DISAGREE:
                        verdict += "（已知：%s）" % KNOWN_DISAGREE[key]
                    else:
                        disagree.append(key)
                elif key in KNOWN_DISAGREE:
                    stale.append(key)
                rows.append((f.name, name, lint, o, verdict))
    w = max(len(r[0]) for r in rows)
    for fn, name, lint, o, verdict in rows:
        print("%-*s  %-40s lint=%-9s oracle=%-12s %s" % (w, fn, name[:40], lint, o, verdict))
    n = len(rows)
    print("\n%d 個 step：一致 %d、不一致 %d（已知 %d）、不可比 %d"
          % (n, sum(1 for r in rows if r[4] == "一致"),
             sum(1 for r in rows if r[4].startswith("不一致")), sum(1 for r in rows if "（已知" in r[4]),
             sum(1 for r in rows if r[4].startswith("不可比"))))
    rc = 0
    if disagree:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 之外的不一致（lint 與 runner 對同一個 step 說不同的話）：")
        for fn, name in disagree: print("  - %s :: %s" % (fn, name))
    if stale:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 裡的項目現在一致了（理由不再成立，移除它）：")
        for fn, name in stale: print("  - %s :: %s" % (fn, name))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
