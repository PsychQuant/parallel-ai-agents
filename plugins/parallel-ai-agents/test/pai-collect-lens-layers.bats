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
# 由 key 重組的字串（可能不存在）。哪幾條在修法前紅、哪幾條依 readdir 順序而定、哪幾條是護欄，
# 逐條記在 CHANGELOG #56 段（對 `cb0c7ba^` 的 collector 實跑）。

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

@test "#56 正式版高於同 core 的 prerelease（0.3.0 > 0.3.0-rc1、0.3.0-zzz）" {
  # 修法前三者 key 全是 (0,3,0)、`max()` 取 iterdir 的第一個：readdir 已排序的檔案系統上
  # 正式版恰好排第一（'0.3.0' 是另兩者的前綴），所以這條在修法前**不一定紅** —— 依 readdir 順序而定。
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
assert "/plugin uninstall pai-lenses@psychquant" in w and "scope" in w, w   # 同 marketplace 的補救方法
' "$output"
}

@test "#56 跨 marketplace 同版本 → ambiguous（先前固定取 marketplace 名字母序第一個）" {
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
w=" ".join(d["warnings"])
# 補救方法要說得出口：兩個 marketplace 各自的 uninstall 指令
assert "/plugin uninstall pai-lenses@alpha" in w and "/plugin uninstall pai-lenses@beta" in w, w
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

@test "#56 semver 與 validate.py 逐對同序：regex 逐字、函式本體 AST、corpus ＋ 定種子 fuzz（兩份規格的機械對帳）" {
  VALIDATOR="${BATS_TEST_DIRNAME}/../../pai-lenses/scripts/validate.py"
  MKT="${BATS_TEST_DIRNAME}/../../../.claude-plugin/marketplace.json"
  if [ ! -f "$VALIDATOR" ]; then
    # 只有「collector 被單獨安裝」（plugin cache 副本，沒有 sibling pack）才可以 skip；
    # 若所在 repo 的 marketplace.json 把 pai-lenses 列在本 repo 內，validate.py 缺席就是壞了，不是不適用。
    if [ -f "$MKT" ] && python3 -c '
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
sys.exit(0 if any(p.get("name")=="pai-lenses" and str(p.get("source","")).startswith("./") for p in d.get("plugins",[])) else 1)
' "$MKT"; then
      echo "marketplace.json 列了本 repo 內的 pai-lenses，卻找不到 $VALIDATOR —— 對帳測試不得 skip"
      return 1
    fi
    skip "找不到 $VALIDATOR 且不在列出 pai-lenses 的 monorepo 內（collector 單獨安裝）"
  fi
  run python3 - "$BIN" "$VALIDATOR" <<'PY'
import ast, importlib.machinery, importlib.util, itertools, random, sys
sys.dont_write_bytecode = True        # 不在 bin/ 與 pai-lenses/scripts/ 留 __pycache__
def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec); loader.exec_module(m); return m
c = load("collector", sys.argv[1]); v = load("validator", sys.argv[2])
key, tup = c.version_key, v.version_tuple
bad = {}
def fail(kind, item):
    bad.setdefault(kind, []).append(item)

# (a) regex 逐字：pattern 與 flags 都要相同（re.ASCII 之類只加在一邊，行為上可能測不出來，這裡測得出來）
if c.SEMVER.pattern != v.SEMVER.pattern:
    fail("regex", ("pattern", c.SEMVER.pattern, v.SEMVER.pattern))
if c.SEMVER.flags != v.SEMVER.flags:
    fail("regex", ("flags", c.SEMVER.flags, v.SEMVER.flags))

# (b) 函式本體：兩邊的 AST（去掉 docstring、參數名正規化）必須相同。註解不在 AST 裡，可以各寫各的。
def body(path, fname):
    tree = ast.parse(open(path, encoding="utf-8").read())
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fname]
    assert len(fn) == 1, (path, fname)
    fn = fn[0]
    params = [a.arg for a in fn.args.args]
    class N(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id in params:
                n.id = "_p%d" % params.index(n.id)
            return n
        def visit_arg(self, n):
            n.arg = "_p%d" % params.index(n.arg) if n.arg in params else n.arg
            return n
    stmts = fn.body
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) \
            and isinstance(stmts[0].value.value, str):
        stmts = stmts[1:]
    fn.body = stmts; fn.name = "_f"; fn.decorator_list = []
    return ast.dump(N().visit(fn))
if body(sys.argv[1], "version_key") != body(sys.argv[2], "version_tuple"):
    fail("ast", "version_key 與 version_tuple 的函式本體不同")

# (c) 行為：固定 corpus（含 verify 指名的每種一邊式變異的觸發形狀）＋ 定種子的隨機字串
corpus = ["0.0.0", "1.0.0", "1.0.1", "1.1.0", "2.0.0", "1.10.0", "1.9.0",
          "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
          "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0-rc1", "1.0.0-rc10", "1.0.0-rc9", "1.0.0-0",
          "1.0.0-1", "1.0.0-01", "1.0.0-a-b", "1.0.0-x.7.z.92", "1.0.0+build", "1.0.0-rc.1+b.2",
          "01.0.0", "1.0", "1.0.0.bak", "1.0.0-", "1.0.0+", "1.0.0\n", " 1.0.0", "v1.0.0",
          "9.9.9_x", "1.0.0-rc..1", "1.0.0-é", "unknown", "abc1234", "",
          # 一邊式變異的觸發形狀（#56 verify R1）
          "1.0.0+a_b", "1.0.0+_", "1.0.0-a_b",                         # build／prerelease 放行 `_`
          "1.0.0-a.b.c", "1.0.0-a.b.d", "1.0.0-a.b", "1.0.0-a.b.c.d",   # 只比前 N 個 identifier
          "1.01.0", "1.0.01", "1.00.0", "0.0.00",                      # minor／patch 前導零
          "9９.0.0", "1.٣.0", "1.0.0-rc.９", "1.0.0-٣", "1.0.0+٣",        # Unicode 數字（`\d` vs `[0-9]`）
          "1.0.0-A", "1.0.0-a", "1.0.0-Alpha", "1.0.0-alpha.B", "1.0.0-alpha.b",   # 大小寫（不得 lower()）
          "1.0.0--", "1.0.0--a", "1.0.0-a.-b", "1.0.0-a.-", "1.0.0-0-", "1.0.0+-",  # 以 `-` 開頭的 identifier
          "4.9.8-9.9.9", "9.9.9-not-a-real-version-just-a-prefix"]
rng = random.Random(56)
DIGITS = "0123456789"
def num():
    r = rng.random()
    if r < 0.04: return "0" + rng.choice(DIGITS)             # 前導零
    if r < 0.06: return rng.choice(["９", "٣", "1٣", "0９"])   # 非 ASCII 數字
    return str(rng.choice([0, 0, 1, 1, 2, 3, 9, 10, 11]))
ID_ALPH = "019azAZ-"                                          # 小字母表 → 前綴相同、後段才分出高下的對很多
def ident():
    if rng.random() < 0.45: return num()
    x = [rng.choice(ID_ALPH) for _ in range(0 if rng.random() < 0.02 else rng.randint(1, 3))]
    if x and rng.random() < 0.04: x[rng.randrange(len(x))] = rng.choice("_９é")
    return "".join(x)
def gen():
    s = ".".join(num() for _ in range(3 if rng.random() < 0.95 else rng.choice([2, 4])))
    if rng.random() < 0.7: s += "-" + ".".join(ident() for _ in range(rng.randint(1, 4)))
    if rng.random() < 0.3: s += "+" + ".".join(ident() for _ in range(rng.randint(1, 3)))
    if rng.random() < 0.03: s = rng.choice([" ", "v", ""]) + s + rng.choice(["\n", "", ".bak", " "])
    return s
fuzz = [gen() for _ in range(20000)]
strings = list(dict.fromkeys(corpus + fuzz))
for s in strings:
    if (key(s) is None) != (tup(s) is None):
        fail("validity", (s, key(s), tup(s)))
ok = [s for s in strings if tup(s) is not None and key(s) is not None]
def sign(a, b): return (a > b) - (a < b)
pairs = list(itertools.product([s for s in corpus if s in ok], repeat=2))
ok.sort(key=tup)
pairs += list(zip(ok, ok[1:]))                                  # 依 validator 排序後的相鄰對（最細的差異）
pairs += [(rng.choice(ok), rng.choice(ok)) for _ in range(100000)]
for a, b in pairs:
    if sign(key(a), key(b)) != sign(tup(a), tup(b)):
        fail("order", (a, b))
n_valid = len(ok)
print("strings=%d valid=%d pairs=%d" % (len(strings), n_valid, len(pairs)))
for k in bad:
    print("DRIFT[%s] %d: %r" % (k, len(bad[k]), bad[k][:5]))
# 護欄：fuzz 要真的產生夠多合法字串，否則「逐對同序」是空轉
if n_valid < 8000:
    print("fuzz 產生的合法 semver 太少（%d）—— 產生器壞了，對帳是空轉" % n_valid); sys.exit(1)
sys.exit(1 if bad else 0)
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

# ── #56 verify R1：孤兒目錄（`.orphaned_at`）、Unicode 數字、profile 長度 ──────────────────────
# Claude Code 在版本目錄不再被任何安裝引用時（update 換版、uninstall）在該目錄**正下方**寫
# `.orphaned_at`（cache/<marketplace>/<plugin>/<version>/.orphaned_at），約 7 天後才刪。

# mkorphan <marketplace> <version>：造一個孤兒版本目錄（帶一條 lens，好讓「誤載入」看得見）
mkorphan() {
  mkpack "$1" "$2"
  printf 'key,focus\norphan,孤兒目錄的 lens\n' > "${PACK}/lenses/code.csv"
  printf '1790000000000' > "${PACK}/.orphaned_at"
}

@test "#56 孤兒 + 同版本的現役安裝 → 選現役、status ok（不是 ambiguous）" {
  mkorphan alpha 1.0.0
  mkpack beta 1.0.0
  printf 'key,focus\nlive,現役\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ok", P
assert [x["key"] for x in d["lenses"]]==["live"], d["lenses"]
assert "/beta/" in P["path"], P
assert d["warnings"]==[], d["warnings"]
' "$output"
}

@test "#56 孤兒的版本較高 → 仍選版本較低的現役安裝" {
  mkorphan alpha 9.0.0
  mkorphan beta 2.0.0
  mkpack beta 1.0.0
  printf 'key,focus\nlive,現役\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ok", P
assert P["version"]=="1.0.0", P
assert [x["key"] for x in d["lenses"]]==["live"], d["lenses"]
' "$output"
}

@test "#56 只剩孤兒 → absent（已解除安裝的殘留，靜默），不是 unversioned 也不載入" {
  mkorphan alpha 1.0.0
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="absent", P
assert d["lenses"]==[] and d["warnings"]==[], d
' "$output"
}

@test "#56 兩個非孤兒同版本（旁邊還有孤兒）→ 仍是 ambiguous，警告不列孤兒" {
  mkorphan gamma 2.0.0
  mkpack alpha 2.0.0
  printf 'key,focus\na,fa\n' > "${PACK}/lenses/code.csv"
  mkpack beta 2.0.0
  printf 'key,focus\nb,fb\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ambiguous", P
assert d["lenses"]==[], d["lenses"]
w=" ".join(d["warnings"])
assert "/alpha/" in w and "/beta/" in w and "/gamma/" not in w, w
assert ".orphaned_at" in w, w      # 告訴使用者殘留目錄已經不算了，剩下的是真的兩份安裝
' "$output"
}

@test "#56 Unicode 數字不是 semver：'9９.0.0'（全形）不得勝過 1.0.0，'1.0.0-rc.９' 不算版本" {
  mkpack psychquant 1.0.0
  printf 'key,focus\ngood,ASCII 版本\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant '9９.0.0'
  printf 'key,focus\nwide,全形數字\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant '1.0.1-rc.９'
  printf 'key,focus\nwidepre,全形 prerelease\n' > "${PACK}/lenses/code.csv"
  mkpack psychquant '1.٣.0'
  printf 'key,focus\narabic,阿拉伯-印度數字\n' > "${PACK}/lenses/code.csv"
  run "$BIN" code
  [ "$status" -eq 0 ]
  jq_py "$pack_layer"'
assert P["status"]=="ok", P
assert P["version"]=="1.0.0", P
assert [x["key"] for x in d["lenses"]]==["good"], d["lenses"]
' "$output"
}

@test "#56 <profile> 長度上限 64：65／300 字元 → exit 2（不是 ENAMETOOLONG traceback），64 照常" {
  # user 目錄要**存在** —— 不存在時 stat 回 ENOENT、is_file() 安靜回 False；存在時才是
  # ENAMETOOLONG → 未捕捉的 OSError、exit 1（修法前的實際失敗形狀）
  mkdir -p "$USERDIR"
  mkpack psychquant 1.0.0
  run "$BIN" "$(printf 'a%.0s' $(seq 1 300))"
  echo "$output"
  [ "$status" -eq 2 ]
  [ "${output#*Traceback}" = "$output" ]
  run "$BIN" "$(printf 'a%.0s' $(seq 1 65))"
  [ "$status" -eq 2 ]
  run "$BIN" "$(printf 'a%.0s' $(seq 1 64))"
  [ "$status" -eq 0 ]
}

@test "無參數 → exit 2（用法）" {
  run "$BIN"
  [ "$status" -eq 2 ]
}
