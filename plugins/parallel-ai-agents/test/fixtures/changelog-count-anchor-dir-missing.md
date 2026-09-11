# fixture for test/lint-changelog-counts.sh --selftest

錨點目錄（第一個非 `..` 段）不在這個 checkout —— 佈局真的缺席，這條宣稱無法驗證，必須跳過。
第一條是**驗得過**的宣稱，用來打掉 `no claims found` 的 vacuity 守衛（否則整份 rc=1，
量到的是守衛不是規則——R17 DA-B 的實驗設計教訓）。lint 必須**接受**（rc=0）：

- 這行 2 條（`grep -c "^- " test/fixtures/changelog-count-anchor-dir-missing.md`）
- 測試 5 條（`grep -c "    def test_" ../no-such-dir/x.md`）
