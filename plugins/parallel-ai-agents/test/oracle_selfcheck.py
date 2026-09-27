#!/usr/bin/env python3
"""神諭的反向探針：只有神諭**失敗**時才成立的檢查（#33 verify R37）。

fixture 集裡的 must-fail 探針（`# ORACLE-MUST-FAIL:`）驗的是「神諭對某張 fixture 以宣告的理由失敗」。
有兩件事它驗不到——要驗它們，未突變的神諭在 fixture 集上就得是紅的：
  1. **must-fail 探針的理由比對本身**：宣告一個永遠不會出現的理由，未突變的神諭必須判「探針沒有以宣告的理由
     失敗」、rc=1（`oracle-probes/mustfail-wrong-reason.yml`）。
  2. **oracle↔lint 的 RULE 字面耦合檢查**：`ORACLE_LINT` 指到不含那兩句訊息的 lint，未突變的神諭必須在讀
     fixture 之前具名退出（`oracle-probes/lint-without-rule-messages.sh`）。
這支把兩者寫成「期待失敗」：每一項斷言神諭的 rc 與輸出裡的一句話，全部成立 rc=0。`mutation_check.py` 的
`oracle-inverted` 守備單位跑它，所以拿掉那兩道檢查的突變會讓這裡紅——R37 的神諭工作包原本把第 1 項（must-fail 理由比對）列為
「harness 結構上測不到」的預期存活；第 2 項（RULE 字面耦合檢查）是合併時才加的。「未突變＝綠」的前提對兩項都成立，
把期待寫成失敗就滿足了它。

封閉列舉，只有這兩項，不得依性質相似類推。

用法：test/oracle_selfcheck.py      rc=0：兩項都照預期失敗；rc=1：至少一項沒有。
"""
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ORACLE = HERE / "oracle.py"
PROBES = HERE / "oracle-probes"

# (說明, 額外環境變數, 神諭的檔案參數, 期待的 rc, 輸出裡必須出現的字串)
CHECKS = [
    ("must-fail 探針的理由比對",
     {}, [PROBES / "mustfail-wrong-reason.yml"], 1, "must-fail 探針沒有以宣告的理由失敗"),
    ("oracle↔lint 的 RULE 字面耦合檢查",
     {"ORACLE_LINT": str(PROBES / "lint-without-rule-messages.sh")},
     [HERE / "fixtures" / "ci-log-filter-good.yml"], 1, "用來認 RULE 的字面"),
    # 以下四項（R39，#33 verify R38 第 3、6、7 列）量的是**神諭的歸類**：real lint 已經擋下這些形狀，神諭走不到歸類分支，
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
]


def main():
    bad = 0
    for what, extra, files, want_rc, want_text in CHECKS:
        env = dict(os.environ, **extra)
        r = subprocess.run([sys.executable, str(ORACLE)] + [str(f) for f in files],
                           env=env, capture_output=True, text=True, errors="replace")
        out = r.stdout + r.stderr
        ok = r.returncode == want_rc and want_text in out
        print("%s %s：rc=%d（期待 %d）、「%s」%s" % ("✓" if ok else "✗", what, r.returncode, want_rc, want_text,
                                             "出現" if want_text in out else "沒有出現"))
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
