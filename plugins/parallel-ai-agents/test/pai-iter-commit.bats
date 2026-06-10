#!/usr/bin/env bats
# pai-iter-commit（academic --auto-iterate 的 per-round checkpoint commit）的 bats 測試。
# 對抗案例：標準訊息、空 commit 防護、round 驗證、非 repo。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-iter-commit"
  REPO="${BATS_TEST_TMPDIR}/repo"
  git init -q "$REPO"
  git -C "$REPO" config user.email t@example.com
  git -C "$REPO" config user.name tester
  git -C "$REPO" config commit.gpgsign false
  printf 'base\n' > "$REPO/f.txt"; git -C "$REPO" add f.txt; git -C "$REPO" commit -qm base
}

commits() { git -C "$REPO" rev-list --count HEAD; }

@test "有變更 → commit，訊息為 iter-N: ..." {
  printf 'fix\n' >> "$REPO/f.txt"
  run "$BIN" -C "$REPO" 1
  [ "$status" -eq 0 ]
  [ "$(commits)" -eq 2 ]
  [ "$(git -C "$REPO" log -1 --pretty=%s)" = "iter-1: apply HIGH fixes from ensemble round 1" ]
}

@test "untracked 新檔 → 被 add -A 納入 commit" {
  printf 'new\n' > "$REPO/g.txt"
  run "$BIN" -C "$REPO" 2
  [ "$status" -eq 0 ]
  [ "$(commits)" -eq 2 ]
  git -C "$REPO" ls-files --error-unmatch g.txt
}

@test "空輪（無變更）→ 跳過、不留空 commit、exit 0" {
  run "$BIN" -C "$REPO" 3
  [ "$status" -eq 0 ]
  [[ "$output" == *"無變更，跳過"* ]]
  [ "$(commits)" -eq 1 ]
}

@test "round 0 → exit 2" {
  printf 'x\n' >> "$REPO/f.txt"
  run "$BIN" -C "$REPO" 0
  [ "$status" -eq 2 ]
  [[ "$output" == *"需正整數"* ]]
}

@test "round 非數字 → exit 2" {
  run "$BIN" -C "$REPO" abc
  [ "$status" -eq 2 ]
}

@test "round 11 位數 → exit 2（位數上限）" {
  run "$BIN" -C "$REPO" 12345678901
  [ "$status" -eq 2 ]
}

@test "缺 round → exit 2" {
  run "$BIN" -C "$REPO"
  [ "$status" -eq 2 ]
}

@test "非 git repo → exit 1" {
  mkdir "$BATS_TEST_TMPDIR/plain"
  run "$BIN" -C "$BATS_TEST_TMPDIR/plain" 1
  [ "$status" -eq 1 ]
  [[ "$output" == *"不在 git repo"* ]]
}

@test "-C 缺目錄參數 → exit 2" {
  run "$BIN" -C
  [ "$status" -eq 2 ]
}
