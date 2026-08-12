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

**手動跑，不進 CI**（一輪 = 靶數 × 全套測試，目前約 10 分鐘；比照 `ensemble-eval` 的定位）。
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
    ("containment（只判目錄層）",
     "        outside = [p for p in (resolved, pj) if not _inside(p, repo_abs)]",
     "        outside = [p for p in (resolved,) if not _inside(p, repo_abs)]"),
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
    ("entry name 重複", "            if ent_name in entry_names:", "            if False:"),
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
    ("lenses/ 目錄本身的 containment", "        if not _inside(d.resolve(), repo_abs):",
     "        if False:"),
    ("catalog 的 containment", "    if not _inside(cat.resolve(), repo.resolve()):",
     "    if False:"),
    ("check_bumped 的 now 型別守衛", "    if now_obj is None:", "    if False and now_obj is None:"),
    ("check_bumped 的 prev 型別守衛", "    if prev_obj is None:",
     "    if False and prev_obj is None:"),
    ("純改名不算 lens 變更", '        if parts[0] == "R100":', "        if False:"),
    ("反向檢查的 name 交叉比對", "            if culprit is not None:", "            if False:"),
    ("workflow-command 消毒（值層）", '    t = t.replace("::", "∷")', "    t = t"),
    ("workflow-command 消毒（輸出邊界）",
     '    t = str(line).replace("\\r\\n", "⏎").replace("\\n", "⏎").replace("\\r", "⏎")',
     "    t = str(line)"),
]


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

    完整的 mutation 量測太慢（靶數 × 全套測試 ≈ 十分鐘），不適合每個 PR 跑。但**靶清單
    相對 validate.py 的漂移**是可以便宜擋住的：有人改動被 mutate 的那幾行、或搬走一道閘門，
    靶就對不上。先前這件事只有在有人手動跑整輪時才會發現，而「忘了跑」是預設。
    """
    src = VALIDATE.read_text(encoding="utf-8")
    broken = []
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
    # 打錯旗標（`--check-target`）會被靜默忽略，然後**直接跑十分鐘的就地改寫迴圈**。
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
    pre = subprocess.run([sys.executable, str(TESTS)], cwd=PACK, capture_output=True, text=True)
    if pre.returncode != 0:
        print("✗ 基準測試就沒過 —— 先把測試修綠再量 mutation，"
              "否則每個 mutation 都會被誤判為『殺掉』。\n" + pre.stdout[-2000:] + pre.stderr[-2000:])
        return 1

    original = VALIDATE.read_text(encoding="utf-8")
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

    print(f"\n殺掉 {len(killed)} / 存活 {len(survived)} / 靶壞 {len(broken)}")
    if survived:
        print("\n存活（可能缺測試，也可能是 equivalent mutant —— 逐條判讀）：")
        for n in survived:
            print("  -", n)
    if broken:
        print("\n靶壞（mutation 定義與現行程式碼對不上，先修這裡）：")
        for n, why in broken:
            print(f"  - {n} | {why}")
    # 靶壞是這支自己的缺陷，必須 fail-loud；存活留給人判讀，不當成失敗。
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
