#!/usr/bin/env bats
# pai-parse-verdict（academic --auto-iterate 的 Codex verdict 解析器）的 bats 測試。
# 對抗案例：last-match、echoed instruction 範例、{N} placeholder、大小寫、無 tag、stdin/file。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-parse-verdict"
  OUT="${BATS_TEST_TMPDIR}/codex.txt"
}

@test "單一 verdict（stdin）→ 取出 TAG" {
  run bash -c "printf '...review...\n<verdict>CONVERGED</verdict>\n' | '$BIN'"
  [ "$status" -eq 0 ]
  [ "$output" = "CONVERGED" ]
}

@test "REGRESSION: echoed instruction 範例在前、真 verdict 在後 → 取最後一個" {
  # Codex 開頭 echo 了「輸出格式說明」（含 <verdict>CONVERGED</verdict> 範例），
  # 結尾才是真的 NEEDS_ITER_3。first-match 會誤抓 CONVERGED → 假收斂。
  printf '輸出格式：<verdict>CONVERGED</verdict> 或 <verdict>PERMANENT_CONVERGENCE</verdict>\n\n審閱...\n\n<verdict>NEEDS_ITER_3</verdict>\n' > "$OUT"
  run "$BIN" "$OUT"
  [ "$status" -eq 0 ]
  [ "$output" = "NEEDS_ITER_3" ]
}

@test "PERMANENT_CONVERGENCE → 取出（halt verdict）" {
  run bash -c "printf 'done.\n<verdict>PERMANENT_CONVERGENCE</verdict>\n' | '$BIN'"
  [ "$status" -eq 0 ]
  [ "$output" = "PERMANENT_CONVERGENCE" ]
}

@test "NEEDS_ITER_12（含數字）→ 取出" {
  run bash -c "printf '<verdict>NEEDS_ITER_12</verdict>\n' | '$BIN'"
  [ "$status" -eq 0 ]
  [ "$output" = "NEEDS_ITER_12" ]
}

@test "instruction 的 {N} placeholder 不被匹配（{ 不在 [A-Z_0-9]）" {
  # 只有含 {N} 的範例、沒有真 verdict → 查無 tag
  run bash -c "printf 'output <verdict>NEEDS_ITER_{N}</verdict> when unsure\n' | '$BIN'"
  [ "$status" -eq 1 ]
}

@test "小寫 verdict 不被匹配（嚴格大寫契約）→ exit 1" {
  run bash -c "printf '<verdict>converged</verdict>\n' | '$BIN'"
  [ "$status" -eq 1 ]
}

@test "查無 tag → exit 1（caller 視為未收斂、繼續迭代）" {
  run bash -c "printf 'basically converged but no tag\n' | '$BIN'"
  [ "$status" -eq 1 ]
  [[ "$output" == *"查無"* ]]
}

@test "空輸入 → exit 1" {
  run bash -c "printf '' | '$BIN'"
  [ "$status" -eq 1 ]
}

@test "兩個真 verdict → 最後一個勝" {
  printf '<verdict>NEEDS_ITER_1</verdict>\n中段\n<verdict>CONVERGED</verdict>\n' > "$OUT"
  run "$BIN" "$OUT"
  [ "$status" -eq 0 ]
  [ "$output" = "CONVERGED" ]
}

@test "file 參數（非 stdin）→ 讀檔" {
  printf '<verdict>CONVERGED</verdict>\n' > "$OUT"
  run "$BIN" "$OUT"
  [ "$status" -eq 0 ]
  [ "$output" = "CONVERGED" ]
}

@test "tag 同行夾雜其他文字 → 仍取出" {
  run bash -c "printf 'verdict: <verdict>CONVERGED</verdict> (done)\n' | '$BIN'"
  [ "$status" -eq 0 ]
  [ "$output" = "CONVERGED" ]
}
