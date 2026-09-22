#!/usr/bin/env python3
"""bash 神諭：runner 到底有沒有把 `neutralise.py` 接在管線的接收端——與 lint 的判定對帳。

為什麼（#33 verify R28 DA）：lint 對一個 fixture 的判定與 fixture 上 `# EXPECT:` 的宣告，**兩者都是作者寫的**。
selftest 只證明「lint 的判定 = 作者的宣告」，證不了「作者的宣告 = runner 的行為」。神諭把第三個東西（runner）
拉進來對帳。R30 的 DA 把同一支工具指向 base 的 lint，一條指令重現出 R28 的十條——網有牙。

## 管線判定改由 **bash 自己的剖析器**回答（R30 MB-4）
前一版在 stub 裡問 `[ -p /dev/stdin ]`。那量的是「stdin 是不是 pipe fd」，而 bash 5.x 的 heredoc **也用 pipe**
——於是 `python3 …neutralise.py <<EOF` 被算成「有管線」，神諭對 lint 發出**假指控**。
現在用 DEBUG trap ＋ `${#PIPESTATUS[@]}`：trap 在**下一個**命令之前觸發，此時 `PIPESTATUS` 是剛結束那個
pipeline 的每段狀態，長度 ≥2 就代表它真的是 pipeline。這是 bash 自己的答案，
對 `<<"EO"F`、`$'…'`、`${VAR#…}`、反引號註解這些詞法花招**一律免疫**——剖析是它做的，不是我們做的。
（`( … )` 之類的子殼層不影響：PIPESTATUS 的長度只由 pipeline 的段數決定。）

## 宣告的判定改用**差分**（R30 MB-2）
前一版是對 step 行範圍做裸子字串 `"LOG-FILTER:" in l`，於是寫在 **heredoc 內文**裡的假宣告被當成真宣告，
把一個真繞過認證成「一致」。宣告的定義是「runner 不會執行、也不會當資料吃掉的文字」，所以現在**直接問 bash**：
把那一行刪掉再跑一次，`(rc, stdout, stderr, 被記錄的呼叫)` 完全相同 ⟹ 它既不被執行也不被消費 ⟹ 它是註解。
（YAML 層的註解——真正的註解行、`run:` 行尾註解——不在 run 區塊的文字裡，另行辨識，不需要差分。）

## 判定表（六格，含第三格「量不到」）
  lint pass     ∧ piped                         → 一致
  lint pass     ∧ 非 piped ∧ 有**真**宣告        → 一致（宣告的豁免）
  lint RULE-red ∧ 非 piped                      → 一致
  lint RULE-red ∧ piped                         → **不一致：誤擋**
  lint pass     ∧ 非 piped ∧ 無宣告             → **不一致：繞過**
  lint PARSE    ∧ piped ∧ PyYAML 解析成功        → **不一致：誤擋（PARSE）**，除非該檔自己宣告 `# EXPECT: parse-red`
  timeout／stub 沒被呼叫到但腳本逾時             → **量不到**（不是繞過，也不算一致；逐項具名）

**適用邊界**：lint 依設計不判可達性（`if false; then … | python3 …; fi` 它算「有管線」），神諭是真的跑——
這類差異是**設計上的**，列在 `KNOWN_DISAGREE` 並寫理由。神諭不用 `-e`：runner 用 `bash -e`，但這裡要問的是
「管線有沒有被建立」，前面的指令失敗屬於可達性、不屬於本題。

**盲區（明寫）**：YAML 層用 PyYAML 解析，而 GitHub 的解析器**不同**——R28 探針實測 tab 分隔的引號 key
PyYAML 拒絕、GitHub 照樣執行；R29 探針實測整份縮排的文件 PyYAML 接受、GitHub 也執行。所以 `YAML-FAIL`
那一格是神諭**看不到**的地方，不是「runner 也不會跑」的保證。神諭對帳的是 shell 層，YAML 層的真值要靠探針。

**它會真的執行 fixture 裡的 shell**（R30 M-16）：PATH 只有 stub 與 `/usr/bin:/bin`、cwd 與 HOME 都是臨時目錄、
stdin `/dev/null`、逾時 5 秒。但那不是沙箱——fixture 寫絕對路徑就寫得出去、背景程序活得過逾時。
**加 fixture 等於加一段會被執行的 shell**，review 時請當成程式碼看。

依賴：PyYAML（`python3 -m pip install pyyaml`）。缺就 fail-loud，不靜默跳過。
用法：test/oracle.py [FILE…]   不給檔案 → 全部 test/fixtures/ci-log-filter-*.yml
退出碼：有 `KNOWN_DISAGREE` 之外的不一致 → 1；`KNOWN_DISAGREE` 裡的項目變成一致（理由不再成立）→ 1；否則 0。
「量不到」不改變退出碼，但一定逐項印出來。
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
LINT = HERE / "lint-ci-log-filter.sh"
FIXTURES = HERE / "fixtures"

try:
    import yaml
except ImportError:                       # 依賴缺席不是「沒有不一致」——那是沒量到
    print("✗ oracle.py 需要 PyYAML：python3 -m pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# (fixture 檔名, step 名) → 理由。每一條都要能說出「runner 與 lint 為什麼依設計會不同」；說不出來的就是缺陷。
KNOWN_DISAGREE = {
    # **YAML tag 一律 fail-closed，而 `!!str` 的值 bash 照跑** ⇒ 誤擋。這是**刻意保留**的，
    # 理由與代價都寫在這裡（R33，由 642 檔產生語料的 `R31-5 tag 值` 那一列量出來）：
    #   · 那道守衛是 R30 MB-8 加的，堵的是 `jobs: !!map {…}` 讓 flow 規則、`steps:` flow 檢查、
    #     anchor／alias 檢查**三條全部跳過**、整個 job 隱形的洞。
    #   · 只放行 `!!str` 需要動 YAML 分類路徑本身；那條路徑守著一個真的洞，而 `!!str` 的
    #     野外出現率是 **0/1565**（`shapes.py` 的 `R31-5` 列，本機語料實測）。
    #   · 所以本輪**不動它**，改成記在這裡：數字誠實地印成「不一致 1（已知 1）」，
    #     而不是讓它在「量不到」或某個寬鬆的述詞後面消失。
    # 這一條若哪天變成「一致」（有人放行了 tag），神諭會 rc=1 要求重判——理由不再成立就要拿掉。
    # **stderr 沒有規則**（R32 security S-2）**不在這裡逐檔列**：它按類別處理（`run_script` 把 stdout／stderr
    # 的外流分開記，`pass ∧ piped ∧ 僅 stderr` 的判定自帶「已知類別 S-2」並計入「已知」）。逐檔列會讓
    # 產生語料上的幾十條各佔一行、沒人讀；類別讓 R34 加上 stderr 規則的那一天，整類一起翻成一致並被逼重判。
    ("gen-d-yaml-tag-bang.yml", "tag-bang"):
        "YAML tag 一律 fail-closed（R30 MB-8 堵 `jobs: !!map` 隱形 job）；`!!str` 因此被連帶擋下。"
        "野外 0/1565，不值得為它動那條守著真洞的路徑。",
}

# lint 自己的宣告正規式（與 `lint-ci-log-filter.sh` 的 `LOGFILTER_RE` 同形）。這裡只用它判**文字長相**；
# 「那段文字是不是真的不會被執行」由差分決定，不靠任何一支的詞法分析。
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")

TIMEOUT_S = 5
# `$PR_TITLE` 的值：**「有沒有洩漏」是繞過判定的第三個條件**。lint 放行 ∧ runner 沒接管線，
# 只說明「沒過濾」；要構成繞過還得真的把 fork 可控的文字印出去。少了這一條，任何「lint 以為有管線、
# 但那一行根本沒執行」的構造都會被誤報成繞過（R31 自查：產生語料上 60 筆假指控全屬此類）。
PR_MARKER = "ORACLE-PR-TITLE-MARKER"

STUB = '''#!/bin/sh
for a in "$@"; do case "$a" in *neutralise.py) echo "called $a" >> "$ORACLE_MARK";; esac; done
cat >/dev/null 2>&1; exit 0
'''

# DEBUG trap：`PIPESTATUS` 在**下一個**命令之前才反映剛結束的 pipeline，所以記錄的是「上一個命令」。
# 最後一個 pipeline 需要「之後還有一個命令」才記得到——那個收尾命令用 **EXIT trap**，不是在腳本
# 尾端補一行文字。
#
# **R32 DA-6：這件事是本輪整份報告的前提，而前一版把它做成了文字。** 前一版在 run 區塊後面接
# `"\n:\n"`，於是**未終止的 heredoc 會把那個 `:` 一起吞掉**——最後一個 pipeline 因此沒有下一個
# 命令、PIPESTATUS 沒被讀到、神諭回報「量不到」。而「量不到」不改變 rc，所以 CI 全綠。
# 實測差別（468 檔產生語料）：文字哨兵 `一致 408、不一致 0、量不到 60`；EXIT trap
# `一致 413、不一致 55、量不到 0`。**那個被宣傳成「不一致 0」的數字，量到的是儀器答不出來。**
# EXIT trap 不是腳本正文的一部分，heredoc 的資料區吞不掉它——這是「非文字哨兵」的意思。
PRELUDE = '''set -T
__orc_prev=""
trap '[ ${#PIPESTATUS[@]} -ge 2 ] && case "$__orc_prev" in *neutralise.py*) echo "piped" >> "$ORACLE_MARK";; esac; __orc_prev=$BASH_COMMAND' DEBUG
trap ':' EXIT
'''


def pick_bash():
    for cand in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
        if cand and os.path.exists(cand):
            return cand
    raise SystemExit("找不到 bash")


def run_script(run, bash, stub_bin):
    """跑一次 run 區塊，回傳 (verdict, observable)。
    verdict: 'piped' / 'called-unpiped' / 'not-invoked' / 'timeout'
    observable: 差分用的可觀察結果（rc, stdout, stderr, mark 內容）——逾時的那次不拿來差分。"""
    with tempfile.TemporaryDirectory() as d:
        mark = os.path.join(d, "mark")
        open(mark, "w").close()
        script = os.path.join(d, "s.sh")
        with open(script, "w") as fh:
            # 收尾命令由 PRELUDE 的 `trap ':' EXIT` 提供——**不要**在這裡再補文字，
            # 那正是 R32 DA-6 抓到的缺陷（heredoc 會吞掉它）。
            fh.write(PRELUDE); fh.write(run); fh.write("\n")
        env = {"PATH": stub_bin + ":/usr/bin:/bin", "ORACLE_MARK": mark,
               "PR_TITLE": PR_MARKER, "HOME": d}
        try:
            # stdin **一定要**是 /dev/null：繼承呼叫端的 stdin 會讓任何讀 stdin 的指令卡住，
            # 於是「量不到」變成隨呼叫環境而定的東西（R31 自查：同一個 fixture 在終端機下逾時、
            # 在 pipe 下不逾時）。runner 的 step stdin 也不是終端機。
            r = subprocess.run([bash, script], env=env, cwd=d, capture_output=True,
                               stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return "timeout", None, False
        got = open(mark).read().split("\n")
        # 分開記 stdout 與 stderr：**stderr-only 的外流是 R32 S-2 那個已知缺口**（`PIPED_RE` 不要求 `2>&1`），
        # 按**類別**記為已知而不是逐檔列 KNOWN_DISAGREE——否則產生語料上幾十條會把數字淹掉、也沒人會逐條讀。
        # stdout 有 marker 一律是繞過，不分類別。
        leaked = (PR_MARKER.encode() in r.stdout, PR_MARKER.encode() in r.stderr)
        obs = (r.returncode, r.stdout, r.stderr, sorted(got))
        if "piped" in got:
            return "piped", obs, leaked
        if any(l.startswith("called ") for l in got):
            return "called-unpiped", obs, leaked
        return "not-invoked", obs, leaked


MARKER_RE = re.compile(r"#\s*LOG-FILTER:\s*(?:in-process|none — .+)")


def real_declaration(run, bash, stub_bin, baseline):
    """run 區塊裡有沒有**真的**宣告：把候選文字**從 `#` 切到行尾**再跑一次，可觀察結果完全相同
    ⟹ 那段文字既不被執行也不被當資料消費 ⟹ 它是註解。

    這是 R30 MB-2 的修法。前一版用裸子字串，於是 heredoc 內文裡的假宣告把一個真繞過認證成「一致」。
    差分法不依賴任何一支的詞法分析——判準是 bash 自己的行為。
    切到行尾（而不是刪整行）是因為宣告可以跟程式碼同行：`echo x;# LOG-FILTER:none — …`。
    """
    if baseline is None:
        return False                       # 量不到就不當成宣告（fail-closed）
    lines = run.split("\n")
    for i, l in enumerate(lines):
        m = MARKER_RE.search(l)
        if not m:
            continue
        probe = "\n".join(lines[:i] + [l[:m.start()]] + lines[i + 1:])
        v, obs, _leak = run_script(probe, bash, stub_bin)
        if v != "timeout" and obs == baseline:
            return True
    return False


def steps_with_lines(text):
    """[(job, step-name, run, (start_line, end_line))]，行號 0-based，用 yaml.compose 的 mark 取範圍。"""
    root = yaml.compose(text)
    all_lines = text.split("\n")
    out = []
    if not isinstance(root, yaml.MappingNode):
        return out
    for k, v in root.value:
        if k.value != "jobs" or not isinstance(v, yaml.MappingNode):
            continue
        for jk, jv in v.value:
            if not isinstance(jv, yaml.MappingNode):
                continue
            for sk, sv in jv.value:
                if sk.value != "steps" or not isinstance(sv, yaml.SequenceNode):
                    continue
                # **step 的行範圍用「下一個 step 的起點 - 1」**，不用 `end_mark`：PyYAML 的 end_mark 指向
                # 下一個 token 的起點，也就是**下一個 step 的第一行**——用它會讓相鄰 step 的範圍重疊，
                # 而範圍一重疊，逐 step 的 RULE／PARSE 歸屬就整批錯位（R31 自查：每個檔的第一個 step
                # 都被算成 RULE-red）。
                sibs = [st for st in sv.value if isinstance(st, yaml.MappingNode)]
                # 先把每個 step 的**起點**都調整好（bare `-`：鍵寫在下一行時 PyYAML 的 mapping 起點在
                # **鍵**那一行，而 lint 報的是 **dash** 那一行），**再**用「下一個起點 - 1」算終點。
                # 兩步不能合成一步：先算終點就會讓 dash 那一行同時落在兩個 step 的範圍裡（R31 自查）。
                starts = []
                for st in sibs:
                    st0 = st.start_mark.line
                    while st0 > 0 and re.match(r"^\s*-\s*$", all_lines[st0 - 1]):
                        st0 -= 1
                    starts.append(st0)
                for idx, st in enumerate(sibs):
                    kv = {kk.value: vv for kk, vv in st.value if isinstance(kk, yaml.ScalarNode)}
                    run = kv.get("run")
                    if not isinstance(run, yaml.ScalarNode):
                        continue
                    name = kv["name"].value if isinstance(kv.get("name"), yaml.ScalarNode) else "<未命名>"
                    end = (starts[idx + 1] - 1) if idx + 1 < len(sibs) else sv.end_mark.line
                    out.append((jk.value, name, run.value, (starts[idx], end)))
    return out


def yaml_declaration(text, a, b, block_bodies):
    """YAML 層的宣告來源：step 行範圍內**不在 block scalar 內文裡**的註解行，或 `run:` 行尾註解。
    這兩種 runner 結構上看不到，不需要差分。`block_bodies` 是 block scalar 內文的行號集合。"""
    lines = text.split("\n")
    for i in range(a, min(b + 1, len(lines))):
        if i in block_bodies:
            continue
        l = lines[i]
        if LOGFILTER_RE.match(l):
            return True
        m = re.match(r"^\s*(?:- )?[\w-]+:\s*(?:\"[^\"]*\"|'[^']*'|[^#]*?)\s(#.*)$", l)
        if m and LOGFILTER_RE.match(" " + m.group(1)):
            return True
    return False


def block_scalar_body_lines(text):
    """block scalar 內文的行號集合（給 `yaml_declaration` 排除用）——內文不是 YAML 註解。"""
    lines = text.split("\n")
    hdr = re.compile(r"^(\s*)(?:- )?[\w-]+:\s*[|>][+-]?\d?[+-]?\s*(?:#.*)?$")
    out, deeper = set(), None
    for i, l in enumerate(lines):
        ind = len(l) - len(l.lstrip())
        if deeper is not None:
            if not l.strip() or ind > deeper:
                out.add(i); continue
            deeper = None
        m = hdr.match(l)
        if m:
            deeper = len(m.group(1)) + (2 if l.lstrip().startswith("- ") else 0)
    return out


def main(argv):
    files = [pathlib.Path(a) for a in argv] or sorted(FIXTURES.glob("ci-log-filter-*.yml"))
    bash = pick_bash()
    ver = subprocess.run([bash, "-c", 'echo "$BASH_VERSION"'], capture_output=True, text=True).stdout.strip()
    print("bash: %s (%s)  管線判定：DEBUG trap + PIPESTATUS（bash 自己的剖析）" % (bash, ver))
    rows, disagree, stale, unmeasured = [], [], [], []
    known_cat = []      # 已知**類別**（R32 S-2：stderr-only 外流），按類別不按檔——見 run_script 的註解
    with tempfile.TemporaryDirectory(prefix="oracle-") as d:
        stub_bin = os.path.join(d, "bin"); os.mkdir(stub_bin)
        p = os.path.join(stub_bin, "python3"); open(p, "w").write(STUB); os.chmod(p, 0o755)
        # CI runner 的 sudo 是無密碼的；本機的會等密碼而讓整個 step 逾時（＝把量得到的變成量不到）。
        q = os.path.join(stub_bin, "sudo"); open(q, "w").write('#!/bin/sh\nexec "$@"\n'); os.chmod(q, 0o755)
        for f in files:
            text = f.read_text(encoding="utf-8")
            expect = (re.search(r"^# EXPECT: (\S+)", text, re.M) or [None, ""])[1] if "# EXPECT:" in text else ""
            try:
                steps = steps_with_lines(text)
            except yaml.YAMLError:
                rows.append((f.name, "-", "YAML-FAIL", "-", "不可比（PyYAML 也拒絕）")); continue
            r = subprocess.run(["bash", str(LINT), str(f)], capture_output=True, text=True)
            # **逐 step 歸屬用行號，不用名稱**：lint 印的是它自己解析出來的 step 名，而 `name: |` 這種
            # block scalar 的名字在 lint 眼中是 `|`、在 PyYAML 眼中是內文——名稱比對必然失配，於是
            # 一個真的被 lint 擋下來的 step 會被神諭讀成 `lint=pass` 並反過來指控 lint 放行（R31 自查）。
            red_lines = {int(x) for x in re.findall(r":(\d+): RULE: ", r.stderr)}
            parse_lines = {int(x) for x in re.findall(r":(\d+): PARSE: ", r.stderr)}
            bodies = block_scalar_body_lines(text)
            ranges = [(a + 1, b + 1) for _j, _n, _r, (a, b) in steps]
            # **一次算完**：落在任何一個 step 範圍外的 PARSE 才是結構性的（整檔不可信）。
            # 前一版在每個 step 內各算一次，於是別的 step 的 PARSE 讓這個 step 也變成 PARSE
            # （`bypass-duplicate-key` 的合規對照 step 被算成「PARSE ∧ piped」＝誤擋，R31 自查）。
            struct_parse = any(not any(lo <= x <= hi for lo, hi in ranges) for x in parse_lines)
            for _job, name, run, (a, b) in steps:
                o, obs, leaked = run_script(run, bash, stub_bin)
                in_step = lambda s: any(a + 1 <= x <= b + 1 for x in s)
                # step 範圍外的 PARSE 是**結構性**的（整檔不可信）→ 所有 step 都不可比；
                # 範圍內的 PARSE 只影響那一個 step。前一版對整檔一視同仁，於是
                # `bypass-duplicate-key` 的合規對照 step 被算成「PARSE ∧ piped」＝誤擋（R31 自查）。
                # **lint 自己 fail-loud（rc=2：檔案不存在／用法錯誤）不是 pass**（R32 DA-8）。
                # 前一版只看 stderr 裡的 RULE/PARSE 標記，rc=2 時兩者都沒有 ⇒ 落到 `pass` ⇒ 一個
                # 刻意的 fail-loud 被神諭讀成「lint 放行」。命名為 ERROR、歸不可比，不進一致也不進不一致。
                if r.returncode == 2:
                    lint = "ERROR"
                else:
                    lint = ("RULE-red" if in_step(red_lines)
                            else ("PARSE" if (in_step(parse_lines) or struct_parse) else "pass"))
                key = (f.name, name)
                if o == "timeout":
                    verdict = "量不到（逾時 %ds）" % TIMEOUT_S
                    unmeasured.append(key)
                elif lint == "ERROR":
                    verdict = "不可比（lint rc=2：fail-loud，不是判定）"
                elif lint == "PARSE":
                    if o == "piped" and expect != "parse-red":
                        verdict = "不一致：誤擋（PARSE）"
                    else:
                        verdict = "不可比（fail-closed%s）" % ("，檔案自己宣告 parse-red" if expect == "parse-red" else "")
                elif lint == "pass" and o == "piped":
                    # **「某處有管線」≠「沒有洩漏」**（R32 Codex 第 4 條／security S-3／requirements F4）。
                    # 前一版在這一支直接判「一致」，即使 `leaked` 已經是 True——於是 `echo "$PR_TITLE"` 接一條
                    # 不相干的管線、或 PR 文字從 **stderr** 繞過只接 stdout 的管線，都被認證成一致。
                    # 判準與另一支相同：洩漏就是繞過，不管旁邊有沒有一條管線。
                    if leaked[0]:
                        # o == piped ⇒ 這個區塊裡**真的有**一條接 neutralise 的管線；PR 文字卻從 stdout 出去，
                        # 只能是**另一條命令**印的——這正是 lint 明寫的限制第 2 條「一條管線＝整個區塊已過濾」
                        # （Codex 第 4 條）。與詞法繞過不同（那種 bash 不會建管線，o ≠ piped，走下面那一支）。
                        # 按類別記已知，與 S-2 同理：整類在「什麼算已過濾」改掉的那一天一起翻。
                        verdict = "不一致：繞過（已知類別 G：一條管線＝整個區塊已過濾——顆粒度，限制第 2 條）"
                        known_cat.append(key)
                    elif leaked[1]:
                        verdict = "不一致：繞過（已知類別 S-2：僅 stderr——`PIPED_RE` 不要求 `2>&1`，規則留 R34）"
                        known_cat.append(key)
                    else:
                        verdict = "一致"
                elif lint == "pass":
                    decl = (yaml_declaration(text, a, b, bodies)
                            or real_declaration(run, bash, stub_bin, obs))
                    if decl:
                        verdict = "一致"
                    elif leaked[0] or leaked[1]:
                        verdict = "不一致：繞過"
                    else:
                        # lint 放行、runner 沒過濾，但這一次執行**沒有把 PR 文字印出去**——
                        # 沒有洩漏就沒有繞過，可是也證不了「不會洩漏」。第三格，逐項具名。
                        verdict = "量不到（沒有觀察到 PR 文字外流）"
                        unmeasured.append(key)
                elif o != "piped":
                    verdict = "一致"
                else:
                    verdict = "不一致：誤擋"
                if verdict.startswith("不一致") and key in known_cat:
                    pass                                   # 已知**類別**（S-2 stderr-only）：印出、計入「已知」、不改 rc
                elif verdict.startswith("不一致"):
                    if key in KNOWN_DISAGREE:
                        verdict += "（已知：%s）" % KNOWN_DISAGREE[key]
                    else:
                        disagree.append(key)
                elif key in KNOWN_DISAGREE:
                    stale.append(key)
                rows.append((f.name, name, lint, o, verdict))
    w = max(len(r[0]) for r in rows)
    for fn, name, lint, o, verdict in rows:
        print("%-*s  %-40s lint=%-9s oracle=%-14s %s" % (w, fn, name[:40], lint, o, verdict))
    n = len(rows)
    print("\n%d 個 step：一致 %d、不一致 %d（已知 %d）、不可比 %d、量不到 %d"
          % (n, sum(1 for r in rows if r[4] == "一致"),
             sum(1 for r in rows if r[4].startswith("不一致")), sum(1 for r in rows if "（已知" in r[4]),
             sum(1 for r in rows if r[4].startswith("不可比")), len(unmeasured)))
    rc = 0
    if disagree:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 之外的不一致（lint 與 runner 對同一個 step 說不同的話）：")
        for fn, name in disagree: print("  - %s :: %s" % (fn, name))
    if stale:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 裡的項目現在一致了（理由不再成立，移除它）：")
        for fn, name in stale: print("  - %s :: %s" % (fn, name))
    if unmeasured:
        # R32 requirements F1：前一版這一行的標題斷言「腳本逾時」，而列在下面的大多數是另一個原因
        # （「這一次執行沒有把 PR 文字印出去」）。標題不得斷言它沒量到的原因——兩個都寫，逐列自帶。
        print("\n⚠ 量不到（逾時、或這一次執行沒有把 PR 文字印出去——各列自帶原因；不是繞過也不是一致，這一格存在本身就是揭露）：")
        for fn, name in unmeasured: print("  - %s :: %s" % (fn, name))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
