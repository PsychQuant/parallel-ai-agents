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
    ("any heredoc（分母參考）", sh(lambda run, hd: True)),
    ("any `<<-`（分母參考）", sh(lambda run, hd: hd[3])),
]


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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
