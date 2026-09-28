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

R39（#33 verify R38 第 3、6、7 列）再加六項，量的是**神諭的歸類**本身。real lint 已經擋下那些形狀，神諭走不到
歸類分支，所以每一項都用 `oracle-probes/lint-*.sh` 假 lint 模擬「lint 放行」（第 3–8 項，見 CHECKS 的說明欄）：
  3. 多行群組裡的外流：差分語法壞掉時往上擴範圍，仍然判得出「管線自己印到 stdout」。
  4. 已知類別 G 被與外流無關的原因擋下：原因檢查必須判繞過。
  5. `>/dev/fd/2 2>&1 |` 宣告 S-2：機制差分不成立，必須判「不是 S-2」。
  6. xtrace 外流宣告 S-2：必須判 xtrace。
  7. 已觀察到外流、分類失敗、沒有類別宣告：必須判繞過（前一版判「量不到」、rc=0）。
  8. 已知類別 S-2 被與外流無關的原因擋下：同第 4 項。

R40 再加兩項（逾時之前的外流、ORACLE-COMPARABLE），R42（#33 verify R41）加五項，量的是 KD 條目與啟動檢查：
  11. KNOWN_DISAGREE 比對方向：登記成誤擋的條目不得吞掉同名 step 的繞過（R41 DA-5）。
  12. KNOWN_DISAGREE 比對內容雜湊：step 內容改了一個字元，條目就不再擔保它。
  13. 版本守衛：神諭用的 bash 不在 lint 檔頭 `# ORACLE-BASH-SUPPORTED:` 宣告的集合裡就具名退出。
  14. `GH_SAFE_EXPRS` 同步：神諭與 lint 各有一份，兩份不同就具名退出。
  15. 文法外類別的閘門：lint 多拒絕一種寫法（`echo`），神諭把那些 step 歸進文法外、檔頭卻沒有宣告 ⇒ rc=1。
第 14、15 項在暫存目錄裡產生突變版的神諭／lint（`mut` 欄，錨點必須在原檔裡恰好出現一次——錨點過期時這一項判失敗，
不會安靜地拿沒突變的檔案去跑）。

R42 WP7 加四項：pipefail 探針看到關閉（lint 放行時判繞過）、探針被腳本換掉（判量不到、不是一致）、跨 step 通道，
以及「唯一的 RULE 是 pipefail」不再整步跳過（接替退役的 must-fail 探針 `bypass-r37a-mustfail-strict-pipefail-hides-2to1`）。

R42 WP8 加六項：payload 的三種脈絡（註解、heredoc、算術）、運算式規則關掉的突變、取最嚴重的單元測試、S-2 機制差分的突變。

封閉列舉，只有這二十五項，不得依性質相似類推。

用法：test/oracle_selfcheck.py      rc=0：二十五項都照預期（二十三項失敗、一項判量不到、一項單元測試通過）；rc=1：至少一項沒有。
"""
import os
import pathlib
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
    ("逾時之前已經觀察到外流（R40，#33 verify R39 第 8 列）",
     {"ORACLE_LINT": str(PROBES / "lint-pass-all.sh")},
     [PROBES / "timeout-after-leak.yml"], 1, "逾時之前"),
    ("宣告 ORACLE-COMPARABLE 的檔有不可比的 step（R40，#33 verify R39 放行條件 12）",
     {}, [PROBES / "comparable-declared-but-sh.yml"], 1, "ORACLE-COMPARABLE"),
    ("已知類別 S-2 被與外流無關的原因擋下",
     {"ORACLE_LINT": str(PROBES / "lint-strict-blocks-set-E.sh")},
     [PROBES / "s2-blocked-for-unrelated-reason.yml"], 1, "原因與外流無關"),
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
    # 以下三項（R42 WP7）：pipefail 探針與跨 step 通道。lint 放行一切（`lint-pass-all.sh`）時，神諭自己要看得出來。
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
    ("取最嚴重：stdout 的外流勝過 stderr 的（單元測試）", {}, ["--selftest-severity"], 0, "select_most_severe ok"),
    ("S-2 機制差分：多出 baseline 沒有的外流行（突變）", {}, [HERE / "fixtures" / "ci-log-filter-oracle-r42-s2-flip.yml"], 1,
     "must-fail 探針沒有以宣告的理由失敗",
     {"oracle": ("                and not (ml[1] - base_ml[1]))", "                )")}),
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
        r = subprocess.run([sys.executable, str(oracle)] + [str(f) for f in files],
                           env=env, capture_output=True, text=True, errors="replace")
        return r.returncode, r.stdout + r.stderr


def main():
    bad = 0
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
