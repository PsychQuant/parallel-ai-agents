# fixture for test/lint-changelog-counts.sh --selftest

`../` 開頭、但錨點（第一個非 `..` 段）**不在已知佈局錨點的封閉列舉裡**。R13–R17 的規則是
「錨點不存在就跳過」，於是打錯字的路徑等於永久豁免——R18 用 `../pai-lensez` 與
`../bogus/../real/file` 兩種構造各穿過一次（同一個後門的第三、四次）。現在只有這個 repo
真實存在的兩個錨點可以觸發跳過，其餘一律照常驗證。lint 必須**拒絕**：

- 測試 130 條（`grep -c "    def test_" ../pai-lenses/scripts/test_validate.py`）
- 測試 5 條（`grep -c "    def test_" ../no-such-pack/scripts/test_validate.py`）
