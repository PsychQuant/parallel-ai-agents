#!/usr/bin/env bash
# ORACLE-BASH-SUPPORTED: 5.2 5.3
# 神諭反向探針用的假 lint（R42 WP7）：預設模式一律放行；`--strict` 下每個 step **只**判 pipefail 那一條 RULE
# （「卻沒有跑在 pipefail 之下」）。拿去跑一個 pipefail 確實開著的 step：神諭的探針看到開著，這一條 RULE 就是誤擋——
# 歸進文法外、檔頭沒宣告 ⇒ rc=1。R35–R41 的神諭把「唯一的 RULE 是 pipefail」一律判不可比、整步跳過；誰把那個跳過改回來，
# 這一項就不再失敗（`oracle_selfcheck.py` 第 19 項）。「不在 `--strict` 的正面文法裡」只為神諭的耦合檢查而出現在這裡。
f="${!#}"
case " $* " in *" --strict "*) ;; *) exit 0 ;; esac
grep -n '^ *- name:' "$f" | while IFS=: read -r ln _; do
  echo "$f:$ln: RULE: [--strict] 假 lint：step 有管線卻沒有跑在 pipefail 之下" >&2
done
exit 1
