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
        print(f"{rel}: {len(lenses)} 條 lens ✓")
        for r in lenses:
            for col in ("override", "needsSrt"):
                raw = (r.get(col) or "").strip().lower()
                if raw and raw not in TRUTHY + FALSY:
                    print(f"::warning file={rel}::{col}='{r[col]}' 不是可辨識的真假值"
                          f"（1/true/yes vs 空/0/false/no）—— 會被當成 false")


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    errs = []
    check_version(root, errs)
    check_csvs(root, errs)
    for e in errs:
        print(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
