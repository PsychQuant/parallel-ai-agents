#!/usr/bin/env python3
"""把 stdin 經 validate.py 的 `LineSanitiser` 過一遍再印到 stdout —— CI step log 的 workflow-command 中和。

#33 verify R14（logic L-4 / security S2）：R13 在 test.yml 用一行 `sed` 做這件事，是**第二份實作**，
而且第一天就分岔：`[[:space:]]` 比 .NET `IsWhiteSpace` 小（U+00A0 開頭的 `::` 穿過）、`^` 只認 `\\n`
（含 `\\r` 的檔名穿過——而同一個 commit 的 `LineSanitiser._LINE_END` 就是 `(?<=[\\r\\n])`）。
R11/R12 兩輪在 Python 端修掉的洞，在 shell 端重生。所以「行」與「行首空白」只能有一個定義：這支只是
把 stdin 接到那份實作上。哪些 step 經過它、哪些明示不過濾（bats／node／codex-call bats 執行 PR 自己的程式碼，
安裝與版本 step 不含 PR 文字）由 `test/lint-ci-log-filter.sh` 逐 step 機械檢查；它自己永遠 exit 0，上游的非零由
`set -o pipefail` 保留。它本身是 PR 可控的檔（fork 可以把它改成 cat）——那是 `on: pull_request` 執行 PR 程式碼的
固有面，test.yml 開頭已明寫。

用法：<command> 2>&1 | python3 scripts/neutralise.py
"""
import codecs
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import LineSanitiser  # noqa: E402


def main():
    """**串流**，不是 all-or-nothing（#33 verify R24 DA-9／security S-4）。

    前一版是 `sys.stdin.buffer.read()` —— 讀到 **EOF 才動**。實測：producer 每 0.5 s 印一行時，
    t=0.8 s 經過濾器是 **0 bytes**、不經過濾器已有兩行；而把整個 process group SIGKILL（那正是
    `timeout-minutes` 與 cancel 的實際行為）時，經過濾器 **0 bytes**、對照組 31 bytes。
    也就是說：**任何被逾時或取消砍掉的 step，它的 log 會整段消失** —— fail-silent 出現在專門
    為了防 fail-silent 而建的機制上。

    `read1()` 而不是 `read()`：後者會等到收滿 n bytes 或 EOF 才回，對慢速 producer 一樣不串流。
    增量解碼器而不是逐塊 `.decode()`：後者會把跨塊邊界的多位元組字元切成兩半、產生本來不存在的
    替代字元。`LineSanitiser` 自己會緩衝未完成的一行，所以「一行永遠是一行」的保證不受影響。
    """
    out = sys.stdout
    try:
        out.reconfigure(errors="replace")
    except AttributeError:                                          # 3.8 之前的 TextIOWrapper
        pass
    w = LineSanitiser(out)
    dec = codecs.getincrementaldecoder("utf-8")(errors="replace")   # 非 UTF-8 不得讓過濾器炸
    while True:
        chunk = sys.stdin.buffer.read1(65536)
        if not chunk:
            break
        w.write(dec.decode(chunk))
        out.flush()
    w.write(dec.decode(b"", final=True))
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
