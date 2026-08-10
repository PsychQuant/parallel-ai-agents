# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> ⚠ This file was bootstrapped by `changelog-tools:changelog-init` from the
> `plugin.json` description field. Section categorization is best-effort —
> review and refine `Added` / `Changed` / `Fixed` etc. as needed.

## [Unreleased]

## [2.23.0] - 2026-08-09

`pai-lenses` 從獨立 repo 併回本 repo 成為第二個 plugin，並把三層 lens 疊加的文件與 CI 閘門補齊。

> **範圍說明**：本版**不含**層 ③ 的自動回流工具。它原本在同一個 PR 裡，經八輪 6-AI verify
> （HIGH 數 15 → 18 → 32 → 14 → 15 → 4 → 3；R8 因 session limit 只有 1/6 agent 完成，
> 不計入序列但其 CRITICAL 已修）後拆出到 **#39**。R3 的 32 個 HIGH 有 **29 個**落在
> 回流工具上；剩下 3 個在 `validate.py`（**本版出貨的內容**，已於 R4 修掉）。
> 收斂之後的 R4／R5／R6／R7 共 36 個 HIGH **全部**落在本版出貨的內容裡並已逐條修掉 ——
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
- **pack README 的「CI 會檢查」清單改成完整表格**（#33 verify R8）。先前漏掉對貢獻者最重要
  的兩道：改 lens 必 bump、撞名。諷刺的是本 PR 出貨的唯一一條 lens 就叫 `docs-vs-code`。

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
