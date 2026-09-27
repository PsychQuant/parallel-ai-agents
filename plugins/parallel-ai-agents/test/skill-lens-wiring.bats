#!/usr/bin/env bats
#
# 每一支專屬 review skill（`skills/ensemble-<profile>-review/`）都必須把三層 lens 疊加的
# 層 ②③ 接進它的 Workflow 派發（#40）。
#
# 為什麼要機器擋：`/ensemble-minutes-review`（v2.22.0 出貨）漏接 `bin/pai-collect-lens-layers`，
# 結果 `pai-lenses` 的 `lenses/minutes.csv` 與 `~/.claude/pai-lenses/minutes.csv` 在它的審閱裡
# **完全不生效，而且沒有任何警告**——CI 全綠、報表沒有 provenance 行，從輸出上看不出少了東西。
# `plugins/pai-lenses/scripts/validate.py` 的 `collector_wiring` 只在「該 profile 有 pack CSV」時
# 才看、只印 warning，且自承是啟發式；這裡是主 plugin 這一側的閘門：以目錄 glob 列舉，新增第五支
# `ensemble-*-review` 時自動涵蓋，漏接就紅。**`ensemble-compose` 不在這裡**（它的 collector 只在
# `--base` 時跑，形狀不同），它的接線目前沒有機器閘門。
#
# 判準是 SKILL.md 的**結構**，不是「某個字出現在檔案某處」（#65 verify R1：先前的版本只 grep 字，
# 把呼叫改成「⚠️ **不要**呼叫 …」、刪掉模板的 customLenses、刪掉報表段的 provenance 仍 5/5 綠）。
# 下面的 `wiring` 以 markdown 的 fenced block 與 `Phase N` 標題切段，四條判準：
#
#   派發模板     ```json / jsonc / javascript / js fenced block，**位於某個 `Phase N` 段內**，有 `profile` 鍵，
#                且另有至少一個派發標記鍵（`agentModel` / `contextBlock` / `codexEnabled` / `replicas` /
#                `scriptPath`）或 `Workflow(` 呼叫。派發段 = 第一個派發模板所在的 `Phase N` 段（含其子標題）。
#   collector    派發段裡有一個 ```bash / sh / shell / zsh fenced block，其中一行是**命令形狀**的呼叫：
#                （可選的縮排與 `VAR=值` 前綴之後）以 `python3` 開頭，下一個 token 是 collector 路徑
#                （`"${CLAUDE_PLUGIN_ROOT}/bin/pai-collect-lens-layers"`，引號可有可無），再下一個參數是
#                自己的 profile（取自目錄名）；且位置在派發模板**之前**。因此 `# …` 註解行、行尾註解
#                （`true # python3 …`）、`echo '… pai-collect-lens-layers minutes'`、`true || python3 …`、
#                `: python3 …` 都不算。寫在散文或 inline code 裡也不算 —— 那是否定句也能滿足的形狀。
#   customLenses 每一個派發模板都有 `customLenses` 鍵（`//` 註解行不算）。
#   profile      同一批派發模板裡的每一個 `profile` 值都等於自己的 profile —— 因此也不是 `custom`。
#   provenance   派發段**之後**的某個 `Phase N` 段（minutes 是 Phase 3，其餘是 Phase 4，見
#                references/lens-layers.md §4；這裡不寫死號碼，只要求「在派發之後」）裡，fenced block 以外有一句
#                （以 。！？； 切句）同時含 `provenance`（不含 `lensProvenance` 這種識別字）與「印」／print，
#                且同一句沒有固定否定詞表（NEG：不要／不必／不用／不需／無需／勿／禁止／跳過／省略／
#                別印／免印／`不` 緊接 `印`（不印、不再印…）／don't／never／skip…）裡的任何一個。
#                這是**同句共現 ＋ 固定否定詞表**的啟發式，不是語意判讀：表外的否定寫法（例如「provenance
#                行可以拿掉」）它看不出來。
#
# 寫作約束（判準的前提，改 SKILL.md 時要守）：
#   - 反例／錯誤示範的 json/js block 若同時帶 `profile` 與派發標記鍵，而且寫在某個 `Phase N` 段內，
#     會被當成派發模板（`profile: "custom"` 的反例就會讓 profile 判準紅）。反例請寫在 Phase 段以外、
#     或只寫 `profile` 一鍵（不帶派發標記）、或寫在散文 / inline code 裡。
#   - 真正的派發模板必須寫在 `Phase N` 標題之下，且第一個派發模板所在的 Phase 就是 collector 呼叫所在的 Phase。
#
# 已知界限（刻意不追）：它證明「指令在正確的位置、以可執行的形狀寫著」，不證明模型會照做；
# 也擋不住**跨句否定** —— 在 fence 旁邊的另一句寫「下面這段已停用，不要執行」，或在同一段另寫一句
# 「上面那個指令別跑」，fence 裡的呼叫形狀不變，判準仍綠。
#
# 每條判準都有 mutation case（本檔後半）：把對應的缺口套到**暫存副本**上，斷言 `wiring` 變紅、
# 且紅在預期的那條判準。mutation 找不到錨點時直接失敗（不會因為沒套上而假綠）。

setup() {
  SKILLS="${BATS_TEST_DIRNAME}/../skills"
}

# 列出某個 skills 目錄下所有專屬 review skill 的目錄名（ensemble-<profile>-review）。
# 用 if 而不是 `[ … ] && …`：後者在最後一個 glob 命中沒有 SKILL.md 時讓函式回非零（#65 verify R1-3）。
review_skills() {
  local d
  for d in "${1:-$SKILLS}"/ensemble-*-review; do
    if [ -f "$d/SKILL.md" ]; then basename "$d"; fi
  done
}

profile_of() { local n="${1#ensemble-}"; printf '%s\n' "${n%-review}"; }

# wiring check <SKILL.md> <profile> <collector|customLenses|profile|provenance|all>
#   → 每個失敗印一行 `FAIL <判準>: …`，有任何失敗 exit 1
# wiring mutate <SKILL.md> <profile> <mutation>...
#   → 就地改寫；任一 mutation 找不到錨點 exit 3
wiring() {
  python3 - "$@" <<'PY'
import re, sys

mode, path, prof = sys.argv[1], sys.argv[2], sys.argv[3]
args = sys.argv[4:]
text = open(path, encoding="utf-8").read()

OPEN = re.compile(r'^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+-]*)\s*$')
HEAD = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
PHASE = re.compile(r'^Phase\s*(\d+)', re.I)
SHELL = {"bash", "sh", "shell", "zsh"}
DISPATCH_LANGS = {"json", "jsonc", "javascript", "js"}
PROFILE_KEY = re.compile(r'^\s*"?profile"?\s*:')
PROFILE_VAL = re.compile(r'^\s*"?profile"?\s*:\s*["\']([^"\']*)["\']')
CUSTOM_KEY = re.compile(r'^\s*"?customLenses"?\s*:')
PROV = re.compile(r'(?<![A-Za-z])provenance', re.I)
PRINT = re.compile(r'印|print', re.I)
NEG = re.compile(r"不要|不必|不用|不需|無需|無須|勿|禁止|跳過|省略|別印|免印|不(?:再|會)?印"
                 r"|don't|do not|never|skip", re.I)
# 派發模板除了 `profile` 之外至少要有其中一個：只帶 `profile` 的反例 block 不算派發模板（#65 verify R2-7）
DISPATCH_MARK = re.compile(r'^\s*"?(?:agentModel|contextBlock|codexEnabled|replicas|scriptPath)"?\s*:|Workflow\s*\(')
COLLECTOR_NAME = re.compile(r'pai-collect-lens-layers')


def parse(lines):
    """→ blocks [{start,end,lang}]（start/end 為 fence 行號）、phase_of[i]（(num, head_line) 或 None）、infence[i]"""
    blocks, infence, phase_of = [], [False] * len(lines), [None] * len(lines)
    cur = None          # 目前開著的 fence
    phase = None        # (num, level, head_line)
    for i, l in enumerate(lines):
        if cur is not None:
            infence[i] = True
            s = l.strip()
            if s and set(s) == {cur["ch"]} and len(s) >= cur["n"]:
                cur["end"] = i
                blocks.append(cur)
                cur = None
            phase_of[i] = phase and (phase[0], phase[2])
            continue
        m = OPEN.match(l)
        if m:
            cur = {"start": i, "ch": m.group(1)[0], "n": len(m.group(1)), "lang": m.group(2).lower()}
            infence[i] = True
            phase_of[i] = phase and (phase[0], phase[2])
            continue
        h = HEAD.match(l)
        if h:
            level = len(h.group(1))
            p = PHASE.match(h.group(2))
            if p:
                phase = (int(p.group(1)), level, i)
            elif phase and level <= phase[1]:
                phase = None
        phase_of[i] = phase and (phase[0], phase[2])
    return blocks, infence, phase_of


def body(lines, b):
    return range(b["start"] + 1, b["end"])


def dispatch_blocks(lines, blocks, phase_of):
    """派發模板：Phase 段內、json/js、有未註解的 `profile` 鍵、且有另一個派發標記（見檔頭）"""
    out = []
    for b in blocks:
        if b["lang"] not in DISPATCH_LANGS or phase_of[b["start"]] is None:
            continue
        live = [lines[i] for i in body(lines, b) if not lines[i].strip().startswith("//")]
        if any(PROFILE_KEY.match(l) for l in live) and any(DISPATCH_MARK.search(l) for l in live):
            out.append(b)
    return out


def collector_re(p):
    """命令形狀：[縮排][VAR=值 …]python3 <collector 路徑> <profile>（見檔頭 collector 判準）"""
    return re.compile(r'^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*python3\s+'
                      r'(["\']?)\$\{?CLAUDE_PLUGIN_ROOT\}?/bin/pai-collect-lens-layers\1'
                      r'\s+(["\']?)' + re.escape(p) + r'\2(?:\s|;|&|\||$)')


def paragraphs(lines, infence, pred):
    """fenced block 以外、以空行／fence／標題分隔的段落；pred(i) 決定該行是否納入"""
    paras, cur = [], []
    for i, l in enumerate(lines):
        if infence[i] or not l.strip() or HEAD.match(l) or not pred(i):
            if cur:
                paras.append(cur)
            cur = []
            continue
        cur.append(i)
    if cur:
        paras.append(cur)
    return paras


def prov_sentence_ok(joined):
    for s in re.split(r'[。！？；]', joined):
        if PROV.search(s) and PRINT.search(s) and not NEG.search(s):
            return True
    return False


def check(lines, want):
    blocks, infence, phase_of = parse(lines)
    fails = []
    disp = dispatch_blocks(lines, blocks, phase_of)
    if not disp:
        fails.append(("dispatch", "找不到派發模板（`Phase N` 段內、含 `profile` 鍵與派發標記鍵的 "
                                  "```json / javascript fenced block）"))
        return fails
    dphase = phase_of[disp[0]["start"]]

    if want in ("all", "collector"):
        rx, hits = collector_re(prof), []
        for b in blocks:
            if b["lang"] in SHELL and phase_of[b["start"]] == dphase:
                hits += [i for i in body(lines, b) if rx.match(lines[i])]
        if not hits:
            fails.append(("collector", f"派發段（Phase {dphase[0]}）沒有 fenced shell block 以命令形狀呼叫 "
                                       f"`python3 \"${{CLAUDE_PLUGIN_ROOT}}/bin/pai-collect-lens-layers\" {prof}`"))
        elif min(hits) > disp[0]["start"]:
            fails.append(("collector", "collector 呼叫在派發模板之後 —— 必須先蒐集再派發"))

    if want in ("all", "customLenses"):
        for b in disp:
            if not any(CUSTOM_KEY.match(lines[i]) and not lines[i].strip().startswith("//") for i in body(lines, b)):
                fails.append(("customLenses", f"派發模板（第 {b['start'] + 1} 行起）沒有 `customLenses` 鍵"))

    if want in ("all", "profile"):
        for b in disp:
            for i in body(lines, b):
                if PROFILE_KEY.match(lines[i]) and not lines[i].strip().startswith("//"):
                    m = PROFILE_VAL.match(lines[i])
                    v = m.group(1) if m else None
                    if v != prof:
                        fails.append(("profile", f"第 {i + 1} 行 profile={v!r}，應為 {prof!r}"
                                                 + ("（改成 custom 會換掉 profile.title）" if v == "custom" else "")))

    if want in ("all", "provenance"):
        later = lambda i: phase_of[i] is not None and phase_of[i][0] > dphase[0]
        if not any(prov_sentence_ok("".join(lines[i].strip() for i in p))
                   for p in paragraphs(lines, infence, later)):
            fails.append(("provenance", f"派發段（Phase {dphase[0]}）之後的 Phase 段沒有一句（未否定的）"
                                        "「印 provenance 行」指令"))
    return fails


def mutate(lines, name):
    blocks, infence, phase_of = parse(lines)
    disp = dispatch_blocks(lines, blocks, phase_of)
    rx = collector_re(prof)
    coll = [b for b in blocks if b["lang"] in SHELL and any(rx.match(lines[i]) for i in body(lines, b))]
    if name in ("collector-negated", "collector-commented", "collector-wrong-profile",
                "collector-trailing-comment", "collector-echo", "collector-or-true"):
        if not coll:
            return None
        b = coll[0]
        if name == "collector-negated":
            indent = re.match(r'\s*', lines[b["start"]]).group(0)
            return lines[:b["start"]] + [f"{indent}⚠️ **不要**呼叫 `pai-collect-lens-layers {prof}`"] + lines[b["end"] + 1:]
        out = list(lines)
        for i in body(lines, b):
            if rx.match(out[i]):
                ind, cmd = re.match(r'(\s*)(.*)$', out[i]).groups()
                if name == "collector-commented":
                    out[i] = f"{ind}# {cmd}"
                elif name == "collector-trailing-comment":
                    out[i] = f"{ind}true # {cmd}"
                elif name == "collector-echo":
                    out[i] = f"{ind}echo '{cmd}'"
                elif name == "collector-or-true":
                    out[i] = f"{ind}true || {cmd}"
                else:
                    other = "custom" if prof != "custom" else "code"
                    out[i] = re.sub(r'(pai-collect-lens-layers["\']?\s+["\']?)' + re.escape(prof), r'\g<1>' + other, out[i])
        return out
    if name in ("drop-customlenses", "profile-custom"):
        if not disp:
            return None
        drop, out, hit = set(), list(lines), False
        for b in disp:
            for i in body(lines, b):
                if name == "drop-customlenses" and CUSTOM_KEY.match(lines[i]):
                    drop.add(i); hit = True
                if name == "profile-custom" and PROFILE_VAL.match(lines[i]):
                    out[i] = re.sub(r'(:\s*["\'])[^"\']*', r'\g<1>custom', lines[i], count=1); hit = True
        return [l for i, l in enumerate(out) if i not in drop] if hit else None
    if name == "insert-antipatterns":
        # 反例 block：一個在所有 Phase 段之前（連派發標記都帶），一個在派發段內但只帶 `profile`
        if not disp:
            return None
        first_phase = next((i for i, l in enumerate(lines)
                            if HEAD.match(l) and PHASE.match(HEAD.match(l).group(2))), None)
        dhead = phase_of[disp[0]["start"]][1]
        if first_phase is None or first_phase > dhead:
            return None
        # 逐鍵分行 —— PROFILE_KEY 只認行首的鍵，單行 `{ "profile": … }` 本來就不會被當成模板
        before = ["❌ 錯誤示範（不要這樣派發）：", "", "```json", "{",
                  '  "profile": "custom",', '  "contextBlock": "…",', '  "replicas": 1', "}", "```", ""]
        inside = ["", "❌ 反例：", "", "```json", "{", '  "profile": "custom"', "}", "```"]
        return (lines[:first_phase] + before + lines[first_phase:dhead + 1] + inside + lines[dhead + 1:])
    if name == "drop-dispatch-templates":
        if not disp:
            return None
        drop = set()
        for b in disp:
            drop.update(range(b["start"], b["end"] + 1))
        return [l for i, l in enumerate(lines) if i not in drop]
    if name in ("drop-render-provenance", "negate-render-provenance", "negate-render-provenance-buyin"):
        if not disp or phase_of[disp[0]["start"]] is None:
            return None
        dn = phase_of[disp[0]["start"]][0]
        later = lambda i: phase_of[i] is not None and phase_of[i][0] > dn
        targets = [p for p in paragraphs(lines, infence, later)
                   if PROV.search("".join(lines[i] for i in p))]
        if not targets:
            return None
        repl = {p[0]: p for p in targets}
        out, skip = [], set()
        for i, l in enumerate(lines):
            if i in skip:
                continue
            if i in repl:
                skip.update(repl[i])
                if name == "negate-render-provenance":
                    out.append("**不要**印 provenance 行。")
                elif name == "negate-render-provenance-buyin":
                    out.append("provenance 行一律不印。")
                continue
            out.append(l)
        return out
    raise SystemExit(f"unknown mutation {name}")


lines = text.split("\n")
if mode == "check":
    fails = check(lines, args[0] if args else "all")
    for k, msg in fails:
        print(f"FAIL {k}: {msg}")
    sys.exit(1 if fails else 0)
if mode == "mutate":
    for name in args:
        new = mutate(lines, name)
        if new is None or new == lines:
            print(f"mutation {name}: 找不到錨點，沒有套上", file=sys.stderr)
            sys.exit(3)
        lines = new
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    sys.exit(0)
raise SystemExit(f"unknown mode {mode}")
PY
}

# 對真實 skill 跑一條判準；失敗時列出每一支紅的 skill 與原因
check_all() {
  local want="$1" s p out bad=()
  while IFS= read -r s; do
    p="$(profile_of "$s")"
    if ! out="$(wiring check "$SKILLS/$s/SKILL.md" "$p" "$want")"; then
      bad+=("${s}（profile=${p}）：${out}")
    fi
  done < <(review_skills)
  if [ "${#bad[@]}" -ne 0 ]; then
    printf '%s\n' "${bad[@]}" >&2
    return 1
  fi
}

# 把某支 skill 複製到暫存樹、套 mutation；印出副本路徑
mutated_copy() {
  local s="$1"; shift
  local dst="$BATS_TEST_TMPDIR/skills/$s"
  mkdir -p "$dst"
  cp "$SKILLS/$s/SKILL.md" "$dst/SKILL.md"
  if [ "$#" -gt 0 ]; then
    wiring mutate "$dst/SKILL.md" "$(profile_of "$s")" "$@" >&2 || return 1
  fi
  printf '%s\n' "$dst/SKILL.md"
}

# 對每一支 review skill 套同一組 mutation，斷言 wiring 紅、且紅在 <expect> 這條判準
expect_red_everywhere() {
  local expect="$1"; shift
  local s p f out bad=()
  while IFS= read -r s; do
    p="$(profile_of "$s")"
    if ! f="$(mutated_copy "$s" "$@")"; then bad+=("${s}：mutation $* 套不上"); continue; fi
    if out="$(wiring check "$f" "$p" all)"; then
      bad+=("${s}：mutation $* 之後仍然綠")
    elif [[ "$out" != *"FAIL ${expect}:"* ]]; then
      bad+=("${s}：mutation $* 紅了，但不是紅在 ${expect}：${out}")
    fi
  done < <(review_skills)
  if [ "${#bad[@]}" -ne 0 ]; then
    printf '%s\n' "${bad[@]}" >&2
    return 1
  fi
}

# ── 列舉 ──

@test "至少有四支專屬 review skill，且含 minutes（防列舉為空的 vacuous 綠燈）" {
  run review_skills
  [ "$status" -eq 0 ]
  [ "$(printf '%s\n' "$output" | grep -c .)" -ge 4 ]
  # minutes 就是 #40 漏掉的那一支 —— 釘住它在列舉裡
  printf '%s\n' "$output" | grep -qx "ensemble-minutes-review"
}

@test "review_skills：最後一個 glob 命中沒有 SKILL.md 時仍回 0、只列有 SKILL.md 的" {
  local t="$BATS_TEST_TMPDIR/enum"
  mkdir -p "$t/ensemble-a-review" "$t/ensemble-zzz-review"
  touch "$t/ensemble-a-review/SKILL.md"
  run review_skills "$t"
  [ "$status" -eq 0 ]
  [ "$output" = "ensemble-a-review" ]
}

# ── 對真實 skill 的四條判準 ──

@test "collector：每一支 review skill 在派發段的 fenced shell block 以自己的 profile 呼叫 pai-collect-lens-layers，且在派發之前" {
  check_all collector
}

@test "customLenses：每一支 review skill 的每個 Workflow 派發模板都帶 customLenses 鍵" {
  check_all customLenses
}

@test "profile：每一支 review skill 的派發模板 profile 等於自己的 profile（因此不是 custom）" {
  check_all profile
}

@test "provenance：每一支 review skill 在派發之後的 Phase 段指示印 provenance 行" {
  check_all provenance
}

# ── mutation：每條判準都要看得到它變紅（#65 verify R1）──

@test "mutation 對照組：未改動的暫存副本在 wiring 下全綠（副本機制本身不製造紅燈）" {
  local s f bad=()
  while IFS= read -r s; do
    f="$(mutated_copy "$s")"
    wiring check "$f" "$(profile_of "$s")" all >/dev/null || bad+=("$s")
  done < <(review_skills)
  [ "${#bad[@]}" -eq 0 ]
}

@test "mutation：collector 的 fenced block 換成否定句「⚠️ **不要**呼叫 …」→ collector 紅" {
  expect_red_everywhere collector collector-negated
}

@test "mutation：collector 那一行改成 shell 註解 → collector 紅" {
  expect_red_everywhere collector collector-commented
}

@test "mutation：collector 用別的 profile 呼叫 → collector 紅" {
  expect_red_everywhere collector collector-wrong-profile
}

@test "mutation（verify R2-1）：collector 那一行變成行尾註解「true # python3 …」→ collector 紅" {
  expect_red_everywhere collector collector-trailing-comment
}

@test "mutation（verify R2-1）：collector 那一行包進 echo '…' → collector 紅" {
  expect_red_everywhere collector collector-echo
}

@test "mutation（verify R2-1）：collector 那一行前面加「true || 」（永不執行）→ collector 紅" {
  expect_red_everywhere collector collector-or-true
}

@test "mutation：派發模板刪掉 customLenses 那一行 → customLenses 紅" {
  expect_red_everywhere customLenses drop-customlenses
}

@test "mutation：派發模板的 profile 改成 custom → profile 紅" {
  expect_red_everywhere profile profile-custom
}

@test "mutation：刪掉報表段（派發之後的 Phase）提到 provenance 的段落 → provenance 紅" {
  expect_red_everywhere provenance drop-render-provenance
}

@test "mutation：報表段的 provenance 指令改成「**不要**印 provenance 行」→ provenance 紅" {
  expect_red_everywhere provenance negate-render-provenance
}

@test "mutation（verify R2-2）：報表段的 provenance 指令改成「provenance 行一律不印。」→ provenance 紅" {
  expect_red_everywhere provenance negate-render-provenance-buyin
}

@test "mutation（verify R2-7）：Phase 段外與派發段內各插一個 profile=custom 的反例 block → 仍全綠" {
  local s f out bad=()
  while IFS= read -r s; do
    if ! f="$(mutated_copy "$s" insert-antipatterns)"; then bad+=("${s}：套不上"); continue; fi
    out="$(wiring check "$f" "$(profile_of "$s")" all)" || bad+=("${s}：${out}")
  done < <(review_skills)
  if [ "${#bad[@]}" -ne 0 ]; then printf '%s\n' "${bad[@]}" >&2; return 1; fi
}

@test "mutation（verify R2-7）：插了反例 block 之後再刪掉真正的派發模板 → dispatch 紅（反例不會頂替）" {
  expect_red_everywhere dispatch insert-antipatterns drop-dispatch-templates
}

@test "mutation（verify R1 實測的組合）：minutes 三處一起拿掉 → collector、customLenses、provenance 全紅" {
  local f
  f="$(mutated_copy ensemble-minutes-review collector-negated drop-customlenses drop-render-provenance)"
  run wiring check "$f" minutes all
  [ "$status" -eq 1 ]
  [[ "$output" == *"FAIL collector:"* ]]
  [[ "$output" == *"FAIL customLenses:"* ]]
  [[ "$output" == *"FAIL provenance:"* ]]
}

@test "mutation（verify R1 實測的組合）：lecture 刪模板欄位 + provenance 段 → customLenses、provenance 紅" {
  local f
  f="$(mutated_copy ensemble-lecture-review drop-customlenses drop-render-provenance)"
  run wiring check "$f" lecture all
  [ "$status" -eq 1 ]
  [[ "$output" == *"FAIL customLenses:"* ]]
  [[ "$output" == *"FAIL provenance:"* ]]
}
