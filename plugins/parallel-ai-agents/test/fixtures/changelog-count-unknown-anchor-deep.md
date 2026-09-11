# fixture for test/lint-changelog-counts.sh --selftest

同上，但錨點後面還有路徑段（`../no-such-dir/x.md`）。第一條是**驗得過**的宣稱，用來打掉
`no claims found` 的 vacuity 守衛——否則整份 rc=1，量到的是守衛不是規則（R17 DA-B 的教訓）。
lint 必須**拒絕**：

- 測試 130 條（`grep -c "    def test_" ../pai-lenses/scripts/test_validate.py`）
- 測試 5 條（`grep -c "    def test_" ../no-such-dir/x.md`）
