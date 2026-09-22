#!/usr/bin/env python3
"""詞法對帳產生器：按**封閉的構造維度**取笛卡兒積產生 workflow，交給 `test/oracle.py` 與 runner 對帳。

為什麼（#33 verify R30 §六「第 14 類：網的投餵」）：R29 把兩個作者無關的網交進 repo（`opsweep.py`、
`oracle.py`），但**餵給它們的輸入集合仍然是作者挑的**——同一支 `oracle.py` 在作者的 109 個 fixture 上
不一致 0，在 DA 與 regression 各自產生的語料上分別報出 10 與 72 條。判準已經與作者無關，投餵還沒有。
這一支把投餵也拿掉：**不列舉已知的形狀，列舉構造的維度**，再取積。

維度（封閉列舉；**改動這份清單是另一次 change**，不得在別處「順便」擴充）：

1. heredoc 分隔字的引號擺法（12）：`EOF` `'EOF'` `"EOF"` `"EO"F` `E"OF"` `'EOF'x` `""EOF` `'E'OF`
   `\\EOF` `E\\OF` `'E\\OF'` `' '`
   —— bash 對整個**詞**做 quote removal，所以這十二種的終止字只有三個相異值；任何一種被讀錯，
   heredoc 不是提早終止（資料變 code）就是永不終止（吞掉後面的真管線）。
2. 引號種類（4）：無／`'…'`／`"…"`／`$'…\\'…'`（ANSI-C，含 `\\'`）
3. `#` 的位置（6）：行首／空白後／字母後／`${VAR#…}` 內／反引號內／`$( )` 內
   —— 前三種決定「這是不是註解」，後三種是 bash 會**改變** `#` 意義的三個上下文。
4. block scalar 形式（8）：`|` `>` `|2` `>2`，各自 ±行尾註解（註解含 1-9 的與不含的各一）
5. 管線運算元的位置（3）：同一行／前一行以 `|` 結尾續行／行首（bash 是語法錯誤）
6. 內文縮排（2）：等於自動偵測值／多一格（more-indented）

**維度不是全域取積**（12×4×6×8×3×2 = 13824 檔，一輪 oracle 要跑一小時以上，沒有人會在 CI 跑它）。
改成**三組**各自取積，每一組把會互相影響的維度放在一起——分組本身也是封閉列舉：
  A：1 × 4 × 6      （heredoc 的分隔字 × block 形式 × 內文縮排）×2 個方向 = 384
  B：2 × 3 × 5      （引號種類 × 管線位置 × `#` 位置的前五種）              = 60
  C：3 × 4          （`#` 的六個位置 × block 形式）                          = 48
每個檔產生前先用 PyYAML 驗一次；不合法的丟掉並在結尾報數（**不靜默跳過**）。

「方向」指的是兩種構造，兩個都要有才擋得住兩個方向的錯：
  data —— 管線的文字只出現在 heredoc **內文**裡，之後有一行會洩漏的 `echo "$PR_TITLE"`。
           分隔字讀錯而提早終止 ⟹ lint 看見假管線 ⟹ pass ⟹ 神諭報**繞過**。
  real —— heredoc 內文是普通資料，之後接一條**真的**管線。
           分隔字讀錯而永不終止 ⟹ 真管線被吞 ⟹ lint 打紅 ⟹ 神諭報**誤擋**。

用法：
  test/corpus/shellgen.py --out DIR        產生檔案（DIR 會被建立；既有的同名檔會被覆寫）
  test/corpus/shellgen.py --count          只印會產生幾檔，不寫檔
產出的檔名帶維度值，便於從 oracle 的輸出直接讀出是哪一組構造。
"""
import argparse
import itertools
import pathlib
import sys

try:
    import yaml
except ImportError:
    print("✗ shellgen.py 需要 PyYAML：python3 -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)

NEUT = "python3 scripts/neutralise.py"

# ── 維度 1：分隔字的引號擺法（值 → 寫在 `<<` 後面的字面, bash quote removal 之後的終止字）──
DELIMS = [
    ("plain",      "EOF",      "EOF"),
    ("sq",         "'EOF'",    "EOF"),
    ("dq",         '"EOF"',    "EOF"),
    ("infix-dq",   '"EO"F',    "EOF"),
    ("suffix-dq",  'E"OF"',    "EOF"),
    ("sq-then-x",  "'EOF'x",   "EOFx"),
    ("empty-dq",   '""EOF',    "EOF"),
    ("split-sq",   "'E'OF",    "EOF"),
    ("bs-head",    "\\EOF",    "EOF"),
    ("bs-mid",     "E\\OF",    "EOF"),
    ("bs-in-sq",   "'E\\OF'",  "E\\OF"),
    ("space",      "' '",      " "),
    # ── R33 新增（#33 verify R32：Codex 第 3 條／logic L-1／DA-3／DA-5）。終止字**不是推的**，
    #    是用 bash 自己的 EOF 警告問出來的（`cat <<X` ⏎ `body` → 警告訊息寫「需要「…」」）：
    #      `<<''`        → 需要「」      （空字串；一行空行就終止——實測 `echo AFTER` 有跑）
    #      `<<""`        → 需要「」
    #      `<<EOF`x``    → 需要「EOF`x`」 （反引號**不是**詞界，是詞的一部分）
    #      `<<EOF$(x)`   → 需要「EOF$(x)」（`$(`／`)` 同上）
    ("nul-sq",     "''",       ""),
    ("nul-dq",     '""',       ""),
    ("backtick",   "EOF`x`",   "EOF`x`"),
    # `$(…)` 在分隔字裡本 lint fail-closed 走 PARSE（bash 會重新序列化它；見 lint 內的說明）。這一組檔**自己
    # 宣告** parse-red——與 fixture 的 `# EXPECT:` 同一個機制，神諭因此歸「不可比（fail-closed）」而不是誤擋。
    ("cmdsubst",   "EOF$(x)",  "EOF$(x)", "parse-red"),
]
# ── 維度 4：block scalar 形式（值 → 標頭字面, 內文相對 key 的縮排）──
STYLES = [
    ("lit",         "|",            2),
    ("fold",        ">",            2),
    ("lit2",        "|2",           2),
    ("fold2",       ">2",           2),
    ("lit-c",       "| # note",     2),
    ("fold-c",      "> # note",     2),
    ("lit-c9",      "| # note 9",   2),
    ("lit2-c",      "|2 # note",    2),
]
# ── 維度 6：內文縮排（相對於自動偵測值）──
INDENTS = [("flush", 0), ("deeper", 1)]
# ── 維度 2：引號種類 ──
QUOTES = [("none", "%s"), ("sq", "'%s'"), ("dq", '"%s"'), ("ansic", "$'%s\\''")]
# ── 維度 5：管線運算元的位置 ──
PIPEPOS = ["same-line", "continued", "line-start"]
# ── 維度 3：`#` 的位置 ──
HASHPOS = ["line-start", "after-space", "after-letter", "param-expansion", "backtick", "cmdsubst"]

HEAD = "name: t\non: pull_request\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"


def wrap(name, body_lines, style_hdr, key_indent=8):
    """把 run 區塊包成一份 workflow。`body_lines` 是**相對縮排 0** 的內文。"""
    pad = " " * (key_indent + 2)
    body = "\n".join(pad + l if l.strip() else l for l in body_lines)
    return HEAD + "      - name: %s\n%srun: %s\n%s\n" % (name, " " * key_indent, style_hdr, body)


def group_a():
    """分隔字 × block 形式 × 內文縮排 × 方向。"""
    for dspec, (sn, shdr, _), (inm, extra), direction in itertools.product(
            DELIMS, STYLES, INDENTS, ("data", "real")):
        dn, dlit, dterm = dspec[:3]; expect = dspec[3] if len(dspec) > 3 else None
        ind = " " * extra
        if direction == "data":
            body = [ind + "cat <<" + dlit, ind + "x | " + NEUT, ind + dterm, ind + 'echo "$PR_TITLE"']
        else:
            body = [ind + "cat <<" + dlit, ind + "plain data", ind + dterm,
                    ind + 'echo "$PR_TITLE" | ' + NEUT]
        yield "a-%s-%s-%s-%s" % (dn, sn, inm, direction), body, (shdr, expect)


def group_b():
    """引號種類 × 管線位置 × `#` 位置（前五種）。"""
    for (qn, qf), pipe, hn in itertools.product(QUOTES, PIPEPOS, HASHPOS[:5]):
        word = qf % "hello"
        frag = {"line-start": "# note",
                "after-space": "echo a # note",
                "after-letter": "echo a#note",
                "param-expansion": "echo ${PR_TITLE#note}",
                "backtick": "echo a `#note`"}[hn]
        if pipe == "same-line":
            body = ["echo %s | %s" % (word, NEUT), frag, 'echo "$PR_TITLE"']
        elif pipe == "continued":
            body = ["echo %s |" % word, "  " + NEUT, frag, 'echo "$PR_TITLE"']
        else:
            body = ["echo %s" % word, "| " + NEUT, frag, 'echo "$PR_TITLE"']
        yield "b-%s-%s-%s" % (qn, pipe, hn), body, "|"


def group_c():
    """`#` 的六個位置 × block 形式（折疊會把 `#` 之後的東西吃掉——這一組專打那個交互作用）。"""
    # **`STYLES[:4]` 是與 docstring 分岔的那一刀**（R32 Codex 第 5 條／requirements F2）：
    # 文件說 C 組 48 檔，程式只跑 24。分岔的兩邊都是宣稱，改成一致——取完整 STYLES。
    for hn, (sn, shdr, _) in itertools.product(HASHPOS, STYLES):
        frag = {"line-start": "# " ,
                "after-space": 'echo "$PR_TITLE" # ',
                "after-letter": 'echo "$PR_TITLE" a#',
                "param-expansion": 'echo ${PR_TITLE#',
                "backtick": 'echo "$PR_TITLE" `#',
                "cmdsubst": 'echo "$PR_TITLE" $(#'}[hn]
        tail = {"param-expansion": "}", "backtick": "`", "cmdsubst": ")"}.get(hn, "")
        body = [frag + "| " + NEUT + tail]
        yield "c-%s-%s" % (hn, sn), body, shdr


# ── D 組的維度（R33 新增；每一條對應 R31／R32 的一個機制，且 `shapes.py` 各有一列）──
# 維度 7：參數展開的內部構造（5）——決定「展開在哪裡結束」，是 `${…}` 消費器的實際觸發條件
PARAMEXP_CORES = [
    ("plain",        "a"),
    ("literal-brace", "a{b}c"),
    ("nested",       "${SEP}"),
    ("escaped-brace", "a\\}b"),
    ("quoted-brace", '"}"'),
]
# 維度 8：分隔字詞的跨行構造（4）——不是 (名, 字面, 終止字) 三元組表示得了的，所以另立
DELIM_WORDS = [
    ("cont-unq",  ["cat <<AB\\", "CD"],  "ABCD"),
    ("cont-dq",   ['cat <<"AB\\', 'CD"'], "ABCD"),
    ("unterm-dq", ['cat <<"EOF'],         None),
    ("unterm-sq", ["cat <<'EOF"],         None),
]
# 維度 9：YAML 層的四個形狀（tag、`${{ }}` 三種擺法）
YAML_SHAPES = ["tag-bang", "ghexpr-plain", "ghexpr-brace-in-quote", "ghexpr-folded"]


def group_d():
    """R31／R32 機制的構造維度。

    為什麼要這一組（#33 verify R32 DA-9）：`shapes.py` 對 R31 的每一個機制都報 0 檔——語料**沒有**
    那些形狀，而 CHANGELOG 仍然拿那份語料當「不一致 0」的證據。**分母裡沒有的形狀，量到的 0 不是證據。**
    """
    for (cn, core), place in itertools.product(PARAMEXP_CORES, ("in", "out")):
        if place == "in":      # 管線文字在展開**裡面** ⇒ 提早結束展開的 lint 會看到假管線
            body = ['echo "$PR_TITLE"', "echo ${PR_TITLE#%s| %s }" % (core, NEUT)]
        else:                  # 展開正確收尾後接**真**管線 ⇒ 過度消費的 lint 會把它吞掉
            body = ["echo ${PR_TITLE#%s}| %s" % (core, NEUT)]
        yield "d-paramexp-%s-%s" % (cn, place), body, "|"

    for (wn, opener, term), direction in itertools.product(DELIM_WORDS, ("data", "real")):
        tail = (["x | " + NEUT] + ([term] if term else []) + ['echo "$PR_TITLE"']
                if direction == "data"
                else ["plain data"] + ([term] if term else []) + ['echo "$PR_TITLE" | ' + NEUT])
        yield "d-delimword-%s-%s" % (wn, direction), list(opener) + tail, "|"

    for yn in YAML_SHAPES:
        if yn == "tag-bang":
            yield "d-yaml-tag-bang", None, None          # 特例：整份 workflow 自己組
        elif yn == "ghexpr-plain":
            yield "d-yaml-ghexpr-plain", ['echo "${{ github.event.pull_request.title }}" | ' + NEUT], "|"
        elif yn == "ghexpr-brace-in-quote":
            yield ("d-yaml-ghexpr-brace-in-quote",
                   ['echo "${{ format(\'{0}\', github.event.pull_request.title) }}" | ' + NEUT], "|")
        else:
            yield ("d-yaml-ghexpr-folded",
                   ['echo "${{ format(\'{0}\', github.event.pull_request.title) }}"', "| " + NEUT], ">")


TAG_BANG_DOC = (HEAD + '      - name: tag-bang\n        run: !!str "echo hi | '
                + NEUT + '"\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", metavar="DIR")
    ap.add_argument("--count", action="store_true", help="只印檔數，不寫檔")
    a = ap.parse_args()
    cases = list(group_a()) + list(group_b()) + list(group_c()) + list(group_d())
    if a.count:
        print(len(cases)); return 0
    if not a.out:
        ap.error("--out 或 --count 擇一")
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    written, invalid = 0, []
    for name, body, hdr in cases:
        # `body is None` 的那一個是 YAML 層的 tag 形狀：它的 `run:` 值帶 `!!str`，
        # 不是 block scalar，`wrap()` 表示不了，所以整份 workflow 自己組。
        expect = None
        if isinstance(hdr, tuple):
            hdr, expect = hdr
        text = TAG_BANG_DOC if body is None else wrap(name, body, hdr)
        if expect:
            text = "# EXPECT: %s\n" % expect + text
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as e:
            invalid.append((name, str(e).splitlines()[0])); continue
        (out / ("gen-%s.yml" % name)).write_text(text, encoding="utf-8")
        written += 1
    print("%d 個構造 → 寫出 %d 檔（PyYAML 拒絕 %d 檔，逐一列出如下）" % (len(cases), written, len(invalid)))
    for name, why in invalid:
        print("  拒絕 %s | %s" % (name, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
