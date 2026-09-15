# fixture for test/lint-changelog-counts.sh --selftest（R17 logic L-5）

sibling 目錄 `../pai-lenses` 存在，但宣稱指向一個**不存在的子目錄**——R16 的 dirname 判準會把它當「佈局缺席」跳過
（永久豁免後門重開）。lint 必須拒絕：

- 測試 5 條（`grep -c "    def test_" ../pai-lenses/nosuchdir/x.py`）
