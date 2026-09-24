#!/usr/bin/env python3
"""合成 base-綠語料（#33 verify R28 regression lens 的三種變體；R29 進 repo）。

為什麼要合成（R26 M7）：真實語料裡含 heredoc 的檔在舊版 lint 下**全部是紅的**（heredoc 終止分支不可達），
所以「base 綠→head 紅 = 0」對 heredoc 機制根本沒有分母。把每個 run 區塊機械地加上一行讓它在任何版本下都
該綠的東西，才有分母。三種變體各有盲點，所以三種都產：
  A: 每個 `run: |`／`>` 區塊**第一行**插 `# LOG-FILTER: none — synth`；inline `run:` 前一行插同一句
     ——宣告置首，不受 heredoc 吞噬影響（R28 DA D11 指定的分母變體）
  B: 同一句插在區塊**最後一行**（heredoc 之後）——會被 heredoc 吞噬吃掉，所以量得到吞噬
  C: 最後一行插 `echo synth | python3 scripts/neutralise.py`；inline run 尾端接 ` | python3 scripts/neutralise.py`
     ——R26 DA 的 green2 作法
用法：synth.py <list> <outdir>   → outdir/<A|B|C>/<n>.yml ＋ manifest.txt（n → 原檔路徑）
"""
import re, sys, pathlib, hashlib
src_list, outdir = sys.argv[1], pathlib.Path(sys.argv[2])   # 清單每行 `<hash> <path>`／`x <path>`；不寫死任何路徑
RUN=re.compile(r'^(\s*)(- )?run:(\s*)(.*)$')
BLOCK=re.compile(r'^[|>](?:[+-]\d*|\d+[+-]?)?\s*(#.*)?$')
def transform(lines, variant):
    out=[]; i=0; n=len(lines)
    while i<n:
        ln=lines[i]; m=RUN.match(ln)
        if not m: out.append(ln); i+=1; continue
        ind=len(m.group(1)); dash=m.group(2) or ""; val=m.group(4).strip()
        key_ind = ind + (2 if dash else 0)
        if BLOCK.match(val):
            # find body extent
            j=i+1; body=[]
            while j<n and (not lines[j].strip() or (len(lines[j])-len(lines[j].lstrip()))>key_ind):
                body.append(lines[j]); j+=1
            nonblank=[b for b in body if b.strip()]
            if not nonblank: out.append(ln); i+=1; continue
            pad=min(len(b)-len(b.lstrip()) for b in nonblank)
            # trim trailing blank lines from body so "last" is real
            while body and not body[-1].strip(): body.pop()
            j=i+1+len(body)
            if variant=="A": new=[ln, " "*pad+"# LOG-FILTER: none — synth"]+body
            elif variant=="B": new=[ln]+body+[" "*pad+"# LOG-FILTER: none — synth"]
            else: new=[ln]+body+[" "*pad+"echo synth | python3 scripts/neutralise.py"]
            out.extend(new); i=j; continue
        # inline run
        if variant in ("A","B"):
            out.append(" "*key_ind+"# LOG-FILTER: none — synth"); out.append(ln)
        else:
            out.append(ln+" | python3 scripts/neutralise.py")
        i+=1
    return out
for v in "ABC": (outdir/v).mkdir(parents=True,exist_ok=True)
man=[]
k=0
for l in open(src_list):
    if not l.strip() or l.startswith('#'): continue
    p=l.split(' ',1)[-1].strip()
    try: t=pathlib.Path(p).read_text(encoding="utf-8")
    except Exception: continue
    if "run:" not in t: continue
    k+=1
    for v in "ABC":
        (outdir/v/f"{k:04d}.yml").write_text("\n".join(transform(t.split("\n"),v)))
    man.append(f"{k:04d} {p}")
(outdir/"manifest.txt").write_text("\n".join(man)+"\n")
print("synthesised",k,"files x 3 variants into",outdir)
