#!/usr/bin/env bash
# ORACLE-BASH-SUPPORTED: 5.2 5.3
# 神諭反向探針用的假 lint（R39，#33 verify R38 第 3 列）：兩種模式一律放行——模擬 lint 的缺口。
# 「不在 `--strict` 的正面文法裡」「卻沒有跑在 pipefail 之下」只為神諭的耦合檢查而出現在這裡。
exit 0
