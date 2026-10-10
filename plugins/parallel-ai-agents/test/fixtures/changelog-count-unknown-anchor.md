# fixture for test/lint-changelog-counts.sh --selftest

`../` 開頭、但錨點（第一個非 `..` 段）**不在已知佈局錨點的封閉列舉裡**。R13–R17 的規則是
「錨點不存在就跳過」，於是打錯字的路徑等於永久豁免——R18 用 `../pai-lensez` 與
`../bogus/../real/file` 兩種構造各穿過一次（同一個後門的第三、四次）。現在只有這個 repo
真實存在的兩個錨點可以觸發跳過，其餘一律照常驗證。lint 必須**拒絕**：

> **對照組**（R22 Codex #5）：下面第一條是**驗得過**的宣稱，用來打掉 `no claims found`
> 的 vacuity 守衛。它指向本檔自己的一行固定標記，**數量恆為 1**——先前用「測試 130 條」當對照，
> 而正式測試數已增長到 137，於是 fixture 失敗的原因變成數字不符**而不是**未知錨點被拒，
> selftest 只斷言非零就報 ok，等於把負向 fixture 變成假綠。

- 測試 5 條（`grep -c "    def test_" ../no-such-pack/scripts/test_validate.py`）

# EXPECT-CONTROL: 這一行是上面那條對照宣稱的計數目標，請勿刪除
- 這行 1 條（`grep -c "^# EXPECT-CONTROL" test/fixtures/changelog-count-unknown-anchor.md`）
