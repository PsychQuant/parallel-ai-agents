#!/usr/bin/env python3
"""驗證這個 lens pack 可被 parallel-ai-agents 正確消費。

兩件事，都對應一個**安靜**的失敗模式：

1. `plugin.json` 必須有 semver `version`。缺了的話 Claude Code 的 cache 目錄名會退回
   git commit SHA（或 `unknown`），兩者都不是 semver，consumer 的 semver glob 定位不到 ——
   pack 看起來裝好了卻什麼都不貢獻。

2. 每個 `lenses/*.csv` 必須解析出至少一條 lens。header 打錯（`keys` 而非 `key`）時
   `csv.DictReader` 不會報錯，只會讓每一列都被跳過；檔案看起來好好的，lens 卻全部消失。

用 stdlib `csv` —— 與 consumer 的 `pai-parse-lens-csv` 同一個模組、同一套 quoting 規則。

退出碼：0 全部通過；1 有錯。
"""
import csv
import json
import pathlib
import re
import subprocess
import sys

SEMVER = re.compile(r"^\d+\.\d+\.\d+")
TRUTHY = ("1", "true", "yes")
FALSY = ("", "0", "false", "no")


def check_version(root, errs):
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version", "")
    except (OSError, json.JSONDecodeError) as e:
        errs.append(f"::error file={manifest}::讀不到或不是合法 JSON：{e}")
        return
    print(f"version = {version or '<missing>'}")
    if not SEMVER.match(str(version)):
        errs.append(
            f"::error file={manifest}::需要 semver version —— 缺了的話 cache 目錄名會退回 "
            "commit SHA 或 unknown，consumer 的 semver glob 定位不到這個 pack"
        )


def check_csvs(root, errs):
    files = sorted((root / "lenses").glob("*.csv"))
    if not files:
        errs.append("::error::找不到任何 lenses/*.csv —— 空的 pack 不貢獻任何東西")
        return
    for path in files:
        rel = path.relative_to(root)
        try:
            with path.open(newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            errs.append(f"::error file={rel}::讀取/解析失敗：{e}")
            continue
        if not rows or "key" not in rows[0] or "focus" not in rows[0]:
            errs.append(f"::error file={rel}::header 必須含 key 與 focus")
            continue
        lenses = [r for r in rows
                  if (r.get("key") or "").strip() and (r.get("focus") or "").strip()]
        if not lenses:
            errs.append(
                f"::error file={rel}::解析出 0 條 lens —— 存在卻不貢獻任何東西的檔案比沒有更糟"
                "（consumer 會警告，而審閱者會安靜地少一個 lens）"
            )
            continue
        # #33 verify H14：CSV 沒有註解語法，而 builtin-lenses.csv（本 pack README 叫人拿它
        # 當範本）第二列**就是**一行 `# 唯讀 catalog…` 的說明。那一列在 catalog 裡是安全的
        # （key/focus 欄為空 → parser 跳過），但複製過來當範本時若把它放進 key 欄、又剛好
        # 帶了逗號，就會被解析成一條「focus 是說明文字」的真 lens —— 而且舊版 CI 會蓋章通過。
        for r in lenses:
            if (r.get("key") or "").lstrip().startswith("#"):
                errs.append(
                    f"::error file={rel}::key 以 '#' 開頭（'{r['key'][:40]}'）—— CSV 沒有註解語法。"
                    "這幾乎一定是從 builtin-lenses.csv 複製範本時把說明列一起帶進來了；"
                    "它會變成一條真的 lens 送進 reviewer prompt。請刪掉該列"
                )
        print(f"{rel}: {len(lenses)} 條 lens ✓")
        for r in lenses:
            for col in ("override", "needsSrt"):
                raw = (r.get(col) or "").strip().lower()
                if raw and raw not in TRUTHY + FALSY:
                    print(f"::warning file={rel}::{col}='{r[col]}' 不是可辨識的真假值"
                          f"（1/true/yes vs 空/0/false/no）—— 會被當成 false")


def repo_root(root):
    """併回主 repo 後，root 的祖父目錄就是 monorepo root（plugins/pai-lenses → repo）。
    獨立使用（pack 不在 monorepo 內）時回 None，相關檢查自動略過 —— 這支要能單獨跑。"""
    cand = root.parent.parent
    return cand if (cand / ".claude-plugin" / "marketplace.json").is_file() else None


def check_marketplace_sync(root, errs):
    """plugin.json 的 version 必須與 marketplace.json 的 pai-lenses entry 一致。

    #33 verify H5/H9/H15：貢獻者只 bump 一處時，PR merge 後使用者 `/plugin update`
    收不到新版 —— 而且沒有任何錯誤訊息。這是本 pack 最後一哩的靜默失敗，靠散文守不住。"""
    repo = repo_root(root)
    if repo is None:
        print("note: 不在 monorepo 內 —— 略過 marketplace 版本一致檢查")
        return
    mp = repo / ".claude-plugin" / "marketplace.json"
    try:
        pj_ver = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version")
        entries = [p for p in json.loads(mp.read_text(encoding="utf-8")).get("plugins", [])
                   if p.get("name") == "pai-lenses"]
    except (OSError, json.JSONDecodeError) as e:
        errs.append(f"::error file={mp}::讀取失敗：{e}")
        return
    if not entries:
        errs.append(f"::error file={mp}::找不到 pai-lenses entry —— 這個 pack 不會被散發")
        return
    mp_ver = entries[0].get("version")
    if mp_ver != pj_ver:
        errs.append(
            f"::error file={mp}::version 不同步 —— plugin.json={pj_ver} 但 marketplace.json={mp_ver}。"
            "兩者不一致時使用者 /plugin update 收不到新版，且不會有任何錯誤訊息"
        )
    else:
        print(f"marketplace 版本一致：{pj_ver} ✓")


def check_profiles(root, errs):
    """每個 lenses/<profile>.csv 的檔名必須是 harness PROFILES 裡真的存在的 profile。

    #33 verify H8：這是本設計的核心不變式，先前只寫在散文裡。檔名打錯或想用 pack
    偷渡新 profile 時，harness 會回 unknown ensemble profile、0 個 agent 被派出，
    而 workflow 仍「成功」結束 —— 正是這個 repo 反覆在防的那種安靜失敗。

    profile 清單查真源（bin/pai-list-profiles），不查 builtin-lenses.csv ——
    後者由 lens 產生，lenses: [] 的 profile（如 custom）在裡面一列都沒有（H7）。"""
    repo = repo_root(root)
    if repo is None:
        print("note: 不在 monorepo 內 —— 略過 profile 名稱檢查")
        return
    lister = repo / "plugins" / "parallel-ai-agents" / "bin" / "pai-list-profiles"
    if not lister.is_file():
        print(f"note: 找不到 {lister} —— 略過 profile 名稱檢查")
        return
    proc = subprocess.run(["bash", str(lister)], capture_output=True, text=True)
    if proc.returncode != 0:
        errs.append(f"::error::無法取得 PROFILES 清單：{proc.stderr.strip()}")
        return
    known = {p.strip() for p in proc.stdout.split() if p.strip()}
    for path in sorted((root / "lenses").glob("*.csv")):
        if path.stem not in known:
            errs.append(
                f"::error file={path.relative_to(root)}::'{path.stem}' 不是既有 profile"
                f"（真源 PROFILES 有：{', '.join(sorted(known))}）。"
                "pack 只能為既有 profile 加 lens —— CSV 描述不了 profile 級的 "
                "title/daFocus/codexDefault，新 profile 必須改 PROFILES（層 ①）"
            )
        else:
            print(f"{path.relative_to(root)}: profile '{path.stem}' 存在於 PROFILES ✓")


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    errs = []
    check_version(root, errs)
    check_marketplace_sync(root, errs)
    check_profiles(root, errs)
    check_csvs(root, errs)
    for e in errs:
        print(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
