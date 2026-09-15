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


SHAPES = [
    ("D1  heredoc 終止行帶尾端空白/tab（lint 前一版 rstrip 後相等）",
     sh(lambda run, hd: hd[4] is not None and run.split("\n")[hd[4]] != run.split("\n")[hd[4]].rstrip())),
    ("D2  未引號分隔字含反斜線（`<<E\\OF`）",
     sh(lambda run, hd: "\\" in hd[1] and not hd[2])),
    ("D3  未引號 heredoc 內文最後一行以反斜線結尾",
     sh(lambda run, hd: (not hd[2]) and "\\" not in hd[1] and bool(hd[5]) and hd[5][-1].endswith("\\"))),
    ("D4  同一實體行先 `((`/`$((` 再 `<<`",
     lambda text, runs: any(re.search(r"\(\(.*<<", hollow(l)) for run in runs for l in run.split("\n"))),
    ("D5  `run: |N`／`>N` 顯式縮排指示子",
     raw(r"^\s*(?:- )?run:\s*[|>][+-]?\d")),
    ("D6  heredoc 開頭行以反斜線續行（`<<EOF \\`）",
     lambda text, runs: any(re.search(r"<<\S*.*\\$", hollow(l)) for run in runs for l in run.split("\n"))),
    ("D7  引號 run 值後接 YAML 行尾註解",
     raw(r"""^\s*(?:- )?run:\s*(?:"[^"]*"|'[^']*')\s+#""")),
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
    out = []
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if l and not l.startswith("#"):
            parts = l.split(" ", 1)
            out.append(parts[1].strip() if len(parts) == 2 else parts[0])
    return out


def main(argv):
    if not argv:
        print(__doc__); return 2
    cols = []
    for lst in argv:
        files = read_list(lst)
        counts = [0] * len(SHAPES); yaml_fail = 0
        for f in files:
            try:
                text = pathlib.Path(f).read_text(encoding="utf-8")
            except OSError:
                continue
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
        cols.append((pathlib.Path(lst).name, len(files), yaml_fail, counts))
    w = max(len(n) for n, _p in SHAPES)
    print("%-*s" % (w, "形狀 \\ 清單（檔數／PyYAML 拒）") + "".join("  %18s" % ("%s(%d/%d)" % (n[:10], t, yf)) for n, t, yf, _ in cols))
    for k, (name, _p) in enumerate(SHAPES):
        print("%-*s" % (w, name) + "".join("  %18d" % c[k] for _n, _t, _yf, c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
