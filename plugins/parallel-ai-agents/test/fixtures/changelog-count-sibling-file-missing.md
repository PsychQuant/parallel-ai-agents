# fixture for test/lint-changelog-counts.sh --selftest

sibling 目錄 `../pai-lenses` 存在、但宣稱指向的檔案不存在——lint 必須**拒絕**（R14 的「`../` 缺席就跳過」在
monorepo 裡是永久豁免後門，R14 S5 / R15）：

- 測試 5 條（`grep -c "    def test_" ../pai-lenses/scripts/no-such-file.py`）
