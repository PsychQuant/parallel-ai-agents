#!/usr/bin/env python3
r"""`FL_REDIR_BAD_RE` 與 `FL_REDIR_DUP_OK_RE` 是否互斥的檢查（#33 verify R42，opsweep 的 EXPECTED_SURVIVE 依據；R44 更正範圍的說法）。

為什麼進 repo：`fl_tokens` 的 `if m and FL_REDIR_BAD_RE.match(s, i) and not FL_REDIR_DUP_OK_RE.match(s, i):` 拿掉 `not DUP_OK`
之後，語料與所有手寫輸入都沒有任何一檔不同——「零區分」不等於等價。這支把等價性換成可重跑的窮舉：列出某個字母表上長度 0 到 N 的**所有**字串，
逐一檢查 `FL_REDIR_AT_RE`、`FL_REDIR_BAD_RE`、`FL_REDIR_DUP_OK_RE` 是否**同時**在位置 0 命中。同時命中的字串就是拿掉 `not DUP_OK` 會翻色的輸入。

**兩遍，各自的字母表寫清楚**（R44，#33 verify R43 第 17 列：前一版寫「兩個正規式只用到這十個字元與其他字元」，不對——`BAD` 還有 `(`（`<\(`、`>\(`）、
`DUP_OK`／`BAD` 的前瞻有 tab（`[ \t\n;|&]`）、`[0-9]*` 與 `(?!2|1)` 涉及 3–9 的數字）：
  第 1 遍（基本字母表）：`0 1 2 < > & | ;` 空白 換行 `x`（`x` 代表一個「其他字元」），長度 0 到 7——`2>&1` 前面再加兩個數字的情形在內。
  第 2 遍（擴充字母表）：基本字母表加 `(`、tab、`3`（`3` 代表數字 3–9：兩個正規式對它們一視同仁），長度 0 到 6。
**這不是證明，下面才是**：`DUP_OK` 只可能由以 `2>&1` 或 `>&2` 開頭的字串命中（兩個選項都是位置 0 的字面前綴）；`BAD` 在這兩種前綴上的每一個選項都不命中——
`[<>]&(?!2|1)` 的前瞻擋掉後面接 1 或 2 的 `>&`；`[<>]&1(?<=2>&1)?(?![ \t\n;|&]|$)` 要求 `>&1` **之後不是**分隔字或結尾，而 `DUP_OK` 的 `2>&1(?=[ \t\n;|&]|$)`
要求**之後是**分隔字或結尾，兩個前瞻互相矛盾；其餘選項（`<<`、`<(`、`>(`、`&>`、`>|`、`<>`）在這兩個前綴上第二個字元就對不上。窮舉是這個論證的實證對照。

範圍（沒有量、不宣稱）：長度超過 N 的字串（兩個正規式的最長匹配加前瞻約 6 個字元）；字母表以外的字元（兩個正規式對其他字元的處理都是「不匹配」）。

用法：regexcheck.py [--lint PATH] [--max N] [--max-extended N]
  rc=0：兩遍都沒有任何字串同時命中；rc=1：列出同時命中的字串。
"""
import argparse
import ast
import itertools
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WANT = ("FL_REDIR_AT_RE", "FL_REDIR_BAD_RE", "FL_REDIR_DUP_OK_RE")


def load_regexes(lint):
    src = pathlib.Path(lint).read_text(encoding="utf-8")
    head, rest = src.split("<<'PY'\n", 1)
    py, _tail = rest.rsplit("\nPY", 1)
    found = {}
    for node in ast.parse(py).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", None) in WANT:
            found[node.targets[0].id] = eval(compile(ast.Expression(node.value), "<re>", "eval"), {"re": re})
    missing = [n for n in WANT if n not in found]
    if missing:
        sys.exit("regexcheck: lint 裡找不到 %s" % "、".join(missing))
    return found


def sweep(at, bad, ok, alpha, maxlen):
    n = both = 0
    for length in range(maxlen + 1):
        for t in itertools.product(alpha, repeat=length):
            s = "".join(t)
            n += 1
            if at.match(s) and bad.match(s) and ok.match(s):
                both += 1
                print("同時命中：%r" % s)
    return n, both


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lint", default=str(HERE.parent / "lint-ci-log-filter.sh"))
    ap.add_argument("--max", type=int, default=7, help="第 1 遍（基本字母表）的最長長度")
    ap.add_argument("--max-extended", type=int, default=6, help="第 2 遍（擴充字母表）的最長長度")
    a = ap.parse_args()
    rx = load_regexes(a.lint)
    at, bad, ok = rx["FL_REDIR_AT_RE"], rx["FL_REDIR_BAD_RE"], rx["FL_REDIR_DUP_OK_RE"]
    base = list("012<>&|; \nx")
    extended = base + list("(\t3")
    total_both = 0
    for label, alpha, maxlen in (("基本", base, a.max), ("擴充", extended, a.max_extended)):
        n, both = sweep(at, bad, ok, alpha, maxlen)
        total_both += both
        print("第%s遍：窮舉 %d 個字串（字母表 %d 個字元、長度 0 到 %d），同時命中 %d 個" % ("1" if label == "基本" else "2", n, len(alpha), maxlen, both))
    return 1 if total_both else 0


if __name__ == "__main__":
    sys.exit(main())
