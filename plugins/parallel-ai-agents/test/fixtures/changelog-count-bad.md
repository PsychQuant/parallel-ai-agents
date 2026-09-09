# fixture for test/lint-changelog-counts.sh --selftest

一行故意寫錯的宣稱——lint 必須拒絕它（實際 case 數不可能是 0）：

- 新增 `test/codex-call-detach.bats`（macOS job，**0 個 case**（`grep -c "^@test" test/codex-call-detach.bats`））
