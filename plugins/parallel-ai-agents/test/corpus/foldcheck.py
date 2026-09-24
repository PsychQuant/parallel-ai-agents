#!/usr/bin/env python3
"""lint 的 `dedent_block` ＋ `fold_block` 對 PyYAML 的窮舉對帳（#33 verify R37）。

為什麼進 repo（#33 verify R37 合併時協調者發現）：R37 的 e 包在 `opsweep.py` 寫下「窮舉 5,838 組合法 YAML、修完後
兩種模式 0 組不符」，指令碼卻是工作包的暫存檔、沒有進 repo，合併時已經找不到——那句話變成任何人都重跑不了的
數字。這支把同一類量測放進 repo；本 PR 對外寫的「逐行相符」數字以**這支的輸出**為準。

構造（封閉列舉，只有這些，不得類推）：
  每一行 = 10 個空白（block 的基準縮排）＋ LEAD ＋ BODY，另加一種「真正的空行」（連基準縮排都沒有）。
  LEAD ∈ {"", " ", "  ", "\\t", "\\t\\t", " \\t", "\\t "}，BODY ∈ {"", "x", "x "} → 7 × 3 ＋ 1 = 22 種行。
  `--lines N`（預設 3）行的所有組合，每組各以 `run: |` 與 `run: >` 產一份 YAML；全空白的組合略過（沒有內容可比）。
  PyYAML 拒絕的組合另計、不進分母。

比對兩個口徑，分開報：
  1. **整字串**：lint 的輸出（`None` 佔位丟掉、以換行接起）與 PyYAML 讀出的值，兩邊都去掉結尾換行後完全相等。
  2. **內容承載行**：只比「strip() 後非空」的行、依序比對。
整字串不符的組合再分類：去掉**第一個內容行之前**的所有行後就相等 ⟹「只差前導空白行」。前導空白行在第一個命令之前，
沒有任何 heredoc 開著、不承載任何 shell 詞，對 `shell_scan()` 的判定沒有影響；其餘的不符逐項列出。

用法：foldcheck.py [--lint PATH] [--lines N] [--examples K]
  rc=0：內容承載行 0 組不符、且整字串的不符全部屬於「只差前導空白行」；否則 rc=1。
"""
import argparse
import itertools
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
BASE = " " * 10
LEADS = ("", " ", "  ", "\t", "\t\t", " \t", "\t ")
BODIES = ("", "x", "x ")
SHAPES = tuple(BASE + l + b for l in LEADS for b in BODIES) + ("",)


def load_lint(path):
    """把 lint 內嵌的 Python 載進來、拿到 `dedent_block` 與 `fold_block`（不執行主迴圈）。"""
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.index("<<'PY'\n") + len("<<'PY'\n")
    body = src[start:src.rindex("\nPY\n")]
    cut = body.index("\nfor path in [a for a in sys.argv[1:] if a not in FLAGS]:")
    ns = {"__name__": "foldcheck_lint"}
    saved = sys.argv
    sys.argv = ["lint"]
    try:
        exec(compile(body[:cut], str(path), "exec"), ns)
    finally:
        sys.argv = saved
    return ns["dedent_block"], ns["fold_block"]


def content(lines):
    return [l for l in lines if l.strip()]


def after_first_content(lines):
    for i, l in enumerate(lines):
        if l.strip():
            return lines[i:]
    return []


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lint", default=str(HERE.parent / "lint-ci-log-filter.sh"))
    ap.add_argument("--lines", type=int, default=3)
    ap.add_argument("--examples", type=int, default=5)
    a = ap.parse_args(argv)
    dedent_block, fold_block = load_lint(a.lint)
    stats = {}
    other = []
    for style, folded in (("|", False), (">", True)):
        tot = rej = exact = content_bad = lead_only = 0
        for body in itertools.product(SHAPES, repeat=a.lines):
            if not any(l.strip() for l in body):
                continue
            doc = "k:\n  run: %s\n%s\n" % (style, "\n".join(body))
            try:
                v = yaml.safe_load(doc)["k"]["run"]
            except yaml.YAMLError:
                rej += 1
                continue
            tot += 1
            out = [x for x in fold_block(dedent_block([""] + list(body)), folded)[1:] if x is not None]
            got, want = "\n".join(out).rstrip("\n").split("\n"), v.rstrip("\n").split("\n")
            if got == want:
                exact += 1
                continue
            if content(got) != content(want):
                content_bad += 1
                other.append((style, body, want, got, "內容承載行不符"))
            elif after_first_content(got) == after_first_content(want):
                lead_only += 1
            else:
                other.append((style, body, want, got, "內容承載行相符、空白行的位置或內容不符"))
        stats[style] = (tot, rej, exact, content_bad, lead_only)
    for style, (tot, rej, exact, content_bad, lead_only) in stats.items():
        print("run: %s  組合 %d（PyYAML 拒絕 %d 另計）：整字串相等 %d、只差前導空白行 %d、內容承載行不符 %d、其他不符 %d"
              % (style, tot, rej, exact, lead_only, content_bad, tot - exact - lead_only - content_bad))
    for style, body, want, got, why in other[:a.examples]:
        print("  ✗ run: %s %s：%r → PyYAML %r／lint %r" % (style, why, body, want, got))
    return 0 if not other else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
