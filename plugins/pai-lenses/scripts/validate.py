#!/usr/bin/env python3
"""驗證這個 lens pack 可被 parallel-ai-agents 正確消費。

每一項檢查都對應一個**安靜**的失敗模式 —— 東西看起來好好的、CI 全綠，
但使用者端少了一條 lens 或整個 pack 不生效，而且沒有任何錯誤訊息。

用 stdlib `csv` —— 與 consumer 的 `pai-parse-lens-csv` 同一個模組、同一套 quoting 規則。

用法：validate.py [--base <ref>] [--event {pull_request,push,workflow_dispatch}]

參數由 argparse 解析（#33 verify R9）—— 未知旗標、未知位置參數、缺值、`--event` 不在
列舉內，全部 exit 2。手寫解析的每一個洞後果都是**安靜地換掉判準**，而不是報錯。

退出碼：0 全部通過；1 有錯；2 用法錯。
"""
import argparse
import csv
import json
import os
import pathlib
import re
import subprocess
import sys

# #33 verify R9：先前是 `^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$` 搭 `match()` —— `$` 接受尾端
# 換行、`01.2.3` 前導零、`1.2.3-`／`1.2.3+` 空後綴全部放行，而這道閘門的**整個理由**
# 就是「cache 目錄名必須是 semver」。改用 semver 官方文法 + `fullmatch()`。
SEMVER = re.compile(
    r"(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")
TRUTHY = ("1", "true", "yes")
FALSY = ("", "0", "false", "no")
KNOWN_COLS = ("key", "focus", "needsSrt", "override")
# 封閉列舉，不是判準：只略過這些已知的 OS 產物（#33 verify R9）。
OS_ARTIFACTS = (".DS_Store", ".gitkeep", ".gitignore", "Thumbs.db")


def _truthy(value):
    """與生產端 `bin/pai-parse-lens-csv` 的 `_truthy` **逐字同義**。

    守門者與被守的契約用兩套判準，就是「兩份不會一起改的規格」—— 分岔會安靜地發生在邊界上。
    這裡刻意用同一個運算式（`str(value or "").strip().lower() in TRUTHY`），
    而不是自己重寫一套看起來等價的判斷。"""
    return str(value or "").strip().lower() in TRUTHY


def version_tuple(v):
    """semver → 可比較的 tuple。build 後綴忽略；prerelease 依 semver §11 排在同 core 正式版之前。

    #33 verify R4：先前 check_version 用 `^\\d+\\.\\d+\\.\\d+` 前綴比對放行 `0.3.0-rc1`，
    而 check_bumped 用 `int(x) for x in v.split('.')[:3]` 對同一字串炸掉（'0-rc1' 不是 int）
    → 兩個檢查對同一版本字串的認定不一致。統一走這裡。"""
    m = SEMVER.fullmatch(str(v or ""))
    if not m:
        return None
    core = (int(m["major"]), int(m["minor"]), int(m["patch"]))
    # #33 verify R7：先前只回 core，於是 `0.3.0-rc1 → 0.3.0`（rc 轉正式，最典型的發布
    # 動作）與 `rc1 → rc2` 都被 `tn <= tp` 判為「版本沒有增加」。semver §11：有 prerelease
    # 的版本**低於**同 core 的正式版。
    # 照 semver §11 逐 identifier 比較：數字段按整數、非數字段按 ASCII、
    # 數字段低於非數字段、identifier 較少者較低（其餘皆相等時）。
    #
    # #33 verify R10 更正：R9 在這裡寫「`1.0.0-rc10 → 1.0.0-rc9` 的閘門逃逸現在修掉了」——
    # **那句是假的**。`rc9` / `rc10` 是**單一個 alphanumeric identifier**（不是 `rc.9`），
    # 逐 identifier 比較之後仍然落在同一個 ASCII 字串比較上，與 R7 的整段字串比較在這個
    # 案例上逐字等價。實測 `rc10 → rc9` 照樣通過閘門，`rc9 → rc10` 這個正常的遞增發布
    # 照樣被擋。
    #
    # **就 semver 2.0.0 而言那是對的**（`rc9 > rc10`，因為 '1' < '9'），所以程式碼合規、
    # 不改。要正確排序請用 `rc.9` / `rc.10`（點分隔，數字段按整數比較）——
    # 下面 `check_version` 會對 `rcN` 這種把數字黏在字母後面的形式印 warning，
    # 把這個陷阱顯性化，而不是讓人在發布當天才撞到。
    if m["pre"] is None:
        return core + (1,)                       # 正式版高於任何同 core 的 prerelease
    ids = []
    for part in m["pre"].split("."):
        ids.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return core + (0, tuple(ids))




def emit(line):
    """**所有 workflow-command 輸出的唯一出口。**

    #33 verify R10（作者自查）：R10 的第一版修法是在**個別呼叫點**包 `wc()` —— 我包了六處，
    而實際上有約四十處插入了攻擊者可控的值（git 檔名可以含換行、marketplace.json 的字串、
    CSV 衍生的 key/欄位…）。**那個修法本身就是這個 PR 一路在抓的「同類只修一處」，
    只是規模更大。**

    正確的形狀是在**邊界**消毒，不是在每個呼叫點：GitHub 的 workflow command 必須從**行首**
    開始解析，所以只要保證一行永遠是一行，`::stop-commands::` 就注入不進來。這裡把整行的
    CR/LF 換成 `⏎` 並限長 —— 一個地方做完，不需要再問「我有沒有漏掉某個站點」。

    行內的 `::` 保持原樣：它是 annotation 格式的一部分（`::error file=x::msg`），
    而且不在行首就構不成新的 command。"""
    t = str(line).replace("\r\n", "⏎").replace("\n", "⏎").replace("\r", "⏎")
    if len(t) > 4000:
        t = t[:4000] + "…（截斷）"
    print(t)


def wc(value, limit=200):
    """把攻擊者可控的字串消毒成可安全插進 GitHub workflow-command 行的形式。

    #33 verify R10 M8：多處把**未消毒**的 PR 內容原樣插進 `::error::` / `::warning::`，
    而 CSV 的引號欄位與 JSON 字串都可以含真正的換行。實測在 `needsSrt` 欄塞
    `x\n::stop-commands::zzz\n::error file=innocent.py,line=1::forged`，輸出就多出一行
    `::stop-commands::` —— runner 會**停止解析後續所有 workflow command**，包含 `main()`
    最後印出的每一條 `::error::`。job 仍然紅，但 PR 上不會有任何 annotation 指出問題在哪，
    等於把本 PR 一路在建的 fail-loud 降級成 fail-silent；還能偽造指向無辜檔案的 annotation。

    做三件事：換行與 CR 換成 `⏎`（保留可讀性、不製造新行）、`::` 換成 `∷`（U+2237，
    形似但不是 workflow-command 分隔符）、超長截斷。
    """
    t = str(value)
    t = t.replace("\r\n", "⏎").replace("\n", "⏎").replace("\r", "⏎")
    t = t.replace("::", "∷")
    return t if len(t) <= limit else t[:limit] + "…（截斷）"


def load_obj(path_or_text, label, errs, *, is_text=False):
    """讀 JSON 並確認是 dict。回傳 dict 或 None（已把原因寫進 errs）。

    #33 verify R9：先前各處只捕捉 `json.JSONDecodeError`，於是**合法 JSON 但型別不是
    dict**（`[]`、`"x"`、`3`）會在 `.get()` 上拋 `AttributeError` —— 不在任何 except 裡，
    整支 crash，`main()` 印 errs 的迴圈永遠到不了。後果與 R6 M5 逐字相同（GitHub 只拿到
    裸 traceback、零 annotation），而 R6 的測試餵的是語法壞掉的 JSON，走的是另一條 except，
    所以抓不到。這是同一個缺陷的第二個站點。"""
    try:
        raw = path_or_text if is_text else pathlib.Path(path_or_text).read_text(encoding="utf-8")
        obj = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        errs.append(f"::error file={label}::讀取失敗：{e}")
        return None
    if not isinstance(obj, dict):
        errs.append(f"::error file={label}::內容是合法 JSON 但不是物件"
                    f"（是 {type(obj).__name__}）—— manifest 必須是 JSON object")
        return None
    return obj


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
    d = load_obj(manifest, manifest, errs)
    if d is None:
        return
    version = d.get("version", "")
    print(f"version = {version or '<missing>'}")
    m = SEMVER.fullmatch(str(version or ""))
    if m and m["pre"]:
        # `rc9` / `beta2` 這種把數字黏在字母後面的 identifier，semver 規定按 ASCII 比較 ——
        # 於是 `rc9 > rc10`，遞增發布會被 bump 閘門擋下（#33 verify R10）。
        risky = [x for x in m["pre"].split(".")
                 if not x.isdigit() and any(c.isdigit() for c in x)]
        if risky:
            emit(f"::warning file={manifest}::prerelease identifier {risky} 把數字黏在字母後面 —— "
                  "semver §11 對這種 identifier 按 ASCII 比較，於是 `rc9` 排在 `rc10` **之後**，"
                  "遞增發布會被 bump 閘門擋下。請改用點分隔（`rc.9` / `rc.10`），數字段才會按整數比較")
    if version_tuple(version) is None:
        errs.append(
            f"::error file={manifest}::需要 semver version（現在是 '{version}'）—— 缺了或格式不對時 "
            "cache 目錄名會退回 commit SHA 或 unknown，consumer 的 semver glob 定位不到這個 pack"
        )


def _inside(path, repo_abs):
    """path 是否在 repo_abs 之內（含 repo_abs 本身）。兩者都必須已 resolve()。"""
    try:
        return path.is_relative_to(repo_abs)                  # Python 3.9+
    except AttributeError:                                    # 3.8 fallback
        return str(path).startswith(str(repo_abs) + os.sep)


def check_marketplace_sync(root, errs):
    """**每一個**在本 repo 內的 plugin，其 plugin.json version 必須與 marketplace entry 一致，
    而且**每一個 plugin 目錄都必須有 entry**。

    #33 verify R6：先前只從 marketplace entry 這一側走，於是「entry 根本不存在」完全不被
    涵蓋 —— 實測把 `pai-lenses` 整條 entry 刪掉，validator 印
    `marketplace 版本一致：parallel-ai-agents 2.23.0 ✓` 並 exit 0，而使用者
    `/plugin install pai-lenses@parallel-ai-agents` 直接裝不到。`seen == 0` 那道保險也不會
    觸發（主 plugin 讓 seen 是 1）。新增第三個 plugin 時最可能的失誤正是「建了目錄、忘了加
    entry」，走的是同一段 code。所以現在**雙向**：entry → 檔案（版本一致）、檔案 → entry（存在）。"""
    repo = repo_root(root)
    if repo is None:
        print("note: 不在 monorepo 內 —— 略過 marketplace 版本一致檢查")
        return
    mp = repo / ".claude-plugin" / "marketplace.json"
    mp_obj = load_obj(mp, mp, errs)
    if mp_obj is None:
        return
    plugins = mp_obj.get("plugins", [])
    if not isinstance(plugins, list):
        errs.append(f"::error file={mp}::`plugins` 必須是陣列（現在是 {type(plugins).__name__}）"
                    " —— 迭代 dict 會拿到 key、迭代字串會拿到字元，兩者都會讓下游誤判")
        return
    repo_abs = repo.resolve()
    seen = 0
    claimed = set()
    entry_names = set()
    claimed_paths = set()
    named_entries = {}   # 有 entry 指名的 plugin 目錄（含被判非法者）
    for entry in plugins:
        if not isinstance(entry, dict):
            errs.append(f"::error file={mp}::`plugins` 的元素必須是物件"
                        f"（有一個是 {type(entry).__name__}：{entry!r}）")
            continue
        src = entry.get("source")
        # #33 verify R4：先前用字串前綴 './' 當「在本 repo 內」的判準，少寫 './' 的
        # 相對路徑（"plugins/foo"）會被靜默跳過 —— 那正是最該檢查的 entry。
        # #33 verify R6：先前是「三個遠端前綴的白名單，其餘一律當本 repo 相對路徑」——
        # 一個**開放的否定判準**去界定一組封閉的遠端形式（正是 rules 那條
        # 「能列舉的就列舉，不要寫總括判準」的鏡像失敗）。落在洞裡的常見形式：
        # `ssh://git@host/owner/repo`、`github:owner/repo`、`file:///abs`、純 `owner/repo`
        # —— 全部會走到 `pj.is_file()` 為 False → hard error「該處沒有 plugin.json」。
        # 也就是 marketplace 一旦收錄任何第三方遠端 plugin（那正是 marketplace 的用途），
        # CI 直接紅，訊息還把原因說成檔案不存在。
        # 改成正面判定「這是不是本 repo 的相對路徑」，且**三態**而非二態：
        # 是 → 納入閘門；明確是遠端 → 略過；判不出來 → 印 warning（不靜默、也不誤紅）。
        # #33 verify R10 M4：把「有一個叫這個名字的 entry」記下來，供反向檢查用。
        # 先前只要 entry 的 source 形式不合（判不出來的字串、dict 缺 path），反向檢查就報
        # 「marketplace.json 裡沒有指向它的 entry」—— **那句話會把維護者導向「再加一條
        # entry」這個錯誤修法**，而真正的問題是既有那條的 source 寫錯了。
        # 注意不能用「登記它宣稱的路徑」來解：那會讓一個指錯地方的 entry 遮蔽掉「真的缺
        # entry」的情況。正確的做法是讓反向檢查按**名字**交叉比對後說出真正的原因。
        if isinstance(entry.get("name"), str) and entry["name"]:
            named_entries[entry["name"]] = src
        rel = None
        if isinstance(src, str):
            if src.startswith("./"):
                rel = src[2:]                      # 明確的本 repo 相對路徑
            elif "://" in src or ":" in src:
                continue                           # scheme / scp-like / `github:owner/repo`
            elif src.startswith("/"):
                rel = src                          # 絕對路徑 —— 交給下面的 containment 報錯
            elif (repo / src.split("/", 1)[0]).is_dir():
                rel = src                          # 第一段在本 repo 內存在 → 當相對路徑
            else:
                emit(f"::warning file={mp}::判不出 {entry.get('name')} 的 source {src!r} "
                      "是本 repo 路徑還是遠端來源 —— **未納入版本閘門**。"
                      "本 repo 內的 plugin 請用 './' 開頭的相對路徑")
                continue
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
        # #33 verify R7：登記必須在**所有** continue 之前。R6 把它放在 `..`／絕對路徑那道
        # 檢查**之後**，還在註解裡宣稱「順序是刻意的，避免反向檢查再罵一次」—— 那句是假的：
        # 實測 `source: "../evil"` 會同時得到「只能用相對路徑」與「沒有指向它的 entry」兩則
        # error，後者是假訊息（有 entry，只是非法）。R6 只測了 symlink 那條（它在登記之後）。
        claimed.add(pathlib.Path(os.path.normpath(repo_abs / rel)))
        if os.path.isabs(rel) or ".." in pathlib.PurePosixPath(rel).parts:
            errs.append(f"::error file={mp}::{wc(entry.get('name'))} 的 source 是 {wc(repr(src))} —— "
                        "本 repo 內的 plugin 只能用不含 '..' 的相對路徑。"
                        "絕對路徑與 '..' 會讓這道版本閘門去比對 repo 外的檔案")
            continue
        # #33 verify R6：R5 只對 **plugin 目錄** 做 containment，然後才把
        # `.claude-plugin/plugin.json` 接上去讀 —— **檢查的路徑不是實際讀的路徑**。
        # 實測：`plugins/evil/.claude-plugin -> /repo/外` 這個形狀完全不被擋，
        # 版本閘門拿了 repo 外的 plugin.json 當來源並印「marketplace 版本一致：evil 9.9.9 ✓」。
        # 修法：對**最終要讀的那個檔**做判定；目錄那層也保留，兩層才涵蓋
        # 「目錄本身是 symlink」與「目錄合法但底下某層是 symlink」兩種形狀。
        # 登記用 normpath 而非 resolve：反向檢查那側枚舉的是 repo 內的實際目錄，
        # 兩側必須用同一種正規化才比得起來。
        resolved = (repo / rel).resolve()
        pj = (resolved / ".claude-plugin" / "plugin.json").resolve()
        outside = [p for p in (resolved, pj) if not _inside(p, repo_abs)]
        if outside:
            errs.append(f"::error file={mp}::{entry.get('name')} 的 source {src!r} "
                        f"解析後落在 repo 外（{outside[0]}）—— 可能是 symlink。"
                        "版本閘門只能比對本 repo 內的 plugin")
            continue
        if not pj.is_file():
            errs.append(f"::error file={mp}::{entry.get('name')} 的 source 指向 {src}，"
                        "但該處沒有 .claude-plugin/plugin.json")
            continue
        pj_obj = load_obj(pj, pj, errs)
        if pj_obj is None:
            continue
        pj_ver = pj_obj.get("version")
        # #33 verify R9：先前 `entry.get("name")` 只出現在錯誤訊息字串裡，**從未參與判定** ——
        # 於是「entry 名字錯了」這個最貼近使用者症狀的形狀完全不在守備範圍：把 name 刪掉或
        # 打成 `pai-lense`，版本與路徑都對，validator 印 ✓、反向檢查也因目錄已被 claim 而通過，
        # 而使用者 `/plugin install pai-lenses@…` 裝不到。root CLAUDE.md 把版本同步標為
        # CRITICAL 並宣稱「機械閘門守這條」—— 那句話漏掉了身分這一半。
        ent_name, pj_name = entry.get("name"), pj_obj.get("name")
        if not ent_name:
            errs.append(f"::error file={mp}::有一個指向 {rel} 的 entry 沒有 name —— "
                        "使用者 `/plugin install <name>@<marketplace>` 沒有名字可用")
        elif pj_name and ent_name != pj_name:
            errs.append(f"::error file={mp}::entry name '{ent_name}' 與 {rel} 的 "
                        f"plugin.json name '{pj_name}' 不一致 —— 兩者必須相同，"
                        "否則使用者用哪一個名字都可能裝不到")
        if ent_name:
            if ent_name in entry_names:
                errs.append(f"::error file={mp}::entry name '{ent_name}' 重複 —— "
                            "後出現的會蓋掉先出現的，你以為裝到的可能是另一個")
            entry_names.add(ent_name)
        if resolved in claimed_paths:
            errs.append(f"::error file={mp}::有兩個 entry 指向同一個目錄 {rel} —— "
                        "無法判斷哪一個才是那個 plugin 的 entry")
        claimed_paths.add(resolved)

        seen += 1
        mp_ver = entry.get("version")
        # #33 verify R7：先前只有 pack 自己的 check_version 驗 semver 格式，主 plugin 的
        # 非 semver 版本一路綠燈 —— 與 root CLAUDE.md「這條對每一個 plugin 各自成立」不符。
        # cache 目錄名不是 semver 時 consumer 的 glob 定位不到，那是逐 plugin 成立的失敗。
        for label, val in (("plugin.json", pj_ver), ("marketplace.json", mp_ver)):
            if val is not None and version_tuple(val) is None:
                errs.append(f"::error file={mp}::{entry.get('name')} 的 {label} version "
                            f"'{val}' 不是 semver —— cache 目錄名會退回 commit SHA 或 unknown，"
                            "consumer 的 semver glob 定位不到這個 plugin")
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
        # #33 verify R6：這道閘門先前只比對 version，對 description 完全無視 ——
        # 而本 PR 自己就製造了那個漂移（plugin.json 換成 v2.23.0 的說明、marketplace
        # 仍停在 v2.21.0），使用者看到的版本是 2.23.0、描述卻是兩版前的文字。
        # 剛立起來的閘門對它自己造成的漂移是盲的。warning 而非 error：description 不同步
        # 不會讓人裝不到東西（version 會），但兩份敘述指向不同版本區間仍是缺陷。
        try:
            pj_desc = json.loads(pj.read_text(encoding="utf-8")).get("description")
        except (OSError, json.JSONDecodeError):
            pj_desc = None
        mp_desc = entry.get("description")
        if pj_desc is not None and mp_desc is not None and pj_desc != mp_desc:
            emit(f"::warning file={mp}::{entry.get('name')} 的 description 兩處不同步 —— "
                  "使用者在 /plugin 看到的是 marketplace 那份，可能在敘述舊版本的內容")
    if seen == 0:
        errs.append(f"::error file={mp}::沒有任何本 repo 內的 plugin 被檢查 —— 這個檢查形同虛設")

    # 反向：檔案系統 → marketplace entry。缺 entry 的 plugin 使用者根本裝不到，
    # 而正向迴圈**結構上**看不到它（它不在 plugins 陣列裡）。#33 verify R6。
    for found in sorted(repo_abs.glob("plugins/*/.claude-plugin/plugin.json")):
        pdir = found.parent.parent
        if pathlib.Path(os.path.normpath(pdir)) not in claimed:
            # 先看有沒有「名字對得上但 source 指錯地方」的 entry —— 訊息要指向真正的修法。
            try:
                dir_name = json.loads(
                    found.read_text(encoding="utf-8")).get("name")
            except (OSError, json.JSONDecodeError, AttributeError):
                dir_name = None
            culprit = named_entries.get(dir_name) if dir_name else None
            if culprit is not None:
                errs.append(
                    f"::error file={mp}::有一個名為 {wc(dir_name)} 的 entry，但它的 source "
                    f"（{wc(repr(culprit))}）沒有指向 {pdir.relative_to(repo_abs)} —— "
                    "**要修的是那條 entry 的 source，不是再加一條 entry**")
            else:
                errs.append(
                    f"::error file={mp}::{pdir.relative_to(repo_abs)} 有 plugin.json，"
                    f"但 marketplace.json 裡沒有指向它的 entry —— 使用者 "
                    f"`/plugin install {pdir.name}@<marketplace>` 會直接裝不到，且沒有任何錯誤訊息")



def _find_pack_at(repo, ref, pj_rel, name):
    """找出 `pj_rel` 這個檔在 `ref` 時的舊路徑（用來偵測 pack 改名）。找不到回 None。

    #33 verify R9：R7 的版本只靠 `plugin.json` 的 `name` 欄比對，而 validate.py 從頭到尾
    **沒有任何地方驗證 `name`**。於是「目錄改名 + 同時改 plugin 名」（很常見的一個 PR）
    或 `name` 缺席，改名偵測整條失效 —— 實測 rc=0，印出「本次在新增整個 pack…**這是唯一
    合法的略過情境**」，而那句話在這條路徑上是假的，會讓 reviewer 停止追問。

    改成**先問 git**：`git diff --name-status -M` 的 rename detection 是按內容相似度，
    不依賴檔案裡的任何欄位。git 認不出來時（改動太大）才退回 name 比對當第二來源。"""
    # 偵測 pack **目錄**的改名，不是單一檔案的：plugin.json 內容常常跟著改
    # （改目錄通常也改 plugin 名），git 就把它判成 A+D 而非 R —— 但同一次改名裡
    # 其他檔案（README/LICENSE/scripts）仍是 R100。取多數決還原舊的 pack 根目錄。
    pack_rel = pj_rel[: -len("/.claude-plugin/plugin.json")]
    dt = subprocess.run(["git", "diff", "--name-status", "-M", ref, "HEAD"],
                        cwd=repo, capture_output=True, text=True)
    if dt.returncode == 0:
        votes = {}
        for line in dt.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or not parts[0].startswith("R"):
                continue
            old_path, new_path = parts[1], parts[2]
            prefix = pack_rel + "/"
            if not new_path.startswith(prefix):
                continue
            suffix = new_path[len(prefix):]
            if old_path.endswith("/" + suffix):
                old_pack = old_path[: -(len(suffix) + 1)]
                votes[old_pack] = votes.get(old_pack, 0) + 1
        if votes:
            old_pack = max(votes, key=votes.get)
            candidate = f"{old_pack}/.claude-plugin/plugin.json"
            if subprocess.run(["git", "cat-file", "-e", f"{ref}:{candidate}"],
                              cwd=repo, capture_output=True).returncode == 0:
                return candidate
    if not name:
        return None
    ls = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref],
                        cwd=repo, capture_output=True, text=True)
    if ls.returncode != 0:
        return None
    for path in ls.stdout.splitlines():
        if not path.endswith(".claude-plugin/plugin.json"):
            continue
        blob = subprocess.run(["git", "show", f"{ref}:{path}"],
                              cwd=repo, capture_output=True, text=True)
        if blob.returncode != 0:
            continue
        try:
            obj = json.loads(blob.stdout)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("name") == name:
            return path
    return None


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
            emit("::notice::手動觸發（workflow_dispatch）沒有 base ref —— bump 檢查本次未執行。"
                  "它守的是 PR 與 push 的發布路徑，手動重跑不是發布事件")
            return
        if os.environ.get("GITHUB_ACTIONS") != "true":
            print("note: 本機執行且未給 --base —— bump 檢查未跑（CI 會跑）。"
                  "要在本機驗這一條：--base <上游分支>（預設走 merge-base 語意）")
            return
        # #33 verify R7：先前一律說「workflow 沒把 base 傳進來」。但 push 事件的
        # `event.before` 在**建立分支**與 **main 被重建**時是全零 SHA，workflow 依約定
        # 傳空字串 —— 那不是設定壞了，是這個事件本來就沒有前一個狀態可比。
        # 把責任推給 workflow 會讓人去改一個沒有壞的地方。
        if event == "push":
            errs.append(
                "::error::push 事件拿不到 base（`event.before` 為全零）——**bump 檢查沒有跑**"
                "（不是「無需 bump」）。全零通常代表這是新建立的分支，或 main 剛被重建；"
                "兩種情況都沒有前一個狀態可比。若這次 push 動了 lens，請人工確認版本已 bump")
        else:
            errs.append(
                "::error::CI 裡沒有 base ref，無法判斷「改了 lens 卻沒 bump」——"
                f"事件是 {event or '<unknown>'}，workflow 沒把 base 傳進來"
                "（pull_request 用 base.sha、push 用 event.before）")
        return
    # #33 verify R6：先前寫死 "plugins/pai-lenses/…"。`root` 與 `repo` 都已知，
    # 導得出來卻選擇寫死 —— 實測 `git mv plugins/pai-lenses plugins/lens-pack` 之後，
    # 下一個 commit 起每一次 lens 變更都印「無需 bump ✓」而完全不受守護。
    # 位置耦合造成的假綠燈，正是本 PR 反覆在修的那一類。
    pack_rel = root.resolve().relative_to(repo.resolve()).as_posix()
    try:
        _pk = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        pack_name = _pk.get("name") if isinstance(_pk, dict) else None
    except (OSError, json.JSONDecodeError):
        pack_name = None
    rel = f"{pack_rel}/lenses"
    pj_rel = f"{pack_rel}/.claude-plugin/plugin.json"
    # #33 verify R4：先前只堵 returncode != 0。git 對「pathspec 指向 base 不存在的路徑」
    # 是成功 + 空輸出 —— 與「真的沒改」不可區分。先確認 base 這個 ref 本身存在。
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
                      cwd=repo, capture_output=True).returncode != 0:
        # #33 verify R6：先前訊息一律叫人「確認 checkout 帶 fetch-depth: 0」。但對
        # push 事件最常見的成因是 **force-push**：舊 tip（event.before）已不被任何 ref
        # 指到，`actions/checkout` 只 fetch ref 可達的物件，fetch-depth: 0 也拿不到它。
        # 照那句建議做完全無效。誠實的處置是說清楚「這個情境無法判定」而不是給錯的補救。
        if event == "push":
            errs.append(
                f"::error::base '{base}' 不在本地歷史內 —— bump 檢查**沒有跑**（不是「無需 bump」）。"
                "push 事件最常見的成因是 force-push：舊 tip 已不被任何 ref 指到，"
                "`actions/checkout` 只 fetch ref 可達的物件，`fetch-depth: 0` 也拿不到它。"
                "**force-push 到 main 不在這道閘門的守備範圍**；請人工確認這次 push 有沒有動 lens")
        else:
            errs.append(f"::error::base ref '{base}' 不在本地歷史內 —— bump 檢查沒有跑。"
                        "CI 請確認 checkout 帶 fetch-depth: 0")
        return
    # #33 verify R6：先前 `--event` 缺省 → exact-tree。但本檔自己印的提示叫人在本機跑
    # `--base main`，而 main 常常已經前進 —— 實測一個**完全沒碰 lenses/** 的分支照著做，
    # 會拿到「lenses/ 改了（…code.csv）但版本沒有增加」的假失敗，還指名一個它沒動過的檔案。
    # 缺省的問題是「我的分支引入了什麼」，那是 merge-base 語意；exact-tree 只在 push 事件
    # （「這次 push 讓 main 變成什麼」）才是對的，而 CI 一律會傳 --event。
    cmp_base = base
    if event != "push":
        mb = subprocess.run(["git", "merge-base", base, "HEAD"],
                            cwd=repo, capture_output=True, text=True)
        if mb.returncode != 0 or not mb.stdout.strip():
            errs.append(f"::error::算不出 merge-base({base}, HEAD)：{mb.stderr.strip()}。"
                        "這不是「無需 bump」—— 是這道閘門沒有跑")
            return
        cmp_base = mb.stdout.strip()
        print(f"bump 檢查基準：merge-base({base[:12]}, HEAD) = {cmp_base[:12]}"
              f"（{event or '預設'}：問「這個分支引入了什麼」）")
    else:
        print(f"bump 檢查基準：{base[:12]} 本身（push：exact-tree）")
    # #33 verify R6：R5 把「變更清單」與「舊版本」統一到 cmp_base，但**漏了第三個讀取點**
    # —— `now` 當時是從工作目錄的 plugin.json 讀的。同一次執行裡 changed 看 committed
    # history、now 看 working tree，還是兩個基準。CI 裡兩者相同所以看不出來；但本檔自己
    # 印的提示叫人在本機用 `--base <ref>` 驗，照做（改了 lens 還沒 commit）實測會得到：
    #   lenses/ 相對 base 無變更 —— 無需 bump ✓      ← 肯定式綠燈，且是假的
    #   lenses/code.csv: 2 條 lens ✓                ← 同一次執行看到了那條新 lens
    # 現在三個讀取點全部取自 committed history，並且**先**把未 commit 的差異講出來 ——
    # 那句提示必須在「無變更」那條路徑上也印得到，否則假綠燈依舊。
    dirty = subprocess.run(["git", "status", "--porcelain", "--", rel, pj_rel],
                           cwd=repo, capture_output=True, text=True)
    if dirty.returncode == 0 and dirty.stdout.strip():
        # porcelain v1 = 2 個狀態字元 + 1 個空白 + 路徑。**不可**先 strip() 整個 stdout：
        # 那會吃掉第一行的前導空白（` M path` → `M path`），ln[3:] 就多切一個字元。
        paths = [ln[3:] for ln in dirty.stdout.splitlines() if len(ln) > 3]
        emit("::warning::工作目錄有未 commit 的變更，bump 檢查**只涵蓋已 commit 的內容**："
              + ", ".join(paths))
    # #33 verify R10 M3：改名偵測先前只讓「舊版本」那一側 rename-aware，**變更清單這一側
    # 用的仍是新路徑** —— pack 目錄一改名，舊路徑下的每個 lens 在新路徑上都算「新增」，
    # `changed` 必然非空，於是一次**純目錄搬移**（lens 內容零變動）被要求 bump 版本。
    # 同一次執行裡「版本那一側知道這是改名，變更清單那一側不知道」—— 與 R5/R6 反覆在修的
    # 「同一次執行用兩個基準」同形，只是這次的兩側是 rename-aware vs rename-blind。
    moved_pj = _find_pack_at(repo, cmp_base, pj_rel, pack_name)
    pathspec = [rel]
    if moved_pj:
        old_lens = moved_pj[: -len("/.claude-plugin/plugin.json")] + "/lenses"
        pathspec = [old_lens, rel]
    changed = subprocess.run(
        ["git", "diff", "--name-status", "-M", cmp_base, "HEAD", "--", *pathspec],
        cwd=repo, capture_output=True, text=True)
    if changed.returncode != 0:
        errs.append(f"::error::bump 檢查無法執行：{wc(changed.stderr.strip())}。"
                    "這不是「無需 bump」—— 是這道閘門沒有跑")
        return
    # 純改名（R100，內容零變動）不算 lens 有變更；R<100 表示搬移時內容也改了，要算。
    real = []
    for line in changed.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        if parts[0] == "R100":
            continue
        real.append(parts[-1])
    if not real:
        msg = "lenses/ 相對 base 無變更（已 commit 的部分）—— 無需 bump ✓"
        if moved_pj:
            msg += "（偵測到純目錄改名，內容零變動）"
        print(msg)
        return
    pj = root / ".claude-plugin" / "plugin.json"
    cur = subprocess.run(["git", "show", f"HEAD:{pj_rel}"],
                         cwd=repo, capture_output=True, text=True)
    if cur.returncode != 0:
        errs.append(f"::error file={pj}::HEAD 上沒有 {pj_rel} —— 無法與 base 比較版本。"
                    "這不是「無需 bump」")
        return
    # #33 verify R6：這兩處 json.loads 先前沒有 try。plugin.json 壞掉時整支 crash，
    # main() 的 `for e in errs: print(e)` 永遠到不了 —— check_version 與
    # check_marketplace_sync 已寫進 errs 的 ::error 一條都印不出來（GitHub 只拿到裸
    # traceback、零 annotation），而且後面兩項檢查整段被跳過。同一支檔案的其他函式
    # 都小心地把 JSONDecodeError 收成 errs，唯獨這裡沒有。
    # #33 verify R10：R9 把三個站點改走 load_obj，**漏了 check_bumped 裡的這兩個** ——
    # 非 dict 的 plugin.json 仍在 `.get()` 上拋 AttributeError、整支 crash，
    # 已累積的 ::error 一條都印不出來。同一個 commit 裡還在隔壁替 pack_name 加了
    # isinstance 守衛，可見想到過這件事，只補了一處。`load_obj` 的 `is_text` 參數
    # 正是為此而加，而它在 R9 出貨時**零呼叫端使用**。
    now_obj = load_obj(cur.stdout, pj, errs, is_text=True)
    if now_obj is None:
        return
    now = now_obj.get("version", "")
    old = subprocess.run(
        ["git", "show", f"{cmp_base}:{pj_rel}"],
        cwd=repo, capture_output=True, text=True)
    if old.returncode != 0:
        # #33 verify R7：先前一律說「本次在新增整個 pack…這是唯一合法的略過情境」——
        # **pack 改名的那個 commit 也走這條**，而那不是新增。先在 base 的樹裡找同名 pack；
        # 找得到就是改名，用它的舊路徑比對，閘門照跑。找不到才是真的新增。
        moved = moved_pj
        if moved:
            print(f"note: pack 在 base 時位於 {moved}（本次改名為 {pack_rel}）—— 用舊路徑比對版本")
            old = subprocess.run(["git", "show", f"{cmp_base}:{moved}"],
                                 cwd=repo, capture_output=True, text=True)
            if old.returncode != 0:
                errs.append(f"::error::讀不到 base 上的 {moved} —— bump 檢查沒有跑")
                return
        else:
            print(f"note: base（{cmp_base[:12]}）的樹裡找不到名為 '{pack_name}' 的 pack —— "
                  "本次在新增整個 pack，無前一版可比。這是唯一合法的略過情境")
            return
    prev_obj = load_obj(old.stdout, f"{cmp_base[:12]}:{pj_rel}", errs, is_text=True)
    if prev_obj is None:
        return
    prev = prev_obj.get("version", "")
    tn, tp = version_tuple(now), version_tuple(prev)
    if tn is None or tp is None:
        errs.append(f"::error file={pj}::版本字串不是 semver（base={prev!r}、現在={now!r}），無法比較")
    elif tn <= tp:
        errs.append(
            f"::error file={pj}::lenses/ 改了（{wc(', '.join(real))}）"
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
    # #33 verify R10：R9 的 symlink 守衛只作用在 lenses/ 的**直接條目**上，`lenses/` 目錄
    # **自己**是 symlink 時整個逃逸 —— 實測把它指向 repo 外的目錄，validator 會把該目錄的
    # 檔名逐一印進 CI annotation，並讀取其中的檔案、把第一行內容印出來。
    # 「同類洞只修一半」在同一輪裡又發生一次；`_inside` 已是現成的共用函式。
    repo_for_containment = repo_root(root)
    if repo_for_containment is not None:
        repo_abs = repo_for_containment.resolve()
        if not _inside(d.resolve(), repo_abs):
            errs.append(f"::error::{d.relative_to(root)} 解析後落在 repo 外"
                        "（可能是 symlink）—— 拒絕讀取。validator 只能讀本 repo 內的 lens")
            return []
    if not d.is_dir():
        errs.append(f"::error::找不到 {d} —— 空的 pack 不貢獻任何東西")
        return []
    good = []
    for p in sorted(d.iterdir()):
        rel = p.relative_to(root)
        # #33 verify R6：先前用 `p.suffix != ".csv"` 判定，而 pathlib 對 dotfile 回傳空
        # suffix（`Path(".DS_Store").suffix == ""`）→ 一個 .DS_Store 就讓整支 exit 1，
        # 訊息還說它是「大小寫不同的 csv」。本 pack 自己的 .gitignore 就只有 .DS_Store
        # 一行 —— 作者清楚知道 macOS 會生成它；CI 是乾淨 checkout 永遠碰不到，
        # 只有「貢獻者本機跑同一支」這條本 PR 主打的路徑會被卡死。
        # #33 verify R9：但 R6 的修法是「所有 dotfile 一律忽略」—— 一個總括判準吃掉了
        # 一個封閉列舉（正是 rules/common-spec-prose-enumeration.md 點名的形狀）。
        # `.lecture.csv` 這種明顯是 lens 的檔案會靜默消失：consumer 不載入隱藏檔，
        # 而 validator 因為 good 非空仍然 exit 0。改成白名單 OS artifact。
        if p.name in OS_ARTIFACTS:
            continue
        if p.name.startswith(".") and p.suffix == ".csv":
            errs.append(f"::error file={rel}::隱藏的 .csv —— consumer 只讀 "
                        "lenses/<profile>.csv，點開頭的檔案不會被載入。"
                        "要嘛改名（去掉前面的點），要嘛刪掉")
            continue
        if p.name.startswith("."):
            emit(f"::warning file={rel}::lenses/ 下有不認識的隱藏檔 —— 已略過。"
                  "若它其實是 lens，改名（去掉前面的點）才會被載入")
            continue
        # #33 verify R9：`check_marketplace_sync` 花了兩輪把 containment 修到「實際要讀的
        # 那個檔」，但**同一支檔案讀 lens CSV 的路徑完全沒有對應防護** —— 檔案型 symlink 的
        # `is_dir()` 為 False、suffix 為 `.csv`，直接進 good，隨後 `path.open()` 跟隨到
        # repo 外。此 job 掛在 `on: pull_request`，fork 完全控制 repo 內容；而
        # 「header 必須含 key 與 focus（現在是 {fieldnames}）」這類訊息還會把目標檔第一行
        # 原文印進 CI annotation。同類洞只修一半，正是本 PR 反覆出現的形狀。
        if p.is_symlink():
            errs.append(f"::error file={rel}::lenses/ 下不能有 symlink —— "
                        "它會讓 validator 讀到 repo 外的檔案，並可能把該檔內容印進 CI log")
            continue
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


def builtin_lens_keys(repo, errs):
    """{profile: {lens key, …}}，取自 `references/builtin-lenses.csv`。讀不到就**報錯**。

    #33 verify R7：先前讀不到回 `None`，呼叫端 `if builtin_keys is not None:` 於是整段
    撞名判定跳過、**一個字都不印**，還印「N 條 lens ✓」exit 0 —— 一道剛立起來的閘門，
    守不守得住取決於另一個檔案讀不讀得到，而失敗方向是肯定式綠燈。R6 在**同一個 commit**
    裡才剛把 `pai-list-profiles` 的「工具不見了」從靜默升級為 hard error，理由逐字適用於
    這裡，卻沒有一併改。第二條路徑更隱蔽：檔案讀得到但 header 缺 `profile` 欄時回的是
    `{}` 而非 `None`，連上面那個保險都不觸發，每一列都被判為「沒撞名」。

    **為什麼這裡可以用那份投影，而 profile 存在性不行**（#33 verify R6，兩者不矛盾）：
    該檔由 `regen-builtin-lenses.sh` **逐 lens** 產生 —— 一條 lens 一列。所以
    `lenses: []` 的 profile（`custom`）在裡面一列都沒有，拿它問「這個 profile 存在嗎」
    必定答錯（那要問 `bin/pai-list-profiles`）；但問「這個 profile 有哪些 lens key」時，
    沒有列 == 沒有 lens == 沒有東西可撞名，答案是對的。CI 有 drift 檢查守它的新鮮度。"""
    if repo is None:
        return None
    cat = repo / "plugins" / "parallel-ai-agents" / "references" / "builtin-lenses.csv"
    # #33 verify R10：同一個洞的第三個站點 —— catalog 的讀取先前也沒有 containment，
    # 把它指到任意檔案同樣會被讀，且 header 缺欄時錯誤訊息會把該檔第一行解析結果印出來。
    if not _inside(cat.resolve(), repo.resolve()):
        errs.append("::error::builtin-lenses.csv 解析後落在 repo 外（可能是 symlink）—— "
                    "拒絕讀取。撞名閘門沒有跑")
        return None
    if not cat.is_file():
        errs.append(f"::error::找不到 {cat.relative_to(repo)} —— **撞名閘門沒有跑**"
                    "（這不是「沒有撞名」）。與 built-in 同 key 且未標 override 的 lens 會被 "
                    "harness 判為 ignored、一個 agent 都不會派")
        return None
    out = {}
    try:
        with cat.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            fields = list(reader.fieldnames or [])
            if "profile" not in fields or "key" not in fields:
                errs.append(f"::error file={cat.relative_to(repo)}::header 缺 profile 或 key 欄"
                            f"（現在是 {fields}）—— 撞名閘門沒有跑。這個檔由 "
                            "references/regen-builtin-lenses.sh 產生，格式變了要同步改這裡")
                return None
            for r in reader:
                prof = (r.get("profile") or "").strip()
                key = (r.get("key") or "").strip()
                # 檔頭的 GENERATED 註解列會被 DictReader 當成資料列（CSV 無註解語法）。
                if not prof or prof.startswith("#") or not key:
                    continue
                out.setdefault(prof, set()).add(key)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        errs.append(f"::error file={cat.relative_to(repo)}::讀取失敗：{e} —— 撞名閘門沒有跑")
        return None
    if not out:
        errs.append(f"::error file={cat.relative_to(repo)}::解析出 0 條 built-in lens —— "
                    "撞名閘門形同虛設（catalog 空了或格式變了）")
        return None
    return out


def check_csvs(root, errs, files):
    repo = repo_root(root)
    builtin_keys = builtin_lens_keys(repo, errs)
    known_profiles = None
    if repo is not None:
        lister = repo / "plugins" / "parallel-ai-agents" / "bin" / "pai-list-profiles"
        # #33 verify R6：先前「工具不存在」是唯一的靜默路徑 —— known_profiles 留 None，
        # 下面的 profile 名稱閘門整條蒸發且一個字都不印。同一支檔案對「拿不到 base ref」
        # 與「工具跑失敗」都是 hard error，唯獨「工具不見了」靜默，語意不一致。
        # 而 bin/pai-list-profiles 正是本 PR 新加的檔案，被改名／搬走完全可能。
        if not lister.is_file():
            errs.append(f"::error::找不到 {lister.relative_to(repo)} —— profile 名稱閘門沒有跑"
                        "（這不是「檔名都合法」）。它是 PROFILES 的唯一真源查詢入口")
        else:
            r = subprocess.run(["bash", str(lister)], capture_output=True, text=True)
            if r.returncode != 0:
                errs.append(f"::error::無法取得 PROFILES 清單：{r.stderr.strip()}")
            elif not r.stdout.split():
                # rc=0 但空輸出 → known_profiles 會是空 set，於是**每一個** CSV 都被報
                # 「不是既有 profile（真源 PROFILES 有：）」，清單還是空的 —— 讀者無從判斷
                # 是自己寫錯還是抽取壞了。空輸出必然是抽取壞了，直接說。
                errs.append("::error::pai-list-profiles 成功結束但沒有輸出任何 profile —— "
                            "PROFILES 抽取壞了（harness 的區塊分隔線可能變了），閘門沒有跑")
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
            errs.append(f"::error file={rel}::header 必須含 key 與 focus（現在是 {wc(fieldnames)}）")
            continue
        dupes = sorted({c for c in fieldnames if fieldnames.count(c) > 1})
        if dupes:
            errs.append(f"::error file={rel}::header 有重複欄位 {wc(dupes)} —— "
                        "後出現的會靜默覆蓋先出現的，你以為填了的值會消失")
            continue
        unknown = [c for c in fieldnames if c not in KNOWN_COLS]
        if unknown:
            errs.append(f"::error file={rel}::header 有不認識的欄位 {wc(unknown)}"
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

        # #33 verify R6：先前完全沒有撞名檢查。harness 的合成邏輯對**未標 override** 的
        # 撞名是 `action: 'ignored'` —— 那條 lens 不會被派任何 agent。實測一個含
        # 「與 built-in 同 key」+「檔內重複 key」的 CSV：validator 印「3 條 lens ✓」exit 0，
        # 而三條裡只有一條會真的跑。貢獻者正確 bump、CI 全綠、PR merge、使用者收到新版 ——
        # 那條 lens 從來沒出現在任何審閱裡。這是本 PR 想鋪的貢獻路徑上最可能發生的安靜失敗
        # （新手最容易挑一個現成的 lens 名字），而判定所需的資料就在同一棵樹裡。
        seen_keys = {}
        dup = []
        for i, r in enumerate(rows, start=2):
            k = (r.get("key") or "").strip()
            if k in seen_keys:
                dup.append(f"第 {i} 列的 '{k}'（與第 {seen_keys[k]} 列重複）")
            else:
                seen_keys[k] = i
        if dup:
            errs.append(f"::error file={rel}::同一檔內 key 重複：{wc('、'.join(dup))} —— "
                        "後面那條會被 harness 判為 ignored、一個 agent 都不會派，"
                        "但這個檔案看起來仍有那麼多條 lens")
            continue
        if builtin_keys is not None:
            clash = sorted(
                k for k, i in seen_keys.items()
                if k in builtin_keys.get(profile, set())
                and not _truthy(rows[i - 2].get("override"))
            )
            # #33 verify R7：標了 override 的撞名先前**完全不出聲**（連 warning 都沒有）——
            # 一個純資料 PR 就能讓 built-in 的 `security` lens 從所有人的審閱裡消失，
            # 而 CI 只印「N 條 lens ✓」。閘門保證那個決定是顯式的，但顯式 ≠ 被看見；
            # reviewer 需要在 CI log 裡看到「這個 PR 刪掉了哪一條」。
            overriding = sorted(
                k for k, i in seen_keys.items()
                if k in builtin_keys.get(profile, set())
                and _truthy(rows[i - 2].get("override"))
            )
            if overriding:
                emit(f"::warning file={rel}::這個 PR 會**取代** built-in lens {overriding}"
                      f"（profile '{profile}'）—— 原本那條會從所有使用者的審閱裡消失。"
                      "請以「刪除既有 lens 的 PR」的標準審查：PR 描述必須說明原本那條為何不夠用")
            if clash:
                errs.append(
                    f"::error file={rel}::{clash} 與 built-in 的同名 lens 撞名，且未標 override "
                    f"—— harness 會判為 ignored，這些 lens 一個 agent 都不會派。"
                    "要嘛改名，要嘛標 override=true 並在 PR 說明為何原本那條不夠用"
                    "（override 會讓一條調校過的 built-in lens 消失，等於替所有人做這個決定）")
                continue

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
            emit(f"::warning file={rel}::profile '{profile}' 沒有 ensemble-{profile}-review "
                  f"這支專屬 skill —— 這裡的 lens 只會在 /ensemble-compose --base {profile} "
                  f"時被載入")
        elif wired is False:
            emit(f"::warning file={rel}::在 `/{own}` 的 SKILL.md 裡找不到 "
                  f"pai-collect-lens-layers 的呼叫 —— 若確實沒接，這裡的 lens 不會出現在"
                  f"它的審閱裡，只會在 /ensemble-compose --base {profile} 時被載入"
                  f"（那是該 skill 的接線缺口，追蹤於 #40，不是本 pack 的問題）。"
                  f"**本檢查是掃 SKILL.md 文字的啟發式，可能誤判，請人工確認**")

        for r in rows:
            for col in ("override", "needsSrt"):
                raw = (r.get(col) or "").strip().lower()
                if raw and raw not in TRUTHY + FALSY:
                    emit(f"::warning file={rel}::{col}='{wc(r[col])}' 不是可辨識的真假值 —— 會被當成 false")


EVENTS = ("pull_request", "push", "workflow_dispatch")


def main():
    # #33 verify R9：手寫的 argv 解析有一串洞，而每一個洞的後果都是**安靜地換掉判準**：
    #   - 位置參數完全不檢查 —— 漏打 `--event`（`--base <sha> push`）時 `push` 被丟棄、
    #     event 變 None → 走 merge-base 而非 exact-tree。實測在 force-push 情境下印出
    #     `無需 bump ✓` exit 0，而正確呼叫報「版本沒有增加」exit 1。**R5 修掉的漏檢
    #     經由 argv 層原樣復活。**
    #   - 旗標值不檢查是不是另一個旗標 —— `--event --base <sha>` 讓 event 變成字串
    #     `"--base"`，仍然「合法」。
    #   - `--event` 的值不受任何約束 —— `--event pusch` 靜默走非 push 語意。
    #   - 重複旗標只取第一次，其餘靜默忽略。
    # R8 只讓未知**旗標**（`-` 開頭）fail-loud，那是同一個缺陷的一半：workflow 實際傳的
    # 是旗標**值**，而值那一側仍然靜默。改用 argparse 並對 --event 設 choices，
    # 未知旗標／未知位置參數／缺值／非法 event 全部由它回 2。
    ap = argparse.ArgumentParser(
        prog="validate.py", add_help=True,
        description="驗證這個 lens pack 可被 parallel-ai-agents 正確消費。")
    ap.add_argument("--base", metavar="<ref>",
                    help="判斷「改了 lens 卻沒 bump」的比較基準（CI 傳 PR base 或 push 的 before SHA）")
    ap.add_argument("--event", metavar="<github-event-name>", choices=EVENTS,
                    help=f"觸發事件名（{' / '.join(EVENTS)}）。決定 base 的比較語意，"
                         "以及拿不到 base 時該報錯還是留紀錄")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        # argparse 對用法錯誤回 2、對 --help 回 0；兩者都照它的意思走。
        return e.code if isinstance(e.code, int) else 2
    base, event = args.base or None, args.event
    root = pathlib.Path(__file__).resolve().parent.parent
    errs = []
    check_version(root, errs)
    check_marketplace_sync(root, errs)
    check_bumped(root, errs, base, event)
    files = check_lens_dir_shape(root, errs)
    if files:
        check_csvs(root, errs, files)
    for e in errs:
        emit(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
