#!/usr/bin/env bash
# ORACLE-BASH-SUPPORTED: 5.2 5.3
# 神諭反向探針用的假 lint（R39，#33 verify R38 第 7 列）：預設模式一律放行；`--strict` 下**只有**檔案裡出現 `set -E`
# 開頭的前綴時才判正面文法的 RULE（「不在 `--strict` 的正面文法裡」；R42 以前是群組規則）——模擬「`--strict` 擋下這個 step，但原因與外流無關」。
# 「卻沒有跑在 pipefail 之下」只為神諭的耦合檢查而出現在這裡。
f="${!#}"
case " $* " in *" --strict "*) ;; *) exit 0 ;; esac
grep -q 'set -E' "$f" || exit 0
grep -n '^ *- name:' "$f" | while IFS=: read -r ln _; do
  echo "$f:$ln: RULE: [--strict] 假 lint：run 區塊不在 \`--strict\` 的正面文法裡（set -E）" >&2
done
exit 1
