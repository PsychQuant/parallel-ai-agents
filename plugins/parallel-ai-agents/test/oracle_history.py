#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歷史注入設定的凍結表與逐目標履行檢查（R64；#33 verify R63 第 2、3、4 列）。由 `oracle_selfcheck.py` 匯入，不單獨執行。

R61 的處方是把「單調」改成機械檢查：`oracle_selfcheck.py` 的 `HISTORICAL_SENTINEL_POSITIONS` 凍結了**哨兵目標的名稱與條件**。R63 證明那張表不夠：
(1) payload 字串集合不在表裡——`32d45ff` 的四個複合 payload（含 `;`；路徑佔位符算在內長 95～117 字）從 R54 起就不在 `INJECT_PAYLOADS`，以 PR 文字特徵把關的求值者因此舊樹判繞過、新樹判一致（第 2 列）；
(2) 路徑形狀不在表裡——`priv-tmpdir` 的私有目錄前綴寫成 `o`，`32d45ff` 是 mkdtemp 預設的 `tmp`（第 3 列）；隱藏 cwd 哨兵的路徑壞掉（`.orc-*/injectx`），110 項 selfcheck 全綠（第 4 列的 X2）。
這個模組補上兩件事，兩件都是**封閉的**：

- `PAYLOAD_UNION`／`HISTORICAL_PAYLOADS`：封閉清單各樹的 `INJECT_PAYLOADS`（R61 停止規則的八棵樹，加上 R61 驗過的 `636fcfe`），以 ast 從 `git show <sha>:…/oracle.py` 抽出後凍結（標記與路徑記號在九棵樹都是同一個值，R66 起重抽時直接比對，不再正規化）。
  `payload_history_problems` 要求每一列的每一個字串都在現在的 `INJECT_PAYLOADS` 裡；`payload_history_regen_problems` 在有 git 歷史時重新抽一次、與凍結表逐列比對（只有三種情況跳過並說明、不算通過：這個目錄沒有 `.git`、沒有 git 可執行檔、git 明確回答九棵樹的 commit 都不在〔淺層 clone 就是這樣；重抽不向遠端抓〕）。
- `TARGET_SHAPES`：`_inject_runs` 的每一個目標，`run_script` **實際建出**的哨兵路徑形狀、上一層目錄、是否預先建檔，以及寫進去之後神諭有沒有偵測到。`target_fulfillment_problems` 對每個目標真的跑一次 `run_script`。

**它不守的**：鍵模式軸（`_inject_key_modes`，由 aud 的值比較守）；跨執行持久狀態（H3，停止規則的第三個豁免類，見 `oracle.py`〈已知限制〉(9)）；求值者在程式內轉換 PR 文字（L1 族）；
**這一次執行的環境裡、在比較的兩方之間不同的特徵**（R65 DA 的「儀器指紋」：神諭設定、建好或不提供的東西，例如導出的環境變數 `ORACLE_INJECT`、`ORACLE_PRIV`，繼承的 fd 197，cwd 與 stub 目錄裡預先建好的檔案；封閉的五個類別見 `oracle.py`〈已知限制〉(11)）——舊樹在這一軸與現在不同，
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
#   · `8984454`（R65 的對象）與 `3d94732`（R67 的對象）：**暫不另列，待使用者確認**（R69 DA：本規則寫的是由使用者裁定，這一條是作者自己寫下的，沒有使用者的裁定紀錄；
#     已列進待使用者決定的事項——確認不列，或把規則改成「注入設定與某棵已列入的樹相同的對象，作者可以不列並記錄比對」）。作者不列的理由：兩棵樹的 `INJECT_PAYLOADS`（以 `extract_payloads` 抽出）與 `_inject_runs`、`_inject_key_modes`、
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
_EV_TOTAL = 1 << 20   # `+` 與 `%` **新造**的字串合計上限（R70 查核）：單一字串有上限、變數的個數沒有——兩千個 `B<i> = A + "x"` 各存一份接近上限的字串，
#                      96 KB 的原始碼就用掉 128 MiB。常數與 tuple 不算（它們的大小受原始碼長度限制，不放大）。九棵封閉樹實際新造的合計見 `_spend` 的說明。
_EV_SPENT = " spent"   # `env` 裡記已用預算的鍵：含空白，不會和任何識別字相撞
_EV_SPEC_RE = re.compile(r"%[^a-zA-Z%]*")   # R68 宣稱查核（程式審查 #5）：每個轉換的旗標、寬度、精度；估計結果長度時把寬度與精度加進去（四位數寬度重複一萬次也是幾十 MB）


def _spend(env, n):
    """把新造的 `n` 個字元記進 `env` 的預算；合計超過 `_EV_TOTAL` 就不抽這一個（之後要新造字串的指派也都抽不到）。
    2026-11-10 實測：九棵封閉樹與現在的 `oracle.py`，`+` 與 `%` 新造的字串合計最多 3,990 個字元，是預算（1 MiB）的 1/262。"""
    env[_EV_SPENT] = env.get(_EV_SPENT, 0) + n
    if env[_EV_SPENT] > _EV_TOTAL:
        raise _Unev("total")


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
            _spend(env, len(a) + len(b))   # 先記帳再造：預算用完之後不再配置
            return a + b
        if isinstance(n.op, ast.Mod) and isinstance(a, str):
            if len(a) > _EV_MAX or _EV_WIDE_RE.search(a):
                raise _Unev("format width")
            args = b if isinstance(b, tuple) else (b,)
            # R70（R69 Codex、logic、security）：`%` 的參數只收字串與整數（整數在常數那一關已限制在 19 位以內）。前一版對其他型別用 `len(repr(x))` 估計——
            # repr 會先把整個巢狀 tuple 展成字串：共用子結構的 `X = (X, X)` 重複 22 次，292 位元組的原始碼就用掉 5 秒與約 70 MiB，估計本身成了它要防的那個尖峰。
            # 歷史上的 `oracle.py` 只拿字串當 `%` 的參數；巢狀 tuple 當參數的原始碼一律不抽。
            if not all(isinstance(x, (str, int)) for x in args):
                raise _Unev("format arg")
            est = len(a) + sum(len(x) if isinstance(x, str) else 20 for x in args) \
                + sum(int(d) for spec in _EV_SPEC_RE.findall(a) for d in re.findall(r"\d+", spec))
            if est > _EV_MAX:   # R68（R67 logic L、Codex）：展開前先估計結果——短格式字串重複、`%s` 的參數、每個轉換的寬度與精度
                raise _Unev("format result")
            try:
                r = a % b
            except (TypeError, ValueError, ArithmeticError) as e:   # R70（R69 logic）：`"%c" % 1114112` 丟 OverflowError（ArithmeticError 的子類）
                raise _Unev("format") from e
            if len(r) > _EV_MAX:
                raise _Unev("format result")
            _spend(env, len(r))   # 記實際長度（估計只是上界的近似，`%r` 會超過它）；這一個已經造出來了，超過預算時丟掉它
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
    """`repo_root` 自己有沒有 `.git`（目錄或檔案）。只看檔案系統、不解析 git 的錯誤訊息（訊息會依 locale 翻譯）。
    R70（R69 security、logic）：只看 `repo_root` 這一層。前一版（R68）連上層一起看：上層的 `.git` 是別人的 repo——多人共用的主機上任何人建一個 `/tmp/.git`，
    建在那底下的突變副本就從「跳過」變成紅；暫存目錄剛好在某個 checkout 裡時，「沒有 .git」的案也跟著不成立。`repo_root` 依構造就是這個專案的頂層，
    它自己的 checkout（含 linked worktree，那時 `.git` 是檔案）一定在這一層有 `.git`。"""
    return (pathlib.Path(repo_root) / ".git").exists()


def _same_dir(a, b):
    """兩個路徑是不是同一個目錄。先問檔案系統（`os.path.samefile`：符號連結、大小寫不分的檔案系統上大小寫不同的拼法都算同一個）；問不到
    （任何 `OSError`：任一個不存在〔`--selftest-matcher` 的假路徑〕、沒有權限、符號連結成環）才比 realpath 的字串。兩個都不能是空字串——
    `realpath("")` 是目前的目錄，git 沒有回報頂層時不能因此剛好相符。"""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return bool(a) and bool(b) and os.path.realpath(a) == os.path.realpath(b)


# git 自己列為「跟著 repo 走」的環境變數（`git rev-parse --local-env-vars`，2.55；另加 `GIT_NAMESPACE`）。呼叫者的環境帶著它們時，`git -C <目錄>` 作用的就不是那個目錄的 repo：
# git 在 linked worktree 的 hook 與 `rebase --exec` 裡會匯出 `GIT_DIR`（R69 DA 實測）；一般 repo 的 pre-commit 匯出的是 `GIT_INDEX_FILE` 與 `GIT_PREFIX`、
# `rebase --exec` 匯出 `GIT_PREFIX`（2.55 實測；hook 與 `rebase --exec` 另外匯出的——例如 `GIT_AUTHOR_*`、`GIT_EDITOR`、`GIT_EXEC_PATH`、`GIT_SEQUENCE_EDITOR`——不在這份名單裡，它們不決定 git 作用在哪個 repo）。
_GIT_REPO_ENV = ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
                 "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE",
                 "GIT_COMMON_DIR", "GIT_NAMESPACE")


def git_env(base=None):
    """跑 git 用的環境：拿掉 `_GIT_REPO_ENV`，關掉 replace refs（`refs/replace/` 能讓 `git show <完整 SHA>` 回別的內容），並且**不向遠端抓物件**。
    R70 查核：partial clone（`--filter=blob:none`）裡，git 查到本機沒有的物件會自己向 promisor remote 抓——重抽的 `cat-file --batch-check` 與 `git show`
    因此連網、把抓來的 pack 寫進呼叫者 repo 的物件庫（2.55 實測：淺層＋blobless 的 clone 跑一次重抽，pack 檔從 4 個變 72 個，回的還是「九棵都在、相符」）。
    兩道：`GIT_NO_LAZY_FETCH=1`（git 2.44 起：不嘗試）；`GIT_ALLOW_PROTOCOL` 設成空字串（任何傳輸都不允許，嘗試了也抓不到；2.43.0〔不認得前一個變數〕與 2.55 實測擋得住，其他版本沒有量）。
    擋下之後：本機沒有那個 commit 就照實回 `missing`；commit 在而 `oracle.py` 的 blob 不在（非淺層的 blobless clone）就是「讀不到」——是問題、不是跳過。"""
    env = {k: v for k, v in (os.environ if base is None else base).items() if k not in _GIT_REPO_ENV}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_ALLOW_PROTOCOL"] = ""
    return env


def real_git(repo_root):
    """回傳 `git(*args, input=None)`：在 `repo_root` 跑真的 git，環境是 `git_env()`，60 秒逾時；stdout 以 UTF-8 解碼，stderr 丟掉、不解碼
    （R68 宣稱查核〔程式審查 #6〕：前一版連用不到的 stderr 也嚴格解碼，非 UTF-8 的 git 訊息會把跳過變成「探測失敗」）。"""
    def git(*a, input=None):
        return subprocess.run(["git", "-C", repo_root] + list(a), input=input, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, encoding="utf-8", timeout=60, env=git_env())
    return git


_BATCH_PRESENT_RE = re.compile(r"([0-9a-f]{40}) commit \d+")
_PROBE_ERRORS = (OSError, subprocess.SubprocessError, UnicodeDecodeError)


def payload_history_regen_problems(repo_root, git=None, in_worktree=None):
    """有 git 歷史時，從九棵樹重新抽 `INJECT_PAYLOADS`、與凍結表逐列比對。回傳 (是否跑了, 問題清單)。
    **只有三種情況跳過、回 (False, [原因])，其餘一律是問題**（R66、R68、R70 三次改寫都是因為「跳過」收得太寬）：
      (1) `repo_root` 沒有 `.git`（不是 git 工作樹：突變全輪的拷貝、archive 副本）；
      (2) 沒有 git 可執行檔（第一次呼叫 git 就 `FileNotFoundError`）；
      (3) git 明確回答九棵樹的 commit **都不在**這個 repo 的物件庫裡（`cat-file --batch-check` 九行都是「問的那個輸入 + ` missing`」；淺層 clone 就是這樣。
          git 的環境不讓它向遠端抓〔`git_env`〕，所以淺層的 partial clone 也走這一條，不會連網把歷史補回來）。
    R70（R69 第 1 列；Codex、logic、security、DA）：(3) 只認 `--batch-check` 的 `missing`。前一版在 `rev-parse` 成功之後把 `cat-file -e` 的**任何**非零碼都當成
    「沒有這個 commit」——被訊號終止、用法錯誤、物件庫讀不了都一樣，九棵都如此就印「淺層 clone」跳過；也沒有確認 git 找到的是哪個 repo，環境裡的 `GIT_DIR`
    指到別處時，有完整歷史的工作樹照樣跳過。現在：git 的環境拿掉 repo-local 變數（`git_env`）；先以 `rev-parse --show-toplevel` 確認 git 能用、而且它找到的工作樹就是
    `repo_root`（自己的 `.git` 壞掉時 git 會往上找到別的 repo）；再用**一次** `cat-file --batch-check` 問九棵樹，真的 git 對在與不在都回 rc=0、各有明確的一行
    （2.54／2.55 實測），結束碼非零、行數不符、看不懂的行、SHA 不符、例外，全部是探測失敗。**部分**在、部分不在也是問題（R66）。
    `git(*args, input=None)` 回傳有 `returncode` 與 `stdout` 的物件；`--selftest-matcher` 傳假的進來，不需要 git 就能測這段。`in_worktree` 沒給時：
    真的 git 看檔案系統，假的 git 當成在工作樹裡。"""
    if in_worktree is None:
        in_worktree = git is not None or _in_git_worktree(repo_root)
    if not in_worktree:
        return False, ["不在 git 工作樹（這個目錄沒有 .git）"]   # 不印路徑：這行會進 selfcheck 的輸出與殺手證據
    if git is None:
        git = real_git(repo_root)
    try:
        rp = git("rev-parse", "--show-toplevel")
    except FileNotFoundError as e:
        return False, ["沒有可用的 git（%s）" % e]
    except _PROBE_ERRORS as e:
        return True, ["探測 git 失敗（rev-parse：%s）" % type(e).__name__]
    if rp.returncode != 0:
        return True, ["git 不能用（rev-parse rc=%d，例如 dubious ownership）：九棵樹的歷史都沒有比對" % rp.returncode]
    top = rp.stdout[:-1] if rp.stdout.endswith("\n") else rp.stdout   # 只去掉 git 自己加的那一個換行：目錄名尾端的空白與換行是名字的一部分（`strip()` 會把 `repo ` 當成 `repo`）
    if not _same_dir(top, repo_root):   # R70 查核：前一版比 realpath 的字串，大小寫不分的檔案系統上以另一種大小寫進到這個目錄時假紅
        return True, ["git 找到的工作樹不是這個目錄（這個目錄的 .git 壞了，或環境把 git 導到別處）：九棵樹的歷史都沒有比對"]
    want = ["%s^{commit}" % TREE_SHA.get(tree, tree) for tree in CLOSED_TREES]
    try:
        bc = git("cat-file", "--batch-check", input="".join(w + "\n" for w in want))
    except _PROBE_ERRORS as e:
        return True, ["探測 git 歷史失敗（cat-file --batch-check：%s）" % type(e).__name__]
    lines = bc.stdout.splitlines()
    if bc.returncode != 0 or len(lines) != len(want):
        return True, ["探測 git 歷史失敗（cat-file --batch-check rc=%d，回了 %d 行、問了 %d 棵）" % (bc.returncode, len(lines), len(want))]
    present, missing, probs = [], [], []
    for tree, w, line in zip(CLOSED_TREES, want, lines):
        m = _BATCH_PRESENT_RE.fullmatch(line)
        if m and m.group(1) == w.split("^")[0]:
            present.append(tree)
        elif line == w + " missing":
            missing.append(tree)
        else:
            probs.append("`%s`：探測 git 歷史失敗（cat-file --batch-check 回了看不懂的一行）" % tree)
    if not present and not probs:
        return False, ["git 回答九棵樹的 commit 都不在這個 repo 的物件庫裡（淺層 clone 就是這樣；重抽不向遠端抓）"]
    probs += ["`%s`：其他樹有 git 歷史、這棵沒有（完整 SHA 寫錯，或歷史被截斷）" % t for t in missing] if present else \
        ["`%s`：探測失敗的樹之外，這棵不在這個 repo 裡" % t for t in missing]
    for tree in present:
        try:
            r = git("show", "%s:%s" % (TREE_SHA.get(tree, tree), ORACLE_REL))
        except _PROBE_ERRORS as e:
            probs.append("`%s`：讀 %s 失敗（%s）" % (tree, ORACLE_REL, type(e).__name__))
            continue
        if r.returncode != 0:
            probs.append("`%s`：讀不到 %s（commit 在、這個檔的內容不在本機時也是這樣，例如 blobless clone；重抽不向遠端抓）" % (tree, ORACLE_REL))
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
