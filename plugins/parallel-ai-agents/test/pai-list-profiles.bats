#!/usr/bin/env bats
#
# `bin/pai-list-profiles` 是 PROFILES 的**唯一真源查詢入口**，卻在 #33 出貨時零測試覆蓋
# （#33 verify R6 MEDIUM）。它有兩個脆弱點值得錨住：
#
#   1. 它靠 harness 裡一行**註解分隔線**（`// ── Orchestration ──`）切出 PROFILES 那段。
#      那行是註解 —— 沒有任何東西阻止未來有人改寫或移除它，而它一壞，抽取就壞。
#   2. `plugins/pai-lenses/scripts/validate.py` 的 profile 名稱閘門現在**依賴它**：
#      工具不見或輸出為空都會讓那道閘門報錯（R6 之前是靜默蒸發）。
#
# 所以這裡錨的不只是「它會動」，而是「它答得對」——特別是 `custom`：
# `references/builtin-lenses.csv` 是**由 lens 產生**的投影，`lenses: []` 的 profile
# 在裡面一列都沒有，拿投影問存在性對 `custom` 必定答錯。這正是這支工具存在的理由。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-list-profiles"
  HARNESS="${BATS_TEST_DIRNAME}/../workflows/ensemble-workflow.js"
}

@test "印出 PROFILES 的 key，一行一個" {
  run bash "$BIN"
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  # 每一行都必須是合法的 identifier（抽取壞掉時常見的症狀是吐出整段 JS）
  while IFS= read -r line; do
    [[ "$line" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]
  done <<< "$output"
}

@test "涵蓋 custom —— 那是 builtin-lenses.csv 投影答不出來的那一個" {
  run bash "$BIN"
  [ "$status" -eq 0 ]
  # **整行**精確比對，不是子字串。先前寫 `[[ "$output" == *"custom"* ]]`，
  # 把真源的 key 改成 `customXX` 一樣通過 —— 那是套套邏輯的覆蓋，等於沒測。
  printf '%s\n' "$output" | grep -qx "custom"
}

@test "與 harness 的 PROFILES key 集合逐一相符（不是子集、也不是超集）" {
  run bash "$BIN"
  [ "$status" -eq 0 ]
  from_tool=$(printf '%s\n' "$output" | sort)
  # 直接數 harness 裡 PROFILES 的頂層 key，作為獨立的第二來源
  from_src=$(awk '
    /^const PROFILES = \{/ {inp=1; next}
    inp && /^\}/ {exit}
    inp && /^  [a-zA-Z_][a-zA-Z0-9_]*: \{/ { gsub(/[ :{]/,""); print }
  ' "$HARNESS" | sort)
  [ -n "$from_src" ]
  [ "$from_tool" = "$from_src" ]
}

@test "PAI_HARNESS 指向不存在的檔案時 fail-loud，不回空清單" {
  # 這條同時證明下一條測試的注入點是有效的（否則那條會套套邏輯地通過）。
  PAI_HARNESS="$BATS_TEST_TMPDIR/does-not-exist.js" run bash "$BIN"
  [ "$status" -ne 0 ]
}

@test "分隔線被改掉時要壞得看得見，而不是安靜地少幾個 profile" {
  tmp="$BATS_TEST_TMPDIR/harness.js"
  # 移除 Orchestration 分隔線 —— 抽取靠它切段（那是一行**註解**，沒有東西阻止它被改掉）
  grep -v '── Orchestration ──' "$HARNESS" > "$tmp"
  run diff -q "$HARNESS" "$tmp"
  [ "$status" -ne 0 ]        # 確認 mutation 真的改到了東西

  PAI_HARNESS="$tmp" run bash "$BIN"
  # 可接受的結果只有兩種：報錯，或輸出仍與真源完全相符。
  # **不可接受**的是「rc=0 且輸出一個看起來正常但少了東西的清單」——
  # validate.py 對 rc != 0 與空輸出都會報錯（R6），唯獨那一種會安靜地放行。
  if [ "$status" -eq 0 ]; then
    from_tool=$(printf '%s\n' "$output" | sort)
    from_src=$(awk '
      /^const PROFILES = \{/ {inp=1; next}
      inp && /^\}/ {exit}
      inp && /^  [a-zA-Z_][a-zA-Z0-9_]*: \{/ { gsub(/[ :{]/,""); print }
    ' "$HARNESS" | sort)
    [ "$from_tool" = "$from_src" ]
  fi
}

# ── `--json` 與 `PAI_HARNESS=-`（#42）────────────────────────────────────────────
# 消費者是 pai-lenses/scripts/validate.py 的層 ① bump 閘門：它把 base 與 HEAD 兩版 harness 都交給
# 這支求值、比對輸出。所以這裡錨的是「值相同 ⇔ 輸出相同」的兩個方向，以及「看不見的型別不得靜默」。

mini() {  # $1 = PROFILES 的 JS 字面值；寫成一份最小 harness（分隔線之後的內容不該被求值）
  printf 'const PROFILES = %s\n// ── Orchestration ──\nthrow new Error("不該被求值")\n' "$1"
}

@test "--json：一行 JSON，頂層 key 與 keys 模式逐一相符" {
  run bash "$BIN" --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s\n' "$output" | wc -l)" -eq 1 ]
  from_json=$(printf '%s' "$output" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{for(const k of Object.keys(JSON.parse(s)))console.log(k)})' | sort)
  from_keys=$(bash "$BIN" | sort)
  [ -n "$from_keys" ]
  [ "$from_json" = "$from_keys" ]
}

@test "PAI_HARNESS=- 從 stdin 讀，結果與讀檔逐字相同" {
  a=$(bash "$BIN" --json)
  b=$(PAI_HARNESS=- bash "$BIN" --json < "$HARNESS")
  [ -n "$a" ]
  [ "$a" = "$b" ]
}

@test "--json 是標準形：物件 key 的書寫順序與字串串接不影響輸出" {
  mini "{ a: { title: 'x', lenses: [{ key: 'k', focus: 'ab' }] } }" > "$BATS_TEST_TMPDIR/h1.js"
  mini "{ a: { lenses: [{ focus: 'a' + 'b', key: 'k' }], title: 'x' } }" > "$BATS_TEST_TMPDIR/h2.js"
  a=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h1.js" bash "$BIN" --json)
  b=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h2.js" bash "$BIN" --json)
  [ -n "$a" ]
  [ "$a" = "$b" ]
}

@test "--json 對值的差異有鑑別力：focus 一個字、lens 順序各自改變輸出" {
  mini "{ a: { lenses: [{ key: 'k', focus: 'ab' }, { key: 'm', focus: 'c' }] } }" > "$BATS_TEST_TMPDIR/h1.js"
  mini "{ a: { lenses: [{ key: 'k', focus: 'aB' }, { key: 'm', focus: 'c' }] } }" > "$BATS_TEST_TMPDIR/h2.js"
  mini "{ a: { lenses: [{ key: 'm', focus: 'c' }, { key: 'k', focus: 'ab' }] } }" > "$BATS_TEST_TMPDIR/h3.js"
  a=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h1.js" bash "$BIN" --json)
  b=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h2.js" bash "$BIN" --json)
  c=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h3.js" bash "$BIN" --json)
  [ -n "$a" ]
  [ "$a" != "$b" ]
  [ "$a" != "$c" ]
}

@test "--json 遇到 JSON 表達不了的值（函式）fail-loud，不靜默丟掉" {
  mini "{ a: { title: 'x', pick: () => 1 } }" > "$BATS_TEST_TMPDIR/h.js"
  PAI_HARNESS="$BATS_TEST_TMPDIR/h.js" run bash "$BIN" --json
  [ "$status" -ne 0 ]
  # 同一份 harness 在 keys 模式仍然可用（函式值不影響「有哪些 profile」）——證明紅的原因是型別，不是 fixture 壞了
  PAI_HARNESS="$BATS_TEST_TMPDIR/h.js" run bash "$BIN"
  [ "$status" -eq 0 ]
  [ "$output" = "a" ]
}

@test "未知參數是用法錯（rc=2），不是安靜地走 keys 模式" {
  run bash "$BIN" --jsn
  [ "$status" -eq 2 ]
  run bash "$BIN" --json extra
  [ "$status" -eq 2 ]
}

# ── #42 verify R1：標準化的型別守衛與 own key `__proto__` ─────────────────────────────
# 下面四條先前沒有測試：把任一條守衛拿掉，上面六條照樣全綠（mutation 存活）。

@test "--json 保留名為 __proto__ 的 own key（兩側只差在它的值時輸出必須不同）" {
  # `['__proto__']` 是計算屬性名 —— 建立 own key，不改原型（與非計算的 `__proto__:` 不同）。
  # 先前輸出容器是 {}，`o['__proto__'] = …` 命中原型 setter，這個 key 連同值一起消失，兩份輸出逐字相同。
  mini "{ a: { ['__proto__']: { focus: 'before' }, lenses: [] } }" > "$BATS_TEST_TMPDIR/h1.js"
  mini "{ a: { ['__proto__']: { focus: 'after' }, lenses: [] } }" > "$BATS_TEST_TMPDIR/h2.js"
  a=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h1.js" bash "$BIN" --json)
  b=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h2.js" bash "$BIN" --json)
  [ "$a" = '{"a":{"__proto__":{"focus":"before"},"lenses":[]}}' ]
  [ "$a" != "$b" ]
}

@test "--json 遇到非有限數值（NaN／±Infinity）fail-loud——JSON.stringify 會把它們印成 null" {
  for v in NaN '1/0' '-1/0'; do
    mini "{ a: { lenses: [], n: $v } }" > "$BATS_TEST_TMPDIR/h.js"
    PAI_HARNESS="$BATS_TEST_TMPDIR/h.js" run bash "$BIN" --json
    [ "$status" -ne 0 ]
  done
  # 對照組：有限數值照常輸出——紅的原因是「非有限」，不是「有數字」
  mini "{ a: { lenses: [], n: 900 } }" > "$BATS_TEST_TMPDIR/h.js"
  PAI_HARNESS="$BATS_TEST_TMPDIR/h.js" run bash "$BIN" --json
  [ "$status" -eq 0 ]
  [ "$output" = '{"a":{"lenses":[],"n":900}}' ]
}

@test "--json 遇到 Map 或 class instance fail-loud——Object.keys 看不到它們的內容" {
  mini "{ a: { lenses: [], m: new Map([['k', 'v']]) } }" > "$BATS_TEST_TMPDIR/h1.js"
  mini "(() => { class C { constructor () { this.k = 'v' } }; return { a: { lenses: [], c: new C() } } })()" > "$BATS_TEST_TMPDIR/h2.js"
  for h in h1 h2; do
    PAI_HARNESS="$BATS_TEST_TMPDIR/$h.js" run bash "$BIN" --json
    [ "$status" -ne 0 ]
    PAI_HARNESS="$BATS_TEST_TMPDIR/$h.js" run bash "$BIN"     # keys 模式仍可用：紅的原因是型別
    [ "$status" -eq 0 ]
    [ "$output" = "a" ]
  done
}

@test "--json：值為 undefined 的屬性視同不存在；null-prototype 物件與 plain object 同形" {
  mini "{ a: { lenses: [] } }" > "$BATS_TEST_TMPDIR/h0.js"
  mini "{ a: { lenses: [], x: undefined } }" > "$BATS_TEST_TMPDIR/h1.js"
  mini "{ a: Object.assign(Object.create(null), { lenses: [] }) }" > "$BATS_TEST_TMPDIR/h2.js"
  ref=$(PAI_HARNESS="$BATS_TEST_TMPDIR/h0.js" bash "$BIN" --json)
  [ "$ref" = '{"a":{"lenses":[]}}' ]
  for h in h1 h2; do
    PAI_HARNESS="$BATS_TEST_TMPDIR/$h.js" run bash "$BIN" --json
    [ "$status" -eq 0 ]
    [ "$output" = "$ref" ]
  done
}
