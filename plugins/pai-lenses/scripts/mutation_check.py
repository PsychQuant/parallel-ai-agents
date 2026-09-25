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
    # **這一條列入 EXPECTED_SURVIVE，而且理由要能被檢查**：把它關掉之後，`<<<` 會落到下面的
    # `<<` 分支，但那裡的分隔字解析從第三個 `<` 開始讀，而 `<` 本身就在 `SHELL_WORD_BREAK` 裡，
    # 於是 delim 為空、`if delim:` 不成立、不會產生 heredoc —— **行為等價**。
    # 保留這個分支是為了把意圖寫成程式碼（here-string 不是 heredoc），不是因為它在擋東西。
    # R26 說它是 off-by-one 的那個版本是 `db0c0f2` 的舊結構，本輪重寫後不再成立。
    ("lint: `<<<` 是 here-string 不是 heredoc（依構造等價，保留為意圖宣告）",
     '            if line.startswith("<<<", i):', "            if False:", "lint"),
    ("lint: `$((` 深度內不判 heredoc（R26 M3）",
     '            if arith or brk or cond:', '            if brk or cond:', "lint"),
    ("lint: `<<-` 剝 tab（R26 M3）",
     '                if line[j:j + 1] == "-":            # 切片越界回空字串，不另寫 `j < n` 守衛', "                if False:", "lint"),
    ("lint: 單引號狀態分支（R26 logic MEDIUM-6：整段刪掉 selftest 仍綠）",
     '            if quote == "\'":', "            if False:", "lint"),
    ("lint: 續行摺疊（R26 M5：`cat <\\` ⏎ `<EOF`）",
     "                if li + spans < len(lines):", "                if False:", "lint"),
    ("lint: block scalar 共同縮排先剝除（R26 M2）",
     "        scan_in = fold_block(dedent_block(run_lines, explicit_pad), block_folded)",
     "        scan_in = fold_block(run_lines, block_folded)", "lint"),
    ("lint: YAML 引號純量先解碼（R26 M4：未實作的逃脫不得猜）",
     "            decoded = yaml_decode_scalar(inline[:len(inline) - len(yaml_cmt)] if yaml_cmt else inline)",
     "            decoded = inline[:len(inline) - len(yaml_cmt)] if yaml_cmt else inline", "lint"),
    ("lint: jobs 子樹的 flow 值 fail-closed（R26 M1(b)）",
     '        if (":" in code_val and top_key == "jobs") or not balanced:',
     "        if False:", "lint"),
    # ── R30 H-1…H-6／MB-1…MB-12（G-R31-1）：本輪每個新機制一個靶 ──
    # 每一條的括號裡寫「關掉它，哪個 fixture 翻色」——答不出來的不該進來。
    ("lint: heredoc 分隔字做整詞 quote removal（R30 H-1 → bypass-heredoc-delim-quote-infix/-suffix/-empty-quotes/-split）",
     '                    if c in ("\'", \'"\'):\n                        saw_word = True',
     "                    if False:\n                        saw_word = True", "lint"),
    ("lint: `$\'…\'` 的 `\\\'` 是逃脫不是收尾（R30 H-2 → 由產生語料的 ansic 維度守）",
     '            if line.startswith("$\'", i):', "            if False:", "lint"),
    ("lint: `${…}` 整段消費（R30 H-3 → bypass-param-expansion-hash）",
     '\n            if line.startswith("${", i):\n                # **只有巢狀的', '\n            if False:\n                # **只有巢狀的', "lint"),
    ("lint: 反引號是詞界（R30 H-4 → bypass-backtick-hash）",
     'SHELL_WORD_BREAK = " \\t;&|()<>`"', 'SHELL_WORD_BREAK = " \\t;&|()<>"', "lint"),
    ("lint: 折疊 block scalar 先折再掃（R30 H-5 → bypass-folded-scalar-comment）",
     "        scan_in = fold_block(dedent_block(run_lines, explicit_pad), block_folded)",
     "        scan_in = dedent_block(run_lines, explicit_pad)", "lint"),
    ("lint: 管線左邊必須有東西（R30 H-6 → bypass-leading-pipe-literal）",
     'PIPED_RE = re.compile(r"[^|\\s]\\s*\\|(?!\\|)&?\\s*python3\\s+\\S*neutralise\\.py(\\s|$)")',
     'PIPED_RE = re.compile(r"(?<!\\|)\\|(?!\\|)&?\\s*python3\\s+\\S*neutralise\\.py(\\s|$)")', "lint"),
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
    ("lint: root_indent 由解析器認定的 key 行決定（R30 MB-7 → bypass-shallow-continuation-root-indent）",
     "    root_indent = min((ind for _i, ind, _k in key_lines), default=0)",
     "    root_indent = min((len(m.group(1)) for i in range(len(raw)) for m in [KEY_RE.match(norm[i])] if m), default=0)",
     "lint"),
    ("lint: tag 也 fail-closed（R30 MB-8 → bypass-tag-flow-mapping）",
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
    ("lint: `((` 進算術深度（R28 D4：`$((` 也走這裡 → good-arith-command-shift-then-pipe）",
     '            if line.startswith("((", i):', "            if False:", "lint"),
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
    ("lint: 雙引號裡的 `${…}` 走配對剖析（R34 logic F1 p3 → bypass-param-expansion-inside-double-quotes）",
     '                if line.startswith("${", i):\n                    e = _param_end(line, i)\n                    if e is None:\n                        unparsed = "`${…}` 裡有本 lint 不解析的構造（命令替換／舊式算術），或同一行沒收尾"\n                        break\n                    code.append(" " * (e - i)); i = e; prev_sig = "x"; continue\n                if ch == "`"', '                if ch == "`"', "lint"),
    ("lint: 雙引號裡的命令替換開 heredoc fail-closed（R35 → bypass-heredoc-in-dq-cmdsubst）",
     '                if dq_sub and line.startswith("<<", i)', '                if False and line.startswith("<<", i)', "lint"),
    ("lint: `$'…'` 跨行 fail-closed（R34 logic F3 r2 → bypass-ansic-quote-multiline）",
     '                if j >= n:\n                    # 跨行的 ANSI-C 字串', '                if False:\n                    # 跨行的 ANSI-C 字串', "lint"),
    ("lint: 命令替換裡的 heredoc 遇「以終止字開頭」的行 fail-closed（R34 logic F3 r1 → bypass-heredoc-in-cmdsubst-prefix-terminator）",
     '            elif in_sub and delim and probe.startswith(delim)', '            elif False', "lint"),
    ("lint: 反引號深度（R35 → bypass-heredoc-in-backticks-prefix-terminator）",
     '                bt = not bt\n', '                pass\n', "lint"),
    ("lint: 命令替換深度（R35 → bypass-heredoc-in-cmdsubst-prefix-terminator）",
     '                csub += 1; code.append("$(")', '                csub += 0; code.append("$(")', "lint"),
    ("lint: 算術深度跨行保留（R34 logic F3 t2／DA t2prime → bypass-arith-multiline-shift）",
     '        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, dq_sub)\n', '        arith = 0\n        lex0 = (arith, arith_par, brk, csub, cpar, cond, bt, dq_sub)\n', "lint"),
    ("lint: 算術／條件式裡的內容不是 code（R34 DA n5、n5b → bypass-pipe-inside-arith、-cond-regex）",
     '                code.append(" "); i += 1; prev_sig = "x"; continue\n            if ch in ("\'", \'"\'):\n                quote = ch; code.append(ch)', '                code.append(ch); i += 1; prev_sig = "x"; continue\n            if ch in ("\'", \'"\'):\n                quote = ch; code.append(ch)', "lint"),
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
    ("lint: step 的 shell 不是字面 bash ⇒ PARSE（R34 security S-3 → bypass-shell-python、-sh、-bash-xtrace-template）",
     '        if STRICT and eff_shell is not None and (not is_bash or XTRACE_OPT_RE.search(eff_shell)):', '        if False:', "lint"),
    ("lint: shell 從 workflow defaults 繼承（R34 security S-3 → bypass-shell-python-from-defaults）",
     '            or (job["shell"] if job else None) or wf_shell', '            or (job["shell"] if job else None)', "lint"),
    ("lint: shell 從 job defaults 繼承（R35 → good-shell-bash-explicit、good-strict-pipefail-forms）",
     '            or (job["shell"] if job else None) or wf_shell', '            or wf_shell', "lint"),
    ("lint: container／Windows runner 沒寫 shell ⇒ PARSE（R34 DA n4／n4b → bypass-shell-container-default、-windows-default）",
     '        if STRICT and eff_shell is None and job and (job["container"] or job["windows"]):', '        if False:', "lint"),
    ("lint: 靠管線過濾的 step 不得轉到 stderr 或開 xtrace（R34 security S-2／DA G-B → bypass-stderr-redirect-*、bypass-xtrace-set-x）",
     '        elif not declared and any(FD_RE.search(l) for l in logical):', '        elif False:', "lint"),
    ("lint: --strict：靠管線過濾的 step 整個區塊是一個群組（#59／#60 → bypass-strict-group-other-command-stdout）",
     '        elif not declared and group_why:', '        elif False:', "lint"),
    ("lint: --strict：群組外（前綴、`{` 之前、`}` 之後）必須是字面（#59／#60 → bypass-strict-group-expansion-before-opener）",
     '    if not all(raw[i][a:b] == code[i][a:b] for i, a, b in spans):', '    if False:', "lint"),
    ("lint: --strict：群組形式的 pipefail 必須在 set 前綴裡（#59／#60 → bypass-strict-pipefail-inside-group）",
     '                window = group_prefix', '                window = logical', "lint"),
    ("lint: --strict：有管線的 step 要在 pipefail 之下（R34 security S-1 → bypass-strict-pipe-without-pipefail）",
     '        if STRICT and not is_bash:', '        if False:', "lint"),
    ("lint: --strict：認得 run 裡的 set -o pipefail（R35 → good-strict-pipefail-forms）",
     'PIPEFAIL_RE = re.compile(r"\\bset\\b[^;&|]*-[A-Za-z]*o\\s+pipefail\\b")', 'PIPEFAIL_RE = re.compile(r"(?!)")', "lint"),
    ("lint: 引號開到 run 區塊結尾 ⇒ fail-closed（R35 E 組語料 → bypass-quote-open-at-block-end）",
     "    if quote is not None:              # `and not unparsed` 只決定訊息寫哪個原因、判定都是 PARSE（opsweep 報存活，刪掉）\n", "    if False:\n", "lint"),
    ("lint: `${…}` 雙引號內的反斜線是逃脫（R34 requirements F2 → bypass-param-expansion-dq-escaped-quote）",
     '                if line[k] == "\\\\":\n                    k += 2; continue\n                if line.startswith("$(", k) or line[k] == "`":', '                if line.startswith("$(", k) or line[k] == "`":', "lint"),
    ("lint: 解碼後的引號純量按換行切行（R35 → bypass-quoted-scalar-newline-comment）",
     '        run_lines = inline.split("\\n") + [raw[k] for k in range(r + 1, s["end"] + 1)', '        run_lines = [inline] + [raw[k] for k in range(r + 1, s["end"] + 1)', "lint"),
    ("lint: 切出來的行不 dedent（R35 → bypass-quoted-scalar-indented-lines-no-dedent）",
     '            if "\\n" in inline:\n                explicit_pad = 0', '            if False:\n                explicit_pad = 0', "lint"),
]

EXPECTED_SURVIVE = {
    "lint: `<<<` 是 here-string 不是 heredoc（依構造等價，保留為意圖宣告）",
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
