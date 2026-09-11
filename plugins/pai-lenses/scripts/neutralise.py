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

哪些 step 經過它、哪些明示不過濾：`test/lint-ci-log-filter.sh` 對 test.yml 每一個 run step 機械檢查（R15 L-2 / S-3 / F2）。

用法：<command> 2>&1 | python3 scripts/neutralise.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from validate import LineSanitiser  # noqa: E402


def main():
    data = sys.stdin.buffer.read().decode("utf-8", errors="replace")   # 非 UTF-8 不得讓過濾器炸
    out = sys.stdout
    try:
        out.reconfigure(errors="replace")
    except AttributeError:                                          # 3.8 之前的 TextIOWrapper
        pass
    w = LineSanitiser(out)
    w.write(data)
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
