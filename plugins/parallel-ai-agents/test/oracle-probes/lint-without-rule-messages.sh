#!/bin/bash
# 反向探針（由 test/oracle_selfcheck.py 經 ORACLE_LINT 使用）：一支**刻意不含**神諭用來認 RULE 的兩句
# 訊息字面的 lint。未突變的 test/oracle.py 在讀任何 fixture 之前就要具名退出；這個檔永遠不可以跟真的
# lint 同步——它存在的意義就是「漂移了」。
exit 0
