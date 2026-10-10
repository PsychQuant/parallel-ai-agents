#!/usr/bin/env bash
# ORACLE-BASH-SUPPORTED: 5.2 5.3
# 神諭反向探針用的假 lint（R39，#33 verify R38 第 3、6 列）：預設模式一律放行；`--strict` 下每個 step 都判正面文法的
# RULE（訊息含「不在 `--strict` 的正面文法裡」；R42 以前是群組規則），從不判 pipefail（「卻沒有跑在 pipefail 之下」只為神諭的耦合檢查而出現在這裡）。
# 用途：讓神諭走到「lint 放行、`--strict` 擋下」的歸類分支，量的是**神諭的歸類**，不是 lint。
f="${!#}"
case " $* " in *" --strict "*) ;; *) exit 0 ;; esac
grep -n '^ *- name:' "$f" | while IFS=: read -r ln _; do
  echo "$f:$ln: RULE: [--strict] 假 lint：run 區塊不在 \`--strict\` 的正面文法裡" >&2
done
exit 1
