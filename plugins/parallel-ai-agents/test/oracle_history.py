#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歷史注入設定的凍結表與逐目標履行檢查（R64；#33 verify R63 第 2、3、4 列）。由 `oracle_selfcheck.py` 匯入，不單獨執行。

R61 的處方是把「單調」改成機械檢查：`oracle_selfcheck.py` 的 `HISTORICAL_SENTINEL_POSITIONS` 凍結了**哨兵目標的名稱與條件**。R63 證明那張表不夠：
(1) payload 字串集合不在表裡——`32d45ff` 的四個複合 payload（含 `;`；路徑佔位符算在內長 95～117 字）從 R54 起就不在 `INJECT_PAYLOADS`，以 PR 文字特徵把關的求值者因此舊樹判繞過、新樹判一致（第 2 列）；
(2) 路徑形狀不在表裡——`priv-tmpdir` 的私有目錄前綴寫成 `o`，`32d45ff` 是 mkdtemp 預設的 `tmp`（第 3 列）；隱藏 cwd 哨兵的路徑壞掉（`.orc-*/injectx`），110 項 selfcheck 全綠（第 4 列的 X2）。
這個模組補上兩件事，兩件都是**封閉的**：

- `PAYLOAD_UNION`／`HISTORICAL_PAYLOADS`：封閉清單各樹的 `INJECT_PAYLOADS`（R61 停止規則的八棵樹，加上 R61 驗過的 `636fcfe`），以 ast 從 `git show <sha>:…/oracle.py` 抽出、把標記與路徑記號正規化成現在的寫法後凍結。
  `payload_history_problems` 要求每一列的每一個字串都在現在的 `INJECT_PAYLOADS` 裡；`payload_history_regen_problems` 在有 git 歷史時重新抽一次、與凍結表逐列比對（淺層 clone 沒有歷史就跳過並說明，不算通過）。
- `TARGET_SHAPES`：`_inject_runs` 的每一個目標，`run_script` **實際建出**的哨兵路徑形狀、上一層目錄、是否預先建檔，以及寫進去之後神諭有沒有偵測到。`target_fulfillment_problems` 對每個目標真的跑一次 `run_script`。

**它不守的**：鍵模式軸（`_inject_key_modes`，由 aud 的值比較守）；跨執行持久狀態（H3，停止規則的第三個豁免類，見 `oracle.py`〈已知限制〉(9)）；求值者在程式內轉換 PR 文字（L1 族）。
"""
import ast
import os
import re
import subprocess
import tempfile

ORACLE_REL = "plugins/parallel-ai-agents/test/oracle.py"
CANON_MARKER = "ORACLE-INJECT-MARKER"          # 凍結表的字串用這兩個記號寫；比對時換成 oracle 現在的值
CANON_TOKEN = "@@ORACLE-INJECT-PATH@@"

# 封閉清單，只有這九棵樹（R61 停止規則的八棵，加上 R61 驗過的 `636fcfe`）；新增一棵樹要同時在這裡與 `HISTORICAL_PAYLOADS` 加一列，拿掉一列要有書面理由。
CLOSED_TREES = ("5b5a46d", "8b45659", "32d45ff", "b86bc53", "6490b57", "ecb77d9", "bf0c8a7", "28ec8c3", "636fcfe")

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


def _canon(s, marker, token):
    return s.replace(CANON_MARKER, marker).replace(CANON_TOKEN, token)


def payload_history_problems(payloads, marker, token):
    """凍結表每一列的每一個字串都要在 `payloads`（真檢查傳 `oracle.INJECT_PAYLOADS`）裡。回傳問題清單（空＝全過）。"""
    probs = []
    if tuple(sorted(HISTORICAL_PAYLOADS)) != tuple(sorted(CLOSED_TREES)):
        probs.append("凍結表的樹與封閉清單不一致：%s 對 %s" % (sorted(HISTORICAL_PAYLOADS), sorted(CLOSED_TREES)))
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


def _ev(n, env):
    """只認常數、名字、字串 `+` 與 `%` 的極小求值器：從舊樹的原始碼抽常數，**不執行**舊樹的任何程式碼。"""
    if isinstance(n, ast.Constant) and isinstance(n.value, (str, int)):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in env:
            return env[n.id]
        raise _Unev(n.id)
    if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Mod)):
        a, b = _ev(n.left, env), _ev(n.right, env)
        if isinstance(n.op, ast.Add) and isinstance(a, str) and isinstance(b, str):
            return a + b
        if isinstance(n.op, ast.Mod) and isinstance(a, str):
            return a % b
        raise _Unev("binop")
    if isinstance(n, (ast.Tuple, ast.List)):
        return tuple(_ev(e, env) for e in n.elts)
    raise _Unev(type(n).__name__)


def extract_payloads(source):
    """從一份 `oracle.py` 原始碼抽出 (INJECT_MARKER, INJECT_PATH_TOKEN, INJECT_PAYLOADS)；抽不到的回 None。"""
    env = {}
    for st in ast.parse(source).body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            try:
                env[st.targets[0].id] = _ev(st.value, env)
            except _Unev:
                pass
    return env.get("INJECT_MARKER"), env.get("INJECT_PATH_TOKEN"), env.get("INJECT_PAYLOADS")


def payload_history_regen_problems(repo_root):
    """有 git 歷史時，從九棵樹重新抽 `INJECT_PAYLOADS`、正規化後與凍結表逐列比對。回傳 (是否跑了, 問題清單)：沒有歷史（淺層 clone、不在 git 工作樹）回 (False, [原因])。"""
    def git(*a):
        return subprocess.run(["git", "-C", repo_root] + list(a), capture_output=True, text=True, timeout=60)
    try:
        missing = [t for t in CLOSED_TREES if git("cat-file", "-e", t + "^{commit}").returncode != 0]
    except (OSError, subprocess.SubprocessError) as e:
        return False, ["沒有可用的 git（%s）" % e]
    if missing:
        return False, ["沒有這幾棵樹的 git 歷史：%s" % ", ".join(missing)]
    probs = []
    for tree in CLOSED_TREES:
        r = git("show", "%s:%s" % (tree, ORACLE_REL))
        if r.returncode != 0:
            probs.append("`%s`：讀不到 %s" % (tree, ORACLE_REL))
            continue
        probs += _regen_one(tree, r.stdout)
    return True, probs


def _regen_one(tree, source):
    """一棵樹：從它的 `oracle.py` 原始碼重抽 payload、正規化後與凍結表那一列逐組比對（獨立成函式，`--selftest-matcher` 不需要 git 就能測它）。"""
    marker, token, pays = extract_payloads(source)
    if not pays:
        return ["`%s`：抽不到 INJECT_PAYLOADS" % tree]
    got = tuple(p.replace(marker or "\0", CANON_MARKER).replace(token or "\0", CANON_TOKEN) for p in pays)
    want = tuple(PAYLOAD_UNION[i] for i in HISTORICAL_PAYLOADS.get(tree, ()))
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
    "cwd":         {"oi": r"(?:<TMP>/)?\.orc-" + _RND + r"/inject"},                                       # 5b5a46d、R58 起
    "cwd-abs":     {"oi": r"<TMP>/\.orc-" + _RND + r"/inject"},                                            # R60：絕對路徑
    "cwd-vis":     {"oi": r"(?:<TMP>/)?inject"},                                                         # 2835ead／28ec8c3：cwd 頂層
    "cwd-vis-abs": {"oi": r"<TMP>/inject"},                                                              # R62：絕對路徑
}
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


def target_fulfillment_problems(mod, manifest_targets):
    """對 `mod`（載入的 `oracle.py`）的每一個目標真的跑一次 `run_script`，比對 `TARGET_SHAPES`。回傳問題清單。"""
    import contextlib
    import io
    import shutil
    probs = []
    if set(TARGET_SHAPES) != set(manifest_targets):
        probs.append("TARGET_SHAPES 的目標 %s 與 manifest 的目標 %s 不同" % (sorted(TARGET_SHAPES), sorted(manifest_targets)))
    e_quoted = next(pl for pl in mod.INJECT_PAYLOADS if '"$ORACLE_INJECT"' in pl)
    short = mod._short_tmp() or tempfile.gettempdir()
    for target in sorted(TARGET_SHAPES):
        sd = tempfile.mkdtemp(prefix="oracle-fulfil-")
        try:
            sb = os.path.join(sd, "bin")
            os.mkdir(sb)
            with contextlib.redirect_stderr(io.StringIO()):
                res = mod.run_script(FULFIL_STEP, mod.pick_bash(), sb, None, extra=True, inject=e_quoted, inject_to=target)
        finally:
            shutil.rmtree(sd, ignore_errors=True)
        obs = res[1]
        if obs is None:
            probs.append("目標 %s：run_script 逾時" % target)
            continue
        out = obs[1].decode("utf-8", "replace") if isinstance(obs[1], bytes) else str(obs[1])
        probs += fulfillment_shape_problems(target, out, bool(res[4]["inject"]), short, tempfile.gettempdir())
    return probs
