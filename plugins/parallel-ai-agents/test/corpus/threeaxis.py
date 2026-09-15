#!/usr/bin/env python3
"""三軸量測：對一份語料清單，逐檔比對 base 與 head 兩版 lint 的 RULE 行／PARSE 行／rc。

為什麼是三軸不是一軸（#33 verify R26 M7）：只數 `RULE:` 看不到誤擋方向——一個修法可以讓 RULE 少一條、PARSE
多十條，rc 從綠翻紅，而「RULE 沒增加」照樣成立。三軸分開報，GREEN→RED（base 綠、head 紅）是誤擋，
RED→GREEN 是放寬——放寬的每一檔都要能說出它本來為什麼紅。

分母（#33 verify R26 M7／R28 DA D11）：**base-綠檔數**是誤擋方向的靈敏度分母；分母不為零仍不等於
「涵蓋了觸發形狀」——每個新機制的觸發形狀在分母裡各有幾檔，由 `shapes.py` 另報。

用法：threeaxis.py --base <git ref> <list> [--head <lint path>] [-v] [--write-green <out>]
  list 每行 `<hash> <path>` 或 `x <path>` 或 `<path>`；`#` 開頭略過。base 版 lint 用 `git archive <ref>` 取，
  不碰工作樹；head 預設是本 repo 的 test/lint-ci-log-filter.sh。`--write-green` 把 base-綠清單寫出來給 shapes.py 用。
"""
import argparse
import collections
import concurrent.futures as cf
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent            # test/corpus
PLUGIN = HERE.parent.parent                                # plugins/parallel-ai-agents
REPO = PLUGIN.parent.parent
REL = "plugins/parallel-ai-agents/test/lint-ci-log-filter.sh"


def read_list(p):
    out = []
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        parts = l.split(" ", 1)
        out.append(parts[1].strip() if len(parts) == 2 else parts[0])
    return out


def run(lint, f):
    r = subprocess.run(["bash", lint, f], capture_output=True, text=True)
    out = r.stdout + r.stderr
    rule = [re.sub(r"^.*?:(\d+): ", r"L\1: ", l) for l in out.splitlines() if ": RULE: " in l]
    parse = [re.sub(r"^.*?:(\d+): ", r"L\1: ", l) for l in out.splitlines() if ": PARSE: " in l]
    return r.returncode, rule, parse


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("list")
    ap.add_argument("--base", required=True, help="git ref（用 git archive 取那一版的 lint）")
    ap.add_argument("--head", default=str(PLUGIN / "test" / "lint-ci-log-filter.sh"))
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--write-green", metavar="OUT", help="把 base-綠檔清單寫出（每行 `x <path>`）")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    files = read_list(a.list)
    with tempfile.TemporaryDirectory(prefix="threeaxis-") as d:
        subprocess.run("git -C %s archive %s %s | tar -x -C %s" % (REPO, a.base, REL, d), shell=True, check=True)
        base = str(pathlib.Path(d) / REL)
        res = {}
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            futs = {ex.submit(lambda f=f: (run(base, f), run(a.head, f))): f for f in files}
            for fu in cf.as_completed(futs):
                res[futs[fu]] = fu.result()
    n = len(res)
    bgreen = [f for f, (b, h) in res.items() if b[0] == 0]
    hgreen = [f for f, (b, h) in res.items() if h[0] == 0]
    g2r = [f for f in bgreen if res[f][1][0] != 0]
    r2g = [f for f, (b, h) in res.items() if b[0] != 0 and h[0] == 0]
    rb = sum(len(b[1]) for b, h in res.values()); rh = sum(len(h[1]) for b, h in res.values())
    pb = sum(len(b[2]) for b, h in res.values()); ph = sum(len(h[2]) for b, h in res.values())
    newrule, lostrule, newparse, lostparse = (collections.Counter() for _ in range(4))
    for f, (b, h) in res.items():
        for l in set(h[1]) - set(b[1]): newrule[(f, l)] += 1
        for l in set(b[1]) - set(h[1]): lostrule[(f, l)] += 1
        for l in set(h[2]) - set(b[2]): newparse[(f, l)] += 1
        for l in set(b[2]) - set(h[2]): lostparse[(f, l)] += 1
    print("corpus files=%d  base(%s)-green(denominator)=%d  head-green=%d" % (n, a.base, len(bgreen), len(hgreen)))
    print("RULE:  base %d -> head %d   new %d  lost %d" % (rb, rh, len(newrule), len(lostrule)))
    print("PARSE: base %d -> head %d   new %d  lost %d" % (pb, ph, len(newparse), len(lostparse)))
    print("per-file rc: GREEN->RED %d  RED->GREEN %d" % (len(g2r), len(r2g)))
    short = lambda f: "/".join(f.split("/")[-2:])
    for f in g2r: print("  G->R:", short(f), "|", (res[f][1][1] + res[f][1][2])[:1])
    for f in r2g: print("  R->G:", short(f), "| base said:", (res[f][0][1] + res[f][0][2])[:1])
    if a.v:
        for title, c in (("new PARSE lines (head only)", newparse), ("lost PARSE lines (base only)", lostparse),
                         ("new RULE lines", newrule), ("lost RULE lines", lostrule)):
            print("\n-- " + title + ":")
            for (f, l), _ in sorted(c.items()): print("  ", short(f), "|", l[:150])
    if a.write_green:
        pathlib.Path(a.write_green).write_text("".join("x %s\n" % f for f in sorted(bgreen)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
