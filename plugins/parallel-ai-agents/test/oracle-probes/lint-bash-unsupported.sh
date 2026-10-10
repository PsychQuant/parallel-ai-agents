#!/usr/bin/env bash
# 神諭反向探針用的假 lint（R42 WP6）：宣告一個沒有任何平台會用的 bash 版本。神諭啟動時比對自己用的 bash 與 lint 檔頭的
# 支援集合，不符就具名退出——lint 的詞法模型（`${ cmd; }`、`compgen` 的兩份集合）是對特定版本寫的。
# ORACLE-BASH-SUPPORTED: 4.0
# 「不在 `--strict` 的正面文法裡」「卻沒有跑在 pipefail 之下」只為神諭的耦合檢查而出現在這裡。
exit 0
