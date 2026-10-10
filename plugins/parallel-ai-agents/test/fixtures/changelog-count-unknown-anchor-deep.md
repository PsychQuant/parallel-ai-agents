# fixture for test/lint-changelog-counts.sh --selftest

同上，但錨點後面還有路徑段（`../no-such-dir/x.md`）。第一條是**驗得過**的宣稱，用來打掉
`no claims found` 的 vacuity 守衛——否則整份 rc=1，量到的是守衛不是規則（R17 DA-B 的教訓）。
lint 必須**拒絕**：

> **對照組**（R22 Codex #5）：下面第一條是**驗得過**的宣稱，用來打掉 `no claims found`
> 的 vacuity 守衛。它指向本檔自己的一行固定標記，**數量恆為 1**——先前用「測試 130 條」當對照，
> 而正式測試數已增長到 137，於是 fixture 失敗的原因變成數字不符**而不是**未知錨點被拒，
> selftest 只斷言非零就報 ok，等於把負向 fixture 變成假綠。

- 測試 5 條（`grep -c "    def test_" ../no-such-dir/x.md`）

# EXPECT-CONTROL: 這一行是上面那條對照宣稱的計數目標，請勿刪除
- 這行 1 條（`grep -c "^# EXPECT-CONTROL" test/fixtures/changelog-count-unknown-anchor-deep.md`）
