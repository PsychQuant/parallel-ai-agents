#!/usr/bin/env bats
# pai-collect-lens-layers（#29 三層 lens 疊加的層 ②③ 蒐集器）的 bats 測試。
#
# 層 ① built-in 不在這裡 —— 它活在 harness 的 PROFILES 裡，這支只負責
# lens pack（層 ②）與 user（層 ③）。所以本檔不斷言任何 builtin 層。
#
# 鐵律（兩條，界線明確 —— #33 verify R9 M23 修正）：
#
# 1. **絕不讀開發機的 `~/.claude/pai-lenses/`。** 那是使用者的私人層，讀它會讓測試結果
#    取決於誰在跑，且無法在 CI 重現。這條沒有例外。
# 2. **單元測試全部用 BATS_TEST_TMPDIR 自建的假 cache 與假 pack。**
#
# **一個明確的例外**：檔案末的「整合錨點（#33）」刻意把**本 repo 的真實**
# `plugins/pai-lenses/` 複製進假 cache —— 它要抓的正是「pack 的實際內容壞掉 / 併回後
# collector 定位不到」，用假 pack 就驗不到那件事。代價是主 plugin 的 bats 套件從此
# 依賴 `plugins/pai-lenses/lenses/*.csv` 的內容，純資料 PR 會影響它；這是刻意接受的耦合。
#
# 先前這裡寫的是「絕不讀真實 lens pack」，而同一個 commit 新增的整合錨點就在讀 ——
# 一句已經為假的不變式比沒有更糟：下一個人會據以判斷「這裡不能碰真實 pack」而繞路。

setup() {
  BIN="${BATS_TEST_DIRNAME}/../bin/pai-collect-lens-layers"
  CACHE="${BATS_TEST_TMPDIR}/cache"
  USERDIR="${BATS_TEST_TMPDIR}/userlens"
  export PAI_LENS_CACHE_ROOT="$CACHE"
  export PAI_USER_LENS_DIR="$USERDIR"
}

# 造一個假的 lens pack cache 目錄：mkpack <marketplace> <version>
mkpack() {
  PACK="${CACHE}/$1/pai-lenses/$2"
  mkdir -p "${PACK}/lenses"
}

# 便利斷言：用 python 讀 stdout JSON
jq_py() { python3 -c "$1" "$2"; }

@test "兩層都有 → pack 在前、user 在後，各自標 _layer" {
  mkpack psychquant 1.2.0
  printf 'key,focus\npack-lens,來自 pack\n' > "${PACK}/lenses/code.csv"
  mkdir -p "$USERDIR"
  printf 'key,focus\nuser-lens,來自 user\n' > "${USERDIR}/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
ls=[(x["key"],x["_layer"]) for x in d["lenses"]]
assert ls==[("pack-lens","pack"),("user-lens","user")], ls
' "$output"
}

@test "兩層皆缺席 → 靜默（exit 0、lenses 空、warnings 空）" {
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
assert d["lenses"]==[], d["lenses"]
assert d["warnings"]==[], d["warnings"]
assert {l["name"]:l["status"] for l in d["layers"]}=={"pack":"absent","user":"absent"}, d["layers"]
' "$output"
}

@test "pack 有、user 缺席 → 只回 pack，不警告" {
  mkpack psychquant 0.1.0
  printf 'key,focus\na,fa\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
assert [x["key"] for x in d["lenses"]]==["a"], d["lenses"]
assert d["warnings"]==[], d["warnings"]
' "$output"
}

@test "pack 裝了但無 semver 目錄（plugin.json 缺 version）→ 警告，不當成沒裝" {
  mkdir -p "${CACHE}/psychquant/pai-lenses/unknown/lenses"
  printf 'key,focus\na,fa\n' > "${CACHE}/psychquant/pai-lenses/unknown/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
st={l["name"]:l["status"] for l in d["layers"]}
assert st["pack"]=="unversioned", st
assert any("version" in w for w in d["warnings"]), d["warnings"]
' "$output"
}

@test "pack CSV 存在但解析出 0 條（header 打錯）→ 警告，不靜默吞掉" {
  mkpack psychquant 1.0.0
  printf 'keys,focuses\na,fa\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
st={l["name"]:l["status"] for l in d["layers"]}
assert st["pack"]=="empty", st
assert d["warnings"], "header 打錯卻沒有任何警告"
' "$output"
}

@test "一層壞掉不影響另一層（user 照常出貨）" {
  mkpack psychquant 1.0.0
  printf 'keys,focuses\na,fa\n' > "${PACK}/lenses/code.csv"
  mkdir -p "$USERDIR"
  printf 'key,focus\nu,fu\n' > "${USERDIR}/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
assert [x["key"] for x in d["lenses"]]==["u"], d["lenses"]
' "$output"
}

@test "多版本並存 → 取最高 semver（10 > 9，非字典序）" {
  mkpack psychquant 1.9.0
  printf 'key,focus\nold,舊版\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 1.10.0
  printf 'key,focus\nnew,新版\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
assert [x["key"] for x in d["lenses"]]==["new"], d["lenses"]
v=[l["version"] for l in d["layers"] if l["name"]=="pack"][0]
assert v=="1.10.0", v
' "$output"
}

@test "profile 決定檔名 —— 要 academic 不會拿到 code.csv" {
  mkpack psychquant 1.0.0
  printf 'key,focus\nc,程式\n' > "${PACK}/lenses/code.csv"
  run "$BIN" academic
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
assert d["lenses"]==[], d["lenses"]
' "$output"
}

@test "override 欄穿透到輸出（harness 才是判定者，這裡只搬運）" {
  mkpack psychquant 1.0.0
  printf 'key,focus,override\nsecurity,取代內建的,true\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
assert d["lenses"][0].get("override") is True, d["lenses"]
' "$output"
}

@test "整合錨點（#33）：併回後的真實 pai-lenses 內容，在安裝後的 cache 佈局仍被解析" {
  # issue #33 要求 4 —— source 從 github 改成相對路徑後，cache 佈局會不會變、
  # semver glob 還找不找得到 pack。這條用**真實的 plugins/pai-lenses 內容**（不是 fixture）
  # 複製進模擬 cache，所以 pack 的檔名、版本、CSV 任何一項壞掉都會在這裡紅。
  #
  # 佈局取自同 marketplace 的實證：parallel-ai-agents 自己就是相對路徑 source，
  # 其 cache 是 ~/.claude/plugins/cache/parallel-ai-agents/parallel-ai-agents/<semver>/。
  PACK_SRC="${BATS_TEST_DIRNAME}/../../pai-lenses"
  [ -d "$PACK_SRC" ] || skip "找不到 $PACK_SRC（pai-lenses 未併入本 repo）"
  VER=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" \
        "${PACK_SRC}/.claude-plugin/plugin.json")
  DEST="${CACHE}/parallel-ai-agents/pai-lenses/${VER}"
  mkdir -p "$DEST"
  cp -R "${PACK_SRC}/." "$DEST/"

  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py '
import json,sys
d=json.loads(sys.argv[1])
pack=[l for l in d["layers"] if l["name"]=="pack"][0]
assert pack["status"]=="ok", pack
assert d["lenses"], "真實 pack 的 code.csv 一條 lens 都沒收到"
assert all(x["_layer"]=="pack" for x in d["lenses"]), d["lenses"]
assert d["warnings"]==[], d["warnings"]
' "$output"
  # 版本要如實回報 —— provenance 行靠它，報錯版本等於量測條件記錯
  jq_py "
import json,sys
d=json.loads(sys.argv[1])
v=[l for l in d['layers'] if l['name']=='pack'][0]['version']
assert v=='${VER}', (v, '${VER}')
" "$output"
}

@test "無參數 → exit 2（用法）" {
  run "$BIN"
  [ "$status" -eq 2 ]
}
