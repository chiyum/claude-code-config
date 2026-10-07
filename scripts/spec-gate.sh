#!/bin/bash
# spec-gate: 外部規格模式下，每個 gate 轉換前的 SPEC 漂移檢查（包裝 verify-external-spec.py）
# 用法: bash ~/.claude/scripts/spec-gate.sh <state.json> [gate 名稱]
#   例: bash ~/.claude/scripts/spec-gate.sh ~/.claude/state/20260908-xxx.json "reviewer 前"
# 退出碼: 0=通過（state 記 last_spec_gate）
#         7=SPEC_DRIFT（state 標 blocked_spec_drift，印舊 hash / 新 hash / 路徑 / 目前步驟）
#         其他非 0=驗證器的錯誤碼（state 標 blocked_spec_invalid）
#         非外部規格模式的 state → 直接 0（原生模式不受影響）
# 規約見 ~/.claude/acceptance/EXTERNAL_SPEC_PROTOCOL.md

STATE="$1"; GATE="${2:-unnamed}"
if [ -z "$STATE" ] || [ ! -f "$STATE" ]; then
  echo "用法: spec-gate.sh <state.json> [gate 名稱]"; exit 64
fi
command -v jq >/dev/null 2>&1 || { echo "缺 jq"; exit 64; }

MODE=$(jq -r '.spec_mode // empty' "$STATE")
if [ "$MODE" != "external" ]; then
  echo "state 非外部規格模式（spec_mode=${MODE:-無}），spec-gate 跳過"; exit 0
fi

SPEC=$(jq -r '.spec_path // empty' "$STATE")
HASH=$(jq -r '.spec_sha256 // empty' "$STATE")
PRODUCT=$(jq -r '.product // empty' "$STATE")
CONFIRM=$(jq -r '.environment_confirmed // empty' "$STATE")
STEP=$(jq -r '.current_step // empty' "$STATE")
if [ -z "$SPEC" ] || [ -z "$HASH" ]; then
  echo "❌ state 缺 spec_path / spec_sha256，無法做漂移檢查"; exit 4
fi

ARGS=(--spec "$SPEC" --expected-sha256 "$HASH")
[ -n "$PRODUCT" ] && ARGS+=(--expected-product "$PRODUCT")
[ -n "$CONFIRM" ] && ARGS+=(--confirm-environment "$CONFIRM")
# 測試 fixture 用：指向暫存的產品目錄；正式流程不設此變數，走 ~/.claude/products
[ -n "${SPEC_PRODUCTS_DIR:-}" ] && ARGS+=(--products-dir "$SPEC_PRODUCTS_DIR")

OUT=$(python3 "$HOME/.claude/scripts/verify-external-spec.py" "${ARGS[@]}" 2>/dev/null)
RC=$?
NOW=$(date +%s); NOW_ISO=$(date -Iseconds)

if [ "$RC" -eq 0 ]; then
  tmp=$(mktemp); jq --arg g "$GATE" --arg t "$NOW_ISO" --argjson n "$NOW" \
    '.last_spec_gate = {gate: $g, at: $t, result: "pass"} | .updated_at = $n' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
  echo "✅ spec-gate [$GATE] 通過：SPEC hash 未漂移（${HASH:0:12}…）"
  exit 0
fi

ERR=$(echo "$OUT" | jq -r '.error // "UNKNOWN"')
MSG=$(echo "$OUT" | jq -r '.message // empty')
if [ "$ERR" = "SPEC_DRIFT" ]; then
  ACTUAL=$(echo "$OUT" | jq -r '.details.actual_sha256 // empty')
  tmp=$(mktemp); jq --arg g "$GATE" --arg t "$NOW_ISO" --argjson n "$NOW" --arg a "$ACTUAL" \
    '.status = "blocked_spec_drift" | .blocked_reason = "SPEC_DRIFT" | .spec_drift = {gate: $g, at: $t, expected_sha256: .spec_sha256, actual_sha256: $a} | .last_spec_gate = {gate: $g, at: $t, result: "SPEC_DRIFT"} | .updated_at = $n' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
  cat <<EOF

SPEC_DRIFT

Spec path：$SPEC
目前步驟：$STEP（gate：$GATE）
run 綁定 hash（舊）：$HASH
目前 SPEC hash（新）：${ACTUAL:-無法計算}
說明：$MSG

已停止：不得繼續 architect / review / QA / push / 部署；state 已標 blocked_spec_drift。
不得自行接受新版本。請規格治理者確認變動來源；若為正式變更，走 Change Request 開新版本目錄後由使用者重新啟動 run。
EOF
  exit 7
fi

tmp=$(mktemp); jq --arg g "$GATE" --arg t "$NOW_ISO" --argjson n "$NOW" --arg e "$ERR" \
  '.status = "blocked_spec_invalid" | .blocked_reason = $e | .last_spec_gate = {gate: $g, at: $t, result: $e} | .updated_at = $n' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
echo "❌ spec-gate [$GATE] 失敗：$ERR — $MSG"
echo "$OUT" | jq -c '.details // {}'
exit "$RC"
