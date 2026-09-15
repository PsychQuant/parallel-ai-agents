# fixture for test/lint-changelog-counts.sh --selftest

`../` 開頭、但第一個非 `..` 段就是路徑最後一段（`../nothing-at-all.md`）——它的容身處只有 `..`，
在任何佈局都存在，所以**不得**以「佈局缺席」跳過。lint 必須**拒絕**（R17 logic L-5：R16 的 dirname
判準與它的第一版修法都讓這個形狀拿到永久豁免）：

- 測試 5 條（`grep -c "    def test_" ../nothing-at-all.md`）
