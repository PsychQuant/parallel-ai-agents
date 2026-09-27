#!/usr/bin/env python3
"""觸發形狀計數：本輪每個新機制對應一個可機械計數的形狀，報它在一份（或多份）語料清單裡出現在幾個檔。

為什麼（#33 verify R28 DA D11）：「base-綠 → head 紅 = 0」只在分母裡**真的有那個形狀**時才是證據。R28 對 heredoc
機制報 0，而分母裡含 heredoc 的檔是 0 個——量到的是「沒有分母」，不是「沒有誤擋」。所以每個新機制都要能
回答：它的觸發形狀在 (i) 野外 base-綠、(ii) 合成 base-綠、(iii) 合成 head-綠 各出現幾檔；(ii) 為 0 的機制
**不得**在註解／CHANGELOG 寫 GREEN→RED = 0。

形狀是**封閉列舉**（下面 SHAPES），每一條對一個機制；用 PyYAML 取 run 區塊（shell 層形狀）或掃原始文字
（YAML 層形狀）。計數是「檔數」不是「次數」——分母也是檔數。PyYAML 拒絕的檔對 shell 層形狀計 0（進不了）。

用法：shapes.py <list>…   每份清單各出一欄；清單格式同 threeaxis.py。
"""
import pathlib
import re
import sys

try:
    import yaml
except ImportError:
    print("✗ shapes.py 需要 PyYAML：python3 -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)

RUN_LINE = re.compile(r"^\s*(?:- )?run:\s*(.*)$")


def hollow(s):
    """把引號內容挖空（保留長度），讓 `<<` 的搜尋不落在字串裡。"""
    out, q, i = [], None, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\" and q == '"' and i + 1 < len(s):
                out.append("  "); i += 2; continue
            out.append(q if c == q else " ")
            if c == q:
                q = None
            i += 1; continue
        if c == "\\" and i + 1 < len(s):
            out.append("  "); i += 2; continue
        if c in "'\"":
            q = c
        out.append(c); i += 1
    return "".join(out)


def heredocs(run):
    """[(opener_line_idx, delim, quote_char|"", dash, terminator_idx|None, body_lines)]；粗略、與 lint 無關的獨立實作。
    bash 語意：分隔字帶引號**或含反斜線**都算引號化（內文不展開、行尾反斜線不續行）；這裡把引號字元原樣回傳，
    讓 D2 能分辨「引號分隔字」與「未引號但含反斜線」。"""
    phys = run.split("\n"); out = []; i = 0
    while i < len(phys):
        h = hollow(phys[i])
        m = re.search(r"(?<!<)<<(-?)(?!<)\s*", h)
        if not m or re.search(r"\(\(", h[:m.start()]):
            i += 1; continue
        j0 = m.end(); orig = phys[i]; q = ""
        if j0 < len(orig) and orig[j0] in "'\"":
            q = orig[j0]; j0 += 1; e = orig.find(q, j0); delim = orig[j0:e] if e > 0 else ""
        else:
            delim = re.match(r"[^\s;&|<>()]*", orig[j0:]).group(0)
        if not delim:
            i += 1; continue
        cd = delim.replace("\\", "")
        dash = m.group(1) == "-"
        j = i + 1; term = None
        while j < len(phys):
            pj = phys[j].lstrip("\t") if dash else phys[j]
            if pj.rstrip() == cd:          # 用 rstrip 找「lint 前一版會當成終止字」的那一行
                term = j; break
            j += 1
        out.append((i, delim, q, dash, term, phys[i + 1:term] if term is not None else phys[i + 1:]))
        i = (term + 1) if term is not None else len(phys)
    return out


def runs_of(text):
    d = yaml.safe_load(text)
    if not isinstance(d, dict):
        return []
    out = []
    for j in (d.get("jobs") or {}).values():
        if isinstance(j, dict):
            for s in (j.get("steps") or []):
                if isinstance(s, dict) and isinstance(s.get("run"), str):
                    out.append(s["run"])
    return out


# ── 封閉列舉：機制 → 形狀述詞（回傳該檔是否含此形狀）──
def sh(pred):                       # shell 層：對每個 run 區塊的 heredoc
    def f(text, runs):
        return any(pred(run, hd) for run in runs for hd in heredocs(run))
    return f


BLOCK_HDR = re.compile(r"^(\s*)(?:- )?[\w-]+:\s*[|>][+-]?\d?[+-]?\s*(?:#.*)?$")


def structural_lines(text):
    """跳過 block scalar 的內文行（`key: |`／`>` 之後比它深的行）：那是不透明文字，`script: |` 裡的 JavaScript
    `{ Accept: '…' }` 不是 YAML flow 值。R29 第一版沒跳，把 react 的 github-script 算成 D8 形狀（野外 base-綠 1 → 0）。"""
    out, skip_deeper_than = [], None
    for l in text.split("\n"):
        ind = len(l) - len(l.lstrip())
        if skip_deeper_than is not None:
            if not l.strip() or ind > skip_deeper_than:
                continue
            skip_deeper_than = None
        m = BLOCK_HDR.match(l)
        if m:
            skip_deeper_than = len(m.group(1)) + (2 if l.lstrip().startswith("- ") else 0)
            out.append(l)          # 標頭本身是結構行（D5／D5' 就是看它）
            continue
        out.append(l)
    return out


def raw(regex):                     # YAML 層：結構行逐行（不含 block scalar 內文）
    r = re.compile(regex)
    return lambda text, runs: any(r.search(l) for l in structural_lines(text))


# **形狀必須對準機制的實際觸發條件，不是它的典型長相**（R30 MB-10）：R29 的 D5 述詞要求數字**緊接**
# `|`，於是 R30 MB-1 那一族（數字在標頭的行尾註解裡）整批不被計數——而那正是當輪唯一從綠翻紅的機制。
# 「量測設計得比改動窄」出現在**專門為了修那個病而寫的工具**上。下面每一條旁邊註明它對應的是哪一段
# 程式碼的條件。
SHAPES = [
    ("D1  heredoc 終止行帶尾端空白/tab（lint 前一版 rstrip 後相等）",
     sh(lambda run, hd: hd[4] is not None and run.split("\n")[hd[4]] != run.split("\n")[hd[4]].rstrip())),
    ("D2  未引號分隔字含反斜線（`<<E\\OF`）",
     sh(lambda run, hd: "\\" in hd[1] and not hd[2])),
    # R31：本輪真正改動的是**分隔字的 quote removal**——引號出現在詞的任何位置。
    # R30 MB-10 點名 D2 量的是「沒改動的那一半」，所以這一條獨立列出。
    ("D2b 分隔字的引號不在詞首（`<<\"EO\"F`／`<<'EOF'x`／`<<\"\"EOF`）",
     sh(lambda run, hd: bool(re.search(r"<<-?\s*[^\s;&|()<>]*[\"']", run)) and hd[2] and not str(run).lstrip().startswith("<<"))),
    # R31：折疊 block scalar（`>`）——換行是空白，`#` 之後整條邏輯行都是註解。
    ("D-fold `run: >` 折疊 block scalar",
     raw(r"^\s*(?:- )?run:\s*>")),
    # R31：行首的 `|`（bash 語法錯誤，不是管線續行）。
    ("D-leadpipe 內文行首是 `|`",
     lambda text, runs: any(l.lstrip().startswith("|") for run in runs for l in run.split("\n")[1:])),
    ("D3  未引號 heredoc 內文最後一行以反斜線結尾",
     sh(lambda run, hd: (not hd[2]) and "\\" not in hd[1] and bool(hd[5]) and hd[5][-1].endswith("\\"))),
    ("D4  同一實體行先 `((`/`$((` 再 `<<`",
     lambda text, runs: any(re.search(r"\(\(.*<<", hollow(l)) for run in runs for l in run.split("\n"))),
    ("D4b 任何 `((`／`$((`（算術深度的入口）",
     lambda text, runs: any("((" in hollow(l) for run in runs for l in run.split("\n"))),
    ("D-paramexp `${…#…}`（`#` 在參數展開裡）",
     lambda text, runs: any(re.search(r"\$\{[^}]*#", l) for run in runs for l in run.split("\n"))),
    ("D-backtick 反引號命令替換",
     lambda text, runs: any("`" in hollow(l) for run in runs for l in run.split("\n"))),
    ("D-ansic `$'…'`（ANSI-C 引號）",
     lambda text, runs: any("$'" in l for run in runs for l in run.split("\n"))),
    # `BLOCK_SCALAR_RE` 命中 ∧ 標頭裡任何位置有 1-9（**含行尾註解**）——這是 `explicit_pad` 真正的入口。
    ("D5  block scalar 標頭裡出現 1-9（含行尾註解 —— explicit_pad 的實際觸發條件）",
     lambda text, runs: any(re.search(r"[1-9]", m.group(1))
                            for l in structural_lines(text)
                            for m in [re.match(r"^\s*(?:- )?run:\s*([|>].*)$", l)] if m)),
    ("D5a `run: |N`／`>N` 真的有縮排指示子",
     raw(r"^\s*(?:- )?run:\s*[|>](?:[1-9][+-]?|[+-][1-9])")),
    ("D5b block scalar 標頭帶行尾註解（不論有沒有數字）",
     raw(r"^\s*(?:- )?run:\s*[|>][+-]?[1-9]?[+-]?\s+#")),
    ("D6  heredoc 開頭行以反斜線續行（`<<EOF \\`）",
     lambda text, runs: any(re.search(r"<<\S*.*\\$", hollow(l)) for run in runs for l in run.split("\n"))),
    # 這條路徑對 **plain 純量**也成立（`run: echo hi # note`），不得只認引號純量。
    ("D7  run 值後接 YAML 行尾註解（引號或 plain 純量皆算）",
     raw(r"""^\s*(?:- )?run:\s*(?:"[^"]*"|'[^']*'|[^|>#][^#]*)\s+#""")),
    ("D8b flow 序列裡有 `\\\"`",
     raw(r"""^\s*[\w-]+:\s*\[.*\\".*\]""")),
    ("D8  jobs 子樹的 flow 值含 `:`（fail-closed 的那一類）",
     lambda text, runs: _flow_colon_in_jobs(text)),
    ("D5' 指示子為 0 或 ≥10（YAML 錯誤）",
     raw(r"^\s*(?:- )?run:\s*[|>][+-]?(?:0|\d\d)")),
    # ── R31 與 R32 的機制各自一列（#33 verify R32 DA-9）──
    # **上一輪把機制加進 lint，卻沒有把對應的列加進來**，於是 `shapes.py` 對 R31 的每一個機制都是 0 列，
    # 而 CHANGELOG 仍然照著寫 `GREEN→RED 0`——這支工具的檔頭第 6-7 行明文禁止那件事，作者在 R29 的
    # CHANGELOG 段遵守過，一輪之後就破壞了。**一條沒有閘門的散文規則，一輪就失去遵守**，所以本輪
    # 除了補列，還把 `shapes.py` 接進 CI 與 `run.sh`（見 G-R32-DA-5）。
    ("R31-1 `${…}` 內含**巢狀** `${`（depth 只在 `${` 加一層的入口）",
     lambda text, runs: any(re.search(r"\$\{[^{}]*\$\{", l) for run in runs for l in run.split("\n"))),
    ("R31-2 `${…}` 內含**字面** `{`（不是 `${`——自查缺陷 (b) 的觸發條件）",
     lambda text, runs: any(re.search(r"\$\{[^{}]*(?<!\$)\{", l) for run in runs for l in run.split("\n"))),
    ("R31-3 分隔字詞以反斜線結尾（續行；`<<AB\\`）",
     lambda text, runs: any(re.search(r"<<-?\s*['\"]?[^\s;&|<>()]*\\$", l) for run in runs for l in run.split("\n"))),
    ("R31-4 分隔字的引號未在同一行收尾（fail-closed `PARSE:` 的入口）",
     lambda text, runs: any(re.search(r"<<-?\s*(['\"])[^'\"]*$", l) for run in runs for l in run.split("\n"))),
    ("R31-5 tag 值（`!`——fail-closed 的那一類）",
     raw(r"^\s*(?:- )?[\w-]+:\s*!")),
    ("R32-1 run 區塊內出現 `${{ }}`（GitHub Actions 運算式）",
     lambda text, runs: any("${{" in l for run in runs for l in run.split("\n"))),
    ("R32-2 `${{ }}` 內有引號字串包著大括號（誤擋的實際觸發條件）",
     lambda text, runs: any(re.search(r"\$\{\{[^}]*['\"][^'\"]*\{", l) for run in runs for l in run.split("\n"))),
    ("R32-3 分隔字詞含反引號或 `$(`（bash 在此不斷詞）",
     lambda text, runs: any(re.search(r"<<-?\s*[^\s;&|<>()]*(?:`|\$\()", l) for run in runs for l in run.split("\n"))),
    ("R32-4 空分隔字（`<<''`／`<<\"\"`）",
     # `(?![^\s;&|<>()])` 是必要的：沒有它，`<<""EOF` 也會被算成空分隔字（第一版如此，在產生語料上
     # 報 32 檔而真正的空分隔字是 0 檔——**一個太鬆的述詞會讓普查報出它其實沒有涵蓋的東西**，
     # 那正是這支工具存在的理由的反面）。
     lambda text, runs: any(re.search(r"<<-?\s*(?:''|\"\")(?![^\s;&|<>()])", l) for run in runs for l in run.split("\n"))),
    ("R32-5 `${…}` 內含逃脫的 `\\}`",
     lambda text, runs: any(re.search(r"\$\{[^}]*\\\}", l) for run in runs for l in run.split("\n"))),
    ("R32-6 折疊 block scalar 有 **≥3 行**連續內容（遞移折疊的觸發條件）",
     lambda text, runs: _folded_run_three_plus(text)),
    # ── R35 的機制各自一列（#33 verify R34 中心發現：四個語意不同的最小修法在所有網上數字都不變——
    # 網只對作者點名的輸入有鑑別力）。每一列對應 shellgen E 組的一個維度，由 `--require-nonzero R3` 守。──
    ("R35-1 分隔字詞後緊接 `(`／`)`（`(cat <<EOF)`）",
     lambda text, runs: any(re.search(r"<<-?\s*['\"]?\w+['\"]?[()]", l) for run in runs for l in run.split("\n"))),
    ("R35-2 折疊區塊裡以 `\\` 結尾的行後接空行或 more-indented 行（續行跨佔位）",
     lambda text, runs: _folded_backslash_then_break(text)),
    ("R35-3 `${…}` 內含反引號、`$(` 或 `$'`",
     lambda text, runs: any(re.search(r"\$\{[^}]*(?:`|\$\(|\$')", l) for run in runs for l in run.split("\n"))),
    ("R35-4 雙引號裡的 `${…}` 內又有雙引號",
     lambda text, runs: any(re.search(r"\"\$\{[^}]*\"", l) for run in runs for l in run.split("\n"))),
    ("R35-5 `${…}` 在同一行沒收尾（跨行）",
     lambda text, runs: any(re.search(r"\$\{[^}]*$", l) for run in runs for l in run.split("\n"))),
    ("R35-6 分隔字用 `$'…'`／`$\"…\"`",
     lambda text, runs: any(re.search(r"<<-?\s*\$['\"]", l) for run in runs for l in run.split("\n"))),
    ("R35-7 舊式算術 `$[…]`",
     lambda text, runs: any("$[" in l for run in runs for l in run.split("\n"))),
    ("R35-8 算術 `$((` 在同一行沒收尾（跨行）",
     lambda text, runs: any(re.search(r"\$\(\((?:(?!\)\)).)*$", l) for run in runs for l in run.split("\n"))),
    ("R35-9 算術或條件式裡出現 `|`",
     lambda text, runs: any(re.search(r"\$\(\([^)]*\||\[\[[^\]]*\|", l) for run in runs for l in run.split("\n"))),
    ("R35-10 run 內文行以 tab 開頭（YAML 縮排之後）",
     lambda text, runs: any(l.startswith("\t") for run in runs for l in run.split("\n"))),
    ("R35-11 heredoc 開在 `$(…)` 裡",
     lambda text, runs: any(re.search(r"\$\([^)]*<<", l) for run in runs for l in run.split("\n"))),
    ("R35-12 折疊區塊以空行開頭（`prev_flush_content` 的 EXPECTED_SURVIVE 到得了的唯一情形）",
     lambda text, runs: _folded_leading_blank(text)),
    ("R35-13 折疊內容行帶行尾空白（`strip→id` 的 EXPECTED_SURVIVE 的觸發條件）",
     # 不能用 `raw()`：它只看結構行，行尾空白在 block scalar **內文**裡——`raw()` 依設計看不到內文，套在這個形狀上必然報 0 檔。
     lambda text, runs: any(b.strip() and b != b.rstrip() for body in _folded_blocks(text) for b in body)),
    # ── R37 的機制各自一列（#33 verify R36 master 第 3–17、21、22 列，以及合併時修的反引號註解）。
    # 命名沿用既有慣例：`R37-N <一句話說明觸發條件>`。列的分母是 `--require-nonzero R3`（前綴比對，R37 也吃得到）；
    # `shellgen.py --strict` 組是 R37-1、2、4、5、6、7、8 這七列的主要非零來源（R37-3、9、10 全部來自既有 A-E 組，見下）——預設 A-E 組沒有 `shell:`／`env:`／`defaults:` 維度，
    # R37-1、2、4、5、6、7、8 這七列在純預設語料上是 0（見 R36 第 19 列：「--strict 沒有任何作者無關的網」正是這裡要補的分母）；R37-9、R37-10 反而完全靠預設語料量到；
    # 少數（R37-3、R37-9、R37-10）恰好也被既有 A-E 組的其他維度覆蓋，一併算數——這三列在純預設語料上反而是它們唯一的非零來源。
    #
    # **只收「本工作包（R36 放行條件第 6 條：--strict 語料）驗過非零」的機制**——這是刻意的收斂，不是遺漏：
    # 下面 13 個 R37 機制對應 master 第 5(a)(b)(c)、7、10、13、14、15、16、17（第二段）、21、22 列，
    # 其中第 13 列（defaults 根層級 flow 形式）其實屬於 r37b（已有既有 fixture）；其餘屬於**另外三個修法包**（r37c 雙引號詞法／r37d 命令位置詞法與未收尾構造／r37e decode+dedent+fold）
    # 的觸發形狀，不是 `--strict` 六個維度（shell 值／env 鍵／fd 轉向拼法／xtrace 拼法／多段管線／子殼層包管線）
    # 的產物。**寫成列會是空頭支票**：`shellgen.py` 目前沒有任何維度會產生這些形狀，加了列只會讓
    # `--require-nonzero R3` 這個 CI 硬閘門在合併後對著注定是 0 的分母紅——除非那三個修法包各自也把
    # 對應的產生維度併進 `shellgen.py`。這件事不在本工作包的職權（見任務鐵律第 2 條：不得動別的修法包的檔案），
    # 所以在這裡**列出來、不寫成列**（deliverable 4 原文「寫不成形狀的列出來並說明」）：
    #   · `[[` 緊接管線之後（bracket 起始誤判，master 第 5(a) 列）——需要 `((`／`[[` 詞法維度
    #   · ANSI-C `\xHH`／`\NNN` 逃脫（decode 回歸，master 第 5(b) 列）——需要 ANSI-C 逃脫維度
    #   · `${…:-$[` 巢狀舊式算術（`_param_end` fail-closed 守衛，master 第 5(c) 列）——需要巢狀算術維度
    #   · 命令替換內的 `case … in`（`_cmdsub_end` 深度，master 第 7 列）——需要命令替換巢狀 case 維度
    #   · block 內文只有 tab／空白的行（dedent 邊界，master 第 10 列）——需要 tab-blank-line 維度
    #   · workflow 根層級 `defaults:` 用 flow 形式（master 第 13 列）——**已有既有 fixture**
    #     （`ci-log-filter-bypass-r37b-strict-defaults-root-run-flow.yml`），但本組 `shellgen.py --strict`
    #     沒有把它做成產生維度（六個維度封閉列舉裡沒有「defaults 根層級 flow」這一項，見檔頭）
    #   · heredoc 分隔字詞含未配對 `${`／`$[`（master 第 14 列）——需要分隔字詞構造維度
    #   · 管線後未收尾的 `$(`／反引號／`((`／`[[`／`$[`／`(`（master 第 15 列）——需要未收尾構造維度
    #   ·（master 第 16 列後半的 `"${VAR:-…'…}"` 不列：R36 那一例寫「bash 把 `'` 當字面」是錯的——bash 5.3 實測
    #     是語法錯誤、lint 的 PARSE 正確，R37 沒有為它加機制，也就沒有要普查的形狀）
    #   · `shopt -s extglob`（master 第 17 列）——需要 extglob 詞法維度
    #   · `|&` 在行尾續行（master 第 21 列，LOW）——需要續行維度
    #   · `runs-on:` 帶行尾 `#` 註解（master 第 22 列前半，LOW）——需要 runs-on 註解維度
    #   · `case … in` 模式含 `|`（master 第 22 列後半，LOW）——需要 case 模式維度
    # 這些機制目前只由 repo 既有的 `test/fixtures/ci-log-filter-bypass-r37{b,c,d,e}-*.yml`／
    # `good-r37{b,c,d,e}-*.yml` 覆蓋（selftest 對帳），不是本組 `shellgen.py --strict` 的產物；等負責
    # r37c／r37d／r37e 的修法包各自把對應維度加進 `shellgen.py`，才把這些列一起加回來（同一個 PR 內，
    # 不要提前開一個會紅的閘門）。
    ("R37-1 多段管線（同一行 ≥2 個 `|`，不含 `||`）",
     lambda text, runs: any(len(re.findall(r"(?<!\|)\|(?!\|)", hollow(l))) >= 2 for run in runs for l in run.split("\n"))),
    ("R37-2 shell 值是 bash 樣板但不是純關鍵字 `bash`（帶 `{0}`）",
     raw(r"^\s*(?:- )?shell:\s*.*bash.*\{0\}")),
    ("R37-3 雙引號內出現 `$(`（命令替換巢狀在雙引號裡）",
     lambda text, runs: any(re.search(r'"[^"]*\$\(', l) for run in runs for l in run.split("\n"))),
    # 這一列**刻意不用 `hollow()`**：`hollow()` 會把引號內容挖成空白，`>&"2"` 的 `2` 正是要偵測的目標，挖掉就
    # 測不到。改用「逐一找 `>&` 後面的數字，只要有任何一個不是單獨的 `1`」——比對排除 `2>&1`（strict 要求的
    # 合規收尾）本身這個常見的假警報（第一版用整行排除 `>&1\b`，而每個合規檔都帶 `2>&1`，整行排除把三個
    # 拼法全部誤判成 0；改成逐一比對後才量到非零檔數——目前在 `--strict` 語料上實測是 11 檔，不是 3 檔）。
    ("R37-4 fd 複製到非 1/2、或加引號／前導零的拼法（`>&02`／`>&\"2\"`）",
     lambda text, runs: any(re.search(r'>&"?0*[02-9]"?(?!\d)', l) for run in runs for l in run.split("\n"))),
    ("R37-5 重導向目標落在 /dev 或 /proc（fd 流向白名單以外）",
     lambda text, runs: any(re.search(r'>\s*"?/(?:dev|proc)/', l) for run in runs for l in run.split("\n"))),
    ("R37-6 env: 帶 SHELLOPTS／BASHOPTS／BASH_ENV／BASH_XTRACEFD／ENV",
     raw(r"^\s*(?:SHELLOPTS|BASHOPTS|BASH_ENV|BASH_XTRACEFD|ENV):\s")),
    ("R37-7 `{ …; }` 或 `( … )` 收尾後緊接 `2>&1 |`（群組豁免的觸發條件）",
     lambda text, runs: any(re.search(r"[)}]\s*2>&1\s*\|", hollow(l)) for run in runs for l in run.split("\n"))),
    ("R37-8 shell: 的值加引號（`\"bash\"`／`'bash'`）",
     raw(r"""^\s*(?:- )?shell:\s*["']""")),
    ("R37-9 雙引號內出現 `$((`（算術與 heredoc 判定的交互）",
     lambda text, runs: any(re.search(r'"[^"]*\$\(\(', l) for run in runs for l in run.split("\n"))),
    ("R37-10 反引號命令替換內含 `#`（合併時修的收尾判定）",
     lambda text, runs: any(re.search(r"`[^`]*#[^`]*`", l) for run in runs for l in run.split("\n"))),
    ("any heredoc（分母參考）", sh(lambda run, hd: True)),
    ("any `<<-`（分母參考）", sh(lambda run, hd: hd[3])),
]


def _folded_blocks(text):
    """每個 `run: >` 區塊的內文行（原始文字，含縮排）。"""
    lines = text.split("\n")
    for i, l in enumerate(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*>[+-]?\d?[+-]?\s*(?:#.*)?$", l)
        if not m:
            continue
        base = len(m.group(1)) + (2 if l.lstrip().startswith("- ") else 0)
        body, j = [], i + 1
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > base):
            body.append(lines[j]); j += 1
        yield body


def _folded_backslash_then_break(text):
    """R35-2：折疊區塊裡以 `\\` 結尾的內容行，後面緊接空行或 more-indented 行——`_next_phys` 會跳過佔位的地方。"""
    for body in _folded_blocks(text):
        pad = min((len(b) - len(b.lstrip()) for b in body if b.strip()), default=0)
        for a, b in zip(body, body[1:]):
            if a.rstrip().endswith("\\") and (not b.strip() or b[pad:][:1] in (" ", "\t")):
                return True
    return False


def _folded_leading_blank(text):
    """R35-12：折疊區塊的第一行是空行。"""
    return any(body and not body[0].strip() for body in _folded_blocks(text))


def _folded_run_three_plus(text):
    """`run: >` 底下有沒有**三行以上**連續的內容行（剝掉區塊縮排後不再有前導空白、且非空行）。

    為什麼是 3 不是 2（R32 DA-2）：前一版的 `fold_block` 兩兩折，兩行的情形**恰好正確**，
    所以「有折疊 block scalar」這個形狀（D-fold）計得到、卻對那個缺陷完全不靈敏。
    觸發條件是**折疊鏈長度 ≥ 3**，形狀就要照那個條件寫。"""
    lines = text.split("\n")
    for i, l in enumerate(lines):
        # **key 限定 `run`**（#33 verify R34 regression M-1；文字更正見 #33 verify R36 第 24 列）：前一版收
        # 任何 key 的 `>`，野外綠分母那 13 檔裡**最多的是 `if:`（6 檔）**，`stale-issue-message:` 只有 2 檔（其餘 5 檔散在別的 key，未逐一列出）——
        # 折疊的 run 區塊是 0 檔，而 CHANGELOG 據此說「野外 0/0 對本輪任何一個機制都不是證據」（這句話正是這次 key 限定修法（regression M-1）的直接產物（分母從 13 塌縮到 0），不是不受影響；不受影響的只是
        # 前一句「全部是 stale-issue-message: > 之類」的舉例本身仍不準，兩輪對外宣稱查核都只看過散文、沒看這裡）。
        m = re.match(r"^(\s*)(?:- )?run:\s*>[+-]?\d?[+-]?\s*(?:#.*)?$", l)
        if not m:
            continue
        base = len(m.group(1)) + (2 if l.lstrip().startswith("- ") else 0)
        body, j = [], i + 1
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > base):
            body.append(lines[j]); j += 1
        if not body:
            continue
        pad = min((len(b) - len(b.lstrip()) for b in body if b.strip()), default=0)
        run_len = 0
        for b in body:
            stripped = b[pad:]
            flush = bool(stripped.strip()) and stripped[:1] not in (" ", "\t")
            run_len = run_len + 1 if flush else 0
            if run_len >= 3:
                return True
    return False


def _flow_colon_in_jobs(text):
    top = None
    for l in structural_lines(text):
        m = re.match(r"^([A-Za-z_][\w-]*):(?:\s|$)", l)
        if m:
            top = m.group(1)
        mv = re.match(r"^\s+(?:- )?[\w-]+:\s*([{\[].*)$", l)
        if mv and top == "jobs" and ":" in hollow(mv.group(1)):
            return True
    return False


def read_list(p):
    """讀語料清單；**解不開的路徑一律 fail-loud**（R30 MB-6，與 `threeaxis.py` 同一個理由）。
    前一版對解不開的清單印出一整欄 0 並 rc=0——那與「這些形狀在語料裡出現 0 次」長得一模一樣。"""
    out, missing = [], []
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if l and not l.startswith("#"):
            parts = l.split(None, 1)
            path = parts[1].strip() if len(parts) == 2 else parts[0]
            (out if pathlib.Path(path).is_file() else missing).append(path)
    if missing:
        print("✗ 語料清單有 %d／%d 個路徑解不開（前三個：%s）——形狀表不會印出來，"
              "因為一整欄 0 與「這些形狀真的是 0」分不出來。"
              % (len(missing), len(missing) + len(out), ", ".join(missing[:3])), file=sys.stderr)
        sys.exit(2)
    return out


def main(argv):
    # `--require-nonzero PREFIX`：以 PREFIX 開頭的每一列在**第一份清單**上都必須 > 0，否則 rc=1。
    # 這是 G-R32-DA-5 的閘門：「一個沒有普查列（或列是 0）的機制不得出貨」。散文規則一輪就失守
    # （R31 遵守、R32 破壞），所以改成 CI 會紅的東西。
    require = None
    if "--require-nonzero" in argv:
        k = argv.index("--require-nonzero"); require = argv[k + 1]; argv = argv[:k] + argv[k + 2:]
    if not argv:
        print(__doc__); return 2
    cols = []
    for lst in argv:
        files = read_list(lst)
        counts = [0] * len(SHAPES); yaml_fail = 0; non_utf8 = 0
        for f in files:
            try:
                text = pathlib.Path(f).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                non_utf8 += 1; continue        # 另計一欄，不是 traceback、也不是靜默 0
            except OSError:
                non_utf8 += 1; continue
            try:
                runs = runs_of(text)
            except yaml.YAMLError:
                yaml_fail += 1; runs = []
            for k, (_name, pred) in enumerate(SHAPES):
                try:
                    if pred(text, runs):
                        counts[k] += 1
                except Exception:
                    pass
        cols.append((pathlib.Path(lst).name, len(files), yaml_fail, counts, non_utf8))
    w = max(len(n) for n, _p in SHAPES)
    print("%-*s" % (w, "形狀 \\ 清單（檔數／PyYAML 拒／非 UTF-8）")
          + "".join("  %20s" % ("%s(%d/%d/%d)" % (n[:10], t, yf, nu)) for n, t, yf, _, nu in cols))
    for k, (name, _p) in enumerate(SHAPES):
        print("%-*s" % (w, name) + "".join("  %20d" % c[k] for _n, _t, _yf, c, _nu in cols))
    first_col = [(name, cols[0][3][k]) for k, (name, _p) in enumerate(SHAPES)]
    if require is not None:
        zero = [name for name, cnt in first_col if name.startswith(require) and cnt == 0]
        if zero:
            print("\n✗ 以下機制在第一份語料上是 0 檔——分母裡沒有這個形狀，它的 GREEN→RED 數字不是證據（G-R32-DA-5）：",
                  file=sys.stderr)
            for name in zero: print("  -", name, file=sys.stderr)
            return 1
        print("\n✓ %s* 的每一列在第一份語料上都 > 0" % require)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
