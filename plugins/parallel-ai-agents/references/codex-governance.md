# Codex Governance Resolution（#23，v2.20.0+）

pai 自家 skills 的 codex leg（cross-model lens）**深度整合 codex-pro 的治理契約** — model / effort 不在 pai 樹內 pin，由 codex-pro 的 EXTERNAL-CONSUMER CONTRACT（`references/profile-contract.md` + `references/defaults.json`，0.7.0+）解析。本檔是 pai 端解析流程的 canonical — **skills 引用本檔，不內嵌分歧複本**。同形先例：issue-driven-dev#264。

## 何時解析

**僅當該次呼叫 `codexEnabled: true`**（或 skill 的 `--codex` flag 生效）。codexEnabled=false 的路徑不查 codex-pro、無此依賴。

## 解析流程

```bash
MIN_CODEX_PRO="0.7.0"   # defaults.json + profile-contract 起點（codex-pro#7）
CP_DIR=$(ls -d ~/.claude/plugins/cache/codex-pro/codex-pro/*/ 2>/dev/null | grep -E '/[0-9]+\.[0-9]+\.[0-9]+/$' | sort -V | tail -1)
CP_VER=$(basename "$CP_DIR" 2>/dev/null)
CP_DEFAULTS="${CP_DIR}references/defaults.json"

# Gate（fail-fast — codexEnabled 表示使用者要跨模型驗證，靜默跑錯 model 比失敗糟）：
if [ ! -f "$CP_DEFAULTS" ] || [ "$(printf '%s\n%s\n' "$MIN_CODEX_PRO" "$CP_VER" | sort -V | head -1)" != "$MIN_CODEX_PRO" ]; then
  echo "✗ codex governance unavailable（codex-pro 缺席 / $CP_VER < $MIN_CODEX_PRO / defaults.json 缺檔）" >&2
  echo "  Install (one step): claude plugin install codex-pro@codex-pro" >&2
  echo "  （或改跑 codexEnabled=false — Claude-only ensemble 不需此依賴）" >&2
  exit 1
fi

# 解析（per codex-pro profile-contract.md §2：defaults.json 起底 → ~/.codex-pro/profile.yaml → ./.codex-pro/profile.yaml，per-field 高層蓋低層）：
CODEX_MODEL=$(python3 -c "import json;print(json.load(open('$CP_DEFAULTS'))['model'])")
CODEX_EFFORT=$(python3 -c "import json;print(json.load(open('$CP_DEFAULTS'))['effort'])")
# profile.yaml overlay（扁平 YAML regex parse，不依賴 PyYAML）：
for PF in "$HOME/.codex-pro/profile.yaml" "./.codex-pro/profile.yaml"; do
  [ -f "$PF" ] || continue
  M=$(grep -E '^model:' "$PF" | head -1 | sed 's/^model:[[:space:]]*//'); [ -n "$M" ] && CODEX_MODEL="$M"
  E=$(grep -E '^effort:' "$PF" | head -1 | sed 's/^effort:[[:space:]]*//'); [ -n "$E" ] && CODEX_EFFORT="$E"
done
```

解析值以 Workflow args `codexModel` / `codexEffort` 傳入 engine（#22 契約），或以顯式 `--model` / `--effort` 傳給 `bin/codex-call` 直呼。

## Baked fallbacks 的地位

engine 的 args 預設值與 `bin/codex-call` 的內建 default 是**治理 snapshot**（release 當下 codex-pro defaults 的快照），只服務不傳參的 legacy caller — **authoritative source 永遠是 codex-pro 的 `defaults.json`**。換代時 snapshot 隨 release 更新，但 skills 走本檔解析、不吃 snapshot。
