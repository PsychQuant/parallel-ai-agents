---
name: ensemble-eval
description: |
  Ensemble 偵測品質 eval（dev 工具）：對埋好缺陷的 fixture 論文跑 K 次真 ensemble，
  用 pai-eval-grade 容差斷言「缺陷有沒有被抓到」；可選 --apply-fix 驗證模型修稿品質。
  當維護者提到「跑 eval」「eval ensemble」「驗證偵測率」「apply-fix 驗證」時使用。
argument-hint: "[--fixture stats-paper] [--runs K] [--min-hits N] [--codex] [--apply-fix]"
---

# /ensemble-eval — ensemble 偵測品質 eval（dev 工具）

測試金字塔的最後一塊：`test/` 的單元測試覆蓋了所有**確定性** surface（diff 建構、harness 接線、
解析器、迴圈狀態機、commit），唯一沒測的是**模型判斷品質**（reviewer 抓不抓得到真缺陷、
`apply_fixes` 改稿改得對不對）。這塊不適合單元測試 —— 非確定、貴、慢 —— 所以走 eval：

> fixture 論文**故意埋缺陷**（幻覺文獻、錯數字、前後不一致）→ 跑 **K 次真 ensemble** →
> `bin/pai-eval-grade` **容差斷言**（每個缺陷在 K 次中 ≥ minHits 次被抓到）。
> **手動偶爾跑、絕不進 CI**（每次 K×5 agents，貴且非確定）。

## Fixtures

`${CLAUDE_PLUGIN_ROOT}/eval/fixtures/<name>/`：

| 檔案 | 內容 |
|------|------|
| `paper.md` | 合成論文（埋好缺陷）|
| `analysis/*.csv` | ground-truth artifact（number-verifier 比對用）|
| `manifest.json` | 缺陷清單（id / match patterns / fix checks）—— **評分依據，絕不能進 reviewer context** |

內建 `stats-paper`：4 缺陷 —— 捏造文獻（Tanaka & Whitfield 2019）、錯平均（5.42 vs 4.42）、
錯 t 值（6.34 vs 2.79）、Abstract/Method 樣本數不一致（120 vs 102）。

## 執行流程

### Phase 0: 解析參數

```
--fixture <name> — 預設 stats-paper
--runs K         — ensemble 重複次數，預設 3（容差聚合的母數）
--min-hits N     — 每缺陷的命中門檻，預設過半（floor(K/2)+1）
--codex          — 加 Codex 跨模型（預設關 —— eval 測 Claude lenses 的偵測率，且省成本）
--apply-fix      — 加跑修稿驗證（Phase 3）
```

### Phase 1: 跑 K 次真 ensemble

1. 解析 `FIX=${CLAUDE_PLUGIN_ROOT}/eval/fixtures/<fixture>`；`mktemp -d` 建 results 目錄。
2. 解析 dispatch model（#20）：`PAI_AGENT_MODEL` 未設 → `opus`；設了但不在 `sonnet|opus|haiku|fable` → **abort with usage error**（fail-loud，不靜默換模型；engine 對顯式非法值亦會於派發前 throw 作第二層）。解析值經 `args.agentModel` 傳入。然後 **K 次**呼叫 `Workflow` tool（`scriptPath` = `${CLAUDE_PLUGIN_ROOT}/workflows/ensemble-workflow.js`）：

   ```json
   {
     "profile": "academic",
     "agentModel": "<PAI_AGENT_MODEL 解析值（預設 opus，#20）>",
     "file": "<FIX>/paper.md",
     "contextBlock": "學術論文審閱。ground-truth 計算 artifact：<FIX>/analysis/results.csv（number-verifier 逐數字比對用）。",
     "codexEnabled": false,
     "replicas": 1
   }
   ```

   ⚠️ **contextBlock 必須中性** —— 跟真實審閱一模一樣。**絕不提「eval」「fixture」「埋了缺陷」
   「manifest」**，否則 reviewer 會被 prime 去找碴，偵測率失真（量到的是 prompted recall 不是
   natural recall）。
3. 每次 Workflow 回傳的 `{findings, verdict, stats}` **原封不動**用 Write 存 `results/run-<i>.json`。
   某 run 若 `stats.integrity > 0`（有 lens 沒跑完），照存 —— grader 會把 integrity 列在報表，
   integrity 多的 run 結果不可信，考慮補跑。

### Phase 2: 評分（確定性，bin/pai-eval-grade）

```bash
node "${CLAUDE_PLUGIN_ROOT}/bin/pai-eval-grade" detect \
  --manifest "$FIX/manifest.json" ${MIN_HITS:+--min-hits $MIN_HITS} results/run-*.json
```

退出碼 0 = 每個缺陷都 ≥ minHits 次被抓到。Render 報表：

```markdown
## Ensemble Eval: stats-paper（K=3, minHits=2）
| 缺陷 | 命中 | 哪幾 run | 抓到的 lens | 判定 |
|------|------|---------|------------|------|
| hallucinated-ref | 3/3 | 1,2,3 | reference-verifier | ✅ |
| wrong-mean       | 2/3 | 1,3   | number-verifier    | ✅ |
| ...
run integrity: [0, 0, 1] ⚠ run-3 有 1 個 lens 沒跑完
```

### Phase 3（`--apply-fix`）: 修稿品質驗證

1. **複製** fixture 到 temp：`cp -R "$FIX" "$WORK"`（**絕不**改 fixture 本體）。
2. 取 Phase 1 任一 run 的 HIGH findings，照 academic Phase 5b 的 apply-fixes protocol
   用 Edit 修 `$WORK/paper.md`（這一步是受測的 LLM 行為 —— 不要看 manifest 作弊）。
3. 評分：

   ```bash
   node "${CLAUDE_PLUGIN_ROOT}/bin/pai-eval-grade" fix \
     --manifest "$FIX/manifest.json" "$WORK/paper.md"
   ```

   檢查每個缺陷的 planted 文字**已消失**（且 corrected 值出現）。

### Phase 4: 報告 + 清理

彙整 detect（K 次容差）+ fix（若有）報告；`rm -rf` temp results/work 目錄。
結果**不 commit**（非確定性產物，不是 regression 資產）。

## 鐵律

- **fixture 唯讀**：apply-fix 只能在 temp 複本上動，`eval/fixtures/` 永不被修改。
- **reviewer context 中性**：manifest / 「eval」字眼絕不進 ensemble 的 contextBlock 或任何 prompt。
- **容差斷言，不是硬斷言**：單次 miss 是雜訊，K 次 < minHits 才是訊號。fail 先看是缺陷太難抓
  還是 fixture/match pattern 寫壞，再決定改哪邊。
- **絕不進 CI**：每次 eval = K×(4 lens + DA) 個 agents。CI 只跑 `test/`（確定性）。
- **新 fixture**：照 `stats-paper` 結構建目錄 + manifest；match pattern 用「planted 值或 true 值」
  雙向匹配（reviewer 可能引用任一邊）。
