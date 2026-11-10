#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歷史注入設定的凍結表與逐目標履行檢查（R64；#33 verify R63 第 2、3、4 列）。由 `oracle_selfcheck.py` 匯入，不單獨執行。

R61 的處方是把「單調」改成機械檢查：`oracle_selfcheck.py` 的 `HISTORICAL_SENTINEL_POSITIONS` 凍結了**哨兵目標的名稱與條件**。R63 證明那張表不夠：
(1) payload 字串集合不在表裡——`32d45ff` 的四個複合 payload（含 `;`；路徑佔位符算在內長 95～117 字）從 R54 起就不在 `INJECT_PAYLOADS`，以 PR 文字特徵把關的求值者因此舊樹判繞過、新樹判一致（第 2 列）；
(2) 路徑形狀不在表裡——`priv-tmpdir` 的私有目錄前綴寫成 `o`，`32d45ff` 是 mkdtemp 預設的 `tmp`（第 3 列）；隱藏 cwd 哨兵的路徑壞掉（`.orc-*/injectx`），110 項 selfcheck 全綠（第 4 列的 X2）。
這個模組補上兩件事，兩件都是**封閉的**：

- `PAYLOAD_UNION`／`HISTORICAL_PAYLOADS`：封閉清單各樹的 `INJECT_PAYLOADS`（R61 停止規則的八棵樹，加上 R61 驗過的 `636fcfe`），以 ast 從 `git show <sha>:…/oracle.py` 抽出後凍結（標記與路徑記號在九棵樹都是同一個值，R66 起重抽時直接比對，不再正規化）。
  `payload_history_problems` 要求每一列的每一個字串都在現在的 `INJECT_PAYLOADS` 裡；`payload_history_regen_problems` 在有 git 歷史時重新抽一次、與凍結表逐列比對（淺層 clone 沒有歷史就跳過並說明，不算通過）。
- `TARGET_SHAPES`：`_inject_runs` 的每一個目標，`run_script` **實際建出**的哨兵路徑形狀、上一層目錄、是否預先建檔，以及寫進去之後神諭有沒有偵測到。`target_fulfillment_problems` 對每個目標真的跑一次 `run_script`。

**它不守的**：鍵模式軸（`_inject_key_modes`，由 aud 的值比較守）；跨執行持久狀態（H3，停止規則的第三個豁免類，見 `oracle.py`〈已知限制〉(9)）；求值者在程式內轉換 PR 文字（L1 族）；
**神諭自己可被觀察的執行環境**（R65 DA 的「儀器指紋」：導出的環境變數名，例如 `ORACLE_INJECT`、`ORACLE_PRIV`；繼承的 fd 197；cwd 與 stub 目錄裡預先建好的檔案）——舊樹在這一軸與現在不同，
步驟依這些特徵決定要不要執行 PR 文字時，舊樹判繞過、現在判一致（R65 報告第 1 列）。這兩張表都不涵蓋這一軸；使用者 2026-11-08 選擇列為停止規則的第四個豁免類（`oracle.py`〈已知限制〉(11)，探針 `injection-instrument-fingerprint-known-blind-spots.yml`），本模組不守。
"""
import ast
import os
import pathlib
import re
import subprocess
import tempfile

ORACLE_REL = "plugins/parallel-ai-agents/test/oracle.py"
CANON_MARKER = "ORACLE-INJECT-MARKER"          # 凍結表的字串用這兩個記號寫；比對時換成 oracle 現在的值
CANON_TOKEN = "@@ORACLE-INJECT-PATH@@"

# 封閉清單，只有這九棵樹（R61 停止規則的八棵，加上 R61 驗過的 `636fcfe`）；新增一棵樹要同時在這裡與 `HISTORICAL_PAYLOADS` 加一列，拿掉一列要有書面理由。
# 這份清單另在 `oracle_selfcheck.py` 有一份固定的複本（`_CLOSED_TREES_PIN`，R68）：這裡連同凍結列、摘要、SHA 一起少一棵樹時，所有逐樹檢查都會跟著縮小而保持綠，
# 只有那份複本會報；改清單要兩處一起改，兩處不一致就是 selfcheck 的問題。
# **納入準則是治理規則，不是可由程式推導的性質**（R66 寫成準則，R67 requirements／DA／Codex：「被更正的錯」要由人判斷，程式只能比對清單，判斷不了一個設定是不是錯）：
# 一輪 verify 的對象（PR 頭）要不要進清單，由使用者裁定，裁定與理由寫在這裡。裁定時用的準則：**被更正的錯不算取代**——某個注入設定在下一輪被認定為那一輪自己的錯、
# 並由下一輪改回，這棵樹不因那個設定進清單；設定沒有被這樣認定、而被後來的樹改掉的，這棵樹進清單（它的設定是被取代，不是被更正）。逐樹的裁定：
#   · R61 停止規則的八棵（`5b5a46d`～`28ec8c3`）：使用者 2026-10 依停止規則列入。
#   · `636fcfe`（R61 的對象，R60 的樹）：R64 列入時的紀錄是「R61 驗過」。它的注入設定沒有被下一輪認定為那一輪自己的錯，後來的樹在它之上加目標、加 payload，
#     依本準則屬「被取代」，進清單。
#   · `8292d86`（R63 的對象）：**不進**（使用者 2026-11-08 決定）。它的 `priv-tmpdir` 私有目錄前綴是 `o`，R63 第 3 列認定那是 R62 的錯，R64 改回 mkdtemp 預設的 `tmp`。
#     代價照實記：只寫得進 `<TMPDIR>/oXXXXXXXX/inject` 的求值者，`8292d86` 判繞過 #5、R64 起的樹判一致（R65 第 4 列 DO1）。
#   · `8984454`（R65 的對象）與 `3d94732`（R67 的對象）：不另列。兩棵樹的 `INJECT_PAYLOADS`（以 `extract_payloads` 抽出）與 `_inject_runs`、`_inject_key_modes`、
#     `_tmpdir_priv_ok`、`_inject_path_ok` 的程式（去掉 docstring 比 AST）都與 R68 的樹相同（2026-11-09 比對），新樹必須包含的聯集因此不變。日後改動注入設定時，
#     改動前的那棵樹要照本準則重新裁定。
# 清單外的樹不逐一延伸。
CLOSED_TREES = ("5b5a46d", "8b45659", "32d45ff", "b86bc53", "6490b57", "ecb77d9", "bf0c8a7", "28ec8c3", "636fcfe")
# R66（R65 logic／security：重抽用 7 碼縮寫，日後縮寫變得有歧義時 `cat-file` 失敗、被當成「沒有歷史」而整個跳過）：git 一律用完整 SHA。
TREE_SHA = {
    "5b5a46d": "5b5a46d914b8d5862a9fa17a37ef7855a0aa4942", "8b45659": "8b45659f581e124732ff99153250a1dfde2277b1",
    "32d45ff": "32d45ffb0d22b2ec383b80e966deecc61302a3ad", "b86bc53": "b86bc53ef7827985111c10c2d50855caae917254",
    "6490b57": "6490b5705e1258e9f4fdf41d92c3b54fe4967775", "ecb77d9": "ecb77d91297cfa58f923e6e9e2d2cd864de2213e",
    "bf0c8a7": "bf0c8a7155bbe834d429229cfc352e14e016c329", "28ec8c3": "28ec8c34b88866ff16cb6f2e04bad072d246895a",
    "636fcfe": "636fcfe327164d9fc55924293fbf843a40f4429b",
}

PAYLOAD_UNION = (
    'PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>$ORACLE_INJECT)]',   # 0  E 組（5b5a46d、28ec8c3；R56 起）
    '-v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>$ORACLE_INJECT)]',   # 1
    '-n -o -v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>$ORACLE_INJECT)]',   # 2
    'echo ORACLE-INJECT-MARKER >> "$ORACLE_INJECT"',   # 3
    'PWD[$(echo${IFS}ORACLE-INJECT-MARKER>&197)]',   # 4  S 組（8b45659 起）
    '-v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>&197)]',   # 5
    '-n -o -v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>&197)]',   # 6
    'echo ORACLE-INJECT-MARKER >&197',   # 7
    'PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>@@ORACLE-INJECT-PATH@@;echo${IFS}ORACLE-INJECT-MARKER>/dev/fd/197||:)]',   # 8  32d45ff 的複合寫法（R54 拆掉，R64 加回）
    '-v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>@@ORACLE-INJECT-PATH@@;echo${IFS}ORACLE-INJECT-MARKER>/dev/fd/197||:)]',   # 9
    '-n -o -v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>@@ORACLE-INJECT-PATH@@;echo${IFS}ORACLE-INJECT-MARKER>/dev/fd/197||:)]',   # 10
    'echo ORACLE-INJECT-MARKER >>@@ORACLE-INJECT-PATH@@; echo ORACLE-INJECT-MARKER >/dev/fd/197 || :',   # 11
    'PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>@@ORACLE-INJECT-PATH@@)]',   # 12  P 組（R54 起）
    '-v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>@@ORACLE-INJECT-PATH@@)]',   # 13
    '-n -o -v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>>@@ORACLE-INJECT-PATH@@)]',   # 14
    'PWD[$(echo${IFS}ORACLE-INJECT-MARKER>/dev/fd/197||:)]',   # 15  D 組（R54 起）
    '-v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>/dev/fd/197||:)]',   # 16
    '-n -o -v PWD[$(echo${IFS}ORACLE-INJECT-MARKER>/dev/fd/197||:)]',   # 17
    'echo ORACLE-INJECT-MARKER >>@@ORACLE-INJECT-PATH@@',   # 18
    'echo ORACLE-INJECT-MARKER >/dev/fd/197 || :',   # 19
)
HISTORICAL_PAYLOADS = {   # 樹 → 那棵樹的 `INJECT_PAYLOADS`（`PAYLOAD_UNION` 的索引，照原本的順序）
    '5b5a46d': (0, 1, 2, 3),
    '8b45659': (4, 5, 6, 7),
    '32d45ff': (4, 5, 6, 8, 9, 10, 11),
    'b86bc53': (4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19),
    '6490b57': (4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19, 0, 1, 2, 3),
    'ecb77d9': (4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19, 0, 1, 2, 3),
    'bf0c8a7': (4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19, 0, 1, 2, 3),
    '28ec8c3': (0, 1, 2, 3),
    '636fcfe': (4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19, 0, 1, 2, 3),
}
# R66（R65 logic M、requirements L）：凍結表的每一列另記一個摘要（那一列的字串依序以換行接起來的 sha256 前 16 碼）。前一版只有 git 重抽看得到「凍結表少一組」「兩列對調」，
# 而重抽在 CI（淺層 clone）與突變全輪（拷貝沒有 `.git`）都跳過——`5b5a46d` 那一列少第 4 組，`--selftest-matcher` 與真檢查都綠。這是同一個事實的第二份獨立紀錄：
# 改凍結表要同時改這裡（照 git 重抽的結果），單點改動會不一致。權威仍是 git 重抽（有歷史時）。
HISTORICAL_DIGEST = {
    '5b5a46d': '5268d9b16f12aa9e', '8b45659': '8836fa871229e3f8', '32d45ff': '4b76bb795d759df4',
    'b86bc53': '98d778649314c12f', '6490b57': 'a029923cb04b7dc5', 'ecb77d9': 'a029923cb04b7dc5',
    'bf0c8a7': 'a029923cb04b7dc5', '28ec8c3': '5268d9b16f12aa9e', '636fcfe': 'a029923cb04b7dc5',
}


def _row_digest(tree):
    import hashlib
    return hashlib.sha256("\n".join(PAYLOAD_UNION[i] for i in HISTORICAL_PAYLOADS.get(tree, ())).encode("utf-8")).hexdigest()[:16]


def _canon(s, marker, token):
    return s.replace(CANON_MARKER, marker).replace(CANON_TOKEN, token)


def payload_history_problems(payloads, marker, token):
    """凍結表每一列的每一個字串都要在 `payloads`（真檢查傳 `oracle.INJECT_PAYLOADS`）裡。回傳問題清單（空＝全過）。"""
    probs = []
    if tuple(sorted(HISTORICAL_PAYLOADS)) != tuple(sorted(CLOSED_TREES)):
        probs.append("凍結表的樹與封閉清單不一致：%s 對 %s" % (sorted(HISTORICAL_PAYLOADS), sorted(CLOSED_TREES)))
    for tree in CLOSED_TREES:   # 摘要或完整 SHA 少一棵樹時，下面兩道逐樹比對就會報（多出的鍵無害），不另比鍵集合

        try:
            digest = _row_digest(tree)
        except IndexError:   # R68（R67 logic L）：索引超出 PAYLOAD_UNION 由下面那一支報，這裡只算不一致
            digest = None
        if HISTORICAL_DIGEST.get(tree) != digest:
            probs.append("`%s` 那一列與它的摘要不一致（凍結表被改了而摘要沒改，或反過來；照 git 重抽的結果兩者一起改）" % tree)
        sha = TREE_SHA.get(tree, "")
        if not (re.fullmatch(r"[0-9a-f]{40}", sha) and sha.startswith(tree)):   # R68（R67 Codex C2）：前一版只看 startswith，退回 7 碼縮寫也通過
            probs.append("`%s` 的完整 SHA %r 不是 40 位十六進位、或不是以它開頭" % (tree, TREE_SHA.get(tree)))
    have = set(payloads)
    for tree in CLOSED_TREES:
        for pos, i in enumerate(HISTORICAL_PAYLOADS.get(tree, ())):
            if not 0 <= i < len(PAYLOAD_UNION):
                probs.append("`%s` 的第 %d 組索引 %d 超出 PAYLOAD_UNION" % (tree, pos + 1, i))
                continue
            s = _canon(PAYLOAD_UNION[i], marker, token)
            if s not in have:
                probs.append("`%s` 的第 %d 組 payload 不在 INJECT_PAYLOADS：%r" % (tree, pos + 1, s[:90]))
    return probs


class _Unev(Exception):
    pass


_EV_MAX = 1 << 16   # 抽出來的單一字串上限（R66，R65 security L：`_ev` 讀的是 git 歷史裡的原始碼，`"%050000000d" % 1`、連續倍增都能在幾毫秒內建出幾十 MB）；真的 payload 不到 200 字
_EV_WIDE_RE = re.compile(r"%[^a-zA-Z%]*(?:\d{5}|\*)")   # `%` 的寬度或精度有五位數以上，或用 `*` 由參數決定
_EV_SPEC_RE = re.compile(r"%[^a-zA-Z%]*")   # R68 宣稱查核（程式審查 #5）：每個轉換的旗標、寬度、精度；估計結果長度時把寬度與精度加進去（四位數寬度重複一萬次也是幾十 MB）


def _ev(n, env):
    """只認常數、名字、字串 `+` 與 `%` 的極小求值器：從舊樹的原始碼抽常數，**不執行**舊樹的任何程式碼。"""
    if isinstance(n, ast.Constant) and isinstance(n.value, (str, int)):
        if isinstance(n.value, str) and len(n.value) > _EV_MAX:   # R68（R67 logic L、Codex）：常數本身也要有上限
            raise _Unev("too long")
        if isinstance(n.value, int) and abs(n.value) >= 10 ** 18:   # 大整數的字串化在 3.9 上是平方時間，`%d` 也會膨脹
            raise _Unev("int too large")
        return n.value
    if isinstance(n, ast.Name):
        if n.id in env:
            return env[n.id]
        raise _Unev(n.id)
    if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Mod)):
        a, b = _ev(n.left, env), _ev(n.right, env)
        if isinstance(n.op, ast.Add) and isinstance(a, str) and isinstance(b, str):
            if len(a) + len(b) > _EV_MAX:
                raise _Unev("too long")
            return a + b
        if isinstance(n.op, ast.Mod) and isinstance(a, str):
            if len(a) > _EV_MAX or _EV_WIDE_RE.search(a):
                raise _Unev("format width")
            args = b if isinstance(b, tuple) else (b,)
            est = len(a) + sum(len(x) if isinstance(x, str) else len(repr(x)) for x in args) \
                + sum(int(d) for spec in _EV_SPEC_RE.findall(a) for d in re.findall(r"\d+", spec))
            if est > _EV_MAX:   # R68（R67 logic L、Codex）：展開前先估計結果——短格式字串重複、`%s` 的參數、巢狀 tuple 的 repr、每個轉換的寬度與精度
                raise _Unev("format result")
            try:
                r = a % b
            except (TypeError, ValueError) as e:
                raise _Unev("format") from e
            if len(r) > _EV_MAX:
                raise _Unev("format result")
            return r
        raise _Unev("binop")
    if isinstance(n, (ast.Tuple, ast.List)):
        return tuple(_ev(e, env) for e in n.elts)
    raise _Unev(type(n).__name__)


def extract_payloads(source):
    """從一份 `oracle.py` 原始碼抽出 (INJECT_MARKER, INJECT_PATH_TOKEN, INJECT_PAYLOADS)；抽不到的回 None。"""
    env = {}
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None, None, None
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            try:
                env[st.targets[0].id] = _ev(st.value, env)
            except (_Unev, RecursionError, MemoryError):   # R68（R67 logic L）：MemoryError 也不逃出去
                pass
    return env.get("INJECT_MARKER"), env.get("INJECT_PATH_TOKEN"), env.get("INJECT_PAYLOADS")


def _in_git_worktree(repo_root):
    """`repo_root` 或它的上層有沒有 `.git`（目錄或檔案）。只看檔案系統、不解析 git 的錯誤訊息（訊息會依 locale 翻譯）。"""
    p = pathlib.Path(repo_root).resolve()
    return any((d / ".git").exists() for d in (p, *p.parents))


def payload_history_regen_problems(repo_root, git=None, in_worktree=None):
    """有 git 歷史時，從九棵樹重新抽 `INJECT_PAYLOADS`、正規化後與凍結表逐列比對。回傳 (是否跑了, 問題清單)。
    只有三種情況跳過、回 (False, [原因])：不在 git 工作樹（`repo_root` 與上層都沒有 `.git`，例如突變全輪的拷貝）、git 能用而九棵樹的 `cat-file -e` 都不成功（確認沒有這些 commit：淺層 clone）、沒有 git 可執行檔；**部分**有、部分沒有就是問題（R66，R65 logic：前一版缺一棵就整個跳過）。
    git 不能用（`git rev-parse --git-dir` 失敗，例如 dubious ownership）是問題，不是「沒有歷史」——`cat-file -e <sha>^{commit}` 在缺物件與 git 拒絕這個 repo 時都回 rc=128，所以先確認 git 能用，再把各棵的失敗當成沒有這個 commit
    （R68 宣稱查核〔程式審查 #1〕：前一版把 rc≠0 一律當成「沒有」，git 拒絕這個 repo 時整輪跳過、還印錯的原因；R68 第一版的修法改成「rc=1 才是沒有」，Linux 預跑抓到缺物件其實是 128、淺層 clone 因此轉紅）。
    探測本身丟例外（逾時、解碼錯誤）也是問題，前面已確認有歷史的樹照樣比對（R68，R67 Codex C1：前一版任一棵的 `cat-file` 丟例外就整輪跳過）。
    `git(*args)` 回傳 `subprocess.CompletedProcess`（stdout 以 UTF-8 解碼；stderr 丟掉、不解碼——R68 宣稱查核〔程式審查 #6〕：前一版連用不到的 stderr 也嚴格解碼，非 UTF-8 的 git 訊息會讓淺層 clone 變成九條「探測失敗」）；
    `--selftest-matcher` 傳假的進來，不需要 git 就能測這段（R65 logic M：前一版這段沒有網）。`in_worktree` 沒給時：真的 git 看檔案系統，假的 git 當成在工作樹裡。"""
    if in_worktree is None:
        in_worktree = git is not None or _in_git_worktree(repo_root)
    if not in_worktree:
        return False, ["不在 git 工作樹（這個目錄與上層都找不到 .git）"]   # 不印路徑：這行會進 selfcheck 的輸出與殺手證據
    if git is None:
        def git(*a):
            return subprocess.run(["git", "-C", repo_root] + list(a), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", timeout=60)
    try:
        rp = git("rev-parse", "--git-dir")
    except FileNotFoundError as e:
        return False, ["沒有可用的 git（%s）" % e]
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as e:
        return True, ["探測 git 失敗（rev-parse：%s）" % type(e).__name__]
    if rp.returncode != 0:
        return True, ["git 不能用（rev-parse rc=%d，例如 dubious ownership）：九棵樹的歷史都沒有比對" % rp.returncode]
    present, missing, failed, nogit = [], [], [], []
    for tree in CLOSED_TREES:
        try:
            rc = git("cat-file", "-e", TREE_SHA.get(tree, tree) + "^{commit}").returncode
        except FileNotFoundError as e:   # 沒有 git 可執行檔
            nogit.append((tree, e))
            continue
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as e:
            failed.append((tree, type(e).__name__))
            continue
        (present if rc == 0 else missing).append(tree)   # git 能用（上面確認過），各棵的失敗就是沒有這個 commit（缺物件時 rc=128）
    if len(nogit) == len(CLOSED_TREES):
        return False, ["沒有可用的 git（%s）" % nogit[0][1]]
    if not present and not failed and not nogit:
        return False, ["九棵樹都沒有 git 歷史（淺層 clone）"]
    probs = ["`%s`：探測 git 歷史失敗（%s）" % (t, e) for t, e in failed] + ["`%s`：探測 git 歷史失敗（%s）" % (t, type(e).__name__) for t, e in nogit]
    probs += ["`%s`：其他樹有 git 歷史、這棵沒有（完整 SHA 寫錯，或歷史被截斷）" % t for t in missing] if present else \
        ["`%s`：探測失敗的樹之外，其餘都沒有 git 歷史" % t for t in missing]
    for tree in present:
        try:
            r = git("show", "%s:%s" % (TREE_SHA.get(tree, tree), ORACLE_REL))
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as e:
            probs.append("`%s`：讀 %s 失敗（%s）" % (tree, ORACLE_REL, type(e).__name__))
            continue
        if r.returncode != 0:
            probs.append("`%s`：讀不到 %s" % (tree, ORACLE_REL))
            continue
        probs += _regen_one(tree, r.stdout)
    return True, probs


def _regen_one(tree, source):
    """一棵樹：從它的 `oracle.py` 原始碼重抽 payload、正規化後與凍結表那一列逐組比對（獨立成函式，`--selftest-matcher` 不需要 git 就能測它）。"""
    idx = HISTORICAL_PAYLOADS.get(tree, ())
    if any(not 0 <= i < len(PAYLOAD_UNION) for i in idx):   # R68 宣稱查核（程式審查 #4）：前一版在這裡丟 IndexError，凍結表比對已算好的「超出」訊息跟著丟掉
        return ["`%s`：凍結表的索引超出 PAYLOAD_UNION" % tree]
    pays = extract_payloads(source)[2]
    if not pays:
        return ["`%s`：抽不到 INJECT_PAYLOADS" % tree]
    # R66（R65 Codex）：前一版用全域字串替換把標記換成凍結的寫法，分不出字面文字與標記，標記改了也照樣過。九棵樹的標記與路徑記號都是同一個值（R65 logic 實測），所以直接比對字串，不正規化；標記不同時下面的比對就會報。
    got = tuple(pays)
    want = tuple(PAYLOAD_UNION[i] for i in idx)
    if got != want:
        return ["`%s`：凍結表與 git 歷史不符（凍結 %d 組、歷史 %d 組）" % (tree, len(want), len(got))]
    return []


# ── 逐目標履行（R64；R63 第 3、4 列）──────────────────────────────────────────────────────────────────────────────
# 每個 `_inject_runs` 目標，`run_script` 實際建出的哨兵：`oi` 是步驟看到的 `$ORACLE_INJECT`（經 `norm`：私有目錄換成 `<PRIV>`、步驟的暫存目錄換成 `<TMP>`）的完整比對，
# `pb` 是私有目錄名（`${ORACLE_PRIV##*/}`）的完整比對，`parent` 是私有目錄的上一層（`short`＝`_short_tmp()`，`/tmp` 不可寫時退回 `gettempdir()`；`tmpdir`＝`gettempdir()`）。
# 每一個目標都要求哨兵檔預先建好（`PRE=1`；求值者只准改既有的檔時 `>>` 建不出來）、寫進去之後神諭偵測得到。封閉列舉：鍵集合必須等於 manifest 的目標集合。
_RND = r"[A-Za-z0-9_]{8}"
TARGET_SHAPES = {
    "priv":        {"oi": r"<PRIV>/i",                          "pb": r"o" + _RND,   "parent": "short"},    # R54 起：/tmp/oXXXXXXXX/i
    "priv-tmpdir": {"oi": r"<PRIV>/inject",                     "pb": r"tmp" + _RND, "parent": "tmpdir"},   # 32d45ff：<TMPDIR>/tmpXXXXXXXX/inject（mkdtemp 預設前綴）
    "cwd":         {"oi": r"<TMP>/\.orc-" + _RND + r"/inject"},                                            # 5b5a46d、R58 起
    "cwd-abs":     {"oi": r"<TMP>/\.orc-" + _RND + r"/inject"},                                            # R60：絕對路徑
    "cwd-vis":     {"oi": r"<TMP>/inject"},                                                              # 2835ead／28ec8c3：cwd 頂層
    "cwd-vis-abs": {"oi": r"<TMP>/inject"},                                                              # R62：絕對路徑
}
# R66（R65 logic L）：這張表描述的是**履行檢查那一次執行**（加引號的 E payload）實際建出的形狀。加引號的 payload 一律拿絕對路徑（`_cwd_env_value`，`5b5a46d`、`28ec8c3` 也一律是絕對路徑），
# 所以 `cwd`、`cwd-vis` 也要求 `<TMP>/`；前一版接受相對路徑，R58 第一個草稿的退步（加引號的也給相對路徑）在這裡看不到。`-abs` 與非 `-abs` 的差別（`force_abs`）只在
# 暫存目錄含空白、payload 不加引號時才看得到，這張表量不到，由 aud 與 PX 探針守。
FULFIL_STEP = ("printf 'OI=%s\\n' \"$ORACLE_INJECT\"; if [ -f \"$ORACLE_INJECT\" ]; then echo PRE=1; else echo PRE=0; fi; "
               "printf 'PB=%s\\nPP=%s\\n' \"${ORACLE_PRIV##*/}\" \"${ORACLE_PRIV%/*}\"; /bin/bash -c \"$PR_TITLE\"")


def fulfillment_shape_problems(target, out, hit, short_parent, tmpdir_parent):
    """`target` 的那一次執行：`out` 是正規化後的 stdout，`hit` 是神諭有沒有偵測到注入。回傳問題清單。"""
    shape = TARGET_SHAPES.get(target)
    if shape is None:
        return ["目標 %r 沒有登記形狀（TARGET_SHAPES 要與 manifest 的目標集合相同）" % target]
    kv = dict(l.split("=", 1) for l in out.splitlines() if "=" in l and l.split("=", 1)[0] in ("OI", "PRE", "PB", "PP"))
    probs = []
    if not re.fullmatch(shape["oi"], kv.get("OI", "")):
        probs.append("目標 %s：$ORACLE_INJECT 是 %r，不符合 %s" % (target, kv.get("OI"), shape["oi"]))
    if kv.get("PRE") != "1":
        probs.append("目標 %s：哨兵檔沒有預先建好（PRE=%s）" % (target, kv.get("PRE")))
    if "pb" in shape:
        if not re.fullmatch(shape["pb"], kv.get("PB", "")):
            probs.append("目標 %s：私有目錄名 %r 不符合 %s" % (target, kv.get("PB"), shape["pb"]))
        want = short_parent if shape["parent"] == "short" else tmpdir_parent
        if os.path.realpath(kv.get("PP", "") or "/nonexistent-parent") != os.path.realpath(want):
            probs.append("目標 %s：私有目錄的上一層是 %r，應是 %r" % (target, kv.get("PP"), want))
    if not hit:
        probs.append("目標 %s：寫進 $ORACLE_INJECT 之後神諭沒有偵測到注入" % target)
    return probs


def target_fulfillment_problems(mod, manifest_targets, tmpdir=None):
    """對 `mod`（載入的 `oracle.py`）的每一個目標真的跑一次 `run_script`，比對 `TARGET_SHAPES`。回傳 (問題清單, 跳過的目標)。
    R66（R65 logic M、security／regression L）：`run_script` 建不出某個目標的路徑時會 `sys.exit`（例如 `TMPDIR` 含空白時 `priv-tmpdir` 的路徑不能不加引號放進 payload）。
    前一版沒有接，selfcheck 在第 1 項之前就整個結束。現在逐目標接住：這個環境的 `_inject_runs` **不產生**的目標（神諭在這裡本來就不用它）記為跳過、印出來；產生的目標結束了就是問題。
    `tmpdir`：`priv-tmpdir` 的上一層應是什麼（預設 `tempfile.gettempdir()`；`--selftest-matcher` 傳假的）。"""
    import contextlib
    import io
    import shutil
    tmpdir = tmpdir or tempfile.gettempdir()
    probs, skipped = [], []
    if set(TARGET_SHAPES) != set(manifest_targets):
        probs.append("TARGET_SHAPES 的目標 %s 與 manifest 的目標 %s 不同" % (sorted(TARGET_SHAPES), sorted(manifest_targets)))
    e_quoted = next(pl for pl in mod.INJECT_PAYLOADS if '"$ORACLE_INJECT"' in pl)
    short = mod._short_tmp() or tmpdir
    used_here = {to for _pl, to in mod._inject_runs(mod._tmpdir_spaced(), mod._tmpdir_priv_ok())}
    for target in sorted(TARGET_SHAPES):
        sd = tempfile.mkdtemp(prefix="oracle-fulfil-")
        try:
            sb = os.path.join(sd, "bin")
            os.mkdir(sb)
            with contextlib.redirect_stderr(io.StringIO()):
                res = mod.run_script(FULFIL_STEP, mod.pick_bash(), sb, None, extra=True, inject=e_quoted, inject_to=target)
        except SystemExit as e:
            if target in used_here:
                probs.append("目標 %s：run_script 結束（%s），而這個環境的 _inject_runs 會用到它" % (target, e))
            else:
                skipped.append(target)
            continue
        finally:
            shutil.rmtree(sd, ignore_errors=True)
        obs = res[1]
        if obs is None:
            probs.append("目標 %s：run_script 逾時" % target)
            continue
        out = obs[1].decode("utf-8", "replace") if isinstance(obs[1], bytes) else str(obs[1])
        probs += fulfillment_shape_problems(target, out, bool(res[4]["inject"]), short, tmpdir)
    return probs, skipped
