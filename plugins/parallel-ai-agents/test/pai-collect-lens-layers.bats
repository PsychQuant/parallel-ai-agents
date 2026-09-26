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

# ── #56：semver 與 <profile> 參數對齊 validator ──────────────────────────────────────────
# 先前 `SEMVER = ^(\d+)\.(\d+)\.(\d+)` 是 prefix match、`_semver_key` 丟掉 prerelease：
# 不是 semver 的目錄名能勝出、prerelease 之間打平由 readdir 順序決定、回報的 version 是
# 由 key 重組的字串（可能不存在）。以下每條都在修法前實測為紅（見 CHANGELOG #56 段）。

# 便利：取 pack 層
pack_layer='
import json,sys
d=json.loads(sys.argv[1])
P=[l for l in d["layers"] if l["name"]=="pack"][0]
'

@test "#56 prefix match：非 semver 的 '9.9.9.bak' 不得勝過合法的 1.0.0" {
  mkpack psychquant 1.0.0
  printf 'key,focus\ngood,合法版本\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 9.9.9.bak
  printf 'key,focus\nevil,前綴比對撈到的\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 01.0.0
  printf 'key,focus\nlz,前導零\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert [x["key"] for x in d["lenses"]]==["good"], d["lenses"]
assert P["version"]=="1.0.0", P
assert P["status"]=="ok", P
' "$output"
}

@test "#56 只有非 semver 目錄（如 1.0.0.bak）→ unversioned，不是 ok" {
  mkpack psychquant 1.0.0.bak
  printf 'key,focus\nx,fx\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="unversioned", P
assert d["lenses"]==[], d["lenses"]
assert P["version"] is None, P
' "$output"
}

@test "#56 prerelease 依 semver §11 排序（rc.2 > rc.1；rc.10 > rc.9），回報實際目錄名" {
  mkpack psychquant 0.4.0-rc.1
  printf 'key,focus\nrc1,fx\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 0.4.0-rc.10
  printf 'key,focus\nrc10,fx\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 0.4.0-rc.9
  printf 'key,focus\nrc9,fx\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert [x["key"] for x in d["lenses"]]==["rc10"], d["lenses"]
assert P["version"]=="0.4.0-rc.10", P
' "$output"
}

@test "#56 正式版高於同 core 的 prerelease（0.3.0 > 0.3.0-rc1），不靠 readdir" {
  mkpack psychquant 0.3.0-rc1
  printf 'key,focus\nrc,fx\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 0.3.0
  printf 'key,focus\nrel,fx\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 0.3.0-zzz
  printf 'key,focus\nzzz,fx\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert [x["key"] for x in d["lenses"]]==["rel"], d["lenses"]
assert P["version"]=="0.3.0", P
' "$output"
}

@test "#56 回報的 version 是實際目錄名（build metadata 不被 key 重組吃掉）" {
  mkpack psychquant 1.2.3+build.7
  printf 'key,focus\nb,fb\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["version"]=="1.2.3+build.7", P
assert P["path"].endswith("/1.2.3+build.7/lenses/code.csv"), P
' "$output"
}

@test "#56 版本打平（只差 build metadata）→ ambiguous + 警告，不靠 readdir 挑一個" {
  mkpack psychquant 1.0.0+a
  printf 'key,focus\na,fa\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant 1.0.0+b
  printf 'key,focus\nb,fb\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ambiguous", P
assert P["version"] is None and P["path"] is None, P
assert d["lenses"]==[], d["lenses"]
w=" ".join(d["warnings"])
assert "1.0.0+a" in w and "1.0.0+b" in w, d["warnings"]
' "$output"
}

@test "#56 跨 marketplace 同版本 → ambiguous（不靠 glob 排序挑一個）" {
  mkpack alpha 2.0.0
  printf 'key,focus\na,fa\n' > "${PACK}/lenses/code.csv"
  mkpack beta 2.0.0
  printf 'key,focus\nb,fb\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ambiguous", P
assert d["lenses"]==[], d["lenses"]
assert any("alpha" in w and "beta" in w for w in d["warnings"]), d["warnings"]
' "$output"
}

@test "#56 打平只在最高版本才算：較低版本的打平不影響選出唯一最高者" {
  mkpack alpha 1.0.0
  printf 'key,focus\nold,fa\n' > "${PACK}/lenses/code.csv"
  mkpack beta 1.0.0
  printf 'key,focus\nold2,fb\n' > "${PACK}/lenses/code.csv"
  mkpack beta 1.1.0
  printf 'key,focus\nnew,fb\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ok", P
assert [x["key"] for x in d["lenses"]]==["new"], d["lenses"]
assert P["version"]=="1.1.0", P
' "$output"
}

@test "#56 semver 比較與 validate.py 的 version_tuple 逐對同序（兩份規格的機械對帳）" {
  VALIDATOR="${BATS_TEST_DIRNAME}/../../pai-lenses/scripts/validate.py"
  [ -f "$VALIDATOR" ] || skip "找不到 $VALIDATOR（pai-lenses 未併入本 repo）"
  run python3 - "$BIN" "$VALIDATOR" <<'PY'
import importlib.machinery, importlib.util, itertools, sys
sys.dont_write_bytecode = True        # 不在 bin/ 與 pai-lenses/scripts/ 留 __pycache__
def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec); loader.exec_module(m); return m
c = load("collector", sys.argv[1]); v = load("validator", sys.argv[2])
key = getattr(c, "version_key", None) or getattr(c, "_semver_key")
corpus = ["0.0.0", "1.0.0", "1.0.1", "1.1.0", "2.0.0", "1.10.0", "1.9.0",
          "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
          "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0-rc1", "1.0.0-rc10", "1.0.0-rc9", "1.0.0-0",
          "1.0.0-1", "1.0.0-01", "1.0.0-a-b", "1.0.0-x.7.z.92", "1.0.0+build", "1.0.0-rc.1+b.2",
          "01.0.0", "1.0", "1.0.0.bak", "1.0.0-", "1.0.0+", "1.0.0\n", " 1.0.0", "v1.0.0",
          "9.9.9_x", "1.0.0-rc..1", "1.0.0-é", "unknown", "abc1234", ""]
bad = []
for s in corpus:
    if (key(s) is None) != (v.version_tuple(s) is None):
        bad.append(("validity", s, key(s), v.version_tuple(s)))
ok = [s for s in corpus if v.version_tuple(s) is not None]
for a, b in itertools.product(ok, ok):
    ka, kb, va, vb = key(a), key(b), v.version_tuple(a), v.version_tuple(b)
    if ka is None or kb is None:
        continue
    if ((ka > kb) - (ka < kb)) != ((va > vb) - (va < vb)):
        bad.append(("order", a, b))
print(bad[:10]); sys.exit(1 if bad else 0)
PY
  echo "$output"
  [ "$status" -eq 0 ]
}

@test "#56 <profile> 路徑逃逸（../、絕對路徑、子目錄）→ exit 2，且不讀任何檔" {
  mkdir -p "$USERDIR" "${BATS_TEST_TMPDIR}/elsewhere"
  printf 'key,focus\nevil,逃出 user 目錄\n' > "${BATS_TEST_TMPDIR}/elsewhere/evil.csv"
  mkdir -p "${USERDIR}/sub"
  printf 'key,focus\nsub,子目錄\n' > "${USERDIR}/sub/x.csv"
  for p in '../elsewhere/evil' "${BATS_TEST_TMPDIR}/elsewhere/evil" 'sub/x' './code' '..' '.' \
           'code/../../elsewhere/evil' '..\evil'; do
    run "$BIN" "$p"
    echo "profile=$p status=$status output=$output"
    [ "$status" -eq 2 ]
    [ "${output#*\"lenses\"}" = "$output" ]      # 沒有吐出任何 JSON（逃逸路徑沒被讀）
  done
}

@test "#56 <profile> 字元集與 validator 端的 profile 名一致：[a-z0-9][a-z0-9-]*，其餘 exit 2" {
  for p in 'Code' '-code' 'code_x' '_code' 'code.x' 'cöde' 'code x' $'code\nx'; do
    run "$BIN" "$p"
    echo "profile=$p status=$status"
    [ "$status" -eq 2 ]
  done
  # 合法名照常（這組是 bin/pai-list-profiles 目前印出的全部 key + 含 `-` 的形狀）
  for p in minutes lecture code academic general custom my-profile 2x; do
    run "$BIN" "$p"
    [ "$status" -eq 0 ]
  done
}

@test "無參數 → exit 2（用法）" {
  run "$BIN"
  [ "$status" -eq 2 ]
}
