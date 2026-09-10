# fixture for test/lint-changelog-counts.sh --selftest

一條指向 sibling plugin（`../`）而該檔不在這個 checkout 的宣稱——lint 必須**跳過並註明**，不得判成
「數字錯」（plugin cache 副本沒有 sibling pack；#33 verify R12 #4 那種假診斷）：

- 測試 5 條（`grep -c "    def test_" ../no-such-pack/scripts/test_validate.py`）
