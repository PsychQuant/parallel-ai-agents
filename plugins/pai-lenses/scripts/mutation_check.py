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

    python3 scripts/mutation_check.py

**手動跑，不進 CI**（36 個 mutation × 全套測試 ≈ 5–8 分鐘；比照 `ensemble-eval` 的定位）。
改動 `validate.py` 的閘門、或新增閘門之後跑一次；存活清單就是待補的測試。

## 兩個誠實邊界

1. **存活 ≠ 一定缺測試。** 有些是 *equivalent mutant*：關掉某道檢查後行為沒變（下游另一道
   守住了）。例如把 `if not cat.is_file()` 關掉，`cat.open()` 仍會拋 `OSError` 被同一個
   `except` 接住並報同一類錯 —— 那是縱深防禦，不是缺口。判讀存活清單要逐條看。
2. **這支只 mutate `if` 條件。** 它不動運算式、邊界值、訊息內容，所以「零存活」**不等於**
   測試完備。它回答的是一個窄而具體的問題：**每一道閘門被整段拿掉時，有沒有東西會叫。**

## 一個踩過的坑

R7 有一個 mutation 一直沒轉紅，差點被判定成「那條測試是套套邏輯」。追下去發現是
**mutation 打偏了** —— `str.replace(old, new, 1)` 命中的是註解裡的同一個字串，不是程式碼。
所以下面每個靶都要求**在檔案中恰好出現一次**，不唯一就直接報錯而不是默默替換第一個。
mutation test 本身也需要被驗證有沒有真的打中。
"""
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
    ("prerelease 排序", '    return core + ((0, pre) if pre else (1, ""))', "    return core"),
    ("未 commit warning", "    if dirty.returncode == 0 and dirty.stdout.strip():",
     "    if False:"),
    ("pack 改名偵測", "        moved = _find_pack_at(repo, cmp_base, pack_name)",
     "        moved = None"),
    ("bump 比較（tn <= tp）", "    elif tn <= tp:", "    elif False:"),
    ("未知旗標 fail-loud", "    if unknown:\n        print(\"用法：validate.py",
     "    if False:\n        print(\"用法：validate.py"),
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


def main():
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
