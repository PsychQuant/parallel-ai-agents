#!/usr/bin/env python3
"""驗證這個 lens pack 可被 parallel-ai-agents 正確消費。

每一項檢查都對應一個**安靜**的失敗模式 —— 東西看起來好好的、CI 全綠，
但使用者端少了一條 lens 或整個 pack 不生效，而且沒有任何錯誤訊息。

用 stdlib `csv` —— 與 consumer 的 `pai-parse-lens-csv` 同一個模組、同一套 quoting 規則。

用法：validate.py [--base <ref>] [--event <github-event-name>]
  --base   用來判斷「改了 lens 卻沒 bump 版本」。CI 傳 PR base 或 push 的 before SHA。
  --event  觸發事件名（`pull_request` / `push` / `workflow_dispatch`）。決定 base 的
           比較語意，以及「拿不到 base」時該報錯還是只留一行紀錄。

退出碼：0 全部通過；1 有錯；2 用法錯。
"""
import csv
import json
import os
import pathlib
import re
import subprocess
import sys

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
TRUTHY = ("1", "true", "yes")
FALSY = ("", "0", "false", "no")
KNOWN_COLS = ("key", "focus", "needsSrt", "override")


def version_tuple(v):
    """semver → 可比較的 tuple。prerelease/build 後綴一律忽略（只比 major.minor.patch）。

    #33 verify R4：先前 check_version 用 `^\\d+\\.\\d+\\.\\d+` 前綴比對放行 `0.3.0-rc1`，
    而 check_bumped 用 `int(x) for x in v.split('.')[:3]` 對同一字串炸掉（'0-rc1' 不是 int）
    → 兩個檢查對同一版本字串的認定不一致。統一走這裡。"""
    m = SEMVER.match(str(v or ""))
    return tuple(int(g) for g in m.groups()) if m else None


def repo_root(root):
    """併回主 repo 後，root 的祖父目錄就是 monorepo root。獨立使用時回 None。"""
    cand = root.parent.parent
    return cand if (cand / ".claude-plugin" / "marketplace.json").is_file() else None


def collector_wiring(repo, profile):
    """回傳 (該 profile 的專屬 skill 目錄名 or None, 那支 skill 看起來有沒有接 collector)。

    **這是啟發式，不是事實判定。** 前一版（#33 verify R4）用 regex 掃全部 SKILL.md
    推導「哪些 profile 已接線」，並在 docstring 宣稱「訊息依構造為真」——
    R5 用六個 case 實測，**兩個方向都被推翻**：

      - regex 只認裸字與雙引號，`pai-collect-lens-layers 'minutes'`（單引號）→ 判成沒接
      - 散文（「之後應該要跑 …，目前尚未接線」）、註解掉的程式碼、甚至
        「**不要**呼叫 pai-collect-lens-layers minutes」這句警語 → 全部判成已接

    也就是說：在 SKILL.md 的**散文**上用 regex 推導事實，做不到「依構造為真」。
    現在改成 (1) 只看該 profile 自己的 skill、(2) 跳過 shell 註解行、(3) 不再解析參數
    （`"$PROFILE"` 這種變數寫法本來就抓不到），並且**訊息降級為附帶但書的提示** ——
    它指出一個值得人工確認的可能缺口，不宣稱事實。真正的接線缺口追蹤於 #40。"""
    if repo is None:
        return None, None
    d = repo / "plugins" / "parallel-ai-agents" / "skills" / f"ensemble-{profile}-review"
    if not (d / "SKILL.md").is_file():
        return None, None
    lines = (d / "SKILL.md").read_text(encoding="utf-8", errors="replace").splitlines()
    wired = any("pai-collect-lens-layers" in ln and not ln.lstrip().startswith("#")
                for ln in lines)
    return d.name, wired


def check_version(root, errs):
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version", "")
    except (OSError, json.JSONDecodeError) as e:
        errs.append(f"::error file={manifest}::讀不到或不是合法 JSON：{e}")
        return
    print(f"version = {version or '<missing>'}")
    if version_tuple(version) is None:
        errs.append(
            f"::error file={manifest}::需要 semver version（現在是 '{version}'）—— 缺了或格式不對時 "
            "cache 目錄名會退回 commit SHA 或 unknown，consumer 的 semver glob 定位不到這個 pack"
        )


def check_marketplace_sync(root, errs):
    """**每一個**在本 repo 內的 plugin，其 plugin.json version 必須與 marketplace entry 一致。"""
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
        # #33 verify R4：先前用字串前綴 './' 當「在本 repo 內」的判準，少寫 './' 的
        # 相對路徑（"plugins/foo"）會被靜默跳過 —— 那正是最該檢查的 entry。
        rel = None
        if isinstance(src, str):
            if src.startswith(("http://", "https://", "git@")):
                continue                       # 明確的遠端來源，本 repo 無從比對
            rel = src[2:] if src.startswith("./") else src
        elif isinstance(src, dict) and src.get("source") in (None, "local", "path"):
            rel = src.get("path")
        if not rel:
            continue                           # github/url/npm 等物件式遠端來源
        # #33 verify R5：先前直接 `repo / rel` 組路徑，完全沒有 containment 檢查。
        # 三條逃逸路徑實測都成立：(1) 絕對路徑 —— pathlib 的 `/` 遇絕對右運算元會**整段
        # 取代**左邊（`Path('/repo') / '/tmp/x'` == `/tmp/x`）；(2) `..` 不做正規化；
        # (3) symlink。後果有兩層：這道被標 CRITICAL 的版本同步閘門，可以被一個指到
        # repo 外（例如 maintainer 本機另一個 checkout）的 source 滿足 —— 同一份 commit
        # 在本機綠、在 CI 紅；而且這支在 `on: pull_request` 下會跑，fork PR 完全控制
        # marketplace.json，等於拿未受信任字串去讀任意 <X>/.claude-plugin/plugin.json。
        # 判定必須是 error 而非 continue —— 靜默跳過正是本 PR 一路在修的病。
        if os.path.isabs(rel) or ".." in pathlib.PurePosixPath(rel).parts:
            errs.append(f"::error file={mp}::{entry.get('name')} 的 source 是 {src!r} —— "
                        "本 repo 內的 plugin 只能用不含 '..' 的相對路徑。"
                        "絕對路徑與 '..' 會讓這道版本閘門去比對 repo 外的檔案")
            continue
        resolved = (repo / rel).resolve()
        try:
            inside = resolved.is_relative_to(repo.resolve())    # Python 3.9+
        except AttributeError:                                  # 3.8 fallback
            inside = str(resolved).startswith(str(repo.resolve()) + os.sep)
        if not inside:
            errs.append(f"::error file={mp}::{entry.get('name')} 的 source {src!r} "
                        f"解析後落在 repo 外（{resolved}）—— 可能是 symlink。"
                        "版本閘門只能比對本 repo 內的 plugin")
            continue
        pj = resolved / ".claude-plugin" / "plugin.json"
        if not pj.is_file():
            errs.append(f"::error file={mp}::{entry.get('name')} 的 source 指向 {src}，"
                        "但該處沒有 .claude-plugin/plugin.json")
            continue
        try:
            pj_ver = json.loads(pj.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError) as e:
            errs.append(f"::error file={pj}::讀取失敗：{e}")
            continue
        seen += 1
        mp_ver = entry.get("version")
        # #33 verify R4：先前 `mp_ver != pj_ver` 把「兩邊都沒有 version」判為一致並印 ✓ ——
        # 而那正是 pack README 說會讓 pack 靜默消失（cache 目錄名不是 semver）的條件。
        if pj_ver is None or mp_ver is None:
            errs.append(
                f"::error file={mp}::{entry.get('name')} 缺 version"
                f"（plugin.json={pj_ver!r}、marketplace.json={mp_ver!r}）。"
                "兩邊都沒有不是「一致」—— cache 目錄名會退回 commit SHA，consumer 定位不到"
            )
        elif mp_ver != pj_ver:
            errs.append(
                f"::error file={mp}::{entry.get('name')} version 不同步 —— "
                f"plugin.json={pj_ver} 但 marketplace.json={mp_ver}。"
                "兩者不一致時使用者 /plugin update 收不到新版，且不會有任何錯誤訊息"
            )
        else:
            print(f"marketplace 版本一致：{entry.get('name')} {pj_ver} ✓")
    if seen == 0:
        errs.append(f"::error file={mp}::沒有任何本 repo 內的 plugin 被檢查 —— 這個檢查形同虛設")


def check_bumped(root, errs, base, event=None):
    """改了 `lenses/*.csv` 就**必須** bump 版本（相對 base 增加），不只是「兩處一致」。

    #33 verify R5：先前變更清單用三點 `base...HEAD`（= merge-base(base,HEAD) → HEAD），
    版本卻用 `git show base:`（= base **本身**）—— **兩個不同的比較基準**。在分岔歷史下
    這不只是不一致，而是漏檢：對 main force-push 時 `event.before`（B）與新 tip（C）的
    merge-base 是更早的 A，`git diff B...C` 完全看不見「B→C 之間 lens 被回退或刪掉」，
    validator 會印「無需 bump ✓」。

    改法：**先把 base 收斂成單一個 cmp_base，變更清單與舊版本都從它取**。
    語意由 event 決定 —— PR 要問「這個 PR 引入了什麼」（merge-base），
    push 要問「這次 push 讓 main 的樹變成什麼」（exact tree，兩點）。"""
    repo = repo_root(root)
    if repo is None:
        print("note: 不在 monorepo 內 —— 略過 bump 檢查")
        return
    if not base:
        # #33 verify R4：CI 的 push-to-main 事件沒有 pull_request.base.sha，先前會走到這裡
        # 靜默略過 —— 「CI 宣稱的核心發布閘門在 push-to-main 上結構性不存在」。
        # #33 verify R5：但 R4 的修法讓 `workflow_dispatch` **永遠紅** —— 那個事件既沒有
        # pull_request.base.sha 也沒有 event.before。一個結構上不可能綠的檢查，下一個人
        # 會直接把 fail-loud 拿掉，連 PR/push 的守備一起失去。改成看事件與執行環境分流：
        # 手動觸發／本機執行留可見紀錄（那不是發布事件），CI 的 PR/push 拿不到才是設定壞了。
        if event == "workflow_dispatch":
            print("::notice::手動觸發（workflow_dispatch）沒有 base ref —— bump 檢查本次未執行。"
                  "它守的是 PR 與 push 的發布路徑，手動重跑不是發布事件")
            return
        if os.environ.get("GITHUB_ACTIONS") != "true":
            print("note: 本機執行且未給 --base —— bump 檢查未跑（CI 會跑）。"
                  "要在本機驗這一條：--base <ref>")
            return
        errs.append(
            "::error::CI 裡沒有 base ref，無法判斷「改了 lens 卻沒 bump」——"
            f"事件是 {event or '<unknown>'}，workflow 沒把 base 傳進來"
            "（pull_request 用 base.sha、push 用 event.before）"
        )
        return
    rel = "plugins/pai-lenses/lenses"
    # #33 verify R4：先前只堵 returncode != 0。git 對「pathspec 指向 base 不存在的路徑」
    # 是成功 + 空輸出 —— 與「真的沒改」不可區分。先確認 base 這個 ref 本身存在。
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
                      cwd=repo, capture_output=True).returncode != 0:
        errs.append(f"::error::base ref '{base}' 不在本地歷史內 —— bump 檢查沒有跑。"
                    "CI 請確認 checkout 帶 fetch-depth: 0")
        return
    cmp_base = base
    if event == "pull_request":
        mb = subprocess.run(["git", "merge-base", base, "HEAD"],
                            cwd=repo, capture_output=True, text=True)
        if mb.returncode != 0 or not mb.stdout.strip():
            errs.append(f"::error::算不出 merge-base({base}, HEAD)：{mb.stderr.strip()}。"
                        "這不是「無需 bump」—— 是這道閘門沒有跑")
            return
        cmp_base = mb.stdout.strip()
        print(f"bump 檢查基準：merge-base({base[:12]}, HEAD) = {cmp_base[:12]}（pull_request）")
    else:
        print(f"bump 檢查基準：{base[:12]} 本身（{event or 'exact-tree'}）")
    # 兩點 —— 與下面取舊版本的 `git show {cmp_base}:` 是同一個基準。
    changed = subprocess.run(["git", "diff", "--name-only", cmp_base, "HEAD", "--", rel],
                             cwd=repo, capture_output=True, text=True)
    if changed.returncode != 0:
        errs.append(f"::error::bump 檢查無法執行：{changed.stderr.strip()}。"
                    "這不是「無需 bump」—— 是這道閘門沒有跑")
        return
    if not changed.stdout.strip():
        print("lenses/ 相對 base 無變更 —— 無需 bump ✓")
        return
    pj = root / ".claude-plugin" / "plugin.json"
    now = json.loads(pj.read_text(encoding="utf-8")).get("version", "")
    old = subprocess.run(
        ["git", "show", f"{cmp_base}:plugins/pai-lenses/.claude-plugin/plugin.json"],
        cwd=repo, capture_output=True, text=True)
    if old.returncode != 0:
        print(f"note: base（{cmp_base[:12]}）沒有 plugins/pai-lenses/.claude-plugin/plugin.json —— "
              "本次在新增整個 pack，無前一版可比。這是唯一合法的略過情境")
        return
    prev = json.loads(old.stdout).get("version", "")
    tn, tp = version_tuple(now), version_tuple(prev)
    if tn is None or tp is None:
        errs.append(f"::error file={pj}::版本字串不是 semver（base={prev!r}、現在={now!r}），無法比較")
    elif tn <= tp:
        errs.append(
            f"::error file={pj}::lenses/ 改了（{', '.join(changed.stdout.split())}）"
            f"但版本沒有增加（base={prev} → 現在={now}）。"
            "版本沒變時使用者 /plugin update 收不到這些 lens，而且不會有任何錯誤訊息"
        )
    else:
        print(f"lenses/ 有變更且已 bump：{prev} → {now} ✓")


def check_lens_dir_shape(root, errs):
    """`lenses/` 下只能有單層、小寫 `.csv`，檔名即 profile。

    #33 verify R4：先前用 `glob("*.csv")`，`lenses/academic.CSV` 與 `lenses/sub/x.csv`
    完全不會被任何檢查看到 —— 貢獻者正確 bump、CI 全綠，而那些 lens 根本不會被載入。"""
    d = root / "lenses"
    if not d.is_dir():
        errs.append(f"::error::找不到 {d} —— 空的 pack 不貢獻任何東西")
        return []
    good = []
    for p in sorted(d.iterdir()):
        rel = p.relative_to(root)
        if p.is_dir():
            errs.append(f"::error file={rel}::lenses/ 下不能有子目錄 —— consumer 只讀 "
                        "lenses/<profile>.csv 單層，放在這裡的 lens 不會被載入")
        elif p.suffix != ".csv":
            errs.append(f"::error file={rel}::副檔名必須是小寫 .csv（現在是 '{p.suffix}'）—— "
                        "consumer 用 <profile>.csv 精確比對，大小寫不同的檔案不會被載入")
        else:
            good.append(p)
    if not good:
        errs.append("::error::lenses/ 下沒有任何合法的 <profile>.csv")
    return good


def check_csvs(root, errs, files):
    repo = repo_root(root)
    known_profiles = None
    if repo is not None:
        lister = repo / "plugins" / "parallel-ai-agents" / "bin" / "pai-list-profiles"
        if lister.is_file():
            r = subprocess.run(["bash", str(lister)], capture_output=True, text=True)
            if r.returncode != 0:
                errs.append(f"::error::無法取得 PROFILES 清單：{r.stderr.strip()}")
            else:
                known_profiles = {p.strip() for p in r.stdout.split() if p.strip()}

    for path in files:
        rel = path.relative_to(root)
        # #33 verify R4：header 要看 reader.fieldnames，不能從 rows[0].keys() 反推 ——
        # 反推看不出重複欄位（DictReader 會覆蓋），也看不出多餘欄位（跑進 restkey）。
        try:
            with path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh, restkey="__extra__", restval=None)
                fieldnames = list(reader.fieldnames or [])
                rows = list(reader)
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            errs.append(f"::error file={rel}::讀取/解析失敗：{e}")
            continue

        if "profile" in fieldnames and "key" in fieldnames and "focus" in fieldnames:
            errs.append(
                f"::error file={rel}::header 含 `profile` 欄 —— 這是 builtin-lenses.csv 的格式，"
                "不是 pack 的格式（key,focus,needsSrt,override）。整份複製 catalog 會讓 key 欄"
                "拿到 profile 名、focus 欄拿到 key，而每一列看起來都還是合法的 lens")
            continue
        if "key" not in fieldnames or "focus" not in fieldnames:
            errs.append(f"::error file={rel}::header 必須含 key 與 focus（現在是 {fieldnames}）")
            continue
        dupes = sorted({c for c in fieldnames if fieldnames.count(c) > 1})
        if dupes:
            errs.append(f"::error file={rel}::header 有重複欄位 {dupes} —— "
                        "後出現的會靜默覆蓋先出現的，你以為填了的值會消失")
            continue
        unknown = [c for c in fieldnames if c not in KNOWN_COLS]
        if unknown:
            errs.append(f"::error file={rel}::header 有不認識的欄位 {unknown}"
                        f"（合法：{list(KNOWN_COLS)}）。拼錯的欄位會被靜默忽略 —— "
                        "例如 'overide' 會讓該列的 override 完全失效而不報錯")
            continue

        extra = [i for i, r in enumerate(rows, start=2) if r.get("__extra__")]
        if extra:
            errs.append(f"::error file={rel}::第 {extra} 列的欄位數多於 header —— "
                        "多出來的值會被丟棄。最常見原因是 focus 裡的逗號沒有用雙引號包起來，"
                        "那會讓 focus 被截斷、後面的欄位整個錯位")
            continue
        # #33 verify R5：先前這裡對「任一欄是 None」（列比 header 短）一律 error —— 那是
        # **假陽性，而且擋掉的正是本 PR 想鋪的貢獻路徑**。`perf,"a, b, c"` 這種省略尾端
        # 可選欄的寫法：pack README 明文允許（「空白**或省略** = false」）、生產端
        # `pai-parse-lens-csv`（`DictReader(restval=None)` → `_truthy(None)` = False）
        # 解析得好好的、rc=0。守門者比被守的契約嚴，擋掉的是合法貢獻。
        # 真正危險的是「key / focus 被截斷」—— 那由下面的 bad 檢查涵蓋（None → 空字串 → 命中）。
        bad = [i for i, r in enumerate(rows, start=2)
               if not ((r.get("key") or "").strip() and (r.get("focus") or "").strip())]
        if bad:
            errs.append(f"::error file={rel}::第 {bad} 列缺 key 或 focus —— 這些列會被解析器整列丟棄")
            continue
        if not rows:
            errs.append(f"::error file={rel}::解析出 0 條 lens —— 存在卻不貢獻任何東西的檔案比沒有更糟")
            continue
        for r in rows:
            if (r["key"] or "").lstrip().startswith("#"):
                errs.append(f"::error file={rel}::key 以 '#' 開頭 —— CSV 沒有註解語法，"
                            "這一列會變成一條真的 lens 送進 reviewer prompt")

        profile = path.stem
        if known_profiles is not None and profile not in known_profiles:
            errs.append(
                f"::error file={rel}::'{profile}' 不是既有 profile"
                f"（真源 PROFILES 有：{', '.join(sorted(known_profiles))}）。"
                "pack 只能為既有 profile 加 lens —— CSV 描述不了 profile 級的 "
                "title/daFocus/codexDefault，新 profile 必須改 PROFILES（層 ①）")
            continue

        print(f"{rel}: {len(rows)} 條 lens ✓（profile '{profile}'）")

        # 這段是**啟發式提示**，不是事實判定 —— 見 collector_wiring() 的註解。
        own, wired = collector_wiring(repo, profile)
        if own is None:
            print(f"::warning file={rel}::profile '{profile}' 沒有 ensemble-{profile}-review "
                  f"這支專屬 skill —— 這裡的 lens 只會在 /ensemble-compose --base {profile} "
                  f"時被載入")
        elif wired is False:
            print(f"::warning file={rel}::在 `/{own}` 的 SKILL.md 裡找不到 "
                  f"pai-collect-lens-layers 的呼叫 —— 若確實沒接，這裡的 lens 不會出現在"
                  f"它的審閱裡，只會在 /ensemble-compose --base {profile} 時被載入"
                  f"（那是該 skill 的接線缺口，追蹤於 #40，不是本 pack 的問題）。"
                  f"**本檢查是掃 SKILL.md 文字的啟發式，可能誤判，請人工確認**")

        for r in rows:
            for col in ("override", "needsSrt"):
                raw = (r.get(col) or "").strip().lower()
                if raw and raw not in TRUTHY + FALSY:
                    print(f"::warning file={rel}::{col}='{r[col]}' 不是可辨識的真假值 —— 會被當成 false")


def main():
    argv = sys.argv[1:]
    opts = {"--base": None, "--event": None}
    for flag in opts:
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                print("用法：validate.py [--base <ref>] [--event <github-event-name>]",
                      file=sys.stderr)
                return 2
            opts[flag] = argv[i + 1] or None
    base, event = opts["--base"], opts["--event"]
    root = pathlib.Path(__file__).resolve().parent.parent
    errs = []
    check_version(root, errs)
    check_marketplace_sync(root, errs)
    check_bumped(root, errs, base, event)
    files = check_lens_dir_shape(root, errs)
    if files:
        check_csvs(root, errs, files)
    for e in errs:
        print(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
