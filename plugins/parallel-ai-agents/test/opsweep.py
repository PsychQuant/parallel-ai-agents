#!/usr/bin/env python3
"""作者無關的運算子突變掃描：對 `lint-ci-log-filter.sh` 內嵌的 Python 逐一套用**固定的**運算子，看 `--selftest` 抓不抓得到。

為什麼還要這一支（#33 verify R28 DA 的中心診斷）：`mutation_check.py` 的具名靶是**作者挑的**——RED 驗證的對象、
突變的選擇、fixture 的內容，三者都由剛寫完那段程式碼的人決定。R28 的 DA 用固定運算子掃 R26 的新機制，
62 個突變體 29 個存活，其中四個是**當輪剛修好的機制**（`probe == delim`、`balanced`、`top_key == "jobs"`…）——
靶清單裡沒有它們，因為作者沒想到要放。這一支把「挑」拿掉：運算子集合是封閉的、套用位置由 AST 決定，
作者剩下的選擇只有 EXPECTED_SURVIVE（而那個集合的每一條都要能回答「為什麼等價」，且受下方比例上限約束）。

運算子（封閉列舉，五種；改動這個集合是另一次 change）：
  strip→id       `x.strip()/.rstrip()/.lstrip()` 的呼叫換成 `x`
  ±1→±2          `+= 1`／`-= 1` 換成 `+= 2`／`-= 2`
  drop-operand   `a and b`／`a or b` 拿掉其中一個運算元（整個運算式換成其餘運算元各自加括號接回去）
  startswith→F   `x.startswith(...)` 換成 `False`
  ==↔!=          `==` 換成 `!=`

用法：
  test/opsweep.py --since REF   只掃「自 REF 起被改動的區域」：被 diff 觸及的**整個函式**，加上模組層**新增／改動的行**
                                （R28 DA 指定的守備範圍：`git diff db0c0f2..HEAD` 觸及的函式；模組層以行文本比對）
  test/opsweep.py               整段內嵌 Python（不分區域；數字只供揭露，收手條件用 --since）
  test/opsweep.py --list        只列突變體 id 與數量，不跑
  test/opsweep.py --json F      把結果寫成 JSON（CI／量測用）
  test/opsweep.py --jobs N      同時跑 N 個突變體（判定不變，只改完成順序與耗時）
退出碼：有**非預期**存活或**預期存活被殺**（等價性不再成立）→ 1；否則 0。

EXPECTED_SURVIVE 的紀律（G-R29-5）：
  (a) 每一條要寫理由，且理由是「依構造等價」——不是「fixture 沒蓋到」；後者的正解是補會翻色的 fixture。
  (b) 修法型的突變體（關掉一個當輪剛修好的機制）**不得**列入——那正是「新機制沒有網」。
  (c) 集合大小 ≤ 存活總數的 1/3（含預期）；超過就是在用這個集合藏東西（R13 DA-5）。程式會檢查。
"""
import argparse
import ast
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent          # plugins/parallel-ai-agents/test
PLUGIN = HERE.parent
LINT = HERE / "lint-ci-log-filter.sh"

# 突變體 id 的形狀：`<op>|<函式>|<該行去空白的原文>|<同一行第幾個>`。用原文不用 offset：offset 會隨任何改動漂移，
# 原文只在那一行真的改了才變——而那時本來就該重新判讀。
EXPECTED_SURVIVE = {   # id → 理由（依構造等價）。每一條都要能回答「為什麼關掉它沒有任何輸出會變」
    # `len(v) >= 2` 只擋單一字元的 `'`／`"`：那是沒收尾的引號，不是合法 YAML（PyYAML ScannerError、GitHub
    # 「workflow file issue」），runner 不會跑。拿掉守衛只改變 lint 對無效輸入的訊息，不改變任何合法輸入的判定。
    "drop-operand|yaml_decode_scalar|if len(v) >= 2 and v[0] == v[-1] == \"'\":|1": "單字元 `'` 是沒收尾的引號、非合法 YAML；守衛只防越界",
    "drop-operand|yaml_decode_scalar|if len(v) >= 2 and v[0] == v[-1] == '\"':|1": "單字元 `\"` 同上",
    # R30 MB-11／Codex 第 4 條：這一條的「依構造等價」**是假的**——引號 heredoc 的分隔字可以是空白
    # （`cat <<' '`），於是「剝不剝純空白行」會改變 heredoc 有沒有終止。R31 採納突變體的答案：
    # `dedent_block` 現在對**每一行**剝（YAML 就是這樣），這一條從 EXPECTED_SURVIVE 移除，
    # 並由 `good-whitespace-heredoc-delimiter` fixture 釘住。留這段註解當紀錄：
    # **「依構造等價」若沒有一條會翻色的指令在守，它就只是一句散文**（R30 §六 擴寫後的第 8 類）。
    # `<<<` 分支關掉後落到 `<<` 分支，分隔字從第三個 `<` 起讀、而 `<` 在 SHELL_WORD_BREAK 裡 → delim 空 →
    # 不排 heredoc。依構造等價；分支保留是把「here-string 不是 heredoc」寫成程式碼（mutation_check 同一條理由）。
    "startswith→F|shell_scan|if line.startswith(\"<<<\", i):|1": "落到 `<<` 分支後 delim 為空，不排 heredoc",
    # **R32 DA-2 之後，`fold_block` 在這裡只剩一條。** R31 列了四條，只有一條理由明白點名「佔位的空字串讓
    # 下一行不再折」（另外兩條說的是 `more`／`prev_more` 已擋住折疊，第四條說的是折進去的只差行尾空白）——那句話描述的就是那個缺陷本身（兩兩折而非遞移折）。等價論證的根據是 bug，
    # 論證就隨 bug 一起作廢，**不得改寫後沿用**。R32 重寫了 `fold_block`（遞移）；**「對 PyYAML
    # 逐行相符」這句話 R37 改成有範圍、可重跑的量測**（#33 verify R36 requirements 第 20 列）：
    # `test/corpus/foldcheck.py` 窮舉「10 空白基準縮排 ＋ 7 種前導（含 tab）× 3 種內容（空、`x`、帶行尾空白的
    # `x `）＋ 真正的空行」這 22 種行的所有組合，`run: |` 與 `run: >` 各比一次整字串與內容承載行。
    # 現行 lint：3 行各 6,518 組、4 行各 136,660 組合法 YAML，**整字串全部相等**；負對照 380e4a4（修 R36 第 10 列
    # 的 tab 首行之前）3 行就有 literal 462 組、folded 588 組內容承載行不符。範圍外（沒有量、不宣稱）：5 行以上、
    # 這 22 種以外的行形、`|N`／`>N` 顯式縮排指示子、chomping 指示子。
    # R37 的 e 包曾在這裡寫「blank-line 的計數／位置另有一個既有的簡化」並指向一段不存在的說明，
    # 它自己的窮舉指令碼沒有進 repo、合併時已經找不到；上面那支工具在同一類構造下量不到任何空白行差異，所以刪掉。
    # 它的突變體由 `--since` 掃描重新判讀：殺不掉的先補 fixture，真的依構造等價才回到這裡、且理由要能
    # 用 `--verify-expected` 在產生語料上跑出來。
    # **R33 曾在這裡列「折進去的那一段要不要 `strip()`」，R37 證明那一條也是假的**（#33 verify R36
    # logic 第 11 列）：`--verify-expected` 用的產生語料裡「內容行帶行尾空白」這個維度（`shapes.py`
    # R35-13）**只有 2 檔命中**，是**誠實邊界沒被兌現**——理由寫著「機械證據：642 檔上逐檔相同」，
    # 聽起來像是「這個維度沒被測到」，但正確的講法是**測到了、只是分母小到不足以踩出分歧**（2 檔裡
    # 剛好都沒有讓 `l.strip()` 在 heredoc 分隔字比對上翻色的組合）；逐檔相同不代表等價，只代表這 2 個
    # 樣本沒有踩到分歧點。R36 DA 用突變體本身（把 `.strip()` 拿掉、也就是這裡曾經
    # 列的那個 id）反手證明：PyYAML 折疊只在兩個內容行之間插入一個空白、不動任一行本身的內容，
    # `l.strip()` 悄悄把**行尾**空白也吃掉，而 heredoc 分隔字比對用的正是沒被折走的整行——分隔字恰好
    # 是空白時（`cat <<' '` 這一族）差一個字元就是有沒有終止的差別。拿掉 `.strip()` 之後 selftest 數字
    # 不變（108／100／68），而它讓 `ci-log-filter-bypass-r37e-fold-trailing-space-terminator` 這類探針
    # 從「lint 誤判 heredoc 已收尾、pass」翻成正確的 RULE。這是同一句規則第二次踩：**「依構造等價」若
    # 沒有一條會翻色的指令在守，它就只是一句散文**——上面那句話本身就在講這件事，這裡曾經違反了它。
    # R33：`prev_flush_content` 裡的 `acc is not None`。`acc` 為 None 只有兩種時刻：區塊開頭、或剛結束一個空行段——
    # 而空行段會把**連續的**空行一次吃完，所以下一次進到空行段時 `acc` 必然已被一個內容行設定。唯一到得了的
    # 情形是**區塊開頭的前導空行**：拿掉運算元會把它折成佔位，而一個前導空行在 shell 裡什麼都不是（空的
    # code 行），判定不變。`--verify-expected` 在 624 檔上逐檔相同（#33 verify R37：語料自 R35 起
    # 是 624 檔，不是 642——642 是 R33／R34 當時的舊數字，這裡先前照抄了那個數字沒跟著改）。
    "drop-operand|fold_block|prev_flush_content = acc is not None and not prev_more     # 同上：acc 非 None ⇒ 非空內容行|1": "只在區塊開頭的前導空行到得了；前導空行在 shell 裡沒有效果",
    # R31：`run` key 守恆式的計數增量。這個突變體**不關掉機制**，只把計數加得更多——而 `found` 唯一的
    # 消費者是 `found > accounted`，`accounted ∈ {0, 1}`：
    #   accounted = 0 → 原版 found ≥ 1 > 0，突變體 ≥ 2 > 0，兩邊都 reject；
    #   accounted = 1 → 那個沒引號的 `run` key 本身會被 `PLAIN_RUN_KEY` 數到，所以進迴圈前 found ≥ 1，
    #                   加完原版 ≥ 2 > 1、突變體 ≥ 3 > 1，兩邊也都 reject。
    # 也就是說**只要這一行執行到，兩版的判定必定相同**；差別只在訊息裡印的那個數字，而 fixture 比的是
    # pass／rule-red／parse-red，不是訊息文字。
    "±1→±2|<module>|found += 1|1": "`found` 只用於 `found > accounted`，而這一行執行到時兩版都必然 reject",
    # R31：邏輯行組裝前的正規化。`cs` 只餵給兩個地方：`PIPED_RE.search`（搜尋，不受前後空白影響）與
    # `elif cs:`。差別只有「純空白的 code 行」——原版跳過，突變體推成一條邏輯行。而純空白的邏輯行
    # 既不可能命中 `PIPED_RE`，也不可能命中 `CONT_RE`（它要求結尾是 `|`／`||`／`&&`），所以它當上
    # `logical[-1]` 之後，下一行的續接判定**兩版都是否**；至於接進去時多出來的那段空白，同樣被
    # `PIPED_RE` 的 `\\s*` 吸收。
    "strip→id|<module>|cs = c.strip()|1": "純空白的邏輯行對 `PIPED_RE`／`CONT_RE` 都不成立，多出的空白被 `\\s*` 吸收",
}


def embedded_python(src):
    """回傳 (python 原始碼, 在 src 裡的起點)。"""
    head, rest = src.split("<<'PY'\n", 1)
    py, _tail = rest.rsplit("\nPY", 1)
    return py, len(head) + len("<<'PY'\n")


def _span(py_lines, node):
    """(start_offset, end_offset) in the python text, from ast line/col (0-based col, 1-based line).

    ast 的 col_offset／end_col_offset 是 **UTF-8 位元組**位置，不是字元位置。R37 以前這裡直接加，
    同一行在節點前面有中文的節點就切錯位置——`==↔!=` 會找不到 `==` 而當掉，其他運算子則是
    **安靜地**替換到別的文字上。這支工具 R28 進 repo 之後，查過的四個 lint 版本（d278e99、d8340a6、6cf6864、380e4a4）各有 3 個這樣的節點（`縮排含 tab` 那行的
    `i += 1`、`cur["name"]` 那行的 `or`、`而不解析就不放行` 那行的 `.strip()`），一直沒人發現；R37 的 lint
    多了 3 個，其中兩個是 `==`，量測時當掉才看到。"""
    starts = [0]
    for l in py_lines:
        starts.append(starts[-1] + len(l) + 1)

    def col(lineno, byte_col):
        return len(py_lines[lineno - 1].encode()[:byte_col].decode())
    return (starts[node.lineno - 1] + col(node.lineno, node.col_offset),
            starts[node.end_lineno - 1] + col(node.end_lineno, node.end_col_offset))


def mutants(py):
    """依固定運算子產生 [(id, start, end, replacement)]。id 由 (op, 所在函式, 行原文, 行內序號) 組成。"""
    tree = ast.parse(py)
    lines = py.split("\n")
    func_of = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                func_of.setdefault(id(n), fn.name)
    raw = []

    def add(op, node, start, end, new, part=None, cut=None):
        # 切到的文字必須就是這個運算子的原文——位置算錯時要當場失敗，不能安靜地突變到別的文字上
        # （_span 的位元組／字元混用就是這樣藏了好幾輪）。drop-operand 的切片含 and/or 與空白，只驗被拿掉的運算元在內。
        want = {"==↔!=": "==", "±1→±2": "1"}.get(op) or ast.get_source_segment(py, part or node)
        got = py[start:end]
        if (want not in got) if part is not None else (got != want):
            raise SystemExit("opsweep: %s 在第 %d 行切到 %r，應該是 %r——位置計算錯了" % (op, node.lineno, got, want))
        # 排序鍵與行號用 (start, end)——id 的序號由它決定，不能動；實際替換的範圍與文字可以另給（cut）。
        raw.append(((start, end, op, func_of.get(id(node), "<module>"), lines[node.lineno - 1].strip(), new),
                    cut or (start, end, new)))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("strip", "rstrip", "lstrip"):
                s, e = _span(lines, node); vs, ve = _span(lines, node.func.value)
                add("strip→id", node, s, e, py[vs:ve])
            elif node.func.attr == "startswith":
                s, e = _span(lines, node)
                add("startswith→F", node, s, e, "False")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, (ast.Add, ast.Sub)) \
                and isinstance(node.value, ast.Constant) and node.value.value == 1:
            s, e = _span(lines, node.value)
            add("±1→±2", node, s, e, "2")
        elif isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            spans = [_span(lines, v) for v in node.values]
            bs, be = _span(lines, node)
            word = " and " if isinstance(node.op, ast.And) else " or "
            for k in range(len(node.values)):
                # 拿掉第 k 個運算元。(s, e) 是它連同前面（或它是第一個時後面）的 `and`/`or` 的範圍，只用來排序與驗位置；
                # **實際的突變是把整個布林運算式換成其餘運算元各自加括號再接回去**。R37 以前直接刪 (s, e)，
                # 而運算元外面的括號不在 AST 節點的範圍裡，`(a or (b and c))` 拿掉 a 會刪到 `a or (`——括號不平衡、
                # 程式碼壞掉，那個位置等於沒量（R37 的 lint 全段 1044 個突變體裡有 46 個這樣）。
                if k == 0:
                    s, e = spans[0][0], spans[1][0]
                else:
                    s, e = spans[k - 1][1], spans[k][1]
                rest = word.join("(%s)" % ast.get_source_segment(py, v) for i, v in enumerate(node.values) if i != k)
                add("drop-operand", node, s, e, "", part=node.values[k], cut=(bs, be, rest))
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            ls, le = _span(lines, node.left); rs, re_ = _span(lines, node.comparators[0])
            gap = py[le:rs]
            k = gap.index("==")
            add("==↔!=", node, le + k, le + k + 2, "!=")
    # 依原始碼位置排序後再編序號：同一函式裡同一行原文（`i += 1; continue` 這種）出現多次時，序號是
    # 「第幾次出現」——與行號無關，所以插入一行註解不會讓 id 漂移。
    out, seen = [], {}
    starts = [0]
    for l in lines:
        starts.append(starts[-1] + len(l) + 1)
    for (pos, _e, op, fn, line, _new), (start, end, new) in sorted(raw, key=lambda r: r[0]):
        key = (op, fn, line)
        seen[key] = seen.get(key, 0) + 1
        lineno = next(k for k in range(len(lines), 0, -1) if starts[k - 1] <= pos)
        out.append(("%s|%s|%s|%d|L%d" % (op, fn, line, seen[key], lineno), start, end, new))
    return out


def region_since(ref, py):
    """回傳述詞 mutant → 是否在區域內。區域 = 被 `git diff REF` 觸及的函式全部 ＋ 模組層新增／改動的行。
    「觸及」用函式原始碼逐行去空白比對；模組層用行文本是否存在於 REF 版判斷（改名也算新——保守方向）。"""
    base_src = subprocess.run(["git", "-C", str(PLUGIN), "show", "%s:%s" % (ref, LINT.relative_to(PLUGIN.parent.parent))],
                              capture_output=True, text=True, check=True).stdout
    base_py, _ = embedded_python(base_src)
    # **區域＝真正的變更行**（R30 MB-13／Codex 第 1 條）。前一版有兩個洞：
    #   函式層用「去空白後的文字」比對——只改縮排（＝改控制流）而文字相同的函式判成沒動；
    #   模組層用「文字集合」——新增一行與檔案別處相同的文字（`kind[i] = "BAD"; i += 1`）判成舊行。
    # 兩者都不是「被 diff 觸及」的意思。改用 difflib 對**行**做真正的比對：變更行的集合是答案，
    # 函式只要**有任何一行**落在變更行集合裡就整個進區域。
    import difflib
    base_lines, head_lines = base_py.split("\n"), py.split("\n")
    changed = set()
    sm = difflib.SequenceMatcher(None, base_lines, head_lines, autojunk=False)
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            changed.update(range(j1 + 1, j2 + 1))          # 1-based，對齊 ast 的 lineno
    tree = ast.parse(py)
    spans = {n.name: (n.lineno, n.end_lineno) for n in tree.body if isinstance(n, ast.FunctionDef)}
    touched = {name for name, (a, b) in spans.items() if any(a <= x <= b for x in changed)}
    in_func = {x for name in touched for x in range(spans[name][0], spans[name][1] + 1)}
    region_lines = changed | in_func

    def inside(mid):
        return int(mid.rsplit("|L", 1)[1]) in region_lines
    return inside, touched


def sample_corpus(work):
    """產生一份**形狀完整的小樣本**（每個構造維度值至少一個檔）給突變體當第二道判準。

    R30 §六 第 14 類：`opsweep` 的殺不殺只看 `--selftest`，而 selftest 餵的是**作者寫的** fixture ——
    網目對了，投餵還是作者挑的。這裡把 `shellgen.py` 的產物抽樣進來：突變體只要讓**任何一個**
    產生檔的判定改變，就算被抓到。抽樣（不是全 468 檔）是為了讓一輪跑得完：每個維度值取前兩檔，
    覆蓋所有維度值而不取完整笛卡兒積。
    """
    gen = pathlib.Path(work) / "sample"
    r = subprocess.run([sys.executable, str(HERE / "corpus" / "shellgen.py"), "--out", str(gen)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # **fail-loud，不是回空清單**（#33 verify R32：Codex 第 8 條／DA-12）。前一版失敗就 `return []`，
        # 於是第二道判準整個消失、掃描照常跑完並回綠——「網不見了」與「網什麼都沒抓到」在輸出上
        # 長得一模一樣。這一支存在的理由就是不要有那種東西。
        raise SystemExit("✗ 第二道判準無法建立：shellgen.py rc=%d\n%s"
                         % (r.returncode, (r.stdout + r.stderr)[-1500:]))
    by_dim, out = {}, []
    for f in sorted(gen.glob("*.yml")):
        for token in f.stem.split("-")[1:]:
            by_dim.setdefault(token, []).append(f)
    for token, files in sorted(by_dim.items()):
        out.extend(files[:2])
    return sorted(set(out))


def _tags(stderr):
    """從 lint 的 stderr 抽出**紅的來源標記序列**（`RULE:`／`PARSE:`），忽略訊息文字與行號。

    只比文字會讓「訊息改寫」也算殺掉（那不是行為差異）；只比 rc 會讓 `RULE:`⇄`PARSE:` 不算
    （那是行為差異）。抽出標記序列剛好落在兩者之間。"""
    return tuple(t for line in stderr.split("\n") for t in ("RULE", "PARSE") if (": %s: " % t) in line)


def run_mutant(src, py, py_off, m, work, fixtures, sample):
    """把突變後的 lint 放進臨時 plugin 樹，跑 selftest。fixtures 是**開跑時的快照**（copy，不是 symlink）：
    R29 第一輪掃到一半時作者又加了三個 fixture，之後每個突變體都因「數量與門檻不符」被判殺——整輪後半段作廢。
    lint 原始碼與 fixture 都要在同一個時間點凍結。"""
    mid, s, e, new = m
    # 語法壞掉要在跑 selftest **之前**直接判：selftest 每張 fixture 只印 stderr 的前兩行，`SyntaxError:` 那一行
    # 被截掉，下面那個「輸出裡有沒有 SyntaxError」的判準因此量不到——R37 以前這類突變體一律記成 KILLED
    # （R29、R30 DA 那個切錯位置、把 `if seq_at[i]:` 的冒號換成 2 的突變體就是這樣被算成殺掉的）。
    try:
        compile(py[:s] + new + py[e:], "<lint>", "exec")
    except SyntaxError:
        return "BROKEN"
    mutated = src[:py_off] + py[:s] + new + py[e:] + src[py_off + len(py):]
    d = tempfile.mkdtemp(dir=work, prefix="op_")
    try:
        (pathlib.Path(d) / "test").mkdir()
        p = pathlib.Path(d) / "test" / "lint-ci-log-filter.sh"
        p.write_text(mutated, encoding="utf-8")
        os.symlink(fixtures, pathlib.Path(d) / "test" / "fixtures")
        r = subprocess.run(["bash", str(p), "--selftest"], cwd=d, capture_output=True, text=True)
        out = r.stdout + r.stderr
        if r.returncode != 0 and "SyntaxError" in out:
            return "BROKEN"                 # 運算子產出不合法的程式碼：是這支的缺陷，不是套件的功勞
        if r.returncode != 0 and "Traceback" in out:
            return "CRASHED"                # 突變體讓 lint 當掉：套件抓到了，但那是「當掉」不是「判錯」——分開報
        if r.returncode != 0:
            return "KILLED"
        # selftest 沒抓到 → 再問**不是作者挑的**那份語料（形狀完整的小樣本）。
        for f in sample:
            a = subprocess.run(["bash", str(LINT), str(f)], cwd=PLUGIN, capture_output=True, text=True)
            b = subprocess.run(["bash", str(p), str(f)], cwd=d, capture_output=True, text=True)
            # **比 (rc, 紅的來源標記)，不只比 rc**（#33 verify R32：Codex 第 8 條）。
            # 本輪特別在意的 `RULE:` ⇄ `PARSE:` 轉換兩邊 rc 都是 1，只比 rc 的網對它完全不靈敏——
            # 而那正是「fail-closed 改判」這一類修法唯一會動到的東西。
            if (a.returncode, _tags(a.stderr)) != (b.returncode, _tags(b.stderr)):
                return "KILLED-BY-CORPUS"
        return "SURVIVED"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def base_id(mid):
    """去掉 id 尾端的 `|L<行號>`——行號會漂，理由不會。"""
    return mid.rsplit("|L", 1)[0]


def verify_expected(src, py, py_off, ms):
    """把每一條 `EXPECTED_SURVIVE` 的「依構造等價」**真的跑一次**（R30 MB-11／G-R31-8）。

    為什麼：「依構造等價」四個字在 R29 是散文，沒有任何會翻色的指令在守它——而其中一條是**假的**
    （`dedent_block` 的純空白行：引號 heredoc 的分隔字可以是空白）。散文擋不住這種事，差分可以。
    做法：用 `shellgen.py` 產生一份**獨立於 fixture** 的語料（作者挑不動它的形狀），對每一條
    EXPECTED_SURVIVE 逐檔比對「原碼」與「突變體」的 `(rc, stderr)`；任何一檔不同 ⟹ 不等價 ⟹ rc=1。
    """
    import shutil as _sh
    gen = pathlib.Path(tempfile.mkdtemp(prefix="opsweep-exp-")) / "gen"
    r = subprocess.run([sys.executable, str(HERE / "corpus" / "shellgen.py"), "--out", str(gen)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("✗ 產生語料失敗：\n" + r.stdout + r.stderr); return 2
    files = sorted(gen.glob("*.yml"))
    print("對 %d 檔產生語料驗證 %d 條 EXPECTED_SURVIVE 的等價論證" % (len(files), len(EXPECTED_SURVIVE)), flush=True)
    by_id = {base_id(m[0]): m for m in ms}
    rc = 0
    with tempfile.TemporaryDirectory(prefix="opsweep-exp-run-") as work:
        fixtures = pathlib.Path(work) / "fixtures"
        _sh.copytree(HERE / "fixtures", fixtures)
        for mid, why in sorted(EXPECTED_SURVIVE.items()):
            m = by_id.get(mid)
            if m is None:
                print("  ✗ %s —— 這個突變體不在本次掃描範圍內，無法驗證" % mid); rc = 1; continue
            _i, a, b, new = m
            mutated = src[:py_off] + py[:a] + new + py[b:] + src[py_off + len(py):]
            d = pathlib.Path(tempfile.mkdtemp(dir=work)); (d / "test").mkdir()
            mp = d / "test" / "lint-ci-log-filter.sh"; mp.write_text(mutated, encoding="utf-8")
            os.symlink(fixtures, d / "test" / "fixtures")
            diffs = []
            for f in files:
                o1 = subprocess.run(["bash", str(LINT), str(f)], cwd=PLUGIN, capture_output=True, text=True)
                o2 = subprocess.run(["bash", str(mp), str(f)], cwd=d, capture_output=True, text=True)
                if (o1.returncode, o1.stderr.replace(str(LINT), "L")) != (o2.returncode, o2.stderr.replace(str(mp), "L")):
                    diffs.append(f.name)
            _sh.rmtree(d, ignore_errors=True)
            if diffs:
                rc = 1
                print("  ✗ %s\n     理由寫的是「%s」，但這 %d 檔上原碼與突變體給出不同答案（前三：%s）"
                      % (mid, why, len(diffs), ", ".join(diffs[:3])))
            else:
                print("  ✓ %s（%d 檔全部相同）" % (mid, len(files)))
    _sh.rmtree(gen.parent, ignore_errors=True)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--list", action="store_true", help="只列突變體，不跑")
    ap.add_argument("--json", metavar="FILE", help="結果寫成 JSON")
    ap.add_argument("--since", metavar="REF", help="只掃自 REF 起被改動的區域（見 docstring）")
    ap.add_argument("--verify-expected", action="store_true",
                    help="把每一條 EXPECTED_SURVIVE 的「依構造等價」真的跑一次（見 docstring）")
    ap.add_argument("--jobs", type=int, default=1, metavar="N", help="同時跑幾個突變體（預設 1）")
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error("--jobs 至少是 1")
    src = LINT.read_text(encoding="utf-8")
    py, py_off = embedded_python(src)
    ms = mutants(py)
    all_ids = [m[0] for m in ms]          # **陳舊性檢查對全集做**，不對區域做：
                                          # 區域外的 EXPECTED_SURVIVE 本來就不會出現在區域清單裡，
                                          # 拿區域清單去判「這個 key 還在不在」會對每一條區域外的條目誤報。
    scope = "整段內嵌 Python"
    if args.since:
        inside, touched = region_since(args.since, py)
        ms = [m for m in ms if inside(m[0])]
        scope = "自 %s 起的區域（觸及的函式：%s；加模組層新行）——全集 %d 個中的 %d 個" % (
            args.since, ", ".join(sorted(touched)) or "無", len(all_ids), len(ms))
    ids = all_ids
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        print("✗ 突變體 id 不唯一（同一行同一運算子要靠序號分開，這裡分不開）：", sorted(dup)[:5]); return 2
    # `EXPECTED_SURVIVE` 的 key **不含行號**：行號會隨任何插入而漂，而理由不會。
    # id 的行號尾巴只給區域判定用。
    stale = sorted(set(EXPECTED_SURVIVE) - {base_id(i) for i in ids})
    if stale:
        print("✗ EXPECTED_SURVIVE 裡有不存在的突變體（那一行改了，理由要重判）：")
        for x in stale: print("  -", x)
        return 2
    print("%d 個突變體（五種運算子；%s）" % (len(ms), scope), flush=True)
    if args.list:
        for m in ms: print("  ", m[0])
        return 0
    if args.verify_expected:
        return verify_expected(src, py, py_off, ms)
    t0 = time.monotonic()
    pre = subprocess.run(["bash", str(LINT), "--selftest"], cwd=PLUGIN, capture_output=True, text=True)
    if pre.returncode != 0:
        print("✗ 未突變的 selftest 就紅——先修綠再掃，否則每個突變體都會被誤判為殺掉。\n" + (pre.stdout + pre.stderr)[-1500:]); return 1
    results = {}
    with tempfile.TemporaryDirectory(prefix="opsweep-") as work:
        fixtures = pathlib.Path(work) / "fixtures"
        shutil.copytree(HERE / "fixtures", fixtures)
        sample = sample_corpus(work)
        if not sample:
            # 取樣為空 = 沒有第二道判準。前一版只印數字，而 0 印出來與 40 印出來一樣不引人注意。
            raise SystemExit("✗ 第二道判準的樣本是空的——掃描會退化成只問 selftest，拒絕繼續")
        print("   第二道判準：%d 個產生檔（形狀完整樣本，非作者挑選）" % len(sample), flush=True)

        def one(m):
            return m[0], run_mutant(src, py, py_off, m, work, fixtures, sample)
        # 每個突變體在自己的 mkdtemp 裡跑、只讀共用的 fixture 快照與樣本，彼此沒有依賴；--jobs 只改完成順序，
        # 不改任何一個突變體的判定（R37：區域 868 個突變體循序估計要 8 小時）。
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for mid, st in pool.map(one, ms):
                results[mid] = st
                tag = st if not (st == "SURVIVED" and base_id(mid) in EXPECTED_SURVIVE) else "EXPECTED"
                print("  %-9s %s" % (tag, mid), flush=True)
    elapsed = time.monotonic() - t0
    survived = [i for i, st in results.items() if st == "SURVIVED"]
    unexpected = [i for i in survived if base_id(i) not in EXPECTED_SURVIVE]
    expected = [i for i in survived if base_id(i) in EXPECTED_SURVIVE]
    killed_expected = [i for i in EXPECTED_SURVIVE if any(base_id(k) == i and v == "KILLED" for k, v in results.items())]
    broken = [i for i, st in results.items() if st == "BROKEN"]
    print("\n耗時 %.1f 分 / %d 突變體（--jobs %d）= 每個 %.1f s 牆鐘" % (elapsed / 60, len(ms), args.jobs, elapsed / max(1, len(ms))))
    crashed = [i for i, st in results.items() if st == "CRASHED"]
    by_corpus = [i for i, st in results.items() if st == "KILLED-BY-CORPUS"]
    print("殺掉 %d（其中當掉 %d、**產生語料抓到而 selftest 沒抓到的 %d**）/ 存活 %d（非預期 %d、預期 %d）/ 壞掉（語法）%d"
          % (sum(1 for st in results.values() if st in ("KILLED", "CRASHED", "KILLED-BY-CORPUS")), len(crashed),
             len(by_corpus), len(survived), len(unexpected), len(expected), len(broken)))
    if by_corpus:
        print("\n這些突變體 **selftest 沒抓到、產生語料抓到了** —— 每一個都代表 fixture 集缺一個形狀：")
        for i in by_corpus: print("  -", i)
    rc = 0
    if unexpected:
        rc = 1
        print("\n✗ 非預期存活（補會翻色的 fixture，或證明等價後列入 EXPECTED_SURVIVE 並寫理由）：")
        for i in unexpected: print("  -", i)
    if killed_expected:
        rc = 1
        print("\n✗ 預期存活卻被殺掉（等價性不再成立，從 EXPECTED_SURVIVE 移除）：")
        for i in killed_expected: print("  -", i)
    # 兩條上限：(1) 工具內守「EXPECTED_SURVIVE ≤ 本次掃描突變體數的 10%」——修完之後存活的只剩預期的，
    # 「≤ 存活的 1/3」在工具裡會退化成永遠失敗；(2) 每輪「新增條數 ≤ 該輪存活數的 1/3」是**審查規則**，
    # 對照該輪修法前的 sweep log 在 PR body 檢查（R29：30 存活 → 4 條預期 = 13%）。
    cap = len(ms) // 10
    if len(EXPECTED_SURVIVE) > cap:
        rc = 1
        print("\n✗ EXPECTED_SURVIVE（%d）超過本次突變體數的 10%%（上限 %d）——這個集合在藏東西" % (len(EXPECTED_SURVIVE), cap))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({"results": results, "elapsed_s": elapsed}, ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
