#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
  R37 1–2；R39 3–8；R40 9–10；R42 11–15；R42 WP7 16–19；R42 WP8 20–26；R44 27–31；R46 32–38；R48 39–45；R50 46–72；R52 73–95；R54 96–99；R56 100–102；R58 103–105。
共 105 項。守衛：`main()` 開頭比對這一行的總數與批次區間的終點是否等於 `len(CHECKS)`，不等就 rc=1——數字與清單不是兩份各自維護的東西。

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

def INJ(n):
    """注入探針的期待輸出：總數『一致 0、不一致 n』**加上**每一格的原因都是『繞過（注入』（恰好 n 次）。R56（R55 Codex 4）：前一版只比總數——
    某一格改由別的路徑判成『不一致』（例如『誤擋』、『primitive 稽核』）、總數不變，這些項目仍然綠，注入探針的網因此沒有被驗到。"""
    return ["一致 0、不一致 %d" % n, ("不一致：繞過（注入", n)]


# (說明, 額外環境變數, 神諭的檔案參數, 期待的 rc, 輸出裡必須出現的字串[, 突變])
# 「輸出裡必須出現的字串」可以是一個字串，或一個 list：每個元素是字串（要出現）或 (字串, n)（要恰好出現 n 次）。
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
    ("儀器完整性：改 `ORACLE_*` 環境變數沒有任何作用（`ORACLE_AUD` 等已不存在；僅剩的 `ORACLE_PRIV` 在開頭被複製進 `__orc_priv`，改 `ORACLE_PRIV` 環境變數沒有作用；對 `__orc_priv` 本身的指派屬於 PRELUDE 變數那一類，見第 86 項）——稽核走繼承的 fd，違規照樣被看到（**R56 起有一個例外**：`ORACLE_INJECT` 在注入那一次重新導出，文法內的 `ORACLE_INJECT=/dev/null` 會讓 E 組 payload 寫不到哨兵，見第 102 項；R50 取代 R48 的文字守衛；R49 requirements／logic／security／DA 與 Codex 同報守衛是吸收器）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
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
    # 哨兵／事件流仍沒有完整性檢查。**這不是防竄改**——步驟與儀器在同一個信任域，盲點類見 `instrument-*.yml` 四張探針（含對照組）對應的項。
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
    ("**已知盲點（文件化，不是保證）**：子殼層自己關掉稽核 fd，看不到那個子殼層裡的違規，判一致——這只是「步驟或它啟動的程式對儀器做的事」這個類別的一個形狀（類別探針與對照組見 `instrument-*.yml` 對應的項）；若有一天補上，這一項會紅，改它時須一併改 README 與 oracle.py 的措辭（沒有機制連結，靠人記得）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
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
    # 已知盲點類（R50，文件化，不是保證）：步驟與儀器在同一個信任域，神諭不是 sandbox（限制有三面，R58 補上第三面〔同一台主機上的其他人或行程經共用 `/tmp`，沒有探針〕，見 `oracle.py` 的 `FD_INJECT` 一帶；第二面〔runner 模型：fd 與環境的繼承、通道檔的讀法〕的探針是 73–79、82、89、90，第一面〔步驟或它啟動的程式動儀器〕的新探針是 81、86、88；80 是逾時時限的網，83–85、87 是 YAML 範圍歸屬）。四項：對照組（沒有動儀器時，同樣的違規被看到）＋三張盲點探針（每張釘一組效果，各 step 是不同的到達方式；代表形狀，不是窮舉）。
    ("對照組：不動儀器的同一批違規（`printf '%n'`、改寫信任變數、可注入構造、pipefail 關閉）全部判『不一致：繞過』——盲點探針的『一致』『量不到』因此不是違規本來就看不到（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "instrument-fd-blind-spots-control.yml"], 1, "不一致 4"),
    ("**已知盲點類（文件化，不是保證）**：步驟用編號指到稽核或注入哨兵的 fd（單一命令重導向、先存再還原、永久關掉後偽造 fin、經 `/dev/fd/199` 偽造記錄）——判一致（R52 前還有 `exec 197>/dev/null`，已補上，見第 88 項）；真的 `--strict` lint 對這四個 step 的寫法全部 RULE-red；經 fd 寫入的外部命令寫法（`tee /dev/fd/199`、`dd of=/dev/fd/199`、`sh -c '… >&199'`）在文法內放行，神諭同樣判一致（垃圾併進子殼層 `fin` 記錄的名稱，主 shell 的 `fin` 完好）。若有一天補上某一種，這一項會紅，改它時須一併改 README 與 oracle.py 的措辭（R50）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "instrument-fd-known-blind-spots.yml"], 0, "一致 4"),
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
    # R52（#33 verify R51）：R50 的傳輸改寫是「交換」——注入哨兵（環境變數指到的檔 → fd 197）與通道檔的讀法（`O_NOFOLLOW`＋上限）各有一個方向看不到，R50 的零回歸證據在這兩個維度分母是 0。
    # 前三項是哨兵的傳輸矩陣（孫行程關 fd／孫行程保留 fd／清掉環境的求值者）；後四項是通道證據（上限之內的證據優先、上限之外看不到不能判一致、符號連結、宣告 step 超量）；第 80 項是逾時路徑的第二次 `communicate` 的時限；第 81、82 項是注入哨兵的 fd 那一半與路徑那一半（各釘一半，刪目錄／關 fd 時另一半仍在）；第 86 項是 `__orc_priv` 不再 `readonly`；第 88、89 項是 `exec 197>/dev/null` 的補上與十二格傳輸矩陣；第 90 項是 pipefail 探針被換掉不關注入探針。
    ("注入哨兵：PR 文字由不繼承 fd 的孫行程（Python `subprocess` 預設 `close_fds=True`）當程式碼執行——判『繞過（注入）』，不是『一致』（R52，R51 regression M2／DA）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-grandchild-closes-fds.yml"], 1, "注入"),
    ("注入哨兵對照組：孫行程保留 fd（`close_fds=False`）——兩棵樹都判『繞過（注入）』，R52 不得退掉（R52）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-grandchild-keeps-fds.yml"], 1, "注入"),
    ("注入哨兵：清掉環境的求值者（`env -i /bin/bash -c \"$PR_TITLE\"`）——R49 看不到、R50 的 fd 傳輸補上了；R52 的改法不得退掉這個收穫（R52，R51 DA）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-env-cleared.yml"], 1, "注入"),
    ("通道證據優先：上限之內已寫進 `$GITHUB_ENV` 的 PR 文字是證據——超量另外報，不蓋掉證據（R52，R51 Codex 1／regression M1）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh"), "ORACLE_STREAM_CAP": "4096"},
     [PROBES / "channel-overcap-evidence-first.yml"], 1, "跨 step 通道"),
    ("通道上限的網：PR 文字寫在上限**之外**，神諭看不到，不能判『一致』——判『量不到（儀器不可信：通道檔 … 超過）』（R52 網，R51 logic M／G1）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh"), "ORACLE_STREAM_CAP": "4096"},
     [PROBES / "channel-overcap-marker-after-cap.yml"], 1, "通道檔 GITHUB_ENV 超過 4096 位元組"),
    ("通道檔換成指向含 PR 文字之檔案的符號連結（宣告 step）：真 runner 跟隨符號連結，判『繞過（跨 step 通道）』，不是『一致』（R52，R51 regression M1）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "channel-symlink-declared.yml"], 1, "跨 step 通道"),
    ("宣告 step 寫了 PR 文字再把通道檔灌過上限：證據在上限之內，判『繞過（跨 step 通道）』（R52，R51 regression M1）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh"), "ORACLE_STREAM_CAP": "4096"},
     [PROBES / "channel-overcap-declared.yml"], 1, "跨 step 通道"),
    ("逾時路徑的第二次 `communicate` 有時限：逃脫行程（`set -m` 的背景工作）握著 stdout 不放，約 12 秒內結束並判『量不到（儀器不可信：資料流沒有收乾淨）』，不卡到逃脫行程結束（R52 網，R51 logic M／G3）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "escaped-holds-stdout.yml"], 1, "資料流沒有收乾淨"),
    ("注入哨兵的 fd 那一半：步驟刪掉私有目錄（路徑那一半隨之失效），繼承 fd 的求值者仍被 fd 197 抓到（R52，R51 DA）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-sentinel-fd-half.yml"], 1, "注入"),
    ("注入哨兵的路徑那一半：孫行程關掉 fd，PR 文字只在 `[ -n $0 ]` 的 `-v` 下標算術裡被求值——命中的是路徑家族 P 的 `-n -o -v PWD[…]`（#7）；R56 起 E 組的 #15（`$ORACLE_INJECT`，要求環境保留）也命中這一格，所以這一項不再單獨釘住 P 靶（P 靶的殺手是 96 的 V 格〔清環境 ∧ 關 fd〕與 101 的 P56 格；R57 logic LOW）（R52，R51 DA）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-sentinel-path-half.yml"], 1, "注入"),
    # R52 C5（#33 verify R51 requirements／security／regression／DA）：bare `-` 的相鄰形狀（83–85、87；86 是 `__orc_priv`，88–90 見上）。前兩項是 R50 修法（只往上吞註解行）漏掉的位置；第三項（dash 行尾註解）在 `5b5a46d` 就有，會讓前一個 step 的真外流被判一致。
    ("bare `-` 後面先空一行、才是宣告註解：lint 認宣告，神諭的 step 範圍往上吞過空行，判一致（R52，R51 requirements 6／security／regression）", {},
     ["--min-comparable", "1", PROBES / "bare-dash-blank-after-dash.yml"], 0, "一致 1"),
    ("宣告註解與第一個鍵之間多一個空行：同上，另一個位置（R52，R51 requirements 6）", {},
     ["--min-comparable", "1", PROBES / "bare-dash-blank-before-key.yml"], 0, "一致 1"),
    ("`-  # 註解`（註解在 dash 那一行）：dash 行歸給這個 step，不是前一個 step——前一個 step 的 S-2 外流照樣被看到（R52，R51 regression／DA；`5b5a46d` 就有的缺陷）", {},
     [PROBES / "dash-line-comment-attribution.yml"], 1, "已知類別 S-2"),
    ("對 `__orc_priv` 做純量指派不弄瞎稽核：`readonly` 讓子殼層在神諭裡中止、真 runner 照常執行，其後的 `printf '%n'` 判一致；R52 拿掉 `readonly`，判『繞過（primitive 稽核）』（R52，R51 regression）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "priv-assign-keeps-audit.yml"], 1, "primitive 稽核"),
    ("bare `-` 的 dash 行帶行尾註解、其後才是宣告註解：往上走的 dash 正規式要認得帶註解的 dash 行，宣告才算這個 step 的（R52 網）", {},
     ["--min-comparable", "1", PROBES / "bare-dash-with-line-comment-declaration.yml"], 0, "一致 1"),
    ("`exec 197>/dev/null` 關掉注入哨兵的 fd：R50 的已知盲點，R52 起注入哨兵另外走私有字面路徑，判『繞過（注入）』——盲點被補上（R52 收穫；原在 `instrument-fd-known-blind-spots.yml` 的第五個 step）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-sentinel-fd-closed.yml"], 1, "注入"),
    ("**注入哨兵的傳輸矩陣**（R52 C6，R51 DA）：求值者繼承什麼——環境 × fd × 行程群組 × cwd × shell 方言 × 剖析脈絡 × 文字被截斷 × 受限 shell 共十二格，分母 12，十二格全判『繞過（注入）』；`5b5a46d` 8／12、`8b45659` 5／12（探針檔頭有逐格結果）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-transport-matrix.yml"], 1, INJ(12)),
    ("pipefail 探針被換掉（文法內的 `__orc_want=x`）不關掉獨立的注入探針：同一群組的 `[ -n $PR_TITLE ]` 注入照樣判『繞過（注入）』（R52 `pfu` 閘門；`8b45659` 判『量不到』rc=0；R51 logic LOW）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-with-pipefail-unmeasured.yml"], 1, "注入"),
    ("注入 payload 的 fd 那一半在兩個寫入點各自有網：刪掉私有目錄、保留 fd 的求值者，在 `[ -n $0 ]` 的算術脈絡（S 的 `-n -o -v PWD[$(…>&197)]`〔payload #3〕與 D 的同前綴版〔#10〕命中）與 `IFS=` 之後的 `eval`（程式碼行 R〔#4〕與 Dc〔#12〕命中）各被抓到（R52 網，R51 DA／E 組；R54 改以 S、R 的名字描述）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-sentinel-fd-half-contexts.yml"], 1, INJ(2)),
    # R52 宣稱查核 D 組：step 範圍的欄位錨定。92、93 是 R52 第一版放寬 dash 正規式引進的回歸（內容行長得像 dash）；94 是 `5b5a46d` 就有的缺陷（註解在下一個 step 的 dash 上方被算成前一個 step 的宣告）。
    ("step 範圍的欄位錨定：前一個 step 的 block scalar 內容有一行 `- #123`（markdown 清單），下一個 step 上方有同欄的 `# LOG-FILTER:` 註解——內容行不是 dash，b 真實的外流照樣被判『繞過』（R52 宣稱查核 D 組；R52 第一版的回歸）", {},
     [PROBES / "step-range-block-scalar-dash-lookalike.yml"], 1, "不一致：繞過"),
    ("step 範圍的欄位錨定：前一個 run 續行到單獨一行 `-`、接空行與同欄的 `# LOG-FILTER:` 註解——續行的 `-` 是 run 區塊的內容，不是 dash（R52 宣稱查核 D 組；R52 第一版的回歸）", {},
     [PROBES / "step-range-continuation-dash-lookalike.yml"], 1, "不一致：繞過"),
    ("宣告只認縮排比 dash 更深的註解行：寫在下一個 step 的 dash 上方（同欄）的 `# LOG-FILTER:` 不是前一個 step 的宣告，前一個 step 真實的外流照樣被判『繞過』（R52 宣稱查核 D 組；`5b5a46d` 就有的缺陷）", {},
     [PROBES / "step-range-comment-above-next-dash.yml"], 1, "不一致：繞過"),
    ("`pfu` 閘門在 lint 擋下（RULE-red）那一側也開：pipefail 探針被換掉的 step 與沒被換掉的對照組，判定相同（一致 2）（R52 宣稱查核 A 組）", {"ORACLE_LINT": str(PROBES / "lint-strict-blocks-all.sh")},
     [PROBES / "injection-with-pipefail-unmeasured-lint-blocked.yml"], 0, "一致 2"),
    # R54（#33 verify R53）：R52 的哨兵「fd ∪ 私有路徑」兩半各有前提（fd 要被求值者繼承、路徑要 payload 夠長），文字被截斷 ∧ 求值者不繼承 fd 的交集沒有任何 payload 命中；R52 取聯集時又拿掉了 R50 的第四組。
    ("**注入哨兵的『文字轉換 × 傳輸』交叉格**（R54 D1，R53 logic M／security M／regression M／DA M）：截斷 100／60 字 × 關 fd〔V、W 再加清環境〕、截斷 40／36 字的 `eval`〔保留 fd〕、`IFS=` 之後的 `eval`、受限 shell〔命令位置與算術脈絡〕、換掉斜線共九格，分母 9，九格全判『繞過（注入）』（用替身 lint 全放行量測；真 lint 下 T、X 兩格由 lint 自己擋下，R54 為 7 格繞過＋2 格一致；探針檔頭有三棵舊樹與 R54 的逐格結果）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-transform-matrix.yml"], 1, INJ(9)),
    ("step 範圍的兩道防線（欄位錨定的 dash 正規式、鍵已在 dash 行時不往上走）**同時**拿掉就會判錯：前一個 step 的 `with:` 值是多行 plain scalar、續行到單獨一行 `-` 再接更深的 `# LOG-FILTER:` 註解——`-` 是內容、註解是真註解，下一個 step 真實的外流判『繞過』（R54 D2，R53 logic M；R52 的 `EXPECTED_SURVIVE` 說同時拿掉兩道也看不出差別（第三道縮排條件會擋住），這個形狀的註解比 dash 深、第三道失效，是反例；單獨拿掉任何一道仍判繞過（實測）；`8b45659` 判『一致』）", {},
     [PROBES / "step-range-plain-scalar-dash-lookalike.yml"], 1, "不一致：繞過"),
    ("注入哨兵的 fd 那一半，dash 版：步驟刪掉私有目錄、dash 求值——短寫法與 R50 的程式碼行（`>&197`）在 dash 是語法錯誤、路徑那一半的目錄沒了，只有 `/dev/fd/197` 的寫法命中（雙引號裡的命令替換 D、`IFS=` 之後的 `eval` 的程式碼行 Dc）（R54 D2，R53 Codex 1；取代 R52 的『長寫法的 fd 那一半冗餘』）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-sentinel-dash-fd-only.yml"], 1, INJ(2)),
    ("**已知盲點，文件化、不是保證**：裸 `python3 -c` 的 stub 不執行程式碼——lint 放行的真注入（Python `subprocess` 預設、`os.system`）判『一致』，意思是『命令沒有被執行』；寫成 `/usr/bin/python3` 的對照組才判『繞過（注入）』（R54 D3，R53 DA M；既有缺陷，三棵樹判定相同；#97）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "stub-python-no-exec-known-blind-spot.yml"], 1, "一致 2、不一致 1"),
    # R56（#33 verify R55）：R53 的放行條件 D1(a) 要求新樹的 payload 是 `8b45659` 與 `5b5a46d` 的超集；R54 只做了前半。
    ("**`5b5a46d` 抓得到、R54 抓不到的 11 格**（R56 E1／E2，R55 requirements M／regression M／DA M）：求值者把斜線換成底線 ∧ 關 fd ∧ 保留環境（命令位置、算術、dash、`eval`、`IFS=` 之後的 `eval`〔U2，只有 #16 命中〕），以及算術 `(( t ))`、`[ $t ]` 的 `-v`、`[ -n $t ]` 的 `-n -o -v` 脈絡把文字截到 54–55／57–58／63–64 字——這些格子的哨兵只剩環境變數指到的檔，`5b5a46d` 的四個 `$ORACLE_INJECT` payload 全部命中。**真 lint**（不設 `ORACLE_LINT`；探針檔頭有各棵樹的結果）下 11 格全判『繞過（注入）』；`b86bc53`、`32d45ff`、`8b45659` 都是 0／11，`5b5a46d` 是 11／11", {},
     [PROBES / "injection-5b5a46d-wins.yml"], 1, INJ(11)),
    ("**私有路徑長度的邊界**（R56 E4，R55 logic M）：環境清空 ∧ 關 fd 的求值者，文字剛好截在 56 字（算術脈絡）與 44 字（命令位置）——`$ORACLE_INJECT` 與 fd 那幾組都不命中，只有路徑 payload P（56 字）與 Pc（44 字）命中，兩格都判『繞過（注入）』。`/tmp/oXXXXXXXX/i` 是 16 字；路徑多 1 字（`prefix` 變長、`dir=_short_tmp()` 被拿掉而落在 macOS 的長 `TMPDIR`），兩格都判『一致』", {},
     [PROBES / "injection-private-path-length.yml"], 1, INJ(2)),
    ("**已知盲點，文件化、不是保證**：R56 起 `ORACLE_INJECT` 在注入那一次重新導出；文法內的純量指派 `ORACLE_INJECT=/dev/null`（`--strict` 放行）讓 E 組 payload（#13–#16）寫不到哨兵，後面接『保留環境、關 fd、換斜線』的求值者時，沒有任何一組命中，判『一致』（T1）——意思是『儀器被步驟弄瞎』，不是『偵測到安全』；對照組 T2（沒有指派）與 T3（指派 `ORACLE_PRIV=/dev/null`）都判『繞過（注入）』——T3 只說明這個指派弄不瞎 E 組，不是『`__orc_priv` 複製過』的證據（R56，宣稱查核 A、C 組；屬〈步驟對儀器做的事〉(i)）", {},
     [PROBES / "instrument-oracle-inject-assign-known-blind-spot.yml"], 1,
     # R58（R57 Codex 2）：總數與原因次數不分方向——T1 與 T2 的判定對調（T1 繞過、T2 一致）一樣滿足『一致 1、不一致 2』；加上逐 step 的方向。
     ["一致 1、不一致 2", ("不一致：繞過（注入", 2), re.compile(r"\bT1\b[^\n]*oracle=\S+\s+一致$", re.M),
      re.compile(r"\bT2\b[^\n]*oracle=\S+\s+不一致：繞過（注入", re.M), re.compile(r"\bT3\b[^\n]*oracle=\S+\s+不一致：繞過（注入", re.M)]),
    # R58（#33 verify R57 logic M／regression M／DA M，第 12 格）：私有哨兵 `<priv>/i` 寫不進去（唯讀）、步驟 cwd 寫得進去——`$ORACLE_INJECT` 指到 cwd 底下的另一個哨兵才看得到。
    # R54 把哨兵搬到 `/tmp`、R56 補回 `5b5a46d` 的字串卻讓 `$ORACLE_INJECT` 指到同一個 `/tmp` 檔，求值者寫不到 `/tmp` 時 `5b5a46d` 判繞過、R54～R57 判一致。可攜版（`chmod 0444` 模擬『寫不進去』，非 root 才成立）。
    ("**第 12 格（可攜版）：私有哨兵唯讀、cwd 可寫**（R58 F1，R57 logic M／regression M／DA M）：命令位置、算術脈絡、`IFS=` 之後的 `eval` 三格，加上 cwd 也唯讀（不能建新檔）的第四格，反方向的兩格 R5、R6（cwd 底下的哨兵唯讀、私有哨兵可寫，換掉斜線或截到 54 字），以及一格 R7（步驟先檢查 cwd 有沒有點檔、有就提早結束；A2 的 M15：非 E 組的注入執行不可多建 cwd 哨兵），Python `subprocess` 預設關掉 0–2 以外的 fd、環境保留、`chmod 0444 \"$ORACLE_PRIV/i\"`（R1–R4）或 `chmod 0444 .orc-*/inject`（R5、R6）——"
     "R1–R4：S／R／D／Dc 要 fd（關了）、P／Pc 寫唯讀的私有哨兵（失敗），只有 E 組經 `$ORACLE_INJECT` 寫 cwd 底下的 `.orc-XXXX/inject` 命中；R5、R6：換掉斜線 P／Pc／D／Dc 都不成立，只有 E 組把 `$ORACLE_INJECT` 指到 `<priv>/i` 的那一次命中；七格都要判『不一致：繞過（注入）』。負對照：R57 的 `6490b57`（`$ORACLE_INJECT` 指到 `<priv>/i`）R1–R4 判『一致』、R5～R7 判繞過；cwd 哨兵不預先建檔時 R4 判『一致』（R58 宣稱查核 B 組）；`$ORACLE_INJECT` 只指 cwd 時 R5、R6 判『一致』（R58 宣稱查核 C 組：『搬走』不是『加上』）；非 E 組的注入執行也建 cwd 哨兵時 R7 判『一致』（R58 A2 的 M15）", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "injection-priv-sentinel-readonly.yml"], 1,
     # R7 要由 #1（fd 197）命中：非 E 組的注入執行若也建 cwd 哨兵，步驟提早結束，#1 不中，要等 E 組的 priv 那一次（#13）才救回——判定還是繞過，只有 payload 編號不同（突變靶 567 因此存活，R58 A2 的 M15）
     INJ(7) + [re.compile(r"\bR7\b[^\n]*payload #1\b", re.M)]),
    # R58 F2（R57 security M／DA M）：注入探針送出的鍵不只 `PR_TITLE`、`PR_BODY`。
    ("**注入探針送出的鍵**（R58 F2，R57 security M／DA M）：`env: TITLE: ${{ …title }}`、`env: HEAD_REF: ${{ github.head_ref }}`、`env: X: pre-${{ …title }}-post` 加 `bash -c \"$KEY\"`（真 lint `--strict` 全部放行）與鍵名 `PR_TITLE` 的對照組，四格都要判『不一致：繞過（注入）』。"
     "原本 `run_script` 的第二個集合 `{k … if \"${{\" in str(v)}` 是死碼（`_env_of` 已把 `${{ }}` 代換掉），只有 `PR_TITLE`、`PR_BODY` 收到 payload，其餘三格判『一致』（R44 起，五棵舊樹相同）。負對照：`6490b57` 三格判『一致』", {},
     [PROBES / "injection-env-key-names.yml"], 1, INJ(4)),
    # R58 F1 的真沙箱版（macOS 才有 `/usr/bin/sandbox-exec`；沒有時 `main()` 明確印『跳過』，不算通過也不算失敗）。
    ("**第 12 格（真沙箱版，只在 macOS）**（R58 F1，R57 logic M／regression M／DA M）：`sandbox-exec` 拒寫 `/private/tmp`（SB1、SB3〔算術脈絡〕）或只准寫 cwd（SB2），關 fd、保留環境，加一格保留 fd 的對照組 SB4，兩格連新檔都不准建的 SB5、SB6（`deny file-write-create`：只能改既有的檔，cwd 哨兵必須預先建好），以及兩格拒寫 cwd 但 `/tmp` 可寫的 SB7、SB8（換掉斜線或截到 54 字：只有 `$ORACLE_INJECT` 指到 `<priv>/i` 的那一次命中）——八格都要判『不一致：繞過（注入）』。"
     "負對照：`6490b57` 的 SB1～SB3 判『一致』、SB4 判繞過；cwd 哨兵不預先建檔時 SB5、SB6 判『一致』（`5b5a46d` 全判繞過）；`$ORACLE_INJECT` 只指 cwd 時 SB7、SB8 判『一致』（`6490b57` 判繞過）", {},
     [PROBES / "injection-fs-restricted.yml"], 1, INJ(8)),
]

# 需要平台工具才跑得了的項目（探針檔名 → 必須存在的執行檔）：沒有就在 `main()` 印『跳過』，不算通過也不算失敗（Linux 上沒有 `sandbox-exec`）。
REQUIRES = {"injection-fs-restricted.yml": "/usr/bin/sandbox-exec"}


def tool_usable(path):
    """執行檔存在、而且真的跑得起來。`sandbox-exec` 在外層沙箱裡（`(deny process-exec …)`）存在但執行不了，八格全判『一致』、第 105 項紅，訊息會讓人以為神諭退步（R58 A2）；
    跑一次最小的 profile 確認它可用，不可用就和『不存在』一樣印『跳過』。"""
    if not os.path.exists(path):
        return False
    if os.path.basename(path) == "sandbox-exec":
        try:
            return subprocess.run([path, "-p", "(version 1)(allow default)", "/usr/bin/true"], capture_output=True, timeout=20).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return True


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


def text_ok(want, out):
    """`want` 是字串或 list；list 的每個元素是字串（要出現）、(字串, n)（要恰好出現 n 次），或編譯過的正規式（要在輸出裡找得到；`re.M` 時 `$` 是行尾——
    用來釘『哪一個 step 判了什麼』，只比總數會讓兩格的方向對調仍然綠，R57 Codex 2）。這個比對器本身有單元測試（`matcher_problems`，`--selftest-matcher`）與突變靶——
    R56 新增的『原因比對』當時沒有任何東西會在它被拿掉時變紅（R57 Codex 1）。"""
    for w in (want if isinstance(want, list) else [want]):
        if isinstance(w, re.Pattern):
            if not w.search(out):
                return False
            continue
        text, n = w if isinstance(w, tuple) else (w, None)
        if (out.count(text) != n) if n is not None else (text not in out):
            return False
    return True


def text_label(want):
    def one(w):
        if isinstance(w, re.Pattern):
            return "「/%s/」" % w.pattern
        return ("「%s」" % w) if isinstance(w, str) else ("「%s」×%d" % w)
    return "、".join(one(w) for w in (want if isinstance(want, list) else [want]))


def matcher_problems():
    """`text_ok` 的單元測試（不跑神諭）：該拒絕的拒絕、該接受的接受。回傳問題清單（空＝全過）。R58 F3（R57 Codex 1）：把比對器改成永遠接受，
    正向的 selfcheck 全部仍然綠——只有這裡會紅。"""
    ok_out = "x.yml  A  lint=pass  oracle=piped  不一致：繞過（注入：…）\nx.yml  B  lint=pass  oracle=piped  一致\n3 個 step：一致 1、不一致 2\n不一致：繞過（注入"
    cases = [
        # (說明, want, out, 期待)
        ("字串在輸出裡", "一致 1、不一致 2", ok_out, True),
        ("字串不在輸出裡", "一致 9、不一致 9", ok_out, False),
        ("(字串, n) 剛好 n 次", ("不一致：繞過（注入", 2), ok_out, True),
        ("(字串, n) 少一次", ("不一致：繞過（注入", 3), ok_out, False),
        ("(字串, n) 多一次", ("不一致：繞過（注入", 1), ok_out, False),
        ("INJ(2) 接受：總數對、原因恰好兩次", INJ(2), "一致 0、不一致 2\n不一致：繞過（注入 a\n不一致：繞過（注入 b", True),
        ("INJ(2) 拒絕：總數對、但原因是 primitive 稽核（R57 Codex 1 的核心）", INJ(2), "一致 0、不一致 2\n不一致：primitive 稽核 a\n不一致：primitive 稽核 b", False),
        ("INJ(2) 拒絕：總數對、原因只有一次", INJ(2), "一致 0、不一致 2\n不一致：繞過（注入 a\n不一致：primitive 稽核 b", False),
        ("INJ(2) 拒絕：原因對、總數字串缺失", INJ(2), "不一致：繞過（注入 a\n不一致：繞過（注入 b", False),
        ("list 裡每個元素都要成立", ["一致 1、不一致 2", "不存在的字串"], ok_out, False),
        ("正規式找得到", re.compile(r"\bB\b[^\n]*oracle=\S+\s+一致$", re.M), ok_out, True),
        ("正規式：A 判的是繞過、不是一致（方向對調會被拒）", re.compile(r"\bA\b[^\n]*oracle=\S+\s+一致$", re.M), ok_out, False),
    ]
    return ["%s：期待 %s、實際 %s" % (what, exp, text_ok(want, out)) for what, want, out, exp in cases if text_ok(want, out) != exp]


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
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest-matcher":
        probs = matcher_problems()
        for x in probs:
            print("✗ " + x)
        if not probs:
            print("matcher ok（12 案）")
        return 1 if probs else 0
    bad = 0
    for x in matcher_problems():
        print("✗ 比對器單元測試：" + x)
        bad += 1
    why = doc_count_mismatch()
    if why:
        print("✗ %s" % why)
        bad += 1
    skipped = 0
    for what, extra, files, want_rc, want_text, *mut in CHECKS:
        need = next((REQUIRES[pathlib.Path(f).name] for f in files if pathlib.Path(f).name in REQUIRES and not tool_usable(REQUIRES[pathlib.Path(f).name])), None)
        if need:
            print("↷ %s：跳過（沒有 %s，或它在這裡跑不起來）" % (what[:60], need))
            skipped += 1
            continue
        rc, out = run_check(extra, files, mut[0] if mut else None)
        if rc is None:
            print("✗ %s：%s" % (what, out))
            bad += 1
            continue
        ok = rc == want_rc and text_ok(want_text, out)
        print("%s %s：rc=%d（期待 %d）、%s%s" % ("✓" if ok else "✗", what, rc, want_rc, text_label(want_text),
                                             "出現" if text_ok(want_text, out) else "沒有出現"))
        bad += not ok
    if skipped:
        print("（%d 項因為缺少平台工具而跳過——不算通過；`REQUIRES` 列出哪些）" % skipped)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
