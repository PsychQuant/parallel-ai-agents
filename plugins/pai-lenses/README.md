# pai-lenses

[`parallel-ai-agents`](https://github.com/PsychQuant/parallel-ai-agents) 的 **lens pack** —— 用 CSV 提供可疊加的 reviewer lens。

裝了這個 plugin 之後，`ensemble-code-review` / `ensemble-academic-review` / `ensemble-lecture-review` /
`ensemble-compose` 的 lens 集合會自動疊上這裡的內容。

## 為什麼有這個 repo

built-in lens 的真源是 `parallel-ai-agents` 裡 `workflows/ensemble-workflow.js` 的 `PROFILES` 物件。
動它 = 改程式碼 → bump plugin 版本 → 同步 marketplace。結果是 lens 從 2026-06 起一條都沒新增過 ——
**不是沒人想改，是改一條的成本太高**。

拆出來之後：

|  | 之前 | 現在 |
|---|---|---|
| 新增一條 lens | 改 JS + bump plugin + 同步 marketplace | 改 CSV + bump 本 repo |
| 收外部貢獻 | 收一條 lens = 發一次 plugin release | merge 一個 PR |
| 量測條件可追溯 | plugin 版本號會被無關改動污染 | lens pack 版本就是 lens 的版本座標 |

最後一點對 `eval/fixtures/` 的偵測率數字尤其重要：lens 是量測儀器，前後用不同 lens 量到的數字不可比。
報表的 provenance 行會印出本 pack 的版本。

## 三層疊加

| 層 | 來源 | 給誰 |
|---|---|---|
| ① built-in | `parallel-ai-agents` 的 `PROFILES` | 所有人的 baseline |
| ② **lens pack（本 repo）** | `lenses/<profile>.csv` | 裝了這個 plugin 的人 |
| ③ user | `~/.claude/pai-lenses/<profile>.csv` | 只有你自己 |

順序即優先序。撞名時**預設 first-wins**（先到的勝），只有標了 `override` 的才取代。

## CSV 格式

一個 profile 一個檔，profile 由**檔名**決定（`lenses/code.csv` → `code` profile）。

```csv
key,focus,needsSrt,override
perf,"檢查每個 hot path 的時間複雜度與不必要的重算",,
security,"（取代內建的 security lens）……",,true
```

| 欄 | 必填 | 說明 |
|---|---|---|
| `key` | ✅ | lens 識別名。與其他層同名時觸發撞名判定 |
| `focus` | ✅ | 該 reviewer 的檢查清單。**含逗號要 quote** —— 這是長 prose，不是短標籤 |
| `needsSrt` | — | truthy 時標記此 lens 需要逐字稿（`lecture` profile 用） |
| `override` | — | truthy 時**取代**同 key 的既有 lens |

truthy 判準：`1` / `true` / `yes`（不分大小寫）。空白或省略 = false。

### `override` 的語意

`override` 是「**我要取代那一條**」，不是「我比較重要」。

不標記 = 純新增；撞名時你的那條會被忽略（並在報表警告）。標記則會讓一條經過調校的 built-in lens
**消失**，所以請在 PR 描述裡寫清楚為什麼原本那條不夠用。

## 怎麼寫一條好 lens

看 `parallel-ai-agents` 的 [`references/builtin-lenses.csv`](https://github.com/PsychQuant/parallel-ai-agents/blob/main/plugins/parallel-ai-agents/references/builtin-lenses.csv)
—— 那是內建 lens 的唯讀 catalog，可以直接當範本。共同特徵：

- **一個 lens 只審一件事**。範圍越窄，reviewer 越不會滑回泛泛而談
- **focus 是逐點檢查清單**，不是一句話的期望。`(1)…(2)…(3)…` 的形式最有效
- **明講要用工具查證**（「用 Read/Grep 實際打開檔案核對」），否則模型傾向只讀眼前的內容
- **寫下這條 lens 的失敗模式**（「一段寫得很有說服力卻與程式碼不符的說明，比沒有註解更危險」）——
  reviewer 需要知道它在防什麼

## 貢獻

1. Fork → 改 `lenses/<profile>.csv` → PR
2. PR 描述說明：這條 lens 抓什麼、為什麼既有的抓不到、若標了 `override` 為何要取代
3. CI 會檢查 CSV 可解析、`plugin.json` 有 `version`

## 硬性前提：`plugin.json` 必須有 `version`

Claude Code 把 plugin 解到 `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`。
`plugin.json` 缺 `version` 時，目錄名會退回 **git commit SHA**（[官方文件](https://code.claude.com/docs/en/plugin-marketplaces)
的 fallback）或 `unknown`（實測在 `claude-plugins-official` 的幾個 plugin 上看過）。兩者都不是 semver，
`parallel-ai-agents` 的 semver glob 就定位不到，本 pack 等同沒裝 —— 但報表會出現 `unversioned` 警告，
不會靜默。CI 有守這一條。

順帶一提，這也是為什麼**每次改 lens 都要 bump 版本**：版本沒變，使用者端不會收到更新。

## License

MIT
