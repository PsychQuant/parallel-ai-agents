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

> **範圍說明**：本版**不含**層 ③ 的自動回流工具。它原本在同一個 PR 裡，經十輪 6-AI verify
> （HIGH 數 15 → 18 → 32 → 14 → 15 → 4 → 3 → R8 降級 → 11 → **7**；R8 只有 1/6 agent 完成，
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
  > **揭露（#33 verify R10 M9）**：這個動作刪掉了 v2.19.0–v2.22.0 五版的註記，而那些是使用者
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
  （靶數 × 全套 ≈ 十分鐘）不進 CI，但**靶清單相對 `validate.py` 的漂移**秒級就能擋：
  改動被 mutate 的那幾行、或搬走一道閘門，靶就對不上。先前這件事只有在有人手動跑整輪時
  才會發現，而「忘了跑」是預設。
  > **量測（R9 後）：46 個靶 → 45 殺掉 / 1 存活 / 0 靶壞**（R8 後是 36→35/1/0）。
  > 唯一存活的「catalog 缺檔」經實測確認是 equivalent mutant。
  > 五個存活裡有三個是**真缺口**（行為確實不同），已逐條補測試；判讀靠實測不靠推論。

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
  然後直接跑十分鐘的就地改寫迴圈）。兩者都改。

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
  truthy 無法辨識、未知旗標。**量測結果：37 靶 → 35 殺掉 / 1 存活 / 0 靶壞**，
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
