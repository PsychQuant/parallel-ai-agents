#!/usr/bin/env python3
"""神諭的反向探針：只有神諭**失敗**時才成立的檢查（#33 verify R37）。

fixture 集裡的 must-fail 探針（`# ORACLE-MUST-FAIL:`）驗的是「神諭對某張 fixture 以宣告的理由失敗」。
R37 時有兩件事它驗不到——要驗它們，未突變的神諭在 fixture 集上就得是紅的：
  1. **must-fail 探針的理由比對本身**：宣告一個永遠不會出現的理由，未突變的神諭必須判「探針沒有以宣告的理由
     失敗」、rc=1（`oracle-probes/mustfail-wrong-reason.yml`）。
  2. **oracle↔lint 的 RULE 字面耦合檢查**：`ORACLE_LINT` 指到不含那兩句訊息的 lint，未突變的神諭必須在讀
     fixture 之前具名退出（`oracle-probes/lint-without-rule-messages.sh`）。
這支把兩者寫成「期待失敗」：每一項斷言神諭的 rc 與輸出裡的一句話，全部成立 rc=0。`mutation_check.py` 的
`oracle-inverted` 守備單位跑它，所以拿掉那兩道檢查的突變會讓這裡紅——R37 的神諭工作包原本把第 1 項（must-fail 理由比對）列為
「harness 結構上測不到」的預期存活；第 2 項（RULE 字面耦合檢查）是合併時才加的。「未突變＝綠」的前提對兩項都成立，
把期待寫成失敗就滿足了它。

批次與編號（編號＝下面 `CHECKS` 的順序；每一項的內容在它自己的說明欄，這裡不再複述一份會過期的描述——R43 第 21 列：
前一版的 docstring 逐批列舉、數字加起來少一項，而且寫著「二十六項」「三十項」卻沒有一個地方真的數過）：
  R37 1–2；R39 3–8；R40 9–10；R42 11–15；R42 WP7 16–19；R42 WP8 20–26；R44 27–31；R46 32–38；R48 39–45；R50 46–72。
共 72 項。守衛：`main()` 開頭比對這一行的總數與批次區間的終點是否等於 `len(CHECKS)`，不等就 rc=1——數字與清單不是兩份各自維護的東西。

用法：test/oracle_selfcheck.py      rc=0：每一項都照預期；rc=1：至少一項沒有（或上面的數字與 `CHECKS` 不符）。
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ORACLE = HERE / "oracle.py"
PROBES = HERE / "oracle-probes"
LINT = HERE / "lint-ci-log-filter.sh"

# (說明, 額外環境變數, 神諭的檔案參數, 期待的 rc, 輸出裡必須出現的字串[, 突變])
# 突變：{"lint": (錨點, 替換)} 或 {"oracle": (錨點, 替換)}——在暫存目錄產生那一份再跑（見 `run_check`）。
CHECKS = [
    ("must-fail 探針的理由比對",
     {}, [PROBES / "mustfail-wrong-reason.yml"], 1, "must-fail 探針沒有以宣告的理由失敗"),
    ("oracle↔lint 的 RULE 字面耦合檢查",
     {"ORACLE_LINT": str(PROBES / "lint-without-rule-messages.sh")},
     [HERE / "fixtures" / "ci-log-filter-good.yml"], 1, "用來認 RULE 的字面"),
    # 以下六項（R39，#33 verify R38 第 3、6、7 列）量的是**神諭的歸類**：real lint 已經擋下這些形狀，神諭走不到歸類分支，
    # 所以用 `oracle-probes/lint-*.sh` 假 lint 模擬「lint 放行」。每一項在 R38 的神諭上都是 rc=0。
    ("已觀察到外流而差分語法壞掉（多行群組）",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "multiline-group-fd3.yml"], 1, "印到 stdout"),
    ("已知類別 G 被與外流無關的原因擋下",
     {"ORACLE_LINT": str(PROBES / "lint-strict-blocks-set-E.sh")},
     [PROBES / "g-blocked-for-unrelated-reason.yml"], 1, "原因與外流無關"),
    ("S-2 的機制差分：補 `2>&1` 不消失的 stderr 外流",
     {"ORACLE_LINT": str(PROBES / "lint-strict-blocks-all.sh")},
     [PROBES / "s2-shape-fd-redirect.yml"], 1, "不是 S-2"),
    ("xtrace 外流不歸 S-2",
     {"ORACLE_LINT": str(PROBES / "lint-strict-blocks-all.sh")},
     [PROBES / "s2-shape-xtrace.yml"], 1, "xtrace 的輸出"),
    ("已觀察到外流而分類失敗、沒有類別宣告",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "unmeasured-leak-no-class.yml"], 1, "分類失敗不抵銷"),
    ("已知類別 S-2 被與外流無關的原因擋下",
     {"ORACLE_LINT": str(PROBES / "lint-strict-blocks-set-E.sh")},
     [PROBES / "s2-blocked-for-unrelated-reason.yml"], 1, "原因與外流無關"),
    ("逾時之前已經觀察到外流（R40，#33 verify R39 第 8 列）",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "timeout-after-leak.yml"], 1, "逾時之前"),
    ("宣告 ORACLE-COMPARABLE 的檔有不可比的 step（R40，#33 verify R39 放行條件 12）",
     {}, [PROBES / "comparable-declared-but-sh.yml"], 1, "ORACLE-COMPARABLE"),
    # 以下五項（R42，#33 verify R41）：KD 的方向與雜湊、版本守衛、GH_SAFE 同步、文法外的閘門。
    ("KNOWN_DISAGREE 比對方向（R41 DA-5）",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "kd-direction" / "ci-log-filter-restrict-r40-undisclosed-false-blocks.yml"], 1, "方向不符"),
    ("KNOWN_DISAGREE 比對內容雜湊",
     {}, [PROBES / "kd-hash" / "ci-log-filter-restrict-r40-undisclosed-false-blocks.yml"], 1, "內容雜湊不符"),
    ("版本守衛：bash 不在 lint 宣告的支援集合裡",
     {"ORACLE_LINT": str(PROBES / "lint-bash-unsupported.sh")},
     [HERE / "fixtures" / "ci-log-filter-good.yml"], 1, "ORACLE-BASH-SUPPORTED"),
    ("GH_SAFE_EXPRS 神諭與 lint 同步",
     {}, [HERE / "fixtures" / "ci-log-filter-good.yml"], 1, "GH_SAFE_EXPRS",
     {"oracle": ('    "github.sha", "github.run_id",', '    "github.sha", "github.actor", "github.run_id",')}),
    ("文法外類別的閘門：lint 多拒絕 `echo`",
     {}, [HERE / "fixtures" / "ci-log-filter-good-strict-group-forms.yml"], 1, "歸了類卻沒宣告",
     {"lint": ('FL_INERT = frozenset(("echo", "printf",', 'FL_INERT = frozenset(("printf",')}),
    # 以下四項（R42 WP7）：pipefail 探針與跨 step 通道。lint 放行一切（`lint-pass-all.sh`）時，神諭自己要看得出來。
    ("pipefail 探針：lint 放行、管線在 pipefail 關閉下完成",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [HERE / "fixtures" / "ci-log-filter-bypass-r40-pf-or-on.yml"], 1, "繞過（pipefail"),
    ("pipefail 探針被腳本換掉：判量不到、不判一致",
     {}, [HERE / "fixtures" / "ci-log-filter-bypass-r40-pf-trap-debug-off.yml"], 0, "量不到（pipefail 探針被換掉"),
    ("跨 step 通道：lint 放行、PR 文字寫進 GITHUB_ENV",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [HERE / "fixtures" / "ci-log-filter-bypass-r42-ghenv.yml"], 1, "跨 step 通道"),
    ("唯一的 RULE 是 pipefail、而 pipefail 其實開著：判誤擋，不整步跳過",
     {"ORACLE_LINT": str(PROBES / "lint-strict-pipefail-only.sh")},
     [HERE / "fixtures" / "ci-log-filter-good-strict-group-forms.yml"], 1, "歸了類卻沒宣告"),
    # 以下六項（R42 WP8，#33 verify R41 DA-4、logic F9、requirements s2-flip）：payload 的脈絡、取最嚴重、S-2 機制差分。
    ("payload 脈絡：註解裡的運算式", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")}, [PROBES / "ctx-comment.yml"], 1, "繞過"),
    ("payload 脈絡：heredoc 內文裡的運算式", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")}, [PROBES / "ctx-heredoc.yml"], 1, "繞過"),
    ("payload 脈絡：算術裡的運算式", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")}, [PROBES / "ctx-arith.yml"], 1, "繞過"),
    ("payload 脈絡：運算式規則關掉、正面文法接受非字面（突變）", {}, [PROBES / "ctx-comment.yml"], 1, "繞過",
     {"lint": [('        elif not drop_nonliteral:\n            raise FlatReject("非字面的 runner 運算式")',
                '        elif not drop_nonliteral:\n            out.append("")'),
               ('    if not declared and any(not gh_literal(inner) for _a, _b, inner in runner_exprs(text)):',
                '    if False:')]}),
    # R42（mutation 全輪，靶 406 重新錨定）：payload 不得依賴運算式前面的命令成功。`bash -e` 下 `false` 之後腳本就停了，
    # 每一組 payload 都要先 `|| :`；拿掉之後神諭量不到外流、只剩 fail-closed 的「繞過」（沒有「把 PR 文字印到 stdout」那句來源分類）。
    ("payload 不依賴前一個命令成功：`false ${{ … }}` 之後仍量得到外流", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "payload-after-failing-command.yml"], 1, "把 PR 文字印到 stdout"),
    ("取最嚴重：stdout 的外流勝過 stderr 的（單元測試）", {}, ["--selftest-severity"], 0, "select_most_severe ok"),
    ("S-2 機制差分：多出 baseline 沒有的外流行（突變）", {}, [HERE / "fixtures" / "ci-log-filter-oracle-r42-s2-flip.yml"], 1,
     "must-fail 探針沒有以宣告的理由失敗",
     {"oracle": ("                and not (ml[1] - base_ml[1]))", "                )")}),
    ("EXIT 失敗路徑：errexit 之下仍跑使用者的 trap 動作（R44）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "exit-trap-failure-path.yml"], 1, "跨 step 通道"),
    ("逾時保留通道證據：先寫通道、再逾時（R44）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "timeout-keeps-channel.yml"], 1, "逾時之前跨 step 通道"),
    ("注入探針：未加引號的 `[ -n $PR_TITLE ]` 讓 PR 文字被當程式碼執行（R44）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-unquoted-test.yml"], 1, "注入：PR 文字被當程式碼執行"),
    ("宣告 step 的 trap 動作裡的管線：pipefail 探針讀得到（R44）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "trap-pipeline-pipefail.yml"], 1, "繞過（pipefail"),
    ("可比的 step 不足：`--min-comparable` 對一組全是「不可比」的檔 rc=1（R44，#33 verify R43 第 22 列）",
     {}, ["--min-comparable", "1", HERE / "fixtures" / "ci-log-filter-parse-r40-bash53-funsub-space.yml"], 1, "可比的 step 只有 0 個"),
    # R46（#33 verify R45）：primitive 稽核——神諭看 `[`／`test`／`printf` 實際收到什麼、信任變數有沒有被改寫；以下三項沒有任何 PR 文字出現在 log 裡，所以只有稽核看得到。
    ("primitive 稽核：`test {-v,\"$X\"}` 的實際 argv 在文法的三種形狀之外（R46）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-brace-test.yml"], 1, "primitive 稽核"),
    ("primitive 稽核：`printf '%n'` 的格式在封閉的轉換列舉之外（R46）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-printf-n.yml"], 1, "primitive 稽核"),
    ("primitive 稽核：管線子殼層裡信任變數被具名 fd 改寫（R46）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-named-fd-trusted.yml"], 1, "信任變數"),
    ("注入探針：注入完成之後才逾時的 step（R46）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-after-timeout.yml"], 1, "注入：PR 文字被當程式碼執行"),
    ("稽核與探針的範圍：宣告而沒有觸發的 step 不進文法、不報繞過（R46）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-declared-step-not-in-grammar.yml"], 0, "一致 1"),
    ("稽核的負對照：日常的 `test`／`[`／`printf` 不誤報（R46）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-benign-test-and-printf.yml"], 0, "一致 1"),
    ("稽核與探針的範圍：只含 `||` 的宣告 step 同樣不進文法（與 lint 的 `flat_trigger` 同一套規則；R46 宣稱查核）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-declared-step-or-only-not-in-grammar.yml"], 0, "一致 1"),
    ("稽核與探針的範圍：宣告寫在 YAML 層（step 的註解行）而沒有觸發的 step 同樣不進文法（R48，R47 logic）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-declared-step-yaml-level-not-in-grammar.yml"], 0, "一致 1"),
    ("儀器完整性：改 `ORACLE_*` 環境變數沒有任何作用（`ORACLE_AUD`／`ORACLE_INJECT` 等已不存在；僅剩的 `ORACLE_PRIV` 在開頭被複製進唯讀的 `__orc_priv`，改它沒有作用）——稽核走繼承的 fd，違規照樣被看到（R50 取代 R48 的文字守衛；R49 requirements／logic／security／DA 與 Codex 同報守衛是吸收器）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-tamper-instrument-var.yml"], 1, "primitive 稽核"),
    ("儀器完整性：相對路徑重導向截斷不到儀器檔（R48，R47 security）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-tamper-relative-truncate.yml"], 1, "primitive 稽核"),
    ("儀器完整性：記錄邊界字元偽造不了稽核記錄（R48，R47 Codex）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-forged-record-boundary.yml"], 1, "primitive 稽核"),
    ("儀器完整性：cwd 裡同名的檔（`chan-GITHUB_ENV`）不是通道，截斷它截斷不到真的通道（R48 歷史項；R50 起通道檔在 `$RUNNER_TEMP/_runner_file_commands/`；R48 宣稱查核 E 組）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-tamper-channel-truncate.yml"], 1, "跨 step 通道"),
    ("稽核檔解析與儀器完整性（單元測試；R48）", {}, ["--selftest-aud"], 0, "aud_violations ok"),
    ("宣告差分不被儀器污染：xtrace 會印出路徑的 step 仍判一致（R48 量測 v9 抓到的回歸——當時儀器目錄的隨機後綴漏進去；R50 起 cwd 裡沒有儀器的資料或記錄檔〔只有 `s.sh` 與 `runner_temp/`〕，這一項守著不要再有東西漏進宣告差分）", {},
     ["--min-comparable", "1", HERE / "fixtures" / "ci-log-filter-good-r37o-module-misc-env-trace-declared-logfilter.yml"], 0, "一致 1"),
    # ── R50（#33 verify R49）：儀器改走繼承的 pipe fd、判決證據優先、行程群組收束、儀器不可信預設 rc=1。以下二十七項（46–72）。 ──
    # R49 找到的、針對稽核檔的路徑式失明法（截到 init、存檔還原、萬用字元覆寫）：稽核已經不是檔案，違規照樣被看到。通道檔仍是路徑（換成 FIFO 判量不到，見下面的 FIFO 項）；R49 的儀器目錄已不存在（`$ORACLE_PRIV` 仍可刪，判量不到〔缺 fin〕，rc=1）；
    # 哨兵／事件流仍沒有完整性檢查。**這不是防竄改**——步驟與儀器在同一個 shell，盲點類見 `instrument-*.yml` 四張探針（含對照組）對應的項。
    ("儀器完整性：把稽核截到只剩 init 也截不到——沒有稽核檔（R49 requirements F2）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-truncate-to-init.yml"], 1, "primitive 稽核"),
    ("儀器完整性：先存檔、違規、再還原也沒有稽核檔可存（R49 regression）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-save-restore-derived-path.yml"], 1, "primitive 稽核"),
    ("儀器完整性：用萬用字元覆寫成假的 init／fin 也沒有檔案可覆寫（R49 Codex 第 1 條）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-glob-overwrite-forged-init-fin.yml"], 1, "primitive 稽核"),
    ("通道檔被換成 FIFO：神諭不卡住，判量不到（儀器不可信）（R49 Codex 第 3 條）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     ["--allow-distrust", PROBES / "channel-replaced-by-fifo.yml"], 0, "不是一般檔案"),
    # 文字守衛已移除：獨立的注入探針與稽核證據都不受步驟文字影響。
    ("步驟文字提到 ORACLE_ 不關掉獨立的注入探針（R49 security／logic／Codex 同報守衛連注入探針一起關掉）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-with-oracle-token.yml"], 1, "注入"),
    ("步驟文字（註解）提到 ORACLE_ 不撤銷已被稽核看到的違規（R49 requirements F1／logic M1）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-violation-with-oracle-token-comment.yml"], 1, "primitive 稽核"),
    # 行程群組收束：確定性的快照；儀器不可信預設 rc=1。
    ("背景行程在收尾時仍在跑：整群殺掉，判量不到（儀器不可信；在 `--strict`、lint 放行、step 在文法內、記錄無違規時）；對遠超寬限的行程是確定的（R49 Codex 第 4 條，取代 R48 的 ignore_cleanup_errors）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     ["--allow-distrust", PROBES / "straggler-keeps-running.yml"], 0, "背景行程在神諭收尾時仍在跑"),
    ("儀器不可信預設讓神諭 rc=1（不是 rc=0 的吸收器）；--allow-distrust 只給探針用（R49 security 的建議）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "straggler-keeps-running.yml"], 1, "儀器不可信（R50）"),
    ("主 shell 自己關掉稽核 fd：寫不出 fin，判量不到（儀器不可信）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     ["--allow-distrust", PROBES / "audit-fd-closed-in-main-shell.yml"], 0, "主 shell 卻沒有 fin"),
    ("**已知盲點（文件化，不是保證）**：子殼層自己關掉稽核 fd，看不到那個子殼層裡的違規，判一致——這只是「步驟與儀器在同一個 shell」這個類別的一個形狀（類別探針與對照組見 `instrument-*.yml` 對應的項）；若有一天補上，這一項會紅，改它時須一併改 README 與 oracle.py 的措辭（沒有機制連結，靠人記得）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-fd-closed-in-subshell-known-blind-spot.yml"], 0, "一致 1"),
    # 宣告差分與 YAML 範圍
    ("cwd 裡沒有儀器的裸名：宣告 step 印出目錄項目（echo .*）仍判一致（R49 logic／requirements LOW）", {},
     ["--min-comparable", "1", PROBES / "declared-step-lists-cwd.yml"], 0, "一致 1"),
    ("宣告註解寫在 bare `-` 與第一個鍵之間：神諭的 step 範圍涵蓋它（R49 logic LOW）", {},
     ["--min-comparable", "1", PROBES / "yaml-bare-dash-declaration.yml"], 0, "一致 1"),
    ("YAML 層宣告而沒有觸發的 step 不進正面文法，注入探針不跑（`in_grammar(run, yaml_decl_step)` 的呼叫點；R49 logic M2）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-yaml-declared.yml"], 0, "一致 1"),
    # 把新機制接進網（R49 logic M2：5 個突變體通過 46 項 selfcheck）：證據優先、儀器不可信不關掉注入探針、儀器不可信只對 lint 放行的 step、通道檔裸名的正規化、資料流溢出、資料流沒收乾淨。
    ("證據優先：違規記錄先寫進去、之後才關掉稽核 fd——已經看到的違規不撤銷（R49 logic M1）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "audit-evidence-then-fd-closed.yml"], 1, "primitive 稽核"),
    ("儀器不可信不關掉獨立的注入探針（R49 security M）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-with-fd-closed.yml"], 1, "注入"),
    ("儀器不可信只對 lint 放行的 step：lint 已擋下（RULE-red）而神諭看到外流，仍判一致（R50）", {},
     ["--min-comparable", "1", PROBES / "audit-fd-closed-lint-blocked.yml"], 0, "一致 1"),
    ("宣告 step 列出 `$RUNNER_TEMP/_runner_file_commands`：通道檔裸名（uuid）先換成固定標記，宣告差分才判得成（R50）", {},
     ["--min-comparable", "1", PROBES / "declared-step-lists-runner-commands.yml"], 0, "一致 1"),
    ("儀器資料流有上限：超過判量不到（儀器不可信）；步驟自己的 stdout／stderr 沒有位元組上限，只受 5 秒逾時限制（`ORACLE_STREAM_CAP` 是神諭自己的環境變數，步驟改不到；R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh"), "ORACLE_STREAM_CAP": "30"},
     ["--allow-distrust", PROBES / "audit-stream-overflow.yml"], 0, "流超過 30 位元組"),
    ("有行程握著儀器的資料流卻不在步驟的行程群組裡（`set -m` 的背景工作）：收不到 EOF 也不卡住，判量不到（儀器不可信）（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     ["--allow-distrust", PROBES / "stream-held-by-other-group.yml"], 0, "資料流沒有收乾淨"),
    # 已知盲點類（R50，文件化，不是保證）：步驟與儀器同一個 shell、同一個信任域，神諭不是 sandbox。四項：對照組（沒有動儀器時，同樣的違規被看到）＋三張盲點探針（每張釘一組效果，各 step 是不同的到達方式；代表形狀，不是窮舉）。
    ("對照組：不動儀器的同一批違規（`printf '%n'`、改寫信任變數、可注入構造、pipefail 關閉）全部判『不一致：繞過』——盲點探針的『一致』『量不到』因此不是違規本來就看不到（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "instrument-fd-blind-spots-control.yml"], 1, "不一致 4"),
    ("**已知盲點類（文件化，不是保證）**：步驟用編號指到稽核或注入哨兵的 fd（單一命令重導向、先存再還原、永久關掉後偽造 fin、經 `/dev/fd/199` 偽造記錄、`exec 197>/dev/null`）——判一致；真的 `--strict` lint 對這五個 step 的寫法全部 RULE-red；經 fd 寫入的外部命令寫法（`tee /dev/fd/199`、`dd of=/dev/fd/199`、`sh -c '… >&199'`）在文法內放行，神諭同樣判一致（垃圾併進子殼層 `fin` 記錄的名稱，主 shell 的 `fin` 完好）。若有一天補上某一種，這一項會紅，改它時須一併改 README 與 oracle.py 的措辭（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "instrument-fd-known-blind-spots.yml"], 0, "一致 5"),
    ("**已知盲點類（文件化，不是保證）**：讓 pipefail 觀測量不到——`exec 198>/dev/null`（事件流）、`$ORACLE_PRIV` 裡的 FIFO、管線後接逾時的外部命令、對 PRELUDE 變數的純量指派——判『量不到』且 rc=0（R42 起的設計，R50 沒改）；真的 `--strict` lint 對前三個 step 的寫法全部 RULE-red，第四個（`__orc_want=x`）在文法內被放行（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "instrument-event-and-priv-known-blind-spots.yml"], 0, "量不到 4"),
    ("**已知盲點類（文件化，不是保證）**：不碰 fd 編號——`unset -f printf`、`builtin printf`、`unset __orc_tvn`——步驟動 PRELUDE 裝進同一個 shell 的東西，判一致；真的 `--strict` lint 對這三個 step 全部 RULE-red（`unset`／`builtin` 在文法外）（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "instrument-prelude-known-blind-spots.yml"], 0, "一致 3"),
    # 第三輪宣稱查核 I 組：事件流被偽造的行不能讓神諭崩潰（崩潰＝整輪沒有判定表）。
    ("事件流有解析不出來的行（偽造的 `P fin x`）：判量不到（儀器不可信），不崩潰（R50 第三輪宣稱查核 I 組）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     ["--allow-distrust", PROBES / "event-stream-forged-line.yml"], 0, "事件流有無法解析的行"),
    # 第四輪宣稱查核 K 組：宣告 step 的差分不被事件行帶的絕對路徑污染（K4）。
    ("宣告 step 用絕對路徑呼叫過濾器（`\"$GITHUB_WORKSPACE/scripts/neutralise.py\"`）：事件行的路徑先正規化，宣告差分判一致，不是『不一致：繞過』（R50 第四輪 K4）", {},
     ["--min-comparable", "1", PROBES / "declared-step-absolute-path-stub.yml"], 0, "一致 1"),
    # 第五輪宣稱查核 L 組：L1（stub 目錄的深目錄樹；Python 3.12 的 CI 才會崩，本機 3.13 看不出來，由 Docker 實證）、L3（stub 的 `--version` 在 errexit 下截斷後面的整段）。
    ("深目錄樹建在全程序共用的 stub 目錄（`PATH` 的第一段）：神諭離開 `main()` 清理時不崩潰，判定表照印（R50 第五輪 L1，K1 的漏網之魚；Python ≤3.12 才重現）", {},
     ["--min-comparable", "1", PROBES / "deep-tree-in-stub-dir.yml"], 0, "一致 1"),
    ("stub `python3 --version` 之後的 `echo \"$PR_TITLE\"`（errexit 的 step）：判『不一致：繞過』，不是被截斷而『量不到』（R50 第五輪 L3）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "stub-python-version-errexit.yml"], 1, "不一致：繞過"),
]


def run_check(extra, files, mut):
    """跑一項：`mut` 給了就先在暫存目錄產生突變版（錨點必須恰好出現一次），回傳 (rc, 輸出)。"""
    env = dict(os.environ, **extra)
    oracle = ORACLE
    with tempfile.TemporaryDirectory(prefix="oracle-selfcheck-") as d:
        for kind, pairs in (mut or {}).items():
            src_path = LINT if kind == "lint" else ORACLE
            src = src_path.read_text(encoding="utf-8")
            for anchor, repl in ([pairs] if isinstance(pairs, tuple) else pairs):
                if src.count(anchor) != 1:
                    return None, "突變錨點在 %s 裡出現 %d 次（要恰好 1 次）：%r" % (src_path.name, src.count(anchor), anchor)
                src = src.replace(anchor, repl)
            if kind == "lint":
                t = pathlib.Path(d) / "test"; t.mkdir()
                dst = t / LINT.name
                env["ORACLE_LINT"] = str(dst)
            else:
                dst = pathlib.Path(d) / ORACLE.name
                oracle = dst
                env.setdefault("ORACLE_LINT", str(LINT))   # 突變版神諭的 HERE 是暫存目錄，lint 要明確指回 repo 的那一支
            dst.write_text(src, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, str(oracle)] + [str(f) for f in files],
                               env=env, capture_output=True, text=True, errors="replace", timeout=600)
        except subprocess.TimeoutExpired as e:
            return 124, "（selfcheck：神諭 600 秒沒跑完，卡住了）" + (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return r.returncode, r.stdout + r.stderr


def doc_count_mismatch():
    """docstring 的「共 N 項」與最後一個批次區間的終點必須等於 `len(CHECKS)`。"""
    m = re.search(r"共 (\d+) 項", __doc__)
    r = re.findall(r"(\d+)–(\d+)", __doc__.split("批次與編號", 1)[-1].split("共 ")[0])
    if not m or not r:
        return "docstring 找不到「共 N 項」或批次區間"
    if int(m.group(1)) != len(CHECKS) or int(r[-1][1]) != len(CHECKS):
        return "docstring 寫共 %s 項、最後一個區間到 %s，CHECKS 有 %d 項" % (m.group(1), r[-1][1], len(CHECKS))
    return None


def main():
    bad = 0
    why = doc_count_mismatch()
    if why:
        print("✗ %s" % why)
        bad += 1
    for what, extra, files, want_rc, want_text, *mut in CHECKS:
        rc, out = run_check(extra, files, mut[0] if mut else None)
        if rc is None:
            print("✗ %s：%s" % (what, out))
            bad += 1
            continue
        ok = rc == want_rc and want_text in out
        print("%s %s：rc=%d（期待 %d）、「%s」%s" % ("✓" if ok else "✗", what, rc, want_rc, want_text,
                                             "出現" if want_text in out else "沒有出現"))
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
