#!/usr/bin/env bash
# Claude Code Stop hook：每次 Claude 完成回覆時，將最後一段文字回覆送到 Slack
# 設計重點：
#   - 不阻塞 Claude（任何錯誤都靜默 exit 0）
#   - 用 timeout 避免 Slack 慢時卡住整個 session
#   - 不截斷內容：使用 top-level text 欄位（支援至 40000 字元），完整傳送

set -u

# Webhook URL 從外部檔讀取（避免硬編碼進此腳本，方便輪替）
WEBHOOK_FILE="$HOME/.claude/hooks/slack-webhook.url"

if [ ! -r "$WEBHOOK_FILE" ]; then
  exit 0
fi
WEBHOOK_URL=$(tr -d '\n\r' < "$WEBHOOK_FILE")
[ -z "$WEBHOOK_URL" ] && exit 0

# 讀取 Stop hook 從 stdin 傳入的 JSON payload
payload=$(cat)
transcript_path=$(printf '%s' "$payload" | jq -r '.transcript_path // empty' 2>/dev/null)
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
session_id=$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null | cut -c1-8)

if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  exit 0
fi

# 從 transcript JSONL 反向找最後一段 assistant 文字回覆
# 跳過僅有 tool_use 的訊息（那不是給使用者的回覆）
last_text=$(tail -r "$transcript_path" 2>/dev/null | \
  jq -r 'select(.type=="assistant") | .message.content // [] | map(select(.type=="text") | .text) | join(" ") | select(length > 0)' 2>/dev/null | \
  head -n 1)

if [ -z "$last_text" ]; then
  last_text="(本次無文字回覆，可能只執行了工具呼叫)"
fi

project_name=$(basename "${cwd:-unknown}")

# 組 Slack payload（用 jq 確保正確跳脫）
# 完整回覆放在 top-level text 欄位（支援至 40000 字元），不做截斷
slack_payload=$(jq -n \
  --arg proj "$project_name" \
  --arg sid "${session_id:-unknown}" \
  --arg text "$last_text" \
  '{
    text: ("Claude 完成回覆 — " + $proj + "  ·  Session " + $sid + "\n\n" + $text)
  }')

# 5 秒 timeout，背景送出，不影響 Claude session 結束
curl -s --max-time 5 -X POST \
  -H 'Content-type: application/json' \
  --data "$slack_payload" \
  "$WEBHOOK_URL" >/dev/null 2>&1 &

exit 0
