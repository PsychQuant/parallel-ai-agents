#!/usr/bin/env bats
# pai-build-diff 的 bats 測試 —— 把 ensemble-code-review diff 模式 3 輪人工 re-audit
# 抓到的 bug 全部固化成 regression。
#
# 跑法：bats test/pai-build-diff.bats   （需 brew install bats-core）
# 只用 bats-core 內建（run/$status/$output），不依賴 bats-assert/bats-support。
#
# --pr 的 happy-path 需要 live gh + 網路 + 真 PR，不在單元測試範圍；此處只測
# --pr 的「N 驗證在 gh 之前」（injection / 非正整數被擋）這個會出 bug 的部分。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-build-diff"
  REPO="${BATS_TEST_TMPDIR}/repo"
  git init -q "$REPO"
  git -C "$REPO" config user.email t@example.com
  git -C "$REPO" config user.name tester
  git -C "$REPO" config commit.gpgsign false
  printf 'v1\n' > "$REPO/a.txt"; git -C "$REPO" add a.txt; git -C "$REPO" commit -qm c1
  printf 'v2\n' > "$REPO/a.txt"; git -C "$REPO" add a.txt; git -C "$REPO" commit -qm c2
  # 此時 REPO：2 commits、工作樹乾淨
}

# 小工具：把 tracked 檔改成有 uncommitted 變更
dirty() { printf 'wip\n' >> "$REPO/a.txt"; }

# ── 退出碼契約 ──────────────────────────────────────────────

@test "--diff 乾淨工作樹 → exit 3（無變更可審，非錯誤）" {
  run "$BIN" -C "$REPO" --diff
  [ "$status" -eq 3 ]
  [[ "$output" == *"無變更可審"* ]]
}

@test "--diff 有 uncommitted 變更 → exit 0 且含該檔 diff" {
  dirty
  run "$BIN" -C "$REPO" --diff
  [ "$status" -eq 0 ]
  [[ "$output" == *"diff --git a/a.txt b/a.txt"* ]]
  [[ "$output" == *"+wip"* ]]
}

@test "非 git repo → exit 1" {
  mkdir "$BATS_TEST_TMPDIR/plain"
  run "$BIN" -C "$BATS_TEST_TMPDIR/plain" --diff
  [ "$status" -eq 1 ]
  [[ "$output" == *"不在 git repo 內"* ]]
}

# ── --diff 含 untracked 新檔 ────────────────────────────────

@test "--diff 含 untracked 一般新檔（不靜默漏審）" {
  printf 'brand new\n' > "$REPO/b.txt"
  run "$BIN" -C "$REPO" --diff
  [ "$status" -eq 0 ]
  [[ "$output" == *"b.txt"* ]]
  [[ "$output" == *"+brand new"* ]]
}

@test "untracked symlink → 只列路徑、不 follow（不洩漏目標內容）" {
  printf 'TOP_SECRET_TOKEN_42\n' > "$BATS_TEST_TMPDIR/secret"
  ln -s "$BATS_TEST_TMPDIR/secret" "$REPO/link"
  run "$BIN" -C "$REPO" --diff
  [ "$status" -eq 0 ]
  [[ "$output" == *"僅列路徑"* ]]
  # 關鍵：symlink 目標內容絕不可出現在 diff
  [[ "$output" != *"TOP_SECRET_TOKEN_42"* ]]
}

@test "untracked FIFO → 不卡死、正常結束" {
  mkfifo "$REPO/pipe"
  printf 'real change\n' > "$REPO/c.txt"   # 確保有東西、exit 0
  run "$BIN" -C "$REPO" --diff
  [ "$status" -eq 0 ]
  # 跑到這裡就代表沒卡在 FIFO read
}

@test "untracked 含換行檔名 → git C-quote、不偽造假 diff 行" {
  printf 'payload\n' > "$REPO/$(printf 'wn\nfake.txt')"
  run "$BIN" -C "$REPO" --diff
  [ "$status" -eq 0 ]
  # git 把換行 C-quote 成字面 \n（反斜線+n），不是真換行
  [[ "$output" == *'wn\nfake.txt'* ]]
}

# ── --base / --since（ref 模式） ────────────────────────────

@test "--base <ref> 合法 → exit 0" {
  run "$BIN" -C "$REPO" --base HEAD~1
  [ "$status" -eq 0 ]
  [[ "$output" == *"diff --git"* ]]
}

@test "--since <ref> 合法 → exit 0" {
  run "$BIN" -C "$REPO" --since HEAD~1
  [ "$status" -eq 0 ]
  [[ "$output" == *"diff --git"* ]]
}

@test "--base 缺 ref → exit 1" {
  run "$BIN" -C "$REPO" --base
  [ "$status" -eq 1 ]
  [[ "$output" == *"需要 <ref>"* ]]
}

@test "--base 壞 ref → exit 1（ref 非法）" {
  run "$BIN" -C "$REPO" --base no-such-ref-xyz
  [ "$status" -eq 1 ]
  [[ "$output" == *"ref 非法"* ]]
}

@test "--base injection 'x; rm -rf /' → 被擋（exit 1，永不進 shell）" {
  run "$BIN" -C "$REPO" --base 'x; rm -rf /'
  [ "$status" -eq 1 ]
  [[ "$output" == *"ref 非法"* ]]
}

@test "--base dashed-ref '--config' → 被擋（exit 1，不被當 git option）" {
  run "$BIN" -C "$REPO" --base --config
  [ "$status" -eq 1 ]
  [[ "$output" == *"ref 非法"* ]]
}

# ── --commits（N 模式 + empty-tree base + 驗證） ─────────────

@test "--commits 1 → exit 0" {
  run "$BIN" -C "$REPO" --commits 1
  [ "$status" -eq 0 ]
  [[ "$output" == *"diff --git"* ]]
}

@test "--commits N=TOT → empty-tree base（含 root 全部變更，不越界 fatal）" {
  run "$BIN" -C "$REPO" --commits 2   # repo 剛好 2 commits
  [ "$status" -eq 0 ]
  # empty tree 為 base → 連最初的 a.txt 內容都算新增
  [[ "$output" == *"new file"* ]] || [[ "$output" == *"--- /dev/null"* ]]
}

@test "--commits N>TOT → empty-tree base（不 clamp 成 HEAD~TOT fatal）" {
  run "$BIN" -C "$REPO" --commits 99
  [ "$status" -eq 0 ]
  [[ "$output" == *"diff --git"* ]]
}

@test "--commits 0 → exit 1（排除 0）" {
  run "$BIN" -C "$REPO" --commits 0
  [ "$status" -eq 1 ]
  [[ "$output" == *"需正整數"* ]]
}

@test "--commits 01 → exit 1（排除 leading-zero）" {
  run "$BIN" -C "$REPO" --commits 01
  [ "$status" -eq 1 ]
  [[ "$output" == *"需正整數"* ]]
}

@test "--commits 12345678901（11 位）→ exit 1（防算術溢位）" {
  run "$BIN" -C "$REPO" --commits 12345678901
  [ "$status" -eq 1 ]
  [[ "$output" == *"需正整數"* ]]
}

@test "--commits abc → exit 1（非數字）" {
  run "$BIN" -C "$REPO" --commits abc
  [ "$status" -eq 1 ]
  [[ "$output" == *"需正整數"* ]]
}

# ── --pr：只測「N 驗證在 gh 之前」（injection / 非正整數被擋） ─

@test "--pr injection → 被擋（驗證先於 gh）" {
  run "$BIN" -C "$REPO" --pr 'x; rm -rf /'
  [ "$status" -eq 1 ]
  [[ "$output" == *"需正整數"* ]]
}

@test "--pr 0 → exit 1" {
  run "$BIN" -C "$REPO" --pr 0
  [ "$status" -eq 1 ]
  [[ "$output" == *"需正整數"* ]]
}

# ── 用法 / 未知 mode ────────────────────────────────────────

@test "未知 mode --bogus → exit 1 且印『未知 MODE』（多位元組 regression）" {
  run "$BIN" -C "$REPO" --bogus
  [ "$status" -eq 1 ]
  [[ "$output" == *"未知 MODE"* ]]
  # regression：$MODE 緊貼全形『（』曾被 set -u 誤判 unbound variable
  [[ "$output" != *"unbound variable"* ]]
}

@test "無 mode → exit 1（缺 MODE）" {
  run "$BIN" -C "$REPO"
  [ "$status" -eq 1 ]
  [[ "$output" == *"缺 MODE"* ]]
}

@test "--help → exit 0 且含用法" {
  run "$BIN" --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"用法"* ]]
}
