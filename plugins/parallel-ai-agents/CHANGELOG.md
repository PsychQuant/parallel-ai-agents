# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> ⚠ This file was bootstrapped by `changelog-tools:changelog-init` from the
> `plugin.json` description field. Section categorization is best-effort —
> review and refine `Added` / `Changed` / `Fixed` etc. as needed.

## [Unreleased]

## [2.24.0] - 2026-09-10

`pai-lenses` 從獨立 repo 併回本 repo 成為第二個 plugin，並把三層 lens 疊加的文件與 CI 閘門補齊。

> **範圍說明**：本版**不含**層 ③ 的自動回流工具。它原本在同一個 PR 裡，經多輪 6-AI verify
> （HIGH 數 15 → 18 → 32 → 14 → 15 → 4 → 3 → R8 降級 → 11 → 7 → …，逐輪見下方各 Fixed 段；R8 只有 1/6 agent 完成，
> 不計入序列但其 CRITICAL 已修。R9 的 11 個 HIGH 偏高是因為四個 core lens **從未審過**
> R8 之後新增的 `scripts/`，那是那批程式碼的第一次真正審閱）後拆出到 **#39**。R3 的 32 個 HIGH 有 **29 個**落在
> 回流工具上；剩下 3 個在 `validate.py`（**本版出貨的內容**，已於 R4 修掉）。
> 收斂之後的 R4／R5／R6／R7／R9 共 47 個 HIGH **全部**落在本版出貨的內容裡並已逐條修掉 ——
> 也就是說「另一半很乾淨」從來不是收斂的理由（見下方 Fixed 段）。理由是**缺陷密度差了
> 一個量級**，且回流工具連三輪不收斂（每輪的修法都讓 HIGH 變多）。拆開之後：使用者現在
> 裝得到層 ②，回流工具在自己的 issue 裡從頭想。三輪換來的 29 條缺陷清單已逐條寫進 #39 當規格。
> #33 的另外兩項待決需求（user 層單檔 vs 一檔一 profile、公共層更新後的 reverse 提示）
> **不在 #39 範圍內**，已另開 **#41**；層 ① 的 lens 沒有 bump 閘門則是 **#42**。

### Changed

- **`pai-lenses` 併回 `plugins/pai-lenses/`**（`git subtree`，保留其 3 個原始 commit）。
  marketplace source 由 `{"source":"github",...}` 改為 `./plugins/pai-lenses`，與主 plugin 一致。
  併回理由：`bin/pai-collect-lens-layers` 的 `PACK_PLUGIN` 寫死單一 pack 名、只 glob `*/pai-lenses`，
  架構只認一個官方 pack，「讓第三方各自發 pack」的分離理由不成立；且層 ③ 要回流時，
  判定目標層與開 PR 都得跨兩個 repo。舊 repo 已封存並在 README 指向新位置。
- 其 `validate.yml` 併入 root `test.yml` 為獨立 job（`manifests-and-lens-pack`）——
  併入後落在 `plugins/` 下的 workflow 不會被 GitHub 執行，故移除以免誤導。
- **主 plugin 的 `description` 不再累積歷代 release note**，只保留功能敘述 + 當版一行。
  > **揭露（#33 verify R10 M9）**：這個動作刪掉了 v2.19.0–v2.22.0 之間的版號註記（兩份 manifest 在 base 上各四段且不一致：marketplace.json 領頭 v2.21.0、plugin.json 領頭 v2.22.0——正是 R11 抓到的不同步；聯集五個版號），而那些是使用者
  > 在 `/plugin` 清單裡看得到的唯一版本說明（CHANGELOG 不在 plugin UI 裡）。先前 Fixed 段
  > 只寫「接回功能敘述」，讀起來像單純還原，**沒有揭露刪除** —— 本 PR 一路在抓的
  > 「修一半的宣稱」在變更紀錄層的鏡像。歷史註記從此以 CHANGELOG 為準。
  > 本 PR 新立的 description-drift 閘門對此結構上是盲的（它只比對兩份是否相同）。

### Added

- **`bin/pai-list-profiles`** — 印出 `PROFILES` 的 profile key。**profile 的存在性必須查真源**：
  `references/builtin-lenses.csv` 是**由 lens 產生**的投影，`lenses: []` 的 profile（`custom`）
  在裡面一列都沒有。拿投影問存在性對 `custom` 必定答錯。
- **root `README.md` 補上 `pai-lenses` 的安裝路徑**（先前完全沒有）。舊 repo 封存後，
  README 是唯一的入口 —— 沒寫等於使用者裝不到層 ②，而沒裝時 collector 回 `absent`
  （靜默、依設計不警告），整個層 ② 會安靜地不存在。
- **`references/lens-layers.md` 的「我想加一條 lens，該去哪」決策表**（四種情況直接對到動作）。
- **`plugins/pai-lenses/scripts/validate.py` 的機械閘門**，先前都只寫在散文裡：
  - `check_marketplace_sync` — **雙向**：每一個相對路徑 plugin 的 `plugin.json` 與 marketplace
    entry 版本必須一致（不只 `pai-lenses`；主 plugin 先前完全沒有閘門），且每一個
    `plugins/*/` 目錄都必須有 entry 指向它。路徑一律做 containment 判定，且判定的是
    **實際要讀的那個檔**而非它的祖先目錄
  - `check_bumped` — 改了 `lenses/*.csv` 就必須 bump（相對 base ref 增加）。
    equality 守得住「同步」，守不住「有 bump」。**git 跑不起來時報錯而非略過** ——
    「閘門沒跑」與「無需 bump」是兩回事
  - `check_csvs` 內的 profile 檢查 — CSV 檔名必須是既有 profile（真源查 `bin/pai-list-profiles`）；
    並對「lens 進不到該 profile 專屬 skill」的情況發警告：`minutes` **有**專屬 skill
    （`/ensemble-minutes-review`，v2.22.0 出貨）但尚未呼叫 collector（接線缺口，追蹤於 #40），
    `general` / `custom` 則本來就沒有專屬 skill。兩種情況下該 profile 的層 ②③ lens 都只在
    `/ensemble-compose --base <profile>` 生效。**這個警告是掃 SKILL.md 文字的啟發式，
    可能誤判**（R5 實測：註解掉的呼叫會被判成沒接、散文提及會被判成已接），訊息本身有標注
  - CSV 形狀：未知 header 欄（`overide` 這種 typo 會讓整欄靜默失效）、缺 `key`/`focus` 的列、
    整份複製 catalog 造成的欄位錯位，全部改為 error
- CI 帶 `--base` 並改 `fetch-depth: 0` —— 預設 shallow clone 會讓 `git diff base...HEAD` 失敗，
  bump 檢查會安靜地不存在。

### Fixed

- **測試 harness 自己的三個脆弱點**（#33 verify R9 MEDIUM）：`Fixture` 的複製清單寫死
  （新增第三個 plugin 會讓**所有 assertGreen 同時轉紅**，訊息還指著真實 repo 裡存在的路徑 ——
  諷刺的是那正是 root `CLAUDE.md` 這次的賣點「新增第三個 plugin 時自動涵蓋」：閘門會，
  harness 不會）；`seen == 0` 那條測試把 plugin 名寫死；`pai-collect-lens-layers.bats` 檔頭的
  鐵律「絕不讀真實 lens pack」在同一個 commit 新增的整合錨點裡就已為假。
  **一句已經為假的不變式比沒有更糟** —— 下一個人會據以判斷而繞路。三處都改了。
- **CI 新增 `mutation_check.py --check-targets`**（#33 verify R9 M11/M24）。完整量測太慢
  （靶數 × 全套 ≈ 30–60 分鐘）不進 CI，但**靶清單相對 `validate.py` 的漂移**秒級就能擋：
  改動被 mutate 的那幾行、或搬走一道閘門，靶就對不上。先前這件事只有在有人手動跑整輪時
  才會發現，而「忘了跑」是預設。
  > **量測（R9 後）：46 個靶 → 45 殺掉 / 1 存活 / 0 靶壞**（R8 後是 35 殺 / 1 存活 / 0 靶壞；
  > 當時的靶總數本段兩處分別記成 36 與 37，已無法重建 —— #33 verify R11 抓到這個矛盾。判準
  > 是跑一次 `mutation_check.py`，不是這張表）。R10／R11 後的數字見下方各輪。
  > R9 那一輪唯一存活的「catalog 缺檔」經實測確認是 equivalent mutant；R8 那一輪的五個存活裡有三個是
  > **真缺口**（行為確實不同），已逐條補測試 —— 判讀靠實測不靠推論。（R12 指出這兩句先前沒標輪次，
  > 讀起來像同一次量測自相矛盾。）

- **R9 的兩個修正又是半成品**（#33 verify R10 HIGH）—— 而且是**同一輪之內**沒掃到手足：
  - `load_obj()` 只改了三個 JSON 讀取點，**漏了 `check_bumped` 裡的兩個**。非 dict 的
    plugin.json 仍讓整支 crash、零 annotation。同一個 commit 裡還在隔壁替 `pack_name` 加了
    `isinstance` 守衛 —— 想到過，只補了一處。`load_obj` 的 `is_text` 參數正是為此而加，
    而它在 R9 出貨時**零呼叫端使用**。
  - symlink 守衛只作用在 `lenses/` 的**條目**上，**目錄自己是 symlink 時整個逃逸** ——
    實測會把 repo 外目錄的檔名逐一印進 CI annotation，並讀取其中的檔案把第一行印出來。
    第三個站點在 catalog（`builtin-lenses.csv`）的讀取。三處現在都做 `_inside` 判定。
- **`version_tuple` 的 R9 註解對自己的守備範圍作了假陳述**（#33 verify R10 HIGH）。
  它寫「`1.0.0-rc10 → 1.0.0-rc9` 的閘門逃逸現在修掉了」—— **實測兩個方向一個都沒變**：
  `rcN` 是單一個 alphanumeric identifier，逐 identifier 比較之後仍落在同一個 ASCII 比較上，
  與 R7 的整段字串比較逐字等價。就 semver 2.0.0 而言那是**對的**（`rc9 > rc10`），
  所以程式碼不改；改的是註解，並新增 warning 把 `rcN` 這個陷阱顯性化
  （`rc9 → rc10` 這個正常的遞增發布會被 bump 閘門擋下，請改用 `rc.9` / `rc.10`）。
- **兩道閘門出貨時零鑑別力**（#33 verify R10 HIGH，DA 抓到）：`check_version` 自己的 semver
  閘門被 `check_marketplace_sync` 的同類檢查遮蔽（整道拿掉，57/57 全綠）；
  `OS_ARTIFACTS` 白名單的測試只斷言 rc=0，**從不斷言「靜默」**（拿掉白名單，`.DS_Store`
  改成印一則 warning，rc 仍是 0）。兩者現在斷言的是**只有它會印的那句話**與**靜默本身**。
- **`lenses/` 純改名被誤判為「改了但沒 bump」**（#33 verify R10 M3）。改名偵測先前只讓
  「舊版本」那一側 rename-aware，**變更清單那一側仍用新路徑** —— 同一次執行裡
  rename-aware vs rename-blind，與 R5/R6 反覆在修的「兩個基準」同形。
  > 連帶更正一條測試：`test_pack_rename_…` 先前斷言純改名應該 `rc=1`「版本沒有增加」——
  > **它把這個假陽性寫成了預期行為**。M3 修掉之後那條斷言必須跟著翻面。
- **未消毒的 PR 內容可注入 GitHub workflow command**（#33 verify R10 M8）。CSV 的引號欄位
  可含真正的換行，於是能多出一行 `::stop-commands::` —— runner 會**停止解析後續所有
  workflow command**，包含 validator 自己排隊的每一條 `::error::`。job 仍紅，但 PR 上零
  annotation：把本 PR 一路在建的 **fail-loud 降級成 fail-silent**；還能偽造指向無辜檔案的
  annotation。

  > **作者自查的更正**：R10 的第一版修法是在**個別呼叫點**包 `wc()` —— 我包了六處，
  > 而枚舉之後發現**約四十處**插入了攻擊者可控的值（git 檔名可以含換行、marketplace.json
  > 的字串、CSV 衍生的 key 與欄位…）。**那個修法本身就是本 PR 一路在抓的「同類只修一處」，
  > 只是規模更大。** 正確的形狀是在**邊界**消毒：workflow command 必須從**行首**開始解析，
  > 所以只要保證「一行永遠是一行」就夠了。現在所有 `::error` / `::warning` / `::notice`
  > 都走唯一的出口 `emit()`，一個地方做完，不需要再問「我有沒有漏掉某個站點」。
  > 新增的測試走**檔名**這條先前完全沒防到的路徑（`wc()` 版本擋不住它）。
- **反向檢查的訊息會把人導向錯誤的修法**（#33 verify R10 M4）。entry 的 source 形式不合時
  （打錯路徑、dict 缺 `path`），先前報「marketplace.json 裡沒有指向它的 entry」——
  **那句話會讓維護者再加一條 entry**，而真正的問題是既有那條寫錯了。現在按**名字**交叉比對後
  說出真正的原因；真的缺 entry 時訊息不變。
- **設計 spec 加上 superseded banner**（#33 verify R10 HIGH ×2）。
  `docs/superpowers/specs/2026-07-29-lens-pack-externalization-design.md` 的狀態仍寫
  「設計已確認…待寫實作計畫」，而它的 **D1（獨立 repo）／D7（平行 repo）已被本 PR 推翻**，
  連 D7 反駁欄的「CI 整合測試不應吃真實 lens repo」也被本 PR 新增的整合錨點推翻。
  更糟的是 `lens-layers.md` 仍把它指為契約來源。兩處都已標註。
  這正是本 PR 自己寫下的判準：**一句已經為假的不變式比沒有更糟**。
- **`mutation_check.py` 自己的三個問題**（#33 verify R10 M5/M6）：`--check-targets` 對特殊靶
  只驗了兩個 anchor 的其中一個、且沒驗唯一性（而未驗的那個是一句**註解**）；
  它自己還在用 R9 剛從 `validate.py` 拆掉的手寫 argv 解析（打錯旗標會靜默忽略，
  然後直接跑 30–60 分鐘的就地改寫迴圈）。兩者都改。

- **argv 解析改用 argparse**（#33 verify R9 HIGH）。手寫解析的每一個洞，後果都是**安靜地
  換掉判準**，而 R8 只修了「未知**旗標**」那一半 —— workflow 實際傳的是旗標**值**。
  實測：漏打 `--event`（`--base <sha> push`）時 `push` 被當位置參數丟棄、event 變 `None`
  → 走 merge-base 而非 exact-tree，在 force-push 情境下印出 `無需 bump ✓` exit 0，
  而正確呼叫報「版本沒有增加」exit 1。**R5 修掉的漏檢經由 argv 層原樣復活。**
  另外 `--event --base <sha>` 會讓 event 變成字串 `"--base"`、`--event pusch` 靜默走非
  push 語意、重複旗標只取第一個。現在未知旗標／未知位置參數／缺值／`--event` 不在
  `choices` 內全部 exit 2。`--event` 的語意分流本身也補了雙向測試（先前**零覆蓋**）。
- **合法 JSON 但型別不對的 manifest 不再讓 validator crash**（#33 verify R9 HIGH）。
  R6 M5 的修正與其測試都只覆蓋**語法**壞掉的 JSON；`[]` / `"x"` / `3` 會在 `.get()` 上拋
  `AttributeError`，不在任何 `except` 裡 → 整支 crash，`main()` 印 errs 的迴圈永遠到不了。
  後果與 R6 M5 逐字相同（GitHub 只拿到裸 traceback、零 annotation）。**同一個缺陷的第二個
  站點**，三處讀取都改走共用的 `load_obj()`，並驗 `plugins` 是 list、其元素是 dict。
- **`lenses/` 的讀取面補上 containment**（#33 verify R9 HIGH）。`check_marketplace_sync`
  花了 R5→R6 兩輪把 containment 修到「實際要讀的那個檔」，而**同一支檔案讀 lens CSV 的
  路徑完全沒有對應防護** —— 檔案型 symlink 的 `is_dir()` 為 False、suffix 是 `.csv`，
  直接被當成 lens 讀進去。此 job 掛在 `on: pull_request`，fork 完全控制 repo 內容，
  而「header 必須含 key 與 focus（現在是 …）」這類訊息會把目標檔第一行印進 CI annotation。
  已驗證修正後目標檔內容不會外洩。
- **dotfile 從「一律略過」改為白名單**（#33 verify R9 HIGH）。R6 為了修 `.DS_Store` 的假陽性
  套了總括判準，於是 `.lecture.csv` 這種明顯是 lens 的檔案會**靜默消失**（consumer 不載入
  隱藏檔，而 validator 因為 `good` 非空仍 exit 0）—— 一個總括判準吃掉封閉列舉，
  正是 `common-spec-prose-enumeration.md` 點名的形狀。現在只略過已知 OS 產物，
  隱藏的 `.csv` 報錯，其他未知隱藏檔印 warning。
- **marketplace entry 的身分納入判定**（#33 verify R9 HIGH）。先前 `entry.get("name")`
  **只出現在錯誤訊息字串裡，從未參與判定** —— 把 name 刪掉或打成 `pai-lense`，版本與路徑
  都對，validator 印 ✓、反向檢查也因目錄已被 claim 而通過，而使用者裝不到。
  現在要求 entry name 非空且等於該 `plugin.json` 的 `name`，並檢查 name 與 source 路徑各自唯一。
- **semver 改用官方文法 + `fullmatch`，prerelease 依 §11 逐 identifier 比較**
  （#33 verify R9 HIGH）。先前的正則接受 `01.2.3`、`1.2.3-`、`1.2.3+`、尾端換行 ——
  而這道閘門的**整個理由**就是「cache 目錄名必須是 semver」。prerelease 先前整段字串比較，
  R7 的註解只承認了假失敗那一側（`rc9` vs `rc10`），沒承認**閘門逃逸**那一側。
  > 附帶更正：R9 把 `1.0.0-rc10 → 1.0.0-rc9` 列為「降版通過閘門」。**依 semver §11 那是
  > 正確行為** —— 含字母的 identifier 按 ASCII 比較，`rc10 < rc9`。正確的寫法是 `rc.9`／
  > `rc.10`（點分隔，數字段按整數比較），現在處理正確。照規格走，不照直覺改。
- **pack 改名偵測改用 git 的 rename detection**（#33 verify R9 HIGH）。R7 的版本只比
  `plugin.json` 的 `name`，而 validate.py **從頭到尾沒有任何地方驗證 `name`**。
  「目錄改名 + 同時改 plugin 名」（很常見的一個 PR）或 `name` 缺席時，偵測整條失效並印出
  「本次在新增整個 pack…**這是唯一合法的略過情境**」—— 那句話在這條路徑上是假的，
  會讓 reviewer 停止追問。現在先問 `git diff --name-status -M`，按**目錄**還原舊路徑
  （plugin.json 內容常跟著改而被判成 A+D，但同批其他檔案仍是 R100），git 認不出來才退回 name 比對。
- **pack README 的 lens 撰寫界線改為封閉列舉**（#33 verify R9 HIGH ×2）。同一份 README
  前面推薦「明講要用工具查證（用 Read/Grep 實際打開檔案核對）」，後面禁止「**任何**指向
  reviewer 自身行為的祈使句（讀取檔案、…）」—— 兩句互相抵消，而本 repo 出貨的唯一一條
  lens（`docs-vs-code`）正好踩在中間。README 自稱「在 #36 落地之前這一節是唯一的防線」，
  而一條由互斥規則構成的防線無法做任何判定。現在明列**四類禁止**（改變存取範圍或回報範圍：
  讀審閱標的外的路徑、指示不要回報某類 finding、輸出到別處、覆寫其他指令），
  並**明確允許**在審閱標的內用 Read/Grep 查證。判準是範圍有沒有被改變，不是語氣是不是祈使。
- **mutation harness 補上綠底線前置檢查與中斷保護**（#33 verify R9 MEDIUM）。測試套件本身
  是紅的時候，**每一個 mutation 都會被判為「殺掉」** —— harness 回報漂亮的「0 存活」而其實
  什麼都沒量到，那是它自己版本的「肯定式綠燈」。另外只有 `finally` 保護時，中斷會把
  `if False:` 留在正式的 `validate.py` 裡。靶清單也補上 R9 新增的十道閘門。
- **`main()` 未知旗標、`py_compile` 清單、pack README 的閘門表**三處都從「寫死清單」改掉
  （#33 verify R9 MEDIUM）：`mutation_check.py` 先前**在任何地方都沒被語法檢查**（改 glob）；
  README 的閘門表補上七道並改寫為「完整清單以 `scripts/validate.py` 為準」。

- **測試套件本身是套套邏輯 —— 已修，並改成可量測**（#33 verify R8 CRITICAL）。
  `Fixture.run()` 寫死 `GITHUB_ACTIONS=""`，而 `check_bumped` 的 no-base 分支順序是
  workflow_dispatch → **本機** → CI fail-loud，於是**每一條測試都走本機分支**，後面兩道
  全被吃掉：整段「拿不到 base → fail-loud」（R4 的頭號修正）可以換成無條件 `return`
  而 26 條全綠，而那條名義上守 workflow_dispatch 的測試實際命中的是本機分支。
  **它自己犯了它 docstring 裡批判的錯。** 現在 `Fixture.run(ci=)` 參數化，四條分支各有測試。
- **新增 `scripts/mutation_check.py`**（#33 verify R8）——「這套測試有多少鑑別力」先前只能
  靠作者宣稱，現在是可機械回答的問題：逐一關掉 `validate.py` 的每道閘門，看測試抓不抓得到。
  手動跑、不進 CI（37 個靶 × 全套 ≈ 5–8 分鐘，比照 `ensemble-eval` 的定位）。
  它明寫兩個誠實邊界：**存活 ≠ 一定缺測試**（可能是 equivalent mutant）、
  **只 mutate `if` 條件，零存活不等於測試完備**。並要求每個靶恰好命中一次 ——
  R7 踩過 `replace(old, new, 1)` 打到註解而非程式碼的坑。
- **測試從 26 條增為 46 條**（#33 verify R8）。R8 實測初版有 18 個閘門沒有測試網，逐一補上：
  版本同步（`CLAUDE.md` 標為 CRITICAL 的那條）、兩邊都缺 version、`seen == 0` 保險、
  description 漂移、header 重複欄位、focus 逗號未 quote（pack README 的頭號陷阱）、
  整份複製 catalog 的 header、0 條 lens、`key` 以 `#` 開頭、`lenses/` 下子目錄、大寫 `.CSV`、
  `lenses/` 目錄不存在、沒有合法 csv、lister rc=0 空輸出、catalog 解析出 0 條、
  truthy 無法辨識、未知旗標。**量測結果：35 殺掉 / 1 存活 / 0 靶壞**（靶總數當時記成 37，
  但 35+1+0=36，與上方另一處記的 36 對不上；R11 指出後不再宣稱那個總數），
  唯一存活經實測確認是 equivalent mutant。
- **`main()` 的未知旗標改為 `return 2`**（#33 verify R8）。先前靜默丟棄 —— 本檔花大量篇幅
  論證「靜默略過正是本 PR 一路在修的病」，未知旗標卻是唯一的例外：workflow 若把旗標打錯
  （`--events`），validate 會以「沒有 base」的姿態繼續跑，安靜地換掉判準。
- **pack 改名的測試補上 rc 斷言**（#33 verify R8）。先前只驗訊息措辭，而 CHANGELOG 宣稱的是
  「用舊路徑比對、**閘門照跑**」—— 把版本比對整段跳過，那條測試照樣綠。
- **pack README 的「CI 會檢查」清單補上最重要的兩道**（#33 verify R8）：改 lens 必 bump、撞名。
  諷刺的是本 PR 出貨的唯一一條 lens 就叫 `docs-vs-code`。

  > **更正（R9）**：這條原本寫「改成**完整**表格」—— 逐條對照後至少還漏七道
  > （子目錄、大寫 `.CSV`、目錄不存在、header 重複欄位、整份複製 catalog 的 header、
  > marketplace source 的 containment、lenses/ 下的 symlink 與隱藏 `.csv`）。
  > **補了兩道最重要的就宣告完整**，與 R8 那個 CRITICAL 是同一形狀的第三次。
  > 表格已補齊並改寫為「完整清單以 `scripts/validate.py` 為準」。

- **`validate.py` 補上自己的回歸測試**（#33 verify R7，`scripts/test_validate.py`，26 條）。
  它有十餘道閘門卻**零測試覆蓋** —— 所有錯誤分支只在 CI 的 happy path 被執行（也就是都沒被
  執行）。六輪 verify 有超過二十個 finding 落在這一支，反覆出現的形狀是「閘門在某條件下安靜
  蒸發並印肯定式綠燈」，那種缺陷用讀的抓不到。每條測試對應一個**真實發生過**的缺陷、斷言
  兩個方向。已接進 CI。
  （其中一個 mutation 一開始沒轉紅 —— 追下去發現是**我的 mutation 工具**打偏了：
  `replace(old, new, 1)` 命中的是註解裡的同一個字串。測試沒問題，靶錯了。）

  > **更正（R8）**：這條原本寫「十個 mutation 逐一確認轉紅」，而 `test.yml` 註解與
  > `test_validate.py` 開頭則寫「**都**做過 mutation」—— 兩者互相矛盾，而且都高估了。
  > R8 實測：**20 個閘門 mutation 有 18 個存活**，包含 `CLAUDE.md` 標為 CRITICAL 的版本
  > 同步閘門。見下方 R8 條目。
- **撞名閘門的真源讀不到時改為報錯**（#33 verify R7）。`builtin_lens_keys()` 先前在
  catalog 缺檔／讀取失敗時回 `None`，呼叫端 `if builtin_keys is not None:` 於是整段跳過、
  **一個字都不印**，還印「N 條 lens ✓」exit 0。R6 在**同一個 commit** 裡才剛把
  `pai-list-profiles` 的「工具不見了」從靜默升級為 hard error，理由逐字適用於這裡卻沒一併改。
  第二條路徑更隱蔽：header 缺 `profile` 欄時回的是 `{}` 而非 `None`，連那個保險都不觸發。
- **`claimed.add()` 移到所有 `continue` 之前**（#33 verify R7）。R6 把它放在 `..`／絕對路徑
  那道檢查**之後**，還在註解裡宣稱「順序是刻意的，避免反向檢查再罵一次」—— **那句是假的**：
  `source: "plugins/x/../x"` 會同時得到「只能用相對路徑」與「沒有指向它的 entry」兩則 error，
  後者是假訊息。R6 只測了 symlink 那條（它在登記之後）。
- **prerelease 納入版本排序**（#33 verify R7）。`version_tuple` 先前只取 major.minor.patch，
  於是 `0.3.0-rc1 → 0.3.0`（rc 轉正式，最典型的發布動作）與 `rc1 → rc2` 都被判為「版本沒有
  增加」。依 semver §11 讓 prerelease 排在同 core 正式版之前。（build metadata 仍不參與
  優先序 —— 那是 semver §10 的規定，`0.3.0+b1 → +b2` 判為非 bump 是正確的。）
- **pack 改名不再被誤報為「新增整個 pack」**（#33 verify R7）。改名的那個 commit 先前走
  「base 沒有 plugin.json」那條，還印「這是唯一合法的略過情境」—— 假的。現在先在 base 的樹裡
  找同名 pack，找得到就用舊路徑比對，閘門照跑。
- **semver 格式檢查涵蓋每一個 plugin**（#33 verify R7）。先前只有 pack 自己驗，主 plugin 的
  非 semver 版本一路綠燈 —— 與 root `CLAUDE.md`「這條對每一個 plugin 各自成立」不符。
- **`override` 掉一條 built-in lens 現在會印 warning**（#33 verify R7）。先前完全不出聲，
  一個純資料 PR 就能讓 built-in 的 `security` lens 從所有人的審閱裡消失，而 CI 只印
  「N 條 lens ✓」。閘門保證那個決定是顯式的，但**顯式 ≠ 被看見**。
- **全零 `event.before` 的訊息不再把責任推給 workflow**（#33 verify R7）。建立分支與 main
  被重建時它本來就是全零，那不是設定壞了 —— 先前的訊息會讓人去改一個沒有壞的地方。
- **主 plugin 的 description 接回功能敘述**（#33 verify R7）。本 PR 先前把它整段換成一行
  release note，於是使用者在 `/plugin` 看到的唯一說明是版本註記，不再說明這個 plugin 做什麼。
  那是搭 version bump 便車的 scope creep，且**本 PR 自己新增的 description-drift 警告對此是盲的**
  （它只比對兩份是否相同，對「兩份一起變得沒有資訊」無感）。
- **CI job 改名的另外三處引用**（#33 verify R7）：`CLAUDE.md`、`plugins/pai-lenses/README.md`、
  以及 CHANGELOG 自己的 Changed 段（它與同版 Fixed 段自相矛盾）。R6 只改了 workflow 那一側 ——
  **又一次「修一半」**。
- **`lens` 的 `focus`/`key` 是 prompt 權限，文件現在講明了**（#33 verify R7）。它們逐字進
  reviewer prompt 且**刻意不經 sentinel 包裹**，而 validator 只驗形狀、對語意零判斷 ——
  CI 綠燈不代表內容審過。`plugins/pai-lenses/README.md` 新增專節、`lens-layers.md` 同步。
  結構性修法（把 lens 文字也包進 sentinel）屬 lens 的信任模型，追蹤於 #36。

- **閘門的路徑與判準不再與位置耦合**（#33 verify R6 MEDIUM 批次）：
  - bump 檢查的 pack 路徑由 `root.relative_to(repo)` 導出，不再寫死 `plugins/pai-lenses/…`
    （實測改名後每一次 lens 變更都印「無需 bump ✓」而完全不受守護）
  - `--event` 缺省時改用 merge-base 語意。先前 exact-tree 讓「本機跑 `--base main`」在
    分岔分支上必定假失敗，訊息還指名一個該分支沒動過的檔案
  - `pai-list-profiles` 不存在或輸出為空時**報錯**，不再讓 profile 名稱閘門靜默蒸發
  - `lenses/` 下的 dotfile（`.DS_Store`）略過。先前一個 macOS 產物就讓貢獻者本機自檢 exit 1，
    而 CI 是乾淨 checkout 永遠碰不到 —— 只卡本 PR 主打的那條路徑
  - marketplace `source` 改為**正面判定相對路徑**且三態（是／明確遠端／判不出來→warning）。
    先前是「三個遠端前綴的白名單，其餘一律當本 repo 路徑」，`ssh://`、`github:owner/repo`、
    `file://`、`owner/repo` 全都會被誤判成缺檔而 hard error —— marketplace 一收錄第三方
    遠端 plugin，CI 就直接紅
  - `check_bumped` 的兩處 `json.loads` 包了 try。先前 plugin.json 壞掉會 crash，
    `main()` 印 errs 的迴圈永遠到不了 —— 前兩項檢查已寫進 errs 的 `::error` 一條都印不出來，
    GitHub 只拿到裸 traceback、零 annotation，後兩項檢查整段被跳過
  - 版本閘門補上 description 漂移偵測（warning）。本 PR 自己就製造了那個漂移，
    而剛立起來的閘門對它是盲的；補上後立刻抓到第二處（`pai-lenses` 也不同步），兩處皆已同步
- **`bin/pai-list-profiles` 補上回歸錨點**（#33 verify R6）。它是 PROFILES 的唯一真源查詢
  入口、靠 harness 的一行**註解**分隔線切段，出貨時卻零測試覆蓋 —— 而 profile 名稱閘門現在
  依賴它。五條測試全部做過 mutation：其中「涵蓋 `custom`」原本寫成子字串比對，
  把真源改成 `customXX` 照樣通過，已改為整行精確比對。
- **CI job 更名 `pai-lenses-validate` → `manifests-and-lens-pack`**（#33 verify R6）。
  它跑的 `check_marketplace_sync` 檢查的是 repo 內**每一個** plugin 的 manifest（含主 plugin），
  掛在以 pack 命名的 job 底下會讓人以為主 plugin 沒有版本閘門。
- **文件補上三個缺口**（#33 verify R6）：已安裝舊版 `0.1.0`（github source）者的遷移路徑
  （README，並誠實標注該路徑未實測）；`override` 在決策表的專屬一列與「預設不送、送就要舉證」
  的警告（`lens-layers.md`，對應 #33 (c) 的第三條判準）；**Backend B 吃不到層 ②③** ——
  舊版 Claude Code 沒有 `Workflow` tool 時會 fallback，那條路裝了 pack 也不生效且無警告，
  現在 `lens-layers.md` 與三支 skill 的 Backend B 段落都寫明了。
- **`check_marketplace_sync` 改為雙向**（#33 verify R6）。先前只從 marketplace entry 那側走，
  「entry 根本不存在」完全不涵蓋 —— 實測把 `pai-lenses` 整條 entry 刪掉，validator 印
  `marketplace 版本一致：parallel-ai-agents 2.23.0 ✓` 並 exit 0，而使用者直接裝不到。
  現在另從檔案系統枚舉 `plugins/*/.claude-plugin/plugin.json`，每一個都必須有 entry 指向它。
- **containment 檢查移到「實際要讀的那個檔」上**（#33 verify R6）。R5 只判定 plugin **目錄**，
  之後才把 `.claude-plugin/plugin.json` 接上去讀 —— 檢查的路徑不是讀的路徑。
  `plugins/x/.claude-plugin -> repo 外` 這個形狀因此完全不被擋，仍印綠燈。
  R5 的註解與上一版 CHANGELOG 都逐字宣稱 symlink 已擋，**那是只修到一半的宣稱**。
- **`check_bumped` 的第三個讀取點也收斂到 committed history**（#33 verify R6）。R5 統一了
  「變更清單」與「舊版本」，卻漏了 `now` —— 它讀的是工作目錄。同一次執行裡兩個基準仍然並存：
  在工作目錄 bump（不 commit）可以讓閘門印「已 bump ✓」並整支 exit 0。另外，未 commit 的
  變更現在會先印一行 warning，因為假綠燈出現在「無變更」那條路徑上，訊息必須在那裡也看得到。
- **新增撞名檢查**（#33 verify R6）。harness 對未標 `override` 的撞名是 `action: 'ignored'` ——
  那條 lens 一個 agent 都不會派。先前 validator 對「與 built-in 同 key」與「同檔內重複 key」
  完全無感，印「3 條 lens ✓」而實際只有 1 條會跑。這是貢獻路徑上最可能發生的安靜失敗
  （新手最容易挑一個現成的 lens 名字）。標了 `override` 則照常放行，並在訊息裡說明它的代價。
- **`check_bumped` 的比較基準收斂成一個**（#33 verify R5）。先前變更清單用三點
  `base...HEAD`（merge-base → HEAD）、舊版本卻用 `git show base:`（base 本身）——
  兩個不同基準。現在由 `--event` 決定語意：`push` 用 base 本身做兩點 exact-tree 比較
  （問「這次 push 讓 main 變成什麼」），其餘（含本機不帶 `--event`）收斂成 merge-base
  （問「這個分支引入了什麼」），變更清單與舊版本取自同一個基準。

  > **更正（R6）**：R5 這條原本寫「force-push 到 main 時 lens 被回退完全漏檢…現在
  > 用 exact-tree 比較」，**暗示 force-push 已被守住 —— 那是不實的**。`actions/checkout`
  > 只 fetch **ref 可達**的物件，force-push 之後舊 tip（`event.before`）不再被任何 ref 指到，
  > `fetch-depth: 0` 也拿不到，所以 `git rev-parse` 直接失敗。**force-push 到 main 不在這道
  > 閘門的守備範圍**；現在的行為是印一則說清楚原因的 `::error`（fail-loud，不是假綠燈），
  > 而不是假裝比較過。修掉的是「兩個基準」那個真缺陷，不是 force-push。
- **`check_marketplace_sync` 補上 containment 檢查**（#33 verify R5）。先前直接
  `repo / rel` 組路徑，絕對路徑（pathlib 的 `/` 會整段取代左邊）、`..`、symlink 三條路
  都能讓這道版本閘門去比對 repo **外**的 `plugin.json` 並印綠燈 —— 同一份 commit 在本機綠、
  在 CI 紅。此檢查在 `on: pull_request` 下會跑，fork PR 完全控制 marketplace.json。
- **短列不再是 error**（#33 verify R5）。`perf,"a, b, c"`（省略尾端可選欄）是 pack README
  明文允許、生產端 `pai-parse-lens-csv` 解析得好好的寫法，先前卻被判 error —— 守門者比被守的
  契約嚴，擋掉的正是本版想鋪的貢獻路徑。真正危險的「`focus` 被截斷」由既有的缺 key/focus 檢查涵蓋。
- **`workflow_dispatch` 不再必定失敗**（#33 verify R5）。該事件結構上既沒有
  `pull_request.base.sha` 也沒有 `event.before`，R4 的無條件 fail-loud 讓手動觸發永遠紅；
  一個不可能綠的檢查，下一個人會直接把 fail-loud 拿掉、連 PR/push 的守備一起賠掉。
  現在手動觸發與本機執行留可見紀錄（那不是發布事件），CI 的 PR/push 拿不到 base 才報錯。
- `references/builtin-lenses.csv` 檔頭改為 `!!! GENERATED FILE — DO NOT EDIT !!!` ——
  實測有人（含本次開發 session）第一次就誤以為該檔可編輯而去改它。
- root `CLAUDE.md` 不再宣告「唯一的 plugin」；版本同步的 CRITICAL 規則改為逐 plugin 的表格。

### Fixed（#33 verify R11 —— rebase 到 main 後的第一次完整判決：4 lens + DA，Codex 因配額缺席）

R11 是 PR #34 rebase 到 main `5eab1e4`（含 2.23.0 的 codex-call 背景執行）之後跑的。閘門邏輯本身
比前十輪都紮實（DA 跑完整輪 mutation：56 靶 → 55 殺 / 1 存活（已知 equivalent）/ 0 壞；R9 可判定的
10 個 HIGH 全部有測試接著），失守的是**三句宣稱**：

- **R10 最後一個修法宣稱的邊界是假的**（HIGH，三個 lens + DA 各自重現）。`emit()` 的 docstring
  與 commit message 都寫「所有 workflow-command 輸出的唯一出口」，但 GitHub runner 解析的是
  這個 process 寫進 step log 的**每一行**（`ActionCommand.TryParseV2`：`TrimStart()` 後
  `StartsWith("::")`），`validate.py` 有十二處裸 `print()`、五處插入 fork PR 可控的值。實測
  pack `version` 含換行 → validator **第 2 行**就是 `::stop-commands::`；兩份 manifest 的 `name`
  同時含換行 → **rc=0 全綠**且 log 帶它。這是本 PR 第三次把「邊界」劃得比實際邊界小
  （per-call-site `wc()` → annotation 出口 `emit()` → …）。DA 另外查到 **stderr 走同一個
  `ActionCommandManager` 實例**，且 lens 提議的 `print = emit` 會無窮遞迴。第四次一次到位：
  新增 `LineSanitiser` 在 `main()` 開頭包住 **stdout 與 stderr**，任何一行 `lstrip()` 後以 `::`
  開頭就把它中和成 `∷`；`emit()` 改走原始 stdout（`RAW_OUT`），是唯一能印出真 annotation 的
  路徑。測試改成**形狀斷言**（輸出中每一行以 `::` 開頭者必須是 validator 的 annotation 形狀、
  head 不得含注入標記），並對 `LineSanitiser` 的跨 `write()` 部分行與兩條 stream 的安裝各有測試；
  靶清單加了邊界本身與兩個安裝點。
- **`entry_names` 登記在所有 `continue` 之後**（HIGH，只有 1/4 lens 抓到，DA 獨立重現）。
  第二條同名 entry 只要 source 是遠端（`github:…`）或判不出來，撞名**完全不報、rc=0**。程式碼裡
  就寫著 R7 的教訓「登記必須在所有 continue 之前」，R10 新加的 `named_entries` 照做了，
  `entry_names` 沒有。情境正是本 PR 的主題：舊的遠端 `pai-lenses` entry 沒刪乾淨。搬到同一區塊。
- **description 的版號前綴沒跟著 rebase 改**（MEDIUM）：version 改 2.24.0，兩份 description
  仍寫 `v2.23.0: pai-lenses 併回…`，而同一棵樹的 2.23.0 是 #47。既有的 description-drift 閘門只比
  兩份彼此是否相同，兩份一起錯就靜默。改字串，並補一行 2.23.0（#47）的敘述（main 從未替它寫過），
  新增 warning：description 以 `v<semver>:` 標示時，最新那個必須等於 `version` 欄。
- **綠燈路徑上一句永遠為假的「（偵測到純目錄改名，內容零變動）」**（MEDIUM）：`_find_pack_at`
  在沒改名時退回 name 比對、回傳**現**路徑，呼叫端把「非 None」當「有改名」。契約是「找出**舊**
  路徑」，與現路徑相同就回 None；補「無改名 → 不得出現該字串」的測試（先前兩條 rename 測試的
  `assertIn("純目錄改名")` 對此零鑑別力）。
- **`R100` 判定只有「過嚴」方向有靶**（MEDIUM）：放寬成 `.startswith("R")` 全套仍綠，而放寬後
  「改名 + 追加一條 lens」（git 判 `R09x`）變成假綠燈。既有測試的 fixture 整檔覆寫、git 判 A/D，
  沒踩到那條分支。新測試只 append 一行並斷言 fixture 逼出 `R0xx`；靶清單加放寬方向。
- **annotation 的 `file=` property**（MEDIUM ×2）：(a) 檔名裡一個逗號就能偽造 `line=` /
  `title=`（runner 用 `,` 切 property），`emit()`／`wc()` 都不處理；(b) `check_lens_dir_shape` /
  `check_csvs` 那組 `file=lenses/x.csv` 是相對 pack 根 —— 併回後 repo 根沒有這個檔，annotation
  貼不上 PR diff（runner 只自動轉換 workspace 底下的**絕對**路徑，所以 manifest 那組不動）。
  新增 `ann_path()`：相對 repo 根 + 依 runner `_escapePropertyMappings` 轉義 `% \r \n : ,`。
- **`culprit is not None` 把「沒有這條 entry」與「有名字但 source 缺席」混為一談**（MEDIUM）：
  忘了寫 `source` 仍被導向「再加一條 entry」。存在性改用 key 判。
- **反向 glob 沒有 containment**（LOW）：`plugins/evil → repo 外` 的 plugin.json 會被讀 ——
  五處 `_inside` 硬化漏了第六處。先判再讀。
- 零星：`emit()` 截斷補測試（mutation 存活）；`:379` 改用已解析的 `pj_obj`；`_inside` 的 3.8
  fallback 補「含自身」；`EVENTS` 旁註明與 `test.yml` `on:` 是兩份規格；`test/run.sh` 補
  `bin/pai-list-profiles` 的 shellcheck、`pai-collect-lens-layers` 的 py_compile、並跑 pack 的
  python 測試（先前 66 條測試沒有任何本機入口，`test/README.md` 的「CI 跑同一組」為假）；
  `test.yml` 補兩支 lint 的 shellcheck 與 `node` 隱含相依的註解；root README「純資料無程式碼」
  改為與目錄樹一致；刪掉 subtree 殘留的 `plugins/pai-lenses/.gitignore`；本段 R8 的 mutation
  數字自相矛盾處已改寫（見上）。
- **跨 profile 的 lens 檔改名先前算「純改名」**（R11 修法後自己的 mutation 量測抓到：新加的
  「沒改名時不回現路徑」靶在 git 分支存活）：`lenses/code.csv → lenses/academic.csv` 是同一 pack 內
  的 R100，(a) `_find_pack_at` 的多數決把 pack 自己投成「舊路徑」、印假的「純目錄改名」；
  (b) `R100` 被無條件當純改名 —— 但**檔名就是 profile**，整批 lens 換了 profile 而不 bump，
  使用者收不到。現在 pack 內部改名不投票，且只有檔名（profile）不變的 R100 才是純改名。
- 明示**不在本 PR**：`bin/pai-collect-lens-layers` 的 semver prefix match／prerelease 打平靠
  readdir／`<profile>` 未驗證 → #56（不在本 diff 內）；shellcheck 清單的自動列舉 → #30。

  測試 66 → 79 條；靶清單 56 → 68 個。量測（R11 後）的殺／存活數見 `scripts/test_validate.py` 檔頭。

### Fixed（#33 verify R12 —— R11 修法的重驗：4 lens + DA，Codex 仍因配額缺席）

R11 的 15 列有 11 列真的修好（各 lens 自建 fixture 重現，不只讀作者的測試），但**R11 #1 的修法只做到一半，
同一個邊界第四次劃錯**：

- **`LineSanitiser` 的「行」與 runner 的「行」是兩套定義**（HIGH，三個 lens + DA 各自重現）。R11 版用
  Python `str.splitlines()` 切段（8 種行界），卻用 `endswith(("\n","\r"))` 判行首 —— `\v` `\f` `\x85`
  U+2028 U+2029 讓 `_at_line_start` 在實體行中途歸零，下一段的 `::` 不經消毒；而 .NET `TrimStart()`
  把那五個字元當空白吃掉。實測兩份 manifest 的 `name` 含 `\n\v::stop-commands::` → **rc=0 全綠**且
  log 帶它，與 R11 的攻擊只差一個字元；R11 為此加的兩條測試守的是 `\n` 這一個字元（把 `INJECT` 的分隔符
  換成 `\n\v` 兩條立刻轉紅），`MUTATIONS` 也漏了那一行。現在「行」只有 runner 的定義（`\r`／`\n` 之後
  才是新行），`INJECT` 參數化成十種分隔符的封閉列舉（單元 + 端到端各一條），靶清單加「換回 splitlines」；
  `emit()`／`wc()` 順帶把 Python 認得的全部行界壓成 `⏎`（縱深防禦）。`LineSanitiser` docstring 明寫它守
  不住 `.buffer`／`os.write`／未 capture 的子行程 —— 12/12 `subprocess.run` 皆 `capture_output=True`
  是紀律不是機械保證。
- **runner 有第二套語法 `##[cmd …]…`，全樹沒有任何東西碰它**（HIGH，DA 從 `actions/runner` 原始碼抓到：
  `TryProcessCommand` 對每一行依序試 `TryParseV2`（`::`）與 `TryParse`（`##[`）；V1 用 `IndexOf` 定位，
  不 trim、不錨定行首、不需要換行，runner 自己的 L0 測試斷言 `">>>   ##[do-something k1=v1;]msg"` 會被
  解析）。PoC：兩份 manifest 的 `name` = `pai-lenses ##[stop-commands]zzz ##[error file=…]FORGED`
  （單行、零特殊字元）→ rc=0 全綠、runner 解析出 `[stop-commands]`。四個 Claude lens 都只知道 V2、
  三個 lens 一致提的行界修法對這份 payload 一個字元都動不到 —— Codex 缺席時跨模型的問法多樣性也缺席。
  `LineSanitiser`／`emit()`／`wc()` 現在全行把 `##[` 換成 `##⟦`；`emit()` 的截斷只截訊息、保證
  `::cmd props::` 頭完整（否則 V2 找不到第二個 `::` 就落到 V1）；`LineSanitiser` 改成**緩衝未完成的一行**
  到行界才判（DA-3：`::` 被切在兩次 `write()` 中間時只記行首旗標看不到）；測試語料含 runner 的 L0 輸入，
  `assertNoInjectedCommand` 對每一行斷言不含 `##[`。
- **反向 glob 是唯一沒走 `load_obj` 的 JSON 讀取點**（MEDIUM）：`{"name":[]}` 在 `in` 上拋 TypeError、
  非 UTF-8 拋 UnicodeDecodeError，都是裸 traceback、零 annotation、已累積的 errs 全部消失 —— `load_obj`
  的 docstring 逐字寫著這個後果，R9/R10 修了三個站點、漏了第四個。改走 `load_obj` + `isinstance(str)`。
- **`run.sh` 的 `|| echo HEAD` 把「無法比較」印成「比較過且通過」**（MEDIUM，R11 修法自己引進的）：
  `--base HEAD` 恆印「無需 bump ✓」，站在 main 上跑也一樣。拿不到 merge-base（或 HEAD 就在 main 上）就明說
  「bump 檢查本次未跑」、其餘閘門照跑；`cd ../pai-lenses` 加非 monorepo 佈局的 guard；並把 CI 的
  `builtin-lenses.csv` drift step 搬進 `run.sh`（R11 #9 最後一處分岔）。
- **property 轉義只落在 2/26 個 `file=` 站點**（MEDIUM，R11 #6 半成品）：manifest 側 24 處仍是裸路徑，
  目錄名 `plugins/evil,line=1,title=CI PASSED/` 一樣偽造 property。抽出 `prop()`，所有 `file=` 一律經它；
  base 側 load_obj 的 label 從 `<sha>:<path>` 改成 repo 相對路徑（裸 `:` 不是 runner 認得的任一種路徑）。
- **「三個守衛互為後盾」是假的**（MEDIUM，logic 代數證明 + mutation 實測）：R11 在 `_find_pack_at` git 分支
  加的兩個守衛依構造不可達（`old_pack == pack_rel ⟺ old_path == new_path`，git 不會對同路徑輸出 R），
  兩個同時關掉全套仍綠；load-bearing 的只有 name 分支的 `path != pj_rel`。依 DA 的裁決**保留**那兩個守衛
  （不可達是上游窄入口的副產品，入口一放寬就變回 load-bearing）、改文字，並把對應的兩個靶列進
  `mutation_check.py` 的 `EXPECTED_SURVIVE`（永遠殺不掉，不再每輪讓人重新判讀）。同輪 requirements lens 另證明「containment（只判目錄層）」
  **不是** equivalent（source 指到 `plugins/` 以外時反向 glob 看不到）—— 補 `./docs/evil` fixture 讓那個靶轉紅。
- **description 版號閘門的「第一個＝最新」沒有規格也沒有測試**（MEDIUM）：改成取最後一個 match 全套仍綠。
  補雙向測試（舊在前 → warning；新在前 → 無），靶清單加「first→last」；慣例寫進 root `CLAUDE.md` 版本同步表。
  另記錄一個取捨（R12 regression R12-7）：兩份 description 統一後只列最近兩版（v2.24.0 / v2.23.0），
  v2.19.0–v2.22.0 之間的敘述移出（兩份 manifest 各四段、領頭版號不同） —— 歷史看 CHANGELOG，這裡是 `/plugin` 清單的一句話。
- 零星：`bin/pai-list-profiles` 補 containment（第七處，這一處是**執行**不只讀）；root `CLAUDE.md:38/:52`
  的「純資料無程式碼」與 README 對齊（R11 只修了 README —— 同類只修一處第 N 次）；`test.yml` 的 `on:`
  補回指 `EVENTS` 的對稱註解；`validate.py` 引用已刪 `.gitignore` 的註解改寫；`note: pack 在 base 時位於 …`
  改印目錄而非 plugin.json 路徑；本段 R8/R9 兩句存活數補上輪次。
- 明示未動：root README skill 表格的擴充（R11 #13 已標可選，內容正確、不在 checklist）。

  測試 79 → 89 條；靶清單 68 → 75 個（含 3 個 EXPECTED_SURVIVE；commit `96f26a4` 的訊息寫成 2，以程式碼為準——R13 errata）。量測（R12 後）：71 殺 / 1 存活（equivalent）/ 0 壞，見 `scripts/test_validate.py` 檔頭。

### Fixed（#33 verify R13 —— R12 修法的重驗：4 lens + DA，Codex 仍缺席）

R12 的 12 列全部確認修好（三個 lens 各自用探針／fixture 重現，含十幾種分隔符與 V1 重疊前綴），
沒有 not-fixed；但「同類只修一處」在 R12 修法自己身上又發生：

- **非 UTF-8 manifest 還有兩個 crash 站點**（HIGH，security S1）：R12 說「反向 glob 是唯一沒走 `load_obj` 的
  JSON 讀取點」—— 假的。`check_bumped` 讀 `pack_name` 的 except 少列 `UnicodeDecodeError`，所有
  `subprocess.run(text=True)` 對 git 輸出的解碼也會炸；裸 traceback、零 annotation、後面的閘門整段不跑。
  except 補齊、12 處 `text=True` 一律 `errors="replace"`，測試在無 base／有 base 兩條路徑各斷言「後面的閘門仍跑到」。
- **`##［`（U+FF3B）有 `<wide>` 相容分解，NFKC 會回到 `[`**（security S3）：替身改用 U+27E6 `⟦`
  （無分解；`∷` U+2237 亦無）。
- **containment 第八、九處**（logic N1）：pack 自己的 `.claude-plugin` 是 symlink 時 `check_version`
  印出 repo 外的 `version`，同一次輸出下兩行卻說「拒絕讀取」；`check_bumped` 的 `pack_name` 讀取同。
- **harness 本身沒有 containment**（requirements R13-4）：`bin/pai-list-profiles` 求值的
  `workflows/ensemble-workflow.js` 是 symlink 到 repo 外時，node 的 SyntaxError code frame 把該檔內容經
  stderr → errs → annotation 印出（與 R9 標 HIGH 的 lenses symlink 洩漏同類）。呼叫前判 `_inside`，
  stderr 走 `wc()` 截斷。
- **drift 檢查印 diff 內容**（requirements R13-5）：catalog 的 `focus` 是 fork 可控文字，`git diff` 的 `+` 行
  會把 `##[…]` 原樣印進同一個 job 的 log —— `LineSanitiser` 守的是 `validate.py` 這個 process，不是整個
  workflow。`test.yml` 與 `run.sh` 兩處改 `git diff --quiet`，不印內容。
- **drift 檢查落在非 git checkout 的 guard 之外**（logic N4 / regression R13-1 / requirements R13-3）：
  plugin cache 副本下 `git diff` rc=129 被報成「檔案過期」。包進 `git rev-parse --is-inside-work-tree`。
- **description 版號 regex 的 `\bv` 在 CJK 相黏時不成立**（logic N2）：「補齊v0.0.1:」跳過真正最前面的版號。
  改成「前一個字元不是 ASCII 英數」，雙向測試。
- **`main()` 把所有 annotation 留到最後才印，任何閘門拋例外就全部消失**（DA-1：這是 R6／R9／R10／R12 #3／
  本輪 S1 同一結構的第五次發作，五次的修法都是「再加一個 except」）。現在每道閘門各自 try/except，
  例外變成一條具名的 `::error::validator 內部錯誤（閘門 X 未跑完）`，後面的閘門照跑、已累積的 errs
  一定印出。`LineSanitiser` 補 `writelines`（DA-3：`__getattr__` 透傳讓它整個繞過消毒）；`emit()` 先
  `lstrip()` 再認命令頭（DA-12：與 runner 的 `TrimStart()` 同一定義）；`test.yml` 的 `py_compile` step
  過一層中和 filter（DA-4：SyntaxError code frame 把 fork 可控原始碼行原樣印進 log；`stop-commands` 是
  step-scoped、`add-mask` 是 job-scoped——守備範圍寫進註解）。
- `--check-targets` 也驗 `EXPECTED_SURVIVE ⊆ 靶名`（regression R13-6 / DA-5：這個集合在機制上能藏東西，
  報表措辭改成「每輪仍需確認理由是否成立」）；`flush()` 的中和補測試（logic N5）；
  `test.yml` 註明 node 測試的 stdout 不在輸出邊界守備範圍（security S2）；root `CLAUDE.md` 註明 pai-lenses
  不採用版號前綴（requirements R13-8）；本段開頭 blockquote 不再寫死輪數（R13-9）；「五版／四段」統一（R13-7）；
  `lint-changelog-counts.sh` 的宣稱形式擴成也認 `grep -c "<pattern>" <file>`（R13-1，python 測試數不再手打；指向 sibling plugin 的 `../` 路徑在非 monorepo 佈局不存在時跳過並註明，不判「數字錯」）。

- **`main()` 逐閘門隔離讓 8 個 mutation 靶假存活**（本輪修法自己的副作用，全輪量測抓到）：守衛被刪掉後
  只剩一條「validator 內部錯誤」，rc 仍 1、沒 traceback，舊的「不 crash」測試分不出「守衛在」與「由 gate()
  兜住」。`test_validate.py` 的 `Fixture.run` 預設把那個字串視為失敗（一處，不是八條測試各補一句）。
  測試 89 → 97 條；靶清單 75 → 83 個（lint 形式的宣稱只留在最新一段——舊段的數字是當時的紀錄）。
  量測（R13 後）見 `scripts/test_validate.py` 檔頭。
- **verify R14（4 lens + DA；Codex 第四輪 429）— R13 的 12 列 9 fixed、2 partial、1 機制修好但同 commit 裝進假理由。**
  失守的仍是「同類只修一處」，本輪兩個新形狀：R13 放行條件 #2 的**後半**（讀檔站點改成封閉列舉）整條沒做；
  在修前一輪缺陷的同一個 commit 裡用另一個工具（sed）重劃錯了同一條邊界。修法：
  - **`repo_root()` 回 None 時五道閘門靜默蒸發、rc=0**（logic L-1，唯一具「安靜綠燈」形狀的一條）：fork 把
    `.claude-plugin/marketplace.json` 改名就做得到，還印一句假 warning（「沒有 ensemble-code-review 這支 skill」）、
    並重開 R9 的 `lenses/` symlink 外洩。現在 `report_no_repo()` 一處分流（CI error／本機 note，與 no-base 同形）、
    各閘門對 None 靜默 return、`lenses/` 目錄層 containment 的邊界退回 pack 自身、缺 repo 時不跑接線啟發式。
  - **讀檔／執行站點的封閉列舉**（logic L-2 / security S1 / regression E-2）：`READ_SITES` 表 18 列，每個
    `read_text(`/`.open(`/`subprocess.run(`/`iterdir(` 帶 `# READ-SITE k/N` 標記，測試機械比對（缺標記、總數不一、
    與表列數不合 → 紅）；補第十處（root `marketplace.json`，先前直接 `load_obj`——DA 更正：完整 git round-trip 是
    rc=1 不是 rc=0，反向 glob 會抓到；仍是無守衛）與第 11 處（`collector_wiring` 的 SKILL.md）；lister 呼叫時
    **顯式傳入** `PAI_HARNESS`（檢查的路徑 = 求值的路徑，逐字是 R6 修過的缺陷第二次）；harness 求值的 stderr
    **一律不進 annotation**（路徑守衛擋不住 in-repo 合法 JS 去 `import` repo 外的檔——內容再無管道；R13 的
    `wc()` 那一半先前零測試零靶，logic L-6）。表旁明寫守什麼／守不住什麼（hardlink、bind mount、被求值的程式碼
    自己讀什麼），containment 是佈局健檢不是安全邊界。
  - **CI 中和只剩一份實作**（logic L-4 / security S2 / S3 / L-5 / regression E-1 / requirements F2）：新增
    `scripts/neutralise.py`（stdin → `LineSanitiser` → stdout），兩個 job 所有會印 PR 可控文字的 step
    （兩處 py_compile、test_validate.py、mutation_check.py、regen 腳本）都經它；sed 版刪除（`[[:space:]]` 比 .NET
    IsWhiteSpace 小——NBSP 開頭的 `::` 穿過；`^` 只認 `\n`——含 CR 的檔名穿過）。兩個 job 各有 step 級封閉列舉
    的註解（bats／node tests 明寫不過濾：它們執行 PR 自己的程式碼）。**DA 的定價更正**：這整族洩漏／偽造在
    `on: pull_request` + `contents: read` + 零 secrets 下不擴大攻擊者已有的能力（同 job 本來就執行 fork 的
    Python）——修的是「新增的控制自己可繞過」與「兩份不會一起改的規格」，不是爆炸半徑。
  - `gate()` 的相依（logic L-3，DA 降 LOW）：`check_lens_dir_shape` 未跑完時 `check_csvs` 具名回報「沒有跑」；
    gate 訊息不再說「其餘閘門的結果仍在下面」；drain 迴圈保護（emit 拋例外時退化成 ASCII 留痕，其餘照印）。
  - `EXPECTED_SURVIVE` 第四條移除（requirements F3；DA 降 LOW：committed symlink 在 `git show HEAD:` 就 return，
    只有 dirty worktree 到得了那行 print，CI 產不出）——現在有 dirty-worktree 形狀的測試網，靶轉殺；規則明寫：
    每一條進來的靶都要能回答「關掉它，哪一行輸出會變」。
  - ubuntu job 補 `pai-collect-lens-layers.bats` 的 no-skip step（R13 row 11 / R14 F4：pack 改名時整合錨點會靜默
    skip）；`regen-builtin-lenses.sh` 進兩份 shellcheck 清單（N9）。
  - **明示不修的 LOW（R13 row 11 / R14 F4，記錄在此免得下輪重報）**：`emit()` 的 4000 上限只約束訊息、命令頭
    無上限（N7：頭是 validator 自己組的固定字串，不含 PR 文字）；`prop()` 的靶只守 5 字元中的 2 個（N6）；
    `run.sh` 的 drift 檢查會改寫工作樹（reg R13-4：那正是「請 commit」的用意，run.sh 內已註明）；
    `Fixture.run` 的內部錯誤判定是全輸出子字串比對，有假紅路徑無假綠路徑（L-8）；`gate()` 的 `repr(e)` 會印
    例外攜帶的檔案位元組（S6，目前不可達）。
  - 文件 errata：description 版號段——R14 寫「v2.19.0–v2.21.0 四段、main 從無 v2.22.0」是**錯的**（R15 三個 lens 各自
    查證）：base `5eab1e4` 的**兩份** manifest 各四段但不一致——marketplace.json 領頭 v2.21.0、plugin.json 領頭
    v2.22.0（R11 抓到的 description 不同步正是這件事），聯集五個版號。R13 的「五版／四段」其實各指一件事，R14 把
    正確的一半改錯；本段與 2.22.0 那條現在寫成「兩份各四段、領頭不同」。「一輪 mutation 約十分鐘」六處全是低估
    （DA-N1 五處 + ASCII 的「10 分鐘」第六處；R14 的批次替換還把兩處弄成「三三十分鐘」——R15 F4/L-3）：每套測試
    20–30 s × 92 靶 ≈ 30–50 分，六處統一（**這兩個數字 R17 實測仍低估，見該段**——歷史條目保留當時寫的值，
    不回頭改，否則 CHANGELOG 就不再是「當時宣稱了什麼」的紀錄）；靶數改成 lint 認的第三種宣稱形式；`pai-list-profiles.bats` 登記進 test/README；
    「containment 的第八處」不再指到兩個站點（E-11）。
  測試 97 → 111 條；靶清單 83 → 92 個（3 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段）。
  量測（R14 後）：全輪 88 殺／1 存活（「lister 不存在」補斷言後單靶重跑轉殺）／3 預期存活。
- **verify R15（4 lens + DA；Codex 第五輪 429）— R14 的三條 blocking 全部確認修好、零 HIGH；四份共同指向兩件事：
  「宣稱封閉的列舉不封閉」（READ_SITES 的偵測器只認六種字面；step 級列舉漏 shellcheck／lint-* 與整個 macOS job）
  與「errata 本身又改錯」。**修法：**
  - READ_SITES 的偵測改走 **AST**（logic L-1 / requirements F1 / security S-1 / regression F4）：三個封閉集合
    `READ_CALLS`／`READ_MODULES`／`READ_MODULE_PURE`，任何 Call 命中就必須帶 `READ-SITE` 標記；純 metadata 述詞
    （is_file／resolve／exists／os.path.*）明示不在列舉內。四個 lens 注入的七種形狀（裸 `open(`、`glob`、`Popen`、
    `os.listdir`、`check_output`、`shutil.copy`、`os.scandir`）逐一驗過會紅；反向檢查的 `glob(` 補為第 19 處。
  - CI 的 step 級列舉改成 **lint**（logic L-2 / security S-3 / requirements F2 / regression F5）：新增
    `test/lint-ci-log-filter.sh`（＋ good／bad fixture selftest），test.yml **每一個** run step 都必須經
    `neutralise.py` 或帶 `# LOG-FILTER:` 註解明示不過濾與理由（三個 job 全部 run step 交代（當時 20 個；lint 形式的數字只留在最新一段）；shellcheck／
    lint-*／pack 錨點 bats 改經過濾器）；接進 run.sh 與 CI。
  - harness **stdout** 也是管道（security S-2）：profile 名清單進 annotation 經 `wc()`；READ_SITES 旁列出所有
    「子行程輸出 → annotation」站點（三處，皆經 wc()）。
  - pack 錨點 no-skip 守衛（regression F1 → **DA 推翻**：reviewer 的 `grep` 是 Claude Code shell snapshot 裡帶 `-I` 的
    ugrep，CI 的 GNU grep 會命中；本機用同一個 shell 也重現了「漏」，所以 `-a` 仍加上——它讓守衛不依賴 grep 對
    CJK 截斷後 binary 判定的實作差異——並補上 macOS job 那份的 plan-vs-executed 檢查（R14 版是它的真子集）。
    run.sh 同步這份守衛。**教訓**：reviewer 自己的工具鏈也會「同一概念兩套實作」。
  - gate 相依第二半（logic L-4）：`files == []`（lenses/ 沒有合法 CSV）時 check_csvs 具名回報「沒有跑」。
  - `mutation_check.py` 掛 SIGTERM／SIGHUP handler 轉 SystemExit（requirements F9：被砍掉時 mutated 的
    validate.py 無聲留在工作樹——只有 Ctrl-C 走得到還原）。
  - `lint-changelog-counts` 的 `../` 跳過只在 **sibling 目錄**缺席時生效（R14 S5 / R15 security LOW：檔案缺席就跳
    在 monorepo 裡是永久豁免；補 fixture 讓「目錄在、檔不在」被拒）。
  - errata 的 errata：description 版號段見上面 2.22.0 那條（R14 改錯了正確的一半）；「十分鐘」第六處（ASCII
    `10 分鐘`）、兩處「三三十分鐘」與 CHANGELOG 本段內再兩處（DA-6，四份都漏）改對（30–50 分）；`NO_REPO_GATES`
    的訊息改由清單算數量、測試逐名比對並加靶（DA-3）；獨立 pack 下 profile 名未驗時不再印 ✓（DA-4）；
    merge-base 的 stderr 也經 `wc()`（DA-5）；`README.md` 與 plugin `CLAUDE.md` 把 minutes 的第四個 lens
    寫成不存在的 `actionability`（真源 `cross-document`，requirements F5，十輪未抓到）；neutralise.py docstring
    指向的清單改指 lint；`test/run.sh` 與 `lint-ci-log-filter.sh` 進兩份 shellcheck 清單。
  測試 111 → 118 條；靶清單 92 → 96 個（3 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段）。
  量測（R15 後）：全輪 94 靶 89 殺／2 存活（補斷言後單靶轉殺）＋ DA 修補的 2 靶單獨驗殺 → 93／0／3（複合值）。
- **verify R16（4 lens + DA；Codex 第六輪 429）— R15 的三條 blocking 全部確認修好、零 HIGH；但 R15 修法自己引進
  一條 CI 回歸，且新蓋的機械閘門各有解析漏洞。修法：**
  - **CI 紅在 `test/run.sh:40`（requirements H1）**：pack 錨點守衛寫成 `A && B || C`（SC2015）——本機 shellcheck 0.11 不報、
    ubuntu runner 的版本報，`shellcheck-bats` job 紅、後面七個 step 全 skipped（含 R15 新建的兩道閘門）。改 `if`。
    同一檢查兩份實作（shellcheck 版本）——本機請用 `shellcheck -S style`。
  - **`lint-ci-log-filter.sh` 自己的解析漏洞**（requirements F3 / logic L-1 / security S-3 / regression F4）：`- run:`
    起頭（無 name）的 step 整個看不見或併進前一個 step；flow mapping 寫法被跳過；`neutralise.py` 寫在註解裡也算數；
    寫在下一個 `- name:` 上方的 `# LOG-FILTER:` 被歸給前一個 step。四種都補 fixture 進 selftest：任何 `- ` 清單項都是
    step、flow mapping 直接拒絕、只認非註解行的 `neutralise.py`、新 step 開始時剝掉前一個 body 尾端的註解行。
    已知限制明寫：`in-process` 是自我宣告，lint 不查證（本 repo 唯一的 in-process 是 validate.py，其 LineSanitiser
    由 test_validate.py 釘住）。
  - **非 monorepo 佈局回歸**（logic L-2 / L-3 / regression F1）：`lint-ci-log-filter` 找不到 `.github/` 時裸 traceback、
    `lint-changelog-counts --selftest` 第三條斷言依賴 `../pai-lenses`、pack 錨點守衛在沒有 sibling pack 時把設計上的
    skip 判成 vacuous——三處都改成「明說略過」，plugin-only 佈局 run.sh 重新綠（R15 的「四種佈局全綠」在 895b104
    上不成立）。
  - **「內容再也沒有管道」三處改成誠實的**（security S-2 / regression F2，R15 唯一放行條件的後半）：harness stdout
    （profile 名）依構造是 PR 可控文字、仍是內容管道，經 `wc()` 截到 200 字——有上限，不是沒有管道。「子行程輸出 →
    annotation 三處」的手寫站點清單換成 **taint 傳播的 AST 保證**（DA-1：security 建議的「直接插值必須包 wc」版本出廠即
    vacuous、漏掉 `:848`／`:924`／`:938`／`:940`——`.stdout` 在前一個 statement）：從 `.stdout`／`.stderr` 出發，逐函式
    沿 Assign／for／comprehension 染色，任何進 `errs.append`／`emit`／`print` 的染色插值都必須是 `wc()`／`prop()`；補
    `git status` 路徑清單、merge-base sha、改名前路徑、manifest version 字串（五處 echo）、`version =` note。**母體明說**
    （DA-2）：這條網守的是「子行程輸出」；manifest／CSV 的單值（version／name／source／header）另由 `prop()`（property
    位置）與 emit() 的兩套語法中和 + 4000 上限守，**不宣稱 200 字上限對它們成立**——那是 emit 的邊界，不是 wc 的。
  - AST 偵測器的別名繞過（logic LOW / security S-1 / DA R16-Q1）：`from os import listdir as _ld`／`import subprocess
    as sp` 讓 base 名消失。DA 的答案比四份都強、只要兩條 AST 斷言：**凍結 validate.py 的 import 全集**（`ALLOWED_IMPORTS`
    八個 stdlib、零 asname、零 from-import）+ **禁動態派發內建**（`getattr`／`vars`／`globals`／`locals`／`exec`／
    `eval`／`__import__`／`compile`；唯一例外是 `LineSanitiser.__getattr__` 對 `self._stream` 的委派）——「能讀檔的
    東西」只能經這 8 個模組的靜態呼叫名進來。metadata 述詞（`os.path.exists`／`os.stat`／`getsize`／`realpath`…）
    從偵測器排除，讓散文與偵測器對同一組述詞給同一個答案（DA）。
  - SIGTERM wiring 補靜態網（logic LOW）：main() 的 AST 裡必須在 mutate 迴圈前呼叫 `install_restore_signals()`。
  - **TAP 守衛三份手抄實作抽成一支**（DA-6：這才是 H1 的根因——R15 手抄第三份時改寫成 `A && B || C`；shellcheck
    版本只是引信）：`test/assert-tap-complete.sh`（no fail／no skip／plan == executed；`grep -a`；`plan=` 加 `|| true`
    讓 errexit 下守衛到得了），macOS job、ubuntu pack 錨點 step、run.sh 三處呼叫；進兩份 shellcheck 清單。
  - `lint-ci-log-filter.sh` 守備目標改成 `.github/workflows/*.yml` 全部（DA-4），read-site 判定式在測試裡只留一份
    （DA-5）。
  - 數字：「三個 job、15 step」實為當時 20 個 run step（R16 時以 lint 形式寫出；歷史數字，現況見最新一段）
    （security S-4 / regression F3，改成 lint 認的形式）；mutation 耗時再上修為 30–50 分（logic 實測 29 s × 96 ≈ 47 分）。
  測試 118 → 124 條；靶清單 96 → 98 個（3 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段）。
  量測（R16 後）：全輪 98 靶 93 殺／2 存活（emit 自己的中和層，補單元測試後單靶轉殺）→ 95／0／3（複合值）。
- **verify R45（4 lens + DA + Codex 跨模型 leg，`gpt-6-astra`／medium，靜態推演）— 2 HIGH、5 MEDIUM blocking、22 LOW；requirements、logic、regression、DA、Codex 判 FAIL，security 判「PASS（有限）」被 DA 推翻，聚合判 FAIL。**
  CI 在 `2835ead` 上是綠的。報告的中心發現（DA）：**逐原語問「運算元給定時它做什麼」沒問「bash 在原語看到運算元之前怎麼重塑運算元向量」**——R44 的文法收窄與全輪 opsweep 都沒有看到那一層；神諭的注入探針其實看得到（`2835ead` 的神諭對 `test {-v,"$PR_TITLE"}` 與 `echo hi {a["$PR_TITLE"]}>/dev/null` 都判「不一致：繞過（注入…）」），缺的是文法語料從沒餵它們這兩個輸入——R45 報告說「盲區不在神諭」指的就是這個；探針真正看不到的是 `printf '%n'` 改寫信任變數（要靠 primitive 稽核）。四個 lens 各自都沒找到兩個 HIGH；是 DA 與 Codex 找到的，我在凍結樹上逐個實跑重現。HIGH：(1) **大括號展開**（`test {-v,"$PR_TITLE"}` 是 `test -v "$PR_TITLE"`——`-v` 的運算元被算術求值，標題 `PWD[$(命令)]` 的命令替換執行；`--strict` 與預設都 rc=0，DA 端到端寫進 `$GITHUB_ENV`）；lint 檔頭 R44 寫的「未加引號的大括號與波浪號展開的結果不來自 PR 的檔名，照收」只看了結果的來源、沒看展開對 argv **個數與位置**的影響。(2) **具名 fd 的陣列參照**（`echo hi {a["$PR_TITLE"]}>/dev/null` 的下標被算術求值；`{RUNNER_TEMP[0]}>` 把 `RUNNER_TEMP` 改成 10）；R44 只比對 `\{NAME\}`，P1 第 8 類「具名 fd 不收」是全稱宣稱。放行條件十條在報告末段；**修法方向（DA）：不要再補拼法，把 lint 的詞模型與 bash 實際 argv／被改寫的變數做機械對帳。**
  - **文法（第 1、2、3 列）**：文法收的 builtin（`echo printf test [ true false : exit` 與 `trap`）的參數不收會展開的大括號詞——未加引號的字面（P 片段）合起來同時有 `{` 與（`,` 或 `..`）；引號裡的逗號、沒有逗號的 `{NAME}`、**外部命令的參數**不受影響（L1，`mkdir -p out/{bin,lib}` 是常見寫法）。具名 fd：詞以 `{` 開頭、以 `}` 結尾又緊接 `<`／`>` 一律擋，不比對內容。`printf` 的格式改成封閉的轉換列舉（`FL_PRINTF_FMT_RE`：`%%`、旗標＋寬度＋精度＋`sdiuoxXeEfFgGcq` 之一，加不含 `%` 與反斜線的文字、或反斜線接 `abefnrtv\'"?0-7xuU` 之一；精度是 `.` 加至少一位數字）——`%n`（`%5n`、`%ln`）把已輸出的字元數指派給參數所命名的變數（`printf '%n' HOME` 之後 `HOME=0`，bash 5.3 與 3.2 實測；`printf '%n' 'a[$(cmd)]'` 被 bash 以 not a valid identifier 拒絕，**沒有命令執行路徑**，所以 Codex 判 HIGH、我判 MEDIUM）。**我先前說「`printf {-v,x} y` 目前放行」是錯的**——printf 的第一個參數守衛早就擋它（`{-v,x}` 不以 `-` 開頭但 `_fl_lit` 判它不是純字面）；那張 fixture 是回歸、不是紅燈。`exit "$X"` 的狀態值（DA 第 10 列；test.yml 自己就寫 `exit "$rc"`）改成在檔頭明講限制：值的來源不受檢查，只遮蔽退出碼、不外流、不執行。
  - **bash 展開／剖析階段全表（放行條件 6）**：lint 檔頭新增「bash 的展開與剖析階段 × 文法允許的原語位置」——S0 詞法（具名 fd、IO_NUMBER）、S1 大括號、S2 波浪號、S3 參數／命令替換／算術、S4 斷詞、S5 檔名展開、S6 quote removal、S7 builtin 自己的剖析（`test` 的 `-v`、`printf` 的 `-v` 與 `%n`、`echo` 的選項、`exit`、`trap`、指派），每格回答「這個階段能不能讓原語拿到文法沒有點名的 argv、或讓 shell 指派／求值沒點名的東西」。**表交給另一個讀者對 bash 核對**（不是核對文字對得上程式）：獨立審閱者用 bash 5.3.15 做了三輪差分（約 1700 筆輸入）與 27 個 exotic 構造，沒有發現會執行命令或改寫信任變數的繞過（審閱者自己的報告與嚴重度判定沒有留存；可查的是三輪結果檔：1683 筆輸入裡 lint 放行的 1078 筆，神諭全判一致）；找到表裡一句（S1 的重導向目標「bash 判 ambiguous redirect、不執行，照收」）與實作不符——只有會展開的目標（`>{a,b}`）才是 ambiguous，不會展開的 `>{a}` bash 會建出字面檔名 `{a}` 的檔，而 lint 在靠管線過濾的群組裡其實一律擋（目標字元集 `FL_REL_TARGET_RE` 不含大括號；宣告且被觸發的 step 不檢查重導向目標，L3）；已更正（R46 宣稱查核再更正一次：這句的第二版寫成「一律」，過寬）。**限制：bash 5.2.21（CI 實際用的版本）本機沒有、未實測。**
  - **神諭（第 1–3 列、logic 第 4、5 列；放行條件 3、4、7）**：新增 **primitive 稽核**——PRELUDE 把 `[`、`test`、`printf` 換成記錄**實際** argv 的函式（函式優先於 builtin；PRELUDE 內部一律改用 `[[ ]]`，不經過它們），並在每個命令之前（任何行程，不只主 shell——群組跑在管線的子殼層裡，`{RUNNER_TEMP[0]}>` 改寫的值到主 shell 結束時早就看不到）比對 `HOME RUNNER_TEMP GITHUB_WORKSPACE TMPDIR PATH IFS BASH_ENV ENV` 與五個通道。判讀（`aud_violations`）：`test`／`[` 的 argv 不在三種形狀、`printf` 的第一個參數是選項或格式不在封閉列舉、信任變數的值變了。這與 PR 文字有沒有出現在 log 無關，所以**不需要任何 payload**：lint 放行 ∧ 有違反 ⇒ 繞過、lint 擋下 ∧ 有違反 ⇒ 一致（取代「誤擋」）。**與 DA 的 C3 原文有偏離**：C3 要求 `[`／`test` 的 `$#` 等於 lint 的詞數；我實作的是「argv 在文法的三種形狀裡」——不需要 lint 輸出它的詞模型，抓的是同一類缺陷（`test {-v,"$X"}` 的 argv 是兩個運算元、第一個是 `-v`），代價是看不到「詞數對、形狀也在三種之內、但詞的身分不同」的錯位。結果：**「文法外」類別 301 → 264**——51 個簽名消失（40 個改判「一致」：神諭直接看到了違規；11 個是 `restrict-r44-test-shapes-corpus` 的第 016–026 個隨一元運算子清單補全移到 good fixture、lint 改放行），另有 14 個新 step 簽名；簽名數照實測對齊，各 fixture 檔頭有 R46 註記。注入探針逾時也跑（前一版的條件含 `o != "timeout"`，「注入完成之後才被 `/bin/sleep` 拖逾時」判量不到）；宣告而沒有觸發的 step 不進文法（`in_grammar`；**R46 宣稱查核更正**：前一版宣稱與 lint 的 `flat_trigger` 同一把尺，其實只看 `|` 字元，而 `flat_trigger` 先剔除 `||`——只含 `||` 的宣告 step 因此被神諭當成在文法內、稽核把它報成繞過〔`audit-declared-step-or-only-not-in-grammar`，先紅後綠〕。現在複製 `flat_trigger` 的第一種讀法；第二種讀法〔字面常數代換之後才出現的 `|`，如 `${{ '|' }}`〕沒有複製，那種 step 神諭當成不在文法內），探針與稽核都不把它報成繞過。`oracle_selfcheck` 31 → 38 項（三個稽核、逾時後注入、範圍閘、負對照，以及宣稱查核之後補的「只含 `||` 的範圍閘」）。**第一版稽核的兩個錯，自己抓到**（該版沒有進 commit、當時的 log 沒留存，這兩句是當時的紀錄，沒有再驗證）：(a) 把 `SHELLOPTS` 放進信任快照，`set -o pipefail` 本來就會改它，每一步都被報成違規（lint 擋下的 step 因此都判「一致」，先前單檔跑出來的「一致」被這個誤報污染）；(b) 包裝函式裡的 `set +T`（關 functrace）在管線的子殼層讓 DEBUG trap 被改掉，pipefail 探針判「被換掉」、「量不到」從 26 跳到 66——改成在 DEBUG 的防護條件裡跳過來自包裝函式的呼叫。
  - **網（放行條件 5、8）**：`--strict` 組新增維度 11（`STAGE_CELLS`，27 格：大括號 × `test`／`[`／`printf`／`echo`／`exit`／外部命令、具名 fd 與陣列參照 × 重導向方向、`printf` 的轉換規格；每格一個 lint 結論，擋下的由稽核／哨兵／信任變數直接看到、七格沒有觀察簽 `文法外`）。**文法語料的取樣池這是第三次要跟著文法收窄**：`a{b,c}`（會展開的大括號詞）原本放在 echo／printf／`test` 的參數位置——產生器因為作者先在 P1 判大括號惰性、只把它放在作者認為無害的位置，所以 `test {-v,…}` 這一格從來沒被取樣；換成不展開的 `a{b}c`，會展開的那一類改由維度 11 逐位置明寫；另加 trap 動作裡有管線的產生式（R43 第 18 列的殘餘）。**`opsweep.py`**：`killed_expected` 前一版只數 `KILLED`，兩條 `yaml_decode_scalar` 的預期存活（`shell:` 無值時 `IndexError`，`CRASHED`）因此沒被報成等價性不成立——**我的疏漏**：R44 的全輪 log 就列了這兩條，我讀了「非預期 0」沒有拿 `EXPECTED_SURVIVE` 的 66 條對「預期 64」；現在任何非 SURVIVED 的狀態都推翻等價論證，**全輪**結束另外對帳（每條都必須對到一個存活的突變體），兩條已移除（現為 64 條）。**兩條 `_cmdsub_end_case` 的理由改寫**：R44 把它們說成「同第 0 條」（`==↔!=|1`，被殺的那條）——那個前提是錯的，`|1` 被殺是因為單行輸入（`a#b`，`!=` 讓 `at_word` 恆真），與換行到不到得了無關；這兩條只在 `c == "\n"` 那一支被走到（替換**本體**含換行）才與原碼不同，插樁計數那一支在整套 selftest 與 600 個多行構造（差分模糊測試，預設與 `--strict` 各一輪）裡執行 0 次；有界證據，不是證明。mutation 靶 472 → 485（13 個新靶，守新規則與新神諭，其中「只含 `||` 的宣告 step」一個是宣稱查核之後補的；其中「稽核不查 printf 的格式」第一次存活——探針用 `printf '%n' HOME` 時信任變數稽核也會報、掩蓋了格式稽核，改用非信任變數後殺掉）。
  - **區域 opsweep 的存活者（R46 新寫的程式碼本身要有網）**：`--since 2835ead`，115 個突變體，第一輪 5 個非預期存活——`a,b`／`1..3` 這類沒有大括號的詞（殺 `drop "{"`）、`{a>out.txt`（殺具名 fd 的 `}` 運算元）、`trap : {EXIT,0}`（`trap` 的訊號位置，殺 `p0 == "trap"`）、`date +%Y-%m-%d`／`echo 100%`（殺「printf 以外的命令也被查格式」）各補 fixture；`printf` 守衛的 `_fl_lit(args[0])` 運算元**是冗餘的**（`_fl_value` 對雙引號裡的 `V` 片段略過、其他非字面片段更早就被擋），直接刪掉、不補殺手也不列 `EXPECTED_SURVIVE`。最後一輪：114 個突變體、殺 110、存活 4（全為預期）、非預期 0。
  - **工具缺陷（logic 第 2、3 列、security 第 5 列；放行條件 9）**：`lint-ci-log-filter.sh --selftest` 在 `shopt -s nullglob` 下 `grep -qs '^1 ' "${resd}"/*.cnt` 在還沒有任何結果檔時沒有檔案運算元、改讀 stdin——`printf '1 x\n' | LINT_SELFTEST_FAILFAST=1 … --selftest` 的第一圈就 break、一張 fixture 都沒跑（rc=1、「正向 fixture 是 0 個」）；stdin 是開著的管線時整個卡住；`mutation_check.py` 的 `lint` 守備單位就用這個模式、而且繼承呼叫端的 stdin。修法：整個 selftest `exec < /dev/null`、兩處 grep 各加 `/dev/null` 當運算元、`mutation_check.py` 兩處 `stdin=subprocess.DEVNULL`、`run.sh` 加回歸測試；FAILFAST 下缺 `.cnt` 且沒有任何失敗回報時算失敗（前一版靠後面的數量門檻碰巧兜住）。`inputs_digest` 對 `__pycache__` 看絕對路徑、`.git`／`.pytest_cache` 看相對路徑——checkout 放在任何叫 `__pycache__` 的目錄底下時每個輸入都被排除、digest 恆為空雜湊，快取 key 不再隨輸入而變；三個名字一律看相對 root 的部分。
  - **R45 的 LOW 與文字（requirements、regression、security 各列）**：`FL_SPECIAL_VARS` 前一版註解說「全集」卻沒有逐名比對——現在用 bash 5.3.15 的 man page「Shell Variables」一節逐名比對（111 個名字；手冊另列的 `_` 不收——bash 每個命令之後覆寫它，沒有證據它能執行命令或改寫信任變數），補 `GLOBSORT`（5.3 新增）與 `auto_resume`；`$GITHUB_ENV` 的鍵加 `GIT_*` 前綴（`GIT_SSH_COMMAND`、`GIT_EXTERNAL_DIFF`、`GIT_ASKPASS` 讓 git 執行命令）與 `LOCPATH`／`GCONV_PATH`／`NLSPATH`；`test`／`[` 的一元運算子補 `-b -c -g -k -p -t -u -G -N -O -S`（`test -S /var/run/docker.sock` 是常見寫法；仍不收 `-v -R -a -o`）——原本當作「運算子清單拒絕邊界」的 11 個 restrict 例子移到 `good-r46-test-harmless-unary`；`$GITHUB_PATH`「不碰工作區」的宣稱改寫成實作真正保證的（不含 `$GITHUB_WORKSPACE` 的寫法與 `..`，只擋拼法）；**宣告且被觸發的 step** 也受 R44 的新規則影響，#60 代價表只量了群組內——補 `restrict-r46-declared-triggered-costs`（七個日常寫法，在 11e2b8f 放行、現在擋；都沒有會執行 PR 文字的效果）並讓訊息依 step 種類說「群組裡」或「run 區塊裡」；R44 改寫的三張 good fixture 補回 `restrict-r46-was-good-*` twin；oracle.py、test.yml、test/README、CHANGELOG R42 條目裡過期的通道敘述更正；本條 R44 條目裡的分組、「每一張都過神諭」、「macOS job 只跑 codex-call 的 bats」、快取句等就地更正（見各處的「R46 更正」）。PR body 的 R42 區段更正與 #33 決策留言的更正指標在推送之後才套用，不在這個 commit 裡。
  - **刻意不改的一條（logic 第 6 列：注入探針只在沒有非字面 `${{ }}` 的分支）**：`--strict` 的 P3 在靠管線過濾的 step 裡拒絕非字面運算式（RULE），宣告而沒有觸發的 step 不進文法（L3）——lint 放行、同時帶非字面運算式的 step 只有「宣告且沒有觸發」那一類，而那一類現在由 `in_grammar` 排除在探針與稽核之外；所以在文法內不存在需要那個分支跑探針的 step。這是依構造的論證，不是量測；**R46 宣稱查核更正**：前一版這句不成立——`in_grammar` 與 `flat_trigger` 對只含 `||` 的宣告 step 判得不同（上面「神諭」一條），那類 step 的非字面運算式探針因此被漏掉；`in_grammar` 對齊之後這句才依構造成立（`flat_trigger` 第二種讀法觸發的 step 神諭當成不在文法內，這個缺口沒有補、也沒有量測）。
  - **我自己在這一輪的錯**：(1) `EXPECTED_SURVIVE` 沒有對帳（上面）；(2) P1／P2 的逐原語核對是對著 R43 報告看到的拼法做的，第二個讀者核對的是「文字對得上程式」、不是「程式對得上 bash 的展開階段」；(3) 先前說「`printf {-v,x} y` 目前放行」是錯的；(4) 神諭稽核第一版的兩個錯（`SHELLOPTS` 誤報、`set +T` 弄丟 DEBUG trap），自己抓到；(5) 文法語料的取樣池第三次忘了跟著文法收窄；(6) 一個 mutation 靶存活是因為探針選了會被另一條稽核掩蓋的輸入（`HOME`）；(7) `in_grammar` 的註解宣稱「與 `flat_trigger` 同一把尺」而我沒有對照實作，宣稱查核（A1）抓到只含 `||` 的宣告 step 兩邊判得不同；(8) 更正的文字本身又寫錯：宣稱查核在 R46 自己新寫或更正的句子裡抓到不少 FALSE（`oracle.py` 註解的 `301 → 259`、「重導向目標一律擋」、「`in_grammar` 同一把尺」、「19 張裡 16 張」）——一句話在寫下時讀起來自洽，不代表它對得上程式。
  - **宣稱查核（推送前）**：對 CHANGELOG 的這條與 R43 條目的 R46 更正、lint／oracle／test_validate 的檔頭註解、以及要送出的 PR／issue 文字做一輪逐條對抗式核對（六組唯讀 agent，約 550 條原子宣稱）：10 條 FALSE、約 35 條 PARTLY、約 15 條 UNVERIFIABLE，全部更正或標明（更正散在各條，標「R46 宣稱查核」）；一條查出真缺陷（`in_grammar`，上面「神諭」一條）。更正動到快取 key 的輸入，所以量測在 `f690f4b` 上整輪重跑（opsweep 全輪除外，理由見量測段）。

  **量測（本機 macOS、bash 5.3，沒有 `/proc`；CI 的 lint／神諭以 Linux（ubuntu，bash 5.2.21）為準，macOS job（bash 5.3.15）跑 lint selftest、神諭子集與文法語料；CI 對 mutation 只跑 `--check-targets`；量測樹 `f690f4b`——本輪的 `2992737`、`aee5d67`、`296457d`、`f690f4b` 是 squash 前的 WIP、不在遠端；全輪 opsweep 與 `--since` 的三輪區域預檢是在 `2992737` 上量的，其後只改了註解、docstring、fixture 檔頭、一條訊息字串，以及 `oracle.py` 的 `in_grammar`（不在 opsweep 的範圍；lint 嵌入的 Python 與 `2992737` 比對 AST 逐字相同），所以 opsweep 沒有重跑，其餘各項在 `f690f4b` 上整輪重量；`2835ead`、`11e2b8f`、`df5e7a5` 是已推送的 PR 頭；量測途中發現而修掉的問題——區域 opsweep 的存活者、`EXPECTED_SURVIVE` 對帳、神諭稽核第一版的兩處錯、一個 mutation 靶存活——都寫在上面；`test_validate` 與 `run.sh` 輸出裡的 `ResourceWarning: unclosed file` 是 R44 就有的既存警告，這輪沒有處理）**：
  selftest 290 正向／508 規則紅／160 解析紅／114 張訊息斷言／33 張逐步斷言（compgen：bash 5.3.15 的 83 個 builtin／保留字都在 `FL_BUILTINS ∪ FL_KEYWORDS` 裡）；`oracle_selfcheck` 38 項全過；
  fixture 神諭 1665 個 step：一致 1133、不一致 319（全部已知：類別 G 8、S-2 3、文法外 264、文法外-without-proc 2，其餘走 `KNOWN_DISAGREE`）、不可比 187、量不到 26（與 R44 同一組步驟）；
  產生語料預設組 624 個 step：一致 516、不一致 62（全部已知；類別 G 1、S-2 60，另 1 條走 `KNOWN_DISAGREE`〔`gen-d-yaml-tag-bang`〕）、不可比 46、量不到 0（與 R44 逐數相同）；`--strict` 組 115 個（維度 11 新增 27 格）：一致 78、不一致 29（全部已知；文法外 28、文法外-without-proc 1）、不可比 8、量不到 0；
  文法語料 100 格：lint 100／100 放行、神諭 100／100 一致；`opsweep.py --verify-expected` 對 739 檔產生語料（`--strict` 組 115 檔）驗證 64 條 `EXPECTED_SURVIVE` 全 ✓；`test.yml` 的 `--strict --require-run-steps` rc=0；`test_validate.py` 153 條 OK；mutation 靶清單 485 個全部恰好命中一次。
  **全輪 opsweep**（不帶 `--since`，`--jobs 9`，最終樹上整輪）：1389 個突變體——殺 1325（當掉 130、逾時 1、只被產生語料抓到 0）、存活 64（預期 64、**非預期 0**）、語法壞掉 0；40.6 分（開跑時一分鐘平均負載 19；中途讀數沒有留存）。R46 新增的全輪對帳通過：預期存活的突變體數（64）等於 `EXPECTED_SURVIVE` 的條數（64），每一條都對到一個存活的突變體。**區域預檢**（`--since 2835ead`）三輪：115／115／114 個突變體，非預期存活 5／1／0——上面「區域 opsweep 的存活者」一條。
  **mutation 全輪**（`git archive f690f4b` 副本、`--no-cache --jobs 8`，沿用 0 靶）：485 靶 → 481 殺／0 存活／4 預期存活／0 靶壞；82.9 分（每靶 10.3 s；牆鐘；開跑時負載 26.98）。`test_validate.py` 檔頭預先寫的「485 → 481／0／4／0」與實測相符，所以量測之後沒有為它重跑任何一組。
  **run.sh**（真實路徑，最終樹，負載 20.70）：全部通過——shellcheck、py_compile、各 lint、神諭、形狀普查、`assert-tap-complete` 自測，以及 bats 194 個案例全 ok。
- **verify R43（4 lens + DA + Codex 跨模型 leg，`gpt-6-astra`／medium）— 1 HIGH、11 MEDIUM blocking、11 LOW；五條 leg 判 FAIL（logic、security、regression、DA、Codex），requirements 判 PASS 但被 DA 駁回、協調者同意，聚合判 FAIL。**
  CI 在 `11e2b8f` 上是綠的。報告的中心發現（DA）：缺陷從「字串的形狀」搬到了「允許清單元素的語意」——R42 的正面文法把形狀收窄了，但文法裡每一個原語本身是不是惰性，沒有人逐個核對。HIGH：
  群組裡**未加引號**的 `[ -n $PR_TITLE ]`（同理 `[ $P ]`、`[ $T = WIP ]`、`test -z $B`）`--strict` 與預設模式都放行，bash 把標題斷詞後的 `-v PWD[$(命令)]` 交給 `test` 的 `-v`，對陣列下標做**算術求值**，
  下標裡的命令替換就執行了（bash 5.2.21 與 5.3 實測，可寫 `$GITHUB_ENV`，run 文字裡沒有 `GITHUB_ENV` 這個詞）——推翻前一版 P1「在 step 的 shell 裡執行的只有 `FL_INERT` 的八個 builtin、`NAME=值` 指派、`trap <動作> EXIT`」背後「這些都是惰性」的前提。同一個機制還有：加了引號的 `[ -v "$X" ]`、
  整數特殊變數的指派（`RANDOM=`／`SRANDOM=`／`OPTIND=`／`HISTCMD=`）、`printf` 的選項只看原始拼法（`printf "\<換行>-v"`）。放行條件的十三條在報告末段；縮小允許清單、不回到否定清單的方向在報告的「本輪的中心發現」段。**修法方向（DA 與協調者提出，使用者回覆「好，可以開始」同意開工）：縮小允許清單，不回到否定清單；P1、P2 的文字逐個原語改寫，並交給另一個讀者核對。**
  - **文法（第 1–5、8、11、13–15 列）**：`--strict` 下，命令**參數**裡的參數展開（`$NAME`、`${…}`）一律要在雙引號裡（不是只擋 `[ -n $X ]` 那幾種寫法——是形狀無關的規則；指派右值不在此限，因為 bash 不對它斷詞、不 glob；預設模式不跑正面文法，`[ -n $X ]` 仍 rc=0）；
    `test`／`[` 只收三種形狀（零個或一個運算元、`FL_TEST_UNARY` 的運算子加一個運算元、運算元加 `FL_TEST_BINARY` 的運算子加運算元），`-v`／`-R`／`-a`／`-o`／括號都不在裡面，運算元不得有未加引號的 glob 字元（宣稱查核抓到，見下）；
    bash 特殊變數（`FL_SPECIAL_VARS` 與 `BASH_`／`COMP_`／`LC_`／`READLINE_` 開頭）不得指派；`printf` 的格式參數判 quote removal **之後**的值（`\<換行>-v` 還原成 `-v`）；`--strict` 下過濾器路徑不得以 `-` 開頭（`python3 -Xneutralise.py` 是選項、改讀 stdin 執行群組輸出；`PIPED_RE` 與 strict TAIL 各一道，預設模式只有 `PIPED_RE`，而它只在該行是唯一的過濾管線時擋得到）；
    宣告 step 的 `trap` 動作字串裡的管線也要求 pipefail（前一版「觸發」與「要求」用了兩把尺）；`$GITHUB_ENV` 的鍵擋的是 step `env:` 那組啟動鍵與信任變數的超集（另擋 bash 特殊變數與 `GITHUB_`／`RUNNER_`／`BASH`／`PYTHON`／`NODE_`／`LD_`／`DYLD_`／`COMP_`／`LC_`／`READLINE_` 開頭），`$GITHUB_PATH` 的值要是絕對路徑、不展開 `$GITHUB_WORKSPACE`、不含 `..`；
    五個 runner 通道（`ENV`／`PATH`／`OUTPUT`／`STATE`／`STEP_SUMMARY`）共用一個產生式：只收 echo／printf 的參數全是字面（雙引號裡只准 `$HOME`／`$RUNNER_TEMP`／`$GITHUB_WORKSPACE`）`>>` 寫進它本身，唯讀 `< "$GITHUB_…"` 也收（`tee -a "$GITHUB_OUTPUT"` 因此 RULE；R43 的字面 `>> "$GITHUB_OUTPUT"` 反而被擋，現在放行）；
    重導向後面的數字詞緊接重導向（`>> 2>/dev/null`）、具名 fd `{NAME}>`、`NAME=$(mktemp …)` 當別的命令的參數都不收。
  - **神諭（第 6、7、16、22 列與注入探針——探針回應的是第 1–3 列）**：EXIT 組合在 errexit 下**跑使用者的 trap 動作**（`__orc_ret … && :`，動作字串後補一行 `:` 讓 DEBUG 看得到最後一條管線）；逾時分支保留已寫進通道的 PR 文字；
    新增**注入探針**——神諭給環境變數（`$PR_TITLE` 等）的值是純標記，所以結構上看不到「環境變數的值被 shell 再次求值」；現在把 `PR_TITLE`、`PR_BODY` 與 `env:` 裡值含 `${{ }}` 運算式的鍵換成會留下哨兵的 payload（`PWD[$(…)]`、`-v PWD[…]`、`-n -o -v PWD[…]`、一行純程式碼）再跑一次——
    只在 `--strict` 的檔、run 文字沒有非字面 `${{ }}`、lint 放行而判定一致的 step 上（**放行而哨兵有東西 ⇒ 繞過**），或判為誤擋的 step 上（**擋下而哨兵有東西 ⇒ 改判一致**，不再歸文法外）。
    第一版的條件寫成「判定不是一致」，於是 lint 放行而標記沒外流的那一格（判定本來就是一致）根本沒跑到探針——`oracle_selfcheck` 第 29 項用「永遠放行」的替身抓到、修好。python3 stub 現在照真 CPython 的行為：沒有腳本參數就把 stdin 當程式讀（`-Xneutralise.py` 的 SyntaxError 把第一行印到 stderr）。
    「文法外」類別的訊息措辭由「沒有外流」改成「神諭沒有觀察到外流」，並註明這個類別不是安全證明（類別名稱仍是「文法外」）；`--min-comparable N`（第 22 列）讓一組檔的「可比 step」少於 N 個就 rc=1。
    **神諭多了觀察能力之後，三處舊簽名變成過期（類別閘門是雙向的，這是設計）**：`bypass-r42-trap-unquoted-var-action` 與 `restrict-r42-was-good-strict-group-forms` 的第 1 步原本簽「文法外」，現在判一致；`bypass-r42-trap-action-registers-mktemp` 的 KNOWN_DISAGREE 移除。
  - **網（第 9、10、22、23 列）**：`region_since` 展開類別方法（`_Sh.parse_command` 等各算一個單位；前一版只看頂層函式）；13 個失效突變體——12 個補了預設模式的 fixture 或雙胞胎（新形狀 3 張、雙胞胎 5 張，見檔頭）、1 個（`_logical_lines` 的 `.strip()`）逐一提殺手假設後列 `EXPECTED_SURVIVE`（消費者都不錨定字串開頭；差分模糊測試 160 個 step 0 區分）；
    四條 R42 生產限制各補 rule-red fixture 與具名靶（trap 動作裡的 `exit`、`env:` 設定信任變數、`$GITHUB_ENV` 字面值裡的 glob、mktemp 重新指派）；R44 新增的規則中 11 條各配一靶（過濾器路徑 `-` 開頭的 strict TAIL 那一層列 `EXPECTED_SURVIVE`），通道寫入的 echo 選項／printf 格式／單行限制、`$GITHUB_PATH` 路徑、mktemp 當參數、重導向目標是重導向這六條只有 fixture、沒有 mutation 靶，由區域 opsweep 涵蓋；
    mutation 靶 456 → 472；mutation 快取的輸入排除 `.pytest_cache`（第 23 列：用 pytest 跑過 `test_validate.py` 後，`validate`／`neutralise` 兩組共一百多個靶的快取不再整批失效）；macOS 神諭子集加 `*r44-*` 並要求至少一個可比 step。
  - **區域 opsweep 的存活者（R43 第 9 列的延續；R44 新寫的程式碼本身要有網）**：`opsweep.py --since 11e2b8f` 第一輪跑在精簡之前的樹上（253 個突變體，跑到 252 個時停掉——樹已經改了，不再有意義；49 個非預期存活，另有 7 個預期存活）；
    其中 20 個隨精簡消失（抽成 `_fl_t_text`：`_fl_value`／`_fl_parts` 共用、各只剩一個判準，`_fl_command` 的雙引號 trap 動作還有第三份、帶「首字元」運算元，列在 `EXPECTED_SURVIVE`；`_fl_env_key_denied` 列了五個運算元而沒有任何鍵只被三個冗餘的命中——縮成兩個、
    其餘由載入時的 `_fl_env_key_cover_problems` 斷言涵蓋；`_fl_chan_line_ok` 對 V 片段先判種類的運算元，V 片段的文字是變數名、不含換行、`=`、`/`，不必判）、17 個被 `84e7512` 已提交的 fixture 殺掉（14 個由 `chan-lines`／`test-shapes` 兩組語料的四張 fixture，3 個由手寫的 brace-word、redirect-spaced）、12 個要新殺手：
    **新增 `*-r44-surv-corpus` 兩張**（放行 21、被擋 28：通道的多重導向、`>` 截斷、目標名含通道字樣、參數含通道字樣、特殊前綴指派、trap 動作裡的管線）與兩張手寫 fixture
    （`good-r44-declared-trap-no-pipe`：宣告 step 要先被觸發——run 文字有 `|` 字元（連續兩個 `||` 除外）或提到 `$GITHUB_ENV`／`$GITHUB_PATH`——才會走到 trap 動作的檢查，所以這張用引號裡的 `|` 觸發、同時沒有任何寫出來的管線；`good-r44-gh-path-literal-workspace-text`：放行方向——
    `"/opt/${HOME}GITHUB_WORKSPACE"` 的字面片段文字剛好等於 `GITHUB_WORKSPACE`，拿掉 `k == "V"` 的運算元會被誤擋）。**第二輪（精簡後的樹 `c02484f`，227 個突變體，`--jobs 6`，67.9 分）**：殺 218（當掉 36、逾時 0、
    產生語料抓到而 selftest 沒抓到的 0）、存活 9（含預期的口徑）＝預期 8＋非預期 1；非預期那一個補上面第二張 fixture 後，以 opsweep 的 `run_mutant` 單獨重判為 KILLED（一個不在樹裡的 `rerun_surv.py`；不是全輪重跑——fixture 只增不減，已殺的突變體不會復活）。
    預期存活新增 1 條：`okp` 的 `first[1] in ("HOME", "RUNNER_TEMP")`——依三條上游不變式（字面片段相鄰已合併、V 片段的名字只會是 `FL_GHVALUE_VARS` 的三個、`GITHUB_WORKSPACE` 在下一個條件被同一則訊息擋掉）等價，理由寫在 `opsweep.py`。
    **批次工具的盲點（自己的）**：`batchkill`（逐 step 比對候選語料的判定）把「突變體當掉」看成「沒有判定」＝放行，所以「當掉型」的殺手它回報「沒有區分者」，而真正的 `selftest` 會抓到（`_fl_body` 的 `"piped" in ctx` 在群組 ctx 沒有 `piped` 鍵時 `KeyError`）；
    因此每個殺手都用 opsweep 自己的 `run_mutant` 重判，不用批次工具的結論。
  - **全輪 opsweep 的 54 個長期存活者（放行條件 9 的「做一次不帶 `--since` 的全輪」做了，而且抓到東西）**：量測提速之後全輪只要 70–80 分鐘，於是在 `8d26e3d` 上做了（1374 個，69.4 分）：殺 1264、存活 110＝預期 56＋**非預期 54**，另有 1 條 `EXPECTED_SURVIVE` 被殺。
    **54 個非預期存活在 `11e2b8f` 上也全部存活**——不是 R44 引入的，是從來沒被看過的長期缺口：`_word`（預設模式的詞法器）1 個、模組層級的 YAML 結構分類器 53 個；`--since` 區域掃描看不到它們（R44 沒改那些行），這正是 R43 第 9 列預告的盲區，只是這次是「從來沒有網」而不是「網失效了」。用完整 selftest（不提早結束）重判一樣存活，所以不是量測提速造成的。
    處置（**R46 更正分組**：54＝41［19 張模糊測試 fixture 殺得掉］＋4［只有手寫 fixture 殺得掉：`odd|2` 靠 `restrict-r44-stray-line-boundary-char`、`owner[k] == r|2` 靠 `bypass-r44-two-block-scalars-filter-in-other-key`、`if seen == 0 and not bad` 的兩個靠 `good-r44-require-run-steps-pass`（`==↔!=` 那個另有 `vacuous-r44-no-run-steps`）］＋1［`rc_all`：`vacuous-r44-no-run-steps` 與 selftest 的多檔 rc 檢查都殺得掉］＋8［沒有任何殺手、靠論證］；分組是逐 fixture 單獨跑突變版 lint 模擬 selftest 判準得出的，不是整套 selftest；下面 (1)(2) 的「45」是這 23 張 fixture 合起來殺的，不是模糊測試獨力殺的；對外寫的「補上 54 個長期缺口的網」該是 **46 個**）：(1) 45 個用**差分模糊測試**殺掉——`yamlfuzz.py`／`yamlfuzz2.py` 產生幾千個 YAML 結構變體（tab 縮排、文件標記、空白行與註解、清單項與 key 的各種寫法、flow／anchor／tag、單雙引號裡的反斜線、奇怪的行界字元、`steps:` 之後的同層 key、尾端空白行、`run:` 後接空白值…），`ydiff.py` 逐檔比對基準與突變版 lint 的輸出，`mkfix_yaml.py` 對每個突變體挑「可斷言」的最小殺手（類別翻轉，或基準有一則訊息突變版沒有並用 `# EXPECT-MSG:` 釘住）、貪婪集合覆蓋、每一張都過神諭（**R46 更正**：「每一張過神諭」是空的——19 張裡 15 張是「不可比（PyYAML 也拒絕）」、2 張的 `steps:` 在 jobs 層、PyYAML 看到一個叫 `steps` 的 job 而得 0 個 step，只有 2 張有可比的 step（共 4 個、全一致）；YAML 結構層本來就是神諭的盲區，L5），收成 **`ci-log-filter-{good,restrict}-r44-yamlstruct-*.yml` 19 張**（這些工具**不在樹裡**；進樹的是 fixture、selftest 的多檔 rc 檢查與 8 條 `EXPECTED_SURVIVE`）；
    (2) 手寫 4 張：`good-r44-require-run-steps-pass`（帶 `--require-run-steps` 的放行檔）、`vacuous-r44-no-run-steps`（`# EXPECT: vacuity`，沒有 run step ⇒ VACUOUS）、`restrict-r44-stray-line-boundary-char`（U+0085 的 repr）、`bypass-r44-two-block-scalars-filter-in-other-key`（**同一個 step 有兩個 block scalar 時，把 `| python3 scripts/neutralise.py` 藏在 `if:` 的內文裡**——拿掉 `owner[k] == r`，`run:` 會連 `if:` 的那幾行一起算而被放行；這本身是個 bypass 形狀，現在 RULE）；
    (3) selftest 新增**多檔 rc 聚合檢查**（第一個檔紅、最後一個檔綠，rc 要是 1；CI 正是一次餵全部 workflow，而 `rc_all = rc_all or rc or …` 退化成「只看最後一個檔」時沒有任何單檔 fixture 會紅）；
    (4) 剩下 8 個各有結構論證、列進 `EXPECTED_SURVIVE`，能驗的都驗了：`odd = next((ch for … len(ch.splitlines()) > 1 …))` 的第一個運算元對單一字元恆為假（窮舉全部 Unicode 碼位，`splitlines()` 長度最大是 1）；`seen` 只有初始化、`+= 1`、`== 0` 三處；`owner[]` 只在設 `SCALAR` 的兩處一起賦值；`_word` 的單引號內容在 `C` 視圖裡恆為空白（另有 5000 個引號形狀的差分模糊測試 0 個區分）等等。**這 8 個靠論證加有界的模糊測試，不是靠任何一張 fixture 會紅；輸入集合是我挑的，這與 fixture 同一個弱點**。
    **被推翻的一條舊論證**：`EXPECTED_SURVIVE` 裡的 `_cmdsub_end_case` 的 `at_word = prev in SHELL_WORD_BREAK or prev == "\n"` 原本寫「依構造等價」，這一輪的全輪裡它被殺了（舊樹上也被殺）——那條等價論證是錯的，條目已移除。`--verify-expected` 在產生語料上沒抓到它，是因為語料沒有那個形狀（又一次「零區分≠等價」）。
    **這一段自己犯的錯**：(a) `ydiff.py` 用 `hash(k) % 1000` 當突變版腳本的檔名，53 個突變體之間會碰撞、後來的沿用先前那個的腳本，部分「殺手清單」因此是別的突變體的——`mkfix_yaml.py` 逐個重新比對所以挑出來的 fixture 可信，但「0 個殺手」的名單被污染過，改成流水號後重跑；(b) `mkfix_yaml.py` 以檔名當 key，兩批候選目錄都有 `cNNNNN.yml`，寫出來的 fixture 與評估的不是同一個檔，改成完整路徑；(c) `# EXPECT-MSG:` 的內容不可含「`# LOG-FILTER`」字樣（寫進註解行會被 lint 讀成真的宣告），而我為此截斷訊息時 `.rstrip(" \`")` 把結尾的反引號也削掉，剛好是一個突變體與基準唯一的差別（基準 ``&a x` ``、突變版 ``&a x ` ``），只有最後在 opsweep 重判才看到那個突變體還活著。
  - **R46 更正：R44 改寫了三張 good fixture、沒有留被擋的版本、也沒寫**（R45 regression 第 4 列）：`good-r37o-dqbrace-brace-end-overrun-strict`（`echo ${A}` → `echo "${A}"`）、`good-strict-group-forms`（`${PR_TITLE}` → `"${PR_TITLE}"`）、`good-r42-flat-opsweep-positives`（`echo Value >> "$GITHUB_ENV"` → `echo NAME=Value >> …`）。R42 的慣例是把新被擋的寫法留成 `restrict-*-was-good-*`；R46 補回三張 twin（`restrict-r46-was-good-*`）並在三張 good 的檔頭加註（同前綴另有兩張來自 R45 verify 第 1 列的大括號展開，不屬這三張）。
  - **R44 的宣稱查核**（對本條、lint 檔頭、README、`test_validate.py` 檔頭、PR body、#60／#82 草稿共 22 段；422 個 agent、每段一位抽取者、一位對抗驗證者、有爭議的再由兩位獨立挑戰；pin sonnet）：55 條確認、115 條有爭議、19 條推翻，逐條判過。**一個真缺陷、兩個工具缺陷、其餘是措辭與數字**：
    (1) **真缺陷**：`test`／`[` 的運算元是未加引號的 glob 字元（`*`、`?`、`[`）時，bash 在執行 `test` 之前先做檔名展開——PR 的 checkout 裡的檔名成了運算元；工作目錄有檔名 `-v` 與 `PWD[$(命令)]` 時，`[ * ]` 展開成 `[ -v PWD[$(命令)] ]`，下標被算術求值（bash 5.3 實測：`[ * ]`、`test *`、`printf * x` 都執行；bash 3.2 不執行；
    `printf "%s\n" *` 與 `echo *` 安全）。前一版 `_fl_test_ok` 只檢查形狀、不檢查運算元，docstring 卻寫「運算元是字面或加了引號的展開」；上一段的獨立審閱者也沒抓到——**它是 R43 同一類缺陷（惰性是原語加運算元的性質）的又一個實例**。`_fl_test_ok` 現在拒絕未加引號的 `*`、`?`、`[`（`printf` 的首參本來就由 `_fl_lit` 擋）；
    補 `restrict-r44-test-glob-operand`（8 個 step，逐步簽 `文法外`）與 `good-r44-test-glob-harmless-contexts`（9 個放行的對照）、一個具名 mutation 靶；
    (2) **工具缺陷**：`opsweep.py` 的「`EXPECTED_SURVIVE` ≤ 區域 10%」上限直接拿含 `|L行號` 的突變體 id 去比、恆為 0，從來沒有生效（README 與檔頭一直宣稱它擋著）——改用 `base_id`；`--verify-expected` 只讀檔案第一行的 `# LINT-ARGS:`，`shellgen.py --strict` 的檔先有 `# KNOWN-CLASS:` 檔頭，22 個 `--strict` 檔因此以預設模式跑、等價論證在那些檔上沒有被 `--strict` 檢查——改成與 `oracle.py` 同一個讀法（整個檔、`re.M`）；
    (3) **文字**：「所以五個通道都寫不出第二行」是假的（echo 選項與 printf 跳脫擋掉的是靠展開寫出第二行；單行檢查只在 `$GITHUB_ENV`／`$GITHUB_PATH`，其餘三個通道可以用引號裡的字面換行寫出多行）、lint 檔頭 L1 的 `tee /proc/$PPID/fd/1` 其實是 RULE（要加雙引號才收）、`-R` 在 bash 5.2.21／5.3.15 實測不求值（沿用 R43 報告的保守擋法）、「六條 leg 全部判 FAIL」、`$GITHUB_ENV` 的鍵「照 `env:` 的同一個標準」其實是超集、
    #60 代價表的「25 個自然寫法」實為 24 個（13 擋、11 放行；重測確認）、`$GITHUB_PATH` 與 P3「宣告的 step 不在此列」的範圍、README 的 `分隔字引號擺法 12`（程式碼是 16）與 `codex-call-detach` 的「全部走同一條路徑」（有 5 個不走）、`shellgen.py` 檔頭的「17 格」（11e2b8f 版產生器在 R44 最終 lint 下是 22 格）等；全部改了。
  - **量測提速（本輪新增；沒有改任何判定）**：一輪量測要跑幾百個突變體、每個都把 919 張 fixture 的 selftest 從頭跑到尾（約 70 秒），機器又常在負載 35–200 之間，R44 一輪量測因此要 4 小時以上。三處改動：
    (1) `lint-ci-log-filter.sh --selftest` 每張 fixture 的檢查彼此獨立，改成平行跑（預設 min(核心數, 8) 個、`LINT_SELFTEST_JOBS=1` 就是原來的串行；每張的訊息與計數寫進暫存檔、依序號彙整，訊息順序與串行相同）——負載 120–170 下串行 323 秒、4 個平行 50 秒、8 個平行 32 秒，閒時整套 15 秒；
    (2) 突變測試只問「有沒有任何一張 fixture 變紅」：`LINT_SELFTEST_FAILFAST=1` 讓第一張失敗就停（沒有失敗時照樣全跑，結論相同）；
    (3) `LINT_SELFTEST_FIRST=<檔>`（只改順序）：`opsweep.py` 每殺一個突變體就記下殺它的 fixture，次數多的先跑，清單存在 repo 外的 `~/.cache/idd-verify/opsweep-killers.txt` 跨輪沿用，`mutation_check.py` 的 lint 守備單位用同一份。
    **驗證**：39 個樣本突變體以「完整 selftest」與「提早結束＋排序」各判一次，殺／存活與分項標籤逐個相同（31 殺、7 當掉、1 存活）；12 個突變體在同一時段交替計時：完整 725 秒、只提早結束 512 秒、提早結束加排序 398 秒（55%）。**誠實：突變掃描只快約 2 倍，不是 10 倍**——殺手不在清單裡的突變體仍要跑 40–60 秒；`OPSWEEP_FULL_SELFTEST=1` 可退回完整 selftest 重做這個對照。
    更大的槓桿沒做：用覆蓋率挑 fixture、或把靶搬到中研院統計所的 Linux 叢集（要先裝 bash 5.x 與 PyYAML）。
  - **文字（第 12、17–21 列）**：lint 檔頭 P1 逐原語改寫成九類封閉列舉（除第 1 類沒有隱藏效果、第 7 類做什麼不在檢查範圍外，每類寫隱藏效果與文法條件）、P2 補第二個來源（trap 動作裡的管線）、P3 補「宣告 step 一旦觸發，文法不收非字面運算式」；L6 補 errexit 的 `&&` 清單豁免（單獨 `false | tee log && echo ok` 是 rc=1，後面再接命令才被蓋掉——第一次寫反了，實測更正）；
    #60 代價表按 R44 重測（24 個自然寫法 13 擋 11 放行）並**更正第 2 節**：`{ echo "${!PR_TITLE}"; } 2>&1 | …` 被寫成「經過濾」，但 `${!X}` 的下標算術照樣執行命令替換——群組擋得住輸出（錯誤訊息與 stdout）、擋不住副作用；
    `oracle_selfcheck` 的 docstring 數量與批次編號改成機械守衛（`main()` 開頭比對「共 N 項」與 `len(CHECKS)`）；shellgen 維度 10 的標題統一、`regexcheck.py` 檔頭、偏離 (b)(c) 的文字、PR body 的「逐條」。
  - **P1／P2 文字交給另一個讀者核對**（放行條件 12；規格散文的自我矛盾靠另一個讀者，不靠作者重讀）：獨立的 opus 審閱者把九類逐條對到程式碼、實測約 115 個輸入——**沒有 HIGH**；五處措辭問題已改：「展開一律在雙引號裡」是假的全稱（指派右值被接受，改成「命令參數裡的參數展開」）、
    「每個命令的 fd 1、fd 2 都在 neutralise.py 的管線上」與後半句「shell 自己開的重導向只落在第 8 類點名的目標」有張力（重導向到檔案）、第 8 類漏列被接受的唯讀 `< "$GITHUB_ENV"`、「非 ASCII 字元、任何控制字元（引號裡也一樣）」的括號被讀成連非 ASCII 也包含，對引號內的非 ASCII 不成立（收下，危險的 Unicode 行界字元由 `splitlines()` 閘擋成 PARSE）、
    第 9 類的「單行、鍵、PATH 絕對路徑」只對 `$GITHUB_ENV` 與 `$GITHUB_PATH` 成立。審閱者同時確認為真的：九類與程式碼對原語的處理一一對應、命令替換（除了登記的 `NAME=$(mktemp …)` 整個指派）／`[[`／`((`／算術／背景／here-string／process substitution／函式／`eval`／`time`／`builtin` 全部 RULE、
    `[ "$X" -eq 1 ]` 的算術比較在 `test` builtin 下**不**執行下標命令替換（所以第 3 類點名的是 `-v`；`-R` 沿用 R43 報告的保守擋法，bash 5.2.21／5.3.15 實測它不求值）、宣告 step 的 `trap 'false | true' EXIT` 在無 pipefail 的樣板下 RULE。**這位審閱者漏了上面宣稱查核抓到的 glob 運算元缺口**——「交給另一個讀者」少了一個讀者的下限不是 100%，這也是為什麼宣稱查核與審閱各自留著。
  - **本輪中途自己發現的缺陷**：(1) 注入探針（R43 第 1–3 列要求）的放行方向第一版沒跑到；(2) 文法語料的產生器自己走出了文法（未加引號的 `$PR_TITLE`）——產生器改成只放加了引號的形式，並依 R43 第 18 列補失敗路徑（獨立的 `false`、`exit`、會失敗的 `test`）；
    (3) L6 補 errexit 豁免（R43 第 21 列）時第一版寫反；(4) 上面的批次工具盲點。
  **量測（本機 macOS、bash 5.3，沒有 `/proc`；CI 的 lint／神諭以 Linux（ubuntu，bash 5.2.21）為準，macOS job（bash 5.3.15）跑 lint selftest、神諭子集與文法語料（R46 更正：前一版寫「macOS job 只跑 codex-call 的 bats」，與 test.yml 不符）；CI 對 mutation 只跑 `--check-targets`，全輪不在 CI 裡；量測樹 `1d2196c`——本段的 `1d2196c` 是 squash 前的 WIP、不在遠端；已推送的 PR 頭是 `2835ead`，其前身是 `11e2b8f`；量測途中發現的主要問題寫在上面）**：
  selftest 286 正向／495 規則紅／160 解析紅／101 張訊息斷言／27 張逐步斷言（compgen：bash 5.3.15 的 83 個 builtin／保留字都在 `FL_BUILTINS ∪ FL_KEYWORDS` 裡）；`oracle_selfcheck` 31 項全過；
  fixture 神諭 1614 個 step：一致 1045、不一致 356（全部已知：類別 G 8、S-2 3——其中一個 step 兩類都算——、文法外 301、文法外-without-proc 2，其餘 43 條走 `KNOWN_DISAGREE`）、不可比 187、量不到 26；
  產生語料預設組 624 個 step：一致 516、不一致 62（全部已知；G 1、S-2 60、`KNOWN_DISAGREE` 1：`gen-d-yaml-tag-bang`）、不可比 46、量不到 0；`--strict` 組 88 個：一致 58、不一致 22（全部已知；文法外 21、文法外-without-proc 1）、不可比 8、量不到 0；
  文法語料 100 格：lint 100／100 放行、神諭 100／100 一致；`opsweep.py --verify-expected` 對 712 檔產生語料（`--strict` 組 88 檔，修了 `LINT-ARGS` 的讀法之後真的以 `--strict` 跑）驗證 66 條 `EXPECTED_SURVIVE` 全 ✓（**R46 更正**：其中兩條 `yaml_decode_scalar` 的 `len(v) >= 2` 守衛（`'` 與 `"` 各一條）其實被殺——`good-empty-shell-value`（`shell:` 無值）讓突變體 `IndexError`、全輪 log 列為 `CRASHED`，而 `opsweep.py` 的 `killed_expected` 只數 `KILLED`，產生語料也沒有 `shell:` 無值，所以這一行對那兩條是空的；R46 移除這兩條，現為 64 條，`killed_expected` 改成任何非 SURVIVED 的狀態、全輪結束對帳預期存活數）；`test.yml` 的 `--strict --require-run-steps` rc=0；`test_validate.py` 153 條 OK；mutation 靶清單 472 個全部恰好命中一次。
  **全輪 opsweep**（不帶 `--since`，`--jobs 9`，最終樹上整輪）：1374 個突變體——殺 1310（當掉 121、逾時 1、只被產生語料抓到 0）、存活 64（預期 64、**非預期 0**；R46 更正：當時 `EXPECTED_SURVIVE` 有 66 條而不是 64——66−64＝上面那兩條 `CRASHED`，我讀了「非預期 0」就收、沒有對帳）、語法壞掉 0；78.6 分（開跑時負載 12；中途讀數沒有留存）。區域掃描（第二輪 227 個；提速後 `2a0a379` 上另跑的 230 個——殺 222、存活 8、非預期 0，上文沒有逐項描述）都是它的子集；區域那兩輪的結果當歷史留著。
  **mutation 全輪**（`git archive 1d2196c` 副本、`--no-cache --jobs 8`，沿用 0 靶）：472 靶 → 468 殺／0 存活／4 預期存活／0 靶壞；58.4 分（每靶 7.4 s；牆鐘，這一輪中途機器沒有睡眠），開跑時一分鐘平均負載 91（閘門在負載 186 時等了約一分鐘才放行——別的程式在建置）。
  提速前的上一輪（`44f3f3b`）是 471 靶 → 467 殺／0 存活／4 預期存活，工具時鐘 107.2 分、牆鐘 155.6 分——差的約 48 分鐘是機器睡眠（17:09 起離開電源、闔蓋與維護睡眠；睡眠不會把靶誤記成殺掉：驗證指令 rc≠0 才算殺，逾時用單調時鐘、判「量不到」、不改退出碼）；提速後、全輪 opsweep 之前在 `2a0a379` 上也量過一輪：472 靶 → 468／0／4／0，55.3 分。
  **量測提速對判定的影響**：mutation 的 lint 守備單位用提早結束＋殺手排序，其餘三個守備單位（validate、neutralise、oracle 系）沒有改；468 殺這個數字在提速前後的樹上一致。
  **快取**：這一輪重建的 `mutation-cache.json`（472 靶）隨本次一併提交；對推送的樹不帶 `--no-cache` 重跑 `mutation_check.py`，472 靶全數沿用、重跑 0 靶（**只改 `CHANGELOG.md`** 不在任何守備單位的輸入裡；R46 更正：前一版寫成「文字改動——CHANGELOG、檔頭註解以外的檔——不在任何守備單位的輸入裡」，過寬——`lint` 守備單位的輸入含檔頭註解與 fixture，`validate`／`neutralise` 也受多種文字編輯影響；發版前仍要加 `--no-cache`）。快取檔從 R38 起就在樹裡，不是 R44 才提交——每輪改的是內容。
  **run.sh**（真實路徑，最終樹，負載 23）：全部通過——shellcheck、py_compile、各 lint、神諭、形狀普查、`assert-tap-complete` 自測，以及 bats 194 個案例全 ok（包含上一輪唯一紅的 `codex-call-detach.bats` #85，R10-FR1）。**這個結果不是一次過來的，照實寫**：(1) 第一次（`44f3f3b`）193 ok／1 not ok，紅的是 #85；R44 的 diff 不碰 `bin/codex-call` 也不碰那支 bats，單獨重跑綠，當時機器負載 110–200、有別的 session 在建置，判為環境造成，之後在低負載下整套重跑確認；(2) 量測提速（平行 selftest）之後第一次跑 `run.sh` 在 shellcheck 階段 rc=1——`lint-ci-log-filter.sh` 的子殼層改計數觸發 SC2030／SC2031（info，`run.sh` 與 CI 用預設嚴重度）；那是我只用 `-S warning` 檢查造成的，子殼層改計數、經檔案回傳本來就是設計，加了一行有說明的 `# shellcheck disable=SC2030,SC2031` 後過。
- **verify R41（4 lens + DA + Codex 跨模型 leg，`gpt-6-astra`／medium）— 1 HIGH、14 MEDIUM blocking、7 LOW；六條 leg 全部判 FAIL。**
  CI 在 `45dee04` 上是綠的。報告的中心發現是 DA 的結構判斷：R40 新寫或改動的六個函式（`ctl`、lastpipe、`trap_cmd`、`github_env_write`、
  `_param_end`、字面運算式）上找到約 30 個作者沒點名的相鄰放行輸入——**用否定清單模擬 bash 不收斂**；而 test.yml 的 15 個靠管線過濾
  的 step 全是 `{ 命令表; } 2>&1 | …neutralise.py`（命令表只有簡單命令與管線，沒有控制流程、trap、shopt、eval、source、`$GITHUB_ENV`、`${{`）。R42 換方向：`--strict` 對靠管線過濾的 step 改成**正面文法**（只收點名的形狀，其餘一律紅：文法外是 RULE，詞法層讀不了的是 PARSE），
  R40 的 pipefail 模擬與 `$GITHUB_ENV` 形狀清單整段刪除；神諭加 pipefail 探針與跨 step 通道觀測，這兩類不再只靠 fixture。方向與放行條件
  的六處偏離在寫程式之前記在 #33 的決策留言（(a)–(f)；(a)–(d) 寫明替代的驗收，(e)、(f) 只寫了處置與理由）。修正以 TDD 為主：WP1 的 20 張 fixture 中 17 張在 `45dee04` 上讓 selftest 失敗，1 張（`good-r42-testyml-shapes`）設計上就綠、是回歸釘，2 張（`bypass-r42-ghenv`、`bypass-r42-pf-outside-grammar`）整檔本來就紅、只有步驟層級是紅燈；WP4、WP5 與 opsweep 補的 fixture 也先看過紅；WP3 是刪除，WP6–WP8 以突變體與 `oracle_selfcheck.py` 驗證，WP9、WP11 是 CI 與文件，這幾包沒有先紅的紀錄。新 mutation 靶：40 個新靶與改錨點靶的子集跑過（見下方），最後一個（trap 動作的片段種類）由全輪確認：
  - **正面文法（第 1–8 列，放行條件 1–4）**：自己的斷詞器逐字元吃掉 run 文字，每個字元都要屬於點名的詞元之一，**不讀** `shell_scan`
    的挖空結果（第 15 列的缺陷在挖空層）；產生式寫在 lint 檔內（`run_F`／`run_D`／`PREFIX`／`TAIL`／`LIST`／命令／`WORD`／重導向）。
    群組裡的命令名只收未加引號的字面；bash 的 builtin 與保留字只收 `echo`、`printf`、`test`、`[`、`true`、`false`、`:`、`exit` 八個——
    builtin 與保留字的全集是 bash 5.3 的 `compgen -b`／`-k`，selftest 另外檢查 PATH 上的 bash 列出的名字都在裡面。於是 `shopt`、`eval`、
    `source`／`.`、`alias`、`enable`、`mapfile`、`coproc`、函式定義、`if`／`for`／`while`／`case`、加引號或跳脫的保留字（第 4 列的
    `'fi'`、`\done`）都在文法外，第 2–7 列的輸入全部 RULE。`trap` 只收 `trap <動作> EXIT`／`0`：單引號動作照同一套文法剖析、不准
    `exit`，雙引號動作只准展開 `NAME=$(mktemp 字面…)` 登記過的變數（第 6 列；放行條件 11 的 `trap "rm -rf $tmp" EXIT` 因此放行）。
    `$GITHUB_ENV`／`$GITHUB_PATH` 只收一種寫法：`echo`／`printf` 的參數全是字面（值裡准展開 `$HOME`、`$RUNNER_TEMP`、`$GITHUB_WORKSPACE`）、
    `>> "$GITHUB_ENV"`；唯讀寫成 `< "$GITHUB_ENV"`。第 1 列的十三種寫法全部 RULE。宣告了 `# LOG-FILTER:` 的 step，run 文字裡有寫出來的
    管線或提到這兩個通道，也要落在同一套產生式裡（`flat_trigger`——這是字元檢查，擋寫出來的管線，不擋執行時組出來的）。文法信任其值的
    變數由各產生式的集合聯集而成（`FL_TRUSTED_VARS`），run 裡不得指派、`env:` 不得設定；模組載入時斷言產生式正規式裡寫出的變數名
    都在集合裡。`${{ }}` 先代換再剖析：字面常數換成它的值，所以第 8 列收掉群組的字面字串現在 RULE（決策 (f)：宣告的 step 不擋非字面
    運算式，另開 #81）。R37–R40 累積的 pipefail 模擬（`_pipefail_holds`）與群組規則，以及 R40 新寫的 `ctl`、`trap_cmd`、lastpipe、`github_env_write`，整段刪除；pipefail 只剩兩個
    來源：`bash` 樣板與群組前的 `set` 前綴。**預設模式從此不檢查 `$GITHUB_ENV`／`$GITHUB_PATH` 寫入**（`github_env_write` 原本兩種模式
    共用；強制預設模式時，`45dee04` 就有的 fixture 只有 3 張由擋變放行（`bypass-r40-github-env-redirect`／`-env-tee-stdin`／`-path-heredoc`），其餘輸出逐位元組不變；HEAD 上連 R42 新增的共 10 張由擋變放行（WP3 當時量到 7 張）；WP5 的預設模式 fail-closed 另使 4 張新 fixture 由放行變 PARSE）。移植時在原型上修掉三處（先在照原型寫的版本上看到紅）：兩個繞過——trap 動作與外層共用
    mktemp 登記（PR 文字在離開時被當成程式碼、寫進 `$GITHUB_ENV`）、`printf -v` 經 `$GITHUB_ENV` 產生式指派信任變數——各一張 bypass fixture；另一處是誤擋：宣告的 step 裡的非字面運算式（由 `good-r40-ghexpr-declared-step` 守）。
    放行條件 1 與 2 互相矛盾（決策 (a)）：以第 2 條為準，R41 DA 的 `shopt -s lastpipe` 之後頂層的 `set -o pipefail` 改為 `restrict-r42-shopt`，子殼層裡的 `set +o pipefail`（`good-r40-pf-subshell-off-*`）改為 `restrict-r42-subshell-scope`；「不過度擋」改由 test.yml 本身與 `good-r42-testyml-shapes`（R42 開始時 test.yml 的 15 個過濾 step 加 macOS bats 宣告 step 的逐字複本；WP9 新增的兩個過濾 step 只由 test.yml 本身守）守。
  - **代價（第 10 列，放行條件 11）**：誤擋改用性質描述、不再列「九類」：在 `--strict` 下，靠管線過濾的 step 通過 `shell_scan` 之後，文法的補集一律 RULE（`shell_scan` 看不懂的先判 PARSE；宣告了 `# LOG-FILTER:` 的 step 只在觸發時才套用），fixture 裡每一個「靠管線過濾、被文法擋下、神諭實跑沒有外流」的 step 在檔頭簽
    `KNOWN-CLASS: 文法外`（神諭的已知類別，見下）。R41 regression lens 的 26 個自然寫法，`45dee04` 的 `--strict` 放行 22 個、現在放行 9 個：
    16 個新被擋（控制流程 9 個、mktemp 以外的命令替換 `$(cat VERSION)`、`time`、`shopt` 兩個、`trap … ERR`、動作裡有 `$(jobs -p)` 的
    `trap … EXIT`、`grep … "$GITHUB_ENV"`），3 個新放行（`trap "rm -rf $tmp" EXIT`、`trap 'echo set up done' EXIT`、`$GITHUB_PATH`
    值裡的 `$HOME`）。21 張 strict good fixture 不在文法裡：19 張成為 `restrict-r42-was-*`（15 張改名、4 個多 step 檔把文法外的 step
    拆出），2 張併入 `restrict-r42-subshell-scope`。test.yml 為了新文法只改一行既有的 run 行（`45dee04` 的第 213 行、現為第 232 行；WP9 另加的 step 見「網」：`$(bash --version | head -1)` →
    `$(bash -c 'echo "$BASH_VERSION"')`，決策 (e)）。控制流程的產生式追蹤在 #82；神諭的「執行名稱稽核」（直接觀測斷詞器與 bash 對同一字串的切法是否一致；R42 設計的 D11，未實作）追蹤在 #83。
  - **預設模式（第 9、15 列）**：只加兩條 fail-closed，不再多模擬 bash。巢狀在 `${…}` 裡的 `${ cmd; }`／`${| cmd; }` 與最外層同一條
    （`${` 後面接空白、tab、`|` 或行尾就不解析）；從掃描器沒能在同一行收掉的命令替換（跨行、heredoc、行尾註解、`$'…'`）回到雙引號之後，同一個字串再出現 `$(`／反引號就不解析。第 15 列的
    `_word` `p += 1` 由 `bypass-r42-default-k3` 殺掉。strict 不再經 `_Sh` 之後只剩預設模式走得到三個靶：兩個各補一張預設模式的雙胞胎（`good-r42-default-set-arg-cond-word`、`bypass-r42-default-group-proc-pid-fd1`），第三個（`_lex` 的 `$(case …)` 追蹤）雙胞胎做不出來，改用形狀不同的 `good-r42-default-subshell-cmdsub-case`。**預設模式仍開著的兩處**：R41 第 21 列（`opaque_cmd`：`${X:-shopt} -so xtrace`）沒有修，追蹤在 #79；跨行命令替換之後、**另一個**雙引號字串裡的命令替換（`echo "$(`⏎`true`⏎`)" "$(echo … >&2)" 2>&1 | …`）仍不解析、預設模式 rc=0，bash 5.3 實測外流——`--strict` 擋下（命令替換在文法外），追蹤在 #84。
  - **神諭（第 11–14、20 列，放行條件 5–8）**：
    · **pipefail 探針**：PRELUDE 的 DEBUG trap 在每條多段管線記下開始時的 pipefail（同一筆記錄另寫入 `masked` 欄位，目前沒有任何判定讀它）；DEBUG trap 被換掉、或主 shell
      沒跑到 EXIT，判「量不到」；`trap <動作> EXIT` 經 `trap` 函式與神諭的收尾組合（不組合的話，主 shell 裡的 `trap <動作> EXIT`（宣告的 step）會讀成量不到；靠管線過濾的群組裡的 trap 跑在子殼層、本來就讀得到）。
    · **跨 step 通道**：`GITHUB_ENV`／`PATH`／`OUTPUT`／`STATE`／`STEP_SUMMARY` 指到暫存檔，跑完看有沒有 PR 文字（比 lint 嚴：預設模式與宣告的 step 裡，lint 接受 `$GITHUB_OUTPUT`、`$GITHUB_STEP_SUMMARY` 的寫入（`--strict` 靠管線過濾的 step 一律 RULE——**R44／R46 更正**：R44 起五個通道共用一個產生式，字面 `>> "$GITHUB_OUTPUT"` 放行、`tee -a` 等一律 RULE，這句「一律 RULE」不再成立；R43 第 11 列指過它），神諭五個一起看）。strict 檔：RULE 且（pipefail 關或通道外流）⇒ 一致；放行
      且其一 ⇒ 繞過。前一版「唯一的 RULE 是 pipefail ⇒ 整步不可比」收窄：唯一的 RULE 是 pipefail、而且沒有任何多段管線跑完、通道也沒帶 PR 文字，才判不可比；其餘照探針判。
    · **已知類別「文法外」**：誤擋那一格、KNOWN_DISAGREE 之後才判；step 的每一條 RULE 都帶文法標記或是 pipefail、沒有外流、探針沒看到
      pipefail 關閉。檔頭簽名、雙向計數閘門；平台變體「文法外-without-proc」只在沒有 `/proc` 的平台計數。
    · **KNOWN_DISAGREE 記方向與內容雜湊**（第 14 列）：值改成 `{dir, hash, why}`，方向與 run 區塊的雜湊都要相符才算已知——登記成誤擋的
      條目不再吞得掉同一格的繞過。69 條（含 `_WITHOUT_PROC` 4 條）逐條實測：保留 34、改由檔頭簽名 28（文法外 25、文法外-without-proc 3）、
      過期刪除 7（R42 起判一致）；新增 8 條，現為 42 條。
    · **payload 脈絡與取最嚴重**（第 12 列）：加註解、算術、heredoc 內文三種脈絡；每一組適用的 payload 都判（heredoc 那一組只在運算式落在 heredoc 內文時適用；語法壞掉又沒外流的不參與排序），lint 放行時取最嚴重的一份。
    · **版本守衛**（第 13 列）：lint 檔頭 `# ORACLE-BASH-SUPPORTED: 5.2 5.3`，神諭的 bash 不在其中就具名退出；CI 的 macOS job 用 bash 5.3
      跑 lint selftest、只有 5.3 才有意義的 fixture 與文法語料。`GH_SAFE_EXPRS` 與 lint 那一份比對，不同步就具名退出（第 17 列的「共用同一份」）。
    · **第 20 列**：RULE 且逾時前已外流 ⇒ 一致。
    · 決策 (b)、(c)：第 5、6 條的原文驗收在新文法下跑不出來（突變的程式碼已刪；heredoc 與 `$((` 不論運算式規則都被擋），改用「永遠放行」
      的替身 lint 與 FLAT 的突變體；三種脈絡在替身 lint 上 rc=1、「字面代換也接受非字面」的突變體在 `ctx/comment` rc=1。`oracle_selfcheck.py` 10 → 25 項。
      > **R44 更正（#33 verify R43 第 20 列）**：這一段原本寫「pipefail 判定關掉的 FLAT 突變體神諭 rc=1、6 列判『繞過（pipefail）』」——**描述的不是實際量到的實驗**。
      > 實測：(b) 那個突變體在 `bypass-r40-pf-*`（15 張）上神諭 **rc=0**（文法已經把這 15 張全擋下，神諭看到的是「擋下、沒有外流」）；它判繞過的是 `bypass-r37b-strict-pipefail-template-*`
      > 上的 5 列（rc=1）；而「永遠放行」的替身 lint 在 `bypass-r40-pf-*` 上 rc=1（那才是這 15 張在神諭那一側的負對照）。(c) 的前提「原文驗收跑不出來」也不成立：
      > 條件 6 的原文驗收跑得出來、而且通過；替代驗收站得住，但描述的是另一個實驗。
  - **網（第 15 列，放行條件 9、10）**：文法語料 `shellgen.py --grammar` 從產生式取樣 100 格、每個放得進詞的位置以固定種子從 10 個詞裡抽（其中 4 個會展開 `$PR_TITLE`）：lint 100 格全收、
    神諭 100 格一致——其中 80 個靠管線過濾的格在 bash 裡沒有觀察到 PR 文字外流，另 20 個是宣告不過濾的 step、神諭只看 pipefail 與跨 step 通道、不判輸出外流（這是抽樣，不是證明：文法接受、而斷詞與 bash 不一致的字串，只有被抽到才看得到；
    CI 在 ubuntu 的 bash 5.2 與 macOS 的 5.3 各跑一次）。`oracle-r42-s2-flip`
    是 requirements c10 的翻色 fixture 收成的 must-fail 探針。mutation 靶 464 → 456：錨在刪掉程式碼上的 38 個退役、8 個改錨點，新增 31 個（FLAT 每條產生式限制一個、各配一張會殺它的 fixture，15 個——最後一個是 trap 動作的片段種類，見下；神諭 15 個；S-2 1 個），之後全輪再退役 1 個（見下方「mutation 全輪」）。
    opsweep `EXPECTED_SURVIVE` 48 → 44（決策 (d)：錨在刪掉程式碼上的四條移除；第 5 列 `'done' || :` 的同族輸入（跳脫的 `\done 2>/dev/null || :`）由 `restrict-r42-quoted-reserved-word` 釘住；字面的 `'done' || :` 沒有專屬 fixture，`--strict` 一樣 rc=1（命令名不是純字面）），
    之後 44 → 56（見下方「opsweep」）。
  - **文字（第 17–19 列）**：lint 檔頭改寫兩種模式（R42 起是兩套判準：`--strict` 的整條規則鏈是 `flat_step_rules`，預設模式不查
    `$GITHUB_ENV` 寫入）；「比預設模式多四條」改成三條並對應程式裡 `STRICT` 的四處用法；已刪的群組規則段落改寫成 `run_F` 接手的說明，
    「九類」代價清單改成性質；`--strict` 宣稱的性質（P1–P3）與照性質寫的已知限制（L1–L6：step 呼叫的程式、之前就在的狀態、沒有寫出
    管線的宣告 step、工作目錄、YAML、pipefail 以外的退出碼）寫進正面文法一節——L1 包括命令參數給的路徑（`tee /proc/$PPID/fd/1`
    照收）；規則層詞法一節的規則（fd 流向，`_analyse`）只有預設模式在跑，已知不涵蓋第 3 條（沒走到的分支裡的 `set -o pipefail`）隨模擬刪除；`GH_SAFE_EXPRS` 的
    「共用同一份」改成「神諭另有一份、載入時比對」（lint 檔內與 `oracle.py` 兩處說明）；`runner_exprs` 沒收尾的運算式照常判。oracle.py docstring 補判定表的 strict 疊加、
    兩個觀測、文法外、KD 格式與版本守衛；`mutation_check.py` 兩處把 key 寫成「剝掉註解的 AST」的說明改成原文，另一處指向 `_key_content` 的指標（該函式已不存在）改成 `source_for_key`；README 的前綴、檔數、項數；
    三張 `bypass-r40-github-*` 檔頭的 `PYTHONIOENCODING` 例子換成 `BASH_ENV`，前一版的說法標成更正、冒號之後那段標未證實（第 18 列）；
    `python3 -u` 的訊息（第 19 列）：`--strict` 已改（`FL_NEUT_NEAR_RE`，見正面文法一節），預設模式仍印「既沒有經 neutralise.py」，沒改。以上 lint 與 oracle.py 的改動都以「剝掉 docstring 的 AST 相同、bash 部分去掉註解
    行後相同」確認只動了文字。第 16 列（快取）見量測；第 22 列（issue 狀態段）在推送後更新。
  - **mutation 快取的環境指紋（第 16 列）**：前一版只記 PATH 上的 bash，神諭卻優先用 `/opt/homebrew/bin/bash`；`/bin/sh` 記的是 realpath，
    而 macOS 的 `/bin/sh` 是轉接程式、realpath 恆為 `/bin/sh`。現在記神諭可能選用的每一支 bash（`BASH_CANDIDATES`，測試以 AST 讀 `pick_bash` 迴圈裡的字面路徑（`shutil.which("bash")` 那一項不讀，由 PATH 上的 bash 那條指紋與假 bash 測試覆蓋）、斷言它們是子集）與 `/bin/sh` 的內容雜湊，及 `/bin/sh -c` 實際執行時回報的 `BASH_VERSION`／`KSH_VERSION`／`ZSH_VERSION`（dash 等其他 shell 三欄全空、彼此分不出）。測試 152 → 153 條（`grep -c "    def test_" ../pai-lenses/scripts/test_validate.py`）。
  - **opsweep 抓到的（`--since 45dee04`）**：第一次全輪掃描（程式碼在 trap 修法之前）：自 `45dee04` 起被改動的區域是 510 個突變體，**102 個非預期存活**（另有 9 個預期存活）——selftest 對它們一個也沒報紅；補巢狀 `${` 的行尾 fixture 與逐步斷言（`EXPECT-EACH-STEP`）之後重跑剩 100 個。`ef85adb` 上區域是 513 個，最終樹（`fa9f932`）是 519 個——多出來的是我刪死碼後進入範圍的 `_set_prefix_line`；最終結果見文末。逐個處置的經過與教訓：
    · 我先用「產生語料 712 檔上原碼與突變體的 (rc, stderr) 逐檔比對」把 100 個分成「可區分」與「零區分」，把零區分的當成等價候選。
      **這個分法是錯的**：零區分只說明語料沒有那個形狀。#29（`_fl_command` 拿掉 `w0 is not None`）被分在「零區分」，一行「只有重導向的
      命令」（`> out.txt`）就讓突變體崩潰。先用語料與候選庫（`killer_finder`／`combo_finder`，暫存工具、不在 repo）批次找殺手，最後 70 個改成讀突變後的那一行、逐一手寫殺手輸入並實測。
    · 殺掉的都補了測試（新 fixture、既有 fixture 加 `EXPECT-MSG`、或 selftest 的假 bash 檢查）——反例 fixture 在原碼上紅、突變體上翻綠，正向 fixture 在原碼上綠、突變體上翻紅或崩潰——不進 `EXPECTED_SURVIVE`。其中一個是**真缺陷**（不是 opsweep 報的、是處置時另外發現），其餘都是網的洞（原碼本來就擋、只是沒有測試釘住；下面第二個例子是我原本判成等價的）：
      `trap $X EXIT`（未加引號的變數當動作）被文法收下、bash 卻在離開時把 `$X` 的值當程式碼執行——`_fl_command` 的 trap 分支只寫了 P 與 D 的
      種類判斷、其餘落到「把 body 當文法剖析」，現在按種類拒絕（`bypass-r42-trap-unquoted-var-action`，mutation 靶 456 → 457 就是它）；
      宣告 step 的 `env:` 值寫在同一行（`env: ${{ fromJSON(…) }}`）時鍵名看不到，`_env_names` 記成 `?`、fail-closed，但我原本判等價的那條
      `k == "?"` 拿掉後突變體只留具名啟動鍵、放行——補 `restrict-r42-declared-unseen-env-keys`。
    · 一個運算元是**多餘**的（`fl_tokens` 的 `;;` 偵測裡 `op == ";"`：迴圈依序 `&&`／`||`／`|&`／`|`／`;`，`s.startswith(";;", i)` 為真時只有 `;` 命中）——
      與 R40 同做法，拿掉運算元而不是列進 `EXPECTED_SURVIVE`；712 檔新舊輸出（rc＋stderr）逐位元組相同。
    · **最後一批 70 個我先用模板批量草擬了理由（草稿沒進 commit，開頭標「【有界：712 語料＋1804 組合候選零區分，非證明】」，內文卻論證同判），逐條驗證後 58 條是假的**：拿掉 `p[0] == "D"` 在 `'Value'` 這類字串上 `IndexError`；
      `"${HOME:-x}"` 的預設值；兩行 `set` 前綴、pipefail 在第一行；`"${HOME}"` 的變數名；`printf` 無參數與 `printf '-v'`；群組內先放一條 neutralise
      管線讓 R1 放行、而尾巴才錯；宣告 step 結尾的 `>`。共同缺陷：把「語料＋我手寫的輸入零區分」寫成「同值」，而每個缺口都是這 712 檔裡沒有的輸入形狀（診斷訊息那三個則是語料根本走不到的 bash 環境）。
      改成逐一提殺手假設（兩輪共 101 個手寫輸入）：58 個殺掉——10 張新 fixture、selftest 加**假 bash**檢查（`--check-compgen` 的版本字串、空版本行、
      rc≠0 時 stderr 的 `strip()`，真的 bash 只會走「一切正常」那條路）；只差訊息的突變體加 `EXPECT-MSG`（六張新的裡四張是單步 fixture、另兩張是多步）；12 個依構造等價，
      列進 `EXPECTED_SURVIVE`（44 → 56），**每一條給出理由：11 條是結構論證、互斥那一條是有界窮舉；其中 5 條點名它依賴的上游不變式，其餘靠區域代數或下游不讀該欄位**（`_fl_word` 的 mktemp 條件、`_fl_lines` 的命令恆非空、`PIPED_RE` 命中的是孤立管線…）。
      `FL_REDIR_BAD_RE` 與 `FL_REDIR_DUP_OK_RE` 互斥那一條用 `test/corpus/regexcheck.py` 窮舉：重導向字元加一個「其他字元」的字母表上長度 0 到 7
      的 21,435,888 個字串沒有一個同時命中（`--lint` 指向人為改成重疊的副本時會列出同時命中，我用它做過負對照，腳本本身不含這個對照；字母表與長度以外沒有量）。
    · 補簽：9 張既有 fixture（8 張 restrict、1 張 bypass）漏了 `# KNOWN-CLASS: 文法外`（21 條 step 簽名），fixture 神諭因此 rc=1；已簽，另有 5 張新 fixture 帶簽名（32 條），`FIXTURE_CLASS_TOTALS` 的文法外 39 → 92。
    · 另補 `parse-r42-default-nested-param-open-at-eol`：`_param_end` 巢狀檢查的 `j + 2 >= n` 拿掉後，巢狀的 `${` 落在行尾時突變體丟 `IndexError`
      （`echo ${X:-${` ⏎ `set -x; }}`，bash 5.3 是跨行的 `${ cmd; }`、會開 xtrace），與 R40 的最外層那條同形；parse-red 門檻 148 → 153（WP5 已到 152）。
    selftest 門檻最終是 269 正向／455 規則紅／153 解析紅／66 張訊息斷言／12 張逐步斷言（這一段的 fixture 處理完時是 268／454／153／65／11）（`EXPECT-EACH-STEP`：多步 fixture 每一步各自要有自己的 RULE 行——
      先前只判整張檔紅，某個守衛被拿掉、放行其中幾步時，只要還有一步被別的規則擋下就照樣綠）。**結果見文末量測**
  - **mutation 全輪抓到的**（`4faaea2`，`git archive` 副本、`--no-cache --jobs 8`，78.9 分鐘）：457 靶 → 452 殺／**2 個非預期存活**／3 預期存活；兩個都是 R42 改動之後才出現的：
    · 靶「`set` 前綴行尾的 `;` 不收」：`_set_prefix_line` 的 `toks[-1:] == [";"]` 是**死碼**——R42 起它唯一的呼叫者 `_fl_split_prefix` 的 `toks` 來自
      `_fl_lines`，`;` 是分隔符、不是詞，永遠不會出現在裡面。刪除；新舊 lint 對 877 張 fixture 與 812 個產生語料（共 1689 檔）的 rc 與 stderr 逐位元組相同；
      靶退役（457 → 456）；`good-r39-strict-set-prefix-semicolon` 仍釘住「`set -o pipefail;` 放行」。
    · 靶「runner 運算式的 payload 依賴前一個命令成功」（只拿掉**一組** payload 的 `|| :`）：R42 起每一組 payload 都判、取最嚴重，同一脈絡裡有兩組會收掉群組的
      payload（不加引號脈絡那組與註解脈絡那組），只改其中一組不改變任何判定。重新錨定成**所有** payload 一起拿掉；但 RULE-red 的 fixture 分辨不出（兩邊都判「一致」，
      只差 `oracle=` 欄的 `piped`／`not-invoked`），能分辨的只有替身 lint 全放行時的探針：補 `oracle-probes/payload-after-failing-command.yml`（`false ${{ … }}`，
      期待「把 PR 文字印到 stdout」那句來源分類），`oracle_selfcheck.py` 25 → 26 項，靶改由 `oracle-inverted` 守備，單靶實測殺掉。
    這兩個是**同一類**：R42 前半的改動（WP2 起 FLAT 改寫換掉 `_set_prefix_line` 的呼叫端、WP8 讓每組 payload 都判）讓先前的靶失去分辨力，到全輪才看得到；刪死碼與重新錨定是對全輪結果的處置，不是原因。所以最終量測不能用改動之前的樹。
  **我自己的錯**：WP5 把 `_lex` 的 `$(case …)` 追蹤列成預期存活候選，理由是「試了 22 種形狀找不到會翻色的輸入」——探針目錄留下 19 種（編號到 a22），多半是頂層或群組 `{ …; }`、沒有一個把 `$(case …)` 放進子殼層 `( … )`，而突變體多讀到的 `)` 在群組裡只是被略過的殘渣；翻色要子殼層 `( … )`（`good-r42-default-subshell-cmdsub-case`）。
  「找不到反例」被我當成等價的證據。WP6 的 commit 訊息把 KNOWN_DISAGREE 的帳記成「25 條改由類別宣告簽名」，34＋25＋7 只有 66、不是 69，漏了 without-proc 的 3 條；上面是逐條重算的數字。
  **同一個錯在這一輪反覆出現**：WP5 的 `$(case`、partition 的零區分、「殊途同歸」、測反方向的等價理由、最後一批 70 條的草稿，以及我暫存腳本
  `gen_expected.py` 裡的 `KILLED` 名單（不在 repo）——其中一條記成「已由 fixture 殺」的其實沒殺（`_fl_command` 指派判定的種類判斷，重跑顯示
  仍存活，補 `restrict-r42-flat-quoted-first-word` 才殺掉）。`test/opsweep.py` 的註解在 R36 就寫過「第二次踩」。這次寫進 `test/opsweep.py` 註解的規則：零區分只能寫「有界」，不能寫「等價」；「已殺要重跑對過」只寫在 `d725638` 的 commit 訊息裡（重跑用的 `rerun.py` 是暫存工具、不在 repo）。
  **量測（本機 macOS、bash 5.3；CI 以 Linux 為準）**：量測樹 `fa9f932`（mutation 全輪、opsweep）與最終 commit `d31ae51`（其餘）。本段與上文的 commit 雜湊（`4faaea2`、`fa9f932`、`d31ae51`、`120fbd4` 等）都是 squash 前的 WIP commit，保存在分支 `r42-fix`；PR 分支上 squash commit 的樹與 `r42-fix` 最後一個 commit 逐位元相同。兩者的差異是封閉列舉、只有這些：
  一張 fixture（`restrict-r42-flat-set-option-without-name`）、selftest 三組門檻（規則紅 454 → 455、訊息斷言 65 → 66、逐步斷言 11 → 12）、
  `oracle.py` 的 `FIXTURE_CLASS_TOTALS`（文法外 92 → 95）、`opsweep.py` 的一條 `EXPECTED_SURVIVE`；lint 內嵌的 Python（opsweep 的突變對象，也是 mutation 456 靶裡 290 個 lint 靶的對象）從 `fa9f932` 到 `d31ae51` 逐位元相同（184,797 字元，已比對）；之後只改了 `_set_prefix_line` 的 docstring 一句話（AST 相同）。mutation 另有 oracle 系兩個單位共 51 靶（`oracle.py` 的 `FIXTURE_CLASS_TOTALS` 一行不同）、validate 114 靶、neutralise 1 靶，不在這句的範圍。
  · selftest 269 正向／455 規則紅／153 解析紅／66 張訊息斷言／12 張逐步斷言（`EXPECT-EACH-STEP`）。
  · fixture 神諭 1216 個 step：一致 871、不一致 148（全部已知：107 步屬類別宣告——G 8、S-2 3、文法外 95、文法外-without-proc 2，其中一步同時算 G 與 S-2——另 41 步是逐條簽名的 `KNOWN_DISAGREE`）、不可比 171、量不到 26。
    產生語料：預設 624 個 step 一致 516／不一致 62（已知）／不可比 46／量不到 0；`--strict` 88 個 step 一致 58／不一致 22（已知）／不可比 8／量不到 0；
    文法語料 100 個 step 一致 100／不一致 0。`oracle_selfcheck.py` 26 項全數照預期。`--verify-expected` 57 條（712 檔，其中 `--strict` 組 66 檔）全部逐位元組相同。
  · **mutation 全輪**（`fa9f932`，`git archive` 副本、`--no-cache --jobs 8`，開跑負載 23.4）：456 靶 → **453 殺／0 存活／3 預期存活／0 靶壞**，94.4 分鐘、每靶 12.4 s（工具的單調時鐘、不含機器睡眠；bash 量到的牆鐘是 115.3 分鐘，中間機器睡了約 21 分鐘）。
    先前一輪（`4faaea2`）是 457 靶、452 殺／2 非預期存活（見上），處置後才是這一輪。
    · **mutation 在最終 commit（`120fbd4`）上重建**：`--no-cache --jobs 8`、worktree 上跑（快取 key 把整個 repo 當輸入，上面任何一處改動都讓它整批換掉，所以最終 commit 的快取只能是一輪全輪，不是沿用）：
    456 靶 → **453 殺／0 存活／3 預期存活／0 靶壞**，84.9 分鐘、每靶 11.2 s（單調時鐘與牆鐘一致，5094 秒，這一輪機器沒有休眠）。結果寫回 `mutation-cache.json`。
    驗證：在這個 commit 的 fresh `git archive` 加這份快取上跑 `--only 0,1`，沿用 2 靶、重跑 0 靶；再改 `test_validate.py` 一行，同一個靶沿用 0 靶、重跑 1 靶（快取確實會失效）。
  · **opsweep `--since 45dee04`**（`fa9f932`，519 個突變體、`--jobs 4`，193.3 分鐘，單調時鐘、不含機器睡眠；牆鐘 215 分鐘）：殺 496（當掉 68、逾時 0、產生語料抓到而 selftest 沒抓到的 0）／存活 23（預期 21、**非預期 2**）。
    兩個非預期都在 `_set_prefix_line`——我刪死碼（靶 399）時動到這個函式，它因此進入 `--since` 的範圍，既有的盲點才暴露：
    `len(toks) <= k + 1` 拿掉後，`set -o`（與 `-e`、`-eu` 合寫）少選項名時突變體 `IndexError`，補 `restrict-r42-flat-set-option-without-name`（3 步逐步斷言、簽名 3 條），單靶重跑殺掉；
    `toks[:1] != ["set"]` 拿掉後等價——唯一呼叫者 `_fl_split_prefix` 在呼叫前已 `break` 掉首詞不是 `set` 的行——列入 `EXPECTED_SURVIVE`（56 → 57；本輪自 WP10 的 44 起共 +13）。
    最終樹非預期 0：突變的程式碼逐位元相同，新 fixture 只會多殺，兩個存活另以單靶重跑確認（一個殺掉、一個列預期）；沒有在最終 commit 上重跑整輪（193 分鐘）；最終 commit 上重跑的是 mutation 全輪與 `run.sh`（見下）。
  · **`run.sh`**（最終 commit `120fbd4`，worktree＝git checkout，單獨跑——我的量測腳本串行、開跑一分鐘負載 23.1，同機其他 session 無法排除）：`✓ 全部通過`，rc=0、1187 秒；
    bats 194 案例 0 not ok、0 skip（`grep -c '^ok'` 數出 255 是含 node 與 pack 檢查的雜行，不是 255 個 bats 案例）。
    **先前在 `git archive` 副本裡跑過兩次**：放在 macOS 臨時目錄（`/var` 是指向 `/private/var` 的 symlink）底下的那次 6 個 detach bats 案例紅（`R7-D/R9`、`R9-A1`、`R10-L9-1`、`R10-FR1`、`R10-FR3`、`R11-HOOK`）：
    `own_workers` 用 `pwd -P`（`/private/var/…`）組 `pgrep` 的比對字串，worker 命令列卻是邏輯路徑 `/var/…`，兩邊對不上——位置造成、不是 R42（R42 沒動 `bin/` 與 bats）；
    放在沒有 symlink 的路徑底下的副本全過（255 ok、0 not ok，955 秒）。副本不是 git checkout，8 個 #48 的 bats 案例因此 skip、builtin-lenses 的 drift 檢查略過——所以最終的跑法
    是 worktree 這一次。這個測試對「樹放在 symlink 底下」敏感，本 PR 不處理。
- **verify R39（4 lens + DA + Codex 跨模型 leg，`gpt-6-astra`／medium）— 1 HIGH、11 MEDIUM blocking、6 LOW；六條 leg 全部判 FAIL。**
  CI 在 `6aced19` 上是綠的（R38 的平台那一半部分修好）。報告的中心發現：這一輪找到的每一個繞過，都落在神諭結構上
  看不到的地方——runner 運算式不代換、pipefail 不可比、每個 step 單獨跑所以看不到跨 step 的 `GITHUB_ENV`、逾時丟掉輸出、bash 版本；
  產生語料在 `--strict` 下對 R39 加的安全規則零鑑別力。R40 的方向是縮小神諭的盲區，不是再加 fixture。修正全部 TDD（fixture、
  selfcheck 探針或單元測試先在修法前看過紅；新 mutation 靶逐條實跑確認被殺）：
  - **`${{ }}`（第 1 列，HIGH）**：前一版只認點號的 `github.event.`／`github.head_ref`，檔內卻寫成「封閉列舉，只有這兩種」——
    `toJSON(github.event)`、`format('{0}', …)`、`github['event']…`、`env.X`、`steps.*.outputs.*`、大寫都放行，未加引號的四種相對
    c53ac22 是回歸（R39 放寬群組內的運算式遮罩）。反過來：靠管線過濾的 step，run 裡**任何非字面**的運算式都擋；運算式的邊界照
    運算式語言找（單引號字串裡的 `}}` 不收尾）。只放行字面常數與 GitHub 產生的八個純量欄位（`GH_SAFE_EXPRS`：PR 編號、base／head
    SHA、`github.sha`、run id／number／attempt，封閉列舉），順帶解掉 `.number`／`base.sha` 的誤擋。**神諭代換運算式**：非字面的依序
    換成七組逃出引號與群組的 payload（`RUNNER_PAYLOADS`），任何一組外流就算外流——關掉規則後神諭在 12 個 step 上判繞過、rc=1。
    三條「神諭不代換運算式」的 KNOWN_DISAGREE 過期刪除；`matrix.*` 這類作者控制的值也擋（它們可以經 `fromJSON(needs.*.outputs…)`
    帶進 PR 文字），改經 `env:`，`restrict-r40-ghexpr-*` 兩張釘住。
  - **pipefail 控制流程（第 5 列）**：範圍模型照詞元順序。條件（if／while／until／for／select／case、`&&`／`||` 右邊）裡的「開」
    不算數；迴圈本體裡的「關」作用到同一迴圈的所有管線；trap 動作非字面或含 `set`／`pipefail` 時，之後的管線一律當成關掉，
    而且之後的「開」蓋不掉（DEBUG trap 每個命令之前再執行一次——第一版讓之後的「開」蓋掉它，mutation 的 glob 靶存活才看到）；
    `shopt -s lastpipe` 之後的設定不分範圍。bash 5.3 實跑六種輸入的失敗都被遮蔽。
  - **前綴詞與 bash 5.3（第 7、10 列）**：`command`／`builtin` 是 builtin，加引號或跳脫照樣執行，改用字面值判；**保留字不在此列**——
    `'time' -p set -x` 執行外部 `time`、不開 xtrace（bash 5.3 實跑），R39 報告把它列成繞過，那一格不成立。`opaque_cmd` 認合寫的
    `-…o NAME`（`${X:-set} -euxo pipefail`）。`${ cmd; }`／`${| cmd; }` 在目前的 shell 執行（5.3 以前是 bad substitution），一律不解析。
  - **神諭（第 3、8、15 列、放行條件 12）**：逾時時保留部分輸出，已經外流就判繞過（前一版判量不到、rc=0）；S-2 的機制差分也禁止
    多出的 stderr 外流行（這一條能翻色的形狀要 Linux 的 `/proc`，本機沒有會翻色的網，寫進盲區段）；bash 樣板照旗標跑——`shell: bash`
    照 `-eo pipefail`、沒寫 shell 照 `-e`、封閉清單內的旗標翻成 run 第一行的 `set`（前一版照裸 bash 跑、二十個樣板不可比）。
    連帶：五張前一版刻意不可比的 fixture 與產生語料七個樣板量得到了，是保守誤擋，列 KNOWN_DISAGREE；payload 改成 `|| :` 開頭。
    不可比的 step 掛著 KNOWN_DISAGREE 時也算過期（前一版靜默保留）；`# ORACLE-COMPARABLE` 的檔每個 step 都要可比。
    第一版另外見到 `<<` 就不做 S-2 差分，產生語料 60 條 S-2 全掉成繞過（folded 成一行、沒有內文），撤回。
  - **`GITHUB_ENV`（第 9 列）**：DA 量到 `PYTHONIOENCODING` 經多行語法帶入後，每個過濾 step 右端 python3 的 stderr 原樣印出換行與
    行首的 `##[error]`。靠管線過濾的 step，把看不出是字面的內容寫進 `$GITHUB_ENV`／`$GITHUB_PATH` 就擋（封閉列舉三種：其他參數
    非字面、管線後段、heredoc／here-string）。神諭一次跑一個 step、看不到跨 step 的效果，三張列 KNOWN_DISAGREE。
  - **揭露（第 2、12 列）**：命令參數裡的 `/proc` 路徑與群組內自建的 symlink 寫進已知不涵蓋第二組第 5 條（參數分不出讀寫）；
    `python3 -u`／`-I`、`$GITHUB_WORKSPACE` 路徑、群組前的 `set +e`／`shopt`、`PYTHONPATH` 運算式、頂層 `export PYTHONPATH`、`../dev`——
    不放寬，restrict 兩張、KNOWN_DISAGREE、代價清單（改寫成性質，七類 → 九類）。R39 寫「不一致的 8 條都屬已揭露類別」——兩條不是。
  - **網（第 11 列）**：產生語料加維度 10（只靠一條規則擋下的群組形式三格）：把運算式規則關掉神諭判繞過、遮罩關掉判誤擋、`_redir_hit`
    關掉本機是 KNOWN_DISAGREE_WITHOUT_PROC 過期（Linux 上判繞過）。env 那一格第一版放了，神諭判誤擋才看到它在群組形式下不外流，
    拿掉並寫明。`f-inner-heredoc` 的 EOF 多縮排、什麼都沒量到——群組內部內容不再縮排。
  - **mutation 快取（第 4、17 列）**：key 丟掉註解，而 `test_validate.py` 讀 `# READ-SITE` 註解——改用原文；全部命中時也跑前置檢查；
    key 含 `/proc` 能力、`/bin/sh`、PATH 上的 `python3`、`ORACLE_LINT`；`--only` 命中時照印 RESULT；全部沿用時不印每靶耗時；
    `load_cache` 只收 killed／survived。測試 148 → 152 條（歷史數字；帶指令的現況宣稱只留在最新一段，R42 起是 153）。
  - **其他**：`run.sh` 的 `if …; then A && B`——A 失敗不觸發 errexit（第 6 列，我在 R39 自己引入）；opsweep 的 10% 上限改比區域內的
    預期存活（第 18 列）；test.yml 註解、fixture 檔頭、R38 段的分配數字（第 14、16 列）。
  - **最終量測抓到的**：opsweep 報 `_param_end` 的 `i + 2 >= len(line)` 拿掉後存活——`${` 落在行尾時 lint 丟 IndexError（traceback，
    不是不解析的訊息），而 fixture 檔頭寫「後面緊接空白、tab 或行尾」，行尾那一半沒有任何一張 fixture。補
    `parse-r40-param-open-at-eol`（沒有它時突變體過 selftest、有它時判 unknown-red），parse-red 門檻 147 → 148。
    opsweep 另外報的兩條 `_word` 存活是 R37 留下、R39 已揭露的兩條無解（R40 給 `_word` 加了 `src` 欄位，它又落進 `--since` 的區域）。
    **其餘 26 條全部落在 R40 自己新寫的 pipefail 控制流程上**（`ctl`、`trap_cmd`、`shopt_cmd`、`_pipefail_holds`、`opaque_cmd`、`runner_exprs`、
    運算式規則）——R40 的 fixture 釘住的是 R39 報告點名的那幾個輸入，沒有釘住機制本身，正是 R39 批評的形狀。其中三條引出**真的繞過**
    （pipefail 規則，bash 5.3 各自實跑 rc=0、沒有那一行時 rc=1）：`trap -- '-:||:;set +o pipefail' DEBUG`（前一版剝掉 `--` 之後把以 `-` 開頭的動作
    當成選項）；`shopt "$O" pipefail`（O=-uo）與 `shopt -uo "$N"`（非字面只記外流類命中，宣告了 `# LOG-FILTER:` 的 step 不看那一類）；
    `shopt -s "$OPT"`（OPT=lastpipe；前一版只認字面的 `lastpipe`）。四張 `bypass-r40-pf-*` 先在修法前看過放行。處置：13 張會翻色的 fixture
    （修法前的突變體逐一對候選輸入跑過，判定與原碼不同才收；第 13 張是修法後定向重跑 opsweep 時 `shopt` 名字清單那一支又存活，
    `shopt -s nullglob "$OPT"` 同樣是繞過）；mutation 加 5 個具名靶守這三個修法（其中兩個第一次跑存活：那兩張 fixture 走的是另一條路徑，
    改寫後才殺得掉——`shopt -uo -- "$N"` 的 `--`、lastpipe 那張中間的 `set -o pipefail`），4 個 R40 靶的錨點跟著改寫的程式碼更新；四處多餘的運算元拿掉（`len(l) > 1`、glob 事件的 `not e["on"]`、`st and ev["loop"]`、
    `runner_exprs` 的 `q`——每一處在註解寫了為什麼等價）；`EXPECTED_SURVIVE` 加兩條（`nloop` 的 `±1`、多出來的 `done`＝bash 語法錯誤）。
  **我自己的錯**：run.sh 的 `&&`；R38 放行條件 10 要我把 `${{ github.event.* }}` 寫成已知限制，我寫成規則加「封閉列舉」；
  「不一致的 8 條都屬已揭露類別」沒有逐條核對；快取 key 丟掉註解，而我在同一個檔寫了「一行 `#` 就可能改變某個靶的生死」。
  **量測（本機 macOS，CI 以 Linux 為準）**：selftest 273 正向／389 規則紅／148 解析紅／5 張訊息斷言；fixture 神諭 975 個 step：一致 693、不一致 62（全部已知）、不可比 202、量不到 18；產生語料 712 個 step：一致 580、不一致 78（全部已知）、不可比 54、量不到 0；`oracle_selfcheck.py`
  10 項 ✓；mutation 靶 464 個，全輪 （`8f2d21a` 的 `git archive` 副本，`--jobs 8`）殺 461／存活 0／預期存活 3／靶壞 0，牆鐘 75.9 分（每靶 9.8 s）；同一棵樹立刻重跑：464 靶全部沿用快取、203 秒（R40 起全部命中也跑前置檢查——R39 的 16 秒沒有這一步）；R40 第一次量測（`7ced8fe`，`--no-cache`）459 靶 456 殺／0 存活／3 預期、68.0 分；opsweep `--since 6aced19` （本輪最終，`8f2d21a`）379 個突變體：殺 365（其中當掉 35、逾時 0）／存活 14（預期 12、非預期 2＝R37 留下的兩條無解），牆鐘 74.8 分；R40 第一次量測（`7ced8fe`）390 個、非預期存活 29，處置見上；`--verify-expected` 48 條全部相同（712 檔）；`run.sh` 全綠（254 ok、0 not ok，973 秒）。量測在 `8f2d21a` 上跑；之後的 commit 只改了註解與 docstring（剝掉 docstring 的 AST 比對相同）與 CHANGELOG。量測當天機器同時有其他工作，
  opsweep 與 mutation 的牆鐘時間不能與前幾輪直接比。CI 以推送後的 run 為準（run 編號與結果推送後記在 PR 說明）。
- **verify R38（4 lens + DA + Codex 跨模型 leg，`gpt-6-astra`／medium）— 4 HIGH、11 MEDIUM blocking、7 LOW，共 22 列（報告的 Aggregate 行寫成 12 MEDIUM，逐列表格是 #5–#15 十一條——那一行是我寫錯的，發文時沒對表）；六條 leg 全部判 FAIL。**
  中心發現：網只對作者點名過的輸入有鑑別力，而且量它的平台不是 CI 的平台。strict 產生語料的判定完全由「是不是群組」決定——群組規則擋下
  所有非群組形式、群組形式又豁免 fd 規則，所以 fd 流向規則在 `--strict` 下從來不是決定判定的那一條（R37 條目的「關掉 fd 複製偵測 → 7 檔繞過」
  已就地更正）；本輪每一個新繞過與新誤擋都落在語料沒有的維度上。CI 在 c53ac22 上是紅的：一張 fixture 的外流依賴 `/bin/sh` 是 bash，
  ubuntu 上是 dash。R39 的修正全部 TDD（fixture 或反向探針先在修法前看過紅；新 mutation 靶逐條實跑確認被殺）：
  - **CI（R38 第 1 列）**：named-fd fixture 改用 `bash -c`。以 `/bin/dash` 充當 `sh` 跑一次 fixture 神諭，重現 CI 的 `一致 595、不一致 27`，
    而且在 dash 替換下只有這一張翻成不一致（另有 4 張宣告 `shell: sh` 的 fixture，神諭本來就只用 bash 跑、不比對它們）。
  - **群組規則：空白碼行（第 2 列）**：群組外的**每一個**實體行都做字面比對，不只程式碼非空白的行——`${PR_TITLE}`、`\e\c\h\o …`、
    `$'\x65cho' …`、`${X:-eval} $'…'` 整行挖空後詞元檢查與字面檢查都看不到，bash 照樣執行。純註解行照常放行（註解被截掉、不是挖空）。
    8 張 bypass＋1 張 good。
  - **神諭（第 3、6、7 列）**：(a) 已觀察到外流而分類失敗 ⇒ 判繞過（前一版判「量不到」、不改 rc，Codex 的多行群組輸入讓 lint 與神諭
    同時 rc=0）；多行群組的差分先把範圍往上擴到語法完整。(b) 外流行是 xtrace 的輸出（神諭把 PS4 設成自己的標記）⇒ 繞過，不歸任何類別。
    (c) S-2 要求**機制**成立：每一段補 `2>&1`（`|` → `|&`）後外流消失，或外流行全是 bash 自己的錯誤訊息、左邊包成群組就消失；
    `>/dev/fd/2 2>&1 |` 這類 fd 規則該擋的外流不再被收進 S-2。(d) 已知類別的**原因檢查**：刪掉與外流無關的行之後 `--strict` 仍擋
    （DA 的 `set -Eeuo` 反例）。`oracle_selfcheck.py` 從 2 項擴成 8 項（假 lint 讓神諭走到歸類分支）；新增的六項在 R38 的神諭上都是 rc=0。
  - **`_Sh`（第 4、8、11 列）**：前綴詞的選項（`command -p`、`builtin --`、`eval --`、`time -p`，`command -v` 只描述不執行）；非字面命令名
    的參數像 `set` 選項時 fail-closed（`-x`、`-o xtrace`、`pipefail`；`"$TAR" -xzf` 照常放行）；`$"…"` 當雙引號；pipefail 改成**範圍模型**——
    子殼層、管線的每一段、命令替換、背景執行各開一層，設定只作用在同一範圍或更內層、之後的管線（`( set +o pipefail )`、先關再開不再誤擋；
    `set -o pipefail &` 不再當成開了）。第 4 列那一族在預設模式是 R37 的回歸（380e4a4 擋、c53ac22 放行），現在回到擋。
  - **fd 與 env（第 5、9、20 列）**：群組豁免只給寫到自己 fd 1／2 的目標（數字 fd 複製、`/dev/stdout|stderr`、`/dev/fd/1|2`、
    `/proc/self/fd/1|2`）；`/proc/$$/…`、`/proc/$PPID/…`、`/dev/tty` 不豁免。含 `..` 又經過 /dev、/proc 的目標 fail-closed。`PYTHON*` 的值是
    runner 運算式（env 三層），或 run 裡設成非字面值 ⇒ RULE（過濾器 `python3` 啟動時就讀它，`PYTHONWARNINGS` 的不合法值原樣印到管線右端的
    stderr，協調者實跑）。**Linux 預測**：`/proc/$$`、`exec >/proc/$$`、`..` 三張在本機（沒有 /proc）列為已知誤擋
    （`KNOWN_DISAGREE_WITHOUT_PROC`），在 CI（Linux）上必須判一致——以推送後的 CI run 為準（run 編號與結果推送後記在 PR 說明）。
  - **誤擋（第 10、11 列）**：放寬四類——群組內未加引號的 `${{ … }}`（遮罩後計數；R32 HIGH-1 修過的那一類重新出現）、尾巴後的 `;`、
    `set -E`／`-o errtrace`、`set` 前綴行尾的 `;`。揭露五類（`restrict-r39-*` ＋ KNOWN_DISAGREE）：群組內定義函式、巢狀群組
    （`>> "$GITHUB_ENV"`）、兩個群組、群組前的 `cd`／`export`、命令替換裡不在命令起點的 `case` 普通參數。regression lens 的 61 個安全寫法：
    一致 51、不一致 8、不可比 2，不一致的 8 條都屬已揭露類別。群組規則的完整代價（七類）寫進 lint 的註解。
  - **run 裡的 PR 可控運算式（第 14 列）**：靠管線過濾的 step，run 裡直接寫 `${{ github.event.* }}`／`${{ github.head_ref }}` ⇒ RULE
    （兩種模式；runner 在 bash 之前代換，可以收掉引號與群組）。產生語料 d 組的 `gen-d-yaml-ghexpr-plain` 因此從放行變成擋（真的注入形狀）。
  - **網（第 12、13 列）**：`shellgen.py --strict` 從六個維度擴成九個（群組外的行 × 位置、群組內容、群組尾巴），54 → 85 檔；用 c53ac22
    的 lint 跑這三個新維度，神諭抓出 12 條繞過或 STRICT_MISS、4 條誤擋、1 條 pipefail 不可比（R39 verify 第 14 列更正：原寫 11／5／1，實跑 12／4／1，總數 17 相符），全部是 R38 找到的缺陷。形狀普查加 R39-1..3。
    `EXPECTED_SURVIVE` 47 → 46 是三個變動的淨值：`_scalar` 的 `strip→id` 用一張 EXPECT-MSG fixture 殺掉（移出）；`<module>` 的 `cs = c.strip()` 因那段程式碼搬進新函式 `_logical_lines()`、id 改名後被 opsweep 證明可殺（移出）；pipefail 範圍模型新增的 `new_scope` `±1→±2` 列為等價（加入）；logic lens 對 8 條「無解」存活者找到的 6 個殺法
    做成 fixture（其中 4 張是保守 RULE、列 KNOWN_DISAGREE）。
  - **其他**：TAP 守衛在上一步被跳過時不跑（第 16 列，R38 那次 CI run 裡實際印了不實的 `::error::`）；run.sh 補 `oracle_selfcheck.py` 與產生語料
    神諭（第 18 列）；lint 註解更正「R36 要求每一段」（實際只要求緊鄰 neutralise 的那一段）與「群組未收尾什麼都不會印」（bash 會印語法診斷）；
    已知不涵蓋第二組加第 4 條「過濾器的身分」（lint 檢查接線，不驗證 `neutralise.py` 的內容，第 21 列）；神諭盲區補平台、固定 marker、stub、
    `$?`；README／`test_validate.py` 檔頭的語料與 `EXPECTED_SURVIVE` 數字。
  - **量測工具（使用者要求：一輪 6 小時、每改一版就等半天）**：`mutation_check.py` 加 `--jobs N`——每個 worker 一份 repo 副本（不含
    `.git`，與 `git archive` 的量測副本同條件），在副本裡以 `--only i --worker` 跑單一個靶，本樹不被改寫；加 `--only`（索引子集）。
    等價性：13 個靶（五個守備單位都有）串行與 `--jobs 4` 逐靶結果相同，33.0 分 → 8.4 分。加**結果快取** `mutation-cache.json`：key 是
    「突變後被改寫檔的正規化內容（Python 剝掉註解與 docstring 的 AST）＋ 守備單位讀得到的輸入檔 ＋ python／bash／PyYAML 版本」，key 相同
    就沿用、摘要分開印「沿用」與「重跑」；`validate`／`neutralise` 兩組的輸入是整個 repo（它們讀的範圍逐一列舉必然漏）。判斷「有沒有改變」
    的是雜湊、不是人對「是不是大改版」的判斷；發版前的量測用 `--no-cache`。四條新測試（註解不換 key、輸入檔換 key、命中不跑／`--no-cache`
    重跑、`--no-cache` 跑子集不丟別的靶的紀錄且清掉過期 key），測試 144 → 148 條（歷史數字；帶指令的現況宣稱只留在最新一段，R40 起是 152）。`opsweep.py` 的 10% 上限改用全集分母（前一版除以 `--since` 的區域：R39 的區域只有 368 個）。
  - **mutation 子集抓到的一條**：類別閘門「KNOWN-CLASS 過期」方向的靶在 R39 之後失去網——原本殺它的 must-fail 探針
    `g-diff-syntax-break`，在「分類失敗改判繞過」之後光憑繞過就以宣告的理由失敗。補 `known-r39-mustfail-class-stale-only`（唯一的
    失敗理由就是過期），`FIXTURE_MUSTFAIL_TOTAL` 7 → 8。
  - **mutation 全輪抓到的一條**（`bf961d1`，唯一的非預期存活者）：續行判定的 bash 那一支（行尾 `|` 後面帶註解）。我原本想把它列成
    等價（上一行以 `|` 懸空時 stdout 只流進管線，換不換都一樣），實際試了兩個反例都不變色——原因是中性命令 `! ! :` 接在 `|` 後面
    本身就是語法錯誤，R39 的差分往上擴到最短的完整範圍，剛好補回續行判定該給的範圍。但擴範圍是逐段貪婪、每段都要求**整份腳本**
    語法完整：同一個 run 區塊有**兩條**註解續行的管線時就量不到。補 `known-r39-g-two-continued-pipelines`（修法前後分別判 G 與 rc=1），
    G 7 → 8。**量測工具的兩個缺陷**：`--only 389 --no-cache` 讓快取從 433 筆只剩 1 筆（`--no-cache` 不讀舊檔、存檔只寫這一輪）；
    舊 key 從不清，一輪後長到 868 筆——改成 `--no-cache` 只是不沿用、存檔只留所有靶的現行 key。摘要一律印「沿用 N 靶、重跑 M 靶」：
    `bf961d1` 那一輪沿用 0（lint、神諭、整個 repo 都變了），當時摘要不印 0，看不出來。快取 key 不計入 `CHANGELOG.md`（沒有任何
    驗證指令讀它；回填數字是每一輪的最後一步）。
  **我自己的錯**：R37 推送後沒等 CI 就開 verify；`( set +o pipefail )` 的誤擋是我在 R37 改 `_pipefail_holds` 時引入的；併入群組規則後沒重跑
  放行條件 6 的負對照；`unmeasured` 不計入失敗是我在 R35／R36 寫的、檔頭還寫成「fail-closed 的方向」。R39 起 verify 要等 CI 綠才開。
  **量測（本機 macOS，CI 以 Linux 為準）**：selftest（最終樹）259 正向／362 規則紅／145 解析紅／5 張訊息斷言；fixture 神諭 907 個 step：一致 640、不一致 49（全部已知；類別 G 8、S-2 3）、不可比 201、量不到 17；產生語料 709 個 step：一致 577、不一致 71（全部已知）、不可比 61、量不到 0（於 `bf961d1`；之後 lint 內嵌的 Python 沒動）；`oracle_selfcheck.py` 8 項 ✓；
  mutation 靶 435 個，全輪 （`c99e4c5` 的 `git archive` 副本，`--jobs 8`）殺 432／存活 0／預期存活 3／靶壞 0，牆鐘 60.6 分（每靶 8.4 s）；同一棵樹立刻重跑：435 靶全部沿用快取、16 秒；opsweep `--since c53ac22` （於 `bf961d1`）368 個突變體：殺 354（其中當掉 37）／存活 14（預期 12、非預期 2＝R37 留下的兩條無解）；`--verify-expected` 46 條全部相同（709 檔）；CI 以推送後的 run 為準（run 編號與結果推送後記在 PR 說明；R39 起 verify 等 CI 綠才開）。
- **verify R36（4 lens + DA + Codex 跨模型 leg，`gpt-6-astra`／medium）— 7 HIGH、13 MEDIUM blocking，另 LOW 5 條 in-scope、1 條交給 #58。**
  中心發現：R34 的判斷還成立，只是往上搬了一層。R35 讓 R34 點名的四個輸入各自讓網變色，四個 lens 與 Codex 卻在 R35 改過的述詞上又找到
  二十個以上作者沒點名的相鄰輸入，沒有一個讓 repo 內任何一張網變色，其中三個是 R35 引入的回歸。結構原因在神諭：判定「這個外流是不是已知類別」
  的分類層用的正規式幾乎就是 lint 規則的副本，所以正規式以外的 fd 轉向，lint 放行、神諭也收進已知 G——而神諭本身不在任何突變範圍裡。
  **R36 報告的勘誤**：第 16 列第三個例子 `"${MESSAGE:-it's fine}"` 我寫成「bash 把 `'` 當字面、lint 誤擋」並標「協調者核對」——bash 5.3 實測是
  語法錯誤（rc=2，「尋找符合的 ' 時遇到了未預期的檔案結束符」），lint 的 PARSE 是對的；那四個字是假的，我沒有跑 bash、照 Codex 的說法寫進去。
  R37 的修正分五個工作包平行做、合併時協調者又修了一批，全部 TDD（fixture 先在修法前的 lint 上看過紅）：
  - **神諭（第 1、2、8、18 列）**：已知類別改用**差分**判定——把接 neutralise 的邏輯行換成中性命令再跑一次，外流原封不動才算「另一條命令印的」（G）；
    S-2 改成「管線自己只從 stderr 外流，**而且 `--strict` 真的擋下這個 step**」（併入群組規則後查的是群組規則，見下）。兩個判準都不含 lint 規則的正規式副本。類別閘門雙向、
    條數釘死（`FIXTURE_CLASS_TOTALS`、`FIXTURE_MUSTFAIL_TOTAL`）；must-fail 探針量「只在神諭失敗時才走得到」的分支；YAML `env:` 三層帶進腳本；
    pipefail 的排除只在它是 step 唯一的 RULE 時成立。**神諭進入突變範圍**（放行條件第 7 條）：`mutation_check` 加 `oracle` 與 `oracle-inverted` 兩個守備單位，
    16 個神諭靶；條件 7 點名的正規式分支已不存在，對應閘門是差分 G 的 `if not contrib`。神諭工作包原本把三個靶列為「無網／預期存活」，
    其中耦合檢查一條的理由是「harness 的『未突變＝綠』前提與它結構上互斥」——不成立：寫成「期待失敗」的斷言（`test/oracle_selfcheck.py`）就滿足那個前提；
    三個都在副本上看過未突變綠、突變紅。
  - **`--strict` 與 fd 流向（第 3、4、8、9、12、13、22、25 列）**：R35 的六條正規式（R36 在其中五條找到相鄰輸入）整組刪掉，改讀 run 區塊的**結構**——修法包先做成逐條管線、每一段都要把 stderr
    併進管線（或整段包成 `{ …; } 2>&1 |`），這一條後來由 PR #61 的群組規則取代（見下）；pipefail 只認關鍵字 `bash` 或樣板自帶 `-o pipefail`，頂層的 `set ±o pipefail` 依序模擬；fd 流向按流向判
    （複製到 2 或另存的 fd、/dev 與 /proc 底下的目標、xtrace／verbose 的各種拼法、子 shell 的選項），並讀 workflow／job／step 三層的 `env:`；
    群組寫法 `{ …; } 2>&1 |` 不再誤擋；`_scalar` 的 `.strip()` 照 YAML 引號解碼後才判；根層級 flow 形式的 `defaults:` 看得到。
  - **雙引號詞法（第 6、7、16 列）**：雙引號裡的 `$(…)`／反引號是新的引號脈絡——同一行收得掉就整段不透明，收不掉就照 bash 當 code 掃、收尾時回到雙引號；
    `_cmdsub_end` 認得 case（主掃描器追蹤 case 的模式括號，表示不了的形狀 fail-closed）；雙引號裡的算術 `$((1 << 2))` 不是 heredoc。
  - **命令位置詞法（第 5(a)、14、15、17 列）**：`[[` 與算術命令 `((` 只在命令位置成立（`cmd_pos`），`((cmd) )` 的孤兒 `)` fail-closed；未收尾的構造
    （`$(`、反引號、`((`、`[[`、`$[`、裸 `(`）掃描結束時一律 fail-closed；分隔字詞配對 `${…}`／`$[…]`；`shopt -s extglob` 整段 fail-closed。
  - **解碼（第 5(b)(c)、10、11、20、21、24 列）**：`$'…'` 解出 NUL 或 ≥0x80 的值 fail-closed（`\x` 與八進位在 bash 裡產生的是原始位元組，不是 Unicode 碼位；`\u`／`\U` 其實產生 UTF-8，lint 一併 fail-closed 是保守的簡化）；
    `_param_end` 的兩個 `$[` 守衛還原（R35 當死碼刪掉，其實是 fail-closed 守衛）；`dedent_block` 算縮排時只認空白；`fold_block` 接行不再 `strip()`
    （R35 `EXPECTED_SURVIVE` 裡那條「依構造等價」的論證是假的，突變體才是對的）；殘留文字更正。
  **合併時協調者發現的缺陷**（每一條都有 fixture 先紅）：
  - `cmd_pos` 在各個 `continue` 分支沒維護（主引號、ANSI-C、`${…}`、跳脫字元）——`bypass-r37m-*-before-cond` 六張。
  - 反引號裡的 `#` 註解一律吃到行尾，`bt` 留在 True，d 包新增的區塊結尾檢查因此把合法的 bash 判 PARSE（產生語料 gen-c-backtick-* 八檔）。380e4a4 就有
    這個缺陷，當時被「step 沒有 neutralise 管線 → RULE」蓋住、判定碰巧正確。
  - **`PIPED_RE` 的右半邊不是 bash 的詞**：路徑部分 `\S*` 跨過命令分隔字元——`| python3 -mquopri;scripts/neutralise.py` 在 bash 是管線接到 quopri、
    再另跑一個命令，PR 文字幾乎原樣印出（實測 `::warning::MARK` 未經過濾），預設模式判「已過濾」（380e4a4 兩種模式都放行）；結尾只認空白，
    `neutralise.py;`、`&&`、`)`、反引號等緊接在後被誤擋（a 包報告交來）。兩端改用 bash 的 metacharacter 當詞界。
  - **E 類：在該段 `2>&1` 生效之前寫出的 stderr**——展開期錯誤（`${!PR_TITLE}`、`$(( PR_TITLE ))`）與寫在 `2>&1` 左邊的重導向本身出錯，
    **兩種模式都看不到**。所以 R35 在 #59 寫的「S-2 在 `--strict` 下已是規則」即使逐段規則修好，也只對命令執行時的 stderr 成立。當時沒有加規則
    （逐拼法列舉正是 R36 批評的形狀；完整解是只接受群組寫法），開 #60 追蹤——PR #61 就是那個完整解，本輪併入（見下），`--strict` 下這一類關掉了。
  - `test/corpus/foldcheck.py` 進 repo：e 包在 `opsweep.py` 寫的「窮舉 5,838 組、0 組不符」引用了一支沒進 repo、合併時已找不到的指令碼。新工具窮舉
    22 種行形（含 tab 前導、行尾空白、真正的空行）的所有組合：現行 lint 4 行 `run: |`／`run: >` 各 136,660 組整字串全部相等；負對照 380e4a4 在 3 行
    的 6,518 組裡就有 literal 462 組、folded 588 組內容承載行不符。e 包寫的「空白行另有一個既有的簡化」在這個構造下重現不出來、指向的說明也不存在，刪掉。
  **量測時發現的三個 `opsweep.py` 缺陷，R28 這支工具進 repo 起就在**（三個都先寫了測試，是 repo 外的一次性腳本）：
  - **欄位是 UTF-8 位元組、不是字元**：ast 的 `col_offset` 是位元組位置，`_span` 當字元位置用，同一行節點前面有中文就切錯。
    查過的四個版本（d278e99、d8340a6、6cf6864、380e4a4）各有 3 個這樣的突變體（`縮排含 tab` 那行的 `i += 1`、`cur["name"]` 那行的 `or`、`而不解析就不放行` 那行的
    `.strip()`）；`i += 1` 那個實際換掉的是前一行 `if seq_at[i]:` 的冒號（在 d278e99 與 380e4a4 上重算），R29 的兩份掃描記錄與
    R30 DA 的全段掃描都把它記成 KILLED。R37 的 lint 多了 3 個，其中兩個是 `==`，`==↔!=` 找不到 `==` 當掉才被看到。
    修法：換算成字元位置，並在產生每個突變體時驗「切到的文字就是這個運算子的原文」，位置算錯當場失敗。
  - **語法壞掉的突變體一律記成 KILLED**：`drop-operand` 直接刪文字，運算元外面的括號不在 AST 節點範圍裡，`(a or (b and c))`
    拿掉 a 會刪到 `a or (`——括號不平衡；而 BROKEN 的判準是「selftest 輸出裡有 `SyntaxError`」，selftest 每張 fixture 只印
    stderr 前兩行，`SyntaxError:` 那一行被截掉，所以永遠量不到。R35 最終掃描（`--since 6cf6864`）報的 249 殺裡有 11 個是語法
    壞掉的——那 11 個位置等於沒量（存活數不受影響）；R37 的 lint 全段 1044 個突變體裡有 46 個這樣。修法：`drop-operand` 改成把
    整個運算式換成其餘運算元各自加括號接回去（語意就是拿掉那一個；突變體 id 不變，三個 lint 版本 1624 個 id 逐一相同），
    BROKEN 改成跑 selftest 之前直接 `compile()`。另加 `--jobs N`（區域 868 個突變體循序估計要 8 小時）。
  - **沒有逾時**：突變體可能讓 lint 進無窮迴圈——補跑時有一個一邊迴圈一邊配置記憶體，38 分鐘吃到約 22 GB；`--jobs`
    照順序輸出，一個卡住就整批不動。修法：每個突變體逾時（未突變 selftest 實測耗時 × 10，下限 600 秒），逾時殺整個行程群組
    （lint 是 bash 包 python，只殺 bash 會留下 python 孫行程）、stdin 接 /dev/null，逾時單獨報 TIMEOUT。
  **完整性審查**（四個工作包驗殺各修法包建議的突變靶之後，再派一位逐 hunk 走 380e4a4..e50c303 的 lint diff）：列出 14 處沒有網、或只有一部分有網的
  hunk（其中 1 處是 selftest 門檻）、為存活的突變寫了 50 張提案 fixture（逐對驗過未突變＝EXPECT、突變後≠EXPECT），另找到 e50c303 本身的五個缺陷——
  (a) 反引號開啟時設的 `cmd_pos` 沒有 `continue`、在迴圈底部被覆寫；(b) `if [[ … ]] then`（不寫分號）bash 接受、lint 不認 `then`——bash 接不接受取決於
  外層的 if／while，lint 不追蹤複合命令的巢狀，改成 fail-closed（野外 1538 檔的真實 bash 裡 0 檔這樣寫）；(c) 規則層把 `((…))`／`[[…]]`／`$((…))`
  當成沒有命令替換的不透明詞，裡面的 `>&2` 逃過 fd 流向規則，**兩種模式都放行**（協調者另補同一族的 `$[…]`）；(e) 規則層一看到 `[[` 開頭就當不透明詞，
  引數位置的 `set -o pipefail [[ -n x ]]` 被誤擋——改成與掃描器同一個判準（內部被挖空才是）；(d) 頂層 `case` 模式的 `|` 在預設模式被讀成管線——
  **刻意保留**（已知不涵蓋第三組第 5 條、神諭 `KNOWN_DISAGREE`）：`--strict` 當時由「看得到管線、規則層剖析不出它」那條擋下（併入群組規則後
  那條拿掉、改由群組規則擋），而把 case 追蹤延伸到頂層的誤擋代價沒量過。另外，負責合併程式碼的那個工作包把兩個存活靶論證成「等價突變」，完整性審查寫的 fixture 就殺得掉它們——論證是錯的。
  **網**：`shellgen.py --strict` 組 54 檔（shell 值、env 鍵、fd 轉向拼法、xtrace 拼法、多段管線、子殼層包管線；預設組 624 檔的內容行相對 380e4a4 不變，只有 61 檔多了一行 `# KNOWN-CLASS:` 檔頭（S-2 60、G 1；已知類別由構造決定）），神諭 rc=0；
  負對照：現行 lint 關掉 fd 複製偵測 → 7 檔繞過、rc=1（整份換成舊 lint 的負對照會先撞到神諭的耦合檢查、量不到維度）**〔R38 第 12 列更正：這是併入群組規則**之前**量的。併入之後 strict 組的非群組形式全部先被群組規則擋下，同一個突變在 c53ac22 上神諭結果逐字不變、rc=0——這句負對照在出貨的樹上不成立，放行條件 6 因此判未達。R39 加了維度 7–9，見 R39 條目〕**；`shapes.py` R37-1…10；
  CI 的產生語料 step 一併產生並對帳 strict 組、另跑 `oracle_selfcheck.py`。mutation 靶 193 → 390（併入群組規則後 393、R37 訊息回歸靶後 394，見下）：14 個漂移靶沿用原名重新對位（13 個是修法包改寫了規則，1 個是協調者在
  條件式分支與引號分支之間插入缺陷 b 的檢查），新增 197 個（lint 181、神諭 16）；不登記 19 個——等價 8、死碼或走不到 3、
  被另一個重寫過的靶取代 2、找不到會翻色的輸入 4（其中一條也沒證明等價）、兩處要同時改而靶格式表達不了 1、量的是 selftest 門檻本身 1——
  逐條理由寫在 `mutation_check.py` 那個區塊的開頭。
  **併入 PR #61 的 `--strict` 群組規則（#59／#60；使用者定的整合順序：B）**：靠管線過濾的 step，整個 run 區塊必須是
  `[set -e／-u／-o pipefail 前綴]` ＋ 一個 `{ …; } 2>&1 | python3 <路徑>/neutralise.py`（或 `} |& python3 …`）。它同時關掉 #59（同區塊另一條命令，
  已知類別 G）與 #60 第 2 類（那一段 `2>&1` 生效前的展開期／重導向錯誤）——群組的重導向在群組內任何展開之前生效。規則本體（恰好一對獨立詞大括號、
  `}` 在最後一個邏輯行的命令位置、尾巴逐字比對、群組外三段必須是字面、斷詞只認 ASCII 空白）照 #61 搬過來；R37 版本的差異：
  - 字面檢查改用 `_aligned_sources` 的對齊原文（R37 的 `scan_in` 有折疊佔位、`<<` 分隔字被讀掉，#61 直接切原文的做法不成立）；對不齊 ⇒ 拒絕。
  - 取代的是 R37 的逐段 `2>&1` 規則與「剖析不出接 neutralise 的管線」規則；只為它們存在的 `_fd2_to_pipe`／`_touches_fd2` 刪掉。
  - **pipefail 沿用 R37 的模擬**（#61 是「群組形式時 pipefail 要在前綴裡」的視窗規則）：群組規則通過時頂層只剩 `set` 前綴，兩者等價；而 pipefail 規則也管
    宣告 `# LOG-FILTER:` 的 step（它們不受群組規則約束、結構任意），模擬在那裡仍然是活的。
  - **移植時查到的 R37 缺陷**：模擬把管線段裡（子殼層）的 pf 事件整個忽略，於是 `shell: bash` 下 `{ set +o pipefail; false | true; } 2>&1 | python3 …`
    放行——群組內關掉 pipefail 會吞掉群組內之後的失敗（bash 5.3 實測外層 rc=0，不關的對照組 rc=1）。群組形式把一切都放進子殼層，這個洞變成主路徑。
    改成子殼層裡的「關」也算數（fail-closed：`( set +o pipefail ); a | b` 因此誤擋）；`bypass-strict-group-pipefail-off-inside`、`…-shopt-pipefail-off-inside`。
  - **fixture**：#61 的 22 張＋它改寫的 7 張；R37 自己的 `--strict` fixture 逐張看它觸發哪些規則——群組規則會把本來守 pipefail 的 14 張「順便」染紅
    （拿掉 pipefail 規則照樣紅，網失去鑑別力），改成群組形式（樣板類 6 張）或宣告 `# LOG-FILTER:`（模擬類 8 張：函式、子殼層、同行後 set 等寫不成群組）；
    守逐段 `2>&1` 的 8 張是真的外流形狀，保留、改由群組規則擋，檔頭註明；R36 的負對照「逐段 `2>&1` 形式都放行」只留大括號群組，子殼層群組
    `( … ) 2>&1 |` 安全但被擋，另立 `restrict-r37-strict-subshell-group`（`KNOWN_DISAGREE`）。改完每張只觸發它點名的規則，唯一例外是刻意雙紅的 must-fail 探針。
  - **神諭**：已知類別 G 也要 `--strict` 真的擋下這個 step（非 pipefail 的 RULE 或 PARSE），否則判「形狀像已知類別 G，但 `--strict` 也放行」的繞過（#61 的
    `STRICT_MISS`）；S-2 的查核改認群組規則的訊息（原本認的 `2>&1` 規則訊息已不存在——耦合檢查會具名失敗，不會安靜錯）。新 must-fail 探針
    `known-r37-mustfail-g-strict-not-blocking`（殺「G 查核恆真」）。#61 的 `known-expansion-error-before-2to1` 被 R37 的差分歸成 S-2（換掉那一行外流就消失——
    是那一段自己印的），不是 #61 按症狀歸的 G，檔頭照改。
  - **突變靶**：刪 4 個指向已刪程式碼的靶，加群組規則 5 個、pipefail 子殼層 1 個、神諭 G 查核 2 個；新增與改指向的 15 個逐一在「未突變基線綠」的複本上實跑、全殺。
    `set` 前綴不收 `-v`／`-x` 那個靶放寬後觀察不到——頂層的 `set -v`／`-x` 先被 fd 流向規則擋下，對判定是等價的（縱深防禦），改設「裸 `set` 不是前綴」。
    我第一次跑這批靶時沒改 selftest 門檻，基線本身是紅的、每個突變體都「殺掉」——補上基線檢查重跑才作數。
  - **test.yml**：oracle 與產生語料兩個 step 改群組形式（保留 R37 多的 `oracle_selfcheck.py`、`shellgen.py --strict`）；#61 已拆出的兩個 `::error::` step 照收。
  **最終 lint 上的 opsweep 與存活者處置**：併入群組規則之後對最終 lint 重跑 `opsweep.py --since 380e4a4`（`d1014e6` 上 866 個突變體：殺掉 815——其中當掉 79、逾時 3、只被產生語料抓到 0——存活 51＝預期 43＋非預期 8，語法壞掉 0；`--jobs 8`、醒著的耗時 122.8 分鐘，牆鐘另含約 4 小時 40 分的系統休眠）。
  兩波存活者分群交給分析者（每群一位，寫 fixture 或給構造論證），再由一位反駁者逐條試著推翻「等價」主張；每張 fixture 都用
  mutcheck 逐一重驗「原版＝EXPECT、宣稱的突變體全部 KILL」，最後用 opsweep 自己的判定對存活 id 重跑一次確認。
  第一波（併入前）87 張、第二波（最終 lint）72 張補件（71 張出自分析者、1 張由協調者補）；第二波 155 個存活者：殺掉 105 個、42 條等價列入 `EXPECTED_SURVIVE`
  （52 條主張裡反駁者推翻 6 條，已補 fixture；另 4 條理由是「純訊息文字」：其中 `set_cmd` 那條被 `--verify-expected` 推翻，同理由的另 3 條一併撤掉，見下；`_rule_lines` 的第 2 個 drop-operand 由協調者補的 fixture 殺掉）、8 條殺不掉也證明不了等價
  （照實揭露：`_cmdsub_end_case` 的 drop-operand（`elif cases and cases[-1][0] == depth and (cases[-1][1] == "pat" or a…`，第 5 個）；`_cmdsub_end_case` 的 drop-operand（`if (c == "#" and at_word) or line.startswith("$'", k) or line.starts…`，第 3 個）；`_cmdsub_end_case` 的 drop-operand（`if cases and cases[-1][0] == depth:`，第 2 個）；`_rule_lines` 的 drop-operand（`rl_src[-1] = None if rl_src[-1] is None or a is None else rl_src[-1]…`，第 1 個）；`_word` 的 drop-operand（`if c == '"' and C[p + 1:e].strip():`，第 1 個）；`_word` 的 drop-operand（`return {"k": "W", "code": C[st:p], "lit": "".join(lit) if literal an…`，第 2 個）；`_cmdsub_end_case` 的 startswith→F（`if line.startswith("<<<", k):`，第 1 個）；`_word` 的 ±1→±2（`p += 1`，第 1 個））。
  **「純訊息文字」這類等價理由整個撤掉**：`--verify-expected` 比對整段 stderr，`set_cmd` 那條（`set -x` 印成「開了 verbose」仍照樣
  rule-red）在 3 個 `--strict` 語料檔上被推翻；同理由的另 3 條只是語料沒碰到。selftest 因此多一種斷言 `# EXPECT-MSG:`（可多行，
  每行必須以子字串出現在輸出裡；帶它的 fixture 張數寫死），在 4 張既有 fixture 上加斷言殺掉這 4 個突變體——順帶抓到一個真缺陷：
  子 shell `bash -o xtrace` 的訊息一直印成 `-oo xtrace`（格式字串 `` `%so %s` `` 而 `a` 已經是 `-o`），就是因為沒有任何 fixture 看訊息。
  `--verify-expected` 另一個範圍缺口一併修：它拿 `--since` 的區域清單去查條目，區域外的 4 條舊條目在帶 `--since` 呼叫時只得到
  「不在本次掃描範圍內」、沒被驗到（不帶 `--since` 時會驗——9/25 在 624 檔上驗過，但那是移植前的 lint）；現在一律對全集驗（陳舊性檢查本來就對全集做）。
  11 張補件是「保守拒絕」的形狀——輸入實際不外流、突變體把拒絕放寬——改名 `restrict-r37p-*`、神諭記 `KNOWN_DISAGREE`；
  14 張 bypass 補件原本印常數或那一支不執行，改成真的印 PR 文字，讓神諭判「一致」而不是「誤擋」。
  **`--verify-expected` 本身的盲點**（量測時發現）：它只產生預設組語料、跑 lint 也不帶 `--strict`，所以只在 `--strict` 下
  才有差別的突變體在這裡永遠「全部相同」——把 `elif STRICT and not declared and group_why:` 拿掉 `group_why`（明顯不等價）
  冒充成預期存活，前一版回報「624 檔全部相同」、rc=0。現在加入 `--strict` 組並照 `# LINT-ARGS:` 帶旗標（同一個探針在
  gen-strict 的 3 檔上抓到差異、rc=1），原碼結果只算一次、依 `--jobs` 平行。
  **產生語料神諭在群組規則下的 8 條保守誤擋**：`shellgen.py --strict` 是移植前按逐段 `2>&1` 設計的，它的「該放行」基準
  （`shell value bash`／`-dq`／`-sq`、`pipeline of 2／3 segments, gap=0`，以及三個 `( … )` 子殼層包裹）在群組規則下被擋，神諭判誤擋、rc=1。
  lint 行為是設計（逐段形式擋的是 #60 第 2 類；子殼層同 `restrict-r37-strict-subshell-group`），逐檔記進 `KNOWN_DISAGREE` 並寫理由；
  shellgen 只改說明，產生的 678 檔前後逐位元組相同。
  **我在這一輪自己的錯**：移植群組規則後只重跑了 fixture 神諭，沒重跑產生語料神諭——CI 的那個 step 兩組都跑，推上去會紅；加 `shellgen.py --strict` 組時只改了 CI，`run.sh` 的形狀普查仍只產生預設組，R37 的 10 列裡有 7 列（R37-1、2、4–8）恆為 0、本機必紅（最終量測跑 `run.sh` 時才抓到，已改成兩組都產生）；R36 報告第 16 列的「協調者核對」（見上面的勘誤）；`bypass-r37m-backtick-comment-hides-rest` 的檔頭我第一版寫「380e4a4 放行」，實測 380e4a4 判 RULE（commit 前量到、已改）；一次 grep 把常數名拼錯（`FIXTURE_MUST_FAIL_TOTAL`，實際沒有中間那個底線），`&&` 讓後面寫 fixture 的指令沒執行，我對著一張不存在的檔讀了一輪神諭結果才發現；缺陷 c 的第一版把「找不到收尾」改成 fail-closed，誤擋了 `good-cond-like-command-word`（`[[x` 是命令名）——selftest 抓到，才改成與掃描器同一個判準。
  數字（`d1014e6`（推上 `r37-fix` 分支備份；最終 commit 與它只差註解、docstring、mutation 靶名稱、`run.sh` 的語料產生與文件（CHANGELOG、`test_validate.py` 檔頭）——lint 嵌入的 Python 剝掉 docstring 後 AST 相同；`run.sh` 在 `d1d2637` 上跑，最終 commit 只再改了它的註解） 上實跑，負載 開跑時一分鐘平均 11.9–12.5；量測期間一分鐘平均一度超過 100（兩項量測同時在跑，同機另有其他 session 的編譯），`run.sh` 時約 31）：selftest 233 正向／310 rule-red／143 parse-red（686 張 fixture），另有 4 張訊息斷言；`--strict` 對本 repo 的 workflow rc=0。`mutation_check.py --check-targets` 394 靶；全輪（`git archive` 副本）391 殺／0 存活／3 預期存活／0 靶壞，327.7 分鐘（每靶 49.9 s，醒著的時間）。opsweep 見上。`--verify-expected`（突變體全集、678 檔產生語料，其中 `--strict` 組 54 檔）47／47 條成立。神諭：fixture 829 個 step——一致 596、不一致 26（全為已知）、不可比 190、量不到 17；產生語料 678 個 step——一致 547、不一致 70（全為已知）、不可比 61、量不到 0；`oracle_selfcheck.py` rc=0。`run.sh` rc=0（15.7 分鐘；TAP `ok` 254 行、`not ok` 0 行；形狀普查 R3* 每列 > 0）。
- **verify R34（4 lens + DA 前半；Codex 因 OpenAI 429 缺席、使用者決定不等）— 7 HIGH（其中 3 條 R33 回歸）、7 MEDIUM blocking。**（R34 發文時寫成 8 MEDIUM，但它自己的表只有 #8–#14 七條——
  協調者合併時算錯；這裡原本照抄了那個數，R35 發 commit 前的宣稱查核抓到。）
  R33 換的證據標準確認是真的：點名的 7 個機制還原後 selftest 全部轉紅，R33 的每個數字逐條重跑吻合。**缺的是另一半**：
  regression 與 DA 各自把缺陷修掉、看既有的網——四個語意不同的最小修法（括號斷詞、`_next_phys` 步長、刪掉 `${…}` 雙引號內
  逃脫的分支、S-2 改按機制分類）在**量過的每一張網上都得到同一組數字**（前兩條四軸全量；後兩條只量了 selftest 與／或 642 檔語料，神諭與三軸那幾格
  是「—」、沒有量——這裡原本寫成「在四軸上全部」，寫過頭了）。網只對作者點名的輸入有鑑別力。三條 R33 回歸都住在那個盲區：CI 的形狀普查 step 缺 pipefail（CI 上結構上紅不了）；`DELIM_WORD_BREAK` 把 `(` `)`
  一起拿掉（繞過＋誤擋）；`_next_phys` 跳過佔位但 `spans` 只加 1（被接上的行重掃）。另四條既有 HIGH：`${…}` 消費器 5 個繞過、
  「分隔字比 bash 長只會誤擋」的方向論證不成立、`dedent_block` 把 tab 當縮排、S-2 按症狀歸類（把帶了 `2>&1` 的繞過也算已知）。
  R35 的修正——**每一條都在 `test/` 複本上單獨還原、看過它讓指定的 fixture 翻色**，並登記成 `mutation_check.py` 的具名靶：
  - **三條回歸**：`DELIM_WORD_BREAK` 補回 `(` `)`（靶拆成反引號、括號兩個，不再是複合突變）；`_next_phys` 回傳吃掉的格數；
    普查 step 補 `shell: bash`，並由新的 `--strict` 規則機械檢查（有管線的 step 必須在 pipefail 之下）。**在 CI 上看過它紅**：
    GitHub 探針 run 35869946905，同一個 step 本體餵空清單，`shell: bash` 的 job 紅、R33 寫法的 job 綠（log：`bash -e {0}`）。
  - **`${…}` 改成配對剖析**（`_param_end`）：引號、`$'…'`、巢狀 `${`、`$(…)` 與反引號照 bash 配對；雙引號裡的 `${` 也走它；
    同一行沒收尾 ⇒ fail-closed。**分隔字的 `$'…'` 解 ANSI-C 逃脫、`$"…"` 照雙引號**（`\c` 與解出 `\x01`／`\x7f` 的 fail-closed——
    bash 5.3 讀 EOF 警告實測 `E\cAF` 得到 `E\x01\x01F`）。**算術**：深度跨行保留、`$[…]`、`((…))`／`[[…]]` 裡的內容不是 code
    （DA n5、n5b：位元 OR 與正規式的 `|` 不是管線）。**命令替換裡的 heredoc**：bash 5.3 以「以終止字開頭」的行收尾（`EOF)`、
    `EOFx)`；一般 subshell 不算），版本相依 ⇒ 遇到就 fail-closed；雙引號裡的命令替換開 heredoc 改成照 bash 解析。
    **`dedent_block` 只剝空白**：含 tab 的 fold 窮舉（PyYAML 接受的 175,982 組）不符 7,310 → 2,429，剩下的**全部**是
    「首行比後面的 `#` 行深」——YAML 讀成區塊外的註解、lint 讀成區塊內的 shell 註解，兩邊都不執行；含 tab 的不符 0 組。
  - **stderr 與 shell**：fd 流向規則（`>&2`、`1>&2`、`>/dev/stderr`、`set -x`／`set -o xtrace` 在靠管線過濾的 step 一律 RULE，
    兩種模式都適用——**R33 在 `known-stderr-leak-piped-stdout` 記錄在案的那個已知繞過（`echo "$PR_TITLE" >&2 | python3 …neutralise.py`）
    因此被關掉**：那張 `EXPECT: pass` 的記錄型 fixture 換成 `bypass-stderr-redirect-piped-stdout` 等四張 `rule-red`，
    是「已知繞過」轉成「規則＋網」，不是刪掉一張網）；`--strict` 另要求接 neutralise 的管線帶 `2>&1`／`|&`、shell 是 bash（可帶選項、不得開 xtrace）、container 或
    Windows／運算式 runs-on 的 job 明寫 bash。**shell 規則本來在預設模式，三軸量到合成 A 語料 959 個 base-綠檔 290 個翻紅**
    （`shell: bash -euo pipefail {0}`、`runs-on: ${{ matrix.os }}`、container job）——移進 `--strict` 後 290 → 10，剩下的 9 個
    `bash -n` 自己也報語法錯誤（8 個是 PowerShell 腳本）、1 個是跨行 `${…}`（第三組已知限制）。`--strict` 第一次跑就抓到 test.yml
    pack anchor 那一步 `… | tee | python3 …` 的最後一段沒帶 `2>&1`——R33 寫的「17 條管線全部已帶」是假的（`tee` 沒有 PR 文字，補上）。
  - **神諭**：S-2 按**機制**三分（管線缺 `2>&1` ⇒ S-2；fd 轉向／xtrace ⇒ 非已知繞過；其餘 stderr 外流 ⇒ G 的 stderr 版本）；
    step key 含行號（DA n1：同名 step 共用 key，一個已知 S-2 遮住同名的真繞過）；`sleep` 是空操作（DA n6：`sleep 6` 讓繞過落進
    「量不到」）；非 bash 的 shell 判不可比；讀 fixture 的 `# LINT-ARGS:`；`RULE ∧ piped ∧ leaked` 判一致（前一版一律誤擋）；
    只因 `--strict` pipefail 而紅的 step 判不可比（它量的是退出碼遮蔽）。**已知類別本身是閘門**：fixture 可用 `# KNOWN-CLASS:`
    宣告，沒被歸進那一類 ⇒ rc=1；fixture 集上 G 或 S-2 任一類 0 條 ⇒ rc=1——兩者都在複本上翻紅過。
    神諭的判定表有 5 種（`python3 -c "import ast,pathlib;t=ast.parse(pathlib.Path('test/oracle.py').read_text());print(next(len(ast.literal_eval(n.value)) for n in t.body if isinstance(n,ast.Assign) and getattr(n.targets[0],'id','')=='VERDICT_KINDS'))"`）。
  - **R35 自己的量測抓到、6cf6864 就有的兩個繞過**：雙引號 YAML 純量的 `\n` 解碼後沒有切行（`run: "echo x\n#| python3 …"`，
    換行後的 `#` 不起註解）——改按換行切、切出來的行不 dedent；引號開到 run 區塊結尾（那一行 bash 語法錯誤、不執行，前面的行
    照樣先外流）——fail-closed。第二個是 E 組語料的產生器抄錯一個引號時撞出來的。
  - **網的鑑別力**：shellgen B 組重做（logic F6：前一版 60 檔的 `#` 維度 0 檔有鑑別力、G 類 41 條裡 40 條是它構造出來的；
    現在 PR 文字在管線那一條邏輯行上，12 檔）、新增 E 組 30 檔（R34 的探針形狀做成構造維度）⇒ 642 → 624 檔；`shapes.py` 補
    R35-1…13 十三列，`--require-nonzero R3` 守；R32-6 限定 `run:`（regression M-1：舊述詞在野外 base-綠分母命中 13 檔，**key 並不清一色**——重跑舊述詞實測最多的是 `if:`（6 檔），
    `stale-issue-message:` 只有 2 檔；R34 報告寫「全部是 `stale-issue-message: >` 之類」，這裡原本抄成「全是」。修後 0 檔——**野外 0/0 對本輪任何一個機制都不是證據**，R35 十三列在野外 base-綠分母全部 0 檔）。兩條 EXPECTED_SURVIVE 原本
    0 檔走得到突變點（requirements F6），E 組補了前導空行與行尾空白兩個維度。`fold_block` 兩個空行判斷式共用 `_fold_blank`
    （logic F8：只改一處會卡死；共用後改成 `not l.strip()` 也不卡——兩者在 shell 層等價，純空白行與空行都打斷折疊）。
  - **宣稱層**：`LEN_CLAIM` 改讀 `oracle.VERDICT_KINDS`（requirements F3：前一版量的是 CHANGELOG 自己打的字面清單）；
    舊段那一句改成純文字。已知類別 G 開追蹤 #59，test.yml 的對外註解寫明 `--strict` 規則與這條例外。PR body 的「缺」殘骸已刪。
  - **`opsweep --since 6cf6864` 的非預期存活逐一處理**——**這是本輪鑑別力工作的主體**，因為它直接回應 R34 的中心
    發現（網只對作者點名的輸入有鑑別力）：這個機制被關掉的時候，有沒有東西會叫。第一輪（在 `42e0e4a` 上）271 個突變體
    報 66 個非預期存活，處置分兩種、**不是各半**——16 個那一行已不存在（刪死碼或改寫），50 個靠補 fixture 殺掉：**死碼刪掉**（`_ansic_decode` 的越界守衛、`_param_end` 的兩個 `$[` 分支、算術的巢狀 `((`、
    分隔字收集器的 `k + 1 < n`、兩處 `and not unparsed`、`_kids` 的 `ind_ > pind`、`_scalar` 的三個 `.strip()`
    ——依構造到不了、或到得了但不改變判定；留著只會讓人以為有東西在守），**其餘補會翻色的 fixture**
    （`${…}` 裡的命令替換含空字串、分隔字 `$'…'` 讀到行尾未收尾、container job 與 Windows runner 沒寫 shell、
    `--strict` 下預設 shell 但完全沒有管線、帶 `# LOG-FILTER:` 宣告的 step 不受兩條 stderr 規則管、
    `steps` 不在 job 底下的 composite 形狀…）。
    **突變體 id 的末段是「同一運算子、同一函式、同一行原文的第幾次出現」，不是第幾個運算元**——這一點我踩過，寫在這裡當警告：
    `if STRICT and eff_shell is None and job and (job["container"] or job["windows"]):` 這一行有兩個 `BoolOp`
    （外層四個運算元、內層兩個），依原始碼位置排序後 **5 號是內層的第一個，也就是拿掉 `job["container"]`**。
    我照運算元序號把它讀成 `job["windows"]`，於是補的 fixture 守的是 Windows 那半邊，而 container 那半邊仍然
    空著——下一輪 opsweep 照樣報它存活。**載體是「手寫錨點重放」**：錨點為了唯一性會帶上前後文，於是**鄰行**
    也被比對成「已涵蓋」。判斷一個突變體有沒有被處理，只有兩種可靠依據——比對 (運算子, 函式, 行原文, 序號) 四元組——也就是 opsweep 自己的 id，
    或直接在最終樹上重跑一輪；現在單點重放一律 import `opsweep.mutants()` 用它自己算出的 span。
  **我在這一輪自己的錯**：負對照腳本兩次把 `$?` 接在管線或命令替換之後、讀到別的命令的退出碼（當下發現、重跑）；E 組抄錯一個
  引號（反而撞出一個繞過）；shell 規則第一版放在預設模式（三軸抓到 290 個誤擋）；雙引號 heredoc 第一版 fail-closed（8 個誤擋）；
  一個 fixture 的 step 名稱含 `: `、PyYAML 拒絕（lint 碰巧判紅——不合法的 YAML 證明不了任何事）；R35-4 的 fixture 先寫實作才跑
  selftest（事後把新 fixture 丟給上一個 WIP 的 lint 補看 RED：12 個反向 fixture 全部判 pass）；把 opsweep 的突變體序號讀成
  運算元序號、於是把一個機制的網補在隔壁（見上面 opsweep 那一條，該條也寫了現在怎麼避免）；寫 `test_validate.py` 檔頭的量測段時，
  先宣稱「這是第一次三個檔一起零存活」（**假的**——R27 的 125 靶就是 0 存活，守備範圍當時已是三個檔），
  又把 62.6 s 這個每靶秒數記到別輪頭上（那是 R27 的）。兩次都是憑印象寫輪次對應、當場回 CHANGELOG 原文核才發現。
  **「第一次／歷來最好」這類最高級敘述是本 PR 反覆長出來的東西**，寫之前一定要回原文查——這一次沒有流出去，
  但前幾輪流出去過。
  **發 commit 之前另跑了一輪對抗式宣稱查核**（本段與 `test_validate.py` 檔頭切成 12 段、279 條可查核宣稱，每條由一位查核者
  試著推翻，判假的再交兩位獨立挑戰者從證據與範圍兩面反駁；有兩條因挑戰者輸出格式失敗只剩一位，我回原始資料補判）：抓到 **12 條寫錯或寫過頭**的——R34 的 MEDIUM 數、四個最小修法
  「全部」量過、野外 13 檔的 key、把一句問句掛到 R34 名下、opsweep 第一輪的突變體數、死碼與 fixture「各半」、突變體序號的
  定義、「三元組」、「lint 沒動」、「30 個新靶」、每靶秒數的低端、「主要受同機負載」。全部在原處就地更正並註明。**作者自審
  報「完全符合」、另一個讀者才抓得到**——這一輪又是一次。對外文字（squash 的 commit message、PR body 的新段落，270 條）
  另跑一輪：兩位挑戰者都維持的 5 條——commit message 的神諭漏寫「不可比」一格、語料數字的量測樹、PR body checklist
  裡還有一個 R34 的「8 MEDIUM」、量測段標題的「全部於最終樹」、上一輪有兩條只剩一位挑戰者卻寫成兩位（就是上面那個分號）；
  另有 15 條挑戰者意見分歧，我回原始資料判定採納 12 條（多數同屬「量測樹」這一個根因）、駁回 3 條。
  數字（selftest、fixture 神諭、opsweep、run.sh 在 R35 最終樹上實跑；產生語料、`--verify-expected`、三軸、全輪 mutation 在 `d135f13`
  上實跑——兩者之間只加了兩個 fixture、lint 只改 selftest 門檻四行，這四項的輸入與被量的程式碼都沒變。這裡原本寫成「全部在
  最終樹上實跑」，是對外文字的第二輪查核抓到的）：lint fixture 173 → 268 個——108 個正向、98 條規則紅、62 條解析紅；
  **R35 時這四個數字寫成帶指令的宣稱**（`lint-changelog-counts.sh` 會實際執行它們）——先前這一行的 fixture 計數
  只是散文，而 selftest 的門檻與它之間沒有任何機械連結，抄錯不會有人叫。（歷史數字；帶指令的現況宣稱只留在最新一段，R37 起移到上面。）靶清單 161 → 193 個；
  CI run step 23 個；
  fixture 神諭 356 個 step：一致 282、不一致 3（**全部已知**：G 2、S-2 1——三張都是刻意寫成已知類別的 `known-*` fixture）、不可比 71、量不到 0；產生語料 624 檔：一致 524、不一致 62（**全部已知**：S-2 60、G 1、`!!str` 1）、不可比 38、
  量不到 0；`opsweep --since 6cf6864` 252 個突變體 → 249 殺（其中當掉 26）／3 存活（**非預期 0**、預期 3）；第二道判準（產生語料抓到而 selftest 沒抓到）0；`--verify-expected` 的 7 條在 624 檔上逐檔相同；
  三軸（base `6cf6864`）合成 A 1222 檔（base-綠 959）GREEN→RED 10（9 個是 `bash -n` 自己就報語法錯誤的檔、1 個跨行 `${…}`）、
  野外 1538 檔（base-綠 364）0／0；`shapes.py` 的 R3* 每一列在產生語料上都 > 0（野外對 R35 十三列全部 0 檔——**野外 0/0 對本輪
  任何一個機制都不是證據**）；run.sh `✓ 全部通過`（254 ok、0 not ok；單獨跑，無其他量測並行，724 秒）。
  **全輪 mutation（193 靶）已量完**（在 `git archive d135f13` 的隔離副本上）：**189 殺／0 存活／4 預期存活／0 靶壞，
  146.8 分鐘＝每靶 45.6 s**。那之後只再加了兩個 fixture；三個被 mutate 的檔裡 `validate.py`／`neutralise.py` 沒動，
  `lint-ci-log-filter.sh` 只改了 selftest 門檻四行（107→108、61→62 與它們的訊息），不在任何靶的錨點內，所以靶仍然對得上
  （`--check-targets` 秒級可驗；這一句原本寫成「lint 沒動」，是假的）。靶清單 161 → 193：新增 33 個名稱、1 個舊靶拆成兩個
  （淨增 32；原本寫成「30 個」，是錯的）；新增的靶在這一輪全部被殺——4 個預期存活都是 R27 以前就有的。

- **verify R32（4 lens + DA + Codex 跨模型 leg）— 8 HIGH、7 MEDIUM blocking。** 失守的**形狀**變了：前十輪是
  「新機制沒有網」，這一輪是「**網存在、跑了、回綠，而它從來沒有被人看過它變紅**」。中心發現由 DA 獨立跑出：
  R31 宣傳的「468 檔語料不一致 **0**」是**儀器失能**——神諭的文字哨兵（腳本尾端補一行 `:`）被未終止的 heredoc
  吞掉，最後一個 pipeline 因此沒被記到、報「量不到 60」而 rc 不變。DA 改一行（`trap ':' EXIT`）之後是
  「**不一致 55**」，而那 55 個恰好就是正確的 `fold_block` 會修好的那一組（逐檔比對相同）。**兩個檔案裡的兩個
  缺陷互相抵消成一個綠色的招牌數字。** 另有三個活繞過（folded scalar 三行、`${…}` 逃脫的 `}`、空分隔字 `<<''`
  ——第三個**只有那條什麼都沒跑的跨模型 leg** 提出，四個 Claude lens 全部收斂到同兩處：**收斂本身就是盲點**）、
  一個本輪引進的誤擋（`${{ format('{0}', …) }}`，野外 11/1565）、`shapes.py` 對 R31 每個機制零列且不在 CI、
  `LEN_CLAIM` 對它為之而寫的那一句零命中、自查缺陷 (b) 的 fixture 還原時不翻色而 header 寫了假的因果句。
  R33 的修正（**換證據標準：一張網只有在有人看過它變紅之後才算數**）——每一條都附 negative control：
  - **儀器**：神諭改 `trap ':' EXIT`（非文字哨兵）；`量不到` 的標題不再斷言「逾時」（各列自帶原因）；lint rc=2
    讀成 `ERROR`／不可比而非 `pass`（DA-8）；`pass ∧ piped ∧ leaked` 不再判「一致」（Codex 第 4 條），且洩漏分
    stdout／stderr：**stderr-only 按類別記為已知 S-2**（不逐檔列）。修前後（468 檔）：`量不到 60` → **0**；
    只修哨兵是「不一致 55」，哨兵＋`fold_block` 是「一致 468、不一致 0」——**中間那一行就是 negative control**。
  - **`fold_block` 遞移折疊**，並對 PyYAML **逐行**相符（R37 更正：這句在 R33 當時沒有範圍、也不成立——首行含 tab
    的 block，`dedent_block` 把它當空行算縮排，R36 第 10 列量到不符；R37 修掉之後以 `test/corpus/foldcheck.py` 的構造量到
    `run: |`／`run: >` 各 136,660 組（4 行）整字串全部相等；同一支對 380e4a4 的 lint 在 3 行就量到 literal 462 組、folded
    588 組內容承載行不符；構造與範圍外見該檔檔頭）（含空行不折、more-indented 前後不折、**內容行後的第一個
    空行是分隔符而非一行**——最後這條是 642 檔語料抓到的 R33 自查：空分隔字的 heredoc 被一個 runner 沒有的
    佔位空行終止）。先前那個「7 個案例全相符」的驗證**濾掉了空行**，所以看不見它；重寫成不濾任何東西、
    外加行數契約的比對，15 個案例全過。佔位改用 `None`（runner 眼中沒有那一行）。
  - **`${…}` 只在未引號、未逃脫的 `}` 結束展開**（bash 5.3 實測 `${X#a\}b}`、`${X#"}"}`、`${X#'}'}` 三者都吃到
    最後一個 `}`）——同一個修法同時關掉 S-1 的繞過與 regression HIGH-1 的誤擋（三個真實世界形狀：
    swift-transformers、facebook/react，R31 出貨版 rc=1 → R33 rc=0）。
  - **分隔字詞尾另立 `DELIM_WORD_BREAK`**（`SHELL_WORD_BREAK` 是為「`#` 在不在詞首」定義的，被重用就錯了）；
    `$(…)`／`` `…` `` 是詞的一部分整段消費；**空分隔字**登記 heredoc（`saw_word` 與 `delim` 分開）。三個探針
    在 R31 出貨版上都是「不一致：繞過」、R33 都是「一致」。
  - **形狀普查進 CI 與 `run.sh`**：`shapes.py` 補 11 列（R31-1…5、R32-1…6），`--require-nonzero R3` 任一列
    為 0 就 rc=1；`shellgen.py` 新增 D 組（參數展開內部構造 5 × 擺法 2、分隔字跨行構造 4 × 方向 2、YAML 層 4）
    並把 DELIMS 補 4 個實測過的終止字（`''`／`""` → 空字串、`` EOF`x` ``、`EOF$(x)`——**用 bash 自己的 EOF
    警告讀出來的**）；C 組改用完整 STYLES（docstring 說 48、程式跑 24，分岔改成一致）。468 → **642 檔**。
  - **`EXPECTED_SURVIVE` 的 `fold_block` 四條全部撤掉**——理由本身就是那個 bug，不得改寫後沿用。
  - **`LEN_CLAIM`** 量詞放寬（「格」等）＋每種宣稱形式各自的 vacuity 守衛（99 → rc=1、6 → rc=0）。
  - **opsweep** 第二道網：shellgen 失敗 fail-loud 而非回空樣本；空樣本拒跑；比 `(rc, RULE/PARSE 標記序列)`
    而非只比 rc。
  - **DA-7**：`good-literal-brace-then-pipe` 改成 `${PR_TITLE#a{b}`（差一個 `c}`），還原「每個 `{` 加一層」
    → rc=1（先前那個 fixture 還原後 rc=0，header 的因果句是假的，已刪）。
  - **四個 R31 折疊 fixture 的第一行原是 `echo "$PR_TITLE"`**，與它們要釘的語意無關，卻把會外流的 workflow
    釘成 pass——神諭誠實化後當場報出，改成不外流的第一行。
  - **刻意保留、明寫的三條已知**（lint 檔內新增封閉列舉「第二組」）：stderr 沒有規則（repo 自己 17 條管線全帶
    `2>&1`／`|&`，影響面 0；規則的網是 149 個 fixture 與 `shellgen.NEUT`，留 R34，儀器已看得見）；一條管線＝
    整個區塊已過濾（宣告過的語意，先前沒寫在清單裡）；多行分隔字一律 `PARSE:`（誤擋方向）。`!!str` tag 誤擋
    記 `KNOWN_DISAGREE`（那道 fail-closed 守著 R30 MB-8 的隱形 job 真洞，野外 0/1565）。
  - **兩個 R33 自己的缺陷，都是 opsweep 的存活指出來的——而且存活的突變體比程式碼對**：(a) `fold_block` 用
    `l.strip()` 判空行，但 PyYAML 對 `['a','   ','b']` 給 `'a\n   \nb'`——只含空白、比縮排深的行是 more-indented 的
    一行，不是空行，也不終止 `cat <<''`；`if l:` 那個突變體存活，因為它才是對的（改照它，補
    `bypass-folded-whitespace-only-line-empty-delim`）。(b) 分隔字裡的 `$(…)` 前一版整段消費，而 bash 會**重新序列化**
    它再當終止字（`cat <<EOF$(a;b)` 的 EOF 警告寫「需要 EOF$(a; b)」——多一個空格），詞法抄不出來 ⇒ 改 fail-closed
    `PARSE`；反引號逐字保留（實測 `EOF`a;b`` 原樣）。那十個「守著追不到的東西」的運算元隨之消失。
  - **依構造多餘的運算元刪掉、不豁免**（同 R31 對 `fold_block` 的處置）：`acc` 非 None ⇒ 必指向非空內容行，所以
    `out[acc] is not None and out[acc].strip()` 恆真（兩處）；`drop_first` 裡的 `j < n` 是死的；續行的
    `li + spans < len(lines)` 邊界移進 `_next_phys`（越界回空字串）。
  數字（全部在 R33 commit 樹上實跑，指令見各行）：fixture 神諭 **253 step：一致 214、不一致 1（已知 1）、
  不可比 37、量不到 1**；產生語料 **642 step：一致 504、不一致 102（已知 102——類別 G「一條管線＝整區塊」41、類別 S-2「僅 stderr」60、
  `!!str` tag 1）、不可比 36（fail-closed：未收尾引號 4、`$(…)` 分隔字 32——後者由產生器自宣告 parse-red）、量不到 0**；`opsweep --since d8340a6` **107 個突變體 → 殺掉 104（當掉 17、產生語料抓到而 selftest 沒抓到的 2）／存活 3（非預期 0、全在 EXPECTED_SURVIVE）／壞掉 0**；
  靶清單 155 → 161 個（R33 當時以 grep 計數；lint 形式的宣稱只留在最新一段）（7 個 EXPECTED_SURVIVE，
  **五條全部**由 `opsweep.py --verify-expected` 在 642 檔上逐檔跑出「全部相同」——R31 留了兩條沒驗，這次沒有）；
  lint fixture 156 → 173 個（70 正向／67 規則紅／36 解析紅；`ls test/fixtures/ci-log-filter-*.yml | wc -l`）；
  CI run step 23 個（R33 當時以 grep 計數；lint 形式的宣稱只留在最新一段）。
  三軸（base `d8340a6`）：野外清單 1565 檔中本機今日可解析 1534（31 檔隨 plugin cache 換版消失——R34 requirements F8 更正：原寫 25，1565 − 1534 = 31；`threeaxis.py`
  對解不開的路徑 fail-loud、不印假 0）／分母 362：`RULE:` 8550 → 8550、`PARSE:` 1619 → 1619、`GREEN→RED` 0、
  `RED→GREEN` 0；合成 A 1222／分母 959 同（0／0）。**但這個 0 只對一個機制是證據**：用 `shapes.py` 量野外
  base-綠分母，R31-1…5 與 R32-1…5 **全部 0 檔**、只有 R32-6（折疊 ≥3 行）13 檔——依 `shapes.py` 檔頭的規則，
  其餘十個機制**不寫** `GREEN→RED` 數字，它們的網是 642 檔產生語料（每列 > 0，由 `--require-nonzero` 閘門守）。
  **R31 段的「不一致 0」已依 G-R32-DA-1 改述**：那個 0 是「量不到 60」的鏡像，不是一致。

- **verify R30（4 lens + DA + Codex 跨模型 leg）— 6 HIGH、14 MEDIUM blocking、4 MEDIUM、7 LOW。
  件數跳升不是因為改壞了，是因為驗證的武器變了。**
  先給 credit（DA 自己重跑出來的）：把 R29 交進 repo 的 `oracle.py` 指向 **base 的 lint ＋ head 的 fixture**，
  一條指令、167 step、**10 個不一致**，逐一對上 R28 的 D1–D7；指向 head 的 lint 則是 **0**。
  **R28 在機制層點名的每一條都真的關上了，而且「關上了」現在可以用一條指令證明。** 六條 HIGH 在 base 上
  同樣 rc=0（既有缺陷、非 R29 回歸）；R29 自己引進的只有兩條誤擋（MB-1、MB-12），兩條都 fail-closed。
  **方法層新增第 14 類「網的投餵」**：判準已經與作者無關（固定運算子、bash 神諭），但**餵給它們的輸入集合
  仍然是作者挑的**——同一支 `oracle.py` 在作者的 109 個 fixture 上不一致 0，在 DA 與 regression 各自產生的
  語料上分別報出 10 與 72 條。另**擴寫第 8 類**涵蓋相反方向：凡是「等價／不涵蓋／不可能」，
  沒有一條會翻色的指令就是未量測的宣稱（本輪兩次為假：`EXPECTED_SURVIVE` 的 `dedent_block` 條目、
  14 個「依構造等價」改寫之一）。R31 的修法：
  - **`shell_scan()` 改照 bash 的性質做，不再逐個形狀補**（六條 HIGH 兩族）：heredoc 分隔字**整詞
    quote removal**（`<<"EO"F`／`<<'EOF'x`／`<<""EOF`／`<<'E'OF` 四個實例一個根因——前一版只認「詞的開頭是
    引號」，`<<""EOF` 被讀成空字串、整段內文變 code）；`$'…'` 的 `\'` 是逃脫；`${…}` 整段消費（`${VAR#pat}`
    裡的 `#` 不是註解、`|` 不是管線）；反引號是詞界（bash 在 `` `#… `` 起註解）；**折疊 `>` 先折再掃**
    （YAML 把相鄰內容行接成一條 shell 行，`#` 之後整條都是註解——前一版逐實體行掃，lint／CI／job
    三個訊號全綠而 runner 真的洩漏）；**管線的左邊必須有東西**（行首的 `|` 在 bash 是語法錯誤），
    且「一條命令」改由**邏輯行**定義（只在 `|`／`||`／`&&` 之後接續），不再把整個區塊接成一串。
  - **YAML 層三條規則的觸發條件從字元類改成結構**：`root_indent` 由**解析器實際分類成 KEY 的行**決定
    （一行寫在第 0 欄的跨行 scalar 續行就能關掉整族 flow 規則）；flow 規則移到分類完成之後判，
    順序問題結構性消失；tag（`!!map`）與 anchor／alias 同列 fail-closed；**引號 key 先解碼再比對，
    解不出來就當它可能是 `run`**——R31 探針證實 GitHub **接受並執行** `- "\x72un":<TAB>echo …`
    （run 34938201988，log 逐字 `Run echo HEXKEY-TAB-PROBE`），而 PyYAML 拒絕它。
  - **`explicit_pad` 只從標頭本身取指示子**（MB-1，四條 leg 各自獨立提出）：`BLOCK_SCALAR_RE` 自己允許
    行尾註解，而前一版對整個標頭搜數字，於是 `run: | # see issue 9` 這種合法又合規的寫法由綠翻紅，
    訊息還捏造一個不存在的 PyYAML ParserError。**假診斷第三次 → 機械化**：新增
    `test_parse_messages_claiming_pyyaml_failure_are_true`，走「訊息 → 印得出它的 fixture → PyYAML
    對那個 fixture 真的丟例外」整條鏈，**每一個**印出該訊息的 fixture 都必須真的被拒絕（用 `any` 會被
    旁邊一個真的壞掉的 fixture 蓋過去——R29 的假診斷正是這樣活了一輪）。
  - **`test/corpus/shellgen.py`（本輪最高槓桿）**：按**封閉的構造維度**取笛卡兒積產生 workflow，
    **不列舉已知形狀**——分隔字引號擺法 12、引號種類 4、`#` 位置 6、block scalar 形式 8、管線位置 3、
    內文縮排 2，分三組取積共 **468 檔**。神諭對它：**舊 lint 97 個不一致、新 lint 0**。（**R32 DA-6 更正**：這個 0 是儀器失能——同一份語料同時報「量不到 60」，哨兵修掉後是 55；正確的數字在 R32 段。）
    這份語料進 CI（`oracle.py` 跑兩次：作者的 fixture 一次、產生語料一次），並成為 `opsweep` 的
    **第二道判準**——突變體只要讓任何一個產生檔的判定改變就算被抓到，於是「selftest 沒抓到」與
    「沒有任何網抓得到」第一次被分開報。
  - **神諭改用 bash 自己的剖析器判管線**：DEBUG trap ＋ `${#PIPESTATUS[@]}`（長度 ≥2 才是 pipeline）。
    前一版問 `[ -p /dev/stdin ]`，而 bash 5.x 的 heredoc 也用 pipe → 對 lint 發出**假指控**。
    宣告改用**差分**（把候選文字從 `#` 切到行尾再跑一次，可觀察結果相同才算註解）——前一版的裸子字串
    把 heredoc **內文**裡的假宣告當成真宣告，**認證了一個真繞過**。逐 step 歸屬改用**行號**
    （`name: |` 的名字在 lint 與 PyYAML 眼中不同，名稱比對必然失配）。判定表補第三格
    **「量不到」**（逾時、或這一次執行沒有把 PR 文字印出去）——**繞過的判準現在是三件事同時成立**：
    lint 放行 ∧ runner 沒接管線 ∧ PR 文字真的外流。
  - **`EXPECTED_SURVIVE` 的「依構造等價」現在跑得出來**：`opsweep.py --verify-expected` 對每一條在
    468 檔產生語料上逐檔比對原碼與突變體；`dedent_block` 那一條**當場被證偽**（引號 heredoc 的分隔字
    可以是空白），R31 採納突變體的答案（純空白行也剝區塊縮排）並補正向 fixture。
    `--since` 的區域改用 difflib 的**真正變更行**（前一版函式層比「去空白後的文字」、模組層比文字集合）。
  - **語料工具 fail-loud**：`threeaxis.py`／`shapes.py` 對解不開的清單一律 rc=2 具名報告——前一版對
    repo 內**唯一** tracked 的那份清單印出一張合格的 0 表 rc=0（它記的是可攜格式，在任何機器上都解不開）；
    非 UTF-8 的檔另計一欄。`shapes.py` 的述詞改**對準機制的實際觸發條件**（D5 含行尾註解裡的數字、
    D7 含 plain 純量、flow key 用 `root_indent`），並補上本輪真正改動的分支各自的形狀。
  - **1002 檔 GitHub 語料清單進 repo**（`test/corpus/gh-workflow-corpus.txt`，hash ＋ repo 相對路徑）：
    R29 在註解裡寫「清單見 test/corpus/」而那 1002 檔只活在維護者本機的快取裡——位置陳述為假比沒有
    陳述更糟，它讓讀者以為自己可以查證。
  - **CHANGELOG 的第四種宣稱形式**：「N 種（`python3 -c "…"`）」這類「數字 = 資料結構長度」的宣稱
    現在由 `lint-changelog-counts.sh` 逐字執行並比對（前三種都要求宣稱自己寫出 `grep -c`，所以這一類
    在結構上碰不到那支 lint——R30 抓到兩個實例）。正反兩個 fixture 各一。
  - **本輪自己的三個缺陷是新工具抓到的，不是我抓到的**（這是 R30 第 14 類要的那個證據）：
    (a) 雙引號分隔字裡的反斜線——第一版無條件吃掉，而 bash 只在 `$`／`` ` ``／`"`／`\` 之前才當逃脫
    （`<<"E\OF"` 的終止字是 `E\OF`，實測 bash 5.3）。lint 的 delim 比 bash 短 ⟹ 一行 `EOF` 在 lint 眼中
    終止 heredoc、在 bash 眼中還是資料 ⟹ **我自己在這一輪引進了一個真的繞過**，由 opsweep 的存活指出那一行
    沒有網、再由產生語料的神諭確認。(b) `${…}` 的巢狀——第一版對每個 `{` 都加一層，而 bash 只在 `${` 開新層
    （`${PR_TITLE#a{b}c}` 在第一個 `}` 就結束），於是 `echo ${PR_TITLE#a{b}c}| python3 …neutralise.py`
    這條**真管線**被整段吃掉＝誤擋，由神諭在產生語料上報「不一致：誤擋」抓到。(c) **分隔字詞裡的行尾反斜線**——
    R30 的註解把「行尾 `\` 不續行」寫成**全稱**，而 bash 5.3 實測三條規則各不相同：`cat <<AB\` ⏎ `CD` 的終止字是
    `ABCD` 且內文**照樣展開**（所以那個反斜線**不**使 heredoc 變成 quoted）、`cat <<"AB\` ⏎ `CD"` 的終止字也是
    `ABCD`（不展開是因為有引號）、而 `cat <<'AB\` ⏎ `CD'` **不**續行（單引號裡反斜線與換行都是字面，bash 直接
    警告 EOF）。前一版照那句全稱做，delim 讀成 `AB\` 且被判成 quoted ⟹ 終止字永遠對不上 ⟹ heredoc 吃到檔尾 ⟹
    真管線被吞掉＝**誤擋**。opsweep 對那兩個 `j + 1 < n` 各報存活，指的就是這裡沒有網。三條各補會翻色的 fixture。
  - **分隔字裡的引號沒在同一行收尾 → 改成 fail-closed 的 `PARSE:`**（opsweep 的最後一個存活逼出來的）。
    前一版假裝引號在行尾收掉、算出一個終止字，然後對整個 step 回**綠**；bash 5.3 實測兩種情形都不是綠
    （引號到檔尾沒收＝語法錯誤；收在下一行＝分隔字含換行、heredoc 永不終止、後面全部當內文）。
    本 lint 的分隔字是單行字串、表示不了含換行的那個，所以不解析它——且**不再印 `RULE:`**
    （R24 DA-8(b)：沒被解析出來的區塊沒有適用對象）。**這一條的價值在於它是唯一分得出「不解析」與
    「解析成別的東西」的形狀**：在它之前，那個運算元的兩版對所有輸入判定都相同，寫得出來的 fixture
    只能把一個**錯的**綠釘住。四個 fixture 因此從 rule-red 改判 parse-red。
  - **一個分支因為「沒有網」而被刪掉，不是被豁免**：opsweep 對 `$"…"` 那個 `startswith` 報存活，而寫不出
    會翻色的 fixture——因為 `$"` 的引號規則與雙引號**完全相同**，`$` 走通用字元路徑、下一格的 `"` 走一般引號
    分支，結果一模一樣。R30 為它寫了一個分支，它從來沒有行為。**多餘的程式碼沒有網，是因為它沒有行為**；
    處置是刪掉（同 `fold_block` 折疊條件那兩個運算元），不是寫進 `EXPECTED_SURVIVE`。
  三軸（base `d278e99`，野外 1565 檔／分母 369）：`GREEN→RED` **0**、`RED→GREEN` 0、`RULE:` 逐行相同
  （`PARSE:` 有 26 行是訊息文字改了：anchor／alias／merge key **／tag**）。
  測試 143 → 144 條（歷史數字；帶指令的現況宣稱只留在最新一段，R39 起是 147）；
  靶清單 139 → 155 個（9 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段——R33 起是 161）；
  lint fixture 109 → 156 個（61 正向／60 規則紅／35 解析紅；`ls test/fixtures/ci-log-filter-*.yml | wc -l`）；
  CI run step 22 個（R33 起 23：形狀普查閘門）；
  神諭的判定表現在有 6 格（一致／繞過／誤擋／誤擋（PARSE）／不可比／量不到；R35 起這一類宣稱改由 `oracle.VERDICT_KINDS` 驗，見最新一段）。

- **verify R28（4 lens + DA + Codex 跨模型 leg）— 掃描器五個 rc=0 回歸、兩個誤擋、方法層三條。
  0 HIGH、12 MEDIUM blocking、2 LOW。** 先給 credit：繞過方向在野外分佈上第一次收斂（regression 抓 59 repo／
  1002 檔 GitHub workflow，`GREEN→RED` 0），R27 的 11 個新靶 10 殺 1 預期存活成立。FAIL 來自 D1–D5（`shell_scan()`
  重寫後的五個 rc=0：`$((` 雙重計數、終止字 `rstrip()` 太寬、內文行尾 `\` 併掉終止字、`<<'E\OF'` 反斜線被剝、
  `run: |2` 顯式縮排指示子被忽略——**最後這條只有 Codex 看到**）、D6/D7（續行重掃漏 `pending` 快照、引號 run
  ＋行尾註解不解碼）、D8（flow 規則擋 `matrix.include`，blocking 在量測與宣稱不在機制）、D9（harness 前置
  只驗一個 suite）、**D10 網的顆粒度**（作者挑 RED 驗證的對象——DA 用固定運算子掃 R26 的新機制，62 個突變體
  29 存活，其中四個是當輪剛修好的機制）、**D11 分母結構性為 0**（含 heredoc 的檔在 base 全紅，分母裡沒有那個
  形狀）、D12 宣稱層。修法：
  - **掃描器 D1–D6**：終止字要**完全**相等；未引號分隔字含反斜線視同引號化；未引號內文行尾 `\` 是續行、下一行
    不可能是終止字；`((`／`))` 整個 token 消費（**`$((` 不另開分支**——`$` 沒有特殊意義，獨立分支關掉後 selftest
    仍綠、依構造等價，所以刪掉而不是列預期存活）；`run: |N` 由呼叫端算 `explicit_pad` 交給 `dedent_block()`，
    淺於指示子的內文行與 `|0`／`|10` 標頭都是 YAML 錯誤（PyYAML 各自 ParserError／ScannerError）→ `PARSE:` 不猜；
    續行重掃前還原 `pending` 快照。D7：`run: "…" # note` 先用 YAML 規則切掉註解再解碼，註解半邊歸宣告來源 (3)；
    D8b：`yaml_split_comment` 雙引號內 `\"` 是逃脫。**每個機制一個 mutation 靶、一個會翻色的 fixture**：13 個新
    lint 靶單獨實測全殺；三個第一版 fixture 零鑑別力（D2 只寫了引號分隔字那半邊、`((` 從沒被裸用、`$((` 等價）
    當場由 mutation 迴圈抓到——**這一次是機制抓的，不是人抓的**。
  - **作者無關的網進 repo（D10，本輪最高槓桿）**：`test/opsweep.py`——對 lint 內嵌的 Python 用 AST 套五種固定運算子
    （strip→id、±1、刪布林運算元、startswith→False、==↔!=），每個突變體跑一次 selftest；`--since REF` 只掃自 REF 起
    被 diff 觸及的函式＋模組層新行。**基線（修法前）：區域 106 個突變體，30 存活。** 處置分三類、比例明寫：
    12 個補會翻色的 fixture 殺掉（含 `<< EOF` 分隔字前有空白、`printf ""` 空引號後接管線、`$(a $(b)); cat <<EOF`
    巢狀命令替換讓深度變負、續行後緊接的下一行、`|2` 區塊裡的空行）；14 個是**依構造等價**——不列預期存活，
    改寫程式碼把等價的運算元拿掉（`j < n and line[j]` 改切片、`not quoted and body_continued` 的前半已含在後半、
    引號字元不再留在 code 裡、`i == 0 or …` 改 `prev`、run 值在抽取處一次 strip）；4 個列 `EXPECTED_SURVIVE` 並各附
    可檢查的理由（單字元引號是無效 YAML、純空白行剝成空行、`<<<` 落到 `<<` 後 delim 為空）——**4 / 30 = 13%
    ≤ 1/3**（G-R29-5(c)），工具內另守 ≤ 突變體數 10%。修後：91 個突變體、0 非預期存活（見下方量測）。
    第一輪整段 sweep 跑到一半時我又加了三個 fixture，之後每個突變體都因門檻對不上被判殺——整輪後半作廢；
    `opsweep.py` 現在開跑時快照 fixtures，lint 與 fixture 在同一個時間點凍結。
  - **bash 神諭進 repo（D10(b)）**：`test/oracle.py`——stub `python3` 記錄「被呼叫時 stdin 是不是管線」，對每個
    fixture 的每個 `run:` step 真的用 bash 跑，與 lint 逐 step 對帳。selftest 只證「lint 判定 = 作者宣告」，這是第一次
    把 runner 拉進來；CI 新增 step（先 `pip install pyyaml`，缺席 rc=2 fail-loud）。它當場抓到一件 selftest 三輪都綠
    的事：`good-semicolon-logfilter` 前一版**根本不是合法 YAML**（plain scalar 裡有 `: `；GitHub 探針 run 34927068746
    「workflow file issue」）——lint 放行了一個 runner 不會跑的檔。改成 `LOG-FILTER:none`（冒號後不接空白）。
    盲區明寫：YAML 層 PyYAML ≠ GitHub（R28 探針 tab 分隔的引號 key PyYAML 拒、GitHub 執行），`YAML-FAIL` 那格
    是它看不到的地方，不是安全區。
  - **前置檢查對每個守備單位各跑（D9）**：`precheck_suites()`，同指令去重、任一紅整輪不跑並點名 suite；
    `test_mutation_precheck_runs_every_suite_command` 用假 suite 釘「每條指令恰好一次、紅的被點名、main() 走同一條」。
  - **GitHub 探針第三次（G-R29-8）**：整份縮排 2 格的 workflow **GitHub 接受並執行**（run 34927069456，
    `Run echo INDENT-ROOT-PROBE`）；`steps: [run: …]`（34927069402）與 `steps: [{"\x72un": …}]`（34927069449）
    **也都執行**——三者 lint 都是 `PARSE:` fail-closed，方向正確。indented root 被接受 ⇒ `top_key` 改成「文件
    最小縮排的 plain key」（前一版寫死縮排 0，縮排根文件裡 jobs 子樹的 flow 規則整個不觸發；
    `bypass-indented-root-flow-mapping` 修前 rc=0）。探針分支讀完即刪，run 保留為證據。
  - **flow 規則的受影響面寫出來（D8，選 b1）**：野外 1565 檔被擋 58 檔／177 行——121 行單行 `{ name: …, os: … }`
    （`matrix.include`），56 行跨行 flow 序列的開頭 `[`；量法與數字寫在規則旁邊，`bypass-matrix-include-flow-mapping`
    釘住「刻意 fail-closed」；放行方向補 `branches: [main]`、引號內冒號、`\"`、`""` 空字串、`build#1` 字內 `#`、
    jobs 外的 `{ branches: [ main ] }` 六個正向 fixture；不平衡的 `{`／`[`（含無續行的）各一個 parse-red。
  - **分母形狀（D11）**：`test/corpus/shapes.py` 對每個新機制一個可計數的觸發形狀，報它在各清單的檔數；
    `threeaxis.py`／`synth.py`（A/B/C 三變體）一併進 `test/corpus/`。量到的（見 PR body 表）：D1–D5、D7、D8b
    的形狀在 1565 檔野外與 1222 檔合成 A 語料**都是 0**——所以**本段對這些機制不寫 `GREEN→RED = 0`**；它們的
    網是 fixture＋神諭＋靶，不是語料。D6 野外 2 檔、D8 34 檔。
  - **解碼不變式的 mode 位置（G-R29-9）**：`io.open`／`codecs.open` 與 builtin 同 signature，前一版把所有 Attribute
    都當 `Path.open(mode)`，讀到的是路徑（R26 修過的同形缺陷換了兩個 callable）；Starred 引數 → 不推定 binary。
    判定本體抽成模組層 `decoding_findings()`，四紅四綠的 probe 真的跑它。
  - **宣稱層（D12）**：`shell_scan` docstring「四件」實列五件 → 改五件並補 R28 六件，`test_shell_scan_docstring_counts_match_bullets`
    機械對齊（對 HEAD 版實測 FAILED `5 != 4`）；R27 寫「量測腳本 threeaxis.py」而它只在 verify 暫存目錄——現在
    `test -f test/corpus/threeaxis.py`；`EXPECTED_SURVIVE` 檔頭 4 vs 內文 3 → 4；G-R27-9 兩處自揭句裡的被禁字面改寫；
    README「三支 lint」→ 四支＋oracle；`def shell_scan` 前補空行。
  測試 140 → 143 條（R29 當時的數字；lint 形式的宣稱只留在最新一段）；
  靶清單 125 → 139 個（4 個 EXPECTED_SURVIVE）（R29 當時的數字）；
  lint fixture 70 → 109 個（42 正向／41 規則紅／26 解析紅；selftest 三個門檻等於實測值，`ls test/fixtures/ci-log-filter-*.yml | wc -l`）；
  CI run step 當時 21 個。
  神諭：109 fixture 共 167 個 step，一致 125、不一致 0、不可比 42（PARSE fail-closed 或 PyYAML 拒）。
  區域 opsweep（修後）：84 個突變體、80 殺（其中 4 個是當掉）、0 非預期存活、4 預期存活（基線 106／30 → 91／11 → 84／4；每輪都是靠改寫或補 fixture 減，不是靠豁免）。全輪 mutation（139 靶，於 `git archive d278e99` 副本上跑）：**135 殺 / 0 存活 / 4 預期存活 / 0 靶壞**，98.8 分鐘、每靶 42.6 s。見 `scripts/test_validate.py` 檔頭。
- **verify R26（4 lens + DA + Codex 跨模型 leg）— 繞過方向乾淨、誤擋方向有回歸、新機制沒有網。
  0 HIGH、9 MEDIUM blocking。**
  先給 credit：regression 用 636 檔語料逐檔比對，`RED→GREEN` 零、規則層新增零行，**R25 在繞過方向的宣稱
  完全成立**；放行條件 G1–G8 由多條 leg 各自在隔離樹拆掉驗紅、全部 PASS（G9 語料存檔 FAIL）。
  FAIL 來自：誤擋方向兩條回歸、新引進的繞過兩條、方法層三條。修法：
  - **mutation harness 的守備範圍擴到三個檔**（本輪最高槓桿）。「新機制沒有 RED 驗證」在本 PR
    **發作了七次**，R26 的 DA 把它診斷到方法層：RED 驗證的對象、突變的選擇、fixture 的內容，三者都由
    剛寫完那段程式碼的人自己挑；而 repo 早有正解——具名靶 ＋ `EXPECTED_SURVIVE`——只是守備範圍寫死
    「只 mutate `validate.py`」。現在每個靶用第四欄選守備單位（`validate`／`lint`／`neutralise`），既有
    114 個靶一個字都沒動。**靶數 114 → 125；11 個新靶單獨實測 10 殺 / 1 預期存活**（`<<<` 那條依構造
    等價，理由寫在靶旁邊可檢查）。R26 對這七個機制的 sweep 是 7/7 SURVIVED，現在它們第一次有網。
    `neutralise.py` 的串流補了 `test_neutralise_streams_instead_of_buffering_until_eof`，revert 回 `read()`
    實測 FAILED。
  - **`shell_scan()` 重寫（M2＋M3＋M5 同一個 patch）**：呼叫端先剝 block scalar 共同縮排（heredoc 終止
    判定才可達——前一版在任何真實 `run: |` 裡都不可達，之後的真管線與 `# LOG-FILTER:` 一起被吞）；
    `<<<` 一次消費三格；`$((` 深度內不判 heredoc；heredoc 佇列改 FIFO（前一版只存 `pending[0]`，註解裡
    「其餘由分隔行順推」是假的）；`<<\EOF` 的反斜線只是引號化分隔字；**行尾 `\` 真的續行**——把下一個
    實體行接上來、從邏輯行開頭重掃（接縫可能落在 token 中間，`cat <\` ⏎ `<EOF` 的 `<<` 就跨在接縫上）；
    詞首判定改用 `prev_sig`，被逃脫的空白不再起註解。
  - **`run` key 守恆不變式改結構判定**（M1）：不再補字元類。`[-{,]` 有兩個錯——漏 `[`（YAML flow 序列
    允許無括號的單對 mapping）、`-` 命中識別字內的連字號（`dry-run:`／`operations-per-run:` 被判成藏起來
    的 run key，**我在 R25 引進的真誤擋**，第三方語料當場 6 處）。修字元類之外，**`jobs:` 子樹裡的 flow 值
    只在「單行且不含 mapping」時才容忍**，其餘 fail-closed：本 lint 不解析 flow mapping，不解析就不放行。
    第一版對整份文件套用，`on: pull_request: { branches: [ main ] }` 這種合法且結構上不可能藏 step 的寫法
    被打紅——**三軸量測當場抓到兩個第三方檔從綠翻紅**，收窄到 `jobs:` 子樹。
  - **`yaml_decode_scalar()` 對未實作的逃脫一律拒絕**（M4，Codex 第 1 條）：前一版只是刪反斜線，
    `"echo \x22hi | python3 …"` 被解成 `echo x22hi | python3 …`——憑空生出一條管線，而 runner 拿到的是
    一個沒有管線的字串。**lint 與 runner 跑不同的字串**，上一層就給錯了。現在只解 `\\`／`\"`／`\n`／`\t`／
    `\r`／`\/`，其餘 `PARSE:` 拒絕不猜。
  - **解碼不變式的 scope 述詞**（M9，Codex 第 7／8 條）：`binary_mode` 前一版讀 `n.args[:1]` 找 `"b"`——
    那是 `open()` 的**路徑**引數不是 mode，於是 `open("blob.txt")` 綠、`open("notes.txt")` 紅，差別只有
    檔名裡的字母；改成依 signature 取 mode 位置、無法解析不得推定 binary。`text=` 只認 `True`／`1` 讓
    `text=2`／`text=<變數>` 掉出 scope，改成除非能靜態證明為 false 否則算數。封閉列舉補 `getoutput`／
    `getstatusoutput`。六個探針（四紅二綠）各自實測。
  - **五處假宣稱改成事實**（M8）：`:428` 的「已知誤判方向」寫的形狀實測不會被拒、而真正會被誤擋的
    沒寫——現在只寫量到的並附語料與分母；「兩種宣告來源」實為三種（`run:` 行尾註解），明寫並補正向
    fixture；`mutation_check.py` 宣稱串流「由兩條 CI 中和測試釘住」為假，改成事實；`shell_scan` docstring
    的「五種」封閉列舉實列六項且有第七種，**改回陳述性質**（本掃描器不判可達性）而不是再列一個會漏的清單。
  - **語料清單進 commit**（M10）：`test/corpus/r25-workflow-corpus.txt`，**不寫本機絕對路徑**（對別人
    不可重跑），改用內容 hash ＋ `<repo>/.github/workflows/<檔名>` 形式，可在任何有同批 checkout 的機器上
    重新對帳。
  - **GitHub 探針第二次（G-R27-8）**：`run: "echo x \| …"` 三個 YAML 實作都拒絕，但 R24 的前例是「兩個
    library 拒絕、GitHub 接受」，所以再推一次一次性探針問 GitHub——**GitHub 也拒絕**（0 秒失敗、零 job）。
    四方一致，不可利用。**教訓不是「library 總是判錯 GitHub」，是每一種形狀都得各自問**；用其中一次
    的結果類推另一次，正是 R24 讓 coordinator 連錯兩次的動作。
  **三軸量測（R26 M7 的方法）**，base 用 `git archive db0c0f2`，逐檔比 `RULE:`／`PARSE:`／rc，
  **並報告 base-綠檔數當靈敏度分母**：真實語料 563 檔（分母 129）`GREEN→RED` 0、`RED→GREEN` 1（R25 的
  `-run:` 誤擋被修好）；DA 合成的 base-綠語料 324 檔（分母 93）`GREEN→RED` 0、`RED→GREEN` **16**（正是
  R26 指出 `db0c0f2` 誤擋的那 16 檔）。原始語料對 heredoc 誤擋的分母是 0，合成那份是 93——兩份都跑，
  分母都寫出來。
  **coordinator 在本輪自己犯的錯，當場抓到並修**：一個 patch 腳本把整個檔案的空行刪光（26 個）；flow
  結構規則第一版對整份文件套用（見上）；三個新 fixture 第一版零鑑別力（`<<<` 與 `$((` 的管線寫在同一行、
  `<<-` 終止字縮排比 block scalar 淺——那在 YAML 裡根本不是區塊內容、單引號 fixture `.py` 後面沒空白讓
  尾錨兩種狀態都不命中）。**為了修「fixture 沒有網」而寫的 fixture，自己沒有網**——同一個形狀，
  發生在為了修它而做的事上，第八次。
  測試 139 → 140 條；靶清單 114 → 125 個（4 個 EXPECTED_SURVIVE）（R27 時的數字；lint 形式的宣稱只留在最新一段）。
  lint fixture 51 → 70 個（19 正向／32 規則紅／19 解析紅，selftest 三個門檻改成等於實測值）。
  全輪量測（125 靶，三個檔的守備範圍）：**121 殺 / 0 存活 / 4 預期存活 / 0 靶壞**，130.3 分鐘、
  每靶 62.6 s。見 `scripts/test_validate.py` 檔頭。
- **verify R24（4 lens + DA + Codex 跨模型 leg）— 述詞層**沒有**關閉：五個互相獨立的根因，
  加上一個 GitHub 實測確認**可利用**的繞過。0 HIGH、6 MEDIUM blocking。**
  先給 credit：R22 的五條 blocking **全部真的修好了**（regression 與 DA 各自在隔離樹逐條實測），
  CI 三 job 全綠、無 scope creep。FAIL 來自三處：同族未關閉成員、本輪修法自己沒有 RED 驗證、宣稱層。
  - **`run:` 區塊改用真正的跨行 shell 詞法掃描器**（`shell_scan()`）。R23 宣稱的架構事實是真的
    （兩個述詞確實共用同一個抽取函式），但**共用的是同一個錯誤答案**：那支函式的名字與 docstring
    說它切的是「會被執行的部分」，它實際切的是「引號外且 `#` 外的部分」。三條 leg 獨立收斂到同一點。
    新掃描器的狀態**跨行**：單雙引號、反斜線逃脫、heredoc（含 `<<-` 與引號分隔字）。三個桶而不是兩個
    ——code（會執行）／decls（shell 註解）／**丟棄**（heredoc 內文與引號內容是**資料**，前一版把
    heredoc 內文留在 code 裡，所以裡面寫一句話就能冒充管線或宣告）。
  - **`#` 改用 shell 的詞首規則**（`;#`／`&#`／`|#` 都起註解），前一版用的是 YAML 的「前一字元須為空白」。
  - **`||` 不是管線、`|&` 是**。`echo x || python3 …neutralise.py` 在 `echo` 成功時後者**從未執行**，
    前一版把它算成已過濾；反向真管線 `|&` 被誤擋。兩個方向各一個 fixture。
  - **YAML 引號純量先解碼再交給 shell 掃描**：`run: "echo hi | python3 …"` 是合法寫法、runner 執行的
    命令真的有管線，前一版把含 YAML 外層引號的原始文字整段挖空 → 誤擋且訊息是假診斷。
  - **`run` key 的守恆不變式**（一條式子取代兩個特例）：文字裡看得出是 `run` key 的位置數一遍，
    與解析器實際記到的對帳，多出來就 fail-closed。這一條同時關掉「引號 key ＋ tab 分隔」與
    「flow 形式的 job／jobs」兩種讓 step 完全隱形的寫法，而且未來任何新的藏法都走同一條。
  - **`- { … }` 這類 flow 清單項的雙重訊息**：`reject()` 之後少一個 `continue`，於是同一行再吐一則
    「清單項的 key 不是 plain 形式」——而 flow mapping 裡的 key **全都是 plain**，那是假診斷。
    563 檔語料上出現 6 次，全是 `matrix.include`。補 `continue`，誠實的那一則留下。
  - **資訊行不再斷言原因**：整檔沒偵測到 run step 時，前一版說「純 uses:／reusable workflow」——
    那是它**沒有驗證**的事。現在只陳述觀察，不給原因；真正擋「沒看懂」的是上面那條守恆式。
  - **解碼不變式的 scope 述詞改成封閉列舉**：`errors=` **自己就會啟用** subprocess 的文字模式，
    所以 R23 新加的「檢查 errors 的值」對最自然的危險寫法**根本不可達**；`encoding=` 從 scope 條件
    移到 requirement 側（前一版「`open` 且有 `encoding=`」會讓**不寫** `encoding=` 的更不安全寫法掉出範圍）。
    九種形狀各自注入、**九個各自轉紅**。
  - **`neutralise.py` 改成串流**：前一版讀到 EOF 才動，整個 process group 被砍（＝逾時／取消的實際行為）
    時 log 整段消失——fail-silent 出現在專門防 fail-silent 的機制上。實測：t=0.8 s 有輸出、
    group SIGKILL 後位元組數與對照組相等。
  - **本輪自己的修法補網**：`REMOTE_SOURCES` 六個成員先前只有 `github` 有網，現在**六個各自拿掉都會紅**。
    這條測試的第一版我寫成 `for kind in V.REMOTE_SOURCES`——**迭代實作的表**，成員被拿掉時迴圈連測都不測，
    六個全綠；那正是本 PR R19/R20 失守過的「測試要陳述需求、不要把實作的表當規格」。已改成測試自己列出
    六個再與實作對帳。
  - **三句過期的「誠實邊界」註解改成事實**：`SINK_CONTAINERS` 的那句在 R23 打通 taint 鏈的同一個 commit
    之後變成假（清空它現在**恰好多出 1 條** `(1410, 'e')`），已寫成測試釘住、兩個方向都斷言；
    fixpoint 的那句宣稱它在真檔上有證據，實測改回短路版全套仍綠、且 `:1193` 兩版結果逐項相同——
    因為 fixpoint 沒有迭代上限，短路只延後收斂、不改變不動點，**那一條目前沒有斷言也沒有靶**；
    「零豁免清單」那句刪除。第四句（R22 裁決 4 的第三句假宣稱）漏改的第四處在 issue 的
    Implementation Complete comment 裡，已補 errata、原句保留。
  - **GitHub Actions 自己的解析器：實測，不推斷。** 放行條件明文禁止再用任何單一 YAML library 推斷
    tab 分隔合不合法（libyaml 接受、PyYAML 與 ruamel 拒絕）。推一個一次性探針分支實測：
    **GitHub 解析成功並執行了那個 step**（run `34663977450`，log 逐字含那行 echo），探針已刪除。
    所以那是**真的可利用**的繞過。coordinator 在 R24 期間對這一條做了三次公開更正，
    **第一次是對的、第二次（說不可利用）是錯的、第三次（說未定）誠實但已被硬證據取代**——三次都留在 PR body。
  **不宣稱這一類已經關閉。** `shell_scan()` 是**詞法**的，不判定**可達性**：`false && …`、`if`／`case`
  的未走到分支、`eval` 的字串、`$(...)` 內的巢狀命令替換，詞法上看得到管線、執行上不會跑到。
  這五種寫在該函式 docstring 的**封閉列舉**裡並明寫「不要因為這段話存在就以為它們有網」。
  要關掉它們必須真的求值 shell，不在本 lint 的範圍內。
  測試 137 → 139 條；靶清單 114 → 114 個（3 個 EXPECTED_SURVIVE）（當輪值；lint 形式的宣稱只留在最新一段）。
  lint fixture 51 個（11 正向／27 規則紅／13 解析紅，selftest 的三個門檻改成**等於**實測值——
  先前寫 `>=` 而實際更高，那個差額沒有網）。
  真實語料前後比對（563 檔去重，排除前幾輪 verify 自己的產物、含 142 份第三方來源）：
  `RULE:` 行 2711 → 2709，差異**只有 2 條**且兩條都是把**假的 `RULE:`** 換成**誠實的 `PARSE:`**，
  檔案仍 rc=1；新抓到的 RULE 行 0 條。假診斷 6 處 → **0**；每行最多一則 `PARSE:`。
- **verify R22（4 lens + DA + **Codex 跨模型 leg 恢復**）— 白名單做在結構層，兩個判定述詞仍是
  對原始文字的正規式。0 HIGH、5 MEDIUM blocking。**
  **本輪的大事：R10 以來第一次成功取得跨模型 leg**（R11–R21 連續九輪 429）。Codex 五條裡**三條是
  四個 Claude lens 都沒提出的**，DA 在隔離樹逐一實測後**五條全部成立**，其中一條被評為本輪最銳利。
  這是「5-AI 同家族夠不夠」的直接資料點：不夠。修法：
  - **兩個判定述詞共用同一個抽取函式**（R22 的 meta 根因）。`ok = (PIPED_RE …) or (LOGFILTER_RE …)`
    是兩個判斷，R21 只白名單化了右邊；左邊對原始文字搜尋，於是 YAML 行尾註解、shell 註解、字串裡
    「提到」管線都算已過濾。而 `COMMENT` 的分類又排在白名單**之上**，只看 `strip()` 是否以 `#` 開頭
    ——requirements 的控制組把因果釘死：拿掉那個 `#` 就變 rc=1 並印「本 lint 不解析這一行」，
    **白名單本來抓得到**。現在 `split_code_and_comment()` 把每一行切成「會被執行」與「不會被執行」
    兩半（引號內容整段挖空），管線判定只看前者、`# LOG-FILTER:` 只看後者。
  - **結構／分類層的五種殘留**：`BLOCK_SCALAR_RE` 只認 chomping 在前的指示子順序，而 YAML 兩種都
    合法（`|2-`／`>2-`／`|2+`）；跨行引號 scalar 的續行被當成註解。**`ff0f215` 也有這些洞**，是這一族
    未關閉的成員、不是 R21 的回歸。另外修掉 R21 自己帶進來的一個：`run: |` 的 `|` 是 block scalar
    **指示子**不是程式碼，接上下一行會**憑空造出一條管線**。
  - **誤擋與繞過同時關**（R22 裁決 3 與 5：22 個 fixture 裡 8 個**只靠 parse-reject 變紅**，而
    parse-reject 正是修誤擋必須放寬的機制——selftest 分不出兩種紅，就等於「修誤擋會靜默重開繞過」）。
    R22 的 DA 在 26 份合法 workflow 上量到先前誤擋 20 份（那份 corpus 是它臨時蒐集的、無法逐字
    重現，故本輪另做了下方可重跑的量測），根因是把「清單項一定是 mapping」當成不成文前提，於是
    `on: push: branches:` 底下的 `- main`（Actions 最常見的寫法之一）被拒、訊息還是**假診斷**。
    判別式改用 **YAML 自己的**：rest 含 `": "` 或以 `":"` 結尾才是 mapping。**每個拒絕訊息現在帶
    `RULE:`／`PARSE:` 來源標記**，每個 fixture 用 `# EXPECT:` 宣告它該是哪一種，selftest 逐一比對
    （斷言的是**紅的種類**，不只是 rc）。**那 8 個「只靠 parse-reject 變紅」的 bypass fixture 在本版
    逐一實測：8 個全部仍紅、且仍是 `PARSE:` 紅，零個被放行**——被放寬的（清單項的 mapping 判準、
    `---`、純 `uses:`、指示子順序）與它們依賴的不是同一個機制。base 上那 22 個的 14 rule／8 parse
    分佈也逐一重跑核對過，與 R22 的裁決相符。
    正向 fixture 從 **1 個增為 9 個**（負向 23 → 30）——先前 24 個 fixture 裡只有一個是正向，
    沒有東西在證明它放得過好輸入，誤擋失控正是這個不對稱的必然結果。（**更正**：本段初稿寫成
    「補上 9 個正向、先前 22 個全是負向」，兩個數字都錯——22 是 `bypass-*` 的數量，`bad.yml` 與
    既有的 `good.yml` 沒算進去。這種「把子集講成全集」正是本輪在修的同一個形狀，寫在這裡而不是
    默默改掉。）`---`／`...` 文件標記與純 `uses:` workflow 也不再被拒（vacuity 保護改由
    selftest 專用的 `--require-run-steps` 提供）。
    **在真實 workflow 上的前後量測**（fixture 是自己寫的，證不了「對別人的檔也對」）：本機 21 個
    repo 的 33 份 `.github/workflows/*.yml`，同一份清單各跑一次 base 與本版 ——
    假診斷「清單項的 key 不是 plain 形式」**23 處／5 檔 → 0**；純 `uses:` workflow 的 vacuity 拒絕
    **1 檔 → 0**；而 `RULE:` 那 137 行**逐行完全相同**。最後這一項正是 R22 裁決 5 擔心的事
    （放寬解析層會不會連規則層一起放掉）的直接反證。**仍會被拒的一種，明寫**：欄位用 YAML
    anchor／alias 帶入時（corpus 裡 1 檔 2 處）本 lint 印 `PARSE:` 並拒絕 —— 這是**刻意 fail-closed**
    （alias 後面可以藏 `run:`），訊息也誠實寫「本 lint 不解析」，不是假診斷。
  - **taint 的鏈補完**（security S-1；R12 第 5 條的缺陷類別靠這個洞回來了）：傳播沿參數但**不沿
    回傳值**，而主要閘門又都經 `gate(name, fn, …)` **間接呼叫**——兩者相加讓 `check_csvs` 的
    `files`／`path` 一路到 `:1189` 都沒染色，剝掉那裡的 `ann_path` 全套仍綠且無靶。補三件：
    回傳值傳播、gate 間接呼叫解析、**fixpoint 不再用會短路的 `any()`**（後面的函式那一輪不會被
    分析，迴圈可能在收斂前結束）。鏈打通後**立刻在乾淨樹上抓到 8 個未包裹的站點**（`profile` 來自
    lens 檔名、`own` 來自 collector_wiring），全部補 `wc()` 並各自驗紅。
  - **解碼不變式改成驗值**（Codex #3，DA 評為最銳利）：前一版只檢查 `errors` keyword **存在**，所以
    `errors="replace"` → `errors="strict"`／`None` 照樣綠，而子行程吐 `\xff` 時仍會讓整道 `check_csvs`
    退化成「validator 內部錯誤」。站點集合也補上 `text=1`／`universal_newlines=`／`check_output`／
    `Path.open(encoding=)`。四種破壞方式各自驗紅。
  - **`REMOTE_SOURCES` 對齊官方表**（Codex #4，DA 更正 Codex 只講對一半）：官方是
    `github`／`url`／`git-subdir`／`npm`／`archive`／`command`——R21 寫的**漏三種、且多一個官方表裡
    沒有的 `git`**。
  - **changelog fixture 的對照組改用固定值**（Codex #5）：先前用「測試 130 條」當對照，而正式測試數
    已增長，於是 fixture 失敗的原因變成**數字不符**而不是未知錨點被拒——把 R18 的後門重新引入，
    selftest 仍會報 ok。對照宣稱改指向本檔一行固定標記，selftest 並斷言**拒絕的理由**。
  - **更正 R21 的三句假宣稱**（R22 裁決 4）：`_LINE_BREAKS` 的副本否認同時出現在 commit message、
    CHANGELOG **與那份副本上方兩行的程式碼註解**——`OTHER_BREAKS` 逐位元就是它減掉兩個條目且順序
    相同。**現在不列舉了**：改用 Python 自己的 `splitlines()` 推導，副本整個移除。另外「matrix/defaults
    零誤擋」為假（block 形式會被拒）、「PR body 數字由 `lint-changelog-counts.sh` 機械重算」為假
    （那支 lint 只讀 `CHANGELOG.md`，PR body 是人工抄本）。
  - **補做 R21 漏掉且未揭露的一項**：`bin/pai-collect-lens-layers` 的 `profile` 直接接成檔名、零驗證，
    `..` 與絕對路徑都逃得出去。改成封閉字元集。**R21 的八項 LOW 修 5 留 3 而 commit message 與
    CHANGELOG 都沒揭露——未揭露本身被定為 MEDIUM，這裡一併補記。** 仍未修的：`SEED_CALLS`／
    `READ_CALLS` 不對齊、`wc()` 的 `##[` 與截斷無專屬靶（行為上有網）。
  - **本輪自己的三個數字也寫錯過，一併揭露**：fixture 的「22 個全是負向」（實為 24 個 = 23 負向 + 1 正向）、
    taint 形狀的「5 → 8」（實為 6 → 8）、PR body 的「數字由 lint 機械重算」（那支 lint 只讀 CHANGELOG）。
    三個都在 commit 前用 `grep`／`ls` 核出來並就地更正。**三個的共同點是它們都不在 lint 認得的宣稱形式裡**
    （`N（\`grep -c "…" path\`）`）——會被機械驗的那兩個數字（測試條數、靶數）本輪一次都沒錯。
    這不是巧合，是「散文裡的數字沒有網」的直接證據；把 fixture 分佈之類的宣稱也納入 lint 形式列為下一輪候選，
    本輪不動（改 lint 的文法屬於另一件事，而它自己也需要一輪 verify）。
  測試 137 → 137 條（當輪值；**lint 形式的宣稱只留在最新一段**，舊段落一律改成歷史敘述，
  否則下一輪加測試時它會被重新驗而紅——R25 實際踩到）——**數字不動是實情**，
  本輪擴充的是既有測試的涵蓋（taint 形狀從 6 種增為 8 種——第 8 種與第 7 種共用同一條斷言、
  註解已說明；解碼不變式改成驗值並多四類站點），沒有新增 test 函式；
  靶清單 112 → 114 個（3 個 EXPECTED_SURVIVE）（當輪值；lint 形式的宣稱只留在最新一段）。
  量測（R23 後）：單一副本（`git archive` 取）完整一輪 **114 靶 → 111 殺 / 0 存活 / 0 靶壞**（另 3 個 `EXPECTED_SURVIVE`），實測 **72.2 分鐘 = 每靶 38.0 s**。
  **順手收斂了一處漂移**：同一個「最近一輪」的數字先前散在 `mutation_check.py` 兩處 docstring、`test/run.sh` 一處與 `test_validate.py` 檔頭共四份（其中一處還重複貼上了半句），現在只留檔頭那一份、其餘指回去。**CHANGELOG 的各輪數字不在此列**——那是歷史紀錄，每一條記的是當輪的值、本來就不該被更新。
- **verify R20（4 lens + DA；Codex 第九輪 429）— R19 換方向的檢定：方向對，但只套用到兩層裡的一層。**
  R18 的四條 blocking 有**三條確認真的修好**且 DA 逐一嘗試推翻失敗（taint 容器累積、`prop()` 五個轉義、
  containment 兩個方向）。lint 那條 partial：第一階段的**行形式**白名單守得住（DA 在能穿過第二階段的 job 裡
  寫 `"run":` 與 flow 寫法仍拿到具名拒絕），失敗形狀存活在**第二個解析階段**。DA 把四份各自報的多條 lint
  問題裁決成**同一個根因**，並指明分三個 patch 修等於保證下一輪有第四個出口。修法：
  - **第二階段整體白名單化**（不是三個 patch）。前一版用 `if ind <= s_indent: break` 當 steps 區塊的結束
    條件，暗含一個沒寫出來的前提「清單項一定比 `steps:` 更深」——**那不是 YAML 的規則**，block sequence
    可以與它的 key 同縮排，於是整個 job 隱形、rc=0 零輸出。現在 dash 的縮排由「`steps:` 之後第一個清單項」
    決定、之後只認恰好那個縮排的項；找不到任何清單項 → **per-`steps:` fail-loud**。
  - **宣告層也白名單**：`# LOG-FILTER:` 只認 (1) 真的是註解行且落在這個 step 自己的行範圍內、(2) `run:`
    **自己**那個 block scalar 的內容。先前 `name: |` 的 scalar 裡寫一行就放行整個 step（那是 step 的顯示
    名稱不是註解），而註解歸屬還會跨 step 邊界記到前一個 step。
  - **行界**：非 `\n` 的行界字元一律 fail-loud 拒絕（先前一個 U+2028 藏得住第二個 `run:`）。刻意**不**在
    lint 裡複製一份 `_LINE_BREAKS`——同一概念兩份實作正是本 PR 反覆修的病；白名單的作法是不解析就拒絕。
  - **跨行管線**：折疊 scalar（`>`）或行尾留 `|` 續行的合規寫法先前被誤擋，現在接成一串再比對；
    反向驗過折疊但未過濾的仍會被擋。
  - **走表測試改成陳述需求**（DA-6，四份都沒做）：R19 為「靶顆粒度」寫的那條測試**自己是假綠**——它只走
    實作的表並斷言長度 ≥ 11，於是把 `\x1c` **換成**別的字元（長度不變）→ 全套仍綠，那三個靶是被長度斷言
    殺掉的、不是被行為殺掉的。現在測試獨立列出「runner 會當成換行的字元」這個**需求**，雙向斷言，
    三個靶也改成**替換**而非刪除。刪除與替換各自驗過會紅。
  - **解碼站點改成機械不變式**（第四個粗靶）：`errors="replace"` 的 11 個呼叫點先前只有 1 個靶，拆掉
    `:1164`（由 node 求值 fork 可控 JS 的那個）→ 一個 `\xff` 讓 `gate()` 吞掉 `UnicodeDecodeError`、
    **整個 `check_csvs` 閘門不跑**而全套仍綠。出口不是手寫 9 個靶（清單自己會漂），是一條 AST 不變式：
    任何解碼外部位元組的呼叫要嘛帶 `errors=`、要嘛包在接得住 `UnicodeDecodeError` 的 try 裡。
    **11 個站點逐一拆掉各自驗過會紅、零豁免清單。** 嚴重度按 DA 更正為 denial-of-gate（rc 仍為 1 並具名）。
  - **`source` 三態守衛**（修掉 R19 引進的回歸）：R19 把合法的遠端物件形式 `{"source":"github",…}`（`pai-lenses`
    在 main 上的形狀）當成「既不是字串也不是物件」硬報錯——對一個 dict 說它不是物件。但只放寬成「非 str
    非 dict 才報」會用一個假陽性換到兩個靜默跳過，所以做三態：本地 → 進閘門；**封閉列舉內**的遠端 →
    具名跳過；其餘（不認得的 dict source、`source` 缺席／null）→ 具名報錯。三態各一條測試。
  - LOW：`--selftest` 的 vacuity 斷言補涵蓋 `bad.yml`；composite action 不在守備範圍**寫進 header**（依 DA
    不擴大 glob——composite 的 step 語意不同，硬套會假紅）。
  **流程**：本輪發生過共用 checkout 污染（有 agent 變異 tracked 檔、而 `git status` 當下讀起來乾淨），
  DA 全程改用 `git archive` 的獨立樹並逐位元驗過。**往後 lens 的破壞性實驗一律 `git archive`，不得 `cp -R`。**
  測試 133 → 137 條；
  靶清單 111 → 112 個（3 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段）。
  量測（R21 後）：單一副本（`git archive` 取）完整一輪 112 靶 → 109 殺 / 0 存活 / 0 靶壞（另 3 個 `EXPECTED_SURVIVE`），
  實測 64.2 分鐘 = 每靶 34.4 s。**耗時不再寫固定區間**——靶數每輪增加，舊區間連四輪被抓到低估；
  散文只留「靶數 × 全套測試」的關係，數字由 `mutation_check.py` 收尾自己印。
- **verify R18（4 lens + DA；Codex 第八輪 429）— R17 的兩條 blocking 主體都修好了，CI 三 job 全綠；
  失守的性質變了：不是又漏一個 case，而是**量測工具的顆粒度比缺口粗**。修法一律往結構走，不加特例：**
  - **`lint-ci-log-filter.sh` 改成白名單解析器**（四份 findings + DA 去重後仍有 **7 個互不相同的根因**：
    `run :` 冒號前空白、`"\x72un":` 雙引號跳脫、`? run` 顯式 key、重複 `run:` key、`steps: [{…}]`、
    column-0 的 `# LOG-FILTER:`、`env:` block scalar 裡的假 run 區塊、較早的 key 的 scalar 裡一行 `- `
    讓整個 `run:` 消失）。R15–R17 三輪都在加「拒絕這種寫法」的特例，而合法 YAML 比任何手寫黑名單大。
    現在只認明確列出的結構（plain key、block 清單、block scalar），**其餘一律 fail-loud**；七個根因裡有
    四個的來源是同一件事——沒有正確消化 block scalar，現在 scalar 內容是不透明文字，結構上不可能再被
    誤讀成 key 或清單項。白名單的**作用域**也要對：`with:`／`env:` 底下的巢狀鍵不是 step 欄位（第一版
    把它們也拿去比對，誤擋了真 `test.yml` 的四個鍵）。驗收：真 `test.yml` **0 誤擋**、19 個 bypass fixture
    **全部是規則紅**、`--selftest` 會斷言紅得對（種一個沒有 run step 的 fixture 進去，selftest 必須紅）。
    順帶移除一個靜默 fallback：傳不存在的檔先前會改去 lint 真的 `test.yml`。
  - **taint 傳播補容器累積**（requirements F-2 / logic / regression B-3）：`.append()`／`+=`／`.extend()`／
    `.add()` 先前斷鏈，於是 `validate.py:1218`（CSV `key` 欄名，本 validator **唯一真正 fork 可控的輸入**）
    與 `:962`（子行程 stdout）剝掉 `wc()` 之後那條測試綠、全套綠、連靶都沒有。兩個站點各自驗紅並進靶清單；
    形狀測試加第 ⑤⑥ 種並各自驗過會紅。`errs` 列為 sink 容器——**誠實邊界**：實測清空那個集合仍然全綠，
    所以它現在是防禦性守衛、不是 load-bearing，註解照實寫。
  - **粗顆粒的靶拆成細顆粒**（regression B-1 / security S-3 / DA-1 / DA-2 —— 本輪的共同根因）：
    `prop()` 的五個轉義共用一個靶，靠 `,` 那條測試就被殺掉，另外四個沒有網，而**沒有網的 `%` 正是可利用
    的那個**（fork 可控的檔名 `a%2Cline%3D1%2Ctitle%3DCI-PASSED.csv` 讓 runner 解碼回 `,`／`=`）→ 拆成五個靶、
    五條斷言、外加一條 PoC 測試。containment 的兩層（plugin 目錄／實際要讀的 plugin.json）共用一個靶，
    拿掉目錄層 **rc=0、全套全綠**，而 `plugins/evil` symlink 到 repo 外、`.claude-plugin` 再 symlink 回來時
    validator 會印「marketplace 版本一致 ✓」→ 拆成兩個方向、補反方向的 fixture。`_LINE_BREAKS` 的 11 個
    分隔符只有 8 個有網、`wc()` 自己那層的 `collapse_lines` 沒有靶 → 測試改成**走表**（加分隔符自動涵蓋）、
    補四個靶。三處各自驗紅。
  - **`source` 的型別守衛**（security S-4）：`source.path` 是 fork 可控的 JSON 值，給它 int／list／dict／bool
    會讓 `repo_abs / rel` 拋 `TypeError` 被 `gate()` 吞成「validator 內部錯誤」——這道標為 CRITICAL 的版本
    同步閘門整個不跑，同 PR 裡真正的版本不同步因此不被回報。改成具名回報；`source` 整個不是字串也不是
    物件時先前**靜默跳過**，也改成具名回報。兩個各一個靶。
  - **`lint-changelog-counts` 的 `../` 自我豁免改封閉列舉**（第四次）：`../pai-lensez`（打錯字）與
    `../bogus/../real/file`（繞路）各穿過一次。只有 `../pai-lenses` 與 `../../.github` 兩個真實佈局錨點
    可以觸發跳過，其餘照常驗證；路徑先 `normpath`。兩個 fixture 的語意隨規則反轉（名字說「必須跳過」而
    斷言是拒絕，正是這個 PR 在修的漂移），真正的「佈局缺席 → 跳過」改在 plugin-only 分支驗。
  - **`assert-tap-complete.sh` 補 `--selftest`**（requirements F-7）：它是 repo 裡唯一沒有網、不在 mutation
    範圍的守衛，而它守的正是「假綠」。六種 TAP 輸入各自判對，並掛進 `run.sh` 與 CI 兩個 job。
  測試 130 → 133 條；
  靶清單 105 → 111 個（3 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段）。
  量測（R19 後）：單一副本完整一輪 111 靶 → 108 殺 / 0 存活 / 0 靶壞（另 3 個 `EXPECTED_SURVIVE`），
  實測 55.1 分鐘 = 每靶 29.8 s。**靶數從 105 增為 111 不是多測了幾件事，是同樣的事量得比較細**（見檔頭）。
- **verify R17（4 lens + DA；Codex 第七輪 429）— R16 的 HIGH（CI 回歸）已清、CI 三 job 全綠、regression lens 首次 PASS；
  其餘三份 FAIL 全是「新閘門自己的假綠」（第七次同一形狀）。修法：**
  - `lint-ci-log-filter.sh` 第 5–9 種繞過（requirements F-1 / security S-1 / logic L-1 / L-7）：key 加引號的 `- "run":`；
    `.yaml` 副檔名不在 glob；`neutralise.py` 只要被**提到**（字串、`env:` value）就算；bare `-`（鍵在下一行）與 dash 後
    雙空白的項被併進前一個 step 而繼承豁免；`<<:` merge key 帶入的 `run` 看不見。改：step 正規式 `-(\s|$)`、key 去引號、
    glob 含 `*.yaml`、`neutralise.py` 必須是 pipeline 的一段、merge key／anchor／alias 起頭一律拒絕（本 lint 不解析就
    fail-loud）；`neutralise.py` 的判定再縮到 **`run:` 區塊之內的管線位置**（`env:` value 裡寫個像管線的字不算，R17 DA-B ⑤）；
    每一種各補一個 bypass fixture，selftest 改用 **glob** 逐一驗（寫死清單自己會跟目錄漂——同 repo 已有兩份 shellcheck 清單互不為超集的前例）。
  - taint 網（requirements F-2 / security S-2 / logic L-2 / L-3 / L-4）：R16 版只看 f-string、不跨函式，而「任何外部字串
    一律 wc()」在檔內有數十個反例、38 個 wc() 站點過半無回歸網。改成**來源封閉列舉 + 跨函式 taint**：從子行程
    `.stdout`/`.stderr`、`load_obj()`／`json.loads()` 回傳、`csv.DictReader` 列與 `.fieldnames`、`iterdir()`／`glob()`
    路徑出發，逐函式沿 Assign／for／comprehension 染色並跨函式（染色引數 → 被呼叫端參數，全域 fixpoint）；sink
    （`errs.append`／`emit`／`print`）引數裡任何未包 `wc()`／`prop()`／`ann_path()` 的染色子運算式一律紅，語法形式
    無關；`len`／`type`／`.returncode` 之類衍生值明示安全。網一開就抓到 40 個站點（entry name／source、`rel`、
    `pdir`、CSV 欄名／重複 key／未知欄位、列號清單、override 清單…）——全部補 `wc()`；規則措辭改成封閉列舉
    （來源列舉經 wc()，其餘只由 emit() 的兩套語法中和與 4000 上限守），不再宣稱「一律」。三種形狀（`+` 串接、
    跨函式參數、comprehension 衍生清單）與 entry name／CSV 欄名兩個新靶各自驗過會紅。
  - **自查（不是 lens 找到的，本輪修法自己的缺陷）**：為了證明 taint 規則「會紅」而寫的形狀測試
    **出廠即空轉**——它建了一段 snippet，卻只斷言裡面的函式叫什麼名字，從頭到尾沒跑判定；把跨函式
    傳播整段關掉它照樣綠。也就是說 R8 以來一路在修的那個缺陷（新機制沒有 RED 驗證），這次出現在
    **為了做 RED 驗證而寫的那條測試裡**。修法：判定抽成模組層的 `taint_findings()` 一份實作，真檔那條
    與形狀測試共用；形狀測試改成真的跑它，四種形狀（`+` 串接、comprehension 衍生清單、跨函式位置
    引數、裸 `for` 的目標變數）各自斷言被抓到，外加一個「全部包 `wc()` 就不該紅」的對照組。五種
    破壞方式（關掉 Assign／For／跨函式傳播、sink 退回只認 f-string、sink 漏掉 `print`）各自驗過會紅。
  - **更正 R16 commit message 的一句宣稱**（regression F7）：`dcd5c19` 寫「補 git status 路徑清單、manifest
    version 五處 echo、version note，**各釘測試與靶**」——全輪 mutation 實測六個站點裡有兩個存活：`:836`
    的 merge-base sha（`READ_SITES` 第 9 條早就註明結構上不可觸發，是正確的設計判斷）與 `:934` 的改名前
    路徑（這個是真缺口，理論上可測）。commit message 已 push、不改寫歷史，更正記在這裡；`:934` 就地
    補上「已知缺口」註記，不再假裝有網。
  - **issue #33 的 Implementation Complete comment 加註時效**（requirements F-4）：那張 Verification 表停在
    2026-08-12（plugin 2.23.0、46 條測試、37 靶、「九輪 verify」），而它是 IDD 規定的實作真源。加一則註記
    指向兩個 current 來源（PR body 的機械重算數字、`test_validate.py` 檔頭的 mutation 量測），**不改 Checklist**、
    也不就地把數字換新——把過期的表留著才看得出漂移。這是本輪唯一一次 diff 之外的寫入。
  - **全輪 mutation 抓到兩個真缺口，並推翻 R16 檔頭的一句宣稱**：`emit()` 自己那一層的
    `collapse_lines()` 與 `##[` → `##⟦` 兩個靶**零測試網**而存活。R16 檔頭寫「補一條直接呼叫 `emit()` 的
    單元測試後單靶轉殺」——**那句是假的**，既有四條 `emit` 測試驗的是截斷。而且它們**不是** equivalent
    mutant：實測拿掉 emit 這一層之後，`\n`／`\r`／U+2028／U+2029／`\v`／`\f`／U+0085 全部原樣輸出，
    runner 會在新的一行看到第二個**偽造的** workflow command；`##[error]` 同理。原因是縱深防禦的兩層
    （emit 與輸出邊界 `LineSanitiser`）共用同一個端到端斷言，拆掉其中一層另一層仍會擋 —— **每一層各自
    要有網**。補兩條直接餵 `emit()` 的測試（八種分隔符逐一驗），四個相關靶現在全部驗過會被殺。
  - 偵測器入口（security S-3 / S-5 / logic L-9）：`argparse.FileType`／`subprocess.getoutput`／`os.fdopen` 進
    `READ_CALLS`、禁 `fromfile_prefix_chars`；動態派發內建改看**任何** Name 引用（`_g = getattr` 綁變數先前能穿過）。
  - **自查之二**：L-5 的第一版修法**自己留了同一個後門**——「第一個非 `..` 段」若就是路徑最後一段
    （`../nothing-at-all.md`），錨點會等於那個不存在的檔本身 → `isdir` 為假 → 靜默跳過。錨點必須是
    **目錄段**；只差一層的路徑其容身處是 `..`，任何佈局都存在，因此不得跳過。兩個 fixture（必拒／必收）
    進 selftest，且三個舊版判準（R14 的「`../` 一律跳過」、R16 的 `dirname`、本輪第一版）各自驗過會紅。
    順帶記一筆方法論：驗這條時我**連兩次**把 vacuity 守衛的紅當成規則的紅（`no claims found` 也是 rc=1），
    與 R17 DA-B 抓到 regression 的是同一個實驗設計缺陷——fixture 必須同檔附一條驗得過的宣稱。
  - `lint-changelog-counts` 的 `../` 跳過再收窄（logic L-5：R16 的 dirname 判準讓「多寫一層不存在的子目錄」重開豁免）：
    只看第一個非 `..` 路徑段所指的**錨點目錄**（`../pai-lenses`、`../../.github`）不在才跳過，訊息不斷言佈局；補
    fixture。
  - `EVENTS` 與 test.yml `on:` 兩份規格（logic L-8）：測試機械比對 `on:` 的 trigger ⊆ EVENTS。
  - mutation 耗時再上修為 30–60 分（regression 實測 ≈54 分；每套測試 20–35 s × 靶數）；neutralise.py docstring 重複句
    （L-11）；test/README 的 lint 描述改成全部 workflow。
  測試 124 → 127 條；
  靶清單 98 → 100 個（3 個 EXPECTED_SURVIVE；lint 形式的宣稱只留在最新一段）。
  量測（R17 後）：單一副本完整一輪 100 靶 → 97 殺 / 0 存活 / 0 靶壞（另 3 個 `EXPECTED_SURVIVE`），
  實測 46.3 分鐘 = 每靶 27.8 s（由 `mutation_check.py` 自己印）；細節與前一輪的兩個真缺口見 `scripts/test_validate.py` 檔頭。

## [2.23.0] - 2026-09-10

### Changed

- **Codex leg 的背景執行收進 `bin/codex-call` 本身（`--detach` / `--poll` / `--abort`），退役 bash helper。**
  #37 的根因是 codex leg 一通最長 600 s 的阻塞呼叫超過 Workflow runtime 的 180 s
  no-progress 門檻，且 artifact 兩次經過 agent context。PR #47 先用 bash helper
  （`bin/pai-codex-review`）做背景執行，**三輪 verify（2.22.1 → 2.22.2 → 2.22.3，皆未進 main）
  每一輪都在修法本身找到新的 blocking**：supervisor 子 shell、trap 轉殺、marker 檔、status 檔、
  deadline 檔、child_pid 檔——六個機制各自帶 race。round 2 的結論：這是在用 bash 重新發明
  process supervision，而 bash 沒有原子操作、沒有 process identity、沒有不可偽造的 capability。

  現在 worker 是**單一 Swift 程序**（`codex-call` 以 `--_worker` 重新執行自己，它就是那通 HTTP
  呼叫，無 subprocess）：
  - **生存**：worker 對 `<run>/lock` 持有 `fcntl(F_SETLK)` record lock 直到結束
  - **身分**：`--poll`／`--abort` 用 `F_GETLK` 取得**此刻**持鎖者的 pid，發訊號只對它——不從任何檔案讀 pid；PID 重用的誤殺視窗縮到單一系統呼叫之間（契約 §4 誠實邊界，round 6 R6-6 指出本行曾寫「不可能」）。（實測 `flock()` 鎖在 macOS 的 `F_GETLK` 下 `l_pid = -1`，故用 `fcntl`）
  - **capability**：只接受 32 字元 CSPRNG run id，解析到 `~/.cache/codex-call/runs/<id>`（0700）。**不接受路徑**——round 2 證明「接受任意目錄 + 檔案存在性檢查」等於任意 PID kill／`rm -rf` 原語
  - **原子性**：terminal 清理以 `rename(run, run.done)` claim，併發 poll 只有一個回 terminal
  - **期限**：worker 自己強制 `--max-time`；poll 端兜底 `max-time + 60 s` 才 kill；meta 損毀 fail-closed
  - **stdio 不繼承**：`Process` 的 stdio 明確指派——round 1 在 bash 裡自抓的「`$(... start)` 阻塞到 run 結束」在這裡結構上不會發生
  - 既有同步路徑**逐 byte 不變**（codex-pro producer skills 不受影響）

- **`references/codex-call-contract.md` 新增（回應 #35）**：`codex-call` 至此有 documented STABLE
  surface——旗標、exit code、run id 格式、base 路徑、四種 poll 狀態、威脅模型、穩定性承諾。
  breaking change 需 major bump + migration note。

- engine `codexPrompt()` 改為兩條 engine 生成的命令（`--detach` / `--poll <id> --wait 30`，所有值 `shQuote()`
  單引號化）加兩條 agent 自組的命令（讀完後 `rm -f '<path>'`、早停 `--abort '<id>'`；round 4／5）。
  移除 `codexReviewPath` arg（隨 helper 退役）。

### Fixed（round 3 verify：5:0 FAIL + Devil's Advocate，全部修於同版）

- **startup race（唯一 CRITICAL 根因，四方各算一次）**：`--detach` 返回後有 0.6–1.0 s 無人持鎖，
  `--poll` 會把健康的 run 判成 `FAILED status missing` 並刪除、`--abort` 印 `ABORTED` 卻留下 orphan。
  修法是 **readiness handshake**：id 只在 worker **已寫出 status 或已持鎖**之後才印出（上限 20 s，
  worker 先退出且無 status → 同步 exit 1、附 `worker.log` 尾段）。「還沒開始」與「已經跑完」是兩個
  不同的答案——第一版 handshake 把它們壓成同一個，DA 實測 `--_selftest-sleep 0` 12 次 11 次把已完成
  的 run 判成沒啟動並刪掉結果；修正後 12/12。
- **status token**：`doPoll` 原用 `hasPrefix("3")` 分類，`NSError code 3`（`auth.json` 缺 tokens）與 3xx
  被報成可重試的 `TIMEOUT`。worker 改寫 token `TIMEOUT`，poll 比對整個 token。
- **測試無牙齒**（round 2 finding 4/5 同型第三度復發）：`! pgrep` 在 bats 中段被 errexit 豁免、
  路徑穿越 fixture 沒建出目標 → `validRunId` 零覆蓋。兩處改為 `run …; [ $status -ne 0 ]` 與真實 fixture。
- **契約誠實化**：§1 同步路徑順序以條件式 guard 還原（缺 `--output` 時先報錯、不先讀 prompt）；
  §4 的「不可能」改成量到的邊界（`F_GETLK` 與 `kill` 之間存在微秒級視窗）；§2 / §6 標為**封閉列舉**並
  明寫「不得依性質相似類推」，§6 補第三列「caller 環境完整性（`HOME` / base）」。
- lock 檔完整性（`O_NOFOLLOW` + `fstat`：一般檔案、`nlink == 1`、owner 是當前 uid）；
  base 硬化（`hardenBase`：symlink / 非目錄 / 非本 uid 擁有 → 同步 exit 1，宣告為行為）；
  worker 不可重放（status 已存在 → 拒絕）；poll 的 timeout / meta 損毀路徑經 `killHolder` 並確認鎖已釋放；
  `removeRun` 失敗不再被吞（abort 清不掉 → `FAILED` exit 2）；預設輸出檔在非 DONE 終態清除；
  worker `setsid()`；re-exec 用 realpath；模式旗標互斥；stale `.done`（>60 s）接手；
  `--detach` 的 `--max-time` 必須正整數；`--_selftest-grace` 需與 `--_selftest-sleep` 並用。
- **engine / skills**：無 artifact 時 context block 本身成為 positional prompt（原本叫 Codex 審一個它拿不到
  的 block）、兩者皆無則不派 leg；step 2 加 `sleep 30` 輪詢節奏；`DONE` 後輸出檔轉為 caller 所有、讀完要刪；
  早停要 `--abort`；detach 非零退出不 poll；`'<id>'` 單引號。
- **回收**：`--abort` 是盡力而為的早停路徑（agent 被硬殺時做不到），所以 `--detach` 每次先回收 >24 h
  且無人持鎖的 `<id>` / `<id>.done` / `<id>.out.md`（含 `prompt.txt`，即 artifact 的完整副本）。
- `FAILED` 終態把 `worker.log` 尾段附進 stderr——那正是 #37 抱怨看不到的診斷。

### Fixed（round 4 verify：四方一致 FAIL，全部修於同版）

- **輪詢節奏收進 codex-call**：`--poll <id> --wait N`（1–120 s）在工具內部阻塞、每秒重查持鎖者與期限、
  終態提早返回。round 3 的 `sleep 30; --poll` 在 Claude Code 的 Bash tool 上**被工具層拒絕**（實測
  `Blocked: sleep 30 …`），agent 只剩高速輪詢、`until` 迴圈（= stall detector 會殺的形狀）或放棄三條路。
  engine 與兩份 SKILL.md 改用 `--wait 30`，node 測試斷言 prompt 不含 shell `sleep`。
- **逾時判定依 (domain, code)**：`--max-time` 到期的主要路徑是 URLSession 自己的 timer
  （`NSURLErrorDomain/-1001`，比 semaphore 兜底早 5 s），worker 原本只認 `codex-call/408`，真逾時被寫成
  `FAILED -1001` exit 2——與 round 3 的 `hasPrefix("3")` 同型缺陷換了一端。新增隱藏 `--_selftest-classify`
  讓 bats 打到 catch 分支。
- **lock 完整性失敗 fail-closed**：三態 `LockState`（unlocked／held／untrusted）；完整性檢查失敗時 poll／abort
  exit 1、不發訊號、run 原地保留，GC 也跳過（原本被折疊成「未持鎖」→ 判為終止、刪 run、把活的 worker 孤兒化）。
  契約 §4 改成量得到的邊界：`rename()` 保留 inode，把 victim 持鎖檔搬進 lock 可過三檢查，bats 鎖住這個宣告的邊界。
- **`.done` claim 年齡改用 ctime**：`rename` 不動目錄 mtime（實測），舊判準會把剛 claim 的 `.done` 當 stale 讓第二個
  poll 接手；無 `status` 的 `.done` 是清理中斷殘留 → 清掉回 unknown，不再把已回報的 DONE 翻成 FAILED。
- **readiness 逾時先終止 worker**（SIGTERM→SIGKILL→等退出→再查鎖→才清；殺不死則 run 保留並說明）；driver 退出後
  多等 2 s 再判死（`p` 追的是 swift driver，exec-into-interpreter 是工具鏈事實不是不變式）；`killHolder` 兩輪收斂。
- worker 六條提早 `exit(1)` 各補一行原因、`finish()` 寫 status 失敗也 log——契約承諾的 `worker.log` 尾段不再在最需要時是空的；
  尾段改為**真的從檔尾**有界讀最後 12 行並過 sanitizer（原本 `clampToBudget` 取的是頭）。
- `hardenBase`：`chmod` 失敗 throw（原本被吞掉，「強制 0700」曾是 best-effort）；先驗上層再建 `runs/`；`~/.cache` 本身的歸屬寫進契約。
- `rename` 失敗依 errno 分流（EPERM 不再說「concurrent — retry」）；meta 損毀時預設輸出路徑可推導仍清除；`setsid` 失敗記 log。
- 文件：`rm -f '<path>'` 加引號、三處「agent 不組任何 shell」改為三條命令的誠實描述、兩份 SKILL.md 補 step 3／4；DATA_GUARD 涵蓋
  codex-call 的 stderr；契約 §2 首句與 handshake 對齊、§6 三列與 prompt-injection 段落分開、`HOME` 只隔離 run base 不隔離憑證。

### Fixed（round 5 verify：五方一致 FAIL，全部修於同版）

- **`--wait` 迴圈把 lock 三態折回兩態**（五方都抓到）：untrusted 在 wait 視窗內被當「已終止」→ 刪 run、孤兒化 worker。
  迴圈改為窮舉三態，untrusted 與無 `--wait` 的路徑同一個答案（exit 1、run 保留）；終態 claim 前再查一次。
- **`--wait 0` 溜過全部驗證**（用值當旗標存在性的 proxy），同步路徑因此真的發 HTTPS → 欄位改 `Int?`，
  `--wait` 不得配 `--detach`。
- **接手 stale `.done` 缺原子 claim**（1/20 雙 DONE）與 **`--abort` 不參與 claim**（曾 7/12 對成功的 run 偽造 FAILED）→
  依 round 5 DA 的結構建議一次收掉：終態處理只剩單一 `claimTerminal`（`--poll`／`--wait`／`--abort`／接手共用），接手以
  `.done` 內的 `O_EXCL` 標記為 claim、**不引入第三種目錄名**；`lockHolder() -> pid_t?` 整個刪除，12 個呼叫點改為 `switch`
  窮舉三態（Swift 編譯器強制），「無法判斷」在任何路徑都不再被讀成「已結束」。
- **`lstat` 失敗折進「沒有 lock」**（EACCES／EIO 等被當已結束）→ 只有 ENOENT 算沒有，其餘為「無法檢查」→ exit 1。
- **`removeDefaultOutput` 信任 `meta.output`** → 同 uid 寫 base 可遞迴刪任意目錄；改為只 `unlink` 可推導的
  `<base>/<id>.out.md`。契約 §6 第二列的傷害上界改寫。
- `rename` ENOENT 分流（另一個 poll claim vs abort／GC 已刪，兩者皆不建議 retry）；GC 對 `.done` 用 mtime／ctime 較新者；
  abort 撞上 poll 的 claim 不再誤報 `could not remove`；readiness 逾時先殺持鎖者再殺 driver；
  `--wait N` 不再超過 N；`setsid` 移除（對 group leader 依定義必失敗，存活靠 Foundation 的獨立 pgid）；
  `openOurLock` 回傳原因，不再印陳舊 errno。
- `tailOfFile`：`O_NOFOLLOW`＋一般檔案檢查＋`O_NONBLOCK`（FIFO 曾讓 poll 無限阻塞）、保留尾端位元組、剝除 bidi／Tags／BOM。
- `--_selftest-claim-age` 只對 selftest run 生效；契約 §7 補三個隱藏旗標；§2 的 exit-1 答案列舉補齊。（round 6 regression：本行原本還寫「`--help` 補 `--wait`」，在 `880785a` 上並不成立——round 7 才補，見下。）
- 測試：`Codex-R4-3` 的 `pgrep -f -- "--_worker"` 改為只數本 checkout 的 worker（曾因同機其他 codex-call 6/6 假 RED）；
  `--wait 500` 斷言改用活 id 並比對訊息；補 worker 提早退出四條 log、GC 對 untrusted 舊 run、abort 撞 prelock 的案例；
  teardown 先 `chflags -R nouchg`。detach bats 43 → 63。

### Fixed（round 6 verify：六方一致 FAIL + Devil's Advocate，修於 round 7）

round 6 的結論：round 5 六條 blocking 六條全關、`lockState` 三態成立，但**「恰好回報一次」不是一個函式能保證的**——五方都把「唯一 claim」當充分條件，它只是必要條件（DA-1）。round 7 依 DA 的封閉列舉 S1–S8：

- **S1 逾時兜底先 claim 再 kill**（RC1a：`terminate()` 曾在 claim 之外 kill＋刪＋印，兩個 poll 打同一個逾時 run **10/10 雙終態**）；kill 後**重讀 status**——逾時瞬間剛收尾的 run 以 status 為準、不再被刪輸出報 TIMEOUT（RC1c）；`removeRun` 回傳值不再丟（RC1b）。
- **S2 `resolveRun` 不再看年齡、不再刪任何東西**（RC2：無 status 的 `.done` 曾被當殘留刪掉，而 worker 還活著——abort 先 claim 但 kill 未收斂的殘局）。`.done` 內 worker 持鎖 → `RUNNING`／逾時兜底。
- **S3 接手標記改成 `.done/.claimed` 上的 fcntl 寫鎖、持到程序結束**——與 worker 鎖同一個原語，一次消掉 `lstat→unlink→O_EXCL` 的 ABA、60 s mtime lease、`touch` 偽造、接手者慢而非死被搶（RC3a）；標記完整性檢查與 errno 分流回 `.failed`，EACCES／ENOSPC 不再被說成「別人拿走了、不要 retry」（RC3b）。`CLAIM_MARKER_STALE_SECONDS`、`resolveRun` 的 ctime 門檻與 `--_selftest-claim-age` 一併移除（單一機制）。
- **S4 印任何終態之前先讓 `reported` 落地**（`rename(status, reported)`，缺 status 則 `O_EXCL` 建立；失敗則不印、exit 1、run 保留）。有 `reported` 的殘留永不重報（RC4：DONE 後清理失敗曾在 65 s 後被改報 FAILED）。**S3 與 S4 同 commit**——DA-2：fcntl 標記單獨出貨會把重報視窗從 60 s 縮成 0 s。
- **S5 `--abort` 的 stdout 只有 `ABORTED` 或空**：輸給併發 poll、run 已消失、已 `reported` → 空 stdout、exit 0（後置條件成立）；`ABORTED` 專指本次呼叫終止了它（RC6）。engine step 4 同步：非 ABORTED 的結果不是 leg 失敗也不是判決。契約 §2 改為精確表。
- **S6 CI 錨點**：macOS job 改裝 Homebrew bash 並斷言 `bash ≥ 5`（RC7：runner 的 bats 跑在 bash 3.2，63 個中文名 detach case **四個 head 從未在 CI 執行**，job 一直是紅的、PR body 卻寫「全綠」）；TAP `1..N` 必須等於執行數；verify 的 freshness gate 加「head check-runs 全綠」。
- **S7 `test/lint-bats.sh`**（零例外、含會失敗的 fixture 自測，進 `run.sh` 與兩個 CI job）：裸 `!` 斷言在 bats errexit 下是 no-op，散文規則寫了四次都復發（RC11：`R5-S3`／`R5-L8` 的 mutant 偵測率 0/10，改寫後 10/10）。三處改寫。
- **S8 誠實化**：`--help` 真的補上 `--wait`（round 5 宣稱過但沒做）；`--_selftest-gc-age` 只掃 selftest run（RC5：曾掃掉正式 run 與已交付輸出）；契約 §2 第 53／57／58／62–64 行、§4、§5、§7 逐行對齊，新增 **§8 Known limitations**（dirfd/openat、`--wait 120` vs harness timeout、`.untrusted` 回收、`O_RDWR` 探測、`did not terminate` 的第二 token 例外——DA 3.2 的付費 run 無法回收也在 Known limitations）；Tests 段不再出現「N 個先驗 RED」這類無腳本可重現的數字（RC13）。

### Fixed（round 7 verify：requirements／regression FAIL + logic／security 初稿四條新根因，修於 round 8）

round 7 的新根因全部在 `.claimed` 這個新物件上——它的生命週期（誰建、誰刪、刪的順序）沒寫成不變式：

- **`.claimed` 只由 rename 成功者建立、接手者只 open 不建立**（regression B-CRIT：A 的 `removeRun` 遞迴 unlink 先刪掉標記名，B 的 `O_CREAT` 建出**新 inode**並取得鎖 → 三路併發接手無 status 的 `.done`，`1514d40` 上 **7/150 雙 `FAILED status missing`**；契約「沒有 ABA」實測為偽——ABA 從 `claimMarker` 換到 `removeRun` 這扇門）。接手時 ENOENT → `.gone`（正在被清除或 claim 未完成），不回報。`R7-X` 的接手迴圈改三路 ×10。
- **`openTrusted` 加 `O_NONBLOCK`**（logic L-R7-1／security F-SEC-1：`mkfifo <id>.done/.claimed` 讓 GC 的 `open` 永久阻塞 → 之後每一次 `--detach` 掛死）。`R8-FIFO`。
- **`markerHeld` 只在 `F_GETLK` 明確回報持鎖者時才算持有**（logic L-R7-2／security F-SEC-2：目錄／symlink／`chmod 000` 的標記曾讓 `.done` 永遠不被 GC）；完整性失敗的標記對 poll／abort 仍是 `.failed` exit 1。`R8-RC3b`（regression 的 CE mutant：errno 摺成 `takenByOther` 讓 abort exit 0 而 worker 仍活）、`R8-GC2`（GC2 mutant）——**這兩個是護欄型：在 `1514d40` 上就綠**，鑑別力在對應 mutant 上，不宣稱能區分修法前後；在 `1514d40` 上為紅的是 `R7-X`（三路 ×十輪，重現 B-CRIT）與 `R8-FIFO`（detach 掛住，SIGALRM 142）。
- **CI 的兩個環境相依斷言**（第一次真的在 CI 執行就照出來）：`Codex-R4-3` prelock 90／上界 60；`R5-S5` 以 `perl -e 'alarm'` 取代 macOS runner 沒有的 `timeout`（round 7 得到 127 被讀成「不是 2」）。
- 誠實化：契約第 63 行「stdout 只有兩種」與自己的表矛盾（改為三種）；四處封閉列舉補「不得類推」；重複的 `## 8.` → `## 9.`；§9 補 rename→建立標記之間崩潰的洩漏、標記完整性失敗、`reported`→print 視窗、`FAILED worker did not terminate` 之後的第二 token 實測是 `FAILED status missing`；`reported`／`.claimed` 的同 uid 偽造面揭露；case 數改由 grep 產生。
- 兩個 mutant 判為等價、不補測試並在此宣告：S1 逾時兜底「只 rename 不取標記鎖」（S4 的 `reported` 已保證至多印一次，S1 留著是為性質 (3) 的對稱）；S2 detach readiness 清理不 claim（id 尚未印出，沒有第二個 caller 能撞到）。

### Fixed（round 8 verify：FAIL + Devil's Advocate 裁決「有條件換設計」，Stage A 修於 round 9）

round 8 的 CI **首度全綠**（TAP plan 86 == executed 86、bash 5.3.15）、round 7 的五條 blocking **全部關閉**（B-CRIT 儀器化 0/150，round 7 是 7/150）。但三個 lens 獨立收斂到同一格：**`<id>.done` 存在、`.claimed` 不存在**。DA 裁決連續三輪（6→7→8）的根因是同一個結構特徵——「名字 ＋ 事後建立的檔案」是兩個不可組合的系統呼叫——**有條件換設計，但先做兩條與設計無關的修法，且必須在舊設計上就綠**。本節是那兩條（Stage A）：

- **A1 止血與回報分離**（round 8 L-R8-1 實測）：`--abort` 先問 worker 鎖、該殺就殺，**不再被 claim 協定擋住**；claim 只決定誰回報終態、誰刪 run。round 8 把兩者綁在一起的後果是：一個標記從未建成的 `.done`，`--abort` 回 **exit 0**（契約說那代表「不會再跑、不會再花錢」）**而 worker 仍在跑，且此後沒有任何命令能終止它**。同時把 `.gone` 拆成兩列：真的消失 → exit 0 靜默；**claim 不可得但 run 還在磁碟上 → exit 1，明說「worker 已終止、清理沒做成」**——後置條件只成立一半就不得用 exit 0 宣稱全部成立。`R9-A1`／`R9-A1b`。
- **A2 `markerHeld` → `markerState` 三答案**（round 8 DA §3 實測）：`held`／`unheld`／`untrusted`，GC 對 `untrusted` **不刪、記錄一行**。round 8 的 `Bool` 把「不可判定」摺成「沒鎖」，方向正好是本專案自己 R4-S1 紀律點名的那個：同 uid 對標記 `ln` 一個 hard link 就讓 GC 印「claimer died first」並掃掉一個 **claimer 全程存活**的 `.done`；**非對抗入口**是 `F_GETLK` 在 NFS／SMB 的 `$HOME` 上失敗，不需要攻擊者。代價（這種 `.done` 需人工清理）寫進契約 §9——round 7 L-R7-2 的原始問題是「沒有回收路徑」，用「不可判定就刪」去修它是錯的方向。`R9-A2`（hard link／目錄／`chmod 000` 三變體）。
- **`R8-FIFO` 的斷言隨語意一起改（明講，不靜默）**：它原本斷言 FIFO 標記的 `.done` **會被 GC 掃掉**——那是 round 8 的決定，方向與 R4-S1 相反。A2 之後它斷言 `.done` **存活**且 stderr 有拒掃的理由；案例的原始價值（`O_NONBLOCK`：detach 與 poll 都不掛住）原封不動。改測試去配合新行為需要理由才不算移動球門，理由就是上一條。
- 測試護欄：`no_worker_for <id>`（run-id 級的孤兒斷言；`own_workers` 是 checkout 級，一個案例的孤兒會污染後面每一個案例——round 5 F-3 把 scope 從機器全域縮到 checkout，這裡再縮一級）；`bats_require_minimum_version 1.5.0`。

**Stage B — 換設計（round 8 DA §1.7 三個前置條件已滿足：Stage A 在舊設計上綠、建立順序寫進契約、明寫消不掉什麼）**

連續三輪（6→7→8）每一輪的修法製造下一輪的根因，全部在同一個 claim 協定裡；DA 判定共同的結構特徵是**「一個名字 ＋ 一個事後才建立的檔案」是兩個不可組合的系統呼叫**。Stage B 刪掉那個特徵本身：

- **`claim` 檔由 `--detach` 與 run 一起建立**（`lock` 也是），在 spawn worker 之前、印出 id 之前。**任何 caller 都不建立它**（`open` 不帶 `O_CREAT`）：輸掉是 `EAGAIN` 不是第二個 inode，「檔案不在」是「run 正在被清除」不是「輪到我建」。
- **取消 `rename(<id>, <id>.done)` claim、取消 `.done` 這個名字、取消接手（adoption）分支**。接手不再是特例，就是「拿得到鎖」——claimer 崩潰 → kernel 釋放鎖 → 下一個 caller 直接拿到。連帶消失的還有：第二個目錄名、年齡門檻、`ctime`／`mtime` 兩個時鐘（`R5-L6` 因此刪除，教訓移入 `gcStaleRuns` 的 doc-comment）。
- **claim 檔不在但 run 目錄還在 ＝ `.failed`，不是 `gone`**（round 8 R8-A：一個帶著已付費結果、還躺在磁碟上的 run 曾被說成「gone — 不要 retry」）。這一格在新設計上只剩同 uid `rm <id>/claim` 一條入口，**它沒有消失**，寫進契約 §9——不把「結構上不存在」講成假話（DA 條件 3）。
- **附帶收益（DA §1.6 指出、`R9-B7` 守）**：取消 rename 之後 run 目錄名終生不變，worker 手上的路徑字串永遠有效，契約 §9 原本第一項「rename 之後才收尾的 run 被誤報 TIMEOUT」**結構上關閉**，不需要 dirfd／`openat` 重構。
- **對外契約一個旗標都沒動**：`--detach`／`--poll`／`--abort` 的旗標名、stdout token、exit code、id 格式、base 路徑與 round 8 逐字相同；engine（`*.js`／`*.mjs`）與兩份 SKILL.md 零改動。run 目錄的內部布局從來不是 §8 的 STABLE 面——**因此不需要 major bump**（DA 特別要求寫明：否則「換 claim 協定」最可能死於「破壞相容性」的誤讀）。
- **被刪機制的失敗史不得淨損失**（DA 遷移完整性）：round 5 的第三種目錄名、round 6 的 `O_EXCL`＋60 s lease、round 7–8 的 rename＋marker ABA 與它造成的黑洞，全部保留在 `ClaimResult` 的 WHY NOT doc-comment 與契約 §2「為什麼不是前三種設計」。
- **三條 wall-clock 餘裕斷言改成錨定事實**（`R7-M05`／`R9-B7` 錨在「claim 鎖已被持有」，用唯讀 `F_GETLK` 查詢、不自己取鎖以免跟被測的 caller 搶；`R5-L9` 的上界改成自校準——先量這台機器此刻的 swift 啟動成本再加 N）。它們在單獨跑時綠、跟整套一起跑時紅：量到的是「啟動＋行為」而不是行為。這與 round 8 CI 首度真的執行套件後照出的兩條（`Codex-R4-3`、`R5-S5`）是同一類。
- 新驗收案例：`R9-B3`（claim 開不起來的四種變體，`--poll` 一律不得說 gone、已付費結果原地保留）、`R9-B5`（建立順序）、`R9-B6`（claim inode 全程不變 ＋ 靜態：用到 `CLAIM_FILE` 的 open 零個帶 `O_CREAT`）、`R9-B7`（不再誤報 TIMEOUT）。既有 21 個引用 `.done`／`.claimed` 的案例全部遷移，`R5-L6` 明確刪除並說明。

**Stage C — 誠實化**

- 契約 §2 末新增**狀態叉積表**（5 種 run 狀態 × 6 種 caller 配對，每格填 stdout token 與 exit code，**不留空格**；不可達要寫理由）。放契約而不是 CHANGELOG 或 PR 留言，理由是 DA 第五題：**round 8 的兩條 blocking 正好落在 round 7 那張表沒有的格子裡**，表在契約裡，下一輪逐格驗證才會撞上空白。
- 契約 §6 的傷害上界句改成**封閉列舉五項**（同一句話已兩次為假：round 5 修了刪除面、round 8 DA 實測回報面仍在——改寫 `meta.json` 的 `output` 可讓 `--poll` 印出攻擊者選定的路徑，直接餵進 prompt-injection 鏈的下游）。
- §9 的「上列五項」改成可數的「上列各項」（實際 10 條，round 8 DA §4.3）。

### Removed

- `bin/pai-codex-review` 與 `test/pai-codex-review.bats`（從未進 main）。

### Tests

- 新增 `test/codex-call-detach.bats`（macOS job，**95 個 case**（`grep -c "^@test" test/codex-call-detach.bats`）；round 3 後 12 → 31，round 4 後 → 43，round 5 後 → 63，round 7 後 → 70，round 8 後 → 73，round 9 Stage A 後 → 76，Stage B／C 後 → 79，round 10 後 → 91（+12 `R10-*`），round 11 後 → 95（+4 `R11-*`）——**這個數字自 round 10 起由 `test/lint-changelog-counts.sh` 對照括號內那條命令的實際輸出（run.sh 與 CI 都跑）**；round 9 verify 抓到本行在宣稱「由 grep 產生、不手打」的同一句裡寫 76、實際 79，RC13 第五度復發，散文規則已證明無效：+8 `R7-*`（含 `R7-X` 狀態叉積補格）、+3 `R8-*`、+3 `R9-A*`、−1 `Codex-R4-1`（年齡判準已不存在）、5 個改寫。round 7 verify 抓到本行曾寫 69／+7——`R7-X` 加在段落寫完之後，數字沒跟上：RC13 第四度，所以 round 8 起 case 數由 `grep -c "^@test" test/codex-call-detach.bats` 產生、不手打）。
  走**同一條** detach／lock／poll／abort 路徑，只以 `--_selftest-*` 把 HTTP 換成 sleep + 寫檔。
  **round 7 的 RED-first 證據以名稱列出、原始輸出貼在 PR #47 的 round 7 留言**（round 6 regression 實測 round 5 寫在這裡的「13 個先驗 RED／7 個護欄型」名單有 4 個成員是錯的，而且沒有腳本能重現那些數字——所以不再寫數字）：
  在 `880785a` 上為 RED 的案例：`R7-A`（雙逾時 poll ×10）、`R7-D`（`.done` 內活 worker）、`R7-R`（reported 痕跡）、`R7-M05`（kill 等待中 lock 變不可信；含新 hook `--_selftest-ignore-term`，RED 一部分來自旗標不存在）、`R7-RC1c`（逾時瞬間 status 已落地）、`R7-GC`（GC hook 只掃 selftest run）、`R7-S5`（abort 輸家 stdout 空）、`R7-X`（狀態叉積補格：poll×abort 逾時、abort×abort、接手×接手無 status）、`R3-L10/R7`、`R4-L3/R7`、`R5-L2`（拿掉 hook 後）、`R5-S6/R7`。
  `R5-S3`、`R5-L8` 的改寫是護欄（裸 `!` → `run cmd; [ "$status" -ne 0 ]`），修法前後皆綠，其鑑別力由 round 6 regression 的 mutant 量得（0/10 → 10/10）。
- 新增 `test/lint-bats.sh` + `test/fixtures/lint-bats-bad.bats`：裸 `!` 斷言的機械護欄，先自測（fixture 必須被拒）再掃套件。
- `test/ensemble-workflow.test.mjs` 改為新契約（**31 個**；round 7 +1：`--abort` 的空 stdout／非零退出不是判決）；補 `--instructions` 與 wrapper 路徑的
  `shQuote()` 正向斷言（round 2 指出零覆蓋）。

### Known limitations（誠實邊界）

- **codex-pro 的 vendored 快照仍是 2.22.1 之前的 `codex-call`**，須在該 repo 另行 re-vendor
  （其 openspec spec 規定 byte-for-byte snapshot；觸及 `provenance.json` ×3、`THIRD_PARTY_NOTICES` ×2、
  `tests/codex-runtime.sh` pinned 值、`codex-pro-call` 的 `EXPECTED_SHA256`）。
- 威脅模型是封閉列舉的三列（同 uid／caller 環境完整性／跨 uid）：同 uid 與 `HOME` 注入在模型之外；lock 完整性與 base 硬化把「寫得到 base」的傷害縮到「殺自己的 worker」，但不把它們宣稱為提權防禦。
- Claude lens 的同類 stall（#44）、目錄型 artifact（#45）、`xhigh` 治理（#43）、
  `response.completed` 的 tier／usage 可觀測性——皆不在本版。**issue #37 Expected 第 3 點（leg 被放棄時回報已花成本）
  依賴後者，明確延後至該獨立 issue**；本版 leg 缺席時的 integrity finding 只標記缺席、不含 token 數（round 5 D-1）。
- Swift script 每次啟動約 1.5–2.5 s（compile cache）；poll 是分開 tool call、間隔數十秒，屬雜訊——但 bats 內任何「未逾時應回 RUNNING」的斷言必須把這個啟動時間算進 `max-time + grace` 的餘裕（round 7 R7-D 實測 3 s 的 deadline 會被啟動時間吃掉）。
- round 7 明確排除的五項見契約 §9（round 10 之前這裡寫 §8——§8 是穩定性承諾）：worker 以路徑字串寫 status（dirfd/`openat` 未做）、`--wait 120` 與 harness timeout、`.untrusted` run 無回收、`O_RDWR` 探測、`FAILED worker did not terminate` 後的第二 token。DA 3.2：被硬殺的 agent 留下的付費 run 沒有 `--list`，只能等 24 h GC。
### Fixed（round 10 verify：FAIL 但收斂——六個 blocking 族全是文件層＋三個一行／三行 code 改動；round 11 依 DA 封閉列舉七項，**唯一的新機制是一個 lint**）

round 10 verify（4 lens，requirements／security 各兩個盲驗實例，＋ DA ＋ **round 7 以來首次有額度的 Codex**）判 FAIL：round 9 的 blocking 是行為的，round 10 剩下的是契約文字＋三個小改動——但**同型的手打封閉列舉缺陷在同一輪契約裡復發四次**（force-reap stdout 少一種 token、exit-1 少一個答案、§6 lead-in「五項」句尾「六項」、abort 表「十一列」實有十二列），而 round 10 剛把同一個教訓機械化到 CHANGELOG 卻沒推到契約。round 11 做的是 DA 的七項：

- **R11-1 `test/lint-contract-enumerations.sh`**（本輪唯一的新東西）：五項檢查——(A) `doPoll`／`doAbort`／`doForceReap` 每個 `print` 字面 token 必須出現在契約**對應小節**（全域出現不算：round 10 的漏項正是「abort 表有、force-reap 節沒有」）；(B) exit-1 答案雙向——§2 列舉的每個反引號片語（`…`／`<path>` 當萬用）要對得到 code 的 die 字串，反過來五個入口函式的每個 `die` 要對得到契約（§2 ∪ abort 表 ∪ force-reap 節）的某個反引號答案；(C) abort 表資料列數 = 「上表封閉（N 列）」；(D) §6 `(n)` 項數 = lead-in = 句尾；(E) `R10-B5s` 三個 grep pattern 各唯一。`--selftest` 對五個 fixture（四個壞契約＋一個雙 spawn 的壞 code）各自拒絕、對真契約接受；接進 `run.sh` 與 CI（bats 之前）。對修前契約 RED 7 處（A／B×4／C／D）。**lint 自己也被抓到一次假綠**：force-reap 的 print 改成三元式後，anchored 在 `print("` 的 regex 什麼都沒抽到就通過——改成掃 `print(` 括號內全部字串字面。
- **R11-2 契約文字一批**（全部有 round 10 findings 編號可追）：force-reap 的 stdout／exit-1 封閉列舉補齊（含 `FAILED could not remove run dir <dir>; output kept at <path>`、`cannot enumerate processes (ps failed)`）並把 `REAPED` 改寫成**後置條件**、身分句改成「`ps -o args=` 文字含相鄰兩 token，不是 argv 邊界檢查」（B6；不做 KERN_PROCARGS2）；abort 表補兩列（`.gone`／`.failed` × 無法確認 worker 停止）並改成十四列、第 11 列與 §2 exit-1 列舉補三個 `could not confirm` 答案；§2 性質 (3) 的例外改為「恰好兩個」（GC 與 `--force-reap`，B3a）；§2:53 與 §5 的 abort exit 碼改 0（B3b/c）；「stderr 無任何行」×3 改成「stdout 無 token、stderr 一行」（B2a）；§6 lead-in 改六項、item (1) 的 `rename` 歸因改到 (6)、(5) 擴到 `prompt.txt`／`instructions`（S10-4，#54）、(6) 機制補 `rename`；§7 `--_selftest-ignore-term` 改成實況；§9 補「到 `FAILED worker did not terminate` 的第二條路」（B2c）、2 s 重查的 lstat fold（F6）、`.done` 殘留與封閉句後的多餘項搬回；`--wait` 一句寫清楚「不超過 N」指等待迴圈（F2）；叉積表補 force-reap 說明與 live-expired 格的 L9-1 例外（F8）。
- **R11-3 一行修 B5**：`if unterminated || !killHolderConverged(dir)` → `if !killHolderConverged(dir)`——claim 之後的探測是真相，記憶的值只決定 exit-1 的措辭。**誠實邊界**：DA 描述的分歧情境（第一輪沒收斂、claim 取得前 worker 退出）**黑箱不可構造**——第一輪回 false 只有 lock 不可判定一途，而 kill 輪結束到 claimRun 之間只有微秒，沒有讓 lock 從不可判定翻回已釋放的窗口；round 10 Logic 之所以量到「成功的 run 被印成 FAILED」是因為 B4 的 bug 讓 worker 提早退出。所以本輪**沒有** `R11-ABORT-LATE` 這個 case，改以 `R11-ABORT-MSG` 守同一分支可觀測的性質（見下），並在此明寫這條修法沒有黑箱測試。
- **R11-4 修 B4（測試鉤子回歸）**：`--_selftest-ignore-term` 的 handler 觸發後 `sleep()` 被 EINTR 提早返回、worker 0 秒內結束——4/91 個 case（`R7-M05`／`R9-B7`／`R10-L9-1`／`1b`）綠的理由靜默變了。改成 deadline 迴圈 `while remaining > 0 { remaining = sleep(remaining) }`（三行、無新旗標、同時保住存活與 `term-seen` 錨點）；handler 的 `open` 加 `O_NOFOLLOW`（全檔唯一沒帶的，S10-5 實測 symlink 目標被建出）；路徑在安裝前 `strdup` 成 C 字串，handler 不碰 Swift String（round 10 的「async-signal-safe」註解對一半）。新增 **`R11-HOOK`** 斷言這個前提本身（SIGTERM 後 3 s 仍活、無 status）——它從來沒被任何測試斷言過，所以才會靜默壞掉。
- **R11-5 force-reap 清理失敗仍取得回輸出**：`removeRun` 失敗時 token 帶上 `<id>.out.md` 路徑（`FAILED could not remove run dir <dir>; output kept at <path>`，exit 2）；新增 **`R11-FR5`**（`chmod 0500 base`）。
- **R11-6 收緊 `R10-REG-A2`**：背景拆除者記下刪除時刻，若刪除發生在 poll 已過啟動之後就**只接受** `gone`，不再讓修前也會出現的 `unknown run id` 靜默過關（L-R10-11）。
- **訊息誠實化（L-R10-2）**：`--abort` 兩輪訊號後 `killHolderConverged` 回 false 有兩個成因（持鎖者沒死／lock 變不可判定），round 10 的訊息只講前者、宣稱「the run is still spending」——在測試自己造的情境裡就是假話。三個 exit-1 分支與 stderr 全改成「could not confirm the worker stopped」；新增 **`R11-ABORT-MSG`**。
- **R11-7**：Expected 第 3 點（abandoned leg 回報成本）已立案 **#52**，#37 body 記錄移交；`?? left` 的取捨立 **#53**；§6 (5) 的配額竊取面立 **#54**（本輪已順手擴寫，#54 核對後關）。
- 2.23.0 的日期改為實際發布輪（原本停在 round 3 的 09-03，排在 2.22.2 的 09-09 之上）；round 7 排除項的章節引用 §8 → §9。

**明確不做**（DA 封閉列舉）：KERN_PROCARGS2（換設計）；改 `lockState` 的 ENOENT 語意（S9-1 根因，已揭露）；第四種 claim 協定；`?? left` 改 fail-closed（#53）；SIGKILL 升級輪第二個旗標（R11-4 後 `R7-M05`／`R9-B7` 自然重新走到）；動 §6 三列；實測 `.gone × unterminated`（表內標「靜態可達、未實測」）。

**Merge 判準（round 10 DA）**：round 11 之後只需 targeted verify（R11-1 lint 含 selftest、`R11-HOOK`／`R11-ABORT-MSG`／`R11-FR5`、12 個 `R10-*`、CI 兩 job），不再召集四 lens＋DA。若 R11-1 綠而事後仍見同型缺陷，那才是重新召集全員的訊號。

### Fixed（round 9 verify：FAIL——round 8 DA 的收斂判準成立，round 10 依封閉列舉六項**接受並揭露，不換設計**）

round 9 出現三條修法自帶的新根因（R9-REG-A／S9-2／L9-1），判準原文：「不做第三次換設計，改為接受並揭露（寫進 §9 封閉列舉、叉積表標『不保證』、給一條逃生命令），然後 merge」。round 10 只做那六項：

- **R9-REG-A（訊息三句假話）**：`claimRun` 對「claim 檔 ENOENT、run 目錄還在」的訊息說「不是本工具刪的／沒有別的 poll／retry 沒用」——而最常見的入口是**本工具自己的併發拆除**（`removeRun` 遞迴 unlink 先刪 claim、最後才 rmdir；round 9 實測 13/150 = 8.7 %，無攻擊者）。現在先做 **2 s 有界重查**：目錄消失 → `gone`；仍在才回 `cannot claim … still on disk`，訊息指向契約 §9 與 `--force-reap`。`R10-REG-A`（訊息）、`R10-REG-A2`（拆除視窗，自校準排程）。
- **L9-1（abort 的 `FAILED worker did not terminate` 逃出 claim）**：round 9 A1 把止血搬到 claim 之前時順帶把這個 stdout token 搬了出去，兩個併發 abort 會各印一次。現在 kill 是否收斂先記住、claim 之後才印；claim 被別人持有 → stdout 空、**exit 1**（worker 還活著，後置條件沒成立，不得用輸家的 exit 0）；claim 不可得／run 已消失 → exit 1 並說明。`R10-L9-1`／`R10-L9-1b`（錨點：selftest worker 在 `--_selftest-ignore-term` 下收到 SIGTERM 會 touch `<run>/term-seen`，測試等它再讓 lock 在 grace 視窗內變不可判定——取代賭啟動時間）。
- **R9-REG-B／C（契約自相矛盾）**：叉積表「claim 被第三方持有」欄四格對 `--abort` 寫 exit 1、實測 0 → 改成 poll／abort 分寫；`--abort` 第一條 bullet 寫的 `claimTerminal` 在程式碼裡不存在、順序也已被 A1 反轉 → 改為描述現行順序。`R10-C`。
- **S9-3（GC 捏造一個死掉的 claimer）**：對「有 status、無 reported、無人持 claim」的 run，GC 印「its claimer died first」——Stage B 之後那最常是「跑完沒被 poll」，兩者已分不出來。訊息改為只說已知的事。`R10-S9-3`。
- **逃生命令 `--force-reap <id>`**（round 8 DA 預先授權；契約 §2 新小節）：「我知道我在繞過 claim 協定」。**完全不信任 lock**——以 `ps` 找同 uid 且 argv 含相鄰 `--_worker <id>` 的程序（CSPRNG id 撞不到、植不進 victim），SIGTERM → SIGKILL；**永不**對 `F_GETLK` 回報的 pid 送訊號（`rename` 進來的 victim lock 會過全部檢查，逃生口不得變成殺 victim 的原語）；不取 claim、不落地 `reported`，直接清 run；`<base>/<id>.out.md` 存在則印 `REAPED <path>` 並保留給 caller，否則印 `REAPED`；S9-1 之後目錄已被刪的孤兒只靠 argv 找——「沒目錄且沒程序」才是 `unknown run id`。engine 的 prompt **不得**自動使用它。`R10-FR1`（S9-2 重現＋逃生）、`R10-FR2`（取回結果）、`R10-FR3`（驗證與互斥、不發訊號）、`R10-FR4`（繞過被持有的 claim）。
- **揭露**：契約 §6 補第六項（讓工具對活 worker 印終態並刪 run／讓 `--abort` 永久無法止血）、§9 補 R9-REG-A 的非對抗入口與 S9-1／S9-2（各自寫明**為什麼不修**）、叉積表加「不保證的格子」段。
- **把契約補到真的（Stage C 沒做完的部分）**：§3 run 目錄列舉補 `claim`／`reported`、去掉 `.done`；§4 GC 依 mtime 單一時鐘、`.claimed` → `claim`；§5 整段從「`.done` 中繼目錄／接手」改成「finalize 所有權＝拿到 `<id>/claim` 的鎖」；§8 把 `--force-reap` 納入 STABLE。`R10-C` 靜態守：契約無 `claimTerminal`，§3–§5 提到舊名字的行必須同時說它已移除。
- **RC13 機械化**：新增 `test/lint-changelog-counts.sh`（＋ `--selftest` 與 fixture），對 CHANGELOG 每一個「N 個 case（`grep -c "^@test" <file>`）」宣稱實際跑那條命令比對；接進 `test/run.sh` 與 CI。`R10-RC13`。
- **R9-B5 補牙**：動態半（`--_selftest-prelock-sleep 6`）對 mutant「建立搬到 `p.run()` 之後」5/5 全綠——swift 啟動 1.5 s 遠慢於檔案建立，順序從外部觀察不到。加靜態半 `R10-B5s`：建立行號 < `try p.run()` 行號 < `print(id)` 行號；本輪實際做了 mutant，動態半 3/3 綠、靜態半紅，還原後綠。

**誠實邊界（round 10 明確不做）**：S9-1／S9-2 本身不修——在「寫得到 base」的前提下沒有任何檢查能區分「我們建的 lock」與「別人放的一般檔」（§4 早已寫明），修法只會是第四種設計；R9-REG-A 的 2 s 重查分不出「正在拆除」與「被 `rm`」（前者慢過 2 s 幾乎不可能、後者白等 2 s）；`--force-reap` 的身分來源是 `ps` 的 argv，同 uid 可偽造——它本來就在 §6 第一列之外。

## [2.22.2] - 2026-09-09

### Added

- repo root `.codex-pro/profile.yaml`：專案層 codex-pro profile，把 ensemble codex leg pin 到 `gpt-6-astra` / effort `medium`（service tier `fast` 為既有現況）。走 codex-pro 契約三層解析的 project 層，engine / codex-call 零改動；`test/codex-profile.bats` 用 `references/codex-governance.md` 同組正規式鎖住解析後的字面、重複 key、git 追蹤狀態，並以 fixture 斷言三層優先序（不依賴 codex-pro cache）。**作用半徑**：本檔不隨 plugin 散發；契約的 project 層是 cwd 相對，只在 repo root 當 cwd 執行 ensemble 時生效（codex-pro#19）。本機另有同值的全域 `~/.codex-pro/profile.yaml`，只有本檔可攜。**退場**：codex-pro baseline 換代（PsychQuant/codex-pro#17）後，先確認移除後解析值仍符合，再連同 `test/codex-profile.bats` 一起刪（#49 認領）（#48）。

### Changed

- `references/codex-governance.md` 解析片段：defaults.json 路徑改以 argv 交給 python（不再內插進程式碼字串）；解析後對 `model` / `effort` 做形狀驗證（`[A-Za-z0-9._-]`），不合即 fail-fast——這兩個值會進 engine 的 shell 命令列，而 profile.yaml 是 repo 內可改的檔案（#48 verify findings #1 / #11）。
- `skills/ensemble-code-review/SKILL.md` legacy Backend B 的 codex 呼叫改用解析出的 `"$CODEX_EFFORT"`，不再寫死 `xhigh`；Workflow 不可用的 session 走的正是這條（#48 verify finding #9）。

### Fixed

- `.gitignore` 加 `.codex-pro/*` + `!.codex-pro/profile.yaml`：codex-pro producer 的結果檔不再被 `pai-build-diff --diff` 當 untracked 新檔餵進下一輪 ensemble（#48 verify finding #6）。

## [2.22.1] - 2026-09-01

### Fixed

- **Codex leg 不再讓 artifact 兩次經過 agent context，並改為背景執行 + 輪詢（#37）。**
  cross-model leg 曾連續 4 次 ensemble run 沒完成，失敗全部來自 runtime 的 stall
  detector（非 API error）：單次嘗試燒 976k token、145 次 tool call、72 分鐘才被殺，
  再從零重試五次。成因有兩條獨立路徑：

  1. `codexPrompt()` 要 agent 先「讀」 artifact、再把它「寫」回暫存檔 —— 同一份 bytes
     兩次過 context。逼它這樣做的是注入禁令措辭過寬：它連**只傳 path** 的 `cat` 串接也
     一起禁掉，而 `bin/codex-call` 本來就支援 `--prompt-file`。現在改成
     `cat "$INSTR_FILE" "$ARTIFACT_FILE" > "$PROMPT_FILE"`，artifact 零次進 agent context。
  2. `codex-call` 是最長 600 s 的**阻塞**呼叫，期間零 tool call。600 > 180 ⇒ 與 context
     大小無關，結構上保證觸發 detector。現在改為背景啟動 + 以**分開的 tool call** 輪詢，
     每次輪詢本身就是 progress 事件。

  **注意這不是把安全規則放寬**：禁令沿 path/content 軸重寫 —— 傳 path 當參數安全
  （bytes 不會變成 shell token），把 content 內插進命令（`echo` / `printf` / heredoc）
  仍然禁止。`test/ensemble-workflow.test.mjs` 新增 6 個斷言，其中 T3 是這條規則的回歸護欄、
  T4 守住 Claude lens 仍必須讀 artifact（不被過度編輯波及）。

### Known limitations

- 本修法**不會讓 Codex 變快**，它消除的是「重試五次」的乘數與 token 膨脹。實測極短 prompt
  的往返 `xhigh` 約 4 s、`medium` 約 3 s —— 基礎延遲不是瓶頸，輸入量才是。
- **Claude lens agent 的同類 stall 未解**（#44）：它們必須把 artifact 讀進 context 才能審，
  沒有 file-only 旁路。
- **目錄型 artifact 仍走舊的 read-based 路徑**（#45）：需先決定排除規則／順序／大小上限。
- runtime 的 stall threshold 與 retry-from-zero 策略不在本 repo 控制範圍（#37 的 Residue）。

## [2.22.0] - 2026-08-04

### Added

- `minutes` profile：會議記錄的 ensemble 審閱，四個 lens 互為補集。
  `fidelity`（記錄寫的逐字稿有嗎、推論有無被寫成會中決定、有無誤讀原話）與
  `completeness`（逐字稿有的記錄漏了嗎、不利內容有無消失）一正一反，缺一不可；
  `attribution` 查發言與責任歸屬的依據（語者分離常不可靠，未確認即具名是嚴重問題）；
  `cross-document` 比對來函、開會通知、前次記錄，並檢查交叉參照是否指對位置。
  DA 盯三種安靜的偏移：個別發言寫成全體共識、條件句寫成確定句、會後才知道的事寫得像會中已知。
- `ensemble-minutes-review` skill：載明與 `sinica-admin:meeting-minutes` 的分工
  （機械檢查歸 compile.sh、事實核對歸本 skill），以及無逐字稿時應拒絕執行而非降級。

### Fixed

- 文件補上兩個實測陷阱：`args` 傳字串時 `profile` 解析為 `undefined`、0 個 agent 被派出
  而 workflow 仍「成功」結束（僅在 findings 留一條 harness HIGH）；`agentModel` 不指定時
  agent 繼承 session main-loop model，高階 session 單輪曾燒 56-109 萬 token 並撞死 lens agent。


## [2.21.0] - 2026-08-01

### Added

- **三層 lens 疊加：built-in → lens pack → user (#29)** — lens 集合不再只能來自 harness 的 `PROFILES`。`pai-lenses` plugin 的 `lenses/<profile>.csv`（層 ②）與 `~/.claude/pai-lenses/<profile>.csv`（層 ③）會自動疊上來。新增一條 lens 的成本從「改 JS + bump plugin + 同步 marketplace」降為「改 CSV + bump lens pack」；外部貢獻的**出口成本**同步下降 —— 收一條 lens 不再等於發一次 plugin release。設計見 `docs/superpowers/specs/2026-07-29-lens-pack-externalization-design.md`（D1–D8），契約見 `references/lens-layers.md`。
- **`bin/pai-collect-lens-layers`** — 層 ②③ 的蒐集器（跨 marketplace semver glob 定位 lens pack、委派 `pai-parse-lens-csv` 解析、依序串接）。四個 ensemble skill 共用同一個入口。
- **`stats.lensProvenance`** — harness 回報每個 lens 的處置（`added` / `overridden` / `ignored` + `overrodeFrom`），供報表的 provenance 行使用。
- **報表新增 provenance 行** — 列出各層來源與版本、哪些 lens 被覆蓋。**沒裝 lens pack 時也會印**：量測儀器換了刻度卻不說，是 eval 偵測率數字前後不可比的根源。
- **CSV 新增可選欄 `override`** — truthy（`1`/`true`/`yes`）時取代同 key 的既有 lens。語意是「我要取代那一條」，不是「我比較重要」。
- **CI 新增 `builtin-lenses.csv` drift 檢查** — 跑 regen 後 `git diff --exit-code`。catalog 過期是文件缺陷（它不驅動 runtime），但會把想貢獻 lens 的人指向錯的檔案。

### Changed

- **harness 的 lens 去重從純 first-wins 改為 override-aware** — 撞名時後來者只有標了 `override` 才勝出，且是**原位取代**（devil's-advocate 依 lens 順序讀 reviewer 完稿，移位會讓它看到的東西因與 override 無關的理由改變）。**未標記的行為與 2.20.1 逐位元相同**，向後相容鎖有專屬測試。
- **`references/builtin-lenses.csv` 檔頭標明唯讀** 並指向 lens pack。註解列刻意放在 header **之後** —— 放前面會被 `csv.DictReader` 當成 header，整份檔案解析成空。

### Known limitations

- **`profile.title` 沒有 `args` 覆寫路徑** —— 這是為何三個 profile skill 的 `profile` 必須維持原值而非改傳 `"custom"`（改了會讓每次審閱對所有 agent 自稱「自訂 ensemble」）。目前無驅動案例要求可覆寫。
- **專案級 lens（第四層 `.claude/pai-lenses/`）未實作** —— 折疊形式已使增層只需延長來源序列，但無需求驅動（spec §11 明確排除）。
- **多個 lens pack 並存的優先序未定義** —— 本版假設單一 pack；`pai-collect-lens-layers` 取 semver 最高者。

## [2.20.1] - 2026-07-31

### Fixed

- **`bin/codex-call` 吞掉 SSE `error` 事件的訊息 (#25)** — 後端在 HTTP 200 stream 內以 `{"type":"error","error":{...,"message":...}}` 回報時（實測觸發：`server_is_overloaded`），原有的兩條提取路徑皆不匹配，塌成 fallback 字面值 `"Codex error"`，使該類失敗無法區分原因。抽出 `extractErrorMessage(_:)` 並補上 `json["error"]["message"]` 路徑。HTTP 4xx 類（實測 model 400 / auth 401 / rate-limit 429）走既有 HTTP 錯誤路徑、本來就正確報告，不受影響。

### Changed

- **後端錯誤訊息現在會被淨化並設上限（使用者可見的行為改變）** — 新增 `sanitizeBackendText`：剝除 C0/DEL/C1 控制字元（保留 newline 與 tab），並以 **UTF-8 byte（2000）+ 行數（20）** 為預算截斷，超出時附加 `…(truncated)`。
  預算刻意**不用** `String.count` —— 它數的是 extended grapheme cluster，長度無上限（一個基底字元加 N 個組合記號是**一個** Character），因此 Character-based cap 實際上不約束任何東西。實測前一版：500 個 CJK 字元以 1,500 bytes 通過、500 個各含 20 個組合記號的 cluster 以 20,500 bytes 通過，兩者皆無截斷標記。TTY 版面與 agent context 都是以 byte／行計價，故以此為準。

### Added

- **`--selftest-error-extract <json>` hidden flag** — 餵一則 SSE 事件 payload 給 `extractErrorMessage` 並印出結果，不發 HTTP、不列於 `--help`。`CODEX_URL` 是 hardcoded 常數、無注入點，沒有這個 hook 該提取邏輯結構上無法自動化回歸。
- **`test/codex-call-error-extract.bats`** — **13 case**：提取路徑 5 個（含實測 payload 作 regression 錨點）+ sanitize／budget 8 個。後者以 mutation 驗證有分辨力（換回 grapheme cap → 組合記號與行數兩個 case 轉紅；移除 newline 保留子句 → 分隔符 case 轉紅）。**測試標題須為 ASCII** —— macOS runner 的 `/bin/bash` 3.2 在 `printf '%02x'` 上做 signed-char 符號延伸，會 mangle CJK 標題導致 bats 宣告 N 個卻執行 0 個（見 CI job `macos-swift-bats`）。

### Known limitations

- **經 ensemble 使用時，本修正對使用者尚不可見（#27）** — `workflows/ensemble-workflow.js` 的 codex lens prompt 以硬編碼字串回報失敗，不帶 `codex-call` 的 stderr。本版真正改善的是**直接呼叫 `codex-call`** 的情境。
- **sanitize 尚未覆蓋的類別，與另兩個 sink（#28）** — bidi override（U+202A–U+202E、U+2066–U+2069）、Unicode Tags block、U+FEFF、U+2028/U+2029 仍會通過；同檔另外兩處後端文字（`HTTP <code>: <body>`）仍用 `String.prefix(500)`，與本版修掉的 Character-counting 缺陷相同且未被 sanitize；截斷標記為 in-band、可被後端偽造。這些需要對所有 backend-text sink 做一次整體處理，不宜再以片段修補累加。
- 分幀與終端事件語意 —— UTF-8 切在 byte 邊界導致整個 chunk 被丟棄、殘留 buffer 從不 flush、多個終端事件時的勝出政策、CRLF 分幀 —— 同樣追蹤於 **#28**，該處會先蒐集後端 teardown 的真實 trace 再定政策。
- `extractErrorMessage` 的每條路徑接受任意 String（含 `""` 及 sanitize 後變空者），故空的 top-level `message` 會遮蔽真實的巢狀值；修法需要「資訊量謂詞」而非「存在性檢查」，一併歸 #28。


## [2.20.0] - 2026-07-18

### Added

- **first-party skills 深度整合 codex-pro governance (#23)** — 五個 ensemble-* skill 的 codex leg 不再於 pai 樹內 pin model/effort，改由 codex-pro 的 EXTERNAL-CONSUMER CONTRACT（`references/profile-contract.md` + `references/defaults.json`，0.7.0+）解析；解析流程的 canonical 落在 `references/codex-governance.md`，skills 引用該檔而不內嵌分歧複本。

## [2.19.0] - 2026-07-18

### Added

- **`codexModel` / `codexEffort` engine args (#22)** — `ensemble-workflow.js` 新增這兩個 caller-governed args，讓跨模型 leg 的 model/effort 由呼叫端治理契約決定，而非引擎內部寫死。消費端（如 issue-driven-development 的 idd-verify）據此把 codex-pro 的治理值 thread 進來；引擎若靜默忽略這兩個 arg，canonical tier 的治理鏈會斷（故 consumer 端以最低版本閘門把關）。

## [2.18.0] - 2026-07-02

### Added

- **Explicit dispatch model for every ensemble agent — default `opus` (#20, mirrors issue-driven-development#205)** — `ensemble-workflow.js` resolves `AGENT_MODEL` from the new `args.agentModel` (whitelist `sonnet|opus|haiku|fable`; absent → `opus`; an explicitly invalid value throws **before any dispatch**) and passes `model: AGENT_MODEL` at all 3 `agent()` sites (lens reviewers × replicas, the codex runner, devil's-advocate); `stats.dispatchModel` + the progress log disclose what actually ran. All 5 ensemble-* skills resolve `PAI_AGENT_MODEL` (unset → `opus`, invalid → usage-error abort) and pass it as `agentModel`; legacy TeamCreate fallback backends carry the same explicit model per spawned Agent. Rationale: an unpinned dispatch inherits the session's main-loop model — on high-tier sessions that burned 563k–1,092k tokens per ensemble round and killed a lens agent at a session limit (evidence in the primary issue). Regression tests: default-opus-everywhere, override honored, invalid-throws-before-dispatch (3 new cases in `test/ensemble-workflow.test.mjs`).
- **External-consumer contract officialized (#20)** — the engine's args surface + return shape are now the documented STABLE API for dependent plugins (first consumer: `issue-driven-development`'s idd-verify, which will swap its vendored 305-line fork for resolve-installed-engine dependency per the user's direct-dependency ruling). Breaking changes require a major bump + migration note.

## [2.17.0] - 2026-06-10

### Added
- **Eval harness —— 測試金字塔最後一塊：模型判斷品質**（reviewer 偵測率 + `apply_fixes` 修稿品質）。確定性 surface 已全由 `test/` 覆蓋，唯一沒測的「模型抓不抓得到真缺陷」不適合單元測試 → 走 eval：
  - **`eval/fixtures/stats-paper/`**：合成統計論文，**故意埋 4 個缺陷**（捏造文獻 Tanaka & Whitfield 2019、錯平均 5.42 vs 4.42、錯 t 值 6.34 vs 2.79、Abstract/Method 樣本數 120 vs 102 不一致）+ ground-truth `analysis/results.csv` + `manifest.json`（match patterns / fix checks）。
  - **`bin/pai-eval-grade`**：eval 的**確定性評分器**（唯一可單元測的部分，故有單元測）。`detect` 模式 = K 次 run 容差聚合（每缺陷 hits ≥ minHits，預設過半；integrity findings 排除於命中、單獨列報）；`fix` 模式 = 修稿驗證（planted 文字消失 + corrected 值出現）。`test/pai-eval-grade.test.mjs`（11 個）。
  - **`skills/ensemble-eval/SKILL.md`**（dev 工具）：K 次真 ensemble → 存 findings → grade。鐵律：fixture 唯讀（apply-fix 只動 temp 複本）、**reviewer context 必須中性**（manifest／「eval」字眼絕不進 prompt，否則量到 prompted recall 不是 natural recall）、容差斷言、**絕不進 CI**。
  - End-to-end smoke 驗證：實跑一次真 ensemble（K=1、codex 關）對 fixture，`pai-eval-grade detect --min-hits 1` 驗證缺陷可被抓到。

## [2.16.0] - 2026-06-10

### Added
- **`bin/pai-iterate-decide` —— `--auto-iterate` 主迴圈的轉移函式抽成純狀態機**（單一真相源）。Phase 5b 那個看似「LLM 編排」的迴圈，其決策核心（halt 判定、mode 奇偶交替、`last_3_同focus_CONVERGED → focus 輪替`、pool 繞回、max-rounds clamp [1,30]）其實全是確定性邏輯 —— 抽成 JSON in/out 的 node script 後可窮舉測試。`test/pai-iterate-decide.test.mjs`（17 個）涵蓋：converged≠max-rounds 兩種 halt、**最後一輪仍套 fix 才 halt**、自訂 `--converge-on`、clamp 上下界、奇偶 mode、剛好 3 次同 focus CONVERGED 才輪替（2 次／focus 不一致／含 NEEDS_ITER 都不輪替）、pool 繞回、自訂 focus 落 pool[0]、自訂 focusPool、非法 round/JSON → exit 2。
- **`bin/pai-iter-commit` —— per-round checkpoint commit 抽成 script**：標準 `iter-N:` 訊息單一真相源 + **空輪防護**（apply-fix 全 skip 的輪不留空 commit）。`test/pai-iter-commit.bats`（9 個）用 fixture repo 斷言 commit graph：有變更才 commit、untracked 被納入、空輪跳過、round 驗證（0/非數字/11 位）、非 repo。
- academic SKILL.md Phase 5b 主迴圈改寫：確定性決策全部委派給上述兩個 script，**唯一的 LLM 步驟剩 `apply_fixes`**（屬 eval 範疇，非單元測試）。
- `test/README.md` 補「哲學」一節：把「LLM 編排」拆成確定性核心 + 模型 seam（Functional Core, Imperative Shell）—— decider/parser 窮舉測、mock seam 測接線、fixture 測 side-effect、模型判斷品質歸 eval。
- CI/`run.sh`：shellcheck 擴及 `pai-iter-commit`、node 測試改跑全部 `test/*.test.mjs`。bats 50 → 59、node 8 → 25。

## [2.15.0] - 2026-06-04

### Added
- **`bin/pai-parse-lens-csv` —— ensemble-compose 的 `--lens-file` CSV 解析器抽成 shipped script**（單一真相源）。原 inline python heredoc 抽出，SKILL.md 改呼叫。csv 模組（不 naive split）、輸出 JSON array。`test/pai-parse-lens-csv.bats`（14 個）覆蓋含逗號/引號/換行的 focus、needsSrt 變體、空欄跳過、BOM、CRLF、缺檔/缺欄。
- **`bin/pai-parse-verdict` —— ensemble-academic-review `--auto-iterate` 的 Codex verdict tag 解析器抽成 shipped script**（單一真相源）。SKILL.md 的 regex 改呼叫。`test/pai-parse-verdict.bats`（11 個）覆蓋 last-match、`{N}` placeholder、嚴格大寫、查無 tag、stdin/file。
- CI/`test/run.sh` 加 `py_compile`（python script lint）、shellcheck 擴及 `pai-parse-verdict`；bats 總數 25 → 50。

### Fixed
- **compose CSV 的 BOM 靜默丟列**（抽取時 dogfood 抓到）：原 inline snippet 用 `encoding='utf-8'`，Excel/Windows 存的帶 BOM CSV 會讓首欄 header 變 `﻿key` → 每列 `r.get('key')` 回 None → **整批 lens 被靜默丟棄**（使用者 CSV 形同被忽略）。`bin/pai-parse-lens-csv` 改 `utf-8-sig`。負控確認舊寫法對 BOM CSV 輸出 `[]`。
- **academic verdict 的 first-match 假收斂**（抽取時 dogfood 抓到）：原 regex 取 first-match，但 Codex 開頭可能 echo「輸出格式說明」裡的範例標籤（`<verdict>CONVERGED</verdict>` 字面寫在 instruction）→ first-match 誤抓成假收斂、提前 halt 迴圈。`bin/pai-parse-verdict` 取 **last-match**（verdict 在 review 最末），對齊契約。

## [2.14.1] - 2026-06-03

### Fixed
- **共用 harness `ensemble-workflow.js` 的 null-skip fail-OPEN**（dogfood lecture/academic/compose/harness 時抓到）：Workflow runtime 在「使用者中途 skip 某 agent」時讓 `agent()` 回 `null`。但 review / codex / devil's-advocate 三個 `.then` 只用 `(r && r.findings) || []` 處理 null 的 findings、**沒處理 `ok` flag** → 被 skip 的 reviewer 被當 `ok:true`（乾淨通過），**繞過 fail-closed integrity 檢查 → 可能假 PASS**（與 code-review 三輪一直在防的「假綠燈」同類，只是換成 JS null 路徑）。修：三處 `.then` 把 `r == null` 視為 `ok:false` → core lens／DA 被 skip 會如預期觸發 HIGH integrity finding。

### Added
- **`test/ensemble-workflow.test.mjs` —— 共用 harness 的 node regression 測試**（8 個）：unknown profile、空 lens 組合、core lens 被 skip(null)/error(throw)/DA 缺席 → HIGH integrity（鎖死上述 fail-open 修正）、codex 缺席 → INFO 非阻塞、mergeDedup 對 malformed severity 穩健。把 workflow script body 包成可 import 的 async 函式、注入 mock globals 實跑。已接進 `test/run.sh` 與 CI。

### Docs
- **plugin `CLAUDE.md` 修正 drift**：原本只列已不存在的單一 `/parallel-ai-agents:ensemble-review` + 「4 teammates + 1 Codex」舊架構；改成實際的 4 個 skill（code/academic/lecture/compose）+ 雙 backend（Workflow harness 預設、legacy fallback）+ fail-closed 說明。

## [2.14.0] - 2026-06-03

### Added
- **`bin/pai-build-diff` —— diff 模式建構器抽成 version-pinned shipped script**（單一真相源）。原本 inline 在 `ensemble-code-review` SKILL.md 的 bash recipe（經 3 輪 self-dogfood 硬化）抽成獨立可執行檔，`SKILL.md` 改成呼叫它（`bash "${CLAUDE_PLUGIN_ROOT}/bin/pai-build-diff" "$MODE" ...`）。好處：消除「LLM 改寫 inline recipe 時 typo」的風險、可 shellcheck、可 bats 覆蓋。退出碼契約：`0` 有 diff／`3` 無變更（良性）／`1` 錯誤。
- **`test/pai-build-diff.bats` —— 25 個 bats regression 測試**：把 3 輪人工 re-audit 抓到的 bug 全部固化（5 種模式、退出碼、ref/N 驗證防 injection/dashed-ref/0/leading-zero/位數溢位、untracked symlink no-follow、FIFO no-hang、換行檔名 C-quote、empty-tree base）。取代「每次改 diff 邏輯都人工重審」。附 `test/run.sh`（shellcheck + bats 一鍵）+ `test/README.md`。
- **`.github/workflows/test.yml` —— CI**：每次 push / PR 自動跑 shellcheck + bats。

### Fixed
- **`bin/pai-build-diff` 未知 mode 的多位元組 bug**（extraction 過程 dogfood 抓到）：`未知 MODE: $MODE（限...`—— `$MODE` 緊貼全形 `（`，bash 把 `（` 的首位元組吞進變數名 → `set -u` 誤報 `unbound variable`。改 `${MODE}` 明確界定。已加 regression 測試。

## [2.13.2] - 2026-06-02

### Fixed
- **diff 模式第三輪硬化（第三次 `--diff` re-audit 抓到第二輪 `append_new()` 引入的新 bug）**：第二輪為了「大新檔加 size cap」改寫的 untracked append helper 自己埋了三類 pathological-input 漏洞，本輪修正：
  - **symlink no-follow**：舊 `wc -c < "$f"` 會跟隨 symlink → 量到目標檔大小、甚至把目標內容讀進 diff（symlink 指向 `/etc/passwd` 之類即洩漏）。改成先 `[ -L ] || [ ! -f ]` 守衛，symlink/特殊檔只用 `printf %q` 列**路徑**、不讀內容。
  - **FIFO no-hang**：untracked 列表若含具名管道（FIFO），讀內容會永久阻塞。同一守衛把非一般檔擋在讀取之外，杜絕掛死。
  - **含換行檔名防偽造 diff 行**：一般新檔內容改走 `git diff --no-index`（git 自動 C-quote 檔名，`weird\nname.txt` 變字面 `"a/weird\nname.txt"`）而非手組 header，惡意檔名無法注入假 diff 行；外加 `head -c 65536` 保留 64KB 上限。
  - **`validate_int` 加位數上限**：`^[1-9][0-9]*$` 之外再要求 `${#1} <= 9`，防 10+ 位數的 `--commits`/`--pr N` 在後續 `(( N >= TOT ))` 算術比較溢位。
  - **Phase 4.5 明確 cleanup step**：第二輪拿掉 `trap EXIT` 後，DIFF_FILE 刪除只散落在 prose；本輪在 Phase 4 與 Phase 5 之間補 actionable 的 `rm -f "$DIFF_FILE"` 步驟（含 changed-line 祕密，排在報表 render 完、下游確定讀完之後）。

## [2.13.1] - 2026-06-01

### Fixed
- **diff 模式第二輪硬化（`--diff` re-audit dogfood 抓到「修正引入的新 bug」）**：上一版的 4 個 HIGH 經 re-audit 確認修好，但其中 `--commits` 的越界 clamp 自己有 off-by-one：
  - **`--commits N` clamp off-by-one**：`N=$TOT` → `HEAD~TOT`（root 的 parent、不存在）→ `git diff` fatal → hard-abort。改成 `N≥TOT` 時對 **empty tree**（`git hash-object -t tree /dev/null`）取 diff，涵蓋含 root 的全部變更、不越界。
  - **`validate_int` 排除 0 / leading-zero**：`^[0-9]+$` → `^[1-9][0-9]*$`（合約是「正整數」，舊版 `--commits 0` 會給假綠燈）。
  - **untracked 加 64KB size cap**（對齊 codex-pro），超大新檔轉 path-only，避免單檔撐爆 prompt；改用 repo-relative path（diff header 一致）。
  - **MODE/REF/N 明確賦值**（Phase 0 判定 lower 成變數，不只留 prose）；`--pr` 加 `--color never`；DIFF_FILE cleanup 改「ensemble 跑完後刪」（**不**用 trap EXIT 提前刪）。

## [2.13.0] - 2026-06-01

### Added
- **`ensemble-code-review` 完整 diff 輸入模式**：除了既有的 `FILE_OR_DIR`，現在能審變更 —— `--diff`（uncommitted）、`--base <ref>`（分支相對 merge-base）、`--commits <N>`、`--since <ref>`、`--pr <N>`（gh pr diff）。對齊 idd-verify 的輸入彈性，但不綁 issue。
  - 純 skill 改動：skill 算出 diff 寫 temp 檔 → 傳 harness `code` profile 的 `diffFile`（早已支援），reviewer/Codex 用 file-read tool 讀 diff，避開 inline escape + prompt 膨脹。
  - path 與 diff flag 互斥；都沒給預設 `--diff`；空 diff 不空跑 ensemble。
  - Backend B（legacy）同步支援：diff 模式把 `{FILE_OR_DIR}` 換成 `$DIFF_FILE`。

## [2.12.0] - 2026-06-01

### Added
- **`general.security-review` 內建 lens**（使用者提供）：LLM 應用安全 —— prompt injection（不可信輸入/RAG/工具回傳能否覆寫 system 指令、越權呼叫工具、外洩 system prompt）、secret 洩漏、不可信內容邊界、工具授權範圍。補上 `code.security` 沒涵蓋的 LLM 專屬面。內建 lens 15 → 16（general 6）。

### Docs
- ensemble-compose SKILL 補明：**devil's-advocate 與 Codex 由 harness 自動加入每個 ensemble**（DA fail-closed、Codex 由 `--codex` 開），不可 `--include`、不在 lens 表/CSV —— 它們本來就在每次 run，不該被當成可挑 lens 放進清單。

## [2.11.0] - 2026-06-01

### Added
- **新內建 `general` profile — 5 個通用軟體品質 lens**（`perf` / `a11y` / `i18n` / `deps-and-portability` / `observability`）。現在 `--include general.perf` 等可跨任何 ensemble 取用，且出現在 `builtin-lenses.csv`（內建 lens 10 → 15）。`deps-and-portability` 是 codex-call dogfood 真用過、抓到 bug 的那個。
- `references/example-lenses.csv` 改為與內建**不重複**的專案型範本（`api-compat` / `migration-safety` / `flaky-tests`），保持「自訂 `--lens-file` 包」的乾淨示範。

### Notes
- 內建只放**廣用、低後悔**的通用 lens；專案/個人特定的 reviewer 角色建議留在你自己的 `--lens-file` 包（user-owned、零 code、零 version bump）。

## [2.10.2] - 2026-06-01

### Added
- **`references/builtin-lenses.csv` — 內建 lens 的 reference catalog**：10 個內建 reviewer lens（lecture 3 / code 3 / academic 4）攤成 `profile,key,focus,needsSrt` 的 CSV，方便一覽、或 copy 到自己的 `--lens-file` 包。
  - **唯讀 reference**：harness runtime 無 FS、讀不到此檔；內建 lens 的真源是 `PROFILES`（code）。編此 CSV 不會改 harness。
  - **`references/regen-builtin-lenses.sh`**：從 `PROFILES` 重生此 CSV（砍 Orchestration 段、`export {PROFILES}`、用 JS engine eval 而非 regex parse）。idempotent，改 PROFILES 後跑它同步。
  - ensemble-compose SKILL 內建 lens 表加指引指向此檔。

## [2.10.1] - 2026-06-01

### Fixed
- **`bin/codex-call` 4 個 MEDIUM bug（ensemble-compose dogfood 抓到的剩餘項）**：
  - **`jwtExp` `exp as? Int` → `(... as? NSNumber)?.intValue`**：`exp` 是 NumericDate，JSONSerialization 可能給 Double，`as? Int` 會失敗 → 有效 token 讀成 exp=0 → 每次呼叫被當過期強制 refresh。改 NSNumber 解析（parse 失敗仍回 0，保守地強制 refresh）。
  - **`saveAuthRaw` umask 窗**：chmod-after-write 留下 staging temp 為 umask-default（常 0644 group/other-readable）的窗。改寫前 `umask(0o077)`（defer 還原），含 `.atomic` staging 都 ≤0600。
  - **rotating refresh_token race + `now` TOCTOU**：lock 後 re-read 卻沿用 pre-lock 的 `refresh`／`now`。flock 久等後，pre-lock `now` 讓 freshness recheck 偏樂觀（漏該 refresh），pre-lock `refresh` 可能已被並行 process rotate（single-use → 失敗）。改 re-read 後重抓 `nowLocked` 與 `refreshNow`。
  - **`.urlQueryAllowed` → 自訂 unreserved CharacterSet**：form body 用 `.urlQueryAllowed` 不轉義 `+ & = /`，refresh_token 含這些字會被伺服器解錯（`+`→空格）或破壞欄位邊界（參數污染）。改只允許 RFC 3986 unreserved。
  - e2e：CLT swift 編譯 4 處 + 真跑（jwtExp NSNumber 每次跑、request 成功）。

## [2.10.0] - 2026-06-01

### Added
- **`/ensemble-compose --lens-file <csv>` — 可重用 lens 包**：把自訂 reviewer 角色維護成 CSV（`key,focus,needsSrt`），一個檔一包（`frontend-lenses.csv`、`security-audit.csv`…），skill 讀進來轉成 `customLenses`。
  - 純 skill 改動（harness 的 `customLenses` 已支援，無需動 JS）；**CSV 由 skill 讀（主 session 有 Read），不是 harness（runtime 無 FS）**。
  - skill 必用 **python3 `csv` 模組**解析（focus 含逗號/中文標點，naive split 會切爛）—— recipe 內建於 SKILL.md。
  - `references/example-lenses.csv` 範本（perf / a11y / i18n / deps-and-portability / observability）。
  - 定位：CSV 是**使用者擴充包**入口，不是把穩定的內建 lens 搬出去。

## [2.9.1] - 2026-06-01

### Fixed
- **`bin/codex-call` 兩個 HIGH bug（由 `/ensemble-compose` dogfood 審 codex-call 本身抓到）**：
  - **empty-output → exit 0**：Codex stream 以 200 完成但無 text delta（只有 reasoning、或首個 delta 前斷流）時，原會寫**空檔 + exit 0**，被 ensemble 誤讀成「Codex reviewer 跑完無發現 = PASS」（偽造贊成票）。現在空輸出 fail-closed：throw（exit 非 0 + 明確訊息），不寫空檔。
  - **`#!/usr/bin/env swift` → `#!/usr/bin/swift`**：env shebang 解到 PATH 第一個 swift（這台機器是 swiftly 6.2.4），與 CLAUDE.md 宣稱的「Xcode CLT 內建 swift」不符、破壞確定性。釘 `/usr/bin/swift`（CLT，本機 6.3.2）後文件與實際一致。CLAUDE.md 同步註明不用 env 的理由。

## [2.9.0] - 2026-06-01

### Added
- **`/ensemble-compose` — 自由組合 ensemble 審閱（#1 的「自由組合 agents」原始構想落地）**：跨 profile 挑既有 reviewer lens、或在呼叫時自訂全新 reviewer 角色，組成一次性 ensemble。
- **harness composition engine**：
  - **`includeLenses`**（跨 profile 拉 lens，如 `["code.security", "academic.methodology"]`）
  - **`customLenses`**（呼叫時自訂 `[{key, focus, needsSrt?}]` reviewer 角色）
  - **`profile: "custom"`**（無內建 lens，全靠 include/custom 組）
  - **`maxAgents`**（agent 上限可調，硬上限 30）+ `daFocus` / `codexInstructions` / `codexMaxTime` args override
  - 組裝順序 base → include → custom、**key 去重 first-wins**；**雙重成本封頂**（先砍 lens 數到 `maxAgents − codex − DA`，replicas 再依剩餘 budget clamp）—— 組合自由但成本始終有 ceiling。

## [2.8.0] - 2026-06-01

### Added
- **Workflow backend Phase 3 — `ensemble-academic-review`（完成三 skill 全轉，#1）**：harness 加 `academic` profile（methodology / writing / reference-verifier / number-verifier + devil's-advocate + Codex），`ensemble-academic-review` 改 dual-backend。**workflow = 「一輪 ensemble」inner primitive**；mix / hybrid / `--auto-iterate` 多輪迴圈、verdict parse、apply-HIGH-fix、git commit per round、prior-slicing **全留 skill 側**（每輪呼叫 Backend A 一次）。
  - **reference-verifier**：harness 內用 **ToolSearch 取 che-zotero-mcp 工具**逐筆查文獻、抓幻覺文獻（workflow agents 可達 session MCP）。
  - **number-verifier**：用 **Bash 跑 Rscript / python** 從 ground-truth artifact 重算、抓幻覺數字。
  - Codex `--max-time 900`（論文較長，較 code 的 600 長）。
- **per-lens `priors` map**（取代單一 `priorBlock`）：skill 用「放不放某 lens 進 map」控制 hybrid 資訊不對稱 —— DA 收 `priors.da`（全部前輪）、reference-verifier 收自己的 watch-list，methodology/writing/number-verifier/codex 收不到任何前輪。機制留 harness、策略留 skill。
- **`disableLenses` arg**：對應 academic 的 `--no-numeric`（`["number-verifier"]`）/ `--no-references`（`["reference-verifier"]`）；fail-safe：全關退回全集。
- **`profile.codexMaxTime`**：Codex max-time 改 per-profile（academic 900 / 其餘 600）。

## [2.7.0] - 2026-06-01

### Added
- **Workflow backend Phase 2 — `ensemble-code-review` (#1)**：harness 新增 `code` profile（architecture / correctness / security + devil's-advocate），`ensemble-code-review` 改 dual-backend（workflow 預設 + legacy TeamCreate+Codex fallback）。CLI 與 Phase 4 報表契約不變。
  - **Codex 作為 barrier 內成員**：`codexEnabled: true` 時，Codex（gpt-5.5）是 Phase-1 barrier 的第 4 個 agent，shell 出去呼 `bin/codex-call`（**絕不** `codex exec`），fail-soft（timeout/error 只回 1 個 INFO，不阻擋 Claude-lens verdict）。跨模型獨立性由 codexPrompt 保證（不提及 Claude reviewers）。

### Changed
- **`codexPrompt` 改用絕對路徑 `args.codexCallPath`**（skill 傳 `${CLAUDE_PLUGIN_ROOT}/bin/codex-call`）取代裸 `codex-call`：workflow agent 的 shell PATH 是 install-time version-pinned 注入、可能 stale/不存在，絕對路徑消除此脆弱性（bare `codex-call` 僅 fallback）。

### Fixed
- **harness self-review 硬化**（Phase 2 dogfood 用 `code` profile 自審 harness 時，由 correctness/security lens 抓到）：
  - **empty-lenses guard**：若 `PROFILES` 出現 lenses 為空的 profile，原 `budgetForLenses / profile.lenses.length` 會 divide-by-zero → `maxReplicas=Infinity`（繞過 `MAX_AGENTS`）、fan-out 0 reviewer、fail-closed 迴圈空轉 → **false PASS**。現在 unknown-profile guard 一併攔截 empty/malformed lenses，bail with HIGH integrity finding。
  - **`SENTINEL_RE` 標籤類別 `[A-Z_]` → `[^>]`**：digit/space 等 sentinel-shaped 變體一併中和，符合「中和每個已知 sentinel token」原意（原窄類別讓 forge-shaped 變體漏網；非可 forge 真 boundary，但屬 defense-in-depth gap）。

## [2.6.0] - 2026-06-01

### Added
- **Workflow-tool backend for ensemble review (#1)** — 新增共用 harness `workflows/ensemble-workflow.js`，把 ensemble 審閱改用 Claude Code `Workflow` tool（dynamic workflows）編排，鏡像 `issue-driven-development` 的 idd-verify dynamic-workflow backend。
  - **dual-backend（加法、不破壞）**：`Workflow` tool 可用時走 workflow path，否則 capability-gate fallback 到既有 TeamCreate fan-out。findings 形狀與 Phase 4 報表契約不變。
  - **「大量 agents」**：reviewer 數量改為 data-driven（profile `lenses` × `args.replicas` 旋鈕），自動封頂 `MAX_AGENTS=16`，跨 replica 由 `mergeDedup` 去重強化共識訊號。
  - **Phase 1 範圍**：先轉 `ensemble-lecture-review`（最低風險：無 Codex / 無 MCP / 單輪）。`ensemble-code-review`（Phase 2，加 Codex-via-`codex-call`）、`ensemble-academic-review`（Phase 3，僅單輪進 workflow）後續。
- `references/ensemble-findings-schema.json` — harness 內嵌 `FINDINGS_SCHEMA` literal 的 canonical mirror（runtime 無 FS，schema 必須內嵌，此檔為人類可讀來源、防 drift）。

### Changed
- **devil's-advocate 行為（僅 workflow backend）**：從 live `TeamCreate`+`SendMessage` 即時拷問改為 downstream node 讀同儕**完稿** findings。更穩（消滅 idle-teammate / SendMessage 不觸發的失敗模式），但 DA 看的是定稿而非即時對話。legacy backend 行為不變。

## [2.3.0] - 2026-05-07

### Added
- **`--auto-iterate` mode for `/ensemble-academic-review` (#34)**: round → fix → round 自治收斂迴圈,內部沿用 mix N 的 alternating independent/hybrid pattern,但加上每輪結束的:
  - **Verdict parsing**: Codex prompt 強制要求 `<verdict>PERMANENT_CONVERGENCE | CONVERGED | NEEDS_ITER_N</verdict>` 結構化 tag,skill 用 regex 解析,不靠語意判斷
  - **HIGH-only fix application**: 從 `review-round-{N}.md` 解 HIGH-severity findings 自動套到 working tree;ambiguous fix skip + log to `skipped_fixes.log`
  - **Auto-commit per round**: `iter-{N}: apply HIGH fixes from ensemble round {N}`,user 可隨時 `git revert iter-{N}`
  - **Rotate-focus heuristic**: 連續 K=3 同 focus CONVERGED 才 switch (focus pool: method-section / proofs / typography / cross-references / boundary-cases)
  - **Stop conditions**: 達 `--converge-on` (default `PERMANENT_CONVERGENCE`) 或 `--max-rounds` (default 12, max 30)
- **8 cumulative methodological lessons** in SKILL.md tail — 來自實戰 23-round campaign (`PsychQuantHsu/psychophysic_representations_manuscript/docs/rounds/INDEX.md`),作為 rare-audited section / hypothesis-inheritance / verdict-tier 等坑的 reference

### Notes
- Self-contained Bash while + state machine,**不**依賴 ralph-loop 的 Stop-hook 機制
- 與 ralph-loop 同時跑時 skill 偵測並警告(雙 Stop-hook 衝突風險)
- Spec-only PR — agent 讀 SKILL.md 後在 user 顯式傳 `--auto-iterate` 才觸發,既有 mode 行為不變

## [2.2.0] - 2026-05-03

### Added
- **`number-verifier` reviewer**: 5th ensemble reviewer that checks every
  number in a doc against ground-truth artifacts (`.rds`, `.npz`, `.csv`,
  R/Python scripts). Catches hallucinated numbers that other reviewers
  miss. Verified by ASSG3 review pipeline (Canadian GDP ARIMA + Australian
  yields VAR/VECM) where it caught wrong y_T, drift omission, Ljung-Box
  fitdf errors, and ARIMA(1,1,1) reference p-value mistakes across 4 rounds.
- `--no-numeric` flag to disable number-verifier (pure theoretical papers)
- `--no-references` flag to disable reference-verifier (technical notes)
- Auto-detect: number-verifier enables when `analysis/`, `*.rds`, `*.ipynb`,
  `*.Rmd`, or `data/*.csv` are present near the doc
- Hybrid mode: `prior_number_issues` watch list passed to number-verifier
  in subsequent rounds (analogous to `prior_ref_issues`)

### Changed
- Reviewer count: 4 → 5 Claude teammates + Codex
- Tool-call rule: "5 calls in one message" → "N+1 calls (N ∈ {3,4,5})"
- Ironclad rules: HIGH-priority bucket now includes hallucinated numbers
  alongside hallucinated references

## [2.1.1] - (date unknown — please fill in)

### Changed
- 平行派發任務給多個 AI agent（Claude + Codex），獨立執行後交叉比對結果
