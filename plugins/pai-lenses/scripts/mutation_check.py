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

**手動跑，不進 CI**（一輪 = 靶數 × 全套測試，每套測試 20–35 s × 靶數，目前約 30–60 分鐘；比照 `ensemble-eval` 的定位）。
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
    ("source 形狀守衛（非字串非物件）", "        elif src is not None:", "        elif False:"),
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
    ("分隔符表：\\x1c", '"\\x1c", ', ""),
    ("分隔符表：\\x1d", '"\\x1d", ', ""),
    ("分隔符表：\\x1e", '"\\x1e", ', ""),
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
    ("entry name 進 annotation 經 wc()（R17 logic L-3/L-4：taint 網涵蓋 manifest 來源）",
     "f\"::error file={prop(mp)}::{wc(entry.get('name'))} 的 source {wc(repr(src))} \"",
     "f\"::error file={prop(mp)}::{entry.get('name')} 的 source {wc(repr(src))} \""),
    ("CSV 欄名進 annotation 經 wc()（R17 L-4）",
     "（現在是 {wc(fields)}）", "（現在是 {fields}）"),
    ("profile 清單經 wc() 進 annotation（R15 S-2）",
     "f\"（真源 PROFILES 有：{wc(', '.join(sorted(known_profiles)))}）。\"",
     "f\"（真源 PROFILES 有：{', '.join(sorted(known_profiles))}）。\""),
]
# neutralise.py 不在 mutation 範圍（本 harness 只 mutate validate.py）；它的行為由 test_validate.py 的
# 兩條 CI 中和測試釘住，且它本身只是把 stdin 接到 LineSanitiser——LineSanitiser 的靶在上面。

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
        raise ValueError(f"靶在 validate.py 中出現 {n} 次（需恰好 1 次）")
    return src.replace(old, new)


def check_targets_only():
    """只驗每個靶是否恰好命中一次 —— 秒級，可以進 CI（#33 verify R9 M11/M24）。

    完整的 mutation 量測太慢（靶數 × 全套測試 ≈ 30–60 分鐘），不適合每個 PR 跑。但**靶清單
    相對 validate.py 的漂移**是可以便宜擋住的：有人改動被 mutate 的那幾行、或搬走一道閘門，
    靶就對不上。先前這件事只有在有人手動跑整輪時才會發現，而「忘了跑」是預設。
    """
    src = VALIDATE.read_text(encoding="utf-8")
    broken = []
    # R13（regression R13-6）：EXPECTED_SURVIVE 只是名字集合 —— 靶被改名或刪掉後，這裡的名字會靜默
    # 失效（那個靶重新變成「要人判讀的存活」，或更糟：一個不存在的名字永遠「預期存活」）。
    names = {n for n, _o, _n in MUTATIONS}
    for n in sorted(EXPECTED_SURVIVE - names):
        broken.append((n, "列在 EXPECTED_SURVIVE 但 MUTATIONS 裡沒有這個靶"))
    for name, old, _new in MUTATIONS:
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
        n = src.count(old)
        if n != 1:
            broken.append((name, f"在 validate.py 中出現 {n} 次（需恰好 1 次）"))
    if broken:
        print(f"::error::mutation 靶清單與 validate.py 漂移了（{len(broken)} 個對不上）—— "
              "改動閘門時請一併更新 scripts/mutation_check.py 的 MUTATIONS")
        for n, why in broken:
            print(f"  - {n} | {why}")
        return 1
    print(f"mutation 靶清單 {len(MUTATIONS)} 個全部恰好命中一次 ✓"
          "（這只驗靶解析得到，不代表測試抓得到 —— 那要跑完整輪）")
    return 0


def main():
    # #33 verify R10 M6：先前是 `if "--check-targets" in sys.argv[1:]` —— 手寫解析，
    # 打錯旗標（`--check-target`）會被靜默忽略，然後**直接跑 30–60 分鐘的就地改寫迴圈**。
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
    print("前置：確認未 mutate 的測試套件是綠的 …", flush=True)
    t0 = time.monotonic()
    pre = subprocess.run([sys.executable, str(TESTS)], cwd=PACK, capture_output=True, text=True)
    if pre.returncode != 0:
        print("✗ 基準測試就沒過 —— 先把測試修綠再量 mutation，"
              "否則每個 mutation 都會被誤判為『殺掉』。\n" + pre.stdout[-2000:] + pre.stderr[-2000:])
        return 1

    original = VALIDATE.read_text(encoding="utf-8")
    install_restore_signals()
    survived, killed, broken = [], [], []
    try:
        for name, old, new in MUTATIONS:
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
            VALIDATE.write_text(mutated, encoding="utf-8")
            rc = subprocess.run([sys.executable, str(TESTS)], cwd=PACK,
                                capture_output=True, text=True).returncode
            (survived if rc == 0 else killed).append(name)
            print(("  存活 " if rc == 0 else "  殺掉 ") + name, flush=True)
    except BaseException:
        # #33 verify R9 M16：只有 finally 保護時，SIGINT/SIGTERM 或當機會把 `if False:`
        # 留在正式的 validate.py 裡 —— 一個被 mutate 過的 validator 看起來完全正常。
        # 這裡明確印出還原提示，讓「檔案現在可能是壞的」不會靜默。
        VALIDATE.write_text(original, encoding="utf-8")
        print("\n⚠ 中斷 —— 已把 validate.py 還原。若程序被強制砍掉未跑到這裡，"
              "請執行 `git checkout -- scripts/validate.py` 確認。", flush=True)
        raise
    finally:
        VALIDATE.write_text(original, encoding="utf-8")

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
