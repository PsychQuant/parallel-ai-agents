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
# 有專屬 review skill 硬接 pai-collect-lens-layers 的 profile。其餘 profile 的 pack CSV
# 仍然合法（ensemble-compose --base <profile> 會載入），但不會出現在任何專屬審閱裡 ——
# 貢獻者值得被告知這件事（#33 verify R3 H30）。
WIRED_PROFILES = {"code", "academic", "lecture"}
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
        # #33 verify R2 H14：先前的「key 以 # 開頭」偵測對真正的 catalog 註解列**不可能觸發**
        # —— 那一列在 catalog 裡的第一欄是 profile，複製過來時整份 header 也一起帶了。
        # 真正的複製危害是**欄位錯位**：catalog 是 profile,key,focus,needsSrt，pack 是
        # key,focus,needsSrt,override。整份複製後 key 欄拿到 profile 名、focus 欄拿到 key。
        # 這個失敗是機械可測的：header 開頭就不一樣。
        if rows and "profile" in rows[0] and "key" in rows[0] and "focus" in rows[0]:
            errs.append(
                f"::error file={rel}::header 含 `profile` 欄 —— 這是 builtin-lenses.csv 的格式"
                "（profile,key,focus,needsSrt），不是 pack 的格式（key,focus,needsSrt,override）。"
                "整份複製 catalog 會讓 key 欄拿到 profile 名、focus 欄拿到 key，"
                "而每一列看起來都還是合法的 lens。請只複製你要的那幾列並改成 pack 的欄位順序"
            )
            continue
        if not rows or "key" not in rows[0] or "focus" not in rows[0]:
            errs.append(f"::error file={rel}::header 必須含 key 與 focus")
            continue
        # #33 verify R3 H9：未知 header 欄是錯不是警告。`overide`（少一個 r）這種 typo
        # 會讓整欄被 csv 模組當成不認識的欄位而丟掉 —— lens 照常出貨、override 靜默失效，
        # 而 CI 全綠。這正是本 validator 存在的理由那一類失敗。
        KNOWN = {"key", "focus", "needsSrt", "override"}
        unknown = [c for c in (rows[0].keys() if rows else []) if c and c not in KNOWN]
        if unknown:
            errs.append(
                f"::error file={rel}::header 有不認識的欄位 {unknown}（合法欄位：{sorted(KNOWN)}）。"
                "拼錯的欄位會被靜默忽略 —— 例如 'overide' 會讓該列的 override 完全失效而不報錯"
            )
            continue

        # #33 verify R3 H9：缺 key 或 focus 的列先前只是被濾掉，只要同檔另有一列有效就整體通過。
        # 但那一列是**貢獻者想送的東西**，被吃掉了卻沒人知道。
        bad = [i for i, r in enumerate(rows, start=2)
               if not ((r.get("key") or "").strip() and (r.get("focus") or "").strip())]
        if bad:
            errs.append(
                f"::error file={rel}::第 {bad} 列缺 key 或 focus —— 這些列會被解析器整列丟棄。"
                "若是刻意留空請刪掉該列；若是資料，補齊欄位"
            )
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
    """**每一個**相對路徑 plugin 的 plugin.json version 必須與 marketplace.json entry 一致。

    #33 verify R1 H5/H9/H15：只 bump 一處時使用者 `/plugin update` 收不到新版，且無錯誤訊息。
    #33 verify R2 H6：先前只檢查 `pai-lenses` 一個 entry，但 SKILL.md 的層 ① 路徑也指示要
    bump `parallel-ai-agents` —— 那條路徑上沒有任何閘門。改為逐一檢查所有 `./plugins/...`
    來源的 plugin，新增第三個 plugin 時自動涵蓋。"""
    repo = repo_root(root)
    if repo is None:
        print("note: 不在 monorepo 內 —— 略過 marketplace 版本一致檢查")
        return
    mp = repo / ".claude-plugin" / "marketplace.json"
    try:
        plugins = json.loads(mp.read_text(encoding="utf-8")).get("plugins", [])
    except (OSError, json.JSONDecodeError) as e:
        errs.append(f"::error file={mp}::讀取失敗：{e}")
        return
    seen = 0
    for entry in plugins:
        src = entry.get("source")
        if not isinstance(src, str) or not src.startswith("./"):
            continue                                  # 非相對路徑來源不在本 repo 內，無從比對
        pj = repo / src[2:] / ".claude-plugin" / "plugin.json"
        if not pj.is_file():
            errs.append(f"::error file={mp}::{entry.get('name')} 的 source 指向 {src}，但該處沒有 plugin.json")
            continue
        try:
            pj_ver = json.loads(pj.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError) as e:
            errs.append(f"::error file={pj}::讀取失敗：{e}")
            continue
        seen += 1
        if entry.get("version") != pj_ver:
            errs.append(
                f"::error file={mp}::{entry.get('name')} version 不同步 —— "
                f"plugin.json={pj_ver} 但 marketplace.json={entry.get('version')}。"
                "兩者不一致時使用者 /plugin update 收不到新版，且不會有任何錯誤訊息"
            )
        else:
            print(f"marketplace 版本一致：{entry.get('name')} {pj_ver} ✓")
    if seen == 0:
        errs.append(f"::error file={mp}::沒有任何相對路徑 plugin 被檢查 —— 這個檢查形同虛設")


def check_bumped(root, errs, base):
    """改了 `lenses/*.csv` 就**必須** bump 版本（相對 base ref 增加），不只是「兩處一致」。

    #33 verify R2 H5/H10：equality 守得住「同步」，守不住「有 bump」。改了 lens 而兩處
    都停在同一版時，其餘檢查全過、CI 全綠、使用者收不到新 lens、無任何錯誤訊息 ——
    而 pack README 白紙黑字寫「每次改 lens 都要 bump…CI 會擋」。那句話先前是空頭支票。

    需要 base ref 才能判斷「有沒有改」，所以 CI 要傳 `--base origin/<default>`；
    本機不傳時明確印出略過（不假裝檢查過）。"""
    if not base:
        print("note: 未給 --base —— 略過「改了 lens 必須 bump」檢查（CI 會帶 base）")
        return
    repo = repo_root(root)
    if repo is None:
        print("note: 不在 monorepo 內 —— 略過 bump 檢查")
        return
    rel = "plugins/pai-lenses/lenses"
    changed = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD", "--", rel],
                             cwd=repo, capture_output=True, text=True)
    if changed.returncode != 0:
        # #33 verify R3 H8：先前這裡只印 note 就成功返回 —— fail-open。
        # 「git 跑不起來」與「沒東西要檢查」是兩回事：前者代表這道閘門**根本沒跑**，
        # 而 CI 仍然全綠。最常見的原因是 shallow clone 沒有 base（已加 fetch-depth: 0），
        # 但無論原因為何，靜默放行等於讓閘門在最需要它的時候消失。
        errs.append(
            f"::error::bump 檢查無法執行（base={base}）：{changed.stderr.strip()}。"
            "這不是「無需 bump」—— 是這道閘門沒有跑。"
            "CI 請確認 checkout 有 fetch-depth: 0 且 base SHA 在本地歷史內"
        )
        return
    if not changed.stdout.strip():
        print("lenses/ 相對 base 無變更 —— 無需 bump ✓")
        return
    pj = root / ".claude-plugin" / "plugin.json"
    now = json.loads(pj.read_text(encoding="utf-8")).get("version", "")
    old = subprocess.run(["git", "show", f"{base}:plugins/pai-lenses/.claude-plugin/plugin.json"],
                         cwd=repo, capture_output=True, text=True)
    prev = json.loads(old.stdout).get("version", "") if old.returncode == 0 else None
    if prev is None:
        # base 沒有這個 plugin.json = 這個 PR 本身在新增整個 pack。此時沒有「前一版」
        # 可比，跳過是對的 —— 但必須說出口。#33 verify R3 H8 指出：引入這道閘門的
        # 那個 PR 正好落在這個分支，所以閘門在它自己身上結構性不可達。
        print(f"note: base（{base}）沒有 plugins/pai-lenses/.claude-plugin/plugin.json —— "
              "本 PR 在新增整個 pack，無前一版可比，bump 檢查略過。"
              "（這是唯一合法的略過情境；下一個改 lens 的 PR 就會被實際檢查。）")
        return
    def tup(v):
        try:
            return tuple(int(x) for x in str(v).split(".")[:3])
        except ValueError:
            return ()
    if tup(now) <= tup(prev):
        errs.append(
            f"::error file={pj}::lenses/ 改了（{', '.join(changed.stdout.split())}）"
            f"但版本沒有增加（base={prev} → 現在={now}）。"
            "版本沒變時使用者 /plugin update 收不到這些 lens，而且不會有任何錯誤訊息"
        )
    else:
        print(f"lenses/ 有變更且已 bump：{prev} → {now} ✓")


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
            # #33 verify R3 H30：profile 存在於 PROFILES ≠ 有 skill 會載入這一層。
            # 只有 code / academic / lecture 有專屬 review skill 硬接 pai-collect-lens-layers；
            # 其餘（minutes / general / custom）唯一的載入路徑是 ensemble-compose --base <profile>。
            # 不是錯（compose 確實會載），但貢獻者需要知道它不會出現在任何專屬審閱裡。
            if path.stem not in WIRED_PROFILES:
                print(f"::warning file={path.relative_to(root)}::profile '{path.stem}' 沒有專屬的 "
                      f"review skill（只有 {', '.join(sorted(WIRED_PROFILES))} 有）。"
                      f"這些 lens 只會在 /ensemble-compose --base {path.stem} 時被載入，"
                      "不會出現在任何專屬審閱中")


def main():
    base = None
    argv = sys.argv[1:]
    if "--base" in argv:
        i = argv.index("--base")
        if i + 1 >= len(argv):
            print("用法：validate.py [--base <ref>]", file=sys.stderr)
            return 2
        base = argv[i + 1]
    root = pathlib.Path(__file__).resolve().parent.parent
    errs = []
    check_version(root, errs)
    check_marketplace_sync(root, errs)
    check_bumped(root, errs, base)
    check_profiles(root, errs)
    check_csvs(root, errs)
    for e in errs:
        print(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
