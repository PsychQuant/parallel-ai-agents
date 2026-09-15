#!/usr/bin/env python3
"""作者無關的運算子突變掃描：對 `lint-ci-log-filter.sh` 內嵌的 Python 逐一套用**固定的**運算子，看 `--selftest` 抓不抓得到。

為什麼還要這一支（#33 verify R28 DA 的中心診斷）：`mutation_check.py` 的具名靶是**作者挑的**——RED 驗證的對象、
突變的選擇、fixture 的內容，三者都由剛寫完那段程式碼的人決定。R28 的 DA 用固定運算子掃 R26 的新機制，
62 個突變體 29 個存活，其中四個是**當輪剛修好的機制**（`probe == delim`、`balanced`、`top_key == "jobs"`…）——
靶清單裡沒有它們，因為作者沒想到要放。這一支把「挑」拿掉：運算子集合是封閉的、套用位置由 AST 決定，
作者剩下的選擇只有 EXPECTED_SURVIVE（而那個集合的每一條都要能回答「為什麼等價」，且受下方比例上限約束）。

運算子（封閉列舉，五種；改動這個集合是另一次 change）：
  strip→id       `x.strip()/.rstrip()/.lstrip()` 的呼叫換成 `x`
  ±1→±2          `+= 1`／`-= 1` 換成 `+= 2`／`-= 2`
  drop-operand   `a and b`／`a or b` 拿掉其中一個運算元
  startswith→F   `x.startswith(...)` 換成 `False`
  ==↔!=          `==` 換成 `!=`

用法：
  test/opsweep.py --since REF   只掃「自 REF 起被改動的區域」：被 diff 觸及的**整個函式**，加上模組層**新增／改動的行**
                                （R28 DA 指定的守備範圍：`git diff db0c0f2..HEAD` 觸及的函式；模組層以行文本比對）
  test/opsweep.py               整段內嵌 Python（不分區域；數字只供揭露，收手條件用 --since）
  test/opsweep.py --list        只列突變體 id 與數量，不跑
  test/opsweep.py --json F      把結果寫成 JSON（CI／量測用）
退出碼：有**非預期**存活或**預期存活被殺**（等價性不再成立）→ 1；否則 0。

EXPECTED_SURVIVE 的紀律（G-R29-5）：
  (a) 每一條要寫理由，且理由是「依構造等價」——不是「fixture 沒蓋到」；後者的正解是補會翻色的 fixture。
  (b) 修法型的突變體（關掉一個當輪剛修好的機制）**不得**列入——那正是「新機制沒有網」。
  (c) 集合大小 ≤ 存活總數的 1/3（含預期）；超過就是在用這個集合藏東西（R13 DA-5）。程式會檢查。
"""
import argparse
import ast
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent          # plugins/parallel-ai-agents/test
PLUGIN = HERE.parent
LINT = HERE / "lint-ci-log-filter.sh"

# 突變體 id 的形狀：`<op>|<函式>|<該行去空白的原文>|<同一行第幾個>`。用原文不用 offset：offset 會隨任何改動漂移，
# 原文只在那一行真的改了才變——而那時本來就該重新判讀。
EXPECTED_SURVIVE = {   # id → 理由（依構造等價）。每一條都要能回答「為什麼關掉它沒有任何輸出會變」
    # `len(v) >= 2` 只擋單一字元的 `'`／`"`：那是沒收尾的引號，不是合法 YAML（PyYAML ScannerError、GitHub
    # 「workflow file issue」），runner 不會跑。拿掉守衛只改變 lint 對無效輸入的訊息，不改變任何合法輸入的判定。
    "drop-operand|yaml_decode_scalar|if len(v) >= 2 and v[0] == v[-1] == \"'\":|1": "單字元 `'` 是沒收尾的引號、非合法 YAML；守衛只防越界",
    "drop-operand|yaml_decode_scalar|if len(v) >= 2 and v[0] == v[-1] == '\"':|1": "單字元 `\"` 同上",
    # 純空白行剝縮排後變成空行：兩者對 shell_scan 都是「沒有 token」，heredoc 內文比對也只看終止字。
    "strip→id|dedent_block|return [lines[0]] + [(l[pad:] if l.strip() else l) for l in lines[1:]]|1": "純空白行剝成空行，shell 語意相同",
    # `<<<` 分支關掉後落到 `<<` 分支，分隔字從第三個 `<` 起讀、而 `<` 在 SHELL_WORD_BREAK 裡 → delim 空 →
    # 不排 heredoc。依構造等價；分支保留是把「here-string 不是 heredoc」寫成程式碼（mutation_check 同一條理由）。
    "startswith→F|shell_scan|if line.startswith(\"<<<\", i):|1": "落到 `<<` 分支後 delim 為空，不排 heredoc",
}


def embedded_python(src):
    """回傳 (python 原始碼, 在 src 裡的起點)。"""
    head, rest = src.split("<<'PY'\n", 1)
    py, _tail = rest.rsplit("\nPY", 1)
    return py, len(head) + len("<<'PY'\n")


def _span(py_lines, node):
    """(start_offset, end_offset) in the python text, from ast line/col (0-based col, 1-based line)."""
    starts = [0]
    for l in py_lines:
        starts.append(starts[-1] + len(l) + 1)
    return (starts[node.lineno - 1] + node.col_offset,
            starts[node.end_lineno - 1] + node.end_col_offset)


def mutants(py):
    """依固定運算子產生 [(id, start, end, replacement)]。id 由 (op, 所在函式, 行原文, 行內序號) 組成。"""
    tree = ast.parse(py)
    lines = py.split("\n")
    func_of = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                func_of.setdefault(id(n), fn.name)
    raw = []

    def add(op, node, start, end, new):
        raw.append((start, end, op, func_of.get(id(node), "<module>"), lines[node.lineno - 1].strip(), new))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("strip", "rstrip", "lstrip"):
                s, e = _span(lines, node); vs, ve = _span(lines, node.func.value)
                add("strip→id", node, s, e, py[vs:ve])
            elif node.func.attr == "startswith":
                s, e = _span(lines, node)
                add("startswith→F", node, s, e, "False")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, (ast.Add, ast.Sub)) \
                and isinstance(node.value, ast.Constant) and node.value.value == 1:
            s, e = _span(lines, node.value)
            add("±1→±2", node, s, e, "2")
        elif isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            spans = [_span(lines, v) for v in node.values]
            for k in range(len(node.values)):
                # 拿掉第 k 個運算元：連同它前面（或它是第一個時後面）的 `and`/`or` 一起拿掉
                if k == 0:
                    s, e = spans[0][0], spans[1][0]
                else:
                    s, e = spans[k - 1][1], spans[k][1]
                add("drop-operand", node, s, e, "")
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            ls, le = _span(lines, node.left); rs, re_ = _span(lines, node.comparators[0])
            gap = py[le:rs]
            k = gap.index("==")
            add("==↔!=", node, le + k, le + k + 2, "!=")
    # 依原始碼位置排序後再編序號：同一函式裡同一行原文（`i += 1; continue` 這種）出現多次時，序號是
    # 「第幾次出現」——與行號無關，所以插入一行註解不會讓 id 漂移。
    out, seen = [], {}
    for start, end, op, fn, line, new in sorted(raw):
        key = (op, fn, line)
        seen[key] = seen.get(key, 0) + 1
        out.append(("%s|%s|%s|%d" % (op, fn, line, seen[key]), start, end, new))
    return out


def region_since(ref, py):
    """回傳述詞 mutant → 是否在區域內。區域 = 被 `git diff REF` 觸及的函式全部 ＋ 模組層新增／改動的行。
    「觸及」用函式原始碼逐行去空白比對；模組層用行文本是否存在於 REF 版判斷（改名也算新——保守方向）。"""
    base_src = subprocess.run(["git", "-C", str(PLUGIN), "show", "%s:%s" % (ref, LINT.relative_to(PLUGIN.parent.parent))],
                              capture_output=True, text=True, check=True).stdout
    base_py, _ = embedded_python(base_src)
    def funcs(text):
        tree = ast.parse(text); lines = text.split("\n")
        return {n.name: "\n".join(l.strip() for l in lines[n.lineno - 1:n.end_lineno]) for n in tree.body if isinstance(n, ast.FunctionDef)}
    bf, hf = funcs(base_py), funcs(py)
    touched = {name for name, body in hf.items() if bf.get(name) != body}
    base_lines = {l.strip() for l in base_py.split("\n")}
    def inside(mid):
        op, fn, line, _n = mid.split("|", 3)
        return fn in touched if fn != "<module>" else line not in base_lines
    return inside, touched


def run_mutant(src, py, py_off, m, work, fixtures):
    """把突變後的 lint 放進臨時 plugin 樹，跑 selftest。fixtures 是**開跑時的快照**（copy，不是 symlink）：
    R29 第一輪掃到一半時作者又加了三個 fixture，之後每個突變體都因「數量與門檻不符」被判殺——整輪後半段作廢。
    lint 原始碼與 fixture 都要在同一個時間點凍結。"""
    mid, s, e, new = m
    mutated = src[:py_off] + py[:s] + new + py[e:] + src[py_off + len(py):]
    d = tempfile.mkdtemp(dir=work, prefix="op_")
    try:
        (pathlib.Path(d) / "test").mkdir()
        p = pathlib.Path(d) / "test" / "lint-ci-log-filter.sh"
        p.write_text(mutated, encoding="utf-8")
        os.symlink(fixtures, pathlib.Path(d) / "test" / "fixtures")
        r = subprocess.run(["bash", str(p), "--selftest"], cwd=d, capture_output=True, text=True)
        out = r.stdout + r.stderr
        if r.returncode != 0 and "SyntaxError" in out:
            return "BROKEN"                 # 運算子產出不合法的程式碼：是這支的缺陷，不是套件的功勞
        if r.returncode != 0 and "Traceback" in out:
            return "CRASHED"                # 突變體讓 lint 當掉：套件抓到了，但那是「當掉」不是「判錯」——分開報
        return "KILLED" if r.returncode != 0 else "SURVIVED"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--list", action="store_true", help="只列突變體，不跑")
    ap.add_argument("--json", metavar="FILE", help="結果寫成 JSON")
    ap.add_argument("--since", metavar="REF", help="只掃自 REF 起被改動的區域（見 docstring）")
    args = ap.parse_args()
    src = LINT.read_text(encoding="utf-8")
    py, py_off = embedded_python(src)
    ms = mutants(py)
    scope = "整段內嵌 Python"
    if args.since:
        inside, touched = region_since(args.since, py)
        ms = [m for m in ms if inside(m[0])]
        scope = "自 %s 起的區域（觸及的函式：%s；加模組層新行）" % (args.since, ", ".join(sorted(touched)) or "無")
    ids = [m[0] for m in ms]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        print("✗ 突變體 id 不唯一（同一行同一運算子要靠序號分開，這裡分不開）：", sorted(dup)[:5]); return 2
    stale = sorted(set(EXPECTED_SURVIVE) - set(ids))
    if stale:
        print("✗ EXPECTED_SURVIVE 裡有不存在的突變體（那一行改了，理由要重判）：")
        for x in stale: print("  -", x)
        return 2
    print("%d 個突變體（五種運算子；%s）" % (len(ms), scope), flush=True)
    if args.list:
        for i in ids: print("  ", i)
        return 0
    t0 = time.monotonic()
    pre = subprocess.run(["bash", str(LINT), "--selftest"], cwd=PLUGIN, capture_output=True, text=True)
    if pre.returncode != 0:
        print("✗ 未突變的 selftest 就紅——先修綠再掃，否則每個突變體都會被誤判為殺掉。\n" + (pre.stdout + pre.stderr)[-1500:]); return 1
    results = {}
    with tempfile.TemporaryDirectory(prefix="opsweep-") as work:
        fixtures = pathlib.Path(work) / "fixtures"
        shutil.copytree(HERE / "fixtures", fixtures)
        for m in ms:
            st = run_mutant(src, py, py_off, m, work, fixtures)
            results[m[0]] = st
            tag = st if not (st == "SURVIVED" and m[0] in EXPECTED_SURVIVE) else "EXPECTED"
            print("  %-9s %s" % (tag, m[0]), flush=True)
    elapsed = time.monotonic() - t0
    survived = [i for i, st in results.items() if st == "SURVIVED"]
    unexpected = [i for i in survived if i not in EXPECTED_SURVIVE]
    expected = [i for i in survived if i in EXPECTED_SURVIVE]
    killed_expected = [i for i in EXPECTED_SURVIVE if results.get(i) == "KILLED"]
    broken = [i for i, st in results.items() if st == "BROKEN"]
    print("\n耗時 %.1f 分 / %d 突變體 = 每個 %.1f s" % (elapsed / 60, len(ms), elapsed / max(1, len(ms))))
    crashed = [i for i, st in results.items() if st == "CRASHED"]
    print("殺掉 %d（其中當掉 %d）/ 存活 %d（非預期 %d、預期 %d）/ 壞掉（語法）%d"
          % (sum(1 for st in results.values() if st in ("KILLED", "CRASHED")), len(crashed),
             len(survived), len(unexpected), len(expected), len(broken)))
    rc = 0
    if unexpected:
        rc = 1
        print("\n✗ 非預期存活（補會翻色的 fixture，或證明等價後列入 EXPECTED_SURVIVE 並寫理由）：")
        for i in unexpected: print("  -", i)
    if killed_expected:
        rc = 1
        print("\n✗ 預期存活卻被殺掉（等價性不再成立，從 EXPECTED_SURVIVE 移除）：")
        for i in killed_expected: print("  -", i)
    # 兩條上限：(1) 工具內守「EXPECTED_SURVIVE ≤ 本次掃描突變體數的 10%」——修完之後存活的只剩預期的，
    # 「≤ 存活的 1/3」在工具裡會退化成永遠失敗；(2) 每輪「新增條數 ≤ 該輪存活數的 1/3」是**審查規則**，
    # 對照該輪修法前的 sweep log 在 PR body 檢查（R29：30 存活 → 4 條預期 = 13%）。
    cap = len(ms) // 10
    if len(EXPECTED_SURVIVE) > cap:
        rc = 1
        print("\n✗ EXPECTED_SURVIVE（%d）超過本次突變體數的 10%%（上限 %d）——這個集合在藏東西" % (len(EXPECTED_SURVIVE), cap))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({"results": results, "elapsed_s": elapsed}, ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
