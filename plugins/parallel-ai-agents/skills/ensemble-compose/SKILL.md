---
name: ensemble-compose
description: |
  自由組合 ensemble 審閱：跨 profile 挑既有 reviewer lens、或自訂任意 reviewer 角色，再用 Workflow 大量 fan-out。
  當用戶要「自己挑審閱角度」「混搭 code/academic/lecture 的 reviewer」「自訂 reviewer 角色」「compose ensemble」「自由組合 agents」時使用。
argument-hint: "FILE_OR_DIR [--lens-file pack.csv] [--include profile.lens]... [--lens 'key: focus']... [--base profile] [--replicas N] [--max-agents N] [--codex] [--focus '...']"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - Agent
  - TeamCreate
  - SendMessage
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - AskUserQuestion
---

# /ensemble-compose — 自由組合 ensemble 審閱

跨 profile 挑既有 reviewer lens、或在呼叫時**自訂全新 reviewer 角色**，組成一次性 ensemble，用 Workflow harness 大量平行 fan-out（+ 可選 Codex 跨模型 + devil's-advocate）。findings 形狀、合併去重、fail-closed 與其他 ensemble skill 完全一致。

> 既有三個 skill（lecture / code / academic）是**固定 profile**；本 skill 是**組合層** —— 當固定 profile 不合、要混搭、或要自訂角度時用。

## 可挑的內建 lens（`--include <profile>.<lens>`）

| `profile.lens` | 審閱角度 |
|----------------|----------|
| `code.architecture` | 設計模式、API 用法、依賴、死碼 |
| `code.correctness` | bug、edge case、型別安全、錯誤處理 |
| `code.security` | injection、secrets、權限、輸入驗證（攻擊者視角） |
| `academic.methodology` | 研究設計、統計方法、推論邏輯 |
| `academic.writing` | 論述結構、學術語氣、APA、文法 |
| `academic.reference-verifier` | che-zotero-mcp 逐筆查文獻、抓幻覺文獻 |
| `academic.number-verifier` | R/Python 重跑 ground-truth、抓幻覺數字 |
| `lecture.content-accuracy` | 教學內容知識正確性 |
| `lecture.student-readability` | 零基礎學生可讀性 |
| `lecture.completeness` | 逐字稿覆蓋率 + 結構完整性 |
| `general.perf` | 效能：hot path 複雜度、N+1、不必要重算、快取/批次 |
| `general.a11y` | 無障礙：ARIA、鍵盤可達性、色彩對比、報讀器 |
| `general.i18n` | 國際化：硬編字串、日期/數字/貨幣格式、RTL、時區 |
| `general.deps-and-portability` | 依賴鎖版本、跨平台/版本假設、硬編路徑 |
| `general.observability` | log/error context、secret 洩漏、metric/trace |

> 完整 focus 文字見 [`references/builtin-lenses.csv`](../../references/builtin-lenses.csv)（從 harness `PROFILES` 自動產生的 reference）。⚠️ 這是**唯讀 reference** —— 編它**不會**改 harness（內建 lens 的真源是 code，且 workflow runtime 無 FS 讀不到）。要客製請用下方 `--lens-file` 自己的 CSV、或 `--lens`。改了 `PROFILES` 後重生此檔：`bash references/regen-builtin-lenses.sh`。

## CSV lens 包（`--lens-file`）

把可重用的自訂 reviewer 角色維護成 CSV，一個檔一包（如 `frontend-lenses.csv`、`security-audit.csv`、`stats-paper.csv`）。每列 = 一個自訂 lens，等同一個 `--lens`。**這是把 reviewer 「做成 CSV」的正確位置 —— 使用者擴充包，不是把內建 lens 搬出去**（內建 lens 穩定、且 harness runtime 讀不到 FS）。

**格式**（UTF-8、第一列 header）：

```csv
key,focus,needsSrt
perf,"檢查每個 hot path 的時間複雜度、N+1 query、不必要的重算、記憶體配置",false
a11y,"檢查 ARIA 標籤、鍵盤導航、色彩對比、focus 順序",false
i18n,"檢查硬編字串、日期/數字/貨幣格式、RTL、複數規則",false
```

- `key`：短名（lens 標識；與其他來源同名時 first-wins）。
- `focus`：給 agent 的**具體**檢查清單（像內建 lens 那樣逐點，太空泛審閱品質差）。**含逗號/中文標點必用 `"..."` 包住。**
- `needsSrt`（可選欄）：`true` 時該 lens 收到 `srtFile`（lecture 場景）；省略/`false` 即一般。

**解析（skill 必照做）**：用 python3 `csv` 模組（**絕不** naive `split(",")` —— focus 含逗號會被切爛）：

```bash
python3 - "$LENS_FILE" <<'PY'
import csv, json, sys
out=[]
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        k=(r.get('key') or '').strip(); foc=(r.get('focus') or '').strip()
        if not k or not foc: continue
        row={"key": k, "focus": foc}
        if str(r.get('needsSrt','')).strip().lower() in ('1','true','yes'): row["needsSrt"]=True
        out.append(row)
print(json.dumps(out, ensure_ascii=False))
PY
```

把輸出 array append 進 `customLenses`（與 `--lens` 合併）。範本見 `references/example-lenses.csv`。

## 執行流程

### Phase 0: 解析輸入

```
FILE_OR_DIR      — 審閱對象（缺則問使用者）
--lens-file pack.csv — 從 CSV 載入一整包可重用的自訂 lens（見下方 § CSV lens 包）
--include p.lens — 從某 profile 拉一個內建 lens（可重複）
--lens 'key: focus 檢查清單' — 自訂 reviewer 角色（可重複）；key 是短名、focus 是給 agent 的具體檢查指示
--base profile   — 基底 profile（預設 custom = 無內建 lens）；給 code/academic/lecture 則先帶入該 profile 全部 lens 再加 include/custom
--replicas N     — 每個 lens 複製 N 份獨立實例（預設 1）
--max-agents N   — agent 上限（預設 16，硬上限 30）
--codex          — 加 Codex（gpt-5.5）跨模型盲驗（預設關）
--focus '...'    — 全域審閱重點（注入每個 lens 的 context）
```

**至少要有一個 lens**（`--include` 或 `--lens`，或 `--base` 帶內建 lens），否則 harness 會回 HIGH integrity finding。

### Phase 1: 讀取 + 準備 context

讀 FILE_OR_DIR；組 `contextBlock`（檔案類型 emphasis + `--focus`）。

### Phase 2: 組裝 + 派發（Workflow）

1. 解析 harness 絕對路徑 `${CLAUDE_PLUGIN_ROOT}/workflows/ensemble-workflow.js`；wrapper `${CLAUDE_PLUGIN_ROOT}/bin/codex-call`。
2. 把 flag 解析成 args：
   - `--base` → `profile`（預設 `"custom"`）
   - `--include code.security` → `includeLenses: ["code.security", ...]`
   - `--lens 'perf: 檢查每個迴圈的時間複雜度...'` → `customLenses: [{key:"perf", focus:"檢查每個迴圈的時間複雜度..."}]`
   - `--lens-file pack.csv` → **用 python3 csv 模組解析**（見 § CSV lens 包；focus 含逗號/中文標點，**不可** naive split）→ 每列轉 `{key, focus, needsSrt?}` append 到 `customLenses`（與 `--lens` 合併；同 key first-wins）
   - `--replicas` / `--max-agents` / `--codex` → `replicas` / `maxAgents` / `codexEnabled`
3. 呼叫 `Workflow` tool，傳 `scriptPath` + `args`：

   ```json
   {
     "profile": "custom",
     "file": "<FILE_OR_DIR 絕對路徑>",
     "contextBlock": "<檔案類型 emphasis + focus>",
     "includeLenses": ["code.security", "academic.methodology"],
     "customLenses": [{"key": "perf", "focus": "檢查每個 hot path 的時間複雜度與不必要的重算"}],
     "replicas": 1,
     "maxAgents": 16,
     "codexEnabled": false,
     "codexCallPath": "${CLAUDE_PLUGIN_ROOT}/bin/codex-call"
   }
   ```

   - harness 組裝順序：base profile lens → include（跨 profile）→ custom，**key 去重 first-wins**，再砍到 `maxAgents − codex − DA`、replicas 依剩餘 budget clamp。**組合自由但成本始終有 ceiling。**
4. Workflow 回 `{ findings, verdict, stats }`，已 merge+dedup。`stats.reviewers` 列出實際跑了哪些 lens。

### Phase 3: 渲染比較表

依 `lens` 分組 render（同其他 ensemble skill 的比較表：# / 嚴重性 / title—body / lens·file:line）。**不要**再 dedup。附 `stats`（實際 agent 數、被砍掉的 lens 若有）。

## Legacy fallback（無 Workflow tool）

`Workflow` 不可用時，用 TeamCreate 把組裝後的 lens 各開一個 `general-purpose` Agent（role prompt = lens focus）、一個 devil's-advocate、可選 Codex Bash，同其他 skill 的 legacy 流程。所有 tool calls 同一 message 送出。

## 鐵律

- **至少一個 lens**。空組合 → harness 回 HIGH integrity finding。
- **自訂 lens 的 focus 要具體**：給 agent 明確檢查清單（像內建 lens 那樣逐點），focus 太空泛審閱品質會差。
- **maxAgents 硬上限 30**；成本由 `lens 數 × replicas + codex + DA` 決定。
- **跨 profile 同名 lens**：first-wins（base 先、include 次、custom 後），不會疊兩份。
- **findings/報表契約與其他 ensemble skill 一致** —— 下游消費方式相同。
- **`--lens-file` 必用 python3 csv 解析**，不可 naive split —— focus 是長 prose，逗號/中文標點會把欄位切爛。CSV 由 skill（主 session，有 Read）讀，**不是** harness（runtime 無 FS）。
