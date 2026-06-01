#!/usr/bin/env bash
# Regenerate references/builtin-lenses.csv from the harness PROFILES.
#
# builtin-lenses.csv is a READ-ONLY reference of the built-in reviewer lenses (a catalog you can
# --include or model your own --lens after). It does NOT drive the harness — the source of truth for
# built-in lenses is the PROFILES object in workflows/ensemble-workflow.js (the workflow runtime has
# no filesystem access, so it cannot read a CSV; editing this CSV changes nothing). Run this after
# editing PROFILES to keep the catalog in sync.
#
# Extraction approach: take the pure-definitions region (everything BEFORE "// ── Orchestration ──",
# which is where runtime globals phase()/agent()/parallel()/args/log appear), neutralise the meta
# export, append `export { PROFILES }`, and let the real JS engine evaluate it (PROFILES' focus
# strings use '...'+'...' concatenation, so a regex/brace parse would be fragile — eval is exact).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
harness="$here/../workflows/ensemble-workflow.js"
out="$here/builtin-lenses.csv"
tmp="$(mktemp -d)/profiles.mjs"
trap 'rm -rf "$(dirname "$tmp")"' EXIT

awk '/^\/\/ ── Orchestration ──/{exit} {print}' "$harness" | sed 's/^export const meta/const meta/' > "$tmp"
echo 'export { PROFILES }' >> "$tmp"

node --input-type=module <<NODE
import { PROFILES } from '${tmp}'
import { writeFileSync } from 'fs'
const esc = (s) => '"' + String(s).replace(/"/g, '""') + '"'
const rows = ['profile,key,focus,needsSrt']
for (const [pname, p] of Object.entries(PROFILES)) {
  for (const l of (p.lenses || [])) {
    rows.push([pname, l.key, esc(l.focus), l.needsSrt ? 'true' : 'false'].join(','))
  }
}
writeFileSync('${out}', rows.join('\n') + '\n')
console.log('wrote', rows.length - 1, 'built-in lenses →', '${out}')
NODE
