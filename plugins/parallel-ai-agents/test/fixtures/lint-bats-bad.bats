#!/usr/bin/env bats
# test/lint-bats.sh 的自測 fixture：故意含一個裸 `!` 斷言，lint 必須拒絕它。
# 不是測試套件的一部分（`bats test/` 不遞迴進 fixtures/）。
@test "fixture: a bare ! assertion that bats' errexit would never fail" {
  ! false
}
