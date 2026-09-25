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
import collections
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
    # **`--strict` 群組規則只收恰好一對大括號**（#59／#60）⇒ 群組裡再包一個群組是誤擋。刻意保留：計深度要判斷每個
    # `{`／`}` 在 bash 眼中是不是保留字，而 `case` 模式的 `{)` 會讓計數器以為群組還開著（`bypass-strict-group-case-pattern-brace`
    # 實測外流）。代價只落在 `--strict`（真 workflow）：要短路改寫成 `if`，repo 自己的 workflow 沒有巢狀群組。
    ("ci-log-filter-restrict-strict-group-nested.yml", "nested group"):
        "群組規則只收恰好一對大括號（計深度會被 `case` 的 `{)` 騙過）；巢狀群組因此被連帶擋下，改寫成 `if` 即可。",
    # **神諭的 python3 是 stub**：它不檢查路徑存不存在，所以真 python3 的「can't open file '<路徑>'」（路徑裡帶著展開後的
    # PR 文字、寫在 python3 自己的 stderr）在這裡不會出現。lint 擋下是對的，神諭量不到——這是儀器的盲區，不是 lint 的誤擋。
    ("ci-log-filter-bypass-strict-group-expansion-in-filter-path.yml", "expansion in the filter path"):
        "stub python3 不報「can't open file」；真 python3 會把含 PR 文字的路徑印到群組外的 stderr。",
}

# lint 自己的宣告正規式（與 `lint-ci-log-filter.sh` 的 `LOGFILTER_RE` 同形）。這裡只用它判**文字長相**；
# 「那段文字是不是真的不會被執行」由差分決定，不靠任何一支的詞法分析。
LOGFILTER_RE = re.compile(r"^\s*#\s*LOG-FILTER:\s*(in-process|none — .+)")

TIMEOUT_S = 5
# `$PR_TITLE` 的值：**「有沒有洩漏」是繞過判定的第三個條件**。lint 放行 ∧ runner 沒接管線，
# 只說明「沒過濾」；要構成繞過還得真的把 fork 可控的文字印出去。少了這一條，任何「lint 以為有管線、
# 但那一行根本沒執行」的構造都會被誤報成繞過（R31 自查：產生語料上 60 筆假指控全屬此類）。
PR_MARKER = "ORACLE-PR-TITLE-MARKER"
# 判定表的**種類**（#33 verify R34 requirements F3）：每一列的判定都必須以其中之一開頭（`main()` 逐列 assert）。
# CHANGELOG 的「判定表有 N 種」由 `lint-changelog-counts.sh` 讀這個常數驗——前一版那一句量的是 CHANGELOG 自己打的字面清單，
# 永遠抓不到 CHANGELOG 與神諭分岔。「不一致」的兩種各自帶後綴（繞過／誤擋），所以這裡列的是完整前綴。
# 形狀像已知類別、`--strict` 卻放行 ⇒ 不是已知，是真繞過（計入不一致、rc=1）。
STRICT_MISS = "不一致：繞過（形狀像已知類別 %s，但 `--strict` 也放行——已知類別的定義是 CI 模式擋得下）"
VERDICT_KINDS = ("一致", "不一致：繞過", "不一致：誤擋", "不可比", "量不到")
# S-2 的**機制**判定（見 main 的 S-2 分支）：run 文字裡有 fd 轉向到 stderr 或 xtrace ⇒ 不是 S-2；
# 接 neutralise 的管線帶了 `2>&1`／`|&` ⇒ 不是 S-2。
STDERR_ROUTE_RE = re.compile(r">&2|/dev/stderr|\bset\s+-[A-Za-z]*x|\bset\s+-o\s+xtrace|\bbash\s+-[A-Za-z]*x")
NEUT_WITH_STDERR_RE = re.compile(r"(2>&1\s*\||\|&)\s*python3\s+\S*neutralise\.py")

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
    def _shell_of(node):
        """`defaults: run: shell:` 的值（沒有就 None）。"""
        if not isinstance(node, yaml.MappingNode):
            return None
        d = {kk.value: vv for kk, vv in node.value if isinstance(kk, yaml.ScalarNode)}.get("defaults")
        if not isinstance(d, yaml.MappingNode):
            return None
        r = {kk.value: vv for kk, vv in d.value if isinstance(kk, yaml.ScalarNode)}.get("run")
        if not isinstance(r, yaml.MappingNode):
            return None
        sh = {kk.value: vv for kk, vv in r.value if isinstance(kk, yaml.ScalarNode)}.get("shell")
        return sh.value if isinstance(sh, yaml.ScalarNode) else "<非純量>" if sh is not None else None
    wf_shell = _shell_of(root)
    for k, v in root.value:
        if k.value != "jobs" or not isinstance(v, yaml.MappingNode):
            continue
        for jk, jv in v.value:
            if not isinstance(jv, yaml.MappingNode):
                continue
            jkv = {kk.value: vv for kk, vv in jv.value if isinstance(kk, yaml.ScalarNode)}
            job_shell = _shell_of(jv)
            ro = jkv.get("runs-on")
            ro_text = " ".join(x.value for x in ro.value if isinstance(x, yaml.ScalarNode)) if isinstance(ro, yaml.SequenceNode) \
                else (ro.value if isinstance(ro, yaml.ScalarNode) else "")
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
                    # **神諭只會用 bash 跑**（#33 verify R34 security S-3、DA n4／n4b）：runner 實際用的 shell
                    # 由 step `shell:` → job `defaults.run.shell` → workflow `defaults.run.shell` 決定；都沒寫時，
                    # container 裡是 sh、Windows runner 是 pwsh。這些情況神諭的判定沒有意義 ⇒ 不可比，並寫出原因。
                    st_sh = kv.get("shell")
                    eff = (st_sh.value if isinstance(st_sh, yaml.ScalarNode) else None) or job_shell or wf_shell
                    if eff is not None:
                        note = None if eff.strip() == "bash" else "shell 是 %r" % eff
                    elif "container" in jkv:
                        note = "job 跑在 container 裡、沒寫 shell（預設 sh）"
                    elif "windows" in ro_text.lower() or "${{" in ro_text:
                        note = "runs-on 是 %r、沒寫 shell（Windows 預設 pwsh；運算式無法靜態判定）" % ro_text
                    else:
                        note = None
                    out.append((jk.value, name, run.value, (starts[idx], end), note))
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
    cls_stale, cls_count = [], collections.Counter()
    with tempfile.TemporaryDirectory(prefix="oracle-") as d:
        stub_bin = os.path.join(d, "bin"); os.mkdir(stub_bin)
        p = os.path.join(stub_bin, "python3"); open(p, "w").write(STUB); os.chmod(p, 0o755)
        # CI runner 的 sudo 是無密碼的；本機的會等密碼而讓整個 step 逾時（＝把量得到的變成量不到）。
        q = os.path.join(stub_bin, "sudo"); open(q, "w").write('#!/bin/sh\nexec "$@"\n'); os.chmod(q, 0o755)
        # **`sleep` 是空操作**（#33 verify R34 DA n6）：`sleep 6` 讓腳本超過 TIMEOUT_S，一個真繞過因此落進
        # 「量不到（逾時）」——逾時不改 rc。等待不改變 PR 文字有沒有外流，所以不讓它耗時。
        z = os.path.join(stub_bin, "sleep"); open(z, "w").write('#!/bin/sh\nexit 0\n'); os.chmod(z, 0o755)
        for f in files:
            text = f.read_text(encoding="utf-8")
            expect = (re.search(r"^# EXPECT: (\S+)", text, re.M) or [None, ""])[1] if "# EXPECT:" in text else ""
            try:
                steps = steps_with_lines(text)
            except yaml.YAMLError:
                rows.append((f.name, "-", "YAML-FAIL", "-", "不可比（PyYAML 也拒絕）")); continue
            # **用 fixture 宣告的模式跑 lint**（`# LINT-ARGS:`，R35）：前一版一律用預設模式，於是 `--strict` 的 fixture
            # 被放到它沒宣告的模式下量——一個嚴格模式該擋的 step 被讀成「lint 放行」，還被算進已知類別 S-2。
            largs = (re.search(r"^# LINT-ARGS: (.+)$", text, re.M) or [None, ""])[1].split()
            r = subprocess.run(["bash", str(LINT)] + largs + [str(f)], capture_output=True, text=True)
            # **逐 step 歸屬用行號，不用名稱**：lint 印的是它自己解析出來的 step 名，而 `name: |` 這種
            # block scalar 的名字在 lint 眼中是 `|`、在 PyYAML 眼中是內文——名稱比對必然失配，於是
            # 一個真的被 lint 擋下來的 step 會被神諭讀成 `lint=pass` 並反過來指控 lint 放行（R31 自查）。
            # `[--strict]` 的 pipefail 規則管的是**退出碼被遮蔽**，不是 PR 文字外流——神諭量不到它（R35）。
            # 只因它而紅的 step 判「不可比」並寫明原因，不當成 lint 的判定拿來對帳。
            pf_lines = {int(x) for x in re.findall(r":(\d+): RULE: \[--strict\][^\n]*pipefail", r.stderr)}
            red_lines = {int(x) for x in re.findall(r":(\d+): RULE: ", r.stderr)} - pf_lines
            parse_lines = {int(x) for x in re.findall(r":(\d+): PARSE: ", r.stderr)}
            bodies = block_scalar_body_lines(text)
            ranges = [(a + 1, b + 1) for _j, _n, _r, (a, b), _sh in steps]
            declared_cls = set(re.findall(r"^# KNOWN-CLASS: (\S+)", text, re.M))
            seen_cls = set()
            # **已知類別＝`--strict` 真的擋下這個 step**（#59／#60）：G 與 S-2 是「預設模式（量詞法）放行、CI 用的
            # `--strict` 擋下」的類別。前一版只按形狀歸類，於是「`--strict` 也放行的同形繞過」一樣被算成已知、不改 rc。
            # 現在歸類前先問 `--strict`：它對這個 step 印 RULE（pipefail 那條除外——它管退出碼，不管外流）或 PARSE，
            # 才算已知；否則是真繞過。檔案本身就用 `--strict` 跑的，上面那一次就是答案。
            if "--strict" in largs:
                rs = r
            else:
                rs = subprocess.run(["bash", str(LINT), "--strict"] + largs + [str(f)], capture_output=True, text=True)
            # 逐則訊息判斷，不用行號相減：同一個 step 可以同時吃 pipefail 與群組兩條 RULE（行號相同）。
            strict_block = {int(m.group(1)) for m in re.finditer(r":(\d+): (?:PARSE: |RULE: (?!\[--strict\][^\n]*pipefail))", rs.stderr)}
            # **一次算完**：落在任何一個 step 範圍外的 PARSE 才是結構性的（整檔不可信）。
            # 前一版在每個 step 內各算一次，於是別的 step 的 PARSE 讓這個 step 也變成 PARSE
            # （`bypass-duplicate-key` 的合規對照 step 被算成「PARSE ∧ piped」＝誤擋，R31 自查）。
            struct_parse = any(not any(lo <= x <= hi for lo, hi in ranges) for x in parse_lines)
            for _job, name, run, (a, b), shell_note in steps:
                key = (f.name, name, a + 1)     # **含行號**（#33 verify R34 DA n1）：同名 step 不得共用一個 key
                if any(a + 1 <= x <= b + 1 for x in pf_lines):
                    rows.append((f.name, name, "RULE-pipefail", "-", "不可比（`--strict` 的 pipefail 規則：量的是退出碼遮蔽，不是外流）")); continue
                if shell_note:
                    rows.append((f.name, name, "-", "-", "不可比（%s——神諭只會用 bash 跑）" % shell_note)); continue
                o, obs, leaked = run_script(run, bash, stub_bin)
                in_step = lambda s: any(a + 1 <= x <= b + 1 for x in s)
                strict_blocks = lambda: in_step(strict_block) or any(
                    not any(lo <= x <= hi for lo, hi in ranges) for x in strict_block)
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
                        verdict = "不一致：繞過（已知類別 G：一條管線＝整個區塊已過濾——顆粒度，限制第 2 條；`--strict` 的群組規則擋）"
                        if strict_blocks(): known_cat.append(key); seen_cls.add("G")
                        else: verdict = STRICT_MISS % "G"
                    elif leaked[1] and not STDERR_ROUTE_RE.search(run) and not NEUT_WITH_STDERR_RE.search(run):
                        # **S-2 按機制歸類，不按症狀**（#33 verify R34 security S-2／logic F5／DA G-B）：前一版只要
                        # 「只有 stderr 帶 PR 文字」就記已知，於是 `>&2 2>&1 |`、`>&2 |&`、`set -x` 後接 `2>&1 |`
                        # 這些**帶了** `2>&1`、S-2 的定義根本不涵蓋的真繞過也被算成已知、不改 rc。
                        # 現在只有「接 neutralise 的管線確實缺 `2>&1`／`|&`、而且沒有 fd 轉向或 xtrace」才是 S-2——
                        # 那一類在 `--strict`（CI 對真 workflow 用的模式）會被規則擋下；預設模式不要求它。
                        verdict = "不一致：繞過（已知類別 S-2：僅 stderr，接 neutralise 的管線缺 `2>&1`——預設模式不要求，`--strict` 要求）"
                        if strict_blocks(): known_cat.append(key); seen_cls.add("S-2")
                        else: verdict = STRICT_MISS % "S-2"
                    elif leaked[1] and STDERR_ROUTE_RE.search(run):
                        # fd 轉向或 xtrace：lint 的 fd 流向規則該擋下它——lint 放行就是真繞過，不屬任何已知類別。
                        verdict = "不一致：繞過（stderr 外流，run 裡有 fd 轉向／xtrace——lint 的 fd 流向規則應擋下）"
                    elif leaked[1]:
                        # 接 neutralise 的管線帶了 `2>&1`、沒有 fd 轉向，PR 文字仍從 stderr 出去 ⇒ 印它的是**管線以外**
                        # 的另一條命令（例：單獨一行 `cat "$PR_TITLE"`）——與 G 同一個限制（一條管線＝整個區塊已過濾），
                        # 只是走 stderr。歸 G；`known-granularity-stderr-other-command` 是它的範例，S-2 若退回按症狀歸類，
                        # 那一檔會被錯歸成 S-2 而觸發 KNOWN-CLASS 過期。
                        # #60 第 2 類（管線那一段的 `2>&1` 生效**之前**寫出的展開期／重導向錯誤）也落在這一格：神諭分不出
                        # 印 PR 文字的是另一條命令還是同一段的展開，而兩者由同一條 `--strict` 群組規則關掉。
                        verdict = ("不一致：繞過（已知類別 G：stderr 不經過濾——管線以外的命令，或那一段 `2>&1` 生效前的"
                                   "展開期／重導向錯誤；`--strict` 的群組規則擋）")
                        if strict_blocks(): known_cat.append(key); seen_cls.add("G")
                        else: verdict = STRICT_MISS % "G"
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
                elif leaked[0] or leaked[1]:
                    # **有管線不等於沒有外流**（R35）：lint 擋下、bash 也確實建了接 neutralise 的管線，但 PR 文字
                    # 仍然出去了（fd 轉向到 stderr、xtrace、管線以外的命令）——擋下是對的。前一版這一格一律判誤擋。
                    verdict = "一致"
                else:
                    verdict = "不一致：誤擋"
                if verdict.startswith("不一致") and key in known_cat:
                    pass                                   # 已知**類別**（S-2 stderr-only）：印出、計入「已知」、不改 rc
                elif verdict.startswith("不一致"):
                    if key[:2] in KNOWN_DISAGREE:
                        verdict += "（已知：%s）" % KNOWN_DISAGREE[key[:2]]
                    else:
                        disagree.append(key)
                elif key[:2] in KNOWN_DISAGREE:
                    stale.append(key)
                assert verdict.startswith(VERDICT_KINDS), verdict   # 判定表的種類是 VERDICT_KINDS（CHANGELOG 讀它）
                rows.append((f.name, name, lint, o, verdict))
            # **宣告了已知類別、卻沒被歸進那一類 ⇒ stale**（#33 verify R34 security LOW-1）：前一版的 S-2 範例
            # fixture 在檔頭說「變成一致會逼人重判」，而類別路徑根本沒有 stale 檢查。
            for c in sorted(declared_cls - seen_cls):
                cls_stale.append((f.name, c))
            cls_count.update(seen_cls if len(seen_cls) else ())
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
        for fn, name, ln in disagree: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if stale:
        rc = 1
        print("\n✗ KNOWN_DISAGREE 裡的項目現在一致了（理由不再成立，移除它）：")
        for fn, name, ln in stale: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if unmeasured:
        # R32 requirements F1：前一版這一行的標題斷言「腳本逾時」，而列在下面的大多數是另一個原因
        # （「這一次執行沒有把 PR 文字印出去」）。標題不得斷言它沒量到的原因——兩個都寫，逐列自帶。
        print("\n⚠ 量不到（逾時、或這一次執行沒有把 PR 文字印出去——各列自帶原因；不是繞過也不是一致，這一格存在本身就是揭露）：")
        for fn, name, ln in unmeasured: print("  - %s :: %s（第 %d 行）" % (fn, name, ln))
    if cls_stale:
        rc = 1
        print("\n✗ 檔頭宣告了已知類別、神諭卻沒把它歸進那一類（KNOWN-CLASS 過期——重判這個 fixture）：")
        for fn, c in cls_stale: print("  - %s :: %s" % (fn, c))
    # **類別本身是閘門**（#33 verify R34 requirements F5）：已知類別依設計不改 rc，所以「類別路徑整個壞掉」
    # 在 rc 上看不出來。只在跑 repo 自己的 fixture 集（沒有給檔案參數）時檢查：G 與 S-2 各至少一條。
    if not argv:
        for c in ("G", "S-2"):
            if cls_count[c] < 1:
                rc = 1
                print("\n✗ 已知類別 %s 在 fixture 集上是 0 條——類別路徑沒有網（該類的範例 fixture 被改掉，或分類壞了）" % c)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
