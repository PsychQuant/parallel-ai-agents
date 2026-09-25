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
- **#59／#60 —— `--strict` 改成群組規則：靠管線過濾的 step，整個 run 區塊必須是一個 `{ …; } 2>&1 | python3 …neutralise.py`。**
  兩張 issue 是同一個缺口的兩面：R35 的 `--strict` 只要求「接 neutralise 的管線帶 `2>&1`」，那量的是**有沒有一條**過濾管線，
  不是**每一個位元組**都經過它——(1) 同一個區塊裡另一條命令印的 PR 文字不經任何管線（#59，已知類別 G）；(2) bash 先展開詞、
  再由左到右套用重導向，`echo "${!PR_TITLE}" 2>&1 | …` 的展開期錯誤、`echo x > "$PR_TITLE" 2>&1 | …` 的重導向錯誤，都在那一段的
  `2>&1` 生效**之前**寫到當下的 stderr（#60 第 2 類，逐段 `2>&1` 在結構上看不到）。群組的重導向在群組內任何展開之前生效，
  而整個區塊都在群組裡——兩類一起關掉，不需要 taint，也不列拼法清單（#60 Expected 的第一個方向；第二、三個方向不採用）。
  - **規則**（`strict_group_violation`）：`set` 前綴（只收 `-e`／`-u`／`-o pipefail|errexit|nounset`；裸 `set` 印出所有變數、
    `-v`／`-o verbose` 印出含 `${{ … }}` 代入值的原始碼，都不收）＋ 恰好一對獨立詞 `{`／`}` ＋ `}` 在最後一個邏輯行的命令位置
    ＋ 之後恰好是 `2>&1 | python3 <路徑>/neutralise.py` 或 `|& python3 …`。有管線而 shell 不是 bash 時，`set -o pipefail`
    必須在前綴裡（群組在管線裡是子殼層，群組內的 `set` 管不到外層管線）。
  - **為什麼是「恰好一對」而不是計深度**：計深度要判斷每個大括號在 bash 眼中是不是保留字；`case` 的模式 `{)` 不是，計數器會以為
    群組還開著、bash 已經關了——`bypass-strict-group-case-pattern-brace` 在 bash 5.2 實測外流。只收一對就不必判斷：多出任何一個
    ⇒ 拒絕；唯一的 `}` 若被某個沒收的構造吞掉，bash 讀不完那個複合命令、群組裡什麼都不執行。代價是巢狀群組被連帶擋下
    （`restrict-strict-group-nested`，神諭記在 KNOWN_DISAGREE；改寫成 `if` 即可）。
  - **字面檢查**：規則讀的是 shell_scan 挖空後的程式碼，而群組**外**被挖空的內容 bash 會展開——`${PR_TITLE} {` 挖空後第一個詞是
    `{`（bash 把 PR 文字當命令名執行）、`python3 ${X}neutralise.py` 挖空後路徑是 `neutralise.py`、`set -e ${X:+-v}` 挖空後是
    `set -e`。群組外這三段（前綴、`{` 之前、`}` 之後）必須與原文逐字相同。這一條是寫 opsweep 存活者的 fixture 時自己找到的，
    不在兩張 issue 裡。斷詞只認 ASCII 空白與 tab：Python 的 `\s` 還認 NBSP，`{<NBSP>true` 會被讀成開群組，bash 卻讀成一個
    不存在的命令、群組沒開、下一行在過濾之外（`bypass-strict-group-nbsp-after-opener`；自審時找到，改回 `\s` 這一檔即放行）。
  - **test.yml**：10 個靠管線過濾的 step 改成群組形式（另外 5 個本來就是單一群組）；兩個刻意印 `::error::` 的檢查（`builtin-lenses.csv` drift、pack 錨點的
    TAP 守衛）拆成自己的 `# LOG-FILTER: none` step——放進群組 annotation 會被中和，留在群組外群組規則不收。pack 錨點原本的
    `assert-tap-complete.sh` 就在管線之外，是 repo 裡一個真的 G 類實例（它只印固定文字與計數，所以沒有外流）。
    TAP 守衛用 `if: success() || failure()` 取代先前的 `rc=$?` ⋯ `exit "$rc"`。
  - **神諭**：已知類別（G、S-2）的判準改成「`--strict` 真的擋下這個 step」（RULE，pipefail 那條除外；或 PARSE）——前一版只按形狀
    歸類，`--strict` 也放行的同形繞過一樣算已知、不改 rc。產生語料上 62 條已知逐條都被 `--strict` 擋下（數字與 base 相同）。
    #60 第 2 類補了預設模式的範例 `known-expansion-error-before-2to1`（歸 G 的 stderr 格：神諭分不出印 PR 文字的是另一條命令還是
    同一段的展開，兩者由同一條群組規則關掉）。
  - 既有 `--strict` fixture 改寫成群組形式，讓每一檔仍然只因它點名的那條規則變紅（pipefail 三檔先前會同時吃到群組規則，拿掉 pipefail
    規則也照樣紅）；`run: { … }` 的純量寫法是 YAML flow mapping（PyYAML 拒絕整檔），一律改成 `run: |`。
  數字：lint fixture 268 → 289 個（`python3 -c "import pathlib;print(len(list(pathlib.Path('test/fixtures').glob('ci-log-filter-*.yml'))))"`）——
  110 個正向（`python3 -c "import pathlib;print(sum(1 for f in pathlib.Path('test/fixtures').glob('ci-log-filter-*.yml') if '# EXPECT: pass' in f.read_text().splitlines()))"`）、117 條規則紅（`python3 -c "import pathlib;print(sum(1 for f in pathlib.Path('test/fixtures').glob('ci-log-filter-*.yml') if '# EXPECT: rule-red' in f.read_text().splitlines()))"`）、62 條解析紅（`python3 -c "import pathlib;print(sum(1 for f in pathlib.Path('test/fixtures').glob('ci-log-filter-*.yml') if '# EXPECT: parse-red' in f.read_text().splitlines()))"`）；
  CI run step 25 個（`grep -c "^        run:" ../../.github/workflows/test.yml`）；fixture 神諭 380 個 step：一致 302、不一致 6（**全部已知**：
  G 3、S-2 1、巢狀群組 1、stub python3 的盲區 1）、不可比 72、量不到 0；產生語料 624 個 step：一致 524、不一致 62（全部已知，且逐條被
  `--strict` 擋下）、不可比 38、量不到 0；形狀普查閘門綠；mutation 靶清單 193 → 195 個（`grep -c "^    (\"" ../pai-lenses/scripts/mutation_check.py`；
  群組規則那一條換成三條：群組、字面、pipefail 窗口，連同兩條改了靶文字的逐一實跑、全部被 selftest 殺掉）；`opsweep --since 380e4a4` 的結果記在下一個 commit（本 commit 時仍在跑）。
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
  最終樹上實跑」，是對外文字的第二輪查核抓到的）：lint fixture 173 → 268 個（R35 當時以指令計數；lint 形式的宣稱只留在最新一段，見 #59／#60 段）——
  108 個正向、98 條規則紅、62 條解析紅；
  **四個數字都改成帶指令的宣稱**（`lint-changelog-counts.sh` 會實際執行它們）——先前這一行的 fixture 計數
  只是散文，而 selftest 的門檻與它之間沒有任何機械連結，抄錯不會有人叫。靶清單 161 → 193 個；
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
  - **`fold_block` 遞移折疊**，並對 PyYAML **逐行**相符（含空行不折、more-indented 前後不折、**內容行後的第一個
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
  CI run step 23 個。
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
  測試 143 → 144 條（`grep -c "    def test_" ../pai-lenses/scripts/test_validate.py`）；
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
