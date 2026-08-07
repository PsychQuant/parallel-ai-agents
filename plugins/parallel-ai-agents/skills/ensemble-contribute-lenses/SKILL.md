---
name: ensemble-contribute-lenses
description: |
  把本機 user 層的 lens 送回公共層並開 PR。掃 ~/.claude/pai-lenses/*.csv，
  比對 built-in（PROFILES）與 lens pack（plugins/pai-lenses/lenses/），
  判定每條 lens 該進哪一層，產出變更後開 PR。
  Use when: 自己寫的 lens 想貢獻回 repo、或想知道本機有哪些 lens 還沒回流。
argument-hint: "[--profile <name>] [--dry-run] [--include-override]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - AskUserQuestion
---

# /ensemble-contribute-lenses — 把本機 lens 送回公共層

三層 lens 疊加（`references/lens-layers.md`）裡，層 ③（user）原本是單向終點：寫在
`~/.claude/pai-lenses/<profile>.csv` 的 lens 只有自己機器吃得到。這個 skill 是它的出口。

## 兩個目標層，判準不同

| 目標 | 何時 | 改什麼 |
|---|---|---|
| **層 ②** lens pack | 為**既有** profile 加 lens | `plugins/pai-lenses/lenses/<profile>.csv` + bump **兩處** version（`plugin.json` **與** `marketplace.json` 對應 entry）|
| **層 ①** built-in | 需要**新 profile**，或需要 profile 級語意 | `plugins/parallel-ai-agents/workflows/ensemble-workflow.js` 的 `PROFILES` + 跑 `references/regen-builtin-lenses.sh` + bump 兩處 version |

> **「bump」永遠是兩處**：只改 `plugin.json` 而漏 `marketplace.json`，PR merge 後使用者
> `/plugin update` 收不到新版 —— 而且沒有任何錯誤訊息。見 root `CLAUDE.md` 的「版本同步（CRITICAL）」。

**判準是「能不能只用一條 lens 表達」**：

- lens pack 的 CSV 只能描述 lens 本身（`key` / `focus` / `needsSrt` / `override`）。
- profile 級的東西——`title`、`daFocus`、`codexDefault`——**只存在於 `PROFILES`**。CSV 表達不了。
- 更關鍵：harness 的 `PROFILES` 沒有某個 profile key 時，用該 profile 呼叫會回
  `unknown ensemble profile` 且 **0 個 agent 被派出**，workflow 卻仍「成功」結束。
  把新 profile 誤送層 ② 的後果是這個安靜失敗，所以**判錯必須 fail-loud，不可猜**。

## 執行流程

> **路徑基準（全流程唯一）**：Phase 0 解出 `$REPO_ROOT` 之後，**下面每一個檔案路徑都相對於它**。
> 這個 skill 的目標使用者，其定義就是「lens 寫在 `~/.claude/pai-lenses/`、人在別的專案目錄工作」
> 的貢獻者 —— 他手上有的是 plugin cache（`~/.claude/plugins/cache/...`，**那不是 git checkout，
> 不能 commit/PR**），不是 repo。沒有 Phase 0 就沒有可修改的樹。

### Phase 0：定位可修改的 repo 工作樹

```bash
UPSTREAM="PsychQuant/parallel-ai-agents"

# 1) 已經在 repo 裡？
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$REPO_ROOT" ] && [ -f "$REPO_ROOT/.claude-plugin/marketplace.json" ] \
   && [ -d "$REPO_ROOT/plugins/pai-lenses" ]; then
    echo "→ 使用當前 repo：$REPO_ROOT"
else
    # 2) 使用者是否有寫入權？有 → clone upstream；沒有 → fork 再 clone
    REPO_ROOT="${PAI_CONTRIB_CLONE_DIR:-$(mktemp -d)/parallel-ai-agents}"
    if gh repo view "$UPSTREAM" --json viewerPermission -q .viewerPermission \
         | grep -qE '^(ADMIN|MAINTAIN|WRITE)$'; then
        gh repo clone "$UPSTREAM" "$REPO_ROOT"
    else
        # 外部貢獻者沒有 push 權限 —— 必須經 fork（pai-lenses README 給人類的流程同此）
        gh repo fork "$UPSTREAM" --clone --remote --fork-name parallel-ai-agents -- "$REPO_ROOT"
    fi
    echo "→ 已取得工作樹：$REPO_ROOT"
fi
cd "$REPO_ROOT"
```

`--dry-run` 時**跳過 clone/fork**，只用既有 repo（沒有就印出「需要 checkout 才能產出變更」並只做盤點與判定）。

### Phase 1：盤點本機 lens

```bash
USER_DIR="${PAI_USER_LENS_DIR:-$HOME/.claude/pai-lenses}"
[ -d "$USER_DIR" ] || { echo "本機無 $USER_DIR — 沒有可貢獻的 lens。"; exit 0; }
ls "$USER_DIR"/*.csv >/dev/null 2>&1 || { echo "$USER_DIR 下沒有 .csv。"; exit 0; }
```

每個檔名即 profile（一檔一 profile 是 user 層的既定格式，見 `lens-layers.md`）。
解析一律走 `bin/pai-parse-lens-csv`，**不可** naive split——`focus` 是含逗號與中文標點的長 prose。

### Phase 2：比對，找出本機獨有的 lens

**必須用 parser 的 JSON 輸出比對，不可用 `grep`。** 兩個理由，都是硬的：

- `focus` 是 quoted 長 prose，可含換行與逗號。`grep` 拿到的是 record 的第一個**實體行**，
  不是欄位值 —— 下面「focus 相同 / 不同」的分支用 grep **無法實作**。
- `key` 與 `profile` 來自使用者的檔案內容與檔名，直接插進 `grep -E "..."` 是 regex 注入
  （`.` `*` `[` 會被當 pattern，`-` 開頭會被當 option）。

```bash
PARSE="$REPO_ROOT/plugins/parallel-ai-agents/bin/pai-parse-lens-csv"
PACK_CSV="$REPO_ROOT/plugins/pai-lenses/lenses/${profile}.csv"

python3 - "$PARSE" "$USER_DIR/${profile}.csv" "$PACK_CSV" "$REPO_ROOT" "$profile" <<'PY'
import json, subprocess, sys, csv, pathlib
parse, user_csv, pack_csv, root, profile = sys.argv[1:6]

def lenses(path):
    if not pathlib.Path(path).is_file():
        return {}
    out = subprocess.run([sys.executable, parse, path], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"解析失敗 {path}: {out.stderr.strip()}")
    return {l["key"]: l for l in json.loads(out.stdout)}

mine, pack = lenses(user_csv), lenses(pack_csv)

# 層 ① 的同 key 查詢用 generated 投影即可（它保證列出所有 built-in *lens*）；
# 但「profile 是否存在」不可用它 —— 見 Phase 3。
builtin = {}
cat = pathlib.Path(root, "plugins/parallel-ai-agents/references/builtin-lenses.csv")
with cat.open(newline="", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        if (r.get("profile") or "") == profile and (r.get("key") or "").strip():
            builtin[r["key"]] = r.get("focus", "")

for key, l in mine.items():
    if key in pack and pack[key]["focus"] == l["focus"]:
        print(f"SKIP\t{key}\t已回流（層 ② 內容相同）")
    elif key in pack or key in builtin:
        print(f"MODIFY\t{key}\t同 key 但 focus 不同 → 走 Phase 4 的 override 路徑")
    else:
        print(f"CANDIDATE\t{key}\t兩層都沒有")
PY
```

| 比對結果 | 處置 |
|---|---|
| `CANDIDATE` | 進 Phase 3 |
| `SKIP` | 已回流，略過（並提示本機該條可刪） |
| `MODIFY` | 這是**修改**不是新增，走 Phase 4 的 override 路徑 |

### Phase 3：判定目標層

profile 存在性**必須查真源**，不可查 `builtin-lenses.csv`：

```bash
# 真源 = PROFILES。投影是「由 lens 產生」的，lenses: [] 的 profile（例如 custom）
# 在投影裡一列都沒有 —— 拿它問存在性對 custom 必定答錯（#33 verify H7）。
bash "$REPO_ROOT/plugins/parallel-ai-agents/bin/pai-list-profiles" | grep -qxF -- "$profile"
```

```
該 lens 的 profile 是否已存在於 PROFILES？（用上面的指令判定）
├── 是 → 目標 = 層 ②（改 lenses/<profile>.csv）
└── 否 → 目標 = 層 ①（新 profile，改 PROFILES）
         └── 但 CSV 只有 lens 資訊，profile 級欄位（title / daFocus / codexDefault）
             缺失 → 必須向使用者索取，不可代填
```

> **為什麼判錯的代價不對稱**：把該進層 ② 的送去層 ①，會在 `PROFILES` 產生**重複的物件 key**，
> 後者靜默勝出、把既有 profile（連同它的 `title`/`daFocus`/`lenses`）整個蓋掉。反向（新 profile
> 誤送層 ②）則是 `unknown ensemble profile` + 0 agent。兩個方向都是安靜失敗，所以這一步用真源、
> 且 `grep -qxF --` 全字面全行比對（不讓 profile 名當 regex 或 option）。

**新 profile 一律要問**。`daFocus` 決定 devil's advocate 盯什麼、`codexDefault` 決定要不要跑跨模型 leg，兩者都不是能從 lens 的 `focus` 推導出來的。代填等於替使用者做設計決定。

### Phase 4：`override` 的特別處理

標了 `override` 的 lens 語意是「**取代**某條 built-in lens」，不是「新增」。貢獻到公共層等於
**替所有使用者移除一條調校過的 lens**。

預設**不送**。要送必須：

1. 用 `AskUserQuestion` 確認，並在問題中列出被取代的那條 built-in lens 的 `focus` 全文
2. 取得取代理由（一句話），寫進 PR body
3. `--include-override` flag 才會把它列入候選

沒有理由就不送——這條規則存在是因為 override 的傷害是靜默的：被取代的 lens 消失後，
沒有人會收到通知。

### Phase 5：產出變更

> **bump 一律是「兩處」不是「一處」**（#33 verify H5/H9/H15）。本 repo 的
> [`CLAUDE.md` 版本同步（CRITICAL）](../../../../CLAUDE.md) 規定 `plugin.json` 與
> `.claude-plugin/marketplace.json` 對應 entry 必須一致 —— pai-lenses 併回後，這條**同樣適用於它**。
> 只 bump `plugin.json` 的後果正好是這個 skill 想達成的相反面：PR merge 了、`marketplace.json`
> 仍是舊版，**沒有任何使用者收得到那條 lens，而且沒有任何錯誤訊息**。

**層 ②**（多數情形）：

```bash
# 1. 附加到既有 CSV（保持 header 不動；欄位順序 key,focus,needsSrt,override）
#    focus 含逗號/換行 → 必須 quote。用 python csv.writer 寫，不要手拼字串。

# 2. bump 兩處 —— 缺一則使用者收不到
python3 - "$REPO_ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
pj   = root / "plugins/pai-lenses/.claude-plugin/plugin.json"
mp   = root / ".claude-plugin/marketplace.json"
d = json.loads(pj.read_text())
major, minor, patch = (int(x) for x in d["version"].split(".")[:3])
new = f"{major}.{minor + 1}.0"          # 新增 lens = minor
d["version"] = new; pj.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
m = json.loads(mp.read_text())
for p in m["plugins"]:
    if p["name"] == "pai-lenses":
        p["version"] = new
mp.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n")
print("bumped pai-lenses →", new, "(plugin.json + marketplace.json)")
PY
```

**層 ①**（新 profile）：

```bash
# 1. 在 plugins/parallel-ai-agents/workflows/ensemble-workflow.js 的 PROFILES 加 entry
#    （加之前先確認該 key 不存在 —— 重複 key 會靜默蓋掉既有 profile，見 Phase 3）
# 2. 跑 plugins/parallel-ai-agents/references/regen-builtin-lenses.sh 重生唯讀 catalog
#    （順序不可反 —— CSV 是投影，改它不影響行為）
# 3. bump parallel-ai-agents 的兩處版本（plugin.json + marketplace.json 對應 entry）
```

### Phase 6：驗證 → branch → commit → PR

```bash
cd "$REPO_ROOT"

# ── 驗證 ──
# lens pack 自我檢查（semver version + marketplace 版本一致 + 每個 CSV 至少一條 lens
#                     + 檔名必須是既有 profile）
(cd plugins/pai-lenses && python3 scripts/validate.py)

# 層 ① 變更時確認 catalog 與 PROFILES 同步。
# 注意：Phase 5 已經跑過 regen，所以此時 catalog 相對 HEAD **本來就該有差異** ——
# 直接 `git diff --exit-code` 會把正常流程判成失敗（#33 verify H4）。
# 正確的判準是「再跑一次 regen 不會再變」，也就是冪等：
if git diff --quiet -- plugins/parallel-ai-agents/references/builtin-lenses.csv; then
    :   # 沒動過 catalog（層 ② 路徑）— 無需檢查
else
    cp plugins/parallel-ai-agents/references/builtin-lenses.csv /tmp/pai-catalog-before
    bash plugins/parallel-ai-agents/references/regen-builtin-lenses.sh
    diff -q /tmp/pai-catalog-before \
            plugins/parallel-ai-agents/references/builtin-lenses.csv \
      || { echo "✗ catalog 與 PROFILES 不同步 —— 你的 regen 沒跑或跑在改 PROFILES 之前"; exit 1; }
fi

# ── branch / commit / PR ──
SLUG="lenses-$(date +%Y%m%d-%H%M%S)"        # 或用第一條 lens 的 key
git switch -c "contrib/${SLUG}"
git add plugins/pai-lenses/lenses \
        plugins/pai-lenses/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json
# 層 ① 變更時另加：
#   git add plugins/parallel-ai-agents/workflows/ensemble-workflow.js \
#           plugins/parallel-ai-agents/references/builtin-lenses.csv \
#           plugins/parallel-ai-agents/.claude-plugin/plugin.json
git commit -m "feat(lenses): 貢獻 <n> 條 lens 回層 <②|①>"
git push -u origin "contrib/${SLUG}"
gh pr create --repo "$UPSTREAM" --title "lens 貢獻：<摘要>" --body-file /tmp/pai-contrib-pr-body.md
```

PR body（寫進 `/tmp/pai-contrib-pr-body.md`）須含：每條 lens 的**來源**（本機哪個 profile）、
**目標層與理由**、`override` 的**取代理由**（若有）、以及新 profile 時使用者給的
`title` / `daFocus` / `codexDefault`。

`--dry-run` 跳過 Phase 0 的 clone/fork 與本 Phase 的全部寫入動作，只印計畫。

## 為什麼是單一 repo 的一個 PR

`pai-lenses` 曾是獨立 repo，貢獻要跨兩個 repo 判斷該去哪、開兩個 PR。#33 裁定它是本 repo 的
官方增補層並併入 `plugins/pai-lenses/` 後，兩層的變更落在同一個 PR，這個 skill 也因此不需要
處理跨 repo 的分支與版本對齊。

## 反模式

| 想做的 | 為什麼不行 |
|---|---|
| 直接編 `references/builtin-lenses.csv` | 那是 generated 的唯讀投影，改它不改變任何行為。真源是 `PROFILES` |
| 新 profile 送層 ② | harness 的 `PROFILES` 沒有該 key → `unknown ensemble profile`、0 agent 派出，且 workflow 仍「成功」結束 |
| 代填 `daFocus` / `codexDefault` | 那是設計決定不是格式轉換。缺就問 |
| 自動送出 `override` lens | 會替所有使用者移除一條調校過的 lens，且無人收到通知 |
| 送完就刪本機檔 | PR 未 merge 前刪掉會兩頭落空。提示使用者，由他決定何時清 |
