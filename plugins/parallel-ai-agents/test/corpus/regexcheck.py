#!/usr/bin/env python3
"""`FL_REDIR_BAD_RE` 與 `FL_REDIR_DUP_OK_RE` 是否互斥的窮舉檢查（#33 verify R42，opsweep 的 EXPECTED_SURVIVE 依據）。

為什麼進 repo：`fl_tokens` 的 `if m and FL_REDIR_BAD_RE.match(s, i) and not FL_REDIR_DUP_OK_RE.match(s, i):` 拿掉 `not DUP_OK`
之後，語料與所有手寫輸入都沒有任何一檔不同——「零區分」不等於等價。這支把等價性換成可重跑的窮舉：
在「重導向運算子會用到的十個字元」的字母表上，列出長度 0 到 N（預設 7）的**所有**字串，逐一檢查
`FL_REDIR_AT_RE`、`FL_REDIR_BAD_RE`、`FL_REDIR_DUP_OK_RE` 是否**同時**在位置 0 命中。同時命中的字串就是拿掉 `not DUP_OK` 會翻色的輸入。

範圍（沒有量、不宣稱）：字母表以外的字元（兩個正規式的字元類別與前瞻只用到這十個字元與「其他字元」；「其他字元」在
這裡以 `x` 代表一個，因為兩個正規式對非列出字元的處理都是「不匹配」）、長度超過 N 的字串（兩個正規式的最長匹配加前瞻約 6 個
字元，`[0-9]*` 前綴以多個數字重複——N=7 已包含 `2>&1` 前面再加兩個數字的情形）。

用法：regexcheck.py [--lint PATH] [--max N]
  rc=0：沒有任何字串同時命中；rc=1：列出同時命中的字串。
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lint", default=str(HERE.parent / "lint-ci-log-filter.sh"))
    ap.add_argument("--max", type=int, default=7)
    a = ap.parse_args()
    rx = load_regexes(a.lint)
    at, bad, ok = rx["FL_REDIR_AT_RE"], rx["FL_REDIR_BAD_RE"], rx["FL_REDIR_DUP_OK_RE"]
    alpha = list("012<>&|; \nx")
    n = both = 0
    for length in range(a.max + 1):
        for t in itertools.product(alpha, repeat=length):
            s = "".join(t)
            n += 1
            if at.match(s) and bad.match(s) and ok.match(s):
                both += 1
                print("同時命中：%r" % s)
    print("窮舉 %d 個字串（字母表 %d 個字元、長度 0 到 %d），同時命中 %d 個" % (n, len(alpha), a.max, both))
    return 1 if both else 0


if __name__ == "__main__":
    sys.exit(main())
