#!/usr/bin/env python3
"""量測 `test_validate.py` 的鑑別力：逐一關掉 `validate.py` 的判定條件，看測試抓不抓得到。

**存活（survived）= 那道閘門沒有測試網。**

## 為什麼這支存在

#33 verify R8 的 devil's-advocate 實測指出：當時 26 條測試裡，**20 個閘門 mutation 有 18 個
存活** —— 包含 root `CLAUDE.md` 標為 CRITICAL 的版本同步閘門，以及 R4 的頭號修正
「拿不到 base → fail-loud」（後者甚至可以整段換成無條件 `return` 而全套仍綠）。

而當時 `test_validate.py` 的開頭、`test.yml` 的註解、CHANGELOG 三處都寫著
「每條測試對應一個真實缺陷、斷言兩個方向、都做過 mutation」。**那三句話會讓下一個維護者
以為改動 `validate.py` 有測試網接著。**

所以問題不是「當時漏了幾條」，而是**「這套測試有多少鑑別力」在當時只能靠作者宣稱**。
這支把它變成可機械回答的問題：跑一次，看存活清單。

## 用法

    python3 scripts/mutation_check.py                  # 完整量測（慢）
    python3 scripts/mutation_check.py --check-targets  # 只驗靶還對得上（秒級，CI 會跑）

**手動跑，不進 CI**（一輪 = 靶數 × 全套測試；比照 `ensemble-eval` 的定位）。
**最近一輪的實測數字只寫在一個地方**：`scripts/test_validate.py` 檔頭。這裡與 `test/run.sh` 先前各抄了一份、
連同本行原本還有一段重複貼上的半句 —— 同一個會過期的數字散在四處，正是本 PR 反覆在抓的漂移形狀（#33 verify R23）。
改動 `validate.py` 的閘門、或新增閘門之後跑一次；存活清單就是待補的測試。

## 兩個誠實邊界

1. **存活 ≠ 一定缺測試。** 有些是 *equivalent mutant*：關掉某道檢查後行為沒變（下游另一道
   守住了）。例如把 `if not cat.is_file()` 關掉，`cat.open()` 仍會拋 `OSError` 被同一個
   `except` 接住並報同一類錯 —— 那是縱深防禦，不是缺口。判讀存活清單要逐條看。
2. **這支只 mutate `if` 條件。** 它不動運算式、邊界值、訊息內容，所以「零存活」**不等於**
   測試完備。它回答的是一個窄而具體的問題：**每一道閘門被整段拿掉時，有沒有東西會叫。**
3. **靶清單是手維護的，它相對閘門集合的完備性沒有機械保證**（#33 verify R9 M24）。
   新增一道閘門卻忘了加靶 → 照樣「0 靶壞」+ 高殺率，而那道閘門其實沒被量到。
   對沖的是靶壞會 fail-loud：改動被 mutate 的那幾行時靶會對不上，逼你回來更新。
   **新增閘門時請一併加靶**；`main()` 的回傳值對「靶壞」是 1，不是 0。

## 一個踩過的坑

R7 有一個 mutation 一直沒轉紅，差點被判定成「那條測試是套套邏輯」。追下去發現是
**mutation 打偏了** —— `str.replace(old, new, 1)` 命中的是註解裡的同一個字串，不是程式碼。
所以下面每個靶都要求**在檔案中恰好出現一次**，不唯一就直接報錯而不是默默替換第一個。
mutation test 本身也需要被驗證有沒有真的打中。
"""
import argparse
import pathlib
import time
import signal
import subprocess
import sys

PACK = pathlib.Path(__file__).resolve().parent.parent
VALIDATE = PACK / "scripts" / "validate.py"
TESTS = PACK / "scripts" / "test_validate.py"
NEUTRALISE = PACK / "scripts" / "neutralise.py"
PAI = PACK.parent / "parallel-ai-agents"
LINT = PAI / "test" / "lint-ci-log-filter.sh"
ORACLE = PAI / "test" / "oracle.py"

# ── 守備範圍（#33 verify R26 M6 / G-R27-6）───────────────────────────────────────────
# 「新機制沒有 RED 驗證」在這個 PR **發作了七次**，而 R26 的 DA 把它診斷到方法層：
# RED 驗證的對象、突變的選擇、fixture 的內容，**三者都由剛寫完那段程式碼的人自己挑**。
# 而這個 repo 早就有正解——就是這支的具名靶 ＋ `EXPECTED_SURVIVE`——只是守備範圍寫死成
# 「只 mutate validate.py」。所以修法不是再補幾個 fixture，是**把 harness 指向新程式碼**。
#
# 每個「守備單位」= 被 mutate 的檔 ＋ 驗它的指令 ＋ 工作目錄。靶用第四個欄位選守備單位，
# 省略時是 `validate`（既有 114 個靶一個字都不用動）。
SUITES = {
    "validate":   (VALIDATE,   lambda: [sys.executable, str(TESTS)],          PACK),
    "lint":       (LINT,       lambda: ["bash", str(LINT), "--selftest"],     PAI),
    "neutralise": (NEUTRALISE, lambda: [sys.executable, str(TESTS)],          PACK),
    # R37（#33 verify R36 條件 7）：神諭（`test/oracle.py`）進入突變範圍。**不帶參數**執行——只有
    # 不帶參數，`test/oracle.py` 才會掃 `test/fixtures/ci-log-filter-*.yml` 全集並額外檢查
    # `FIXTURE_CLASS_TOTALS`／`FIXTURE_MUSTFAIL_TOTAL` 這兩個釘死總數；must-fail 探針本身的理由比對不受此限，帶檔案參數一樣會跑；帶檔案參數只會跳過 `FIXTURE_CLASS_TOTALS`／`FIXTURE_MUSTFAIL_TOTAL` 這兩個釘死的
    # 總數檢查（見 `oracle.py` 的 `if not argv:`），must-fail 探針本身的理由比對不在此限，量到的網會變窄。`oracle.py` 自己從 `__file__`
    # 解析 `lint-ci-log-filter.sh` 與 `fixtures/`（`HERE = pathlib.Path(__file__).resolve().parent`），
    # 跟 mutation_check 執行時的 cwd 無關，所以不需要另外 symlink。
    "oracle":     (ORACLE,     lambda: [sys.executable, "test/oracle.py"],    PAI),
    # 神諭的**反向探針**：只有未突變的神諭**失敗**時才成立的兩項檢查（must-fail 探針的理由比對、oracle↔lint 的
    # RULE 字面耦合），寫成「期待失敗」的斷言放在 `test/oracle_selfcheck.py`——未突變時它 rc=0，滿足
    # `precheck_suites` 的「未突變＝綠」前提；拿掉任一道檢查它就紅。被突變的檔仍是 `test/oracle.py`。
    "oracle-inverted": (ORACLE, lambda: [sys.executable, "test/oracle_selfcheck.py"], PAI),
}

# (名稱, 要替換的字串, 替換成什麼)。每個 old 必須在 validate.py 中**恰好出現一次**。
# `None` 的 new 代表特殊處理（見 _apply）。
MUTATIONS = [
    ("no-base fail-loud 整段", "__SPECIAL_NOBASE__", None),
    ("version 不同步", "        elif mp_ver != pj_ver:", "        elif False:"),
    ("兩邊都缺 version", "        if pj_ver is None or mp_ver is None:", "        if False:"),
    ("seen == 0 保險", "    if seen == 0:", "    if False:"),
    ("反向檢查（缺 entry）",
     "        if pathlib.Path(os.path.normpath(pdir)) not in claimed:", "        if False:"),
    # R18 security S-3 / DA-1：兩層 containment 共用一個靶，於是只有一層有網。兩層各自一個靶。
    ("containment：實際要讀的 plugin.json（.claude-plugin 是 symlink）",
     "        outside = [p for p in (resolved, pj) if not _inside(p, repo_abs)]",
     "        outside = [p for p in (resolved,) if not _inside(p, repo_abs)]"),
    ("containment：plugin 目錄本身（plugins/evil 是 symlink，json 解析回 repo 內）",
     "        outside = [p for p in (resolved, pj) if not _inside(p, repo_abs)]",
     "        outside = [p for p in (pj,) if not _inside(p, repo_abs)]"),
    # R18 security S-4：fork 可控的 JSON 型別讓這道 CRITICAL 閘門拋 TypeError 被 gate() 吞掉。
    ("source.path 型別守衛", "            if rel is not None and not isinstance(rel, str):", "            if False:"),
    ("source 缺席守衛（第三態）", "        elif src is None:", "        elif False:"),
    ("source 遠端來源封閉列舉", '                if isinstance(kind, str) and kind in REMOTE_SOURCES:', "                if False:"),
    ("abs/.. 前置檢查",
     '        if os.path.isabs(rel) or ".." in pathlib.PurePosixPath(rel).parts:',
     "        if False:"),
    ("description 漂移 warning",
     "        if pj_desc is not None and mp_desc is not None and pj_desc != mp_desc:",
     "        if False:"),
    ("per-plugin semver",
     "            if val is not None and version_tuple(val) is None:", "            if False:"),
    ("撞名檢查", "        if builtin_keys is not None:\n            clash = sorted(",
     "        if False:\n            clash = sorted("),
    ("override warning", "            if overriding:", "            if False:"),
    ("同檔重複 key", "        if dup:", "        if False:"),
    ("header 重複欄位", "        if dupes:", "        if False:"),
    ("欄位數過多（focus 逗號未 quote）", "        if extra:", "        if False:"),
    ("整份複製 catalog 的 header",
     '        if "profile" in fieldnames and "key" in fieldnames and "focus" in fieldnames:',
     "        if False:"),
    ("未知 header 欄", "        if unknown:", "        if False:"),
    ("缺 key/focus 的列", "        if bad:", "        if False:"),
    ("解析出 0 條 lens", "        if not rows:", "        if False:"),
    ("key 以 # 開頭", '            if (r["key"] or "").lstrip().startswith("#"):',
     "            if False:"),
    ("lenses/ 下子目錄", "        if p.is_dir():", "        if False:"),
    ("大寫 .CSV", '        elif p.suffix != ".csv":', "        elif False:"),
    ("略過 dotfile", '        if p.name.startswith("."):', "        if False:"),
    ("lenses/ 目錄不存在", "    if not d.is_dir():", "    if False and not d.is_dir():"),
    ("沒有合法 csv", "    if not good:", "    if False:"),
    ("catalog 缺檔", "    if not cat.is_file():", "    if False and not cat.is_file():"),
    ("catalog header 缺 profile",
     '            if "profile" not in fields or "key" not in fields:', "            if False:"),
    ("catalog 解析出 0 條", "    if not out:", "    if False:"),
    ("lister 不存在", "        if not lister.is_file():",
     "        if False and not lister.is_file():"),
    ("lister rc=0 空輸出", "            elif not r.stdout.split():", "            elif False:"),
    ("profile 名稱閘門",
     "        if known_profiles is not None and profile not in known_profiles:",
     "        if False:"),
    ("truthy 無法辨識 warning", "                if raw and raw not in TRUTHY + FALSY:",
     "                if False:"),
    ("base ref 不存在",
     '    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],',
     '    if False and subprocess.run(["git", "rev-parse", "--verify", "--quiet", '
     'f"{base}^{{commit}}"],'),
    ("prerelease 排序", '    if m["pre"] is None:\n        return core + (1,)',
     '    if True:\n        return core + (1,)'),
    ("未 commit warning", "    if dirty.returncode == 0 and dirty.stdout.strip():",
     "    if False:"),
    ("pack 改名偵測", "    moved_pj = _find_pack_at(repo, cmp_base, pj_rel, pack_name)",
     "    moved_pj = None"),
    ("bump 比較（tn <= tp）", "    elif tn <= tp:", "    elif False:"),
    ("entry name 缺席", "        if not ent_name:", "        if False:"),
    ("entry name 與 plugin.json 不符", "        elif pj_name and ent_name != pj_name:",
     "        elif False:"),
    ("兩個 entry 指向同一目錄", "        if resolved in claimed_paths:", "        if False:"),
    ("lenses/ 下 symlink", "        if p.is_symlink():", "        if False:"),
    ("隱藏的 .csv", '        if p.name.startswith(".") and p.suffix == ".csv":',
     "        if False:"),
    ("manifest 型別不是 dict", "    if not isinstance(obj, dict):", "    if False:"),
    ("plugins 不是 list", "    if not isinstance(plugins, list):", "    if False:"),
    ("plugins 元素不是 dict", "        if not isinstance(entry, dict):", "        if False:"),
    ("--event choices", 'ap.add_argument("--event", metavar="<github-event-name>", choices=EVENTS,',
     'ap.add_argument("--event", metavar="<github-event-name>",'),
    ("check_version 的 semver 閘門", "    if version_tuple(version) is None:", "    if False:"),
    ("rcN prerelease warning", "        if risky:", "        if False:"),
    ("lenses/ 目錄本身的 containment", "    if not _inside(d.resolve(), repo_abs):",
     "    if False:"),
    ("catalog 的 containment", "    if not _inside(cat.resolve(), repo.resolve()):",
     "    if False:"),
    ("check_bumped 的 now 型別守衛", "    if now_obj is None:", "    if False and now_obj is None:"),
    ("check_bumped 的 prev 型別守衛", "    if prev_obj is None:",
     "    if False and prev_obj is None:"),
    ("純改名不算 lens 變更",
     '        if parts[0] == "R100" and len(parts) == 3 and parts[1].rsplit("/", 1)[-1] == parts[2].rsplit("/", 1)[-1]:',
     "        if False:"),
    ("反向檢查的 name 交叉比對", "            if dir_name in named_entries:", "            if False:"),
    ("workflow-command 消毒（值層）", '    t = t.replace("::", "∷")', "    t = t"),
    ("workflow-command 消毒（emit 的一行一行）",
     "    t = collapse_lines(str(line))",
     "    t = str(line)"),
    # #33 verify R11：真正的輸出邊界（stdout + stderr 的行首 `::`）與它的兩個安裝點。
    ("輸出邊界（行首 :: 中和）",
     '        if line.lstrip().startswith("::"):',
     "        if False:"),
    ("輸出邊界（stdout 安裝）", "    if not isinstance(sys.stdout, LineSanitiser):", "    if False:"),
    ("輸出邊界（stderr 安裝）", "    if not isinstance(sys.stderr, LineSanitiser):", "    if False:"),
    # R11 #5：`R100` 判定的**放寬**方向 —— 原本只有「整段拿掉」（過嚴）那一個方向的靶。
    ("純改名判定放寬（R0xx 也算純改名）",
     '        if parts[0] == "R100" and len(parts) == 3 and parts[1].rsplit("/", 1)[-1] == parts[2].rsplit("/", 1)[-1]:',
     '        if parts[0].startswith("R") and len(parts) == 3 and parts[1].rsplit("/", 1)[-1] == parts[2].rsplit("/", 1)[-1]:'),
    ("純改名判定放寬（跨 profile 的 R100 也算純改名）",
     '        if parts[0] == "R100" and len(parts) == 3 and parts[1].rsplit("/", 1)[-1] == parts[2].rsplit("/", 1)[-1]:',
     '        if parts[0] == "R100":'),
    # R12（logic L3 / DA-6）：git 分支的兩個守衛依構造不可達（見檔尾 EXPECTED_SURVIVE），
    # 「沒改名時回 None」真正 load-bearing 的只有 name 分支這一個。
    ("純改名偵測不得在沒改名時回現路徑（name 分支）",
     '        if isinstance(obj, dict) and obj.get("name") == name and path != pj_rel:',
     '        if isinstance(obj, dict) and obj.get("name") == name:'),
    ("entry name 登記在所有 continue 之前",
     "            if entry[\"name\"] in entry_names:", "            if False:"),
    ("description 版號前綴",
     "            if m_desc and pj_ver and m_desc.group(1) != pj_ver:", "            if False:"),
    # R12（logic L4）：「第一個 v<semver>: 就是最新」是慣例；把 search 換成取最後一個 match 要被抓到。
    ("description 版號前綴取第一個（最新在前）",
     '            m_desc = re.search(r"(?<![A-Za-z0-9])v(\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z.-]+)?):", str(desc or ""))',
     '            m_desc = (lambda ms: ms[-1] if ms else None)(list(re.finditer(r"(?<![A-Za-z0-9])v(\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z.-]+)?):", str(desc or ""))))'),
    ("description 版號前綴的 CJK 相黏（R13 N2）",
     '            m_desc = re.search(r"(?<![A-Za-z0-9])v(\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z.-]+)?):", str(desc or ""))',
     '            m_desc = re.search(r"\\bv(\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z.-]+)?):", str(desc or ""))'),
    ("check_version 的 containment（R13 N1）", "    if not _inside(manifest.resolve(), ws):", "    if False:"),
    ("反向 glob 的 containment",
     "        if not _inside(found.resolve(), repo_abs):", "        if False:"),
    # R18 regression B-1 / DA-2：一個粗靶蓋住五個轉義，靠 `,` 那條測試就被殺掉，另外四個沒有網。
    # 靶的顆粒度要對齊**被測的那一件事**，不是對齊「一行程式碼」。沒有網的 `%` 正是可利用的那個。
    ("property 轉義 %（prop；必須第一個，否則 %XX 被二次解碼）",
     'str(value).replace("%", "%25")', "str(value)"),
    ("property 轉義 CR（prop）", '.replace("\\r", "%0D")', ""),
    ("property 轉義 LF（prop）", '.replace("\\n", "%0A")', ""),
    ("property 轉義 :（prop）", '.replace(":", "%3A")', ""),
    ("property 轉義 ,（prop）", '.replace(",", "%2C")', ""),
    # R12（三 lens + DA）：輸出邊界的「行」必須是 runner 的定義。把它換回 Python splitlines() 就是 R11 的洞。
    ("輸出邊界的行定義（runner 的，不是 splitlines）",
     "        segs = [x for x in self._LINE_END.split(data) if x]",
     "        segs = [x for x in data.splitlines(keepends=True) if x]"),
    ("反向 glob 走 load_obj",
     "            found_obj = load_obj(found, found, errs)",
     "            found_obj = json.loads(found.read_text(encoding=\"utf-8\"))"),
    ("lister 的 containment",
     "        elif not _inside(lister.resolve(), repo.resolve()):", "        elif False:"),
    ("main() 逐閘門隔離（R13 DA-1）", "        except Exception as e:                      # noqa: BLE001 —— 這裡就是要接住一切",
     "        except () as e:"),
    ("emit 認命令頭前先 lstrip（R13 DA-12）", "    t = collapse_lines(str(line)).lstrip()", "    t = collapse_lines(str(line))"),
    ("harness 的 containment（R13 R13-4）",
     "        elif not _inside(harness.resolve(), repo.resolve()):", "        elif False:"),
    # R12 DA-1：runner 的第二套語法。V1 是 IndexOf，只能全行取代。
    ("V1 `##[` 中和（輸出邊界）", '        return line.replace("##[", "##⟦")', "        return line"),
    ("輸出邊界緩衝未完成的一行", '        if segs and not segs[-1].endswith(("\\n", "\\r")):', "        if False:"),
    # R18 DA-2：`wc()` 自己那層的 collapse_lines 沒有靶（emit 那層有），而 `_LINE_BREAKS` 的
    # 11 個分隔符只有 8 個有網。粗顆粒的靶蓋住細顆粒的缺口，第三處。
    ("wc() 自己那層的 collapse_lines", "    t = collapse_lines(str(value))", "    t = str(value)"),
    ("分隔符表：\\x1c（**替換**而非刪除——長度不變，才驗得到行為）",
     '"\\x1c", ', '"\\x07", '),
    ("分隔符表：\\x1d（**替換**而非刪除——長度不變，才驗得到行為）",
     '"\\x1d", ', '"\\x07", '),
    ("分隔符表：\\x1e（**替換**而非刪除——長度不變，才驗得到行為）",
     '"\\x1e", ', '"\\x07", '),
    ("V1 `##[` 中和（emit）", '    t = t.replace("##[", "##⟦")', "    t = t"),
    ("emit 截斷保留命令頭", "    if len(msg) > 4000:", "    if False:"),
    # R12 DA-6：這兩個守衛在目前的入口條件（`old_path.endswith("/" + suffix)`）下**依構造不可達**
    # （old_pack == pack_rel ⟺ old_path == new_path，git 不會對同路徑輸出 R）。保留為防禦（R11 #5 才
    # 剛放寬過隔壁的入口），但它們**永遠殺不掉**——列在 EXPECTED_SURVIVE，不算「可能缺測試」的存活。
    ("pack 內部改名不投票（依構造不可達，保留為防禦）",
     "                if old_pack != pack_rel:", "                if True:"),
    ("純改名偵測 git 分支（依構造不可達，保留為防禦）",
     "            if candidate != pj_rel and subprocess.run(",
     "            if subprocess.run("),
]

MUTATIONS += [
    # R13（security S1）：非 UTF-8 manifest 的第三、第四個 crash 站點。
    ("pack_name 讀取的 UnicodeDecodeError",
     "        except (OSError, UnicodeDecodeError, json.JSONDecodeError):\n            pack_name = None",
     "        except (OSError, json.JSONDecodeError):\n            pack_name = None"),
    ("pack_name 讀取的 containment（R13 N1 第九處）",
     "    if _inside(_pj_path.resolve(), repo.resolve()):", "    if True:"),
    ("git show 解碼 errors=replace（HEAD 側）",
     '    cur = subprocess.run(["git", "show", f"HEAD:{pj_rel}"],\n                         cwd=repo, capture_output=True, text=True, errors="replace")',
     '    cur = subprocess.run(["git", "show", f"HEAD:{pj_rel}"],\n                         cwd=repo, capture_output=True, text=True)'),
    # ── #33 verify R14 ──
    ("repo_root None 在 CI 報錯（R14 L-1：五道閘門不得靜默蒸發）",
     '    if os.environ.get("GITHUB_ACTIONS") == "true":\n        errs.append("::error::" + what',
     '    if False:\n        errs.append("::error::" + what'),
    ("collector_wiring 缺 repo 不印假 warning（R14 L-1）",
     '        if repo is None:\n            own, wired = "(no repo)", "skip"',
     '        if False:\n            own, wired = "(no repo)", "skip"'),
    ("root marketplace.json 的 containment（R14 L-2 第十處）",
     "    if not _inside(mp.resolve(), repo.resolve()):", "    if False:"),
    ("SKILL.md 的 containment（R14 L-2 第 11 處）",
     '    if not _inside((d / "SKILL.md").resolve(), repo.resolve()):', "    if False:"),
    ("lenses/ 目錄層 containment 不依賴 repo_root（R14 L-1）",
     "    repo_abs = (repo_root(root) or root).resolve()",
     '    repo_abs = (repo_root(root) or pathlib.Path("/")).resolve()'),
    ("PAI_HARNESS 顯式傳入（R14 E-2 / L-7）",
     'env={**os.environ, "PAI_HARNESS": str(harness)})', "env={**os.environ})"),
    ("lister stderr 不進 annotation（R14 S1 / L-6）",
     'errs.append(f"::error::無法取得 PROFILES 清單（pai-list-profiles rc={r.returncode}；',
     'errs.append(f"::error::無法取得 PROFILES 清單：{r.stderr.strip()}（pai-list-profiles rc={r.returncode}；'),
    ("check_csvs 沒有跑的具名訊息（R14 L-3a gate 相依）", "    elif files is None:", "    elif False:"),
    ("drain 迴圈的保護（R14 L-3b）",
     "        except Exception as ex:                     # noqa: BLE001", "        except () as ex:"),
    # ── #33 verify R15 ──
    ("check_csvs 空清單的具名訊息（R15 L-4）",
     '        errs.append("::error::check_csvs 沒有跑（lenses/ 沒有任何合法的 CSV 檔）',
     '        pass  # ("::error::check_csvs 沒有跑（lenses/ 沒有任何合法的 CSV 檔）'),
    ("NO_REPO_GATES 少列一道（R15 DA-3：手寫封閉列舉要有網）",
     '"撞名（builtin-lenses.csv）", ', ''),
    ("base 字串進 annotation 經 wc()（R15 DA-5 同類：外部字串進 annotation 一律 wc）",
     "errs.append(f\"::error::base ref '{wc(base)}' 不在本地歷史內",
     "errs.append(f\"::error::base ref '{base}' 不在本地歷史內"),
    ("version 字串進 annotation 經 wc()（R16）",
     "需要 semver version（現在是 '{wc(version)}'）", "需要 semver version（現在是 '{version}'）"),
    ("dirty 路徑清單進 annotation 經 wc()（R16）", '              + wc(", ".join(paths)))', '              + ", ".join(paths))'),
    # R22 security S-1：taint 的鏈補上 gate() 間接呼叫與回傳值之後才看得見的兩個站點。
    ("check_csvs 的 rel 經 ann_path（R22 S-1：R12 第 5 條的缺陷類別靠這個洞回來）",
     "        rel = ann_path(path, root)", "        rel = str(path)"),
    ("profile 名進 annotation 經 wc()（R22 S-1 鏈打通後才看得見）",
     "::error file={rel}::'{wc(profile)}' 不是既有 profile",
     "::error file={rel}::'{profile}' 不是既有 profile"),
    ("entry name 進 annotation 經 wc()（R17 logic L-3/L-4：taint 網涵蓋 manifest 來源）",
     "f\"::error file={prop(mp)}::{wc(entry.get('name'))} 的 source {wc(repr(src))} \"",
     "f\"::error file={prop(mp)}::{entry.get('name')} 的 source {wc(repr(src))} \""),
    ("CSV 欄名進 annotation 經 wc()（R17 L-4）",
     "（現在是 {wc(fields)}）", "（現在是 {fields}）"),
    ("profile 清單經 wc() 進 annotation（R15 S-2）",
     "f\"（真源 PROFILES 有：{wc(', '.join(sorted(known_profiles)))}）。\"",
     "f\"（真源 PROFILES 有：{', '.join(sorted(known_profiles))}）。\""),
]
# R26 regression R-3 抓到這裡曾宣稱 neutralise.py 的行為已被 CI 裡的兩條中和測試接住——**那是假的**：
# 把它的串流一行 revert 回 `read()`，139 條全綠、114 靶全中。它現在**在 mutation 範圍內**
# （守備單位 `neutralise`，靶在下方 R26 M6 那一段），且由 `test_neutralise_streams_instead_of_buffering_until_eof`
# 釘住；那個靶實測會被殺掉。

# ── R26 M6 / G-R27-6：守備範圍擴到 lint 與 neutralise ───────────────────────────────
# 下面每一個靶都對應一個**本輪或上一輪新加的機制**。R26 的 sweep 對它們 7/7 SURVIVED ——
# 也就是整段刪掉而 selftest 照樣全綠。靶進來之後，那些機制才第一次有「它有沒有在擋東西」的量測。
MUTATIONS += [
    ("lint: heredoc 終止判定（R26 M2：吃 YAML 縮排時這分支不可達）",
     "            if probe == delim and not body_continued:", "            if False:", "lint"),
    ("lint: heredoc 佇列接續（R26 M3：`pending[0]` 不是 FIFO）",
     '                heredoc = pending.pop(0) if pending else None\n                body_continued = False\n            elif in_sub', '                heredoc = None\n                body_continued = False\n            elif in_sub', "lint"),
    # R27 把這一條列入 EXPECTED_SURVIVE，理由是：關掉之後 `<<<` 落到下面的 `<<` 分支，分隔字從第三個 `<`
    # 讀起、`<` 在 `SHELL_WORD_BREAK` 裡 ⇒ delim 為空、不產生 heredoc ⇒ 行為等價。**那個論證只看了第一個 `<<`，
    # 是錯的**（#33 verify R37 全輪 mutation 抓到）：`<<<<<EOF`（bash 裡是語法錯誤）拿掉這個分支後，掃描器會在後面的
    # `<<` 登記 heredoc、對齊跟著錯位——`bypass-r37t8-misaligned-herestring-heredoc` 從 rule-red 變成 pass（繞過方向）。
    # 已從 EXPECTED_SURVIVE 移除，靶名也拿掉「依構造等價」。
    ("lint: `<<<` 是 here-string 不是 heredoc",
     '            if line.startswith("<<<", i):', "            if False:", "lint"),
    ("lint: `$((` 深度內不判 heredoc（R26 M3）",
     '            if arith or brk or cond:', '            if brk or cond:', "lint"),
    ("lint: `<<-` 剝 tab（R26 M3）",
     '                if line[j:j + 1] == "-":            # 切片越界回空字串，不另寫 `j < n` 守衛', "                if False:", "lint"),
    ("lint: 單引號狀態分支（R26 logic MEDIUM-6：整段刪掉 selftest 仍綠）",
     '            if quote == "\'":', "            if False:", "lint"),
    ("lint: 續行摺疊（R26 M5：`cat <\\` ⏎ `<EOF`）",
     "                if li + spans < len(lines):", "                if False:", "lint"),
    ('lint: block scalar 共同縮排先剝除（R26 M2）',
     'scan_in = fold_block(dedent_block(run_lines, explicit_pad), block_folded)',
     'scan_in = fold_block(run_lines, block_folded)', "lint"),
    ("lint: YAML 引號純量先解碼（R26 M4：未實作的逃脫不得猜）",
     "            decoded = yaml_decode_scalar(inline[:len(inline) - len(yaml_cmt)] if yaml_cmt else inline)",
     "            decoded = inline[:len(inline) - len(yaml_cmt)] if yaml_cmt else inline", "lint"),
    ("lint: jobs 子樹的 flow 值 fail-closed（R26 M1(b)）",
     '        if (":" in code_val and top_key == "jobs") or not balanced:',
     "        if False:", "lint"),
    # ── R30 H-1…H-6 與 MB-1、7、8、9、11、12（G-R31-1）：lint 裡的新機制各一個靶；其餘 MB 項的修法在神諭與語料工具裡 ──
    # 每一條的括號裡寫「關掉它，哪個 fixture 翻色」——答不出來的不該進來。
    ("lint: heredoc 分隔字做整詞 quote removal（R30 H-1 → good-dq-delim-dollar-literal、bypass-heredoc-in-dq-cmdsubst 等 20 張）",
     '                    if c in ("\'", \'"\'):\n                        saw_word = True',
     "                    if False:\n                        saw_word = True", "lint"),
    ("lint: `$\'…\'` 的 `\\\'` 是逃脫不是收尾（R30 H-2 → 由產生語料的 ansic 維度守）",
     '            if line.startswith("$\'", i):', "            if False:", "lint"),
    ("lint: `${…}` 整段消費（R30 H-3 → bypass-param-expansion-hash）",
     '\n            if line.startswith("${", i):\n                # **只有巢狀的', '\n            if False:\n                # **只有巢狀的', "lint"),
    ("lint: 反引號是詞界（R30 H-4 → bypass-backtick-hash）",
     'SHELL_WORD_BREAK = " \\t;&|()<>`"', 'SHELL_WORD_BREAK = " \\t;&|()<>"', "lint"),
    ('lint: 折疊 block scalar 先折再掃（R30 H-5 → bypass-folded-comment-eats-next-line、-folded-three-content-lines 等 5 張）',
     'scan_in = fold_block(dedent_block(run_lines, explicit_pad), block_folded)',
     'scan_in = dedent_block(run_lines, explicit_pad)', "lint"),
    ('lint: 管線左邊必須有東西（R30 H-6 → bypass-leading-pipe-literal）',
     'r"[^|\\s;&(]\\s*\\|(?!\\|)&?\\s*python3',
     'r"\\|(?!\\|)&?\\s*python3', "lint"),
    ("lint: 邏輯行只在續行運算子後接續（R30 H-6 的另一半 → bypass-leading-pipe-literal）",
     "            if logical and CONT_RE.search(logical[-1]):", "            if logical and True:", "lint"),
    ("lint: explicit_pad 只取標頭本身的指示子（R30 MB-1 → good-block-header-comment-digit）",
     "            ind = m_hdr.group(1) or m_hdr.group(2)      # 只取標頭本身的指示子，不碰行尾註解",
     '            ind = (re.search(r"[1-9]", inline) or [None] and None) and re.search(r"[1-9]", inline).group()', "lint"),
    ("lint: 純空白行也剝區塊縮排（R30 MB-11 → good-whitespace-heredoc-delimiter）",
     "    return [lines[0]] + [l[pad:] for l in lines[1:]]",
     "    return [lines[0]] + [(l[pad:] if l.strip() else l) for l in lines[1:]]", "lint"),
    ("lint: 單引號字元留在 code 裡（R30 MB-12 → good-empty-single-quotes-before-neutralise）",
     '                code.append("\'" if ch == "\'" else " ")', '                code.append(" ")', "lint"),
    ("lint: 雙引號字元留在 code 裡（R30 MB-12 → good-empty-quotes-before-neutralise）",
     '                code.append(\'"\' if ch == \'"\' else " ")', '                code.append(" ")', "lint"),
    ("lint: root_indent 由解析器認定的 key 行決定（R30 MB-7 → bypass-shallow-continuation-flow-mapping）",
     "    root_indent = min((ind for _i, ind, _k in key_lines), default=0)",
     "    root_indent = min((len(m.group(1)) for i in range(len(raw)) for m in [KEY_RE.match(norm[i])] if m), default=0)",
     "lint"),
    ("lint: tag 也 fail-closed（R30 MB-8 → bypass-tag-value-nested）",
     '            if val.startswith(("&", "*", "<<", "!")):', '            if val.startswith(("&", "*", "<<")):', "lint"),
    ("lint: 引號 key 先解碼再比對、解不出來就當可能是 run（R30 MB-9 → bypass-hexkey-tab-run）",
     '            if dec == "run" or dec is None:', '            if dec == "run":', "lint"),
    ("neutralise: 串流而不是讀到 EOF 才動（R26 M6／regression R-3）",
     "        chunk = sys.stdin.buffer.read1(65536)",
     "        chunk = sys.stdin.buffer.read()", "neutralise"),
    # ── R28 D1–D8b（G-R29-2）：本輪每個新機制一個靶，靶與 fixture 同一個 commit 進來 ──
    # 每一條都要能回答「關掉它，哪個 fixture 翻色」（答案寫在名稱括號裡）。
    ("lint: heredoc 終止字要完全相等（R28 D1：`EOF ` 不終止 → bypass-heredoc-terminator-trailing-space）",
     "            if probe == delim and not body_continued:",
     "            if probe.rstrip() == delim and not body_continued:", "lint"),
    ("lint: 未引號 heredoc 內文行尾反斜線續行（R28 D3 → bypass-heredoc-body-backslash-before-terminator）",
     "            if probe == delim and not body_continued:",
     "            if probe == delim:", "lint"),
    ("lint: 未引號分隔字含反斜線視同引號（R28 D2：`<<E\\OF` → good-unquoted-delim-backslash）",
     '                    if c == "\\\\":                                     # 行尾的 `\\` 已被上面的續行分支接走\n                        quoted = True; delim += line[j + 1]; j += 2; continue',
     "                    if False:\n                        quoted = True; delim += line[j + 1]; j += 2; continue", "lint"),
    # ── R31：分隔字詞裡的**行尾**反斜線是續行、不是逃脫（bash 5.3 實測；R30 的註解把
    #    「行尾 `\\` 不續行」寫成全稱，那句是假的）。兩個引號脈絡各一條規則、各一個靶。──
    ("lint: 未引號分隔字的行尾反斜線是續行且**不**使 heredoc quoted（R31 → good-unquoted-delim-line-continuation）",
     '                    if c == "\\\\" and j + 1 == n:                          # 越界由 _next_phys 回 "" 處理',
     "                    if False:", "lint"),
    # ── R33（#33 verify R32）：每一條括號裡寫「還原它，哪個 fixture 翻色」，且翻色紀錄在 CHANGELOG R33 段 ──
    ("lint: `${…}` 內的引號要追蹤（R32 regression HIGH-1 → good-github-expression-format-brace）",
     '        if c == "\'":\n            k = line.find("\'", j + 1)', '        if False:\n            k = line.find("\'", j + 1)', "lint"),
    ("lint: `${…}` 內的 `\\}` 是逃脫不是收尾（R32 security S-1 → bypass-param-expansion-escaped-brace）",
     '        if c == "\\\\":\n            if j + 1 >= n:\n                return None', '        if False:\n            if j + 1 >= n:\n                return None', "lint"),
    ("lint: 分隔字詞尾不以反引號斷詞（R32 logic L-1／DA-3 → bypass-heredoc-delim-backtick；R34 拆開：原本是反引號＋括號的複合突變）",
     'DELIM_WORD_BREAK = " \\t;&|()<>"', 'DELIM_WORD_BREAK = " \\t;&|()<>`"', "lint"),
    ("lint: 分隔字詞尾以 `(` `)` 斷詞（R34 logic F2／regression H-1 → bypass-heredoc-delim-close-paren、good-heredoc-delim-subshell-paren）",
     'DELIM_WORD_BREAK = " \\t;&|()<>"', 'DELIM_WORD_BREAK = " \\t;&|<>"', "lint"),
    ("lint: 續行吃掉的格數含跳過的佔位（R34 regression H-2 → bypass-folded-continuation-*-rescan）",
     "        return lines[k], k - start + 1", "        return lines[k], 1", "lint"),
    ("lint: 空分隔字也登記 heredoc（R32 Codex 第 3 條／DA-5 → bypass-heredoc-delim-empty）",
     "                if saw_word:", "                if delim:", "lint"),
    ("lint: 折疊是遞移的——折完累積點不重設（R32 logic L-0／DA-2 → bypass-folded-three-content-lines）",
     "                out.append(None)                # 佔位：行數不變，但 runner 眼中沒有這一行",
     "                out.append(None); acc = None", "lint"),
    ("lint: 內容行後的第一個空行是分隔符不是一行（R33 自查 → bypass-folded-blank-separator-empty-delim）",
     "        drop_first = prev_flush_content and not nxt_more",
     "        drop_first = False", "lint"),
    ("lint: 分隔字裡的引號沒在同一行收尾 → fail-closed 走 PARSE（R31 → bypass-dq-delim-closing-quote-next-line 等 4 個）",
     '                        if j >= n:                   # 迴圈是因為讀到行尾才停的：收尾引號不存在', '                        if False:                    # 迴圈是因為讀到行尾才停的：收尾引號不存在', "lint"),
    ("lint: 雙引號分隔字的行尾反斜線是續行（R31 → good-dq-delim-line-continuation）",
     '                            if q == \'"\' and line[j] == "\\\\" and j + 1 == n:   # 越界由 _next_phys 回 "" 處理',
     '                            if False:   # 越界由 _next_phys 回 "" 處理', "lint"),
    ('lint: `((` 進算術深度（R28 D4：`$((` 也走這裡 → good-arith-command-shift-then-pipe）',
     'if line.startswith("((", i) and (prev_sig == "$" or cmd_pos):',
     'if False:', "lint"),
    ("lint: `))` 退算術深度（R28 D4：不退則後面的 heredoc 全被忽略 → good-arith-then-pipe-sameline）",
     '                        arith -= 1; code.append("))")', '                        arith -= 0; code.append("))")', "lint"),
    ("lint: 續行重掃前還原 heredoc 佇列快照（R28 D6 → good-heredoc-opener-continuation）",
     "                    pending = list(pending0)", "                    pass", "lint"),
    ("lint: 顯式縮排指示子決定剝多少（R28 D5：`|2` 下 `  EOF` 不終止 → bypass-explicit-indent-indicator）",
     "                explicit_pad = len(KEY_RE.match(norm[r]).group(1)) + int(ind)",
     "                explicit_pad = None", "lint"),
    ("lint: 淺於指示子的內文行是 YAML 錯誤（R28 D5 → bypass-explicit-indent-shallow）",
     "        if explicit_pad is not None and any(", "        if False and any(", "lint"),
    ("lint: 指示子只接受 1-9（R28 D5：`|0` 是 YAML 錯誤 → bypass-explicit-indent-zero）",
     'BLOCK_SCALAR_RE = re.compile(r"^[|>](?:([1-9])[+-]?|[+-]([1-9])?)?\\s*(#.*)?$")',
     'BLOCK_SCALAR_RE = re.compile(r"^[|>](?:([0-9])[+-]?|[+-]([0-9])?)?\\s*(#.*)?$")', "lint"),
    ("lint: 不合法的 block scalar 標頭只印 PARSE 不印 RULE（R28 D5／R24 DA-8(b) → bypass-explicit-indent-zero）",
     '        elif inline[:1] in ("|", ">"):', "        elif False:", "lint"),
    ("lint: 引號純量後的 YAML 行尾註解先切掉再解碼（R28 D7 → good-quoted-run-trailing-comment-dq/sq）",
     "            decoded = yaml_decode_scalar(inline[:len(inline) - len(yaml_cmt)] if yaml_cmt else inline)",
     "            decoded = yaml_decode_scalar(inline)", "lint"),
    ("lint: 引號純量後的 YAML 行尾註解算宣告來源 (3)（R28 D7 → good-quoted-run-logfilter-comment）",
     "        decl_lines += shell_decls + yaml_trailing_cmts", "        decl_lines += shell_decls", "lint"),
    ("lint: yaml_split_comment 雙引號內 `\\\"` 是逃脫不是收尾（R28 D8b → good-flow-seq-escaped-quote）",
     '            if quote == \'"\' and ch == "\\\\":', "            if False:", "lint"),
]

# ── R35（#33 verify R34 的 lint 修法：每一條都在 test/ 複本上單獨還原、看過它翻色）──
MUTATIONS += [
    ("lint: YAML 縮排只剝空白、tab 是內容（R34 logic F4 → bypass-tab-indent-*）",
     '(len(l) - len(l.lstrip(" ")) for l in body)', '(len(l) - len(l.lstrip()) for l in body)', "lint"),
    ("lint: `${…}` 裡的命令替換照 bash 配對（R34 logic F1 p1/p2 → bypass-param-expansion-backtick-inside、-cmdsubst-inside）",
     '        if line.startswith("$(", j) or c == "`":\n            e = _cmdsub_end(line, j) if c == "$" else _backtick_end(line, j)', '        if False:\n            e = _cmdsub_end(line, j) if c == "$" else _backtick_end(line, j)', "lint"),
    ("lint: `${…}` 裡的 `$'…'` 認 `\\'` 逃脫（R34 logic F1 p4 → bypass-param-expansion-ansic-inside）",
     '        if line.startswith("$\'", j):                # ANSI-C', '        if False:                # ANSI-C', "lint"),
    ("lint: `${…}` 同一行沒收尾 fail-closed（R34 logic F1 p5 → bypass-param-expansion-multiline）",
     '                return j\n    return None\n', '                return j\n    return j\n', "lint"),
    ('lint: 雙引號裡的 `${…}` 走配對剖析（R34 logic F1 p3 → bypass-param-expansion-inside-double-quotes）',
     '                if line.startswith("${", i):\n                    e = _param_end(line, i)\n                    if e is None:\n                        unparsed = PARAM_UNPARSED\n                        break\n                    code.append(" " * (e - i)); i = e; prev_sig = "x"; continue\n                if line.startswith("$[", i):',
     '                if line.startswith("$[", i):', "lint"),
    ('lint: 雙引號裡的命令替換開 heredoc fail-closed（R35 → bypass-heredoc-in-dq-cmdsubst）',
     '                    quote = None; code.append(line[i:i + w]); i += w; prev_sig = "`" if w == 1 else "("\n                    cmd_pos = True           # 命令替換裡的第一個詞是新命令（合併 r37c×r37d：c 的雙引號分支原本不知道 cmd_pos）\n                    continue\n',
     '                    code.append(" "); i += 1; prev_sig = ch\n                    continue\n', "lint"),
    ("lint: `$'…'` 跨行 fail-closed（R34 logic F3 r2 → bypass-ansi-c-quote-unterminated）",
     '                if j >= n:\n                    # 跨行的 ANSI-C 字串', '                if False:\n                    # 跨行的 ANSI-C 字串', "lint"),
    ("lint: 命令替換裡的 heredoc 遇「以終止字開頭」的行 fail-closed（R34 logic F3 r1 → bypass-heredoc-in-dq-cmdsubst-prefix-terminator、bypass-heredoc-in-cmdsubst-after-inner-parens）",
     '            elif in_sub and delim and probe.startswith(delim)', '            elif False', "lint"),
    ("lint: 反引號深度（R35 → bypass-heredoc-in-backticks-prefix-terminator）",
     '                bt = not bt\n', '                pass\n', "lint"),
    ("lint: 命令替換深度（R35 → bypass-heredoc-in-cmdsubst-prefix-terminator）",
     '                csub += 1; code.append("$(")', '                csub += 0; code.append("$(")', "lint"),
    ('lint: 算術深度跨行保留（R34 logic F3 t2／DA t2prime → bypass-arith-multiline-shift）',
     '        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, tuple(dq_ret), tuple(map(tuple, cases)), bt_at, arith_cmd)\n',
     '        arith = 0\n        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, tuple(dq_ret), tuple(map(tuple, cases)), bt_at, arith_cmd)\n', "lint"),
    ('lint: 算術／條件式裡的內容不是 code（R34 DA n5、n5b → bypass-pipe-inside-arith、-cond-regex）',
     '                code.append(" "); i += 1; prev_sig = "x"; continue\n            if after_compound and not ch.isspace():',
     '                code.append(ch); i += 1; prev_sig = "x"; continue\n            if after_compound and not ch.isspace():', "lint"),
    ("lint: 舊式算術 `$[…]`（R34 logic F3 t1 → bypass-arith-legacy-bracket-shift）",
     '            if line.startswith("$[", i):\n                brk = 1', '            if False:\n                brk = 1', "lint"),
    ("lint: 條件式 `[[` 開啟（R34 DA n5b → bypass-pipe-inside-cond-regex）",
     '                cond = True; code.append("[[")', '                cond = False; code.append("[[")', "lint"),
    ("lint: 分隔字 `$'…'` 的 quote removal（R34 logic F3 q2、DA n1 → bypass-heredoc-delim-ansic、good-heredoc-delim-ansic）",
     '                    if line.startswith("$\'", j):\n                        # **`$\'…\'` 做 quote removal', "                    if False:\n                        # **`$'…'` 做 quote removal", "lint"),
    ("lint: 分隔字 `$\"…\"` 的 quote removal（R34 logic F3 q3 → bypass-heredoc-delim-locale）",
     '                    if line.startswith(\'$"\', j):\n                        j += 1; continue', '                    if False:\n                        j += 1; continue', "lint"),
    ("lint: ANSI-C 的 `\\x`／`\\u` 逃脫解碼（R35 → good-heredoc-delim-ansic-escapes）",
     '        if d in "xuU":', '        if d in "":', "lint"),
    ("lint: ANSI-C 的 `\\c` fail-closed（R35 → bypass-heredoc-delim-ansic-control-char）",
     '        if d == "c":\n            return None', '        if False:\n            return None', "lint"),
]

# ── R35（#33 verify R34 的 shell／stderr／--strict 規則：每一條都在 test/ 複本上單獨還原、看過它翻色）──
MUTATIONS += [
    ('lint: step 的 shell 不是字面 bash ⇒ PARSE（R34 security S-3 → bypass-shell-python、-bash-xtrace-template）',
     '        if STRICT and eff_shell is not None and (tmpl is None or tmpl["trace"]):',
     '        if False:', "lint"),
    ("lint: shell 從 workflow defaults 繼承（R34 security S-3 → bypass-shell-python-from-defaults）",
     '            or (job["shell"] if job else None) or wf_shell', '            or (job["shell"] if job else None)', "lint"),
    ("lint: shell 從 job defaults 繼承（R35 → good-shell-bash-explicit、good-strict-pipefail-forms）",
     '            or (job["shell"] if job else None) or wf_shell', '            or wf_shell', "lint"),
    ("lint: container／Windows runner 沒寫 shell ⇒ PARSE（R34 DA n4／n4b → bypass-strict-container-runner-clean、-windows-runner-clean）",
     '        if STRICT and eff_shell is None and job and (job["container"] or job["windows"]):', '        if False:', "lint"),
    ('lint: 靠管線過濾的 step 不得轉到 stderr 或開 xtrace（R34 security S-2／DA G-B → bypass-stderr-redirect-*、bypass-xtrace-set-x）',
     '        elif not declared and an["fd"]:',
     '        elif False:', "lint"),
    ('lint: --strict：接 neutralise 的管線要帶 2>&1／|&（R34 requirements F4 → bypass-strict-missing-2to1）',
     '        elif STRICT and not declared and an["bad_segs"]:',
     '        elif False:', "lint"),
    ('lint: --strict：有管線的 step 要在 pipefail 之下（R34 security S-1 → bypass-strict-pipe-without-pipefail）',
     '        if STRICT and not _pipefail_holds(an["events"], tmpl["pipefail"] if tmpl is not None else False):',
     '        if False:', "lint"),
    ('lint: --strict：認得 run 裡的 set -o pipefail（R35 → good-strict-pipefail-forms）',
     '                    elif nm == "pipefail":\n                        self.pf_event(on, ctx)',
     '                    elif nm == "pipefail":\n                        pass', "lint"),
    ("lint: 引號開到 run 區塊結尾 ⇒ fail-closed（R35 E 組語料 → bypass-quote-open-at-block-end）",
     "    if quote is not None:              # `and not unparsed` 只決定訊息寫哪個原因、判定都是 PARSE（opsweep 報存活，刪掉）\n", "    if False:\n", "lint"),
    ('lint: `${…}` 雙引號內的反斜線是逃脫（R34 requirements F2 → bypass-param-expansion-dq-escaped-quote）',
     '        if line[k] == "\\\\":\n            k += 2; continue\n        if line.startswith("$[", k):',
     '        if line.startswith("$[", k):', "lint"),
    ("lint: 解碼後的引號純量按換行切行（R35 → bypass-quoted-scalar-newline-comment）",
     '        run_lines = inline.split("\\n") + [raw[k] for k in range(r + 1, s["end"] + 1)', '        run_lines = [inline] + [raw[k] for k in range(r + 1, s["end"] + 1)', "lint"),
    ("lint: 切出來的行不 dedent（R35 → bypass-quoted-scalar-indented-lines-no-dedent）",
     '            if "\\n" in inline:\n                explicit_pad = 0', '            if False:\n                explicit_pad = 0', "lint"),
]

# ── R37（#33 verify R36 → R37）：lint 的新靶 ──────────────────────────────────────────────
# 來源：五個修法包各自建議的靶、合併時協調者寫的程式碼（含本輪修的 PIPED_RE 兩端、完整性審查缺陷 a／b／c／e）、完整性審查
# 逐 hunk 走 380e4a4..e50c303 的 lint diff 補的靶。每一條都在合併後的樹上看過殺得掉。**不登記的**（等價、死碼、寫不出會翻色的
# fixture）逐條列在下面——那是判斷，不是遺漏；哪天有人寫得出會翻色的 fixture，就把它加回來：
#   · 區塊結尾：雙引號裡的命令替換沒收 ⇒ fail-closed（R37）——等價：dq_ret 非空蘊含 csub>0 或 bt（構造證明：csub 降到 0 的那一步同時把 dq_ret 彈空），只換 PARSE 訊息
#   · `((` 的 cmd_pos 閘門拿掉（非命令位置的 `((` 也當算術）——等價：非命令位置的 `((` 在 bash 一律是語法錯誤（窮舉五種寫法實測，其中一種「`! ((1))`」經 bash -n 覆核其實仍是命令位置、不是有效反例，構造成立的是另外四種）
#   · cmd_pos：雙引號分支開命令替換時未設 True（合併 r37c×r37d，entry 側）——未找到會翻色的 fixture，也未證明等價
#   · 區塊結尾 elif 鏈順序：dq_ret 與 arith-family 對調——等價：dq_ret 蘊含 arith-family 條件，對調只換訊息
#   · selftest 正向門檻的條件改回 108（R37 合併 H2 → 門檻行本身）——量的是 selftest 門檻本身，不是 lint 的行為
#   · `]]` 收尾後不收回 cmd_pos（單獨）——等價：`[[` 開啟時已設 cmd_pos=False，條件式內的字元不會改回 True
#   · `[[` 開啟與 `]]` 收尾都不收回 cmd_pos（R37 d 包 H24 → bypass-r37t8-cond-then-cond-word）——要同時改兩處，靶格式表達不了；fixture bypass-r37t8-cond-then-cond-word 已採用
#   · `((` 分支的 `paren_claimed = True` 拿掉——死碼：同一行緊接 continue，paren_claimed 在迴圈開頭歸零
#   · 反引號分支的 `cmd_pos = not bt` 拿掉——由本輪缺陷 a 的修法讓它變成活碼，改用協調者重寫的同一個靶
#   · `_hidden_subs` 的 `_COVERED` 去重拿掉——等價（對判定）：_COVERED 只防同一區段剖析兩次
#   · `_lex` 不再把 `((…))`／`[[…]]` 當不透明詞——錨點被缺陷 e 的修法改寫，改用協調者重寫的同一個靶
#   · `_touches_fd2` 不認 `2>…`／`&>…`（R37 b 包 R36 第 3 列）——提案 fixture 的 bash 行為不支持 EXPECT，未採用
#   · `_touches_fd2` 不認 `>&word`（R37 b 包）——提案 fixture 的 bash 行為不支持 EXPECT，未採用
#   · `_rule_lines` 不依 CONT_RE 接行——等價：_Sh 在 |、|&、&&、|| 之後都 skip_nl()
#   · `_bash_template` 的 `-o` 名稱白名單拿掉——找不到會外流的輸入（白名單外 13 個 -o 名稱逐一實跑）
#   · `_bash_template` 的 `--verbose` 記成 trace 拿掉——等價：拿掉後落到同一個 reject、同一句訊息
#   · `CMD_POS_CHARS` 拿掉 `!{`——死碼：`!{` 在迴圈底部先被 `if ch in "!{"` 攔下
#   · `_cmdsub_end_case` 收尾時 `None if cases` 拿掉——走不到的分支（構造證明：case 開在某層時那一層的 `)` 走模式分支、不減深度）；不刪，避免重演 R36 第 5 列 (c)
#   · 續行重掃前不還原 arith_cmd（R37 缺陷 b）——等價：arith_cmd 每次進入 `((` 時重設，算術不能巢狀，續行重掃的那一段不會因為沒還原而改變判定；還原保留，只為與其他狀態一致
MUTATIONS += [
    ('dup 規則',
     '            return "`%s` 複製 fd（stdout 可能被帶到 stderr 或另存的 fd）" % shown',
     '            return None', "lint"),
    ('搬移 fd `>&2-`',
     '        if tl is not None and re.fullmatch(r"[0-9]+-", tl):',
     '        if False:', "lint"),
    ('2>&1／>&1 放行',
     '            if op == ">&" and tl == "1" and pre in ("", "1", "2"):',
     '            if False:', "lint"),
    ('/dev、/proc 目標',
     '    if {"dev", "proc"} & set(posixpath.normpath(sk).split("/")):',
     '    if False:', "lint"),
    ('/proc 那一半',
     '    if {"dev", "proc"} & set(posixpath.normpath(sk).split("/")):',
     '    if {"dev"} & set(posixpath.normpath(sk).split("/")):', "lint"),
    ('萬用字元目標',
     '    if t["glob"]:',
     '    if False:', "lint"),
    ('SAFE 白名單',
     '_SAFE_TARGETS = frozenset(("/dev/null", "/dev/stdout", "/dev/fd/1", "/proc/self/fd/1"))',
     '_SAFE_TARGETS = frozenset()', "lint"),
    ('群組豁免',
     '                out["groups"][segs[k]["gid"]] = True',
     '                pass', "lint"),
    ('豁免只給接管線的群組',
     '    fd = [why for why, stack in out["hits"] if not any(out["groups"][g] for g in stack)]',
     '    fd = [why for why, stack in out["hits"] if not stack]', "lint"),
    ('set 的 x／v',
     '                elif on and ch in "xv":\n                    self.hit("`set %s` 開了 %s"',
     '                elif False:\n                    self.hit("`set %s` 開了 %s"', "lint"),
    ('set -o xtrace／verbose',
     '                    elif on and nm in _TRACE_OPTS:',
     '                    elif False:', "lint"),
    ('set 非字面參數',
     '                self.hit("`set` 的參數不是字面（`set -$X`…）——開了什麼看不出來", ctx)',
     '                pass', "lint"),
    ('shopt -so',
     '            elif "s" in flags and nm in _TRACE_OPTS:',
     '            elif False:', "lint"),
    ('子 shell 選項',
     '            if w["lit"] is not None and w["lit"].rsplit("/", 1)[-1] in _SHELL_NAMES:',
     '            if False:', "lint"),
    ('eval 字面詞',
     '        if name == "eval" and args and all(a["lit"] is not None for a in args):',
     '        if False:', "lint"),
    ('run 裡的 env 變數',
     '            if text.startswith((key + "=", key + "+=")) or (bare and text == key):',
     '            if False:', "lint"),
    ('env 規則',
     '        elif not declared and env_hit:',
     '        elif False:', "lint"),
    ('workflow env',
     '                wf_env = _env_names(l_, ind_)',
     '                wf_env = []', "lint"),
    ('job env',
     '                    job_env += _env_names(l2, i2)',
     '                    pass', "lint"),
    ('container env',
     '                    job_env += [n_ for l3, i3, k3 in _kids(l2, _end(l2, i2), i2) if k3 == "env" for n_ in _env_names(l3, i3)]',
     '                    pass', "lint"),
    ('step env',
     '            _env_names(s["keys"]["env"], s["kindent"]) if "env" in s["keys"] else [])',
     '            [])', "lint"),
    ('根層級 env flow',
     '            if _flow_value(l_) and ":" in yaml_split_comment(KEY_RE.match(norm[l_]).group(3) or "")[0]:',
     '            if False:', "lint"),
    ('雙引號裡的命令替換',
     '                    hs = _hidden_subs(S, p + 1, e, dq=True)',
     '                    hs = []', "lint"),
    ('${…} 裡的命令替換',
     '                hs = _hidden_subs(S, p + 2, min(e, n), dq=False)',
     '                hs = []', "lint"),
    ('挖空的詞首不是空白',
     '        if c in " \\t" and S[p] in " \\t\\0":',
     '        if c in " \\t":', "lint"),
    ('對齊：續行訊號',
     '            if s[j] == "\\\\" and j == len(s) - 1 and joined(tail) is not None:',
     '            if False:', "lint"),
    ('對齊：heredoc 分隔字詞',
     '            if c.startswith("<<", i) and s.startswith("<<", j):',
     '            if False:', "lint"),
    ('strict 逐段',
     '            if conns[k] != "|&" and not _fd2_to_pipe(segs[k]["trail"]):',
     '            if False:', "lint"),
    ('strict：|& 連接',
     '            if conns[k] != "|&" and not _fd2_to_pipe(segs[k]["trail"]):',
     '            if not _fd2_to_pipe(segs[k]["trail"]):', "lint"),
    ('pipefail：關鍵字',
     '    if sh == "bash":\n        return {"pipefail": True, "trace": False}',
     '    if sh == "bash":\n        return {"pipefail": False, "trace": False}', "lint"),
    ('pipefail：樣板一律當有（R35 的洞）',
     '    return {"pipefail": pf, "trace": trace}',
     '    return {"pipefail": True, "trace": trace}', "lint"),
    ('pipefail：樣板的 -o pipefail',
     '                if nm == "pipefail":\n                    pf = on',
     '                if nm == "pipefail":\n                    pf = False', "lint"),
    ('pipefail：子脈絡不算',
     '        if ev["k"] == "pf" and not ev.get("sub"):',
     '        if ev["k"] == "pf":', "lint"),
    ('pipefail：set +o 關掉',
     '                    elif nm == "pipefail":\n                        self.pf_event(on, ctx)',
     '                    elif nm == "pipefail":\n                        self.pf_event(True, ctx)', "lint"),
    ('pipefail：shopt -uo 關掉',
     '                self.pf_event("s" in flags, ctx)',
     '                self.pf_event(True, ctx)', "lint"),
    ('case 模式的 |',
     '        if self.word(t, "case"):\n            return self.parse_case(ctx)',
     '        if False:\n            return self.parse_case(ctx)', "lint"),
    ('ro_text 去行尾註解',
     '                    ro_text = " ".join(_uncomment(l) for l in raw[l2:_end(l2, i2) + 1])',
     '                    ro_text = " ".join(raw[l2:_end(l2, i2) + 1])', "lint"),
    ('ro_text 不挖空引號',
     '                    ro_text = " ".join(_uncomment(l) for l in raw[l2:_end(l2, i2) + 1])',
     '                    ro_text = " ".join(yaml_split_comment(l)[0] for l in raw[l2:_end(l2, i2) + 1])', "lint"),
    ('_scalar 對原文解碼',
     '        body = _uncomment(KEY_RE.match(norm[l0]).group(3) or "")',
     '        body = yaml_split_comment(KEY_RE.match(norm[l0]).group(3) or "")[0]', "lint"),
    ('根層級 defaults.run flow',
     '                    if STRICT and _flow_value(l2):',
     '                    if False:', "lint"),
    ('樣板的 trace',
     '        if STRICT and eff_shell is not None and (tmpl is None or tmpl["trace"]):',
     '        if STRICT and eff_shell is not None and tmpl is None:', "lint"),
    ('dq 分支：`$(`／反引號同一行收得掉就整段吃掉（R36 第 6 列）',
     '                    if e is not None:\n                        code.append(" " * (e - i)); i = e; prev_sig = "x"; continue\n                    if line.startswith("$((", i):',
     '                    if False:\n                        code.append(" " * (e - i)); i = e; prev_sig = "x"; continue\n                    if line.startswith("$((", i):', "lint"),
    ('code 模式：從雙引號進來的命令替換收尾時回到雙引號（R37）',
     '            if dq_ret and ((ch == "`" and not bt) if dq_ret[-1] == 0 else (ch == ")" and csub + cpar < dq_ret[-1])):',
     '            if False:', "lint"),
    ('dq 分支：`$((` 收不掉 ⇒ fail-closed（R36 第 16 列）',
     '                    if line.startswith("$((", i):\n                        unparsed = ("雙引號裡的算術',
     '                    if False:\n                        unparsed = ("雙引號裡的算術', "lint"),
    ('dq 分支：舊式算術 `$[` fail-closed（R37 相鄰）',
     '                if line.startswith("$[", i):\n                    # 舊式算術',
     '                if False:\n                    # 舊式算術', "lint"),
    ('_param_end：`$[` fail-closed（R36 第 5 列 (c)）',
     '        if line.startswith("$[", j):                # 舊式算術',
     '        if False:                # 舊式算術', "lint"),
    ('_dq_end：`$[` fail-closed（R37）',
     '        if line.startswith("$[", k):\n            return None\n        if line.startswith("$(", k) or line[k] == "`":',
     '        if line.startswith("$(", k) or line[k] == "`":', "lint"),
    ("_cmdsub_end：詞首 `#`、`$'`、`$[` fail-closed（R36 第 7 列）",
     '            k += 2; prev = "x"; continue\n        if (c == "#" and at_word) or line.startswith("$\'", k) or line.startswith("$[", k):\n            return None\n',
     '            k += 2; prev = "x"; continue\n        if False:\n            return None\n', "lint"),
    ('_cmdsub_end：詞首 `#`（單一運算元）',
     '            k += 2; prev = "x"; continue\n        if (c == "#" and at_word) or line.startswith("$\'", k) or line.startswith("$[", k):\n            return None\n',
     '            k += 2; prev = "x"; continue\n        if line.startswith("$\'", k) or line.startswith("$[", k):\n            return None\n', "lint"),
    ("_cmdsub_end：`$'`（單一運算元）",
     '            k += 2; prev = "x"; continue\n        if (c == "#" and at_word) or line.startswith("$\'", k) or line.startswith("$[", k):\n            return None\n',
     '            k += 2; prev = "x"; continue\n        if (c == "#" and at_word) or line.startswith("$[", k):\n            return None\n', "lint"),
    ('_cmdsub_end：`$[`（單一運算元）',
     '            k += 2; prev = "x"; continue\n        if (c == "#" and at_word) or line.startswith("$\'", k) or line.startswith("$[", k):\n            return None\n',
     '            k += 2; prev = "x"; continue\n        if (c == "#" and at_word) or line.startswith("$\'", k):\n            return None\n', "lint"),
    ('_cmdsub_end：heredoc `<<` fail-closed（R36 第 7 列）',
     '            k += 3; prev = "<"; continue\n        if line.startswith("<<", k):\n            return None\n',
     '            k += 3; prev = "<"; continue\n', "lint"),
    ('_cmdsub_end：`<<<` 不是 heredoc',
     '        if line.startswith("<<<", k):\n            k += 3; prev = "<"; continue\n',
     '', "lint"),
    ('_cmdsub_end：詞首 `case` fail-closed（R36 第 7 列）',
     '        if at_word and line.startswith("case", k) and line[k + 4:k + 5] in ("", " ", "\\t"):\n            return None\n',
     '', "lint"),
    ('主掃描器 case 追蹤：模式 `)` 不減深度（R36 第 7 列）',
     '                cases[-1][1] = "cmd"                        # case 的模式括號：不減深度\n                paren_claimed = True                        # 模式括號不是裸括號（合併 r37c×r37d）\n            elif ch == ")" and cpar:',
     '                cases[-1][1] = "cmd"                        # case 的模式括號：不減深度\n                cpar, csub = (cpar - 1, csub) if cpar else (cpar, csub - 1)\n                paren_claimed = True                        # 模式括號不是裸括號（合併 r37c×r37d）\n            elif ch == ")" and cpar:', "lint"),
    ('主掃描器 case 追蹤：整段關掉（不偵測 case／esac）',
     '            if csub and (prev_sig is None or prev_sig in SHELL_WORD_BREAK):\n                kw = CASE_KW_RE.match(line, i)',
     '            if False:\n                kw = CASE_KW_RE.match(line, i)', "lint"),
    ('主掃描器 case 追蹤：不在命令起點或不是 `WORD in` ⇒ fail-closed',
     '                        if not (at_cmd and _case_head(line, i)):',
     '                        if False:', "lint"),
    ('主掃描器 case 追蹤：`_case_head` 運算元',
     '                        if not (at_cmd and _case_head(line, i)):',
     '                        if not (at_cmd):', "lint"),
    ('主掃描器 case 追蹤：`at_cmd` 運算元',
     '                        if not (at_cmd and _case_head(line, i)):',
     '                        if not (_case_head(line, i)):', "lint"),
    ('主掃描器 case 追蹤：`;;` 回到等模式',
     '                cases[-1][1] = "pat"                        # `;;`',
     '                pass                        # `;;`', "lint"),
    ('主掃描器 case 追蹤：子句命令裡同一層的單獨 `)` ⇒ fail-closed',
     '                if cases[-1][1] == "cmd":\n                    unparsed = "命令替換裡 case 子句',
     '                if False:\n                    unparsed = "命令替換裡 case 子句', "lint"),
    ('`_at_command`：模式 `)` 之後是命令起點',
     '    if s.endswith(")") and cases and cases[-1][0] == lvl and cases[-1][1] == "cmd":\n        return True\n',
     '', "lint"),
    ('_arith_end：深度 0 的單一 `)` fail-closed',
     '            elif line.startswith("))", k):\n                return k + 2\n            else:\n                return None\n',
     '            elif line.startswith("))", k):\n                return k + 2\n', "lint"),
    ('_arith_end：引號／反斜線 fail-closed',
     '        if c in "\\\\\'\\"`":\n            return None\n',
     '', "lint"),
    ("[守 codex 第 8 條不做] `_param_end` 的 `'` 當引號（→ bypass-param-expansion-dq-escaped-quote、-dq-nested-param-quote）",
     '        if c == \'"\':\n            e = _dq_end(line, j)',
     '        if False:', "lint"),
    ('_cmdsub_end：`$((` 交給 _arith_end（R36 第 16 列）',
     '    if line.startswith("$((", j):\n        return _arith_end(line, j)\n    k, n, depth = j + 2, len(line), 1\n    prev = "("                                          # 詞首判定用：`$(` 之後就是詞首\n',
     '    k, n, depth = j + 2, len(line), 1\n    prev = "("                                          # 詞首判定用：`$(` 之後就是詞首\n', "lint"),
    ('主掃描器 case 追蹤：`esac` 只在命令起點或模式位置收尾',
     '(cases[-1][1] == "pat" or at_cmd):\n                        cases.pop()',
     '(True):\n                        cases.pop()', "lint"),
    ('主掃描器 case 追蹤：前導 `(` 不計深度',
     '                if not (cases and cases[-1][0] == csub + cpar and cases[-1][1] == "pat"):\n                    cpar += 1',
     '                if True:\n                    cpar += 1', "lint"),
    ('_cmdsub_end：雙引號字串走 _dq_end（巢狀命令替換）',
     '            e = (_dq_end(line, k) if c == \'"\' else _backtick_end(line, k) if c == "`"\n                 else _param_end(line, k) if line[k + 1] == "{" else _arith_end(line, k))',
     '            e = (line.find(\'"\', k + 1) + 1 or None if c == \'"\' else _backtick_end(line, k) if c == "`"\n                 else _param_end(line, k) if line[k + 1] == "{" else _arith_end(line, k))', "lint"),
    ('`PIPED_RE` 左邊界退回 `[^|\\s]`（R37 d 包 R36 第 15 列 → bypass-r37d-semi-pipe、-andand-cont-pipe）',
     '[^|\\s;&(]\\s*\\|(?!\\|)',
     '[^|\\s]\\s*\\|(?!\\|)', "lint"),
    ('`CONT_RE` 拿掉 `|&`（R37 d 包 R36 第 21 列 → good-r37d-pipe-amp-cont、-chained）',
     'CONT_RE = re.compile(r"(\\|\\|?|\\|&|&&)\\s*$")',
     'CONT_RE = re.compile(r"(\\|\\|?|&&)\\s*$")', "lint"),
    ('`[[` 的判定退回「前一字元是詞界」而非 cmd_pos（R37 d 包 R36 第 5(a) 列 → bypass-r37d-cond-arg-position、-cond-second-arg）',
     'if (line.startswith("[[", i) and line[i + 2:i + 3] in (" ", "\\t", "")\n                    and cmd_pos):',
     'if (line.startswith("[[", i) and line[i + 2:i + 3] in (" ", "\\t", "")\n                    and prev_sig in SHELL_WORD_BREAK):', "lint"),
    ('算術裡未配對的單獨 `)` 不再 fail-closed（R37 d 包 R36 第 5(a) 列 → bypass-r37d-dparen-nested-subshell）',
     '                        unparsed = "`((…))` 裡出現未配對的單獨 `)`——可能是巢狀 subshell `((cmd) )` 不是算術，本 lint 不猜"\n                        break\n',
     '                        pass\n', "lint"),
    ('區塊結尾的未收尾構造檢查整支拿掉（R37 d 包 R36 第 15 列 → bypass-r37d-unterm-*）',
     'elif arith or brk or cond or csub or bt or bare_par:',
     'elif False:', "lint"),
    ('`EXTGLOB_RE` 恆假（R37 d 包 R36 第 17 列 → bypass-r37d-extglob-pattern、-multi-opt）',
     'EXTGLOB_RE = re.compile(r"\\bshopt\\s+-[A-Za-z]*s[A-Za-z]*\\s+(?:\\S+\\s+)*extglob\\b")',
     'EXTGLOB_RE = re.compile(r"(?!)")', "lint"),
    ('分隔字收集迴圈不配對 `${`／`$[`（R37 d 包 R36 第 14 列 → bypass-r37d-delim-*）',
     'if line.startswith("${", j) or line.startswith("$[", j):',
     'if False:', "lint"),
    ('多行引號 run 純量的守衛拿掉（R37 d 包 R36 第 21 列 → bypass-r37d-multiline-dq-run、-sq-run）',
     'if inline[:1] in ("\'", \'"\') and any(\n                    kind[k] == "SCALAR" and owner[k] == r for k in range(r + 1, s["end"] + 1)):',
     'if False:', "lint"),
    ('`_ansic_decode` 八進位 ≥0x80 不再 fail-closed（R37 e 包 R36 第 5(b) 列 → bypass-r37e-ansic-octal-nonascii）',
     'v = int(m, 8) & 0xFF\n            if v == 0 or v >= 0x80:\n                return None\n            out.append(chr(v)); i += 1 + len(m); continue',
     'v = int(m, 8) & 0xFF\n            if v == 0:\n                return None\n            out.append(chr(v)); i += 1 + len(m); continue', "lint"),
    ('`_ansic_decode` 的 NUL 不再 fail-closed（R37 e 包 R36 第 21 列 → bypass-r37e-ansic-nul）',
     'v = int(m, 8) & 0xFF\n            if v == 0 or v >= 0x80:\n                return None\n            out.append(chr(v)); i += 1 + len(m); continue',
     'v = int(m, 8) & 0xFF\n            if v >= 0x80:\n                return None\n            out.append(chr(v)); i += 1 + len(m); continue', "lint"),
    ('`dedent_block` 的空行判斷改回 `strip()`（R37 e 包 R36 第 10 列 → bypass-r37e-dedent-tab-first-line）',
     'body = [l for l in lines[1:] if l.strip(" ")]',
     'body = [l for l in lines[1:] if l.strip()]', "lint"),
    ('`fold_block` 接行時改回 `l.strip()`（R37 e 包 R36 第 11 列 → bypass-r37e-fold-trailing-space-terminator）',
     'out[acc] = out[acc] + " " + l',
     'out[acc] = out[acc] + " " + l.strip()', "lint"),
    ('cmd_pos：主引號開啟分支未收回 False（R37 合併時發現 → bypass-r37m-quoted-command-word-cond）',
     '                quote = ch; code.append(ch); i += 1; prev_sig = ch; cmd_pos = False; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）',
     '                quote = ch; code.append(ch); i += 1; prev_sig = ch; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）', "lint"),
    ("cmd_pos：ANSI-C `$'…'` 詞整段消費未收回 False（R37 合併時發現 → bypass-r37m-ansic-word-before-cond）",
     '                code.append(" " * (j + 1 - i)); i = j + 1; prev_sig = "x"; cmd_pos = False; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）',
     '                code.append(" " * (j + 1 - i)); i = j + 1; prev_sig = "x"; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）', "lint"),
    ('cmd_pos：`${…}` 詞整段消費未收回 False（R37 合併時發現 → bypass-r37m-param-word-before-cond）',
     '                code.append(" " * (e - i)); i = e; prev_sig = "x"; cmd_pos = False; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）',
     '                code.append(" " * (e - i)); i = e; prev_sig = "x"; continue  # 吃掉的是一個詞（的一部分），不是運算子：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）', "lint"),
    ('cmd_pos：跳脫字元分支未收回 False（R37 合併時發現 → bypass-r37m-escaped-word-before-cond）',
     '                    code.append("  "); i += 2\n                    prev_sig = "x"          # 被逃脫的字元一律當成「非空白」——`a\\ #` 的 `#` 不起註解\n                    cmd_pos = False          # 被逃脫的字元是詞的一部分：之後不在命令位置（R37 合併時發現，見 bypass-r37m-*）\n                    continue',
     '                    code.append("  "); i += 2\n                    prev_sig = "x"          # 被逃脫的字元一律當成「非空白」——`a\\ #` 的 `#` 不起註解\n                    continue', "lint"),
    ('cmd_pos：dq_ret 收尾回雙引號未收回 False（合併 r37c×r37d → bypass-r37m-cond-after-dq-cmdsub-close）',
     '                dq_ret.pop(); quote = \'"\'\n                cmd_pos = False          # 回到雙引號＝回到同一個詞的中間，不是命令位置（合併 r37c×r37d）\n                code.append(ch); i += 1; prev_sig = ch; continue',
     '                dq_ret.pop(); quote = \'"\'\n                code.append(ch); i += 1; prev_sig = ch; continue', "lint"),
    ('cmd_pos：迴圈底 `!`／`{` 只在獨立詞才是保留字（R37 合併時發現 → bypass-r37m-bang/brace-argument-before-cond）',
     '                cmd_pos = cmd_pos and line[i:i + 1] in ("", " ", "\\t")',
     '                cmd_pos = True', "lint"),
    ('_hidden_subs 呼叫點失去 case-aware（合併 r37b×r37c → good-r37c-dq-cmdsub-case-sameline）',
     '            e = (_cmdsub_end_case(S, k) if dq else _cmdsub_end(S, k)) if c == "$" else _backtick_end(S, k)   # 雙引號裡認得 case（合併 r37b×r37c）',
     '            e = _cmdsub_end(S, k) if c == "$" else _backtick_end(S, k)   # 雙引號裡認得 case（合併 r37b×r37c）', "lint"),
    ('_word：掃描器把雙引號切成 code 時的識別分支關掉（R37 合併 r37b×r37c → good-r37c-dq-cmdsub-multiline-case）',
     '            if c == \'"\' and C[p + 1:e].strip():',
     '            if False:', "lint"),
    ('nest()/bt_at：反引號註解止於收尾反引號的「最內層」條件關掉（R37 合併時協調者發現 → bypass-r37m-backtick-cmdsub-comment）',
     '                if bt and nest() == bt_at:',
     '                if bt:', "lint"),
    ('shell_scan 雙引號分支的呼叫點失去 case-aware（合併 r37b×r37c → bypass-r37t8-dq-cmdsub-case-inner-pipe、-dq-cmdsub-case-second-clause-pipe）',
     '                    e = _backtick_end(line, i) if ch == "`" else _cmdsub_end_case(line, i)   # 雙引號裡：認得 case（合併 r37b×r37c）',
     '                    e = _backtick_end(line, i) if ch == "`" else _cmdsub_end(line, i)   # 雙引號裡：認得 case（合併 r37b×r37c）', "lint"),
    ('_cmdsub_end_case 自身的 case 模式括號深度追蹤關掉（合併 r37b×r37c → bypass-r37t8-dq-cmdsub-case-inner-pipe、-dq-cmdsub-case-second-clause-pipe）',
     '        elif c == ")":\n            if cases and cases[-1][0] == depth:\n                if cases[-1][1] == "cmd":\n                    return None                         # 子句命令之後同一層的單獨 `)`：bash 語法錯誤\n                cases[-1][1] = "cmd"                    # 模式括號：不減深度\n            else:\n                depth -= 1\n                if not depth:\n                    return None if cases else k + 1',
     '        elif c == ")":\n            if False:\n                if cases[-1][1] == "cmd":\n                    return None                         # 子句命令之後同一層的單獨 `)`：bash 語法錯誤\n                cases[-1][1] = "cmd"                    # 模式括號：不減深度\n            else:\n                depth -= 1\n                if not depth:\n                    return None if cases else k + 1', "lint"),
    ('`_ansic_decode` 的 \\x／\\u／\\U 門檻整段拿掉（R37 e 包 H9 → bypass-r37e-ansic-hex-nonascii 等四張）',
     '                v = int(m.group(), 16)\n                if v == 0 or v >= 0x80:\n                    return None\n',
     '                v = int(m.group(), 16)\n', "lint"),
    ('`_ansic_decode` 十六進位門檻的 ≥0x80 那一半（R37 e 包 → bypass-r37e-ansic-hex-nonascii 等四張）',
     '                v = int(m.group(), 16)\n                if v == 0 or v >= 0x80:\n',
     '                v = int(m.group(), 16)\n                if v == 0:\n', "lint"),
    ('`_arith_end` 的 `(` 不計深度（R37 c 包 R36 第 16 列 → good-r37c-dq-arith-nested-shift）',
     '        if c == "(":\n            depth += 1\n        elif c == ")":\n            if depth:\n                depth -= 1\n            elif line.startswith("))", k):',
     '        if False:\n            depth += 1\n        elif c == ")":\n            if depth:\n                depth -= 1\n            elif line.startswith("))", k):', "lint"),
    ('`_dq_end` 不配對巢狀 `$(`／反引號（R37 c 包 → bypass-param-expansion-dq-backtick-quote、-dq-cmdsubst-quote）',
     '        if line.startswith("$(", k) or line[k] == "`":\n            e = _cmdsub_end(line, k) if line[k] == "$" else _backtick_end(line, k)\n',
     '        if False:\n            e = _cmdsub_end(line, k) if line[k] == "$" else _backtick_end(line, k)\n', "lint"),
    ('`_dq_end` 不配對巢狀 `${`（R37 c 包 → bypass-param-expansion-dq-nested-param-quote）',
     '        if line.startswith("${", k):\n            e = _param_end(line, k)\n            if e is None:\n                return None\n            k = e; continue\n        k += 1\n    return k + 1 if k < n else None',
     '        k += 1\n    return k + 1 if k < n else None', "lint"),
    ('`_cmdsub_end` 的巢狀雙引號／反引號／`${`／`$((` 配對整段關掉（R37 c 包 R36 第 7 列 → bypass-param-expansion-cmdsubst-unterminated-dq、bypass-r37c-param-cmdsub-nested-dq-cmdsub）',
     '        if c == \'"\' or c == "`" or line.startswith("${", k) or line.startswith("$((", k):\n            e = (_dq_end(line, k)',
     '        if False:\n            e = (_dq_end(line, k)', "lint"),
    ('每個實體行開頭不再重設 cmd_pos（R37 d 包 R36 第 5(a) 列 → bypass-cond-bracket-without-space、bypass-pipe-inside-cond-regex、bypass-r37d-dparen-unpaired-plain）',
     '        cmd_pos = True\n        after_compound = False',
     '        after_compound = False', "lint"),
    ('保留字 then／do／else／elif／if／while／until 不再保持命令位置（R37 d 包 → bypass-cond-bracket-without-space、bypass-pipe-inside-cond-regex）',
     '            if (cmd_pos and ch.isalpha() and (prev_sig is None or prev_sig in SHELL_WORD_BREAK)):',
     '            if False:', "lint"),
    ('命令替換裡的 `(` 不再由 cpar／case 認領、改算裸括號（合併 r37c×r37d → good-cmdsubst-parens-then-heredoc、good-r37c-cmdsub-case-leading-paren）',
     '                paren_claimed = True                        # 在命令替換裡：由 cpar／case 追蹤負責，不是裸括號（合併 r37c×r37d）\n',
     '', "lint"),
    ('裸 `(` 不再計深度（R37 d 包 R36 第 15 列 → bypass-r37d-unterm-subshell）',
     '            if ch == "(" and not paren_claimed:\n                bare_par += 1\n',
     '            if False:\n                bare_par += 1\n', "lint"),
    ('裸 `)` 不再減深度（R37 d 包 R36 第 15 列 → good-plain-subshell-then-heredoc 等 12 張）',
     '            elif ch == ")" and not paren_claimed and bare_par:\n                bare_par -= 1\n',
     '            elif False:\n                bare_par -= 1\n', "lint"),
    ('`CMD_POS_CHARS` 之後不再設命令位置（R37 d 包 → bypass-r37d-unterm-cond）',
     '            elif ch in CMD_POS_CHARS:\n                cmd_pos = True\n',
     '            elif False:\n                cmd_pos = True\n', "lint"),
    ('其他非空白字元之後不再收回命令位置（R37 d 包 → bypass-r37m-bang-argument-before-cond、-brace-argument-before-cond）',
     '            elif not ch.isspace():\n                cmd_pos = False\n',
     '            elif False:\n                cmd_pos = False\n', "lint"),
    ("`_word` 不再把挖空的 `$'…'` 解成字面（R37 b 包 → bypass-r37b-fd-ansic-dev-stderr）",
     '                if dec is not None:\n                    lit.append(dec)',
     '                if False:\n                    lit.append(dec)', "lint"),
    ('`_word` 不再剖析未引號的 `$(…)` 內容（R37 b 包 → bypass-r37m-multiline-dq-cmdsub-fd-inside）',
     '            sub, p = _lex(C, S, p + 2, ")")\n            subs.append(sub)',
     '            sub, p = _lex(C, S, p + 2, ")")', "lint"),
    ('子殼層群組 `( … )` 不再當子脈絡（R37 b 包 pipefail → bypass-r37b-strict-pipefail-set-in-subshell）',
     'self.parse_list(dict(ctx, stack=ctx["stack"] + (gid,), sub=True), lambda x: self.op(x, ")"))',
     'self.parse_list(dict(ctx, stack=ctx["stack"] + (gid,)), lambda x: self.op(x, ")"))', "lint"),
    ('`f() …` 的本體不再當子脈絡（R37 b 包 → bypass-r37b-strict-pipefail-set-in-function）',
     '                self.skip_nl()\n                self.parse_command(dict(ctx, sub=True), end)',
     '                self.skip_nl()\n                self.parse_command(ctx, end)', "lint"),
    ('子 shell 的 `-x`／`-v` 不再算 trace（R37 b 包 → bypass-r37b-xtrace-child-bash-x）',
     '                elif on and ch in "xv":\n                    self.hit("子 shell',
     '                elif False:\n                    self.hit("子 shell', "lint"),
    ('`_BASH_PATHS` 只剩關鍵字 `bash`（R37 b 包 R36 第 4 列 → bypass-r37b-strict-pipefail-template-abs-path、good-r37b-strict-pipefail-forms）',
     '_BASH_PATHS = ("bash", "/bin/bash", "/usr/bin/bash")',
     '_BASH_PATHS = ("bash",)', "lint"),
    ('`CMD_POS_CHARS` 拿掉 `;`（R37 d 包 H4 → bypass-r37d-unterm-cond）',
     'CMD_POS_CHARS = ";&|(!{"',
     'CMD_POS_CHARS = "&|(!{"', "lint"),
    ('`_cmdsub_end_case` 的 case 起點／`WORD in` 判定關掉（合併 r37b×r37c → bypass-r37c-dq-case-in-function-body）',
     '                    if not (at_cmd and _case_head(line, k)):\n                        return None\n                    cases.append([depth, "pat"])',
     '                    if False:\n                        return None\n                    cases.append([depth, "pat"])', "lint"),
    ('`_ansic_decode` 十六進位門檻的 `v == 0` 那一半（R37 e 包 H9；八進位那一半有 bypass-r37e-ansic-nul，十六進位沒有 → bypass-r37t8-ansic-hex-nul）',
     '                v = int(m.group(), 16)\n                if v == 0 or v >= 0x80:\n',
     '                v = int(m.group(), 16)\n                if v >= 0x80:\n', "lint"),
    ('`_arith_end` 不再配對巢狀 `${…}`／`$(…)`（R37 c 包 R36 第 16 列 → good-r37t8-dq-arith-nested-cmdsub-quote）',
     '        if line.startswith("${", k) or line.startswith("$(", k):\n            e = _param_end(line, k) if line[k + 1] == "{" else _cmdsub_end(line, k)\n            if e is None:\n                return None\n            k = e; continue\n        if c == "(":\n            depth += 1\n',
     '        if c == "(":\n            depth += 1\n', "lint"),
    ('雙引號分支：反引號裡的雙引號再遇到收不掉的反引號 ⇒ fail-closed 拿掉（R37 c 包 H19 → bypass-r37t8-dq-backtick-inside-backtick）',
     '                    if ch == "`" and bt:\n                        unparsed =',
     '                    if False:\n                        unparsed =', "lint"),
    ('續行重掃前不還原 dq_ret 與 cases（R37 c 包 H20 → good-r37t8-dq-cmdsub-line-continuation）',
     '                    dq_ret, cases = list(lex0[7]), [list(c) for c in lex0[8]]\n',
     '', "lint"),
    ('續行重掃前只不還原 dq_ret（R37 c 包 H20 → good-r37t8-dq-cmdsub-line-continuation）',
     '                    dq_ret, cases = list(lex0[7]), [list(c) for c in lex0[8]]\n',
     '                    cases = [list(c) for c in lex0[8]]\n', "lint"),
    ('續行重掃前只不還原 cases（R37 c 包 H20 → good-r37t8-cmdsub-case-line-continuation）',
     '                    dq_ret, cases = list(lex0[7]), [list(c) for c in lex0[8]]\n',
     '                    dq_ret = list(lex0[7])\n', "lint"),
    ('續行重掃前不還原 bt_at（R37 合併 H20 → good-r37t8-backtick-comment-then-continuation）',
     '                    bt_at, arith_cmd = lex0[9], lex0[10]\n',
     '                    arith_cmd = lex0[10]\n', "lint"),
    ('續行重掃前不還原 bare_par（R37 d 包 H20 → good-r37t8-subshell-line-continuation）',
     '                    bare_par = bare_par0\n',
     '', "lint"),
    ('續行重掃回到邏輯行起點時不重設 cmd_pos（R37 d 包 H20 → bypass-r37t8-cond-line-continuation）',
     '                    cmd_pos = True           # 邏輯行起點永遠是命令位置，重掃回到起點也一樣\n',
     '', "lint"),
    ('`))` 收尾後不收回 cmd_pos（R37 d 包 H23 → bypass-r37t8-arith-cmd-then-cond-word）',
     'prev_sig = ")"; cmd_pos = False\n                        after_compound',
     'prev_sig = ")"\n                        after_compound', "lint"),
    ('`$(` 開啟時不設 cmd_pos=True（R37 d 包 H24 → good-r37t8-cmdsub-first-word-arith-shift）',
     'csub += 1; code.append("$("); i += 2; prev_sig = "("; cmd_pos = True; continue',
     'csub += 1; code.append("$("); i += 2; prev_sig = "("; continue', "lint"),
    ('命令替換裡 cpar 收尾的 `)` 不再認領（合併 r37c×r37d H24 → bypass-r37t8-unterm-subshell-around-cmdsub-group）',
     '                cpar -= 1; paren_claimed = True',
     '                cpar -= 1', "lint"),
    ('命令替換收尾的 `)` 不再認領（合併 r37c×r37d H24 → bypass-r37t8-unterm-subshell-around-cmdsub）',
     '                csub -= 1; paren_claimed = True',
     '                csub -= 1', "lint"),
    ('`_aligned_sources` 的逐字驗證拿掉（R37 b 包 H27 → bypass-r37t8-misaligned-herestring-heredoc）',
     '            if c[i] != " " and c[i] != s[j]:\n                ok = False',
     '            if False:\n                ok = False', "lint"),
    ('`_clamp` 不夾住（挖空段結尾照原文算）（R37 b 包 H27 → bypass-r37t8-clamp-ansic-in-param-then-redirect）',
     '    return max(q, p + 1)',
     '    return max(e, p + 1)', "lint"),
    ('`_dq_parts` 把雙引號裡的 `$X` 當字面（R37 b 包 H27 → bypass-r37t8-set-dq-param-option）',
     '        m = _PARAM_RE.match(body, i)\n        if m:',
     '        m = None\n        if m:', "lint"),
    ('`_dq_parts` 不認雙引號裡的逃脫（R37 b 包 H27 → good-r37t8-set-dq-escaped-dollar）',
     '        if c == "\\\\" and i + 1 < n and body[i + 1] in \'$`"\\\\\\n\':',
     '        if False:', "lint"),
    ('`_hidden_subs` 雙引號模式不在收尾 `"` 停下（R37 b 包 H27 → good-r37t8-dq-cmdsub-then-sq-literal-cmdsub）',
     '        if dq and c == \'"\':\n            break',
     '        if False:\n            break', "lint"),
    ('`_word` 不解挖空的逃脫字元（R37 b 包 H27 → good-r37t8-escaped-char-in-safe-target）',
     '            if s == "\\\\":\n                ch = S[p + 1] if p + 1 < n else ""',
     '            if False:\n                ch = S[p + 1] if p + 1 < n else ""', "lint"),
    ('`_word` 不剖析未引號反引號的內容（R37 b 包 H27 → bypass-r37t8-backtick-word-stderr）',
     '            sub, p = _lex(C, S, p + 1, "`")\n            subs.append(sub)',
     '            sub, p = _lex(C, S, p + 1, "`")', "lint"),
    ('`_lex` 不認 process substitution `<(`／`>(`（R37 b 包 H27 → bypass-r37t8-procsub-stderr-not-a-group）',
     '        if C.startswith("<(", p) or C.startswith(">(", p):   # process substitution：一個詞',
     '        if False:   # process substitution：一個詞', "lint"),
    ('`_lex` 的 fd 前綴不要求緊貼運算子（R37 b 包 R36 第 3 列 → bypass-r37t8-strict-detached-fd-prefix）',
     'prev["k"] == "W" and prev["e"] == p - len(op) and prev["lit"] is not None',
     'prev["k"] == "W" and prev["lit"] is not None', "lint"),
    ('`_lex` 的 fd 前綴不要求未引號（R37 b 包 R36 第 3 列 → bypass-r37t8-strict-quoted-fd-prefix）',
     '                    and prev["lit"] == prev["code"] and re.fullmatch(',
     '                    and re.fullmatch(', "lint"),
    ('`_lex` 不認具名 fd 前綴 `{var}`（R37 b 包 → bypass-r37t8-named-fd-save-stdout）',
     're.fullmatch(r"[0-9]+|\\{[A-Za-z_][A-Za-z0-9_]*\\}", prev["lit"])',
     're.fullmatch(r"[0-9]+", prev["lit"])', "lint"),
    ('`_lex` 在 `$(case …)` 裡不追蹤 case（R37 b 包 → bypass-r37t8-strict-pipefail-in-cmdsub-case）',
     '            if stop == ")" and w["lit"] in ("case", "esac"):',
     '            if False:', "lint"),
    ('`_redir_hit` 不認 `>&-`／`<&-` 是關閉 fd（R37 b 包 → good-r37t8-close-stdin）',
     '        if tl == "-":\n            return None',
     '        if False:\n            return None', "lint"),
    ('`_redir_hit` 不再把 `>&$X`／`<&…`／psub 當外流（R37 b 包 → bypass-r37t8-dup-to-param-fd）',
     '        if op == "<&" or tl is None or t.get("psub"):',
     '        if False:', "lint"),
    ('`_redir_hit` 的「目標看不到原文」fail-closed 拿掉（R37 b 包 → bypass-r37t8-misaligned-herestring-heredoc）',
     '    if sk is None:\n        return "`%s` 的目標看不到原文',
     '    if False:\n        return "`%s` 的目標看不到原文', "lint"),
    ('`_redir_hit` 不豁免 /dev/tcp、/dev/udp（R37 b 包 → good-r37t8-dev-tcp-target）',
     '                                 or re.match(r"/dev/(tcp|udp)/", posixpath.normpath(t["lit"]))):',
     '                                 ):', "lint"),
    ('`function f { …; }` 的本體不當子脈絡（R37 b 包 → bypass-r37t8-strict-pipefail-in-function-keyword）',
     '            self.skip_nl()\n            self.parse_command(dict(ctx, sub=True), end)\n            return {"kind": "func", "trail": [], "neut": False}\n        words, rs',
     '            self.skip_nl()\n            self.parse_command(ctx, end)\n            return {"kind": "func", "trail": [], "neut": False}\n        words, rs', "lint"),
    ('`_Sh.subs` 的 bad_sub fail-closed 拿掉（R37 b 包 → bypass-r37t8-dq-cmdsub-unparsed-stderr）',
     '        if w.get("bad_sub"):',
     '        if False:', "lint"),
    ('`env_word` 的 bare 形式（`export BASH_ENV` 不帶 `=`）拿掉（R37 b 包 R36 第 8 列 → bypass-r37t8-export-bare-bash-env）',
     ' or (bare and text == key):',
     ':', "lint"),
    ('`set -o` 非字面選項名 fail-closed 拿掉（R37 b 包 R36 第 8 列 → bypass-r37t8-set-o-param-name）',
     '                    if nm is None:\n                        self.hit("`set %so`',
     '                    if False:\n                        self.hit("`set %so`', "lint"),
    ('`shopt` 非字面參數 fail-closed 拿掉（R37 b 包 → bypass-r37t8-shopt-param-flags）',
     '            if a is None:\n                self.hit("`shopt` 的參數不是字面',
     '            if False:\n                self.hit("`shopt` 的參數不是字面', "lint"),
    ('`shopt -o` 非字面選項名 fail-closed 拿掉（R37 b 包 → bypass-r37t8-shopt-o-param-name）',
     '            if nm is None:\n                self.hit("`shopt -o`',
     '            if False:\n                self.hit("`shopt -o`', "lint"),
    ('子 shell 的 `-o xtrace` 不算 trace（R37 b 包 → bypass-r37t8-child-bash-o-xtrace）',
     '                    if ch == "o" and on and (nm is None or nm in _TRACE_OPTS):',
     '                    if False:', "lint"),
    ('子 shell 的 `--verbose` 不算 trace（R37 b 包 → bypass-r37t8-child-bash-verbose-long）',
     '            if a == "--verbose":\n                self.hit(',
     '            if False:\n                self.hit(', "lint"),
    ('`_rule_lines` 丟掉整行挖空的程式碼行（R37 b 包自查 → bypass-r37t8-multiline-dq-hollow-mid-cmdsub）',
     '        elif c:\n            rl_code.append(c)',
     '        elif c.strip():\n            rl_code.append(c)', "lint"),
    ('`_analyse` 把沒接 neutralise 的管線也計入 n_neut（R37 b 包 → bypass-r37t8-strict-unrelated-pipeline-not-neut）',
     '        if not last:\n            continue',
     '        if False:\n            continue', "lint"),
    ('`_bash_template` 短選項白名單拿掉（R37 b 包 R36 第 4 列 → bypass-r37t8-strict-shell-template-interactive）',
     '            elif ch not in _BASH_SHORT:',
     '            elif False:', "lint"),
    ('`_env_names` 對同一行運算式不回 `?`（R37 b 包 R36 第 8 列 H28 → bypass-r37t8-step-env-inline-expression）',
     '            return [] if inline[:1] in ("{", "[") else ["?"]',
     '            return []', "lint"),
    ('env 規則不把 `?` 算成命中（R37 b 包 H34 → bypass-r37t8-step-env-inline-expression）',
     '        env_hit = [k for k in env_names if k in ENV_TRACE_KEYS or k == "?"]',
     '        env_hit = [k for k in env_names if k in ENV_TRACE_KEYS]', "lint"),
    ('`--strict`：看得到接 neutralise 的管線、規則層剖析不出它 ⇒ fail-closed 拿掉（R37 b 包 H34 → bypass-r37t8-strict-case-pattern-looks-piped）',
     '        elif STRICT and not declared and not an["n_neut"]:',
     '        elif False:', "lint"),
    ('`_analyse` 外層 try（規則層自己的錯 fail-closed）拿掉（R37 b 包 H34 → bypass-r37t8-rule-layer-recursion-limit）',
     '        except (IndexError, KeyError, ValueError, RecursionError) as e:',
     '        except (ZeroDivisionError,) as e:', "lint"),
    ('`CMD_POS_CHARS` 拿掉 `&`（R37 d 包 H4 → bypass-r37t8-cond-after-andand）',
     'CMD_POS_CHARS = ";&|(!{"',
     'CMD_POS_CHARS = ";|(!{"', "lint"),
    ('`CMD_POS_CHARS` 拿掉 `|`（R37 d 包 H4 → bypass-r37t8-cond-after-oror）',
     'CMD_POS_CHARS = ";&|(!{"',
     'CMD_POS_CHARS = ";&(!{"', "lint"),
    ('`CMD_POS_CHARS` 拿掉 `(`（R37 d 包 H4 → bypass-r37t8-cond-in-subshell）',
     'CMD_POS_CHARS = ";&|(!{"',
     'CMD_POS_CHARS = ";&|!{"', "lint"),
    ('`_cmdsub_end_case` 的 `<<` ⇒ None 拿掉（合併 r37b×r37c H12 → bypass-r37t8-dq-cmdsub-sameline-heredoc）',
     '            code.append("<<<"); k += 3; prev = "<"; continue\n        if line.startswith("<<", k):\n            return None\n',
     '            code.append("<<<"); k += 3; prev = "<"; continue\n', "lint"),
    ("`_cmdsub_end_case` 的詞首 `#`／`$'`／`$[` ⇒ None 拿掉（合併 r37b×r37c H12 → good-r37t8-dq-cmdsub-comment-close-next-line）",
     '            code.append(";"); k += 1; prev = "\\n"; continue\n        if (c == "#" and at_word) or line.startswith("$\'", k) or line.startswith("$[", k):\n            return None\n',
     '            code.append(";"); k += 1; prev = "\\n"; continue\n', "lint"),
    ('`_cmdsub_end_case` 的 `esac` 不收 case（合併 r37b×r37c H12 → bypass-r37t8-dq-cmdsub-case-inner-pipe）',
     '                elif cases and cases[-1][0] == depth and (cases[-1][1] == "pat" or at_cmd):\n                    cases.pop()\n                code.append(kw.group(1))',
     '                elif False:\n                    cases.pop()\n                code.append(kw.group(1))', "lint"),
    ('`_cmdsub_end_case` 的 `;;` 不回到等模式（合併 r37b×r37c H12 → bypass-r37t8-dq-cmdsub-case-second-clause-pipe）',
     '            cases[-1][1] = "pat"\n        if c == "\'":',
     '            pass\n        if c == "\'":', "lint"),
    ('`CASE_KW_RE` 拿掉詞界（合併 r37c H12 → good-r37t8-cmdsub-word-starting-with-case）',
     'CASE_KW_RE = re.compile(r"(case|esac)(?=[\\s;&|()<>]|$)")',
     'CASE_KW_RE = re.compile(r"(case|esac)")', "lint"),
    ('`PIPED_RE` 的路徑部分退回 `\\S*`（R37 合併 → bypass-r37m-neutralise-path-spans-*）',
     'python3\\s+[^\\s;&|()<>`]*neutralise',
     'python3\\s+\\S*neutralise', "lint"),
    ('`PIPED_RE` 的結尾退回只認空白（R37 合併 → good-r37m-neutralise-glued-follower）',
     'neutralise\\.py(?=[\\s;&|)<>`]|$)")',
     'neutralise\\.py(\\s|$)")', "lint"),
    ('迴圈底部覆寫反引號設好的 cmd_pos（R37 完整性審查缺陷 a → bypass-r37t8-backtick-cond-regex）',
     '            elif ch == "`":\n                pass    # 反引號分支已經設好',
     '            elif False:\n                pass    # 反引號分支已經設好', "lint"),
    ('反引號開啟時不設 cmd_pos（R37 完整性審查缺陷 a → bypass-r37t8-backtick-cond-regex）',
     '                cmd_pos = not bt    # 開啟（bt False→True）',
     '                pass    # 開啟（bt False→True）', "lint"),
    ('`]]`／`))` 之後直接接保留字不再 fail-closed（R37 完整性審查缺陷 b → bypass-r37t8-cond-then-no-semicolon）',
     '            if after_compound and not ch.isspace():',
     '            if False:', "lint"),
    ('算術命令 `))` 收尾不設 after_compound（R37 缺陷 b → bypass-r37t8-arith-then-no-semicolon）',
     '                        after_compound = arith_cmd and not arith; continue',
     '                        after_compound = False; continue', "lint"),
    ('`]]` 收尾不設 after_compound（R37 缺陷 b → bypass-r37t8-cond-then-no-semicolon）',
     'cmd_pos = False; after_compound = True; continue',
     'cmd_pos = False; after_compound = False; continue', "lint"),
    ('算術展開 `$((` 也當成算術命令（R37 缺陷 b 的邊界 → good-r37t8-arith-expansion-then-word）',
     '                arith_cmd = prev_sig != "$"',
     '                arith_cmd = True', "lint"),
    ('換行不重設 after_compound（R37 缺陷 b 的邊界 → good-r37t8-cond-then-next-line）',
     '        after_compound = False               # 換行本身就是分隔字元',
     '        pass               # 換行本身就是分隔字元', "lint"),
    ('`_lex`：`((…))`／`[[…]]` 裡的命令替換不剖析（R37 完整性審查缺陷 c → bypass-r37t8-arith-cmd-cmdsub-stderr、-cond-cmdsub-stderr）',
     '                hs = _interior_subs(S, p + 2, e)                    # 但裡面的命令替換照樣執行（缺陷 c）',
     '                hs = []', "lint"),
    ('`_word`：算術展開 `$((…))` 裡的命令替換不剖析（R37 缺陷 c → bypass-r37t8-arith-exp-cmdsub-stderr）',
     '            hs = None if e < 0 else _interior_subs(S, p + 3, e)       # 算術展開裡的命令替換（缺陷 c）',
     '            hs = []', "lint"),
    ('`_word`：舊式算術 `$[…]` 裡的命令替換不剖析（R37 缺陷 c → bypass-r37t8-legacy-arith-cmdsub-stderr）',
     '                hs = _interior_subs(S, p + 2, e - 1) if not d else None   # 舊式算術裡的命令替換（缺陷 c 的相鄰形狀）',
     '                hs = []', "lint"),
    ('`_interior_subs` 不看雙引號段（R37 缺陷 c → bypass-r37t8-cond-dq-apostrophe-cmdsub-stderr）',
     '            hs = _hidden_subs(S, k + 1, e - 1, dq=True)\n            if hs is None:\n                return None\n            out.extend(hs)\n            k = e\n',
     '            k = e\n', "lint"),
    ('`_lex` 不看內部有沒有被挖空、一律當不透明詞（R37 完整性審查缺陷 e → good-r37t8-strict-set-arg-cond-word）',
     '            if e >= 0 and not C[p + 2:e].strip(" \\t\\n\'\\""):',
     '            if e >= 0:', "lint"),
    ('`_lex` 的「挖空」不含引號字元（R37 缺陷 c／e → bypass-r37t8-arith-cmd-cmdsub-stderr、-cond-cmdsub-stderr）',
     '            if e >= 0 and not C[p + 2:e].strip(" \\t\\n\'\\""):',
     '            if e >= 0 and not C[p + 2:e].strip():', "lint"),
    ('`_lex` 的 `((…))`／`[[…]]` 分支整支拿掉（R37 缺陷 c／e → bypass-r37t8-arith-cmd-cmdsub-stderr、-cond-cmdsub-stderr）',
     '        if C.startswith("((", p) or C.startswith("[[", p):\n',
     '        if False:\n', "lint"),
]

# ── R37（#33 verify R36 條件 7）：神諭本身進入突變範圍 ──────────────────────────────
# R36 條件 7 點名的靶（「STDERR_ROUTE_RE 分支改成 elif False:」）已經不存在——r37a 把那整條
# 正規式判定換成差分判定 `classify_piped_leak`。條件 7 真正要的是「有外流就收進已知 G」那個方向的
# 閘門要有網；對應的是 `oracle:g-diff-never-G`（下面第二條）：把 `classify_piped_leak` 判定 G 的
# 那個 `if` 關掉，任何原本該歸 G 的 step 都會改判「不一致：繞過」，被
# `known-granularity-*`／`known-r37a-g-continued-pipeline` 逮到。下面每一條都在合併後的樹上實跑驗殺過，
# 不是照抄 r37a 對合併前 commit 量的結果。
MUTATIONS += [
    ("oracle: G 差分永遠判定為 G（R37，R36 第 1 列 → known-r37a-g-plus-s2-same-step、"
     "known-stderr-cmd-error-missing-2to1、known-r37a-mustfail-s2-strict-not-blocking）",
     '    if not contrib:\n        return "G", None',
     '    if True:\n        return "G", None', "oracle"),
    # R36 條件 7 的對應靶：這是「有外流就收進已知 G」那個方向的閘門本身。
    ("oracle: G 差分永遠不判定為 G——R36 條件 7 對應閘門（R37，R36 第 1 列 → "
     "known-granularity-one-pipe-whole-block、known-granularity-stderr-other-command、"
     "known-r37a-g-continued-pipeline）",
     '    if not contrib:\n        return "G", None',
     '    if False:\n        return "G", None', "oracle"),
    ("oracle: G 差分忽略『部分外流跟著消失』（R37，R36 第 1 列 → known-r37a-g-plus-s2-same-step、"
     "known-stderr-cmd-error-missing-2to1）",
     'if base_mlines[k] - ml[k]]', 'if not (ml[0] or ml[1])]', "oracle"),
    ("oracle: G 差分關掉語法完整性守衛（R37，R36 第 1 列 → known-r37a-mustfail-g-diff-syntax-break）",
     '    if pn[0] != 0 and pn != _bash_n(run, bash):', '    if False:', "oracle"),
    ("oracle: G 差分關掉『出現原本沒有的外流行』守衛（R37，R36 第 1 列 → "
     "known-r37a-mustfail-g-diff-heredoc-feeds-pipe）",
     '    if any(ml[k] - base_mlines[k] for k in (0, 1)):', '    if False:', "oracle"),
    ("oracle: S-2 的 --strict 查核恆真（R37，R36 第 1 列 → known-r37a-mustfail-s2-strict-not-blocking）",
     'elif any(in_step(ln) and STRICT_2TO1_RULE_MSG in m for ln, m in strict_rules()):',
     'elif True:', "oracle"),
    ("oracle: S-2 的 --strict 查核恆假（R37，R36 第 1 列 → known-stderr-cmd-error-missing-2to1、"
     "known-r37a-g-plus-s2-same-step）",
     'elif any(in_step(ln) and STRICT_2TO1_RULE_MSG in m for ln, m in strict_rules()):',
     'elif False:', "oracle"),
    ("oracle: 類別閘門『歸了類卻沒宣告』方向關掉（R37，R36 第 2 列 → known-r37a-mustfail-undeclared-g）",
     '        elif s_ > d_:', '        elif False:', "oracle"),
    ("oracle: 類別閘門『KNOWN-CLASS 過期』方向關掉（R37，R36 第 2 列 → "
     "known-r37a-mustfail-g-diff-syntax-break、known-r37a-mustfail-g-diff-heredoc-feeds-pipe）",
     '        if d_ > s_:', '        if False:', "oracle"),
    ("oracle: pipefail 排除條件改成『任一條 RULE 是 pipefail 就不可比』（R37，R36 第 18 列 → "
     "bypass-r37a-mustfail-strict-pipefail-hides-2to1）",
     'if step_rules and all(PIPEFAIL_RULE_MSG in m for m in step_rules):',
     'if any(PIPEFAIL_RULE_MSG in m for m in step_rules):', "oracle"),
    ("oracle: YAML env 三層覆蓋不帶進腳本（R37，R36 第 8 列 → good-r37a-oracle-env-three-layers）",
     '        env = dict(yaml_env or {})', '        env = {}', "oracle"),
    ("oracle: 續行判定關掉 bash 剖析那一支（R37 → known-r37a-g-continued-pipeline 的註解續行 step）",
     '    return _bash_n(line, bash)[0] != 0 and _bash_n(line + "\\n:", bash)[0] == 0',
     '    return False', "oracle"),
    ("oracle: 續行判定關掉行尾反斜線那一支（R37 → known-r37a-g-continued-pipeline 的反斜線續行 step）",
     '    if re.search(r"(?<!\\\\)(?:\\\\\\\\)*\\\\$", line):\n        return True',
     '    if False:\n        return True', "oracle"),
    ("oracle: G 差分的 pipeline 分支不判定 stdout 外流（R37，R36 第 1 列 → known-r37t8-mustfail-stdout-contribution）",
     '                    if "stdout" in streams:', '                    if False:', "oracle"),
    ("oracle: must-fail 探針只看有沒有失敗、不比對宣告的理由（R37 → test/oracle_selfcheck.py 第 1 項）",
     'ok = bool(res["failures"]) and any(mf.group(1) in x for x in res["failures"] + [r[4] for r in res["rows"]])',
     'ok = bool(res["failures"])', "oracle-inverted"),
    ("oracle: 關掉 oracle↔lint 的 RULE 字面耦合檢查（R37 合併 r37a／r37b 時加 → test/oracle_selfcheck.py 第 2 項）",
     'for _msg in (PIPEFAIL_RULE_MSG, STRICT_2TO1_RULE_MSG):\n    if _msg not in _LINT_SRC:',
     'for _msg in (PIPEFAIL_RULE_MSG, STRICT_2TO1_RULE_MSG):\n    if False:', "oracle-inverted"),
]

EXPECTED_SURVIVE = {
    "pack 內部改名不投票（依構造不可達，保留為防禦）",
    "純改名偵測 git 分支（依構造不可達，保留為防禦）",
    # R12 修法後 LineSanitiser 對**每一段**獨立判 `lstrip().startswith("::")`、不再靠行首旗標——
    # 換回 splitlines() 只會多切幾段、多消毒幾次，方向安全。靶保留是為了釘住「不得再引入旗標」的設計意圖。
    "輸出邊界的行定義（runner 的，不是 splitlines）",
    # R14 requirements F3：R13 把「pack_name 讀取的 containment」放進這裡，理由是「讀取結果不輸出」——假的：
    # check_bumped 的「找不到名為 X 的 pack」會 print(pack_name)，守衛拿掉時 repo 外 symlink 的 name 就進 log。
    # DA-5 預言的後門一輪之後就實現了。現在它有測試網（test_pack_name_containment_keeps_outside_name_out_of_log），
    # 從這裡移除。**每一條進來的靶都要能回答「關掉它，哪一行輸出會變」——答不出來就不是 equivalent，是沒測試。**
}


def suite_of(entry):
    """靶的第四欄選守備單位；省略＝`validate`（既有 114 個靶不用動）。"""
    return entry[3] if len(entry) > 3 else "validate"


def _on_term(signum, _frame):
    """R15 requirements F9：SIGTERM／SIGHUP（不是 Ctrl-C）砍掉一輪時，被 mutate 的 validate.py 無聲留在工作樹——
    BaseException 那條還原路徑只在 KeyboardInterrupt 才會走。把終止訊號轉成 SystemExit（同樣是 BaseException），
    讓同一條路徑還原並印提示。SIGKILL 仍救不了：那正是還原提示叫人跑 `git checkout` 的原因。"""
    raise SystemExit(128 + signum)


def install_restore_signals():
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_term)


def _apply(name, old, new, src):
    """回傳 mutate 後的原始碼。靶不唯一時 raise —— 不默默替換第一個（見模組 docstring）。"""
    if old == "__SPECIAL_NOBASE__":
        i = src.index("    if not base:\n")
        j = src.index('    # #33 verify R6：先前寫死 "plugins/pai-lenses/…"')
        return src[:i] + "    if not base:\n        return\n" + src[j:]
    n = src.count(old)
    if n != 1:
        raise ValueError(f"靶在目標檔中出現 {n} 次（需恰好 1 次）")
    return src.replace(old, new)


def precheck_suites(suites):
    """對每個守備單位的驗證指令各跑一次（同指令＋同工作目錄去重），回傳紅的 `[(suite, rc, 輸出尾巴)]`。
    R28 D9：綠底線是 mutation 量測的前提——基準紅時「殺掉」與「什麼都沒量到」分不開（R9 M15 的洞）。
    測試網：`test_mutation_precheck_runs_every_suite_command`（用假 suite 釘「每條指令恰好跑一次、任一紅就點名」）。"""
    seen, failures = {}, []
    for name, (_f, cmd, cwd) in suites.items():
        key = (tuple(cmd()), str(cwd))
        if key not in seen:
            r = subprocess.run(list(key[0]), cwd=cwd, capture_output=True, text=True)
            seen[key] = (r.returncode, r.stdout[-2000:] + r.stderr[-2000:])
        rc, tail = seen[key]
        if rc != 0:
            failures.append((name, rc, tail))
    return failures


def check_targets_only():
    """只驗每個靶是否恰好命中一次 —— 秒級，可以進 CI（#33 verify R9 M11/M24）。

    完整的 mutation 量測太慢（一輪 = 靶數 × 全套測試；實測數字見 `scripts/test_validate.py` 檔頭），不適合每個 PR 跑。但**靶清單
    相對 validate.py 的漂移**是可以便宜擋住的：有人改動被 mutate 的那幾行、或搬走一道閘門，
    靶就對不上。先前這件事只有在有人手動跑整輪時才會發現，而「忘了跑」是預設。
    """
    srcs = {k: f.read_text(encoding="utf-8") for k, (f, _c, _d) in SUITES.items()}
    src = srcs["validate"]
    broken = []
    # R13（regression R13-6）：EXPECTED_SURVIVE 只是名字集合 —— 靶被改名或刪掉後，這裡的名字會靜默
    # 失效（那個靶重新變成「要人判讀的存活」，或更糟：一個不存在的名字永遠「預期存活」）。
    names = {e[0] for e in MUTATIONS}
    for n in sorted(EXPECTED_SURVIVE - names):
        broken.append((n, "列在 EXPECTED_SURVIVE 但 MUTATIONS 裡沒有這個靶"))
    for entry in MUTATIONS:
        name, old, _new = entry[0], entry[1], entry[2]
        where = suite_of(entry)
        if old == "__SPECIAL_NOBASE__":
            # #33 verify R10 M5：先前只驗兩個 anchor 的其中一個、而且沒驗唯一性 ——
            # 於是它印「全部恰好命中一次」時，另一個 anchor（一句**註解**）可能早就
            # 被改掉了。`_apply` 用 `index()` 找兩個 anchor，兩個都得在、都得唯一。
            for anchor in ("    if not base:\n",
                           '    # #33 verify R6：先前寫死 "plugins/pai-lenses/…"'):
                n = src.count(anchor)
                if n != 1:
                    broken.append((name, f"special anchor {anchor!r:.40} 出現 {n} 次（需 1 次）"))
            continue
        n = srcs[where].count(old)
        if n != 1:
            broken.append((name, f"在 {SUITES[where][0].name} 中出現 {n} 次（需恰好 1 次）"))
    if broken:
        print(f"::error::mutation 靶清單與被守備的檔漂移了（{len(broken)} 個對不上）—— "
              "改動閘門時請一併更新 scripts/mutation_check.py 的 MUTATIONS")
        for n, why in broken:
            print(f"  - {n} | {why}")
        return 1
    print(f"mutation 靶清單 {len(MUTATIONS)} 個全部恰好命中一次 ✓"
          "（這只驗靶解析得到，不代表測試抓得到 —— 那要跑完整輪）")
    return 0


def main():
    # #33 verify R10 M6：先前是 `if "--check-targets" in sys.argv[1:]` —— 手寫解析，
    # 打錯旗標（`--check-target`）會被靜默忽略，然後**直接跑整輪（一小時量級）的就地改寫迴圈**。
    # R9 才剛把 validate.py 的同一種解析拆掉，理由逐字適用於這裡。
    ap = argparse.ArgumentParser(
        prog="mutation_check.py",
        description="量測 test_validate.py 的鑑別力：逐一關掉 validate.py 的判定條件。")
    ap.add_argument("--check-targets", action="store_true",
                    help="只驗每個靶是否恰好命中一次（秒級，CI 會跑），不執行 mutation")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    if args.check_targets:
        return check_targets_only()
    # #33 verify R9 M15：先前沒有綠底線前置檢查。測試套件本身是紅的時候（例如有人正在
    # 改 validate.py 改到一半），**每一個 mutation 都會被判為「殺掉」** —— harness 回報
    # 漂亮的「0 存活」，而它其實什麼都沒量到。這是它自己版本的「肯定式綠燈」。
    # R28 D9（G-R29-4）：前置檢查先前只跑 `test_validate.py`。R27 把守備範圍擴到 lint 之後，lint 靶的
    # 生死由 `--selftest` 判——而 selftest 紅的時候每個 lint 靶都被判「殺掉」，同一個洞換個 suite 又開了。
    # 現在對 SUITES 裡每一條不同的驗證指令各跑一次，任一紅就整輪不跑、點名是哪個 suite。
    print("前置：確認每個守備單位未 mutate 的驗證指令都是綠的 …", flush=True)
    t0 = time.monotonic()
    failures = precheck_suites(SUITES)
    for name, rc, tail in failures:
        print(f"✗ 守備單位 `{name}` 的基準驗證就沒過（rc={rc}）—— 先修綠再量 mutation，"
              "否則它的每個靶都會被誤判為『殺掉』。\n" + tail)
    if failures:
        return 1

    originals = {k: f.read_text(encoding="utf-8") for k, (f, _c, _d) in SUITES.items()}
    install_restore_signals()
    survived, killed, broken = [], [], []
    try:
        for entry in MUTATIONS:
            name, old, new = entry[0], entry[1], entry[2]
            where = suite_of(entry)
            target, cmd, cwd = SUITES[where]
            original = originals[where]
            try:
                mutated = _apply(name, old, new, original)
            except (ValueError, IndexError) as e:
                broken.append((name, str(e)))
                print(f"  靶壞 {name} | {e}", flush=True)
                continue
            if mutated == original:
                broken.append((name, "替換後檔案沒變"))
                print(f"  靶壞 {name} | 替換後檔案沒變", flush=True)
                continue
            target.write_text(mutated, encoding="utf-8")
            try:
                rc = subprocess.run(cmd(), cwd=cwd, capture_output=True, text=True).returncode
            finally:
                target.write_text(original, encoding="utf-8")
            (survived if rc == 0 else killed).append(name)
            print(("  存活 " if rc == 0 else "  殺掉 ") + name, flush=True)
    except BaseException:
        # #33 verify R9 M16：只有 finally 保護時，SIGINT/SIGTERM 或當機會把 `if False:`
        # 留在正式的 validate.py 裡 —— 一個被 mutate 過的 validator 看起來完全正常。
        # 這裡明確印出還原提示，讓「檔案現在可能是壞的」不會靜默。
        for k, (f, _c, _d) in SUITES.items():
            f.write_text(originals[k], encoding="utf-8")
        print("\n⚠ 中斷 —— 已把被 mutate 的檔還原。若程序被強制砍掉未跑到這裡，"
              "請執行 `git status` 與 `git checkout --` 確認。", flush=True)
        raise
    finally:
        for k, (f, _c, _d) in SUITES.items():
            f.write_text(originals[k], encoding="utf-8")

    # R17 DA-H：耗時別再手填。散文裡的區間會漂（R14→R17 連四輪被抓到低估），所以這一輪起
    # **由程式自己量並印出**；文件只保留粗估並指向這一行。
    elapsed = time.monotonic() - t0
    n_run = len(killed) + len(survived) + len(broken)
    if n_run:
        print(f"\n本輪實測耗時：{elapsed/60:.1f} 分鐘 / {n_run} 靶 = 每靶 {elapsed/n_run:.1f} s"
              "（把這個數字填回 test_validate.py 檔頭與 CHANGELOG，不要沿用舊區間）")
    expected = [n for n in survived if n in EXPECTED_SURVIVE]
    survived = [n for n in survived if n not in EXPECTED_SURVIVE]
    print(f"\n殺掉 {len(killed)} / 存活 {len(survived)} / 預期存活 {len(expected)} / 靶壞 {len(broken)}")
    if survived:
        print("\n存活（可能缺測試，也可能是 equivalent mutant —— 逐條判讀）：")
        for n in survived:
            print("  -", n)
    if expected:
        print("\n預期存活（列在 EXPECTED_SURVIVE；每輪仍需確認理由是否成立 —— 這個集合是可以藏東西的，R13 DA-5）：")
        for n in expected:
            print("  -", n)
    unexpected_kill = [n for n in killed if n in EXPECTED_SURVIVE]
    if unexpected_kill:
        # 被殺掉代表它變得可達了 —— 入口條件被放寬。那不是壞事，但 EXPECTED_SURVIVE 要跟著更新。
        print("\n⚠ 預期存活的靶被殺掉了（守衛變成可達，請把它從 EXPECTED_SURVIVE 移除）：")
        for n in unexpected_kill:
            print("  -", n)
    if broken:
        print("\n靶壞（mutation 定義與現行程式碼對不上，先修這裡）：")
        for n, why in broken:
            print(f"  - {n} | {why}")
    # 靶壞是這支自己的缺陷，必須 fail-loud；存活留給人判讀，不當成失敗。
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
