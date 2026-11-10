#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神諭的反向探針：多數是只有神諭**失敗**時才成立的檢查，其餘是期待 rc=0 的單元測試、已知盲點與判『一致』的項目（#33 verify R37 起）。

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
  R37 1–2；R39 3–8；R40 9–10；R42 11–15；R42 WP7 16–19；R42 WP8 20–26；R44 27–31；R46 32–38；R48 39–45；R50 46–72；R52 73–95；R54 96–99；R56 100–102；R58 103–105；R60 106–107；R62 108–110；R64 111–112；R66 113–116。
共 116 項。守衛：`main()` 開頭比對這一行的總數與批次區間的終點是否等於 `len(CHECKS)`，不等就 rc=1——數字與清單不是兩份各自維護的東西。

用法：test/oracle_selfcheck.py      rc=0：每一項都照預期；rc=1：至少一項沒有（或上面的數字與 `CHECKS` 不符）。
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import oracle_history   # noqa: E402  R64：歷史注入設定的凍結表與逐目標履行檢查（#33 verify R63 第 2～4 列）
ORACLE = HERE / "oracle.py"
PROBES = HERE / "oracle-probes"
LINT = HERE / "lint-ci-log-filter.sh"

SPACED_TMPDIR = "<含空白的暫存目錄>"   # `extra` 裡 `TMPDIR` 的這個值：`run_check` 在自己的暫存目錄底下建一個名字含空白的目錄並設成 `TMPDIR`（R60 G2）
SAFE_TMPDIR = "<非 /tmp 的暫存目錄>"   # `extra` 裡 `TMPDIR` 的這個值：`run_check` 在自己的暫存目錄底下建一個子目錄（`safe-tmp`）並設成 `TMPDIR`，所以 `tempfile.gettempdir()` 不是 `/tmp`、`oracle.py` 的 `"priv-tmpdir"` 目標在這裡是 macOS 預設的形狀（R62 H1；`TMPDIR=/tmp` 時它也存在，但那時 PA1、PA2 的 `chmod` 辨認法〔私有目錄路徑長 14〕分不出兩個私有目錄，所以這張探針要在 `/tmp` 之外的 `TMPDIR` 跑）


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
     "負對照：`6490b57` 的 SB1～SB3 判『一致』、SB4 判繞過；cwd 哨兵不預先建檔時 SB5、SB6 判『一致』（`5b5a46d` 的 SB1～SB6 判繞過、SB7、SB8 判『一致』：它的哨兵在被拒寫的 cwd 底下）；`$ORACLE_INJECT` 只指 cwd 時 SB7、SB8 判『一致』（`6490b57` 判繞過）", {},
     [PROBES / "injection-fs-restricted.yml"], 1, INJ(8)),
    # R60 G1（#33 verify R59 regression／logic／DA，F2 的『所有 PR 可控鍵同時注入』不是舊樹的行為超集）。
    ("**注入的鍵設定各是獨立的一次執行：舊樹的設定、所有鍵同時、逐鍵各一次**（R60 G1，R59 regression／logic／DA）：step 先驗證 PR 的另一個欄位——第二個 `${{ …title }}` 鍵的長度閘門、`>` 閘門、`head_ref` 的 `>` 閘門、"
     "純 bash 的 `[[ $0 =~ … ]] && exec` 閘門——再執行 `PR_TITLE`，加上 sink 是非 `PR_TITLE` 的鍵（`TITLE`）、閘門是 `REF` 的 SG6，真 lint `--strict` 全部放行，SG1～SG4 與 SG6 要判『不一致：繞過（注入）』；SG5 是對照組（閘門就是 `PR_TITLE` 自己，L1 類），要判『一致』。"
     "負對照：R58（`ecb77d9`～`bf0c8a7`）的 SG1～SG4 與 SG6 判『一致』（payload 同時塞進閘門鍵，閘門把它擋掉、sink 不執行）；`6490b57`、`5b5a46d` 的 SG1～SG4 判繞過、SG6 判一致（污染不到 `TITLE`）", {},
     [PROBES / "injection-sibling-gate.yml"], 1,
     ["一致 1、不一致 5", ("不一致：繞過（注入", 5)] + [re.compile(r"\bSG%d\b[^\n]*oracle=\S+\s+不一致：繞過（注入" % n, re.M) for n in (1, 2, 3, 4, 6)] + [re.compile(r"\bSG5\b[^\n]*oracle=\S+\s+一致$", re.M)]),
    # R60 G2（第 13 格）：暫存目錄含空白時，POSIX 模式的 shell 不切開重導向的目標詞，絕對路徑寫得進去。
    ("**第 13 格：`TMPDIR` 含空白 ∧ 求值者的 shell 不切開重導向的目標詞 ∧ 求值者先離開步驟 cwd**（R60 G2，R59 requirements／logic／regression／DA／Codex）：`bash --posix` 先 `cd /`（PX1）、`bash --posix` 由 `subprocess` 換 cwd（PX2）、"
     "`IFS` 不含空白的 bash 先 `cd /`（PX3）三格，加上 PX5（同 PX1，另把 `.orc-*/inject` 也設成唯讀，只剩 cwd 頂層 `inject` 的**絕對路徑**寫得進去：`cwd-vis-abs` 目標，Codex 預審 M2）與 PX6（同 PX1，另把 cwd 頂層的 `inject` 也設成唯讀，只剩 `.orc-*/inject` 的絕對路徑寫得進去：`cwd-abs` 目標，R62 量測的突變靶 #597）共五格要判『不一致：繞過（注入）』（私有哨兵用 `chmod 0444` 模擬寫不進去，只有不加引號的 E 組經 cwd 底下的 `$ORACLE_INJECT` 的**絕對路徑**寫得進去）；PX4 是對照組（一般模式的 bash、預設 `IFS`、`cd /`：絕對路徑 `ambiguous redirect`、相對路徑 ENOENT），要判『一致』。"
     "負對照：R58 的 `76bd0f9`／`bf0c8a7` 對 PX1～PX3 判『一致』（不加引號的 E 組的 `ORACLE_INJECT` 改成相對路徑〔加引號的仍用絕對路徑〕，求值者換了 cwd 就 ENOENT；`ecb77d9` 則是停用 cwd 哨兵、退回 `<priv>/i`，私有哨兵唯讀所以也寫不進去）；`5b5a46d`（一律絕對路徑）對這張探針本身判『量不到（儀器不可信）』——步驟文字提到 `ORACLE_PRIV`——，把 `chmod` 那行換成 `:` 的變體則 PX1～PX3 判繞過、PX4 判『一致』。PX6 的負對照（2026-10-28）：`636fcfe` 判 PX6 繞過（`cwd-abs` 的絕對路徑）、`28ec8c3`／`bf0c8a7`／`6490b57` 判『一致』；套上突變靶 #597 的副本只有 PX6 改判『一致』。`run_check` 在自己的暫存目錄底下建一個名字含空白的目錄並設成 `TMPDIR`", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh"), "TMPDIR": SPACED_TMPDIR},
     [PROBES / "injection-posix-spaced-tmpdir.yml"], 1,
     ["一致 1、不一致 5", ("不一致：繞過（注入", 5)] + [re.compile(r"\bPX%d\b[^\n]*oracle=\S+\s+不一致：繞過（注入" % n, re.M) for n in (1, 2, 3, 5, 6)] + [re.compile(r"\bPX4\b[^\n]*oracle=\S+\s+一致$", re.M)]),
    # R62 H1（#33 verify R61：requirements／logic／security／regression／DA／Codex，哨兵位置軸）：舊樹的哨兵位置要各自留成一次獨立的執行。
    ("**哨兵位置軸（可攜版）**（R62 H1，R61 的兩個 blocking）：求值者只寫得到 `TMPDIR` 底下的私有目錄（`/tmp` 底下的私有哨兵唯讀、`env -i`、關 fd；PA1 命令位置、PA2 算術脈絡）時，`32d45ff` 的位置（`\"priv-tmpdir\"` 目標）命中；"
     "所有私有哨兵與 cwd 底下的 `.orc-*/inject` 都唯讀、只有 cwd 頂層的 `inject` 寫得進去（PB1、PB2）時，`28ec8c3` 的位置（`\"cwd-vis\"` 目標）命中；PN 是對照組（所有位置都唯讀：已知盲格，判『一致』）。`TMPDIR` 設成 `/tmp` 之外的目錄（`SAFE_TMPDIR`），替身 lint（一律放行）。"
     "負對照（2026-10-22 在封存的舊樹上實測）：`6490b57`／`bf0c8a7`／`636fcfe` 的五格全判『一致』；`28ec8c3` 的 PB1、PB2 判繞過；`32d45ff` 的 PA1、PA2 判繞過、PB1、PB2、PN 判『一致』（它的私有哨兵檔名是 `$ORACLE_PRIV/inject`，PB／PN 的 `chmod` 同時涵蓋 `i` 與 `inject`；檔名本身的鑑別力在沙箱版 SP9、SP10）。非 root 才成立", {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh"), "TMPDIR": SAFE_TMPDIR},
     [PROBES / "injection-sentinel-position-axis.yml"], 1,
     ["一致 1、不一致 4", ("不一致：繞過（注入", 4)] + [re.compile(r"\b%s\b[^\n]*oracle=\S+\s+不一致：繞過（注入[^\n]*payload #%d" % (c, n), re.M) for c, n in (("PA1", 5), ("PA2", 5), ("PB1", 13), ("PB2", 13))] + [re.compile(r"\bPN\b[^\n]*oracle=\S+\s+一致$", re.M)]),
    ("**哨兵位置軸（真沙箱版，只在 macOS）**（R62 H1，R61 requirements／logic／security／regression／DA／Codex）：SP1、SP2（拒寫 `/private/tmp`、關 fd、`env -i`）、SP3、SP4（拒寫 `/private/tmp` 與 cwd 子樹、**環境保留**——Codex 的變體）、SP5、SP6（拒寫 `/private/tmp` 與整個 `TMPDIR`、只放行 `<cwd>/inject`、環境保留；R66 改寫，前一版拒寫隱藏目錄）、"
     "SP7（Python `env={}`）、SP9、SP10（拒寫 `/private/tmp` 與整個 `TMPDIR`、**只放行基名 `inject`**——`32d45ff` 的私有哨兵檔名也是歷史位置的一部分，Codex 預審 M1）、SP11、SP12（只放行對**既有**的 `<cwd>/inject` 做資料寫入、不放行建立——`cwd-vis` 預先建檔，Codex 預審 LOW）要判『不一致：繞過（注入）』，SP8 是對照組（只拒寫 `/private/tmp`、fd 保留）。真 lint `--strict` 全部放行。負對照（2026-10-22 在封存的舊樹上實測）：`6490b57`／`bf0c8a7`／`636fcfe` 只有 SP8 判繞過、其餘十一格判『一致』；`32d45ff` 判 SP1～SP10 繞過（payload #4；SP8 是 #1）、SP11／SP12 判『一致』；`28ec8c3` 判 SP5、SP6、SP8、SP11、SP12 繞過、其餘判『一致』", {"TMPDIR": SAFE_TMPDIR},
     [PROBES / "injection-sentinel-position-sandbox.yml"], 1,
     INJ(12) + [re.compile(r"\bSP%d\b[^\n]*oracle=\S+\s+不一致：繞過（注入" % n, re.M) for n in range(1, 13)]),
    # R62 H3（R61 DA）：跨執行持久狀態是已知盲點（性質聲明 (ii) 的成員、停止規則的第三個豁免類）——這一項是**現況的棘輪**：每一格都判『一致』（R66 起七格）；日後神諭有了封閉的執行，這一項會紅，那時要更新探針與停止規則。
    ("**跨執行持久狀態（已知盲點，棘輪）**（R62 H3，R61 DA 的 TG1／CG1／DT1）：step 把狀態（taint 檔、計數器、工作區衛生檢查的 taint）留在共用的主機位置（`/tmp`、`/var/tmp`、步驟 cwd 的上層）、並依它決定要不要執行 `PR_TITLE`——神諭對同一個 step 的多次執行共用同一台主機，先跑的執行把後跑的吃掉，七格判『一致』（XR4 是 R63 的工作區衛生檢查格，R62 的 `cwd-vis` 造出；XR5～XR7 是 R63 第 6 列的純計數格、`/var/tmp` 與上層 taint 格，R66 照使用者 2026-11-01 的決定收進來）"
     "（真 lint `--strict` 放行；真 runner 對同一個 step 在一次 workflow run 裡只執行一次，攻擊者給合法的分支名、標題就被執行；神諭的多次反事實執行之間不重置共用的主機狀態）。DA 的鴿籠論證：任何執行順序都無法同時保住所有舊設定，所以列為豁免類而不是缺陷（使用者 2026-11-01 同意，條文見 `oracle.py`〈已知限制〉(9)）。狀態檔名帶神諭這次呼叫的 `PATH` 雜湊、不讀時鐘（結構由 `xrun_probe_problems` 守）", {},
     [PROBES / "injection-cross-run-state-known-blind-spots.yml"], 0, "一致 7"),
    # ── R64（#33 verify R63 第 2～4 列）──
    ("**payload 字串軸（可攜版）**（R64，R63 第 2 列）：求值者只在標題含 `;`（PL1、PL3 算術）或不計路徑的長度 ≥ 70（PL2）時才執行它——`32d45ff` 的四組複合 payload（R54 拆掉、R64 加回 #17～#20）才命中；PL0 是不把關的對照組。"
     "負對照：`32d45ff` 四格繞過（#4），`636fcfe`／`8292d86` 的 PL1～PL3 判『一致』。凍結表在 `oracle_history.HISTORICAL_PAYLOADS`",
     {}, [PROBES / "injection-payload-string-axis.yml"], 1, INJ(4)),
    ("**哨兵路徑形狀（沙箱版，只在 macOS）**（R64，R63 第 3、4 列）：DP1 只放行 `tmpXXXXXXXX/inject`（`32d45ff` 的私有目錄名）、DP0 也放行 `oXXXXXXXX`（對照組）、HO1 只放行隱藏 `.orc-*` 底下的 `inject`（`cwd` 目標）。"
     "負對照：DP1 在 `8292d86`（R62，前綴 `o`）判『一致』；HO1 在 R63 的 X2 突變樹（`.orc-*/injectx`）判『一致』。逐目標的形狀另由 `oracle_history.TARGET_SHAPES` 直接守",
     {}, [PROBES / "injection-sentinel-shape-sandbox.yml"], 1, INJ(3)),
    # R66（R61 Follow-up 指定收進 repo，R62、R64 沒做；R63／R65 requirements）：G1／G2 點名的輸入。只收點名的格子：selfcheck 是突變全輪每個 `oracle-inverted` 靶都要跑的，R61 探針全收（25 格）太貴。
    ("**`git check-ref-format` 閘門（可攜）**（R66，R60 G1 點名）：求值前驗 `head_ref` 是合法分支名，真 lint `--strict` 放行，神諭要判『不一致：繞過（注入）』", {},
     [PROBES / "injection-named-git-refgate.yml"], 1, INJ(1)),
    ("**點名的 shell（沙箱版，只在 macOS）**（R66，R60 G2 點名）：`/bin/sh`、`/bin/dash`、`/bin/ksh` 先 `cd` 到別處再求值，判『不一致：繞過（注入）』；`/bin/zsh` 的算術脈絡判『一致』（〈已知限制〉(8) 的棘輪）", {},
     [PROBES / "injection-named-shells-sandbox.yml"], 1, ["一致 1、不一致 3", ("不一致：繞過（注入", 3)]
     # R68（R67 logic L）：逐格釘死——前一版只比總數，對照格與棘輪格對調時仍綠。
     + [re.compile(r"\b%s\b[^\n]*oracle=\S+\s+不一致：繞過（注入" % c, re.M) for c in ("QA2", "QA3", "C1")] + [re.compile(r"\bC2\b[^\n]*oracle=\S+\s+一致$", re.M)]),
    ("**`PS4`、`PATH` 入口（已知盲點，棘輪）**（R66，R60 G1 點名、〈已知限制〉(7)）：`_OWN_ENV` 裡的鍵帶 PR 文字時神諭不注入，判『一致』；日後涵蓋了，這一項會紅", {},
     [PROBES / "injection-named-entries-known-blind-spots.yml"], 0, "一致 2"),
    # R66（R65 第 1 列；使用者 2026-11-08 選 (b)，停止規則的第四個豁免類，〈已知限制〉(11)）：儀器指紋。FP0 是對照（不設閘門，要判繞過），FP1～FP3 是棘輪。
    ("**儀器指紋（已知盲點，棘輪）**（R66，R65 第 1 列、〈已知限制〉(11)）：三個步驟各自只在一個特徵不在時才執行標題（FP1 沒有 `ORACLE_INJECT`、FP2 沒有 `ORACLE_PRIV`、FP3 fd 197 沒開），判『一致』；對照的 FP0 判『不一致：繞過（注入）』。"
     "負對照：`28ec8c3` FP2、FP3 繞過，`32d45ff` FP1 繞過 #4，`b86bc53` FP1 繞過 #5；日後神諭讓步驟看不到這些特徵，這一項會紅", {},
     [PROBES / "injection-instrument-fingerprint-known-blind-spots.yml"], 1, ["一致 3、不一致 1", ("不一致：繞過（注入", 1)]
     # R68（R67 logic L）：逐格釘死，同上。
     + [re.compile(r"\b%s\b[^\n]*oracle=\S+\s+一致$" % c, re.M) for c in ("FP1", "FP2", "FP3")] + [re.compile(r"\bFP0\b[^\n]*oracle=\S+\s+不一致：繞過（注入", re.M)]),
]

# 需要平台工具才跑得了的項目（探針檔名 → 必須存在的執行檔）：沒有就在 `main()` 印『跳過』，不算通過也不算失敗（Linux 上沒有 `sandbox-exec`）。
# **沒有任何 CI job 會跑第 105、109、112、114 項**（下面 `REQUIRES` 的四張沙箱探針；R66 更正，R65 requirements／regression：前一版只寫第 105 項，R62、R64 加的兩項沒有跟著改）：ubuntu job 沒有 `sandbox-exec`、macOS job 不跑 `oracle_selfcheck`（R59 G5 要求納入 CI；`.github/` 是這個 PR 的閘門本身，加一步會改變『閘門相對 `6490b57` 沒有變』這個前提，R60 沒有做，列在 CHANGELOG 的〈沒有處理的〉）——這一項只在開發機上跑。
REQUIRES = {"injection-fs-restricted.yml": "/usr/bin/sandbox-exec", "injection-sentinel-position-sandbox.yml": "/usr/bin/sandbox-exec", "injection-sentinel-shape-sandbox.yml": "/usr/bin/sandbox-exec", "injection-named-shells-sandbox.yml": "/usr/bin/sandbox-exec"}


def tool_usable(path, timeout=20):
    """執行檔存在；若是 `sandbox-exec`，另外實跑一個最小 profile（20 秒逾時）確認跑得起來，其他執行檔只看存在。`sandbox-exec` 在外層沙箱裡（`(deny process-exec …)`）存在但執行不了，八格全判『一致』、第 105 項紅，訊息會讓人以為神諭退步（R58 A2）；
    跑一次最小的 profile 確認它可用，不可用就和『不存在』一樣印『跳過』。"""
    if not os.path.exists(path):
        return False
    if os.path.basename(path) == "sandbox-exec":
        try:
            return subprocess.run([path, "-p", "(version 1)(allow default)", "/usr/bin/true"], capture_output=True, timeout=timeout).returncode == 0
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
        if env.get("TMPDIR") == SPACED_TMPDIR:
            sp = pathlib.Path(d) / "sp ace"
            sp.mkdir()
            env["TMPDIR"] = str(sp)
        elif env.get("TMPDIR") == SAFE_TMPDIR:
            sp = pathlib.Path(d) / "safe-tmp"
            sp.mkdir()
            env["TMPDIR"] = str(sp)
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
    problems = ["%s：期待 %s、實際 %s" % (what, exp, text_ok(want, out)) for what, want, out, exp in cases if text_ok(want, out) != exp]
    # R60（R59 Codex 3；logic LOW 另外指出第 105 項不在 CI、指紋沒記 `sandbox-exec` 可用性）：`tool_usable` 也有單元測試——把它改成永遠回 False，第 105 項在 macOS 上整個被跳過、selfcheck 仍然綠（R59 凍結樹 `bf0c8a7` 時沒有任何靶殺它；R60 起 `mutation_check.py` 有兩個 `tool_usable` 靶）。
    # 用假的 `sandbox-exec`（一支 shell 腳本）涵蓋：跑得起來、執行失敗、不存在、以及非 `sandbox-exec` 的一般執行檔（只看存在）。
    with tempfile.TemporaryDirectory(prefix="tool-usable-") as td:
        def fake(name, body, mode=0o755):
            q = pathlib.Path(td) / name
            q.parent.mkdir(exist_ok=True)
            q.write_text("#!/bin/sh\n" + body + "\n")
            q.chmod(mode)
            return str(q)
        for what, path, exp in (("假 sandbox-exec 成功（rc=0）→ 可用", fake("ok/sandbox-exec", "exit 0"), True),
                                ("假 sandbox-exec 失敗（rc≠0；真實的外層沙箱 `deny process-exec` 實測為 rc=71，這裡用 1 代表任何非零）→ 不可用", fake("bad/sandbox-exec", "exit 1"), False),
                                ("路徑不存在 → 不可用", str(pathlib.Path(td) / "missing" / "sandbox-exec"), False),
                                ("不是 sandbox-exec 的執行檔，存在就算可用", fake("other/tool", "exit 1"), True),
                                # R62 H5（R61 logic LOW）：逾時與執行失敗兩個例外分支（`except → return False`；把它改成 `return True` 的突變體在 R60 時存活）
                                ("假 sandbox-exec 跑得比逾時久（睡 5 秒、逾時 1 秒）→ 不可用", fake("slow/sandbox-exec", "sleep 5"), False),
                                ("假 sandbox-exec 存在但不可執行（`OSError`）→ 不可用", fake("noexec/sandbox-exec", "exit 0", mode=0o644), False)):
            # 正常路徑給寬鬆的逾時：機器忙的時候（其他工作階段在跑測試）新寫出的小腳本首次執行可能超過 1 秒，1 秒的逾時會讓『成功→可用』這一案偶爾判不可用（2026-10-22 負載 10～17 時實際發生一次）；只有『跑得比逾時久』這一案用 1 秒——它預期判不可用，不會因負載而變。
            got = tool_usable(path, timeout=1 if path.endswith("slow/sandbox-exec") else 15)
            if got != exp:
                problems.append("tool_usable：%s：期待 %s、實際 %s" % (what, exp, got))
    # R62 H2：歷史哨兵位置 manifest 的檢查本身有單元測試（假的 `_inject_runs`）：完整的序列在四個 (spaced, tmpdir_priv) 組合都要全過；缺任何一個目標都要被抓到；有條件的目標變成無條件也要被抓到；
    # 條件寫錯的假產生器（只在對角格正確：交換、`and`、基底格什麼都不跑、只缺混合格）也要被抓到——Codex 預審 M3：前一版只驗 (True, True) 與 (False, False) 兩個對角格，條件寫成 `tmpdir_priv and spaced` 或基底格整個空掉都過得了；
    # manifest 的列數寫死是 6（有人悄悄刪一列，這裡紅）。
    if len(HISTORICAL_SENTINEL_POSITIONS) != 6:
        problems.append("HISTORICAL_SENTINEL_POSITIONS 有 %d 列，要是 6（封閉列舉；拿掉一列要有書面理由）" % len(HISTORICAL_SENTINEL_POSITIONS))
    pays, runs = _fake_runs()
    if sentinel_manifest_problems(pays, "@@TOK@@", runs):
        problems.append("manifest 檢查：完整的假序列被判有問題：%s" % sentinel_manifest_problems(pays, "@@TOK@@", runs))
    for drop in MANIFEST_DROPS:
        pays, runs = _fake_runs(drop)
        if not sentinel_manifest_problems(pays, "@@TOK@@", runs):
            problems.append("manifest 檢查：缺 %s 的假序列沒有被抓到" % drop)
    for variant in MANIFEST_VARIANTS:
        pays, runs = _fake_runs(variant=variant)
        if not sentinel_manifest_problems(pays, "@@TOK@@", runs):
            problems.append("manifest 檢查：條件寫錯的假序列（%s）沒有被抓到" % variant)
    # `main()` 真的呼叫了對真的 `oracle.py` 的 manifest 檢查（拿掉那個呼叫，沒有任何一項會紅——`oracle-inverted` 的突變體靠第 108 項殺，但這個呼叫本身要有人守）：文字檢查，簡單但夠用。
    import contextlib
    import inspect
    import io
    if "sentinel_manifest_problems_real()" not in inspect.getsource(main):
        problems.append("main() 沒有呼叫 sentinel_manifest_problems_real()")
    # R62 量測後（XR 探針的時間依賴）：結構檢查本身的四案——正確的寫法要過；讀時鐘、檔名寫死、沒用 `PATH` 當鍵各要被抓到。
    for what, fake_run, want_bad in XRUN_CASES:
        body = "\n".join("      " + l for l in fake_run.replace("{K}", _XRUN_KEY_EXPR).split("\n"))
        got = bool(xrun_probe_problems("steps:\n  - name: x\n    run: |\n" + body + "\n"))
        if got != want_bad:
            problems.append("XR 探針檢查：%s：期待%s、實際%s" % (what, "有問題" if want_bad else "通過", "有問題" if got else "通過"))
    if "xrun_probe_problems_real()" not in inspect.getsource(main):
        problems.append("main() 沒有呼叫 xrun_probe_problems_real()")
    # R64：歷史 payload 凍結表（R63 第 2 列）與逐目標形狀（第 3、4 列）的檢查本身——完整的要過，缺一組、形狀錯、沒預建、沒偵測到都要被抓到。
    full = tuple(oracle_history._canon(x, "M", "T") for x in oracle_history.PAYLOAD_UNION)
    for what, pays, want_bad in HISTORY_CASES(full):
        got = bool(oracle_history.payload_history_problems(pays, "M", "T"))
        if got != want_bad:
            problems.append("歷史 payload 檢查：%s：期待%s、實際%s" % (what, "有問題" if want_bad else "通過", "有問題" if got else "通過"))
    for what, target, out, hit, want_bad in SHAPE_CASES:
        got = bool(oracle_history.fulfillment_shape_problems(target, out, hit, "/tmp", "/var/T"))
        if got != want_bad:
            problems.append("逐目標形狀檢查：%s：期待%s、實際%s" % (what, "有問題" if want_bad else "通過", "有問題" if got else "通過"))
    saved = oracle_history.CLOSED_TREES
    try:
        oracle_history.CLOSED_TREES = saved + ("deadbee",)   # 封閉清單多一棵樹、凍結表沒有那一列：一定要報
        if not oracle_history.payload_history_problems(full, "M", "T"):
            problems.append("歷史 payload 檢查：封閉清單多一棵樹（凍結表沒有那一列）沒有被抓到")
        # R66 量測後（突變第 637 靶存活）：上一案現在也會被逐樹的摘要／完整 SHA 比對抓到，鍵集合比對因此沒有只靠它的案。
        # 它單獨守的是反方向：封閉清單少一棵樹、凍結表還有那一列時，逐樹比對只走封閉清單，看不到那一列，那棵樹的檢查就安靜地消失。
        oracle_history.CLOSED_TREES = saved[:-1]
        if not oracle_history.payload_history_problems(full, "M", "T"):
            problems.append("歷史 payload 檢查：封閉清單少一棵樹（凍結表還有那一列）沒有被抓到")
    finally:
        oracle_history.CLOSED_TREES = saved
    # R66：凍結表的第二份紀錄（摘要、完整 SHA）對不上、或少一棵樹時一定要報——資料正確時這幾道守衛不會觸發，所以要在這裡故意弄錯一次（R66 的突變對照：關掉這幾道比對時存活）。
    # R68（R67 Codex C2）：TREE_SHA 退回 7 碼縮寫（以樹名開頭、只是不完整）也要報——前一版只看 startswith，這一案存活。
    for name, tree, bad in (("HISTORICAL_DIGEST", "5b5a46d", "0" * 16), ("TREE_SHA", "8b45659", "deadbeef" * 5), ("TREE_SHA", "8b45659", "8b45659"), ("HISTORICAL_DIGEST", "636fcfe", None)):
        table = getattr(oracle_history, name)
        saved_v = table[tree]
        try:
            if bad is None:
                del table[tree]
            else:
                table[tree] = bad
            if not oracle_history.payload_history_problems(full, "M", "T"):
                problems.append("歷史 payload 檢查：%s 的 `%s` %s沒有被抓到" % (name, tree, "少了" if bad is None else "對不上"))
        finally:
            table[tree] = saved_v
    # R68（R67 Codex C2）：假 git 的接受清單要獨立於受測的 TREE_SHA——TREE_SHA 退回縮寫時，重抽也要報（不能被假 git 照收）。
    saved_v = oracle_history.TREE_SHA["8b45659"]
    try:
        oracle_history.TREE_SHA["8b45659"] = "8b45659"
        ran, got = oracle_history.payload_history_regen_problems("/nonexistent", git=_fake_git())
        if not (ran and got):
            problems.append("歷史重抽（假 git）：TREE_SHA 退回 7 碼縮寫時假 git 照收（接受清單要獨立於受測的 TREE_SHA）")
    finally:
        oracle_history.TREE_SHA["8b45659"] = saved_v
    # R68（R67 logic L）：凍結表索引超出 PAYLOAD_UNION 時要報「超出」，不能讓摘要計算先丟 IndexError（那一支曾是死碼）。
    saved_row = oracle_history.HISTORICAL_PAYLOADS["5b5a46d"]
    try:
        oracle_history.HISTORICAL_PAYLOADS["5b5a46d"] = saved_row + (10 ** 6,)
        got = oracle_history.payload_history_problems(full, "M", "T")
        if not any("超出 PAYLOAD_UNION" in g for g in got):
            problems.append("歷史 payload 檢查：凍結表索引超出 PAYLOAD_UNION 沒有報「超出」：%s" % "；".join(got)[:120])
        got = oracle_history._regen_one("5b5a46d", "")   # R68 宣稱查核（程式審查 #4）：有 git 歷史時走的重抽比對也要報「超出」，不丟 IndexError
        if not any("超出 PAYLOAD_UNION" in g for g in got):
            problems.append("歷史重抽比對：凍結表索引超出 PAYLOAD_UNION 沒有報「超出」：%s" % "；".join(got)[:120])
    except IndexError:
        problems.append("歷史 payload 檢查：凍結表索引超出 PAYLOAD_UNION 時丟 IndexError")
    finally:
        oracle_history.HISTORICAL_PAYLOADS["5b5a46d"] = saved_row
    # R68（R67 requirements L）：封閉清單連同它的凍結列、摘要、SHA 一起拿掉一棵樹時，oracle_history.py 內部是自洽的——要靠這個檔案裡的另一份固定清單抓。
    saved_ct = oracle_history.CLOSED_TREES
    try:
        oracle_history.CLOSED_TREES = tuple(t for t in saved_ct if t != "28ec8c3")
        if not closed_trees_pin_problems():
            problems.append("封閉清單的固定份：封閉清單少了 `28ec8c3`（連同凍結列一起拿掉）沒有被抓到")
    finally:
        oracle_history.CLOSED_TREES = saved_ct
    if closed_trees_pin_problems():
        problems.append("封閉清單的固定份：現在的封閉清單與固定份不一致：%s" % "；".join(closed_trees_pin_problems()))
    for what, tree, src, want_bad in REGEN_CASES:
        got = bool(oracle_history._regen_one(tree, src))
        if got != want_bad:
            problems.append("歷史重抽比對：%s：期待%s、實際%s" % (what, "有問題" if want_bad else "通過", "有問題" if got else "通過"))
    for what, fake, targets, want_bad, want_skip in FULFIL_CASES():
        got, skipped = oracle_history.target_fulfillment_problems(fake, targets, tmpdir="/var/T")
        if bool(got) != want_bad or skipped != want_skip:
            problems.append("逐目標履行（假 oracle）：%s：期待%s、跳過 %s；實際%s、跳過 %s" % (what, "有問題" if want_bad else "通過", want_skip, "有問題" if got else "通過", skipped))
        if sorted(fake.calls) != sorted(oracle_history.TARGET_SHAPES):
            problems.append("逐目標履行（假 oracle）：%s：每個目標要各跑一次 run_script，實際跑了 %s" % (what, sorted(fake.calls)))
    for what, kw, want_ran, want_bad in REGEN_GIT_CASES:
        kw = dict(kw); iw = kw.pop("in_worktree", None)
        ran, got = oracle_history.payload_history_regen_problems("/nonexistent", git=_fake_git(**kw), in_worktree=iw)
        if ran != want_ran or bool(got) != want_bad:
            problems.append("歷史重抽（假 git）：%s：期待%s、%s；實際%s、%s（%s）" % (what, "跑了" if want_ran else "跳過", "有問題" if want_bad else "通過",
                                                                     "跑了" if ran else "跳過", "有問題" if got else "通過", "；".join(got)[:120]))
    for what, src, ok in EV_CASES:
        try:
            pays = oracle_history.extract_payloads(src)[2]
            if not ok(pays):
                problems.append("抽常數：%s：抽到 %r" % (what, (pays[0][:20] if pays else pays)))
        except BaseException as e:   # 真的逃出來才算壞；SystemExit／KeyboardInterrupt 不會從這裡來
            problems.append("抽常數：%s：例外逃出 extract_payloads（%s）" % (what, type(e).__name__))
    for what, fmod, freg, want_bad in REAL_HISTORY_CASES():
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                got = payload_history_problems_real(mod=fmod, regen=freg)
        except Exception as e:
            got = None
            problems.append("凍結表組裝（假 oracle、假重抽）：%s：例外 %s" % (what, type(e).__name__))
        if got is not None and bool(got) != want_bad:
            problems.append("凍結表組裝（假 oracle、假重抽）：%s：期待%s、實際%s" % (what, "有問題" if want_bad else "通過", "有問題" if got else "通過"))
    # R68（R67 Codex）：展開前的估計是記憶體守衛——拿掉它時判定不變（展開後的檢查照樣擋），差別只在先配出幾十 MB 才擋，所以量峰值記憶體。
    import tracemalloc
    # 寬度檢查同理（R68 的展開後檢查讓「% 的寬度上億」那一案即使沒有寬度檢查也回 None，突變第 663 靶因此存活——#597 形狀，推送前的靶掃描抓到）。
    for what, src in (("`%` 展開前沒有估計結果大小", 'X = "' + "a" * 60000 + '"\nY = "' + "%s" * 1000 + '" % (' + "X, " * 1000 + ')\nINJECT_PAYLOADS = (Y,)\n'),
                      ("`%` 的大寬度沒有在展開前擋下", 'X = "%050000000d" % 1\nINJECT_PAYLOADS = (X,)\n'),
                      # R68（matcher 靶的突變確認抓到，#597 形狀）：估計加進寬度之後，「%050000000d」改由估計擋下，寬度檢查（`_EV_WIDE_RE`）只剩 `*` 寬度一處不可替代——
                      # 拿掉它時 `%*d` 照樣回 None（展開後的檢查擋），差別只在先配出 50 MB，所以量這一案的峰值。
                      ("`%` 的 `*` 寬度沒有在展開前擋下", 'X = "%*d" % (50000000, 1)\nINJECT_PAYLOADS = (X,)\n'),
                      ("`%` 的四位數寬度重複，展開前的估計沒有算寬度", 'Y = "' + "%9999s" * 10922 + '" % (' + '"", ' * 10922 + ')\nINJECT_PAYLOADS = (Y,)\n')):
        tracemalloc.start()
        try:
            oracle_history.extract_payloads(src)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        if peak > 16 << 20:
            problems.append("抽常數：%s，峰值記憶體 %d MB" % (what, peak >> 20))
    # R68 增量查核（#1、#3）：真的目錄與真的 git——假 git 的案都傳 `in_worktree`，`_in_git_worktree` 與「真的 git 時預設看檔案系統」沒有任何案；
    # 也沒有一案讓真的 git 對一個沒有九棵樹的 repo 跑（R68 第一版的 rc 分類就是在這裡錯的：缺物件的 `cat-file -e <sha>^{commit}` 回 128）。
    import shutil
    with tempfile.TemporaryDirectory(prefix="oracle-selfcheck-git-") as d:
        dp = pathlib.Path(d).resolve()
        base_in_git = oracle_history._in_git_worktree(str(dp))   # 暫存目錄本身若在某個 git 工作樹裡，「沒有 .git」的案不成立，跳過
        (dp / "plain").mkdir(); (dp / "wt").mkdir(); (dp / "wt" / ".git").write_text("gitdir: /nonexistent\n")
        (dp / "parent" / ".git").mkdir(parents=True); (dp / "parent" / "sub").mkdir()
        for what, path, want in (("沒有 .git", dp / "plain", False), (".git 是檔案（連結的工作樹）", dp / "wt", True), (".git 在上一層", dp / "parent" / "sub", True)):
            if base_in_git and not want:
                continue
            if oracle_history._in_git_worktree(str(path)) != want:
                problems.append("git 工作樹判定：%s：期待%s" % (what, "在" if want else "不在"))
        if shutil.which("git"):
            if not base_in_git:
                ran, got = oracle_history.payload_history_regen_problems(str(dp / "plain"))
                if ran or not any("不在 git 工作樹" in g for g in got):
                    problems.append("歷史重抽（真的 git）：沒有 .git 的目錄要跳過（不在 git 工作樹），實際%s：%s" % ("跑了" if ran else "跳過", "；".join(got)[:120]))
            repo = dp / "repo"
            ok = subprocess.run(["git", "init", "-q", str(repo)], capture_output=True).returncode == 0 and subprocess.run(
                ["git", "-C", str(repo), "-c", "user.email=s@c", "-c", "user.name=s", "commit", "-q", "--allow-empty", "-m", "x"], capture_output=True).returncode == 0
            if ok:
                ran, got = oracle_history.payload_history_regen_problems(str(repo))
                if ran or not any("沒有 git 歷史" in g for g in got):
                    problems.append("歷史重抽（真的 git）：沒有九棵樹的 repo（淺層 clone）要跳過，實際%s：%s" % ("跑了" if ran else "跳過", "；".join(got)[:120]))
            else:
                problems.append("歷史重抽（真的 git）：建不出暫存 repo（git init／commit 失敗）")
    for fn in ("payload_history_problems_real()", "target_fulfillment_problems_real()"):
        if fn not in inspect.getsource(main):
            problems.append("main() 沒有呼叫 %s" % fn)
    return problems


def REAL_HISTORY_CASES():
    """R68（R67 blocking 第 1 列 (a)，logic／DA）：`payload_history_problems_real` 本身的兩道接線。(說明, 假 oracle 模組, 假重抽, 是否應該被判有問題)。
    記號守衛：凍結表的比對會把凍結字串換成現在的記號，`INJECT_MARKER` 被改時只有它會紅；重抽：突變副本與 CI 沒有 git 歷史，只有這裡能證明重抽的問題真的被算進去。"""
    import types
    def fake(marker, token=oracle_history.CANON_TOKEN, drop=None):
        return types.SimpleNamespace(INJECT_MARKER=marker, INJECT_PATH_TOKEN=token,
                                     INJECT_PAYLOADS=tuple(oracle_history._canon(x, marker, token) for i, x in enumerate(oracle_history.PAYLOAD_UNION) if i != drop))
    ok, other = fake(oracle_history.CANON_MARKER), fake("OTHER-MARKER")
    return (("記號是凍結的寫法、重抽跳過", ok, lambda: (False, ["假的：沒有歷史"]), False),
            ("記號是凍結的寫法、重抽 0 問題", ok, lambda: (True, []), False),
            ("記號被改（payload 跟著改，凍結表比對自己不會紅）", other, lambda: (False, ["假的：沒有歷史"]), True),
            ("重抽回報一個問題：要算進去", ok, lambda: (True, ["假的：重抽有問題"]), True),
            # R68 宣稱查核（程式審查 #2）：重抽跑了而 0 問題時，前面的問題不能被蓋掉；凍結表比對本身與記號守衛的另一半也要有案。
            ("記號被改、重抽跑了且 0 問題：問題不能被重抽的結果蓋掉", other, lambda: (True, []), True),
            ("路徑記號被改（標記照舊）", fake(oracle_history.CANON_MARKER, "@@OTHER-PATH@@"), lambda: (False, ["假的：沒有歷史"]), True),
            ("模組少一組歷史 payload：凍結表比對要報", fake(oracle_history.CANON_MARKER, drop=0), lambda: (False, ["假的：沒有歷史"]), True))


def HISTORY_CASES(full):
    """(說明, 假的 INJECT_PAYLOADS, 是否應該被判有問題)。`full` 是凍結表聯集的全部字串（標記換成 M、T）。"""
    l32 = oracle_history._canon(oracle_history.PAYLOAD_UNION[8], "M", "T")
    e5b = oracle_history._canon(oracle_history.PAYLOAD_UNION[0], "M", "T")
    return (("聯集全在", full, False),
            ("多出沒登記的 payload 不算錯（只要求包含）", full + ("extra",), False),
            ("缺 `32d45ff` 的第 4 組（R63 第 2 列的形狀）", tuple(x for x in full if x != l32), True),
            ("缺 `5b5a46d` 的第 1 組", tuple(x for x in full if x != e5b), True),
            ("空的", (), True))


_R8 = "ab12cd_3"
_SRC8B = 'INJECT_MARKER = "ORACLE-INJECT-MARKER"\n_S = "$(echo${IFS}" + INJECT_MARKER + ">&197)"\nINJECT_PAYLOADS = ("PWD[" + _S + "]", "-v PWD[" + _S + "]", "-n -o -v PWD[" + _S + "]", "echo " + INJECT_MARKER + " >&197")\n'
REGEN_CASES = (   # (說明, 樹, 合成的 oracle.py 原始碼, 是否應該被判有問題)：`8b45659` 的四組 S payload 用它自己的常數拼出來
    ("與凍結表相符", "8b45659", _SRC8B, False),
    ("少一組", "8b45659", _SRC8B.replace(', "echo " + INJECT_MARKER + " >&197")', ")"), True),
    ("抽不到 INJECT_PAYLOADS", "8b45659", "x = 1\n", True),
)
SHAPE_CASES = (   # (說明, 目標, 正規化後的 stdout, 神諭有沒有偵測到, 是否應該被判有問題)；短路徑的上一層是 /tmp、TMPDIR 是 /var/T
    ("priv 正確", "priv", "OI=<PRIV>/i\nPRE=1\nPB=o%s\nPP=/tmp" % _R8, True, False),
    ("priv 前綴不是 o（R65 regression L：拿掉這一列的 pb 要被抓到）", "priv", "OI=<PRIV>/i\nPRE=1\nPB=tmp%s\nPP=/tmp" % _R8, True, True),
    ("priv 不在短路徑底下（同上，parent）", "priv", "OI=<PRIV>/i\nPRE=1\nPB=o%s\nPP=/var/T" % _R8, True, True),
    ("priv-tmpdir 正確（32d45ff：tmp 前綴、檔名 inject）", "priv-tmpdir", "OI=<PRIV>/inject\nPRE=1\nPB=tmp%s\nPP=/var/T" % _R8, True, False),
    ("priv-tmpdir 前綴是 o（R62 的錯，R63 第 3 列）", "priv-tmpdir", "OI=<PRIV>/inject\nPRE=1\nPB=o%s\nPP=/var/T" % _R8, True, True),
    ("priv-tmpdir 放在 /tmp（上一層錯）", "priv-tmpdir", "OI=<PRIV>/inject\nPRE=1\nPB=tmp%s\nPP=/tmp" % _R8, True, True),
    ("priv-tmpdir 檔名是 i", "priv-tmpdir", "OI=<PRIV>/i\nPRE=1\nPB=tmp%s\nPP=/var/T" % _R8, True, True),
    ("cwd 正確（絕對）", "cwd", "OI=<TMP>/.orc-%s/inject\nPRE=1\nPB=o%s\nPP=/tmp" % (_R8, _R8), True, False),
    ("cwd 給了相對路徑（履行檢查用加引號的 payload，一律應是絕對路徑；R58 第一個草稿的退步，R66 起抓）", "cwd", "OI=.orc-%s/inject\nPRE=1" % _R8, True, True),
    ("cwd-vis 給了相對路徑（同上）", "cwd-vis", "OI=inject\nPRE=1", True, True),
    ("cwd 指到 injectx（R63 的 X2）", "cwd", "OI=<TMP>/.orc-%s/injectx\nPRE=0" % _R8, False, True),
    ("cwd 沒有預先建檔（突變靶 572）", "cwd", "OI=<TMP>/.orc-%s/inject\nPRE=0" % _R8, True, True),
    ("cwd-abs 給了相對路徑", "cwd-abs", "OI=.orc-%s/inject\nPRE=1" % _R8, True, True),
    ("cwd-vis 正確", "cwd-vis", "OI=<TMP>/inject\nPRE=1", True, False),
    ("cwd-vis 指到隱藏目錄", "cwd-vis", "OI=<TMP>/.orc-%s/inject\nPRE=1" % _R8, True, True),
    ("cwd-vis-abs 正確", "cwd-vis-abs", "OI=<TMP>/inject\nPRE=1", True, False),
    ("寫進去之後神諭沒偵測到", "cwd-vis-abs", "OI=<TMP>/inject\nPRE=1", False, True),
    ("沒登記的目標", "cwd-mystery", "OI=<TMP>/inject\nPRE=1", True, True),
)

# R66（R65 logic M：逐目標履行與 git 重抽沒有網——拿掉整個呼叫、迴圈跑零次、偵測寫死成真、逾時不報，`--selftest-matcher` 與真檢查都綠）：
# 用假的 `oracle` 模組跑 `oracle_history.target_fulfillment_problems` 本身。假 `run_script` 依 `inject_to` 回傳排好的結果，所以接線（每個目標都跑、結果傳給形狀檢查、
# 偵測取自 `res[4]["inject"]`、逾時與 `SystemExit` 的處理、上一層目錄的參數）都在這裡量；形狀本身的判斷由上面的 `SHAPE_CASES` 量。
_FULFIL_OK = {   # 每個目標的正確輸出（正規化後的 stdout）；短路徑的上一層 /tmp、TMPDIR 是 /var/T
    "priv": "OI=<PRIV>/i\nPRE=1\nPB=o%s\nPP=/tmp" % _R8, "priv-tmpdir": "OI=<PRIV>/inject\nPRE=1\nPB=tmp%s\nPP=/var/T" % _R8,
    "cwd": "OI=<TMP>/.orc-%s/inject\nPRE=1" % _R8, "cwd-abs": "OI=<TMP>/.orc-%s/inject\nPRE=1" % _R8,
    "cwd-vis": "OI=<TMP>/inject\nPRE=1", "cwd-vis-abs": "OI=<TMP>/inject\nPRE=1",
}
_FULFIL_NEAR = {   # 每個目標各一個差一點的輸出：形狀表任一列被放寬（例如換成 `.*`）就會漏掉它
    "priv": "OI=<PRIV>/inject\nPRE=1\nPB=o%s\nPP=/tmp" % _R8, "priv-tmpdir": "OI=<PRIV>/i\nPRE=1\nPB=tmp%s\nPP=/var/T" % _R8,
    "cwd": "OI=<TMP>/.orc-%s/injectx\nPRE=1" % _R8, "cwd-abs": "OI=.orc-%s/inject\nPRE=1" % _R8,
    "cwd-vis": "OI=<TMP>/.orc-%s/inject\nPRE=1" % _R8, "cwd-vis-abs": "OI=inject\nPRE=1",
}


class _FakeOracle:
    """`target_fulfillment_problems` 只用到這幾個名字。`plan`：目標 → `"ok"`／`"near"`／`"miss"`（沒偵測到）／`"timeout"`／`"exit"`（`sys.exit`）。"""
    INJECT_PAYLOADS = ("echo M >>$ORACLE_INJECT", 'echo M >> "$ORACLE_INJECT"')

    def __init__(self, plan, priv_ok=True):
        self.plan, self.priv_ok, self.calls = plan, priv_ok, []

    def _short_tmp(self):
        return "/tmp"

    def pick_bash(self):
        return "bash"

    def _tmpdir_spaced(self):
        return False

    def _tmpdir_priv_ok(self):
        return self.priv_ok

    def _inject_runs(self, spaced=False, tmpdir_priv=False):
        for to in ("cwd", "priv", "cwd-vis", "cwd-abs", "cwd-vis-abs") + (("priv-tmpdir",) if tmpdir_priv else ()):
            yield self.INJECT_PAYLOADS[1], to

    def run_script(self, run, bash, stub_bin, yaml_env=None, extra=False, inject=None, inject_to="priv", inject_keys="all"):
        self.calls.append(inject_to)
        how = self.plan.get(inject_to, "ok")
        if how == "exit":
            sys.exit("假的：建不出 %s 的路徑" % inject_to)
        if how == "timeout":
            return ("timeout", None, None, None, {"inject": False})
        out = (_FULFIL_NEAR if how == "near" else _FULFIL_OK)[inject_to]
        return ("piped", (0, out.encode(), b"", None), None, None, {"inject": how != "miss"})


def FULFIL_CASES():
    """(說明, 假 oracle, manifest 的目標集合, 是否應該被判有問題, 應該被跳過的目標)。"""
    every = set(_FULFIL_OK)
    cases = [("六個目標都正確", _FakeOracle({}), every, False, [])]
    for t in sorted(every):
        cases.append(("%s 的輸出差一點（形狀表放寬或結果沒傳給形狀檢查）" % t, _FakeOracle({t: "near"}), every, True, []))
    cases += [("cwd-vis 寫進去之後沒偵測到（偵測不得寫死成真）", _FakeOracle({"cwd-vis": "miss"}), every, True, []),
              ("priv 逾時（逾時要報）", _FakeOracle({"priv": "timeout"}), every, True, []),
              ("manifest 多一個目標（目標集合要比對）", _FakeOracle({}), every | {"cwd-mystery"}, True, []),
              ("priv-tmpdir 建不出路徑、這個環境也不用它（記為跳過，不是問題）", _FakeOracle({"priv-tmpdir": "exit"}, priv_ok=False), every, False, ["priv-tmpdir"]),
              ("priv-tmpdir 建不出路徑、但這個環境會用它（是問題）", _FakeOracle({"priv-tmpdir": "exit"}), every, True, []),
              ("cwd 建不出路徑（這個環境一定用它）", _FakeOracle({"cwd": "exit"}), every, True, [])]
    return cases


def _fake_git(missing=(), unreadable=(), boom=(), pct=False, other_marker=(), catboom=(), catdecode=(), nogit=False, refuse=False, showdecode=()):
    """假的 git：`cat-file -e` 對 `missing` 以外的樹成功；`show` 回傳依凍結表合成的 `oracle.py`（`pct=True` 時 `8b45659` 那一份用 `%` 拼字串，量 `_ev` 的 `%`）。
    R68（R67 Codex C1）：`catboom`／`catdecode` 讓那幾棵的 `cat-file` 丟逾時／解碼錯誤，`nogit` 讓每一次呼叫都丟 `FileNotFoundError`（沒有 git 可執行檔）。
    R68（R67 Codex C2）：只接受 40 位十六進位的完整 SHA——接受清單不能只由受測的 `TREE_SHA` 反建，否則 `TREE_SHA` 退回縮寫時假 git 也照收。
    R68 宣稱查核：`refuse` 讓 `rev-parse` 與每一次 `cat-file` 都回 rc=128（git 拒絕這個 repo，例如 dubious ownership；缺物件的 `cat-file` 也回 128，分不開），`showdecode` 讓那幾棵的 `show` 丟解碼錯誤。"""
    import types
    by_sha = {oracle_history.TREE_SHA[t]: t for t in oracle_history.CLOSED_TREES if re.fullmatch(r"[0-9a-f]{40}", oracle_history.TREE_SHA.get(t, ""))}

    def src(tree):
        if pct and tree == "8b45659":
            return _SRC8B_PCT
        m, k = ("OTHER-MARKER", oracle_history.CANON_TOKEN) if tree in other_marker else (oracle_history.CANON_MARKER, oracle_history.CANON_TOKEN)
        pays = tuple(oracle_history._canon(oracle_history.PAYLOAD_UNION[i], m, k) for i in oracle_history.HISTORICAL_PAYLOADS[tree])
        return 'INJECT_MARKER = %r\nINJECT_PATH_TOKEN = %r\nINJECT_PAYLOADS = %r\n' % (m, k, pays)

    def git(*a):
        if nogit:
            raise FileNotFoundError(2, "No such file or directory", "git")
        if a[0] == "rev-parse":
            return types.SimpleNamespace(returncode=128 if refuse else 0, stdout=".git\n")
        if a[0] == "cat-file":
            t = by_sha.get(a[2].split("^")[0])
            if t in catboom:
                raise subprocess.TimeoutExpired("git", 60)
            if t in catdecode:
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
            if refuse:
                return types.SimpleNamespace(returncode=128, stdout="")
            return types.SimpleNamespace(returncode=128 if t is None or t in missing else 0, stdout="")   # 真的 git：`cat-file -e <sha>^{commit}` 缺物件時 rc=128（R68 Linux 預跑抓到）
        t = by_sha.get(a[1].split(":")[0])
        if t in boom:
            raise subprocess.TimeoutExpired("git", 60)
        if t in showdecode:
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        if t is None or t in unreadable:
            return types.SimpleNamespace(returncode=128, stdout="")
        return types.SimpleNamespace(returncode=0, stdout=src(t))
    return git


_SRC8B_PCT = 'INJECT_MARKER = "ORACLE-INJECT-MARKER"\n_S = "$(echo${IFS}%s>&197)" % INJECT_MARKER\nINJECT_PAYLOADS = ("PWD[" + _S + "]", "-v PWD[" + _S + "]", "-n -o -v PWD[" + _S + "]", "echo %s >&197" % INJECT_MARKER)\n'
REGEN_GIT_CASES = (   # (說明, 假 git 的參數, 期待「跑了」, 期待有問題)
    ("九棵樹都在、內容相符", {}, True, False),
    ("九棵樹都在、8b45659 用 % 拼字串（_ev 要認得 %）", {"pct": True}, True, False),
    ("九棵都沒有（淺層 clone）：跳過，不算問題", {"missing": tuple(oracle_history.CLOSED_TREES)}, False, True),
    ("只缺一棵：是問題，不是整個跳過", {"missing": ("32d45ff",)}, True, True),
    ("一棵讀不到 oracle.py", {"unreadable": ("6490b57",)}, True, True),
    ("一棵 git show 逾時：報問題，不讓 selfcheck 當掉", {"boom": ("636fcfe",)}, True, True),
    ("一棵的標記不是凍結的寫法：不能逕自正規化（R65 Codex：全域字串替換分不出字面與標記）", {"other_marker": ("b86bc53",)}, True, True),
    # R68（R67 Codex C1、logic L）：探測本身失敗是問題，不是「沒有歷史」——前一版任一棵的 `cat-file` 丟例外就整輪回 (False, …)。
    ("第一棵的 cat-file 逾時：是問題，不是整個跳過", {"catboom": ("5b5a46d",)}, True, True),
    ("中途一棵的 cat-file 逾時：前面確認有歷史的樹不作廢", {"catboom": ("b86bc53",)}, True, True),
    ("一棵的 cat-file 輸出解碼失敗：是問題", {"catdecode": ("6490b57",)}, True, True),
    ("每一棵的 cat-file 都逾時：是問題，不能當成「九棵都沒有歷史」跳過", {"catboom": tuple(oracle_history.CLOSED_TREES)}, True, True),
    ("沒有 git 可執行檔：跳過，不算問題", {"nogit": True}, False, True),
    # R68 宣稱查核（程式審查 #1、#7）：`cat-file -e` 的 rc=1 才是「沒有這個 commit」；rc=128（不是 git 工作樹、git 拒絕這個 repo）不能當成沒有歷史。
    ("git 拒絕這個 repo（每一棵的 cat-file 都 rc=128，例如 dubious ownership）：是問題，不能當成「九棵都沒有歷史」跳過", {"refuse": True}, True, True),
    ("不在 git 工作樹（找不到 .git）：跳過，不算問題", {"in_worktree": False}, False, True),
    ("一棵的 git show 輸出解碼失敗：是問題", {"showdecode": ("ecb77d9",)}, True, True),
)
# R66（R65 security L）：`_ev` 抽的是舊樹原始碼的常數，資源要有上限，例外不能逃出去。(說明, 原始碼, 抽到的 payload 檢查)
EV_CASES = (
    ("3000 項的 + 鏈：RecursionError 不逃出去", 'M = "a"\nINJECT_PAYLOADS = (M' + " + M" * 3000 + ",)\n", lambda pays: pays is None),
    ("% 的寬度上億：不展開", 'X = "%050000000d" % 1\nINJECT_PAYLOADS = (X,)\n', lambda pays: pays is None),
    ("% 的 * 寬度：不展開", 'X = "%*d" % (50000000, 1)\nINJECT_PAYLOADS = (X,)\n', lambda pays: pays is None),
    ("% 參數不對：不當掉", 'X = "%d" % "a"\nINJECT_PAYLOADS = (X,)\n', lambda pays: pays is None),
    ("倍增串接：單一字串有上限", 'X = "aaaa"\n' + "".join("X = X + X\n" for _ in range(24)) + "INJECT_PAYLOADS = (X,)\n", lambda pays: pays is not None and len(pays[0]) <= 1 << 16),
    ("語法錯誤：回 None", "INJECT_PAYLOADS = (\n", lambda pays: pays is None),
    # R68（R67 logic L、Codex）：上限也要套到常數本身與 `%` 的結果——前一版只看 `+` 與格式字串本身。
    ("單一常數超過上限：不抽", 'X = "' + "a" * ((1 << 16) + 1) + '"\nINJECT_PAYLOADS = (X,)\n', lambda pays: pays is None),
    ("% 的結果超過上限：不展開", 'X = "' + "a" * 40000 + '"\nY = "%s%s" % (X, X)\nINJECT_PAYLOADS = (Y,)\n', lambda pays: pays is None),
    ("大整數常數：不抽", 'X = 1000000000000000000000\nINJECT_PAYLOADS = ("%d" % X,)\n', lambda pays: pays is None),
    ("四位數寬度重複一萬次：展開前的估計要算進寬度（R68 宣稱查核，程式審查 #5）", 'Y = "' + "%9999s" * 10922 + '" % (' + '"", ' * 10922 + ')\nINJECT_PAYLOADS = (Y,)\n', lambda pays: pays is None),
    ("五位數寬度：結果在上限之內也不展開（R68 增量查核 #2：`_EV_WIDE_RE` 的數字分支原本沒有任何殺手）", 'X = "%10000d" % 1\nINJECT_PAYLOADS = (X,)\n', lambda pays: pays is None),
    ("`%r` 把不可印字元展開成跳脫序列：估計之內、結果超過上限就不收（只有展開後的檢查擋得到）", 'X = "' + "\\x00" * 20000 + '"\nY = "%r" % (X,)\nINJECT_PAYLOADS = (Y,)\n', lambda pays: pays is None),
    ("四位數寬度重複：估計超過上限就不展開", 'Y = "' + "%9999s" * 10 + '" % (' + '"a", ' * 10 + ')\nINJECT_PAYLOADS = (Y,)\n', lambda pays: pays is None),
    ("短格式字串重複：結果估計超過上限就不展開", 'X = "' + "a" * 1000 + '"\nY = "' + "%s" * 100 + '" % (' + "X, " * 100 + ')\nINJECT_PAYLOADS = (Y,)\n', lambda pays: pays is None),
)


XRUN_CASES = (   # (說明, 假的 run 內容, 是否應該被判有問題)；`_XRUN_KEY_EXPR` 定義在下面，這裡在呼叫時才取
    ("固定寫法：import 白名單、狀態檔名接 PATH 雜湊", "python3 -c 'import os, sys, hashlib, subprocess; t = \"/tmp/orc-known-xrun-taint-\" + {K}; sys.exit(0) if os.path.exists(t) else None'", False),
    ("固定寫法，加一行提到 time.time() 的 bash 註解（註解不算行為）", "# 不准用 time.time()\npython3 -c 'import os, sys, hashlib; t = \"/tmp/orc-known-xrun-taint-\" + {K}'", False),
    ("讀時鐘（import time、30 秒過期）", "python3 -c 'import os, time, hashlib; t = \"/tmp/orc-known-xrun-taint-\" + {K}; time.time() - os.path.getmtime(t) < 30'", True),
    ("讀時鐘（from time import time as now、os.stat 的 st_ctime）", "python3 -c 'from time import time as now; import os, hashlib; t = \"/tmp/orc-known-xrun-taint-\" + {K}; now() - os.stat(t).st_ctime < 30'", True),
    ("只讀 stat（`os` 在允許清單內，只有禁用寫法那一道抓得到）", "python3 -c 'import os, sys, hashlib; t = \"/tmp/orc-known-xrun-taint-\" + {K}; sys.exit(0) if os.path.exists(t) and os.stat(t).st_ctime > 0 else None'", True),
    ("import uuid（`uuid1()` 帶時間戳；文字裡沒有禁用字，只有 import 允許清單那一道抓得到）", "python3 -c 'import os, hashlib, uuid; t = \"/tmp/orc-known-xrun-taint-\" + {K}; k = uuid.uuid1().hex'", True),
    ("檔名寫死成完整字串（含連字號）、PATH 只是算了沒用", "python3 -c 'import os, hashlib; k = {K}; t = \"/tmp/orc-known-xrun-taint-shared\"'", True),
    ("檔名接了常數尾碼、PATH 只是算了沒用", "python3 -c 'import os; unused = os.environ[\"PATH\"]; t = \"/tmp/orc-known-xrun-taint-\" + \"shared\"'", True),
    ("沒有用 PATH 當鍵", "python3 -c 'import os; t = \"/tmp/orc-known-xrun-taint-\" + str(os.getuid())'", True),
    # R66：XR6、XR7 的兩種固定寫法要過；上層目錄寫死檔名、狀態檔放在使用者的家目錄要被抓到。這是探針衛生，不是豁免範圍：(9) 2026-11-08 起以性質劃界，家目錄也在豁免內。
    # R68（R67 logic L）：這道檢查只看含 `orc-known-xrun` 的字串——家目錄那一案被抓，是因為檔名含這個字、又不是三種固定寫法之一；不含這個字的寫入（不論寫到哪裡）不在這道檢查內。
    ("固定寫法：/var/tmp 底下", "python3 -c 'import os, sys, hashlib; t = \"/var/tmp/orc-known-xrun-vtaint-\" + {K}; sys.exit(0) if os.path.exists(t) else None'", False),
    ("固定寫法：步驟 cwd 的上層", "python3 -c 'import os, sys, hashlib; t = os.path.join(os.path.dirname(os.getcwd()), \"orc-known-xrun-ptaint-\" + {K}); sys.exit(0) if os.path.exists(t) else None'", False),
    ("步驟 cwd 的上層、檔名寫死", "python3 -c 'import os, hashlib; k = {K}; t = os.path.join(os.path.dirname(os.getcwd()), \"orc-known-xrun-ptaint-shared\")'", True),
    ("狀態檔放在使用者的家目錄（`orc-known-xrun` 不是三種固定寫法之一）", "python3 -c 'import os, hashlib; t = os.path.join(os.path.expanduser(\"~\"), \"orc-known-xrun-htaint-\" + {K})'", True),
)


# 歷史上的注入哨兵位置——**凍結的 manifest**（R62 H2，R61 requirements／logic／DA／Codex：『由構造保證單調』沒有機械檢查，R54 把私有目錄搬到 `/tmp`、R50 移除 cwd 頂層哨兵都是『取代』卻沒有任何東西變紅）。
# 它放在這個檔案、不放在 `oracle.py`：manifest 與被檢查的函式不在同一個檔案裡，改函式的人要另外改 manifest。每一列是 (名字, 歷史, `_inject_runs` 裡負責它的目標, 哪些 payload 要有這個目標, 目標存在的條件)。
# 封閉列舉，只有這六列；新增位置要在這裡加一列（讓檢查變嚴），**拿掉一列要有書面理由**。fd 197（R50 起）不是 `_inject_runs` 的目標——它隨每一次執行存在，不在這張表裡。
# **這張表守的範圍**：`_inject_runs(spaced, tmpdir_priv)` 的輸出——哪些 payload 在哪個條件下試哪些目標、目標的順序。它**不**守：(1) 路徑形狀（檔名 `inject` 或 `i`、絕對或相對）——`_inject_runs` 的輸出裡沒有，R64 起由 `oracle_history.py` 的逐目標履行檢查（`TARGET_SHAPES`）守，另由探針守
# （`priv-tmpdir` 的檔名：沙箱版的 SP9、SP10；`cwd-vis` 與 `cwd-vis-abs` 的絕對路徑：PX5；`cwd-abs`：PX6——R62 加了 `cwd-vis-abs` 之後 PX1～PX3 也寫得進 cwd 頂層的 `inject`，不再單獨守 `cwd-abs`）；(2) `run_script` 真的履行每個目標（同上，R64 的逐目標履行檢查、探針與突變靶守）；(3) `_inject_key_modes`（鍵模式軸，由 aud 的值比較守）；(4) payload 集合本身——檢查只巡訪傳入的 payload 清單（真檢查傳 `oracle.INJECT_PAYLOADS`，不是獨立凍結的歷史 payload 清單），清單外的 payload 輸出的目標不檢查；獨立凍結的歷史 payload 清單是 `oracle_history.py` 的 `HISTORICAL_PAYLOADS`（R64）。
# 表裡的 `cond` 是 `None`、`"spaced"`（暫存目錄的路徑含空白）或 `"tmpdir_priv"`（`_tmpdir_priv_ok()`）之一，檢查時真的拿這兩個布林去評估（不是當標籤）。
HISTORICAL_SENTINEL_POSITIONS = (
    ("priv-tmp",        "R54 起：`/tmp/oXXXXXXXX/i`（`_short_tmp()`）",                                                       "priv",        "all",          None),
    ("priv-tmpdir",     "R52～R53（`32d45ff`）：預設 `TMPDIR` 底下的 `<priv>/inject`（R54 取代；檔名也是歷史形狀的一部分）",   "priv-tmpdir", "lit-or-env",   "tmpdir_priv"),
    ("cwd-hidden",      "`5b5a46d`、R58 起：`<cwd>/.orc-XXXXXXXX/inject`",                                                    "cwd",         "env",          None),
    ("cwd-visible",     "R43～R47（`2835ead`、`28ec8c3`）：`<cwd>/inject`（R50 移除、R58 加回的是隱藏目錄的那個）",           "cwd-vis",     "env",          None),
    ("cwd-abs",         "R60：含空白的絕對路徑（`5b5a46d` 的設定；只有不加引號的 E 組）",                                     "cwd-abs",     "env-unquoted", "spaced"),
    ("cwd-visible-abs", "R62：`<cwd>/inject` 的絕對路徑，含空白時（`28ec8c3` 一律給絕對路徑；只有不加引號的 E 組）",           "cwd-vis-abs", "env-unquoted", "spaced"),
)
MANIFEST_DROPS = ("priv", "priv-tmpdir", "cwd", "cwd-vis", "cwd-abs", "cwd-vis-abs", "uncond", "front")      # 假產生器拿掉的目標（`uncond`：有條件的目標變成無條件；`front`：新目標插在最前面）
MANIFEST_VARIANTS = ("empty-base", "swap", "and", "mixed-miss", "extra-target", "uncond-tmpdir", "uncond-vis-abs")                               # 條件寫錯的假產生器，見 `_fake_runs`
MANIFEST_CASE_COUNT = 1 + len(MANIFEST_DROPS) + len(MANIFEST_VARIANTS) + 1                                    # 完整序列 1 ＋ 拿掉 ＋ 寫錯 ＋ 列數寫死 1（`--selftest-matcher` 的輸出用）


def sentinel_manifest_problems(payloads, token, runs_fn):
    """`runs_fn(spaced, tmpdir_priv)`（`oracle._inject_runs`）產生的 (payload, 目標) 序列，是否涵蓋 `HISTORICAL_SENTINEL_POSITIONS` 的每一列。**四個 (spaced, tmpdir_priv) 組合各檢查一次**（Codex 預審 M3：前一版只驗兩個對角格），每個組合、每個 payload：
    (1) manifest 的每一列，條件評估為真且該 payload 屬於這一列的種類時，目標要在序列裡；條件評估為假（或種類不符）時，目標**不**能在序列裡（不是無條件多跑、也不是條件綁錯）；
    (2) 序列裡的每個目標都要在 manifest 裡（封閉：多一個沒登記的目標也紅，逼著新增位置時同步改 manifest），且同一個目標在同一個 payload 的序列裡只出現一次；
    (3) R60 的序列（`cwd`〔含空白時再 `cwd-abs`〕、`priv`；非 E 組只有 `priv`）是新序列的**前綴**——新目標只能加在每個 payload 自己的序列末端：R60 判得出繞過的 step 仍判得出（前提：新增的執行不經共用主機狀態影響後面的執行，見 H3）；報出來的 payload 編號可能變小（某個 payload 經新目標較早命中），不是『歸因不變』。
    基底格（兩個條件都不成立：暫存目錄不含空白、且 `_tmpdir_priv_ok()` 不成立）整個沒有注入執行時，(1) 的『該有』檢查就會抓到（`priv` 對每個 payload 都該有），所以不另設『序列不能為空』的檢查（那個檢查的突變體必然存活，R62 試過、拿掉）。
    回傳問題清單（空＝全過）。這個函式接受 `runs_fn` 與 `payloads`，所以單元測試（`matcher_problems`）可以餵假的產生器、確認缺任何一列與條件寫錯都會被抓到。"""
    probs = []
    conds = {None: lambda sp, tp: True, "spaced": lambda sp, tp: sp, "tmpdir_priv": lambda sp, tp: tp}
    known = {row[2] for row in HISTORICAL_SENTINEL_POSITIONS}

    def needs(kind, pl):
        is_e = "$ORACLE_INJECT" in pl
        return {"all": True, "lit-or-env": is_e or token in pl, "env": is_e, "env-unquoted": is_e and '"$ORACLE_INJECT"' not in pl}[kind]
    for spaced in (False, True):
        for tp in (False, True):
            here = "spaced=%s,tmpdir_priv=%s" % (spaced, tp)
            by = {}
            for pl, to in runs_fn(spaced, tp):
                by.setdefault(pl, []).append(to)
            for pl in payloads:
                got = by.get(pl, [])
                for name, _why, target, kind, cond in HISTORICAL_SENTINEL_POSITIONS:
                    want = needs(kind, pl) and conds[cond](spaced, tp)
                    if want and target not in got:
                        probs.append("[%s] 哨兵位置 %s：目標 %r 不在 payload %r 的序列裡（%s）" % (here, name, target, pl[:30], got))
                    if not want and target in got:
                        probs.append("[%s] 哨兵位置 %s：條件 %r 評估為假（或這個 payload 不屬於它）時目標 %r 仍然出現：payload %r，序列 %s" % (here, name, cond, target, pl[:30], got))
                extra = [t for t in got if t not in known]
                if extra:
                    probs.append("[%s] payload %r 的序列有 manifest 沒登記的目標 %s（新增位置要在 manifest 加一列）" % (here, pl[:30], extra))
                if len(got) != len(set(got)):
                    probs.append("[%s] payload %r 的序列有重複的目標：%s" % (here, pl[:30], got))
                is_e = "$ORACLE_INJECT" in pl
                old = (["cwd"] + (["cwd-abs"] if spaced and '"$ORACLE_INJECT"' not in pl else []) + ["priv"]) if is_e else ["priv"]
                if got[:len(old)] != old:
                    probs.append("[%s] R60 的目標序列 %s 不是 payload %r 的新序列 %s 的前綴" % (here, old, pl[:30], got))
    return probs


def load_oracle():
    import importlib.util
    spec = importlib.util.spec_from_file_location("oracle_under_check", ORACLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sentinel_manifest_problems_real():
    mod = load_oracle()
    return sentinel_manifest_problems(mod.INJECT_PAYLOADS, mod.INJECT_PATH_TOKEN, mod._inject_runs)


# R68（R67 requirements L）：封閉清單的第二份。oracle_history.py 裡的 CLOSED_TREES、HISTORICAL_PAYLOADS、HISTORICAL_DIGEST、TREE_SHA 互相比對，
# 一起拿掉一棵樹時它們仍然自洽；這一份在別的檔案，改封閉清單必須兩處一起改，並在 oracle_history.py 的納入準則旁寫理由。
_CLOSED_TREES_PIN = ("5b5a46d", "8b45659", "32d45ff", "b86bc53", "6490b57", "ecb77d9", "bf0c8a7", "28ec8c3", "636fcfe")


def closed_trees_pin_problems():
    if tuple(oracle_history.CLOSED_TREES) != _CLOSED_TREES_PIN:
        return ["封閉清單與 oracle_selfcheck.py 的固定份不一致：%s 對 %s（改封閉清單要兩處一起改，理由寫在納入準則旁）" % (list(oracle_history.CLOSED_TREES), list(_CLOSED_TREES_PIN))]
    return []


def payload_history_problems_real(mod=None, regen=None):
    """R64（R63 第 2 列）：封閉清單各樹的每一組 payload 都在 `oracle.INJECT_PAYLOADS` 裡；有 git 歷史時另外把凍結表與歷史重抽的結果逐列比對（沒有歷史就印一行說明、不算通過也不算失敗）。
    R68（R67 blocking 第 1 列 (a)）：`mod`、`regen` 可注入，`--selftest-matcher` 用假的模組與假的重抽驗證記號守衛與重抽結果的加入（突變副本與 CI 沒有 git 歷史，真的重抽在那裡一律跳過）。"""
    mod = mod if mod is not None else load_oracle()
    probs = oracle_history.payload_history_problems(mod.INJECT_PAYLOADS, mod.INJECT_MARKER, mod.INJECT_PATH_TOKEN)
    if (mod.INJECT_MARKER, mod.INJECT_PATH_TOKEN) != (oracle_history.CANON_MARKER, oracle_history.CANON_TOKEN):   # R66（R65 Codex）：凍結表的比對會把記號換成現在的值，記號本身要另外守
        probs.append("INJECT_MARKER／INJECT_PATH_TOKEN 與凍結的寫法不同：%r、%r" % (mod.INJECT_MARKER, mod.INJECT_PATH_TOKEN))
    probs += closed_trees_pin_problems()
    ran, rprobs = regen() if regen is not None else oracle_history.payload_history_regen_problems(str(HERE.parents[2]))
    if ran:
        probs += rprobs
    else:
        print("↷ 歷史 payload 凍結表與 git 歷史的重抽比對：跳過（%s）——凍結表本身仍逐列檢查" % "；".join(rprobs))
    return probs


def target_fulfillment_problems_real():
    """R64（R63 第 3、4 列）：每個 `_inject_runs` 目標真的跑一次 `run_script`，比對實際建出的哨兵路徑形狀、上一層、預先建檔與偵測（`oracle_history.TARGET_SHAPES`）。"""
    probs, skipped = oracle_history.target_fulfillment_problems(load_oracle(), {row[2] for row in HISTORICAL_SENTINEL_POSITIONS})
    if skipped:
        print("↷ 逐目標履行：%s 跳過——這個環境的 `_inject_runs` 不用它、`run_script` 也建不出它的路徑（例如 TMPDIR 含空白時的 priv-tmpdir）；不算通過" % ", ".join(skipped))
    return probs


# R62 量測抓到（2026-10-25）：第 110 項的 XR 探針原本用固定檔名 `/tmp/orc-known-xrun-*` 加『30 秒後視為過期』。XR1、XR3 的 taint 只在第一次寫入，之後的執行看它的**年齡**；
# XR2 每次執行都重寫計數檔，要**相鄰兩次執行的間隔**超過 30 秒才會重置。所以機器變慢時判定可能從『一致』翻成『繞過』（窗口改成 0 秒實測三格都判繞過；
# 慢到什麼程度才翻沒有量）；平行的神諭（突變全輪 `--jobs 8`）又共用同一組固定檔名，一方的 taint 會吃掉另一方的執行。兩者都讓第 110 項的判定隨環境改變
# （2026-10-25 的前置驗證就紅過一次，當時校準正常，成因沒有分辨），突變全輪的 `oracle-inverted` 靶因此可能被記成『殺掉』而不是被突變殺掉（本來會存活的靶看不出來）。
# 修法：狀態檔名接上神諭這次呼叫的 `PATH` 雜湊（`PATH` 由 `run_script` 以 `stub_bin` 蓋寫，`stub_bin` 是 `main()` 每次呼叫 mkdtemp 一次、整個行程共用；XR 探針的 YAML `env:` 沒有 `PATH`）。
# **這裡的檢查是刻意的封閉結構約束，不是『不讀時鐘』的證明**（R62 Codex 第三次核對 1–3：黑名單版擋不住 `from time import time as now`、`os.stat(t).st_ctime`、接了常數尾碼的檔名）：
# 每個 `run:`（先去掉 bash 的註解行）必須 (1) 只 import `os`、`sys`、`hashlib`、`subprocess`（不准 `from … import`、`__import__`、`importlib`），(2) 不出現 `_XRUN_FORBIDDEN_RE` 列的時間、stat 與
# 檔案時間類寫法（Python 與 bash 兩邊），(3) 每一個 `orc-known-xrun` 都恰好是下面三種固定寫法之一，且至少一個：`"/tmp/orc-known-xrun-<種類>-" + <_XRUN_KEY_EXPR>`、
# `"/var/tmp/orc-known-xrun-<種類>-" + <_XRUN_KEY_EXPR>`、`os.path.join(os.path.dirname(os.getcwd()), "orc-known-xrun-<種類>-" + <_XRUN_KEY_EXPR>)`（R66：後兩種是 R63 第 6 列的 `/var/tmp` 與步驟 cwd 上層的 taint 格，
# 使用者 2026-11-01 的決定要求收進這張探針；三個位置都在 (9) 的豁免範圍內。固定寫法只收這三種是探針衛生的約束，不是豁免範圍）。
# 語義相同的其他寫法（例如 `os.environ.get("PATH", "")`）也會被判不符——改探針的人要同時改這裡，訊息會說是『不符合固定寫法』。
XRUN_PROBE = PROBES / "injection-cross-run-state-known-blind-spots.yml"
_XRUN_KEY_EXPR = 'hashlib.sha1(os.environ["PATH"].encode()).hexdigest()[:16]'
_XRUN_STATE_RE = re.compile(r'"(?:/tmp|/var/tmp)/orc-known-xrun-[a-z]+-" \+ ' + re.escape(_XRUN_KEY_EXPR)
                            + r'|os\.path\.join\(os\.path\.dirname\(os\.getcwd\(\)\), "orc-known-xrun-[a-z]+-" \+ ' + re.escape(_XRUN_KEY_EXPR) + r'\)')
_XRUN_ALLOWED_IMPORTS = frozenset({"os", "sys", "hashlib", "subprocess"})
_XRUN_IMPORT_RE = re.compile(r"\bimport\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)")
_XRUN_FORBIDDEN_RE = re.compile(r"\bfrom\s+\w+\s+import\b|__import__|\bimportlib\b|\bdatetime\b|\btime\b|stat\b|\bst_\w*time|\bget[amc]time\b|\btimes\b|\bscandir\b"
                                r"|\bdate\b|\bEPOCH\w*|\bSECONDS\b|%\(|-m(?:min|time)\b|-newer")


def xrun_probe_problems(text):
    """XR 探針的結構檢查：回傳問題清單（空清單＝通過）。規則見上面的註解（封閉的固定寫法，不是『不讀時鐘』的證明）。"""
    import yaml   # 神諭本身就依賴 PyYAML（`oracle.py`）；用解析器取每個 `run:` 的值，不用正規式切縮排（前一版的正規式把後面的 step 併進第一個 run）

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "run" and isinstance(v, str):
                    yield v
                else:
                    yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
    runs = list(walk(yaml.safe_load(text)))
    if not runs:
        return ["探針裡找不到任何 `run:` 區塊"]
    problems = []
    for i, r in enumerate(runs, 1):
        code = "\n".join(l for l in r.split("\n") if not l.lstrip().startswith("#"))   # 註解行裡的字不算行為（R62 Codex 第三次核對 3）
        hit = _XRUN_FORBIDDEN_RE.search(code)
        if hit:
            problems.append("第 %d 個 run 不符合固定寫法：用到不允許的 `%s`（時間、stat、檔案時間或動態 import 一律不准，判定不能隨時間改變）" % (i, hit.group(0)))
        bad_imports = sorted({m for g in _XRUN_IMPORT_RE.findall(code) for m in re.split(r"\s*,\s*", g)} - _XRUN_ALLOWED_IMPORTS)
        if bad_imports:
            problems.append("第 %d 個 run 不符合固定寫法：import 了允許清單以外的模組 %s（只准 os、sys、hashlib、subprocess）" % (i, "、".join(bad_imports)))
        n_state, n_keyed = code.count("orc-known-xrun"), len(_XRUN_STATE_RE.findall(code))
        if n_state == 0:
            problems.append("第 %d 個 run 沒有 `orc-known-xrun-…` 狀態檔" % i)
        elif n_keyed != n_state:
            problems.append("第 %d 個 run 不符合固定寫法：`orc-known-xrun` 出現 %d 次，只有 %d 次是三種固定寫法之一（`/tmp`、`/var/tmp` 或步驟 cwd 的上層，接 %s；寫死或接了別的尾碼的檔名會讓平行的神諭與上一次呼叫的殘檔共用狀態）" % (i, n_state, n_keyed, _XRUN_KEY_EXPR))
    return problems


def xrun_probe_problems_real():
    return xrun_probe_problems(XRUN_PROBE.read_text(encoding="utf-8"))


def _fake_runs(drop=None, variant=None):
    """單元測試用的假 `_inject_runs`：實作 manifest 要求的完整序列。`drop` 指定拿掉的目標（`MANIFEST_DROPS`；`uncond`：有條件的目標變成無條件；`front`：新目標插在最前面）。
    `variant`（`MANIFEST_VARIANTS`）是**條件寫錯**的假產生器——都在 (True, True)、有的在 (False, False) 也正確，只有四個組合都驗才抓得到（Codex 預審 M3）：
    `empty-base` 兩個條件都不成立時整個不跑（正常環境完全沒有注入執行）；`swap` 兩個條件接反（`cwd-abs` 看 tmpdir_priv、`priv-tmpdir` 看 spaced）；
    `and` `priv-tmpdir` 的條件寫成 `tmpdir_priv and spaced`（安全且無空白的 TMPDIR 上這個目標消失）；`mixed-miss` 只在 (spaced=True, tmpdir_priv=False) 缺 `cwd`；`extra-target` 多一個沒登記的目標；`uncond-tmpdir`、`uncond-vis-abs` 只讓**一個**目標（`priv-tmpdir`、`cwd-vis-abs`）變成無條件——它們加在序列末端，R60 的前綴檢查看不到，只有『條件為假時目標不能出現』這一條抓得到（`drop="uncond"` 同時讓 `cwd-abs` 無條件，會被前綴檢查先抓走，那一條檢查的突變體因此存活，R62 抽測抓到）。"""
    pays = ("S", "P @@TOK@@", "E $ORACLE_INJECT", 'Q "$ORACLE_INJECT"')

    def runs(spaced, tp):
        if variant == "empty-base" and not spaced and not tp:
            return
        sp_abs, tp_cond = (tp, spaced) if variant == "swap" else (spaced, tp)         # swap：兩個條件接反
        if variant == "and":
            tp_cond = tp and spaced
        for pl in pays:
            e = "$ORACLE_INJECT" in pl
            unq = e and '"$ORACLE_INJECT"' not in pl
            tg = ["priv"] if not e else (["cwd", "cwd-abs", "priv"] if (sp_abs or drop == "uncond") and unq else ["cwd", "priv"])
            if e:
                tg.append("cwd-vis")
                if (sp_abs or drop == "uncond" or variant == "uncond-vis-abs") and unq:
                    tg.append("cwd-vis-abs")
            if (tp_cond or drop == "uncond" or variant == "uncond-tmpdir") and (e or "@@TOK@@" in pl):
                tg.append("priv-tmpdir")
            if drop == "front" and e:
                tg = ["cwd-vis"] + [x for x in tg if x != "cwd-vis"]     # 新目標插在最前面：R60 的目標序列不再是這個 payload 內的前綴（報出來的 payload 編號不變，R63 logic 更正）
            if variant == "mixed-miss" and spaced and not tp:
                tg = [x for x in tg if x != "cwd"]
            if variant == "extra-target":
                tg.append("cwd-mystery")
            for to in tg:
                if to != drop:
                    yield pl, to
    return pays, runs


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
            print("matcher ok（12 案＋tool_usable 6 案＋哨兵位置 manifest %d 案＋XR 探針 %d 案＋歷史 payload %d 案＋歷史重抽 %d 案＋逐目標形狀 %d 案＋逐目標履行 %d 案＋歷史重抽〔假 git〕%d 案＋抽常數 %d 案＋凍結表組裝 %d 案）" % (MANIFEST_CASE_COUNT, len(XRUN_CASES), len(HISTORY_CASES(())), len(REGEN_CASES), len(SHAPE_CASES), len(FULFIL_CASES()), len(REGEN_GIT_CASES), len(EV_CASES), len(REAL_HISTORY_CASES())))
        return 1 if probs else 0
    bad = 0
    for x in matcher_problems():
        print("✗ 比對器單元測試：" + x)
        bad += 1
    for x in sentinel_manifest_problems_real():
        print("✗ 歷史哨兵位置 manifest：" + x)
        bad += 1
    for x in xrun_probe_problems_real():
        print("✗ XR 探針（第 110 項）的結構：" + x)
        bad += 1
    for x in payload_history_problems_real():
        print("✗ 歷史 payload 凍結表：" + x)
        bad += 1
    for x in target_fulfillment_problems_real():
        print("✗ 逐目標履行：" + x)
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
