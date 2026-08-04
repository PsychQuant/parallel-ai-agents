#!/usr/bin/env bats
# pai-parse-lens-csv（ensemble-compose 的 --lens-file 解析器）的 bats 測試。
# 對抗案例：含逗號/引號/換行的 focus、needsSrt 變體、空欄跳過、BOM、CRLF、缺檔、缺欄。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-parse-lens-csv"
  CSV="${BATS_TEST_TMPDIR}/lens.csv"
}

# 小工具：把 stdout 丟給 python 算 JSON array 長度
jlen() { python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'; }

@test "基本：key,focus → JSON 含兩者" {
  printf 'key,focus\nperf,檢查複雜度\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [[ "$output" == *'"key": "perf"'* ]]
  [[ "$output" == *'"focus": "檢查複雜度"'* ]]
}

@test "focus 含逗號（quoted）→ 不被切爛" {
  printf 'key,focus\nperf,"檢查 hot path, N+1 query, 重算"\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [[ "$output" == *'檢查 hot path, N+1 query, 重算'* ]]
  [ "$(printf '%s' "$output" | jlen)" -eq 1 ]
}

@test "focus 含跳脫引號（\"\"）→ 解碼後為單一引號" {
  # CSV 的 "" → 一個 "；JSON 再把 " 跳脫成 \"。驗證 JSON 解碼後的真值（非原始 bytes）。
  printf 'key,focus\na,"他說 ""你好"" 然後走了"\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  python3 -c 'import json,sys; v=json.loads(sys.argv[1])[0]["focus"]; assert v=="他說 \"你好\" 然後走了", v' "$output"
}

@test "focus 含換行（quoted）→ 保留為單一欄" {
  printf 'key,focus\na,"第一行\n第二行"\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jlen)" -eq 1 ]
}

@test "needsSrt true/yes/1 → true；false/空 → 省略" {
  printf 'key,focus,needsSrt\na,fa,true\nb,fb,yes\nc,fc,1\nd,fd,false\ne,fe,\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  python3 -c '
import json,sys
d={x["key"]:x.get("needsSrt") for x in json.loads(sys.argv[1])}
assert d=={"a":True,"b":True,"c":True,"d":None,"e":None}, d
' "$output"
}

@test "override true/yes/1 → true；false/空/缺欄 → 省略（#29）" {
  printf 'key,focus,override\na,fa,true\nb,fb,YES\nc,fc,1\nd,fd,false\ne,fe,\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  python3 -c '
import json,sys
d={x["key"]:x.get("override") for x in json.loads(sys.argv[1])}
assert d=={"a":True,"b":True,"c":True,"d":None,"e":None}, d
' "$output"
}

@test "override 與 needsSrt 互不干擾（#29）" {
  printf 'key,focus,needsSrt,override\na,fa,true,false\nb,fb,false,true\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  python3 -c '
import json,sys
d={x["key"]:(x.get("needsSrt"),x.get("override")) for x in json.loads(sys.argv[1])}
assert d=={"a":(True,None),"b":(None,True)}, d
' "$output"
}

@test "無 override 欄的舊 CSV → 每列都不帶 override（向後相容，#29）" {
  printf 'key,focus\nperf,檢查複雜度\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [[ "$output" != *'"override"'* ]]
}

@test "空 key 或空 focus 的列被跳過" {
  printf 'key,focus\n,有focus沒key\n有key沒focus,\nok,好\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jlen)" -eq 1 ]
  [[ "$output" == *'"key": "ok"'* ]]
}

@test "header-only → 空 array" {
  printf 'key,focus,needsSrt\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$output" = "[]" ]
}

@test "REGRESSION: BOM CSV 不被整批丟棄（utf-8-sig）" {
  printf '\xef\xbb\xbfkey,focus\nperf,檢查\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jlen)" -eq 1 ]
  [[ "$output" == *'"key": "perf"'* ]]
}

@test "CRLF 行尾 → 正常解析（csv 模組處理）" {
  printf 'key,focus\r\nperf,檢查\r\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jlen)" -eq 1 ]
  [[ "$output" != *$'\r'* ]]
}

@test "缺 focus 欄 → 全列被跳過（[]）" {
  printf 'key,note\nperf,something\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$output" = "[]" ]
}

@test "多餘欄被忽略" {
  printf 'key,focus,extra,needsSrt\nperf,檢查,垃圾,false\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [[ "$output" != *'垃圾'* ]]
  [[ "$output" == *'"key": "perf"'* ]]
}

@test "重複 key 保留（去重交給 harness）" {
  printf 'key,focus\nperf,第一\nperf,第二\n' > "$CSV"
  run "$BIN" "$CSV"
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jlen)" -eq 2 ]
}

@test "檔案不存在 → exit 1" {
  run "$BIN" "${BATS_TEST_TMPDIR}/nope.csv"
  [ "$status" -eq 1 ]
  [[ "$output" == *"不存在"* ]]
}

@test "無參數 → exit 2（用法）" {
  run "$BIN"
  [ "$status" -eq 2 ]
  [[ "$output" == *"用法"* ]]
}
